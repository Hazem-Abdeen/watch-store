"""Checkout presentation exercised through the unmodified Oscar checkout views."""
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from oscar.apps.payment.exceptions import RedirectRequired, UnableToTakePayment
from oscar.core.loading import get_class, get_model
from oscar.templatetags.currency_filters import currency
from PIL import Image

Product = get_model('catalogue', 'Product')
StockRecord = get_model('partner', 'StockRecord')
Basket = get_model('basket', 'Basket')
Order = get_model('order', 'Order')
Country = get_model('address', 'Country')
UserAddress = get_model('address', 'UserAddress')
PaymentDetailsView = get_class('checkout.views', 'PaymentDetailsView')
Free = get_class('shipping.methods', 'Free')
FixedPrice = get_class('shipping.methods', 'FixedPrice')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CheckoutPresentationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        media_root = cls.enterClassContext(TemporaryDirectory(prefix='abdeen-checkout-test-media-'))
        cls.enterClassContext(override_settings(MEDIA_ROOT=media_root))
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('checkout-customer', email='checkout@example.test')
        cls.country = Country.objects.create(iso_3166_1_a2='JO', iso_3166_1_a3='JOR',
            printable_name='Jordan', name='Jordan', is_shipping_country=True)
        Country.objects.create(iso_3166_1_a2='AE', iso_3166_1_a3='ARE',
            printable_name='United Arab Emirates', name='United Arab Emirates', is_shipping_country=True)
        cls.product_class = get_model('catalogue', 'ProductClass').objects.create(name='Watches', track_stock=True)
        cls.product = Product.objects.create(title='Real watch with a complete model reference', product_class=cls.product_class)
        cls.partner = get_model('partner', 'Partner').objects.create(name='Checkout supplier')
        cls.stock = StockRecord.objects.create(product=cls.product, partner=cls.partner, partner_sku='CHECKOUT-001',
                                               price_currency='JOD', price=Decimal('125.50'), num_in_stock=5)
        data = BytesIO()
        Image.new('RGB', (40, 50), 'white').save(data, format='JPEG')
        cls.image = get_model('catalogue', 'ProductImage').objects.create(product=cls.product,
            original=SimpleUploadedFile('checkout-watch.jpg', data.getvalue(), content_type='image/jpeg'))

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.client.get(self.product.get_absolute_url())

    def url(self, name):
        return reverse('checkout:' + name)

    def post(self, url, data=None, **kwargs):
        return self.client.post(url, {**(data or {}), 'csrfmiddlewaretoken': self.client.cookies['csrftoken'].value}, **kwargs)

    def add(self, quantity=1):
        response = self.post(reverse('basket:add', kwargs={'pk': self.product.pk}), {'quantity': quantity})
        self.assertEqual(response.status_code, 302)
        return Basket.objects.get(owner=self.user, status=Basket.OPEN)

    def address_data(self):
        return {'first_name': 'Test', 'last_name': 'Customer', 'line1': '12 Example Street',
                'line4': 'Amman', 'postcode': '11118', 'country': 'JO', 'notes': 'Test delivery instructions'}

    def address(self):
        response = self.post(self.url('shipping-address'), self.address_data())
        self.assertRedirects(response, self.url('shipping-method'), fetch_redirect_response=False)
        return response

    def ready(self):
        basket = self.add()
        self.address()
        response = self.client.get(self.url('shipping-method'), follow=True)
        self.assertTemplateUsed(response, 'oscar/checkout/payment_details.html')
        return basket

    def test_login_requirements_and_original_view_classes(self):
        self.assertFalse(settings.OSCAR_ALLOW_ANON_CHECKOUT)
        guest = Client()
        names = {'index': 'IndexView', 'shipping-address': 'ShippingAddressView',
                 'shipping-method': 'ShippingMethodView', 'payment-method': 'PaymentMethodView',
                 'payment-details': 'PaymentDetailsView', 'preview': 'PaymentDetailsView', 'thank-you': 'ThankYouView'}
        for name, view in names.items():
            self.assertIs(resolve(self.url(name)).func.view_class, get_class('checkout.views', view))
            self.assertRedirects(guest.get(self.url(name)), reverse('customer:login') + '?next=' + self.url(name),
                                 fetch_redirect_response=False)

    def test_empty_invalid_basket_and_missing_shipping_preconditions(self):
        for step in ['shipping-address', 'shipping-method', 'payment-details', 'preview']:
            self.assertRedirects(self.client.get(self.url(step), follow=True), reverse('basket:summary'))
        self.add()
        self.assertRedirects(self.client.get(self.url('preview')), self.url('shipping-address'), fetch_redirect_response=False)
        self.address()
        self.assertRedirects(self.client.get(self.url('preview')), self.url('shipping-method'), fetch_redirect_response=False)
        self.stock.num_in_stock = 0
        self.stock.save()
        self.assertRedirects(self.client.get(self.url('payment-details')), reverse('basket:summary'), fetch_redirect_response=False)
        self.assertFalse(Order.objects.exists())

    def test_address_validation_real_form_session_and_pending_summary(self):
        self.add()
        response = self.client.get(self.url('shipping-address'))
        self.assertIsInstance(response.context['form'], get_class('checkout.forms', 'ShippingAddressForm'))
        for text in ['data-home-header', 'abdeen-footer', 'abdeen/css/checkout.css', 'Checkout progress',
                     'aria-current="step"', 'name="country"', 'id="new_shipping_address"', self.image.original.url,
                     self.stock.partner_sku, 'Shipping and the final total will appear']:
            self.assertContains(response, text)
        self.assertNotContains(response, '<h3>Order total</h3>')
        response = self.post(self.url('shipping-address'), {'first_name': 'Still entered'})
        self.assertContains(response, 'error-block')
        self.assertContains(response, 'value="Still entered"')
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(self.client.post(self.url('shipping-address'), self.address_data()).status_code, 403)
        self.address()
        self.assertEqual(self.client.session['checkout_data']['shipping']['new_address_fields']['line1'], '12 Example Street')

    def test_address_book_selection_edit_and_delete_are_original_forms(self):
        self.add()
        fields = {**self.address_data(), 'country': self.country}
        fields.pop('notes')
        address = UserAddress.objects.create(user=self.user, is_default_for_shipping=True, **fields)
        response = self.client.get(self.url('shipping-address'))
        self.assertContains(response, f'id="select_shipping_address_{address.pk}"')
        self.assertContains(response, 'name="action" value="ship_to"')
        self.post(self.url('shipping-address'), {'address_id': address.pk, 'action': 'ship_to'})
        self.assertEqual(self.client.session['checkout_data']['shipping']['user_address_id'], address.pk)
        edit = reverse('checkout:user-address-update', kwargs={'pk': address.pk})
        self.assertContains(self.client.get(edit), 'id="update_user_address"')
        self.post(edit, {**self.address_data(), 'line1': 'Updated test address'})
        address.refresh_from_db()
        self.assertEqual(address.line1, 'Updated test address')
        delete = reverse('checkout:user-address-delete', kwargs={'pk': address.pk})
        self.assertContains(self.client.get(delete), f'id="delete_address_{address.pk}"')
        self.post(delete)
        self.assertFalse(UserAddress.objects.filter(pk=address.pk).exists())
        other = get_user_model().objects.create_user('other-customer')
        foreign = UserAddress.objects.create(user=other, **fields)
        self.assertEqual(self.client.get(reverse('checkout:user-address-update', kwargs={'pk': foreign.pk})).status_code, 404)

    def test_single_shipping_method_still_skips_choice_page(self):
        self.add()
        self.address()
        response = self.client.get(self.url('shipping-method'))
        self.assertRedirects(response, self.url('payment-method'), fetch_redirect_response=False)
        self.assertEqual(self.client.session['checkout_data']['shipping']['method_code'], Free().code)

    def test_multiple_shipping_methods_validation_and_paid_totals(self):
        self.add()
        self.address()
        paid = FixedPrice(charge_excl_tax=Decimal('5'), charge_incl_tax=Decimal('5'))
        paid.code, paid.name = 'express-test', 'Express delivery'
        with patch('oscar.apps.shipping.repository.Repository.methods', (Free(), paid)):
            response = self.client.get(self.url('shipping-method'))
            self.assertIsInstance(response.context['form'], get_class('checkout.forms', 'ShippingMethodForm'))
            self.assertContains(response, 'name="method_code" value="express-test"')
            response = self.post(self.url('shipping-method'), {'method_code': 'forged'})
            self.assertContains(response, 'alert-danger')
            self.assertTrue(response.context['form'].errors)
            self.post(self.url('shipping-method'), {'method_code': paid.code})
            response = self.client.get(self.url('preview'))
            self.assertEqual(response.context['shipping_charge'].incl_tax, Decimal('5'))
            self.assertEqual(response.context['order_total'].incl_tax, Decimal('130.50'))
            self.assertContains(response, str(currency(Decimal('130.50'), 'JOD')))

    def test_no_shipping_methods_returns_to_address(self):
        self.add()
        self.address()
        with patch('oscar.apps.shipping.repository.Repository.methods', ()):
            self.assertRedirects(self.client.get(self.url('shipping-method')), self.url('shipping-address'), fetch_redirect_response=False)

    def test_payment_placeholder_and_original_preview_form_hooks(self):
        self.ready()
        response = self.client.get(self.url('payment-details'))
        self.assertContains(response, 'No online payment is collected')
        self.assertContains(response, 'id="view_preview"')
        self.assertNotContains(response, 'This page needs implementing')
        self.assertNotContains(response, 'name="card_number"')
        self.assertEqual(self.post(self.url('payment-details')).status_code, 400)
        response = self.client.get(self.url('preview'))
        for text in ['id="place_order_form"', 'name="action" value="place_order"', 'csrfmiddlewaretoken',
                     "id='place-order'", '12 Example Street', 'Test delivery instructions', 'Edit bag']:
            self.assertContains(response, text)
        template = Template('{% extends "oscar/checkout/preview.html" %}{% block hiddenforms %}<input name="test_payment_hook" value="preserved">{% endblock %}')
        context = {key: response.context[key] for key in ['request', 'user', 'basket', 'shipping_address', 'shipping_method', 'shipping_charge', 'order_total']}
        html = template.render(Context(context))
        self.assertIn('name="test_payment_hook"', html)
        self.assertIn('id="place_order_form"', html)

    def test_real_order_submission_confirmation_stock_and_duplicate_prevention(self):
        basket = self.ready()
        response = self.post(self.url('preview'), {'action': 'place_order'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        order = Order.objects.get()
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.currency, 'JOD')
        self.assertEqual(order.total_incl_tax, Decimal('125.50'))
        self.assertEqual(order.lines.get().product, self.product)
        self.assertEqual(order.shipping_address.line1, '12 Example Street')
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.num_allocated, 1)
        basket.refresh_from_db()
        self.assertEqual(basket.status, Basket.SUBMITTED)
        self.assertEqual(self.client.session['checkout_order_id'], order.pk)
        self.assertTrue(mail.outbox)
        for text in [order.number, 'Thank you for your order', 'Order summary', self.stock.partner_sku,
                     'No payment transaction is recorded', str(currency(order.total_incl_tax, 'JOD'))]:
            self.assertContains(response, text)
        self.assertNotContains(response, 'id="place_order_form"')
        self.post(self.url('preview'), {'action': 'place_order'})
        self.assertEqual(Order.objects.count(), 1)

    def test_voucher_discount_survives_all_steps_and_is_recorded_on_order(self):
        self.add()
        offer_range = get_model('offer', 'Range').objects.create(name='Checkout watches', includes_all_products=True)
        condition = get_model('offer', 'Condition').objects.create(range=offer_range, type='Count', value=1)
        benefit = get_model('offer', 'Benefit').objects.create(range=offer_range, type='Percentage', value=10)
        offer = get_model('offer', 'ConditionalOffer').objects.create(name='Checkout offer', offer_type='Voucher', condition=condition, benefit=benefit)
        voucher = get_model('voucher', 'Voucher').objects.create(name='Checkout voucher', code='CHECKOUT10', usage='Multi-use',
            start_datetime=timezone.now()-timedelta(days=1), end_datetime=timezone.now()+timedelta(days=1))
        voucher.offers.add(offer)
        self.post(reverse('basket:vouchers-add'), {'code': voucher.code})
        self.address()
        self.client.get(self.url('shipping-method'), follow=True)
        for step in ['payment-details', 'preview']:
            response = self.client.get(self.url(step))
            self.assertContains(response, voucher.code)
            self.assertEqual(response.context['order_total'].incl_tax, Decimal('112.95'))
        response = self.post(self.url('preview'), {'action': 'place_order'}, follow=True)
        order = Order.objects.get()
        self.assertEqual(order.total_incl_tax, Decimal('112.95'))
        self.assertEqual(order.discounts.get().amount, Decimal('12.55'))
        self.assertContains(response, str(currency(Decimal('112.95'), 'JOD')))

    def test_payment_failure_keeps_hook_and_restores_basket(self):
        basket = self.ready()
        with patch.object(PaymentDetailsView, 'handle_payment', side_effect=UnableToTakePayment('Test payment was declined')) as hook:
            response = self.post(self.url('preview'), {'action': 'place_order'})
        hook.assert_called_once()
        self.assertContains(response, 'Test payment was declined')
        self.assertTemplateUsed(response, 'oscar/checkout/payment_details.html')
        basket.refresh_from_db()
        self.assertEqual(basket.status, Basket.OPEN)
        self.assertFalse(Order.objects.exists())

    def test_payment_redirect_hook_still_freezes_basket(self):
        basket = self.ready()
        with patch.object(PaymentDetailsView, 'handle_payment', side_effect=RedirectRequired('/test-payment-redirect/')):
            response = self.post(self.url('preview'), {'action': 'place_order'})
        self.assertRedirects(response, '/test-payment-redirect/', fetch_redirect_response=False)
        basket.refresh_from_db()
        self.assertEqual(basket.status, Basket.FROZEN)
        self.assertFalse(Order.objects.exists())

    def test_free_non_shipping_order_retains_skip_conditions(self):
        self.product_class.requires_shipping = False
        self.product_class.save()
        self.stock.price = Decimal('0')
        self.stock.save()
        self.add()
        response = self.client.get(self.url('shipping-address'), follow=True)
        self.assertTemplateUsed(response, 'oscar/checkout/preview.html')
        self.assertEqual(response.context['order_total'].incl_tax, Decimal('0'))
        self.assertIsNone(response.context['shipping_address'])

    def test_confirmation_access_and_checkout_style_isolation(self):
        self.assertRedirects(self.client.get(self.url('thank-you')), reverse('home'), fetch_redirect_response=False)
        for url in ['/', reverse('catalogue:index'), reverse('basket:summary'), self.product.get_absolute_url(), reverse('customer:login')]:
            self.assertNotContains(self.client.get(url, follow=True), 'abdeen/css/checkout.css')
