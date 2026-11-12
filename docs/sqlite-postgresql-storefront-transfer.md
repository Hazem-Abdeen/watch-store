# Reviewed storefront transfer: SQLite to PostgreSQL

This is a bootstrap transfer into a migrated, empty catalogue, not an ongoing
sync or a SQL dump conversion. Contabo has not been contacted. Source data and
images have not been changed. Django 5.2/Oscar 4.2 and the same project migrations
must be deployed on the target first. Credentials come from the production
environment described in `production-deployment.md`.

## Method and scope

`transfer_storefront` serializes an explicit allowlist through Django's JSON
serializer and imports with raw, forced inserts inside one transaction. It
preserves integer/string primary keys, SKUs, product/category URLs, treebeard
paths/counters, foreign keys, image paths, full-precision timestamps, Decimal
prices and import bookkeeping. No SQLite-specific SQL is executed on PostgreSQL.

The import validates a separately supplied reviewed SHA-256, schema signature,
foreign-key closure, unique stock SKUs, unavailable inventory state and media
checksums. It locks the scoped PostgreSQL tables while checking/inserting, resets
sequences and refreshes Oscar's PostgreSQL category materialized view. That view
is derived, not exported; it does not exist on SQLite. Search indexes are rebuilt
separately after commit.

| Included model/data | Export count |
| --- | ---: |
| Products | 350 |
| Categories (including brand categories) | 24 |
| Product classes / attribute definitions | 2 / 17 |
| Product attribute values / category links | 4,440 / 732 |
| Product images | 252 |
| Partner / stock records | 1 / 350 |
| Excel import ledger entries | 350 |
| Homepage banners / brand presentations | 3 / 8 |
| Best Sellers + New Arrivals ranges / memberships | 2 / 5 |
| Shipping-country configuration | 1 (Jordan) |

Options, option groups/values and explicit product recommendations are also
allowlisted; currently empty. Auto-created many-to-many relationships are
serialized; explicit through models are included separately. Generic entity
attributes or references outside the allowlist block export/import for review.

**Excluded:** users/customers, partner-user memberships, orders/order lines,
payments, baskets, wishlists, addresses, sessions, tokens, permissions, content
types, analytics, email notification history, legacy WooCommerce mappings,
offers/vouchers, arbitrary ranges, thumbnail caches and migration history.
Only the two named curated ranges are transferred. No database credentials or
environment files are included.

The target Django Site/domain is deliberately preserved rather than copying
local `example.com`. Set the production Site separately after approval. Flatpages
are not included (none exist locally). Shipping cost, COD, authentication and
email behavior live in project code/environment, not the bundle. Deploy the
same code and configure real notification recipients separately.

All 350 stocks have `availability_only=True`, `is_available=False`,
`num_in_stock=NULL`, `num_allocated=0`. Export/import rejects enabled stock.
There are 98 products with no assigned image; the placeholder is a static asset
collected with the application, not an additional ProductImage record.

## Prepared artifacts

Final bundle: `var/storefront-transfer/bundle-350-final/`.

- `bundle.json`: data, schema, counts and per-file media checksums/references.
- `media-files.txt`: paths relative to MEDIA_ROOT, suitable for `rsync --files-from`.
- `media/`: **263 referenced originals** (252 product photos, 3 banner files and
  8 brand logo files). Only referenced files are copied. No historical images,
  development-only files or cached thumbnails are transferred.
- `var/storefront-transfer/postgresql-test.json`: disposable PostgreSQL result.

Reviewed final bundle digest:

```text
c00538f5c6aa83717abaad7654f3064e7ee63566a6d762a3ea899aabae485195
```

This is the canonical bundle digest printed by the command, **not** `sha256sum
bundle.json` (which includes formatting and the digest field). Preserve it
independently of the uploaded bundle. A later export must be reviewed again and
will require its own digest. `bundle-350/` is an earlier trial artifact; do not
use it for deployment.

No media copying into the target is performed by the database import command.
All referenced files must already be present at the target MEDIA_ROOT, with
matching hashes. Missing, modified or unsafe paths/symlinks stop the operation
before database writes. Never put the bundle or backups in a web-served folder.

## Export commands (local, read-only database)

The final bundle above is already exported. To prepare a future snapshot, freeze
dashboard edits/uploads during export and choose a NEW directory:

```bash
.venv/bin/python manage.py transfer_storefront export \
  var/storefront-transfer/new-reviewed-bundle --settings=config.settings
```

The command refuses to overwrite an existing bundle. Export reads a consistent
database transaction and verifies copied originals against their hashes. It
never updates local records or original media. `var/storefront-transfer/` is
gitignored; do not commit catalogues or generated backup artifacts.

## Later target execution — NOT performed yet

1. Review this bundle and agree on a maintenance window. Stop application and
   dashboard writers. Take and verify a PostgreSQL backup and a media backup,
   even if the product count is zero. Keep backups outside public directories.
2. Ensure the same code/migrations are present, the production environment is
   loaded and its MEDIA_ROOT is correct. A zero product count alone is not
   enough: the other scoped tables must also be empty, or exactly match the
   entire reviewed bundle. Existing category/class/partner/homepage/country
   records that differ cause a refusal; the command never merges or overwrites
   them. Existing target users and Site configuration remain outside the scope.
3. Copy the reviewed bundle to a private directory on the VPS. This task has
   not uploaded it. For example, after approval:

```bash
# LOCAL: configure VPS_SSH_HOST/USER and use an approved SSH identity/host key.
rsync -a var/storefront-transfer/bundle-350-final/ \
  "$VPS_SSH_USER@$VPS_SSH_HOST:/srv/abdeen-transfer/bundle-350-final/"
```

4. Stage the media on the target, as the application user. The environment must
   define the absolute `DJANGO_MEDIA_ROOT` from production settings. Do not use
   `--delete` or overwrite existing different files. The subsequent verification
   will reject a pre-existing file with a different hash.

```bash
# TARGET: variables loaded from the private production environment.
test -n "$DJANGO_MEDIA_ROOT"
mkdir -p "$DJANGO_MEDIA_ROOT"
rsync -a --ignore-existing \
  --files-from=/srv/abdeen-transfer/bundle-350-final/media-files.txt \
  /srv/abdeen-transfer/bundle-350-final/media/ "$DJANGO_MEDIA_ROOT/"

# Set this only to the independently reviewed digest above.
TRANSFER_SHA256=c00538f5c6aa83717abaad7654f3064e7ee63566a6d762a3ea899aabae485195

.venv/bin/python manage.py transfer_storefront import \
  /srv/abdeen-transfer/bundle-350-final --sha256 "$TRANSFER_SHA256" \
  --dry-run --settings=config.settings_production
```

5. Review the successful dry run before executing the same import with `--apply`:

```bash
.venv/bin/python manage.py transfer_storefront import \
  /srv/abdeen-transfer/bundle-350-final --sha256 "$TRANSFER_SHA256" \
  --apply --settings=config.settings_production

.venv/bin/python manage.py rebuild_index --noinput --settings=config.settings_production
.venv/bin/python manage.py check --settings=config.settings_production
```

6. Repeat the import dry run. It must say `already imported; exact records and
   media verified`. Verify 350 products, 24 categories, 252 images, 350 stocks,
   all unavailable, plus homepage/shop/category/brand/detail/search pages and
   discounts. No source users, orders or sessions should appear. Test checkout
   only on a disposable snapshot with a deliberately enabled test item; do not
   enable the live catalogue just to run a smoke test. Dashboard tests should
   use the target's own administrator, never a transferred local account.

**Repeatability:** an exact replay verifies existing records/media and does
nothing. If operators have since changed a price/title/image/category or added
a scoped record, the importer stops rather than undoing the edit. This is not a
source-authoritative synchronization tool. Do not force a replay by deleting
target rows. Prepare a separately reviewed incremental update if needed.

## Backup and rollback

Before the first real import, use PostgreSQL-native backup, e.g. with environment
credentials already loaded (never embed a password in a command or URL):

```bash
PGPASSWORD="$DB_PASSWORD" pg_dump --host="$DB_HOST" --port="$DB_PORT" \
  --username="$DB_USER" --dbname="$DB_NAME" --format=custom \
  --file=/private/backups/abdeen-before-transfer.dump
pg_restore --list /private/backups/abdeen-before-transfer.dump
```

Verify restoration into a separate disposable database, not merely archive
listing. Back up the existing MEDIA_ROOT with the project's verified media
backup workflow; never back up only the new file manifest when older target
media already exists.

Database errors roll back the data transaction; PostgreSQL sequences may advance
on failed inserts, which is harmless. Media staging is separate and may leave
new unreferenced files after a failed database import. Do not delete existing
media or shared files to clean those up.

If rollback is needed after commit, stop writers, restore the pre-transfer dump
into a NEW empty database, validate it and point the app at it after approval:

```bash
# ROLLBACK_DB_NAME is a separately created, empty recovery database.
PGPASSWORD="$DB_PASSWORD" pg_restore --host="$DB_HOST" --port="$DB_PORT" \
  --username="$DB_USER" --dbname="$ROLLBACK_DB_NAME" --exit-on-error \
  /private/backups/abdeen-before-transfer.dump
```

Restore the corresponding media backup to a new directory, verify checksums,
switch paths/database environment only after validation, and rebuild search.
Do not use `flush`, reverse all migrations, delete users, or run an unreviewed
`pg_restore --clean` against the live database. New customer orders after reopening
must be preserved/reconciled before any rollback; a blanket old backup restore
would lose them.

## Tests and readiness

The transfer was tested on a new private PostgreSQL 16 cluster under `/tmp`,
using a Unix socket, not Contabo. Tests migrated that disposable database,
proved dry-run had no data writes, injected a failed import and confirmed
rollback, imported and compared all records/media, repeated without duplication,
tested ID sequences, refused a changed target, exercised storefront/search
views and preserved a target-only administrator. No source customers/orders were
loaded. The temporary cluster is stopped after testing.

Run regressions with:

```bash
.venv/bin/python manage.py test catalogue_import.tests config.test_settings_production \
  config.test_checkout config.test_shipping config.test_sale_pricing homepage --noinput
```

Latest local result: **211 tests passed**, including nine transfer regression
tests. Django checks and migration checks passed. The original SQLite file's
SHA-256 remained unchanged. The final bundle also passed the command's read-only
exact-match verification against the source.

Remaining execution gates: explicit upload/import approval, target scoped-table
inventory, verified target backups, media staging with correct ownership, and a
successful target dry run. PostgreSQL availability and fixture portability are
tested locally; actual Contabo connectivity and target data have not been
inspected by this task.

Serialization background: [Django 5.2 serialization](https://docs.djangoproject.com/en/5.2/topics/serialization/).
