"""Browser QA server on a disposable DB; production inventory is never changed."""
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings

preview_directory = TemporaryDirectory(prefix='abdeen-detail-preview-')
preview_db = Path(preview_directory.name) / 'db.sqlite3'
with sqlite3.connect(f'file:{settings.DATABASES["default"]["NAME"]}?mode=ro', uri=True) as source:
    with sqlite3.connect(preview_db) as target:
        source.backup(target)
settings.DATABASES['default']['NAME'] = preview_db
settings.ROOT_URLCONF = __name__

import django
django.setup()
from django.contrib.auth import get_user_model, login
from django.core.management import call_command
from django.http import JsonResponse
from django.urls import path
from oscar.core.loading import get_model
from config.urls import urlpatterns as storefront_urls

Product = get_model('catalogue', 'Product')
StockRecord = get_model('partner', 'StockRecord')
products = list(Product.objects.filter(structure='standalone', images__isnull=False,
                                      stockrecords__num_in_stock__gte=1).distinct()[:5])
assert len(products) == 5, 'Browser QA needs five existing products with real images.'
roles = dict(zip(('in_stock', 'out_of_stock', 'no_description', 'mixed', 'unavailable'), products))
roles['out_of_stock'] = Product.objects.filter(
    structure='standalone', images__isnull=False, stockrecords__num_in_stock=0,
).distinct().first()
assert roles['out_of_stock'], 'Browser QA needs an actually out-of-stock catalogue product.'
StockRecord.objects.filter(product=roles['no_description']).update(partner_sku='ABDEEN-999999')
# A controlled multi-quantity fixture exists only in this disposable database.
StockRecord.objects.filter(product=roles['mixed']).update(num_in_stock=3, num_allocated=0)
roles['no_description'].description = ''
roles['no_description'].save()
roles['mixed'].description = '<p>A considered design for everyday wear.</p>\n' + roles['mixed'].description
roles['mixed'].save()
attribute, _ = get_model('catalogue', 'ProductAttribute').objects.get_or_create(
    product_class=roles['mixed'].product_class, code='guarantee', defaults={'name': 'Guarantee', 'type': 'text'},
)
get_model('catalogue', 'ProductAttributeValue').objects.update_or_create(
    product=roles['mixed'], attribute=attribute, defaults={'value_text': 'Two Years (International)'},
)
get_model('catalogue', 'ProductImage').objects.create(
    product=roles['mixed'], original=roles['in_stock'].primary_image().original.name, display_order=10,
    caption='Second QA image',
)
reference = roles['unavailable']
roles['unavailable'] = Product.objects.create(title=reference.title, product_class=reference.product_class)

def fixture(request):
    role = request.GET.get('role')
    if role in ('customer', 'staff', 'superuser'):
        user, _ = get_user_model().objects.get_or_create(username=f'detail-preview-{role}', defaults={
            'email': f'{role}@example.test', 'is_staff': role != 'customer',
            'is_superuser': role == 'superuser',
        })
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return JsonResponse({key: product.get_absolute_url() for key, product in roles.items()})

urlpatterns = [path('__detail_fixture__/', fixture), *storefront_urls]
if __name__ == '__main__':
    try:
        call_command('runserver', '127.0.0.1:8021', use_reloader=False)
    finally:
        preview_directory.cleanup()
