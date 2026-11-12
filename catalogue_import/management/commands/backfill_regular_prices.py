"""Explicit, fill-only reference-price backfill; never changes selling prices."""
from django.core.management.base import BaseCommand
from oscar.core.loading import get_model

from catalogue_import.catalogue import SOURCE
from catalogue_import.models import CatalogueSource
from config.partner.pricing import valid_regular_price


class Command(BaseCommand):
    help = 'Fill missing JOD stock regular prices from imported metadata. Review with --dry-run first.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without database writes.')

    def handle(self, *args, **options):
        StockRecord = get_model('partner', 'StockRecord')
        updated = skipped = 0
        for mapping in CatalogueSource.objects.filter(source=SOURCE).select_related('stockrecord').iterator():
            stock = mapping.stockrecord
            amount = valid_regular_price(mapping.metadata.get('regular_price')) if isinstance(mapping.metadata, dict) else None
            # Import amounts are JOD. Do not attach them to a subsequently
            # reassigned product/currency or overwrite a manual reference price.
            if (stock.regular_price is not None or amount is None or stock.price_currency != 'JOD'
                    or stock.product_id != mapping.product_id):
                skipped += 1
                continue
            if options['dry_run']:
                self.stdout.write(f'WOULD FILL stockrecord={stock.pk} regular_price={amount} JOD')
                updated += 1
            else:
                # Compare-and-set protects a value entered since the read.
                changed = StockRecord.objects.filter(
                    pk=stock.pk, regular_price__isnull=True, price_currency='JOD',
                    product_id=mapping.product_id,
                ).update(regular_price=amount)
                updated += changed
                skipped += not changed
        prefix = 'DRY RUN ' if options['dry_run'] else ''
        self.stdout.write(f'{prefix}filled={updated} skipped={skipped}')
