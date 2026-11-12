# Product reference / sale pricing

Oscar 4.2's `partner.StockRecord.price` remains the current selling price. The
optional `regular_price` is a reference price, on the same currency and tax basis.
For example, enter Price **95** and Regular price **120** in the dashboard's
product **Stock and pricing** tab. Product cards and detail pages show a crossed-out
120 JOD, an emphasized 95 JOD, and 21% OFF. Basket and order unit prices remain 95.

## Oscar extension points

The implementation follows Oscar's model/app override pattern:

- `config.partner.apps.PartnerConfig` inherits Oscar's app config and retains
  the `partner` label. `config.partner.models.StockRecord` subclasses
  `AbstractStockRecord` before importing the remaining Oscar partner models.
- Oscar's seven existing partner migrations were copied unchanged into
  `config/partner/migrations`. Migration
  `0008_stockrecord_regular_price_and_more` adds the nullable Decimal(12, 2)
  field and a database constraint requiring null or a positive value.
- Existing `config/dashboard.py` became `config/dashboard/__init__.py`, preserving
  its import path and homepage routes, and setting the fork's app name.
  `config.dashboard.catalogue` subclasses Oscar's dashboard catalogue config and
  `StockRecordForm`. A narrow template block override adds the adjacent column.
- No installed Oscar package files were changed.

References: [Oscar app forking](https://docs.oscarcommerce.com/en/latest/topics/fork_app.html)
and [model customisation](https://docs.oscarcommerce.com/en/latest/howto/how_to_customise_models.html).
These published guides are labelled 4.0; extension points were also checked against
the locally installed 4.2 source and exercised by integration tests.

## Display rules

Positive regular prices are valid even when equal to or below the current price.
This lets staff update prices independently without artificial ordering errors.
Only `regular_price > price` produces a markdown. Null regular prices and missing
current prices never produce a sale badge. Zero and negative regular prices are
rejected by validation and the database constraint.

`config/partner/pricing.py` obtains reference-price presentation by passing a
detached copy of the selected stock record through the same Oscar strategy. That
copy is never saved or passed to a basket. Both displayed amounts must have the
same currency and known/unknown tax status. Known taxes use inclusive amounts;
unknown taxes use exclusive amounts with an explicit label. The active default
strategy adds zero tax. Tests also cover fixed-rate and deferred tax strategies.

Percentage = `(displayed_regular - displayed_current) * 100 / displayed_regular`,
using Decimal throughout, rounded to an integer with `ROUND_HALF_UP`.
Thus 20.833... becomes 21. A reduction rounding to zero still shows the old/current
prices but omits a misleading 0% OFF badge.

Parent products do not advertise a single child's markdown because Oscar's parent
price may aggregate children. Individual standalone/child products use their
selected stock record. There is no live metadata lookup in the display path.

Both product cards and details include `partials/products/price.html`. Accessible
text identifies regular/current prices and explains the percentage; styling uses
nonbreaking amounts, wrapping groups, and a compact badge.

## Import and backfill policy

The WooCommerce importer keeps its existing source-authoritative current-price
policy: `_price` replaces `StockRecord.price` on re-import. This has **not** become
a general production price-sync policy; review its dry run before re-importing
after manual selling-price changes. The command now explicitly prints the policy.

`_regular_price` additionally fills `StockRecord.regular_price` only if it is null
and the source value is finite, positive, and representable by Decimal(12, 2).
Existing non-null reference prices are preserved, even if the source changes.
The existing metadata remains import traceability. Missing/zero regular values
do not fill the field. Existing source preflight validation still rejects malformed,
negative, or unrepresentable input rather than silently importing it.

Null is treated as unmaintained: clearing a regular price and then re-importing
can fill it again. No ownership marker or second sale-price field was introduced.

Existing products use an explicit, idempotent command rather than an automatic
data migration, allowing review of historical metadata before populating references:

```bash
.venv/bin/python manage.py backfill_regular_prices --dry-run
.venv/bin/python manage.py backfill_regular_prices
```

The command only considers the known Abdeen import source, matching product/stock
relationships, JOD stock records, and null reference prices. It rejects invalid,
nonfinite, nonpositive, overprecision, and overlength values. Updates use a
conditional database write to preserve values entered after its initial read.
Selling prices, stock counts, metadata, and order records are never updated.

During implementation the schema migration was applied and the backfill was run
**only in dry-run mode**: 731 eligible records, 0 skipped. All 731 current prices,
currencies, and inventory values were compared with the pre-migration backup and
were unchanged. Existing regular prices remain null until staff enter them or the
backfill/import is explicitly run.

## Offers and compatibility

Oscar Offers still calculate from the current selling price. The integration
tests verify 120 reference / 95 selling with an additional 10% offer produces
85.50 in the basket, checkout, order, and COD allocation. Campaign discount rules,
shipping, checkout, and order notifications were not changed. The product badge
describes the product markdown, not an additional basket offer.

When upgrading Oscar, reconcile upstream partner migrations and review the
dashboard stock-table block override. A future pricing strategy must honor
Oscar's `fetch_for_product(product, stockrecord=...)` contract to show an accurate
reference price; the current and tested built-in strategies do.

## Verification

- Migration applied; Django system check passed; no missing migrations.
- Full project regression run: 288 tests, 284 passed, 4 pre-existing failures.
  All four expect availability text already removed from product cards in the
  existing workspace. Re-running those four with the pre-change card price
  rendering reproduces the same failures. They were not altered by this work.
- Latest focused run: 95 sale-pricing/importer tests passed, including two added
  metadata-isolation/selected-stock tests after the full run.
- Full regression scope included catalogue, product detail, search, importer,
  basket, cart drawer, checkout, offer integrations, and order notifications.
- Real dashboard GET, form validation/save, and complete product-edit POST tested.
- Responsive Chrome checks passed at 1440, 768, 390, 320px for sale, null, equal,
  and lower reference prices on cards/details; no horizontal overflow or JS errors.
- Browser fixtures use disposable copies of the database and a separate search
  index; they do not create preview products in the working database.
- `npm run build:css` completed; compiled Tailwind CSS remains gitignored by the
  existing project policy and must be built during deployment.

Reproduce browser checks with the existing Playwright installation:

```bash
.venv/bin/python tests/browser/sale_pricing_preview.py
# In a separate terminal; set PLAYWRIGHT_MODULE if not locally installed:
node tests/browser/sale-pricing.cjs
```

## Files changed by this feature

- `config/settings.py` (two app-config substitutions only)
- `config/partner/{__init__,apps,admin,models,pricing}.py`
- `config/partner/migrations/` (unchanged upstream 0001–0007, init, new 0008)
- `config/dashboard.py` moved to `config/dashboard/__init__.py`
- `config/dashboard/catalogue/{__init__,apps,forms}.py`
- `templates/oscar/dashboard/catalogue/product_update.html`
- `templates/oscar/partials/products/{card,price}.html`
- `templates/oscar/catalogue/partials/stock_record.html`
- `assets/styles/product-card.css`
- `catalogue_import/templatetags/sale_price_tags.py`
- `catalogue_import/catalogue.py`
- `catalogue_import/management/commands/import_woocommerce_catalog.py`
- `catalogue_import/management/commands/backfill_regular_prices.py`
- `config/test_sale_pricing.py`
- `catalogue_import/tests/test_sale_pricing.py`
- `tests/browser/sale_pricing_preview.py`, `tests/browser/sale-pricing.cjs`
- `docs/sale-pricing.md`

Other pre-existing working-tree edits were preserved.
