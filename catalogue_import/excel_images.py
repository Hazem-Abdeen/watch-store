"""Conservative identity checks and independent, content-addressed photo archive."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote

from django.conf import settings
from oscar.core.loading import get_model
from PIL import Image

from .catalogue import SOURCE
from .excel import canonical_brand, digest
from .models import CatalogueSource
from .images import uploads_url
from .sql_dump import load_catalogue, ImportDataError


def normalized_fact(value):
    value = value.casefold().strip().replace('grey', 'gray')
    value = value.replace('st.steel', 'stainless steel').replace('st. steel', 'stainless steel')
    value = re.sub(r'\s*\([^)]*\)', '', value)
    return re.sub(r'\s+', ' ', value).strip()


def filename_proves_model(filename, model):
    # Only URL decoding and the slash-to-hyphen filename convention are allowed.
    # Do not strip punctuation, truncate region/colour suffixes or inspect titles.
    name = unquote(Path(filename).stem).casefold()
    model = model.casefold().replace('/', '-')
    return bool(re.search(r'(?<![a-z0-9])' + re.escape(model) + r'(?![a-z0-9-])', name))


def old_catalogue(sql_path):
    data = load_catalogue(sql_path)
    entries = []
    mappings = CatalogueSource.objects.filter(source=SOURCE).select_related(
        'product', 'stockrecord', 'image').prefetch_related('product__attribute_values__attribute')
    RangeProduct = get_model('offer', 'RangeProduct')
    memberships = defaultdict(list)
    for member in RangeProduct.objects.all().values('product_id', 'range_id', 'display_order'):
        memberships[member.pop('product_id')].append(member)
    for mapping in mappings:
        specs = {v.attribute.code: str(v.value_as_text) for v in mapping.product.attribute_values.all()}
        meta = data.meta.get(mapping.source_id, {})
        attachment_id = int(meta.get('_thumbnail_id') or 0)
        attachment = data.meta.get(attachment_id, {}).get('_wp_attached_file', '')
        image = mapping.image
        expected_digest = sha256(uploads_url(attachment).encode()).hexdigest()[:16] if attachment else ''
        provenance_verified = bool(image and image.product_id == mapping.product_id and expected_digest and
            Path(image.original.name).stem in {
                f'watch-{mapping.product_id}-{expected_digest}',
                f'wc-abdeen-{mapping.source_id}-{expected_digest}',
            })
        sku = mapping.stockrecord.partner_sku.strip()
        # Non-numeric WooCommerce SKUs are explicit manufacturer references.
        model = specs.get('model_reference') or (sku if not sku.isdigit() and not sku.startswith('ABDEEN-') else '')
        entries.append({'product_id': mapping.product_id, 'source_id': mapping.source_id,
                        'sku': sku, 'model': model, 'brand': canonical_brand(specs.get('brand', '')),
                        'attributes': specs, 'attachment': attachment,
                        'image': mapping.image.original.name if mapping.image else None,
                        'image_id': mapping.image_id, 'ranges': memberships[mapping.product_id],
                        'provenance_verified': provenance_verified,
                        'source_sku_agrees': meta.get('_sku') == sku})
    return entries


def prepare_images(validation, sql_path, directory):
    """Copies files only. Never changes Product, ProductImage, or original media."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    old = old_catalogue(sql_path)
    (directory / 'old-catalogue.json').write_text(json.dumps(old, indent=2) + '\n')
    sku_index, model_index = defaultdict(list), defaultdict(list)
    for entry in old:
        sku_index[entry['sku'].casefold()].append(entry)
        if entry['brand'] and entry['model']:
            model_index[(entry['brand'], entry['model'].casefold())].append(entry)
    sku_counts = Counter(r['sku'].casefold() for r in validation['rows'])
    model_counts = Counter((r['brand'], r['model'].casefold()) for r in validation['rows'])
    blocked = {i['row'] for i in validation['issues'] if i['severity'] == 'error'}
    records = []
    for row in validation['rows']:
        record = {'row': row['row'], 'sku': row['sku'], 'model': row['model'], 'brand': row['brand'],
                  'status': 'unassigned', 'reason': '', 'old_product_id': None, 'ranges': []}
        records.append(record)
        if row['row'] in blocked or sku_counts[row['sku'].casefold()] != 1 or model_counts[(row['brand'], row['model'].casefold())] != 1:
            record['reason'] = 'Row validation or identifier ambiguity must be resolved first.'
            continue
        matches = sku_index[row['sku'].casefold()]
        method = 'unique SKU'
        if not matches:
            matches = model_index[(row['brand'], row['model'].casefold())]
            method = 'unique brand + manufacturer reference in WooCommerce SKU'
        if len(matches) != 1:
            record['reason'] = 'No unique exact identifier match.'
            continue
        old_row = matches[0]
        record.update(old_product_id=old_row['product_id'], source_id=old_row['source_id'],
                      method=method, source_attachment=old_row['attachment'])
        if not old_row['source_sku_agrees'] or old_row['brand'] != row['brand']:
            record['reason'] = 'WooCommerce source SKU or brand disagrees with current catalogue.'
            continue
        conflicts = []
        for code in ['gender', 'case_size', 'case_material', 'case_color', 'band_material', 'band_color', 'dial_color']:
            a, b = row['attributes'].get(code), old_row['attributes'].get(code)
            if a and b and normalized_fact(a) != normalized_fact(b):
                conflicts.append(f'{code}: Excel={a}; old={b}')
        if conflicts:
            record['reason'] = 'Specification conflicts: ' + '; '.join(conflicts)
            continue
        record['ranges'] = old_row['ranges']
        if not old_row['image']:
            record['reason'] = 'Exact product matched, but no mapped old image.'
            continue
        if not old_row['provenance_verified']:
            record['reason'] = 'Image no longer has verified WooCommerce attachment provenance; review manual replacement.'
            continue
        original = (Path(settings.MEDIA_ROOT) / old_row['image']).resolve()
        if not original.is_relative_to(Path(settings.MEDIA_ROOT).resolve()) or not original.is_file():
            record['reason'] = 'Old image is missing or outside media.'
            continue
        try:
            with Image.open(original) as photo:
                photo.verify()
        except (OSError, ValueError):
            record['reason'] = 'Old image is not a readable bitmap.'
            continue
        checksum = digest(original)
        relative = Path('assets') / (checksum + original.suffix.lower())
        destination = directory / relative
        destination.parent.mkdir(exist_ok=True)
        if not destination.exists():
            shutil.copy2(original, destination)
        if digest(destination) != checksum:
            raise ImportDataError('Archived image checksum mismatch.')
        record.update(file=str(relative), sha256=checksum, original_media=old_row['image'])
        if not filename_proves_model(old_row['attachment'], row['model']):
            record['reason'] = 'Exact product match, but attachment filename does not prove the complete model; manual review required.'
            continue
        record.update(status='verified', reason='Unique identifier, agreeing brand/specifications, exact model in source attachment filename, readable archived bitmap.')
    # Identical image bytes associated with different models need manual review.
    by_hash = defaultdict(list)
    for record in records:
        if record.get('sha256'):
            by_hash[record['sha256']].append(record)
    for group in by_hash.values():
        if len({(r['brand'], r['model'].casefold()) for r in group}) > 1:
            for record in group:
                record.update(status='unassigned', reason='Same image bytes associated with multiple model references.')
    manifest = {'workbook_sha256': validation['workbook_sha256'], 'sql_sha256': digest(sql_path),
                'records': records, 'counts': dict(Counter(r['status'] for r in records))}
    (directory / 'images.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest
