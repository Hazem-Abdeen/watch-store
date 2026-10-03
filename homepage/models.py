from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from .validators import validate_brand_logo


def validate_button_url(value):
    """Allow local absolute paths and HTTP(S), never executable/protocol-relative URLs."""
    if any(character.isspace() or ord(character) < 32 for character in value) or '\\' in value:
        raise ValidationError('Use a local path or a complete http:// or https:// URL.')
    if value.startswith('/') and not value.startswith('//'):
        return
    URLValidator(schemes=['http', 'https'])(value)


class HomeHeroSlide(models.Model):
    desktop_image = models.ImageField(
        upload_to='homepage/hero/%Y/%m/',
        help_text='Wide campaign artwork (recommended 2400 × 1000). Shown without cropping.',
    )
    mobile_image = models.ImageField(
        upload_to='homepage/hero/%Y/%m/', blank=True,
        help_text='Optional portrait artwork for screens below 768px. Desktop artwork is the fallback.',
    )
    image_alt = models.CharField(
        'Image description', max_length=500, blank=True,
        help_text='Describe the campaign and any text embedded in the artwork for screen readers.',
    )
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.TextField(blank=True)
    button_label = models.CharField(max_length=100, blank=True)
    button_url = models.CharField(
        max_length=500, blank=True, validators=[validate_button_url],
        help_text='A local path such as /catalogue/ or a complete https:// URL. Set a label too.',
    )
    display_order = models.PositiveIntegerField(default=0, help_text='Lower numbers appear first.')
    is_active = models.BooleanField('Active', default=True)

    class Meta:
        ordering = ['display_order', 'pk']
        verbose_name = 'hero slide'

    def __str__(self):
        return self.title or f'Hero slide {self.pk or "(new)"}'

    @property
    def has_button(self):
        if not self.button_label or not self.button_url:
            return False
        try:
            validate_button_url(self.button_url)
        except ValidationError:
            return False
        return True

    def clean(self):
        super().clean()
        if bool(self.button_label) != bool(self.button_url):
            raise ValidationError('Provide both a button label and URL, or leave both empty.')


class BrandPresentation(models.Model):
    """Homepage artwork only; Oscar remains the source of category identity."""
    category = models.OneToOneField(
        'catalogue.Category', on_delete=models.CASCADE, related_name='brand_presentation',
    )
    logo = models.FileField(
        upload_to='homepage/brands/%Y/%m/', blank=True, validators=[validate_brand_logo],
        help_text='Transparent PNG, WebP or static SVG, up to 2 MB. Leave empty to show the brand name.',
    )
    is_active = models.BooleanField(
        'Use logo', default=True, help_text='Turn off to show the brand name without removing the logo.',
    )

    def __str__(self):
        return self.category.name

    @property
    def logo_url(self):
        if not self.is_active or not self.logo:
            return ''
        try:
            if self.logo.storage.exists(self.logo.name):
                return self.logo.url
        except (OSError, ValueError):
            pass
        return ''
