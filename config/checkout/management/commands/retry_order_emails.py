"""Explicit operator retries, never invoked by checkout or the thank-you page."""
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from config.checkout.models import OrderEmailNotification
from config.checkout.notifications import retry_failed_notification


class Command(BaseCommand):
    help = 'List failed order emails, or retry specified failed notification IDs.'

    def add_arguments(self, parser):
        parser.add_argument('notification_ids', nargs='*', type=int)
        parser.add_argument('--database', default='default', choices=tuple(connections))

    def handle(self, *args, **options):
        using = options['database']
        if transaction.get_connection(using).in_atomic_block:
            raise CommandError('Run retries outside a database transaction.')
        records = OrderEmailNotification.objects.using(using).select_related('order__basket')
        ids = options['notification_ids']
        if not ids:
            for record in records.filter(status='failed').order_by('pk'):
                self.stdout.write(f'{record.pk}: order={record.order.number} audience={record.kind} error={record.error_type}')
            return
        # Snapshot before any sends. The timestamp in the atomic claim prevents
        # overlapping commands from retrying the same failed attempt twice.
        selected = {record.pk: record for record in records.filter(pk__in=ids)}
        unsuccessful = False
        for pk in dict.fromkeys(ids):
            record = selected.get(pk)
            if record is None:
                self.stdout.write(f'{pk}: not found')
                unsuccessful = True
                continue
            claimed = retry_failed_notification(record, using)
            record.refresh_from_db(using=using)
            self.stdout.write(f'{pk}: {"attempted" if claimed else "not retried"}; status={record.status}')
            unsuccessful |= claimed and record.status != 'sent'
        if unsuccessful:
            raise CommandError('Some notifications could not be delivered; review the statuses above.')
