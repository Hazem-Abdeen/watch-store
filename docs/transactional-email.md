# Transactional email: Brevo SMTP

## Audit and scope

The project already had Oscar COD checkout with an explicit order transaction,
a `transaction.on_commit()` email hook, customer and merchant text/HTML templates,
and a unique `(order, kind)` notification record. The thank-you page never sends
mail. Existing tests cover committed orders, rollbacks, unsuccessful placements,
repeat submissions, discounts, failures and explicit retries.

This change preserves that pipeline. It removes hardcoded seller addresses,
separates development/production mail, validates SMTP configuration, includes
checkout delivery notes in both email formats, adds a database-free SMTP probe,
and sets Oscar email links to HTTPS when production HTTPS is enabled. Account
tests now use the existing real-image fixture required by storefront visibility.

Password reset already uses Django's native reset views, token generation and
validation via Oscar's PasswordResetForm/CustomerDispatcher. Stock subscriptions,
anonymous confirmation and eager back-in-stock alerts are Oscar's existing
implementation (`OSCAR_EAGER_ALERTS=True`). Both use `OSCAR_FROM_EMAIL`, now set
to the same sender as order emails. Registration email remains disabled.
Production disables Oscar's full-email database archive to avoid retaining reset
tokens and message bodies; this does not disable sending or order status records.

## Environment on Contabo

Use the existing Gunicorn service's protected environment configuration, outside
the repository. Django does **not** load `.env.production.example` automatically.
Keep its existing database, domain, TLS and deployment configuration. Load the
same environment for management commands. Do not print the environment, enable
SMTP protocol debugging, or place keys in command-line arguments or source files.

| Variable | Value / purpose |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings_production` |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` (default and required backend) |
| `EMAIL_HOST` | `smtp-relay.brevo.com` by default |
| `EMAIL_PORT` | `587` by default; range 1–65535 |
| `EMAIL_HOST_USER` | Required: copy the SMTP login shown in Brevo |
| `EMAIL_HOST_PASSWORD` | Required: Brevo **SMTP key**, not the HTTP API key or account password |
| `EMAIL_USE_TLS` | `true` by default: STARTTLS |
| `EMAIL_USE_SSL` | `false` by default; for implicit TLS use port 465, TLS=false, SSL=true |
| `EMAIL_TIMEOUT` | `10` seconds by default; permitted range 1–60 |
| `DEFAULT_FROM_EMAIL` | Required: existing verified sender address; `Name <address>` also supported |
| `EMAIL_FROM_NAME` | Sender display name; defaults to the name above or `Abdeen Watches` |
| `ABDEEN_ORDER_NOTIFICATION_EMAILS` | Required: comma-separated seller mailboxes; duplicate entries removed |

Both TLS flags accept `true`/`false` or `1`/`0`; exactly one must be enabled.
Invalid mail configuration stops production startup with a field-specific error
that does not echo credentials. Production console/file/dummy backends are refused
to prevent logging customer messages or silently discarding them. Existing
deployments using the console backend must configure SMTP **before** restarting.
The development profile always uses console email with no seller defaults, even
if production SMTP variables are present. Unit tests use memory/mocked backends.
Console output is intended for local synthetic data only.

Brevo documents the [SMTP settings and sender prerequisites](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP)
and the [SMTP key requirement](https://developers.brevo.com/docs/smtp-integration).
Use a sender already verified and permitted by your Brevo account for testing,
with a mailbox you control as recipient. The example sender is only a placeholder.
If no suitable verified sender is available, stop before live sending and arrange
one independently of the existing domain; configuration alone cannot verify it.
Provider acceptance is not proof of inbox delivery: inspect Brevo's transactional
logs and the controlled mailbox, including spam.

**Do not change DNS/MX/SPF/DKIM, Nginx, the existing email service or WordPress for
this work.** `abdeenwatches.com` still points to the old site. Sender verification
and the website's link hostname are separate concerns. This work does not change
either domain or production database.

## Safe verification and deployment

1. Run local tests using the development profile:

   ```sh
   .venv/bin/python manage.py test --settings=config.settings --noinput
   ```

2. Prepare the protected environment above, using existing deployment paths and
   service configuration. Keep `DJANGO_HTTPS_ENABLED=true` on the existing HTTPS
   deployment (the older example file also contains unrelated HTTP bootstrap
   settings; do not copy those over your deployed values).

3. With that environment loaded, run a connection-only probe on the VPS:

   ```sh
   .venv/bin/python manage.py test_smtp --settings=config.settings_production
   ```

   It opens SMTP, negotiates the configured encryption and authenticates. It sends
   nothing, performs no database queries and skips database/system checks. A
   failure reports only its exception class. Network access to the SMTP port must
   be allowed by the VPS/provider; diagnose failures before changing infrastructure.

4. Explicitly send one synthetic text/HTML message to a controlled test mailbox:

   ```sh
   .venv/bin/python manage.py test_smtp --settings=config.settings_production --to controlled-mailbox@example.net
   ```

   Replace the placeholder recipient. This command reads no customers or orders
   and writes no database records. It never uses the seller list implicitly.
   Check sender name/address, both formats and Brevo delivery status. A timeout
   may occur after acceptance: check Brevo before rerunning to avoid duplicate
   test messages. No real SMTP send was performed during the local implementation.

5. Review the configured Django Site record read-only. Native reset and stock
   email links use its domain, not the sender address or request Host. Merchant
   dashboard links also use this Site. It must already identify the reachable
   Django deployment, not the old WordPress hostname. If it does not, defer link
   acceptance testing and handle that configuration in a separately authorized
   deployment change. The SMTP probe itself has no site links and needs no Site.

6. Deploy through the existing release procedure and restart the existing
   Gunicorn service after configuration/probes pass. No new migrations or
   dependencies are introduced. The existing checkout migrations `0001` and
   `0002` must already be applied; inspect with `showmigrations checkout` using the
   production profile. This task does not apply migrations to production. Keep
   the site private and verify password reset with a controlled existing test
   account only when its Site links are correct.

## Order delivery, retries and limits

The customer recipient is the checkout contact saved in `order.guest_email`
(including account orders), with `order.email` as the legacy fallback. Merchant
mail goes only to the configured seller list, together in `To`. The formats include
order number/date, products, quantities, prices, discounts, shipping, surcharges,
total, contact/address, delivery notes and COD instructions. HTML escapes customer
input. Private staff notes are excluded.

Delivery happens synchronously after commit, customer then merchant. SMTP latency
adds to response time; socket timeouts limit individual operations, not the whole
request. Email exceptions are caught and cannot roll back a completed order or
cause a new order on retry. Only exception classes and order IDs/numbers are
logged. Never add raw SMTP exception strings, message bodies or tracebacks there.

The existing `retry_order_emails` command lists safe failures without sending:

```sh
.venv/bin/python manage.py retry_order_emails --settings=config.settings_production
```

After fixing the cause, explicitly retry selected **notification IDs**, not order
numbers (this sends real emails and updates notification status):

```sh
.venv/bin/python manage.py retry_order_emails 12 13 --settings=config.settings_production
```

`failed` means connection/setup failure, explicit rejection or zero accepted
messages; only these attempts are retryable. `sent` means backend acceptance.
`sending` means claimed, `uncertain` means acceptance cannot be determined, and
`skipped` means no recipients at that time. None of those four states is retried.
The command's conditional claim prevents overlapping retries from sending twice.

SMTP cannot guarantee exactly-once delivery. A process crash between order commit
and its callback can leave an order without notification records; a crash during
sending can leave `sending`. Monitor these cases against order and Brevo records
and review manually; there is no durable queue or automatic crash recovery.
Merchant acceptance is tracked per message, not per recipient; partial recipient
refusals/bounces require inspection in Brevo, never a blanket resend. No Celery,
Redis, background service or scheduled resend has been introduced.

Native stock alerts retain Oscar's behavior, including closing an active alert
before dispatch; they do not use the order retry records. Native account/stock
mail also retains Oscar's exception handling. Do not use order retry commands to
recover those messages. These are existing limitations, not guarantees of durable
delivery for all email types.

## Local validation

- 95 focused tests pass across `config.test_transactional_email`,
  `config.test_settings_production`, `config.test_order_notifications`,
  `config.test_accounts`, `config.test_checkout` and `config.test_shipping`.
- Django system checks and `makemigrations --check --dry-run` pass.
- Full suite: 383 tests, 46 failures and 8 errors. A clean archive of the original
  commit ran 371 tests with 48 failures and 8 errors. Comparing failing test names
  found no new failures; the two account fixture failures were fixed. Remaining
  failures are in existing catalogue, cart-drawer, dashboard search, product
  detail, recommendation, search and homepage tests. The overall suite is not
  green and those failures remain outside this email change.
- No external SMTP connection, live message or production database change was
  made. Live Brevo verification remains a deployment step with a controlled inbox.

Changed files: `config/settings.py`, `config/settings_production.py`,
`.env.production.example`, `config/checkout/notifications.py`,
`config/checkout/management/commands/test_smtp.py`, the text/HTML
`abdeen_order_details` templates, `config/test_transactional_email.py`,
`config/test_order_notifications.py`, `config/test_settings_production.py`,
`config/test_accounts.py`, `tests/browser/checkout_preview.py`,
`tests/browser/order-emails.cjs`, `docs/cod-checkout.md`, and this guide.
