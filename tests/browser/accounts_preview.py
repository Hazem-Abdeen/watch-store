"""Disposable account/browser fixtures; never mounted in the storefront URLconf."""
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings

preview_directory = TemporaryDirectory(prefix='abdeen-accounts-preview-')
with sqlite3.connect(f'file:{settings.DATABASES["default"]["NAME"]}?mode=ro', uri=True) as source:
    with sqlite3.connect(Path(preview_directory.name) / 'db.sqlite3') as target:
        source.backup(target)
settings.DATABASES['default']['NAME'] = Path(preview_directory.name) / 'db.sqlite3'
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
settings.ROOT_URLCONF = __name__

import django
django.setup()
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import JsonResponse
from django.urls import path
from oscar.apps.customer.utils import get_password_reset_url
from oscar.core.loading import get_model
from config.urls import urlpatterns as storefront_urls

User = get_user_model()
Product = get_model('catalogue', 'Product')
product_class = get_model('catalogue', 'ProductClass').objects.create(name='Account browser fixture', track_stock=True)
product = Product.objects.create(title='Abdeen account preview watch', product_class=product_class)
partner = get_model('partner', 'Partner').objects.create(name='Account preview supplier')
get_model('partner', 'StockRecord').objects.create(product=product, partner=partner,
    partner_sku='ACCOUNT-PREVIEW', price_currency='JOD', price='125.50', num_in_stock=100)
country, _ = get_model('address', 'Country').objects.get_or_create(iso_3166_1_a2='JO', defaults={
    'iso_3166_1_a3': 'JOR', 'name': 'Jordan', 'printable_name': 'Jordan'})
country.is_shipping_country = True
country.save()
for width in [1440, 768, 390, 320]:
    user = User.objects.create_user(f'account-browser-{width}', email=f'account-browser-{width}@example.test', password='Browser-example-493!')
    get_model('address', 'UserAddress').objects.create(user=user, first_name='Preview', last_name='Customer',
        line1='24 Example Street', line4='Amman', postcode='11118', country=country)
    get_model('order', 'Order').objects.create(user=user, number=f'PREVIEW-{width}', currency='JOD',
        total_incl_tax='125.50', total_excl_tax='125.50', shipping_incl_tax='0', shipping_excl_tax='0')

def fixture(request):
    width = request.GET.get('width', '1440')
    user = User.objects.get(username=f'account-browser-{width}')
    return JsonResponse({'product': product.get_absolute_url(), 'email': user.email,
        'reset': get_password_reset_url(user), 'order': f'/accounts/orders/PREVIEW-{width}/'})

urlpatterns = [path('__account_fixture__/', fixture), *storefront_urls]
if __name__ == '__main__':
    try:
        call_command('runserver', '127.0.0.1:8022', use_reloader=False)
    finally:
        preview_directory.cleanup()
