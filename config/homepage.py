"""Homepage presentation using Oscar's manually curated catalogue data."""

from django.db.models import OuterRef, Subquery
from django.views.generic import TemplateView
from oscar.core.loading import get_model


PRODUCT_LIMIT = 8
CATEGORY_LIMIT = 4
BRAND_LIMIT = 8
BRANDS_ROOT_SLUG = 'brands'


def range_products(name):
    """Only explicitly selected, public standalone/parent products, in range order.

    Oscar's all_products() retains its exclusion semantics. The membership
    subquery prevents all-products/category/type rules from automatically filling
    these manually merchandised sections. No ranges or products are created.
    """
    Range = get_model('offer', 'Range')
    Product = get_model('catalogue', 'Product')
    Category = get_model('catalogue', 'Category')
    RangeProduct = get_model('offer', 'RangeProduct')
    product_range = Range.objects.filter(name=name).first()
    if product_range is None:
        return []

    members = RangeProduct.objects.filter(range=product_range)
    order = members.filter(product_id=OuterRef('pk')).values('display_order')[:1]
    children = Product.objects.public().select_related(
        'parent__product_class', 'product_class',
    ).prefetch_related('stockrecords')
    products = (
        product_range.all_products().browsable()
        .filter(pk__in=members.values('product_id'))
        .annotate(homepage_display_order=Subquery(order))
        .order_by('homepage_display_order', 'pk')
        .select_related('product_class')
        .prefetch_related('images', 'stockrecords')
        .prefetch_public_children(queryset=children)
        .prefetch_browsable_categories(queryset=Category.objects.for_menu())
    )
    return list(products[:PRODUCT_LIMIT])


class HomepageView(TemplateView):
    template_name = 'oscar/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        Category = get_model('catalogue', 'Category')
        menu_categories = Category.objects.for_menu().order_by('path')
        brands_root = menu_categories.filter(depth=1, slug=BRANDS_ROOT_SLUG).first()
        brands = list(menu_categories.filter(
            path__startswith=brands_root.path, depth=brands_root.depth + 1,
        )) if brands_root else []
        brand_ids = {brand.pk for brand in brands}
        categories = menu_categories.filter(depth=1)
        if brands_root:
            categories = categories.exclude(pk=brands_root.pk)

        best_sellers = range_products('Best Sellers')
        new_arrivals = range_products('New Arrivals')
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
            homepage_categories=list(categories[:CATEGORY_LIMIT]),
            homepage_brands=brands[:BRAND_LIMIT],
            best_sellers=best_sellers,
            new_arrivals=new_arrivals,
            product_filters=[('all', 'All Picks'), *sorted(filters.items(), key=lambda item: item[1])],
        )
        return context
