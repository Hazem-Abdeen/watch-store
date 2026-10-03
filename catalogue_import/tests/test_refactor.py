from hashlib import sha256
from io import StringIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext

from catalogue_import.catalogue import LEGACY_ATTRIBUTES, SOURCE, build_plans, description_html
from catalogue_import.cleanup import cleanup_legacy_products
from catalogue_import.models import CatalogueSource
from catalogue_import.specifications import extract_specifications, php_attributes
from catalogue_import.sql_dump import ImportDataError, load_catalogue

from .test_import import ImportTestCase, fixture, insert


DESCRIPTION = '''Gender: Women
Guarantee: Two Years (International)
Water Resistant: 5 Bar (Diving)
Dial Color: White
Brand: Lotus
Band Material: St.Steel
Band Color: Gold
Case Color: Gold
Case Size: 32.5 mm
Case Material: Stainless Steel
Movement Type: Analog Quartz (Battery)'''


def serialize(value):
    if isinstance(value, int):
        return f'i:{value};'
    if isinstance(value, str):
        return f's:{len(value.encode("utf-8"))}:"{value}";'
    return f'a:{len(value)}:{{' + ''.join(serialize(key) + serialize(item) for key, item in value.items()) + '}'


class SpecificationTests(SimpleTestCase):
    def test_real_description_labels(self):
        specs = extract_specifications(description_html(DESCRIPTION))
        self.assertEqual(len(specs), 11)
        self.assertEqual(specs['movement'], 'Analog Quartz (Battery)')
        self.assertEqual(specs['case_size'], '32.5 mm')
        self.assertEqual(specs['water_resistance'], '5 Bar (Diving)')
        self.assertEqual(specs['guarantee'], 'Two Years (International)')

    def test_tables_lists_taxonomies_and_visible_custom_attributes(self):
        description = '<table><tr><th>Case size</th><td>40 mm</td></tr></table><p>Movement: Quartz</p>'
        attrs = {'movement': {'name': 'Movement', 'value': 'Automatic', 'is_visible': 1, 'is_taxonomy': 0},
                 'band-color': {'name': 'Band color', 'value': 'Hidden', 'is_visible': 0}}
        specs = extract_specifications(description, attributes=attrs,
                                       taxonomy_values=[('pa_gender', ['For Men', 'For Women']),
                                                        ('pa_band-material', ['Leather'])])
        self.assertEqual(specs, {'case_size': '40 mm', 'movement': 'Automatic',
                                'gender': 'Men, Women', 'band_material': 'Leather'})

    def test_no_inference_from_marketing_text(self):
        self.assertEqual(extract_specifications('A gold watch with a steel band for adventurous men.'), {})

    def test_php_scalar_arrays_use_utf8_byte_lengths(self):
        attrs = {'movement': {'name': 'Movement', 'value': 'حركة Quartz', 'is_visible': 1}}
        self.assertEqual(php_attributes(serialize(attrs)), attrs)

    def test_php_objects_references_truncation_and_size_are_rejected(self):
        for value in ['O:4:"Evil":0:{}', 'R:1;', 'a:1:{i:0;s:9:"short";}', 'a:0:{}junk',
                      'a:999999:{}', 'a:1:{i:0;', 'x' * 65537]:
            with self.subTest(value=value[:60]), self.assertRaises(ImportDataError):
                php_attributes(value)


class RefactorTests(ImportTestCase):
    def test_existing_watch_and_normal_partner_are_reused(self):
        partner = self.m['Partner'].objects.create(name='Abdeen Watches', code='existing-supplier')
        self.run_import(skip_images=True)
        self.assertEqual(self.m['ProductClass'].objects.count(), 1)
        self.assertEqual(self.m['Partner'].objects.count(), 1)
        self.assertEqual(set(self.m['StockRecord'].objects.values_list('partner_id', flat=True)), {partner.pk})
        for model in ('ProductClass', 'Partner', 'ProductAttribute'):
            self.assertFalse(self.m[model].objects.filter(name__icontains='woocommerce').exists())

    def test_description_and_custom_attributes_are_normal_watch_specs(self):
        attrs = {'movement': {'name': 'Movement', 'value': 'Automatic', 'is_visible': 1}}
        self.sql.write_text(fixture().replace('<p>Useful <strong>description</strong></p>',
                                              DESCRIPTION.replace('\n', '\\n'))
                            + insert('wp_postmeta', ['post_id', 'meta_key', 'meta_value'],
                                     [(1, '_product_attributes', serialize(attrs))]), encoding='utf-8')
        self.run_import(skip_images=True, limit=1)
        product = self.imported_product(1)
        self.assertEqual(product.attr.movement, 'Automatic')
        self.assertEqual(product.attr.case_size, '32.5 mm')
        self.assertEqual(product.attr.guarantee, 'Two Years (International)')
        self.assertEqual(product.attr.water_resistance, '5 Bar (Diving)')
        self.assertFalse(product.attributes.filter(code__startswith='wc_').exists())

    def test_known_specification_taxonomies_are_imported(self):
        self.sql.write_text(fixture()
                            + insert('wp_terms', ['term_id', 'name'], [(50, 'Leather')])
                            + insert('wp_term_taxonomy', ['term_taxonomy_id', 'term_id', 'taxonomy', 'parent'],
                                     [(60, 50, 'pa_band-material', 0)])
                            + insert('wp_term_relationships', ['object_id', 'term_taxonomy_id'], [(1, 60)]),
                            encoding='utf-8')
        self.run_import(skip_images=True, limit=1)
        self.assertEqual(self.imported_product(1).attr.band_material, 'Leather')

    def test_required_brand_attribute_is_reused(self):
        attribute = self.m['ProductAttribute'].objects.create(
            product_class=self.watch, code='watch_brand', name='Brand', type='text', required=True)
        self.run_import(skip_images=True, limit=1)
        self.assertEqual(self.imported_product(1).attr.watch_brand, 'CASIO')
        self.assertEqual(self.watch.attributes.filter(name='Brand').get(), attribute)

    def test_incompatible_attribute_and_missing_watch_are_clear_preflight_errors(self):
        self.m['ProductAttribute'].objects.create(product_class=self.watch, code='brand', name='Brand', type='option')
        with self.assertRaisesMessage(CommandError, 'expects a text attribute'):
            self.run_import(skip_images=True)
        self.watch.delete()
        with self.assertRaisesMessage(CommandError, 'existing product type named Watch'):
            self.run_import(skip_images=True)
        self.assertFalse(CatalogueSource.objects.exists())


class CleanupTests(ImportTestCase):
    def make_legacy(self, source_id=1):
        product_class, _ = self.m['ProductClass'].objects.get_or_create(
            slug='woocommerce-catalogue', defaults={'name': 'WooCommerce catalogue'})
        partner, _ = self.m['Partner'].objects.get_or_create(
            code='woocommerce-abdeen', defaults={'name': 'Abdeen WooCommerce catalogue'})
        product = self.m['Product'].objects.create(
            upc=f'wc-abdeen-{source_id}', title=f'Watch {source_id}', description=DESCRIPTION,
            product_class=product_class)
        stock = self.m['StockRecord'].objects.create(
            product=product, partner=partner, partner_sku=f'ABC/{source_id}',
            price='12.50', price_currency='JOD', num_in_stock=7)
        for code, value in zip(LEGACY_ATTRIBUTES, (str(source_id), '15.00', '12.50', 'instock')):
            attribute, _ = self.m['ProductAttribute'].objects.get_or_create(
                product_class=product_class, code=code, defaults={'name': code, 'type': 'text'})
            self.m['ProductAttributeValue'].objects.create(product=product, attribute=attribute, value_text=value)
        return product, stock

    def test_cleanup_preview_is_read_only_and_legacy_import_requires_cleanup(self):
        product, stock = self.make_legacy()
        with CaptureQueriesContext(connection) as queries:
            output = StringIO()
            call_command('normalize_imported_catalogue', product_ids=[product.pk], stdout=output)
        self.assertIn('WOULD NORMALIZE', output.getvalue())
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertFalse(CatalogueSource.objects.exists())
        product.refresh_from_db()
        self.assertEqual(product.upc, 'wc-abdeen-1')
        with self.assertRaisesMessage(CommandError, 'normalize_imported_catalogue'):
            self.run_import(skip_images=True, limit=1)

    def test_cleanup_preserves_ids_prices_stock_categories_images_and_unrelated_data(self):
        product, stock = self.make_legacy()
        other = self.m['Product'].objects.create(title='Unrelated', upc='REAL-BARCODE', product_class=self.watch)
        category = self.m['Category'].add_root(name='Manual')
        product.categories.add(category)
        image = self.m['ProductImage'].objects.create(
            product=product, code='wc-abdeen-1-thumbnail', original='products/existing.png')
        with patch('catalogue_import.catalogue.download_image') as download:
            report = cleanup_legacy_products([product.pk], apply=True)
            download.assert_not_called()
        product.refresh_from_db()
        stock.refresh_from_db()
        image.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(report['products'], [product.pk])
        self.assertEqual(self.m['Product'].objects.count(), 2)
        self.assertEqual(self.m['StockRecord'].objects.count(), 1)
        self.assertEqual(stock.num_in_stock, 7)
        self.assertEqual(str(stock.price), '12.50')
        self.assertEqual(stock.partner.name, 'Abdeen Watches')
        self.assertEqual(product.product_class_id, self.watch.pk)
        self.assertFalse(product.upc)
        self.assertEqual(product.description, DESCRIPTION)
        self.assertEqual(product.attr.movement, 'Analog Quartz (Battery)')
        self.assertEqual(product.attr.case_size, '32.5 mm')
        self.assertEqual(list(product.categories.all()), [category])
        self.assertEqual(image.original.name, 'products/existing.png')
        self.assertEqual(image.code, f'catalogue-image-{product.pk}')
        self.assertEqual(other.upc, 'REAL-BARCODE')
        self.assertEqual(CatalogueSource.objects.get(product=product).stockrecord_id, stock.pk)
        self.assertEqual(CatalogueSource.objects.get(product=product).metadata['regular_price'], '15.00')
        self.assertFalse(self.m['ProductClass'].objects.filter(slug='woocommerce-catalogue').exists())
        self.assertFalse(self.m['Partner'].objects.filter(code='woocommerce-abdeen').exists())
        self.assertFalse(self.m['ProductAttribute'].objects.filter(code__startswith='wc_').exists())
        self.assertEqual(cleanup_legacy_products([product.pk], apply=True)['skipped'], [product.pk])

    def test_partial_cleanup_retains_containers_and_other_products(self):
        first, _ = self.make_legacy(1)
        second, stock = self.make_legacy(2)
        report = cleanup_legacy_products([first.pk], apply=True)
        second.refresh_from_db()
        stock.refresh_from_db()
        self.assertEqual(second.product_class.slug, 'woocommerce-catalogue')
        self.assertEqual(stock.partner.code, 'woocommerce-abdeen')
        self.assertEqual(second.attribute_values.count(), 4)
        self.assertTrue(report['retained'])

    def test_unrelated_records_sku_conflicts_and_allocations_abort_cleanup(self):
        product, stock = self.make_legacy()
        other = self.m['Product'].objects.create(title='Unrelated', product_class=self.watch)
        with self.assertRaisesMessage(ImportDataError, 'not a verified legacy import'):
            cleanup_legacy_products([product.pk, other.pk], apply=True)
        partner = self.m['Partner'].objects.create(name='Abdeen Watches', code='abdeen-watches')
        collision = self.m['StockRecord'].objects.create(product=other, partner=partner, partner_sku=stock.partner_sku)
        with self.assertRaisesMessage(ImportDataError, 'SKU collision'):
            cleanup_legacy_products([product.pk], apply=True)
        collision.delete()
        stock.num_allocated = 1
        stock.save()
        with self.assertRaisesMessage(ImportDataError, 'active stock allocations'):
            cleanup_legacy_products([product.pk], apply=True)
        self.assertFalse(CatalogueSource.objects.exists())

    def test_cleanup_rolls_back_entire_batch_on_failure(self):
        product, stock = self.make_legacy()
        with patch.object(self.m['StockRecord'], 'save', side_effect=RuntimeError('simulated')):
            with self.assertRaises(RuntimeError):
                cleanup_legacy_products([product.pk], apply=True)
        product.refresh_from_db()
        self.assertEqual(product.upc, 'wc-abdeen-1')
        self.assertEqual(product.attribute_values.count(), 4)
        self.assertFalse(CatalogueSource.objects.exists())
        self.assertFalse(self.watch.attributes.exists())

    def test_unrelated_partner_reference_prevents_deleting_old_partner(self):
        product, stock = self.make_legacy()
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='Existing supplier user')
        stock.partner.users.add(user)
        old_partner_id = stock.partner_id
        report = cleanup_legacy_products([product.pk], apply=True)
        self.assertTrue(self.m['Partner'].objects.get(pk=old_partner_id).users.filter(pk=user.pk).exists())
        self.assertIn('Legacy partner has other references; retained.', report['retained'])

    def test_import_after_cleanup_reuses_product_stock_and_saved_image(self):
        product, stock = self.make_legacy()
        plan = build_plans(load_catalogue(self.sql), limit=1)[0]
        digest = sha256(plan.image_url.encode()).hexdigest()[:16]
        image = self.m['ProductImage'](product=product, code='wc-abdeen-1-thumbnail')
        image.original.save(f'wc-abdeen-1-{digest}.png', ContentFile(b'existing'))
        cleanup_legacy_products([product.pk], apply=True)
        with patch('catalogue_import.catalogue.download_image') as download:
            output, _ = self.run_import(limit=1)
            download.assert_not_called()
        self.assertIn('created=0 updated=1', output)
        self.assertEqual(CatalogueSource.objects.get(source=SOURCE, source_id=1).product_id, product.pk)
        self.assertEqual(CatalogueSource.objects.get(source=SOURCE, source_id=1).stockrecord_id, stock.pk)
        self.assertEqual(self.m['ProductImage'].objects.count(), 1)
