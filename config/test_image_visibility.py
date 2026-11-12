from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from oscar.core.loading import get_class, get_model

from catalogue_import.visibility import with_storefront_image
from catalogue_import.recommendations import recommended_products
from config.homepage import range_products

Product = get_model('catalogue', 'Product')
ProductImage = get_model('catalogue', 'ProductImage')


class ImageVisibilityTests(TestCase):
    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=self.directory))
        pc = get_model('catalogue', 'ProductClass').objects.create(name='Watch')
        partner = get_model('partner', 'Partner').objects.create(name='Supplier')
        self.category = get_model('catalogue', 'Category').add_root(name='Men')
        root = get_model('catalogue', 'Category').add_root(name='Brands', slug='brands')
        self.brand = root.add_child(name='Brand')
        self.products = []
        for index in range(3):
            p = Product.objects.create(title=f'Visibility needle {index}', upc=f'VISIBLE-{index}', product_class=pc)
            p.categories.add(self.category, self.brand)
            get_model('partner', 'StockRecord').objects.create(product=p, partner=partner, partner_sku=p.upc,
                price='42', regular_price='60', price_currency='JOD', availability_only=True,
                is_available=False, num_in_stock=None, num_allocated=0)
            self.products.append(p)
        self.visible, self.hidden, self.placeholder = self.products
        self.image = self.add_image(self.visible)
        ProductImage.objects.create(product=self.placeholder, original='abdeen/images/watch-placeholder.svg')
        self.range = get_model('offer', 'Range').objects.create(name='Best Sellers', is_public=True)
        for p in self.products:
            self.range.add_product(p)
        self.staff = get_user_model().objects.create_superuser('image-admin','image-admin@example.test','temporary-pass')
        self.rebuild()

    def png(self):
        stream = BytesIO(); Image.new('RGB', (10, 10), 'blue').save(stream, 'PNG')
        return SimpleUploadedFile('real-watch.png', stream.getvalue(), content_type='image/png')

    def add_image(self, product):
        return ProductImage.objects.create(product=product, original=self.png())

    def rebuild(self):
        call_command('rebuild_index', interactive=False, verbosity=0, stdout=StringIO())

    def test_live_query_uses_real_rows_never_placeholder_or_blank_and_no_duplicates(self):
        ProductImage.objects.create(product=self.hidden, original='')
        self.add_image(self.visible)
        self.assertEqual(list(with_storefront_image(Product.objects.all())), [self.visible])
        self.assertEqual(Product.objects.count(), 3)

    def test_direct_urls_hide_missing_images_even_before_slug_redirect(self):
        self.assertEqual(self.client.get(self.visible.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(f'/catalogue/wrong_{self.hidden.pk}/').status_code, 404)
        self.assertEqual(self.client.get(self.placeholder.get_absolute_url()).status_code, 404)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 404)

    def test_shop_search_category_brand_and_range_filter_before_pagination(self):
        urls = [reverse('catalogue:index'), reverse('search:search')+'?q=needle',
                self.category.get_absolute_url(), self.brand.get_absolute_url(),
                reverse('catalogue:range', kwargs={'slug':self.range.slug})]
        # Oscar's range route is installed by the root Shop, not CatalogueConfig
        # in all versions; use the actual resolver name below if needed.
        for url in urls:
            response = self.client.get(url)
            self.assertContains(response, self.visible.title)
            self.assertNotContains(response, self.hidden.title)
            self.assertNotContains(response, self.placeholder.title)
            self.assertEqual(response.context['paginator'].count, 1)

    def test_homepage_recommendations_and_recent_cards(self):
        self.assertEqual(range_products('Best Sellers'), [self.visible])
        response = self.client.get('/')
        self.assertContains(response, self.visible.title)
        self.assertNotContains(response, self.hidden.title)
        strategy = get_class('partner.strategy', 'Selector')().strategy()
        self.assertEqual(recommended_products(self.hidden, strategy), [self.visible])
        from catalogue_import.templatetags.recommendation_tags import prepare_recent_cards
        self.assertEqual(prepare_recent_cards(self.products), [self.visible])

    def test_last_image_removal_hides_immediately_even_with_stale_index(self):
        self.image.delete()
        self.assertEqual(self.client.get(self.visible.get_absolute_url()).status_code, 404)
        response = self.client.get(reverse('search:search')+'?q=needle')
        self.assertNotContains(response, self.visible.title)
        self.assertEqual(range_products('Best Sellers'), [])

    def test_first_image_addition_visible_without_bulk_rebuild(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.add_image(self.hidden)
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 200)
        self.assertContains(self.client.get(reverse('search:search')+'?q=needle'), self.hidden.title)
        self.assertFalse(self.hidden.stockrecords.get().is_available)

    def test_removing_one_of_multiple_images_does_not_hide(self):
        self.add_image(self.visible)
        self.image.delete()
        self.assertEqual(self.client.get(self.visible.get_absolute_url()).status_code, 200)

    def test_first_image_indexes_new_dashboard_product_after_commit(self):
        product = Product.objects.create(title='Fresh unique upload', upc='FRESH', product_class=self.visible.product_class)
        product.categories.add(self.category, self.brand)
        get_model('partner', 'StockRecord').objects.create(product=product, partner=self.visible.stockrecords.get().partner,
            partner_sku='FRESH', price='42', price_currency='JOD', availability_only=True,
            is_available=False, num_in_stock=None, num_allocated=0)
        self.assertNotContains(self.client.get(reverse('search:search')+'?q=Fresh'), product.title)
        self.dashboard_post(product, upload=True)
        self.assertContains(self.client.get(reverse('search:search')+'?q=Fresh'), product.title)

    def test_private_product_stays_private_when_image_is_added(self):
        self.hidden.is_public = False
        self.hidden.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.add_image(self.hidden)
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse('search:search')+'?q=needle'), self.hidden.title)

    def dashboard_post(self, product, upload=False, remove=False):
        self.client.force_login(self.staff)
        url = reverse('dashboard:catalogue-product', kwargs={'pk':product.pk})
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        data = {}; forms = [page.context['form']]
        for name in page.context['view'].formsets:
            fs = page.context[name]; forms.extend([fs.management_form, *fs.initial_forms])
        for form in forms:
            for field in form:
                value = field.value()
                if value is not False:
                    data[field.html_name] = 'on' if value is True else (value if value is not None else '')
        for name in page.context['view'].formsets:
            fs = page.context[name]
            data[f'{fs.prefix}-TOTAL_FORMS'] = str(fs.initial_form_count())
            if fs.model is ProductImage:
                if upload:
                    data[f'{fs.prefix}-TOTAL_FORMS'] = '1'
                    data[f'{fs.prefix}-0-original'] = self.png()
                    data[f'{fs.prefix}-0-display_order'] = '0'
                if remove:
                    data[f'{fs.prefix}-0-DELETE'] = 'on'
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(url, data)
        if result.status_code != 302:
            self.fail(str({name: str(result.context[name].errors) + str(result.context[name].non_form_errors())
                           for name in page.context['view'].formsets}))

    def test_dashboard_lists_hidden_products_and_first_upload_last_delete_toggle(self):
        self.client.force_login(self.staff)
        page = self.client.get(reverse('dashboard:catalogue-product-list'))
        self.assertContains(page, self.hidden.title)
        self.dashboard_post(self.hidden, upload=True)
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 200)
        self.assertFalse(self.hidden.stockrecords.get().is_available)
        self.dashboard_post(self.hidden, remove=True)
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 404)
        self.assertEqual(Product.objects.count(), 3)

    def test_no_stock_enabled_and_spelling_suggestions_cannot_leak_titles(self):
        self.add_image(self.hidden)
        self.assertEqual(get_model('partner','StockRecord').objects.filter(is_available=True).count(), 0)
        self.assertIsNone(get_class('search.forms','SearchForm')().get_suggestion())
