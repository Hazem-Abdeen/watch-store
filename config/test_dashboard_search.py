from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from oscar.core.loading import get_model


class DashboardProductSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Product = get_model('catalogue', 'Product')
        product_class = get_model('catalogue', 'ProductClass').objects.create(name='Watches')
        cls.watch = Product.objects.create(title='Classic watch', upc='WATCH-UPC', product_class=product_class)
        cls.other = Product.objects.create(title='Other watch', product_class=product_class)
        cls.parent = Product.objects.create(title='Variant watch', structure=Product.PARENT, product_class=product_class)
        cls.child = Product.objects.create(parent=cls.parent, structure=Product.CHILD)
        partner = get_model('partner', 'Partner').objects.create(name='Supplier')
        StockRecord = get_model('partner', 'StockRecord')
        for product, sku in [(cls.watch, 'ABC-123'), (cls.child, 'VAR-456')]:
            StockRecord.objects.create(product=product, partner=partner, partner_sku=sku)
        StockRecord.objects.create(product=cls.watch, partner=partner, partner_sku='ABC-124')
        cls.staff = get_user_model().objects.create_user(username='search-admin', is_staff=True)

    def setUp(self):
        self.client.force_login(self.staff)
        self.url = reverse('dashboard:catalogue-product-list')

    def results(self, params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response, list(response.context['object_list'])

    def test_form_renders_new_fields(self):
        response, products = self.results({})
        self.assertContains(response, 'name="sku"')
        self.assertContains(response, 'name="product_id"')
        self.assertCountEqual(products, [self.watch, self.other, self.parent])

    def test_partial_case_insensitive_sku_without_duplicates(self):
        self.assertEqual(self.results({'sku': ' abc-12 '})[1], [self.watch])

    def test_exact_product_id(self):
        self.assertEqual(self.results({'product_id': self.watch.pk})[1], [self.watch])

    def test_variant_search_returns_parent(self):
        for params in [{'sku': 'var-456'}, {'product_id': self.child.pk}]:
            with self.subTest(params=params):
                self.assertEqual(self.results(params)[1], [self.parent])

    def test_filters_combine_with_existing_fields(self):
        self.assertEqual(self.results({
            'sku': 'ABC', 'product_id': self.watch.pk, 'title': 'Classic', 'upc': 'WATCH-UPC',
        })[1], [self.watch])
        self.assertEqual(self.results({'sku': 'ABC', 'title': 'Other'})[1], [])

    def test_unknown_values_return_no_results(self):
        for params in [{'sku': 'missing'}, {'product_id': 999999}]:
            with self.subTest(params=params):
                self.assertEqual(self.results(params)[1], [])

    def test_invalid_ids_show_validation_errors(self):
        for value in ['invalid', '0', '-1', '1.5', '9' * 30]:
            with self.subTest(value=value):
                response, products = self.results({'product_id': value})
                self.assertIn('product_id', response.context['form'].errors)
                self.assertEqual(products, [])
