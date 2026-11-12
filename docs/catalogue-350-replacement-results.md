# Local 350-product replacement — 12 November 2026

Replacement completed using `/home/user/Downloads/abdeen_products_import_ready_350.xlsx`.

- 350 products (334 watches, 16 accessories), 350 unique SKUs, no blocking validation errors.
- 252 verified primary photos attached; 98 products retain the existing placeholder.
- All 350 products are unavailable initially. Inventory quantity remains NULL and allocation is zero. Confirm availability individually through the dashboard.
- Removed all 731 old products, 731 old stock records, 667 old image relationships, 15 obsolete basket lines and associated old catalogue values/analytics.
- Retained the six historical local orders, with obsolete product/stock links retired. No order deletion was necessary.
- Preserved users, groups/permissions, homepage banners, brand presentations, original categories, classes and attribute definitions, partners and ranges. Restored five exact homepage range memberships; three unmatched former picks need manual curation.
- Original media contents were retained. No Oscar package files were modified.
- Live search index rebuilt with 350 documents. A real importer rerun preserved all 350 entries without duplication.

## Backup fix and recovery

`catalogue_import/media_backup.py` validates media before archive creation. It rejects links outside media, dangling links, loops, directory links, unsupported filesystem entries, unsafe archive paths, duplicate/unexpected members and altered archive link targets. Internal file links are archived with relative targets and checksums. Backup verification performs a real disposable extraction and compares every restored file/link/directory to its manifest.

The previous external placeholder link pointed to Oscar's installed `image_not_found.jpg`. It was replaced with an identical regular media file, without changing the package target. See `var/catalogue-replacement/ready-350/placeholder-normalization.json`. External links have no special exemption in backup validation.

Verified pre-replacement backup:

`var/catalogue-replacement/backups/20261112T154124.347585Z/`

Includes `db.sqlite3`, `media.tar.gz`, `media-manifest.json`, `cleanup-before.json`, `restore-verification.json` and `checksums.json`. SQLite integrity and a disposable SQLite restore passed. All 1,021 regular media files were restored and hash-verified; there are no symlinks in this particular backup.

Before any recovery, stop writers and verify every file against `checksums.json`. Restore SQLite to a separate file and media to a new empty directory first. The media restore API is:

```python
import json
from pathlib import Path
from catalogue_import.media_backup import restore_media

backup = Path('var/catalogue-replacement/backups/20261112T154124.347585Z')
restore_media(
    backup / 'media.tar.gz',
    json.loads((backup / 'media-manifest.json').read_text()),
    Path('/tmp/abdeen-recovery-media'),  # Must be empty, or not yet exist.
)
```

The earlier failed backup at `20261112T153624.869494Z` is retained for diagnosis; use the verified backup above for recovery.

## Verification

- 230 focused tests passed, including nine new media-backup tests for regular files, safe relative/absolute internal links, external/broken/loop/directory links, corrupt content, link tampering and unsafe restore destinations/manifests.
- Django checks passed; migration check reported no changes; `git diff --check` passed.
- A rehearsal and post-import disposable snapshot verified all 350 source prices, regular prices, attributes and categories, all 252 photo checksums, homepage/shop/search/category/product views and discount display.
- Snapshot tests placed a two-unit COD order with exactly 2 JOD shipping, verified unpaid COD totals and zero stock/order-line allocations, submitted the real dashboard edit form, and confirmed reruns preserve staff edits and images.
- Only the disposable test product was enabled for checkout. Real catalogue availability remains off and test users/orders were not added to the development database.
- The actual development importer rerun reported `preserved: 350`; the live index contains 350 products.

Audit artifacts: `var/catalogue-replacement/ready-350/`, particularly `replacement-result.json`, `post-import-preservation.json`, `verification.json`, `successful-replacement.log`, `idempotency.log` and `backup-regression-tests.log`.

Remaining work before deployment: confirm product availability; supply/review the 98 missing photos and 284 optional specification warnings; curate unmatched homepage picks; complete production configuration and deployment checks separately. This run verifies local catalogue behavior, not production deployment readiness or browser visual acceptance.
