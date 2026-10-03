# Basket redesign — 2026-09-23

The basket now uses the established Abdeen header/footer, local typography,
charcoal/red palette and restrained borders. Desktop displays product rows beside
an order summary; tablet and mobile stack the sections. Each row shows the actual
product image, Oscar's product/option description, stock-record SKU, available
customer-facing child attributes, availability, unit price and line total.
Missing or failed images use the existing watch placeholder.

The local basket template extends Oscar's installed template and inherits
`oscar.basket.init`. The content partial extends Oscar's basket partial, preserving
its warnings and offer messages. Quantity controls render Oscar's bound field and
submit its original formset, including IDs, management fields, CSRF and validation.
Remove, save for later and move back retain Oscar's action hooks and fields.
Without JavaScript, the ordinary update form and action checkboxes remain usable.

The order summary extends the original totals partial with only its section label
changed to “Subtotal.” Pricing, discounts, vouchers, tax, shipping, surcharges,
post-order actions and order totals still come from Oscar. Values use Oscar's
currency filter and the basket/line currency (JOD in the current catalogue).
The voucher form and voucher-removal forms keep the original POST endpoints.
Checkout uses the original `checkout:index` link.

The small basket script only refreshes the shared header count/accessible label
from Oscar's server-rendered HTML after an AJAX replacement, announces the count,
and handles failed images. It does not calculate prices, maintain a separate cart,
intercept purchase requests or use localStorage. Styles and this script are loaded
only on the basket page. No compatibility/backend fix was needed.

## Verification

- `manage.py check`: no issues.
- `manage.py test --noinput`: **131 tests passed**, including 13 new basket tests.
- Regression coverage includes real CSRF-protected updates, AJAX partials, ordinary
  non-JavaScript POSTs, zero quantity and explicit removal, stock/quantity errors,
  missing management fields, unavailable products, child products/options,
  inherited images, voucher application/removal, invalid codes, saved-item
  movement/removal, paid shipping totals, checkout redirects and style isolation.
- Headless Chrome checked **1440, 768, 390 and 320px** with actual catalogue
  photographs. Filled, multi-item, empty, expanded-voucher and stock-error layouts
  had no horizontal overflow. Desktop and mobile screenshots were inspected.
- Real browser quantity submission changed JOD102.000 to JOD204.000 and updated
  the shared header count from 1 to 2. Removal returned the real empty state and
  zero header count. Invalid vouchers, failed-image fallback and the existing
  checkout login redirect were verified. With page JavaScript disabled, the
  removal checkboxes and voucher form remained visible.
- Browser tests used a temporary copy of the database with additional stock for
  one test product; the working database and stock were not edited. Django tests
  used disposable test data/media and the existing isolated test search index.
- `node --check static/abdeen/js/basket.js` and `git diff --check`: passed.
- Before/after checksums confirmed existing settings, search, catalogue and
  product-detail implementation files were unchanged. Among existing files in
  the inspected source directories, only the basket template and the catalogue
  style-isolation test changed.

## Remaining limitations / existing behavior

- Missing product photographs use the existing placeholder; no product assets
  or inventory details were invented.
- The current shipping repository supplies free shipping, and checkout requires
  login. The redesign preserves both configurations; a paid shipping method is
  covered by an isolated regression test.
- Final order placement/payment was outside this basket-only redesign.
- The existing Whoosh query-faceting warning remains unrelated to this change.

## Files changed or created for this task

- `templates/oscar/basket/basket.html`
- `templates/oscar/basket/partials/basket_content.html`
- `templates/oscar/basket/partials/line_image.html`
- `templates/oscar/basket/partials/summary_totals.html`
- `static/abdeen/css/basket.css`
- `static/abdeen/js/basket.js`
- `config/test_basket.py`
- `config/test_catalogue.py` (shared-header expectation; isolation assertions retained)
- `docs/basket-redesign.md`

No Oscar package files, checkout templates, settings, search configuration,
catalogue/product-detail backend, basket views/forms/models, shipping repository
or business logic were changed. Other working-tree changes predate this task.
