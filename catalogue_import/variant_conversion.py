"""Explicitly selected, reviewed families only; no importing or media writes."""

import json
from pathlib import Path

from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from oscar.core.loading import get_model

from .catalogue import SOURCE, OscarImporter
from .models import CatalogueSource
from .specifications import specification_code
from .sql_dump import ImportDataError
from .variants import BRAND_ALIASES, COLORS, CORE, normalized, normalized_spec, sku_family


MANIFEST = Path(__file__).with_name('approved_variant_groups.json')
MARKER = 'approved_variant_conversion'


def approved_groups():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


def identity_snapshot(group):
    return {key: group[key] for key in ('brand', 'family', 'proposed_parent_title')} | {
        'children': [{key: child[key] for key in ('source_id', 'sku', 'title', 'specifications')}
                     for child in group['children']]}


def select_groups(path, families):
    """Revalidate status, exact reviewed membership and real SKU evidence."""
    approved = {group['family']: group for group in approved_groups()}
    if not families or len(families) != len(set(families)):
        raise ImportDataError('Select one or more distinct approved families with --groups.')
    unknown = set(families) - approved.keys()
    if unknown:
        raise ImportDataError(f'Not an approved SKU-backed family: {", ".join(sorted(unknown))}.')
    try:
        report = json.loads(Path(path).read_text(encoding='utf-8'))
        if report['rule_version'] != 1:
            raise ImportDataError('Unreviewed analysis rule version.')
        selected = []
        for family in families:
            reference = approved[family]
            matches = [g for g in report['candidates']
                       if (g['brand'], g['family']) == (reference['brand'], family)]
            if len(matches) != 1:
                raise ImportDataError(f'{family}: not exactly one candidate in the analysis.')
            group = matches[0]
            if (group['status'] != 'candidate' or group['confidence'] != 'high'
                    or group['basis'] != 'model_family' or group['review_flags']
                    or group['conflicting_specifications']
                    or identity_snapshot(group) != reference):
                raise ImportDataError(f'{family}: differs from the reviewed candidate; review again.')
            members = {c['source_id'] for c in group['children']}
            for other in report['candidates'] + report['ambiguous']:
                if other is not group and members.intersection(c['source_id'] for c in other['children']):
                    raise ImportDataError(f'{family}: overlapping or ambiguous membership.')
            for child in group['children']:
                parsed = sku_family(child['sku'], group['brand'])
                evidence = child['identifier_evidence']
                if (not parsed or parsed[0] != family or parsed[2]
                        or not any(i['source'] == 'sku_pattern' and i['family'] == family
                                   and i['value'] == child['sku'] for i in evidence)
                        or any(i['family'] != family for i in evidence)):
                    raise ImportDataError(f'{family}: child lacks reliable, unconflicted SKU evidence.')
            for code in CORE:
                values = {normalized_spec(code, c['specifications'].get(code)) for c in group['children']}
                if '' in values or len(values) != 1:
                    raise ImportDataError(f'{family}: missing/conflicting {code}.')
            axes = [code for code in COLORS
                    if all(c['specifications'].get(code) for c in group['children'])]
            signatures = {tuple(normalized_spec(code, c['specifications'][code]) for code in axes)
                          for c in group['children']}
            if len(signatures) != len(group['children']):
                raise ImportDataError(f'{family}: indistinguishable child options.')
            selected.append(group)
        return selected
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ImportDataError(f'Invalid analysis file: {exc}') from exc


def comparable(code, value):
    if code == 'brand':
        return BRAND_ALIASES.get(normalized(value), normalized(value))
    return normalized_spec(code, value)


def specifications(product):
    result = {}
    for value in product.attribute_values.select_related('attribute'):
        attribute = value.attribute
        code = specification_code(attribute.code) or specification_code(attribute.name)
        if (not code or code in result or attribute.type != 'text'
                or attribute.product_class_id != product.get_product_class().pk):
            raise ImportDataError(f'Product {product.pk}: unknown, duplicate or non-text specification.')
        result[code] = value.value
    return result


def preflight(group, importer, *, lock=False):
    """Read-only, including for dry runs. Never create then roll back to preview."""
    Product = importer.models['Product']
    watch = importer.watch_class()
    mappings = CatalogueSource.objects.filter(source=SOURCE, source_id__in=[
        c['source_id'] for c in group['children']]).order_by('pk')
    if lock:
        mappings = mappings.select_for_update()
    mappings = {m.source_id: m for m in mappings}
    missing = [c['sku'] for c in group['children'] if c['source_id'] not in mappings]
    if missing:
        raise ImportDataError('Missing imported source mappings: ' + ', '.join(missing))
    rows, categories, live_specs = [], [], []
    markers = []
    for child in group['children']:
        mapping = mappings[child['source_id']]
        products = Product.objects.all()
        if lock:
            products = products.select_for_update()
        product = products.get(pk=mapping.product_id)
        stock = mapping.stockrecord
        if (stock.product_id != product.pk or stock.partner_sku != child['sku']
                or stock.partner_id != getattr(importer.partner(), 'pk', None)
                or product.stockrecords.exclude(pk=stock.pk).exists()):
            raise ImportDataError(f'{child["sku"]}: stock/source identity mismatch or multiple suppliers.')
        if mapping.image_id and mapping.image.product_id != product.pk:
            raise ImportDataError(f'{child["sku"]}: image/source identity mismatch.')
        if product.title != child['title']:
            raise ImportDataError(f'{child["sku"]}: title changed since review.')
        specs = specifications(product)
        if set(specs) != set(child['specifications']) or any(
                comparable(code, value) != comparable(code, child['specifications'][code])
                for code, value in specs.items()):
            raise ImportDataError(f'{child["sku"]}: live specifications differ from the reviewed source.')
        if product.product_options.exists():
            raise ImportDataError(f'{child["sku"]}: product options require manual review.')
        Recommendation = get_model('catalogue', 'ProductRecommendation')
        Range = get_model('offer', 'Range')
        if Recommendation.objects.filter(Q(primary=product) | Q(recommendation=product)).exists():
            raise ImportDataError(f'{child["sku"]}: recommendations require review.')
        ranges = list(Range.objects.filter(Q(included_products=product) | Q(excluded_products=product))
                      .values_list('name', flat=True).distinct())
        if ranges:
            raise ImportDataError(f'{child["sku"]}: explicit ranges require review: {", ".join(ranges)}.')
        categories.append(set(product.categories.values_list('pk', flat=True)))
        live_specs.append(specs)
        markers.append(mapping.metadata.get(MARKER))
        rows.append((mapping, product, stock))

    # A parent never inherits a description containing one child's colors/SKU.
    shared = {code: value for code, value in live_specs[0].items()
              if code not in COLORS and all(comparable(code, specs.get(code)) == comparable(code, value)
                                           for specs in live_specs)}
    if any(code not in shared for code in (*CORE, 'brand')):
        raise ImportDataError('Core specifications are not completely shared.')
    if len({p.is_public for _, p, _ in rows}) != 1:
        raise ImportDataError('Different publication states require review.')
    parent = None
    if any(markers):
        if not all(isinstance(m, dict) for m in markers) or any(m != markers[0] for m in markers):
            raise ImportDataError('Partial or conflicting previous conversion metadata.')
        marker = markers[0]
        if (marker.get('version') != 1 or marker.get('family') != group['family']
                or marker.get('brand') != group['brand']
                or marker.get('source_ids') != sorted(mappings)):
            raise ImportDataError('Previous conversion has different approved membership.')
        parents = Product.objects.all()
        if lock:
            parents = parents.select_for_update()
        parent = parents.filter(pk=marker.get('parent_id')).first()
        if (not parent or parent.structure != Product.PARENT or parent.parent_id
                or parent.product_class_id != watch.pk or parent.stockrecords.exists()
                or set(parent.children.values_list('pk', flat=True)) != {p.pk for _, p, _ in rows}
                or specifications(parent) != shared
                or set(parent.categories.values_list('pk', flat=True)) != set(marker['category_ids'])):
            raise ImportDataError('Existing parent no longer matches the approved conversion.')
        if any(p.structure != Product.CHILD or p.parent_id != parent.pk or p.product_class_id
               or cats for (_, p, _), cats in zip(rows, categories)):
            raise ImportDataError('Existing children no longer match the approved conversion.')
        category_ids = marker['category_ids']
    else:
        if any(p.structure != Product.STANDALONE or p.parent_id or p.product_class_id != watch.pk
               or p.children.exists() for _, p, _ in rows):
            raise ImportDataError('Only mapped standalone Watches or this exact prior conversion are allowed.')
        if not categories[0] or any(cats != categories[0] for cats in categories):
            raise ImportDataError('Category memberships differ or are empty; preserve them by reviewing manually.')
        category_ids = sorted(categories[0])
        slug = slugify(f'imported-variants-{group["brand"]}-{group["family"]}')
        if Product.objects.filter(slug=slug).exists():
            raise ImportDataError('Proposed parent slug already exists without matching conversion metadata.')
    return {'group': group, 'rows': rows, 'parent': parent, 'watch': watch,
            'shared': shared, 'category_ids': category_ids}


def apply_plan(plan, importer):
    if plan['parent']:
        return plan['parent']
    group = plan['group']
    Product = importer.models['Product']
    parent = Product(structure=Product.PARENT, product_class=plan['watch'],
                     title=group['proposed_parent_title'],
                     slug=slugify(f'imported-variants-{group["brand"]}-{group["family"]}'),
                     description='', is_public=plan['rows'][0][1].is_public)
    importer.set_specifications(parent, plan['shared'])
    parent.full_clean()
    parent.save()
    parent.categories.set(plan['category_ids'])
    marker = {'version': 1, 'brand': group['brand'], 'family': group['family'],
              'parent_id': parent.pk, 'source_ids': sorted(m.source_id for m, _, _ in plan['rows']),
              'category_ids': plan['category_ids']}
    for mapping, product, _ in plan['rows']:
        # Oscar forbids direct child categories/classes. The identical category
        # set is now inherited; all original assignments are retained in metadata.
        product.categories.clear()
        product.structure = Product.CHILD
        product.parent = parent
        product.product_class = None
        product.upc = product.upc or None  # NullCharField uniqueness validation
        product.full_clean()
        product.save(update_fields=['structure', 'parent', 'product_class'])
        mapping.metadata = {**mapping.metadata, MARKER: marker}
        mapping.save(update_fields=['metadata'])
    parent.full_clean()
    return parent


def convert_groups(groups, *, apply=False, emit=lambda message: None):
    importer = OscarImporter()
    importer.require_mapping_schema()
    # All selected groups preflight before any writes; any apply failure rolls
    # back every selected group. Row locks protect mapping/parent identity on
    # databases supporting SELECT FOR UPDATE; SQLite serializes writers.
    with transaction.atomic():
        plans, blocked = [], []
        for group in groups:
            emit(f'PARENT {group["proposed_parent_title"]} [family={group["family"]}] / Watch / no stock record')
            emit('  QUALIFIES: every child has the reviewed SKU family; all six core specifications '
                 'match; color options are unique; no ambiguity or title-only identity.')
            emit(f'  Matching core: {group["shared_specifications"]!r}; '
                 f'color differences: {", ".join(group["option_axes"])}')
            for child in group['children']:
                emit(f'  CHILD source={child["source_id"]} SKU={child["sku"]} title={child["title"]!r}')
            try:
                plan = preflight(group, importer, lock=apply)
            except ImportDataError as exc:
                blocked.append(group['family'])
                emit(f'  BLOCKED: {exc}')
                continue
            plans.append(plan)
            for _, product, stock in plan['rows']:
                emit(f'  KEEP product={product.pk} stockrecord={stock.pk} SKU={stock.partner_sku} '
                     f'price={stock.price} {stock.price_currency} stock={stock.num_in_stock} '
                     f'allocated={stock.num_allocated} images={list(product.images.values_list("pk", "original"))}')
            emit(f'  Shared specifications: {plan["shared"]!r}; inherited categories={plan["category_ids"]}')
            emit('  ALREADY CONVERTED (no changes)' if plan['parent'] else '  READY (not yet converted)')
        if apply and blocked:
            raise ImportDataError('No changes applied: blocked selected families: ' + ', '.join(blocked))
        if apply:
            for plan in plans:
                apply_plan(plan, importer)
        return {'ready': sum(p['parent'] is None for p in plans),
                'already_converted': sum(p['parent'] is not None for p in plans), 'blocked': blocked}
