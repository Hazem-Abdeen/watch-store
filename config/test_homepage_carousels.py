"""Range pagination uses the same visibility, ordering and card rendering rules."""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from oscar.core.loading import get_model

from config.homepage import range_products


class HomepageCarouselTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        product_class = get_model('catalogue', 'ProductClass').objects.create(name='Watches')
        cls.selection = get_model('offer', 'Range').objects.create(name='Best Sellers')
        cls.products = []
        for index in range(19):
            product = get_model('catalogue', 'Product').objects.create(
                title=f'Watch {index:02}', product_class=product_class, is_public=index != 18,
            )
            if index != 17:
                get_model('catalogue', 'ProductImage').objects.create(
                    product=product, original='products/carousel-test.jpg',
                )
            cls.selection.add_product(product, display_order=19 - index)
            cls.products.append(product)

    def test_initial_eight_and_all_following_batches_in_manual_order(self):
        response = self.client.get('/')
        expected = list(reversed(self.products[:17]))
        self.assertEqual(list(response.context['best_sellers']), expected[:8])
        self.assertTrue(response.context['best_sellers_more'])
        self.assertEqual(response.context['best_sellers_count'], 17)
        self.assertContains(response, 'data-total="17"')
        self.assertContains(response, 'data-next-page="2"')
        for page, products, next_page in [(2, expected[8:16], 3), (3, expected[16:], None)]:
            payload = self.client.get('/', {'carousel': 'best-sellers', 'page': page}).json()
            self.assertEqual(payload['next_page'], next_page)
            self.assertEqual(payload['total'], 17)
            self.assertEqual(payload['html'].count('data-home-product'), len(products))
            positions = [payload['html'].index(product.get_absolute_url()) for product in products]
            self.assertEqual(positions, sorted(positions))
            self.assertNotIn('Watch 17', payload['html'])
            self.assertNotIn('Watch 18', payload['html'])
            self.assertIn('Sold out', payload['html'])
        self.assertEqual(self.client.get('/', {'carousel': 'best-sellers', 'page': 4}).json(),
                         {'html': '\n', 'next_page': None, 'total': 17})

    def test_invalid_requests_and_empty_range(self):
        for params in [{'carousel': 'unknown'}, {'carousel': 'best-sellers', 'page': 'bad'},
                       {'carousel': 'best-sellers', 'page': '0'}]:
            self.assertEqual(self.client.get('/', params).status_code, 404)
        payload = self.client.get('/', {'carousel': 'new-arrivals'}).json()
        self.assertIsNone(payload['next_page'])
        self.assertEqual(payload['total'], 0)
        self.assertNotIn('data-home-product', payload['html'])

    def test_one_and_exactly_eight_have_no_next_batch(self):
        for size in (1, 8):
            with self.subTest(size=size):
                selected = get_model('offer', 'Range').objects.create(name='New Arrivals')
                for product in self.products[:size]:
                    selected.add_product(product)
                response = self.client.get('/')
                self.assertFalse(response.context['new_arrivals_more'])
                self.assertEqual(len(response.context['new_arrivals']), size)
                self.assertEqual(response.context['new_arrivals_count'], size)
                selected.delete()

    def test_dot_total_changes_with_dashboard_memberships_and_visibility(self):
        excluded = self.products[0]
        self.selection.excluded_products.add(excluded)
        response = self.client.get('/', {'carousel': 'best-sellers'})
        self.assertEqual(response.json()['total'], 16)
        self.assertEqual(self.selection.included_products.count(), 19)
        # A newly added eligible member is counted on the next request.
        image = get_model('catalogue', 'ProductImage')
        image.objects.create(product=self.products[17], original='products/new-image.jpg')
        response = self.client.get('/', {'carousel': 'best-sellers'})
        self.assertEqual(response.json()['total'], 17)

    def test_carousel_markup_has_dots_without_arrow_buttons(self):
        response = self.client.get('/')
        self.assertContains(response, 'class="abdeen-carousel-dots"')
        self.assertNotContains(response, 'data-carousel-next')
        self.assertNotContains(response, 'data-carousel-prev')
        self.assertNotContains(response, 'Scroll to explore')

    def test_empty_ranges_keep_empty_states_without_tracks_or_controls(self):
        self.selection.included_products.clear()
        response = self.client.get('/')
        self.assertContains(response, 'Our Best Sellers selection is being prepared.')
        self.assertContains(response, 'Our New Arrivals selection is being prepared.')
        self.assertNotContains(response, 'data-carousel=')
        self.assertNotContains(response, 'class="abdeen-carousel-dots"')

    def test_out_of_range_batch_is_empty_without_large_database_offsets(self):
        response = self.client.get('/', {'carousel': 'best-sellers', 'page': '9' * 100})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'html': '\n', 'next_page': None, 'total': 17})

    def test_prefetch_query_count_does_not_grow_per_product(self):
        with CaptureQueriesContext(connection) as single:
            range_products('Best Sellers', limit=1)
        with CaptureQueriesContext(connection) as batch:
            products = range_products('Best Sellers', limit=8)
        self.assertEqual(len(single), len(batch))
        with self.assertNumQueries(0):
            for product in products:
                list(product.images.all())
                list(product.stockrecords.all())
                list(product.get_categories())
                self.assertFalse(product.has_options)

    def test_rendered_batch_has_no_per_card_queries(self):
        # Page three has one card; page one has eight. Include template/strategy queries.
        with CaptureQueriesContext(connection) as single:
            response = self.client.get('/', {'carousel': 'best-sellers', 'page': 3})
            self.assertEqual(response.status_code, 200)
        with CaptureQueriesContext(connection) as batch:
            response = self.client.get('/', {'carousel': 'best-sellers', 'page': 1})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(len(single), len(batch))
