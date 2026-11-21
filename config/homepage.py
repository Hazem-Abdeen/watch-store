"""Homepage presentation using Oscar's manually curated catalogue data."""

from django.db.models import Exists, OuterRef, Subquery
from django.http import Http404, JsonResponse
from django.template.loader import render_to_string
from django.views.generic import TemplateView
from oscar.core.loading import get_model
from homepage.models import HomeHeroSlide
from homepage.brands import BRANDS_ROOT_SLUG
from catalogue_import.visibility import with_storefront_image


PRODUCT_LIMIT = 8
CATEGORY_LIMIT = 4


def range_product_queryset(name):
    """Only explicitly selected, public standalone/parent products, in range order.

    Oscar's all_products() retains its exclusion semantics. The membership
    subquery prevents all-products/category/type rules from automatically filling
    these manually merchandised sections. No ranges or products are created.
    """
    Range = get_model('offer', 'Range')
    Product = get_model('catalogue', 'Product')
    Category = get_model('catalogue', 'Category')
    RangeProduct = get_model('offer', 'RangeProduct')
    Option = get_model('catalogue', 'Option')
    product_range = Range.objects.filter(name=name).first()
    if product_range is None:
        return Product.objects.none()

    members = RangeProduct.objects.filter(range=product_range)
    order = members.filter(product_id=OuterRef('pk')).values('display_order')[:1]
    children = with_storefront_image(Product.objects.public()).select_related(
        'parent__product_class', 'product_class',
    ).prefetch_related('stockrecords')
    products = (
        with_storefront_image(product_range.all_products().browsable())
        .filter(pk__in=members.values('product_id'))
        .annotate(
            homepage_display_order=Subquery(order),
            has_product_class_options=Exists(Option.objects.filter(productclass=OuterRef('product_class'))),
            has_product_options=Exists(Option.objects.filter(product=OuterRef('pk'))),
        )
        .order_by('homepage_display_order', 'pk')
        .select_related('product_class')
        .prefetch_related('images', 'stockrecords')
        .prefetch_public_children(queryset=children)
        .prefetch_browsable_categories(queryset=Category.objects.for_menu())
    )
    return products


def range_products(name, offset=0, limit=PRODUCT_LIMIT):
    return list(range_product_queryset(name)[offset:offset + limit])


def range_product_page(name, page=1):
    """Count eligible members for dots; render only the requested batch."""
    products = range_product_queryset(name)
    total = products.count()
    offset = (page - 1) * PRODUCT_LIMIT
    batch = list(products[offset:offset + PRODUCT_LIMIT]) if offset < total else []
    next_page = page + 1 if offset + len(batch) < total else None
    return batch, total, next_page


class HomepageView(TemplateView):
    template_name = 'oscar/home.html'

    def get(self, request, *args, **kwargs):
        if 'carousel' not in request.GET:
            return super().get(request, *args, **kwargs)
        ranges = {'best-sellers': ('Best Sellers', 'Best Seller'),
                  'new-arrivals': ('New Arrivals', 'New Arrival')}
        selection = ranges.get(request.GET['carousel'])
        try:
            page = int(request.GET.get('page', '1'))
        except ValueError:
            raise Http404 from None
        if selection is None or page < 1:
            raise Http404
        products, total, next_page = range_product_page(selection[0], page)
        html = render_to_string('oscar/partials/home/carousel_items.html', {
            'products': products, 'badge': selection[1],
        }, request=request)
        return JsonResponse({'html': html, 'next_page': next_page, 'total': total})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        Category = get_model('catalogue', 'Category')
        menu_categories = Category.objects.for_menu().order_by('path')
        brands_root = menu_categories.filter(depth=1, slug=BRANDS_ROOT_SLUG).first()
        brands = list(menu_categories.filter(
            path__startswith=brands_root.path, depth=brands_root.depth + 1,
        ).select_related('brand_presentation')) if brands_root else []
        brand_ids = {brand.pk for brand in brands}
        categories = menu_categories.filter(depth=1)
        if brands_root:
            categories = categories.exclude(pk=brands_root.pk)

        best_sellers, best_total, best_next = range_product_page('Best Sellers')
        new_arrivals, new_total, new_next = range_product_page('New Arrivals')
        context.update(
            best_sellers_more=bool(best_next), new_arrivals_more=bool(new_next),
            best_sellers_count=best_total, new_arrivals_count=new_total,
        )
        filters = {}
        for products in (best_sellers, new_arrivals):
            for product in products:
                # Transient presentation values, not new Product model fields.
                assigned = product.get_categories()
                product_brands = [category for category in assigned if category.pk in brand_ids]
                product.homepage_brand_name = ', '.join(category.name for category in product_brands)
                tokens = []
                for category in assigned:
                    if category.exclude_from_menu or (brands_root and category.pk == brands_root.pk):
                        continue
                    token = f'category-{category.pk}'
                    tokens.append(token)
                    if products is best_sellers:
                        filters[token] = category.name
                product.homepage_filter_tokens = ' '.join(tokens)

        context.update(
            hero_slides=list(HomeHeroSlide.objects.filter(is_active=True).exclude(desktop_image='')),
            homepage_categories=list(categories[:CATEGORY_LIMIT]),
            homepage_brands=brands,
            best_sellers=best_sellers,
            new_arrivals=new_arrivals,
            product_filters=[('all', 'All Picks'), *sorted(filters.items(), key=lambda item: item[1])],
        )
        return context
