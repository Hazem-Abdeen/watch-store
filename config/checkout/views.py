"""One-page COD collection around Oscar's real order-placement pipeline."""
from django.core import signing
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.forms.models import model_to_dict
from oscar.apps.checkout.views import PaymentDetailsView
from oscar.core.loading import get_class, get_model

from .forms import CODCheckoutForm

Repository = get_class('shipping.repository', 'Repository')
Basket = get_model('basket', 'Basket')
Order = get_model('order', 'Order')
Country = get_model('address', 'Country')
ShippingAddress = get_model('order', 'ShippingAddress')
Source = get_model('payment', 'Source')
SourceType = get_model('payment', 'SourceType')


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class CODCheckoutView(PaymentDetailsView):
    template_name = 'oscar/checkout/cod.html'
    template_name_preview = template_name
    pre_conditions = ['check_basket_is_not_empty', 'check_basket_is_valid']
    quote_salt = 'abdeen.cod.checkout'

    def send_order_placed_email(self, order):
        from .notifications import schedule_order_emails
        schedule_order_emails(order)

    def get_pre_conditions(self, request):
        return self.pre_conditions

    def get_skip_conditions(self, request):
        return []

    def get_initial(self):
        initial = {'country': 'JO', 'email': self.checkout_session.get_guest_email()}
        fields = self.checkout_session.new_shipping_address_fields()
        if fields:
            initial.update(fields)
            initial['country'] = fields.get('country_id', 'JO')
        if self.request.user.is_authenticated:
            initial['email'] = initial['email'] or self.request.user.email
            addresses = self.request.user.addresses.filter(country_id='JO', country__is_shipping_country=True)
            if 'address_id' in self.request.GET:
                try:
                    address_id = int(self.request.GET['address_id'])
                except (TypeError, ValueError):
                    raise Http404('Address not found')
                address = get_object_or_404(addresses, pk=address_id)
            else:
                address = addresses.filter(is_default_for_shipping=True).first() if not fields else None
            if address:
                initial.update(model_to_dict(address, fields=CODCheckoutForm.Meta.fields))
        return initial

    def prepare_form(self):
        initial = self.get_initial()
        data = self.request.POST if self.request.method == 'POST' else None
        # Repository gets the proposed destination, never a posted price.
        values = data if data is not None else initial
        country = Country.objects.filter(pk=values.get('country'), is_shipping_country=True).first()
        address = ShippingAddress(country=country, **{
            key: values.get(key, '') for key in ['first_name', 'last_name', 'line1', 'line2', 'line4', 'postcode']
        }) if country else None
        self.methods = Repository().get_shipping_methods(
            basket=self.request.basket, user=self.request.user,
            shipping_addr=address, request=self.request)
        codes = [method.code for method in self.methods]
        code = self.checkout_session.shipping_method_code(self.request.basket)
        initial['method_code'] = code if code in codes else (codes[0] if codes else '')
        self.form = CODCheckoutForm(data=data, initial=initial, methods=self.methods, user=self.request.user)
        selected = values.get('method_code', initial['method_code'])
        self.selected_method = next((m for m in self.methods if m.code == selected), None)

    def get(self, request, *args, **kwargs):
        self.prepare_form()
        return self.render_to_response(self.get_context_data())

    def get_shipping_method(self, basket, shipping_address=None, **kwargs):
        if hasattr(self, 'selected_method'):
            return self.selected_method
        return super().get_shipping_method(basket, shipping_address, **kwargs)

    def get_billing_address(self, shipping_address):
        # Oscar's billing FK is nullable; COD needs no billing address.
        return None

    def quote_data(self, submission):
        basket = self.request.basket
        total, charge = submission['order_total'], submission['shipping_charge']
        return {'basket': basket.pk, 'currency': basket.currency,
                'lines': [[line.pk, line.quantity, str(line.line_price_incl_tax)] for line in basket.all_lines()],
                'total': str(total.incl_tax) if total else None,
                'shipping': str(charge.incl_tax) if charge else None,
                'method': self.selected_method.code if self.selected_method else None}

    def get_context_data(self, **kwargs):
        if not hasattr(self, 'form'):
            self.prepare_form()
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = self.form
        ctx['shipping_options'] = [(method, method.calculate(self.request.basket)) for method in self.methods]
        ctx['quote'] = signing.dumps(self.quote_data(ctx), salt=self.quote_salt)
        if self.request.user.is_authenticated:
            ctx['addresses'] = self.request.user.addresses.filter(country_id='JO', country__is_shipping_country=True).order_by('-is_default_for_shipping')
        return ctx

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') not in ['place_order', 'update']:
            return HttpResponseBadRequest()
        self.prepare_form()
        if not self.form.is_valid():
            return self.render_to_response(self.get_context_data())
        self.checkout_session.set_guest_email(self.form.cleaned_data['email'])
        address_fields = {field.attname: getattr(self.form.instance, field.attname)
                          for field in self.form.instance._meta.fields}
        self.checkout_session.ship_to_new_address(address_fields)
        self.checkout_session.use_shipping_method(self.form.cleaned_data['method_code'])
        self.checkout_session.pay_by('cod')
        submission = self.build_submission()
        # Snapshot the validated checkout contact on the order, including for
        # account orders. Keep user ownership and the login email unchanged.
        submission['order_kwargs']['guest_email'] = self.form.cleaned_data['email']
        if request.POST['action'] == 'update':
            return self.render_to_response(self.get_context_data())
        try:
            quoted = signing.loads(request.POST.get('quote', ''), salt=self.quote_salt, max_age=3600)
        except signing.BadSignature:
            quoted = None
        if quoted != self.quote_data(submission):
            self.form.add_error(None, 'Your bag or delivery total has changed. Please review the total and place your order again.')
            return self.render_to_response(self.get_context_data())
        # Reads above run in autocommit. The claim is the FIRST statement in the
        # write transaction, avoiding SQLite read-to-write lock upgrades when
        # two identical POSTs arrive together (ATOMIC_REQUESTS is enabled).
        # A conditional DB write serializes simultaneous submissions of a basket.
        # Oscar also retains its unique, basket-derived order number protection.
        with transaction.atomic():
            claimed = Basket.objects.filter(pk=request.basket.pk, status=Basket.OPEN).update(status=Basket.FROZEN)
            if not claimed:
                # A concurrent successful request may not have saved its session
                # yet. Write the same confirmation state, never stale form data.
                order = Order.objects.filter(basket_id=request.basket.pk).first()
                if order:
                    self.checkout_session.flush()
                    request.session['checkout_order_id'] = order.pk
                    return redirect('checkout:thank-you')
                request.session.modified = False
                return redirect('basket:summary')
            return self.submit(**submission)

    def handle_payment(self, order_number, total, **kwargs):
        source_type, _ = SourceType.objects.get_or_create(name='Cash on Delivery (COD)')
        self.add_payment_source(Source(source_type=source_type, currency=total.currency,
                                       amount_allocated=total.incl_tax, amount_debited=0,
                                       label='Payment due on delivery'))
        # No debit, payment event, transaction, or external payment request.
