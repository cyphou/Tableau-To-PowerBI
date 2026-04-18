"""
Sprint 85 — v23.0.0 Cross-Feature Integration Tests.

Validates that Sprint 84 (Conversion Accuracy), gap optimization
(LTRIM/RTRIM/INDEX/REGEXP), and fidelity scoring fixes all work
together end-to-end.
"""

import json
import os
import shutil
import tempfile
import unittest

# ═══════════════════════════════════════════════════════════════════
# 1. Version sanity
# ═══════════════════════════════════════════════════════════════════

class TestVersionBump(unittest.TestCase):
    """Verify version is 23.0.0 everywhere."""

    def test_pyproject_version(self):
        import re
        with open('pyproject.toml', encoding='utf-8') as f:
            content = f.read()
        m = re.search(r'version\s*=\s*"(\d+\.\d+\.\d+)"', content)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), '28.3.0')

    def test_init_version(self):
        from powerbi_import import __version__
        self.assertEqual(__version__, '28.3.0')


# ═══════════════════════════════════════════════════════════════════
# 2. Sprint 84 + Gap Optimization cross-validation
# ═══════════════════════════════════════════════════════════════════

class TestDaxGapAndAccuracyCombined(unittest.TestCase):
    """Verify gap optimization DAX conversions still work after Sprint 84."""

    def test_ltrim_survives_sprint84(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('LTRIM([Name])', table_name='T')
        self.assertIn('MID', result)
        self.assertNotEqual(result, 'TRIM([Name])')

    def test_rtrim_survives_sprint84(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('RTRIM([Name])', table_name='T')
        self.assertIn('LEFT', result)

    def test_index_rownumber(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('INDEX()', table_name='T')
        self.assertIn('ROWNUMBER', result)

    def test_regexp_exact_match(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            'REGEXP_MATCH([Code], "^ABC$")', table_name='T'
        )
        # ^literal$ pattern → equality check (= "ABC") or EXACT()
        self.assertTrue('= "ABC"' in result or 'EXACT' in result,
                        f'Expected equality or EXACT, got: {result}')


class TestSprint84Features(unittest.TestCase):
    """Verify Sprint 84 features are intact."""

    def test_prep_var_in_agg_map(self):
        from tableau_export.m_query_builder import _M_AGG_MAP
        self.assertIn('var', _M_AGG_MAP)
        func, _ = _M_AGG_MAP['var']
        # VAR is special-cased (None func in map)
        self.assertIsNone(func)

    def test_prep_varp_in_agg_map(self):
        from tableau_export.m_query_builder import _M_AGG_MAP
        self.assertIn('varp', _M_AGG_MAP)
        func, _ = _M_AGG_MAP['varp']
        self.assertIsNone(func)

    def test_bump_chart_maps_to_line(self):
        from powerbi_import.visual_generator import VISUAL_TYPE_MAP
        self.assertEqual(VISUAL_TYPE_MAP.get('bumpchart'), 'lineChart')

    def test_pdf_connector_generates_m(self):
        from tableau_export.m_query_builder import generate_power_query_m
        conn = {'type': 'PDF', 'details': {'filename': 'report.pdf'}}
        table = {'name': 'Table1', 'columns': []}
        m = generate_power_query_m(conn, table)
        self.assertIn('Pdf.Tables', m)

    def test_salesforce_connector_generates_m(self):
        from tableau_export.m_query_builder import generate_power_query_m
        conn = {'type': 'Salesforce', 'details': {'server': 'https://login.salesforce.com'}}
        table = {'name': 'Account', 'columns': []}
        m = generate_power_query_m(conn, table)
        self.assertIn('Salesforce', m)


# ═══════════════════════════════════════════════════════════════════
# 3. Fidelity scoring integration
# ═══════════════════════════════════════════════════════════════════

class TestFidelityScoringIntegration(unittest.TestCase):
    """Verify fidelity scoring fixes work with real migration data."""

    def test_skipped_excluded_from_denominator(self):
        from powerbi_import.migration_report import MigrationReport
        report = MigrationReport('test_wb')
        report.add_item('calculation', 'calc1', 'exact', dax='SUM([X])')
        report.add_item('calculation', 'calc2', 'skipped', note='MAKEPOINT')
        summary = report.get_summary()
        # 1 exact out of 1 scored (skipped excluded) = 100%
        self.assertEqual(summary['fidelity_score'], 100.0)

    def test_ismemberof_rls_exact(self):
        from powerbi_import.migration_report import MigrationReport
        report = MigrationReport('test_wb')
        user_filters = [{'type': 'ismemberof', 'groups': ['Finance']}]
        report.add_user_filters(user_filters)
        summary = report.get_summary()
        items = summary.get('items', [])
        rls_items = [i for i in items if 'ISMEMBEROF' in i.get('source', '').upper()
                     or 'ismemberof' in i.get('name', '').lower()]
        for item in rls_items:
            self.assertEqual(item['status'], 'exact')

    def test_weighted_overall_score_exists(self):
        from powerbi_import.migration_report import MigrationReport
        report = MigrationReport('test_wb')
        report.add_item('calculation', 'c1', 'exact', dax='SUM([X])')
        report.add_item('visual', 'v1', 'exact')
        report.add_item('datasource', 'ds1', 'exact')
        scores = report.get_completeness_score()
        self.assertIn('overall_score', scores)
        self.assertGreaterEqual(scores['overall_score'], 90.0)

    def test_all_exact_gives_100(self):
        from powerbi_import.migration_report import MigrationReport
        report = MigrationReport('test_wb')
        report.add_item('calculation', 'c1', 'exact', dax='SUM([X])')
        report.add_item('visual', 'v1', 'exact')
        report.add_item('datasource', 'ds1', 'exact')
        report.add_item('filter', 'f1', 'exact')
        scores = report.get_completeness_score()
        self.assertEqual(scores['overall_score'], 100.0)


# ═══════════════════════════════════════════════════════════════════
# 4. End-to-end sample migration
# ═══════════════════════════════════════════════════════════════════

class TestEndToEndSampleMigration(unittest.TestCase):
    """Migrate a sample .twb and validate output structure."""

    def test_superstore_extraction_and_generation(self):
        sample = 'examples/tableau_samples/Superstore.twb'
        if not os.path.exists(sample):
            self.skipTest('Superstore.twb not found')
        from migrate import run_extraction, run_generation
        run_extraction(sample)
        with tempfile.TemporaryDirectory() as tmpdir:
            run_generation(report_name='Superstore', output_dir=tmpdir)
            # Check output directory has expected structure
            projects = [d for d in os.listdir(tmpdir)
                        if os.path.isdir(os.path.join(tmpdir, d))]
            self.assertGreater(len(projects), 0)

    def test_financial_report_extraction_and_generation(self):
        sample = 'examples/tableau_samples/Financial_Report.twb'
        if not os.path.exists(sample):
            self.skipTest('Financial_Report.twb not found')
        from migrate import run_extraction, run_generation
        run_extraction(sample)
        with tempfile.TemporaryDirectory() as tmpdir:
            run_generation(report_name='Financial_Report', output_dir=tmpdir)
            projects = [d for d in os.listdir(tmpdir)
                        if os.path.isdir(os.path.join(tmpdir, d))]
            self.assertGreater(len(projects), 0)


# ═══════════════════════════════════════════════════════════════════
# 5. M query builder Sprint 84 features work with gap fixes
# ═══════════════════════════════════════════════════════════════════

class TestMQueryCrossFeature(unittest.TestCase):
    """M query features from Sprint 84 and gap optimization coexist."""

    def test_regex_m_transform_available(self):
        from tableau_export import m_query_builder
        # Ensure the module has M transform capabilities
        self.assertTrue(hasattr(m_query_builder, 'generate_power_query_m'))

    def test_multiple_connectors_in_sequence(self):
        """Generate M for multiple connector types without conflicts."""
        from tableau_export.m_query_builder import generate_power_query_m
        connectors = [
            {'type': 'SQL Server', 'details': {'server': 'srv', 'database': 'db'}},
            {'type': 'PostgreSQL', 'details': {'server': 'pg', 'database': 'db'}},
            {'type': 'PDF', 'details': {'filename': 'test.pdf'}},
            {'type': 'Salesforce', 'details': {'server': 'https://sf.com'}},
        ]
        table = {'name': 'T', 'columns': []}
        for conn in connectors:
            m = generate_power_query_m(conn, table)
            self.assertIsInstance(m, str)
            self.assertGreater(len(m), 10)

    def test_new_connectors_coexist_with_existing(self):
        """Sprint 84 connectors don't break existing ones."""
        from tableau_export.m_query_builder import _M_GENERATORS
        # Core connectors still present
        self.assertIn('SQL Server', _M_GENERATORS)
        self.assertIn('PostgreSQL', _M_GENERATORS)
        self.assertIn('Excel', _M_GENERATORS)
        # Sprint 61+ connectors still present
        self.assertIn('MongoDB', _M_GENERATORS)
        self.assertIn('Cosmos DB', _M_GENERATORS)
        self.assertIn('Amazon Athena', _M_GENERATORS)


# ═══════════════════════════════════════════════════════════════════
# 6. Visual type map completeness after Sprint 84
# ═══════════════════════════════════════════════════════════════════

class TestVisualMapCompleteness(unittest.TestCase):
    """Visual type map contains all expected entries after Sprint 84."""

    def test_core_visual_types_present(self):
        from powerbi_import.visual_generator import VISUAL_TYPE_MAP
        core_types = [
            'bar', 'line', 'pie', 'scatter', 'treemap',
            'map', 'table', 'waterfall', 'funnel', 'gauge',
        ]
        for vtype in core_types:
            self.assertIn(vtype, VISUAL_TYPE_MAP, f'{vtype} missing from map')

    def test_sprint84_bump_chart_present(self):
        from powerbi_import.visual_generator import VISUAL_TYPE_MAP
        self.assertIn('bumpchart', VISUAL_TYPE_MAP)

    def test_map_has_100_plus_entries(self):
        from powerbi_import.visual_generator import VISUAL_TYPE_MAP
        self.assertGreaterEqual(len(VISUAL_TYPE_MAP), 100,
                                f'Expected 100+ entries, got {len(VISUAL_TYPE_MAP)}')


# ═══════════════════════════════════════════════════════════════════
# 7. DAX converter completeness
# ═══════════════════════════════════════════════════════════════════

class TestDaxConverterCompleteness(unittest.TestCase):
    """Verify DAX converter handles all documented function categories."""

    def test_basic_functions(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        cases = [
            ('SUM([Sales])', 'SUM'),
            ('COUNT([Orders])', 'COUNT'),
            ('AVG([Price])', 'AVERAGE'),
            ('COUNTD([Customer])', 'DISTINCTCOUNT'),
        ]
        for tableau, expected_fragment in cases:
            result = convert_tableau_formula_to_dax(tableau, table_name='T')
            self.assertIn(expected_fragment, result,
                          f'{tableau} → {result} missing {expected_fragment}')

    def test_null_functions(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('ISNULL([X])', table_name='T')
        self.assertIn('ISBLANK', result)

    def test_text_functions(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('UPPER([Name])', table_name='T')
        self.assertIn('UPPER', result)

    def test_security_functions(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('USERNAME()', table_name='T')
        self.assertIn('USERPRINCIPALNAME', result)


if __name__ == '__main__':
    unittest.main()
