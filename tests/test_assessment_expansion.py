"""
Tests for Sprint 60 — Assessment Expansion.

Covers 5 new assessment categories:
  - Performance impact estimator (LOD, table calcs, complexity score)
  - Data volume analyzer (large tables, row counts)
  - Prep flow complexity scorer (step count, joins, branches)
  - Licensing impact analysis (Premium detection)
  - Multi-datasource worksheet detection
  - Server assessment new complexity axes
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.assessment import (
    _check_performance,
    _check_data_volume,
    _check_prep_complexity,
    _check_licensing,
    _check_multi_datasource,
    run_assessment,
    PASS, WARN, FAIL, INFO,
)
from powerbi_import.server_assessment import _compute_complexity


def _make_extracted(**kwargs):
    """Build minimal extracted dict."""
    base = {
        'worksheets': [],
        'dashboards': [],
        'datasources': [],
        'calculations': [],
        'parameters': [],
        'filters': [],
        'actions': [],
        'stories': [],
        'sets': [],
        'groups': [],
        'bins': [],
        'hierarchies': [],
        'sort_orders': [],
        'aliases': [],
        'custom_sql': [],
        'user_filters': [],
    }
    base.update(kwargs)
    return base


class TestPerformance(unittest.TestCase):
    def test_low_complexity(self):
        ext = _make_extracted(calculations=[], filters=[])
        cat = _check_performance(ext)
        self.assertEqual(cat.checks[0].severity, PASS)

    def test_moderate_complexity(self):
        calcs = [{'formula': '{FIXED [Dim] : SUM([Val])}'} for _ in range(12)]
        ext = _make_extracted(calculations=calcs, filters=[{'field': 'x'}] * 5)
        cat = _check_performance(ext)
        # 12 LODs * 3 = 36 + 5 filters = 41 > 30 → WARN
        self.assertEqual(cat.checks[0].severity, WARN)

    def test_high_complexity(self):
        calcs = [{'formula': '{FIXED [D] : SUM([V])}'} for _ in range(40)]
        ext = _make_extracted(calculations=calcs, filters=[{'f': 'x'}] * 10)
        cat = _check_performance(ext)
        # 40*3 + 10 = 130 > 100 → FAIL
        self.assertEqual(cat.checks[0].severity, FAIL)

    def test_dax_expression_count_warn(self):
        calcs = [{'formula': 'x'} for _ in range(55)]
        ext = _make_extracted(calculations=calcs)
        cat = _check_performance(ext)
        dax_check = [c for c in cat.checks if 'expression count' in c.name]
        self.assertEqual(dax_check[0].severity, WARN)

    def test_dax_expression_count_pass(self):
        calcs = [{'formula': 'x'} for _ in range(10)]
        ext = _make_extracted(calculations=calcs)
        cat = _check_performance(ext)
        dax_check = [c for c in cat.checks if 'expression count' in c.name]
        self.assertEqual(dax_check[0].severity, PASS)


class TestDataVolume(unittest.TestCase):
    def test_small_tables(self):
        ds = [{'tables': [{'name': 'T1', 'columns': [], 'row_count': 1000}]}]
        ext = _make_extracted(datasources=ds)
        cat = _check_data_volume(ext)
        self.assertEqual(cat.checks[0].severity, PASS)

    def test_large_table(self):
        ds = [{'tables': [{'name': 'BigTable', 'columns': [], 'row_count': 15_000_000}]}]
        ext = _make_extracted(datasources=ds)
        cat = _check_data_volume(ext)
        self.assertEqual(cat.checks[0].severity, WARN)
        self.assertIn('DirectQuery', cat.checks[0].detail)

    def test_medium_table(self):
        ds = [{'tables': [{'name': 'MedTable', 'columns': [], 'row_count': 2_000_000}]}]
        ext = _make_extracted(datasources=ds)
        cat = _check_data_volume(ext)
        self.assertEqual(cat.checks[0].severity, INFO)

    def test_no_tables(self):
        ext = _make_extracted(datasources=[])
        cat = _check_data_volume(ext)
        self.assertEqual(cat.checks[0].severity, PASS)


class TestPrepComplexity(unittest.TestCase):
    def test_no_prep(self):
        ext = _make_extracted()
        cat = _check_prep_complexity(ext)
        self.assertEqual(cat.checks[0].severity, PASS)

    def test_simple_prep(self):
        ext = _make_extracted(prep_steps=[{'type': 'filter'}] * 5)
        cat = _check_prep_complexity(ext)
        self.assertEqual(cat.checks[0].severity, PASS)

    def test_moderate_prep(self):
        ext = _make_extracted(prep_steps=[{'type': 'filter'}] * 20)
        cat = _check_prep_complexity(ext)
        self.assertEqual(cat.checks[0].severity, INFO)

    def test_complex_prep(self):
        steps = [{'type': 'filter'}] * 30 + [{'type': 'join'}] * 15 + [{'type': 'union'}] * 10
        ext = _make_extracted(prep_steps=steps)
        cat = _check_prep_complexity(ext)
        self.assertEqual(cat.checks[0].severity, WARN)


class TestLicensing(unittest.TestCase):
    def test_pro_sufficient(self):
        ds = [{'tables': [{'columns': [{'name': f'c{i}'} for i in range(10)]}]}]
        ext = _make_extracted(datasources=ds, worksheets=[{'name': 'ws1'}])
        cat = _check_licensing(ext)
        self.assertEqual(cat.checks[0].severity, PASS)

    def test_premium_needed(self):
        # 600 columns → >500 threshold
        ds = [{'tables': [{'columns': [{'name': f'c{i}'} for i in range(600)]}]}]
        ext = _make_extracted(datasources=ds, worksheets=[{'name': f'ws{i}'} for i in range(35)])
        cat = _check_licensing(ext)
        self.assertEqual(cat.checks[0].severity, WARN)
        self.assertIn('Premium', cat.checks[0].detail)

    def test_rls_heavy(self):
        ext = _make_extracted(
            user_filters=[{'field': f'f{i}'} for i in range(15)],
            datasources=[{'tables': [{'columns': []}]}],
        )
        cat = _check_licensing(ext)
        self.assertEqual(cat.checks[0].severity, WARN)


class TestMultiDatasource(unittest.TestCase):
    def test_single_datasource(self):
        ext = _make_extracted(
            worksheets=[{'name': 'ws1', 'fields': ['A', 'B']}],
            datasources=[{
                'name': 'DS1',
                'tables': [{'columns': [{'name': 'A'}, {'name': 'B'}]}],
            }],
        )
        cat = _check_multi_datasource(ext)
        self.assertEqual(cat.checks[0].severity, PASS)

    def test_multi_datasource(self):
        ext = _make_extracted(
            worksheets=[{'name': 'ws1', 'fields': ['ColA', 'ColB']}],
            datasources=[
                {'name': 'DS1', 'tables': [{'columns': [{'name': 'ColA'}]}]},
                {'name': 'DS2', 'tables': [{'columns': [{'name': 'ColB'}]}]},
            ],
        )
        cat = _check_multi_datasource(ext)
        has_warn = any(c.severity == WARN for c in cat.checks)
        self.assertTrue(has_warn)

    def test_no_worksheets(self):
        ext = _make_extracted(worksheets=[])
        cat = _check_multi_datasource(ext)
        self.assertEqual(cat.checks[0].severity, PASS)


class TestRunAssessmentExpanded(unittest.TestCase):
    def test_14_categories(self):
        ext = _make_extracted(
            datasources=[{
                'name': 'DS1',
                'connection': {'class': 'sqlserver', 'server': 'srv', 'dbname': 'db'},
                'tables': [{'name': 'T1', 'type': 'table', 'columns': [{'name': 'A'}]}],
            }],
        )
        report = run_assessment(ext)
        self.assertEqual(len(report.categories), 14)

    def test_score_consistency(self):
        """Same input → same output."""
        ext = _make_extracted()
        r1 = run_assessment(ext, workbook_name='Test')
        r2 = run_assessment(ext, workbook_name='Test')
        self.assertEqual(r1.total_checks, r2.total_checks)


class TestServerComplexityAxes(unittest.TestCase):
    def test_new_axes_present(self):
        ext = _make_extracted(
            parameters=[{'name': 'P1'}, {'name': 'P2'}],
            user_filters=[{'field': 'UF1'}],
            custom_sql=[{'query': 'SELECT 1'}],
        )
        c = _compute_complexity(ext)
        self.assertEqual(c['parameters'], 2)
        self.assertEqual(c['rls_rules'], 1)
        self.assertEqual(c['custom_sql'], 1)

    def test_axes_zero_when_empty(self):
        ext = _make_extracted()
        c = _compute_complexity(ext)
        self.assertEqual(c['parameters'], 0)
        self.assertEqual(c['rls_rules'], 0)
        self.assertEqual(c['custom_sql'], 0)

    def test_legacy_axes_preserved(self):
        ext = _make_extracted(
            worksheets=[{'name': 'W'}],
            dashboards=[{'name': 'D'}],
        )
        c = _compute_complexity(ext)
        self.assertEqual(c['visuals'], 1)
        self.assertEqual(c['dashboards'], 1)


if __name__ == '__main__':
    unittest.main()
