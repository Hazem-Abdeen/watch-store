import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalogue_import.sql_dump import ImportDataError, load_catalogue
from catalogue_import.variants import MODEL_META_KEYS, analyze_catalogue


class Command(BaseCommand):
    help = 'Analyze the local published catalogue for possible variants; never write or regroup Oscar products.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--sql-file', type=Path,
                            default=settings.BASE_DIR / 'import-data/woocommerce_catalog.sql')
        parser.add_argument('--format', choices=['text', 'json'], default='text')

    def handle(self, *args, **options):
        try:
            data = load_catalogue(options['sql_file'], extra_meta_keys=MODEL_META_KEYS)
            report = analyze_catalogue(data)
        except (ImportDataError, OSError, UnicodeError) as exc:
            raise CommandError(f'Analysis stopped without changes: {exc}') from exc
        if options['format'] == 'json':
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return
        self.stdout.write('READ-ONLY VARIANT ANALYSIS — suggestions for review, not approved grouping rules')
        self.stdout.write(' '.join(f'{key}={value}' for key, value in report['summary'].items()))
        for section in ('candidates', 'ambiguous'):
            self.stdout.write(f'\n{section.upper()} ({len(report[section])})')
            for group in report[section]:
                self.stdout.write(f'\nParent suggestion: {group["proposed_parent_title"]!r} '
                                  f'[{group["confidence"]}; {group["basis"]}]')
                for reason in group['reasons']:
                    self.stdout.write(f'  Evidence: {reason}')
                for flag in group['review_flags']:
                    self.stdout.write(f'  REVIEW: {flag}')
                for child in group['children']:
                    self.stdout.write(f'  Child source={child["source_id"]} SKU={child["sku"]!r} '
                                      f'title={child["title"]!r} price={child["price"] or "unavailable"} JOD')
                    self.stdout.write(f'    Colors: {child["colors"]!r}')
                    self.stdout.write(f'    Visible attributes: {child["visible_attributes"]!r}')
                    self.stdout.write(f'    Specifications: {child["specifications"]!r}')
                    self.stdout.write(f'    Image: {child["image_url"] or "missing/invalid"}')
                    for warning in child['warnings']:
                        self.stdout.write(f'    Source warning: {warning}')
        for excluded in report['excluded']:
            self.stdout.write(f'Excluded source={excluded["source_id"]}: {excluded["reason"]}')
        for note in report['notes']:
            self.stdout.write(f'Note: {note}')
