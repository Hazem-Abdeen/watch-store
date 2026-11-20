from oscar.apps.catalogue.views import *  # noqa: F401,F403
from oscar.apps.catalogue.views import ProductDetailView as OscarProductDetailView
from oscar.apps.catalogue.views import ProductCategoryView as OscarProductCategoryView
from catalogue_import.visibility import with_storefront_image
from config.catalogue.gender import GENDER_CHOICES


class ProductCategoryView(OscarProductCategoryView):
    def form_invalid(self, form):
        # Haystack's invalid-form path otherwise has no queryset for facets.
        # Invalid gender choices must never fall back to unfiltered products.
        self.queryset = self.get_queryset().none()
        return self.render_to_response(self.get_context_data(
            form=form, query='', object_list=self.queryset,
        ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context['form']
        gender = form.cleaned_data.get('gender', '') if form.is_valid() else ''
        context['brand_gender'] = gender
        context['brand_gender_label'] = next((label for value, label in GENDER_CHOICES if value == gender), '')
        return context


class ProductDetailView(OscarProductDetailView):
    def get_queryset(self):
        # Applies before redirects, including customer-site staff previews.
        return with_storefront_image(super().get_queryset())

    def get_context_data(self, **kwargs):
        self.object._prefetched_public_children = list(with_storefront_image(self.object.children.public()))
        return super().get_context_data(**kwargs)
