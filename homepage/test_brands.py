from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from oscar.core.loading import get_model

from .forms import BrandLogoForm
from .models import BrandPresentation

Category = get_model('catalogue', 'Category')
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 80"><path fill="#171717" d="M0 0h300v80H0z"/></svg>'


def logo_upload(extension='png'):
    if extension == 'svg':
        return SimpleUploadedFile('brand.svg', SVG, content_type='image/svg+xml')
    data = BytesIO()
    Image.new('RGBA', (400, 100), (20, 20, 20, 128)).save(data, extension.upper())
    return SimpleUploadedFile(f'brand.{extension}', data.getvalue(), content_type=f'image/{extension}')


class BrandLogoTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.root = Category.add_root(name='Brands', slug='brands')
        self.brand = self.root.add_child(name='Example Brand')

    def section(self):
        response = self.client.get('/')
        return render_to_string('oscar/partials/home/brands.html', {
            'homepage_brands': response.context['homepage_brands'],
        })

    def test_brand_with_logo_uses_media_and_correct_logo_link(self):
        presentation = BrandPresentation.objects.create(category=self.brand, logo=logo_upload())
        self.assertTrue(presentation.logo.storage.exists(presentation.logo.name))
        html = self.section()
        self.assertIn(f'src="{presentation.logo.url}"', html)
        self.assertIn('/media/homepage/brands/', html)
        self.assertIn(f'<a class="abdeen-brand-link" href="{self.brand.get_absolute_url()}"', html)
        self.assertIn('alt="Example Brand"', html)
        self.assertIn('data-brand-logo-fallback hidden', html)
        self.assertEqual(html.count('<a '), 1)

    def test_no_metadata_or_empty_logo_uses_brand_name(self):
        for create_metadata in (False, True):
            if create_metadata:
                BrandPresentation.objects.create(category=self.brand)
            html = self.section()
            self.assertNotIn('<img ', html)
            self.assertIn('data-brand-logo-fallback>Example Brand</span>', html)
            self.assertIn(self.brand.get_absolute_url(), html)

    def test_inactive_logo_keeps_brand_and_catalogue_link(self):
        presentation = BrandPresentation.objects.create(category=self.brand, logo=logo_upload(), is_active=False)
        html = self.section()
        self.assertNotIn(presentation.logo.url, html)
        self.assertIn('data-brand-logo-fallback>Example Brand</span>', html)
        self.assertIn(self.brand.get_absolute_url(), html)

    def test_missing_storage_file_uses_text(self):
        BrandPresentation.objects.create(category=self.brand, logo='homepage/brands/missing.png')
        self.assertNotIn('<img ', self.section())
        self.assertIn('data-brand-logo-fallback>Example Brand</span>', self.section())

    def test_storage_failure_uses_text(self):
        presentation = BrandPresentation.objects.create(category=self.brand, logo='homepage/brands/unavailable.png')
        with patch.object(presentation.logo.storage, 'exists', side_effect=OSError):
            self.assertNotIn('<img ', self.section())

    def test_private_and_menu_excluded_brands_stay_hidden(self):
        hidden = self.root.add_child(name='Private brand', is_public=False)
        excluded = self.root.add_child(name='Excluded brand', exclude_from_menu=True)
        for brand in (hidden, excluded):
            BrandPresentation.objects.create(category=brand, logo=logo_upload())
        html = self.section()
        self.assertNotIn('Private brand', html)
        self.assertNotIn('Excluded brand', html)
        self.root.is_public = False
        self.root.save()
        self.assertEqual(self.client.get('/').context['homepage_brands'], [])

    def test_existing_category_image_is_untouched(self):
        self.brand.image = 'categories/editorial.jpg'
        self.brand.save()
        BrandPresentation.objects.create(category=self.brand, logo=logo_upload())
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.image.name, 'categories/editorial.jpg')
        self.assertNotIn('categories/editorial.jpg', self.section())

    def test_brand_order_limit_and_direct_children_are_preserved(self):
        for index in range(10):
            self.root.add_child(name=f'Brand {index}')
        child = self.brand.add_child(name='Not a direct brand')
        BrandPresentation.objects.create(category=child, logo=logo_upload())
        expected = list(Category.objects.for_menu().filter(
            path__startswith=self.root.path, depth=2,
        ).order_by('path')[:8])
        self.assertEqual(self.client.get('/').context['homepage_brands'], expected)
        self.assertNotIn('Not a direct brand', self.section())

    def test_png_webp_and_svg_uploads_are_valid(self):
        for extension in ('png', 'webp', 'svg'):
            with self.subTest(extension=extension):
                form = BrandLogoForm(data={'is_active': True}, files={'logo': logo_upload(extension)},
                                     instance=BrandPresentation(category=self.brand))
                self.assertTrue(form.is_valid(), form.errors)
                saved = form.save()
                self.assertIn(f'.{extension}', saved.logo_url)
                self.assertIn(saved.logo_url, self.section())
                saved.delete()

    def test_unsafe_and_invalid_uploads_are_rejected(self):
        samples = [
            ('broken.png', b'not an image'),
            ('logo.html', b'<h1>HTML</h1>'),
            ('logo.svg', SVG.replace(b'<path', b'<script>alert(1)</script><path')),
            ('logo.svg', SVG.replace(b'<path', b'<use href="https://example.com/x.svg#x"/><path')),
            ('logo.svg', SVG.replace(b'<path', b'<path onload="alert(1)"/><path')),
            ('logo.svg', b'<!DOCTYPE svg [<!ENTITY a "test">]>' + SVG),
            ('logo.svg', SVG.replace(b'<path', b'<style>@import "https://example.com/x.css";</style><path')),
            ('logo.svg', SVG.replace(b'<path', b'<path style="fill:url(https://example.com/x)"/><path')),
            ('logo.png', b'x' * (2 * 1024 * 1024 + 1)),
        ]
        for name, data in samples:
            with self.subTest(name=name, size=len(data)):
                form = BrandLogoForm(data={'is_active': True}, files={
                    'logo': SimpleUploadedFile(name, data),
                }, instance=BrandPresentation(category=self.brand))
                self.assertFalse(form.is_valid())
                self.assertIn('logo', form.errors)

    def test_static_svg_styles_and_local_references_are_accepted(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><linearGradient id="g"><stop offset="0" stop-color="red"/></linearGradient></defs><style>.mark {fill: url(#g);}</style><path class="mark" d="M0 0h10v10H0z"/></svg>'
        form = BrandLogoForm(data={'is_active': True}, files={'logo': SimpleUploadedFile('logo.svg', svg)},
                             instance=BrandPresentation(category=self.brand))
        self.assertTrue(form.is_valid(), form.errors)

    def login_staff(self):
        self.client.force_login(get_user_model().objects.create_user(username='brand-editor', is_staff=True))

    def test_dashboard_upload_replace_clear_and_deactivate(self):
        self.login_staff()
        url = reverse('dashboard:brand-logo-update', args=[self.brand.pk])
        self.assertContains(self.client.get(url), 'enctype="multipart/form-data"')
        self.assertEqual(BrandPresentation.objects.count(), 0)  # GET has no side effects.
        response = self.client.post(url, {'logo': logo_upload(), 'is_active': 'on'})
        self.assertRedirects(response, reverse('dashboard:brand-logo-list'))
        saved = BrandPresentation.objects.get(category=self.brand)
        original_name = saved.logo.name
        self.client.post(url, {'logo': logo_upload('svg'), 'is_active': 'on'})
        saved.refresh_from_db()
        self.assertNotEqual(saved.logo.name, original_name)
        self.client.post(url, {})
        saved.refresh_from_db()
        self.assertFalse(saved.is_active)
        self.assertTrue(saved.logo)
        self.client.post(url, {'logo-clear': 'on', 'is_active': 'on'})
        saved.refresh_from_db()
        self.assertFalse(saved.logo)

    def test_dashboard_lists_brand_categories_only_and_rejects_other_categories(self):
        self.login_staff()
        category = Category.add_root(name='Department')
        child = self.brand.add_child(name='Nested category')
        response = self.client.get(reverse('dashboard:brand-logo-list'))
        self.assertContains(response, 'Example Brand')
        for invalid in (self.root, category, child):
            url = reverse('dashboard:brand-logo-update', args=[invalid.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {'logo': logo_upload()}).status_code, 404)
        self.assertFalse(BrandPresentation.objects.exists())

    def test_dashboard_permissions_and_csrf(self):
        urls = [reverse('dashboard:brand-logo-list'), reverse('dashboard:brand-logo-update', args=[self.brand.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url).status_code, 302)
        customer = get_user_model().objects.create_user(username='customer')
        self.client.force_login(customer)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url).status_code, 403)
        self.login_staff()
        client = Client(enforce_csrf_checks=True)
        client.force_login(get_user_model().objects.get(username='brand-editor'))
        self.assertEqual(client.post(urls[1], {'logo': logo_upload()}).status_code, 403)

    def test_missing_brands_root_is_safe(self):
        self.root.delete()
        self.assertContains(self.client.get('/'), 'Our brand collection is being prepared.')
        self.login_staff()
        self.assertContains(self.client.get(reverse('dashboard:brand-logo-list')), 'No brand categories found')
