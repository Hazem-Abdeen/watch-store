# Abdeen Watches frontend foundation

This project uses Django templates, Tailwind CSS 4 and vanilla JavaScript.
Oscar 4.2 continues to supply all commerce views, forms, routes and behavior.

## Installed Oscar template map

Paths below are relative to `oscar/templates/` in the installed package
(`.venv/lib/python3.12/site-packages/` in this checkout).

| Area | Oscar templates |
| --- | --- |
| Global HTML document | `oscar/base.html` |
| Shared storefront layout | `oscar/layout.html`, `oscar/layout_2_col.html`, `oscar/layout_3_col.html` |
| Header and navbar | Header markup in `oscar/layout.html`; `oscar/partials/brand.html`, `nav_accounts.html`, `nav_primary.html`, `mini_basket.html`, `search.html` |
| Footer | `oscar/partials/footer.html` |
| Homepage | No built-in homepage template in this installation; `home` redirects to `OSCAR_HOMEPAGE`, which defaults to the catalogue |
| Product listing | `oscar/catalogue/browse.html`, `oscar/catalogue/category.html`; cards in `oscar/catalogue/partials/product.html` |
| Product detail | `oscar/catalogue/detail.html`; Oscar can select product-specific templates first |
| Basket | `oscar/basket/basket.html`, `oscar/basket/partials/basket_content.html` |
| Checkout | `oscar/checkout/layout.html`, `checkout.html`, `gateway.html`, `shipping_address.html`, `shipping_methods.html`, `payment_details.html`, `preview.html`, `thank_you.html`, `nav.html`; footer in `oscar/partials/footer_checkout.html` |
| Dashboard | `oscar/dashboard/base.html`, `oscar/dashboard/layout.html` |

## Local overrides

`TEMPLATES[0]['DIRS']` already contains `BASE_DIR / 'templates'` and
`APP_DIRS` is enabled. Django searches this project directory before installed
app templates. A local file such as `templates/oscar/catalogue/browse.html`
therefore overrides the installed `oscar/catalogue/browse.html`.

An override can extend its own template name. Django skips the current file
when resolving that parent and loads the next matching template from Oscar.
This lets us override selected blocks and retain upstream behavior with
`{{ block.super }}`. The catalogue, basket and checkout files currently just
inherit their originals. Do not copy all of Oscar's templates into the project.

The local `base.html` keeps Oscar's document and script hooks. The local
`layout.html` adds the announcement slot, minimal navbar, semantic main region
and footer. Its inherited `content_wrapper` retains Oscar's `content` block,
messages, breadcrumbs and AJAX targets; the column layouts still work.
Checkout keeps its own layout, and the dashboard keeps its own CSS and scripts.
The dashboard does not load the storefront Tailwind or JavaScript assets.

The only store metadata change is `OSCAR_SHOP_NAME = 'Abdeen Watches'`.
No product data, views, forms, models or URL configuration were changed.

## Build CSS manually

With Node.js and npm installed, run these commands from the project root:

```bash
cd /home/user/watch-store
npm install
npm run build:css
```

For ongoing template work, keep this running in a separate terminal:

```bash
cd /home/user/watch-store
npm run dev:css
```

These commands have not been run as part of the foundation setup. The compiled
`static/abdeen/css/tailwind.css` does not exist until the first build; the browser
will return a 404 for that stylesheet until then. Oscar's existing CSS remains
available. `npm install` creates `package-lock.json`; commit it for reproducible
installs, and use `npm ci` on subsequent clean installs with the lockfile.

`package.json` is build tooling for Django's static files, not a separate app.
The CSS-first Tailwind configuration is `assets/styles/tailwind.css`, so there
is no `tailwind.config.js` or PostCSS setup. It explicitly scans `templates/`
and `static/abdeen/js/`. Write complete literal classes such as `tw:py-4` and
`tw:md:flex`; do not construct fragments such as `tw:bg-{{ color }}-500`.

Utilities and theme variables use the `tw` prefix to avoid Oscar class names.
Preflight is omitted to preserve existing Bootstrap form and page styling.
Utilities are deliberately unlayered to coexist with Oscar's unlayered CSS.
Retain Oscar's Bootstrap/jQuery scripts until their dependent UI has been
migrated; all new custom interaction belongs in `static/abdeen/js/storefront.js`
and should use vanilla JavaScript.

Django discovers `static/` through `STATICFILES_DIRS`. Before a deployment, run
the CSS build before `python manage.py collectstatic`; generated CSS and
`staticfiles/` are ignored by Git. Use the project's virtual environment for
Django commands. No frontend packages are needed for `manage.py check`.

References: [Tailwind CLI](https://tailwindcss.com/docs/installation/tailwind-cli),
[Preflight and prefixes](https://tailwindcss.com/docs/preflight#disabling-preflight),
[source detection](https://tailwindcss.com/docs/detecting-classes-in-source-files).

## Next: homepage

Use `templates/oscar/home.html`. It already extends the shared storefront layout
and has an empty `content` block. It is intentionally not connected to a route
yet: `/` still redirects to `/catalogue/`. When building the homepage, connect a
Django template view at `/` while retaining Oscar's named `home` URL and all
other Oscar URL namespaces. Do not use `catalogue/browse.html` for homepage-only
sections, as that also changes the real product listing.
