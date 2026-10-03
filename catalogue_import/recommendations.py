"""Read-only catalogue recommendations; Oscar owns purchase availability."""

from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Subquery, TextField, Value, When
from django.db.models.functions import Coalesce
from oscar.core.loading import get_model

from homepage.brands import BRANDS_ROOT_SLUG


RECOMMENDATION_LIMIT = 4
CANDIDATE_LIMIT = 32


def card_products(queryset):
    """Load only relations consumed by the shared card and Oscar's strategy."""
    Product = get_model('catalogue', 'Product')
    Option = get_model('catalogue', 'Option')
    AttributeValue = get_model('catalogue', 'ProductAttributeValue')
    brand = AttributeValue.objects.filter(
        product_id=OuterRef('pk'), attribute__code='brand',
    ).annotate(label=Coalesce('value_option__option', 'value_text', output_field=TextField())).order_by('pk')
    children = Product.objects.public().select_related(
        'product_class', 'parent__product_class',
    ).prefetch_related('stockrecords')
    return (
        queryset.select_related('product_class', 'parent__product_class')
        .annotate(
            storefront_card_brand=Subquery(brand.values('label')[:1]),
            has_product_options=Exists(Option.objects.filter(product=OuterRef('pk'))),
            has_product_class_options=Exists(Option.objects.filter(
                productclass=OuterRef('product_class_id'),
            )),
        )
        .prefetch_related('images', 'stockrecords')
        .prefetch_browsable_categories()
        .prefetch_public_children(queryset=children)
    )


def recommended_products(product, strategy):
    """Rank brand+gender, brand, gender, then shared non-brand categories.

    Only public canonical products qualify. Evaluate availability with Oscar on
    a stable pool of at most 32 matches, then return up to four. Availability is
    a preference within each relevance tier, not a replacement stock policy.
    """
    Product = get_model('catalogue', 'Product')
    AttributeValue = get_model('catalogue', 'ProductAttributeValue')
    Category = get_model('catalogue', 'Category')
    ProductCategory = get_model('catalogue', 'ProductCategory')

    # Use Oscar's parent/child attribute inheritance without modifying products.
    attributes = product.get_attribute_values()
    if hasattr(attributes, 'select_related'):
        attributes = attributes.filter(attribute__code__in=['brand', 'gender']).select_related('attribute', 'value_option')
    facts = {
        av.attribute.code: str(av.value_as_text).strip()
        for av in attributes if av.attribute.code in {'brand', 'gender'}
    }
    categories = list(product.get_categories())
    brands_root = Category.objects.filter(depth=1, slug=BRANDS_ROOT_SLUG).first()
    brand_paths = set()
    category_ids = []
    for category in categories:
        if brands_root and category.path.startswith(brands_root.path):
            if category.depth > brands_root.depth:
                # Sub-brand assignments also belong to the direct brand child.
                brand_paths.add(category.path[:len(brands_root.path) + Category.steplen])
        else:
            category_ids.append(category.pk)

    def attribute_match(code):
        value = facts.get(code)
        matches = AttributeValue.objects.filter(product_id=OuterRef('pk'), attribute__code=code)
        if not value:
            return Q(pk__in=[])
        return Q(Exists(matches.filter(
            Q(value_text__iexact=value) | Q(value_option__option__iexact=value),
        )))

    brand_match = attribute_match('brand')
    if not facts.get('brand') and brand_paths:
        paths = Q()
        for path in sorted(brand_paths):
            paths |= Q(category__path__startswith=path)
        brand_match = Q(Exists(ProductCategory.objects.filter(
            paths, product_id=OuterRef('pk'),
        )))
    gender_match = attribute_match('gender')
    category_match = Q(Exists(ProductCategory.objects.filter(
        product_id=OuterRef('pk'), category_id__in=category_ids,
    )))
    candidates = (
        Product.objects.browsable().exclude(pk=product.pk)
        .filter(brand_match | gender_match | category_match)
        .annotate(recommendation_tier=Case(
            When(brand_match & gender_match, then=Value(0)),
            When(brand_match, then=Value(1)),
            When(gender_match, then=Value(2)),
            default=Value(3), output_field=IntegerField(),
        ))
        .order_by('recommendation_tier', 'pk')
    )
    # EXISTS avoids join multiplication: each product occurs exactly once.
    candidates = list(card_products(candidates)[:CANDIDATE_LIMIT])

    def rank(candidate):
        purchase = (strategy.fetch_for_parent(candidate) if candidate.is_parent
                    else strategy.fetch_for_product(candidate))
        return (candidate.recommendation_tier,
                not purchase.availability.is_available_to_buy, candidate.pk)

    return sorted(candidates, key=rank)[:RECOMMENDATION_LIMIT]
