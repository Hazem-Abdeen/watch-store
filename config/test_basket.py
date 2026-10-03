"""Basket presentation regression tests through Oscar's real views and forms."""
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from oscar.core.loading import get_class, get_model
from oscar.templatetags.currency_filters import currency
from PIL import Image

Product = get_model('catalogue', 'Product')
ProductClass = get_model('catalogue', 'ProductClass')
StockRecord = get_model('partner', 'StockRecord')
Line = get_model('basket', 'Line')
Basket = get_model('basket', 'Basket')


class BasketPresentationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        media_root = cls.enterClassContext(TemporaryDirectory(prefix='abdeen-basket-test-media-'))
        cls.enterClassContext(override_settings(MEDIA_ROOT=media_root))
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        cls.product_class = ProductClass.objects.create(name='Watches', track_stock=True)
        cls.product = Product.objects.create(title='A real watch with a complete model reference',
                                            product_class=cls.product_class)
        cls.partner = get_model('partner', 'Partner').objects.create(name='Basket supplier')
        cls.stock = StockRecord.objects.create(product=cls.product, partner=cls.partner,
            partner_sku='WATCH-JOD-001', price_currency='JOD', price=Decimal('125.50'), num_in_stock=5)
        cls.user = get_user_model().objects.create_user('basket-customer', email='basket@example.test')

    def setUp(self):
        data = BytesIO()
        Image.new('RGB', (40, 50), 'white').save(data, format='JPEG')
        self.image = get_model('catalogue', 'ProductImage').objects.create(product=self.product,
            original=SimpleUploadedFile('basket-watch.jpg', data.getvalue(), content_type='image/jpeg'))
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse('basket:summary')
        self.client.get(self.url)

    def post(self, url, data, **kwargs):
        return self.client.post(url, {**data, 'csrfmiddlewaretoken': self.client.cookies['csrftoken'].value}, **kwargs)

    def add(self, product=None, quantity=1, **options):
        self.client.get((product or self.product).get_absolute_url())
        response = self.post(reverse('basket:add', kwargs={'pk': (product or self.product).pk}),
                             {'quantity': quantity, **options})
        self.assertEqual(response.status_code, 302)
        return Line.objects.get(basket__status=Basket.OPEN, product=product or self.product)

    def update(self, quantity, ajax=True, **fields):
        response = self.client.get(self.url)
        formset = response.context['formset']
        data = {field.html_name: field.value() for field in formset.management_form}
        for form in formset:
            data.update({form['id'].html_name: form.instance.pk,
                         form['quantity'].html_name: quantity})
        data.update(fields)
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'} if ajax else {}
        return self.post(self.url, data, **headers)

    def test_empty_state_shared_chrome_and_unchanged_view(self):
        response = self.client.get(self.url)
        for text in ['Your bag is empty', 'Explore watches', 'data-home-header', 'abdeen-footer',
                     'abdeen/css/basket.css', 'oscar.basket.init(options)', 'data-basket-count="0"']:
            self.assertContains(response, text)
        self.assertNotContains(response, 'id="basket_formset"')
        self.assertNotContains(response, 'href="' + reverse('checkout:index') + '"')
        self.assertIs(resolve(self.url).func.view_class, get_class('basket.views', 'BasketView'))

    def test_real_lines_images_prices_totals_and_form_contract(self):
        line = self.add(quantity=2)
        response = self.client.get(self.url)
        for text in [self.product.title, self.image.original.url, self.stock.partner_sku,
                     str(currency(Decimal('125.50'), 'JOD')), str(currency(Decimal('251.00'), 'JOD')),
                     'Subtotal', 'Order total', 'Shipping', 'id="basket_formset"',
                     'name="form-TOTAL_FORMS"', 'name="form-0-quantity"', 'name="form-0-DELETE"',
                     'data-behaviours="remove"', 'href="' + reverse('checkout:index') + '"',
                     'action="' + reverse('basket:vouchers-add') + '"']:
            self.assertContains(response, text)
        self.assertEqual(response.context['basket'].total_excl_tax, Decimal('251.00'))
        self.assertEqual(response.context['order_total'].excl_tax, Decimal('251.00'))
        self.assertEqual(line.stockrecord, self.stock)

    def test_quantity_updates_database_totals_and_ajax_partial(self):
        line = self.add()
        response = self.update(3)
        self.assertEqual(response.status_code, 200)
        line.refresh_from_db()
        self.assertEqual(line.quantity, 3)
        self.assertEqual(line.price_currency, 'JOD')
        html = response.json()['content_html']
        for text in ['abdeen-basket-items', 'data-basket-count="3"', str(currency(Decimal('376.50'), 'JOD'))]:
            self.assertIn(text, html)
        self.assertNotIn('<header class="abdeen-chrome', html)

    def test_plain_post_update_and_delete_work_without_javascript(self):
        line = self.add()
        self.assertEqual(self.update(2, ajax=False).status_code, 302)
        line.refresh_from_db()
        self.assertEqual(line.quantity, 2)
        self.assertEqual(self.update(2, ajax=False, **{'form-0-DELETE': 'on'}).status_code, 302)
        self.assertFalse(Line.objects.filter(pk=line.pk).exists())

    def test_removal_and_zero_quantity_return_real_empty_basket(self):
        for fields in [{'form-0-DELETE': 'on'}, {}]:
            line = self.add()
            response = self.update(1 if fields else 0, **fields)
            self.assertFalse(Line.objects.filter(pk=line.pk).exists())
            self.assertIn('Your bag is empty', response.json()['content_html'])
            self.assertIn('data-basket-count="0"', response.json()['content_html'])

    def test_invalid_quantity_stock_and_missing_management_form(self):
        line = self.add()
        for quantity in [99, -1, 'not-a-number']:
            response = self.update(quantity)
            self.assertNotIn('a maximum of', str(response.content))
            self.assertNotIn('available)', str(response.content))
            self.assertIn('error-block', response.json()['content_html'])
            line.refresh_from_db()
            self.assertEqual(line.quantity, 1)
        response = self.post(self.url, {'form-0-quantity': 2}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertIn('ManagementForm', response.json()['content_html'])
        line.refresh_from_db()
        self.assertEqual(line.quantity, 1)

    def test_csrf_is_still_required(self):
        self.add()
        response = self.client.post(self.url, {'form-0-quantity': 2})
        self.assertEqual(response.status_code, 403)

    def test_unavailable_item_warning_and_deletion(self):
        line = self.add()
        self.stock.num_in_stock = 0
        self.stock.save()
        response = self.client.get(self.url)
        self.assertContains(response, 'Out of stock')
        self.update(1, **{'form-0-DELETE': 'on'})
        self.assertFalse(Line.objects.filter(pk=line.pk).exists())

    def test_child_attributes_options_and_inherited_image(self):
        self.product.structure = Product.PARENT
        self.product.save()
        child = Product.objects.create(title='Silver variant', structure=Product.CHILD, parent=self.product)
        StockRecord.objects.create(product=child, partner=self.partner, partner_sku='SILVER-002',
                                   price_currency='JOD', price=Decimal('99'), num_in_stock=3)
        attribute = get_model('catalogue', 'ProductAttribute').objects.create(
            product_class=self.product_class, code='dial_colour', name='Dial colour', type='text')
        get_model('catalogue', 'ProductAttributeValue').objects.create(
            product=child, attribute=attribute, value_text='Silver')
        option = get_model('catalogue', 'Option').objects.create(name='Engraving', code='engraving', type='text')
        child.product_options.add(option)
        line = self.add(child, engraving='For Amman')
        response = self.client.get(self.url)
        for text in ['Silver variant', 'SILVER-002', 'Dial colour', 'Silver', 'Engraving', 'For Amman', self.image.original.url]:
            self.assertContains(response, text)
        self.update(2)
        self.assertEqual(line.attributes.get(option=option).value, 'For Amman')

    def test_missing_image_uses_existing_placeholder(self):
        self.product.images.all().delete()
        self.add()
        self.assertContains(self.client.get(self.url), '/static/abdeen/images/watch-placeholder.svg')

    def test_voucher_discount_invalid_code_and_removal(self):
        self.add(quantity=2)
        offer_range = get_model('offer', 'Range').objects.create(name='All watches', includes_all_products=True)
        condition = get_model('offer', 'Condition').objects.create(range=offer_range, type='Count', value=1)
        benefit = get_model('offer', 'Benefit').objects.create(range=offer_range, type='Percentage', value=10)
        offer = get_model('offer', 'ConditionalOffer').objects.create(name='Ten percent', offer_type='Voucher',
                                                                    condition=condition, benefit=benefit)
        voucher = get_model('voucher', 'Voucher').objects.create(name='Basket test code', code='WATCH10',
            usage='Multi-use', start_datetime=timezone.now() - timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=1))
        voucher.offers.add(offer)
        response = self.post(reverse('basket:vouchers-add'), {'code': 'watch10'}, follow=True)
        self.assertContains(response, 'WATCH10')
        self.assertEqual(response.context['basket'].total_excl_tax, Decimal('225.90'))
        self.assertContains(response, str(currency(Decimal('25.10'), 'JOD')))
        remove_url = reverse('basket:vouchers-remove', kwargs={'pk': voucher.pk})
        self.assertContains(response, 'action="' + remove_url + '"')
        response = self.post(remove_url, {}, follow=True)
        self.assertEqual(response.context['basket'].total_excl_tax, Decimal('251.00'))
        response = self.post(reverse('basket:vouchers-add'), {'code': 'DOES-NOT-EXIST'}, follow=True)
        self.assertContains(response, 'DOES-NOT-EXIST')
        self.assertTrue(any(message.level_tag == 'error' for message in response.context['messages']))
        self.assertEqual(response.context['basket'].total_excl_tax, Decimal('251.00'))

    def test_save_move_back_validation_and_remove(self):
        self.client.force_login(self.user)
        self.client.get(self.url)
        line = self.add()
        response = self.update(1, **{'form-0-save_for_later': 'on'})
        self.assertIn('Saved for later', response.json()['content_html'])
        line.refresh_from_db()
        self.assertEqual(line.basket.status, Basket.SAVED)

        def saved_post(action):
            formset = self.client.get(self.url).context['saved_formset']
            data = {field.html_name: field.value() for field in formset.management_form}
            data.update({'saved-0-id': line.pk, 'saved-0-' + action: 'on'})
            return self.post(reverse('basket:saved'), data, follow=True)

        self.stock.num_in_stock = 0
        self.stock.save()
        response = saved_post('move_to_basket')
        self.assertTrue(any(message.level_tag == 'error' for message in response.context['messages']))
        line.refresh_from_db()
        self.assertEqual(line.basket.status, Basket.SAVED)
        self.stock.num_in_stock = 5
        self.stock.save()
        saved_post('move_to_basket')
        line = Line.objects.get(basket__status=Basket.OPEN)
        self.update(1, **{'form-0-save_for_later': 'on'})
        line = Line.objects.get(basket__status=Basket.SAVED)
        saved_post('DELETE')
        self.assertFalse(Line.objects.exists())

    def test_shipping_totals_checkout_gateway_and_style_isolation(self):
        self.add()
        shipping = get_class('shipping.methods', 'FixedPrice')(charge_excl_tax=Decimal('5'), charge_incl_tax=Decimal('5'))
        with patch('oscar.apps.basket.views.Repository.methods', (shipping,)):
            response = self.client.get(self.url)
        self.assertEqual(response.context['shipping_charge'].excl_tax, Decimal('5'))
        self.assertEqual(response.context['order_total'].excl_tax, Decimal('130.50'))
        self.assertContains(response, str(currency(Decimal('130.50'), 'JOD')))
        checkout = self.client.get(reverse('checkout:index'), follow=True)
        self.assertEqual(checkout.status_code, 200)
        self.assertTemplateUsed(checkout, 'oscar/customer/login_registration.html')
        self.assertNotContains(checkout, 'abdeen/css/basket.css')
        for url in ['/', reverse('catalogue:index'), self.product.get_absolute_url()]:
            self.assertNotContains(self.client.get(url), 'abdeen/css/basket.css')
