from oscar.apps.search.forms import *  # noqa: F401,F403
from oscar.apps.search.forms import SearchForm as OscarSearchForm
from oscar.apps.search.forms import BrowseCategoryForm as OscarBrowseCategoryForm
from oscar.apps.search.forms import CategoryForm as OscarCategoryForm


class NoHiddenSuggestions:
    def get_suggestion(self):
        # Spelling dictionaries may contain titles hidden by the live filter.
        return None


class SearchForm(NoHiddenSuggestions, OscarSearchForm):
    pass


class BrowseCategoryForm(NoHiddenSuggestions, OscarBrowseCategoryForm):
    pass


class CategoryForm(NoHiddenSuggestions, OscarCategoryForm):
    pass
