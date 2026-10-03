# Read-only variant analysis

Run from `/home/user/watch-store`:

```bash
.venv/bin/python manage.py analyze_woocommerce_variants
```

The command reads only `import-data/woocommerce_catalog.sql` (or a local path
passed with `--sql-file`). It prints candidate parent groups and a separate
ambiguous section. Every group includes child source IDs, SKUs, titles, JOD
prices, color values, visible attributes, specifications, and permitted legacy
image URLs, plus matching evidence and review flags.

Machine-readable output is also available:

```bash
.venv/bin/python manage.py analyze_woocommerce_variants --format json
# Optional: save stdout to a local review artifact, outside the command itself.
.venv/bin/python manage.py analyze_woocommerce_variants --format json > import-data/variant-analysis.json
```

The command has no apply/import mode. It does not query Oscar data, write database
records, download images, or touch Django media storage. It does not require the
internal mapping migration to be applied. It completes source parsing/validation
before printing the report. Malformed SQL, invalid prices or duplicate source
SKUs stop analysis without producing a partial report. Its tests use
`SimpleTestCase`, which forbids all database access, including SELECT queries.

## Evidence and conservative rules

Identity is considered in this order:

1. Explicit model or manufacturer reference in allowed metadata, custom product
   attributes, attribute taxonomies, or labeled description fields. Recognized
   labels include Model, Model Number, Model Reference, Reference Number and MPN.
   The command additionally reads only an explicit allowlist of model-related
   postmeta keys; the normal importer's metadata selection is unchanged.
2. Narrow SKU-family patterns with explicit option separators, such as `18886/3`,
   `J1024/1`, or `DK.1.14005-2`. Casio references retain the complete prefix before
   the option suffix, e.g. `LTP-1308D`, not just `1308`. Dotted references retain
   collection/gender components, e.g. `DK.1.14005` and `DK.6.14005` stay separate.
3. Visible product attributes corroborate identity, shared specifications and
   differing colors/options. Hidden non-model attributes do not provide public
   option evidence. Common specifications alone never establish a model family.
4. Recognizable model tokens in titles are a weaker fallback, requiring more
   matching specifications. Generic normalized titles can generate an ambiguous
   review suggestion but never a high-confidence candidate on their own.

All families are scoped to a single brand, but brand membership contributes no
identity evidence. Numeric barcode prefixes and arbitrary substring/trailing-digit
truncation are never used. Opaque concatenated codes such as `GLWGG0002102` are
not split into speculative families. This deliberately misses some real variants
until manufacturer-specific rules are verified.

A high-confidence candidate must have:

- At least two distinct source SKUs and a specific, compatible model-family
  reference for every member. Stronger identifiers cannot be overridden by a
  weaker SKU or title match. Conflicting identifiers send the group to review.
- Complete agreement on movement and case size, with no known contradictions in
  gender, movement, case size, case material, band material or water resistance.
  Explicit-model groups need at least two complete matching core fields; SKU
  families need four; any family depending on a title token needs five.
- At least one differing color field complete across all children, and a unique
  complete color combination for every child. Dial, band, case, and an explicit
  visible Color attribute are supported option axes. Material changes are held
  for review rather than automatically treated as interchangeable variants.
- No copy-like SKU suffix, conflicting title dial color, contradiction between
  description and structured specifications, or ambiguous brand identity.

The report preserves raw source values and units. Comparison normalizes only
minor formatting, `St.Steel` versus `Stainless Steel`, grey/gray, and color order
such as Gold & Silver versus Silver & Gold. It does not round case sizes, equate
different water-resistance ratings, infer a missing movement, or infer options
from a photo. Missing images or different prices do not establish or disprove a
model family; child prices and source warnings remain visible in the report.

Whole families with conflicting members are flagged, rather than silently
selecting a convenient subset. Ambiguous suggestions may overlap; they must not
be merged transitively. A product cannot appear in two high-confidence parent
suggestions. “High confidence” is a documented rule classification, not a
manufacturer-confirmed relationship or permission to regroup the catalogue.

## Findings from the current export

The completed analysis covered **731 published simple products**:

| Result | Count |
| --- | ---: |
| Candidate parent groups | 77 |
| Products in candidate groups | 198 |
| Ambiguous groups | 34 |
| Products without a reported group | 450 |

The source has 730 `_product_attributes` entries containing gender rather than
model numbers. All 302 `fb_mpn` fields on published products are empty. Therefore,
the present results rely on narrow SKU patterns or recognizable title model
references, corroborated by specifications and distinct colors.

The generated report is in `import-data/variant-analysis.json` (ignored by Git).
No products were imported or regrouped, and the local database checksum remained
unchanged during analysis.

Examples:

| Family | Result | Evidence / issue |
| --- | --- | --- |
| LOTUS 18886 | Candidate: `18886/3`, `18886/4` | Both 31.5 mm, matching movement/materials/5 Bar rating; Blue vs Black dial; each 102 JOD |
| JAGUAR J1024 | Candidate: `/1`, `/2`, `/3` | Matching 44 mm case and core specifications; Blue, Green, Black dials; each 269 JOD |
| JAGUAR J1025 | Ambiguous | 43 vs 44 mm, 5 vs 10 Bar, plus one title/description dial-color conflict |
| JAGUAR J1019 | Ambiguous | Conflicting water resistance and a copy-like `J1019/2-1` listing with another model reference |
| VALENTINO ORLANDI VO.1.10014 | Ambiguous | One barcode SKU is the other plus `-1`; verify distinct identity before grouping |

No published `18886/1` exists in this export, so it is not invented or added to
the Lotus group. Generated parent titles are review labels, not final copy.

## Oscar parent/child creation after approval

The separate `convert_imported_variants` command is now implemented for an
explicit allowlist of 12 reviewed SKU-backed families. See
[controlled conversion and dry-run instructions](variant-conversion.md).
No live conversions have been applied. The command defaults to a read-only
preview and blocks missing imported children or unresolved live relationships.

This step is **not implemented or executed by the analyzer**. Approve explicit
group membership by stable source IDs, the parent model name, and the option axes
first. Resolve every ambiguous member separately. Store the approved group key
and source membership internally; do not place migration metadata in normal
Watch attributes or use fuzzy matching during the eventual write operation.

The installed Oscar 4.2 models require:

| Object | Structure and data |
| --- | --- |
| Parent | `Product.PARENT`, product class Watch, meaningful model title, shared description/specifications, Men/Women and Brands categories; **no stock records** |
| Each purchasable variant | `Product.CHILD`, `parent` set, `product_class=None` (inherited), distinct option attributes/title, its own Abdeen Watches SKU, JOD price, stock and images; **no directly assigned categories or product-level options** |

Use product attributes such as Dial color, Band color and Case color for variant
values. A child is a separately stocked SKU, not an Oscar `ProductOption` such as
an engraving choice. The parent is the browsing/selection entry; purchasing must
resolve to the chosen child and its own price/availability.

A future approved migration should:

1. Back up the current database/media and validate the entire approved mapping,
   including model identifiers, unique option combinations, supplier SKUs and
   any existing category/option/recommendation/range relationships.
2. Create/reuse one parent per approved stable group key. Assign approved shared
   specifications and normalized categories to the parent. Do not give the
   parent a synthetic stock record or a summed quantity.
3. Convert existing standalone products in place where appropriate, retaining
   their product IDs, stock-record IDs, source mappings, SKUs, prices, stock,
   image files and historical order/basket references. Do not delete/recreate
   products or rewrite historical order data to point at the parent.
4. Transfer approved category memberships to the parent and remove direct child
   category memberships as Oscar requires. Review any product-level options,
   recommendations and manual Best Sellers/New Arrivals ranges before conversion;
   children should inherit browse categories and ranges may need the parent.
5. Set the child structure, parent and null product class, preserve child-specific
   attribute values, and validate all parent/child models inside a transaction
   per approved family. Missing/unmatched products remain standalone.
6. **Update the importer before running it again:** it currently deliberately
   accepts standalone products only and assigns categories directly. It must
   honor approved parent mappings, inherited product classes, parent categories,
   and child stock/images without turning children back into standalone items.
7. Verify browsing, parent variant selection, child-specific images and prices,
   availability, basket/order behavior, dashboard editing, and idempotent reruns
   before approving a full catalogue migration.

No grouping or conversion should be driven automatically by this report alone.
