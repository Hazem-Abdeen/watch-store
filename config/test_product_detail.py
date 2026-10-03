"""Product detail presentation and Oscar's unchanged purchase/review flows."""
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from oscar.core.loading import get_class, get_model
from oscar.templatetags.currency_filters import currency
from PIL import Image
from catalogue_import.models import CatalogueSource

Product = get_model('catalogue', 'Product')
ProductClass = get_model('catalogue', 'ProductClass')
ProductImage = get_model('catalogue', 'ProductImage')
Attribute = get_model('catalogue', 'ProductAttribute')
AttributeValue = get_model('catalogue', 'ProductAttributeValue')
Category = get_model('catalogue', 'Category')
Partner = get_model('partner', 'Partner')
StockRecord = get_model('partner', 'StockRecord')
BasketLine = get_model('basket', 'Line')
Review = get_model('reviews', 'ProductReview')
WishlistLine = get_model('wishlists', 'Line')


class ProductDetailTests(TestCase):
    @classmethod
    def setUpClass(cls):
        media_root = cls.enterClassContext(TemporaryDirectory(prefix='abdeen-detail-test-media-'))
        cls.enterClassContext(override_settings(MEDIA_ROOT=media_root))
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        cls.product_class = ProductClass.objects.create(name='Watches', track_stock=True)
        cls.partner = Partner.objects.create(name='Detail test supplier')
        cls.product = Product.objects.create(title='A real watch with its full model reference',
                                            product_class=cls.product_class, upc='123456789012',
                                            description='<p>Actual watch description.</p>')
        cls.stock = StockRecord.objects.create(product=cls.product, partner=cls.partner,
                                               partner_sku='DETAIL-1', price_currency='JOD',
                                               price=Decimal('125.50'), num_in_stock=3)
        cls.category = Category.add_root(name='Watches')
        cls.product.categories.add(cls.category)
        for index, color in enumerate(['white', 'gray', 'black']):
            data = BytesIO()
            Image.new('RGB', (40, 50), color).save(data, format='JPEG')
            ProductImage.objects.create(product=cls.product, display_order=index,
                original=SimpleUploadedFile(f'watch-{index}.jpg', data.getvalue(), content_type='image/jpeg'),
                caption=f'Product view {index + 1}')
        for code, name, value in [('movement', 'Movement', 'Quartz'),
                                  ('glass', 'Glass', 'Sapphire'),
                                  ('woocommerce_id', 'WooCommerce ID', 'hidden-source-701'),
                                  ('internal_notes', 'Internal notes', 'hidden-note-123'),
                                  ('source_metadata', 'Source metadata', 'hidden-source-data'),
                                  ('old_reference', 'Migration reference', 'hidden-migration-3')]:
            attr = Attribute.objects.create(product_class=cls.product_class, name=name, code=code, type='text')
            AttributeValue.objects.create(product=cls.product, attribute=attr, value_text=value)
        cls.user = get_user_model().objects.create_user('detail-customer', email='test@example.test')

    def detail(self, product=None, client=None):
        response = (client or self.client).get((product or self.product).get_absolute_url())
        self.assertEqual(response.status_code, 200)
        return response

    def test_shared_chrome_real_gallery_price_breadcrumbs_and_metadata(self):
        response = self.detail()
        for text in ['data-home-header', 'abdeen-footer', 'abdeen/css/product-detail.css',
                     self.product.title, self.product.description, self.category.get_absolute_url(),
                     'In stock', str(currency(Decimal('125.50'), 'JOD')), 'href="/#brands"']:
            self.assertContains(response, text)
        self.assertContains(response, 'data-gallery-thumbnail', count=3)
        self.assertContains(response, 'aria-label="View image 1" aria-current="true"', count=1)
        for image in self.product.images.all():
            self.assertContains(response, image.original.url)
        self.assertIs(resolve(self.product.get_absolute_url()).func.view_class,
                      get_class('catalogue.views', 'ProductDetailView'))

    def test_product_information_hides_internal_values_without_changing_data(self):
        response = self.detail()
        for value in ['Quartz', 'Sapphire']:
            self.assertContains(response, value)
        for value in ['WooCommerce ID', 'Internal notes', 'Source metadata', 'Migration reference',
                      'hidden-source-701', 'hidden-note-123', 'hidden-source-data', 'hidden-migration-3']:
            self.assertNotContains(response, value)
        self.assertEqual(self.product.attribute_values.count(), 6)
        self.product.upc = 'wc-abdeen-701'
        self.product.save()
        self.assertNotContains(self.detail(), 'wc-abdeen-701')
        self.product.refresh_from_db()
        self.assertEqual(self.product.upc, 'wc-abdeen-701')

    def test_add_to_basket_posts_original_form_with_csrf_and_quantity(self):
        client = Client(enforce_csrf_checks=True)
        response = self.detail(client=client)
        self.assertContains(response, 'id="add_to_basket_form"')
        self.assertContains(response, 'name="quantity"')
        result = client.post(reverse('basket:add', kwargs={'pk': self.product.pk}),
                             {'quantity': 2, 'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
        self.assertEqual(result.status_code, 302)
        line = BasketLine.objects.get(product=self.product)
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.stockrecord, self.stock)
        self.assertEqual(line.price_currency, 'JOD')
        self.assertEqual(line.price_excl_tax, Decimal('125.50'))

    def test_options_and_validation_are_still_oscar_forms(self):
        option = get_model('catalogue', 'Option').objects.create(name='Engraving', code='engraving', type='text', required=True)
        self.product.product_options.add(option)
        self.assertContains(self.detail(), 'name="engraving"')
        response = self.client.post(reverse('basket:add', kwargs={'pk': self.product.pk}), {'quantity': 1}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BasketLine.objects.exists())
        self.assertContains(response, 'This field is required')
        response = self.client.post(reverse('basket:add', kwargs={'pk': self.product.pk}),
                                    {'quantity': 1, 'engraving': 'A real option'})
        self.assertEqual(response.status_code, 302)
        line = BasketLine.objects.get(product=self.product)
        self.assertEqual(line.attributes.get(option=option).value, 'A real option')

    def test_unavailable_product_retains_stock_alert_and_cannot_be_purchased(self):
        self.stock.num_in_stock = 0
        self.stock.save()
        response = self.detail()
        self.assertContains(response, 'Out of stock')
        self.assertContains(response, 'id="alert_form"')
        self.assertContains(response, reverse('customer:alert-create', kwargs={'pk': self.product.pk}))
        self.assertNotContains(response, 'id="add_to_basket_form"')
        self.client.post(reverse('basket:add', kwargs={'pk': self.product.pk}), {'quantity': 1})
        self.assertFalse(BasketLine.objects.exists())

    def test_no_stock_or_image_uses_no_fabricated_price_or_image(self):
        # Don't delete shared fixture image files used by later test methods.
        self.product = Product.objects.create(title='Watch without a stock record',
                                              product_class=self.product_class)
        response = self.detail()
        self.assertContains(response, 'Unavailable')
        self.assertContains(response, '/static/abdeen/images/watch-placeholder.svg')
        self.assertNotContains(response, 'src=""')
        self.assertNotContains(response, 'data-gallery-thumbnail')
        self.assertNotContains(response, str(currency(Decimal('125.50'), 'JOD')))

    def test_parent_links_only_to_public_available_variants_and_child_form_works(self):
        parent = Product.objects.create(title='Watch family', structure=Product.PARENT, product_class=self.product_class)
        child = Product.objects.create(title='Silver option', structure=Product.CHILD, parent=parent)
        private = Product.objects.create(title='Hidden option', structure=Product.CHILD, parent=parent, is_public=False)
        for variant in [child, private]:
            StockRecord.objects.create(product=variant, partner=self.partner, partner_sku=f'VAR-{variant.pk}',
                                       price_currency='JOD', price=Decimal('210'), num_in_stock=2)
        response = self.detail(parent)
        self.assertContains(response, child.get_absolute_url())
        self.assertNotContains(response, private.get_absolute_url())
        self.assertNotContains(response, 'id="add_to_basket_form"')
        self.assertContains(self.detail(child), 'id="add_to_basket_form"')
        self.client.post(reverse('basket:add', kwargs={'pk': child.pk}), {'quantity': 1, 'child_id': child.pk})
        self.assertTrue(BasketLine.objects.filter(product=child).exists())

    @override_settings(ABDEEN_STOREFRONT_HIDDEN_FEATURES=())
    def test_wishlist_add_remove_and_existing_list_dropdown(self):
        self.client.force_login(self.user)
        self.assertContains(self.detail(), 'id="add_to_wishlist_form"')
        response = self.client.post(reverse('customer:wishlists-add-product', kwargs={'product_pk': self.product.pk}))
        self.assertEqual(response.status_code, 302)
        line = WishlistLine.objects.get(product=self.product)
        self.assertEqual(line.wishlist.owner, self.user)
        self.assertContains(self.detail(), 'dropdown-toggle')
        response = self.client.post(reverse('customer:wishlists-remove-product', kwargs={
            'key': line.wishlist.key, 'product_pk': self.product.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(WishlistLine.objects.filter(product=self.product).exists())

    @override_settings(ABDEEN_STOREFRONT_HIDDEN_FEATURES=())
    def test_review_submission_and_approved_review_rendering(self):
        self.client.force_login(self.user)
        url = reverse('catalogue:reviews-add', kwargs={'product_slug': self.product.slug, 'product_pk': self.product.pk})
        self.assertContains(self.detail(), url)
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {'title': 'Actual customer review', 'body': 'A detailed review from a customer.', 'score': 4})
        self.assertEqual(response.status_code, 302)
        review = Review.objects.get(product=self.product, user=self.user)
        review.status = Review.APPROVED
        review.save()
        self.assertContains(self.detail(), review.title)
        self.assertContains(self.detail(), review.body)

    @override_settings(OSCAR_HIDDEN_FEATURES=['reviews', 'wishlists'])
    def test_disabled_features_stay_disabled(self):
        response = self.detail()
        self.assertNotContains(response, 'id="write_review"')
        self.assertNotContains(response, 'btn-wishlist')
        self.assertNotContains(response, 'Customer Reviews')

    def test_other_pages_do_not_load_detail_styles(self):
        for url in [reverse('catalogue:index'), self.category.get_absolute_url(), reverse('basket:summary'), '/']:
            self.assertNotContains(self.client.get(url), 'abdeen/css/product-detail.css')
        self.assertEqual(self.client.get(reverse('checkout:index')).status_code, 302)

    def test_customer_ui_hides_features_stock_counts_and_price_breakdown(self):
        for logged_in in (False, True):
            if logged_in:
                self.client.force_login(self.user)
            for url in (self.product.get_absolute_url(), '/', reverse('catalogue:index'),
                        reverse('basket:summary'), reverse('customer:profile-view')):
                response = self.client.get(url, follow=True)
                for text in ('3 available', 'Add to wish list', 'wishlists/', 'star-rating',
                             'Write a review', 'Customer Reviews', 'does not have any reviews',
                             'Price &amp; availability details', 'Edit this product'):
                    self.assertNotContains(response, text)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.num_in_stock, 3)
        self.assertEqual(self.stock.num_allocated, None)

    def test_hidden_feature_urls_keep_backend_but_hide_forms(self):
        self.client.force_login(self.user)
        for url in (reverse('customer:wishlists-list'), reverse('catalogue:reviews-add', kwargs={
                'product_slug': self.product.slug, 'product_pk': self.product.pk})):
            response = self.client.get(url)
            self.assertContains(response, 'This feature is currently unavailable.')
            self.assertNotContains(response, 'name="score"')
            self.assertNotContains(response, 'Create a new wish list')
        response = self.client.post(reverse('customer:wishlists-add-product', kwargs={
            'product_pk': self.product.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(WishlistLine.objects.filter(product=self.product).exists())

    def test_staff_edit_link_remains_staff_only(self):
        self.client.force_login(self.user)
        self.assertNotContains(self.detail(), 'Edit this product')
        self.user.is_staff = True
        self.user.save()
        self.assertContains(self.detail(), 'Edit this product')
        self.user.is_superuser = True
        self.user.save()
        self.assertContains(self.detail(), 'Edit this product')
        self.assertEqual(self.client.get(reverse('dashboard:catalogue-product',
                                               kwargs={'pk': self.product.pk})).status_code, 200)

    def test_specification_description_and_mixed_prose_are_not_duplicated(self):
        for description, prose in (
            ('', ''), ('<p>&nbsp;</p>', ''),
            ('Movement: Quartz\nGlass: Sapphire\nCase Size: 38 mm', ''),
            ('Glass: Sapphire\nCountry of Manufacture: Switzerland\nThickness: 9 mm', ''),
            ('[video width="1920" mp4="https://example.test/watch.mp4"][/video]', ''),
            ('<p>A refined everyday watch.</p><table><tr><th>Movement</th><td>Quartz</td></tr>'
             '<tr><th>Case Diameter</th><td>38 mm</td></tr></table>', 'A refined everyday watch.'),
            ('A refined everyday watch.\nMovement: Quartz\nMigration ID: hidden-migration',
             'A refined everyday watch.'),
        ):
            with self.subTest(description=description):
                self.product.description = description
                self.product.save()
                response = self.detail()
                self.assertContains(response, '<dd>Quartz</dd>', count=1)
                self.assertContains(response, '<dd>Sapphire</dd>', count=1)
                self.assertNotContains(response, 'hidden-migration')
                if prose:
                    self.assertContains(response, f'<p>{prose}</p>', count=1)
                else:
                    self.assertNotContains(response, 'id="product_description"')
                self.product.refresh_from_db()
                self.assertEqual(self.product.description, description)

    def test_no_empty_specifications_section(self):
        self.product.attribute_values.all().delete()
        self.product.description = ''
        self.product.save()
        response = self.detail()
        self.assertNotContains(response, 'id="product_information"')
        self.assertNotContains(response, 'href="#product_information"')

    def test_recently_viewed_uses_shared_card_and_real_history(self):
        other = Product.objects.create(title='Another watch', product_class=self.product_class)
        self.detail(other)
        response = self.detail()
        self.assertContains(response, 'abdeen-recently-viewed')
        self.assertContains(response, 'abdeen-product-card', count=1)
        self.assertContains(response, other.get_absolute_url())
        self.assertNotContains(response, 'product_pod')
        self.assertNotContains(response, 'star-rating')
        self.assertContains(response, 'id="add_to_basket_form"', count=1)

    def test_excess_stock_is_rejected_without_exposing_limit(self):
        response = self.client.post(reverse('basket:add', kwargs={'pk': self.product.pk}),
                                    {'quantity': 4}, follow=True)
        self.assertFalse(BasketLine.objects.exists())
        self.assertContains(response, 'the requested quantity is not available')
        self.assertNotContains(response, 'a maximum of 3')
        self.assertNotContains(response, '3 available')
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.num_in_stock, 3)

    def test_summary_order_real_brand_sku_shipping_and_guarantee(self):
        for code, value in [('brand', 'LOTUS'), ('guarantee', 'Two Years (International)')]:
            attr = Attribute.objects.create(product_class=self.product_class, code=code, name=code.title())
            AttributeValue.objects.create(product=self.product, attribute=attr, value_text=value)
        # An assigned brand category must not replace the real Brand attribute.
        root = Category.add_root(name='Brands', slug='brands')
        self.product.categories.add(root.add_child(name='Other brand'))
        response = self.detail()
        summary = response.content.decode().split('class="product_main abdeen-detail-summary">')[1].split('</h1>', 1)
        self.assertIn('LOTUS', summary[0])
        self.assertNotIn('Other brand', summary[0])
        self.assertContains(response, '<dd>Two Years (International)</dd>', count=1)
        self.assertContains(response, 'id="specifications-toggle" aria-controls="product-specifications"')
        self.assertNotContains(response, 'Product Details')
        body = summary[1]
        positions = [body.index(text) for text in ('DETAIL-1', '125.5 JOD',
            'Shipping calculated at checkout.', 'In stock, ready to ship', 'id="add_to_basket_form"', 'data-detail-quantity')]
        self.assertEqual(positions, sorted(positions))
        self.assertNotContains(response, 'Tax included')
        self.assertNotContains(response, '123456789012')
        self.assertContains(response, 'type="number" name="quantity"')
        self.assertNotContains(response, 'max="3"')

    def test_missing_or_internal_partner_skus_are_hidden(self):
        self.product.upc = 'wc-abdeen-701'
        self.product.save()
        for sku in ('', 'ABDEEN-701', 'wc-abdeen-701', 'woocommerce-701', 'import-701', 'migration-701'):
            with self.subTest(sku=sku):
                self.stock.partner_sku = sku
                self.stock.save()
                response = self.detail()
                self.assertNotContains(response, 'class="abdeen-detail-sku"')
                self.assertNotContains(response, 'wc-abdeen-701')
        self.stock.partner_sku = '18895/1'
        self.stock.save()
        self.assertContains(self.detail(), 'SKU: <span>18895/1</span>')

    def test_imported_stock_status_never_claims_exact_inventory(self):
        CatalogueSource.objects.create(source='abdeenwatches.com', source_id=701,
                                       product=self.product, stockrecord=self.stock,
                                       metadata={'stock_status': 'instock'})
        for quantity in (1, 2, 3, 0):
            with self.subTest(quantity=quantity):
                self.stock.num_in_stock = quantity
                self.stock.save()
                response = self.detail()
                self.assertContains(response, 'In stock, ready to ship' if quantity else 'Out of stock')
                self.assertNotContains(response, 'item left')
                self.assertNotContains(response, 'items left')
                self.assertNotContains(response, 'Low stock')
                self.stock.refresh_from_db()
                self.assertEqual(self.stock.num_in_stock, quantity)
        # Allocation, not raw stock, controls Oscar's decision.
        self.stock.num_in_stock = self.stock.num_allocated = 3
        self.stock.save()
        self.assertContains(self.detail(), 'Out of stock')

    def test_quantity_errors_and_existing_basket_limits_are_preserved(self):
        url = reverse('basket:add', kwargs={'pk': self.product.pk})
        for quantity in ('0', '-1', '1.5', 'invalid'):
            response = self.client.post(url, {'quantity': quantity}, follow=True,
                                        HTTP_REFERER='http://testserver' + self.product.get_absolute_url())
            self.assertFalse(BasketLine.objects.exists())
            self.assertContains(response, 'error-block')
        self.client.post(url, {'quantity': 2})
        response = self.client.post(url, {'quantity': 2}, follow=True,
                                    HTTP_REFERER='http://testserver' + self.product.get_absolute_url())
        self.assertEqual(BasketLine.objects.get(product=self.product).quantity, 2)
        self.assertContains(response, 'the requested quantity is not available')
        self.assertContains(response, 'value="2"')
        self.assertNotContains(response, 'a maximum of 3')

    def test_missing_guarantee_does_not_invent_one(self):
        self.assertNotContains(self.detail(), '<dt>Guarantee</dt>')
