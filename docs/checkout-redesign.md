# Checkout visual redesign — 2026-10-05

## Follow-up: editable account email and View cart

The reported screenshot showed an authenticated account with an empty email. The
previous account-only disabled field made that checkout impossible to complete.
Email is now required and editable for everyone, prefilled from the account or
checkout session where available. The validated contact is saved in Oscar's existing
order.guest_email field for both guest and account orders; order.user remains set
for signed-in customers, and the account/login email is never modified.

The local notification recipient, email content and confirmation page use that
saved contact, falling back to Oscar's order.email for older account orders. Oscar's
own order.email property continues to mean the account email on account orders.
Notification timing, duplicate protection and merchant recipients remain unchanged.
No model migration or Oscar package change is required.

The drawer's link is now a full-width outlined VIEW CART button directly below
CHECKOUT, linking to the existing basket page. Browser tests click it and verify
navigation before checkout, then edit the account contact and verify it is saved
without changing the login email. The original report below records the earlier
redesign; this follow-up supersedes its disabled-account-email behavior.

Follow-up verification: 88 Django tests passed. Guest and account checkout passed
at 1440/1024/768/390/320px, including View cart navigation, editable account email,
saved order contact, unchanged account email, notifications, and refresh/replay.
No JavaScript runtime errors or overflow; no-JavaScript checkout also passed.
Logs: /tmp/abdeen-email-fix-tests.log and /tmp/abdeen-email-fix-browser.log.

The checkout uses Abdeen Watches' existing logo and navy button color, with a compact
header, labelled fields, two columns on desktop, a sticky neutral order summary,
and a single column below 900px. Names and city/postcode share rows where space
allows. At 320px these fields stack. Delivery and Cash on Delivery render as
selected boxes. The single shipping code is a hidden input, still validated by
CODCheckoutForm against the shipping repository. Multiple configured methods retain
accessible choices; unavailable shipping retains its error and blocked order action.
The update-total button and redundant checkout step navigation are removed.

The drawer now has a centered CHECKOUT · <real basket total> button without a lock
icon. View shopping bag is directly below and aligned with its left edge.

## Email investigation

The restriction is in config/checkout/forms.py: CODCheckoutForm.__init__ explicitly
sets email.disabled = True only when user.is_authenticated. Django therefore renders
the account email as disabled and ignores attempts to post a different address.
This agrees with Oscar's authenticated order.email property and notification flow.
The page now explains that updates go to the account email and styles that field
as non-editable. No CSS/JavaScript restriction was found for guests. Guests retain
an enabled, required EmailField, normalisation, and checkout-session persistence.

Browser tests type and replace the guest email, submit the form, and read the
created Oscar order to verify order.email equals the edited value. A regression
also verifies changing guest email after a server-side validation failure. Account
orders continue using the account email even if a different email is posted.

## Preserved behavior

No Oscar package source, settings, checkout view, notification service, payment
handler, stock logic, or confirmation code was changed for this redesign. Existing
CSRF and address validation, saved-address ownership, signed total review, voucher
and shipping discount calculation, basket claiming, stock allocation, COD source,
order placement, and confirmation protections remain in use. The summary extends
Oscar's totals template; offer/voucher discounts, shipping discount wrappers,
surcharges, taxes and post-order benefits remain inherited. JOD formatting comes
from the existing currency filter. No billing fields or card integrations were added.

## Verification

- 86 Django tests passed across config.test_checkout, config.test_accounts,
  config.test_basket, config.test_messages and config.test_order_notifications.
- Guest and account browser flows passed at 1440, 1024, 768, 390 and 320px:
  validation, email editing/persistence, saved address, phone, order creation,
  0 JOD shipping, correct total, unpaid COD source, confirmation and replay.
- Each browser order has one customer and one merchant notification; confirmation
  refresh retains the same order and notification records.
- Checkout also completes with JavaScript disabled.
- No horizontal overflow or JavaScript runtime errors in the viewport runs.
- Sticky positioning passed at 1440/1024px; the summary follows payment at
  768/390/320px. Drawer alignment/overflow passed at all five widths. Quantity
  changes updated the displayed total from 125.5 to 251 and back to 125.5 JOD.
- The console-email harness verified exactly two messages and zero resends after
  refresh/replay. Two concurrent checkout submissions created one order and one
  customer/merchant notification pair.
- Node syntax validation and git diff --check passed.

Tests use a disposable snapshot database and console/in-memory email backends.
They do not write store orders or send SMTP email. The configured PyCharm
interpreter was verified from the IDE's saved SDK configuration because this
session does not expose the get_python_environment tool.

Evidence: /tmp/abdeen-redesign-tests.log, /tmp/abdeen-redesign-browser.log,
/tmp/abdeen-redesign-emails.log, /tmp/abdeen-redesign-layout.log,
/tmp/abdeen-redesign-concurrency.log and screenshots in
/tmp/abdeen-cod-screenshots/.

## Files changed for this redesign

- config/checkout/forms.py
- config/test_checkout.py
- static/abdeen/css/checkout.css
- static/abdeen/css/cart-drawer.css
- templates/oscar/checkout/cod.html
- templates/oscar/checkout/layout.html
- templates/oscar/checkout/partials/summary_totals.html
- templates/oscar/basket/partials/drawer_content.html
- tests/browser/checkout.cjs
- tests/browser/checkout_preview.py
- docs/checkout-redesign.md

Other modified/untracked files were present before this task and were preserved.
