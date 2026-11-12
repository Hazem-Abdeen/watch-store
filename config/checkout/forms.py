from django import forms
from oscar.apps.checkout.forms import ShippingAddressForm as OscarShippingAddressForm
from oscar.apps.customer.utils import normalise_email
from oscar.core.loading import get_model


class CODCheckoutForm(OscarShippingAddressForm):
    email = forms.EmailField(label='Email', max_length=254)
    method_code = forms.ChoiceField(label='Shipping method', widget=forms.RadioSelect)

    class Meta(OscarShippingAddressForm.Meta):
        fields = ['country', 'first_name', 'last_name', 'line1', 'line2',
                  'line4', 'postcode', 'phone_number', 'notes']
        labels = {'country': 'Country / Region', 'line1': 'Address', 'line2': 'Apartment, suite, etc. (optional)',
                  'line4': 'City', 'postcode': 'Postcode (optional)',
                  'notes': 'Delivery notes (optional)'}
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def adjust_country_field(self):
        # Country stays visible even when Jordan is the only destination.
        self.fields['country'].queryset = get_model('address', 'Country').objects.filter(
            pk='JO', is_shipping_country=True)
        self.fields['country'].empty_label = None

    def __init__(self, *args, methods=(), user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.POSTCODE_REQUIRED = False
        self.fields['method_code'].choices = [(m.code, m.name) for m in methods]
        for name in ['email', 'phone_number', 'first_name', 'last_name', 'line1', 'line4', 'country']:
            self.fields[name].required = True
        self.fields['postcode'].required = False
        self.fields['phone_number'].label = 'Phone'
        self.fields['phone_number'].widget = forms.TextInput(attrs={'type': 'tel'})
        if user and user.is_authenticated:
            self.fields['email'].initial = user.email
            self.fields['email'].help_text = 'Order updates will be sent here. Your account email will not change.'
        autocomplete = {'email': 'email', 'phone_number': 'tel', 'country': 'country',
                        'first_name': 'given-name', 'last_name': 'family-name',
                        'line1': 'address-line1', 'line2': 'address-line2',
                        'line4': 'address-level2', 'postcode': 'postal-code'}
        for name, value in autocomplete.items():
            self.fields[name].widget.attrs['autocomplete'] = value

    def clean_email(self):
        return normalise_email(self.cleaned_data['email'])

    def clean(self):
        data = super().clean()
        phone = data.get('phone_number')
        if phone and hasattr(phone, 'is_valid') and not phone.is_valid():
            self.add_error('phone_number', 'Enter a valid phone number.')
        return data
