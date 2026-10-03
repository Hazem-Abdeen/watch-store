import copy
import json
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from oscar.core.loading import get_model

from catalogue_import.catalogue import OscarImporter, ProductPlan, SOURCE
from catalogue_import.models import CatalogueSource
from catalogue_import.sql_dump import ImportDataError
from catalogue_import.variant_conversion import (
    MARKER, apply_plan, approved_groups, select_groups,
)


def report_fixture():
    groups = approved_groups()
    for group in groups:
        group.update(status='candidate', confidence='high', basis='model_family',
                     review_flags=[], conflicting_specifications={},
                     shared_specifications=group['children'][0]['specifications'],
                     option_axes=['dial_color'])
        for child in group['children']:
            child['identifier_evidence'] = [{'source': 'sku_pattern', 'value': child['sku'],
                                             'family': group['family'], 'rank': 2}]
    return {'rule_version': 1, 'candidates': groups, 'ambiguous': []}


class VariantConversionTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.media = Path(self.temp.name) / 'media'
        settings = override_settings(MEDIA_ROOT=self.media)
        settings.enable()
        self.addCleanup(settings.disable)
        self.report = report_fixture()
        self.path = Path(self.temp.name) / 'analysis.json'
        self.write_report()
        self.importer = OscarImporter()
        self.m = self.importer.models
        self.watch = self.m['ProductClass'].objects.create(name='Watch', slug='watch', track_stock=True)
        self.group = select_groups(self.path, ['18886'])[0]
        self.children = self.import_group(self.group)
        self.unrelated = self.m['Product'].objects.create(title='Unrelated', product_class=self.watch)

    def write_report(self):
        self.path.write_text(json.dumps(self.report), encoding='utf-8')

    def import_group(self, group):
        products = []
        for index, child in enumerate(group['children']):
            plan = ProductPlan(child['source_id'], child['title'], 'Original child description',
                               child['sku'], Decimal('100') + index, Decimal('120'), None,
                               'instock', (('Women',), ('Brands', group['brand'])), None, (),
                               child['specifications'])
            product, _ = self.importer.import_product(plan)
            stock = product.stockrecords.get()
            stock.num_in_stock = 7 + index
            stock.num_allocated = 2
            stock.save()
            image = self.m['ProductImage'](product=product)
            image.original.save(f'{product.pk}.jpg', ContentFile(b'preserve image bytes'), save=False)
            image.save()
            mapping = CatalogueSource.objects.get(product=product)
            mapping.image = image
            mapping.save(update_fields=['image'])
            products.append(product)
        return products

    def run_command(self, *families, **kwargs):
        stdout = StringIO()
        call_command('convert_imported_variants', groups=list(families or ['18886']),
                     analysis_file=self.path, stdout=stdout, **kwargs)
        return stdout.getvalue()

    def assert_no_writes(self, queries):
        for query in queries:
            self.assertFalse(query['sql'].lstrip().upper().startswith(
                ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP')), query['sql'])

    def test_manifest_is_exactly_the_twelve_reviewed_sku_families(self):
        self.assertEqual({g['family'] for g in approved_groups()}, {
            'GBD-200', 'LA670WGA', 'LTP-1302DS', 'LTP-1308D', 'MDV-107D',
            'MTP-1375D', 'MTP-V002G', 'FL.1.10410', 'J1024', 'J893', 'J895', '18886'})
        self.assertEqual(sum(len(g['children']) for g in approved_groups()), 25)
        self.assertEqual(len(select_groups(self.path, [g['family'] for g in approved_groups()])), 12)

    def test_default_and_explicit_dry_run_are_read_only(self):
        for kwargs in ({}, {'dry_run': True}):
            with CaptureQueriesContext(connection) as queries:
                output = self.run_command(**kwargs)
            self.assert_no_writes(queries)
            self.assertIn('QUALIFIES:', output)
            self.assertIn('18886/3', output)
            self.assertIn('ready=1', output)
            self.assertIn('no database or media changes', output)
        self.assertFalse(self.m['Product'].objects.filter(structure='parent').exists())

    def test_conversion_preserves_ids_stocks_images_attributes_and_inherited_categories(self):
        ids = [p.pk for p in self.children]
        stocks = list(self.m['StockRecord'].objects.order_by('pk').values())
        images = list(self.m['ProductImage'].objects.order_by('pk').values())
        attrs = list(self.m['ProductAttributeValue'].objects.order_by('pk').values())
        cats = set(self.children[0].categories.values_list('pk', flat=True))
        descriptions = [p.description for p in self.children]
        self.run_command(apply=True)
        parent = self.m['Product'].objects.get(structure='parent')
        self.assertEqual(parent.product_class, self.watch)
        self.assertFalse(parent.stockrecords.exists())
        self.assertFalse(parent.images.exists())
        self.assertEqual(parent.description, '')
        self.assertEqual(set(parent.categories.values_list('pk', flat=True)), cats)
        self.assertFalse(parent.attribute_values.filter(attribute__code__in=[
            'dial_color', 'band_color', 'case_color']).exists())
        self.assertEqual(set(parent.children.values_list('pk', flat=True)), set(ids))
        for i, product in enumerate(self.children):
            product.refresh_from_db()
            self.assertEqual(product.structure, product.CHILD)
            self.assertEqual(product.parent_id, parent.pk)
            self.assertIsNone(product.product_class_id)
            self.assertEqual(product.get_product_class(), self.watch)
            self.assertFalse(product.categories.exists())
            self.assertEqual(set(product.get_categories().values_list('pk', flat=True)), cats)
            self.assertEqual(product.description, descriptions[i])
            product.full_clean(exclude=['upc'])
            mapping = CatalogueSource.objects.get(product=product)
            self.assertEqual(set(mapping.metadata[MARKER]['category_ids']), cats)
            self.assertEqual(mapping.metadata['regular_price'], '120')
        self.assertEqual(list(self.m['StockRecord'].objects.order_by('pk').values()), stocks)
        self.assertEqual(list(self.m['ProductImage'].objects.order_by('pk').values()), images)
        self.assertEqual(list(self.m['ProductAttributeValue'].objects.filter(
            product_id__in=ids).order_by('pk').values()), attrs)
        for image in self.m['ProductImage'].objects.all():
            self.assertEqual(Path(image.original.path).read_bytes(), b'preserve image bytes')
        self.unrelated.refresh_from_db()
        self.assertEqual(self.unrelated.structure, 'standalone')

    def test_rerun_is_a_true_noop_and_does_not_duplicate_parent(self):
        self.run_command(apply=True)
        with CaptureQueriesContext(connection) as queries:
            output = self.run_command(apply=True)
        self.assert_no_writes(queries)
        self.assertIn('already_converted=1', output)
        self.assertEqual(self.m['Product'].objects.filter(structure='parent').count(), 1)

    def test_unapproved_title_only_ambiguous_and_empty_selections_fail(self):
        for families in (['DK.1.13938'], ['J1025'], ['unknown'], [], ['18886', '18886']):
            with self.subTest(families=families), self.assertRaises(ImportDataError):
                select_groups(self.path, families)

    def test_changed_source_membership_specs_identity_and_status_fail_closed(self):
        original = copy.deepcopy(self.report)
        mutations = [lambda g: g.update(status='ambiguous'),
                     lambda g: g['children'][0].update(sku='18886/99'),
                     lambda g: g['children'][0]['specifications'].update(case_size='50 mm'),
                     lambda g: g['children'][0].update(identifier_evidence=[]),
                     lambda g: g['children'].pop(),
                     lambda g: g.update(review_flags=['Unresolved issue'])]
        for mutation in mutations:
            self.report = copy.deepcopy(original)
            mutation(next(g for g in self.report['candidates'] if g['family'] == '18886'))
            self.write_report()
            with self.assertRaises(ImportDataError):
                select_groups(self.path, ['18886'])

    def test_ambiguous_overlap_rejects_even_an_approved_candidate(self):
        self.report['ambiguous'] = [copy.deepcopy(self.group)]
        self.write_report()
        with self.assertRaisesMessage(ImportDataError, 'overlapping'):
            select_groups(self.path, ['18886'])

    def test_missing_group_prevents_any_selected_apply_but_preview_reports_every_group(self):
        output = self.run_command('18886', 'J1024', dry_run=True)
        self.assertIn('ready=1', output)
        self.assertIn('blocked=1', output)
        self.assertIn('J1024/3', output)
        with self.assertRaises(CommandError):
            self.run_command('18886', 'J1024', apply=True)
        self.assertFalse(self.m['Product'].objects.filter(structure='parent').exists())

    def test_live_core_conflict_prevents_conversion(self):
        for code in ('movement', 'case_size', 'case_material', 'water_resistance'):
            value = self.children[0].attribute_values.get(attribute__code=code)
            original = value.value_text
            value.value_text = 'Conflicting specification'
            value.save()
            with self.subTest(code=code), self.assertRaises(CommandError):
                self.run_command(apply=True)
            value.value_text = original
            value.save()

    def test_distinct_categories_are_not_discarded_or_union_shared(self):
        extra = self.m['Category'].add_root(name='Manual category', slug='manual')
        self.children[0].categories.add(extra)
        with self.assertRaises(CommandError):
            self.run_command(apply=True)
        self.assertTrue(self.children[0].categories.filter(pk=extra.pk).exists())

    def test_sku_collision_and_existing_untracked_parent_are_rejected(self):
        stock = self.children[0].stockrecords.get()
        original = stock.partner_sku
        stock.partner_sku = 'OTHER'
        stock.save()
        with self.assertRaises(CommandError):
            self.run_command(apply=True)
        stock.partner_sku = original
        stock.save()
        self.unrelated.slug = 'imported-variants-lotus-18886'
        self.unrelated.save()
        with self.assertRaises(CommandError):
            self.run_command(apply=True)

    def test_only_explicitly_selected_group_changes(self):
        group = select_groups(self.path, ['J1024'])[0]
        other_children = self.import_group(group)
        self.run_command(apply=True)
        self.assertEqual(self.m['Product'].objects.filter(
            pk__in=[p.pk for p in other_children], structure='standalone').count(), 3)

    def test_failure_in_later_group_rolls_back_all_selected_groups(self):
        group = select_groups(self.path, ['J1024'])[0]
        self.import_group(group)
        original_categories = list(self.m['Product'].categories.through.objects.order_by('pk').values())

        def fail_second(plan, importer):
            if plan['group']['family'] == 'J1024':
                raise RuntimeError('Injected failure after first group conversion')
            return apply_plan(plan, importer)

        with patch('catalogue_import.variant_conversion.apply_plan', side_effect=fail_second):
            with self.assertRaises(CommandError):
                self.run_command('18886', 'J1024', apply=True)
        self.assertFalse(self.m['Product'].objects.exclude(structure='standalone').exists())
        self.assertEqual(list(self.m['Product'].categories.through.objects.order_by('pk').values()),
                         original_categories)
        self.assertTrue(all(MARKER not in m.metadata for m in CatalogueSource.objects.all()))

    def test_partial_mapping_blocks_rerun(self):
        self.run_command(apply=True)
        mapping = CatalogueSource.objects.get(source=SOURCE, source_id=self.group['children'][0]['source_id'])
        mapping.metadata.pop(MARKER)
        mapping.save()
        with self.assertRaises(CommandError):
            self.run_command(apply=True)

    def test_parent_stock_and_unexpected_children_block_rerun(self):
        self.run_command(apply=True)
        parent = self.m['Product'].objects.get(structure='parent')
        stock = self.m['StockRecord'].objects.create(
            product=parent, partner=self.importer.partner(), partner_sku='invalid-parent-stock')
        with self.assertRaises(CommandError):
            self.run_command(apply=True)
        stock.delete()
        self.m['Product'].objects.create(title='Unexpected child', structure='child', parent=parent)
        with self.assertRaises(CommandError):
            self.run_command(apply=True)

    def test_product_options_ranges_and_recommendations_require_review(self):
        product = self.children[0]
        option = get_model('catalogue', 'Option').objects.create(name='Engraving', code='engraving')
        product.product_options.add(option)
        with self.assertRaises(CommandError):
            self.run_command(apply=True)
        product.product_options.clear()
        product_range = get_model('offer', 'Range').objects.create(name='Best Sellers', slug='best-sellers')
        product_range.add_product(product)
        with self.assertRaises(CommandError):
            self.run_command(apply=True)
        self.assertIn('Best Sellers', self.run_command(dry_run=True))
        product_range.included_products.clear()
        get_model('catalogue', 'ProductRecommendation').objects.create(
            primary=self.unrelated, recommendation=product)
        with self.assertRaises(CommandError):
            self.run_command(apply=True)

    def test_conflicting_apply_and_dry_run_cannot_write(self):
        with self.assertRaises(CommandError):
            self.run_command(apply=True, dry_run=True)
        self.assertFalse(self.m['Product'].objects.filter(structure='parent').exists())
