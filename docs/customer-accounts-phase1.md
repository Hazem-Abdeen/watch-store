# Customer accounts and guest checkout — Phase 1

## Audit before implementation

- Installed Oscar version: **4.2**. User model: Django `auth.User`.
- `AUTHENTICATION_BACKENDS`: `oscar.apps.customer.auth_backends.EmailBackend`, then
  `django.contrib.auth.backends.ModelBackend`. No custom authentication backend,
  customer view, registration form, checkout view or session implementation existed.
- Email login was already configured. Oscar's `EmailAuthenticationForm.username`
  is an **EmailField**, despite the internal field name. Django's backend remains
  available for staff/admin compatibility. Customer forms do not accept usernames.
- Oscar's `EmailUserCreationForm` already exposes email, password and confirmation,
  plus a hidden redirect URL. It generates the internal username, uses Django's
  password hashing/validators, and checks duplicate emails case-insensitively.
- `OSCAR_ALLOW_ANON_CHECKOUT` and `OSCAR_ALLOW_GUEST_CHECKOUT_WITH_ACCOUNT` both
  inherited **False**. `/checkout/` redirected anonymous visitors to
  `/accounts/login/?next=/checkout/`; guest checkout was therefore unavailable.
- The native gateway can capture a guest email, authenticate a returning customer,
  or redirect to optional registration. Native preconditions validate the basket
  and require a customer email before subsequent checkout stages.
- No login, registration or reset templates were overridden. Customer overrides
  covered account tabs, order detail, anonymous order display, recently viewed
  products and hidden wishlists. Existing account navigation included email
  history, product alerts and notifications in addition to profile/orders/addresses.
- Native `/accounts/` redirects to `/accounts/profile/`. Login, registration,
  logout, order history/detail, addresses and password change routes already
  existed. `/password-reset/` and its done/confirm/complete routes already used
  Django views, Oscar's reset-email form and Django tokens. `/dashboard/` uses
  Oscar's staff/partner permissions; `/admin/` remains Django admin.
- Order history and addresses use native user-scoped views. Anonymous access to
  protected account pages redirected to login. The regression tests now verify
  actual order visibility, address CRUD and other-customer denial.
- Custom storefront templates, cart drawer code, feature visibility and catalogue
  presentation do not replace authentication. Existing checkout/basket tests
  explicitly expected mandatory login and needed updating. Registration emails
  were already disabled. Outbound email inherited Django's localhost SMTP defaults.

## Changes and behavior

Both Oscar guest settings are now explicitly **True**. This also allows an email
already associated with an account to continue as a guest without disclosing the
account's existence or requiring its password. No fake user is created and guest
orders are not attached to an account just because their email matches.

The gateway has a primary **Continue as guest** form with one email field, followed
by email/password sign-in and an optional registration link. Both forms submit to
Oscar's unchanged `IndexView` and `GatewayForm`, with the existing `anonymous` or
`existing` option. The registration link preserves the checkout destination.
Oscar still owns basket validation/merging, captured guest email, session state,
shipping/payment preconditions and order placement. Empty/invalid baskets are
still rejected, and address-book mutation routes still require login.

The standalone login page uses the native prefixed login form. Registration uses
Oscar's existing three visible fields. Existing safe-redirect validation remains
in force. Generic invalid-login presentation says “The email or password is
incorrect” while real validation and other error messages remain intact.

The existing account icon links directly to login when logged out and to account
summary when logged in. Account navigation exposes only orders, addresses, account
details and a CSRF-protected sign-out form. It reuses Oscar's native logout endpoint.
Wishlist UI remains hidden. Account forms and pages retain native views and
permissions with storefront header/footer, scoped styling and existing messages.

## Password reset and email deployment

The reset request, neutral confirmation, set-password form, invalid/used-link state
and completion page are styled. Tests capture Oscar's actual reset email, follow
its Django token URL, reject invalid passwords, set a new hashed password, reject
reuse and authenticate with the new password. Unknown email addresses get the
same confirmation without an email. No custom token or password handling exists.

**External delivery has not been configured or claimed.** Runtime settings still
use Django's default SMTP backend at localhost. Without an SMTP service, requests
for an eligible account can fail to send. Configure outbound mail before release;
the automated tests and browser fixture use an isolated in-memory email backend.
For manual local development, a local settings module can use
`EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` to inspect reset
links without delivering email. Do not use console email in production.

Production settings must configure:

- `EMAIL_BACKEND` (SMTP or the chosen provider's backend), `EMAIL_HOST`, `EMAIL_PORT`.
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `EMAIL_USE_TLS` or `EMAIL_USE_SSL`
  as required by the provider; keep credentials in deployment secrets, never source.
- `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL`, and Oscar's `OSCAR_FROM_EMAIL`.
- The `django.contrib.sites` record referenced by `SITE_ID`, with the real public
  domain and shop name. Oscar's reset-email template builds links from this record.
- `OSCAR_URL_SCHEMA = 'https'` so generated reset links use HTTPS.

Validate actual delivery, sender-domain verification (SPF/DKIM/DMARC), link domain
and expiry in the deployment environment. No order-notification template or
notification dispatch logic was changed in this phase.

## Production security follow-ups

- Add measured throttling for login, registration and password-reset requests at
  the application or trusted edge. No rate-limiting dependency was installed.
- Replace development settings before deployment: secret-managed `SECRET_KEY`,
  `DEBUG=False`, explicit hosts, HTTPS, secure session/CSRF cookies, appropriate
  HSTS/proxy settings; run `manage.py check --deploy` with production settings.
- Audit legacy accounts for duplicate email/password combinations. The existing
  Django user model does not enforce email uniqueness; Oscar registration checks
  uniqueness and Oscar's backend fails rather than choosing an ambiguous match.
- Oscar retains native duplicate-email registration validation. Review enumeration
  risk together with rate limiting; custom login/reset messages do not distinguish
  a missing account from incorrect credentials.
- The UI signs out with POST and CSRF. Oscar's native logout route also accepts GET;
  restricting that route to POST can be assessed separately without changing its
  authentication/session implementation in this presentation phase.

## Verification

`manage.py check`: no issues.

`manage.py test config homepage catalogue_import --noinput`: **244 tests passed**.
This includes 19 new account tests plus existing basket, checkout, catalogue,
search, messages, cart drawer, homepage and import regressions. Test emails remain
in memory and test databases/indexes are disposable.

After the final gateway template refinements, all **19 account tests passed again**.
Chromium checks passed at **1440, 768, 390 and 320px**, covering 18 page/state
screenshots per width: login and invalid login, registration, the five reset
states, gateway and invalid guest email, guest address entry, account details,
orders/detail, addresses/add, profile editing and password change. Document/body
widths matched each viewport, with no horizontal overflow, duplicate IDs, missing
field-description targets or browser JavaScript errors. Browser actions verified
guest continuation with an existing account email, gateway login, basket
continuity, registration, reset/password replacement and POST sign-out. A separate
320px check verified native guest checkout with JavaScript disabled. Screenshots
were visually inspected, including desktop gateway and mobile login/orders.

Browser reproduction:

1. Start `tests/browser/accounts_preview.py` with the project interpreter. It copies
   the local SQLite database into a temporary directory, creates test accounts,
   an address/order and an in-stock product, and serves only `127.0.0.1:8022`.
2. Run `node tests/browser/accounts.cjs` with Playwright available. Set
   `PLAYWRIGHT_MODULE`/`CHROME_PATH` when using an existing tooling installation.
3. Stop the fixture with Ctrl-C to remove its temporary database.

Restart the fixture after template changes: its server deliberately disables
autoreload, and Django caches loaded templates.

Screenshots go to `/tmp/abdeen-account-screenshots` by default, configurable with
`SCREENSHOT_DIR`. No fixture URL is included in production `config.urls`.

## Changed files

- `config/settings.py`
- `config/test_accounts.py`
- `config/test_basket.py`
- `config/test_checkout.py`
- `static/abdeen/css/account.css`
- `templates/oscar/partials/home/header.html`
- `templates/oscar/checkout/gateway.html`
- `templates/oscar/customer/auth_base.html`
- `templates/oscar/customer/baseaccountpage.html`
- `templates/oscar/customer/login_registration.html`
- `templates/oscar/customer/registration.html`
- `templates/oscar/customer/partials/auth_errors.html`
- `templates/oscar/customer/partials/standard_tabs.html`
- `templates/oscar/customer/profile/profile.html`
- `templates/oscar/registration/password_reset_form.html`
- `templates/oscar/registration/password_reset_done.html`
- `templates/oscar/registration/password_reset_confirm.html`
- `templates/oscar/registration/password_reset_complete.html`
- `tests/browser/accounts.cjs`
- `tests/browser/accounts_preview.py`
- `tests/browser/messages.cjs`
- `docs/customer-accounts-phase1.md`
- `docs/basket-redesign.md`
- `docs/storefront-messages.md`

No Oscar package files, authentication backend, model, migration, payment logic,
shipping configuration, order-notification logic or production database records
were modified. `.gitignore` already covers the existing local artifacts and did
not require changes.
