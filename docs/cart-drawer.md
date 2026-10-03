# Cart drawer — 2026-10-03

Successful Add to Cart submissions now open a white cart drawer from the right,
over a dimmed page. The storefront header cart icon opens the same drawer. At
desktop sizes the panel is 500px wide; smaller screens use the available width.
Items scroll independently of the checkout footer. The drawer includes images,
brand, title, selected options, line totals, quantity controls, removal, an empty
state, a shopping-bag link and checkout with the current basket total. Discounts
and crossed-out prices appear only when supplied by Oscar.

The native modal supports Escape, backdrop/close-button dismissal, focus
containment, focus return and reduced motion. Failed add validation stays beside
the original form. Failed quantity validation appears inside the drawer and
reloads the actual persisted quantities. Requests are serialized, controls are
temporarily inert, and failed writes are never automatically retried. Network
errors offer the full shopping bag to check the current state.

`CartDrawerView` subclasses Oscar's existing `BasketView` for a GET-only,
non-cacheable HTML fragment. Additions still POST to `basket:add`, and quantity
changes/removals POST the original formset contract to `basket:summary`. Oscar
owns CSRF, sessions, forms, stock validation, options, offers, taxes and totals.
The full basket page is also refreshed when changes are made from its drawer.
Without JavaScript (or dialog support), the original form and cart link work.
Checkout's separate layout retains its normal cart navigation.

No settings, Oscar package files, product data, pricing/stock policies, payment
logic, models or migrations were changed by this request. The existing unrelated
workspace edits remain intact.

## Validation

- Django system checks and all 225 project tests pass.
- New server tests cover GET-only/private output, real add/update/remove,
  session isolation, CSRF, stock rejection, selected options and Oscar discounts.
- Chrome checks pass at 1440, 768, 390 and 320px: add without navigation,
  quantities, invalid stock, removal, header count, persistent cart, checkout
  navigation, underlying shopping-bag synchronization, keyboard, dismissal and
  no horizontal overflow. No JavaScript errors.
- Network-failure recovery and ordinary no-JavaScript purchase pass.
- Screenshots inspected at desktop and mobile sizes; output in
  `/tmp/abdeen-cart-qa`. Browser purchases use `product_detail_preview.py` and its
  disposable database copy, never the store database.
- JavaScript syntax and `git diff --check` pass.

## Files changed by this request

1. `config/cart.py`
2. `config/urls.py`
3. `config/test_cart_drawer.py`
4. `templates/oscar/layout.html`
5. `templates/oscar/partials/home/header.html`
6. `templates/oscar/catalogue/partials/add_to_basket_form.html`
7. `templates/oscar/basket/partials/drawer.html`
8. `templates/oscar/basket/partials/drawer_content.html`
9. `static/abdeen/css/cart-drawer.css`
10. `static/abdeen/js/cart-drawer.js`
11. `tests/browser/cart-drawer.cjs`
12. `docs/cart-drawer.md`

The reference's gift-wrap and order-note features are not included; no such
checkout functionality was requested. Existing selected product options are
displayed. Voucher entry and saved-for-later remain on the full shopping-bag
page. The drawer uses HTML responses from Oscar plus a refreshed fragment for
updates; it does not maintain a separate client-side cart or pricing system.
