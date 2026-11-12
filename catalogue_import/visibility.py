"""Image visibility is a customer query rule, independent of publication/stock."""
from django.db.models import Exists, OuterRef
from oscar.core.loading import get_model


def with_storefront_image(queryset):
    images = get_model('catalogue', 'ProductImage').objects.filter(product_id=OuterRef('pk')).exclude(
        original='',
    ).exclude(original__isnull=True).exclude(
        original__iregex=r'(^|/)(image_not_found\.[^/]+|watch-placeholder\.[^/]+)$',
    )
    return queryset.filter(Exists(images))
