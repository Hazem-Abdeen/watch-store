"""Validate raster logos and a static, self-contained subset of SVG."""
from io import BytesIO
from pathlib import Path
import re
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_LOGO_BYTES = 2 * 1024 * 1024
SVG_TAGS = set('svg g defs path rect circle ellipse line polygon polyline text tspan title desc '
               'linearGradient radialGradient stop clipPath mask pattern use style'.split())
SVG_ATTRIBUTES = set('id class style viewBox version width height x y x1 x2 y1 y2 cx cy r rx ry '
                     'd points transform fill fill-opacity fill-rule stroke stroke-width '
                     'stroke-opacity stroke-linecap stroke-linejoin stroke-miterlimit '
                     'stroke-dasharray stroke-dashoffset opacity clip-path clip-rule mask '
                     'offset stop-color stop-opacity gradientUnits gradientTransform spreadMethod '
                     'fx fy fr href preserveAspectRatio patternUnits patternContentUnits '
                     'patternTransform maskUnits maskContentUnits clipPathUnits '
                     'font-family font-size font-weight font-style text-anchor dominant-baseline '
                     'letter-spacing word-spacing dx dy rotate textLength lengthAdjust '
                     'color display visibility overflow vector-effect enable-background '
                     'type {http://www.w3.org/XML/1998/namespace}space'.split())


def validate_svg(data):
    try:
        text = data.decode('utf-8-sig')
        if re.search(r'<!DOCTYPE|<!ENTITY|<\?(?!xml\s)', text, re.I):
            raise ValueError
        root = ElementTree.fromstring(text)
        if root.tag != '{http://www.w3.org/2000/svg}svg':
            raise ValueError
        for element in root.iter():
            if element.tag.removeprefix('{http://www.w3.org/2000/svg}') not in SVG_TAGS:
                raise ValueError
            for name, value in element.attrib.items():
                name = name.removeprefix('{http://www.w3.org/1999/xlink}')
                if name not in SVG_ATTRIBUTES:
                    raise ValueError
                if name == 'type' and value != 'text/css':
                    raise ValueError
                if name == 'href' and not re.fullmatch(r'#[\w.-]+', value):
                    raise ValueError
                validate_svg_style(value)
            if element.tag == '{http://www.w3.org/2000/svg}style':
                validate_svg_style(element.text or '')
    except (ValueError, ElementTree.ParseError, UnicodeError):
        raise ValidationError('Upload a static, self-contained SVG without scripts, external links, '
                              'embedded images or animation. Export as plain SVG if needed.')


def validate_svg_style(value):
    # Local paint/clip references are useful; external resources, CSS escapes,
    # processing instructions, imports and active content are not logo artwork.
    without_local_urls = re.sub(r'url\(\s*[\'"]?#[\w.-]+[\'"]?\s*\)', '', value, flags=re.I)
    if re.search(r'url\s*\(|@|\\|/\*|expression\s*\(|behavior\s*:|-moz-binding', without_local_urls, re.I):
        raise ValueError


def validate_brand_logo(value):
    if not value or getattr(value, '_committed', False):
        return
    if value.size > MAX_LOGO_BYTES:
        raise ValidationError('Logo files must be 2 MB or smaller.')
    extension = Path(value.name).suffix.lower()
    if extension not in {'.png', '.webp', '.svg'}:
        raise ValidationError('Upload a PNG, WebP or SVG logo.')
    try:
        value.seek(0)
        data = value.read(MAX_LOGO_BYTES + 1)
        if extension == '.svg':
            validate_svg(data)
        else:
            try:
                with Image.open(BytesIO(data)) as image:
                    if image.format != {'.png': 'PNG', '.webp': 'WEBP'}[extension]:
                        raise ValidationError('The file contents do not match the logo format.')
                    image.verify()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                raise ValidationError('Upload a valid PNG or WebP image.')
    finally:
        value.seek(0)
