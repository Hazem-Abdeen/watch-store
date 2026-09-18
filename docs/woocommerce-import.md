# WooCommerce catalogue import

The `import_woocommerce_catalog` command reads the local phpMyAdmin export as
data. It never executes the dump's SQL and has no connection to the old database.
The source defaults to `import-data/woocommerce_catalog.sql` under `BASE_DIR`.
Use `--sql-file /absolute/path/to/export.sql` for another local export.

From `/home/user/watch-store`, preview five products:

```bash
/home/user/watch-store/.venv/bin/python manage.py import_woocommerce_catalog --dry-run --limit 5
```

Import those five products, including attempted image downloads:

```bash
/home/user/watch-store/.venv/bin/python manage.py import_woocommerce_catalog --limit 5
```

Add `--skip-images` to import catalogue records without making image requests.
Rerunning without that flag will attempt missing images. Removing `--limit`
selects every published product; **the full import has not been run**.

## Scope and validation

- Only `wp_posts` rows with `post_type='product'` and `post_status='publish'`
  become Oscar products. Simple products are supported. Non-simple products
  are explicitly skipped; variations are not converted into standalone items.
- Only selected catalogue metadata, `product_cat`, `pa_gender`, product type,
  and referenced thumbnail attachment paths are used. No users, customers,
  orders, comments, credentials, WordPress pages, blog posts, or menus are imported.
- `wp_wc_product_meta_lookup` is syntax-checked but not used: `_price`, `_sku`
  and `_stock_status` are authoritative. Cached sales, ratings, and quantities
  from the lookup table are not imported.
- This parser supports the observed phpMyAdmin format: INSERT statements with
  explicit column names, multi-row VALUES, numbers, NULL, quoted Unicode text,
  MySQL backslash escapes, and doubled single quotes. DDL/SET/transaction
  statements are ignored. Expressions, INSERT SELECT, and malformed literals
  are rejected. It is not a general SQL execution engine.
- The entire file's INSERT syntax is checked even with `--limit`. Required
  tables must contain INSERT data. The file is bounded to 128 MiB of decoded
  characters. Semantic mapping and destination checks cover selected products.
- `--limit N` takes the first N published products by ascending source ID;
  unsupported products count toward that selection. N must be positive.
- Source parsing and selected-product validation finish before any writes or
  downloads. Malformed source data aborts preflight with no changes.
- Each product's catalogue, attributes, categories and stock record use one
  atomic transaction. A database failure rolls back that product and stops the
  command; previously successful products remain committed and can be rerun.
- Dry runs perform source validation and read-only destination checks. They do
  not write to the database or storage and do not download images. They cannot
  verify remote image availability or guarantee a later database write succeeds.

## Mapping and assumptions

| Source | Oscar destination / behavior |
| --- | --- |
| Product title | Product title, with HTML entities decoded |
| Product description | Product description with basic HTML formatting retained; scripts, embeds, inline images, attributes and link markup removed |
| Product ID | Stable namespaced Product UPC `wc-abdeen-ID`, plus `wc_source_id` text attribute |
| `_sku` | StockRecord partner SKU under supplier code `woocommerce-abdeen` |
| Missing `_sku` | `wc-abdeen-ID` fallback with warning; source SKU collisions abort |
| `_price` | StockRecord price, currency `JOD`; no conversion or tax adjustment |
| `_regular_price` | `wc_regular_price` text attribute, named as JOD |
| `_sale_price` | `wc_sale_price` text attribute, named as JOD |
| `_stock_status=instock` | One stock unit |
| `outofstock`, `onbackorder`, missing state | Zero stock units; backorders and missing state produce warnings |
| Original stock state | `wc_stock_status` text attribute |
| For Men / For Women | Root Men / Women, from product categories or `pa_gender` |
| All Watches | Root Watches |
| Recognized brand categories | Children of Brands |
| G-SHOCK, Edifice, CASIO ANALOG, CASIO DIGILTAL | Children of Brands / CASIO; DIGILTAL is corrected to DIGITAL |
| GUY LAROCHE JEWELLERY & ACCESSORY | Brands / GUY LAROCHE / Jewellery & Accessories |
| Other product categories | Preserve their names and hierarchy; Uncategorized is omitted |
| `_thumbnail_id` + attachment `_wp_attached_file` | Oscar ProductImage saved through its ImageField's configured Django storage |

All imported products use a dedicated stock-tracking product class with slug
`woocommerce-catalogue`. This avoids changing existing product classes. Existing
categories are matched case-insensitively within the mapped parent, so the current
`Brands / Casio` category is reused. Required ancestors are assigned too, except
the Brands container, allowing existing homepage brand filters to work.

Oscar 4.2 has one selling-price field, not separate regular/sale fields. The
attributes preserve the old values exactly as decimal text, but do not create
offers, strike-through prices, or scheduled sales. Missing `_price` remains NULL
(unavailable), even if a regular price is present. Prices must be nonnegative,
finite and exactly representable in Oscar's 12-digit, two-decimal field. JOD can
use three decimal places, but nonzero third decimals are rejected instead of
being rounded. Tax-inclusive/exclusive meaning remains the responsibility of
the existing Oscar pricing strategy; source tax rules are not reconstructed.

Stock-state mapping is deliberately a **one/zero availability placeholder**,
not an inventory migration. Backorders require a separate availability policy.
Reruns refresh this placeholder stock; use this migration before live trading,
then establish actual quantities before relying on stock counts. The command
refuses products with active stock allocations or ambiguous supplier records.

WordPress shortcodes are not rendered, gallery images and product tags are not
imported, and category descriptions are not copied. Existing homepage Best
Sellers/New Arrivals ranges are not populated automatically.

## Reruns, storage and counts

Product matching uses the namespaced source ID, so a changed SKU updates the same
product and stock record. The synthetic UPC is a migration identity, not a retail
barcode; retain it for future reruns. Conflicting identities and partner SKUs
abort instead of merging products by title or guessing. Products under unrelated
suppliers are not automatically merged by SKU.

The command updates imported titles, descriptions, price attributes and stock;
preserves existing product visibility and slug; and adds category memberships
without removing manual memberships. It never deletes existing Oscar records.
Unpublished or removed source products do not cause destination deletion or
unpublishing. Run one importer process at a time.

Image requests use only `https://abdeenwatches.com/wp-content/uploads/`. Relative
attachment paths and old HTTP/www URLs are normalized to this location. Host,
path traversal and redirect checks prevent leaving that directory. Requests
have a 15-second socket timeout; downloads are limited to 10 MiB and 20 megapixels,
and Pillow must verify JPEG, PNG, GIF or WebP content. No live image download was
needed for implementation verification; remote availability remains unverified.

Each product has a stable importer image code. Matching stored images are reused;
missing files are retried. Changed source paths replace the importer's image
reference but retain old media files. Existing manually added images are preserved
and keep their primary position. A remote image changed in place at the same URL
is not automatically refreshed. Images run after the product transaction commits;
failures warn and retain the product. If an image DB write fails after storage
succeeds, only that newly saved file is cleaned up.

Created/updated/skipped/failed counts refer to selected products. `updated` means
an existing imported product was processed, even when its values did not change.
Dry-run counts are explicitly labeled **planned**. Image saved/failed counts are
separate; missing/invalid attachment references produce per-product warnings.
A source preflight error reports one failure and exits nonzero. Unselected and
non-product WordPress rows are excluded rather than added to the skipped count.

## Verification

```bash
/home/user/watch-store/.venv/bin/python manage.py check
/home/user/watch-store/.venv/bin/python manage.py test catalogue_import.tests config.tests
```

Tests use synthetic SQL fixtures and Django's test database, with mocked image
downloads and temporary media storage. The real export's five-product dry run
reported 731 published products, selected five, and planned five creations with
zero failures. No products were written to the project's local catalogue.
