from oscar.apps.search.facets import *  # noqa: F401,F403
from oscar.apps.search.facets import base_sqs as oscar_base_sqs
from oscar.core.loading import get_model
from catalogue_import.visibility import with_storefront_image


def base_sqs():
    # Current DB visibility filters results BEFORE pagination and facets. Index
    # all public canonical records so image changes need no bulk index rebuild.
    ids = list(with_storefront_image(get_model('catalogue', 'Product').objects.browsable()).values_list('pk', flat=True))
    return oscar_base_sqs().filter(django_id__in=ids) if ids else oscar_base_sqs().none()
