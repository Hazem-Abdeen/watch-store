"""Reference pricing must never become the payable basket/order price."""
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction, connection
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from oscar.core.loading import get_class, get_model
from oscar.apps.partner.strategy import Default, FixedRateTax, UseFirstStockRecord, StockRequired, Structured, DeferredTax

from catalogue_import.catalogue import SOURCE
from catalogue_import.models import CatalogueSource
from config.partner.pricing import sale_presentation, valid_regular_price

StockRecord = get_model('partner', 'StockRecord')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SalePricingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.product_class = get_model('catalogue', 'ProductClass').objects.create(name='Watches', track_stock=True)
        cls.product = get_model('catalogue', 'Product').objects.create(title='Sale watch', product_class=cls.product_class)
        cls.product.categories.add(get_model('catalogue', 'Category').add_root(name='Sale watches'))
        cls.partner = get_model('partner', 'Partner').objects.create(name='Supplier')
        cls.stock = StockRecord.objects.create(product=cls.product, partner=cls.partner,
            partner_sku='SALE', price_currency='JOD', price=Decimal('95'), num_in_stock=10)
        cls.staff = get_user_model().objects.create_superuser('sale-admin', 'admin@example.test', 'test-password')
        get_model('address', 'Country').objects.create(iso_3166_1_a2='JO', iso_3166_1_a3='JOR',
            printable_name='Jordan', name='Jordan', is_shipping_country=True)

    def request(self, strategy=Default):
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        request.strategy = strategy(request)
        return request

    def set_regular(self, value):
        self.stock.regular_price = None if value is None else Decimal(value)
        self.stock.save()

    def test_model_registration_and_positive_validation(self):
        self.assertEqual(StockRecord.__module__, 'config.partner.models')
        for value in [None, '90', '95', '120']:
            self.set_regular(value)
            self.stock.full_clean()
        for value in ['0', '-1']:
            self.stock.regular_price = Decimal(value)
            with self.assertRaises(ValidationError):
                self.stock.full_clean()
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.stock.save()

    def test_card_and_detail_share_sale_rules(self):
        for value, on_sale in [(None, False), ('120', True), ('95', False), ('90', False)]:
            with self.subTest(regular=value):
                self.set_regular(value)
                card = render_to_string('oscar/partials/products/card.html', {
                    'request': self.request(), 'product': self.product})
                detail = self.client.get(self.product.get_absolute_url())
                self.assertEqual(detail.status_code, 200)
                for html in [card, detail.content.decode()]:
                    self.assertIn('95 JOD', html)
                    self.assertEqual('<s class="abdeen-price-regular">' in html, on_sale)
                    self.assertEqual('21% OFF' in html, on_sale)
                    if on_sale:
                        self.assertIn('120 JOD</s>', html)
                        self.assertIn('Current price', html)

    def test_percentage_rounding_and_reference_is_not_saved(self):
        request = self.request()
        self.set_regular('120')
        for current, expected in [('95', 21), ('95.40', 21), ('95.41', 20), ('0', 100)]:
            self.stock.price = Decimal(current)
            self.stock.save()
            purchase = request.strategy.fetch_for_product(self.product)
            result = sale_presentation(request, self.product, purchase)
            self.assertEqual(result['percentage'], Decimal(expected))
            self.stock.refresh_from_db()
            self.assertEqual(self.stock.price, Decimal(current))
            self.assertEqual(purchase.stockrecord.price, Decimal(current))

    def test_missing_price_and_parent_do_not_advertise_sale(self):
        self.set_regular('120')
        self.stock.price = None
        self.stock.save()
        request = self.request()
        self.assertIsNone(sale_presentation(request, self.product, request.strategy.fetch_for_product(self.product)))
        self.product.structure = self.product.PARENT
        self.assertIsNone(sale_presentation(request, self.product, request.strategy.fetch_for_parent(self.product)))

    def test_import_metadata_is_never_a_live_sale_source(self):
        CatalogueSource.objects.create(source=SOURCE, source_id=1, product=self.product,
            stockrecord=self.stock, metadata={'regular_price': '120', 'sale_price': '50'})
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, '95 JOD')
        self.assertNotContains(response, 'abdeen-price-regular')
        self.assertNotContains(response, '50 JOD')

    def test_selected_stockrecord_controls_reference_price(self):
        other_partner = get_model('partner', 'Partner').objects.create(name='Other supplier')
        other = StockRecord.objects.create(product=self.product, partner=other_partner,
            partner_sku='OTHER', price_currency='JOD', price=Decimal('95'),
            regular_price=Decimal('150'), num_in_stock=1)
        request = self.request()
        purchase = request.strategy.fetch_for_product(self.product, stockrecord=other)
        result = sale_presentation(request, self.product, purchase)
        self.assertEqual(result['regular'], Decimal('150'))
        self.assertIsNone(sale_presentation(request, self.product,
                                          request.strategy.fetch_for_product(self.product, stockrecord=self.stock)))

    def test_same_tax_basis_and_currency(self):
        class Taxed(UseFirstStockRecord, StockRequired, FixedRateTax, Structured):
            rate = Decimal('.16')

        class UnknownTax(UseFirstStockRecord, StockRequired, DeferredTax, Structured):
            pass

        self.set_regular('120')
        for strategy, old, current, known in [(Taxed, '139.20', '110.20', True),
                                             (UnknownTax, '120', '95', False)]:
            request = self.request(strategy)
            result = sale_presentation(request, self.product, request.strategy.fetch_for_product(self.product))
            self.assertEqual((result['regular'], result['current']), (Decimal(old), Decimal(current)))
            self.assertEqual(result['currency'], 'JOD')
            self.assertEqual(result['is_tax_known'], known)
            self.assertEqual(result['percentage'], 21)

    def test_dashboard_form_and_edit_page(self):
        Form = get_class('dashboard.catalogue.forms', 'StockRecordForm')
        self.assertEqual(Form.__module__, 'config.dashboard.catalogue.forms')
        for regular in ['', '120', '95', '90']:
            form = Form(self.product_class, self.staff, instance=self.stock, data={
                'partner': self.partner.pk, 'partner_sku': 'SALE', 'price_currency': 'JOD',
                'price': '95', 'regular_price': regular, 'num_in_stock': '10', 'low_stock_threshold': ''})
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
            self.stock.refresh_from_db()
            self.assertEqual(self.stock.regular_price, Decimal(regular) if regular else None)
        self.client.force_login(self.staff)
        response = self.client.get(reverse('dashboard:catalogue-product', kwargs={'pk': self.product.pk}))
        self.assertContains(response, 'name="stockrecords-0-regular_price"')
        self.assertContains(response, 'Regular price')
        # Submit the real product view and all its inline formsets, not just
        # the model form, to verify Oscar's dynamic form loading end to end.
        data = {}
        forms = [response.context['form']]
        for name in response.context['view'].formsets:
            formset = response.context[name]
            forms.extend([formset.management_form, *formset.initial_forms])
        for form in forms:
            for field in form:
                value = field.value()
                if value is not False:
                    data[field.html_name] = 'on' if value is True else (value if value is not None else '')
        data['stockrecords-0-regular_price'] = '120.00'
        for name in response.context['view'].formsets:
            formset = response.context[name]
            data[f'{formset.prefix}-TOTAL_FORMS'] = str(formset.initial_form_count())
        response = self.client.post(reverse('dashboard:catalogue-product', kwargs={'pk': self.product.pk}), data)
        self.assertEqual(response.status_code, 302, {
            name: str(response.context[name].errors) + (str(response.context[name].non_form_errors()) if name != 'form' else '')
            for name in ['form', *response.context['view'].formsets]
        } if response.status_code == 200 else '')
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.regular_price, Decimal('120'))

    def add_offer(self):
        product_range = get_model('offer', 'Range').objects.create(name='Sale watch only')
        product_range.add_product(self.product)
        condition = get_model('offer', 'Condition').objects.create(range=product_range, type='Count', value=1)
        benefit = get_model('offer', 'Benefit').objects.create(range=product_range, type='Percentage', value=10)
        return get_model('offer', 'ConditionalOffer').objects.create(name='Extra 10%', condition=condition, benefit=benefit)

    def place_order(self, offer=False):
        self.set_regular('120')
        if offer:
            self.add_offer()
        response = self.client.post(reverse('basket:add', kwargs={'pk': self.product.pk}), {'quantity': 1})
        self.assertEqual(response.status_code, 302)
        basket = self.client.get(reverse('basket:summary')).context['basket']
        expected = Decimal('85.50') if offer else Decimal('95')
        self.assertEqual(basket.all_lines()[0].unit_price_incl_tax, Decimal('95'))
        self.assertEqual(basket.total_incl_tax, expected)
        page = self.client.get(reverse('checkout:index'))
        response = self.client.post(reverse('checkout:index'), {
            'email': 'guest@example.test', 'phone_number': '0791234567', 'country': 'JO',
            'first_name': 'Sale', 'last_name': 'Customer', 'line1': '12 Example Street',
            'line4': 'Amman', 'method_code': get_class('shipping.methods', 'Delivery')().code,
            'action': 'place_order', 'quote': page.context['quote'],
        }, follow=True)
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        order = get_model('order', 'Order').objects.get()
        self.assertEqual(order.total_incl_tax, expected + Decimal('2.00'))
        self.assertEqual(order.shipping_incl_tax, Decimal('2.00'))
        self.assertEqual(order.lines.get().unit_price_incl_tax, Decimal('95'))
        self.assertEqual(order.sources.get().amount_allocated, expected + Decimal('2.00'))
        if offer:
            self.assertEqual(order.discounts.get().amount, Decimal('9.50'))
        else:
            self.assertFalse(order.discounts.exists())
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.price, Decimal('95'))
        self.assertEqual(self.stock.regular_price, Decimal('120'))

    def test_basket_checkout_order_use_current_price(self):
        self.place_order()

    def test_offer_applies_on_current_price_through_order(self):
        self.place_order(offer=True)

    def test_backfill_is_validated_fill_only_and_dry_run_has_no_writes(self):
        mapping = CatalogueSource.objects.create(source=SOURCE, source_id=1, product=self.product,
            stockrecord=self.stock, metadata={'regular_price': '120'})
        with CaptureQueriesContext(connection) as queries:
            call_command('backfill_regular_prices', dry_run=True, stdout=StringIO())
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('UPDATE', 'INSERT', 'DELETE')) for q in queries))
        self.stock.refresh_from_db()
        self.assertIsNone(self.stock.regular_price)
        call_command('backfill_regular_prices', stdout=StringIO())
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.regular_price, Decimal('120'))
        mapping.metadata['regular_price'] = '140'
        mapping.save()
        call_command('backfill_regular_prices', stdout=StringIO())
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.regular_price, Decimal('120'))
        self.assertEqual(self.stock.price, Decimal('95'))
        for invalid in [None, '', 'NaN', 'Infinity', '-5', '0', 'no', '1.234', '10000000000', True, {}, []]:
            with self.subTest(invalid=invalid):
                self.set_regular(None)
                mapping.metadata['regular_price'] = invalid
                mapping.save()
                self.assertIsNone(valid_regular_price(invalid))
                call_command('backfill_regular_prices', stdout=StringIO())
                self.stock.refresh_from_db()
                self.assertIsNone(self.stock.regular_price)
