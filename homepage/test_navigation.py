"""Navigation and real Oscar category routes share live, scoped gender matching."""
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from oscar.core.loading import get_class, get_model

from config.catalogue.gender import gender_products
from homepage.templatetags.brand_navigation import brand_navigation

Category = get_model('catalogue', 'Category')
Product = get_model('catalogue', 'Product')
ProductImage = get_model('catalogue', 'ProductImage')
AttributeValue = get_model('catalogue', 'ProductAttributeValue')


class BrandCatalogueFixtures:
    @classmethod
    def setUpTestData(cls):
        cls.root = Category.add_root(name='Brands', slug='brands')
        cls.both = cls.root.add_child(name='Zulu')
        cls.male = cls.root.add_child(name='alpha')
        cls.female = cls.root.add_child(name='Beta')
        cls.empty = cls.root.add_child(name='Empty')
        cls.unknown = cls.root.add_child(name='Unknown')
        cls.hidden = cls.root.add_child(name='Excluded', exclude_from_menu=True)
        cls.private = cls.root.add_child(name='Private', is_public=False)
        cls.collection = cls.both.add_child(name='Collection')
        cls.men_category = Category.add_root(name='Men', slug='men')
        cls.watch = get_model('catalogue', 'ProductClass').objects.create(name='Watch')
        cls.accessory = get_model('catalogue', 'ProductClass').objects.create(name='Accessory')
        cls.gender = get_model('catalogue', 'ProductAttribute').objects.create(
            product_class=cls.watch, name='Gender', code='gender', type='text',
        )
        cls.partner = get_model('partner', 'Partner').objects.create(name='Test supplier')
        cls.mens_watch = cls.make_watch('Needle collection watch', cls.collection, 'Men')
        cls.womens_watch = cls.make_watch('Needle women watch', cls.both, 'Women')
        cls.other_brand = cls.make_watch('Needle other brand', cls.male, 'Men')
        cls.only_women = cls.make_watch('Needle only women', cls.female, 'Women')
        cls.unspecified = cls.make_watch('Unspecified watch', cls.unknown)
        cls.sold_out = cls.make_watch('Needle sold out', cls.both, 'Men', available=False)
        cls.private_watch = cls.make_watch('Private women watch', cls.male, 'Women', is_public=False)
        cls.imageless = cls.make_watch('Imageless women watch', cls.male, 'Women', image=False)
        cls.placeholder = cls.make_watch('Placeholder women watch', cls.male, 'Women', image=False)
        ProductImage.objects.create(product=cls.placeholder, original='abdeen/images/watch-placeholder.svg')
        cls.accessory_product = cls.make_watch('Accessory women', cls.male, 'Women', product_class=cls.accessory)
        cls.make_watch('Hidden brand watch', cls.hidden, 'Men')
        cls.make_watch('Private brand watch', cls.private, 'Men')
        cls.mens_watch.categories.add(cls.men_category)
        cls.other_brand.categories.add(cls.men_category)

    @classmethod
    def make_watch(cls, title, category, gender=None, *, image=True, available=True, **kwargs):
        kwargs.setdefault('product_class', cls.watch)
        product = Product.objects.create(title=title, **kwargs)
        product.categories.add(category)
        if gender:
            AttributeValue.objects.create(product=product, attribute=cls.gender, value_text=gender)
        if image:
            ProductImage.objects.create(product=product, original='products/test-watch.jpg')
        get_model('partner', 'StockRecord').objects.create(
            product=product, partner=cls.partner, partner_sku=f'NAV-{product.pk}',
            price_currency='JOD', price='42', availability_only=True,
            is_available=available, num_in_stock=None, num_allocated=0,
        )
        return product


class BrandNavigationTests(BrandCatalogueFixtures, TestCase):
    def menu(self):
        return {brand['name']: brand for brand in brand_navigation()['brands']}

    def test_dynamic_sorted_brands_and_constant_query_count(self):
        with self.assertNumQueries(3):
            menu = brand_navigation()
        self.assertEqual([b['name'] for b in menu['brands']], ['alpha', 'Beta', 'Empty', 'Unknown', 'Zulu'])
        for number in range(20):
            self.root.add_child(name=f'New {number}')
        with self.assertNumQueries(3):
            self.assertEqual(len(brand_navigation()['brands']), 25)

    def test_brand_and_gender_links_use_same_category_url(self):
        menu = self.menu()
        url = self.both.get_absolute_url()
        self.assertEqual(menu['Zulu']['url'], url)
        self.assertEqual(menu['Zulu']['genders'], [
            {'name': 'Men', 'url': url + '?gender=men'},
            {'name': 'Women', 'url': url + '?gender=women'},
        ])
        self.assertEqual(brand_navigation()['url'], self.root.get_absolute_url())

    def test_both_single_gender_empty_and_no_gender_options(self):
        menu = self.menu()
        self.assertEqual([g['name'] for g in menu['alpha']['genders']], ['Men'])
        self.assertEqual([g['name'] for g in menu['Beta']['genders']], ['Women'])
        self.assertEqual(menu['Empty']['genders'], [])
        self.assertEqual(menu['Unknown']['genders'], [])
        html = render_to_string('oscar/partials/home/brand_navigation.html',
                                {'brand_menu': brand_navigation(), 'placement': 'desktop'})
        self.assertEqual(html.count('data-brand-children'), 3)
        self.assertNotIn('Excluded', html)
        self.assertNotIn('Private', html)

    def test_unisex_normalization_and_live_attribute_updates(self):
        AttributeValue.objects.filter(product=self.other_brand).update(value_text=' Unisex ')
        self.assertEqual([g['name'] for g in self.menu()['alpha']['genders']], ['Men', 'Women'])
        AttributeValue.objects.filter(product=self.other_brand).update(value_text=' women ')
        self.assertEqual([g['name'] for g in self.menu()['alpha']['genders']], ['Women'])

    def test_image_removal_changes_options_immediately(self):
        self.only_women.images.all().delete()
        self.assertEqual(self.menu()['Beta']['genders'], [])

    def test_private_or_excluded_root_hides_tree(self):
        for field in ('is_public', 'exclude_from_menu'):
            with self.subTest(field=field):
                setattr(self.root, field, field == 'exclude_from_menu')
                self.root.save()
                self.assertEqual(brand_navigation(), {'brands': [], 'url': None})
                setattr(self.root, field, field != 'exclude_from_menu')
                self.root.save()

    def test_empty_and_missing_root(self):
        self.root.get_descendants().delete()
        with self.assertNumQueries(1):
            menu = brand_navigation()
        self.assertEqual(menu, {'brands': [], 'url': self.root.get_absolute_url()})
        html = render_to_string('oscar/partials/home/brand_navigation.html', {'brand_menu': menu})
        self.assertIn('No brands available yet.', html)
        self.root.delete()
        with self.assertNumQueries(1):
            self.assertEqual(brand_navigation(), {'brands': [], 'url': None})

    def test_public_variants_can_supply_parent_gender(self):
        parent = Product.objects.create(title='Parent', product_class=self.watch, structure=Product.PARENT)
        parent.categories.add(self.empty)
        ProductImage.objects.create(product=parent, original='products/parent.jpg')
        child = Product.objects.create(title='Variant', parent=parent, structure=Product.CHILD)
        ProductImage.objects.create(product=child, original='products/child.jpg')
        AttributeValue.objects.create(product=child, attribute=self.gender, value_text='Women')
        self.assertIn(parent, gender_products('women'))
        self.assertNotIn(child, gender_products('women'))
        self.assertEqual([g['name'] for g in self.menu()['Empty']['genders']], ['Women'])
        child.is_public = False
        child.save()
        self.assertNotIn(parent, gender_products('women'))
        self.assertEqual(self.menu()['Empty']['genders'], [])

    def test_header_preserves_links_and_loads_component_css(self):
        response = self.client.get('/')
        self.assertContains(response, 'data-brands-menu', count=2)
        self.assertContains(response, '>Shop</a>', count=2)
        self.assertContains(response, '>Home</a>', count=2)
        self.assertContains(response, '/static/abdeen/css/brands-navigation.css')
        self.assertContains(response, f'href="{reverse("catalogue:index")}"')


class BrandGenderRouteTests(BrandCatalogueFixtures, TestCase):
    def setUp(self):
        self.assertNotEqual(Path(settings.HAYSTACK_CONNECTIONS['default']['PATH']),
                            settings.BASE_DIR / 'var' / 'whoosh_index')
        call_command('rebuild_index', interactive=False, verbosity=0, stdout=StringIO())

    def result_ids(self, response):
        self.assertEqual(response.status_code, 200)
        return {int(result.pk) for result in response.context['products']}

    def test_brand_gender_intersection_includes_collections_not_other_brands(self):
        url = self.both.get_absolute_url()
        self.assertEqual(self.result_ids(self.client.get(url, {'gender': 'men'})),
                         {self.mens_watch.pk, self.sold_out.pk})
        self.assertEqual(self.result_ids(self.client.get(url, {'gender': 'women'})), {self.womens_watch.pk})
        self.assertEqual(self.result_ids(self.client.get(url)),
                         {self.mens_watch.pk, self.womens_watch.pk, self.sold_out.pk})

    def test_text_search_cannot_escape_brand_or_gender(self):
        self.assertEqual(self.result_ids(self.client.get(self.both.get_absolute_url(),
                         {'gender': 'men', 'q': 'Needle'})), {self.mens_watch.pk, self.sold_out.pk})

    def test_private_imageless_placeholder_accessory_and_empty_results(self):
        for category in (self.male, self.empty):
            self.assertEqual(self.result_ids(self.client.get(category.get_absolute_url(), {'gender': 'women'})), set())

    def test_unknown_gender_fails_closed(self):
        self.assertEqual(self.result_ids(self.client.get(self.both.get_absolute_url(), {'gender': 'invalid'})), set())

    def test_live_gender_change_works_without_reindexing(self):
        AttributeValue.objects.filter(product=self.mens_watch).update(value_text='Women')
        self.assertEqual(self.result_ids(self.client.get(self.both.get_absolute_url(), {'gender': 'women'})),
                         {self.mens_watch.pk, self.womens_watch.pk})

    @patch('oscar.apps.search.views.base.BaseSearchView.paginate_by', 1)
    def test_sort_and_pagination_keep_gender_filter(self):
        params = {'gender': 'men', 'sort_by': 'title-asc'}
        first = self.client.get(self.both.get_absolute_url(), params)
        self.assertEqual(first.context['paginator'].count, 2)
        self.assertEqual(self.result_ids(first), {self.mens_watch.pk})
        self.assertContains(first, 'name="gender" value="men"')
        self.assertContains(first, 'gender=men&amp;sort_by=title-asc&amp;page=2')
        second = self.client.get(self.both.get_absolute_url(), {**params, 'page': 2})
        self.assertEqual(self.result_ids(second), {self.sold_out.pk})
        self.assertContains(second, 'Zulu — Men')
        self.assertContains(second, 'View all Zulu')

    def test_sold_out_stays_unavailable(self):
        response = self.client.get(self.both.get_absolute_url(), {'gender': 'men'})
        self.assertIn(self.sold_out.pk, self.result_ids(response))
        strategy = get_class('partner.strategy', 'Selector')().strategy()
        self.assertFalse(strategy.fetch_for_product(self.sold_out).availability.is_available_to_buy)
        self.sold_out.stockrecords.get().refresh_from_db()
        self.assertFalse(self.sold_out.stockrecords.get().is_available)

    def test_shop_is_unchanged_by_gender_parameter(self):
        url = reverse('catalogue:index')
        self.assertEqual(self.result_ids(self.client.get(url)), self.result_ids(self.client.get(url, {'gender': 'men'})))
