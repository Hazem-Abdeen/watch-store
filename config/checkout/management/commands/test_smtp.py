"""Probe the configured SMTP transport without reading or creating orders."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.smtp import EmailBackend
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email


class Command(BaseCommand):
    help = 'Check SMTP TLS/authentication; optionally send one synthetic email with --to.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--to', help='One controlled test mailbox. Omit to check connection only.')

    def handle(self, *args, **options):
        recipient = options['to']
        if recipient:
            try:
                validate_email(recipient)
                if '\r' in recipient or '\n' in recipient:
                    raise ValidationError('Invalid header')
            except ValidationError:
                raise CommandError('--to must be one valid email address.') from None
        connection = None
        try:
            connection = get_connection(fail_silently=False)
            if not isinstance(connection, EmailBackend):
                raise CommandError('SMTP is not enabled. Use config.settings_production with its environment loaded.')
            connection.open()
            if recipient:
                message = EmailMultiAlternatives(
                    'Abdeen Watches SMTP test',
                    'This is a synthetic SMTP test. No order was placed and no payment is due.',
                    settings.DEFAULT_FROM_EMAIL, [recipient], connection=connection,
                )
                message.attach_alternative(
                    '<p>This is a synthetic SMTP test. No order was placed and no payment is due.</p>',
                    'text/html',
                )
                if message.send() != 1:
                    raise CommandError('SMTP did not accept the test message.')
                self.stdout.write('SMTP accepted one test email. Check the mailbox and Brevo delivery logs.')
            else:
                self.stdout.write('SMTP connection, encryption and authentication succeeded. No email sent.')
        except CommandError:
            raise
        except Exception as error:
            # SMTP exceptions may echo credentials, addresses or message contents.
            raise CommandError(f'SMTP test failed ({type(error).__name__}). Check configuration and Brevo logs.') from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    self.stderr.write('SMTP connection could not close cleanly; do not assume sending failed.')
