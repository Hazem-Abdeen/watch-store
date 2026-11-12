# Storefront messages

Customer-facing messages use one compact Abdeen component: muted green for
success, Abdeen red for errors, amber for warnings, and slate for information.
Each state has a distinct icon, subtle border/background, and a readable link
style. Short messages size to their content; longer messages wrap within a
52rem maximum width and the available mobile width.

## Integration

- `templates/oscar/partials/messages/alert.html` is the shared component.
  It accepts `level`, `message`, optional `heading`, and `dismissible`.
- Local overrides of Oscar's flash, form, inline form, and field partials reuse
  the component and preserve validation conditions and original message text.
  The shipping-method template also uses it for its existing error loops.
- `templates/oscar/layout.html` loads `static/abdeen/css/messages.css` after
  page styles, and loads `static/abdeen/js/messages.js`.
- CSS is scoped to `#main-content`, including inherited `.alert`, `.errorlist`,
  and `.error-block` markup. Dashboard and email presentation are unaffected.
- JavaScript enhances existing and newly inserted Oscar alerts. Oscar's
  `oscar.messages` API still creates/clears AJAX messages, and Bootstrap still
  handles `data-dismiss="alert"`. No message engine or dismissal API is replaced.

Error alerts use `role="alert"`; other states use `role="status"`. Existing
dismiss controls become labeled native buttons with visible keyboard focus.
After keyboard dismissal, focus moves to a neighboring alert control or the
main content. Inline errors and help text have IDs matching Django's
`aria-describedby`; legacy field errors receive equivalent associations.
Reduced-motion preferences disable the alert fade transition.

Message text, triggering conditions, trusted `safe` HTML, extra message tags,
`noicon`, links, validation rules, and existing dismissibility are preserved.
There is no automatic dismissal. No Oscar package, backend, dashboard model,
basket, checkout, payment, catalogue, search, or account logic is changed.

## Verification

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py test --noinput
```

Result after the editorial-category/alert refinement: Django checks clean;
all 190 tests pass. The ten message tests cover
all four states, the danger alias, original text, safe/escaped HTML, extra tags,
empty messages, field/help-text associations, non-field errors, valid/hidden
fields, storefront asset loading, dashboard isolation, and actual login
validation and real singular/plural add-to-basket confirmations with persisted
basket quantities. See [the refinement notes](homepage-categories-and-alerts.md)
for the updated spacing, shadows, basket icon, category artwork, and browser checks.

Browser verification uses a temporary copy of the local SQLite database and
a test-only URL; it does not add production routes or modify the working DB:

```sh
.venv/bin/python tests/browser/messages_preview.py
# In another terminal, with Playwright available:
node tests/browser/messages.cjs
```

Optional environment variables: `PLAYWRIGHT_MODULE` (module path),
`CHROME_PATH` (defaults to `/usr/bin/google-chrome`), and `SCREENSHOT_DIR`
(defaults to `/tmp/abdeen-message-screenshots`).

Headless Chrome verification passes at 1440, 768, 390, and 320px. Document and
body widths equal each viewport width, with no horizontal overflow. Checks
cover state icons/roles, checkout layout, inline error associations, links,
keyboard focus and Enter/Space dismissal, Oscar AJAX creation/clearing,
reduced motion, real invalid login, and the checkout authentication redirect in
place at that time. [Customer accounts Phase 1](customer-accounts-phase1.md) enabled
guest checkout; the script now checks the native empty-basket redirect instead.
No browser JavaScript errors were recorded. Screenshots include all
four message layouts, mobile login, and mobile checkout layout.

## Files changed for this work

- `templates/oscar/layout.html`
- `templates/oscar/checkout/shipping_methods.html`
- `templates/oscar/partials/alert_messages.html`
- `templates/oscar/partials/messages/alert.html`
- `templates/oscar/partials/form_field.html`
- `templates/oscar/partials/form_fields.html`
- `templates/oscar/partials/form_fields_inline.html`
- `static/abdeen/css/messages.css`
- `static/abdeen/js/messages.js`
- `config/test_messages.py`
- `tests/browser/messages_preview.py`
- `tests/browser/messages.cjs`
- `docs/storefront-messages.md`
