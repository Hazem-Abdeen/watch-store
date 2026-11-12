from pathlib import Path
from django.core.management import BaseCommand, CommandError
from catalogue_import.storefront_transfer import export_bundle, import_bundle
from catalogue_import.sql_dump import ImportDataError


class Command(BaseCommand):
    help = 'Export a reviewed storefront bundle or verify/import it into an empty target scope.'

    def add_arguments(self, parser):
        parser.add_argument('operation', choices=['export', 'import'])
        parser.add_argument('directory', type=Path)
        parser.add_argument('--sha256', help='Required independent digest from the reviewed export.')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true')
        mode.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        try:
            if options['operation'] == 'export':
                if options['apply'] or options['dry_run']:
                    raise ImportDataError('Export writes only the new bundle directory; do not use import mode flags.')
                bundle = export_bundle(options['directory'])
                self.stdout.write(f'Export SHA-256: {bundle["sha256"]}')
                self.stdout.write(str(bundle['counts']))
                self.stdout.write(f'Media originals: {len(bundle["media"])}')
            else:
                if not options['sha256']:
                    raise ImportDataError('Supply --sha256 from the reviewed export.')
                self.stdout.write(import_bundle(options['directory'], options['sha256'], apply=options['apply']))
        except (ImportDataError, OSError, ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
