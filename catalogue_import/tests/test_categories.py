from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from oscar.core.loading import get_model

from catalogue_import.cleanup import remove_generic_watch_categories

from .test_import import ImportTestCase, fixture, insert


def generic_category_fixture():
    # Generic containers can be roots or sit within a useful brand hierarchy.
    return (fixture().replace("(31, 21, 'product_cat', 0)", "(31, 21, 'product_cat', 50)")
            + insert('wp_terms', ['term_id', 'name'], [
                (50, 'Watches'), (51, 'All Watches'), (52, ' Watches '),
                (53, 'Limited Editions'), (54, 'G-SHOCK'), (55, 'Edifice')])
            + insert('wp_term_taxonomy', ['term_taxonomy_id', 'term_id', 'taxonomy', 'parent'], [
                (60, 50, 'product_cat', 0), (61, 51, 'product_cat', 0),
                (62, 52, 'product_cat', 21), (63, 53, 'product_cat', 52),
                (64, 54, 'product_cat', 21), (65, 55, 'product_cat', 21)])
            + insert('wp_term_relationships', ['object_id', 'term_taxonomy_id'], [
                (1, 60), (1, 61), (1, 62), (1, 63), (1, 64), (1, 65), (2, 61)]))


class CategoryNormalizationTests(ImportTestCase):
    def test_generic_categories_are_omitted_and_useful_hierarchy_reuses_existing_nodes(self):
        Category = self.m['Category']
        men = Category.add_root(name='Men')
        women = Category.add_root(name='Women')
        brands = Category.add_root(name='Brands')
        casio = brands.add_child(name='Casio')
        self.sql.write_text(generic_category_fixture(), encoding='utf-8')
        self.run_import(skip_images=True)
        self.assertEqual(set(Category.get_root_nodes().values_list('pk', flat=True)),
                         {men.pk, women.pk, brands.pk})
        self.assertEqual(set(self.imported_product(1).categories.values_list('name', flat=True)),
                         {'Men', 'Casio', 'CASIO DIGITAL', 'Limited Editions', 'G-SHOCK', 'Edifice'})
        self.assertEqual(list(self.imported_product(2).categories.values_list('pk', flat=True)), [women.pk])
        for name in ('CASIO DIGITAL', 'Limited Editions', 'G-SHOCK', 'Edifice'):
            self.assertEqual(Category.objects.get(name=name).get_parent().pk, casio.pk)
        count = Category.objects.count()
        self.run_import(skip_images=True)
        self.assertEqual(Category.objects.count(), count)

    def test_existing_generic_roots_are_not_assigned(self):
        watches = self.m['Category'].add_root(name='Watches')
        all_watches = self.m['Category'].add_root(name='All Watches')
        self.sql.write_text(generic_category_fixture(), encoding='utf-8')
        self.run_import(skip_images=True)
        self.assertFalse(self.m['Product'].categories.through.objects.filter(
            category_id__in=[watches.pk, all_watches.pk]).exists())


class CategoryCleanupTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.run_import(skip_images=True)
        self.first = self.imported_product(1)
        self.second = self.imported_product(2)
        self.watches = self.m['Category'].add_root(name='Watches')
        self.all_watches = self.m['Category'].add_root(name='All Watches')
        self.first.categories.add(self.watches, self.all_watches)
        self.other_assignments = set(self.first.categories.exclude(
            pk__in=[self.watches.pk, self.all_watches.pk]).values_list('pk', flat=True))

    def test_command_preview_makes_no_writes(self):
        output = StringIO()
        with CaptureQueriesContext(connection) as queries:
            call_command('remove_imported_watch_categories', product_ids=[self.first.pk],
                         delete_empty=True, stdout=output)
        self.assertIn('WOULD REMOVE assignments=2', output.getvalue())
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertTrue(self.first.categories.filter(pk=self.watches.pk).exists())

    def test_detach_only_selected_links_and_keep_other_assignments_and_data(self):
        self.second.categories.add(self.watches)
        snapshots = {name: list(self.m[name].objects.values()) for name in (
            'Product', 'StockRecord', 'ProductAttributeValue', 'ProductImage')}
        report = remove_generic_watch_categories([self.first.pk], apply=True)
        self.assertEqual(len(report['links']), 2)
        self.assertEqual(set(self.first.categories.values_list('pk', flat=True)), self.other_assignments)
        self.assertTrue(self.second.categories.filter(pk=self.watches.pk).exists())
        self.assertTrue(self.m['Category'].objects.filter(pk=self.all_watches.pk).exists())
        self.assertEqual(snapshots, {name: list(self.m[name].objects.values()) for name in snapshots})
        self.assertEqual(remove_generic_watch_categories([self.first.pk], apply=True)['links'], [])

    def test_delete_empty_roots_and_rerun_import_does_not_recreate_them(self):
        output = StringIO()
        call_command('remove_imported_watch_categories', product_ids=[self.first.pk],
                     apply=True, delete_empty=True, stdout=output)
        self.assertIn('deleted_categories=2', output.getvalue())
        self.assertEqual(set(self.first.categories.values_list('pk', flat=True)), self.other_assignments)
        self.sql.write_text(generic_category_fixture(), encoding='utf-8')
        self.run_import(skip_images=True)
        self.assertFalse(self.m['Category'].objects.filter(name__in=['Watches', 'All Watches']).exists())
        self.assertEqual(remove_generic_watch_categories([self.first.pk], apply=True, delete_empty=True)['links'], [])

    def test_children_other_products_and_ranges_prevent_category_deletion(self):
        child = self.watches.add_child(name='Preserve child')
        self.first.categories.add(child)
        unrelated = self.m['Product'].objects.create(title='Unrelated', product_class=self.watch)
        unrelated.categories.add(self.all_watches)
        report = remove_generic_watch_categories([self.first.pk], apply=True, delete_empty=True)
        self.assertEqual(len(report['retained']), 2)
        self.assertTrue(self.first.categories.filter(pk=child.pk).exists())
        self.assertTrue(unrelated.categories.filter(pk=self.all_watches.pk).exists())
        unrelated.categories.remove(self.all_watches)
        product_range = get_model('offer', 'Range').objects.create(name='Existing range')
        product_range.included_categories.add(self.all_watches)
        report = remove_generic_watch_categories([self.first.pk], apply=True, delete_empty=True)
        self.assertEqual(len(report['retained']), 2)
        self.assertTrue(product_range.included_categories.filter(pk=self.all_watches.pk).exists())

    def test_nested_watches_category_is_not_targeted(self):
        brand = self.m['Category'].objects.get(name='CASIO')
        nested = brand.add_child(name='Watches')
        self.first.categories.add(nested)
        remove_generic_watch_categories([self.first.pk], apply=True, delete_empty=True)
        self.assertTrue(self.first.categories.filter(pk=nested.pk).exists())

    def test_unmapped_or_invalid_ids_abort_before_deleting_any_links(self):
        unrelated = self.m['Product'].objects.create(title='Unrelated', product_class=self.watch)
        for ids in ([self.first.pk, unrelated.pk], [self.first.pk, 999999], [0]):
            with self.subTest(ids=ids), self.assertRaisesMessage(CommandError, 'no changes committed'):
                call_command('remove_imported_watch_categories', product_ids=ids, apply=True, stdout=StringIO())
        self.assertTrue(self.first.categories.filter(pk=self.watches.pk).exists())

    def test_failure_rolls_back_link_removal(self):
        with patch('catalogue_import.cleanup.delete_unreferenced', side_effect=RuntimeError('failure')):
            with self.assertRaisesMessage(CommandError, 'no changes committed'):
                call_command('remove_imported_watch_categories', product_ids=[self.first.pk],
                             apply=True, delete_empty=True, stdout=StringIO())
        self.assertTrue(self.first.categories.filter(pk=self.watches.pk).exists())
        self.assertTrue(self.first.categories.filter(pk=self.all_watches.pk).exists())
