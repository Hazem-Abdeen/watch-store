# Excel catalogue replacement: preparation report

Prepared 28 October 2026. **Replacement is blocked by source-data decisions. No old products have been removed and no new catalogue has been imported into the development database.**

The only development database changes are additive schema migrations for the new import ledger and availability controls. Existing products keep their previous stock behavior. The source workbook and WooCommerce SQL are unchanged. Existing uncommitted project work was preserved; no Oscar package files were modified.

## Validation

Source: `/home/user/Downloads/abdeen_products_formatted.xlsx`, sheet `abdeen_products_formatted`, rows 2–359.

SHA-256: `5dda595c3a5382ff5e81ac56ad52842c125913445ea771df141b39c0193bf3f1`.

| Check | Result |
| --- | --- |
| Product rows | 358: 342 Watch, 16 Accessory |
| Missing SKU, model, title, brand or gender cells | 0; six brand/gender cells contain shifted data |
| Distinct SKUs | 355; three duplicate pairs, all blocked |
| EAN-13 checksum | All 358 supplied barcodes pass |
| Distinct brand/model pairs after proposed column repair | 354; four ambiguous pairs |
| Original workbook | 56 error findings affecting 14 rows; 344 rows without blocking errors |
| With the six proposed Jaguar repairs | 14 error findings affecting 8 rows; 350 rows without blocking errors |
| Prices after proposed repair | All positive and representable without rounding; 36–661 JOD |
| Discount relationships after proposed repair | 342 rows have regular price above selling price; 16 accessory rows have equal prices |
| Brands after proposed repair | 13 recognized brands; explicit aliases reuse existing category IDs/URLs |
| Required existing Oscar attributes | None of the existing 11 Watch attributes are marked required |

All rows are validated before `--limit` is applied. Blank identifiers, duplicate identifiers, unknown categories/brands, invalid prices, formula cells and unsupported layouts block application. Duplicate titles are permitted and never used for identity. Core watch attributes are checked; absent optional details remain blank.

### Duplicate identifiers requiring a decision

Prices below are selling / regular, in JOD. Row numbers are actual Excel row numbers, including the header.

| Excel rows | SKU / model | Differences and source evidence |
| --- | --- | --- |
| 46, 52 | `8682308331714`, `DK.1.14004-4` | 56 / 80 versus 57 / 82. Otherwise identical source fields. Both resolve to old Oscar product 434 / WooCommerce 5181, with attachment `2026/05/DK.1.14004-4.webp`. Choose one record and its prices, or provide verified distinct identifiers if these represent different watches. |
| 121, 131 | `8682308327793`, `DK.1.13951-2` | 42 / 60 versus 43 / 62. Otherwise identical source fields. Both resolve to old product 417 / WooCommerce 5041, attachment `2026/03/DK.1.13951-2.webp`. Same decision needed. |
| 302, 311 | `7620958006966`, `SMWGO2102030` | Row 302: 205 / 341, 44 mm, rubber band. Row 311: 243 / 405, 43 mm, stainless-steel band. The old catalogue contains both descriptions: product 729 / WooCommerce 6600 uses the barcode; product 88 / WooCommerce 1586 uses the model as SKU. Both attachments claim the same model. Source history confirms the conflict but cannot establish which physical watch/barcode is correct. Neither row nor image is merged. |
| 250, 251 | `LC08147.170`, barcodes `8681668614284` and `8681668614253` | Distinct colours and barcodes. Row 251 is titled “(Copy)”. Old product 562 / WooCommerce 5882 points to `2026/08/LC08147.220-1.jpg`; row 250 points to `LC08147.170-1.jpg`. **LC08147.220 is a proposed correction for row 251, not an established fact or an applied change.** Confirm against the actual item/supplier. |

If one row is removed from each SKU pair, the result is **355 products: 339 watches and 16 accessories**, assuming no other removals. Keeping 358 requires verified corrections for genuinely distinct products, not invented suffixes or silent merges.

### Six shifted Jaguar rows

Rows **223, 224, 227, 229, 230 and 231** split the product title across D/E, shifting brand through country one column right. Country is present in U, beyond the 20-column header. The proposal combines the two title fragments with a comma and shifts F:U back to E:T, retaining every source value.

| Row | Model | Proposed selling / regular price |
| --- | --- | --- |
| 223 | J1024/1 | 269 / 385 |
| 224 | J1019/2 | 307 / 438 |
| 227 | J1020/2 | 370 / 529 |
| 229 | J1014/1 | 400 / 572 |
| 230 | J1025/2 | 400 / 572 |
| 231 | J1025/3 | 400 / 572 |

The proposed correction file is `var/catalogue-replacement/proposed-corrections.json`. It is tied to the workbook hash and exact original row contents, with a reason for each change. It has been used only for a second dry run. It does **not** resolve or drop duplicates. The original workbook has not been edited.

### Incomplete specifications

After the proposed column repair, watches have 241 missing Glass values, 44 missing Country values, four missing Water Resistance values (rows 157, 169, 170, 275), and three missing Case Material values (280, 284, 286). These produce 292 warnings, not invented specifications. The 16 accessories are allowed to omit watch-specific attributes. Numeric case size `42` is normalized explicitly to `42 mm`.

Country is stored and displayed as **Country**; the importer does not assert that it means country of manufacture. Technical descriptions are imported from supplied data, not independently certified manufacturer specifications.

## Images

**250 confidently matched images for the original, uncorrected workbook**: 202 by unique SKU and 48 by unique brand plus manufacturer reference recorded as the old WooCommerce SKU. The proposed Jaguar repair makes two more eligible (rows 224 and 229), giving **252 conditionally matched images**.

Each accepted image requires:

1. A unique, valid new identifier and an unambiguous old record, with SKU priority.
2. Agreement between the old database SKU and original WooCommerce source SKU.
3. An explicit brand match and no conflicting populated gender, case size/material/colour, band material/colour or dial-colour fields. Only documented spelling/material synonyms are normalized.
4. The complete model reference in the original attachment filename. Punctuation is retained; only URL decoding and the slash-to-hyphen filename convention are allowed. No title-only match, fuzzy match or shortened regional/model suffix is accepted.
5. The mapped image belongs to that old product and its filename contains the original source-URL digest used by the existing importer. All 667 current mapped images pass that provenance check.
6. A readable image and a verified SHA-256 copy in the independent archive. Image bytes reused across different model identities are withheld.

The 250 eligible photos were visually sanity-checked in ten contact sheets. The two additional Jaguar photos were inspected individually. Identity confidence is based on exact local source evidence; no claim is made that filenames independently authenticate a manufacturer's reference.

The original report leaves **108 images unassigned**:

| Reason | Rows |
| --- | ---: |
| Attachment filename does not establish the complete model | 47 |
| Conflicting old/new specifications | 28 |
| Row validation / duplicate identifiers unresolved | 14 |
| Exact product matched but old image missing | 8 |
| Same image bytes associated with different model references | 6 |
| No unique exact match | 5 |

Artifacts are independent of old Product records:

- `var/catalogue-replacement/review/images.json`: per-row decisions, source attachment, old identity and checksum mapping.
- `var/catalogue-replacement/review/assets/`: content-addressed copies of eligible and reviewable candidate photos.
- `var/catalogue-replacement/review/old-catalogue.json`: all 731 old catalogue identities, specifications, image paths and range memberships.
- `var/catalogue-replacement/review/contact-sheets/`: ten visual review sheets.
- `var/catalogue-replacement/proposed-review/`: equivalent report for the proposed Jaguar repair.

Uncertain images stay unassigned. Products without accepted images use the existing `watch-placeholder.svg`. Import reruns do not replace, reorder, restore or remove staff-maintained images.

## Existing pricing

The project's existing `config.partner.StockRecord.regular_price` field and dashboard support are retained. `price` is the selling price used by Oscar's basket, offers, checkout, order and COD source. The regular price is display-only; a strike-through and percentage appear only when it exceeds the selling price. Both values import as Decimal JOD amounts. Existing percentage/rounding behavior is unchanged.

## Backup and proposed cleanup

Preparation backup: `var/catalogue-replacement/backups/20261028T194834Z-preparation/`.

- SQLite online backup, integrity check `ok`, plus `media.tar.gz` and SHA-256 checksums.
- All **1,020 media files** were read back from the archive and compared byte-for-byte by SHA-256 against originals.
- `var/catalogue-replacement/preservation-check.json` confirms unchanged original product, stock, image, attribute, category, class, mapping, order, basket, range and homepage rows.
- A **fresh** verified database/media backup is mandatory inside the apply procedure, before deletion. The command is restricted to local SQLite with `DEBUG=True`.

The reviewed operation will remove only the 731 products proven to be WooCommerce imports, in the same database transaction as the new import:

| Relationship | Proposed operation |
| --- | --- |
| 731 old products and source mappings | Remove |
| 731 stock records | Remove; retire the six local test allocations explicitly |
| 667 product-image relationships | Remove relationships; retain original media files |
| 7,653 attribute-value rows and 1,665 category links | Remove product-specific values/links |
| 15 basket lines | Remove obsolete lines and their dependent line attributes; retain baskets |
| 28 product analytics records and 80 user-product views | Remove obsolete product-specific records |
| 6 orders / 6 order lines | Retain order history, prices, titles, SKUs, payment sources and addresses. Null product/stock links and set line allocations to zero/cancelled. No order is silently cascaded away. |
| 1 wishlist line | Retain the line with its product link nulled by Oscar |
| 8 homepage range memberships | Archive before deletion; restore the five exact identifiable new matches. Preserve both ranges. Three discontinued/unmatched selections remain empty slots for later curation. |

Preserve all 23 categories, existing brand categories and eight brand presentations, Watch class, 11 existing attribute definitions, partners, three hero slides, ranges and other settings. Create Accessory class and source attributes that do not already exist. Map Bigotti Milano to existing Bigotti category, and SB Polo to Santa Barbara Polo only for old-image identity comparisons. Case-insensitive brand mapping preserves existing IDs/URLs. Accessories also join an Accessories category and the existing Guy Laroche Jewellery & Accessories category where applicable.

The command verifies the full relationship snapshot again inside the transaction, rejects unmapped products and unexpected cascading deletions/relationship updates, and requires the exact reviewed plan hash. Oscar's immediate image-file deletion receiver is disconnected only around this bounded cleanup, then restored, so a database rollback cannot lose old media. Import failures roll back old database deletions. New content-addressed copies can remain as harmless unreferenced media after a failure; originals are never deleted.

Neither `import-data/woocommerce_catalog.sql` nor any original WooCommerce source file is deleted. The live search index stays unchanged until replacement succeeds.

## Importer and commands

Implementation:

- `catalogue_import/excel.py`: literal OOXML reader, validation and explicit correction handling; no new dependency.
- `catalogue_import/excel_images.py`: deterministic image evidence, copies and mapping.
- `catalogue_import/excel_replacement.py`: schema checks, backup, bounded cleanup, atomic import helpers.
- `catalogue_import/management/commands/replace_excel_catalogue.py`: command orchestration and approval-plan gate.
- `catalogue_import/models.py` and migration `0002_excelcatalogueentry.py`: stable string-SKU import ledger.
- `catalogue_import/tests/test_excel_replacement.py`: 27 focused replacement/stock tests.

Run from `/home/user/watch-store` using the IDE-configured interpreter:

```bash
.venv/bin/python manage.py replace_excel_catalogue \
  /home/user/Downloads/abdeen_products_formatted.xlsx --dry-run
```

Current expected result: a nonzero exit with a saved report, because validation is blocked. No database writes occur in a dry run; it writes review files and independent image copies.

Proposed repair preview, still blocked by the four ambiguous identifier pairs:

```bash
.venv/bin/python manage.py replace_excel_catalogue \
  /home/user/Downloads/abdeen_products_formatted.xlsx --dry-run \
  --corrections var/catalogue-replacement/proposed-corrections.json \
  --report-dir var/catalogue-replacement/proposed-review
```

After source decisions are resolved, prepare `approved-corrections.json` with only explicitly accepted changes/removals, rerun validation, and review a new clean plan. Set `--expected-count` to the actual agreed count if rows are intentionally removed. Do not add fake identifiers to meet 358.

**Only after that report and approval**, stop the development server/background writers and execute the reviewed replacement. Example assuming 358 valid rows remain and initial availability stays off:

```bash
.venv/bin/python manage.py replace_excel_catalogue \
  /home/user/Downloads/abdeen_products_formatted.xlsx --dry-run \
  --corrections var/catalogue-replacement/approved-corrections.json \
  --report-dir var/catalogue-replacement/approved-review

# Review approved-review/plan.json and obtain replacement approval first.
.venv/bin/python manage.py replace_excel_catalogue \
  /home/user/Downloads/abdeen_products_formatted.xlsx --apply --replace \
  --corrections var/catalogue-replacement/approved-corrections.json \
  --report-dir var/catalogue-replacement/approved-review \
  --reviewed-plan var/catalogue-replacement/approved-review/plan.json
```

Include `--initially-available` in **both** runs only if accepting availability-confirmation orders for every row is explicitly chosen. Options/source/data changes invalidate the prior plan. `--replace --limit` is rejected to avoid deleting the old catalogue and importing only a fraction.

Normal reruns use `--apply` without `--replace`, retaining the same corrections and report directory. `--limit N` bounds created/preserved rows but still validates the entire workbook. It is suitable for an empty disposable development database or subsequent imports, not a partial replacement of the live old catalogue.

Known Excel SKUs are **create-only on rerun**: product content, publication, categories, price, regular price, availability and images stay as staff edited them. Changed source rows are counted as `source_changes_not_applied`; update existing products through the dashboard or design a separately reviewed synchronization policy. New SKUs are created. Deleting a source row on a later run does not automatically delete the product.

On successful application, the command commits the catalogue and runs `rebuild_index --noinput`. An indexing failure leaves the committed catalogue intact; fix the index issue and rerun that command. No live index rebuild has been performed at preparation time. Tests use disposable indexes.

Recovery: stop writers, verify the chosen backup's `checksums.json`, restore its SQLite file and media archive, then rebuild the search index. Keep the failed database/media separately until verified. A preparation backup predates the additive schema, so run `migrate` if restoring it while keeping the new code. No restore has been executed.

## Temporary stock policy

Implemented in `config/partner/models.py`, `strategy.py`, migration `0009`, project-owned `config/order/`, and the dashboard stock form/template. Existing Watch class tracking and old counted-stock records are unchanged.

- New records have `availability_only=True`, `num_in_stock=NULL`, `num_allocated=0`. A database constraint rejects fake inventory quantities in this mode.
- Staff control **Available to order** in the dashboard. Default for import is **off** because the workbook provides no availability evidence. The optional flag above enables all new rows only when deliberately chosen.
- Oscar's custom strategy uses that boolean. It accepts multiple units when enabled, without pretending that one item exists. No exact stock quantities are displayed to shoppers.
- Checkout rechecks availability inside order placement. Both stock-record and order-line allocations stay zero. Consumption/cancellation do not mutate nonexistent stock. Existing counted inventory retains Oscar's normal allocation behavior.
- The product page says “Available to order; availability confirmed before dispatch”, instead of promising “In stock, ready to ship”.
- Orders do not decrement or disable availability. This is an order-acceptance flag, **not stock reservation or an inventory guarantee**. Enabled items can receive multiple orders; staff must confirm availability before fulfilment. Unknown items should stay disabled.
- Before real inventory/Falcons integration, reconcile outstanding orders, establish quantities and reservations, and migrate away from this mode deliberately. Do not simply populate quantities while availability-only is enabled.

## Verification

- `manage.py check`: no issues.
- `makemigrations --check --dry-run`: no pending model changes.
- `git diff --check`: clean.
- Focused run: **175 tests passed**, including all 27 new tests and existing COD, shipping, pricing, product detail, basket, recommendations, homepage and importer coverage.
- Full suite: **334 tests run; 17 failing assertions/subtests in 11 pre-existing test methods**, with no new errors. Four methods still expect availability text previously removed from cards; seven dashboard-search methods use a staff fixture without the catalogue permissions and receive 403. All 17 failures reproduce in an isolated copy with this task's changes removed. Unrelated pre-existing code/tests were not rewritten.
- New tests exercise strict prices/identifiers, validation before limits, dry-run database read-only behavior, exact-match image archive integrity, placeholder retention, idempotency/manual-edit preservation, reviewed replacement and rollback, order-link handling and retention of original media, dashboard product/price/availability POST, homepage/shop/brand/category/search/detail views, real COD orders for multiple units and repeated baskets, withdrawal during placement, no inventory allocations and fixed 2.00 JOD shipping.
- Image mappings and optional fields were audited for every source row. Contact sheets were visually inspected. This is not a live browser acceptance test of a replaced catalogue: that final check, actual product count, full-image assignment and development index rebuild remain deferred until the data is resolved and replacement approved.

Logs: `var/catalogue-replacement/test-logs/`. No tests created orders or products in the development database.

## Decisions still needed

1. Resolve the three duplicate-SKU pairs with approved rows/prices or verified corrected identities. Confirm the resulting expected product count.
2. Confirm the correct model reference for Lee Cooper row 251; the old image suggests `LC08147.220`.
3. Accept or revise the explicit six-row Jaguar column repair.
4. Choose initial availability: default disabled until confirmed, or accept COD orders for every listed item subject to manual confirmation.
5. After those decisions produce a clean report, approve the local replacement, including retiring the six test allocations while retaining order history and removing obsolete basket lines.

Unassigned images can be uploaded manually later. Three old homepage picks have no approved replacement match; the preserved ranges can be curated through the dashboard.
