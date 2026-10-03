"""Browse-template integration, independent of the development search backend."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from django.contrib.auth.models import AnonymousUser
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse
from haystack.backends.simple_backend import SimpleSearchBackend
from oscar.core.loading import get_class, get_model
from catalogue_import.templatetags.storefront_tags import card_currency as currency

from catalogue_import.templatetags.storefront_tags import catalogue_sorting_available

Product = get_model('catalogue', 'Product')
Category = get_model('catalogue', 'Category')
ProductClass = get_model('catalogue', 'ProductClass')
ProductImage = get_model('catalogue', 'ProductImage')
Partner = get_model('partner', 'Partner')
StockRecord = get_model('partner', 'StockRecord')
Selector = get_class('partner.strategy', 'Selector')
BrowseCategoryForm = get_class('search.forms', 'BrowseCategoryForm')
base_sqs = get_class('search.facets', 'base_sqs')


class CataloguePresentationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.product_class = ProductClass.objects.create(name='Watches', track_stock=True)
        cls.partner = Partner.objects.create(name='Supplier')
        cls.root = Category.add_root(name='Brands', slug='brands')
        cls.category = cls.root.add_child(name='Real brand', slug='real-brand')
        cls.product = Product.objects.create(title='Real watch with a complete untruncated model title', product_class=cls.product_class)
        cls.product.categories.add(cls.category)
        cls.stock = StockRecord.objects.create(product=cls.product, partner=cls.partner, partner_sku='WATCH-1', price_currency='JOD', price=Decimal('125.50'), num_in_stock=4)
        ProductImage.objects.create(product=cls.product, original='products/real-watch.jpg')

    def context(self, query='', products=None, page=1):
        request = RequestFactory().get('/catalogue/' + query)
        request.user = AnonymousUser()
        request.session = {}
        request.strategy = Selector().strategy(request=request, user=request.user)
        request.basket = get_model('basket', 'Basket')()
        request.basket.strategy = request.strategy
        results = [SimpleNamespace(object=p) for p in (products if products is not None else [self.product])]
        paginator = Paginator(results, 1)
        current = paginator.page(page)
        form = BrowseCategoryForm(request.GET, searchqueryset=base_sqs())
        return {'request': request, 'user': request.user, 'form': form, 'products': current.object_list, 'paginator': paginator, 'page_obj': current, 'selected_facets': request.GET.getlist('selected_facets'), 'summary': 'All products'}

    def render(self, context, template='oscar/catalogue/browse.html'):
        return render_to_string(template, context, request=context['request'])

    def test_real_card_links_to_product_with_compact_details(self):
        html = self.render(self.context())
        self.assertIn(self.product.get_title(), html)
        self.assertIn(self.product.get_absolute_url(), html)
        self.assertIn('/media/products/real-watch.jpg', html)
        self.assertIn(str(currency(Decimal('125.50'), 'JOD')), html)
        self.assertIn('In stock', html)
        self.assertNotIn(reverse('basket:add', kwargs={'pk': self.product.pk}), html)
        self.assertIn('class="abdeen-product-link"', html)
        self.assertIn('class="abdeen-product-brand">Real brand', html)
        self.assertIn('abdeen-header', html)
        self.assertIn('abdeen-footer', html)
        self.assertIn('href="/#brands"', html)
        self.assertIn('id="id_sort_by"', html)

    def test_missing_image_and_unavailable_stock(self):
        self.product.images.all().delete()
        self.stock.num_in_stock = 0
        self.stock.save()
        html = self.render(self.context())
        self.assertIn('/static/abdeen/images/watch-placeholder.svg', html)
        self.assertNotIn('src=""', html)
        self.assertIn('Out of stock', html)
        self.assertIn('Sold out', html)
        self.assertNotIn(reverse('basket:add', kwargs={'pk': self.product.pk}), html)

    def test_card_currency_keeps_decimal_values_and_foreign_currency(self):
        from oscar.templatetags.currency_filters import currency as oscar_currency

        for amount, expected in [('102.000', '102 JOD'), ('125.500', '125.5 JOD'),
                                 ('0.001', '0.001 JOD'), ('0', '0 JOD')]:
            self.assertEqual(currency(Decimal(amount), 'JOD'), expected)
        self.assertEqual(currency(Decimal('125.50'), 'USD'),
                         oscar_currency(Decimal('125.50'), 'USD'))

    def test_parent_options_use_oscar_child_price(self):
        parent = Product.objects.create(title='Variant family', product_class=self.product_class, structure=Product.PARENT)
        child = Product.objects.create(title='Variant', parent=parent, structure=Product.CHILD)
        StockRecord.objects.create(product=child, partner=self.partner, partner_sku='VARIANT', price_currency='JOD', price=Decimal('210'), num_in_stock=3)
        html = self.render(self.context(products=[parent]))
        self.assertIn(str(currency(Decimal('210'), 'JOD')), html)
        self.assertIn('Choose options', html)
        self.assertNotIn(reverse('basket:add', kwargs={'pk': parent.pk}), html)

    def test_pagination_preserves_query_sort_and_multiple_facets(self):
        context = self.context('?q=watch&sort_by=price-asc&selected_facets=brand:one&selected_facets=brand:two', products=[self.product] * 3, page=2)
        html = self.render(context)
        self.assertIn('name="q" value="watch"', html)
        self.assertIn('Page 2 of 3', html)
        for number in (1, 3):
            self.assertIn(f'q=watch&amp;sort_by=price-asc&amp;selected_facets=brand%3Aone&amp;selected_facets=brand%3Atwo&amp;page={number}', html)
        self.assertIn('rel="prev"', html)
        self.assertNotIn('tabindex="-1">Previous', html)

    def test_category_breadcrumbs_descriptions_and_real_navigation(self):
        self.category.description = '<p>Actual category description</p>'
        self.category.long_description = '<p>More about this collection</p>'
        context = self.context()
        context['category'] = self.category
        html = self.render(context, 'oscar/catalogue/category.html')
        self.assertIn('aria-current="page">Real brand', html)
        self.assertIn(self.root.get_absolute_url(), html)
        self.assertIn('Actual category description', html)
        self.assertIn('More about this collection', html)
        self.assertIn('abdeen-product-card', html)
        footer = html.split('<footer', 1)[1]
        self.assertIn(self.category.get_absolute_url(), footer)

    def test_empty_state_and_no_invented_facets(self):
        html = self.render(self.context(products=[]))
        self.assertIn('No products found.', html)
        self.assertNotIn('Catalogue pagination', html)
        self.assertNotIn('id="id_sort_by"', html)
        self.assertNotIn('facet_checkbox', html)

    def test_sidebar_uses_real_gender_brand_and_descendant_links(self):
        men = Category.add_root(name='Men', slug='men')
        women = Category.add_root(name='Women', slug='women')
        casio = self.root.add_child(name='Casio', slug='casio')
        gshock = casio.add_child(name='G-SHOCK', slug='g-shock')
        context = self.context()
        context['category'] = gshock
        html = self.render(context, template='oscar/catalogue/category.html')
        navigation = html.split('<nav class="abdeen-category-navigation"', 1)[1].split('</nav>', 1)[0]
        for category in (men, women, self.root, casio, gshock):
            self.assertIn(f'href="{category.get_absolute_url()}"', navigation)
        self.assertEqual(navigation.count('<h3>Gender</h3>'), 1)
        self.assertIn(f'href="{gshock.get_absolute_url()}" aria-current="page"', navigation)
        self.assertIn(f'aria-controls="shop-category-{casio.pk}"', navigation)
        self.assertIn(f'<ul id="shop-category-{casio.pk}">', navigation)
        self.assertNotIn('Show results for', html)
        self.assertIn('id="shop-by-heading">Shop by</h2>', html)

    def test_sidebar_keeps_other_real_roots_and_hides_non_menu_categories(self):
        other = Category.add_root(name='Accessories', slug='accessories')
        hidden = Category.add_root(name='Hidden collection', slug='hidden-collection', is_public=False)
        html = self.render(self.context())
        navigation = html.split('<nav class="abdeen-category-navigation"', 1)[1].split('</nav>', 1)[0]
        self.assertIn(f'href="{other.get_absolute_url()}"', navigation)
        self.assertNotIn(hidden.get_absolute_url(), navigation)
        self.assertNotIn('<h3>Gender</h3>', navigation)

    def test_mobile_navigation_has_one_shared_tree_and_real_sort_form(self):
        html = self.render(self.context('?q=watch&sort_by=price-asc'))
        self.assertEqual(html.count('class="abdeen-category-navigation"'), 1)
        self.assertIn('<dialog id="shop-navigation-drawer"', html)
        self.assertIn('aria-labelledby="shop-by-heading" data-filter-dialog', html)
        self.assertIn('aria-haspopup="dialog" aria-controls="shop-navigation-drawer"', html)
        self.assertIn('aria-label="Close shop navigation"', html)
        self.assertIn('name="q" value="watch"', html)
        self.assertIn('value="price-asc" selected', html)
        self.assertIn('oscar.search.init()', html)

    def test_cards_elsewhere_and_basket_keep_styles_isolated(self):
        self.product.images.all().delete()
        context = self.context()
        context['product'] = self.product
        html = self.render(context, 'oscar/catalogue/partials/product.html')
        self.assertIn('product_pod', html)
        self.assertNotIn('abdeen-product-card', html)
        for url in [reverse('basket:summary')]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'abdeen/css/catalogue.css')
            self.assertContains(response, 'data-home-header')
            self.assertNotContains(response, 'abdeen/css/product-detail.css')
        self.assertEqual(resolve(reverse('catalogue:index')).func.view_class, get_class('catalogue.views', 'CatalogueView'))
        self.assertEqual(self.client.get(self.category.get_absolute_url()).status_code, 200)

    def test_sorting_capability_and_real_form_rendering(self):
        context = self.context()
        self.assertTrue(catalogue_sorting_available(context['form']))
        html = self.render(context)
        self.assertIn('id="id_sort_by"', html)
        self.assertIn('value="price-asc"', html)
        self.assertIn('oscar.search.init()', html)
        context['form'].searchqueryset = Mock()
        context['form'].searchqueryset.query.backend = Mock(spec=SimpleSearchBackend)
        self.assertFalse(catalogue_sorting_available(context['form']))
        self.assertNotIn('id="id_sort_by"', self.render(context))
