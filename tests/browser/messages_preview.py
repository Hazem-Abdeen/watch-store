"""Isolated storefront presentation fixture; never installed in production URLs."""
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings

preview_directory = TemporaryDirectory(prefix='abdeen-messages-')
with sqlite3.connect(settings.DATABASES['default']['NAME']) as source:
    with sqlite3.connect(Path(preview_directory.name) / 'db.sqlite3') as target:
        source.backup(target)
settings.DATABASES['default']['NAME'] = Path(preview_directory.name) / 'db.sqlite3'
settings.ROOT_URLCONF = __name__

import django
django.setup()
from django import forms
from django.contrib import messages
from django.core.management import call_command
from django.http import HttpResponse
from django.template import engines
from django.urls import path
from config.urls import urlpatterns as storefront_urls

class ValidationForm(forms.Form):
    email = forms.EmailField(help_text='Use the email linked to your order.')
    voucher = forms.CharField(label='Voucher code', max_length=20)

TEMPLATE = '''{% extends 'oscar/layout.html' %}
{% block title %}Message presentation verification{% endblock %}
{% block content %}
<h1>Message presentation</h1>
<form method="post" novalidate>
{% csrf_token %}{% include 'oscar/partials/form_fields.html' %}
<button type="submit" class="btn btn-primary">Continue</button>
</form>
<div class="alert alert-warning" id="legacy-alert">An inherited Oscar warning with a <a href="/basket/">basket link</a>.</div>
<div class="form-group"><label for="legacy-input">Legacy quantity</label><input id="legacy-input" value="0"><span class="error-block">This quantity is unavailable.</span></div>
{% endblock %}'''

def preview(request):
    messages.success(request, 'The watch was added to your basket.')
    messages.error(request, 'Please check your payment details and try again.')
    messages.warning(request, 'This voucher cannot be applied to the current basket.')
    messages.info(request, 'Your delivery options will appear after you enter an address.')
    form = ValidationForm(data={'verify-email': 'invalid', 'verify-voucher': ''}, prefix='verify')
    template = TEMPLATE
    if request.GET.get('checkout'):
        template = template.replace("extends 'oscar/layout.html'", "extends 'oscar/checkout/layout.html'")
    return HttpResponse(engines['django'].from_string(template).render({'form': form}, request))

urlpatterns = [path('__messages__/', preview), *storefront_urls]
if __name__ == '__main__':
    try:
        call_command('runserver', '127.0.0.1:8020', use_reloader=False)
    finally:
        preview_directory.cleanup()
