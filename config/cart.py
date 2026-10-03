"""Read-only cart presentation; all writes still use Oscar's basket views."""
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from oscar.core.loading import get_class


@method_decorator(never_cache, name='dispatch')
class CartDrawerView(get_class('basket.views', 'BasketView')):
    http_method_names = ['get', 'head', 'options']
    template_name = 'oscar/basket/partials/drawer_content.html'
