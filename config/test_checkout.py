"""Real Oscar COD orders, validation, discounts, ownership and replay protection."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from oscar.core.loading import get_class, get_model
from .image_test_fixtures import ImageFixtureMedia, add_real_image

Basket = get_model('basket', 'Basket')
Order = get_model('order', 'Order')
Country = get_model('address', 'Country')
UserAddress = get_model('address', 'UserAddress')
Delivery = get_class('shipping.methods', 'Delivery')
FixedPrice = get_class('shipping.methods', 'FixedPrice')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CODCheckoutTests(ImageFixtureMedia, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('cod-customer', email='customer@example.test', password='Example-password-493!')
        cls.country = Country.objects.create(iso_3166_1_a2='JO', iso_3166_1_a3='JOR',
            printable_name='Jordan', name='Jordan', is_shipping_country=True)
        Country.objects.create(iso_3166_1_a2='GB', iso_3166_1_a3='GBR', printable_name='United Kingdom', name='United Kingdom', is_shipping_country=True)
        cls.product_class = get_model('catalogue', 'ProductClass').objects.create(name='Watches', track_stock=True)
        cls.product = get_model('catalogue', 'Product').objects.create(title='COD test watch', product_class=cls.product_class)
        add_real_image(cls.product)
        partner = get_model('partner', 'Partner').objects.create(name='COD supplier')
        cls.stock = get_model('partner', 'StockRecord').objects.create(product=cls.product, partner=partner,
            partner_sku='COD-001', price_currency='JOD', price=Decimal('125.50'), num_in_stock=10)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get(self.product.get_absolute_url())

    def post(self, url, data=None, **kwargs):
        return self.client.post(url, {**(data or {}), 'csrfmiddlewaretoken': self.client.cookies['csrftoken'].value}, **kwargs)

    def add(self, quantity=1):
        self.assertEqual(self.post(reverse('basket:add', kwargs={'pk': self.product.pk}), {'quantity': quantity}).status_code, 302)
        return Basket.objects.filter(status=Basket.OPEN).latest('pk')

    def data(self):
        return {'email': 'guest@example.test', 'phone_number': '0791234567', 'country': 'JO',
                'first_name': 'Test', 'last_name': 'Customer', 'line1': '12 Example Street',
                'line2': '', 'line4': 'Amman', 'postcode': '', 'notes': 'Call on arrival',
                'method_code': Delivery().code, 'action': 'place_order'}

    def checkout(self, data=None, quote=None, **kwargs):
        if quote is None:
            quote = self.client.get(reverse('checkout:index')).context['quote']
        return self.post(reverse('checkout:index'), {**self.data(), **(data or {}), 'quote': quote}, **kwargs)

    def assert_order(self, response, basket):
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        order = Order.objects.get()
        self.assertContains(response, order.number)
        self.assertContains(response, 'Cash on Delivery (COD)')
        self.assertContains(response, 'Payment due on delivery')
        self.assertEqual(order.total_incl_tax, Decimal('127.50'))
        self.assertEqual(order.shipping_incl_tax, Decimal('2.00'))
        self.assertEqual(order.shipping_excl_tax, Decimal('2.00'))
        self.assertEqual(order.shipping_code, Delivery().code)
        self.assertEqual(order.shipping_method, 'Delivery')
        self.assertContains(response, 'Delivery · 2.00 JOD')
        self.assertContains(response, 'Payment due on delivery: 127.5 JOD')
        self.assertEqual(str(order.shipping_address.phone_number), '+962791234567')
        self.assertEqual(order.shipping_address.notes, 'Call on arrival')
        self.assertIsNone(order.billing_address_id)
        self.assertEqual(order.lines.get().product_id, self.product.pk)
        source = order.sources.get()
        self.assertEqual(source.source_type.name, 'Cash on Delivery (COD)')
        self.assertEqual(source.amount_allocated, order.total_incl_tax)
        self.assertEqual(source.amount_debited, 0)
        self.assertEqual(source.balance, order.total_incl_tax)
        self.assertFalse(source.transactions.exists())
        self.assertFalse(order.payment_events.exists())
        basket.refresh_from_db()
        self.assertEqual(basket.status, Basket.SUBMITTED)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.num_allocated, 1)
        return order

    def test_guest_product_basket_checkout_confirmation(self):
        before = get_user_model().objects.count()
        basket = self.add()
        self.assertContains(self.client.get(reverse('basket:summary')), self.product.title)
        response = self.client.get(reverse('checkout:index'))
        for text in ['Contact', 'Delivery', 'Shipping method', 'Cash on Delivery (COD)', 'PLACE ORDER',
                     '1–2 business days', 'Subtotal', self.product.title, '2.00 JOD']:
            self.assertContains(response, text)
        for text in ['Billing address', 'Pay now', 'card_number', 'Continue as guest']:
            self.assertNotContains(response, text)
        self.assertEqual(response.context['form']['country'].value(), 'JO')
        self.assertFalse(response.context['form'].fields['email'].disabled)
        self.assertTrue(response.context['form'].fields['email'].required)
        self.assertNotContains(response, 'type="radio"')
        self.assertNotContains(response, 'Update delivery &amp; total')
        order = self.assert_order(self.checkout(follow=True), basket)
        self.assertIsNone(order.user_id)
        self.assertEqual(order.guest_email, 'guest@example.test')
        self.assertEqual(get_user_model().objects.count(), before)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session['checkout_order_id'], order.pk)

    def test_login_product_saved_address_checkout_history(self):
        response = self.post(reverse('customer:login'), {'login-username': self.user.email,
            'login-password': 'Example-password-493!', 'login_submit': '1'})
        self.assertEqual(response.status_code, 302)
        address = UserAddress.objects.create(user=self.user, first_name='Saved', last_name='Customer',
            line1='24 Saved Street', line4='Amman', country=self.country, phone_number='+962791234567', is_default_for_shipping=True)
        basket = self.add()
        response = self.client.get(reverse('checkout:index'), {'address_id': address.pk})
        self.assertEqual(response.context['form']['line1'].value(), '24 Saved Street')
        self.assertEqual(response.context['form']['phone_number'].value(), address.phone_number)
        self.assertFalse(response.context['form'].fields['email'].disabled)
        self.assertContains(response, 'Your account email will not change.')
        order = self.assert_order(self.checkout({'first_name': 'Saved', 'line1': '24 Saved Street'}, follow=True), basket)
        self.assertEqual(order.user_id, self.user.pk)
        self.assertEqual(order.email, self.user.email)
        self.assertEqual(order.guest_email, 'guest@example.test')
        history = self.client.get(reverse('customer:order-list'))
        self.assertContains(history, order.number)
        self.assertContains(history, '127.5 JOD')
        detail = self.client.get(reverse('customer:order', kwargs={'order_number': order.number}))
        self.assertContains(detail, self.product.title)
        self.assertContains(detail, 'Shipping total')
        self.assertContains(detail, '2 JOD')
        self.assertContains(detail, '127.5 JOD')
        self.assertEqual(UserAddress.objects.filter(user=self.user).count(), 1)
        address.refresh_from_db()
        self.assertEqual(address.num_orders_as_shipping_address, 1)

    def test_guest_can_use_existing_account_email(self):
        self.add()
        self.checkout({'email': self.user.email.upper()}, follow=True)
        order = Order.objects.get()
        self.assertIsNone(order.user_id)
        self.assertEqual(order.guest_email.casefold(), self.user.email.casefold())

    def test_guest_can_edit_email_after_validation_failure(self):
        self.add()
        response = self.checkout({'email': 'first@example.test', 'line1': ''})
        self.assertFalse(response.context['form'].fields['email'].disabled)
        self.assertEqual(response.context['form']['email'].value(), 'first@example.test')
        self.assertFalse(Order.objects.exists())
        self.checkout({'email': 'edited@example.test'}, quote=response.context['quote'], follow=True)
        self.assertEqual(Order.objects.get().guest_email, 'edited@example.test')

    def test_account_without_email_can_enter_order_contact(self):
        self.user.email = ''
        self.user.save(update_fields=['email'])
        self.client.force_login(self.user)
        self.add()
        response = self.client.get(reverse('checkout:index'))
        self.assertFalse(response.context['form'].fields['email'].disabled)
        invalid = self.checkout({'email': ''})
        self.assertIn('email', invalid.context['form'].errors)
        response = self.checkout({'email': 'order-contact@example.test'}, follow=True)
        order = Order.objects.get()
        self.assertEqual(order.user_id, self.user.pk)
        self.assertEqual(order.guest_email, 'order-contact@example.test')
        self.assertContains(response, 'order-contact@example.test')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')

    def test_required_email_phone_and_address_validation(self):
        self.add()
        for field, invalid in [('email', ''), ('email', 'bad'), ('phone_number', ''),
                ('phone_number', '+123'), ('first_name', ''), ('last_name', ''),
                ('line1', ''), ('line4', ''), ('country', 'XX')]:
            with self.subTest(field=field, invalid=invalid):
                response = self.checkout({field: invalid})
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
                self.assertContains(response, 'error-block')
                self.assertFalse(Order.objects.exists())

    def test_only_jordan_is_available_even_when_other_country_is_enabled(self):
        self.add()
        page = self.client.get(reverse('checkout:index'))
        self.assertEqual(list(page.context['form'].fields['country'].queryset.values_list('pk', flat=True)), ['JO'])
        response = self.checkout({'country': 'GB', 'phone_number': '+447911123456'})
        self.assertIn('country', response.context['form'].errors)
        self.assertFalse(response.context['shipping_options'])
        self.assertFalse(Order.objects.exists())

    def test_optional_postcode_for_jordan(self):
        self.add()
        response = self.checkout(follow=True)
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        self.assertEqual(Order.objects.get().shipping_address.postcode, '')

    def test_shipping_selection_and_changed_total_requires_review(self):
        self.add()
        paid = FixedPrice(charge_excl_tax=Decimal('5'), charge_incl_tax=Decimal('5'))
        paid.code, paid.name = 'express-test', 'Express delivery'
        with patch('config.shipping.repository.Repository.methods', (Delivery(), paid)):
            quote = self.client.get(reverse('checkout:index')).context['quote']
            invalid = self.checkout({'method_code': 'forged'}, quote=quote)
            self.assertIn('method_code', invalid.context['form'].errors)
            response = self.checkout({'method_code': paid.code}, quote=quote)
            self.assertFalse(Order.objects.exists())
            self.assertContains(response, 'Please review the total')
            self.assertEqual(response.context['order_total'].incl_tax, Decimal('130.50'))
            response = self.checkout({'method_code': paid.code}, quote=response.context['quote'], follow=True)
            self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
            order = Order.objects.get()
            self.assertEqual(order.shipping_incl_tax, Decimal('5'))
            self.assertEqual(order.total_incl_tax, Decimal('130.50'))

    def test_no_shipping_method_prevents_order(self):
        self.add()
        with patch('config.shipping.repository.Repository.methods', ()):
            response = self.client.get(reverse('checkout:index'))
            self.assertContains(response, 'Delivery is currently unavailable')
            response = self.checkout()
            self.assertIn('method_code', response.context['form'].errors)
            self.assertFalse(Order.objects.exists())

    def test_update_delivery_does_not_place_order(self):
        self.add()
        response = self.checkout({'action': 'update'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.client.session['checkout_data']['shipping']['new_address_fields']['line1'], '12 Example Street')

    def test_empty_and_out_of_stock_basket_protection_on_every_entry(self):
        for name in ['index', 'shipping-address', 'shipping-method', 'payment-method', 'payment-details', 'preview']:
            self.assertRedirects(self.client.get(reverse('checkout:'+name)), reverse('basket:summary'), fetch_redirect_response=False)
        self.add()
        quote = self.client.get(reverse('checkout:index')).context['quote']
        self.stock.num_in_stock = 0
        self.stock.save()
        self.assertRedirects(self.checkout(quote=quote), reverse('basket:summary'), fetch_redirect_response=False)
        self.assertFalse(Order.objects.exists())

    def test_csrf_and_unrecognized_submission(self):
        self.add()
        self.assertEqual(self.client.post(reverse('checkout:index'), self.data()).status_code, 403)
        self.assertEqual(self.post(reverse('checkout:index'), {'action': 'pay'}).status_code, 400)

    def test_duplicate_submit_and_replay_after_new_basket(self):
        self.add()
        quote = self.client.get(reverse('checkout:index')).context['quote']
        self.checkout(quote=quote, follow=True)
        self.checkout(quote=quote)
        self.assertEqual(Order.objects.count(), 1)
        self.add()
        response = self.checkout(quote=quote)
        self.assertContains(response, 'Please review the total')
        self.assertEqual(Order.objects.count(), 1)

    def test_stale_request_cannot_claim_already_submitted_basket(self):
        basket = self.add()
        quote = self.client.get(reverse('checkout:index')).context['quote']
        # Simulate another request claiming it after middleware loaded an OPEN basket.
        from config.checkout.views import CODCheckoutView
        original = CODCheckoutView.build_submission
        def claim(view, **kwargs):
            result = original(view, **kwargs)
            Basket.objects.filter(pk=basket.pk).update(status=Basket.SUBMITTED)
            return result
        with patch.object(CODCheckoutView, 'build_submission', claim):
            self.checkout(quote=quote)
        self.assertFalse(Order.objects.exists())

    def test_modified_quote_and_changed_basket_require_review(self):
        self.add()
        quote = self.client.get(reverse('checkout:index')).context['quote']
        self.assertContains(self.checkout(quote=quote+'tampered'), 'Please review the total')
        self.add()
        self.assertContains(self.checkout(quote=quote), 'Please review the total')
        self.assertFalse(Order.objects.exists())

    def test_changed_catalogue_price_requires_review(self):
        self.add()
        quote = self.client.get(reverse('checkout:index')).context['quote']
        self.stock.price = Decimal('140')
        self.stock.save()
        response = self.checkout(quote=quote)
        self.assertContains(response, 'Please review the total')
        self.assertEqual(response.context['order_total'].incl_tax, Decimal('142'))
        self.assertFalse(Order.objects.exists())

    def test_placement_failure_restores_basket_for_retry(self):
        from config.checkout.views import CODCheckoutView
        from oscar.apps.order.exceptions import UnableToPlaceOrder
        basket = self.add()
        with patch.object(CODCheckoutView, 'handle_order_placement', side_effect=UnableToPlaceOrder('Please try again.')):
            response = self.checkout()
        self.assertContains(response, 'Please try again.')
        basket.refresh_from_db()
        self.assertEqual(basket.status, Basket.OPEN)
        self.assertFalse(Order.objects.exists())
        self.assert_order(self.checkout(follow=True), basket)

    def test_saved_address_ownership_and_missing_phone(self):
        foreign = UserAddress.objects.create(user=self.user, country=self.country, first_name='Saved', last_name='Customer', line1='Street', line4='Amman')
        other = get_user_model().objects.create_user('other', email='other@example.test')
        self.client.force_login(other)
        self.add()
        self.assertEqual(self.client.get(reverse('checkout:index'), {'address_id': foreign.pk}).status_code, 404)
        self.assertEqual(self.client.get(reverse('checkout:index'), {'address_id': 'invalid'}).status_code, 404)
        self.client.force_login(self.user)
        self.add()
        response = self.client.get(reverse('checkout:index'), {'address_id': foreign.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('phone_number', self.checkout({'phone_number': ''}).context['form'].errors)

    def test_voucher_totals_and_order_discount(self):
        self.add()
        offer_range = get_model('offer', 'Range').objects.create(name='COD watches', includes_all_products=True)
        condition = get_model('offer', 'Condition').objects.create(range=offer_range, type='Count', value=1)
        benefit = get_model('offer', 'Benefit').objects.create(range=offer_range, type='Percentage', value=10)
        offer = get_model('offer', 'ConditionalOffer').objects.create(name='COD offer', offer_type='Voucher', condition=condition, benefit=benefit)
        voucher = get_model('voucher', 'Voucher').objects.create(name='COD voucher', code='COD10', usage='Multi-use',
            start_datetime=timezone.now()-timedelta(days=1), end_datetime=timezone.now()+timedelta(days=1))
        voucher.offers.add(offer)
        self.post(reverse('basket:vouchers-add'), {'code': voucher.code})
        response = self.client.get(reverse('checkout:index'))
        self.assertContains(response, 'COD10')
        self.assertEqual(response.context['order_total'].incl_tax, Decimal('114.95'))
        self.checkout(quote=response.context['quote'], follow=True)
        order = Order.objects.get()
        self.assertEqual(order.total_incl_tax, Decimal('114.95'))
        self.assertEqual(order.shipping_incl_tax, Decimal('2.00'))
        self.assertEqual(order.discounts.get().amount, Decimal('12.55'))
        self.assertEqual(order.sources.get().balance, order.total_incl_tax)

    def test_confirmation_access_and_checkout_css_isolation(self):
        self.assertRedirects(self.client.get(reverse('checkout:thank-you')), reverse('home'), fetch_redirect_response=False)
        for url in ['/', reverse('catalogue:index'), reverse('basket:summary'), self.product.get_absolute_url(), reverse('customer:login')]:
            self.assertNotContains(self.client.get(url, follow=True), 'abdeen/css/checkout.css')

    def test_189_jod_product_stores_191_jod_order_and_cod_after_refresh(self):
        self.stock.price = Decimal('189.00')
        self.stock.save()
        basket = self.add()
        page = self.client.get(reverse('checkout:index'))
        self.assertEqual(page.context['basket'].total_incl_tax, Decimal('189.00'))
        self.assertEqual(page.context['shipping_charge'].incl_tax, Decimal('2.00'))
        self.assertEqual(page.context['order_total'].incl_tax, Decimal('191.00'))
        self.assertContains(page, '2.00 JOD')
        self.assertContains(page, '191 JOD')
        quote = page.context['quote']
        self.checkout(quote=quote, follow=True)
        for _ in range(2):
            confirmation = self.client.get(reverse('checkout:thank-you'))
            self.assertContains(confirmation, 'Delivery · 2.00 JOD')
            self.assertContains(confirmation, 'Payment due on delivery: 191 JOD')
        self.checkout(quote=quote)
        order = Order.objects.get(basket=basket)
        self.assertEqual(order.total_incl_tax, Decimal('191.00'))
        self.assertEqual(order.shipping_incl_tax, Decimal('2.00'))
        self.assertEqual(order.shipping_excl_tax, Decimal('2.00'))
        self.assertEqual(order.sources.get().balance, Decimal('191.00'))
        self.assertEqual(order.sources.get().amount_allocated, Decimal('191.00'))
        self.assertEqual(Order.objects.count(), 1)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.num_allocated, 1)

    def test_quantity_greater_than_one_charges_delivery_once(self):
        self.add(quantity=3)
        page = self.client.get(reverse('checkout:index'))
        self.assertEqual(page.context['order_total'].incl_tax, Decimal('378.50'))
        self.checkout(quote=page.context['quote'], follow=True)
        order = Order.objects.get()
        self.assertEqual(order.lines.get().quantity, 3)
        self.assertEqual(order.shipping_incl_tax, Decimal('2.00'))
        self.assertEqual(order.total_incl_tax, Decimal('378.50'))
        self.assertEqual(order.sources.get().balance, Decimal('378.50'))
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.num_allocated, 3)

    def test_multiple_products_charge_delivery_once(self):
        self.add()
        product = get_model('catalogue', 'Product').objects.create(title='Second watch', product_class=self.product_class)
        stock = get_model('partner', 'StockRecord').objects.create(product=product, partner=self.stock.partner,
            partner_sku='COD-002', price_currency='JOD', price=Decimal('189.00'), num_in_stock=10)
        self.post(reverse('basket:add', kwargs={'pk': product.pk}), {'quantity': 2})
        self.checkout(follow=True)
        order = Order.objects.get()
        self.assertEqual(order.lines.count(), 2)
        self.assertEqual(order.basket_total_incl_tax, Decimal('503.50'))
        self.assertEqual(order.shipping_incl_tax, Decimal('2.00'))
        self.assertEqual(order.total_incl_tax, Decimal('505.50'))
        self.assertEqual(order.sources.get().balance, Decimal('505.50'))
        stock.refresh_from_db()
        self.stock.refresh_from_db()
        self.assertEqual(stock.num_allocated, 2)
        self.assertEqual(self.stock.num_allocated, 1)

    def test_stale_free_shipping_quote_requires_review_at_new_rate(self):
        self.add()
        free = get_class('shipping.methods', 'Free')()
        with patch('config.shipping.repository.Repository.methods', (free,)):
            quote = self.client.get(reverse('checkout:index')).context['quote']
        response = self.checkout(quote=quote)
        self.assertContains(response, 'Please review the total')
        self.assertEqual(response.context['order_total'].incl_tax, Decimal('127.50'))
        self.assertFalse(Order.objects.exists())
        forged = self.checkout({'method_code': free.code})
        self.assertIn('method_code', forged.context['form'].errors)
        self.assertFalse(Order.objects.exists())

    def test_foreign_saved_address_is_not_offered_or_accepted(self):
        self.client.force_login(self.user)
        address = UserAddress.objects.create(user=self.user, country_id='GB', first_name='Foreign',
            last_name='Customer', line1='Foreign street', line4='London', is_default_for_shipping=True)
        self.add()
        page = self.client.get(reverse('checkout:index'))
        self.assertEqual(page.context['form']['country'].value(), 'JO')
        self.assertNotContains(page, 'Foreign street')
        self.assertEqual(self.client.get(reverse('checkout:index'), {'address_id': address.pk}).status_code, 404)

    def test_shipping_voucher_cannot_reduce_flat_delivery_fee(self):
        self.add()
        offer_range = get_model('offer', 'Range').objects.create(name='Delivery watches', includes_all_products=True)
        condition = get_model('offer', 'Condition').objects.create(range=offer_range, type='Count', value=1)
        Benefit = get_model('offer', 'Benefit')
        benefit = Benefit.objects.create(range=offer_range, type=Benefit.SHIPPING_PERCENTAGE, value=100)
        offer = get_model('offer', 'ConditionalOffer').objects.create(name='Legacy free delivery',
            offer_type='Voucher', condition=condition, benefit=benefit)
        voucher = get_model('voucher', 'Voucher').objects.create(name='Legacy delivery voucher', code='FREESHIP',
            usage='Multi-use', start_datetime=timezone.now()-timedelta(days=1), end_datetime=timezone.now()+timedelta(days=1))
        voucher.offers.add(offer)
        self.post(reverse('basket:vouchers-add'), {'code': voucher.code})
        self.checkout(follow=True)
        order = Order.objects.get()
        self.assertEqual(order.shipping_incl_tax, Decimal('2.00'))
        self.assertEqual(order.total_incl_tax, Decimal('127.50'))
        self.assertEqual(order.sources.get().balance, Decimal('127.50'))
        self.assertFalse(order.shipping_discounts)
