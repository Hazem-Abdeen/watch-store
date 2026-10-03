"""Give Django's test suite a disposable Whoosh index."""

from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import override_settings
from django.test.runner import DiscoverRunner
from haystack import connections


class SearchIsolatedDiscoverRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self.search_directory = TemporaryDirectory(prefix='abdeen-test-search-')
        self.original_connections = connections.connections_info
        self.search_settings = override_settings(HAYSTACK_CONNECTIONS={
            'default': {
                **settings.HAYSTACK_CONNECTIONS['default'],
                'PATH': self.search_directory.name,
            },
        })
        self.search_settings.enable()
        # Haystack 3.4 caches connection settings independently of Django.
        connections.connections_info = settings.HAYSTACK_CONNECTIONS
        connections.reload('default')

    def teardown_test_environment(self, **kwargs):
        try:
            backend = connections['default'].get_backend()
            if backend.setup_complete:
                backend.index.close()
            self.search_settings.disable()
            connections.connections_info = self.original_connections
            connections.reload('default')
            self.search_directory.cleanup()
        finally:
            super().teardown_test_environment(**kwargs)
