"""Homepage integration tests; all catalogue fixtures live in the test database."""

from decimal import Decimal
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse
from oscar.core.loading import get_class, get_model
from oscar.templatetags.currency_filters import currency

from .homepage import HomepageView, range_products


Product = get_model('catalogue', 'Product')
ProductClass = get_model('catalogue', 'ProductClass')
ProductImage = get_model('catalogue', 'ProductImage')
Category = get_model('catalogue', 'Category')
Range = get_model('offer', 'Range')
Partner = get_model('partner', 'Partner')
StockRecord = get_model('partner', 'StockRecord')
FixedPrice = get_class('partner.prices', 'FixedPrice')
Available = get_class('partner.availability', 'Available')
PurchaseInfo = get_class('partner.strategy', 'PurchaseInfo')


class HomepageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.product_class = ProductClass.objects.create(name='Watches', track_stock=True)
        cls.partner = Partner.objects.create(name='Test supplier')

    def product(self, title, **kwargs):
        kwargs.setdefault('product_class', self.product_class)
        return Product.objects.create(title=title, **kwargs)

    def stock(self, product, price='125.50', currency_code='JOD', quantity=3):
        return StockRecord.objects.create(
            product=product, partner=self.partner, partner_sku=f'TEST-{product.pk}',
            price=Decimal(price), price_currency=currency_code, num_in_stock=quantity,
        )

    def test_missing_and_empty_ranges_render_without_creating_data(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Our Best Sellers selection is being prepared.')
        self.assertContains(response, 'Our New Arrivals selection is being prepared.')
        self.assertContains(response, 'Our categories are being prepared.')
        self.assertContains(response, 'Our brand collection is being prepared.')
        self.assertNotContains(response, 'data-home-product ')
        self.assertNotContains(response, 'data-home-filters')
        self.assertEqual(Range.objects.count(), 0)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)
        Range.objects.create(name='Best Sellers')
        Range.objects.create(name='New Arrivals')
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_named_ranges_are_independent_and_use_manual_order(self):
        best = Range.objects.create(name='Best Sellers')
        new = Range.objects.create(name='New Arrivals')
        first = self.product('First manual pick')
        second = self.product('Second manual pick')
        arrival = self.product('Arrival pick')
        excluded = self.product('Excluded pick')
        hidden = self.product('Private pick', is_public=False)
        self.product('Not selected')
        best.add_product(second, display_order=2)
        best.add_product(first, display_order=1)
        best.add_product(excluded, display_order=0)
        best.excluded_products.add(excluded)
        best.add_product(hidden, display_order=0)
        new.add_product(arrival)
        # Another range's order must not duplicate or reorder the Best Sellers.
        new.add_product(second, display_order=-10)
        self.assertEqual([p.pk for p in range_products('Best Sellers')], [first.pk, second.pk])
        self.assertEqual([p.pk for p in range_products('New Arrivals')], [second.pk, arrival.pk])
        best.remove_product(first)
        self.assertEqual([p.pk for p in range_products('Best Sellers')], [second.pk])

    def test_automatic_range_rules_never_add_unselected_products(self):
        category = Category.add_root(name='Watches')
        automatic = self.product('Not manually selected')
        automatic.categories.add(category)
        selected = self.product('Manually selected')
        product_range = Range.objects.create(name='Best Sellers', includes_all_products=True)
        product_range.add_product(selected)
        self.assertEqual([p.pk for p in range_products('Best Sellers')], [selected.pk])
        product_range.includes_all_products = False
        product_range.save()
        product_range.included_categories.add(category)
        product_range.classes.add(self.product_class)
        self.assertEqual([p.pk for p in range_products('Best Sellers')], [selected.pk])

    def test_limit_and_child_visibility(self):
        product_range = Range.objects.create(name='Best Sellers')
        parent = self.product('Variant family', structure=Product.PARENT)
        child = self.product('Variant only', structure=Product.CHILD, parent=parent, product_class=None)
        product_range.add_product(child, display_order=-2)
        product_range.add_product(parent, display_order=-1)
        expected = [parent.pk]
        for index in range(9):
            product = self.product(f'Manual product {index}')
            product_range.add_product(product, display_order=index)
            expected.append(product.pk)
        self.assertEqual([p.pk for p in range_products('Best Sellers')], expected[:8])

    def test_real_product_links_images_stock_and_jod(self):
        product = self.product('Actual watch title')
        self.stock(product)
        ProductImage.objects.create(product=product, original='products/real-watch.jpg')
        product_range = Range.objects.create(name='Best Sellers')
        product_range.add_product(product)
        response = self.client.get('/')
        self.assertContains(response, product.get_absolute_url())
        self.assertContains(response, '/media/products/real-watch.jpg')
        self.assertContains(response, currency(Decimal('125.50'), 'JOD'))
        self.assertContains(response, 'In stock')
        self.assertNotContains(response, 'Illustrative model')
        stock = product.stockrecords.get()
        stock.num_in_stock = 0
        stock.save()
        self.assertContains(self.client.get('/'), 'Unavailable')

    def test_missing_images_stock_and_foreign_currency(self):
        no_stock = self.product('No stock record')
        foreign = self.product('Foreign currency watch')
        self.stock(foreign, price='987.65', currency_code='USD')
        product_range = Range.objects.create(name='New Arrivals')
        product_range.add_product(no_stock)
        product_range.add_product(foreign)
        response = self.client.get('/')
        self.assertContains(response, '/static/abdeen/images/watch-placeholder.svg')
        self.assertContains(response, 'Price unavailable')
        self.assertContains(response, 'JOD price unavailable')
        self.assertNotContains(response, '987.65')

    def test_parent_uses_public_child_strategy(self):
        parent = self.product('Parent watch', structure=Product.PARENT)
        hidden = self.product('Private variant', structure=Product.CHILD, parent=parent,
                              product_class=None, is_public=False)
        child = self.product('Public variant', structure=Product.CHILD, parent=parent, product_class=None)
        self.stock(hidden, price='999.00')
        self.stock(child, price='210.00')
        product_range = Range.objects.create(name='New Arrivals')
        product_range.add_product(parent)
        response = self.client.get('/')
        self.assertContains(response, currency(Decimal('210.00'), 'JOD'))
        self.assertNotContains(response, currency(Decimal('999.00'), 'JOD'))
        self.assertContains(response, 'Choose Options')

    def test_card_uses_request_strategy_and_handles_unknown_tax_and_zero(self):
        product = self.product('Strategy priced watch')
        request = RequestFactory().get('/')
        request.strategy = Mock()
        for price, tax, expected in [('100', '16', '116'), ('100', None, '100'), ('0', '0', '0')]:
            with self.subTest(price=price, tax=tax):
                policy = FixedPrice('JOD', Decimal(price), tax=Decimal(tax) if tax is not None else None)
                request.strategy.fetch_for_product.return_value = PurchaseInfo(policy, Available(), None)
                html = render_to_string('oscar/partials/home/product_card.html',
                                        {'product': product, 'request': request, 'badge': 'Best Seller'})
                self.assertIn(str(currency(Decimal(expected), 'JOD')), html)
                self.assertEqual('excl. tax' in html, tax is None)
        self.assertEqual(request.strategy.fetch_for_product.call_count, 3)

    def test_real_categories_brand_pages_and_filter_tokens(self):
        root = Category.add_root(name='Brands', slug='brands')
        brand = root.add_child(name='Example brand', slug='example-brand')
        department = Category.add_root(name='Watches', slug='watches', image='categories/watches.jpg')
        missing_image = Category.add_root(name='Accessories')
        private = Category.add_root(name='Private department', is_public=False)
        private.add_child(name='Private descendant')
        product = self.product('Branded watch')
        product.categories.add(brand, department)
        product_range = Range.objects.create(name='Best Sellers')
        product_range.add_product(product)
        response = self.client.get('/')
        self.assertEqual([b.pk for b in response.context['homepage_brands']], [brand.pk])
        self.assertEqual({c.pk for c in response.context['homepage_categories']}, {department.pk, missing_image.pk})
        self.assertContains(response, brand.get_absolute_url())
        self.assertContains(response, department.get_absolute_url())
        self.assertContains(response, '/media/categories/watches.jpg')
        self.assertContains(response, 'Image coming soon')
        self.assertContains(response, f'data-home-filter="category-{brand.pk}"')
        self.assertEqual(response.context['best_sellers'][0].homepage_brand_name, brand.name)
        self.assertNotContains(response, 'Private department')

    def test_oscar_routes_and_dashboard_are_preserved(self):
        self.assertEqual(reverse('home'), '/')
        self.assertIs(resolve('/').func.view_class, HomepageView)
        for name, status in [('catalogue:index', 200), ('basket:summary', 200),
                             ('checkout:index', 302), ('dashboard:login', 200)]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, status)
            self.assertNotContains(response, 'data-home-product ', status_code=status)
        staff = get_user_model().objects.create_user(username='staff', is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        dashboard = self.client.get(reverse('dashboard:index'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotContains(dashboard, 'abdeen/css/tailwind.css')

    def test_menu_excluded_branches_do_not_leak_into_filters(self):
        root = Category.add_root(name='Hidden menu branch', exclude_from_menu=True)
        child = root.add_child(name='Hidden menu descendant')
        product = self.product('Visible product')
        product.categories.add(child)
        product_range = Range.objects.create(name='Best Sellers')
        product_range.add_product(product)
        response = self.client.get('/')
        self.assertContains(response, product.get_title())
        self.assertNotContains(response, child.name)
        self.assertEqual(response.context['product_filters'], [('all', 'All Picks')])
