"""SMTP configuration/probes and regressions for Oscar's native account mail."""
from io import StringIO
import os
import runpy
from smtplib import SMTPAuthenticationError
from unittest.mock import patch

from django.contrib.sites.models import Site
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from oscar.core.loading import get_model

from config import test_checkout
from config.test_settings_production import profile
from config.image_test_fixtures import ImageFixtureMedia


class MailSettingsTests(SimpleTestCase):
    def test_production_defaults_and_environment_overrides(self):
        configured = profile(EMAIL_FROM_NAME='Abdeen Test',
                             ABDEEN_ORDER_NOTIFICATION_EMAILS=' ops@example.test, owner@example.test,ops@example.test ')
        self.assertEqual(configured['EMAIL_BACKEND'], 'django.core.mail.backends.smtp.EmailBackend')
        self.assertEqual(configured['EMAIL_HOST'], 'smtp-relay.brevo.com')
        self.assertEqual(configured['EMAIL_PORT'], 587)
        self.assertTrue(configured['EMAIL_USE_TLS'])
        self.assertFalse(configured['EMAIL_USE_SSL'])
        self.assertEqual(configured['EMAIL_TIMEOUT'], 10)
        self.assertEqual(configured['DEFAULT_FROM_EMAIL'], 'Abdeen Test <sender@example.test>')
        self.assertEqual(configured['OSCAR_FROM_EMAIL'], configured['DEFAULT_FROM_EMAIL'])
        self.assertEqual(configured['ABDEEN_ORDER_NOTIFICATION_EMAILS'], ['ops@example.test', 'owner@example.test'])
        self.assertEqual(configured['OSCAR_URL_SCHEMA'], 'https')
        self.assertFalse(configured['OSCAR_SAVE_SENT_EMAILS_TO_DB'])
        configured = profile(EMAIL_HOST='smtp.example.test', EMAIL_PORT='465', EMAIL_USE_TLS='0',
                             EMAIL_USE_SSL='1', EMAIL_TIMEOUT='20', DEFAULT_FROM_EMAIL='Legacy Name <sender@example.test>')
        self.assertEqual(configured['EMAIL_HOST'], 'smtp.example.test')
        self.assertEqual(configured['EMAIL_PORT'], 465)
        self.assertEqual(configured['EMAIL_TIMEOUT'], 20)
        self.assertEqual(configured['DEFAULT_FROM_EMAIL'], 'Legacy Name <sender@example.test>')

    def test_invalid_or_missing_production_mail_settings_fail_without_echoing_values(self):
        cases = [
            {'EMAIL_HOST_USER': ''}, {'EMAIL_HOST_PASSWORD': None},
            {'DEFAULT_FROM_EMAIL': ''}, {'DEFAULT_FROM_EMAIL': 'invalid-sensitive-value'},
            {'EMAIL_FROM_NAME': 'invalid-sensitive-value\r\nBcc: hidden@example.test'},
            {'ABDEEN_ORDER_NOTIFICATION_EMAILS': ''},
            {'ABDEEN_ORDER_NOTIFICATION_EMAILS': 'invalid-sensitive-value'},
            {'EMAIL_PORT': '0'}, {'EMAIL_PORT': '65536'}, {'EMAIL_PORT': 'invalid-sensitive-value'},
            {'EMAIL_TIMEOUT': '0'}, {'EMAIL_TIMEOUT': '61'},
            {'EMAIL_HOST': ''}, {'EMAIL_HOST': 'https://invalid-sensitive-value'},
            {'EMAIL_USE_TLS': 'invalid-sensitive-value'}, {'EMAIL_USE_SSL': 'true'},
            {'EMAIL_USE_TLS': 'false'}, {'EMAIL_BACKEND': 'django.core.mail.backends.console.EmailBackend'},
        ]
        for changes in cases:
            with self.subTest(fields=list(changes)):
                with self.assertRaises(ImproperlyConfigured) as error:
                    profile(**changes)
                self.assertNotIn('invalid-sensitive-value', str(error.exception))

    def test_development_cannot_accidentally_use_production_credentials(self):
        with patch.dict(os.environ, {'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
                                     'EMAIL_HOST_PASSWORD': 'secret',
                                     'ABDEEN_ORDER_NOTIFICATION_EMAILS': 'ops@example.test'}):
            configured = runpy.run_path('config/settings.py')
        self.assertEqual(configured['EMAIL_BACKEND'], 'django.core.mail.backends.console.EmailBackend')
        self.assertEqual(configured['ABDEEN_ORDER_NOTIFICATION_EMAILS'], [])
        self.assertNotIn('EMAIL_HOST_PASSWORD', configured)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                   DEFAULT_FROM_EMAIL='Abdeen Test <sender@example.test>')
class SMTPProbeTests(SimpleTestCase):
    # SimpleTestCase forbids database access: probes must never query orders/sites.
    def test_connection_only_opens_and_closes_without_sending(self):
        with patch('django.core.mail.backends.smtp.EmailBackend.open') as opened, \
                patch('django.core.mail.backends.smtp.EmailBackend.close') as closed, \
                patch('django.core.mail.backends.smtp.EmailBackend.send_messages') as sent:
            output = StringIO()
            call_command('test_smtp', stdout=output)
        opened.assert_called_once()
        closed.assert_called_once()
        sent.assert_not_called()
        self.assertIn('No email sent', output.getvalue())

    def test_send_only_to_explicit_mailbox(self):
        with patch('django.core.mail.backends.smtp.EmailBackend.open'), \
                patch('django.core.mail.backends.smtp.EmailBackend.close'), \
                patch('django.core.mail.backends.smtp.EmailBackend.send_messages', return_value=1) as sent:
            call_command('test_smtp', to='controlled@example.test', stdout=StringIO())
        message = sent.call_args.args[0][0]
        self.assertEqual(message.to, ['controlled@example.test'])
        self.assertEqual(message.from_email, 'Abdeen Test <sender@example.test>')
        self.assertIn('No order was placed', message.body)
        self.assertEqual(message.alternatives[0].mimetype, 'text/html')

    def test_failure_is_redacted_and_connection_closed(self):
        with patch('django.core.mail.backends.smtp.EmailBackend.open',
                   side_effect=SMTPAuthenticationError(535, b'PRIVATE_CREDENTIAL')), \
                patch('django.core.mail.backends.smtp.EmailBackend.close') as closed:
            with self.assertRaises(CommandError) as error:
                call_command('test_smtp', stdout=StringIO())
        self.assertIn('SMTPAuthenticationError', str(error.exception))
        self.assertNotIn('PRIVATE_CREDENTIAL', str(error.exception))
        closed.assert_called_once()

    def test_rejects_invalid_recipient_before_connecting(self):
        with patch('django.core.mail.backends.smtp.EmailBackend.open') as opened:
            with self.assertRaises(CommandError):
                call_command('test_smtp', to='one@example.test,two@example.test')
        opened.assert_not_called()

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_console_cannot_claim_smtp_success(self):
        with self.assertRaisesMessage(CommandError, 'SMTP is not enabled'):
            call_command('test_smtp')

    def test_zero_send_result_fails(self):
        with patch('django.core.mail.backends.smtp.EmailBackend.open'), \
                patch('django.core.mail.backends.smtp.EmailBackend.close'), \
                patch('django.core.mail.backends.smtp.EmailBackend.send_messages', return_value=0):
            with self.assertRaisesMessage(CommandError, 'did not accept'):
                call_command('test_smtp', to='controlled@example.test')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', OSCAR_URL_SCHEMA='https',
                   OSCAR_FROM_EMAIL='Abdeen Test <sender@example.test>', OSCAR_SAVE_SENT_EMAILS_TO_DB=False)
class NativeOscarEmailTests(ImageFixtureMedia, TestCase):
    @classmethod
    def setUpTestData(cls):
        test_checkout.CODCheckoutTests.setUpTestData.__func__(cls)
        site = Site.objects.get_current()
        site.domain = 'preview.example.test'
        site.save()

    def test_password_reset_uses_https_site_and_shared_sender_without_archiving_token(self):
        response = self.client.post(reverse('password-reset'), {'email': self.user.email})
        self.assertRedirects(response, reverse('password-reset-done'))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertEqual(message.from_email, 'Abdeen Test <sender@example.test>')
        self.assertIn('https://preview.example.test/password-reset/confirm/', message.body)
        self.assertFalse(get_model('communication', 'Email').objects.exists())

    def test_stock_save_sends_active_alert_once_when_product_becomes_available(self):
        self.stock.num_in_stock = 0
        self.stock.save()
        Alert = get_model('customer', 'ProductAlert')
        alert = Alert.objects.create(product=self.product, user=self.user, status=Alert.ACTIVE)
        self.stock.save()
        self.assertEqual(mail.outbox, [])
        self.stock.num_in_stock = 5
        self.stock.save()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertEqual(message.from_email, 'Abdeen Test <sender@example.test>')
        self.assertIn(self.product.title, message.body)
        self.assertIn('https://preview.example.test', message.body)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.CLOSED)
        self.stock.save()
        self.assertEqual(len(mail.outbox), 1)
