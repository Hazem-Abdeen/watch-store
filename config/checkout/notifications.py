"""Transaction-safe order emails. Never send from a confirmation-page request."""
import logging
from functools import partial
from smtplib import SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import URLValidator, validate_email
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from oscar.core.loading import get_model

from .models import OrderEmailNotification

logger = logging.getLogger('abdeen.order_email')


def order_contact_email(order):
    # New COD orders snapshot the editable checkout email in guest_email for
    # both account and guest orders. Older account orders fall back to user.email.
    return order.guest_email or order.email


def schedule_order_emails(order):
    # This official checkout hook runs after basket.submit(), inside the order
    # transaction. A rollback automatically discards the callback.
    transaction.on_commit(partial(send_order_emails, order.pk, order._state.db), using=order._state.db)


def dashboard_url(order):
    """Only use the administrator-configured Site domain, never a request Host."""
    try:
        domain = Site.objects.get(pk=order.site_id).domain
        origin = 'https://' + domain
        URLValidator(schemes=['https'])(origin)
        parsed = urlsplit(origin)
        if (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
                or parsed.hostname in {'example.com', 'localhost'}
                or parsed.hostname.endswith(('.test', '.invalid', '.example'))):
            return ''
        return origin + reverse('dashboard:order-detail', kwargs={'number': order.number})
    except (Site.DoesNotExist, ValidationError, ValueError, NoReverseMatch):
        return ''


def email_context(order, kind):
    """An allowlist of display data; templates receive no request or ORM objects."""
    address = order.shipping_address
    name = ' '.join(filter(None, [address.first_name, address.last_name])) if address else ''
    if not name and order.user:
        name = order.user.get_full_name()
    return {'merchant': kind == 'merchant', 'notification': {
        'number': order.number, 'date': order.date_placed,
        'customer_name': name or 'Customer', 'customer_email': order_contact_email(order),
        'phone': str(address.phone_number) if address else '',
        'address': list(address.active_address_fields()) if address else [],
        'currency': order.currency,
        'lines': [{'title': line.title, 'quantity': line.quantity,
                   'unit_price': line.unit_price_incl_tax,
                   'total': line.line_price_before_discounts_incl_tax} for line in order.lines.all()],
        'subtotal': order.basket_total_before_discounts_incl_tax,
        'discounts': [{'label': discount.offer_name, 'voucher': discount.voucher_code,
                       'amount': discount.amount} for discount in order.basket_discounts],
        'shipping': order.shipping_before_discounts_incl_tax,
        'shipping_discounts': [{'label': discount.offer_name, 'voucher': discount.voucher_code,
                                'amount': discount.amount} for discount in order.shipping_discounts],
        'surcharges': [{'name': charge.name, 'amount': charge.incl_tax} for charge in order.surcharges.all()],
        'total': order.total_incl_tax, 'shipping_method': order.shipping_method,
        'dashboard_url': dashboard_url(order) if kind == 'merchant' else '',
    }}


def send_notification(order, kind, using):
    try:
        record, created = OrderEmailNotification.objects.using(using).get_or_create(order=order, kind=kind)
    except Exception as error:
        logger.error('Order email claim failed: order=%s audience=%s error_type=%s',
                     order.number, kind, type(error).__name__)
        return
    if created:
        deliver_notification(record, order, using)


def retry_failed_notification(record, using='default'):
    """Claim the observed failed attempt once; never retry sent/ambiguous attempts."""
    if record.status != 'failed':
        return False
    order = record.order
    if not order.basket or order.basket.status != order.basket.SUBMITTED:
        return False
    claimed = OrderEmailNotification.objects.using(using).filter(
        pk=record.pk, status='failed', attempted_at=record.attempted_at,
    ).update(status='sending', attempted_at=timezone.now(), error_type='', sent_at=None)
    if not claimed:
        return False
    record.refresh_from_db(using=using)
    deliver_notification(record, order, using)
    return True


def deliver_notification(record, order, using):
    kind = record.kind
    connection = None
    send_started = accepted = False
    try:
        recipients = [order_contact_email(order)] if kind == 'customer' else list(settings.ABDEEN_ORDER_NOTIFICATION_EMAILS)
        recipients = list(dict.fromkeys(recipients))
        if not recipients:
            record.status = 'skipped'
            record.save(update_fields=['status'], using=using)
            logger.warning('Order email skipped: order=%s audience=%s (no recipients)', order.number, kind)
            return
        for recipient in recipients:
            validate_email(recipient)
        context = email_context(order, kind)
        prefix = 'oscar/communication/emails/commtype_' + ('order_placed' if kind == 'customer' else 'merchant_order_placed')
        subject = render_to_string(prefix + '_subject.txt', context).replace('\r', '').replace('\n', '')
        message = EmailMultiAlternatives(subject, render_to_string(prefix + '_body.txt', context),
                                        settings.DEFAULT_FROM_EMAIL, to=recipients)
        message.attach_alternative(render_to_string(prefix + '_body.html', context), 'text/html')
        connection = message.get_connection(fail_silently=False)
        # Failures establishing the connection are safe to retry: no message yet.
        connection.open()
        send_started = True
        if message.send(fail_silently=False) != 1:
            send_started = False
            raise RuntimeError('Email backend did not accept the message')
        accepted = True
        record.status = 'sent'
        record.sent_at = timezone.now()
        record.save(update_fields=['status', 'sent_at'], using=using)
    except Exception as error:
        # SMTP errors can contain credentials, addresses or message content.
        # Log only the exception class, never its message or traceback.
        error_type = type(error).__name__
        logger.error('Order email failed: order=%s audience=%s error_type=%s', order.number, kind, error_type)
        # A disconnect/timeout during send or a DB failure after acceptance may
        # already have delivered mail. Never expose those attempts to retries.
        rejected = isinstance(error, (SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused))
        record.status = 'failed' if not accepted and (not send_started or rejected) else 'uncertain'
        record.error_type = error_type
        try:
            record.save(update_fields=['status', 'error_type'], using=using)
        except Exception:
            logger.error('Could not update order email status: order=%s audience=%s', order.number, kind)
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                logger.warning('Could not close email connection: order=%s audience=%s', order.number, kind)


def send_order_emails(order_id, using='default'):
    try:
        order = get_model('order', 'Order').objects.using(using).select_related(
            'user', 'shipping_address__country', 'basket').get(pk=order_id)
        # Do not send for a failed placement or a basket restored by Oscar.
        if not order.basket or order.basket.status != order.basket.SUBMITTED:
            return
        for kind in ['customer', 'merchant']:
            send_notification(order, kind, using)
    except Exception as error:
        logger.error('Order email callback failed: order_id=%s error_type=%s', order_id, type(error).__name__)
