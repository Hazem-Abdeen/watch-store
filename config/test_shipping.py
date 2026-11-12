"""Oscar loads the project policy for both basket estimates and checkout."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase
from oscar.core.loading import get_class

from config.shipping.methods import Delivery
from config.shipping.repository import Repository


class DeliveryTests(SimpleTestCase):
    def test_oscar_resolves_project_repository(self):
        self.assertIs(get_class('shipping.repository', 'Repository'), Repository)

    def test_fixed_price_has_no_threshold_city_weight_or_shipping_required_exception(self):
        for subtotal in ['0.00', '189.00', '10000.00']:
            for city in ['Amman', 'Aqaba', 'Irbid']:
                with self.subTest(subtotal=subtotal, city=city):
                    basket = Mock(currency='JOD', total_incl_tax=Decimal(subtotal), has_shipping_discounts=True)
                    basket.is_shipping_required.return_value = False
                    methods = Repository().get_shipping_methods(basket,
                        shipping_addr=SimpleNamespace(country_id='JO', line4=city))
                    self.assertEqual(len(methods), 1)
                    self.assertIsInstance(methods[0], Delivery)
                    charge = methods[0].calculate(basket)
                    self.assertEqual(charge.currency, 'JOD')
                    self.assertEqual(charge.excl_tax, Decimal('2.00'))
                    self.assertEqual(charge.incl_tax, Decimal('2.00'))
                    self.assertEqual(charge.tax, Decimal('0.00'))
                    self.assertFalse(methods[0].is_discounted)

    def test_foreign_destination_has_no_method(self):
        self.assertEqual(Repository().get_shipping_methods(Mock(),
            shipping_addr=SimpleNamespace(country_id='GB')), ())

    def test_basket_estimate_without_address_is_two_jod(self):
        basket = SimpleNamespace(currency='JOD')
        method = Repository().get_default_shipping_method(basket)
        self.assertEqual(method.calculate(basket).incl_tax, Decimal('2.00'))
