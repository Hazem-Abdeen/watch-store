"""Conservative, deterministic variant suggestions from local source data only.

No ORM queries, storage writes, network access, or automatic regrouping.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from html import unescape

from .catalogue import build_plans
from .specifications import extract_specifications, php_attributes, plain_text, specification_code


MODEL_META_KEYS = {'_model', 'model', '_model_number', 'model_number', '_product_model',
                   '_mpn', 'mpn', 'fb_mpn', '_manufacturer_part_number'}
MODEL_LABELS = {'model', 'model_number', 'model_no', 'model_reference', 'reference',
                'reference_number', 'manufacturer_part_number', 'mpn'}
CORE = ('gender', 'movement', 'case_size', 'case_material', 'band_material', 'water_resistance')
COLORS = ('dial_color', 'band_color', 'case_color', 'color')
BRAND_ALIASES = {'casio edifice': 'casio', 'sb polo': 'santa barbara polo',
                 'bigotti milano': 'bigotti'}
TITLE_STOP = set('watch watches men women man woman for with and dial case band strap bracelet '
                 'st steel stainless full silver gold golden rose black white blue green red pink '
                 'brown yellow orange purple grey gray beige multicolor multicolored multi color '
                 'coloured colored two tone the a of'.split())


def normalized(value):
    return ' '.join(unescape(value or '').casefold().split())


def label_key(value):
    return re.sub(r'[\s-]+', '_', normalized(value).rstrip(':').removeprefix('pa_'))


def normalized_spec(code, value):
    value = normalized(value)
    if code in {'case_material', 'band_material'}:
        value = re.sub(r'\bst\.?\s*steel\b', 'stainless steel', value)
    if code == 'case_size':
        value = re.sub(r'\s+(?=mm\b)', '', value)
    if code in COLORS:
        value = value.replace('grey', 'gray').replace('multicolored', 'multicolor')
        value = ' & '.join(sorted(part.strip() for part in re.split(r'\s*&\s*|\s+and\s+', value)))
    return value


def sku_family(value, brand):
    """Only explicit separator patterns; never truncate an arbitrary prefix/EAN."""
    value = value.strip().upper()
    # Preserve brand/collection/gender components before the final option suffix.
    patterns = [r'([A-Z]{0,3}\d{3,7})/([A-Z0-9]{1,3})',
                r'((?:DK|FL|SB|BG|LC|VO)\.\d\.\d{4,6})-([A-Z0-9]{1,3})']
    if brand == 'casio':
        patterns.append(r'((?:[A-Z]{1,5}-)?[A-Z]*\d{2,5}[A-Z]*)-([0-9][A-Z0-9]{1,12})')
    for pattern in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            return match[1], match[2], False
    # WordPress copy suffixes are evidence for review, not a reliable option code.
    copy = re.fullmatch(r'(.+)-\d{1,2}', value)
    if copy:
        for pattern in patterns:
            match = re.fullmatch(pattern, copy[1])
            if match:
                return match[1], match[2], True
    return None


def model_family(value, brand):
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9./_-]{2,39}', value) or not re.search(r'\d', value):
        return None
    if re.fullmatch(r'\d{8,}', value):
        return None  # Long numeric references could be barcodes; never infer a prefix.
    family = sku_family(value, brand)
    return family[0] if family else value


def title_key(title, brand):
    words = re.findall(r'[a-z0-9]+', normalized(title))
    brand_words = set(re.findall(r'[a-z0-9]+', brand))
    remaining = [word for word in words if word not in TITLE_STOP | brand_words]
    # Generic brand/material/gender titles provide no family identity at all.
    return ' '.join(remaining) if any(len(word) >= 3 for word in remaining) else ''


@dataclass
class VariantRecord:
    source_id: int
    sku: str
    title: str
    brand: str
    price: str | None
    image_url: str | None
    specifications: dict
    visible_attributes: dict
    identifiers: list
    issues: list
    warnings: list
    title_key: str

    @property
    def primary(self):
        return min(self.identifiers, key=lambda item: (item['rank'], item['family'])) if self.identifiers else None

    def child_report(self):
        return {'source_id': self.source_id, 'sku': self.sku, 'title': self.title,
                'price': self.price, 'currency': 'JOD', 'image_url': self.image_url,
                'colors': {key: self.specifications[key] for key in COLORS if self.specifications.get(key)},
                'specifications': self.specifications, 'visible_attributes': self.visible_attributes,
                'identifier_evidence': self.identifiers, 'warnings': self.warnings}


def records_from_catalogue(data):
    records, excluded = [], []
    source_skus = {(data.meta.get(key, {}).get('_sku') or '').strip() for key in data.products}
    for plan in build_plans(data):
        if plan.skip_reason:
            excluded.append({'source_id': plan.source_id, 'reason': plan.skip_reason})
            continue
        meta = data.meta.get(plan.source_id, {})
        attributes = php_attributes(meta.get('_product_attributes'))
        specs = dict(plan.specifications)
        brand = BRAND_ALIASES.get(normalized(specs.get('brand')), normalized(specs.get('brand')))
        identifiers, issues, visible = [], [], {}
        described = extract_specifications(plan.description)
        for code in CORE:
            if (described.get(code) and specs.get(code)
                    and normalized_spec(code, described[code]) != normalized_spec(code, specs[code])):
                issues.append(f'Description conflicts with structured attributes for {code}.')
        if ',' in brand:
            issues.append('Multiple brand values; a single brand must be verified.')

        def identifier(value, origin, rank):
            if not isinstance(value, str) or not value.strip():
                return
            family = model_family(value, brand)
            if family:
                identifiers.append({'value': value.strip(), 'family': family, 'source': origin, 'rank': rank})
                parsed = sku_family(value, brand)
                if parsed and parsed[2]:
                    issues.append(f'Copy-like numeric suffix in {origin}: {value}.')
            else:
                issues.append(f'Unusable explicit model reference in {origin}; review its value.')

        for key in sorted(MODEL_META_KEYS):
            identifier(meta.get(key), f'metadata:{key}', 1)
        for entry in attributes.values():
            if not isinstance(entry, dict):
                continue  # Source validation in build_plans handles malformed custom attributes.
            label, value = entry.get('name', ''), entry.get('value', '')
            if not isinstance(label, str) or not isinstance(value, str) or entry.get('is_taxonomy'):
                continue
            if label_key(label) in MODEL_LABELS:
                identifier(value, f'attribute:{label}', 1)
            if entry.get('is_visible', 1) and value.strip():
                code = specification_code(label) or label_key(label)
                if code in {*CORE, *COLORS, 'colour', 'brand', *MODEL_LABELS}:
                    visible[code] = ' '.join(plain_text(value).split())
                if code in {'color', 'colour'}:
                    specs['color'] = ' '.join(plain_text(value).split())
        for taxonomy_id in sorted(data.relationships.get(plan.source_id, ())):
            taxonomy = data.taxonomies.get(taxonomy_id)
            if not taxonomy:
                continue
            label = taxonomy['taxonomy']
            value = data.terms.get(int(taxonomy['term_id']), '')
            if label_key(label) in MODEL_LABELS:
                identifier(value, f'taxonomy:{label}', 1)
            code = specification_code(label) or label_key(label)
            if label.startswith('pa_') and code in {*CORE, *COLORS, 'brand'}:
                visible[code] = value
            if label.startswith('pa_') and code in {'color', 'colour'}:
                specs['color'] = value
        for line in plain_text(plan.description).splitlines():
            pair = re.split(r':|\t', line.strip(), maxsplit=1)
            if len(pair) == 2 and label_key(pair[0]) in MODEL_LABELS:
                identifier(pair[1], f'description:{pair[0]}', 1)
        raw_sku = (meta.get('_sku') or '').strip()
        copy = re.fullmatch(r'(.+)-\d{1,2}', raw_sku)
        if copy and copy[1] in source_skus:
            issues.append('SKU is another published SKU plus a numeric copy suffix; review duplicate identity.')
        family = sku_family(raw_sku, brand)
        if family:
            identifiers.append({'value': raw_sku, 'family': family[0], 'source': 'sku_pattern', 'rank': 2})
            if family[2]:
                issues.append('Copy-like numeric suffix in SKU; it may be a duplicate listing.')
        # A recognizable part number in a title is weaker than structured fields/SKU.
        for token in re.findall(r'[A-Za-z0-9][A-Za-z0-9./-]*', unescape(plan.title)):
            family = sku_family(token.rstrip('.,'), brand)
            if family:
                identifiers.append({'value': token, 'family': family[0], 'source': 'title_model_token', 'rank': 4})
                if family[2]:
                    issues.append('Copy-like numeric suffix in title reference.')
        if len({item['family'] for item in identifiers if item['rank'] == 1}) > 1:
            issues.append('Conflicting explicit model identifiers within this product.')
        if not raw_sku:
            issues.append('Missing source SKU; no synthetic SKU is used as grouping evidence.')
        for title_color in re.findall(
                r'\b(black|white|blue|green|red|pink|brown|gold|silver|gray|grey|multicolored)\s+dial\b',
                normalized(plan.title)):
            if (specs.get('dial_color') and normalized_spec('dial_color', title_color)
                    != normalized_spec('dial_color', specs['dial_color'])):
                issues.append('Title dial color conflicts with the structured dial color.')
        records.append(VariantRecord(
            plan.source_id, raw_sku, plan.title, brand,
            None if plan.price is None else str(plan.price), plan.image_url, specs, visible,
            identifiers, issues, list(plan.warnings), title_key(plan.title, brand),
        ))
    return records, excluded


def assess_group(brand, family, records, *, title_only=False):
    reasons, problems, shared, conflicts = [], [], {}, {}
    if not brand:
        problems.append('Brand is missing; model references are not globally unique.')
    if title_only:
        problems.append('Only a normalized title matches; no shared model-family identifier.')
    else:
        evidence = sorted({item['source'] for row in records for item in row.identifiers if item['family'] == family})
        reasons.append(f'Specific family {family} is supported by: {", ".join(evidence)}.')
    for row in records:
        problems.extend(f'Source {row.source_id}: {issue}' for issue in row.issues)
        if not title_only and row.primary and row.primary['family'] != family:
            problems.append(f'Source {row.source_id}: stronger identifier points to {row.primary["family"]}.')
        if any(item['family'] != family for item in row.identifiers) and not title_only:
            problems.append(f'Source {row.source_id}: another model-family reference conflicts with {family}.')
    if len({row.sku for row in records}) != len(records):
        problems.append('Duplicate child SKUs require review.')
    for code in CORE:
        values = [normalized_spec(code, row.specifications.get(code)) for row in records]
        known = set(values) - {''}
        if len(known) > 1:
            conflicts[code] = {str(row.source_id): row.specifications.get(code) for row in records}
            problems.append(f'Conflicting {code.replace("_", " ")}.')
        elif len(known) == 1 and all(values):
            shared[code] = records[0].specifications[code]
    ranks = [row.primary['rank'] if row.primary else 4 for row in records]
    required_count = 2 if max(ranks) == 1 else 5 if max(ranks) == 4 else 4
    if not {'movement', 'case_size'}.issubset(shared) or len(shared) < required_count:
        problems.append(f'Insufficient complete shared specifications: need movement, case size and '
                        f'at least {required_count} matching core fields in every child.')
    if shared:
        reasons.append('Complete matching core fields: ' + ', '.join(shared) + '.')
    option_axes = []
    complete_axes = []
    for code in COLORS:
        values = [normalized_spec(code, row.specifications.get(code)) for row in records]
        if all(values):
            complete_axes.append(code)
            if len(set(values)) > 1:
                option_axes.append(code)
    if not option_axes:
        problems.append('No complete differing color/option field distinguishes the children.')
    signatures = {tuple(normalized_spec(code, row.specifications.get(code)) for code in complete_axes)
                  for row in records}
    if len(signatures) != len(records):
        problems.append('Some children have identical or incomplete option combinations; possible duplicate listings.')
    if option_axes:
        reasons.append('Distinct option evidence: ' + ', '.join(option_axes) + '.')
    if len({row.price for row in records}) > 1:
        reasons.append('Prices differ; retain individual child prices. Price equality is not identity evidence.')
    return {'status': 'ambiguous' if problems else 'candidate',
            'confidence': 'review_required' if problems else 'high',
            'brand': brand, 'family': family, 'proposed_parent_title': f'{brand.upper()} {family}',
            'basis': 'normalized_title' if title_only else 'model_family',
            'reasons': reasons, 'review_flags': sorted(set(problems)), 'shared_specifications': shared,
            'conflicting_specifications': conflicts, 'option_axes': option_axes,
            'children': [row.child_report() for row in sorted(records, key=lambda row: (row.sku, row.source_id))]}


def analyze_catalogue(data):
    records, excluded = records_from_catalogue(data)
    buckets = defaultdict(dict)
    title_buckets = defaultdict(dict)
    for row in records:
        for item in row.identifiers:
            buckets[(row.brand, item['family'])][row.source_id] = row
        if not row.identifiers and row.title_key:
            title_buckets[(row.brand, row.title_key)][row.source_id] = row
    groups = [assess_group(brand, family, list(members.values()))
              for (brand, family), members in sorted(buckets.items()) if len(members) > 1]
    groups.extend(assess_group(brand, title, list(members.values()), title_only=True)
                  for (brand, title), members in sorted(title_buckets.items()) if len(members) > 1)
    candidates = [group for group in groups if group['status'] == 'candidate']
    ambiguous = [group for group in groups if group['status'] == 'ambiguous']
    memberships = Counter(child['source_id'] for group in candidates for child in group['children'])
    # Never propose two different parents for the same product.
    for group in list(candidates):
        if any(memberships[child['source_id']] > 1 for child in group['children']):
            candidates.remove(group)
            group.update(status='ambiguous', confidence='review_required')
            group['review_flags'].append('Overlapping candidate families require a single approved parent choice.')
            ambiguous.append(group)
    reported_ids = {child['source_id'] for group in groups for child in group['children']}
    return {'read_only': True, 'rule_version': 1,
            'summary': {'published_products': len(data.products), 'analyzed_products': len(records),
                        'candidate_groups': len(candidates), 'ambiguous_groups': len(ambiguous),
                        'candidate_products': len({c['source_id'] for g in candidates for c in g['children']}),
                        'ungrouped_products': len({row.source_id for row in records} - reported_ids),
                        'excluded_products': len(excluded)},
            'candidates': candidates, 'ambiguous': ambiguous, 'excluded': excluded,
            'notes': ['Suggestions only; no Oscar objects are read, created or changed.',
                      'Core fields: gender, movement, case size, case material, band material, water resistance.',
                      'High confidence is a rule classification, not a verified manufacturer relationship.',
                      'Barcode prefixes, brand-only matches and arbitrary numeric suffix truncation are forbidden.',
                      'Image URLs are listed without downloading or checking them.',
                      'Ambiguous groups can overlap; never merge them transitively.']}
