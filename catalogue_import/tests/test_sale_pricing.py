from decimal import Decimal

from catalogue_import.models import CatalogueSource
from catalogue_import.tests.test_import import ImportTestCase, fixture


class ImportSalePricingTests(ImportTestCase):
    def test_fill_only_reference_price_and_idempotency(self):
        self.run_import(skip_images=True)
        product = self.imported_product(1)
        stock = product.stockrecords.get()
        self.assertEqual(stock.price, Decimal('12.50'))
        self.assertEqual(stock.regular_price, Decimal('15'))
        self.assertEqual(CatalogueSource.objects.get(product=product).metadata['regular_price'], '15.00')
        self.run_import(skip_images=True)
        self.assertEqual(product.stockrecords.count(), 1)
        stock.refresh_from_db()
        self.assertEqual(stock.regular_price, Decimal('15'))
        stock.regular_price = Decimal('30')
        stock.price = Decimal('11')
        stock.save()
        self.run_import(skip_images=True)
        stock.refresh_from_db()
        self.assertEqual(stock.regular_price, Decimal('30'))
        # Current price remains source-authoritative, exactly as before.
        self.assertEqual(stock.price, Decimal('12.50'))

    def test_missing_or_zero_reference_does_not_create_markdown(self):
        for raw in ['', '0']:
            self.sql.write_text(fixture().replace("'_regular_price', '15.00'", f"'_regular_price', '{raw}'"))
            self.run_import(skip_images=True)
            stock = self.imported_product(1).stockrecords.get()
            self.assertIsNone(stock.regular_price)
            self.assertEqual(stock.price, Decimal('12.50'))

    def test_existing_null_reference_is_filled(self):
        self.run_import(skip_images=True)
        stock = self.imported_product(1).stockrecords.get()
        stock.regular_price = None
        stock.save()
        self.run_import(skip_images=True)
        stock.refresh_from_db()
        self.assertEqual(stock.regular_price, Decimal('15'))
