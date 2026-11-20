"""Dynamic brands and live gender options in at most three database queries."""
from urllib.parse import urlencode

from django import template
from oscar.core.loading import get_model

from config.catalogue.gender import GENDER_CHOICES, gender_products
from homepage.brands import BRANDS_ROOT_SLUG

register = template.Library()


@register.simple_tag
def brand_navigation():
    Category = get_model('catalogue', 'Category')
    categories = list(Category.objects.filter(depth__lte=2).order_by('path'))
    root = next((c for c in categories if c.depth == 1 and c.slug == BRANDS_ROOT_SLUG), None)
    if root is None or not root.is_public or root.exclude_from_menu:
        return {'brands': [], 'url': None}
    brands = sorted((c for c in categories if c.depth == 2 and c.path.startswith(root.path)
                     and c.is_public and c.ancestors_are_public and not c.exclude_from_menu),
                    key=lambda c: (c.name.casefold(), c.pk))
    # A watch can be assigned to a brand or any of its collection descendants.
    # Read the distinct brand paths for each gender in bulk, never per brand.
    paths_by_gender = {
        gender: set(gender_products(gender).filter(categories__path__startswith=root.path)
                    .order_by().values_list('categories__path', flat=True).distinct())
        for gender, _label in GENDER_CHOICES
    } if brands else {}
    result = []
    for brand in brands:
        url = brand._get_absolute_url(parent_slug=root.slug)
        genders = [{'name': label, 'url': f'{url}?{urlencode({"gender": gender})}'}
                   for gender, label in GENDER_CHOICES
                   if any(path.startswith(brand.path) for path in paths_by_gender[gender])]
        result.append({'name': brand.name, 'pk': brand.pk, 'url': url, 'genders': genders})
    return {'brands': result, 'url': root.get_absolute_url()}
