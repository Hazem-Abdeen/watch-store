from oscar.apps.catalogue.views import *  # noqa: F401,F403
from oscar.apps.catalogue.views import ProductDetailView as OscarProductDetailView
from catalogue_import.visibility import with_storefront_image


class ProductDetailView(OscarProductDetailView):
    def get_queryset(self):
        # Applies before redirects, including customer-site staff previews.
        return with_storefront_image(super().get_queryset())

    def get_context_data(self, **kwargs):
        self.object._prefetched_public_children = list(with_storefront_image(self.object.children.public()))
        return super().get_context_data(**kwargs)
