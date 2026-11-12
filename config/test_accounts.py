"""Phase 1: exercise native Oscar auth/checkout, including CSRF and ownership."""
from decimal import Decimal
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from oscar.core.loading import get_class, get_model

User = get_user_model()
Basket = get_model('basket', 'Basket')
Order = get_model('order', 'Order')
UserAddress = get_model('address', 'UserAddress')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CustomerAccountTests(TestCase):
    password = 'An-example-password-493!'

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('internal-user', email='customer@example.test', password=cls.password)
        cls.other = User.objects.create_user('other-user', email='other@example.test', password=cls.password)
        cls.country = get_model('address', 'Country').objects.create(
            iso_3166_1_a2='JO', iso_3166_1_a3='JOR', printable_name='Jordan', name='Jordan', is_shipping_country=True)
        product_class = get_model('catalogue', 'ProductClass').objects.create(name='Account test watches', track_stock=True)
        cls.product = get_model('catalogue', 'Product').objects.create(title='Account flow watch', product_class=product_class)
        partner = get_model('partner', 'Partner').objects.create(name='Account test supplier')
        cls.stock = get_model('partner', 'StockRecord').objects.create(product=cls.product, partner=partner,
            partner_sku='ACCOUNT-001', price_currency='JOD', price=Decimal('125.50'), num_in_stock=20)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get(reverse('customer:login'))

    def post(self, url, data=None, **kwargs):
        return self.client.post(url, {**(data or {}), 'csrfmiddlewaretoken': self.client.cookies['csrftoken'].value}, **kwargs)

    def add(self):
        self.client.get(self.product.get_absolute_url())
        response = self.post(reverse('basket:add', kwargs={'pk': self.product.pk}), {'quantity': 1})
        self.assertEqual(response.status_code, 302)
        return Basket.objects.filter(status=Basket.OPEN).latest('pk')

    def login(self, email=None, password=None, redirect_url=''):
        return self.post(reverse('customer:login'), {'login-username': email or self.user.email,
            'login-password': password or self.password, 'login-redirect_url': redirect_url, 'login_submit': '1'})

    def guest(self, email='guest@example.test'):
        self.checkout_email = email
        return self.client.get(reverse('checkout:index'))

    def submit_order(self):
        quote = self.client.get(reverse('checkout:index')).context['quote']
        return self.post(reverse('checkout:index'), {
            'email': getattr(self, 'checkout_email', 'guest@example.test'),
            'phone_number': '0791234567', 'first_name': 'Test', 'last_name': 'Customer',
            'line1': '12 Example Street', 'line4': 'Amman', 'country': 'JO',
            'method_code': 'jordan-delivery', 'action': 'place_order', 'quote': quote}, follow=True)

    def test_native_views_forms_and_security_configuration(self):
        for name, module, view in [('customer:login', 'customer.views', 'AccountAuthView'),
                ('customer:register', 'customer.views', 'AccountRegistrationView'),
                ('checkout:index', 'checkout.views', 'CODCheckoutView')]:
            self.assertIs(resolve(reverse(name)).func.view_class, get_class(module, view))
        self.assertTrue(settings.OSCAR_ALLOW_ANON_CHECKOUT)
        self.assertTrue(settings.OSCAR_ALLOW_GUEST_CHECKOUT_WITH_ACCOUNT)
        self.assertIn('django.middleware.csrf.CsrfViewMiddleware', settings.MIDDLEWARE)
        response = self.client.get(reverse('customer:login'))
        form = response.context['login_form']
        self.assertIsInstance(form, get_class('customer.forms', 'EmailAuthenticationForm'))
        self.assertEqual(form.fields['username'].widget.input_type, 'email')
        self.assertNotContains(response, 'id="register_form"')
        self.assertContains(response, 'Welcome back')

    def test_anonymous_browse_basket_and_cod_checkout(self):
        for url in [reverse('catalogue:index'), self.product.get_absolute_url()]:
            self.assertEqual(self.client.get(url).status_code, 200)
        basket = self.add()
        self.assertIsNone(basket.owner_id)
        response = self.client.get(reverse('checkout:index'))
        self.assertTemplateUsed(response, 'oscar/checkout/cod.html')
        self.assertContains(response, 'No account needed')
        self.assertContains(response, 'PLACE ORDER')

    def test_guest_order_uses_email_and_never_creates_user(self):
        basket = self.add()
        before = User.objects.count()
        response = self.guest()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.submit_order()
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        order = Order.objects.get()
        self.assertIsNone(order.user_id)
        self.assertEqual(order.guest_email, 'guest@example.test')
        self.assertEqual(order.total_incl_tax, Decimal('127.50'))
        self.assertEqual(User.objects.count(), before)
        self.assertFalse(UserAddress.objects.exists())
        basket.refresh_from_db()
        self.assertEqual(basket.status, Basket.SUBMITTED)
        self.assertEqual(order.basket_id, basket.pk)
        self.post(reverse('checkout:preview'), {'action': 'place_order'})
        self.assertEqual(Order.objects.count(), 1)

    def test_existing_email_can_checkout_as_guest_without_authentication(self):
        self.add()
        response = self.guest(self.user.email.upper())
        self.assertEqual(response.status_code, 200)
        self.submit_order()
        order = Order.objects.get()
        self.assertIsNone(order.user_id)
        self.assertEqual(order.guest_email.casefold(), self.user.email.casefold())
        self.assertNotIn('_auth_user_id', self.client.session)
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse('customer:order-list')), order.number)

    def test_guest_validation_and_native_preconditions(self):
        self.assertRedirects(self.client.get(reverse('checkout:index')), reverse('basket:summary'), fetch_redirect_response=False)
        self.add()
        self.guest('invalid')
        response = self.submit_order()
        self.assertContains(response, 'abdeen-field-errors')
        self.assertIn('email', response.context['form'].errors)
        self.assertFalse(Order.objects.exists())
        self.stock.num_in_stock = 0
        self.stock.save()
        self.assertRedirects(self.client.get(reverse('checkout:index')), reverse('basket:summary'), fetch_redirect_response=False)

    def test_email_login_preserves_basket_and_uses_oscar_backend(self):
        basket = self.add()
        response = self.login(email=self.user.email.upper())
        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertEqual(self.client.session['_auth_user_backend'], 'oscar.apps.customer.auth_backends.EmailBackend')
        self.client.get(reverse('basket:summary'))
        owned_basket = Basket.objects.get(owner=self.user, status=Basket.OPEN)
        self.assertEqual(owned_basket.num_items, 1)
        self.assertEqual(owned_basket.lines.get().product_id, self.product.pk)
        basket.refresh_from_db()
        self.assertIn(basket.status, [Basket.OPEN, Basket.MERGED])
        self.assertTemplateUsed(self.client.get(reverse('checkout:index')), 'oscar/checkout/cod.html')

    def test_login_preserves_basket_and_creates_account_order(self):
        self.add()
        response = self.login(redirect_url=reverse('checkout:index'))
        self.assertRedirects(response, reverse('checkout:index'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.submit_order()
        order = Order.objects.get()
        self.assertEqual(order.user_id, self.user.pk)
        self.assertContains(self.client.get(reverse('customer:order-list')), order.number)
        self.assertContains(self.client.get(reverse('customer:order', kwargs={'order_number': order.number})), self.product.title)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('customer:order-list')), order.number)
        self.assertEqual(self.client.get(reverse('customer:order', kwargs={'order_number': order.number})).status_code, 404)

    def test_invalid_login_is_styled_generic_and_rejects_username(self):
        for email in [self.user.email, 'unknown@example.test']:
            response = self.login(email=email, password='incorrect')
            self.assertContains(response, 'The email or password is incorrect.')
            self.assertContains(response, 'abdeen-message')
            self.assertNotContains(response, 'correct username')
            self.assertNotContains(response, 'value="incorrect"')
            self.assertNotIn('_auth_user_id', self.client.session)
        response = self.login(email=self.user.username)
        self.assertContains(response, 'abdeen-field-errors')
        self.user.is_active = False
        self.user.save()
        self.login()
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_checkout_sign_in_link_uses_native_login(self):
        self.add()
        response = self.client.get(reverse('checkout:index'))
        self.assertContains(response, reverse('customer:login') + '?next=' + reverse('checkout:index'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_header_account_navigation_and_hidden_features(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, f'href="{reverse("customer:login")}" class="abdeen-icon-button abdeen-account-link"')
        self.login()
        response = self.client.get(reverse('customer:summary'), follow=True)
        self.assertContains(response, f'href="{reverse("customer:summary")}" class="abdeen-icon-button abdeen-account-link"')
        for title in ['My orders', 'My addresses', 'Account details', 'Sign out']:
            self.assertContains(response, title)
        for name in ['customer:profile-view', 'customer:order-list', 'customer:address-list']:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-home-header')
            self.assertContains(response, 'abdeen-footer')
            for unwanted in ['Wish Lists', 'My wishlists', 'Email History', 'Product Alerts', 'Notifications']:
                self.assertNotContains(response, unwanted)
        response = self.post(reverse('customer:logout'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_registration_minimal_validated_and_basket_survives(self):
        self.add()
        response = self.client.get(reverse('customer:register') + '?next=/checkout/shipping-address/')
        form = response.context['form']
        self.assertEqual([field.name for field in form.visible_fields()], ['email', 'password1', 'password2'])
        self.assertIsInstance(form, get_class('customer.forms', 'EmailUserCreationForm'))
        response = self.post(reverse('customer:register'), {'email': 'new@example.test', 'password1': self.password,
            'password2': self.password, 'redirect_url': reverse('checkout:shipping-address')})
        self.assertRedirects(response, reverse('checkout:shipping-address'), fetch_redirect_response=False)
        user = User.objects.get(email='new@example.test')
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.client.get(reverse('basket:summary'))
        self.assertEqual(Basket.objects.get(owner=user, status=Basket.OPEN).num_items, 1)

    def test_registration_rejects_weak_mismatched_and_duplicate_credentials(self):
        for data in [dict(email='new@example.test', password1='123', password2='123'),
                     dict(email='new@example.test', password1=self.password, password2='different'),
                     dict(email=self.user.email.upper(), password1=self.password, password2=self.password)]:
            response = self.post(reverse('customer:register'), data)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'abdeen-field-errors')
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(User.objects.count(), 2)

    def test_external_redirects_are_rejected(self):
        response = self.login(redirect_url='https://attacker.example/')
        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)
        self.post(reverse('customer:logout'))
        self.client.get(reverse('customer:register'))
        response = self.post(reverse('customer:register'), {'email': 'safe@example.test', 'password1': self.password,
            'password2': self.password, 'redirect_url': '//attacker.example/'})
        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)

    def test_login_preserves_safe_checkout_redirect(self):
        self.add()
        response = self.login(redirect_url=reverse('checkout:shipping-address'))
        self.assertRedirects(response, reverse('checkout:shipping-address'), fetch_redirect_response=False)

    def test_csrf_required_for_auth_and_gateway(self):
        self.add()
        for name, data in [('customer:login', {'login_submit': '1'}), ('customer:register', {}),
                           ('password-reset', {'email': self.user.email}),
                           ('checkout:index', {'username': 'guest@example.test', 'options': 'anonymous'}),
                           ('customer:logout', {})]:
            self.assertEqual(self.client.post(reverse(name), data).status_code, 403)

    def test_password_reset_email_token_validation_and_new_password(self):
        response = self.client.get(reverse('password-reset'))
        self.assertIsInstance(response.context['form'], get_class('customer.forms', 'PasswordResetForm'))
        response = self.post(reverse('password-reset'), {'email': self.user.email})
        self.assertRedirects(response, reverse('password-reset-done'))
        self.assertEqual(len(mail.outbox), 1)
        reset_url = re.search(r'https?://[^\s]+/password-reset/confirm/[^\s]+', mail.outbox[0].body).group(0)
        path = urlsplit(reset_url).path
        response = self.client.get(path, follow=True)
        self.assertTrue(response.context['validlink'])
        confirm_path = response.request['PATH_INFO']
        self.assertEqual(self.client.post(confirm_path, {'new_password1': self.password}).status_code, 403)
        response = self.post(confirm_path, {'new_password1': 'weak', 'new_password2': 'weak'})
        self.assertContains(response, 'abdeen-field-errors')
        new_password = 'Another-example-password-827!'
        response = self.post(confirm_path, {'new_password1': new_password, 'new_password2': new_password})
        self.assertRedirects(response, reverse('password-reset-complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password(self.password))
        self.assertFalse(self.client.get(path, follow=True).context['validlink'])
        self.assertEqual(self.login(password=new_password).status_code, 302)

    def test_unknown_reset_email_same_confirmation_and_invalid_link(self):
        response = self.post(reverse('password-reset'), {'email': 'unknown@example.test'}, follow=True)
        self.assertContains(response, 'If an eligible account matches that email')
        self.assertEqual(len(mail.outbox), 0)
        response = self.post(reverse('password-reset'), {'email': 'invalid'})
        self.assertContains(response, 'abdeen-field-errors')
        response = self.client.get(reverse('password-reset-confirm', kwargs={'uidb64': 'invalid', 'token': 'invalid'}))
        self.assertContains(response, 'This link is no longer valid')

    def test_account_address_crud_and_ownership(self):
        self.login()
        data = {'first_name': 'Test', 'last_name': 'Customer', 'line1': '24 Account Street',
                'line4': 'Amman', 'postcode': '11118', 'country': 'JO'}
        response = self.post(reverse('customer:address-create'), data)
        self.assertRedirects(response, reverse('customer:address-list'), fetch_redirect_response=False)
        address = UserAddress.objects.get(user=self.user)
        self.assertContains(self.client.get(reverse('customer:address-list')), '24 Account Street')
        edit_url = reverse('customer:address-detail', kwargs={'pk': address.pk})
        self.post(edit_url, {**data, 'line1': '25 Account Street'}, follow=True)
        address.refresh_from_db()
        self.assertEqual(address.line1, '25 Account Street')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(edit_url).status_code, 404)
        self.assertNotContains(self.client.get(reverse('customer:address-list')), '25 Account Street')
        self.client.force_login(self.user)
        self.post(reverse('customer:address-delete', kwargs={'pk': address.pk}))
        self.assertFalse(UserAddress.objects.filter(pk=address.pk).exists())

    def test_protected_account_and_dashboard_routes(self):
        for name in ['customer:summary', 'customer:order-list', 'customer:address-list', 'customer:profile-view']:
            url = reverse(name)
            self.assertRedirects(self.client.get(url), reverse('customer:login') + '?next=' + url, fetch_redirect_response=False)
        self.login()
        self.assertEqual(self.client.get(reverse('dashboard:index')).status_code, 403)
