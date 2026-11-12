# Cash on Delivery checkout

The storefront now uses one checkout page at `/checkout/`. The old Oscar shipping,
payment and preview URLs render the same validated form, so saved links cannot
bypass contact/address validation. Basket → checkout → PLACE ORDER → Oscar's
existing thank-you URL. No account is required. Sign in uses Oscar's customer
login with a return link to checkout.

## Data and order placement

- Required: email, phone, country, first/last name, address line 1 and city.
- Optional: address line 2, postcode and delivery notes. A supplied postcode is
  still validated by Oscar. Local phone numbers use the selected country for
  validation. Jordan is the initial country when configured for shipping.
- Account email comes from the authenticated account. Default saved shipping
  addresses prefill the form; other saved addresses can be selected. Oscar's
  address-book update and customer order history remain in use.
- Guest email is stored in Oscar's checkout session and `Order.guest_email`.
  Phone and delivery notes are saved on the order's `ShippingAddress`.
- Billing is omitted entirely: Oscar accepts a null `billing_address`. There is
  no need to copy shipping data into a second address record.
- The custom view subclasses Oscar's `PaymentDetailsView`. Oscar still calculates
  totals, creates the order and lines, records discounts/voucher usage, allocates
  stock, submits the basket, clears the checkout session, and selects the
  confirmation order. Phase 3 adds a separate notification model and checkout
  migrations; Oscar's order model and shipping/payment calculations are unchanged.
- Every order receives a standard Oscar payment `Source` whose type is
  `Cash on Delivery (COD)`. `amount_allocated` is the total expected in cash;
  `amount_debited` and `amount_refunded` stay zero. No authorization/debit
  transaction or paid payment event is created. Existing order-status policy is
  preserved. Cash collection/settlement after delivery is outside this change.
- Phase 3 replaces Oscar's confirmation-email hook with customer and merchant
  notifications after the order transaction commits. The confirmation page does
  not claim an email was delivered.

## Order email notifications (Phase 3)

After Oscar creates the order and submits its basket, the overridden
`CODCheckoutView.send_order_placed_email()` registers a `transaction.on_commit()`
callback. It checks that the basket is still submitted and sends two separate
plain-text/HTML messages: customer first, then merchant. Failed or rolled-back
placements and confirmation-page visits do not send email. Sending is synchronous
after commit; backend latency can delay the checkout response, but mail failures
do not undo the order, stock allocation, or unpaid COD source.

Customer mail uses `order.email`: guest checkout email or the authenticated
account's email. Merchant mail uses `ABDEEN_ORDER_NOTIFICATION_EMAILS`, defaulting
to `hazem.abdeen39@gmail.com`, `hossam.abdeen199@gmail.com`, and
`emad11abdeen@gmail.com`, together in `To`. A comma-separated environment variable
of the same name replaces that list. Customers only receive merchant mail if
explicitly configured in the merchant list. Exact duplicate addresses are removed.

The development backend is Django's console backend. Real SMTP remains
unconfigured. Emails include order lines, discounts, shipping and final totals,
contact/address information and COD wording. A merchant dashboard link is only
included when the Django Site has a suitable configured domain; `example.com`
intentionally produces no link. Backend acceptance is not proof of inbox delivery,
and merchant recipients are not tracked individually.

### Duplicate protection and explicit recovery

`checkout.0001_initial` creates `OrderEmailNotification`, unique on `(order, kind)`.
Only the request creating that record makes an automatic attempt. Replayed or
concurrent checkout requests, repeated hooks and page refreshes cannot resend it.

`checkout.0002_notification_uncertain` adds the `uncertain` status and converts
legacy `failed` records to `uncertain`: the old handler could record a failure
after mail was already accepted, so those old records are unsafe to retry blindly.
Apply both migrations with `manage.py migrate checkout`.

- `sent`: backend accepted the message; never retried.
- `failed`: failure before sending, explicit SMTP rejection, or backend reported
  zero messages accepted. Eligible for an explicit operator retry.
- `sending`: claimed/in progress; never reclaimed automatically, even after a crash.
- `uncertain`: a timeout/disconnect during sending, or an error saving status after
  backend acceptance. Delivery may already have happened; the retry command refuses
  it. Check provider logs/delivery evidence before any manual intervention.
- `skipped`: no configured recipients; not retried by the command.

After correcting the backend/configuration issue, list failed notifications:

```sh
.venv/bin/python manage.py retry_order_emails
```

Then retry only the selected notification IDs (not order numbers):

```sh
.venv/bin/python manage.py retry_order_emails 12 13
```

No arguments only lists failures and sends nothing. `--database` selects a Django
database alias. Retry uses the current order email and merchant settings. The
command atomically claims `failed → sending`, matching the observed attempt
timestamp, so overlapping commands cannot resend the same attempt. Another failed
attempt remains eligible for a later explicit invocation; no checkout retry loop,
Celery worker, or queue is introduced. Run the command outside a transaction.
Errors are recorded/logged by exception class without SMTP credential/message
contents. Close-connection errors do not turn an accepted message into a failure.

## Shipping and totals

Shipping uses the project-owned Oscar app `config.shipping`, registered in
`config/settings.py`. Its `Delivery(FixedPrice)` method has code
`jordan-delivery`, name **Delivery**, description **1–2 business days**, and both
tax-inclusive and tax-exclusive charges of `Decimal('2.00')`. Previously Oscar's
default `Free()` method supplied **Free shipping / 0 JOD**. Package files are
unchanged; existing Oscar shipping models and migrations are retained.

Delivery is Jordan-only and always costs **2.00 JOD** per order, irrespective of
city, weight, quantity or basket value. There is no free-shipping threshold or
shipping-offer discount. Product/basket vouchers and discounts still apply through
Oscar. Checkout country validation and saved-address choices also enforce Jordan.

The checkout queries this repository for the actual basket, user and destination.
A single method is selected automatically; multiple configured methods render
as choices. Delivery copy is **Delivery / 1–2 business days / 2.00 JOD**.
Summary prices and totals come exclusively
from Oscar's basket, shipping calculator and order-total calculator. Vouchers are
applied/removed in the bag and reflected in checkout and the placed order.

For a 189.00 JOD basket, shipping is 2.00 JOD, the stored Oscar order total is
191.00 JOD, and the COD payment source allocation/balance is 191.00 JOD with no
debit. Confirmation and account order details read persisted order amounts.
Existing historical orders retain their original shipping charges. Email
notification code, SMTP settings and product imports are unchanged.

The signed review token includes the basket ID, lines/quantities/prices, shipping
method/charge, currency and final total. Price/delivery changes, stale tokens and
replays against a new basket require another review. CSRF remains mandatory.
A conditional OPEN→FROZEN database write claims the basket before the standard
Oscar submission; the claim and placement share an atomic transaction. This view
opts out of request-wide transactions so the claim is the first database write
in that transaction, avoiding SQLite read-to-write upgrade races. Oscar's unique
basket-derived order number remains an additional duplicate-order safeguard.
If a concurrent request already placed the order, the second response restores
the same confirmation session instead of overwriting it with stale form data.

## Verification

Regression tests: `config.test_checkout`, `config.test_accounts`,
`config.test_basket`, `config.test_messages` and `config.test_order_notifications`.

Browser harness: start `tests/browser/checkout_preview.py`, then run
`tests/browser/checkout.cjs` with `PLAYWRIGHT_MODULE` pointing to Playwright if it
is not installed in the project. The preview uses a temporary database snapshot
and local-memory email backend; the real development database is never written.
The harness covers guest and signed-in order completion, saved addresses, order
history, required-field errors, replay protection, and screenshots/overflow at
1440, 768, 390 and 320 pixels, plus a complete checkout without JavaScript.

For the Phase 3 console-email browser test, run the preview with
`CONSOLE_ORDER_EMAILS=1` and capture stdout, then run the email harness:

```sh
CONSOLE_ORDER_EMAILS=1 .venv/bin/python -u tests/browser/checkout_preview.py > /tmp/abdeen-phase3-console.log 2>&1
# In a second terminal (set PLAYWRIGHT_MODULE if needed):
CONSOLE_EMAIL_LOG=/tmp/abdeen-phase3-console.log node tests/browser/order-emails.cjs
node tests/browser/checkout-concurrency.cjs
```

This uses Django's actual console backend and real browser checkout against a
disposable database snapshot. The harness checks both printed recipient headers,
two successful notification records, order/COD success, and no further prints
after two confirmation-page refreshes and a replayed checkout POST.

Phase 3 completion verification on 2026-10-04:

- `manage.py check`: no issues; `makemigrations --check --dry-run`: no changes.
- 85 tests pass: 24 notification, 19 checkout, 19 account, 13 basket, 10 message.
- The shipping-discount fixture now uses `Benefit.SHIPPING_PERCENTAGE`; actual
  shipping rules/calculators remain unchanged.
- Retry tests cover recovery, sent-record suppression, overlapping attempts,
  stale claims after another failure, uncertain delivery, post-acceptance database
  failure, and refusal to retry skipped/in-progress/unsubmitted notifications.
- Console browser checkout: customer and merchant messages both printed, merchant
  `To` contained all three configured recipients, order succeeded, and two
  confirmation refreshes plus checkout replay produced zero additional messages.
- Two simultaneous checkout POSTs both redirected successfully, created one
  order, and printed exactly one customer and one merchant message.
- Local checkout migrations `0001_initial` and `0002_notification_uncertain` applied.
- Logs/results: `/tmp/abdeen-phase3-tests.log`, `/tmp/abdeen-phase3-console.log`,
  `/tmp/abdeen-phase3-browser-result.json`, and
  `/tmp/abdeen-phase3-concurrency-result.json`. No real SMTP was configured or used.

Earlier Phase 2 verification on 2026-10-04:

- `manage.py check`: no issues.
- All 61 tests in the four modules above pass, including required email/phone,
  invalid addresses, optional/invalid postcodes, shipping selection/unavailability,
  voucher discounts, changed prices, empty/out-of-stock baskets, CSRF, saved
  address ownership, failed-placement recovery, and replay prevention.
- `manage.py makemigrations --check --dry-run`: no changes detected.
- Guest product → bag → COD → confirmation passes at 1440/768/390/320.
- Account login → product → bag → saved address → COD → confirmation → history
  passes at all four widths. Guest contact details and account ownership were
  checked against actual created orders.
- Browser runs report no JavaScript errors or horizontal overflow. Screenshots
  were visually reviewed at all four widths. A complete guest order also passes
  with JavaScript disabled.
- `tests/browser/checkout-concurrency.cjs`: two simultaneous requests both return
  redirects, create exactly one order, and preserve its confirmation session.
- JavaScript syntax checks and `git diff --check` pass.
- Screenshots: `/tmp/abdeen-cod-screenshots/`; machine-readable browser results:
  `/tmp/abdeen-cod-browser-results.json`. All browser orders are disposable test
  data. The real development database was not modified.

The unavailable PyCharm environment tool was replaced by reading the IDE's
saved SDK configuration, which confirmed `/home/user/watch-store/.venv/bin/python`.
This is checkout code; the repository still has development deployment settings
(`DEBUG=True`, local SQLite and development host/secret configuration).

## Files changed for this checkout

- `config/settings.py` (register custom checkout app)
- `config/checkout/__init__.py`
- `config/checkout/apps.py`
- `config/checkout/forms.py`
- `config/checkout/views.py`
- `config/test_checkout.py`
- `config/test_accounts.py` (adapt checkout expectations; preserve account tests)
- `config/test_basket.py` (adapt checkout entry expectation)
- `templates/oscar/checkout/cod.html`
- `templates/oscar/checkout/layout.html`
- `templates/oscar/checkout/nav.html`
- `templates/oscar/checkout/partials/summary_line.html`
- `templates/oscar/checkout/thank_you.html`
- `static/abdeen/css/checkout.css`
- `static/abdeen/js/checkout.js`
- `tests/browser/checkout_preview.py`
- `tests/browser/checkout.cjs`
- `tests/browser/checkout-concurrency.cjs`
- `tests/browser/accounts.cjs` (adapt checkout entry to the single page)
- `docs/cod-checkout.md`

Other pre-existing workspace changes are outside this checkout change.

Phase 3 additionally adds `config/checkout/models.py`, `notifications.py`,
`migrations/0001_initial.py`, `migrations/0002_notification_uncertain.py`, the
`management/commands/retry_order_emails.py` command and package initializers,
`config/test_order_notifications.py`, the nine templates under
`templates/oscar/communication/emails/`, and `tests/browser/order-emails.cjs`.
It updates email settings, the checkout email hook, this documentation, and the
preview/concurrency browser harnesses.
