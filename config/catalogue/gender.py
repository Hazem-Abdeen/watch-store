"""Live gender matching shared by the brand menu and Oscar category filtering."""
from django.db.models import Q
from django.db.models.functions import Lower, Trim
from oscar.core.loading import get_model

from catalogue_import.visibility import with_storefront_image

GENDER_CHOICES = (('men', 'Men'), ('women', 'Women'))


def gender_products(gender):
    """Browsable watches only; keep Oscar's stock/purchasing rules unchanged.

    Unisex watches belong to both choices. A public, image-bearing variant can
    supply its parent's gender, but child products never become listing cards.
    """
    Product = get_model('catalogue', 'Product')
    AttributeValue = get_model('catalogue', 'ProductAttributeValue')
    products = with_storefront_image(Product.objects.browsable()).filter(
        product_class__name__iexact='Watch',
    )
    if gender not in dict(GENDER_CHOICES):
        return products.none()
    values = AttributeValue.objects.filter(attribute__code='gender').annotate(
        gender_text=Lower(Trim('value_text')),
        gender_option=Lower(Trim('value_option__option')),
    ).filter(Q(gender_text__in=(gender, 'unisex')) | Q(gender_option__in=(gender, 'unisex')))
    matching_ids = values.values('product_id')
    children = with_storefront_image(Product.objects.public()).filter(
        structure=Product.CHILD, pk__in=matching_ids,
    )
    return products.filter(Q(pk__in=matching_ids) | Q(pk__in=children.values('parent_id')))
