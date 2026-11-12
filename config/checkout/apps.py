from oscar.apps.checkout.apps import CheckoutConfig as OscarCheckoutConfig


class CheckoutConfig(OscarCheckoutConfig):
    name = 'config.checkout'

    def ready(self):
        super().ready()
        from .views import CODCheckoutView
        # Keep Oscar's named URLs and protected address-book/thank-you views.
        # Every checkout entry point now uses the same validated COD form.
        self.index_view = CODCheckoutView
        self.shipping_address_view = CODCheckoutView
        self.shipping_method_view = CODCheckoutView
        self.payment_method_view = CODCheckoutView
        self.payment_details_view = CODCheckoutView
