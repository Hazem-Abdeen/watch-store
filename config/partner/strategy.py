"""Staff-controlled availability without fabricated inventory quantities."""
from oscar.apps.partner.strategy import Default as OscarDefault
from oscar.apps.partner.strategy import Selector as OscarSelector
from oscar.apps.partner.availability import Available, Unavailable


class AvailableToOrder(Available):
    code = 'available_to_order'
    message = 'Available to order; availability confirmed before dispatch'


class Default(OscarDefault):
    def availability_policy(self, product, stockrecord):
        if stockrecord and stockrecord.availability_only:
            return AvailableToOrder() if stockrecord.is_available else Unavailable()
        return super().availability_policy(product, stockrecord)


class Selector(OscarSelector):
    def strategy(self, request=None, user=None, **kwargs):
        return Default(request)
