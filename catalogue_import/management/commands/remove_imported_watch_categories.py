from django.core.management.base import BaseCommand, CommandError

from catalogue_import.cleanup import remove_generic_watch_categories
from catalogue_import.sql_dump import ImportDataError


class Command(BaseCommand):
    help = 'Remove only top-level Watches/All Watches links from explicitly selected imported products.'

    def add_arguments(self, parser):
        parser.add_argument('--product-ids', nargs='+', type=int, required=True,
                            help='Exact existing Oscar product IDs, verified against the internal mapping.')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--apply', action='store_true', help='Apply cleanup atomically.')
        mode.add_argument('--dry-run', action='store_true', help='Preview only (the default).')
        parser.add_argument('--delete-empty', action='store_true',
                            help='Also remove generic root nodes if they have no children or remaining references.')

    def handle(self, *args, **options):
        try:
            report = remove_generic_watch_categories(
                options['product_ids'], apply=options['apply'], delete_empty=options['delete_empty'])
        except ImportDataError as exc:
            raise CommandError(f'Cleanup stopped; no changes committed: {exc}') from exc
        except Exception as exc:
            raise CommandError(f'Cleanup rolled back ({type(exc).__name__}); no changes committed.') from exc
        mode = 'REMOVED' if options['apply'] else 'WOULD REMOVE'
        for product_id, category_id, name in report['links']:
            self.stdout.write(f'{mode} product={product_id} category={category_id} name={name!r}')
        for category_id, name in report['deleted']:
            self.stdout.write(f'DELETED empty category={category_id} name={name!r}')
        for category_id, name in report['retained']:
            self.stdout.write(f'RETAINED category={category_id} name={name!r}: children or other references exist.')
        self.stdout.write(f'{mode} assignments={len(report["links"])}; deleted_categories={len(report["deleted"])}')
        if not options['apply']:
            self.stdout.write('Preview only; no changes made.')
            if options['delete_empty']:
                self.stdout.write('On apply, generic root nodes are deleted only if no children or references remain.')
