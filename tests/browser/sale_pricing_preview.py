"""Sale pricing fixtures in a disposable database and search index."""
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings

preview = TemporaryDirectory(prefix='abdeen-sale-preview-')
with sqlite3.connect(f'file:{settings.DATABASES["default"]["NAME"]}?mode=ro', uri=True) as source:
    with sqlite3.connect(Path(preview.name) / 'db.sqlite3') as target:
        source.backup(target)
settings.DATABASES['default']['NAME'] = Path(preview.name) / 'db.sqlite3'
settings.HAYSTACK_CONNECTIONS['default']['PATH'] = str(Path(preview.name) / 'search')
settings.ROOT_URLCONF = __name__

import django
django.setup()
from django.core.management import call_command
from django.http import JsonResponse
from django.urls import path
from haystack import connections
from oscar.core.loading import get_model
from config.urls import urlpatterns as storefront_urls

urlpatterns = list(storefront_urls)

Product = get_model('catalogue', 'Product')
category = get_model('catalogue', 'Category').add_root(name='Sale pricing browser checks')
product_class = get_model('catalogue', 'ProductClass').objects.create(name='Sale browser watches', track_stock=True)
partner = get_model('partner', 'Partner').objects.create(name='Sale browser supplier')
image = get_model('catalogue', 'ProductImage').objects.exclude(original='').first()
products = []
for label, regular in [('Markdown', '120'), ('Normal', None), ('Equal', '95'), ('Lower', '90')]:
    product = Product.objects.create(title=f'{label} preview watch', product_class=product_class)
    product.categories.add(category)
    get_model('partner', 'StockRecord').objects.create(product=product, partner=partner,
        partner_sku=f'SALE-{product.pk}', price_currency='JOD', price='95', regular_price=regular, num_in_stock=10)
    if image:
        get_model('catalogue', 'ProductImage').objects.create(product=product, original=image.original.name)
    connections['default'].get_unified_index().get_index(Product).update_object(product)
    products.append({'label': label, 'url': product.get_absolute_url()})


def fixture(request):
    return JsonResponse({'category': category.get_absolute_url(), 'products': products})


urlpatterns.insert(0, path('__sale_fixture__/', fixture))
if __name__ == '__main__':
    try:
        call_command('runserver', '127.0.0.1:8025', use_reloader=False)
    finally:
        preview.cleanup()
