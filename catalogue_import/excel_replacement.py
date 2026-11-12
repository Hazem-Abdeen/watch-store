"""Reviewable local cleanup, verified backup, and conservative idempotent writes."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
from tempfile import TemporaryDirectory

from django.conf import settings
from django.db import connection
from django.db.models.deletion import Collector
from django.db.models.signals import post_delete
from django.utils.text import slugify
from oscar.core.loading import get_model

from .catalogue import OscarImporter, SOURCE
from .excel import ATTRIBUTES, digest
from .models import CatalogueSource, ExcelCatalogueEntry
from .media_backup import backup_media
from .sql_dump import ImportDataError


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def cleanup_inventory():
    Product = get_model('catalogue', 'Product')
    Stock = get_model('partner', 'StockRecord')
    mappings = CatalogueSource.objects.filter(source=SOURCE)
    ids = list(mappings.order_by('product_id').values_list('product_id', flat=True))
    stocks = Stock.objects.filter(product_id__in=ids)
    result = {'product_ids': ids, 'products': list(Product.objects.filter(pk__in=ids).order_by('pk').values()),
              'stockrecords': list(stocks.order_by('pk').values()),
              'source_mappings': list(mappings.order_by('pk').values()), 'relationships': []}
    for model, targets in [(Product, ids), (Stock, list(stocks.values_list('pk', flat=True)))]:
        for relation in model._meta.related_objects:
            if relation.many_to_many:
                continue  # Through models are also present as reverse FK relations.
            field = relation.field
            query = relation.related_model._default_manager.filter(**{field.attname + '__in': targets})
            if query.exists():
                result['relationships'].append({
                    'model': relation.related_model._meta.label, 'field': field.name,
                    'on_delete': field.remote_field.on_delete.__name__,
                    'rows': list(query.order_by('pk').values()),
                })
    result['unmapped_product_ids'] = list(Product.objects.exclude(pk__in=ids).exclude(
        pk__in=ExcelCatalogueEntry.objects.values('product_id')).values_list('pk', flat=True))
    return result


def schema_preflight(validation):
    """Validate class/attribute/category compatibility before any destructive work."""
    importer = OscarImporter()
    ProductClass = get_model('catalogue', 'ProductClass')
    for row in validation['rows']:
        classes = ProductClass.objects.filter(name__iexact=row['type'])
        if classes.count() > 1:
            raise ImportDataError(f'Ambiguous product class: {row["type"]}')
        product_class = classes.first()
        if product_class:
            if not product_class.track_stock or not product_class.requires_shipping:
                raise ImportDataError(f'{row["type"]} must require shipping and retain stock tracking for existing products.')
            for attribute in product_class.attributes.all():
                if attribute.required and not row['attributes'].get(attribute.code):
                    raise ImportDataError(f'Row {row["row"]}: missing required {attribute.name}.')
                if attribute.code in row['attributes'] and attribute.type != 'text':
                    raise ImportDataError(f'Attribute {attribute.code} must be reviewed; expected text.')
        for path in row['categories']:
            importer.category(path, create=False)
    importer.partner()


def backup_local(directory, inventory):
    if connection.vendor != 'sqlite' or not settings.DEBUG:
        raise ImportDataError('Replacement is restricted to DEBUG=True local SQLite.')
    if connection.in_atomic_block:
        raise ImportDataError('Create the backup outside the replacement transaction.')
    destination = Path(directory) / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    destination.mkdir(parents=True, exist_ok=False)
    database = Path(connection.settings_dict['NAME']).resolve()
    with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as source:
        with sqlite3.connect(destination / 'db.sqlite3') as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ImportDataError('Database backup failed integrity check.')
    # Prove that the SQLite backup can be restored independently, too.
    with TemporaryDirectory(prefix='abdeen-db-restore-') as temporary:
        restored = Path(temporary) / 'db.sqlite3'
        shutil.copy2(destination / 'db.sqlite3', restored)
        with sqlite3.connect(restored) as test_database:
            if test_database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ImportDataError('Restored database failed integrity check.')
    manifest = backup_media(settings.MEDIA_ROOT, destination / 'media.tar.gz')
    (destination / 'media-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (destination / 'restore-verification.json').write_text(json.dumps({
        'sqlite_integrity': 'ok', 'media_restored_and_verified': True,
        'files': sum(e['type'] == 'file' for e in manifest.values()),
        'symlinks': sum(e['type'] == 'symlink' for e in manifest.values()),
    }, indent=2) + '\n')
    (destination / 'cleanup-before.json').write_text(json.dumps(inventory, default=str, indent=2) + '\n')
    checksums = {p.name: digest(p) for p in destination.iterdir() if p.is_file()}
    (destination / 'checksums.json').write_text(json.dumps(checksums, indent=2) + '\n')
    return destination


def clean_old_catalogue(inventory):
    """Caller holds the all-or-nothing replacement transaction and has backed up."""
    if fingerprint(cleanup_inventory()) != fingerprint(inventory):
        raise ImportDataError('Catalogue or related records changed since preflight. Prepare a fresh report.')
    ids = inventory['product_ids']
    if inventory['unmapped_product_ids']:
        raise ImportDataError('Unmapped products exist; refusing to delete or silently retain an unreviewed catalogue.')
    if not ids:
        return {}
    Product = get_model('catalogue', 'Product')
    Line = get_model('order', 'Line')
    # Keep historical order totals, titles, SKUs, addresses and COD sources.
    # Explicitly retire test allocations before their stock records disappear.
    Line.objects.filter(product_id__in=ids).update(
        product=None, stockrecord=None, num_allocated=0, allocation_cancelled=True)
    CatalogueSource.objects.filter(source=SOURCE, product_id__in=ids).delete()
    products = Product.objects.filter(pk__in=ids)
    collector = Collector(using=connection.alias)
    collector.collect(products)
    allowed = {
        'catalogue.Product', 'catalogue.ProductImage', 'catalogue.ProductAttributeValue',
        'catalogue.ProductCategory', 'catalogue.ProductRecommendation',
        'partner.StockRecord', 'partner.StockAlert', 'basket.Line', 'basket.LineAttribute',
        'offer.RangeProduct', 'offer.Range_excluded_products', 'analytics.ProductRecord',
        'analytics.UserProductView', 'analytics.UserProductSearch',
        'wishlists.Line',
    }
    counts = Counter()
    for model, objects in collector.data.items():
        if objects:
            counts[model._meta.label] += len(objects)
    for queryset in collector.fast_deletes:
        if queryset.exists():
            counts[queryset.model._meta.label] += queryset.count()
    if set(counts) - allowed:
        raise ImportDataError(f'Unreviewed cascading deletion: {sorted(set(counts) - allowed)}. No changes committed.')
    for (field, value), batches in collector.field_updates.items():
        if any(batch.exists() if hasattr(batch, 'exists') else bool(batch) for batch in batches):
            if (field.model._meta.label, field.name) not in {('wishlists.Line', 'product')}:
                raise ImportDataError(f'Unreviewed relationship update: {field.model._meta.label}.{field.name}.')
    # Oscar normally deletes image files immediately in post_delete. That is
    # outside transaction rollback and can destroy shared or archived originals.
    # Disconnect only that receiver for this bounded management-command delete.
    from oscar.apps.catalogue import receivers
    Image = get_model('catalogue', 'ProductImage')
    receiver = getattr(receivers, 'delete_image_files', None)
    disconnected = receiver and post_delete.disconnect(receiver, sender=Image)
    try:
        products.delete()
    finally:
        if disconnected:
            post_delete.connect(receiver, sender=Image)
    return dict(counts)


def import_rows(validation, manifest_path, *, limit=None, initially_available=False):
    """New SKUs create products; known SKUs leave all dashboard-maintained data intact."""
    if any(issue['severity'] == 'error' for issue in validation['issues']):
        raise ImportDataError('Cannot import a workbook with unresolved validation errors.')
    importer = OscarImporter()
    Product = get_model('catalogue', 'Product')
    ProductClass = get_model('catalogue', 'ProductClass')
    Attribute = get_model('catalogue', 'ProductAttribute')
    Stock = get_model('partner', 'StockRecord')
    Image = get_model('catalogue', 'ProductImage')
    RangeProduct = get_model('offer', 'RangeProduct')
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest['workbook_sha256'] != validation['workbook_sha256']:
        raise ImportDataError('Image manifest belongs to a different workbook.')
    images = {record['row']: record for record in manifest['records']}
    partner = importer.partner(create=True)
    counts = Counter()
    labels = {v: k for k, v in ATTRIBUTES.items()}
    for row in validation['rows'][:limit]:
        entry = ExcelCatalogueEntry.objects.select_related('product', 'stockrecord').filter(sku__iexact=row['sku']).first()
        if entry:
            if entry.stockrecord.product_id != entry.product_id or entry.stockrecord.partner_id != partner.pk:
                raise ImportDataError(f'SKU {row["sku"]}: inconsistent import mapping.')
            counts['preserved'] += 1
            if entry.imported_values != row['values']:
                counts['source_changes_not_applied'] += 1
            continue
        if (Product.objects.filter(upc__iexact=row['sku']).exists()
                or Stock.objects.filter(partner_sku__iexact=row['sku']).exists()):
            raise ImportDataError(f'SKU collision: {row["sku"]}; no record was merged.')
        product_class = ProductClass.objects.filter(name__iexact=row['type']).first()
        if product_class is None:
            product_class = ProductClass.objects.create(
                name=row['type'], slug=slugify(row['type']), requires_shipping=True, track_stock=True)
        product = Product(product_class=product_class, title=row['values']['Title'], upc=row['sku'],
                          slug=slugify(row['values']['Title'])[:230] or slugify(row['sku']))
        for code, value in row['attributes'].items():
            attribute, _ = Attribute.objects.get_or_create(product_class=product_class, code=code,
                defaults={'name': labels[code], 'type': 'text', 'required': False})
            setattr(product.attr, attribute.code, value)
        product.full_clean()
        product.save()
        for path in row['categories']:
            product.categories.add(importer.category(path))
        if row['type'] == 'Accessory':
            product.categories.add(importer.category(('Accessories',)))
            if row['brand'] == 'GUY LAROCHE':
                product.categories.add(importer.category(('Brands', 'GUY LAROCHE', 'Jewellery & Accessories')))
        stock = Stock(product=product, partner=partner, partner_sku=row['sku'], price_currency='JOD',
                      price=row['price'], regular_price=row['regular_price'], availability_only=True,
                      is_available=initially_available, num_in_stock=None, num_allocated=0)
        stock.full_clean()
        stock.save()
        ExcelCatalogueEntry.objects.create(sku=row['sku'], product=product, stockrecord=stock,
            imported_values=row['values'], workbook_sha256=validation['workbook_sha256'])
        record = images.get(row['row'], {})
        if (record.get('sku'), record.get('model'), record.get('brand')) != (row['sku'], row['model'], row['brand']):
            raise ImportDataError(f'Row {row["row"]}: stale image mapping.')
        if record.get('status') == 'verified':
            source = (manifest_path.parent / record['file']).resolve()
            if not source.is_relative_to(manifest_path.parent.resolve()) or digest(source) != record['sha256']:
                raise ImportDataError('Archived image integrity check failed.')
            # Deterministic content-addressed media files survive rollback and reruns.
            # Never change an existing ProductImage: staff images always win on rerun.
            relative = Path('images/catalogue-excel') / source.name
            destination = Path(settings.MEDIA_ROOT) / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and digest(destination) != record['sha256']:
                raise ImportDataError('Existing image destination has different bytes.')
            if not destination.exists():
                shutil.copy2(source, destination)
            Image.objects.create(product=product, original=str(relative), display_order=0,
                                 code=f'excel-{row["sku"]}')
            counts['images'] += 1
        for membership in record.get('ranges', []):
            RangeProduct.objects.get_or_create(product=product, range_id=membership['range_id'],
                                              defaults={'display_order': membership['display_order']})
            counts['range_memberships'] += 1
        counts['created'] += 1
    return dict(counts)
