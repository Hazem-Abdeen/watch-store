"""Exercise the drawer with Oscar's real basket, forms, strategy and CSRF."""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import resolve, reverse
from oscar.core.loading import get_class, get_model


class CartDrawerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        product_class = get_model('catalogue', 'ProductClass').objects.create(name='Watches', track_stock=True)
        cls.product = get_model('catalogue', 'Product').objects.create(title='Drawer watch', product_class=product_class)
        partner = get_model('partner', 'Partner').objects.create(name='Supplier')
        cls.stock = get_model('partner', 'StockRecord').objects.create(
            product=cls.product, partner=partner, partner_sku='DRAWER-1',
            price=Decimal('125.50'), price_currency='JOD', num_in_stock=3,
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.drawer = reverse('cart-drawer')
        self.summary = reverse('basket:summary')
        self.add_url = reverse('basket:add', kwargs={'pk': self.product.pk})
        self.client.get(self.product.get_absolute_url())

    def post(self, url, data, **kwargs):
        return self.client.post(url, {**data, 'csrfmiddlewaretoken': self.client.cookies['csrftoken'].value}, **kwargs)

    def add(self, quantity=1, **options):
        return self.post(self.add_url, {'quantity': quantity, 'next': self.drawer, **options})

    def update(self, **fields):
        formset = self.client.get(self.drawer).context['formset']
        data = {field.html_name: field.value() for field in formset.management_form}
        for form in formset:
            data[form['id'].html_name] = form.instance.pk
            data[form['quantity'].html_name] = form.instance.quantity
        return self.post(self.summary, {**data, **fields}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_empty_drawer_is_private_read_only_fragment(self):
        response = self.client.get(self.drawer)
        self.assertContains(response, 'Your cart is empty')
        self.assertContains(response, 'data-count="0"')
        self.assertNotContains(response, 'abdeen-cart-checkout')
        self.assertNotContains(response, '<script')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(self.post(self.drawer, {}).status_code, 405)
        self.assertFalse(get_model('basket', 'Line').objects.exists())

    def test_real_add_redirects_to_drawer_and_keeps_oscar_views(self):
        response = self.add(2)
        self.assertRedirects(response, self.drawer)
        response = self.client.get(self.drawer)
        for text in ['Drawer watch', 'data-count="2"', '251 JOD', 'name="form-0-quantity"',
                     'data-cart-remove="form-0-DELETE"', 'name="csrfmiddlewaretoken"',
                     'abdeen/images/watch-placeholder.svg', reverse('checkout:index')]:
            self.assertContains(response, text)
        self.assertIs(resolve(self.add_url).func.view_class, get_class('basket.views', 'BasketAddView'))
        self.assertIs(resolve(self.summary).func.view_class, get_class('basket.views', 'BasketView'))
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.num_in_stock, 3)

    def test_updates_errors_removal_and_session_isolation(self):
        self.add()
        self.update(**{'form-0-quantity': 2})
        self.assertContains(self.client.get(self.drawer), 'data-count="2"')
        rejected = self.update(**{'form-0-quantity': 4})
        self.assertIn('error-block', rejected.json()['content_html'])
        self.assertContains(self.client.get(self.drawer), 'data-count="2"')
        self.assertContains(Client().get(self.drawer), 'Your cart is empty')
        self.update(**{'form-0-DELETE': 'on'})
        self.assertContains(self.client.get(self.drawer), 'Your cart is empty')

    def test_failed_add_and_csrf_do_not_mutate_cart(self):
        self.assertEqual(self.client.post(self.add_url, {'quantity': 1, 'next': self.drawer}).status_code, 403)
        response = self.post(self.add_url, {'quantity': 4, 'next': self.drawer},
                             HTTP_REFERER='http://testserver' + self.product.get_absolute_url())
        self.assertRedirects(response, 'http://testserver' + self.product.get_absolute_url())
        self.assertFalse(get_model('basket', 'Line').objects.exists())

    def test_real_option_and_discount_are_rendered(self):
        Option = get_model('catalogue', 'Option')
        option = Option.objects.create(name='Engraving', code='engraving', type=Option.TEXT, required=True)
        self.product.product_options.add(option)
        self.add(engraving='For you')
        self.assertContains(self.client.get(self.drawer), 'Engraving: For you')
        Condition = get_model('offer', 'Condition')
        Benefit = get_model('offer', 'Benefit')
        offer_range = get_model('offer', 'Range').objects.create(name='All watches', includes_all_products=True)
        condition = Condition.objects.create(range=offer_range, type=Condition.COUNT, value=1)
        benefit = Benefit.objects.create(range=offer_range, type=Benefit.PERCENTAGE, value=10)
        get_model('offer', 'ConditionalOffer').objects.create(name='Ten percent', condition=condition, benefit=benefit)
        response = self.client.get(self.drawer)
        self.assertContains(response, '112.95 JOD')
        self.assertContains(response, '<s>125.5 JOD</s>', html=True)
        self.assertContains(response, 'Ten percent')
