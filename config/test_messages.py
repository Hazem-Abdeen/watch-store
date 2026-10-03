"""Storefront message presentation; the message engine and validation stay Oscar's."""
from html.parser import HTMLParser

from django import forms
from django.contrib import messages
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.safestring import mark_safe
from oscar.core.loading import get_model


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class MessageRenderingTests(SimpleTestCase):
    def flash(self, level, text='Your message.', tags=''):
        return render_to_string('oscar/partials/alert_messages.html', {
            'messages': [Message(level, text, extra_tags=tags)],
        })

    def test_success_error_warning_info_and_danger_alias(self):
        for level, tags, expected, role in [
            (messages.SUCCESS, '', 'success', 'status'),
            (messages.ERROR, '', 'danger', 'alert'),
            (messages.WARNING, '', 'warning', 'status'),
            (messages.INFO, '', 'info', 'status'),
            (messages.INFO, 'danger', 'danger', 'alert'),
        ]:
            with self.subTest(level=level, tags=tags):
                html = self.flash(level, 'Original message text.', tags)
                elements = Elements(html).elements
                alerts = [attrs for tag, attrs in elements if 'abdeen-message' in attrs.get('class', '').split()]
                self.assertEqual(len(alerts), 1)
                self.assertIn(f'alert-{expected}', alerts[0]['class'].split())
                self.assertEqual(alerts[0]['role'], role)
                self.assertEqual(alerts[0]['aria-atomic'], 'true')
                close = next(attrs for tag, attrs in elements if tag == 'button')
                self.assertEqual(close['type'], 'button')
                self.assertEqual(close['data-dismiss'], 'alert')
                self.assertEqual(close['aria-label'], 'Dismiss message')
                self.assertEqual(html.count('Original message text.'), 1)

    def test_safe_tag_escaping_and_extra_tags_are_preserved(self):
        text = '<a href="/basket/">View basket</a>'
        self.assertIn('&lt;a href=', self.flash(messages.INFO, text))
        self.assertIn(text, self.flash(messages.SUCCESS, text, 'safe block'))
        self.assertIn(text, self.flash(messages.SUCCESS, mark_safe(text)))
        self.assertIn('alert-block', self.flash(messages.SUCCESS, text, 'safe block'))
        self.assertIn('alert-noicon', self.flash(messages.INFO, 'Plain', 'noicon'))

    def test_empty_messages_keep_oscar_ajax_target_without_alert(self):
        html = render_to_string('oscar/partials/alert_messages.html', {'messages': []})
        self.assertIn('id="messages"', html)
        self.assertNotIn('abdeen-message', html)
        self.assertNotIn('data-dismiss="alert"', html)

    def test_inline_errors_have_valid_description_targets_and_keep_help_text(self):
        class EmailForm(forms.Form):
            email = forms.EmailField(help_text='Use the email linked to your order.')
        form = EmailForm(data={'login-email': 'invalid'}, prefix='login')
        for template in ('form_fields.html', 'form_fields_inline.html'):
            with self.subTest(template=template):
                html = render_to_string(f'oscar/partials/{template}', {'form': form})
                elements = Elements(html).elements
                control = next(attrs for tag, attrs in elements if tag == 'input')
                self.assertEqual(control['aria-invalid'], 'true')
                ids = [attrs.get('id') for tag, attrs in elements if attrs.get('id')]
                for target in control['aria-describedby'].split():
                    self.assertEqual(ids.count(target), 1)
                self.assertIn('Enter a valid email address.', html)
                self.assertIn('Use the email linked to your order.', html)
                self.assertIn('abdeen-field-errors', html)
                self.assertNotIn('data-dismiss="alert"', html)

    def test_non_field_error_text_and_summary_remain_unchanged(self):
        class FailedForm(forms.Form):
            def clean(self):
                raise forms.ValidationError('Your original checkout error.')
        form = FailedForm(data={})
        html = render_to_string('oscar/partials/form_fields.html', {'form': form})
        self.assertIn('Oops! We found some errors', html)
        self.assertIn('please check the error messages below and try again', html)
        self.assertEqual(html.count('Your original checkout error.'), 1)
        self.assertEqual(html.count('role="alert"'), 2)

    def test_valid_fields_and_hidden_fields_do_not_get_errors(self):
        class TokenForm(forms.Form):
            token = forms.CharField(widget=forms.HiddenInput)
            quantity = forms.IntegerField()
        html = render_to_string('oscar/partials/form_fields.html', {
            'form': TokenForm(data={'token': 'keep-me', 'quantity': 2}),
        })
        self.assertIn('value="keep-me"', html)
        self.assertNotIn('aria-invalid', html)
        self.assertNotIn('abdeen-field-errors', html)
        self.assertNotIn('abdeen-message', html)

    def test_dashboard_alert_and_field_templates_remain_oscar(self):
        html = render_to_string('oscar/dashboard/partials/alert_messages.html', {
            'messages': [Message(messages.SUCCESS, 'Dashboard message')],
        })
        self.assertNotIn('abdeen-message', html)
        self.assertIn('Dashboard message', html)


class StorefrontMessageIntegrationTests(TestCase):
    def test_real_add_to_basket_keeps_original_message_and_persists_quantity(self):
        product_class = get_model('catalogue', 'ProductClass').objects.create(name='Watch', track_stock=True)
        product = get_model('catalogue', 'Product').objects.create(title='Signature watch', product_class=product_class)
        partner = get_model('partner', 'Partner').objects.create(name='Message test supplier')
        get_model('partner', 'StockRecord').objects.create(product=product, partner=partner,
            partner_sku='MESSAGE-1', price_currency='JOD', price='125.00', num_in_stock=5)
        self.client.get(product.get_absolute_url())
        for quantity in (1, 2):
            response = self.client.post(reverse('basket:add', kwargs={'pk': product.pk}),
                                        {'quantity': quantity}, follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'abdeen-basket-confirmation', count=1)
            self.assertContains(response, '<strong>Signature watch</strong>', html=False)
            wording = 'has been added' if quantity == 1 else 'have been added'
            self.assertRegex(response.content.decode(), rf'{wording} to your (basket|cart)\.')
            self.assertContains(response, 'data-dismiss="alert"')
            self.assertContains(response, 'role="status"')
        line = get_model('basket', 'Line').objects.get(product=product)
        self.assertEqual(line.quantity, 3)
        self.assertEqual(str(line.price_excl_tax), '125.00')

    def test_storefront_loads_shared_assets_but_dashboard_does_not(self):
        for name in ('home', 'basket:summary', 'customer:login', 'catalogue:index'):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, 'abdeen/css/messages.css')
                self.assertContains(response, 'abdeen/js/messages.js')
                self.assertContains(response, 'id="messages"')
        response = self.client.get(reverse('dashboard:login'))
        self.assertNotContains(response, 'abdeen/css/messages.css')
        self.assertNotContains(response, 'abdeen/js/messages.js')

    def test_actual_login_validation_still_rejects_invalid_credentials(self):
        response = self.client.post(reverse('customer:login'), {
            'login-username': 'not-an-email', 'login-password': 'incorrect', 'login_submit': 'Log In',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'abdeen-field-errors')
        self.assertContains(response, 'role="alert"')
        self.assertNotIn('_auth_user_id', self.client.session)
