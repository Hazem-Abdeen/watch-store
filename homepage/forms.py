from django import forms
from django.forms import modelformset_factory

from .models import BrandPresentation, HomeHeroSlide


class HeroSlideForm(forms.ModelForm):
    class Meta:
        model = HomeHeroSlide
        fields = ['desktop_image', 'mobile_image', 'image_alt', 'title', 'subtitle',
                  'button_label', 'button_url', 'display_order', 'is_active']
        labels = {'button_url': 'Destination URL (optional)'}
        help_texts = {'button_url': 'When customers click the banner, they will be taken to this page. Leave blank to disable navigation. Prefer a store path such as /catalogue/.'}
        widgets = {'subtitle': forms.Textarea(attrs={'rows': 3})}


HeroSlideOrderFormSet = modelformset_factory(
    HomeHeroSlide, fields=['display_order', 'is_active'], extra=0,
    widgets={'display_order': forms.NumberInput(attrs={'class': 'form-control', 'style': 'width: 6rem'})},
)


class BrandLogoForm(forms.ModelForm):
    class Meta:
        model = BrandPresentation
        fields = ['logo', 'is_active']
        widgets = {'logo': forms.ClearableFileInput(attrs={'accept': '.png,.webp,.svg'})}
