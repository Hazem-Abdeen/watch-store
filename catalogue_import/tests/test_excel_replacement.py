"""Replacement and checkout tests use isolated test databases and media only."""
from copy import deepcopy
from decimal import Decimal
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import connection, transaction, IntegrityError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from oscar.core.loading import get_class, get_model
from PIL import Image

from catalogue_import.excel import HEADERS, digest, validate_workbook
from catalogue_import.excel_images import prepare_images, filename_proves_model
from catalogue_import.excel_replacement import cleanup_inventory, clean_old_catalogue, import_rows, schema_preflight
from catalogue_import.models import CatalogueSource, ExcelCatalogueEntry
from catalogue_import.sql_dump import ImportDataError
from catalogue_import.catalogue import SOURCE

Product = get_model('catalogue', 'Product')
Stock = get_model('partner', 'StockRecord')
ProductImage = get_model('catalogue', 'ProductImage')
Order = get_model('order', 'Order')
Basket = get_model('basket', 'Basket')


def sample(**changes):
    values = dict(zip(HEADERS, [
        '8682308124842', 'BG.1.10450-4', 'Watch', 'Bigotti exact model watch',
        'Bigotti Milano', 'Men', 'Men | Brands / Bigotti Milano', '42 JOD', '60 JOD',
        'Analog Quartz (Battery)', '44 mm', 'Stainless Steel', 'Silver & Gold',
        'Stainless Steel', 'Silver', 'Black', '', '5 Bar', 'Two Years', 'Romania',
    ]))
    return {**values, **changes}


def workbook(path, values):
    rows = [list(HEADERS), *[list(v.get(h, '') for h in HEADERS) for v in values]]
    body = []
    for number, row in enumerate(rows, 1):
        cells = ''.join(f'<c r="{chr(65+i)}{number}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>' for i, v in enumerate(row))
        body.append(f'<row r="{number}">{cells}</row>')
    with ZipFile(path, 'w') as archive:
        archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Catalogue" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(body) + '</sheetData></worksheet>')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ExcelReplacementTests(TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.directory / 'media'))
        (self.directory / 'media').mkdir()
        self.path = self.directory / 'catalogue.xlsx'
        self.manifest_path = self.directory / 'images.json'
        self.prepare([sample()])

    def prepare(self, rows):
        workbook(self.path, rows)
        self.validation = validate_workbook(self.path, expected_count=len(rows))
        self.manifest = {'workbook_sha256': digest(self.path), 'counts': {'unassigned': len(rows)}, 'records': [
            {'row': r['row'], 'sku': r['sku'], 'model': r['model'], 'brand': r['brand'],
             'status': 'unassigned', 'ranges': []} for r in self.validation['rows']]}
        self.manifest_path.write_text(json.dumps(self.manifest))

    def imported(self, available=True):
        schema_preflight(self.validation)
        with transaction.atomic():
            result = import_rows(self.validation, self.manifest_path, initially_available=available)
        self.product = Product.objects.get(upc=self.validation['rows'][0]['sku'])
        self.stock = self.product.stockrecords.get()
        return result

    def test_strict_prices_and_duplicate_identifiers(self):
        for price in ['NaN', 'Infinity', '-1', '0', '1.001', '10000000000', 'USD 42']:
            with self.subTest(price=price):
                self.prepare([sample(Price=price)])
                self.assertTrue(any(i['code'] == 'price' for i in self.validation['issues']))
        self.prepare([sample(), sample(Title='Different title', Price='43')])
        self.assertEqual({i['code'] for i in self.validation['issues'] if i['severity'] == 'error'},
                         {'duplicate_sku', 'duplicate_model'})
        self.assertEqual(len(self.validation['rows']), 2)

    def test_same_model_different_barcode_is_blocked(self):
        self.prepare([sample(), sample(SKU='8681668614253')])
        self.assertTrue(any(i['code'] == 'duplicate_model' for i in self.validation['issues']))

    def test_missing_fields_categories_and_regular_price(self):
        self.prepare([sample(SKU='', Brand='Unknown', Categories='Men', Movement='', **{'Regular Price': '1'})])
        errors = {i['code'] for i in self.validation['issues'] if i['severity'] == 'error'}
        self.assertTrue({'required', 'brand', 'category', 'discount', 'watch_attribute'} <= errors)

    def test_corrections_require_exact_workbook_and_original_row(self):
        correction = self.directory / 'correction.json'
        correction.write_text(json.dumps({'workbook_sha256': 'wrong', 'rows': {}}))
        with self.assertRaises(ImportDataError):
            validate_workbook(self.path, corrections=correction, expected_count=1)
        original = self.validation['raw_rows'][0]
        correction.write_text(json.dumps({'workbook_sha256': digest(self.path), 'rows': {
            '2': {'expected': original, 'set': {'Price': '50'}, 'reason': 'Explicit correction.'}}}))
        corrected = validate_workbook(self.path, corrections=correction, expected_count=1)
        self.assertEqual(corrected['rows'][0]['price'], '50.00')
        self.assertEqual(validate_workbook(self.path, expected_count=1)['rows'][0]['price'], '42.00')

    def test_full_workbook_validation_precedes_limit_or_apply(self):
        self.prepare([sample(), sample(SKU='OTHER', Price='broken', **{'Model Reference': 'OTHER'})])
        with self.assertRaises(CommandError):
            call_command('replace_excel_catalogue', self.path, apply=True, limit=1, expected_count=2,
                         report_dir=self.directory, stdout=StringIO())
        self.assertFalse(Product.objects.exists())

    def test_dry_run_does_not_write_database(self):
        with CaptureQueriesContext(connection) as queries:
            call_command('replace_excel_catalogue', self.path, dry_run=True, expected_count=1,
                         report_dir=self.directory, stdout=StringIO())
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertTrue((self.directory / 'plan.json').exists())

    def test_import_prices_attributes_brand_alias_and_idempotency(self):
        self.assertEqual(self.imported()['created'], 1)
        self.assertEqual((self.stock.price, self.stock.regular_price), (Decimal('42'), Decimal('60')))
        self.assertEqual(self.product.attr.model_reference, 'BG.1.10450-4')
        self.assertEqual(set(self.product.categories.values_list('name', flat=True)), {'Men', 'Bigotti'})
        self.product.title = 'Staff title'
        self.product.is_public = False
        self.product.save()
        self.stock.price, self.stock.regular_price, self.stock.is_available = Decimal('40'), None, False
        self.stock.save()
        image_path = self.directory / 'media' / 'manual.png'
        Image.new('RGB', (10, 10), 'red').save(image_path)
        image = ProductImage.objects.create(product=self.product, original='manual.png', display_order=0)
        result = import_rows(self.validation, self.manifest_path, initially_available=True)
        self.assertEqual(result, {'preserved': 1})
        self.product.refresh_from_db(); self.stock.refresh_from_db()
        self.assertEqual(self.product.title, 'Staff title')
        self.assertFalse(self.product.is_public)
        self.assertEqual(self.stock.price, Decimal('40'))
        self.assertIsNone(self.stock.regular_price)
        self.assertFalse(self.stock.is_available)
        self.assertEqual(self.product.images.get().pk, image.pk)
        self.assertTrue(image_path.exists())

    def test_default_unavailable_has_no_fake_quantity(self):
        self.imported(available=False)
        self.assertIsNone(self.stock.num_in_stock)
        self.assertEqual(self.stock.num_allocated, 0)
        self.assertFalse(get_class('partner.strategy', 'Selector')().strategy().fetch_for_product(self.product).availability.is_available_to_buy)

    def test_database_rejects_fake_quantity_in_availability_mode(self):
        self.imported()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stock.objects.filter(pk=self.stock.pk).update(num_in_stock=1)

    def test_sku_collision_does_not_merge(self):
        self.imported()
        ExcelCatalogueEntry.objects.all().delete()
        with self.assertRaises(ImportDataError):
            import_rows(self.validation, self.manifest_path)
        self.assertEqual(Product.objects.count(), 1)

    def test_accessory_class_no_invented_watch_attributes(self):
        values = sample(**{'Product Type': 'Accessory', 'Model Reference': 'GLJLG0004802',
                           'Brand': 'Guy Laroche', 'Categories': 'Men | Brands / Guy Laroche'})
        for field in HEADERS[9:]:
            values[field] = ''
        self.prepare([values]); self.imported()
        self.assertEqual(self.product.product_class.name, 'Accessory')
        self.assertFalse(self.product.attribute_values.filter(attribute__code='movement').exists())
        self.assertIn('Accessories', self.product.categories.values_list('name', flat=True))

    def test_image_proof_never_fuzzily_shortens_reference(self):
        self.assertTrue(filename_proves_model('2025/BG.1.10450-4.webp', 'BG.1.10450-4'))
        self.assertFalse(filename_proves_model('2025/BG.1.10450-40.webp', 'BG.1.10450-4'))
        self.assertFalse(filename_proves_model('2025/MTP-1374D-5AV.jpg', 'MTP-1374D-5AVDF'))

    def old_image_entry(self):
        photo = self.directory / 'media' / 'old.png'
        Image.new('RGB', (12, 12), 'blue').save(photo)
        return {'product_id': 4, 'source_id': 40, 'sku': sample()['SKU'], 'model': '',
                'brand': 'Bigotti', 'attributes': self.validation['rows'][0]['attributes'],
                'attachment': '2025/BG.1.10450-4.webp', 'image': 'old.png', 'image_id': 5,
                'source_sku_agrees': True, 'provenance_verified': True, 'ranges': []}

    def test_image_archive_independent_and_verified_primary_import(self):
        old = self.old_image_entry()
        with patch('catalogue_import.excel_images.old_catalogue', return_value=[old]):
            manifest = prepare_images(self.validation, self.path, self.directory)
        self.assertEqual(manifest['counts'], {'verified': 1})
        (self.directory / 'media' / 'old.png').unlink()
        self.imported()
        photo = self.product.images.get()
        self.assertEqual(photo.display_order, 0)
        self.assertEqual(digest(photo.original.path), manifest['records'][0]['sha256'])

    def test_conflicting_specs_or_ambiguous_old_identity_leave_placeholder(self):
        for conflict in ['specs', 'duplicate', 'filename']:
            with self.subTest(conflict=conflict):
                old = self.old_image_entry()
                old = deepcopy(old)
                if conflict == 'specs':
                    old['attributes']['dial_color'] = 'Pink'
                if conflict == 'filename':
                    old['attachment'] = 'other-watch.jpg'
                with patch('catalogue_import.excel_images.old_catalogue', return_value=[old, old] if conflict == 'duplicate' else [old]):
                    manifest = prepare_images(self.validation, self.path, self.directory)
                self.assertEqual(manifest['counts'], {'unassigned': 1})

    def test_tampered_archived_image_rolls_back_import(self):
        with patch('catalogue_import.excel_images.old_catalogue', return_value=[self.old_image_entry()]):
            manifest = prepare_images(self.validation, self.path, self.directory)
        (self.directory / manifest['records'][0]['file']).write_bytes(b'bad')
        with self.assertRaises(ImportDataError), transaction.atomic():
            import_rows(self.validation, self.manifest_path)
        self.assertFalse(Product.objects.exists())

    def checkout(self, quantity=3):
        get_model('address', 'Country').objects.get_or_create(iso_3166_1_a2='JO', defaults={
            'iso_3166_1_a3': 'JOR', 'printable_name': 'Jordan', 'name': 'Jordan', 'is_shipping_country': True})
        self.client.post(reverse('basket:add', kwargs={'pk': self.product.pk}), {'quantity': quantity})
        page = self.client.get(reverse('checkout:index'))
        return self.client.post(reverse('checkout:index'), {
            'email': 'guest@example.test', 'phone_number': '0791234567', 'country': 'JO',
            'first_name': 'Test', 'last_name': 'Customer', 'line1': '12 Example Street', 'line4': 'Amman',
            'method_code': 'jordan-delivery', 'action': 'place_order', 'quote': page.context['quote'],
        }, follow=True)

    def test_cod_multiple_units_and_repeat_orders_never_allocate_stock(self):
        self.imported()
        for _ in range(2):
            response = self.checkout(3)
            self.assertTemplateUsed(response, 'oscar/checkout/thank_you.html')
        self.assertEqual(Order.objects.count(), 2)
        for order in Order.objects.all():
            self.assertEqual(order.shipping_incl_tax, Decimal('2'))
            self.assertEqual(order.total_incl_tax, Decimal('128'))
            self.assertEqual(order.sources.get().amount_allocated, Decimal('128'))
            self.assertEqual(order.sources.get().amount_debited, 0)
            line = order.lines.get()
            self.assertEqual(line.num_allocated, 0)
            line.consume_allocation(3); line.cancel_allocation(3)
        self.stock.refresh_from_db()
        self.assertIsNone(self.stock.num_in_stock)
        self.assertEqual(self.stock.num_allocated, 0)
        self.assertTrue(self.stock.is_available)

    def test_disabled_availability_blocks_basket_and_existing_checkout(self):
        self.imported()
        self.client.post(reverse('basket:add', kwargs={'pk': self.product.pk}), {'quantity': 2})
        self.stock.is_available = False; self.stock.save()
        response = self.client.get(reverse('checkout:index'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.exists())
        self.client.post(reverse('basket:add', kwargs={'pk': self.product.pk}), {'quantity': 2})
        self.assertEqual(Basket.objects.get().lines.get().quantity, 2)

    def test_final_allocation_step_rechecks_availability(self):
        self.imported()
        Stock.objects.filter(pk=self.stock.pk).update(is_available=False)
        from oscar.apps.order.exceptions import UnableToPlaceOrder
        with self.assertRaises(UnableToPlaceOrder):
            self.stock.allocate(2)

    def test_availability_change_during_placement_rolls_back_order(self):
        self.imported()
        Creator = get_class('order.utils', 'OrderCreator')
        original = Creator.create_line_models

        def withdraw(creator, *args, **kwargs):
            line = original(creator, *args, **kwargs)
            Stock.objects.filter(pk=self.stock.pk).update(is_available=False)
            return line

        with patch.object(Creator, 'create_line_models', withdraw):
            self.checkout(2)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(get_model('payment', 'Source').objects.exists())
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.num_allocated, 0)

    def test_limit_and_command_rerun_create_only_missing_products(self):
        self.prepare([sample(), sample(SKU='SECOND', **{'Model Reference': 'SECOND'})])
        arguments = dict(apply=True, expected_count=2, report_dir=self.directory, stdout=StringIO())
        call_command('replace_excel_catalogue', self.path, limit=1, **arguments)
        self.assertEqual(Product.objects.count(), 1)
        call_command('replace_excel_catalogue', self.path, **arguments)
        call_command('replace_excel_catalogue', self.path, **arguments)
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(ExcelCatalogueEntry.objects.count(), 2)

    def test_replacement_requires_valid_review_and_disallows_limit(self):
        for arguments in [{'replace': True}, {'replace': True, 'limit': 1}]:
            with self.subTest(arguments=arguments), self.assertRaises(CommandError):
                call_command('replace_excel_catalogue', self.path, apply=True, expected_count=1,
                             report_dir=self.directory, stdout=StringIO(), **arguments)
        self.assertFalse(Product.objects.exists())

    def test_dashboard_real_edit_preserves_null_inventory(self):
        self.imported()
        staff = get_user_model().objects.create_superuser('excel-staff', 'staff@example.test', 'pass')
        self.client.force_login(staff)
        url = reverse('dashboard:catalogue-product', kwargs={'pk': self.product.pk})
        response = self.client.get(url)
        self.assertContains(response, 'stockrecords-0-is_available')
        data = {}
        forms = [response.context['form']]
        for name in response.context['view'].formsets:
            formset = response.context[name]
            forms.extend([formset.management_form, *formset.initial_forms])
        for form in forms:
            for field in form:
                value = field.value()
                if value is not False:
                    data[field.html_name] = 'on' if value is True else (value if value is not None else '')
        for name in response.context['view'].formsets:
            formset = response.context[name]
            data[f'{formset.prefix}-TOTAL_FORMS'] = str(formset.initial_form_count())
        data.update(title='Dashboard edit', **{'stockrecords-0-price': '39', 'stockrecords-0-regular_price': '65'})
        data.pop('stockrecords-0-is_available', None)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None))
        self.stock.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual(self.product.title, 'Dashboard edit')
        self.assertEqual(self.stock.price, Decimal('39'))
        self.assertEqual(self.stock.regular_price, Decimal('65'))
        self.assertFalse(self.stock.is_available)
        self.assertIsNone(self.stock.num_in_stock)

    def test_imported_storefront_routes_search_placeholder_and_discount(self):
        self.imported()
        call_command('rebuild_index', interactive=False, verbosity=0, stdout=StringIO())
        urls = ['/', reverse('catalogue:index'), reverse('search:search') + '?q=Bigotti']
        urls.extend(c.get_absolute_url() for c in self.product.categories.all())
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get(self.product.get_absolute_url()).status_code, 404)
        self.assertFalse(self.product.images.exists())
        photo = self.directory / 'media' / 'confirmed.png'
        Image.new('RGB', (10, 10), 'blue').save(photo)
        get_model('catalogue', 'ProductImage').objects.create(product=self.product, original='confirmed.png')
        detail = self.client.get(self.product.get_absolute_url())
        self.assertContains(detail, 'Available to order')
        self.assertNotContains(detail, 'In stock, ready to ship')
        self.assertContains(detail, '30%')
        self.assertContains(detail, 'BG.1.10450-4')
        self.assertEqual(self.product.images.count(), 1)

    def test_cleanup_preserves_orders_settings_and_original_image_file(self):
        self.imported(); self.checkout(1)
        ExcelCatalogueEntry.objects.all().delete()
        CatalogueSource.objects.create(source=SOURCE, source_id=40, product=self.product, stockrecord=self.stock)
        photo = self.directory / 'media' / 'original.png'
        Image.new('RGB', (10, 10), 'white').save(photo)
        ProductImage.objects.create(product=self.product, original='original.png')
        inventory = cleanup_inventory()
        old_total = Order.objects.get().total_incl_tax
        with transaction.atomic():
            clean_old_catalogue(inventory)
        self.assertFalse(Product.objects.exists())
        self.assertFalse(Stock.objects.exists())
        self.assertTrue(photo.exists())
        order = Order.objects.get()
        self.assertEqual(order.total_incl_tax, old_total)
        self.assertEqual(order.lines.get().num_allocated, 0)
        self.assertIsNone(order.lines.get().product_id)
        self.assertIsNone(order.lines.get().stockrecord_id)
        self.assertTrue(get_model('catalogue', 'ProductClass').objects.exists())
        self.assertTrue(get_model('catalogue', 'Category').objects.exists())

    def test_changed_relationships_abort_cleanup(self):
        self.imported()
        ExcelCatalogueEntry.objects.all().delete()
        CatalogueSource.objects.create(source=SOURCE, source_id=40, product=self.product, stockrecord=self.stock)
        inventory = cleanup_inventory()
        self.stock.price = Decimal('55'); self.stock.save()
        with self.assertRaises(ImportDataError), transaction.atomic():
            clean_old_catalogue(inventory)
        self.assertTrue(Product.objects.exists())

    @override_settings(DEBUG=True)
    def test_reviewed_command_replaces_in_one_transaction(self):
        self.imported()
        old_id = self.product.pk
        ExcelCatalogueEntry.objects.all().delete()
        CatalogueSource.objects.create(source=SOURCE, source_id=40, product=self.product, stockrecord=self.stock)
        self.prepare([sample(SKU='NEW', **{'Model Reference': 'NEW'})])
        command = 'catalogue_import.management.commands.replace_excel_catalogue.'
        arguments = dict(expected_count=1, report_dir=self.directory, stdout=StringIO())
        with patch(command + 'prepare_images', return_value=self.manifest):
            call_command('replace_excel_catalogue', self.path, dry_run=True, **arguments)
            with patch(command + 'backup_local', return_value=self.directory) as backup:
                call_command('replace_excel_catalogue', self.path, apply=True, replace=True,
                             reviewed_plan=self.directory / 'plan.json', **arguments)
            backup.assert_called_once()
        self.assertFalse(Product.objects.filter(pk=old_id).exists())
        self.assertEqual(list(Product.objects.values_list('upc', flat=True)), ['NEW'])
        self.assertEqual(ExcelCatalogueEntry.objects.count(), 1)
        self.assertFalse(CatalogueSource.objects.exists())

    @override_settings(DEBUG=True)
    def test_import_failure_rolls_back_old_catalogue_cleanup(self):
        self.imported()
        ExcelCatalogueEntry.objects.all().delete()
        CatalogueSource.objects.create(source=SOURCE, source_id=40, product=self.product, stockrecord=self.stock)
        self.prepare([sample(SKU='NEW', **{'Model Reference': 'NEW'})])
        command = 'catalogue_import.management.commands.replace_excel_catalogue.'
        arguments = dict(expected_count=1, report_dir=self.directory, stdout=StringIO())
        with patch(command + 'prepare_images', return_value=self.manifest):
            call_command('replace_excel_catalogue', self.path, dry_run=True, **arguments)
            with patch(command + 'backup_local', return_value=self.directory), patch(command + 'import_rows', side_effect=ImportDataError('Failure')) as failing_import:
                with self.assertRaises(CommandError):
                    call_command('replace_excel_catalogue', self.path, apply=True, replace=True,
                                 reviewed_plan=self.directory / 'plan.json', **arguments)
                failing_import.assert_called_once()
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assertTrue(Stock.objects.filter(pk=self.stock.pk).exists())
        self.assertTrue(CatalogueSource.objects.exists())
