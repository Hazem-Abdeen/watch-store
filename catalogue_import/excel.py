"""Strict, read-only OOXML catalogue reader and row validation.

No Excel automation, formula evaluation, title identities, or implicit deduplication.
The small reader deliberately accepts only the flat, literal workbook contract.
"""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from .sql_dump import ImportDataError

HEADERS = ('SKU', 'Model Reference', 'Product Type', 'Title', 'Brand', 'Gender',
           'Categories', 'Price', 'Regular Price', 'Movement', 'Case Size',
           'Case Material', 'Case Color', 'Band Material', 'Band Color', 'Dial Color',
           'Glass', 'Water Resistance', 'Guarantee', 'Country')
ATTRIBUTES = {
    'Model Reference': 'model_reference', 'Brand': 'brand', 'Gender': 'gender',
    'Movement': 'movement', 'Case Size': 'case_size', 'Case Material': 'case_material',
    'Case Color': 'case_color', 'Band Material': 'band_material', 'Band Color': 'band_color',
    'Dial Color': 'dial_color', 'Glass': 'glass', 'Water Resistance': 'water_resistance',
    'Guarantee': 'guarantee', 'Country': 'country',
}
# Explicit aliases preserve existing brand URLs/logos. No fuzzy brand matching.
BRAND_NAMES = {
    'bigotti milano': 'Bigotti', 'bigotti': 'Bigotti', 'casio': 'Casio',
    'casio edifice': 'Casio', 'daniel klein': 'Daniel Klein', 'ducati': 'DUCATI',
    'freelook': 'FreeLook', 'guy laroche': 'GUY LAROCHE', 'hanowa': 'HANOWA',
    'jaguar': 'JAGUAR', 'lee cooper': 'LEE COOPER', 'lotus': 'LOTUS',
    'santa barbara polo': 'Santa Barbara Polo', 'sb polo': 'Santa Barbara Polo',
    'swiss military': 'SWISS MILITARY', 'valentino orlandi': 'VALENTINO ORLANDI',
}
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def digest(path):
    h = sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical_brand(value):
    return BRAND_NAMES.get(value.strip().casefold())


def read_workbook(path):
    def xml(archive, name):
        if archive.getinfo(name).file_size > 10 * 1024 * 1024:
            raise ImportDataError('Oversized worksheet or shared string table.')
        data = archive.read(name)
        if b'<!DOCTYPE' in data or b'<!ENTITY' in data:
            raise ImportDataError('XML entities are not supported.')
        return ET.fromstring(data)

    with ZipFile(path) as archive:
        book = xml(archive, 'xl/workbook.xml')
        sheets = book.findall('s:sheets/s:sheet', NS)
        if len(sheets) != 1:
            raise ImportDataError('Expected exactly one catalogue worksheet.')
        relationships = xml(archive, 'xl/_rels/workbook.xml.rels')
        rid = sheets[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        target = next((r.get('Target') for r in relationships if r.get('Id') == rid), '')
        sheet_path = target.lstrip('/') if target.startswith('/') else f'xl/{target}'
        if '..' in sheet_path.split('/') or not sheet_path.startswith('xl/worksheets/'):
            raise ImportDataError('Unsupported worksheet path.')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(si.itertext()) for si in xml(archive, 'xl/sharedStrings.xml').findall('s:si', NS)]
        rows = []
        for row in xml(archive, sheet_path).findall('s:sheetData/s:row', NS):
            values, errors = {}, []
            for cell in row.findall('s:c', NS):
                reference = cell.get('r', '')
                match = re.fullmatch(r'([A-Z]+)([1-9]\d*)', reference)
                if not match or int(match[2]) != int(row.get('r')) or match[1] in values:
                    raise ImportDataError('Invalid or duplicate cell reference.')
                kind = cell.get('t', 'n')
                value = cell.findtext('s:v', '', NS)
                if kind == 's':
                    value = strings[int(value)]
                elif kind == 'inlineStr':
                    value = ''.join(cell.find('s:is', NS).itertext())
                elif kind not in {'n', 'str'}:
                    errors.append(f'{reference}: unsupported cell type {kind}')
                if cell.find('s:f', NS) is not None:
                    errors.append(f'{reference}: formulas are forbidden; provide literal values')
                values[match[1]] = value.strip()
            if any(values.values()):
                rows.append((int(row.get('r')), values, errors))
    if not rows or rows[0][0] != 1:
        raise ImportDataError('Missing header row.')
    columns = [chr(65 + i) for i in range(len(HEADERS))]
    if tuple(rows[0][1].get(c, '') for c in columns) != HEADERS or rows[0][2]:
        raise ImportDataError('The workbook headers do not match the catalogue contract.')
    if any(v for c, v in rows[0][1].items() if c not in columns):
        raise ImportDataError('Unexpected extra header columns.')
    return [{'row': number, 'values': {h: values.get(c, '') for c, h in zip(columns, HEADERS)},
             'extra_cells': {c: v for c, v in values.items() if c not in columns and v},
             'cell_errors': errors} for number, values, errors in rows[1:]]


def money(value, required=True):
    text = re.sub(r'\s+JOD$', '', value, flags=re.I).strip()
    if not text and not required:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ImportDataError('Expected a numeric JOD price.') from None
    if (not value.is_finite() or value <= 0 or value >= Decimal('10000000000')
            or value != value.quantize(Decimal('.01'))):
        raise ImportDataError('Price must be positive and fit Decimal(12, 2) without rounding.')
    return str(value.quantize(Decimal('.01')))


def validate_workbook(path, *, corrections=None, expected_count=358):
    raw = read_workbook(path)
    fingerprint = digest(path)
    changes = {}
    if corrections:
        changes = json.loads(Path(corrections).read_text())
        if changes.get('workbook_sha256') != fingerprint:
            raise ImportDataError('Corrections were prepared for a different workbook.')
        if set(changes.get('rows', {})) - {str(r['row']) for r in raw}:
            raise ImportDataError('Correction references a nonexistent row.')
    rows, issues, applied = [], [], []
    def issue(number, severity, code, detail):
        issues.append(dict(row=number, severity=severity, code=code, detail=detail))
    for original in raw:
        number = original['row']
        row = {**original['values']}
        extra = original['extra_cells']
        correction = changes.get('rows', {}).get(str(number))
        if correction:
            if correction.get('expected') != original or not correction.get('reason'):
                raise ImportDataError(f'Row {number}: correction requires exact original row and reason.')
            applied.append({'row': number, 'reason': correction['reason'], 'drop': bool(correction.get('drop'))})
            if correction.get('drop'):
                continue
            if set(correction.get('set', {})) - set(HEADERS):
                raise ImportDataError('Unknown correction field.')
            row.update(correction.get('set', {}))
            if correction.get('clear_extra_cells'):
                extra = {}
        for error in original['cell_errors']:
            issue(number, 'error', 'cell', error)
        if extra:
            issue(number, 'error', 'extra_columns', f'Unexpected data beyond Country: {extra}; possible shifted row.')
        for field, maximum in [('SKU', 64), ('Model Reference', 128), ('Title', 255), ('Brand', 128)]:
            if not row[field] or len(row[field]) > maximum:
                issue(number, 'error', 'required', f'Missing or overlong {field}.')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', row['SKU']):
            issue(number, 'error', 'sku', 'SKU must be a literal identifier without whitespace.')
        if re.fullmatch(r'\d{13}', row['SKU']):
            check = sum(int(n) * (1 if i % 2 == 0 else 3) for i, n in enumerate(row['SKU'][:12]))
            if (check + int(row['SKU'][-1])) % 10:
                issue(number, 'warning', 'barcode_checksum', '13-digit SKU fails the EAN-13 checksum; confirm the identifier.')
        brand = canonical_brand(row['Brand'])
        if not brand:
            issue(number, 'error', 'brand', f'Unknown brand: {row["Brand"]}')
        if row['Product Type'] not in {'Watch', 'Accessory'}:
            issue(number, 'error', 'type', 'Expected Watch or Accessory.')
        if row['Gender'] not in {'Men', 'Women', 'Unisex'}:
            issue(number, 'error', 'gender', f'Invalid gender: {row["Gender"]}')
        paths = []
        for part in row['Categories'].split('|'):
            path_parts = tuple(p.strip() for p in part.split('/'))
            if len(path_parts) == 2 and path_parts[0] == 'Brands' and canonical_brand(path_parts[1]) == brand and brand:
                paths.append(('Brands', brand))
            elif path_parts in [('Men',), ('Women',), ('Unisex',)]:
                paths.append(path_parts)
            else:
                issue(number, 'error', 'category', f'Unsupported category path: {part}')
        if ('Brands', brand) not in paths or (row['Gender'],) not in paths:
            issue(number, 'error', 'category', 'Categories must include the exact brand and gender.')
        prices = {}
        for field in ['Price', 'Regular Price']:
            try:
                prices[field] = money(row[field], required=field == 'Price')
            except ImportDataError as exc:
                issue(number, 'error', 'price', f'{field}: {exc}')
        if all(prices.get(f) for f in ['Price', 'Regular Price']):
            if Decimal(prices['Regular Price']) < Decimal(prices['Price']):
                issue(number, 'error', 'discount', 'Regular Price is lower than Price.')
        if row['Product Type'] == 'Watch':
            for field in ['Movement', 'Case Size', 'Case Color', 'Band Material', 'Band Color', 'Dial Color', 'Guarantee']:
                if not row[field]:
                    issue(number, 'error', 'watch_attribute', f'Missing required watch field {field}.')
            if row['Movement'] not in {'Analog Quartz (Battery)', 'Automatic'}:
                issue(number, 'error', 'movement', 'Unrecognized movement; review source row.')
            if not re.fullmatch(r'\d+(?:\.\d+)?(?:\s*mm)?', row['Case Size']):
                issue(number, 'error', 'case_size', 'Expected a case size in millimetres.')
            for field in ['Case Material', 'Water Resistance', 'Glass', 'Country']:
                if not row[field]:
                    issue(number, 'warning', 'optional_attribute', f'{field} is missing; leave blank, do not infer.')
        for field in ATTRIBUTES:
            if len(row[field]) > 2000:
                issue(number, 'error', 'attribute_length', f'{field} exceeds 2000 characters.')
        # Preserve source labels in attributes; category names use explicit aliases.
        specs = {code: row[field] for field, code in ATTRIBUTES.items() if row[field]}
        if specs.get('case_size') and re.fullmatch(r'\d+(?:\.\d+)?', specs['case_size']):
            specs['case_size'] += ' mm'
        rows.append({'row': number, 'values': row, 'sku': row['SKU'], 'brand': brand,
                     'model': row['Model Reference'], 'type': row['Product Type'],
                     'categories': paths, 'attributes': specs, 'price': prices.get('Price'),
                     'regular_price': prices.get('Regular Price')})
    for label, key in [('duplicate_sku', lambda r: r['sku'].casefold()),
                       ('duplicate_model', lambda r: (r['brand'], r['model'].casefold()))]:
        groups = defaultdict(list)
        for row in rows:
            groups[key(row)].append(row['row'])
        for identity, numbers in groups.items():
            if len(numbers) > 1:
                for number in numbers:
                    issue(number, 'error', label, f'{identity}: rows {numbers}; never merged automatically.')
    if len(rows) != expected_count:
        issue(None, 'error', 'row_count', f'Expected {expected_count} rows, found {len(rows)} after explicit corrections.')
    return {'workbook': str(Path(path).resolve()), 'workbook_sha256': fingerprint,
            'source_rows': len(raw), 'expected_count': expected_count, 'rows': rows,
            'counts': dict(Counter(r['type'] for r in rows)), 'issues': issues,
            'corrections': applied, 'raw_rows': raw}
