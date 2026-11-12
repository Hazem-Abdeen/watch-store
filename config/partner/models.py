from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from oscar.apps.partner.abstract_models import AbstractStockRecord


class StockRecord(AbstractStockRecord):
    availability_only = models.BooleanField(default=False, editable=False)
    is_available = models.BooleanField(
        _('Available to order'), default=False,
        help_text='Accept orders subject to manual availability confirmation. No inventory quantity is tracked.',
    )

    @property
    def can_track_allocations(self):
        return not self.availability_only and self.product.get_product_class().track_stock

    def allocate(self, quantity):
        if self.availability_only:
            from oscar.apps.order.exceptions import UnableToPlaceOrder
            # Order placement is atomic. Recheck the staff-controlled flag inside
            # that transaction, including when it changed after basket review.
            current = type(self).objects.select_for_update().get(pk=self.pk)
            if not current.is_available:
                raise UnableToPlaceOrder('This item is no longer available to order.')
            return
        return super().allocate(quantity)

    allocate.alters_data = True

    regular_price = models.DecimalField(
        _('Regular price'), max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
    )

    class Meta(AbstractStockRecord.Meta):
        constraints = [
            models.CheckConstraint(
                condition=models.Q(availability_only=False) | (
                    models.Q(num_in_stock__isnull=True) &
                    (models.Q(num_allocated__isnull=True) | models.Q(num_allocated=0))
                ),
                name='availability_only_has_no_inventory',
            ),
            models.CheckConstraint(
                condition=models.Q(regular_price__isnull=True) | models.Q(regular_price__gt=0),
                name='partner_stockrecord_regular_price_positive',
            ),
        ]


# Register our stock record first; retain Oscar's other partner models.
from oscar.apps.partner.models import *  # noqa: E402,F401,F403
