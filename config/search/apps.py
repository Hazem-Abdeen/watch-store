from oscar.apps.search.apps import SearchConfig as OscarSearchConfig


class SearchConfig(OscarSearchConfig):
    name = 'config.search'

    def ready(self):
        super().ready()
        from . import signals  # noqa: F401
