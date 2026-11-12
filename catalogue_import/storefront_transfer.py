"""Scoped, checksummed Django serialization for SQLite -> PostgreSQL.

Explicit primary keys retain Oscar URLs/tree paths/import identities. First import
requires an empty scope; only an exact replay is accepted thereafter.
"""
from collections import Counter
from datetime import timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management.color import no_style
from django.db import connection, transaction, models
from django.db.migrations.executor import MigrationExecutor

from .excel import digest
from .sql_dump import ImportDataError


LABELS = (
    'catalogue.option', 'catalogue.attributeoptiongroup', 'catalogue.attributeoption',
    'catalogue.productclass', 'catalogue.category', 'catalogue.productattribute',
    'catalogue.product', 'catalogue.productattributevalue', 'catalogue.productcategory',
    'catalogue.productrecommendation', 'catalogue.productimage',
    'partner.partner', 'partner.stockrecord', 'catalogue_import.excelcatalogueentry',
    'homepage.homeheroslide', 'homepage.brandpresentation', 'offer.range',
    'offer.rangeproduct', 'address.country',
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def checksum(value):
    return sha256(canonical(value).encode()).hexdigest()


def schema_signature():
    return {label: [(field.name, field.get_internal_type())
                    for field in [*apps.get_model(label)._meta.fields, *apps.get_model(label)._meta.many_to_many]]
            for label in LABELS}


def require_migrations():
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        raise ImportDataError('Apply reviewed code/schema migrations separately before transfer.')


def records():
    rows = []
    for label in LABELS:
        model = apps.get_model(label)
        query = model.objects.order_by('pk')
        if label.startswith('offer.'):
            query = query.filter(**({'name__in': ['Best Sellers', 'New Arrivals']} if label == 'offer.range'
                                    else {'range__name__in': ['Best Sellers', 'New Arrivals']}))
        objects = list(query)
        values = json.loads(serializers.serialize('json', objects, use_natural_foreign_keys=False,
                                                 use_natural_primary_keys=False))
        for obj, row in zip(objects, values):
            # Django's JSON encoder truncates datetimes to milliseconds. Keep
            # source microseconds and use one representation on both backends.
            for field in model._meta.fields:
                if isinstance(field, models.DateTimeField) and (value := getattr(obj, field.attname)) is not None:
                    row['fields'][field.name] = value.astimezone(timezone.utc).isoformat(timespec='microseconds')
            if label == 'partner.partner':
                # Partner membership is auth/customer data, never transferable.
                row['fields']['users'] = []
            for field in model._meta.many_to_many:
                if field.name in row['fields']:
                    row['fields'][field.name] = sorted(row['fields'][field.name])
        rows.extend(values)
    return rows


def validate(rows):
    keys = set()
    for row in rows:
        if row['model'] not in LABELS:
            raise ImportDataError('Unapproved model in transfer bundle.')
        key = (row['model'], row['pk'])
        if key in keys:
            raise ImportDataError('Duplicate primary key in bundle.')
        keys.add(key)
    skus = set()
    for row in rows:
        model = apps.get_model(row['model'])
        expected = {f.name for f in model._meta.local_fields if f.serialize and not f.primary_key}
        expected |= {f.name for f in model._meta.local_many_to_many
                     if f.serialize and f.remote_field.through._meta.auto_created}
        if set(row['fields']) != expected:
            raise ImportDataError(f'Unexpected fields for {row["model"]}.')
        fields = row['fields']
        if row['model'] == 'partner.partner' and fields['users']:
            raise ImportDataError('Partner user relationships must be excluded.')
        if row['model'] == 'partner.stockrecord':
            if (not fields['availability_only'] or fields['is_available'] or
                    fields['num_in_stock'] is not None or fields['num_allocated'] not in (None, 0)):
                raise ImportDataError('All transferred stock must be unavailable without quantities/allocations.')
            sku = fields['partner_sku'].casefold()
            if not sku or sku in skus:
                raise ImportDataError('Missing or duplicate stock SKU.')
            skus.add(sku)
        if row['model'] == 'catalogue.productattributevalue' and fields['entity_object_id'] is not None:
            raise ImportDataError('Generic entity attributes need separate review.')
        for field in [*model._meta.fields, *model._meta.many_to_many]:
            if not field.is_relation or field.name not in fields:
                continue
            value = fields[field.name]
            values = value if field.many_to_many else [value]
            if any(v is not None and (field.related_model._meta.label_lower, v) not in keys for v in values):
                raise ImportDataError(f'Unresolved/out-of-scope relationship: {row["model"]}.{field.name}')


def media_references(rows):
    refs = {}
    for row in rows:
        model = apps.get_model(row['model'])
        for field in model._meta.fields:
            if isinstance(field, models.FileField) and (name := row['fields'].get(field.name)):
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or str(path) != name or '\\' in name or any(ord(c) < 32 for c in name):
                    raise ImportDataError('Unsafe media path in bundle.')
                refs.setdefault(name, []).append(f'{row["model"]}:{row["pk"]}:{field.name}')
    return refs


def verify_media(root, manifest):
    root = Path(root).resolve()
    for name, entry in manifest.items():
        path = root / name
        if (not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file() or
                path.stat().st_size != entry['size'] or digest(path) != entry['sha256']):
            raise ImportDataError(f'Missing, unsafe or changed media: {name}')


def export_bundle(directory):
    require_migrations()
    directory = Path(directory)
    if directory.exists():
        raise ImportDataError('Export directory must be new; do not overwrite a reviewed bundle.')
    with transaction.atomic():
        rows = records()
        validate(rows)
    refs = media_references(rows)
    manifest = {}
    root = Path(settings.MEDIA_ROOT).resolve()
    # Only referenced originals, never old WooCommerce leftovers or thumbnails.
    for name, references in refs.items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ImportDataError(f'Missing or unsafe referenced media: {name}')
        manifest[name] = {'sha256': digest(path), 'size': path.stat().st_size, 'references': references}
    directory.mkdir(parents=True)
    for name in manifest:
        target = directory / 'media' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    verify_media(directory / 'media', manifest)
    bundle = {'format': 1, 'schema': schema_signature(), 'records': rows, 'media': manifest,
              'counts': dict(Counter(row['model'] for row in rows))}
    bundle['sha256'] = checksum(bundle)
    (directory / 'bundle.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n')
    (directory / 'media-files.txt').write_text(''.join(name + '\n' for name in sorted(manifest)))
    return bundle


def load_bundle(directory, expected_digest):
    directory = Path(directory)
    bundle = json.loads((directory / 'bundle.json').read_text())
    declared = bundle.pop('sha256')
    if declared != expected_digest or checksum(bundle) != expected_digest:
        raise ImportDataError('Bundle checksum differs from the reviewed export.')
    if bundle['format'] != 1 or canonical(bundle['schema']) != canonical(schema_signature()):
        raise ImportDataError('Bundle schema differs from installed code.')
    validate(bundle['records'])
    references = media_references(bundle['records'])
    if set(references) != set(bundle['media']):
        raise ImportDataError('Media manifest does not match record references.')
    verify_media(directory / 'media', bundle['media'])
    return bundle


def import_bundle(directory, expected_digest, apply=False):
    require_migrations()
    if connection.vendor not in {'postgresql', 'sqlite'}:
        raise ImportDataError('Unsupported database backend.')
    bundle = load_bundle(directory, expected_digest)
    with transaction.atomic():
        if connection.vendor == 'postgresql':
            # Serialize simultaneous invocations and block ordinary writes to
            # scoped tables between the empty/exact checks and insertion.
            tables = [connection.ops.quote_name(apps.get_model(label)._meta.db_table) for label in LABELS]
            with connection.cursor() as cursor:
                cursor.execute('LOCK TABLE ' + ', '.join(sorted(tables)) + ' IN EXCLUSIVE MODE')
        current = records()
        if current:
            if canonical(current) == canonical(bundle['records']):
                verify_media(settings.MEDIA_ROOT, bundle['media'])
                return 'already imported; exact records and media verified'
            raise ImportDataError('Target transfer scope is not empty or differs from export; no records overwritten.')
        # Media must be staged and verified before any database import.
        verify_media(settings.MEDIA_ROOT, bundle['media'])
        if not apply:
            return 'dry run passed; target empty, bundle and target media verified'
        objects = list(serializers.deserialize('json', json.dumps(bundle['records'])))
        for obj in objects:
            # PKs were proved absent. Force INSERT, never Django update-or-insert.
            obj.save(using=connection.alias, force_insert=True)
        connection.check_constraints()
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [apps.get_model(label) for label in LABELS]):
                cursor.execute(sql)
            if connection.vendor == 'postgresql':
                cursor.execute('REFRESH MATERIALIZED VIEW catalogue_product_category_hierarchy')
        if canonical(records()) != canonical(bundle['records']):
            raise ImportDataError('Post-import record verification failed; rolling back.')
    return 'imported and verified; rebuild the production search index separately'
