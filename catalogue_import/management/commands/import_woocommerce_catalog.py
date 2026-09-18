from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalogue_import.catalogue import OscarImporter, build_plans
from catalogue_import.sql_dump import ImportDataError, load_catalogue


class Command(BaseCommand):
    help = 'Import published products from a local WooCommerce SQL dump (never execute SQL).'

    def add_arguments(self, parser):
        parser.add_argument('--sql-file', type=Path,
                            default=settings.BASE_DIR / 'import-data/woocommerce_catalog.sql')
        parser.add_argument('--dry-run', action='store_true',
                            help='Validate and preview; no database writes, files or downloads.')
        parser.add_argument('--limit', type=int, help='Select the first N published products by source ID.')
        parser.add_argument('--skip-images', action='store_true', help='Import catalogue data without downloading images.')

    def handle(self, *args, **options):
        counts = dict(created=0, updated=0, skipped=0, failed=0)
        images_saved = images_failed = 0
        dry_run = options['dry_run']

        def summary():
            prefix = 'DRY RUN (planned) ' if dry_run else ''
            self.stdout.write(prefix + ' '.join(f'{key}={value}' for key, value in counts.items())
                              + f' images_saved={images_saved} images_failed={images_failed}')

        limit = options['limit']
        if limit is not None and limit < 1:
            raise CommandError('--limit must be a positive integer.')
        try:
            data = load_catalogue(options['sql_file'])
            plans = build_plans(data, limit)
            importer = OscarImporter()
            # Complete source validation and identity checks before the first write.
            importer.preflight(plans)
        except (ImportDataError, OSError, UnicodeError) as exc:
            counts['failed'] += 1
            summary()
            raise CommandError(f'Preflight failed; no writes or downloads performed: {exc}') from exc
        self.stdout.write(f'Published source products={len(data.products)} selected={len(plans)}')
        for plan in plans:
            if plan.skip_reason:
                counts['skipped'] += 1
                self.stdout.write(f'SKIPPED product={plan.source_id}: {plan.skip_reason}')
                continue
            for warning in plan.warnings:
                self.stderr.write(f'WARNING product={plan.source_id}: {warning}')
            if dry_run:
                created = importer.existing(plan) is None
                counts['created' if created else 'updated'] += 1
                paths = '; '.join(' / '.join(path) for path in plan.categories)
                self.stdout.write(f'WOULD {"CREATE" if created else "UPDATE"} product={plan.source_id} '
                                  f'sku={plan.sku!r} title={plan.title!r} price={plan.price} JOD '
                                  f'stock={plan.status} categories=[{paths}] '
                                  f'image={plan.image_url or "none"}')
                continue
            try:
                product, created = importer.import_product(plan)
            except Exception as exc:
                counts['failed'] += 1
                summary()
                # Do not echo DB exceptions, which can include unrelated sensitive data.
                raise CommandError(f'Stopped at product {plan.source_id} ({type(exc).__name__}). '
                                   'This product was rolled back; earlier products remain committed. '
                                   'Fix the conflict and rerun safely.') from exc
            counts['created' if created else 'updated'] += 1
            self.stdout.write(f'{"CREATED" if created else "UPDATED"} product={plan.source_id} oscar_id={product.pk}')
            if not options['skip_images']:
                try:
                    images_saved += importer.import_image(product, plan)
                except Exception as exc:
                    images_failed += 1
                    self.stderr.write(f'WARNING product={plan.source_id}: image unavailable '
                                      f'({type(exc).__name__}); product retained, rerun to retry.')
        summary()
