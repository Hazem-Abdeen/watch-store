from django.db.models import Q
from oscar.apps.dashboard.catalogue.views import ProductListView as OscarProductListView

from .forms import ProductSearchForm


class ProductListView(OscarProductListView):
    form_class = ProductSearchForm

    def apply_search(self, queryset):
        queryset = super().apply_search(queryset)
        if not self.form.is_valid():
            return queryset.none()

        sku = self.form.cleaned_data.get('sku')
        if sku:
            queryset = queryset.filter(
                Q(stockrecords__partner_sku__icontains=sku)
                | Q(children__stockrecords__partner_sku__icontains=sku)
            )

        product_id = self.form.cleaned_data.get('product_id')
        if product_id:
            # Oscar lists parents, so searches for variants show their parent.
            queryset = queryset.filter(Q(pk=product_id) | Q(children__pk=product_id))

        return queryset.distinct()
