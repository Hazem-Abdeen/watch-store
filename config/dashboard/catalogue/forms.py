from django import forms
from django.utils.translation import gettext_lazy as _
from oscar.apps.dashboard.catalogue.forms import ProductSearchForm as OscarProductSearchForm
from oscar.apps.dashboard.catalogue.forms import StockRecordForm as OscarStockRecordForm


class ProductSearchForm(OscarProductSearchForm):
    sku = forms.CharField(max_length=128, required=False, label=_('SKU'))
    product_id = forms.IntegerField(
        min_value=1, max_value=9223372036854775807, required=False, label=_('Product ID'),
    )


class StockRecordForm(OscarStockRecordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.availability_only:
            for name in ['num_in_stock', 'low_stock_threshold']:
                if name in self.fields:
                    self.fields[name].required = False
                    self.fields[name].disabled = True
                    self.fields[name].widget = forms.HiddenInput()
        else:
            self.fields.pop('is_available', None)

    class Meta(OscarStockRecordForm.Meta):
        fields = list(OscarStockRecordForm.Meta.fields)
        fields.insert(fields.index('price') + 1, 'regular_price')
        fields.append('is_available')
        help_texts = {
            'regular_price': 'Optional original price, in the same currency and tax basis as Price. '
                             'Shown crossed out only when higher than Price.',
        }
