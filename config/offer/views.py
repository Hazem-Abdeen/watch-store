from oscar.apps.offer.views import *  # noqa: F401,F403
from oscar.apps.offer.views import RangeDetailView as OscarRangeDetailView
from oscar.apps.offer.views import OfferDetailView as OscarOfferDetailView
from catalogue_import.visibility import with_storefront_image


class RangeDetailView(OscarRangeDetailView):
    def get_queryset(self):
        return with_storefront_image(super().get_queryset())


class OfferDetailView(OscarOfferDetailView):
    def get_queryset(self):
        return with_storefront_image(super().get_queryset().browsable())
