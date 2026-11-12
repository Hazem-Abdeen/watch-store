"""Notification delivery through real Oscar COD placement and commit hooks."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from smtplib import SMTPDataError
from unittest.mock import patch

from django.contrib.sites.models import Site
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command, CommandError
from django.db import transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from oscar.core.loading import get_model

from config import test_checkout
from config.checkout.models import OrderEmailNotification
from config.checkout.notifications import dashboard_url, retry_failed_notification, schedule_order_emails

Order = get_model('order', 'Order')
MERCHANTS = ['hazem.abdeen39@gmail.com', 'hossam.abdeen199@gmail.com', 'emad11abdeen@gmail.com']


class EmailFixtures:
    def setUp(self):
        super().setUp()
        test_checkout.CODCheckoutTests.setUpTestData.__func__(type(self))
        self.client = Client(enforce_csrf_checks=True)
        self.client.get(self.product.get_absolute_url())
        self.basket = self.add()

    post = test_checkout.CODCheckoutTests.post
    add = test_checkout.CODCheckoutTests.add
    data = test_checkout.CODCheckoutTests.data
    checkout = test_checkout.CODCheckoutTests.checkout

    def place(self, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.checkout(follow=True, **kwargs)
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        return Order.objects.get()

    def assert_messages(self, order, email='guest@example.test', merchants=MERCHANTS):
        self.assertEqual(len(mail.outbox), 2)
        customer, merchant = mail.outbox
        self.assertEqual(customer.to, [email])
        self.assertEqual(merchant.to, merchants)
        for message in mail.outbox:
            self.assertEqual(message.cc, [])
            self.assertEqual(message.bcc, [])
            self.assertEqual(message.from_email, 'Abdeen Watches <orders@example.test>')
            self.assertEqual(message.alternatives[0].mimetype, 'text/html')
            for body in [message.body, message.alternatives[0].content]:
                for value in [order.number, 'Test Customer', email, '+962791234567', '12 Example Street',
                              'Amman', 'Jordan', self.product.title, 'Quantity: 1',
                              'Cash on Delivery', 'Delivery within 1–2 business days', 'Order date:']:
                    self.assertIn(value, body)
                for private in ['COD-001', self.user.password, 'stockrecord', 'partner_sku', 'WooCommerce', 'PRIVATE_STAFF_NOTE']:
                    self.assertNotIn(private, body)
        self.assertEqual(customer.subject, f'Order Confirmation – Abdeen Watches #{order.number}')
        self.assertEqual(merchant.subject, f'New Order #{order.number} – Abdeen Watches')
        self.assertIn('NEW ORDER', merchant.body)
        self.assertNotIn('NEW ORDER', customer.body)
        for recipient in merchants:
            self.assertNotIn(recipient, customer.body)
        self.assertEqual(OrderEmailNotification.objects.filter(status='sent').count(), 2)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   DEFAULT_FROM_EMAIL='Abdeen Watches <orders@example.test>',
                   ABDEEN_ORDER_NOTIFICATION_EMAILS=MERCHANTS)
class OrderNotificationTests(EmailFixtures, TestCase):
    def test_successful_guest_customer_and_three_merchant_recipients(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.checkout(follow=True)
            order = Order.objects.get()
            order.notes.create(message='PRIVATE_STAFF_NOTE')
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        self.assert_messages(order)
        self.assertIsNone(order.user_id)
        self.assertNotIn(order.email, mail.outbox[1].to)
        for text in ['Subtotal: 125.5 JOD', 'Shipping: 2 JOD', 'Final total: 127.5 JOD']:
            self.assertIn(text, mail.outbox[0].body)
            self.assertIn(text, mail.outbox[1].body)

    def test_successful_account_confirmation_only_to_account_email(self):
        self.client.force_login(self.user)
        order = self.place(data={'email': self.user.email})
        self.assert_messages(order, email=self.user.email)
        self.assertEqual(order.user_id, self.user.pk)
        self.assertNotIn(order.email, mail.outbox[1].to)

    def test_account_can_choose_order_email_without_changing_login(self):
        self.client.force_login(self.user)
        order = self.place(data={'email': 'checkout-contact@example.test'})
        self.assert_messages(order, email='checkout-contact@example.test')
        self.assertEqual(order.guest_email, 'checkout-contact@example.test')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'customer@example.test')
        # Retries/refreshes use the persisted contact and cannot resend.
        with self.captureOnCommitCallbacks(execute=True):
            self.client.get(reverse('checkout:thank-you'))
            schedule_order_emails(order)
        self.assertEqual(len(mail.outbox), 2)

    def test_no_sends_until_order_transaction_commits(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.checkout(follow=True)
            self.assertEqual(mail.outbox, [])
            self.assertFalse(OrderEmailNotification.objects.exists())
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_refresh_replay_and_repeated_hook_do_not_resend(self):
        quote = self.client.get(reverse('checkout:index')).context['quote']
        order = self.place(quote=quote)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.get(reverse('checkout:thank-you'))
            self.client.get(reverse('checkout:thank-you'))
            self.checkout(quote=quote)
            schedule_order_emails(order)
            schedule_order_emails(order)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(OrderEmailNotification.objects.count(), 2)

    @override_settings(ABDEEN_ORDER_NOTIFICATION_EMAILS=['ops@example.test', 'owner@example.test'])
    def test_recipients_are_read_from_settings(self):
        order = self.place()
        self.assert_messages(order, merchants=['ops@example.test', 'owner@example.test'])

    @override_settings(ABDEEN_ORDER_NOTIFICATION_EMAILS=['guest@example.test', 'ops@example.test'])
    def test_customer_gets_merchant_email_only_if_explicitly_configured(self):
        self.place()
        self.assertEqual(mail.outbox[0].to, ['guest@example.test'])
        self.assertEqual(mail.outbox[1].to, ['guest@example.test', 'ops@example.test'])

    @override_settings(ABDEEN_ORDER_NOTIFICATION_EMAILS=[])
    def test_empty_merchant_list_does_not_block_customer_confirmation(self):
        self.place()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['guest@example.test'])
        self.assertEqual(OrderEmailNotification.objects.get(kind='merchant').status, 'skipped')

    def test_invalid_checkout_and_unavailable_stock_do_not_send(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.checkout({'email': '', 'phone_number': ''})
            self.assertTrue(response.context['form'].errors)
            quote = response.context['quote']
            self.stock.num_in_stock = 0
            self.stock.save()
            self.checkout(quote=quote)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(mail.outbox, [])
        self.assertFalse(OrderEmailNotification.objects.exists())

    def test_order_placement_failure_does_not_send(self):
        from config.checkout.views import CODCheckoutView
        from oscar.apps.order.exceptions import UnableToPlaceOrder
        with self.captureOnCommitCallbacks(execute=True):
            with patch.object(CODCheckoutView, 'handle_order_placement', side_effect=UnableToPlaceOrder('Please try again')):
                self.checkout()
        self.assertFalse(Order.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_rollback_discards_email_callback(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    self.checkout()
                    self.assertTrue(Order.objects.exists())
                    raise RuntimeError('Rollback test')
        self.assertFalse(Order.objects.exists())
        self.assertEqual(mail.outbox, [])

    def voucher(self, benefit_type='Percentage', value=10):
        offer_range = get_model('offer', 'Range').objects.create(name='Watches', includes_all_products=True)
        condition = get_model('offer', 'Condition').objects.create(range=offer_range, type='Count', value=1)
        benefit = get_model('offer', 'Benefit').objects.create(range=offer_range, type=benefit_type, value=value)
        offer = get_model('offer', 'ConditionalOffer').objects.create(name='Welcome discount', offer_type='Voucher', condition=condition, benefit=benefit)
        voucher = get_model('voucher', 'Voucher').objects.create(name='Welcome', code='WELCOME10', usage='Multi-use',
            start_datetime=timezone.now()-timedelta(days=1), end_datetime=timezone.now()+timedelta(days=1))
        voucher.offers.add(offer)
        self.post(reverse('basket:vouchers-add'), {'code': voucher.code})

    def test_real_voucher_and_paid_shipping_totals_in_both_formats(self):
        self.voucher()
        paid = test_checkout.FixedPrice(charge_excl_tax=Decimal('5'), charge_incl_tax=Decimal('5'))
        with patch('config.shipping.repository.Repository.methods', (paid,)):
            order = self.place(data={'method_code': paid.code})
        self.assertEqual(order.total_incl_tax, Decimal('117.95'))
        self.assertEqual(order.discounts.get().amount, Decimal('12.55'))
        for message in mail.outbox:
            for value in ['Subtotal: 125.5 JOD', 'Shipping: 5 JOD', 'Final total: 117.95 JOD',
                          'Discount: Welcome discount (WELCOME10): -12.55 JOD']:
                self.assertIn(value, message.body)
            for value in ['125.5 JOD', '5 JOD', '117.95 JOD', '12.55 JOD', 'WELCOME10']:
                self.assertIn(value, message.alternatives[0].content)

    def test_shipping_discount_totals_reconcile(self):
        # Retain coverage for historical orders with shipping discounts.
        from oscar.apps.shipping.repository import Repository as OscarRepository
        self.voucher(get_model('offer', 'Benefit').SHIPPING_PERCENTAGE, 50)
        paid = test_checkout.FixedPrice(charge_excl_tax=Decimal('5'), charge_incl_tax=Decimal('5'))
        with patch('config.shipping.repository.Repository.methods', (paid,)), patch(
                'config.shipping.repository.Repository.get_shipping_methods', OscarRepository.get_shipping_methods):
            order = self.place(data={'method_code': paid.code})
        self.assertEqual(order.total_incl_tax, Decimal('128'))
        for message in mail.outbox:
            self.assertIn('Shipping (before discount): 5 JOD', message.body)
            self.assertIn('Shipping discount: Welcome discount (WELCOME10): -2.5 JOD', message.body)
            self.assertIn('Final total: 128 JOD', message.body)

    def test_dashboard_link_is_merchant_only_and_uses_site_not_request_host(self):
        site = Site.objects.get_current()
        site.domain = 'shop.abdeenwatches.com'
        site.save()
        order = self.place()
        url = 'https://shop.abdeenwatches.com' + reverse('dashboard:order-detail', kwargs={'number': order.number})
        self.assertIn(url, mail.outbox[1].body)
        self.assertIn(url, mail.outbox[1].alternatives[0].content)
        self.assertNotIn(url, mail.outbox[0].body)
        self.assertNotIn('dashboard', mail.outbox[0].alternatives[0].content)
        for domain in ['example.com', 'localhost', 'attacker.test', 'valid.com@attacker.com', 'valid.com/path', 'valid.com?x=y']:
            site.domain = domain
            site.save()
            self.assertEqual(dashboard_url(order), '')

    def test_html_escapes_customer_and_product_text(self):
        self.product.title = '<script>private()</script> Watch & Strap'
        self.product.save()
        self.place(data={'first_name': '<img src=x>', 'last_name': 'Customer'})
        for message in mail.outbox:
            self.assertIn(self.product.title, message.body)
            html = message.alternatives[0].content
            self.assertIn('&lt;script&gt;', html)
            self.assertIn('&lt;img src=x&gt;', html)
            self.assertNotIn('<script>', html)
            self.assertNotIn('<img src=x>', html)

    def test_customer_email_failure_does_not_prevent_merchant_email(self):
        original = EmailMultiAlternatives.send
        def fail_customer(message, *args, **kwargs):
            if message.to == ['guest@example.test']:
                raise SMTPDataError(451, 'SENSITIVE_SMTP_PASSWORD')
            return original(message, *args, **kwargs)
        with self.assertLogs('abdeen.order_email', level='ERROR') as logs:
            with patch.object(EmailMultiAlternatives, 'send', fail_customer):
                order = self.place()
        self.assertNotIn('SENSITIVE_SMTP_PASSWORD', ' '.join(logs.output))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, MERCHANTS)
        self.assertEqual(order.email_notifications.get(kind='customer').status, 'failed')
        with self.captureOnCommitCallbacks(execute=True):
            schedule_order_emails(order)
        self.assertEqual(len(mail.outbox), 1)

    def test_zero_backend_delivery_is_recorded_as_failure(self):
        with self.assertLogs('abdeen.order_email', level='ERROR'):
            with patch.object(EmailMultiAlternatives, 'send', return_value=0):
                self.place()
        self.assertEqual(OrderEmailNotification.objects.filter(status='failed').count(), 2)
        self.assertEqual(mail.outbox, [])


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', ABDEEN_ORDER_NOTIFICATION_EMAILS=MERCHANTS)
class OrderEmailCommitSafetyTests(EmailFixtures, TransactionTestCase):
    def failed_order(self):
        with self.assertLogs('abdeen.order_email', level='ERROR'):
            with patch('django.core.mail.backends.locmem.EmailBackend.open', side_effect=ConnectionRefusedError):
                response = self.checkout(follow=True)
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        return Order.objects.get()

    def test_explicit_retry_sends_failed_once_and_never_resends_sent(self):
        order = self.failed_order()
        ids = list(order.email_notifications.values_list('pk', flat=True))
        self.assertEqual(order.email_notifications.filter(status='failed').count(), 2)
        schedule_order_emails(order)
        self.assertEqual(mail.outbox, [])
        listing = StringIO()
        call_command('retry_order_emails', stdout=listing)
        self.assertIn(f'order={order.number}', listing.getvalue())
        self.assertEqual(mail.outbox, [])
        call_command('retry_order_emails', *ids, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(order.email_notifications.filter(status='sent', error_type='').count(), 2)
        call_command('retry_order_emails', *ids, stdout=StringIO())
        schedule_order_emails(order)
        self.client.get(reverse('checkout:thank-you'))
        self.assertEqual(len(mail.outbox), 2)

    def test_overlapping_retry_and_checkout_hook_do_not_duplicate(self):
        order = self.failed_order()
        record = order.email_notifications.get(kind='customer')
        stale_record = OrderEmailNotification.objects.get(pk=record.pk)
        original = EmailMultiAlternatives.send
        def overlapping_send(message, *args, **kwargs):
            self.assertFalse(retry_failed_notification(stale_record))
            schedule_order_emails(order)
            return original(message, *args, **kwargs)
        with patch.object(EmailMultiAlternatives, 'send', overlapping_send):
            self.assertTrue(retry_failed_notification(record))
        self.assertEqual(len(mail.outbox), 1)

    def test_stale_retry_cannot_reclaim_a_new_failed_attempt(self):
        order = self.failed_order()
        record = order.email_notifications.get(kind='customer')
        stale_record = OrderEmailNotification.objects.get(pk=record.pk)
        with self.assertLogs('abdeen.order_email', level='ERROR'):
            with patch('django.core.mail.backends.locmem.EmailBackend.open', side_effect=ConnectionRefusedError):
                with self.assertRaises(CommandError):
                    call_command('retry_order_emails', record.pk, stdout=StringIO())
        self.assertFalse(retry_failed_notification(stale_record))
        record.refresh_from_db()
        self.assertEqual(record.status, 'failed')
        self.assertTrue(retry_failed_notification(record))
        self.assertEqual(len(mail.outbox), 1)

    def test_ambiguous_send_failure_is_not_retryable(self):
        with self.assertLogs('abdeen.order_email', level='ERROR'):
            with patch.object(EmailMultiAlternatives, 'send', side_effect=TimeoutError):
                self.checkout(follow=True)
        records = list(OrderEmailNotification.objects.all())
        self.assertEqual([record.status for record in records], ['uncertain', 'uncertain'])
        call_command('retry_order_emails', *(record.pk for record in records), stdout=StringIO())
        self.assertEqual(mail.outbox, [])

    def test_accepted_email_status_write_failure_never_becomes_retryable(self):
        original = OrderEmailNotification.save
        def fail_sent(record, *args, **kwargs):
            if record.status == 'sent':
                raise RuntimeError('Database write failed after backend accepted email')
            return original(record, *args, **kwargs)
        with self.assertLogs('abdeen.order_email', level='ERROR'):
            with patch.object(OrderEmailNotification, 'save', fail_sent):
                self.checkout(follow=True)
        records = list(OrderEmailNotification.objects.all())
        self.assertEqual([record.status for record in records], ['uncertain', 'uncertain'])
        self.assertEqual(len(mail.outbox), 2)
        call_command('retry_order_emails', *(record.pk for record in records), stdout=StringIO())
        self.assertEqual(len(mail.outbox), 2)

    def test_sending_skipped_and_unsubmitted_orders_cannot_be_retried(self):
        order = self.failed_order()
        record = order.email_notifications.get(kind='customer')
        for status in ['sending', 'skipped', 'sent', 'uncertain']:
            record.status = status
            record.save()
            self.assertFalse(retry_failed_notification(record))
        record.status = 'failed'
        record.save()
        order.basket.status = order.basket.OPEN
        order.basket.save()
        record = OrderEmailNotification.objects.select_related('order__basket').get(pk=record.pk)
        self.assertFalse(retry_failed_notification(record))
        self.assertEqual(mail.outbox, [])

    def test_backend_failure_after_real_commit_keeps_order_stock_and_cod(self):
        with self.assertLogs('abdeen.order_email', level='ERROR') as logs:
            with patch.object(EmailMultiAlternatives, 'send', side_effect=SMTPDataError(451, 'SENSITIVE_SMTP_PASSWORD')):
                response = self.checkout(follow=True)
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        order = Order.objects.get()
        self.assertContains(response, order.number)
        self.assertNotContains(response, 'SENSITIVE_SMTP_PASSWORD')
        self.assertNotIn('SENSITIVE_SMTP_PASSWORD', ' '.join(logs.output))
        self.assertEqual(order.total_incl_tax, Decimal('127.50'))
        self.assertEqual(order.sources.get().amount_debited, 0)
        self.basket.refresh_from_db()
        self.stock.refresh_from_db()
        self.assertEqual(self.basket.status, self.basket.SUBMITTED)
        self.assertEqual(self.stock.num_allocated, 1)
        self.assertEqual(order.email_notifications.filter(status='failed').count(), 2)
        self.assertFalse(transaction.get_connection().in_atomic_block)

    def test_successful_commit_delivers_exactly_two_messages(self):
        response = self.checkout(follow=True)
        self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        self.assertEqual(len(mail.outbox), 2)
        order = Order.objects.get()
        schedule_order_emails(order)
        self.assertEqual(len(mail.outbox), 2)
