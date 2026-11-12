from oscar.apps.shipping.repository import Repository as OscarRepository

from .methods import Delivery


class Repository(OscarRepository):
    methods = (Delivery(),)

    def get_shipping_methods(self, basket, shipping_addr=None, **kwargs):
        # The delivery fee is the same for every order: no free-shipping
        # fallback or shipping-offer wrappers. Basket discounts still apply
        # normally through Oscar's offer and order-total calculators.
        return self.get_available_shipping_methods(basket, shipping_addr, **kwargs)

    def get_available_shipping_methods(self, basket, shipping_addr=None, **kwargs):
        # No address yet is allowed for the basket's indicative total.
        if shipping_addr is not None and shipping_addr.country_id != 'JO':
            return ()
        return self.methods
