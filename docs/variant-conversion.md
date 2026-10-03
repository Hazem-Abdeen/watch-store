**Controlled variant conversion — preview only**

The `convert_imported_variants` management command is implemented. No live conversion has been applied. The fixed manifest `catalogue_import/approved_variant_groups.json` pins the 12 reviewed families, their 25 source IDs/SKUs, titles, and specifications. Changes to that identity snapshot require another review.

**Exact approved source groups**

Every group below has genuine SKU-family evidence for every child, all six matching core specifications, and unique color options. None is title-only or ambiguous. The option suffix is removed only using the analyzer’s narrow family convention; no barcode-prefix or fuzzy title matching is used.

| Proposed parent | Child SKUs | Shared size / movement / water resistance | Distinguishing colors |
|---|---|---|---|
| CASIO GBD-200 | `GBD-200-1DR`, `GBD-200-9DR` | 53 mm / Analog Quartz (Battery) / Power Saving (Display goes blank to save power 3 hours everyday.) / 200-meter | band_color, case_color |
| CASIO LA670WGA | `LA670WGA-1DF`, `LA670WGA-9DF` | 31 mm / Analog Quartz (Battery) / 3 ATM | dial_color |
| CASIO LTP-1302DS | `LTP-1302DS-2AVDF`, `LTP-1302DS-4AVDF` | 31 mm / Analog Quartz (Battery) / 3 ATM | dial_color, band_color |
| CASIO LTP-1308D | `LTP-1308D-2AVDF`, `LTP-1308D-9AVDF` | 31 mm / Analog Quartz (Battery) / 3 ATM | dial_color |
| CASIO MDV-107D | `MDV-107D-1A2VDF`, `MDV-107D-3AVDF` | 45 mm / Analog Quartz (Battery) / 20 BAR | case_color |
| CASIO MTP-1375D | `MTP-1375D-3AVDF`, `MTP-1375D-7A2VDF` | 43 mm / Analog Quartz (Battery) / 5 BAR | dial_color |
| CASIO MTP-V002G | `MTP-V002G-1BUDF`, `MTP-V002G-7B2UDF` | 41 mm / Analog Quartz (Battery) / 5 BAR | dial_color |
| FREELOOK FL.1.10410 | `FL.1.10410-1`, `FL.1.10410-2` | 35 mm / Analog Quartz (Battery) / 3 ATM | band_color, case_color |
| JAGUAR J1024 | `J1024/1`, `J1024/2`, `J1024/3` | 44 mm / Analog Quartz (Battery) / 10 Bar (Diving) | dial_color |
| JAGUAR J893 | `J893/1`, `J893/3` | 34.5 mm / Analog Quartz (Battery) / 20 Bar (Diving) | dial_color, case_color |
| JAGUAR J895 | `J895/1`, `J895/4` | 34.5 mm / Analog Quartz (Battery) / 20 Bar (Diving) | dial_color |
| LOTUS 18886 | `18886/3`, `18886/4` | 31.5 mm / Analog Quartz (Battery) / 5 Bar (Diving) | dial_color |

The dry-run output also prints every child title, source ID, the shared specifications, and (when mapped) existing Oscar product/stockrecord/image IDs and live stock/prices.

**Current database readiness**

The source criteria qualify 12 groups, but none currently passes every live preflight check. Eleven groups lack mapped imported children. Lotus 18886 has existing products 5 and 22 (SKUs 18886/3 and 18886/4); product 5 is explicitly included in the Best Sellers range. The command blocks that family for relationship review rather than altering its range membership. It never imports missing products.

**Dry run for exactly these groups**

```bash
.venv/bin/python manage.py convert_imported_variants --dry-run \
  --groups GBD-200 LA670WGA LTP-1302DS LTP-1308D MDV-107D \
  MTP-1375D MTP-V002G FL.1.10410 J1024 J893 J895 18886
```

A smaller explicit selection is supported, for example `--dry-run --groups 18886`. Omitting both mode flags also previews only. There is no implicit “all” selection. `--analysis-file` can select a local report, but cannot expand the fixed approved identities. `--apply` is implemented for later authorization; it has not been used on the live database. If any selected group is blocked, applying the selection commits nothing.

**Preservation and validation**

- Create one new Watch parent for each selected family; keep every existing child product ID. Parent has no stockrecord, no child-specific colors, and no copied child description/image. Only shared brand/specifications and identical shared categories are assigned.
- Convert only explicitly selected mapped products. Children inherit Watch and categories through their parent, as Oscar requires. Their direct category links are transferred to the parent; original memberships are retained in private import metadata. Different category sets block conversion rather than losing assignments or assigning a union to every child.
- Keep existing child titles, descriptions, UPCs, attribute rows/colors, SKU/stockrecord IDs, prices/currencies, quantities/allocations, image records/files, source mappings, and references to product IDs. No downloads, imports, product deletion, or stock writes.
- Verify source mappings, supplier/SKU identity, full live specifications, publication state, categories, product structure, and existing parent state. Additional suppliers, product options, explicit ranges, recommendations, unfamiliar attributes, overlaps, or conflicting/partial previous conversion metadata require review.
- Preflight every selected group before writing. Apply all selected families in one transaction, locking mapped/product rows where supported. A late failure rolls back the complete selection. Private CatalogueSource.metadata records the family, parent ID, full source membership, and categories, so no new database migration is needed.
- A rerun validates and reuses the same parent/children and performs no writes. Unrelated products are not modified.
- The existing importer still rejects already converted children; it cannot silently turn them back into standalone products. Updating import behavior or storefront presentation is separate work.

**Validation**

Tests cover read-only default/dry-run behavior, exact approved selection, stale/conflicting evidence, category safety, live core conflicts, options/ranges/recommendations, identity and stock collisions, preservation, idempotency, missing children, unexpected existing parents/children, and rollback across multiple families. Apply-mode tests run only in Django’s isolated test database.
