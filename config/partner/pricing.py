"""Reference prices for display/import only. Oscar owns payable prices."""
from copy import copy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator


def valid_regular_price(value):
    """Accept only positive, finite values representable by the stock field."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
        DecimalValidator(max_digits=12, decimal_places=2)(amount)
        return amount if amount.is_finite() and amount > 0 else None
    except (InvalidOperation, ValueError, TypeError, ValidationError):
        return None


def sale_presentation(request, product, purchase):
    """Price a detached reference record through the same Oscar strategy.

    Never save it or pass it to a basket. Parent prices can aggregate different
    children, so they must not advertise a single child's reference price.
    """
    stock = purchase.stockrecord
    if product.is_parent or stock is None or not purchase.price.exists:
        return None
    regular = stock.regular_price
    if regular is None or stock.price is None or not regular > stock.price >= 0:
        return None
    reference = copy(stock)
    reference.price = regular
    reference_price = request.strategy.fetch_for_product(product, stockrecord=reference).price
    current_price = purchase.price
    if (not reference_price.exists or reference_price.currency != current_price.currency
            or reference_price.is_tax_known != current_price.is_tax_known):
        return None
    # Both amounts have the same currency and tax treatment, including any
    # rounding applied by the strategy. Unknown tax is displayed excl. tax.
    old = reference_price.incl_tax if current_price.is_tax_known else reference_price.excl_tax
    current = current_price.incl_tax if current_price.is_tax_known else current_price.excl_tax
    if old <= current or current < 0:
        return None
    percentage = ((old - current) * Decimal('100') / old).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP)
    return {'regular': old, 'current': current, 'percentage': percentage,
            'currency': current_price.currency, 'is_tax_known': current_price.is_tax_known}
