# Editorial categories and premium storefront alerts

## Presentation changes

The homepage Men and Women showcase uses borderless 4:3 photographs with
HTML copy overlaid on the left side: a small collection label, serif title,
subtitle, and an understated Explore Collection link. A light warm gradient
behind the copy preserves contrast without darkening the subjects. Each entire composition is one
accessible link. Desktop/tablet use two columns; screens below 640px stack them.
Hover gently enlarges the image and moves the arrow; reduced motion disables
both effects. Focus remains visible for keyboard navigation.

The partial still uses `homepage_categories` and `category.get_absolute_url`.
Only the existing `men` and `women` categories are shown in this showcase.
The homepage view, category query, navigation, product filters, and other
homepage sections are unchanged. If neither category is supplied, the existing
browse-all fallback appears; no category or URL is manufactured.

## Images

Place or replace these files (they already exist locally):

- `static/abdeen/images/home/categories/men.jpg`
- `static/abdeen/images/home/categories/women.jpg`

The current JPEGs were converted from the provided PNGs at their original
1448 × 1086 dimensions, with no crop or baked-in copy. Use artwork without embedded text, preferably 4:3 landscape images at least
1200px wide. Other ratios are proportionally cropped with `object-fit: cover`,
never stretched. All titles, subtitles, and CTAs are HTML. These campaign files
are deliberately used instead of the catalogue category's media image.
Missing/failed image requests hide the broken image and expose a warm neutral
gradient; captions, dimensions, and the catalogue link remain intact.

## Messages

The actual shared message path is the local
`templates/oscar/partials/alert_messages.html`, which includes
`templates/oscar/partials/messages/alert.html`. It is already loaded by the
storefront layout and used by basket, catalogue, checkout, and account pages.
Its existing accessibility and dismissal behavior are retained.

`static/abdeen/css/messages.css` refines that component globally within
`#main-content`: restrained green/slate/amber/red states, more comfortable
spacing, 12px corners, larger icons, subtle shadows, and circular close-button
focus/hover treatment. Inline errors retain the same accessible field links.
Dashboard/email presentation is unchanged.

The local `templates/oscar/basket/messages/addition.html` extends Oscar's
original template and wraps `block.super` with a decorative bag/check icon.
Oscar retains its translated singular/plural message text, safe HTML tags,
message triggers, basket validation, CSRF, redirects, and database operations.
No new alert JavaScript was needed: existing Oscar/Bootstrap dismissal and the
project's existing accessibility enhancement remain in use.

## Build and test

CSS was rebuilt as part of this change. When editing `assets/styles/homepage.css`
again, run:

```sh
npm run build:css
```

This writes `static/abdeen/css/tailwind.css` (generated and gitignored).
`messages.css` is loaded directly and does not require compilation. Replacing
images needs no CSS rebuild. Include the usual static collection step when
deploying changes to an environment that uses collected static files.

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py test --noinput
```

The original refinement passed all **190 tests**. After the overlay update,
Django checks and all **14 homepage/category tests** pass. Coverage verifies real
category links, absent categories, static campaign paths, preserved homepage
context, and actual singular/plural add-to-basket messages with persisted
quantities. Existing tests still cover checkout, basket, catalogue, and account
behavior.

Browser checks use a temporary copy of the local SQLite DB. Start the existing
test fixture server, then run both scripts with Playwright available:

```sh
.venv/bin/python tests/browser/messages_preview.py
# Separate terminal:
node tests/browser/messages.cjs
node tests/browser/categories-and-basket.cjs
```

For a temporary Playwright installation, set `PLAYWRIGHT_MODULE` to its module
directory. Both scripts use `/usr/bin/google-chrome` by default; `CHROME_PATH`
can override it. The category/basket script expects the real local homepage to
contain Men/Women and at least one purchasable featured watch.

Both scripts pass at **1440, 768, 390, and 320px**, with no horizontal overflow
or browser JavaScript errors. Verified all four alert states, keyboard
dismissal/focus, AJAX messages, reduced motion, inline validation, both real
category routes, and successful real product-form submission followed by a
persisted basket line. Missing-image requests were deliberately blocked to
confirm no change in image-area height or card links.

The category/basket script was rerun after the overlay change at all four
widths. It also checks that every copy block stays inside its visual, that
the visual remains 4:3, and that no caption adds height beneath the image.
Current desktop/mobile captures are `docs/screenshots/category-overlay-desktop.png`
and `docs/screenshots/category-overlay-mobile.png`.

Screenshots are written to `/tmp/abdeen-editorial-screenshots/` (categories,
actual add-to-basket confirmations, and fallback) and
`/tmp/abdeen-message-screenshots/` (all alert states, login, checkout layout).
`SCREENSHOT_DIR` overrides either script's output directory.

For a manual check, open the homepage at each target width, follow each category
card, add an available product to the basket, dismiss its confirmation, and
submit an invalid voucher or login to inspect the error styling. Production
pages display only genuine Django/Oscar messages; sample messages exist solely
in the test fixture.

## Files changed in this refinement

- `templates/oscar/partials/home/categories.html`
- `templates/oscar/basket/messages/addition.html`
- `assets/styles/homepage.css`
- `static/abdeen/css/tailwind.css` (rebuilt, gitignored)
- `static/abdeen/css/messages.css`
- `static/abdeen/js/homepage.js`
- `config/test_homepage_categories.py`
- `config/test_messages.py`
- `config/tests.py`
- `tests/browser/categories-and-basket.cjs`
- `docs/homepage-categories-and-alerts.md`
- `docs/storefront-messages.md`

No backend, settings, model, dashboard, or Oscar package files were changed.
The artwork is unchanged; the overlay update adds JPEG copies at the requested
paths. All copy and gradients remain in HTML/CSS. Message styles and behavior
were not changed by the overlay update.
