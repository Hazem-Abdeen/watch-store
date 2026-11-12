from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from oscar.core.loading import get_model

from catalogue_import.storefront_transfer import export_bundle, import_bundle, load_bundle, validate, checksum
from catalogue_import.sql_dump import ImportDataError


class StorefrontTransferTests(TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.media = self.root / 'media'
        self.media.mkdir()
        self.enterContext(override_settings(MEDIA_ROOT=self.media))
        pc = get_model('catalogue', 'ProductClass').objects.create(name='Watch', track_stock=True)
        self.product = get_model('catalogue', 'Product').objects.create(product_class=pc, title='Transfer watch', upc='TRANSFER-1')
        self.partner = get_model('partner', 'Partner').objects.create(name='Supplier')
        user = get_user_model().objects.create_user('excluded-local-customer')
        self.partner.users.add(user)
        self.stock = get_model('partner', 'StockRecord').objects.create(product=self.product, partner=self.partner,
            partner_sku='TRANSFER-1', price='42', regular_price='60', price_currency='JOD',
            availability_only=True, is_available=False, num_in_stock=None, num_allocated=0)
        (self.media / 'photo.jpg').write_bytes(b'photo-bytes')
        get_model('catalogue', 'ProductImage').objects.create(product=self.product, original='photo.jpg')

    def export(self):
        self.path = self.root / 'bundle'
        return export_bundle(self.path)

    def test_export_preserves_ids_prices_and_excludes_auth_without_db_writes(self):
        with CaptureQueriesContext(connection) as queries:
            bundle = self.export()
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertFalse(any(row['model'].startswith(('auth.', 'order.', 'sessions.', 'customer.')) for row in bundle['records']))
        partner = next(r for r in bundle['records'] if r['model'] == 'partner.partner')
        self.assertEqual(partner['fields']['users'], [])
        stock = next(r for r in bundle['records'] if r['model'] == 'partner.stockrecord')
        self.assertEqual(stock['pk'], self.stock.pk)
        self.assertEqual(stock['fields']['regular_price'], '60.00')
        self.assertEqual((self.path / 'media/photo.jpg').read_bytes(), b'photo-bytes')
        load_bundle(self.path, bundle['sha256'])

    def test_export_directory_cannot_be_overwritten(self):
        self.export()
        with self.assertRaises(ImportDataError):
            export_bundle(self.path)

    def test_datetime_microseconds_preserved(self):
        from django.utils import timezone
        instant = timezone.now().replace(microsecond=123456)
        type(self.stock).objects.filter(pk=self.stock.pk).update(date_updated=instant)
        bundle = self.export()
        stock = next(r for r in bundle['records'] if r['model'] == 'partner.stockrecord')
        self.assertIn('.123456', stock['fields']['date_updated'])

    def test_modified_archive_and_wrong_reviewed_hash_rejected(self):
        bundle = self.export()
        with self.assertRaises(ImportDataError):
            load_bundle(self.path, '0' * 64)
        (self.path / 'media/photo.jpg').write_bytes(b'changed')
        with self.assertRaises(ImportDataError):
            load_bundle(self.path, bundle['sha256'])

    def test_unsafe_or_missing_source_media_rejected(self):
        (self.media / 'photo.jpg').unlink()
        with self.assertRaises(ImportDataError):
            self.export()
        outside = self.root / 'outside.jpg'
        outside.write_bytes(b'outside')
        (self.media / 'photo.jpg').symlink_to(outside)
        with self.assertRaises(ImportDataError):
            self.export()

    def test_scope_conflict_rejected_without_overwriting(self):
        bundle = self.export()
        self.product.title = 'Target operator edit'
        self.product.save()
        with self.assertRaises(ImportDataError):
            import_bundle(self.path, bundle['sha256'], apply=True)
        self.product.refresh_from_db()
        self.assertEqual(self.product.title, 'Target operator edit')

    def test_exact_repeat_preserves_target_partner_membership(self):
        bundle = self.export()
        self.assertIn('already imported', import_bundle(self.path, bundle['sha256'], apply=True))
        self.assertEqual(self.partner.users.count(), 1)
        self.assertEqual(get_model('catalogue', 'Product').objects.count(), 1)

    def test_enabled_stock_or_out_of_scope_relationship_rejected(self):
        bundle = self.export()
        stock = next(r for r in bundle['records'] if r['model'] == 'partner.stockrecord')
        stock['fields']['is_available'] = True
        with self.assertRaises(ImportDataError):
            validate(bundle['records'])
        stock['fields']['is_available'] = False
        stock['fields']['product'] = 99999
        with self.assertRaises(ImportDataError):
            validate(bundle['records'])

    def test_unapproved_model_rejected_even_with_recomputed_hash(self):
        bundle = self.export()
        bundle['records'].append({'model': 'auth.user', 'pk': 1, 'fields': {}})
        del bundle['sha256']
        bundle['sha256'] = checksum(bundle)
        (self.path / 'bundle.json').write_text(json.dumps(bundle))
        with self.assertRaises(ImportDataError):
            load_bundle(self.path, bundle['sha256'])
