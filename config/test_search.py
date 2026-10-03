"""Exercise Oscar's real views against a disposable, populated Whoosh index."""
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from haystack import connections
from haystack.query import SearchQuerySet
from oscar.core.loading import get_class, get_model
from catalogue_import.templatetags.storefront_tags import card_currency as currency
from PIL import Image

Product = get_model('catalogue', 'Product')
ProductClass = get_model('catalogue', 'ProductClass')
Category = get_model('catalogue', 'Category')
Partner = get_model('partner', 'Partner')
StockRecord = get_model('partner', 'StockRecord')
ProductImage = get_model('catalogue', 'ProductImage')
base_sqs = get_class('search.facets', 'base_sqs')


class IndexedCatalogueTests(TestCase):
    @classmethod
    def setUpClass(cls):
        media_root = cls.enterClassContext(TemporaryDirectory(prefix='abdeen-search-test-media-'))
        cls.enterClassContext(override_settings(MEDIA_ROOT=media_root))
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        watches = ProductClass.objects.create(name='Watches', track_stock=True)
        accessories = ProductClass.objects.create(name='Accessories', track_stock=True)
        partner = Partner.objects.create(name='Search test supplier')
        cls.category = Category.add_root(name='Collection')
        cls.subcategory = cls.category.add_child(name='Classic')
        cls.other_category = Category.add_root(name='Other')
        cls.empty_category = Category.add_root(name='Empty')
        cls.products = []

        def stock(product, price, quantity=3):
            StockRecord.objects.create(product=product, partner=partner,
                                       partner_sku=f'SEARCH-{product.pk}',
                                       price_currency='JOD', price=Decimal(price),
                                       num_in_stock=quantity)

        for number in range(25):
            title = f'Needle watch {number:02}' if number < 2 else f'Studio watch {number:02}'
            product = Product.objects.create(title=title, product_class=watches)
            product.categories.add(cls.subcategory if number % 2 == 0 else cls.category)
            stock(product, str(30 + number), quantity=0 if number == 24 else 3)
            cls.products.append(product)
        image_bytes = BytesIO()
        Image.new('RGB', (4, 4)).save(image_bytes, format='JPEG')
        cls.image = ProductImage.objects.create(product=cls.products[0], original=SimpleUploadedFile(
            'search-watch.jpg', image_bytes.getvalue(), content_type='image/jpeg',
        ))
        cls.outside = Product.objects.create(title='Outside accessory', product_class=accessories)
        cls.outside.categories.add(cls.other_category)
        stock(cls.outside, '125.50')
        cls.parent = Product.objects.create(title='Variant family', structure=Product.PARENT, product_class=watches)
        cls.parent.categories.add(cls.category)
        cls.child = Product.objects.create(title='Private-to-listings variant', structure=Product.CHILD, parent=cls.parent)
        stock(cls.child, '210')
        cls.hidden = Product.objects.create(title='Hidden watch', is_public=False, product_class=watches)
        stock(cls.hidden, '999')

    def setUp(self):
        # Refuse to clear an index unless Django's test runner isolated it.
        self.assertNotEqual(Path(settings.HAYSTACK_CONNECTIONS['default']['PATH']),
                            settings.BASE_DIR / 'var' / 'whoosh_index')
        call_command('rebuild_index', interactive=False, verbosity=0, stdout=StringIO())
        self.addCleanup(connections['default'].get_backend().clear)

    def result_ids(self, response):
        self.assertEqual(response.status_code, 200)
        return [int(result.pk) for result in response.context['products']]

    def test_index_and_catalogue_include_only_browsable_products(self):
        expected = set(Product.objects.browsable().values_list('pk', flat=True))
        self.assertEqual(len(expected), 27)
        self.assertEqual(SearchQuerySet().all().count(), len(expected))
        self.assertEqual({int(p.pk) for p in base_sqs()}, expected)
        response = self.client.get(reverse('catalogue:index'))
        self.assertEqual(response.context['paginator'].count, 27)
        self.assertEqual(len(self.result_ids(response)), settings.OSCAR_PRODUCTS_PER_PAGE)
        self.assertContains(response, 'abdeen-product-card')
        self.assertContains(response, 'abdeen-header')
        self.assertContains(response, 'id="id_sort_by"')

    def test_category_membership_includes_descendants_and_empty_category(self):
        for category in [self.category, self.subcategory, self.other_category, self.empty_category]:
            with self.subTest(category=category.name):
                expected = set(Product.objects.browsable().filter(
                    categories__in=category.get_descendants_and_self()).values_list('pk', flat=True))
                response = self.client.get(category.get_absolute_url())
                self.assertEqual(response.context['paginator'].count, len(expected))
                found = set(self.result_ids(response))
                for page in range(2, response.context['paginator'].num_pages + 1):
                    found.update(self.result_ids(self.client.get(category.get_absolute_url(), {'page': page})))
                self.assertEqual(found, expected)
                self.assertContains(response, category.name)

    def test_pagination_has_no_missing_or_duplicate_products(self):
        first = self.client.get(reverse('catalogue:index'), {'sort_by': 'price-asc'})
        second = self.client.get(reverse('catalogue:index'), {'sort_by': 'price-asc', 'page': 2})
        first_ids, second_ids = self.result_ids(first), self.result_ids(second)
        self.assertEqual(len(first_ids), 20)
        self.assertEqual(len(second_ids), 7)
        self.assertFalse(set(first_ids) & set(second_ids))
        self.assertEqual(set(first_ids + second_ids), set(Product.objects.browsable().values_list('pk', flat=True)))
        self.assertContains(first, 'sort_by=price-asc&amp;page=2')
        self.assertEqual(self.client.get(reverse('catalogue:index'), {'page': 999}).status_code, 302)

    def test_search_matches_real_titles_and_excludes_private_and_child_products(self):
        response = self.client.get(reverse('catalogue:index'), {'q': 'Needle'})
        self.assertEqual(set(self.result_ids(response)), {p.pk for p in self.products[:2]})
        response = self.client.get(reverse('search:search'), {'q': 'Needle'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual({int(r.pk) for r in response.context['results']}, {p.pk for p in self.products[:2]})
        self.assertEqual(self.result_ids(self.client.get(reverse('catalogue:index'), {'q': 'Hidden'})), [])
        self.assertEqual(self.result_ids(self.client.get(reverse('catalogue:index'), {'q': 'Private-to-listings'})), [])

    def test_sorting_and_field_facets_use_the_real_index(self):
        response = self.client.get(reverse('catalogue:index'), {'sort_by': 'price-desc'})
        ids = self.result_ids(response)
        self.assertEqual(ids[:2], [self.parent.pk, self.outside.pk])
        response = self.client.get(reverse('catalogue:index'), {'sort_by': 'title-asc'})
        titles = [p.object.title for p in response.context['products']]
        self.assertEqual(titles, sorted(titles))
        response = self.client.get(reverse('catalogue:index'), {'selected_facets': 'product_class:Accessories'})
        self.assertEqual(self.result_ids(response), [self.outside.pk])
        response = self.client.get(reverse('catalogue:index'), {'selected_facets': ['product_class:Accessories', 'product_class:Watches']})
        self.assertEqual(response.context['paginator'].count, 27)

    def test_result_cards_keep_oscar_prices_availability_images_and_links(self):
        response = self.client.get(reverse('catalogue:index'), {'q': 'Needle'})
        self.assertContains(response, self.products[0].get_absolute_url())
        self.assertContains(response, self.image.original.url)
        self.assertContains(response, str(currency(Decimal('30'), 'JOD')))
        self.assertContains(response, 'In stock')
        response = self.client.get(reverse('catalogue:index'), {'q': '"Studio watch 24"'})
        self.assertEqual(self.result_ids(response), [self.products[-1].pk])
        self.assertContains(response, 'Out of stock')
        response = self.client.get(reverse('catalogue:index'), {'q': '"Variant family"'})
        self.assertEqual(self.result_ids(response), [self.parent.pk])
        self.assertContains(response, 'Choose options')
        self.assertContains(response, str(currency(Decimal('210'), 'JOD')))

    def test_rebuild_reflects_catalogue_and_related_stock_changes(self):
        product = self.products[0]
        product.categories.set([self.other_category])
        StockRecord.objects.filter(product=product).update(price=Decimal('500'))
        self.hidden.is_public = True
        self.hidden.save()
        call_command('rebuild_index', interactive=False, verbosity=0, stdout=StringIO())
        self.assertEqual(base_sqs().count(), 28)
        response = self.client.get(self.other_category.get_absolute_url())
        self.assertEqual(set(self.result_ids(response)), {product.pk, self.outside.pk})
        response = self.client.get(reverse('catalogue:index'), {'q': 'Needle', 'sort_by': 'price-desc'})
        self.assertEqual(self.result_ids(response)[0], product.pk)
        self.assertContains(response, str(currency(Decimal('500'), 'JOD')))
