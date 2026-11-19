"""Hero integration tests use real uploads in temporary MEDIA storage."""
from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import HeroSlideForm
from .models import HomeHeroSlide


def campaign_image(name='campaign.png', size=(1200, 500)):
    image = BytesIO()
    Image.new('RGB', size, 'navy').save(image, 'PNG')
    return SimpleUploadedFile(name, image.getvalue(), content_type='image/png')


class HeroTestCase(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

    def slide(self, **kwargs):
        kwargs.setdefault('desktop_image', campaign_image())
        return HomeHeroSlide.objects.create(**kwargs)


class HeroTests(HeroTestCase):
    def test_ordering_including_ties(self):
        last = self.slide(display_order=20)
        first = self.slide(display_order=1)
        tied = self.slide(display_order=1)
        response = self.client.get('/')
        self.assertEqual(response.context['hero_slides'], [first, tied, last])
        html = response.content.decode()
        self.assertLess(html.index(first.desktop_image.url), html.index(tied.desktop_image.url))
        self.assertLess(html.index(tied.desktop_image.url), html.index(last.desktop_image.url))

    def test_inactive_and_missing_artwork_are_excluded(self):
        active = self.slide()
        inactive = self.slide(is_active=False, title='Hidden campaign')
        self.slide(desktop_image='')
        response = self.client.get('/')
        self.assertEqual(response.context['hero_slides'], [active])
        self.assertNotContains(response, inactive.desktop_image.url)
        self.assertNotContains(response, 'Hidden campaign')

    def test_empty_and_all_inactive_hide_the_entire_carousel(self):
        for inactive in (False, True):
            with self.subTest(inactive=inactive):
                if inactive:
                    self.slide(is_active=False)
                response = self.client.get('/')
                self.assertContains(response, 'id="categories"')
                self.assertNotContains(response, 'data-hero-carousel')
                self.assertNotContains(response, 'data-hero-controls')
                self.assertNotContains(response, 'hero-watch.jpg')

    def test_desktop_and_mobile_use_media_storage(self):
        slide = self.slide(mobile_image=campaign_image('mobile.png', (600, 800)), image_alt='Campaign offer')
        self.assertTrue(slide.desktop_image.storage.exists(slide.desktop_image.name))
        self.assertTrue(slide.mobile_image.storage.exists(slide.mobile_image.name))
        response = self.client.get('/')
        self.assertContains(response, f'src="{slide.desktop_image.url}"')
        self.assertContains(response, f'<source media="(max-width: 767px)" srcset="{slide.mobile_image.url}">', html=True)
        self.assertContains(response, 'alt="Campaign offer"')
        self.assertContains(response, '/media/homepage/hero/')

    def test_desktop_fallback_and_image_only_slide(self):
        slide = self.slide()
        response = self.client.get('/')
        self.assertContains(response, slide.desktop_image.url)
        self.assertNotContains(response, '<source media=')
        self.assertNotContains(response, 'campaign-hero-copy')
        self.assertNotContains(response, 'data-hero-controls')
        self.assertContains(response, 'fetchpriority="high"', count=1)

    def test_multiple_slides_have_controls_and_only_first_visible(self):
        self.slide()
        self.slide()
        response = self.client.get('/')
        self.assertContains(response, 'data-hero-controls')
        self.assertContains(response, 'data-hero-dot ', count=2)
        self.assertContains(response, 'aria-label="2 of 2" hidden')
        self.assertContains(response, 'loading="lazy"')
        self.assertContains(response, 'aria-label="Previous campaign"')
        self.assertContains(response, 'aria-label="Next campaign"')
        self.assertNotContains(response, 'data-hero-rotation')
        self.assertNotContains(response, '>Pause rotation<')

    def test_compact_header_is_scoped_to_homepage(self):
        self.assertContains(self.client.get('/'), 'abdeen-header-compact')
        self.assertNotContains(self.client.get(reverse('catalogue:index')), 'abdeen-header-compact')

    def test_optional_text_is_escaped_and_links_render(self):
        slide = self.slide(title='<script>Title</script>', subtitle='New campaign',
                           button_label='Shop campaign', button_url='/catalogue/?campaign=hero&sort=new')
        response = self.client.get('/')
        self.assertContains(response, '&lt;script&gt;Title&lt;/script&gt;')
        self.assertContains(response, 'New campaign')
        self.assertContains(response, 'href="/catalogue/?campaign=hero&amp;sort=new"')
        slide.button_url = 'https://example.com/campaign/'
        slide.save()
        self.assertContains(self.client.get('/'), 'href="https://example.com/campaign/"')

    def test_unsafe_urls_are_rejected_and_never_rendered(self):
        for url in ['javascript:alert(1)', 'data:text/html,hello', '//example.com', '/\\example.com',
                    'ftp://example.com', '/\n/example.com', ' https://example.com']:
            with self.subTest(url=url):
                slide = self.slide(button_label='Unsafe CTA', button_url=url)
                with self.assertRaises(ValidationError):
                    slide.full_clean()
                self.assertFalse(slide.has_button)
                self.assertNotContains(self.client.get('/'), 'Unsafe CTA')
                slide.delete()

    def test_button_label_requires_destination(self):
        slide = self.slide(button_label='Shop')
        with self.assertRaises(ValidationError):
            slide.full_clean()
        self.assertFalse(slide.has_button)

    def test_destination_without_button(self):
        slide = self.slide(button_url='/catalogue/', image_alt='Jaguar campaign')
        slide.full_clean()
        response = self.client.get('/')
        self.assertContains(response, 'class="campaign-hero-link" href="/catalogue/" aria-label="Jaguar campaign"')
        self.assertNotContains(response, 'campaign-hero-copy')
        slide.button_url = ''
        slide.save()
        self.assertNotContains(self.client.get('/'), 'class="campaign-hero-link"')

    def test_destinations_are_independent_and_have_accessible_names(self):
        self.slide(button_url='/catalogue/jaguar_123/', image_alt='Jaguar Special Edition')
        self.slide(button_url='/catalogue/category/watches_4/', title='Watch collection')
        self.slide(title='Unlinked campaign')
        response = self.client.get('/')
        self.assertContains(response, 'class="campaign-hero-link"', count=2)
        self.assertContains(response, 'href="/catalogue/jaguar_123/" aria-label="Jaguar Special Edition"')
        self.assertContains(response, 'href="/catalogue/category/watches_4/" aria-label="Watch collection"')

    def test_banner_and_optional_button_are_sibling_links(self):
        from html.parser import HTMLParser

        class LinkParser(HTMLParser):
            open_links = 0
            nested = False

            def handle_starttag(self, tag, attrs):
                if tag == 'a':
                    self.nested |= self.open_links > 0
                    self.open_links += 1

            def handle_endtag(self, tag):
                if tag == 'a':
                    self.open_links -= 1

        self.slide(title='Campaign', button_label='Explore', button_url='/catalogue/')
        parser = LinkParser()
        parser.feed(self.client.get('/').content.decode())
        self.assertFalse(parser.nested)
        self.assertEqual(parser.open_links, 0)

    def test_bad_upload_and_negative_order_are_rejected(self):
        form = HeroSlideForm(data={'display_order': -1, 'is_active': True}, files={
            'desktop_image': SimpleUploadedFile('fake.png', b'not an image', content_type='image/png'),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('desktop_image', form.errors)
        self.assertIn('display_order', form.errors)


class HeroDashboardTests(HeroTestCase):
    def staff_login(self):
        staff = get_user_model().objects.create_user(username='hero-editor', is_staff=True)
        self.client.force_login(staff)

    def test_dashboard_destination_without_label(self):
        self.staff_login()
        slide = self.slide()
        url = reverse('dashboard:hero-slide-update', args=[slide.pk])
        self.assertContains(self.client.get(url), 'Destination URL (optional)')
        response = self.client.post(url, {'button_url': '/catalogue/', 'display_order': 0, 'is_active': True})
        self.assertRedirects(response, reverse('dashboard:hero-slide-list'))
        slide.refresh_from_db()
        self.assertEqual(slide.destination_url, '/catalogue/')
        self.assertFalse(slide.has_button)

    def test_dashboard_rejects_unsafe_destination_and_can_clear_link(self):
        self.staff_login()
        slide = self.slide(button_url='/catalogue/')
        url = reverse('dashboard:hero-slide-update', args=[slide.pk])
        response = self.client.post(url, {'button_url': 'javascript:alert(1)', 'display_order': 0})
        self.assertEqual(response.status_code, 200)
        self.assertIn('button_url', response.context['form'].errors)
        slide.refresh_from_db()
        self.assertEqual(slide.button_url, '/catalogue/')
        response = self.client.post(url, {'button_url': '', 'display_order': 0})
        self.assertRedirects(response, reverse('dashboard:hero-slide-list'))
        slide.refresh_from_db()
        self.assertEqual(slide.destination_url, '')

    def test_dashboard_navigation_and_forms(self):
        self.staff_login()
        response = self.client.get(reverse('dashboard:hero-slide-list'))
        self.assertContains(response, 'Homepage')
        self.assertContains(response, 'Hero Slides')
        self.assertContains(response, 'No hero slides yet')
        response = self.client.get(reverse('dashboard:hero-slide-create'))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertNotContains(response, 'abdeen/css/tailwind.css')

    def test_create_edit_clear_mobile_and_delete(self):
        self.staff_login()
        list_url = reverse('dashboard:hero-slide-list')
        response = self.client.post(reverse('dashboard:hero-slide-create'), {
            'desktop_image': campaign_image(), 'mobile_image': campaign_image('mobile.png'),
            'display_order': 10, 'is_active': 'on', 'title': 'Launch',
            'button_label': 'Shop', 'button_url': '/catalogue/',
        })
        self.assertRedirects(response, list_url)
        slide = HomeHeroSlide.objects.get()
        self.assertTrue(slide.desktop_image.storage.exists(slide.desktop_image.name))
        self.assertTrue(slide.mobile_image)
        response = self.client.post(reverse('dashboard:hero-slide-update', args=[slide.pk]), {
            'display_order': 5, 'title': 'Revised', 'mobile_image-clear': 'on',
        })
        self.assertRedirects(response, list_url)
        slide.refresh_from_db()
        self.assertEqual(slide.title, 'Revised')
        self.assertFalse(slide.is_active)
        self.assertFalse(slide.mobile_image)
        self.assertTrue(slide.desktop_image)
        delete_url = reverse('dashboard:hero-slide-delete', args=[slide.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        self.assertTrue(HomeHeroSlide.objects.filter(pk=slide.pk).exists())
        self.assertRedirects(self.client.post(delete_url), list_url)
        self.assertFalse(HomeHeroSlide.objects.exists())

    def test_bulk_reorder_and_activation(self):
        self.staff_login()
        first, second = self.slide(), self.slide(is_active=False)
        response = self.client.post(reverse('dashboard:hero-slide-list'), {
            'form-TOTAL_FORMS': 2, 'form-INITIAL_FORMS': 2,
            'form-0-id': first.pk, 'form-0-display_order': 20,
            'form-1-id': second.pk, 'form-1-display_order': 1, 'form-1-is_active': 'on',
        })
        self.assertRedirects(response, reverse('dashboard:hero-slide-list'))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(list(HomeHeroSlide.objects.all()), [second, first])
        self.assertEqual(self.client.get('/').context['hero_slides'], [second])

    def test_invalid_reorder_is_atomic(self):
        self.staff_login()
        first, second = self.slide(), self.slide()
        response = self.client.post(reverse('dashboard:hero-slide-list'), {
            'form-TOTAL_FORMS': 2, 'form-INITIAL_FORMS': 2,
            'form-0-id': first.pk, 'form-0-display_order': 20,
            'form-1-id': second.pk, 'form-1-display_order': -1,
        })
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.display_order, 0)
        self.assertTrue(first.is_active)

    def test_anonymous_and_nonstaff_cannot_read_or_write(self):
        slide = self.slide()
        routes = [reverse('dashboard:hero-slide-list'), reverse('dashboard:hero-slide-create'),
                  reverse('dashboard:hero-slide-update', args=[slide.pk]),
                  reverse('dashboard:hero-slide-delete', args=[slide.pk])]
        for url in routes:
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url).status_code, 302)
        user = get_user_model().objects.create_user(username='customer')
        self.client.force_login(user)
        for url in routes:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(HomeHeroSlide.objects.filter(pk=slide.pk).exists())

    def test_csrf_is_required(self):
        self.staff_login()
        client = Client(enforce_csrf_checks=True)
        client.force_login(get_user_model().objects.get(username='hero-editor'))
        slide = self.slide()
        self.assertEqual(client.post(reverse('dashboard:hero-slide-delete', args=[slide.pk])).status_code, 403)
        self.assertTrue(HomeHeroSlide.objects.filter(pk=slide.pk).exists())
