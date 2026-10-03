"""Run deterministic carousel fixtures in an isolated database and MEDIA directory."""
import os
import sys
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
from django.conf import settings
from django.core.management import call_command

with TemporaryDirectory(prefix='hero-preview-') as preview:
    preview = Path(preview)
    with sqlite3.connect(settings.DATABASES['default']['NAME']) as source:
        with sqlite3.connect(preview / 'db.sqlite3') as target:
            source.backup(target)
    settings.DATABASES['default']['NAME'] = preview / 'db.sqlite3'
    settings.MEDIA_ROOT = preview / 'media'
    import django
    django.setup()
    call_command('migrate', verbosity=0)
    from homepage.models import HomeHeroSlide
    from django.core.files.base import ContentFile
    from PIL import Image, ImageDraw
    from io import BytesIO
    def artwork(name, size, color):
        image = Image.new('RGB', size, color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((4, 4, size[0]-5, size[1]-5), outline='white', width=8)
        draw.text((size[0]//4, size[1]//2), name, fill='white', font_size=56)
        stream = BytesIO()
        image.save(stream, 'PNG')
        return ContentFile(stream.getvalue(), name=name + '.png')
    HomeHeroSlide.objects.all().delete()
    HomeHeroSlide.objects.create(desktop_image=artwork('Desktop campaign', (2400,1000), '#163747'), mobile_image=artwork('Mobile campaign', (750,1000), '#163747'), image_alt='First test campaign', display_order=1)
    HomeHeroSlide.objects.create(desktop_image=artwork('Second campaign', (2400,1000), '#673c31'), title='Optional campaign title', subtitle='A configurable campaign description.', button_label='Explore watches', button_url='/catalogue/', display_order=2)
    call_command('runserver', '127.0.0.1:8017', use_reloader=False)
