"""Keep order-line allocation bookkeeping consistent with availability mode."""
from oscar.apps.order.utils import *  # noqa: F401,F403
from oscar.apps.order.utils import OrderCreator as OscarOrderCreator


class OrderCreator(OscarOrderCreator):
    def update_stock_records(self, line):
        if line.stockrecord.availability_only:
            # Always recheck the flag, even if staff later disables class-level
            # stock tracking. allocate() performs no inventory mutation here.
            line.stockrecord.allocate(line.quantity)
        else:
            super().update_stock_records(line)

    def create_line_models(self, order, basket_line, extra_line_fields=None):
        extra_line_fields = dict(extra_line_fields or {})
        if basket_line.stockrecord.availability_only:
            extra_line_fields['num_allocated'] = 0
        return super().create_line_models(order, basket_line, extra_line_fields)
