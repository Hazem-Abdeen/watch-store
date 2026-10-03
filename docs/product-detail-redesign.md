# Product detail specifications and recommendations — 2026-10-03

## Current behavior

Explore specifications is now a native `details`/`summary` disclosure directly below the purchase controls, collapsed by default. It opens/closes with click, Enter or Space, including without JavaScript. The browser supplies native disclosure semantics; JavaScript also synchronizes `aria-expanded`, and `aria-controls`/`aria-labelledby` connect the summary and region. Only the chevron animates; reduced-motion preferences disable its transition. Specifications use two columns from 1024px and one column below that threshold.

The existing specification helper supplies the same real, non-empty watch attributes, including Guarantee, Country of Manufacture and additional useful facts such as Glass. It removes labeled specifications from descriptive prose and filters internal importer metadata. The standalone Product Details section has been removed. Stored product data is unchanged.

## Exact recommendation rules

1. Start with Oscar's `browsable()` products: public canonical products (standalone or parent), excluding the current product ID. Private products and individual child variants are never suggested.
2. Match real Brand and Gender attributes case-insensitively (text or single-option values), honoring Oscar's inherited attributes on the current child product.
3. Rank matching Brand AND Gender first, then matching Brand, then matching Gender, then any shared public non-brand category. If the current product has no Brand attribute, use its assigned brand category, including nested sub-brands, for brand matching. The generic Brands root is never a fallback match.
4. Take the first **32** candidates in relevance-tier/ascending-product-ID order. Within each tier in that bounded pool, prefer products that Oscar's existing request strategy says are available to buy; use product ID as the stable tie-breaker. Parent availability also comes from Oscar, using public children. No inventory formula is copied or changed.
5. Return at most **four** unique products. Fewer matches yield a smaller section; no matches hide only this section. Availability preference is deliberately limited to the 32-candidate pool, rather than scanning every matching product on each request.

You May Also Like appears before Recently Viewed. Oscar's old manually related-product markup is omitted from this page, without altering its stored relationships. Recently Viewed remains independent: Oscar still reads and updates its history cookie, excludes the current product, and supplies the order; the existing six-card presentation limit remains.

## Queries and shared cards

`Exists` subqueries match attributes/categories without multiplying rows, so products cannot be duplicated by overlapping criteria or multiple assignments. The candidate query is SQL-limited to 32. Product classes are joined, and stock records, images, public categories, and public children/child stock records are bulk-prefetched. Option existence and the real Brand label are annotated, avoiding per-card option/attribute queries. Recently Viewed bulk-loads the same card dependencies while retaining Oscar's selection/order. Specification attributes and option values are also fetched together, avoiding per-attribute lookups.

Both sections include **`templates/oscar/partials/products/card.html`**, the same open card used by Shop, Best Sellers and New Arrivals. There is no duplicated card markup: large image, Brand, complete title, Oscar price formatted in JOD, simple availability, and a whole-card link. No ratings, bordered Oscar cards or cart buttons are added.

## Verification for this change

- Django checks and all **220 tests** pass.
- Recommendation tests cover all relevance tiers, category-only fallback, mixed-case attributes, current-product exclusion, deduplication, public canonical products, stable ordering, four-item maximum, fewer/zero matches, allocated stock, parent availability, history independence, and removal of old manual recommendation markup.
- Query regression test: no more than nine queries for recommendation selection with 37 matching fixtures, SQL limit of 32, and **zero additional database queries while rendering the four selected cards**.
- Chrome at **1440, 768, 390 and 320 pixels** passes click/keyboard open and close, ARIA state/relationships, specification column count, absence of the old section, recommendations/history order, shared open cards, and overflow checks. No JavaScript errors. Screenshots visually inspected at all four widths.
- Existing gallery, purchase, quantity validation, staff permissions and no-JavaScript purchase checks pass. Browser tests and their purchase writes use a disposable database copy.
- JavaScript syntax and `git diff --check` pass.

## Files changed for this change

1. `catalogue_import/recommendations.py`
2. `catalogue_import/templatetags/recommendation_tags.py`
3. `catalogue_import/templatetags/storefront_tags.py`
4. `templates/oscar/catalogue/detail.html`
5. `templates/oscar/customer/history/recently_viewed_products.html`
6. `static/abdeen/css/product-detail.css`
7. `static/abdeen/js/product-detail.js`
8. `config/test_recommendations.py`
9. `config/test_product_detail.py`
10. `tests/browser/product-detail.cjs`
11. `docs/product-detail-redesign.md`

No Oscar package files, product models/data, catalogue backend, Whoosh/search settings, basket behavior, pricing policies or stock calculations were changed. `homepage/brands.py` was inspected and its existing brand-root constant reused without editing it. Unrelated workspace changes were preserved.

---

# Previous purchase summary redesign — 2026-10-03

The current summary order is the real Brand attribute, Oscar title, customer partner SKU when usable, Oscar price, shipping note, availability, full-width Add to Cart, and quantity. Staff editing is below the purchase area. Product Details contains the existing deduplicated specifications, including the actual Guarantee when supplied. Meaningful prose remains separate. Recently Viewed uses the shared open cards and centered homepage section heading. The gallery retains its full-size links, multiple images, keyboard navigation and fallback.

## Inventory audit and exact wording

The read-only catalogue audit found **731 stock records, all mapped to imported products: 710 with `num_in_stock=1`, 21 with `num_in_stock=0`, and no allocations**. `catalogue_import/catalogue.py` assigns `1` for WooCommerce `instock` and `0` otherwise. Import bookkeeping stores the legacy stock status but no reliable physical-count provenance. Consequently **neither 1 nor 2 is trusted as an exact remaining quantity**, and no product receives low-stock wording.

The product summary uses Oscar's selected purchase information, in this order:

1. `availability.is_available_to_buy` → **In stock, ready to ship**.
2. Otherwise `availability.code == 'outofstock'` → **Out of stock**.
3. Otherwise → **Unavailable**, including a missing stock record. Parent products retain Oscar's variant-selection behavior.

This respects Oscar's net stock/allocation and product-class policies. It does not compare raw inventory in the template or expose counts in HTML/JavaScript. Shared card and basket wording remains unchanged. Before enabling **Low stock — X items left**, add an explicit, maintained per-stock-record indication that inventory is an audited physical count, record its provenance, reconcile stock and allocations, and update the import process so placeholder status values cannot overwrite verified inventory. Only then could the selected record's available quantity support exact wording. No such schema or importer change is included here.

## SKU, price, shipping and quantity

- SKU comes exclusively from the **selected Oscar stock record's `partner_sku`**. Blank values, the importer's synthetic `ABDEEN-<source ID>` pattern and internal/import/migration-prefixed identifiers are hidden. UPC, database identifiers and source metadata are never fallbacks. The reserved synthetic pattern is conservatively hidden even without an import mapping.
- Oscar's price and currency remain authoritative, using the existing compact JOD formatter. Known tax uses `incl_tax`; otherwise `excl_tax`, as before. Legacy regular/sale price metadata is not used to fabricate a crossed-out price or discount; Oscar basket offers remain unchanged.
- **Tax included is intentionally omitted.** The configured default Oscar strategy uses zero tax, which does not establish a tax-inclusive retail business policy.
- **Shipping calculated at checkout.** is plain text. The project has no shipping-policy route or flatpage to link.
- `{% basket_form request product 'multiple' %}` selects Oscar's existing `AddToBasketForm`. The real field, bound values, CSRF, required options and errors are retained. Minus/plus buttons operate only on that number input; it also works without JavaScript. Minimum/step constraints come from the form. Oscar validates actual availability, quantities already in the basket and basket thresholds on POST. An excessive request is rejected with a count-free error. No stock-based `max` or client-side inventory data is added for these unreliable quantities.
- Reviews and wishlists remain hidden by the pre-existing storefront setting; their backend functionality is preserved. There is no Buy It Now flow.

## Current verification

- Django system checks pass; **206 tests pass** across the full project suite.
- CSS production build, JavaScript syntax and whitespace checks pass.
- Chrome at **1440, 768, 390 and 320 pixels**: no horizontal overflow or JavaScript errors; inspected desktop, tablet and mobile screenshots.
- Imported in-stock product, existing out-of-stock catalogue product, specifications/guarantee, mixed prose, missing description, usable/hidden SKU, missing stock/image, and multiple-image keyboard selection are covered.
- Real Add to Cart, keyboard-operable quantity controls, minimum quantity, excessive quantity rejection, successful two-item purchase on a controlled fixture, retained form values and no-JavaScript purchase are covered.
- Recently Viewed shared cards, centered heading, whole-tile keyboard links, normal customer, staff and superuser views are verified.
- QA fixtures and basket writes use a disposable database copy. Store inventory is untouched.

## Files changed for this request

1. `catalogue_import/templatetags/storefront_tags.py` — customer partner-SKU filter.
2. `templates/oscar/catalogue/detail.html` — summary order, Brand attribute priority, SKU, Product Details title and staff-link placement.
3. `templates/oscar/catalogue/partials/stock_record.html` — detail-only shipping note and ready-to-ship wording.
4. `templates/oscar/catalogue/partials/add_to_basket_form.html` — Oscar's quantity-enabled form and retained option/error rendering.
5. `templates/oscar/catalogue/partials/quantity_field.html` — new accessible enhancement of the real quantity field.
6. `templates/oscar/customer/history/recently_viewed_products.html` — shared centered section heading.
7. `assets/styles/product-card.css` — Recently Viewed heading typography.
8. `static/abdeen/css/product-detail.css` — summary spacing, typography, stock dot and quantity controls.
9. `static/abdeen/js/product-detail.js` — progressive quantity buttons; existing gallery behavior retained.
10. `static/abdeen/css/tailwind.css` — regenerated CSS output (already gitignored).
11. `config/test_product_detail.py` — summary/data/stock/quantity regressions.
12. `tests/browser/product_detail_preview.py` — isolated QA fixtures.
13. `tests/browser/product-detail.cjs` — responsive and functional browser checks.
14. `docs/product-detail-redesign.md` — audit, behavior, verification and file manifest.

`config/settings.py` was inspected but **not changed by this request**. No Oscar package files, stock quantities, pricing calculations, basket validation, checkout/payment, catalogue/search backend, models or migrations were changed. Existing unrelated workspace edits were preserved.

---

## Previous presentation cleanup (historical)

The product page uses the existing Abdeen gallery, typography, whitespace and shared storefront cards. Brand, title, real Oscar price, stock status and Add to Cart remain prominent. Stock alerts remain available for unavailable products. Staff-only editing retains the authenticated staff guard.

Availability is rendered as In stock, Out of stock or Unavailable. Exact stock quantities are omitted from product cards, product details, basket/saved-basket status, basket input limits and the installed Oscar stock-validation messages. Ordered/cart quantities remain visible. Checkout summaries retain their existing local templates, which do not expose inventory counts. Backend stock validation still rejects excessive quantities.

The expandable pricing/availability breakdown is removed. Structured watch specifications appear once with readable labels. Explicit labeled facts in legacy descriptions (including Glass, Thickness and Country of Manufacture) join that section; structured values take precedence. Genuine prose remains in its own section, and empty/specification-only descriptions have no description section. Internal metadata and legacy WordPress media shortcodes are omitted from this presentation, including generated page-description metadata. Stored descriptions and attributes are untouched.

Recently viewed products keep Oscar's history cookie, selection/order and six-item limit. They use the existing shared card partial and its image sizing, hover, title, brand, price and full-item link. They contain no ratings, wishlist controls or cart buttons.

## Business behavior and restoration

No Oscar package files, models, migrations, stock records, allocation rules, basket validation, checkout/order/payment logic, search configuration or catalogue query behavior were changed. Python changes are presentation helpers only. JOD amounts use a display format such as `102 JOD` or `125.5 JOD`, without changing stored Decimals, tax calculation or currency selection. This Oscar formatting setting also applies wherever its currency template filter is used, including dashboard displays; dashboard stock quantities remain available.

`ABDEEN_STOREFRONT_HIDDEN_FEATURES = ('reviews', 'wishlists')` gates local templates. Unlike Oscar's application-hiding setting, it does not unregister feature routes. Remove a name from this tuple to restore that feature's controls, navigation and bookmarked pages. Models, endpoints and permissions remain intact. Regression tests exercise restored review submission and wishlist add/remove. Existing unrelated workspace changes have been preserved.

## Previous verification

- Django system check: no issues.
- Complete Django suite: **201 tests passed** after the final helper changes.
- CSS production build and `git diff --check`: passed.
- Headless Chrome: **1440, 768, 390 and 320 pixels**, all passed with no horizontal overflow or JavaScript errors.
- Five browser states at each width: in stock, out of stock, unavailable, missing description and mixed prose/specifications.
- Real product images; shared recently viewed layout; full-item keyboard navigation and hover behavior verified.
- Add to Cart persisted a basket line; an excessive basket quantity displayed a count-free error and was rejected by Oscar.
- Anonymous and ordinary customer views hide editing; staff and superuser views show it. Django tests also check dashboard access.
- Wishlist/review controls, Customer Reviews, numeric stock messages and the price/availability disclosure are absent.
- Browser fixtures operate on a disposable SQLite backup, never the store database. Test-only login endpoints are never installed in production URLs.

Run the preview with the project's Python interpreter: `tests/browser/product_detail_preview.py`; then run `tests/browser/product-detail.cjs` with Playwright available. The default preview address is `http://127.0.0.1:8021`. Screenshots are written to `/tmp/abdeen-detail-qa` (override with `SCREENSHOT_DIR`).

## Previous cleanup file manifest (37)

| File | Purpose |
| --- | --- |
| [config/settings.py](../config/settings.py) | Presentation feature switch and compact JOD currency formatting. |
| [catalogue_import/templatetags/storefront_tags.py](../catalogue_import/templatetags/storefront_tags.py) | Quantity-free availability/errors and a read-only description/specifications view. |
| [catalogue_import/templatetags/storefront_display_tags.py](../catalogue_import/templatetags/storefront_display_tags.py) | Optional UI gates that preserve Oscar feature routes and dashboard controls. |
| [assets/styles/product-card.css](../assets/styles/product-card.css) | Extend the shared product-card styles to recently viewed products. |
| [static/abdeen/css/product-detail.css](../static/abdeen/css/product-detail.css) | Refine the summary, availability and specifications; remove obsolete component styles. |
| [static/abdeen/css/tailwind.css](../static/abdeen/css/tailwind.css) | Rebuilt stylesheet containing the shared card styles. |
| [templates/oscar/catalogue/detail.html](../templates/oscar/catalogue/detail.html) | Clean summary, safe metadata, conditional prose and one specifications area. |
| [templates/oscar/catalogue/partials/stock_record.html](../templates/oscar/catalogue/partials/stock_record.html) | Real Oscar prices and quantity-free availability. |
| [templates/oscar/catalogue/partials/add_to_basket_form.html](../templates/oscar/catalogue/partials/add_to_basket_form.html) | Retain the original form and alert logic; gate wishlist UI and label the button Add to Cart. |
| [templates/oscar/catalogue/partials/product.html](../templates/oscar/catalogue/partials/product.html) | Hide review stars on inherited listing/search cards. |
| [templates/oscar/partials/products/card.html](../templates/oscar/partials/products/card.html) | Use quantity-free status in the shared homepage/catalogue/recent-history card. |
| [templates/oscar/customer/history/recently_viewed_products.html](../templates/oscar/customer/history/recently_viewed_products.html) | Reuse shared open cards without changing Oscar history selection or its six-item limit. |
| [templates/oscar/basket/partials/basket_content.html](../templates/oscar/basket/partials/basket_content.html) | Keep basket controls/totals while hiding availability quantities, input stock limits and stock-error counts. |
| [templates/oscar/partials/form_field.html](../templates/oscar/partials/form_field.html) | Redact stock counts in rendered field errors. |
| [templates/oscar/partials/form_fields_inline.html](../templates/oscar/partials/form_fields_inline.html) | Redact stock counts in inline form errors. |
| [templates/oscar/partials/messages/alert.html](../templates/oscar/partials/messages/alert.html) | Redact stock counts in storefront alerts, preserving escaping and other messages. |
| [templates/oscar/partials/home/footer.html](../templates/oscar/partials/home/footer.html) | Gate the wishlist link. |
| [templates/oscar/customer/partials/standard_tabs.html](../templates/oscar/customer/partials/standard_tabs.html) | Gate the account wishlist navigation. |
| [templates/oscar/customer/anon_order.html](../templates/oscar/customer/anon_order.html) | Gate review links in guest order pages. |
| [templates/oscar/customer/order/order_detail.html](../templates/oscar/customer/order/order_detail.html) | Gate review links in customer order details. |
| [templates/oscar/catalogue/reviews/review_detail.html](../templates/oscar/catalogue/reviews/review_detail.html) | Hide bookmarked review UI while preserving the original view/backend. |
| [templates/oscar/catalogue/reviews/review_list.html](../templates/oscar/catalogue/reviews/review_list.html) | Hide bookmarked review UI while preserving the original view/backend. |
| [templates/oscar/catalogue/reviews/review_form.html](../templates/oscar/catalogue/reviews/review_form.html) | Hide bookmarked review UI while preserving the original view/backend. |
| [templates/oscar/customer/wishlists/wishlists_list.html](../templates/oscar/customer/wishlists/wishlists_list.html) | Hide bookmarked wishlist UI while preserving the original view/backend. |
| [templates/oscar/customer/wishlists/wishlists_detail.html](../templates/oscar/customer/wishlists/wishlists_detail.html) | Hide bookmarked wishlist UI while preserving the original view/backend. |
| [templates/oscar/customer/wishlists/wishlists_form.html](../templates/oscar/customer/wishlists/wishlists_form.html) | Hide bookmarked wishlist UI while preserving the original view/backend. |
| [templates/oscar/customer/wishlists/wishlists_delete.html](../templates/oscar/customer/wishlists/wishlists_delete.html) | Hide bookmarked wishlist UI while preserving the original view/backend. |
| [templates/oscar/customer/wishlists/wishlists_delete_product.html](../templates/oscar/customer/wishlists/wishlists_delete_product.html) | Hide bookmarked wishlist UI while preserving the original view/backend. |
| [templates/oscar/partials/feature_unavailable.html](../templates/oscar/partials/feature_unavailable.html) | Shared neutral fallback for hidden feature pages. |
| [config/test_product_detail.py](../config/test_product_detail.py) | Cover display cleanup, data preservation, purchase/feature restoration and staff permissions. |
| [config/test_basket.py](../config/test_basket.py) | Expect the new stock label and confirm errors do not expose stock limits. |
| [config/test_catalogue.py](../config/test_catalogue.py) | Expect the explicit Out of stock label. |
| [config/test_search.py](../config/test_search.py) | Expect the explicit Out of stock label. |
| [config/tests.py](../config/tests.py) | Expect the explicit Out of stock label on homepage cards. |
| [tests/browser/product_detail_preview.py](../tests/browser/product_detail_preview.py) | Disposable database preview fixture; no production inventory writes. |
| [tests/browser/product-detail.cjs](../tests/browser/product-detail.cjs) | Automated viewport, purchase, permissions, history, hover and keyboard checks. |
| [docs/product-detail-redesign.md](../docs/product-detail-redesign.md) | Current behavior, verification and complete file manifest. |
