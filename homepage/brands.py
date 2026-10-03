from oscar.core.loading import get_model

BRANDS_ROOT_SLUG = 'brands'


def brand_categories():
    """All direct brand children for management, including unpublished ones."""
    Category = get_model('catalogue', 'Category')
    root = Category.objects.filter(depth=1, slug=BRANDS_ROOT_SLUG).first()
    if root is None:
        return Category.objects.none()
    return Category.objects.filter(
        path__startswith=root.path, depth=root.depth + 1,
    ).select_related('brand_presentation').order_by('path')
