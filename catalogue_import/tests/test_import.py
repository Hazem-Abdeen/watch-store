from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.request import Request

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from PIL import Image

from catalogue_import.catalogue import OscarImporter, description_html, models, price_value
from catalogue_import.images import UploadsRedirectHandler, download_image, uploads_url
from catalogue_import.sql_dump import ImportDataError, literal_rows


def insert(table, columns, rows):
    def literal(value):
        if value is None:
            return 'NULL'
        if isinstance(value, int):
            return str(value)
        return "'" + value.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n') + "'"
    return (f'INSERT INTO `{table}` (' + ', '.join(f'`{c}`' for c in columns) + ') VALUES\n'
            + ',\n'.join('(' + ', '.join(literal(v) for v in row) + ')' for row in rows) + ';\n')


def fixture(second_price='20', second_type='simple'):
    return ''.join([
        '-- Fixture only; not production content\nSET NAMES utf8mb4;\n',
        insert('wp_posts', ['ID', 'post_type', 'post_status', 'post_title', 'post_content'], [
            (1, 'product', 'publish', "Watch; O'Reilly, عربي", '<p>Useful <strong>description</strong></p>'),
            (2, 'product', 'publish', 'Second watch', 'Second description'),
            (3, 'product', 'draft', 'Draft watch', 'Do not import'),
            (4, 'shop_order', 'publish', 'Order', 'Do not import'),
            (5, 'post', 'publish', 'Blog', 'Do not import'),
            (6, 'product_variation', 'publish', 'Variant', 'Do not import'),
            (10, 'attachment', 'inherit', 'Image', ''),
        ]),
        insert('wp_postmeta', ['post_id', 'meta_key', 'meta_value'], [
            (1, '_sku', 'ABC/1'), (1, '_price', '12.50'), (1, '_regular_price', '15.00'),
            (1, '_sale_price', '12.50'), (1, '_stock_status', 'instock'), (1, '_thumbnail_id', '10'),
            (2, '_sku', 'ABC/2'), (2, '_price', second_price), (2, '_regular_price', '20'),
            (2, '_sale_price', ''), (2, '_stock_status', 'outofstock'),
            (10, '_wp_attached_file', '2023/05/watch.png'), (4, '_billing_email', 'private@example.invalid'),
        ]),
        insert('wp_terms', ['term_id', 'name'], [
            (20, 'For Men'), (21, 'CASIO'), (22, 'CASIO DIGILTAL'), (23, 'For Women'),
            (24, 'simple'), (25, 'Blog category'), (26, second_type),
        ]),
        insert('wp_term_taxonomy', ['term_taxonomy_id', 'term_id', 'taxonomy', 'parent'], [
            (30, 20, 'product_cat', 0), (31, 21, 'product_cat', 0),
            (32, 22, 'product_cat', 21), (33, 23, 'pa_gender', 0),
            (34, 24, 'product_type', 0), (35, 25, 'category', 0), (36, 26, 'product_type', 0),
        ]),
        insert('wp_term_relationships', ['object_id', 'term_taxonomy_id'], [
            (1, 30), (1, 32), (1, 34), (1, 35), (2, 33), (2, 36), (3, 31), (5, 35),
        ]),
        insert('wp_wc_product_meta_lookup', ['product_id'], [(1,), (2,)]),
        insert('wp_users', ['ID', 'user_login'], [(123, 'must-not-import')]),
        insert('wp_comments', ['comment_ID', 'comment_content'], [(123, 'must-not-import')]),
    ])


class ParserAndImageTests(SimpleTestCase):
    def test_literals_preserve_unicode_and_sql_escaping(self):
        rows = list(literal_rows("(1, 'عربي; (a,b) O\\'Reilly', 'it''s', 'a\\nb', NULL, 'C:\\\\x')"))
        self.assertEqual(rows, [['1', "عربي; (a,b) O'Reilly", "it's", 'a\nb', None, 'C:\\x']])

    def test_invalid_row_syntax_is_rejected(self):
        for value in ["(1, 'unfinished)", '(1, NOW())', "(1, 'a'),", '(1,)', "(1 'a')"]:
            with self.subTest(value=value), self.assertRaises(ImportDataError):
                list(literal_rows(value))

    def test_urls_confined_to_uploads(self):
        self.assertEqual(uploads_url('2023/05/a b.png'),
                         'https://abdeenwatches.com/wp-content/uploads/2023/05/a%20b.png')
        self.assertEqual(uploads_url('http://www.abdeenwatches.com/wp-content/uploads/a.png'),
                         'https://abdeenwatches.com/wp-content/uploads/a.png')
        for value in ['https://evil.test/wp-content/uploads/a.png',
                      'https://abdeenwatches.com.evil.test/wp-content/uploads/a.png',
                      'https://abdeenwatches.com@evil.test/wp-content/uploads/a.png',
                      'https://abdeenwatches.com:444/wp-content/uploads/a.png',
                      '//evil.test/wp-content/uploads/a.png', '/etc/passwd', 'file:///etc/passwd',
                      '../a.png', '2023/%2e%2e/a.png', '2023/%252e%252e/a.png',
                      '2023/a%2fb/../c.png', '2023/a\\b.png', '2023/a.png?url=evil',
                      '2023/a%00.png', '\nhttps://evil.test/a.png']:
            with self.subTest(value=value), self.assertRaises(ImportDataError):
                uploads_url(value)

    def test_redirect_is_checked_before_following(self):
        request = Request('https://abdeenwatches.com/wp-content/uploads/a.png')
        with self.assertRaises(ImportDataError):
            UploadsRedirectHandler().redirect_request(request, None, 302, '', {}, 'https://evil.test/a.png')
        with self.assertRaises(ImportDataError):
            UploadsRedirectHandler().redirect_request(request, None, 302, '', {}, 'https://abdeenwatches.com/login')

    def test_downloader_rejects_nonimages_and_excessive_bytes(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.geturl.return_value = 'https://abdeenwatches.com/wp-content/uploads/a.png'
        response.read.return_value = b'<html>not an image</html>'
        with patch('catalogue_import.images.build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(OSError):
                download_image(response.geturl())
            response.read.return_value = b'12345'
            with patch('catalogue_import.images.MAX_BYTES', 4), self.assertRaises(ImportDataError):
                download_image(response.geturl())

    def test_description_removes_active_content_and_remote_assets(self):
        value = '<p onclick="evil()">Hi &amp; bye<script>evil()</script><img src="https://evil.test/x"><b>safe</b></p>'
        self.assertEqual(description_html(value), '<p>Hi &amp; bye<b>safe</b></p>')

    def test_price_requires_exact_oscar_precision(self):
        self.assertEqual(price_value('0', 'price'), Decimal('0'))
        self.assertIsNone(price_value('', 'price'))
        for value in ['NaN', 'Infinity', '-1', '12.345', '10000000000', 'not a number']:
            with self.subTest(value=value), self.assertRaises(ImportDataError):
                price_value(value, 'price')


class CommandTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sql = Path(self.temp.name) / 'fixture.sql'
        self.sql.write_text(fixture(), encoding='utf-8')
        self.media = Path(self.temp.name) / 'media'
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.m = models()

    def run_import(self, **kwargs):
        stdout, stderr = StringIO(), StringIO()
        call_command('import_woocommerce_catalog', sql_file=self.sql,
                     stdout=stdout, stderr=stderr, **kwargs)
        return stdout.getvalue(), stderr.getvalue()

    def test_dry_run_has_no_writes_or_downloads(self):
        with patch('catalogue_import.catalogue.download_image') as download:
            with CaptureQueriesContext(connection) as queries:
                output, _ = self.run_import(dry_run=True, limit=1)
            download.assert_not_called()
        self.assertIn('created=1 updated=0 skipped=0 failed=0', output)
        self.assertEqual(self.m['Product'].objects.count(), 0)
        self.assertEqual(self.m['Category'].objects.count(), 0)
        self.assertEqual(self.m['Partner'].objects.count(), 0)
        self.assertFalse(self.media.exists())
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))

    def test_mapping_and_idempotent_reruns(self):
        output, _ = self.run_import(skip_images=True)
        self.assertIn('created=2 updated=0 skipped=0 failed=0', output)
        self.assertEqual(self.m['Product'].objects.count(), 2)
        self.assertEqual(get_user_model().objects.count(), 0)
        first = self.m['Product'].objects.get(upc='wc-abdeen-1')
        self.assertEqual(first.title, "Watch; O'Reilly, عربي")
        self.assertEqual(first.description, '<p>Useful <strong>description</strong></p>')
        stock = first.stockrecords.get()
        self.assertEqual((stock.partner_sku, stock.price, stock.price_currency, stock.num_in_stock),
                         ('ABC/1', Decimal('12.50'), 'JOD', 1))
        self.assertEqual(first.attr.wc_regular_price, '15.00')
        self.assertEqual(first.attr.wc_sale_price, '12.50')
        self.assertEqual(set(first.categories.values_list('name', flat=True)), {'Men', 'CASIO', 'CASIO DIGITAL'})
        digital = self.m['Category'].objects.get(name='CASIO DIGITAL')
        self.assertEqual(digital.get_parent().name, 'CASIO')
        self.assertEqual(digital.get_parent().get_parent().name, 'Brands')
        second = self.m['Product'].objects.get(upc='wc-abdeen-2')
        self.assertEqual(second.stockrecords.get().num_in_stock, 0)
        self.assertEqual(list(second.categories.values_list('name', flat=True)), ['Women'])
        category = self.m['Category'].add_root(name='Manual category')
        first.categories.add(category)
        first.is_public = False
        first.save()
        counts = {name: model.objects.count() for name, model in self.m.items()}
        output, _ = self.run_import(skip_images=True)
        self.assertIn('created=0 updated=2 skipped=0 failed=0', output)
        self.assertEqual(counts, {name: model.objects.count() for name, model in self.m.items()})
        first.refresh_from_db()
        self.assertFalse(first.is_public)
        self.assertTrue(first.categories.filter(pk=category.pk).exists())

    def test_updated_sku_uses_same_product_and_stock(self):
        self.run_import(skip_images=True)
        product = self.m['Product'].objects.get(upc='wc-abdeen-1')
        stock_id = product.stockrecords.get().pk
        self.sql.write_text(fixture().replace('ABC/1', 'CHANGED/1'), encoding='utf-8')
        self.run_import(skip_images=True)
        stock = product.stockrecords.get()
        self.assertEqual(stock.pk, stock_id)
        self.assertEqual(stock.partner_sku, 'CHANGED/1')

    def test_malformed_sql_after_selected_products_prevents_all_writes(self):
        self.sql.write_text(fixture() + "INSERT INTO `wp_terms` (`term_id`, `name`) VALUES (99, 'broken'); garbage", encoding='utf-8')
        with self.assertRaisesMessage(CommandError, 'no writes or downloads'):
            self.run_import(limit=1)
        self.assertEqual(self.m['Product'].objects.count(), 0)

    def test_bad_column_count_and_invalid_price_prevent_all_writes(self):
        for text in [fixture(second_price='12.345'),
                     fixture() + 'INSERT INTO `wp_terms` (`term_id`, `name`) VALUES (99);']:
            with self.subTest(text=text[-60:]):
                self.sql.write_text(text, encoding='utf-8')
                with self.assertRaisesMessage(CommandError, 'Preflight failed'):
                    self.run_import(skip_images=True)
                self.assertEqual(self.m['Product'].objects.count(), 0)

    def test_duplicate_sku_prevents_overwriting(self):
        self.sql.write_text(fixture().replace('ABC/2', 'ABC/1'), encoding='utf-8')
        with self.assertRaisesMessage(CommandError, 'Duplicate SKU'):
            self.run_import(skip_images=True)
        self.assertEqual(self.m['Product'].objects.count(), 0)

    def test_transaction_rolls_back_only_failed_product(self):
        original = OscarImporter.category

        def category(importer, path, create=True):
            if create and path == ('Women',):
                raise ImportDataError('Simulated failure after stock creation')
            return original(importer, path, create=create)

        with patch.object(OscarImporter, 'category', category):
            with self.assertRaisesMessage(CommandError, 'Stopped at product 2'):
                self.run_import(skip_images=True)
        self.assertEqual(list(self.m['Product'].objects.values_list('upc', flat=True)), ['wc-abdeen-1'])
        self.assertEqual(self.m['StockRecord'].objects.count(), 1)
        self.assertFalse(self.m['Category'].objects.filter(name='Women').exists())

    def test_missing_image_does_not_fail_product_and_is_retried(self):
        with patch('catalogue_import.catalogue.download_image', side_effect=OSError('missing')) as download:
            output, error = self.run_import(limit=1)
            self.assertIn('created=1 updated=0 skipped=0 failed=0', output)
            self.assertIn('images_failed=1', output)
            self.assertIn('image unavailable', error)
            self.run_import(limit=1)
            self.assertEqual(download.call_count, 2)
        self.assertEqual(self.m['ProductImage'].objects.count(), 0)
        self.assertEqual(self.m['Product'].objects.count(), 1)

    def test_image_saved_through_storage_and_not_duplicated(self):
        buf = BytesIO()
        Image.new('RGB', (2, 2)).save(buf, format='PNG')
        with patch('catalogue_import.catalogue.download_image', return_value=(buf.getvalue(), 'png')) as download:
            self.run_import(limit=1)
            self.run_import(limit=1)
            download.assert_called_once()
        image = self.m['ProductImage'].objects.get()
        self.assertTrue(image.original.storage.exists(image.original.name))
        self.assertEqual(image.original.read(), buf.getvalue())

    def test_image_database_failure_cleans_new_file_and_keeps_product(self):
        with patch('catalogue_import.catalogue.download_image', return_value=(b'test', 'png')):
            with patch.object(self.m['ProductImage'], 'save', side_effect=RuntimeError('failure')):
                output, _ = self.run_import(limit=1)
        self.assertIn('images_failed=1', output)
        self.assertEqual(self.m['Product'].objects.count(), 1)
        self.assertEqual(self.m['ProductImage'].objects.count(), 0)
        self.assertEqual([p for p in self.media.rglob('*') if p.is_file()], [])

    def test_unsupported_product_type_is_skipped(self):
        self.sql.write_text(fixture(second_type='variable'), encoding='utf-8')
        output, _ = self.run_import(skip_images=True)
        self.assertIn('created=1 updated=0 skipped=1 failed=0', output)

    def test_active_stock_allocations_are_not_overwritten(self):
        self.run_import(skip_images=True)
        self.m['StockRecord'].objects.filter(partner_sku='ABC/1').update(num_allocated=1)
        with self.assertRaisesMessage(CommandError, 'active allocations'):
            self.run_import(skip_images=True)
        self.assertEqual(self.m['StockRecord'].objects.get(partner_sku='ABC/1').num_allocated, 1)

    def test_unknown_or_backorder_stock_and_missing_price_are_unavailable(self):
        for state in ('onbackorder', 'unknown'):
            self.sql.write_text(fixture().replace("'instock'", f"'{state}'").replace("'_price', '12.50'", "'_price', ''"), encoding='utf-8')
            self.run_import(skip_images=True, limit=1)
            stock = self.m['StockRecord'].objects.get()
            self.assertEqual(stock.num_in_stock, 0)
            self.assertIsNone(stock.price)

    def test_limit_must_be_positive(self):
        for limit in (0, -1):
            with self.assertRaisesMessage(CommandError, 'positive integer'):
                self.run_import(limit=limit)
