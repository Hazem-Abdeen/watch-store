"""Extract explicitly labeled watch facts; never infer specifications from prose."""

import re
from html import unescape
from html.parser import HTMLParser

from .sql_dump import ImportDataError


SPECIFICATIONS = {
    'brand': 'Brand', 'gender': 'Gender', 'movement': 'Movement', 'case_size': 'Case size',
    'case_material': 'Case material', 'case_color': 'Case color', 'band_material': 'Band material',
    'band_color': 'Band color', 'dial_color': 'Dial color',
    'water_resistance': 'Water resistance', 'guarantee': 'Guarantee',
}
ALIASES = {
    'movement_type': 'movement', 'case_diameter': 'case_size', 'case_colour': 'case_color',
    'strap_material': 'band_material', 'bracelet_material': 'band_material',
    'band_colour': 'band_color', 'strap_color': 'band_color', 'strap_colour': 'band_color',
    'bracelet_color': 'band_color', 'bracelet_colour': 'band_color', 'dial_colour': 'dial_color',
    'water_resistant': 'water_resistance', 'warranty': 'guarantee',
}


def specification_code(label):
    key = re.sub(r'[\s-]+', '_', unescape(label).strip().casefold().rstrip(':'))
    key = key.removeprefix('pa_')
    key = ALIASES.get(key, key)
    return key if key in SPECIFICATIONS else None


class SpecificationText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {'br', 'p', 'div', 'li', 'tr', 'dl'}:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in {'th', 'td', 'dt'}:
            self.parts.append('\t')
        elif tag in {'p', 'div', 'li', 'tr', 'dd', 'dl'}:
            self.parts.append('\n')

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = SpecificationText()
    parser.feed(value or '')
    parser.close()
    return ''.join(parser.parts)


def php_attributes(value):
    """Read bounded PHP scalar/array data only. Objects/references are forbidden."""
    if not value:
        return {}
    data = value.encode('utf-8')
    if len(data) > 65536:
        raise ImportDataError('Product attributes exceed the 64 KiB limit.')
    index = nodes = 0

    def consume(token):
        nonlocal index
        if not data.startswith(token, index):
            raise ImportDataError('Malformed serialized product attributes.')
        index += len(token)

    def integer(delimiter):
        nonlocal index
        end = data.find(delimiter, index)
        if end < 0 or not re.fullmatch(rb'-?\d{1,10}', data[index:end]):
            raise ImportDataError('Malformed attribute length or integer.')
        value = int(data[index:end])
        index = end + len(delimiter)
        return value

    def read(depth=0):
        nonlocal index, nodes
        nodes += 1
        if depth > 8 or nodes > 2000:
            raise ImportDataError('Serialized product attributes are too complex.')
        kind = data[index:index + 1]
        index += 1
        if kind == b'N':
            consume(b';')
            return None
        consume(b':')
        if kind in {b'i', b'b'}:
            number = integer(b';')
            if kind == b'b' and number not in {0, 1}:
                raise ImportDataError('Invalid attribute boolean.')
            return number
        if kind == b's':
            size = integer(b':')
            if size < 0 or size > len(data) - index:
                raise ImportDataError('Invalid attribute string length.')
            consume(b'"')
            try:
                result = data[index:index + size].decode('utf-8')
            except UnicodeError:
                raise ImportDataError('Invalid attribute string encoding.') from None
            index += size
            consume(b'";')
            return result
        if kind == b'a':
            count = integer(b':')
            if not 0 <= count <= 200:
                raise ImportDataError('Invalid attribute array size.')
            consume(b'{')
            result = {}
            for _ in range(count):
                key, item = read(depth + 1), read(depth + 1)
                if not isinstance(key, (str, int)) or key in result:
                    raise ImportDataError('Invalid or duplicate attribute key.')
                result[key] = item
            consume(b'}')
            return result
        raise ImportDataError('Only scalar/array product attributes are supported.')

    result = read()
    if index != len(data) or not isinstance(result, dict):
        raise ImportDataError('Invalid serialized product attributes.')
    return result


def normalized_value(code, value):
    value = ' '.join(plain_text(value).split())
    if code == 'gender':
        value = re.sub(r'\bFor\s+(Men|Women)\b', r'\1', value, flags=re.I)
    if len(value) > 2000:
        raise ImportDataError('Watch specification exceeds 2000 characters.')
    return value


def extract_specifications(description, *, categories=(), attributes=None, taxonomy_values=()):
    specs = {}
    for line in plain_text(description).splitlines():
        pair = re.split(r':|\t', line.strip(), maxsplit=1)
        if len(pair) == 2 and (code := specification_code(pair[0])):
            value = normalized_value(code, pair[1])
            if value:
                specs[code] = value
    # Explicit taxonomy and visible custom attributes take priority over content.
    for label, values in taxonomy_values:
        if code := specification_code(label):
            value = normalized_value(code, ', '.join(sorted(set(values))))
            if value:
                specs[code] = value
    for entry in (attributes or {}).values():
        if not isinstance(entry, dict):
            raise ImportDataError('Malformed product attribute entry.')
        if entry.get('is_taxonomy') or not entry.get('is_visible', 1):
            continue
        label, value = entry.get('name'), entry.get('value')
        if not isinstance(label, str) or not isinstance(value, str):
            raise ImportDataError('Malformed custom product attribute.')
        if code := specification_code(label):
            value = normalized_value(code, value)
            if value:
                specs[code] = value
    brands = sorted({path[1] for path in categories if len(path) > 1 and path[0] == 'Brands'})
    genders = sorted({path[0] for path in categories if path and path[0] in {'Men', 'Women'}})
    if brands and 'brand' not in specs:
        specs['brand'] = ', '.join(brands)
    if genders and 'gender' not in specs:
        specs['gender'] = ', '.join(genders)
    return specs
