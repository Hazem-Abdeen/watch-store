from django import template
from config.partner.pricing import sale_presentation

register = template.Library()


@register.simple_tag
def product_sale(request, product, purchase):
    return sale_presentation(request, product, purchase)
