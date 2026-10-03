"""Recommendation ranking, query bounds, and the detail page integration."""
from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from oscar.core.loading import get_class, get_model

from catalogue_import.recommendations import CANDIDATE_LIMIT, card_products, recommended_products

Product = get_model('catalogue', 'Product')
ProductClass = get_model('catalogue', 'ProductClass')
Attribute = get_model('catalogue', 'ProductAttribute')
AttributeValue = get_model('catalogue', 'ProductAttributeValue')
Category = get_model('catalogue', 'Category')
Partner = get_model('partner', 'Partner')
StockRecord = get_model('partner', 'StockRecord')


class RecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.product_class = ProductClass.objects.create(name='Watches', track_stock=True)
        cls.brand = Attribute.objects.create(product_class=cls.product_class, code='brand', name='Brand')
        cls.gender = Attribute.objects.create(product_class=cls.product_class, code='gender', name='Gender')
        cls.partner = Partner.objects.create(name='Supplier')
        cls.men = Category.add_root(name='Men', slug='men')
        cls.brands = Category.add_root(name='Brands', slug='brands')
        cls.casio = cls.brands.add_child(name='Casio', slug='casio')

    def setUp(self):
        self.request = RequestFactory().get('/')
        self.request.user = AnonymousUser()
        self.strategy = self.request.strategy = get_class('partner.strategy', 'Selector')().strategy(
            request=self.request,
        )
        self.current = self.make_product('Current', 'Casio', 'Men')

    def make_product(self, title, brand=None, gender=None, stock=3, **kwargs):
        product = Product.objects.create(title=title, product_class=self.product_class, **kwargs)
        for attribute, value in [(self.brand, brand), (self.gender, gender)]:
            if value is not None:
                AttributeValue.objects.create(product=product, attribute=attribute, value_text=value)
        if stock is not None:
            StockRecord.objects.create(product=product, partner=self.partner, partner_sku=f'WATCH-{product.pk}',
                                       price=Decimal('125.50'), price_currency='JOD', num_in_stock=stock)
        return product

    def recommendations(self, product=None):
        return recommended_products(product or self.current, self.strategy)

    def test_relevance_tiers_and_case_insensitive_matching(self):
        category = self.make_product('Category fallback', 'Other', 'Women')
        category.categories.add(self.men)
        self.current.categories.add(self.men)
        gender = self.make_product('Same gender', 'Other', 'men')
        brand = self.make_product('Same brand', 'CASIO', 'Women')
        both = self.make_product('Both', 'casio', 'MEN')
        self.assertEqual(self.recommendations(), [both, brand, gender, category])

    def test_only_same_brand_matches(self):
        brand = self.make_product('Brand', 'Casio', 'Women')
        self.make_product('Unrelated', 'Other', 'Women')
        self.assertEqual(self.recommendations(), [brand])

    def test_fallback_with_only_gender_or_category(self):
        gender = self.make_product('Gender', 'Other', 'Men')
        category = self.make_product('Category')
        self.current.categories.add(self.men)
        category.categories.add(self.men)
        self.assertEqual(self.recommendations(), [gender, category])

    def test_brand_categories_support_missing_attributes_and_subbrands(self):
        current = self.make_product('No brand attribute')
        subbrand = self.casio.add_child(name='Edifice', slug='edifice')
        current.categories.add(subbrand)
        match = self.make_product('Category brand')
        match.categories.add(self.casio)
        self.assertEqual(self.recommendations(current), [match])

    def test_exclusion_duplicates_public_products_maximum_and_stable_order(self):
        matches = [self.make_product(f'Match {i}', 'Casio', 'Men') for i in range(6)]
        self.current.categories.add(self.casio, self.men)
        for match in matches:
            match.categories.add(self.casio, self.men)
        self.make_product('Private', 'Casio', 'Men', is_public=False)
        child = Product.objects.create(title='Child', structure=Product.CHILD, parent=self.current)
        AttributeValue.objects.create(product=child, attribute=self.brand, value_text='Casio')
        self.assertEqual(self.recommendations(), matches[:4])
        self.assertEqual(self.recommendations(), matches[:4])
        self.assertNotIn(self.current, self.recommendations())

    def test_fewer_than_four_and_no_matches(self):
        self.assertEqual(self.recommendations(), [])
        one = self.make_product('One', 'Casio', 'Men')
        self.assertEqual(self.recommendations(), [one])
        empty = self.make_product('No matching facts')
        self.assertEqual(self.recommendations(empty), [])

    def test_oscar_availability_prefers_stock_and_respects_allocations(self):
        allocated = self.make_product('Allocated', 'Casio', 'Men')
        StockRecord.objects.filter(product=allocated).update(num_allocated=3)
        unavailable = self.make_product('No record', 'Casio', 'Men', stock=None)
        available = self.make_product('Available', 'Casio', 'Men')
        self.assertEqual(self.recommendations(), [available, allocated, unavailable])
        self.assertEqual(StockRecord.objects.get(product=allocated).num_allocated, 3)

    def test_relevance_precedes_availability(self):
        strong = self.make_product('Unavailable strong', 'Casio', 'Men', stock=0)
        weak = self.make_product('Available weaker', 'Casio', 'Women')
        self.assertEqual(self.recommendations(), [strong, weak])

    def test_parent_availability_uses_public_children_and_inherited_class(self):
        parent = self.make_product('Parent', 'Casio', 'Men', stock=None, structure=Product.PARENT)
        child = Product.objects.create(title='Variant', structure=Product.CHILD, parent=parent)
        StockRecord.objects.create(product=child, partner=self.partner, partner_sku='VARIANT',
                                   price=Decimal('99'), num_in_stock=2, price_currency='JOD')
        result = self.recommendations()
        with self.assertNumQueries(0):
            self.assertTrue(self.strategy.fetch_for_parent(result[0]).availability.is_available_to_buy)
        self.assertEqual(result, [parent])

    def test_candidate_work_is_bounded_and_card_rendering_has_no_n_plus_one(self):
        for i in range(CANDIDATE_LIMIT + 5):
            self.make_product(f'Match {i}', 'Casio', 'Men')
        with CaptureQueriesContext(connection) as queries:
            result = self.recommendations()
        self.assertLessEqual(len(queries), 9)
        candidate_sql = next(q['sql'] for q in queries if 'recommendation_tier' in q['sql'])
        self.assertIn(f'LIMIT {CANDIDATE_LIMIT}', candidate_sql)
        template = Template('{% for product in products %}{% include "oscar/partials/products/card.html" %}{% endfor %}')
        with self.assertNumQueries(0):
            html = template.render(Context({'products': result, 'request': self.request}))
        self.assertEqual(html.count('class="abdeen-product-card"'), 4)
        self.assertIn('125.5 JOD', html)
        self.assertIn('Casio', html)
        self.assertNotIn('product_pod', html)

    def test_cards_bulk_load_options(self):
        option = get_model('catalogue', 'Option').objects.create(name='Engraving', code='engraving')
        self.current.product_options.add(option)
        loaded = list(card_products(Product.objects.filter(pk=self.current.pk)))
        with self.assertNumQueries(0):
            self.assertTrue(loaded[0].has_options)

    def test_recommendations_precede_independent_history_and_replace_manual_cards(self):
        match = self.make_product('Recommended', 'Casio', 'Men')
        history = self.make_product('Previously viewed', 'Other', 'Women')
        self.current.recommended_products.add(history)
        self.client.get(history.get_absolute_url())
        response = self.client.get(self.current.get_absolute_url())
        html = response.content.decode()
        self.assertLess(html.index('You May Also Like'), html.index('Recently Viewed'))
        self.assertContains(response, match.get_absolute_url())
        self.assertContains(response, history.get_absolute_url())
        self.assertNotContains(response, 'Recommended items')
        recommendations, history_html = html.split('class="abdeen-recently-viewed"', 1)
        self.assertNotIn(history.get_absolute_url(), recommendations)
        self.assertIn(history.get_absolute_url(), history_html)

    def test_empty_recommendations_do_not_hide_history(self):
        history = self.make_product('Previously viewed', 'Other', 'Women')
        self.client.get(history.get_absolute_url())
        response = self.client.get(self.current.get_absolute_url())
        self.assertNotContains(response, 'You May Also Like')
        self.assertContains(response, 'Recently Viewed')

    def test_specification_disclosure_keeps_useful_values_once(self):
        for code, name, value in [('country_of_manufacture', 'Country of Manufacture', 'Japan'),
                                  ('guarantee', 'Guarantee', 'Two years'),
                                  ('movement', 'Movement', 'Quartz'),
                                  ('case_size', 'Case Size', '   '),
                                  ('import_source', 'Import Source', 'hidden-import')]:
            attr = Attribute.objects.create(product_class=self.product_class, code=code, name=name)
            AttributeValue.objects.create(product=self.current, attribute=attr, value_text=value)
        self.current.description = '<p>Movement: Quartz</p><p>An everyday watch.</p>'
        self.current.save()
        response = self.client.get(self.current.get_absolute_url())
        self.assertContains(response, '<details class="abdeen-detail-disclosure" data-specifications>')
        self.assertContains(response, 'id="product-specifications" role="region" aria-labelledby="specifications-toggle"')
        for text in ['<dd>Quartz</dd>', '<dd>Japan</dd>', '<dd>Two years</dd>']:
            self.assertContains(response, text, count=1)
        for text in ['Product Details', '<dt>Case Size</dt>', 'hidden-import', 'Movement: Quartz']:
            self.assertNotContains(response, text)
