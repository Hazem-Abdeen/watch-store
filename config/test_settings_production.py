"""Production settings tests never connect to PostgreSQL or change local settings."""
import os
from pathlib import Path
import runpy
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, SimpleTestCase, override_settings


ENVIRONMENT = {
    'DJANGO_SECRET_KEY': 'test-only-key-ABcdef0123456789-' * 3,
    'DJANGO_ALLOWED_HOSTS': '203.0.113.10,example.com,[::1]',
    'DJANGO_CSRF_TRUSTED_ORIGINS': 'http://203.0.113.10,https://example.com',
    'DB_NAME': 'test_configuration_only', 'DB_USER': 'test_user',
    'DB_PASSWORD': 'test-only-not-a-real-password',
}


def profile(**changes):
    environment = {**ENVIRONMENT, **changes}
    environment = {key: value for key, value in environment.items() if value is not None}
    with patch.dict(os.environ, environment, clear=True):
        return runpy.run_module('config.settings_production', run_name='config._tested_production')


class ProductionSettingsTests(SimpleTestCase):
    def test_required_secrets_hosts_and_database_credentials_fail_closed(self):
        for name in ['DJANGO_SECRET_KEY', 'DJANGO_ALLOWED_HOSTS', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']:
            with self.subTest(name=name), self.assertRaises(ImproperlyConfigured):
                profile(**{name: None})
        for key in ['django-insecure-' + 'a' * 60, 'a' * 60, 'too-short']:
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                profile(DJANGO_SECRET_KEY=key)

    def test_postgresql_and_existing_oscar_contracts(self):
        settings = profile(DB_HOST='127.0.0.2', DB_PORT='5433')
        self.assertFalse(settings['DEBUG'])
        db = settings['DATABASES']['default']
        self.assertEqual(db['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual((db['HOST'], db['PORT']), ('127.0.0.2', '5433'))
        self.assertTrue(db['ATOMIC_REQUESTS'])
        self.assertTrue(db['CONN_HEALTH_CHECKS'])
        self.assertIn('config.checkout.apps.CheckoutConfig', settings['INSTALLED_APPS'])
        self.assertIn('config.shipping.apps.ShippingConfig', settings['INSTALLED_APPS'])
        self.assertIn('config.partner.apps.PartnerConfig', settings['INSTALLED_APPS'])
        self.assertEqual(settings['OSCAR_DEFAULT_CURRENCY'], 'JOD')
        self.assertTrue(settings['OSCAR_ALLOW_ANON_CHECKOUT'])
        self.assertIn('oscar.apps.customer.auth_backends.EmailBackend', settings['AUTHENTICATION_BACKENDS'])

    def test_http_mode_allows_initial_ip_without_secure_cookies_or_hsts(self):
        settings = profile(DJANGO_HTTPS_ENABLED='false')
        for name in ['SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE',
                     'SECURE_HSTS_INCLUDE_SUBDOMAINS', 'SECURE_HSTS_PRELOAD']:
            self.assertFalse(settings[name])
        self.assertEqual(settings['SECURE_HSTS_SECONDS'], 0)
        with override_settings(**{key: settings[key] for key in ['ALLOWED_HOSTS','SECURE_SSL_REDIRECT','SECURE_HSTS_SECONDS','SECURE_PROXY_SSL_HEADER']}):
            request = RequestFactory().get('/', HTTP_HOST='203.0.113.10', HTTP_X_FORWARDED_PROTO='http')
            self.assertEqual(request.get_host(), '203.0.113.10')
            response = SecurityMiddleware(lambda r: HttpResponse('ok'))(request)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('Strict-Transport-Security', response)

    def test_https_proxy_and_redirect_behavior(self):
        settings = profile()
        for name in ['SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE']:
            self.assertTrue(settings[name])
        self.assertEqual(settings['SECURE_HSTS_SECONDS'], 3600)
        keys = ['ALLOWED_HOSTS', 'SECURE_SSL_REDIRECT', 'SECURE_HSTS_SECONDS', 'SECURE_PROXY_SSL_HEADER']
        with override_settings(**{key: settings[key] for key in keys}):
            middleware = SecurityMiddleware(lambda r: HttpResponse('ok'))
            direct = RequestFactory().get('/', HTTP_HOST='example.com')
            self.assertEqual(middleware(direct).status_code, 301)
            proxied = RequestFactory().get('/', HTTP_HOST='example.com', HTTP_X_FORWARDED_PROTO='https')
            self.assertTrue(proxied.is_secure())
            response = middleware(proxied)
            self.assertEqual(response.status_code, 200)
            self.assertIn('max-age=3600', response['Strict-Transport-Security'])
        self.assertIsNone(profile(DJANGO_TRUST_PROXY_HEADERS='false')['SECURE_PROXY_SSL_HEADER'])

    def test_origin_with_port_and_same_origin_csrf_post(self):
        settings = profile(DJANGO_HTTPS_ENABLED='false', DJANGO_CSRF_TRUSTED_ORIGINS='http://203.0.113.10:8080')
        self.assertEqual(settings['CSRF_TRUSTED_ORIGINS'], ['http://203.0.113.10:8080'])
        with override_settings(ALLOWED_HOSTS=settings['ALLOWED_HOSTS'], CSRF_TRUSTED_ORIGINS=settings['CSRF_TRUSTED_ORIGINS']):
            request = RequestFactory().post('/', HTTP_HOST='203.0.113.10', HTTP_ORIGIN='http://203.0.113.10')
            request.META['HTTP_X_CSRFTOKEN'] = get_token(request)
            request.COOKIES['csrftoken'] = request.META['CSRF_COOKIE']
            self.assertIsNone(CsrfViewMiddleware(lambda r: HttpResponse()).process_view(request, lambda r: HttpResponse(), (), {}))

    def test_invalid_configuration_is_rejected(self):
        cases = [dict(DJANGO_ALLOWED_HOSTS='*'), dict(DJANGO_ALLOWED_HOSTS='https://example.com'),
                 dict(DJANGO_ALLOWED_HOSTS='example.com:8000'),
                 dict(DJANGO_CSRF_TRUSTED_ORIGINS='example.com'),
                 dict(DJANGO_CSRF_TRUSTED_ORIGINS='https://example.com/path'),
                 dict(DJANGO_CSRF_TRUSTED_ORIGINS='https://user:password@example.com'),
                 dict(DJANGO_CSRF_TRUSTED_ORIGINS='https://example.com:invalid'),
                 dict(DJANGO_HTTPS_ENABLED='maybe'), dict(DB_PORT='0'), dict(DB_PORT='invalid'),
                 dict(DB_SSLMODE='invalid'), dict(DJANGO_HSTS_SECONDS='-1')]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ImproperlyConfigured):
                profile(**change)

    def test_paths_are_dedicated_absolute_and_disjoint(self):
        settings = profile()
        root = settings['BASE_DIR']
        self.assertNotEqual(settings['MEDIA_ROOT'], root / 'media')
        self.assertNotEqual(Path(settings['HAYSTACK_CONNECTIONS']['default']['PATH']), root / 'var/whoosh_index')
        for change in [dict(DJANGO_MEDIA_ROOT='relative'), dict(DJANGO_MEDIA_ROOT=str(root / 'media')),
                       dict(DJANGO_STATIC_ROOT='/'),
                       dict(DJANGO_MEDIA_ROOT='/srv/shared', DJANGO_STATIC_ROOT='/srv/shared/static')]:
            with self.subTest(change=change), self.assertRaises(ImproperlyConfigured):
                profile(**change)

    def test_import_does_not_mutate_development_settings(self):
        from config import settings as development
        original = development.DATABASES.copy(), development.HAYSTACK_CONNECTIONS.copy()
        profile()
        self.assertTrue(development.DEBUG)
        self.assertEqual(development.DATABASES['default']['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual((development.DATABASES, development.HAYSTACK_CONNECTIONS), original)
