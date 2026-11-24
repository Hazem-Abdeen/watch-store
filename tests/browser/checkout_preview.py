"""Disposable COD browser fixture. Never imported by the storefront URLconf."""
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings

preview_directory = TemporaryDirectory(prefix='abdeen-cod-preview-')
with sqlite3.connect(f'file:{settings.DATABASES["default"]["NAME"]}?mode=ro', uri=True) as source:
    with sqlite3.connect(Path(preview_directory.name) / 'db.sqlite3') as target:
        source.backup(target)
settings.DATABASES['default']['NAME'] = Path(preview_directory.name) / 'db.sqlite3'
settings.EMAIL_BACKEND = ('django.core.mail.backends.console.EmailBackend'
                          if os.environ.get('CONSOLE_ORDER_EMAILS') == '1'
                          else 'django.core.mail.backends.locmem.EmailBackend')
settings.ABDEEN_ORDER_NOTIFICATION_EMAILS = ['ops@example.test', 'owner@example.test', 'sales@example.test']
settings.ROOT_URLCONF = __name__

import django
django.setup()
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import JsonResponse
from django.urls import path
from oscar.core.loading import get_model
from config.urls import urlpatterns as storefront_urls
from config.checkout.notifications import order_contact_email

User = get_user_model()
Product = get_model('catalogue', 'Product')
product_class = get_model('catalogue', 'ProductClass').objects.create(name='COD browser fixture', track_stock=True)
product = Product.objects.create(title='Abdeen COD preview watch', product_class=product_class)
partner = get_model('partner', 'Partner').objects.create(name='COD preview supplier')
get_model('partner', 'StockRecord').objects.create(product=product, partner=partner,
    partner_sku='COD-PREVIEW', price_currency='JOD', price='189.00', num_in_stock=100)
image = get_model('catalogue', 'ProductImage').objects.exclude(original='').first()
if image:
    get_model('catalogue', 'ProductImage').objects.create(product=product, original=image.original.name)
country, _ = get_model('address', 'Country').objects.get_or_create(iso_3166_1_a2='JO', defaults={
    'iso_3166_1_a3': 'JOR', 'name': 'Jordan', 'printable_name': 'Jordan'})
country.is_shipping_country = True
country.save()
for width in [1440, 1024, 768, 390, 320]:
    user = User.objects.create_user(f'cod-browser-{width}', email=f'cod-browser-{width}@example.test', password='Browser-example-493!')
    get_model('address', 'UserAddress').objects.create(user=user, first_name='Preview', last_name='Customer',
        line1='24 Saved Street', line4='Amman', country=country, phone_number='+962791234567', is_default_for_shipping=True)

def fixture(request):
    width = request.GET.get('width', '1440')
    user = User.objects.get(username=f'cod-browser-{width}')
    return JsonResponse({'product': product.get_absolute_url(), 'email': user.email})

def result(request):
    order = get_model('order', 'Order').objects.get(pk=request.session['checkout_order_id'])
    source = order.sources.get()
    return JsonResponse({'number': order.number, 'user': order.user_id, 'email': order_contact_email(order),
        'account_email': order.user.email if order.user_id else None,
        'phone': str(order.shipping_address.phone_number), 'address': order.shipping_address.line1,
        'total': str(order.total_incl_tax), 'shipping': str(order.shipping_incl_tax),
        'source': source.source_type.name, 'debited': str(source.amount_debited),
        'allocated': str(source.amount_allocated), 'balance': str(source.balance),
        'transactions': source.transactions.count(), 'payment_events': order.payment_events.count(),
        'basket_orders': get_model('order', 'Order').objects.filter(basket_id=order.basket_id).count(),
        'notifications': list(order.email_notifications.order_by('kind').values('kind', 'status'))})

urlpatterns = [path('__cod_fixture__/', fixture), path('__cod_result__/', result), *storefront_urls]
if __name__ == '__main__':
    try:
        call_command('runserver', '127.0.0.1:8023', use_reloader=False)
    finally:
        preview_directory.cleanup()
