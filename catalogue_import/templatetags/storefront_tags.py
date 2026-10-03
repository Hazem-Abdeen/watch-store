"""Presentation helpers for Oscar's existing storefront data and forms."""

import re
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.safestring import SafeData, mark_safe
from django.utils.translation import gettext as _
from catalogue_import.specifications import SPECIFICATIONS, plain_text, specification_code
from haystack.backends.simple_backend import SimpleSearchBackend
from oscar.templatetags.currency_filters import currency

register = template.Library()


@register.filter
def card_currency(value, currency_code):
    """Compact JOD label only; Oscar still supplies the amount and currency."""
    if currency_code != 'JOD':
        return currency(value, currency_code)
    try:
        amount = format(Decimal(value), 'f')
    except (InvalidOperation, TypeError, ValueError):
        return ''
    if '.' in amount:
        amount = amount.rstrip('0').rstrip('.')
    return f'{amount} JOD'


@register.simple_tag(takes_context=True)
def product_card_brand(context, product):
    """Use the same assigned Brands categories as the homepage, without writes."""
    if getattr(product, 'storefront_card_brand', None):
        return product.storefront_card_brand
    if hasattr(product, 'homepage_brand_name'):
        return product.homepage_brand_name
    cache = context.render_context.dicts[0]
    if 'product_card_brands' not in cache:
        from oscar.core.loading import get_model
        from homepage.brands import BRANDS_ROOT_SLUG

        categories = get_model('catalogue', 'Category').objects.for_menu()
        root = categories.filter(depth=1, slug=BRANDS_ROOT_SLUG).first()
        cache['product_card_brands'] = set(
            categories.filter(path__startswith=root.path, depth=root.depth + 1)
            .values_list('pk', flat=True)
        ) if root else set()
    brand_ids = cache['product_card_brands']
    return ', '.join(category.name for category in product.get_categories()
                     if category.pk in brand_ids)


def _internal_attribute(value):
    key = re.sub(r'[^a-z0-9]+', '_', value.casefold()).strip('_')
    return any(key == prefix or key.startswith(prefix + '_') for prefix in (
        'woocommerce', 'woo', 'wc', 'wp', 'migration', 'migrated', 'import',
        'imported', 'internal', 'legacy', 'source',
    ))


@register.filter
def customer_attributes(values):
    """Hide import provenance in the storefront only; retain Oscar's real values."""
    return [value for value in values if not (
        _internal_attribute(value.attribute.code) or _internal_attribute(value.attribute.name)
    )]


@register.filter
def customer_reference(value):
    """The old importer used a synthetic UPC; it is not a customer reference."""
    return bool(value) and not value.casefold().startswith('wc-abdeen-')


@register.filter
def customer_partner_sku(stockrecord):
    """Only the selected Oscar partner SKU, never UPC or an importer fallback."""
    sku = (getattr(stockrecord, 'partner_sku', '') or '').strip()
    # The WooCommerce importer manufactures ABDEEN-<source ID> for absent SKUs.
    # Conservatively hide that reserved shape even on older/unmapped records.
    if not sku or re.fullmatch(r'ABDEEN-\d+', sku, flags=re.I) or _internal_attribute(sku):
        return ''
    return sku


@register.filter
def storefront_availability(availability):
    """Use Oscar's decision, never its quantity-bearing display message."""
    if availability.is_available_to_buy:
        return _('In stock')
    if availability.code == 'outofstock':
        return _('Out of stock')
    return _('Unavailable')


@register.filter(is_safe=True)
def stock_safe_message(value):
    """Redact stock limits in rendered Oscar errors, preserving other messages."""
    value = str(value)
    was_safe = isinstance(value, SafeData)
    value = re.sub(r'In stock \(\d+ available\)', _('In stock'), value)
    value = re.sub(r'a maximum of \d+ can be bought',
                   _('the requested quantity is not available'), value)
    value = re.sub(r'Available stock is only \d+, which has been exceeded because',
                   _('The requested quantity is not available because'), value)
    return mark_safe(value) if was_safe else value


@register.simple_tag
def product_details(product):
    """A read-only view of prose and specs; explicit structured values win.

    Only labeled facts are lifted from descriptions. Other prose is retained as
    escaped text, so mixed legacy descriptions do not repeat specification rows.
    """
    specs = {}
    labels = {code: label.title() for code, label in SPECIFICATIONS.items()}
    # Useful watch facts outside the importer's core specification list.
    labels.update(
        glass='Glass', thickness='Thickness', weight='Weight', functions='Functions',
        country_of_manufacture='Country of Manufacture', additional_features='Additional Features',
        accuracy='Accuracy', world_time='World Time', smartphone_link_feature='Smartphone Link',
        app_connectivity_feature='App Connectivity', power_supply_and_battery_life='Power Supply and Battery Life',
    )

    def watch_code(label):
        key = re.sub(r'[^a-z0-9]+', '_', label.casefold()).strip('_')
        return specification_code(label) or (key if key in labels else None)

    aliases = {}
    attributes = product.get_attribute_values()
    if hasattr(attributes, 'select_related'):
        attributes = attributes.select_related('attribute', 'value_option').prefetch_related('value_multi_option')
    for av in customer_attributes(attributes):
        code = watch_code(av.attribute.code) or watch_code(av.attribute.name)
        if code not in labels:  # Don't expose arbitrary technical attributes.
            continue
        value = ' '.join(plain_text(str(av.value_as_text)).split())
        if value:
            specs.setdefault(code, value)
            aliases[av.attribute.name.casefold().rstrip(':')] = code
    prose = []
    # Legacy WordPress media shortcodes aren't customer-facing description text.
    description = re.sub(r'\[(video|embed)\b[^\]]*\].*?\[/\1\]', '',
                         product.description or '', flags=re.I | re.S)
    description = re.sub(r'\[/?(?:video|embed)\b[^\]]*\]', '', description, flags=re.I)
    lines = [line.strip() for line in plain_text(description).splitlines() if line.strip()]
    pending = None
    for line in lines:
        pair = re.split(r':|\t', line, maxsplit=1)
        label = pair[0].strip()
        code = watch_code(label) or aliases.get(label.casefold())
        if _internal_attribute(label):
            pending = None
            continue
        if code:
            if len(pair) == 2 and pair[1].strip():
                specs.setdefault(code, pair[1].strip())
                pending = None
            else:
                pending = code
        elif pending:
            specs.setdefault(pending, line)
            pending = None
        else:
            prose.append(line)
    return {
        'brand': specs.get('brand', ''),
        'description': '\n\n'.join(prose),
        'specifications': [(label, specs[code]) for code, label in labels.items() if specs.get(code)],
    }


@register.simple_tag
def catalogue_sorting_available(form):
    # SimpleEngine ignores order_by. Keep its inert controls out of the UI
    # without altering the query or inventing an alternative sorting path.
    return bool(form) and not isinstance(
        form.searchqueryset.query.backend, SimpleSearchBackend,
    )
