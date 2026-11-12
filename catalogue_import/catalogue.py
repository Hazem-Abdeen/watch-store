"""Explicit catalogue mapping, source validation, and Oscar-only writes."""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.db.models import Max
from django.utils.text import slugify
from oscar.core.loading import get_model
from config.partner.pricing import valid_regular_price

from .images import download_image, uploads_url
from .models import CatalogueSource
from .specifications import SPECIFICATIONS, extract_specifications, php_attributes, specification_code
from .sql_dump import ImportDataError, source_id


PARTNER_CODE = 'abdeen-watches'
PARTNER_NAME = 'Abdeen Watches'
SOURCE = 'abdeenwatches.com'
LEGACY_CLASS_SLUG = 'woocommerce-catalogue'
LEGACY_PARTNER_CODE = 'woocommerce-abdeen'
LEGACY_ATTRIBUTES = ('wc_source_id', 'wc_regular_price', 'wc_sale_price', 'wc_stock_status')
BRANDS = {
    'casio': 'CASIO', 'lotus': 'LOTUS', 'jaguar': 'JAGUAR', 'swatch': 'SWATCH',
    'swiss military': 'SWISS MILITARY', 'santa barbara polo': 'Santa Barbara Polo',
    'freelook': 'FreeLook', 'ducati': 'DUCATI', 'daniel klein': 'Daniel Klein',
    'bigotti': 'Bigotti', 'guy laroche': 'GUY LAROCHE', 'lacoste': 'LACOSTE',
    'sergio tacchini': 'SERGIO TACCHINI', 'hanowa': 'HANOWA',
    'valentino orlandi': 'VALENTINO ORLANDI', 'lee cooper': 'LEE COOPER',
}
CASIO_CHILDREN = {'g-shock': 'G-SHOCK', 'edifice': 'Edifice',
                  'casio analog': 'CASIO ANALOG', 'casio digital': 'CASIO DIGITAL',
                  'casio digiltal': 'CASIO DIGITAL'}
GENDERS = {'for men': 'Men', 'men': 'Men', 'for women': 'Women', 'women': 'Women'}


class DescriptionHTML(HTMLParser):
    """Keep basic formatting, removing active markup, embeds and remote assets."""

    allowed = {'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li', 'div',
               'span', 'h2', 'h3', 'h4', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
               'blockquote', 'hr', 'sup', 'sub'}
    blocked = {'script', 'style', 'iframe', 'object', 'template', 'svg', 'math'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.suppressed = []

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.suppressed.append(tag)
        elif not self.suppressed and tag in self.allowed:
            self.output.append(f'<{tag}>')

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
        elif tag in self.allowed and tag not in {'br', 'hr'}:
            self.output.append(f'</{tag}>')

    def handle_data(self, data):
        if not self.suppressed:
            self.output.append(escape(data))


def description_html(value):
    parser = DescriptionHTML()
    parser.feed(value or '')
    parser.close()
    return ''.join(parser.output)


def price_value(value, label):
    if value in (None, ''):
        return None
    try:
        price = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ImportDataError(f'Invalid {label}.') from None
    # Oscar 4.2 supports two decimal places even though JOD can use three.
    if (not price.is_finite() or price < 0 or price >= Decimal('10000000000')
            or price != price.quantize(Decimal('.01'))):
        raise ImportDataError(f'{label} cannot be represented by Oscar without loss.')
    return price


@dataclass
class ProductPlan:
    source_id: int
    title: str
    description: str
    sku: str
    price: Decimal | None
    regular: Decimal | None
    sale: Decimal | None
    status: str
    categories: tuple
    image_url: str | None
    warnings: tuple
    specifications: dict
    skip_reason: str = ''

    @property
    def legacy_upc(self):
        return f'wc-abdeen-{self.source_id}'

    @property
    def source_metadata(self):
        return {'regular_price': None if self.regular is None else str(self.regular),
                'sale_price': None if self.sale is None else str(self.sale),
                'stock_status': self.status}


def category_paths(data, product_id):
    categories = {source_id(row['term_id']): row for row in data.taxonomies.values()
                  if row['taxonomy'] == 'product_cat'}

    def term_name(term_id):
        if term_id not in data.terms or not data.terms[term_id]:
            raise ImportDataError(f'Missing category term {term_id}.')
        name = unescape(data.terms[term_id]).strip()
        if len(name) > 255:
            raise ImportDataError('Category name is too long.')
        return name

    def path(term_id, visited=()):
        if term_id in visited or len(visited) > 20:
            raise ImportDataError('Cyclic or excessively deep category hierarchy.')
        if term_id not in categories:
            raise ImportDataError(f'Missing parent category {term_id}.')
        name = term_name(term_id)
        key = name.casefold()
        # Validate parent chains even for categories with explicit mappings.
        parent = categories[term_id]['parent']
        prefix = path(source_id(parent), (*visited, term_id)) if parent != '0' else ()
        if key in GENDERS:
            return (GENDERS[key],)
        if key in CASIO_CHILDREN:
            return ('Brands', 'CASIO', CASIO_CHILDREN[key])
        if key in BRANDS:
            return ('Brands', BRANDS[key])
        if key in {'all watches', 'watches'}:
            # Drop generic containers, retaining useful ancestors/descendants.
            return prefix
        if key == 'uncategorized':
            return ()
        if key == 'guy laroche jewellery & accessory':
            return ('Brands', 'GUY LAROCHE', 'Jewellery & Accessories')
        return (*prefix, name)

    result = set()
    product_types = set()
    for taxonomy_id in data.relationships.get(product_id, ()):
        row = data.taxonomies.get(taxonomy_id)
        if row is None:
            continue  # Tags, visibility, navigation and unrelated taxonomies.
        term_id = source_id(row['term_id'])
        name = term_name(term_id)
        if row['taxonomy'] == 'product_type':
            product_types.add(name.casefold())
        elif row['taxonomy'] == 'pa_gender':
            if name.casefold() in GENDERS:
                result.add((GENDERS[name.casefold()],))
        elif row['taxonomy'] == 'product_cat':
            value = path(term_id)
            if value:
                result.add(value)
    return tuple(sorted(result)), product_types


def build_plans(data, limit=None):
    plans = []
    sku_counts = Counter((data.meta.get(key, {}).get('_sku') or '').strip()
                         for key in data.products)
    for key in sorted(data.products)[:limit]:
        try:
            row = data.products[key]
            meta = data.meta.get(key, {})
            title = unescape(row['post_title'] or '').strip()
            if not title or len(title) > 255:
                raise ImportDataError('Missing or overlong product title.')
            sku = (meta.get('_sku') or '').strip()
            warnings = []
            if not sku:
                sku = f'ABDEEN-{key}'
                warnings.append('Missing SKU; using stable source-ID fallback.')
                if sku_counts[sku]:
                    raise ImportDataError('Fallback SKU conflicts with a source SKU.')
            elif sku_counts[sku] > 1:
                raise ImportDataError('Duplicate SKU among published products.')
            if len(sku) > 128:
                raise ImportDataError('SKU exceeds Oscar field length.')
            status = meta.get('_stock_status') or 'unknown'
            if status not in {'instock', 'outofstock', 'onbackorder', 'unknown'}:
                raise ImportDataError('Unrecognized stock status.')
            if status in {'unknown', 'onbackorder'}:
                warnings.append(f'{status}: mapped to zero available stock.')
            categories, product_types = category_paths(data, key)
            image_url = None
            try:
                attachment = source_id(meta.get('_thumbnail_id'))
                if attachment not in data.attachments:
                    raise ImportDataError('Thumbnail attachment is absent.')
                image_url = uploads_url(data.meta.get(attachment, {}).get('_wp_attached_file'))
            except (ImportDataError, ValueError, UnicodeError) as exc:
                warnings.append(f'Image skipped: {exc}')
            price = price_value(meta.get('_price'), '_price')
            if price is None:
                warnings.append('Missing current price; price remains unavailable.')
            description = description_html(row['post_content'])
            taxonomy_values = {}
            for taxonomy_id in data.relationships.get(key, ()):
                taxonomy = data.taxonomies.get(taxonomy_id)
                if taxonomy and specification_code(taxonomy['taxonomy']):
                    term_id = source_id(taxonomy['term_id'])
                    if term_id not in data.terms:
                        raise ImportDataError('Missing specification taxonomy term.')
                    taxonomy_values.setdefault(taxonomy['taxonomy'], []).append(data.terms[term_id])
            plans.append(ProductPlan(
                key, title, description, sku, price,
                price_value(meta.get('_regular_price'), '_regular_price'),
                price_value(meta.get('_sale_price'), '_sale_price'), status,
                categories, image_url, tuple(warnings),
                extract_specifications(description, categories=categories,
                                       attributes=php_attributes(meta.get('_product_attributes')),
                                       taxonomy_values=taxonomy_values.items()),
                'Unsupported non-simple product type.' if product_types - {'simple'} else '',
            ))
        except ImportDataError as exc:
            raise ImportDataError(f'Product {key}: {exc}') from exc
    return plans


def models():
    return {name: get_model(app, name) for app, names in (
        ('catalogue', ('Product', 'ProductClass', 'ProductAttribute', 'ProductAttributeValue',
                       'Category', 'ProductImage')),
        ('partner', ('Partner', 'StockRecord')),
    ) for name in names}


class OscarImporter:
    def __init__(self):
        self.models = models()

    def require_mapping_schema(self):
        if CatalogueSource._meta.db_table not in connection.introspection.table_names():
            raise ImportDataError('Apply the catalogue_import schema migration before using this command.')

    def watch_class(self):
        matches = self.models['ProductClass'].objects.filter(name__iexact='Watch')
        if matches.count() != 1:
            raise ImportDataError('Exactly one existing product type named Watch is required.')
        product_class = matches.get()
        if not product_class.track_stock:
            raise ImportDataError('Watch must track stock for this availability mapping.')
        return product_class

    def partner(self, create=False):
        matches = self.models['Partner'].objects.filter(name__iexact=PARTNER_NAME)
        if matches.count() > 1:
            raise ImportDataError('Multiple partners named Abdeen Watches; review manually.')
        partner = matches.first()
        if partner is None:
            if self.models['Partner'].objects.filter(code=PARTNER_CODE).exists():
                raise ImportDataError('The Abdeen Watches partner code is already in use.')
            if create:
                partner = self.models['Partner'].objects.create(name=PARTNER_NAME, code=PARTNER_CODE)
        return partner

    def attribute(self, product_class, code, create=False):
        matches = [attr for attr in product_class.attributes.all()
                   if specification_code(attr.code) == code or specification_code(attr.name) == code]
        if len(matches) > 1:
            raise ImportDataError(f'Ambiguous Watch attribute for {SPECIFICATIONS[code]}.')
        attribute = matches[0] if matches else None
        if attribute and attribute.type != 'text':
            raise ImportDataError(f'{attribute.name} must be reviewed: importer expects a text attribute.')
        if attribute is None and create:
            attribute = self.models['ProductAttribute'].objects.create(
                product_class=product_class, code=code, name=SPECIFICATIONS[code], type='text', required=False)
        return attribute

    def validate_specifications(self, product_class, specs, product=None):
        for code in specs:
            self.attribute(product_class, code)
        for attribute in product_class.attributes.filter(required=True):
            code = specification_code(attribute.code) or specification_code(attribute.name)
            if code in specs:
                continue
            existing = product.attribute_values.filter(attribute=attribute).first() if product else None
            if existing is None or existing.value in (None, ''):
                raise ImportDataError(f'Missing required Watch attribute: {attribute.name}.')

    def set_specifications(self, product, specs):
        for code, value in specs.items():
            attribute = self.attribute(product.product_class, code, create=True)
            setattr(product.attr, attribute.code, value)

    def existing(self, plan):
        mapping = CatalogueSource.objects.select_related('product', 'stockrecord').filter(
            source=SOURCE, source_id=plan.source_id).first()
        product = mapping.product if mapping else None
        if product is None and self.models['Product'].objects.filter(upc=plan.legacy_upc).exists():
            raise ImportDataError('Legacy imported product found; run normalize_imported_catalogue before importing.')
        if product and (product.product_class_id is None
                        or product.product_class_id != self.watch_class().pk
                        or product.structure != product.STANDALONE):
            raise ImportDataError(f'Product {plan.source_id}: source identifier collision.')
        partner = self.partner()
        stocks = self.models['StockRecord'].objects.filter(partner=partner)
        collision = stocks.filter(partner_sku=plan.sku).first()
        if collision and (product is None or collision.product_id != product.pk):
            raise ImportDataError(f'Product {plan.source_id}: partner SKU collision.')
        if product:
            if (mapping.stockrecord.product_id != product.pk
                    or mapping.stockrecord.partner_id != (partner.pk if partner else None)):
                raise ImportDataError('Internal source mapping does not match the product stock record.')
            if product.stockrecords.exclude(pk=mapping.stockrecord_id).exists():
                raise ImportDataError(f'Product {plan.source_id}: has another supplier; review manually.')
            owned = stocks.filter(product=product)
            if owned.count() > 1 or owned.exclude(num_allocated__isnull=True).exclude(num_allocated=0).exists():
                raise ImportDataError(f'Product {plan.source_id}: ambiguous stock or active allocations.')
        return product

    def preflight(self, plans):
        self.require_mapping_schema()
        product_class = self.watch_class()
        self.partner()
        for plan in plans:
            if plan.skip_reason:
                continue
            product = self.existing(plan)
            self.validate_specifications(product_class, plan.specifications, product)
            for path in plan.categories:
                self.category(path, create=False)

    def category(self, path, create=True):
        Category = self.models['Category']
        parent = None
        for name in path:
            nodes = parent.get_children() if parent else Category.get_root_nodes()
            matches = nodes.filter(name__iexact=name)
            if matches.count() > 1:
                raise ImportDataError('Ambiguous existing category path.')
            node = matches.first()
            if node is None:
                slug = slugify(name) or 'category'
                if nodes.filter(slug=slug).exists():
                    raise ImportDataError('Existing category slug conflicts with import.')
                if not create:
                    return None
                node = (parent.add_child if parent else Category.add_root)(name=name, slug=slug)
            parent = node
        return parent

    def import_product(self, plan):
        with transaction.atomic():
            product = self.existing(plan)
            created = product is None
            product_class = self.watch_class()
            partner = self.partner(create=True)
            if created:
                product = self.models['Product'](product_class=product_class)
            product.title = plan.title
            product.description = plan.description
            # Oscar's NullCharField reads SQL NULL as ''; normalize before unique validation.
            product.upc = product.upc or None
            # Do not re-publish products hidden by the Oscar operator on a rerun.
            product.slug = product.slug or slugify(plan.title)[:240] or 'watch'
            self.set_specifications(product, plan.specifications)
            product.full_clean()
            product.save()
            stock = self.models['StockRecord'].objects.filter(product=product, partner=partner).first()
            if stock is None:
                stock = self.models['StockRecord'](product=product, partner=partner)
            stock.partner_sku = plan.sku
            stock.price_currency = 'JOD'
            stock.price = plan.price
            # Source remains authoritative for current price (existing policy).
            # Reference prices are fill-only: never replace a maintained value.
            if stock.regular_price is None:
                stock.regular_price = valid_regular_price(plan.regular)
            stock.num_in_stock = 1 if plan.status == 'instock' else 0
            stock.full_clean()
            stock.save()
            CatalogueSource.objects.update_or_create(
                source=SOURCE, source_id=plan.source_id,
                defaults={'product': product, 'stockrecord': stock, 'metadata': plan.source_metadata},
            )
            # Additive only: retain any manually assigned categories.
            for path in plan.categories:
                for depth in range(1, len(path) + 1):
                    category = self.category(path[:depth])
                    if category.name != 'Brands' or depth != 1:
                        product.categories.add(category)
        return product, created

    def import_image(self, product, plan):
        """Core product has committed; image failure cannot roll it back."""
        if not plan.image_url:
            return False
        ProductImage = self.models['ProductImage']
        mapping = CatalogueSource.objects.get(source=SOURCE, source_id=plan.source_id, product=product)
        code = f'catalogue-image-{product.pk}'
        image = mapping.image
        if image is not None and image.product_id != product.pk:
            raise ImportDataError('Image source identifier collision.')
        digest = sha256(plan.image_url.encode()).hexdigest()[:16]
        token = f'watch-{product.pk}-{digest}'
        if (image and (mapping.image_url == plan.image_url
                       or f'{plan.legacy_upc}-{digest}' in PurePosixPath(image.original.name).name)
                and image.original.storage.exists(image.original.name)):
            return False
        content, extension = download_image(plan.image_url)
        if image is None:
            maximum = product.images.aggregate(value=Max('display_order'))['value']
            image = ProductImage(product=product, code=code,
                                 display_order=0 if maximum is None else maximum + 1)
        saved_name = None
        try:
            with transaction.atomic():
                image.original.save(f'{token}.{extension}', ContentFile(content), save=False)
                saved_name = image.original.name
                image.save()
                mapping.image = image
                mapping.image_url = plan.image_url
                mapping.save(update_fields=['image', 'image_url'])
        except Exception:
            # Only remove the newly written file if its DB transaction failed.
            if saved_name:
                image.original.storage.delete(saved_name)
            raise
        # Replaced files are deliberately retained: never delete existing media.
        return True
