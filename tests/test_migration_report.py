"""Tests for powerbi_import.migration_report module."""

import json
import os
import sys
import tempfile
import unittest

# Ensure powerbi_import is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from migration_report import MigrationReport


class TestMigrationReportBasic(unittest.TestCase):
    """Test basic MigrationReport functionality."""

    def test_create_empty_report(self):
        r = MigrationReport("Test")
        self.assertEqual(r.report_name, "Test")
        self.assertEqual(len(r.items), 0)

    def test_add_item(self):
        r = MigrationReport("T")
        r.add_item('calculation', 'Profit', 'exact', dax='DIVIDE([P],[S])')
        self.assertEqual(len(r.items), 1)
        self.assertEqual(r.items[0]['name'], 'Profit')
        self.assertEqual(r.items[0]['status'], 'exact')
        self.assertEqual(r.items[0]['dax'], 'DIVIDE([P],[S])')

    def test_add_item_invalid_status(self):
        r = MigrationReport("T")
        with self.assertRaises(ValueError):
            r.add_item('calculation', 'X', 'invalid_status')

    def test_add_item_with_note(self):
        r = MigrationReport("T")
        r.add_item('visual', 'Sales Chart', 'approximate', note='Fallback to tableEx')
        self.assertEqual(r.items[0]['note'], 'Fallback to tableEx')

    def test_add_item_with_source(self):
        r = MigrationReport("T")
        r.add_item('calculation', 'X', 'exact',
                    source_formula='SUM([Sales])', dax='SUM([Sales])')
        self.assertEqual(r.items[0]['source_formula'], 'SUM([Sales])')


class TestClassifyDax(unittest.TestCase):
    """Test DAX formula classification."""

    def test_exact(self):
        self.assertEqual(MigrationReport._classify_dax('SUM([Sales])'), 'exact')

    def test_exact_complex(self):
        self.assertEqual(MigrationReport._classify_dax(
            "CALCULATE(SUM('Orders'[Amount]), ALLEXCEPT('Orders', 'Orders'[Region]))"
        ), 'exact')

    def test_unsupported_makepoint(self):
        dax = '/* MAKEPOINT: no DAX spatial equivalent */ BLANK( /*'
        self.assertEqual(MigrationReport._classify_dax(dax), 'unsupported')

    def test_unsupported_script(self):
        dax = '/* SCRIPT_REAL: analytics extension — manual conversion needed */ 0 + ( /*'
        self.assertEqual(MigrationReport._classify_dax(dax), 'unsupported')

    def test_approximate_comment(self):
        dax = 'DIVIDE(RANKX(ALL(T), X) - 1, COUNTROWS(ALL(T)) - 1) /* RANK_PERCENTILE: approximate */'
        self.assertEqual(MigrationReport._classify_dax(dax), 'approximate')

    def test_approximate_manual(self):
        dax = '/* manual conversion needed */ BLANK()'
        self.assertEqual(MigrationReport._classify_dax(dax), 'approximate')

    def test_approximate_tableau_leak_countd(self):
        dax = 'COUNTD([Column])'
        self.assertEqual(MigrationReport._classify_dax(dax), 'approximate')

    def test_approximate_tableau_leak_zn(self):
        dax = 'ZN([Sales])'
        self.assertEqual(MigrationReport._classify_dax(dax), 'approximate')

    def test_skipped_empty(self):
        self.assertEqual(MigrationReport._classify_dax(''), 'skipped')
        self.assertEqual(MigrationReport._classify_dax(None), 'skipped')


class TestSummary(unittest.TestCase):
    """Test summary computation."""

    def test_empty_summary(self):
        r = MigrationReport("T")
        s = r.get_summary()
        self.assertEqual(s['total_items'], 0)
        self.assertEqual(s['fidelity_score'], 100.0)

    def test_all_exact(self):
        r = MigrationReport("T")
        for i in range(5):
            r.add_item('calculation', f'c{i}', 'exact')
        s = r.get_summary()
        self.assertEqual(s['exact'], 5)
        self.assertEqual(s['fidelity_score'], 100.0)

    def test_mixed(self):
        r = MigrationReport("T")
        r.add_item('calculation', 'a', 'exact')
        r.add_item('calculation', 'b', 'approximate')
        r.add_item('calculation', 'c', 'unsupported')
        r.add_item('calculation', 'd', 'exact')
        s = r.get_summary()
        self.assertEqual(s['total_items'], 4)
        self.assertEqual(s['exact'], 2)
        self.assertEqual(s['approximate'], 1)
        self.assertEqual(s['unsupported'], 1)
        # fidelity = (2*100 + 1*50 + 0 + 0) / 4 = 62.5
        self.assertEqual(s['fidelity_score'], 62.5)

    def test_by_category(self):
        r = MigrationReport("T")
        r.add_item('calculation', 'a', 'exact')
        r.add_item('visual', 'v1', 'exact')
        r.add_item('visual', 'v2', 'approximate')
        s = r.get_summary()
        self.assertIn('calculation', s['by_category'])
        self.assertIn('visual', s['by_category'])
        self.assertEqual(s['by_category']['visual']['total'], 2)

    def test_summary_cached(self):
        r = MigrationReport("T")
        r.add_item('calculation', 'a', 'exact')
        s1 = r.get_summary()
        s2 = r.get_summary()
        self.assertIs(s1, s2)

    def test_summary_invalidated_on_add(self):
        r = MigrationReport("T")
        r.add_item('calculation', 'a', 'exact')
        s1 = r.get_summary()
        r.add_item('calculation', 'b', 'approximate')
        s2 = r.get_summary()
        self.assertIsNot(s1, s2)


class TestBulkMethods(unittest.TestCase):
    """Test bulk add methods for various object types."""

    def test_add_datasources(self):
        r = MigrationReport("T")
        r.add_datasources([
            {'name': 'DS1', 'connection': {'class': 'sqlserver'}, 'tables': [1, 2]},
            {'caption': 'DS2', 'connection': {'type': 'bigquery'}, 'tables': [1]},
        ])
        self.assertEqual(len(r.items), 2)
        self.assertEqual(r.items[0]['category'], 'datasource')
        self.assertIn('sqlserver', r.items[0]['note'])
        self.assertEqual(r.items[1]['name'], 'DS2')

    def test_add_visuals(self):
        r = MigrationReport("T")
        r.add_visuals([
            {'name': 'ProfitChart', 'mark_type': 'Bar'},
            {'name': 'Table1', 'mark_type': 'Text'},
        ])
        self.assertEqual(len(r.items), 2)
        self.assertTrue(all(i['category'] == 'visual' for i in r.items))

    def test_add_parameters(self):
        r = MigrationReport("T")
        r.add_parameters([{'name': 'TopN', 'domain_type': 'range'}])
        self.assertEqual(r.items[0]['category'], 'parameter')

    def test_add_hierarchies(self):
        r = MigrationReport("T")
        r.add_hierarchies([{'name': 'Geo', 'levels': ['Country', 'State', 'City']}])
        self.assertEqual(r.items[0]['category'], 'hierarchy')
        self.assertIn('3 levels', r.items[0]['note'])

    def test_add_sets(self):
        r = MigrationReport("T")
        r.add_sets([{'name': 'TopCustomers'}])
        self.assertEqual(r.items[0]['category'], 'set')

    def test_add_groups(self):
        r = MigrationReport("T")
        r.add_groups([{'name': 'Region Group'}])
        self.assertEqual(r.items[0]['category'], 'group')

    def test_add_bins(self):
        r = MigrationReport("T")
        r.add_bins([{'name': 'Age Bin'}])
        self.assertEqual(r.items[0]['category'], 'bin')

    def test_add_stories(self):
        r = MigrationReport("T")
        r.add_stories([{'name': 'Overview', 'story_points': [1, 2, 3]}])
        self.assertEqual(r.items[0]['category'], 'bookmark')
        self.assertIn('3 bookmark', r.items[0]['note'])

    def test_add_user_filters(self):
        r = MigrationReport("T")
        r.add_user_filters([{'name': 'Region Filter'}])
        self.assertEqual(r.items[0]['category'], 'rls_role')
        self.assertEqual(r.items[0]['status'], 'exact')

    def test_add_user_filters_ismemberof_approximate(self):
        r = MigrationReport("T")
        r.add_user_filters([{
            'name': 'Manager Access',
            'type': 'calculated_security',
            'ismemberof_groups': ['Managers'],
            'functions_used': ['ISMEMBEROF']
        }])
        self.assertEqual(r.items[0]['category'], 'rls_role')
        self.assertEqual(r.items[0]['status'], 'approximate')
        self.assertIn('Managers', r.items[0]['note'])

    def test_add_user_filters_username_exact(self):
        r = MigrationReport("T")
        r.add_user_filters([{
            'name': 'Current User',
            'type': 'calculated_security',
            'functions_used': ['USERNAME']
        }])
        self.assertEqual(r.items[0]['category'], 'rls_role')
        self.assertEqual(r.items[0]['status'], 'exact')

    def test_add_user_filters_explicit_mappings_exact(self):
        r = MigrationReport("T")
        r.add_user_filters([{
            'name': 'Region Access',
            'type': 'user_filter',
            'user_mappings': {'alice@co': ['East']}
        }])
        self.assertEqual(r.items[0]['category'], 'rls_role')
        self.assertEqual(r.items[0]['status'], 'exact')

    def test_add_calculations_exact(self):
        r = MigrationReport("T")
        calcs = [{'name': 'Profit', 'caption': 'Profit', 'formula': 'SUM([Sales])'}]
        calc_map = {'Profit': 'SUM([Sales])'}
        r.add_calculations(calcs, calc_map)
        self.assertEqual(r.items[0]['status'], 'exact')

    def test_add_calculations_no_dax(self):
        r = MigrationReport("T")
        calcs = [{'name': 'MissingCalc', 'formula': 'SUM([X])'}]
        r.add_calculations(calcs, {})
        self.assertEqual(r.items[0]['status'], 'skipped')


class TestSerialization(unittest.TestCase):
    """Test save/load functionality."""

    def test_to_dict(self):
        r = MigrationReport("Test")
        r.add_item('calculation', 'X', 'exact')
        d = r.to_dict()
        self.assertEqual(d['report_name'], 'Test')
        self.assertIn('summary', d)
        self.assertIn('items', d)
        self.assertEqual(len(d['items']), 1)

    def test_save_creates_file(self):
        r = MigrationReport("Test")
        r.add_item('calculation', 'X', 'exact')
        with tempfile.TemporaryDirectory() as tmpdir:
            path = r.save(tmpdir)
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith('.json'))

            # Validate JSON content
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data['report_name'], 'Test')
            self.assertEqual(len(data['items']), 1)

    def test_save_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, 'sub', 'dir')
            r = MigrationReport("Test")
            path = r.save(nested)
            self.assertTrue(os.path.exists(path))


class TestPrintSummary(unittest.TestCase):
    """Test that print_summary runs without errors."""

    def test_empty_print(self):
        r = MigrationReport("Test")
        r.print_summary()  # Should not raise

    def test_populated_print(self):
        r = MigrationReport("Test")
        r.add_item('calculation', 'A', 'exact')
        r.add_item('calculation', 'B', 'unsupported', note='No spatial equivalent')
        r.add_item('visual', 'Chart', 'approximate', note='Fallback')
        r.print_summary()  # Should not raise


if __name__ == '__main__':
    unittest.main()
