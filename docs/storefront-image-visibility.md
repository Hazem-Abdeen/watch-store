# Storefront image visibility

Customer product discovery requires at least one ProductImage row owned by that
product with a nonempty original-file reference. Known `image_not_found.*` and
`watch-placeholder.*` paths are excluded. Oscar's generated fallback/placeholder
object is never consulted as proof of an image. Upload validation and the
transfer's checksum/media audit remain responsible for validating actual files;
externally removing a storage file is not the same as removing its image record.

The rule applies to homepage product ranges, shop/search/category/brand results,
recommendations, recently viewed cards, offer/range listings and direct product
URLs (404 before canonical redirects). Variants require their own image record;
an image belonging only to a parent does not expose an imageless variant.

Implementation is in `catalogue_import/visibility.py` and project-owned Oscar
catalogue/search/offer app overrides. It changes no models, database fields,
publication flags, product IDs or stock. Django migration modules still point
to Oscar's unchanged migration histories. Dashboard/admin querysets and edit
views remain unfiltered. Staff visiting customer URLs see the same image gate;
use the dashboard to edit an imageless product.

Search deliberately retains public canonical product documents, including those
without images. Customer queries intersect the index with current database
visibility **before** pagination/facets, so totals are correct and a stale index
cannot expose a product after its last image is removed. Spelling suggestions
are disabled because the index's global spelling dictionary may contain hidden
titles. This does not change stock or catalogue sorting.

Saving a ProductImage refreshes its product's search document after transaction
commit, including a product created since the last full index rebuild. The first
image therefore reveals a product automatically, and removing its last image
hides it immediately without a bulk rebuild. If the search backend itself fails,
the dashboard save is retained, the error is logged, and `rebuild_index` is the
explicit recovery command. Homepage/details use the database rule independently
of search health. Existing manual indexing requirements for non-image edits
remain unchanged.

Product image count and checkout availability are separate. Uploading an image
never changes `is_available`, `availability_only`, inventory or allocations.
Existing basket/order selections retain their historical presentation/fallbacks;
this change does not delete basket/order lines or change Oscar purchase policy.

## Transfer compatibility

`transfer_storefront` reads unfiltered base model managers. All **350** products,
including the 98 hidden products, remain in the existing reviewed bundle. Image
paths, hashes, IDs, prices and unavailable flags are unchanged. Raw transfer saves
skip the per-image search signal; rebuild the index once after the full transfer
as documented. No Contabo import was performed.

The live local data audit reports 350 products, 252 image records, 252 visible
products, 252 customer search results and 350 unavailable stock records. The
SQLite file checksum remains identical. No source product/image was deleted,
uploaded or altered by this change; tests use disposable databases/media/indexes.

## Verification

Run the focused regression suite:

```bash
.venv/bin/python manage.py test config.test_image_visibility catalogue_import.tests \
  config.test_settings_production config.test_checkout config.test_shipping \
  config.test_sale_pricing config.test_basket --noinput
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
```

Coverage includes blank/placeholder records, duplicate image relationships,
customer routes and totals, live hiding with a stale index, first/last image
dashboard POSTs, multiple images, new-product indexing, private products,
recommendations/history cards, no automatic availability changes, and existing
transfer/importer, COD, pricing and basket behavior. Checkout/pricing fixtures
now provide real isolated photos; the old importer test expecting an imageless
detail page was updated to expect 404 until its first image is added.

Latest run: **203 focused tests passed**, including 11 visibility tests. Django
checks passed, no migrations were detected, and the source SQLite checksum was
unchanged. The existing reviewed 350-product transfer bundle passed read-only
record/media verification against the same source.

No data migration or live index rebuild is needed for this code change: the
existing index already contains all 350 public products. Deploy the code and
restart application workers. On a fresh transfer, follow its separate rebuild
step as usual. No Django Oscar package file is modified.
