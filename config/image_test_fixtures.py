"""Real image fixtures for tests whose subject is checkout/pricing, not visibility."""
from io import BytesIO
from tempfile import TemporaryDirectory
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from oscar.core.loading import get_model


class ImageFixtureMedia:
    @classmethod
    def setUpClass(cls):
        directory = cls.enterClassContext(TemporaryDirectory(prefix='abdeen-visible-test-media-'))
        cls.enterClassContext(override_settings(MEDIA_ROOT=directory))
        super().setUpClass()


def add_real_image(product):
    data = BytesIO()
    Image.new('RGB', (10, 10), 'blue').save(data, 'PNG')
    return get_model('catalogue', 'ProductImage').objects.create(product=product,
        original=SimpleUploadedFile('fixture-watch.png', data.getvalue(), content_type='image/png'))
