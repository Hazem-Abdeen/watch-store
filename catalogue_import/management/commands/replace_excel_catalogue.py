"""Prepare a review first; apply only the exact reviewed, valid local replacement."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction

from catalogue_import.excel import validate_workbook
from catalogue_import.excel_images import prepare_images
from catalogue_import.excel_replacement import (
    backup_local, clean_old_catalogue, cleanup_inventory, fingerprint, import_rows, schema_preflight,
)
from catalogue_import.sql_dump import ImportDataError


class Command(BaseCommand):
    help = 'Validate Excel, archive exact-match images and prepare or apply a reviewed local replacement.'

    def add_arguments(self, parser):
        parser.add_argument('workbook', type=Path)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true')
        mode.add_argument('--apply', action='store_true')
        parser.add_argument('--limit', type=int)
        parser.add_argument('--expected-count', type=int, default=358)
        parser.add_argument('--corrections', type=Path)
        parser.add_argument('--sql-source', type=Path, default=Path('import-data/woocommerce_catalog.sql'))
        parser.add_argument('--report-dir', type=Path, default=Path('var/catalogue-replacement/review'))
        parser.add_argument('--replace', action='store_true', help='Remove only the reviewed WooCommerce imports.')
        parser.add_argument('--reviewed-plan', type=Path, help='Required for replacement: prior valid plan.json.')
        parser.add_argument('--initially-available', action='store_true',
                            help='Explicitly accept orders for new items; default is unavailable pending confirmation.')

    def handle(self, *args, **options):
        try:
            return self.run(options)
        except (ImportDataError, OSError, ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc

    def run(self, options):
        if options['limit'] is not None and options['limit'] < 1:
            raise ImportDataError('--limit must be positive.')
        if options['replace'] and options['limit'] is not None:
            raise ImportDataError('A clean replacement cannot be limited; use --limit only without --replace.')
        # Read the reviewed artifact before writing a new report to this directory.
        reviewed = json.loads(options['reviewed_plan'].read_text()) if options['reviewed_plan'] else None
        directory = options['report_dir']
        directory.mkdir(parents=True, exist_ok=True)
        validation = validate_workbook(options['workbook'], corrections=options['corrections'],
                                       expected_count=options['expected_count'])
        inventory = cleanup_inventory()
        image_path = directory / 'images.json'
        if inventory['product_ids']:
            images = prepare_images(validation, options['sql_source'], directory)
        elif image_path.exists():
            images = json.loads(image_path.read_text())
        else:
            images = {'workbook_sha256': validation['workbook_sha256'], 'counts': {},
                      'records': [{'row': r['row'], 'sku': r['sku'], 'model': r['model'], 'brand': r['brand'],
                                   'status': 'unassigned', 'ranges': []} for r in validation['rows']]}
            image_path.write_text(json.dumps(images, indent=2) + '\n')
        errors = [i for i in validation['issues'] if i['severity'] == 'error']
        if not errors:
            schema_preflight(validation)
        payload = {'validation': validation, 'cleanup': inventory, 'images': images,
                   'initially_available': options['initially_available']}
        plan = {**payload, 'plan_sha256': fingerprint(payload)}
        (directory / 'plan.json').write_text(json.dumps(plan, indent=2, default=str) + '\n')
        (directory / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n')
        self.stdout.write(f'Rows: {len(validation["rows"])}; types: {validation["counts"]}; '
                          f'errors: {len(errors)} on {len({i["row"] for i in errors})} rows; '
                          f'images: {images["counts"]}; old products: {len(inventory["product_ids"])}.')
        self.stdout.write(f'Report: {directory / "plan.json"}')
        self.stdout.write('Rerun policy: existing Excel SKU mappings preserve all dashboard edits, including images and prices.')
        if errors:
            raise ImportDataError('Validation failed. No database catalogue changes. Review validation.json; duplicates are never merged.')
        if not options['apply']:
            self.stdout.write('Dry run: only review files and independent image copies written. No database changes.')
            return
        if inventory['product_ids'] and not options['replace']:
            raise ImportDataError('Old catalogue still exists. Full replacement requires --replace and a valid --reviewed-plan.')
        if options['replace']:
            if not reviewed or reviewed.get('plan_sha256') != plan['plan_sha256']:
                raise ImportDataError('A matching reviewed plan is required. Review the new report before applying.')
            if not settings.DEBUG:
                raise ImportDataError('Destructive replacement is local development only.')
            backup = backup_local(directory.parent / 'backups', inventory)
            self.stdout.write(f'Verified database/media backup: {backup}')
        with transaction.atomic():
            deleted = clean_old_catalogue(inventory) if options['replace'] else {}
            imported = import_rows(validation, image_path, limit=options['limit'],
                                   initially_available=options['initially_available'])
        result = {'deleted': deleted, 'imported': imported, 'plan_sha256': plan['plan_sha256']}
        (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        self.stdout.write(str(result))
        # Commit the catalogue first; an index error is repairable via rebuild_index.
        call_command('rebuild_index', interactive=False, verbosity=1)
        self.stdout.write(self.style.SUCCESS('Catalogue committed and search index rebuilt.'))
