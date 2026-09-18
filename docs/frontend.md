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
| Homepage | No built-in homepage template in this installation; our local `oscar/home.html` is served at `/` |
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

Store metadata uses `OSCAR_SHOP_NAME = 'Abdeen Watches'` and `OSCAR_HOMEPAGE = '/'`.
`OSCAR_DEFAULT_CURRENCY = 'JOD'` sets the default currency, including the empty
basket display. Existing stock record amounts and currencies are not converted.
The project URL configuration serves the homepage with `HomepageView`, a Django
`TemplateView` subclass,
before the Oscar URL include. Oscar's catalogue and all commerce views, forms,
models and namespaces remain intact.

## Build CSS manually

With Node.js and npm installed, run these commands from the project root:

```bash
cd /home/user/watch-store
npm ci
npm run build:css
```

For ongoing template work, keep this running in a separate terminal:

```bash
cd /home/user/watch-store
npm run dev:css
```

The homepage implementation was compiled with the existing installed Tailwind
dependencies using `npm run build:css`. The generated stylesheet is ignored by
Git, so clean checkouts must run the commands above. `package-lock.json` is
already tracked. No React or Vite dependencies are needed.

`package.json` is build tooling for Django's static files, not a separate app.
The CSS-first Tailwind configuration is `assets/styles/tailwind.css`, so there
is no `tailwind.config.js` or PostCSS setup. It explicitly scans `templates/`
and `static/abdeen/js/`. Write complete literal classes such as `tw:py-4` and
`tw:md:flex`; do not construct fragments such as `tw:bg-{{ color }}-500`.

Utilities and theme variables use the `tw` prefix to avoid Oscar class names.
Preflight is omitted to preserve existing Bootstrap form and page styling.
Utilities are deliberately unlayered to coexist with Oscar's unlayered CSS.
Retain Oscar's Bootstrap/jQuery scripts until their dependent UI has been
migrated. Shared custom interaction belongs in `static/abdeen/js/storefront.js`;
homepage range filtering lives in `static/abdeen/js/homepage.js`. Both use
vanilla JavaScript. Homepage styles in `assets/styles/homepage.css` are imported
by Tailwind and scoped to `.abdeen-home`, preserving Oscar page styling.

Django discovers `static/` through `STATICFILES_DIRS`. Before a deployment, run
the CSS build before `python manage.py collectstatic`; generated CSS and
`staticfiles/` are ignored by Git. Use the project's virtual environment for
Django commands. No frontend packages are needed for `manage.py check`.

References: [Tailwind CLI](https://tailwindcss.com/docs/installation/tailwind-cli),
[Preflight and prefixes](https://tailwindcss.com/docs/preflight#disabling-preflight),
[source detection](https://tailwindcss.com/docs/detecting-classes-in-source-files).

## Homepage catalogue integration

`config/urls.py` matches the exact empty path before including Oscar's URLs.
`HomepageView` in `config/homepage.py` renders `templates/oscar/home.html`.
`reverse('home')` and `OSCAR_HOMEPAGE` remain `/`; `/catalogue/` remains
Oscar's catalogue. The existing homepage partials, header, footer, CSS layout,
responsive grids and JavaScript build setup are preserved.

The inspected database had **no products, categories, ranges, product types,
attributes or stock records**, and the project has no Brand/Manufacturer model
or custom catalogue app. No production data is created by this integration.
Missing or empty collections render explanatory empty states and catalogue links.

### Best Sellers and New Arrivals

Both use the same `range_products(name)` helper, called with the exact,
case-sensitive names `Best Sellers` and `New Arrivals`, respectively.

1. Find the named Oscar `offer.Range`. Missing ranges return an empty list.
2. Start from Oscar's `range.all_products().browsable()`, preserving Oscar's
   exclusion rules and excluding non-public products and child variants.
3. Restrict membership to that range's explicit `RangeProduct` rows. Automatic
   all-products, product-type or category membership never fills the homepage.
4. Order by that range's `RangeProduct.display_order`, then product primary key
   for ties. A correlated subquery keeps another range's order from affecting it.
5. Load at most eight products per section, with images, stock records, product
   classes, public children and browsable categories prefetched as appropriate.

No analytics score, creation date, Product boolean, hardcoded product list,
fallback query or database write is used. A range's `is_public` flag controls
Oscar's separate range page; these two explicitly named homepage collections can
also use internal (non-public) ranges. Product visibility is always enforced.
Unavailable products remain visible with Oscar's availability message.

### Manual dashboard steps

1. Sign in at `/dashboard/` as a superuser or staff member with range/catalogue
   permissions. Because the database is empty, first create a product type under
   **Catalogue → Product Types**, then add real products under
   **Catalogue → Products**.
2. For each product, enable **Is public**, set a unique **UPC** under
   **Product details**, upload photos under **Images**, and complete
   **Stock and pricing** with the fulfilment partner, partner SKU, JOD currency,
   price and stock quantity. Create a real fulfilment partner if none exists.
   For variant families, assign a UPC to the **parent** and add that parent to
   the range; stock/prices belong on its public children.
3. Go to **Catalogue → Ranges** (`/dashboard/ranges/`).
4. Click **Create new range**. Enter exactly **Best Sellers**.
5. Leave **Includes all products?** unchecked and leave **Included Categories**
   and **Excluded Categories** empty. **Is public?** is optional for the homepage;
   check it only if you also want Oscar's separate public range page.
6. Click **Save and edit products**.
7. On **Products in range**, paste actual identifiers into **Product SKUs or
   UPCs**, separated by commas, spaces or newlines. Alternatively upload a file,
   comma-separated or one identifier per line. Click **Go!**.
8. Check the added rows and any unknown/duplicate identifier messages. Use the
   **Re-order** drag handles to arrange the products; Oscar saves their display
   order. The first eight eligible products appear on the homepage.
9. Repeat steps 4–8 with the exact name **New Arrivals**.
10. For subsequent changes, return to **Catalogue → Ranges → Actions → Edit
    products**. Add identifiers with **Go!**, drag to reorder, or select rows
    and click **Remove selected products**. The **Products excluded from range**
    tab manages explicit exclusions. Refresh `/` to see the changes.

Do not enable automatic inclusion rules for these two ranges. Do not add only
child variant SKUs: homepage cards use public standalone products and parent
families, just like Oscar's browsable catalogue. Add the parent's UPC instead.
Keep the exact range names; renaming one makes its section empty until restored.

### Pricing, availability, URLs and images

The product card receives an actual Oscar `Product` and uses
`{% purchase_info_for_product request product as purchase %}`.
Oscar's tag calls `request.strategy.fetch_for_product(product)`, or
`fetch_for_parent(product)` for a parent family. The strategy selects stock
records and pricing/availability policies; the view never reads a raw
stock-record price to construct a display price.

When the policy provides a **JOD** price, the card renders the tax-inclusive
amount if tax is known, otherwise the tax-exclusive amount labeled “excl. tax”.
Oscar's `currency` filter formats it using the policy's currency, including zero
prices. For another currency the card says “JOD price unavailable”; it does not
relabel or convert an amount. Missing prices say “Price unavailable”.
Availability text comes from `purchase.availability.short_message`. Parent
cards show the strategy-selected price, not an independently calculated minimum.

Image/title/CTA links use `product.get_absolute_url()`. Buttons say **View
Details** or **Choose Options**, leading to Oscar's existing purchase forms.
Hearts remain decorative; no cart or wishlist action is simulated.

Cards use `product.primary_image()` and its uploaded storage URL. Missing images
use `static/abdeen/images/watch-placeholder.svg`. JavaScript also replaces broken
storage images with that fallback. Images retain the current fixed aspect ratio
and sizing. No thumbnails are written during rendering.

### Categories and category images

The category section shows the first four public, menu-visible **root
categories** in Oscar tree order, excluding the reserved root with slug
`brands`. Private categories, private ancestors and menu-excluded branches
are filtered by Oscar's `Category.objects.for_menu()`.

Cards use the real category name, description and `get_absolute_url()`.
Oscar 4.2 already provides `Category.image` and its dashboard upload field, so
no model change is needed. Under **Catalogue → Categories**, create/edit the
category and upload its **Image**. Use approved portrait-friendly imagery;
the existing 320px-tall card crops it with `object-fit: cover`.
Missing images use the neutral watch fallback and an **Image coming soon**
label. No fake category cards are inserted when the database is empty.

### Brands without a new model

There was no existing brand representation to reuse. The current browseable
brand approach uses **Oscar categories**, not fulfilment partners or a new model:

1. Under **Catalogue → Categories**, create a public top-level category named
   **Brands**, with slug exactly `brands`; leave **Exclude from menu** unchecked.
2. Create each real brand as an immediate child of Brands, public and visible in
   the menu. Its name and description supply the brand card. Use approved brand
   names/descriptions, not the old reference list.
3. Edit a product's **Categories** tab and assign both its shopping department
   (for example, a watches category) and its brand child category. For a product
   family, put these categories on the parent.

The brand section shows up to eight immediate brand children in tree order;
cards link to those categories' existing Oscar catalogue pages. Product cards
display directly assigned, visible brand child names (or the product type when
none is assigned). No fake model counts, origin, history or authorisation claims
are shown. If multiple brand categories are assigned, their names are joined.
Best Sellers filter pills derive from real assigned categories, including brands;
they only filter the eight already-loaded cards, not the full catalogue.

This is a navigation convention and adds no catalogue business logic. If richer
manufacturer metadata is required later, Oscar product attributes are available;
there is no need to invent a Brand model now or mislabel a fulfilment Partner as
a manufacturer. A separate brand facet can be considered when search is expanded.

### Section mapping and remaining static content

All paths below are under `templates/oscar/partials/home/`:

| Google Studio section | Django partial | Current content |
| --- | --- | --- |
| HeroSection | `hero.html` | Static neutral copy and illustrative Unsplash image; real links/section anchor |
| CategorySection | `categories.html` | Real root categories and uploads; labeled image fallback where needed |
| BrandSection | `brands.html` | Real child categories under Brands; no placeholder brand list |
| BestSellersSection | `best_sellers.html` | Manually selected Best Sellers range products |
| NewArrivalsSection | `new_arrivals.html` | Manually selected New Arrivals range products |
| PromoBannerSection | `promo_banner.html` | Static editorial copy and illustrative watch photography, not an active promotion or store photo |
| WhyChooseSection | `why_choose.html` | Static descriptions of browsing, catalogue, basket and account features |
| NewsletterSection | `newsletter.html` | Disabled signup placeholder; no email collection or endpoint |

Shared `product_card.html`, `section_heading.html`, `service_card.html` and
`icon.html` remain. The existing announcement slot, header/navbar and footer
are unchanged. Hero/editorial photographs and Google Fonts remain externally
hosted. Only missing-image assets and the newsletter are functional placeholders;
homepage copy/section headings, icons and decorative hearts are static content.

### Verification and next work

Run `python manage.py check` and `python manage.py test config --noinput` in
the project virtual environment. Tests use an isolated test database and cover
missing/empty ranges, independent ordering, explicit exclusions, manual-only
membership, eight-card limits, product privacy, parent strategy, JOD/foreign
currency, known/unknown tax, zero prices, category/brand links and Oscar routes.

After catalogue entry and manual merchandising, replace the remaining editorial
photos with approved assets and connect newsletter signup separately. Any future
direct add-to-basket or wishlist controls must reuse Oscar's forms and CSRF
protection; the current product-page links already use Oscar's existing flow.
