# Contabo production configuration

This prepares configuration only. No VPS changes, database creation, migrations,
data transfer, media copy or catalogue replacement were performed by this task.
Local development still uses `config.settings`, SQLite and `manage.py runserver`.

## Required environment

Use `DJANGO_SETTINGS_MODULE=config.settings_production` explicitly for **every**
production command and Gunicorn. The existing WSGI entry point respects that
environment variable and otherwise retains its development default.

Copy `.env.production.example` to a private location outside the checkout, such as
`/etc/abdeen/production.env`. Restrict permissions to the service account/root
(`chmod 600`). Fill it on the server; never commit real values. Django does not
automatically load dotenv files. Supply variables through your service manager
or explicitly export them in the command shell. If using a trusted shell env
file, quote values containing spaces or shell metacharacters:

```bash
set -a
. /etc/abdeen/production.env
set +a
```

Systemd `EnvironmentFile=` and shell files have different quoting rules. Choose
one loader and verify it; never source untrusted env files. Commands below assume
the variables have already been exported and the working directory is the app
checkout. None of these commands logs a secret or password.

| Variable | Requirement/default |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required, independent random key, at least 50 characters. No development fallback. Generate using a password manager or `secrets.token_urlsafe(64)` and store privately. |
| `DJANGO_ALLOWED_HOSTS` | Required comma-separated bare domains/IPs. Include the actual public VPS IP during initial testing, e.g. `203.0.113.10,example.com,www.example.com`. Replace these documentation addresses. No scheme, port or `*`. Bracket IPv6 addresses. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated full origins, e.g. `http://203.0.113.10` initially, then `https://example.com,https://www.example.com`. Include a port for nonstandard ports. No paths/trailing slash. Empty is valid for same-origin requests. This does not enable CORS. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Required. Use a dedicated PostgreSQL database/role; no embedded credentials or SQLite fallback. |
| `DB_HOST`, `DB_PORT` | Defaults `127.0.0.1`, `5432`. Keep PostgreSQL private, not publicly exposed. |
| `DB_CONN_MAX_AGE` | Default 60 seconds; connection health checks enabled. Oscar's `ATOMIC_REQUESTS=True` is retained, as is the COD view's existing transaction handling. |
| `DB_SSLMODE` | Default `prefer` for local PostgreSQL. Remote PostgreSQL should use verified TLS with appropriate CA provisioning (`verify-full`). Nginx HTTPS does not encrypt database connections. |
| `DJANGO_STATIC_ROOT` | Absolute, dedicated collected-static directory. Default `<checkout>/var/production/static`. Example `/srv/abdeen/static`. |
| `DJANGO_MEDIA_ROOT` | Absolute, dedicated upload directory. Default `<checkout>/var/production/media`. Example `/srv/abdeen/media`. **Does not use or copy local development images automatically.** |
| `DJANGO_SEARCH_INDEX_PATH` | Absolute, dedicated Whoosh directory. Default `<checkout>/var/production/whoosh_index`. Example `/srv/abdeen/search`. Keep private and writable by the service account. |
| `DJANGO_HTTPS_ENABLED` | Default `true`. Explicitly set `false` only for temporary HTTP/IP testing. Controls SSL redirect, secure session/CSRF cookies and HSTS together. |
| `DJANGO_TRUST_PROXY_HEADERS` | Default `true` for the Nginx setup below. Only safe when Gunicorn is inaccessible to untrusted clients and Nginx overwrites `X-Forwarded-Proto`. Set false if no trusted proxy is present. |
| `DJANGO_HSTS_SECONDS` | Default 3600 when HTTPS is enabled; forced to zero in HTTP mode. Start short while testing TLS, then increase deliberately. |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_HSTS_PRELOAD` | Default false. Keep off until every affected subdomain supports HTTPS and a separate preload decision has been made. Do not preload an IP test deployment. |

Static, media and search paths must be separate, nonoverlapping absolute
directories. The checkout root, filesystem roots and development `media`/`static`
roots are rejected. Production deployment must provision these directories with
the application user as owner. Nginx needs read/traverse permission for static
and media only; do not serve the checkout, environment file, backups or index.
Uploaded files are mode 0644, directories 0755; application/environment secrets
belong outside these public directories.

## HTTP/IP test stage

Set `DJANGO_HTTPS_ENABLED=false`, the real IP in `DJANGO_ALLOWED_HOSTS`, and the
matching HTTP origin if needed. Django will not force HTTPS or require secure
cookies during this stage. HTTP traffic is unencrypted: use it for temporary
smoke testing with test credentials, not real customer checkout.

The production profile always has `DEBUG=False`. Static and media must be served
by Nginx, not Django's development file-serving URLs.

Example Nginx **HTTP test** server template (review and install separately):

```nginx
server {
    listen 80 default_server;
    server_name _;
    return 444;
}
server {
    listen 80;
    server_name 203.0.113.10 example.com www.example.com;
    client_max_body_size 20m;

    location /static/ {
        alias /srv/abdeen/static/;
        autoindex off;
        add_header X-Content-Type-Options nosniff always;
    }
    location /media/ {
        alias /srv/abdeen/media/;
        autoindex off;
        add_header X-Content-Type-Options nosniff always;
    }
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Use matching aliases if environment paths differ. Keep file locations static:
never pass uploaded media to an interpreter or enable directory listing. Keep
Gunicorn bound to loopback (or a private Unix socket). Firewall its port and
PostgreSQL; expose only the intended Nginx HTTP/HTTPS ports. Never copy a client's
`X-Forwarded-Proto` unchanged to Django.

## Startup commands for a later authorized deployment

```bash
# On the server in its own virtualenv, after review:
.venv/bin/python -m pip install -r requirements.txt
npm ci
npm run build:css

# These validate configuration. They do not migrate/import data.
.venv/bin/python manage.py check --settings=config.settings_production
.venv/bin/python manage.py check --deploy --settings=config.settings_production

# Writes only the configured STATIC_ROOT; execute during deployment, not locally
# against production paths. Static assets are not product media.
.venv/bin/python manage.py collectstatic --noinput --settings=config.settings_production

# Run in a managed service with the private environment supplied:
.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8001 --workers 2 \
  --timeout 60 --error-logfile -
```

Supply the environment through a service manager for persistent operation; do
not rely on a temporary interactive shell. Set its `WorkingDirectory` to the
checkout and its environment module to `config.settings_production`.

No data-migration command is prescribed or executed here. PostgreSQL provisioning,
schema migrations, transfer of the 350 products and their media, and updating
the Django Site domain require a separately reviewed data migration plan and
backup. The server cannot serve the catalogue from an empty PostgreSQL database.

After the database/media have been populated through that later approved plan:

```bash
.venv/bin/python manage.py rebuild_index --noinput --settings=config.settings_production
```

Whoosh's existing backend is preserved; the index is not a database or media
backup. Keep indexing as a single controlled writer; rebuild after catalogue
or stock/category changes. The current application disables automatic save-time
index writes. Search directory ownership must allow the app to read the index
and the indexing command to replace it.

## HTTPS transition

Install and verify the certificate in Nginx, add its TLS listener and an HTTP to
HTTPS redirect, then set `DJANGO_HTTPS_ENABLED=true` and change trusted origins to
HTTPS. Keep Nginx's `$scheme` header override on the TLS listener. Restart Gunicorn
with the updated environment and run `check --deploy` again. HSTS and secure
cookies are enabled only in this mode. Once TLS is stable, consider raising HSTS
to 31536000; subdomains and preload remain opt-in. Rollback of HSTS takes time
because browsers retain it.

An HTTP-only profile intentionally produces Django deployment warnings for SSL
redirect, secure cookies and HSTS. Do not silence those checks; eliminate them
by completing the HTTPS transition.

The default HTTPS profile intentionally retains `security.W005` and
`security.W021`: subdomain HSTS and preload remain disabled until their wider
impact is confirmed. They are not silenced and do not require enabling those
options prematurely.

## Existing behavior and email

Oscar apps/authentication, COD order placement, regular-price discounts, the
availability-only stock policy, fixed 2.00 JOD shipping and the search backend
are inherited unchanged. All 350 local catalogue products remain unavailable;
this profile does not enable products or import data.

Existing email variables remain supported: `EMAIL_BACKEND`, `EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`,
`EMAIL_USE_SSL`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`, and
`ABDEEN_ORDER_NOTIFICATION_EMAILS`. The example intentionally has no merchant
recipients. Set the actual recipients explicitly before taking orders. Configure
SMTP credentials privately; do not enable both TLS and SSL. Console email is the
inherited default and does not deliver order confirmations. Console messages can
contain order details, so restrict service-log access. No real email is sent by
the configuration tests.

## Checks and limitations

Configuration tests run under the development test runner with disposable
SQLite/search data; they validate environment parsing, proxy redirects/HSTS,
HTTP cookies, origins, paths and preservation of Oscar configuration. They do
not claim a PostgreSQL connection or server deployment has been tested.

Local verification for this change: 225 configuration/business regression tests
passed; development and production system checks passed; Gunicorn's
`--check-config` passed; `pip check` passed. Production `check --deploy` completed
with the deliberate warnings described above (two in HTTPS mode, four in HTTP
mode). No migrations or production PostgreSQL connections were run. The local
SQLite database checksum remained identical.

```bash
.venv/bin/python manage.py test config.test_settings_production config.test_checkout \
  config.test_shipping config.test_accounts config.test_sale_pricing \
  config.test_product_detail config.test_basket catalogue_import.tests --noinput
```

Reference: Django's [deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/),
[proxy/security settings](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header),
and [PostgreSQL requirements](https://docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes).
