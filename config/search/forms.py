from oscar.apps.search.forms import *  # noqa: F401,F403
from oscar.apps.search.forms import SearchForm as OscarSearchForm
from oscar.apps.search.forms import BrowseCategoryForm as OscarBrowseCategoryForm
from oscar.apps.search.forms import CategoryForm as OscarCategoryForm
from django import forms

from config.catalogue.gender import GENDER_CHOICES, gender_products


class NoHiddenSuggestions:
    def get_suggestion(self):
        # Spelling dictionaries may contain titles hidden by the live filter.
        return None


class SearchForm(NoHiddenSuggestions, OscarSearchForm):
    pass


class BrowseCategoryForm(NoHiddenSuggestions, OscarBrowseCategoryForm):
    pass


class CategoryForm(NoHiddenSuggestions, OscarCategoryForm):
    gender = forms.ChoiceField(choices=GENDER_CHOICES, required=False)

    def search(self):
        sqs = super().search()
        if not self.data.get('gender'):
            return sqs
        if not self.is_valid():
            return sqs.none()
        # Intersect live database membership with Oscar's search BEFORE paging.
        # Explicitly scope by category even for a non-empty text query: Oscar's
        # default CategoryForm only adds its category clause when q is empty.
        ids = list(gender_products(self.cleaned_data['gender']).filter(
            categories__in=self.categories,
        ).order_by().values_list('pk', flat=True).distinct())
        return sqs.filter(django_id__in=ids) if ids else sqs.none()
