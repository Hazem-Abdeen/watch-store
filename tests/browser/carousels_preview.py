"""Run carousel QA against a disposable copy, never the working catalogue."""
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings

preview_directory = TemporaryDirectory(prefix='abdeen-carousels-')
preview_db = Path(preview_directory.name) / 'db.sqlite3'
with sqlite3.connect(f'file:{settings.DATABASES["default"]["NAME"]}?mode=ro', uri=True) as source:
    with sqlite3.connect(preview_db) as target:
        source.backup(target)
settings.DATABASES['default']['NAME'] = preview_db

import django
django.setup()
from django.core.management import call_command
from oscar.core.loading import get_model
from catalogue_import.visibility import with_storefront_image
from config.homepage import range_product_queryset

Product = get_model('catalogue', 'Product')
# Start with the actual curated watches: sale-price accessibility labels are
# essential fixtures for the mobile overflow regression.
products = list(range_product_queryset('Best Sellers').filter(structure='standalone')[:19])
products += list(with_storefront_image(Product.objects.browsable()).filter(
    structure='standalone', title__icontains='watch',
).exclude(pk__in=[product.pk for product in products])[:19 - len(products)])
assert len(products) == 19
for name in ('Best Sellers', 'New Arrivals'):
    selection, _ = get_model('offer', 'Range').objects.get_or_create(name=name)
    selection.included_products.clear()
    selection.excluded_products.clear()
    for index, product in enumerate(products):
        selection.add_product(product, display_order=index)
products[1].title = 'A longer watch title with stainless steel bracelet and a detailed model reference'
products[1].save()
products[10].title = 'An exceptionally long later-batch watch title ' * 8
products[10].save()
get_model('catalogue', 'ProductImage').objects.filter(product=products[2]).update(original='products/missing-carousel.jpg')
call_command('runserver', '127.0.0.1:8026', use_reloader=False)
