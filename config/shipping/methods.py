from decimal import Decimal

from oscar.apps.shipping.methods import FixedPrice


class Delivery(FixedPrice):
    code = 'jordan-delivery'
    name = 'Delivery'
    description = '1–2 business days'
    charge_excl_tax = Decimal('2.00')
    charge_incl_tax = Decimal('2.00')
