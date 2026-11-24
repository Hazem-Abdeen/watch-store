"""Environment-only production overrides; select explicitly via DJANGO_SETTINGS_MODULE."""
import os
import re
from email.utils import formataddr, parseaddr
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email

from .settings import *  # noqa: F403,F401


def required(name):
    value = os.environ.get(name, '')
    if not value.strip():
        raise ImproperlyConfigured(f'{name} is required for production.')
    return value


def boolean(name, default):
    value = os.environ.get(name, str(default)).lower().strip()
    if value not in {'true', 'false', '1', '0'}:
        raise ImproperlyConfigured(f'{name} must be true or false.')
    return value in {'true', '1'}


def integer(name, default, minimum=0, maximum=None):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        raise ImproperlyConfigured(f'{name} must be an integer.') from None
    if value < minimum or (maximum is not None and value > maximum):
        raise ImproperlyConfigured(f'{name} is out of range.')
    return value


def csv(name):
    return [value.strip() for value in os.environ.get(name, '').split(',') if value.strip()]


def valid_host(value):
    try:
        ip_address(value.strip('[]'))
        return ':' not in value or (value.startswith('[') and value.endswith(']'))
    except ValueError:
        return bool(re.fullmatch(r'\.?[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?', value))


DEBUG = False
SECRET_KEY = required('DJANGO_SECRET_KEY')
if (SECRET_KEY.startswith('django-insecure-') or len(SECRET_KEY) < 50
        or len(set(SECRET_KEY)) < 5):
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be a strong, independently generated key of at least 50 characters.')
SECRET_KEY_FALLBACKS = []
ALLOWED_HOSTS = csv('DJANGO_ALLOWED_HOSTS')
if not ALLOWED_HOSTS or not all(valid_host(host) for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS must contain explicit hostnames or IPs, without schemes, ports or *.')
CSRF_TRUSTED_ORIGINS = csv('DJANGO_CSRF_TRUSTED_ORIGINS')
for origin in CSRF_TRUSTED_ORIGINS:
    try:
        parsed = urlsplit(origin)
        port = parsed.port
        valid = (parsed.scheme in {'http', 'https'} and parsed.hostname and
                 valid_host(parsed.netloc.split(':')[0] if ':' not in parsed.hostname else f'[{parsed.hostname}]') and
                 not parsed.username and not parsed.password and not parsed.path and
                 not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ImproperlyConfigured('DJANGO_CSRF_TRUSTED_ORIGINS entries must be complete http(s) origins without paths.')

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': required('DB_NAME'),
    'USER': required('DB_USER'),
    'PASSWORD': required('DB_PASSWORD'),
    'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
    'PORT': str(integer('DB_PORT', 5432, 1, 65535)),
    'CONN_MAX_AGE': integer('DB_CONN_MAX_AGE', 60),
    'CONN_HEALTH_CHECKS': True,
    'ATOMIC_REQUESTS': True,
    'OPTIONS': {'connect_timeout': 5, 'sslmode': os.environ.get('DB_SSLMODE', 'prefer')},
}}
if DATABASES['default']['OPTIONS']['sslmode'] not in {'disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full'}:
    raise ImproperlyConfigured('Invalid DB_SSLMODE.')


def production_path(name, default):
    path = Path(os.environ.get(name, str(default)))
    if not path.is_absolute():
        raise ImproperlyConfigured(f'{name} must be an absolute path.')
    path = path.resolve()
    if path in {BASE_DIR, *BASE_DIR.parents, BASE_DIR / 'media', BASE_DIR / 'static'}:  # noqa: F405
        raise ImproperlyConfigured(f'{name} must use a dedicated production directory.')
    return path


STATIC_URL = '/static/'
MEDIA_URL = '/media/'
STATIC_ROOT = production_path('DJANGO_STATIC_ROOT', BASE_DIR / 'var/production/static')  # noqa: F405
MEDIA_ROOT = production_path('DJANGO_MEDIA_ROOT', BASE_DIR / 'var/production/media')  # noqa: F405
SEARCH_INDEX_PATH = production_path('DJANGO_SEARCH_INDEX_PATH', BASE_DIR / 'var/production/whoosh_index')  # noqa: F405
for first, second in [(STATIC_ROOT, MEDIA_ROOT), (STATIC_ROOT, SEARCH_INDEX_PATH), (MEDIA_ROOT, SEARCH_INDEX_PATH)]:
    if first == second or first in second.parents or second in first.parents:
        raise ImproperlyConfigured('Static, media and search directories must not overlap.')
HAYSTACK_CONNECTIONS = {'default': {
    'ENGINE': 'config.search_backend.LocalWhooshEngine', 'PATH': str(SEARCH_INDEX_PATH),
}}

# HTTPS is the safe default. Explicitly disable only for temporary IP/HTTP testing.
HTTPS_ENABLED = boolean('DJANGO_HTTPS_ENABLED', True)
TRUST_PROXY_HEADERS = boolean('DJANGO_TRUST_PROXY_HEADERS', True)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if TRUST_PROXY_HEADERS else None
USE_X_FORWARDED_HOST = False
SECURE_SSL_REDIRECT = HTTPS_ENABLED
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_HSTS_SECONDS = integer('DJANGO_HSTS_SECONDS', 3600) if HTTPS_ENABLED else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS_ENABLED and boolean('DJANGO_HSTS_INCLUDE_SUBDOMAINS', False)
SECURE_HSTS_PRELOAD = HTTPS_ENABLED and boolean('DJANGO_HSTS_PRELOAD', False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755

# Production mail must use SMTP; console would expose customer details in logs.
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
if EMAIL_BACKEND != 'django.core.mail.backends.smtp.EmailBackend':
    raise ImproperlyConfigured('Production EMAIL_BACKEND must be django.core.mail.backends.smtp.EmailBackend.')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp-relay.brevo.com').strip()
if not EMAIL_HOST or any(char.isspace() for char in EMAIL_HOST) or '://' in EMAIL_HOST:
    raise ImproperlyConfigured('EMAIL_HOST must be an SMTP hostname.')
EMAIL_PORT = integer('EMAIL_PORT', 587, 1, 65535)
EMAIL_HOST_USER = required('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = required('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = boolean('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = boolean('EMAIL_USE_SSL', False)
if EMAIL_USE_TLS == EMAIL_USE_SSL:
    raise ImproperlyConfigured('Enable exactly one of EMAIL_USE_TLS or EMAIL_USE_SSL for production SMTP.')
EMAIL_TIMEOUT = integer('EMAIL_TIMEOUT', 10, 1, 60)


def mail_address(value, name):
    try:
        validate_email(value)
        if '\r' in value or '\n' in value:
            raise ValidationError('Invalid header')
    except ValidationError:
        raise ImproperlyConfigured(f'{name} must contain valid email addresses.') from None
    return value


# DEFAULT_FROM_EMAIL retains support for an existing "Name <address>" value.
# EMAIL_FROM_NAME optionally overrides its display name.
sender = required('DEFAULT_FROM_EMAIL')
sender_name, sender_address = parseaddr(sender)
sender_name = os.environ.get('EMAIL_FROM_NAME', sender_name or 'Abdeen Watches')
if any(char in sender + sender_name for char in '\r\n'):
    raise ImproperlyConfigured('Email sender fields must not contain newlines.')
DEFAULT_FROM_EMAIL = formataddr((sender_name, mail_address(sender_address, 'DEFAULT_FROM_EMAIL')))
OSCAR_FROM_EMAIL = DEFAULT_FROM_EMAIL
SERVER_EMAIL = DEFAULT_FROM_EMAIL
ABDEEN_ORDER_NOTIFICATION_EMAILS = list(dict.fromkeys(csv('ABDEEN_ORDER_NOTIFICATION_EMAILS')))
if not ABDEEN_ORDER_NOTIFICATION_EMAILS:
    raise ImproperlyConfigured('ABDEEN_ORDER_NOTIFICATION_EMAILS must contain at least one seller recipient.')
for recipient in ABDEEN_ORDER_NOTIFICATION_EMAILS:
    mail_address(recipient, 'ABDEEN_ORDER_NOTIFICATION_EMAILS')
OSCAR_URL_SCHEMA = 'https' if HTTPS_ENABLED else 'http'
# Oscar otherwise stores full account emails, including password-reset tokens.
OSCAR_SAVE_SENT_EMAILS_TO_DB = False

# No exception-report emails or request-body logging.
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
