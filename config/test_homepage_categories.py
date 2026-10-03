"""Editorial category presentation uses the existing homepage catalogue context."""
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from oscar.core.loading import get_model


class HomepageCategoryPresentationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Category = get_model('catalogue', 'Category')
        cls.men = Category.add_root(name='Men', slug='men')
        cls.women = Category.add_root(name='Women', slug='women')
        cls.other = Category.add_root(name='Accessories', slug='accessories')

    def test_homepage_uses_real_links_and_requested_static_artwork(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'class="abdeen-category-card"', count=2)
        for category in (self.men, self.women):
            self.assertContains(response, f'href="{category.get_absolute_url()}"')
            self.assertContains(response, f'abdeen/images/home/categories/{category.slug}.jpg')
            self.assertContains(response, f'id="category-title-{category.pk}">{category.name}</h3>')
            self.assertEqual(self.client.get(category.get_absolute_url()).status_code, 200)
        # The view still loads its original categories; only the showcase changes.
        self.assertIn(self.other, response.context['homepage_categories'])
        for section in ('brands', 'best-sellers', 'new-arrivals'):
            self.assertContains(response, f'id="{section}"')

    def test_missing_categories_never_create_fake_links(self):
        for categories in ([], [self.other]):
            html = render_to_string('oscar/partials/home/categories.html', {'homepage_categories': categories})
            self.assertNotIn('class="abdeen-category-card"', html)
            self.assertIn('Browse all watches', html)
            self.assertIn(f'href="{reverse("catalogue:index")}"', html)

    def test_category_media_does_not_override_the_requested_editorial_files(self):
        self.men.image = 'categories/old-image.jpg'
        html = render_to_string('oscar/partials/home/categories.html', {'homepage_categories': [self.men]})
        self.assertIn('abdeen/images/home/categories/men.jpg', html)
        self.assertNotIn('old-image.jpg', html)
        self.assertIn('data-category-image', html)
        self.assertIn('alt=""', html)
