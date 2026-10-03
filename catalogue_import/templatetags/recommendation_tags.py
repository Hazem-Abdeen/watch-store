from django import template

from oscar.core.loading import get_model

from catalogue_import.recommendations import card_products, recommended_products

register = template.Library()


@register.simple_tag(takes_context=True)
def product_recommendations(context, product):
    return recommended_products(product, context['request'].strategy)


@register.simple_tag
def prepare_recent_cards(products):
    """Keep Oscar's cookie selection/order, batch-load its card dependencies."""
    ids = [product.pk for product in products]
    if not ids:
        return []
    Product = get_model('catalogue', 'Product')
    loaded = {product.pk: product for product in card_products(
        Product.objects.browsable().filter(pk__in=ids),
    )}
    return [loaded[pk] for pk in ids if pk in loaded]
