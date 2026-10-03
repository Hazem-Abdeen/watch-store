from django.core.management.base import BaseCommand, CommandError

from catalogue_import.cleanup import cleanup_legacy_products
from catalogue_import.sql_dump import ImportDataError


class Command(BaseCommand):
    help = 'Normalize explicitly selected legacy test products without importing or downloading anything.'

    def add_arguments(self, parser):
        parser.add_argument('--product-ids', nargs='+', type=int, required=True,
                            help='Exact existing Oscar product IDs to normalize.')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--apply', action='store_true', help='Apply the reviewed cleanup atomically.')
        mode.add_argument('--dry-run', action='store_true', help='Preview only (the default).')

    def handle(self, *args, **options):
        if any(value <= 0 for value in options['product_ids']):
            raise CommandError('Product IDs must be positive integers.')
        try:
            report = cleanup_legacy_products(options['product_ids'], apply=options['apply'])
        except ImportDataError as exc:
            raise CommandError(f'Cleanup stopped; no changes committed: {exc}') from exc
        except Exception as exc:
            raise CommandError(f'Cleanup rolled back ({type(exc).__name__}); no changes committed.') from exc
        mode = 'NORMALIZED' if options['apply'] else 'WOULD NORMALIZE'
        for product_id in report['products']:
            self.stdout.write(f'{mode} product={product_id}: Watch / Abdeen Watches; '
                              f'specifications={report["specifications"][product_id]!r}')
        for product_id in report['skipped']:
            self.stdout.write(f'SKIPPED product={product_id}: already mapped.')
        for message in report['removed'] + report['retained']:
            self.stdout.write(message)
        if not options['apply']:
            self.stdout.write('Preview only. Legacy containers will be removed only if unreferenced. '
                              'No data, media, prices or stock quantities were changed.')
