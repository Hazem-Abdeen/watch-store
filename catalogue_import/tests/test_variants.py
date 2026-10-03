import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from catalogue_import.sql_dump import Catalogue, load_catalogue
from catalogue_import.variants import (
    MODEL_META_KEYS, analyze_catalogue, records_from_catalogue, sku_family,
)

from .test_import import insert
from .test_refactor import serialize


SPECS = {'brand': 'Lotus', 'gender': 'Women', 'movement': 'Analog Quartz (Battery)',
         'case_size': '31.5 mm', 'case_material': 'Stainless Steel',
         'band_material': 'St.Steel', 'water_resistance': '5 Bar (Diving)',
         'band_color': 'Silver & Gold', 'case_color': 'Gold'}


def source_catalogue(*products):
    data = Catalogue()
    data.terms = {1: 'LOTUS', 2: 'simple'}
    data.taxonomies = {
        1: {'term_id': '1', 'taxonomy': 'product_cat', 'parent': '0'},
        2: {'term_id': '2', 'taxonomy': 'product_type', 'parent': '0'},
    }
    for index, product in enumerate(products, 1):
        specs = {**SPECS, 'dial_color': 'Blue' if index == 1 else 'Black', **product.get('specs', {})}
        description = '\n'.join(f'{key.replace("_", " ")}: {value}' for key, value in specs.items())
        if product.get('model'):
            description += '\nModel number: ' + product['model']
        data.products[index] = {'post_title': product.get('title', 'LOTUS WATCH FOR WOMEN'),
                                'post_content': description}
        data.meta[index] = {'_sku': product.get('sku', f'18886/{index}'), '_price': product.get('price', '102'),
                            '_stock_status': 'instock', '_thumbnail_id': str(10000 + index),
                            **product.get('meta', {})}
        data.meta[10000 + index] = {'_wp_attached_file': f'2023/05/{index}.jpg'}
        data.attachments.add(10000 + index)
        data.relationships[index] = {1, 2}
    return data


def dump_fixture(data):
    return ''.join([
        insert('wp_posts', ['ID', 'post_type', 'post_status', 'post_title', 'post_content'],
               [(key, 'product', 'publish', value['post_title'], value['post_content'])
                for key, value in data.products.items()]
               + [(key, 'attachment', 'inherit', 'Image', '') for key in sorted(data.attachments)]
               + [(9999, 'shop_order', 'publish', 'Unrelated order', 'Never analyze')]),
        insert('wp_postmeta', ['post_id', 'meta_key', 'meta_value'],
               [(key, name, value) for key, meta in data.meta.items() for name, value in meta.items()]),
        insert('wp_terms', ['term_id', 'name'], list(data.terms.items())),
        insert('wp_term_taxonomy', ['term_taxonomy_id', 'term_id', 'taxonomy', 'parent'],
               [(key, row['term_id'], row['taxonomy'], row['parent']) for key, row in data.taxonomies.items()]),
        insert('wp_term_relationships', ['object_id', 'term_taxonomy_id'],
               [(key, taxonomy) for key, taxonomies in data.relationships.items() for taxonomy in sorted(taxonomies)]),
        insert('wp_wc_product_meta_lookup', ['product_id'], [(key,) for key in data.products]),
    ])


class VariantAnalysisTests(SimpleTestCase):
    # SimpleTestCase forbids all DB access, including SELECTs.
    def test_sku_family_with_matching_specs_and_distinct_colors_is_candidate(self):
        report = analyze_catalogue(source_catalogue({'sku': '18886/3'}, {'sku': '18886/4', 'price': '110'}))
        self.assertEqual(report['summary']['candidate_groups'], 1)
        group = report['candidates'][0]
        self.assertEqual(group['family'], '18886')
        self.assertEqual(group['option_axes'], ['dial_color'])
        self.assertEqual(group['children'][0]['sku'], '18886/3')
        self.assertEqual(group['children'][1]['price'], '110')
        self.assertEqual(group['children'][0]['image_url'], 'https://abdeenwatches.com/wp-content/uploads/2023/05/1.jpg')

    def test_conflicting_physical_specs_flag_entire_family_not_a_convenient_subset(self):
        for key, value in [('case_size', '32 mm'), ('movement', 'Automatic'), ('gender', 'Men'),
                           ('water_resistance', '10 Bar'), ('band_material', 'Leather')]:
            with self.subTest(key=key):
                report = analyze_catalogue(source_catalogue({}, {}, {'specs': {key: value, 'dial_color': 'Green'}}))
                self.assertFalse(report['candidates'])
                self.assertIn(key, report['ambiguous'][0]['conflicting_specifications'])
                self.assertEqual(len(report['ambiguous'][0]['children']), 3)

    def test_same_brand_or_barcode_prefix_is_never_enough(self):
        data = source_catalogue({'sku': '8682308347005'}, {'sku': '8682308347036'})
        report = analyze_catalogue(data)
        self.assertEqual(report['summary']['ungrouped_products'], 2)
        self.assertEqual(report['candidates'] + report['ambiguous'], [])
        self.assertIsNone(sku_family('8682308347005', 'lotus'))

    def test_shared_specs_without_identity_are_not_grouped(self):
        data = source_catalogue({'sku': 'A0001', 'title': 'First unrelated watch'},
                                {'sku': 'B0002', 'title': 'Second unrelated watch'})
        self.assertEqual(analyze_catalogue(data)['summary']['ungrouped_products'], 2)

    def test_identical_options_or_missing_evidence_require_review(self):
        for changed in ({'dial_color': 'Blue'}, {'movement': ''}, {'case_size': ''}):
            with self.subTest(changed=changed):
                report = analyze_catalogue(source_catalogue({}, {'specs': changed}))
                self.assertFalse(report['candidates'])
                self.assertEqual(len(report['ambiguous']), 1)

    def test_exact_explicit_model_can_match_unrelated_skus(self):
        data = source_catalogue({'sku': 'ABC1', 'model': 'MODEL900'}, {'sku': 'XYZ2', 'model': 'MODEL900'})
        self.assertEqual(analyze_catalogue(data)['candidates'][0]['family'], 'MODEL900')

    def test_stronger_explicit_model_conflicts_are_not_overruled_by_sku(self):
        data = source_catalogue({'model': 'MODEL900'}, {'model': 'MODEL901'})
        rows, _ = records_from_catalogue(data)
        self.assertEqual(rows[0].primary['family'], 'MODEL900')
        report = analyze_catalogue(data)
        self.assertFalse(report['candidates'])
        self.assertTrue(any('stronger identifier' in flag for flag in report['ambiguous'][0]['review_flags']))

    def test_metadata_and_custom_model_attributes_are_used_before_titles(self):
        attrs = serialize({'model': {'name': 'Model Number', 'value': 'REF900', 'is_visible': 1}})
        data = source_catalogue({'sku': 'ABC1', 'meta': {'_model_number': 'REF900'}},
                                {'sku': 'XYZ2', 'meta': {'_product_attributes': attrs}})
        group = analyze_catalogue(data)['candidates'][0]
        self.assertEqual(group['family'], 'REF900')
        self.assertEqual(group['children'][1]['visible_attributes']['model_number'], 'REF900')

    def test_visible_color_attributes_can_distinguish_options(self):
        def attrs(color):
            return serialize({'color': {'name': 'Color', 'value': color, 'is_visible': 1}})
        data = source_catalogue({'meta': {'_product_attributes': attrs('Blue')}},
                                {'specs': {'dial_color': 'Blue'}, 'meta': {'_product_attributes': attrs('Black')}})
        self.assertEqual(analyze_catalogue(data)['candidates'][0]['option_axes'], ['color'])

    def test_title_model_token_needs_stronger_specification_corroboration(self):
        data = source_catalogue({'sku': '8682308347005', 'title': 'LOTUS DK.1.14005-1 WATCH'},
                                {'sku': '8682308347036', 'title': 'LOTUS DK.1.14005-2 WATCH'})
        self.assertEqual(analyze_catalogue(data)['summary']['candidate_groups'], 1)
        for row in data.products.values():
            row['post_content'] = row['post_content'].replace('water resistance: 5 Bar (Diving)', '')
            row['post_content'] = row['post_content'].replace('band material: St.Steel', '')
        self.assertFalse(analyze_catalogue(data)['candidates'])

    def test_normalized_title_alone_is_always_ambiguous(self):
        data = source_catalogue({'sku': 'ABC1', 'title': 'LOTUS EXECUTIVE BLUE DIAL WATCH'},
                                {'sku': 'XYZ2', 'title': 'LOTUS EXECUTIVE BLACK DIAL WATCH'})
        report = analyze_catalogue(data)
        self.assertFalse(report['candidates'])
        self.assertEqual(report['ambiguous'][0]['basis'], 'normalized_title')

    def test_copy_suffix_and_title_color_conflicts_are_ambiguous(self):
        data = source_catalogue({'sku': '8682308347005', 'title': 'LOTUS DK.1.14005-1 WATCH'},
                                {'sku': '8682308347005-1', 'title': 'LOTUS DK.1.14005-2 WATCH'})
        self.assertFalse(analyze_catalogue(data)['candidates'])
        data = source_catalogue({}, {'title': 'LOTUS GREEN DIAL WATCH'})
        self.assertFalse(analyze_catalogue(data)['candidates'])

    def test_families_are_scoped_to_brand(self):
        self.assertEqual(analyze_catalogue(source_catalogue({}, {'specs': {'brand': 'Jaguar'}}))['candidates'], [])

    def test_safe_material_and_color_normalization(self):
        data = source_catalogue({}, {'specs': {'band_material': 'Stainless Steel', 'band_color': 'Gold & Silver'}})
        self.assertEqual(analyze_catalogue(data)['summary']['candidate_groups'], 1)

    def test_command_json_is_read_only_and_does_not_download(self):
        data = source_catalogue({'meta': {'fb_mpn': '18886/1'}}, {'meta': {'fb_mpn': '18886/2'}})
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'catalogue.sql'
            path.write_text(dump_fixture(data), encoding='utf-8')
            self.assertNotIn('fb_mpn', load_catalogue(path).meta[1])
            self.assertIn('fb_mpn', load_catalogue(path, extra_meta_keys=MODEL_META_KEYS).meta[1])
            with patch('catalogue_import.catalogue.download_image') as download:
                output = StringIO()
                call_command('analyze_woocommerce_variants', sql_file=path, format='json', stdout=output)
                download.assert_not_called()
            report = json.loads(output.getvalue())
            self.assertEqual(report['summary']['published_products'], 2)
            self.assertEqual(report['summary']['candidate_groups'], 1)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            output = StringIO()
            call_command('analyze_woocommerce_variants', sql_file=path, stdout=output)
            self.assertIn('Parent suggestion:', output.getvalue())
            self.assertIn('Colors:', output.getvalue())
            self.assertIn('Image:', output.getvalue())
            self.assertIn('AMBIGUOUS (0)', output.getvalue())

    def test_malformed_dump_produces_no_partial_report(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'catalogue.sql'
            path.write_text(dump_fixture(source_catalogue({}, {})) + "INSERT INTO broken", encoding='utf-8')
            output = StringIO()
            with self.assertRaisesMessage(CommandError, 'without changes'):
                call_command('analyze_woocommerce_variants', sql_file=path, stdout=output)
            self.assertEqual(output.getvalue(), '')

    def test_results_are_deterministic(self):
        data = source_catalogue({}, {})
        first = analyze_catalogue(data)
        data.products = dict(reversed(list(data.products.items())))
        self.assertEqual(analyze_catalogue(data), first)
