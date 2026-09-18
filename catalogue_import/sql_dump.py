"""Read phpMyAdmin INSERT literals. Never execute SQL or deserialize PHP data."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


class ImportDataError(ValueError):
    """An unsafe or malformed source record; messages never include row contents."""


REQUIRED = {
    'wp_posts': {'ID', 'post_type', 'post_status', 'post_title', 'post_content'},
    'wp_postmeta': {'post_id', 'meta_key', 'meta_value'},
    'wp_terms': {'term_id', 'name'},
    'wp_term_taxonomy': {'term_taxonomy_id', 'term_id', 'taxonomy', 'parent'},
    'wp_term_relationships': {'object_id', 'term_taxonomy_id'},
    'wp_wc_product_meta_lookup': {'product_id'},
}
META_KEYS = {'_sku', '_price', '_regular_price', '_sale_price', '_stock_status',
             '_thumbnail_id', '_wp_attached_file'}
TAXONOMIES = {'product_cat', 'pa_gender', 'product_type'}
NUMBER = re.compile(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\Z')
INSERT = re.compile(
    r'INSERT\s+INTO\s+`?(\w+)`?\s*\((.*?)\)\s+VALUES\s*', re.I | re.S,
)
ESCAPES = {'0': '\0', 'b': '\b', 'n': '\n', 'r': '\r', 't': '\t', 'Z': '\x1a'}


def statements(text):
    """Split outside strings/comments, including escaped and doubled quotes."""
    start = index = 0
    quote = None
    while index < len(text):
        char = text[index]
        if quote:
            if char == '\\':
                index += 2
                continue
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in "'\"`":
            quote = char
        elif text.startswith('--', index) or char == '#':
            # Comments are allowed only between statements in this dump dialect.
            if text[start:index].strip():
                raise ImportDataError('Inline SQL comments are not supported.')
            end = text.find('\n', index)
            index = len(text) if end < 0 else end + 1
            start = index
            continue
        elif text.startswith('/*', index):
            if text[start:index].strip():
                raise ImportDataError('Inline SQL comments are not supported.')
            end = text.find('*/', index + 2)
            if end < 0:
                raise ImportDataError('Unterminated SQL comment.')
            index = end + 2
            start = index
            continue
        elif char == ';':
            value = text[start:index].strip()
            if value:
                yield value
            start = index + 1
        index += 1
    if quote or text[start:].strip():
        raise ImportDataError('Unterminated SQL statement or quoted string.')


def literal_rows(text):
    """Only NULL, numbers and quoted strings are accepted, never expressions."""
    index = 0
    length = len(text)

    def whitespace():
        nonlocal index
        while index < length and text[index].isspace():
            index += 1

    while True:
        whitespace()
        if index >= length or text[index] != '(':
            raise ImportDataError('Expected an INSERT row.')
        index += 1
        row = []
        while True:
            whitespace()
            if index < length and text[index] == "'":
                index += 1
                chars = []
                while index < length:
                    char = text[index]
                    index += 1
                    if char == '\\':
                        if index == length:
                            raise ImportDataError('Incomplete SQL escape.')
                        escaped = text[index]
                        index += 1
                        chars.append(ESCAPES.get(escaped, escaped))
                    elif char == "'":
                        if index < length and text[index] == "'":
                            chars.append("'")
                            index += 1
                        else:
                            break
                    else:
                        chars.append(char)
                else:
                    raise ImportDataError('Unterminated SQL literal.')
                value = ''.join(chars)
            else:
                start = index
                while index < length and text[index] not in ',)':
                    index += 1
                value = text[start:index].strip()
                if value.upper() == 'NULL':
                    value = None
                elif not NUMBER.fullmatch(value):
                    raise ImportDataError('Unsupported SQL literal or expression.')
            row.append(value)
            whitespace()
            if index >= length or text[index] not in ',)':
                raise ImportDataError('Malformed INSERT row delimiter.')
            delimiter = text[index]
            index += 1
            if delimiter == ')':
                break
        yield row
        whitespace()
        if index == length:
            return
        if text[index] != ',':
            raise ImportDataError('Unexpected content after INSERT row.')
        index += 1


def sql_rows(path):
    path = Path(path)
    # A bounded read keeps corrupt/accidentally selected huge exports manageable.
    with path.open('r', encoding='utf-8-sig') as source:
        text = source.read(128 * 1024 * 1024 + 1)
    if len(text) > 128 * 1024 * 1024:
        raise ImportDataError('SQL export exceeds the 128 MiB character limit.')
    seen = set()
    for number, statement in enumerate(statements(text), 1):
        if not re.match(r'INSERT\b', statement, re.I):
            # DDL, transaction and SET statements are ignored, never executed.
            continue
        match = INSERT.match(statement)
        if not match:
            raise ImportDataError(f'Unsupported INSERT header at statement {number}.')
        table, column_text = match.groups()
        if table not in REQUIRED:
            continue
        columns = [column.strip().strip('`') for column in column_text.split(',')]
        if (any(not re.fullmatch(r'\w+', column) for column in columns)
                or len(set(columns)) != len(columns)
                or not REQUIRED[table].issubset(columns)):
            raise ImportDataError(f'Invalid columns for {table}, statement {number}.')
        seen.add(table)
        try:
            for row in literal_rows(statement[match.end():]):
                if len(row) != len(columns):
                    raise ImportDataError('INSERT column/value count mismatch.')
                yield table, dict(zip(columns, row))
        except ImportDataError as exc:
            raise ImportDataError(f'{table}, statement {number}: {exc}') from exc
    missing = REQUIRED.keys() - seen
    if missing:
        raise ImportDataError(f'Missing INSERT data for tables: {", ".join(sorted(missing))}.')


def source_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9]\d*', value):
        raise ImportDataError('Expected a positive source ID.')
    return int(value)


@dataclass
class Catalogue:
    products: dict = field(default_factory=dict)
    attachments: set = field(default_factory=set)
    meta: dict = field(default_factory=lambda: defaultdict(dict))
    terms: dict = field(default_factory=dict)
    taxonomies: dict = field(default_factory=dict)
    relationships: dict = field(default_factory=lambda: defaultdict(set))


def load_catalogue(path):
    data = Catalogue()
    for table, row in sql_rows(path):
        if table == 'wp_posts':
            if row['post_type'] == 'product' and row['post_status'] == 'publish':
                key = source_id(row['ID'])
                if key in data.products:
                    raise ImportDataError(f'Duplicate published product ID {key}.')
                data.products[key] = {k: row[k] for k in ('post_title', 'post_content')}
            elif row['post_type'] == 'attachment':
                data.attachments.add(source_id(row['ID']))
        elif table == 'wp_postmeta' and row['meta_key'] in META_KEYS:
            key, name = source_id(row['post_id']), row['meta_key']
            if name in data.meta[key] and data.meta[key][name] != row['meta_value']:
                raise ImportDataError(f'Conflicting {name} metadata for source ID {key}.')
            data.meta[key][name] = row['meta_value']
        elif table == 'wp_terms':
            key = source_id(row['term_id'])
            if key in data.terms:
                raise ImportDataError(f'Duplicate term ID {key}.')
            data.terms[key] = row['name']
        elif table == 'wp_term_taxonomy' and row['taxonomy'] in TAXONOMIES:
            key = source_id(row['term_taxonomy_id'])
            if key in data.taxonomies:
                raise ImportDataError(f'Duplicate taxonomy ID {key}.')
            data.taxonomies[key] = row
        elif table == 'wp_term_relationships':
            data.relationships[source_id(row['object_id'])].add(source_id(row['term_taxonomy_id']))
        # The lookup table is syntax-checked but its caches/sales/ratings are not imported.
    image_ids = set()
    for product_id in data.products:
        thumbnail = data.meta.get(product_id, {}).get('_thumbnail_id')
        if thumbnail and str(thumbnail).isdigit():
            image_ids.add(int(thumbnail))
    data.attachments.intersection_update(image_ids)
    data.meta = {key: value for key, value in data.meta.items()
                 if key in data.products or key in data.attachments}
    data.relationships = {key: value for key, value in data.relationships.items()
                          if key in data.products}
    return data
