"""Explicit, bounded conversion of records created by the original importer."""

import re
from dataclasses import dataclass

from django.db import transaction
from django.db.models.deletion import Collector, ProtectedError

from .catalogue import (
    LEGACY_ATTRIBUTES, LEGACY_CLASS_SLUG, LEGACY_PARTNER_CODE, SOURCE,
    OscarImporter, description_html,
)
from .models import CatalogueSource
from .specifications import extract_specifications
from .sql_dump import ImportDataError


@dataclass
class CleanupItem:
    product: object
    stock: object
    source_id: int
    metadata: dict
    specifications: dict
    image: object


def prepare_cleanup(importer, product_ids):
    importer.require_mapping_schema()
    watch = importer.watch_class()
    partner = importer.partner()
    items, skipped = [], []
    for product_id in sorted(set(product_ids)):
        product = importer.models['Product'].objects.filter(pk=product_id).first()
        if product is None:
            raise ImportDataError(f'Product {product_id} does not exist.')
        mapping = CatalogueSource.objects.filter(product=product).first()
        if mapping:
            if (mapping.source != SOURCE or product.product_class_id != watch.pk
                    or mapping.stockrecord.product_id != product.pk
                    or mapping.stockrecord.partner_id != (partner.pk if partner else None)):
                raise ImportDataError(f'Product {product_id}: conflicting internal mapping.')
            skipped.append(product_id)
            continue
        match = re.fullmatch(r'wc-abdeen-([1-9]\d*)', product.upc or '')
        if (not match or product.product_class_id is None
                or product.product_class.slug != LEGACY_CLASS_SLUG
                or product.structure != product.STANDALONE):
            raise ImportDataError(f'Product {product_id} is not a verified legacy import.')
        source_id = int(match[1])
        values = dict(product.attribute_values.filter(
            attribute__product_class=product.product_class, attribute__code__in=LEGACY_ATTRIBUTES,
            attribute__type='text',
        ).values_list('attribute__code', 'value_text'))
        if set(values) != set(LEGACY_ATTRIBUTES) or values['wc_source_id'] != str(source_id):
            raise ImportDataError(f'Product {product_id}: legacy metadata does not match its source ID.')
        if CatalogueSource.objects.filter(source=SOURCE, source_id=source_id).exists():
            raise ImportDataError(f'Product {product_id}: source ID already mapped elsewhere.')
        stocks = list(product.stockrecords.select_related('partner'))
        if len(stocks) != 1 or stocks[0].partner.code != LEGACY_PARTNER_CODE:
            raise ImportDataError(f'Product {product_id}: unexpected supplier or stock records.')
        stock = stocks[0]
        if stock.num_allocated:
            raise ImportDataError(f'Product {product_id}: active stock allocations; review manually.')
        if partner and partner.stockrecords.filter(partner_sku=stock.partner_sku).exists():
            raise ImportDataError(f'Product {product_id}: SKU collision at Abdeen Watches.')
        paths = [tuple(category.get_ancestors().values_list('name', flat=True)) + (category.name,)
                 for category in product.categories.all()]
        specs = extract_specifications(description_html(product.description), categories=paths)
        importer.validate_specifications(watch, specs, product)
        image = product.images.filter(code=f'{product.upc}-thumbnail').first()
        if image and importer.models['ProductImage'].objects.filter(
                code=f'catalogue-image-{product.pk}').exclude(pk=image.pk).exists():
            raise ImportDataError(f'Product {product_id}: image code collision.')
        items.append(CleanupItem(product, stock, source_id, {
            'regular_price': values['wc_regular_price'], 'sale_price': values['wc_sale_price'],
            'stock_status': values['wc_stock_status'],
        }, specs, image))
    return items, skipped


def delete_unreferenced(instance):
    """Delete a container only if Django would delete exactly that row."""
    collector = Collector(using=instance._state.db)
    try:
        collector.collect([instance])
    except ProtectedError:
        return False
    if (any(model is not type(instance) and objects for model, objects in collector.data.items())
            or any(queryset.exists() for queryset in collector.fast_deletes)
            or any(batch.exists() if hasattr(batch, 'exists') else bool(batch)
                   for batches in collector.field_updates.values() for batch in batches)):
        return False
    # Including nullable relations: even a SET_NULL change is unrelated data.
    instance.delete()
    return True


def cleanup_legacy_products(product_ids, *, apply=False):
    importer = OscarImporter()
    with transaction.atomic():
        items, skipped = prepare_cleanup(importer, product_ids)
        report = {'products': [item.product.pk for item in items], 'skipped': skipped,
                  'removed': [], 'retained': [],
                  'specifications': {item.product.pk: item.specifications for item in items}}
        if not apply or not items:
            return report
        watch = importer.watch_class()
        partner = importer.partner(create=True)
        legacy_classes = {item.product.product_class_id for item in items}
        legacy_partners = {item.stock.partner_id for item in items}
        for item in items:
            product = item.product
            CatalogueSource.objects.create(
                source=SOURCE, source_id=item.source_id, product=product,
                stockrecord=item.stock, image=item.image, metadata=item.metadata)
            # Remove only proven legacy metadata values on these selected products.
            product.attribute_values.filter(
                attribute__product_class_id=product.product_class_id,
                attribute__code__in=LEGACY_ATTRIBUTES).delete()
            product.product_class = watch
            product.upc = None
            product.attr.invalidate()
            importer.set_specifications(product, item.specifications)
            product.full_clean()
            product.save()
            item.stock.partner = partner
            item.stock.full_clean()
            item.stock.save(update_fields=['partner'])
            if item.image:
                item.image.code = f'catalogue-image-{product.pk}'
                item.image.save(update_fields=['code'])
        # Only containers used by this verified batch are eligible for removal.
        for product_class in importer.models['ProductClass'].objects.filter(pk__in=legacy_classes):
            if product_class.products.exists():
                report['retained'].append('Legacy product type still has products.')
                continue
            for attribute in product_class.attributes.filter(code__in=LEGACY_ATTRIBUTES):
                if delete_unreferenced(attribute):
                    report['removed'].append(f'Unused attribute {attribute.code}')
            if delete_unreferenced(product_class):
                report['removed'].append('Empty legacy product type')
            else:
                report['retained'].append('Legacy product type has other references; retained.')
        for old_partner in importer.models['Partner'].objects.filter(pk__in=legacy_partners):
            if delete_unreferenced(old_partner):
                report['removed'].append('Empty legacy partner')
            else:
                report['retained'].append('Legacy partner has other references; retained.')
        return report


def remove_generic_watch_categories(product_ids, *, apply=False, delete_empty=False):
    """Detach only generic root categories from explicitly verified imports."""
    importer = OscarImporter()
    importer.require_mapping_schema()
    selected = set(product_ids)
    if not selected or any(product_id <= 0 for product_id in selected):
        raise ImportDataError('Explicit positive Oscar product IDs are required.')
    with transaction.atomic():
        mapped = set(CatalogueSource.objects.filter(
            source=SOURCE, product_id__in=selected).values_list('product_id', flat=True))
        if mapped != selected:
            raise ImportDataError('Every selected product must have a verified internal import mapping; '
                                  f'unmapped IDs: {sorted(selected - mapped)}.')
        categories = [category for category in importer.models['Category'].get_root_nodes()
                      if category.name.strip().casefold() in {'watches', 'all watches'}]
        through = importer.models['Product'].categories.through
        links = through.objects.filter(product_id__in=selected, category_id__in=[c.pk for c in categories])
        report = {'links': list(links.order_by('product_id', 'category_id').values_list(
            'product_id', 'category_id', 'category__name')), 'deleted': [], 'retained': []}
        if not apply:
            return report
        # Delete only these join rows; all other product/category links stay intact.
        links.delete()
        if delete_empty:
            for category in categories:
                category_id, name = category.pk, category.name
                # Treebeard deletes whole subtrees, which Django's collector cannot see.
                if category.get_descendants().exists() or not delete_unreferenced(category):
                    report['retained'].append((category_id, name))
                else:
                    report['deleted'].append((category_id, name))
        return report
