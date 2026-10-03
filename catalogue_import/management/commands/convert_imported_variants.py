from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalogue_import.sql_dump import ImportDataError
from catalogue_import.variant_conversion import convert_groups, select_groups


class Command(BaseCommand):
    help = 'Preview or explicitly apply only selected, reviewed SKU-backed Watch variant families.'

    def add_arguments(self, parser):
        parser.add_argument('--analysis-file', type=Path,
                            default=settings.BASE_DIR / 'import-data/variant-analysis.json')
        parser.add_argument('--groups', nargs='+', required=True,
                            help='Exact reviewed model families, e.g. 18886 J1024. No implicit all mode.')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true', help='Read-only preview (default).')
        mode.add_argument('--apply', action='store_true', help='Explicitly commit all selected groups atomically.')

    def handle(self, *args, **options):
        if options['apply'] and options['dry_run']:
            raise CommandError('Choose --dry-run or --apply, never both.')
        try:
            groups = select_groups(options['analysis_file'], options['groups'])
            report = convert_groups(groups, apply=options['apply'], emit=self.stdout.write)
        except ImportDataError as exc:
            raise CommandError(f'Conversion stopped; no changes committed: {exc}') from exc
        except Exception as exc:
            raise CommandError(f'Conversion stopped ({type(exc).__name__}); no changes committed: {exc}') from exc
        mode = 'APPLIED' if options['apply'] else 'DRY RUN — no database or media changes'
        self.stdout.write(f'{mode}: selected={len(groups)} ready={report["ready"]} '
                          f'already_converted={report["already_converted"]} blocked={len(report["blocked"])}')
