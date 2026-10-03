# WooCommerce catalogue import

The `import_woocommerce_catalog` command reads the local phpMyAdmin export as
data. It never executes the dump's SQL and has no connection to the old database.
The source defaults to `import-data/woocommerce_catalog.sql` under `BASE_DIR`.
Use `--sql-file /absolute/path/to/export.sql` for another local export.

The importer now requires the existing **Watch** product type and uses/creates a
partner named **Abdeen Watches**. Source identity and migration metadata live in
a private `CatalogueSource` table, not Oscar product attributes or UPCs. The
mapping model is not registered in Django admin or the Oscar dashboard.

## Initial normalization of the five test products (completed)

The five products have now been normalized successfully. The procedure below is
retained for reference; it is not needed again for the category cleanup described
in the next section. Oscar product IDs are **1, 2, 3, 4, 5**, corresponding to source IDs
314, 326, 333, 341, 347. `Watch` is product type ID 1. The cleanup requires explicit
Oscar IDs and verifies every product rather than assuming that a matching title
or SKU identifies an old import.

The cleanup plan is:

1. Back up the current database and media before changing anything. Keep the
   existing `db.sqlite3.backup-before-woocommerce-import` as a separate older
   backup; do not overwrite it or restore it over unrelated current work.
2. Apply the new schema migration to create only the internal mapping table.
3. Preview normalization for these five exact product IDs.
4. After reviewing that preview, apply normalization in one transaction. It
   retains product IDs, stock-record IDs, prices, currency, quantities, titles,
   descriptions, categories, visibility, slugs, and image files. It moves source
   IDs and legacy regular/sale/stock values to the private mapping; clears only
   verified synthetic UPCs; assigns Watch; reuses/creates Abdeen Watches; and
   extracts normal specifications from the existing descriptions/categories.
5. Remove only the four legacy attribute values on those verified products.
   Delete their unused legacy definitions and old product type/partner only
   when no other records depend on them. Containers with other products,
   attributes, supplier users, orders, or other references are retained and
   reported for manual review. No unrelated records are deleted or detached.

The following commands document the initial normalization procedure:

```bash
# From /home/user/watch-store, after taking a current backup:
/home/user/watch-store/.venv/bin/python manage.py migrate catalogue_import
/home/user/watch-store/.venv/bin/python manage.py normalize_imported_catalogue --product-ids 1 2 3 4 5 --dry-run

# Apply only after reviewing the preview:
/home/user/watch-store/.venv/bin/python manage.py normalize_imported_catalogue --product-ids 1 2 3 4 5 --apply
```

`normalize_imported_catalogue` defaults to preview when neither flag is supplied.
It reads the current Django catalogue only: it does not import products, read the
SQL export, download images, or reset stock quantities. Existing importer images
are linked to the internal mapping and receive a neutral image code. Their files
are reused on later imports. Repeating cleanup skips already normalized products.
An identity conflict, target SKU collision, active allocation, invalid required
specification, or unexpected supplier stops the entire cleanup without committing
changes. The import command refuses legacy products until they are normalized.

## Remove the unnecessary generic watch categories

The importer ignores **Watches** and **All Watches** category components at any
depth. Useful descendants remain, so an old All Watches / CASIO / G-SHOCK path
becomes Brands / CASIO / G-SHOCK. Men/Women normalization and all useful brand
hierarchies are unchanged. Imports never recreate or assign these generic nodes;
existing assignments are removed only by the separate cleanup below.

`remove_imported_watch_categories` accepts explicit Oscar product IDs and verifies
all of them against the internal source mapping before writing. It removes only
links to top-level categories named Watches or All Watches (case-insensitive).
Nested categories, Men, Women, Brands and all other assignments are preserved.
Missing or unmapped IDs abort the entire cleanup. The operation is transactional
and safe to repeat, and it never imports products or downloads images.

From `/home/user/watch-store`, preview removal from the existing five products:

```bash
.venv/bin/python manage.py remove_imported_watch_categories --product-ids 1 2 3 4 5 --dry-run --delete-empty
```

After reviewing the preview, apply it:

```bash
.venv/bin/python manage.py remove_imported_watch_categories --product-ids 1 2 3 4 5 --apply --delete-empty
```

Preview is the default without `--apply`. The optional `--delete-empty` flag also
deletes generic root nodes only when they have no descendants and no remaining
references (including other products and offer ranges). Otherwise it retains them
and reports why. Omit the flag to remove assignments while retaining the empty
category records. The cleanup has not been applied as part of this category fix.

## Import command usage after normalization

Before a full import, run the [read-only variant analysis](woocommerce-variants.md)
and review its candidate/ambiguous groups. The analyzer never changes products,
and the current import command still creates standalone products. Approved
parent/child conversion requires a separate reviewed implementation.

From `/home/user/watch-store`, preview 25 products:

```bash
/home/user/watch-store/.venv/bin/python manage.py import_woocommerce_catalog --dry-run --limit 25
```

Import those 25 products, including attempted image downloads:

```bash
/home/user/watch-store/.venv/bin/python manage.py import_woocommerce_catalog --limit 25
```

Add `--skip-images` to import catalogue records without making image requests.
`--limit 25` selects the first 25 source products, including the five already
imported. With the current catalogue, expect five updates and 20 creations,
not 25 additional products. No import was run for this category fix.
Rerunning without that flag will attempt missing images. Removing `--limit`
selects every published product; **the full import has not been run**.

## Scope and validation

- Only `wp_posts` rows with `post_type='product'` and `post_status='publish'`
  become Oscar products. Simple products are supported. Non-simple products
  are explicitly skipped; variations are not converted into standalone items.
- Only selected catalogue metadata, `product_cat`, recognized specification taxonomies, product type,
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
| Product ID | Private mapping keyed by source site and source ID; no synthetic UPC or source-ID product attribute |
| `_sku` | StockRecord partner SKU under Abdeen Watches (new partner code `abdeen-watches`; existing partner code preserved) |
| Missing `_sku` | `ABDEEN-ID` fallback with warning; source SKU collisions abort |
| `_price` | StockRecord price, currency `JOD`; no conversion or tax adjustment |
| `_regular_price` | Private mapping metadata only |
| `_sale_price` | Private mapping metadata only |
| `_stock_status=instock` | One stock unit |
| `outofstock`, `onbackorder`, missing state | Zero stock units; backorders and missing state produce warnings |
| Original stock state | Private mapping metadata only |
| For Men / For Women | Root Men / Women, from product categories or `pa_gender` |
| All Watches / Watches | Ignored; useful ancestors/descendants are retained without these generic components |
| Recognized brand categories | Children of Brands |
| G-SHOCK, Edifice, CASIO ANALOG, CASIO DIGILTAL | Children of Brands / CASIO; DIGILTAL is corrected to DIGITAL |
| GUY LAROCHE JEWELLERY & ACCESSORY | Brands / GUY LAROCHE / Jewellery & Accessories |
| Other product categories | Preserve their names and hierarchy; Uncategorized is omitted |
| `_thumbnail_id` + attachment `_wp_attached_file` | Oscar ProductImage saved through its ImageField's configured Django storage |

All imported products use the existing stock-tracking product type named **Watch**.
If Watch is missing, ambiguous, or does not track stock, preflight stops rather
than creating another product type or changing its settings. Abdeen Watches is
matched by name, with ambiguity and code-collision checks. Existing
categories are matched case-insensitively within the mapped parent, so the current
`Brands / Casio` category is reused. Required ancestors are assigned too, except
the Brands container, allowing existing homepage brand filters to work.

Oscar 4.2 has one selling-price field, not separate regular/sale fields. Private
mapping metadata preserves the old values as decimal text, but does not create
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

## Real watch specifications

The importer extracts **Brand, Gender, Movement, Case size, Case material, Case
color, Band material, Band color, Dial color, Water resistance, and Guarantee**
into normal Watch text attributes. It recognizes labels such as `Movement Type`,
`Water Resistant`, `Warranty`, and common strap/bracelet/color spelling variants.
Values and units are preserved as written: for example, `32.5 mm`, `Analog Quartz
(Battery)`, and `Two Years (International)`. Source claims such as `5 Bar (Diving)`
are copied, not interpreted or independently verified.

Extraction supports labeled lines, HTML table rows, product attribute taxonomies
(`pa_*`), and visible custom `_product_attributes`. Custom attributes take priority
over taxonomy values, then labeled description values. Category-derived brand and
gender are fallbacks. Hidden custom attributes and unrecognized labels are not
promoted into public specifications. Free-form marketing prose is retained in
the sanitized description; missing specifications are not guessed.

Serialized attributes use a bounded scalar/array-only reader (64 KiB, maximum
depth 8). It respects UTF-8 byte lengths and rejects PHP objects, references,
malformed lengths and trailing data. It never evaluates PHP or instantiates
serialized objects. Invalid selected-product attribute data aborts preflight.

Existing matching Watch text attributes are reused by recognized code or label.
Non-text or ambiguous matches stop preflight for review; their type and option
definitions are never overwritten. Required Watch attributes must be supplied
or already have a product value. Reruns update extracted specifications but do
not remove manual values for specifications absent from the source.

A read-only audit of all 731 source products found brand/gender values for all
731, movement for 688, case size for 689, case material for 685, and water
resistance for 684. Missing fields stay absent. This audit did not run an import.

## Reruns, storage and counts

Product matching uses the private source-site/source-ID mapping, so a changed SKU
updates the same product and stock record without storing migration IDs in UPCs.
The mapping has unique links to products and stock records and protected foreign
keys to prevent accidental loss of import identity. Back it up with the database.
Conflicting identities and partner SKUs
abort instead of merging products by title or guessing. Products under unrelated
suppliers are not automatically merged by SKU.

The command updates imported titles, descriptions, specifications, private metadata and stock;
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
downloads and temporary media storage. Tests cover normal dashboard naming,
specification extraction, private mapping idempotency, SQL and image safety,
cleanup previews, atomic rollback, retained dependencies, and reuse of the same
products/stock/images after cleanup. This refactor did not run any import command
against the project's local catalogue, including dry runs.
