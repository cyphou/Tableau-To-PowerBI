"""Tests for v5.1.0 features — DAX accuracy, generation quality, assessment enhancements.

Covers:
- Sprint 9: SPLIT, INDEX, SIZE, WINDOW_CORR/COVAR/COVARP, DATEPARSE, ATAN2
- Sprint 10: create_filters_config table_name, Prep VAR/VARP, Prep notInner, M fallback
- Sprint 11: Assessment 2024.3+ detection, REGEXP_EXTRACT_NTH improvement
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from tableau_export.dax_converter import convert_tableau_formula_to_dax
from tableau_export.m_query_builder import _gen_m_fallback
from tableau_export.prep_flow_parser import _PREP_AGG_MAP, _PREP_JOIN_MAP
from powerbi_import.visual_generator import create_filters_config
from powerbi_import.assessment import run_assessment, _check_migration_scope


# ════════════════════════════════════════════════════════════════════
#  Sprint 9: DAX Conversion Accuracy
# ════════════════════════════════════════════════════════════════════

class TestSplitConversion(unittest.TestCase):
    """SPLIT() → PATHITEM(SUBSTITUTE()) conversion."""

    def test_split_three_args(self):
        result = convert_tableau_formula_to_dax('SPLIT([Name], " ", 2)')
        self.assertIn('PATHITEM', result)
        self.assertIn('SUBSTITUTE', result)
        self.assertNotIn('BLANK()', result)

    def test_split_two_args(self):
        result = convert_tableau_formula_to_dax('SPLIT([Email], "@")')
        self.assertIn('PATHITEM', result)
        self.assertIn('SUBSTITUTE', result)

    def test_split_one_arg_fallback(self):
        result = convert_tableau_formula_to_dax('SPLIT([X])')
        self.assertIn('BLANK()', result)

    def test_split_preserves_delimiter(self):
        result = convert_tableau_formula_to_dax('SPLIT([Path], "/", 3)')
        self.assertIn('"/"', result)
        self.assertIn('"', result)

    def test_split_no_placeholder_comment(self):
        """The old placeholder comment should no longer appear."""
        result = convert_tableau_formula_to_dax('SPLIT([Name], ",", 1)')
        self.assertNotIn('no direct DAX equivalent', result)


class TestIndexConversion(unittest.TestCase):
    """INDEX() → improved RANKX."""

    def test_index_basic(self):
        result = convert_tableau_formula_to_dax('INDEX()')
        self.assertIn('RANKX', result)
        self.assertIn('ALLSELECTED', result)
        self.assertIn('DENSE', result)

    def test_index_comment_preserved(self):
        result = convert_tableau_formula_to_dax('INDEX()')
        self.assertIn('INDEX', result.upper() if '/*' in result else result)


class TestSizeConversion(unittest.TestCase):
    """SIZE() → CALCULATE(COUNTROWS(), ALLSELECTED())."""

    def test_size_basic(self):
        result = convert_tableau_formula_to_dax('SIZE()')
        self.assertIn('CALCULATE', result)
        self.assertIn('COUNTROWS', result)
        self.assertIn('ALLSELECTED', result)

    def test_size_not_bare_countrows(self):
        """Old version was just COUNTROWS() — now should use CALCULATE wrapper."""
        result = convert_tableau_formula_to_dax('SIZE()')
        self.assertIn('CALCULATE(COUNTROWS()', result)


class TestWindowCorrCovar(unittest.TestCase):
    """WINDOW_CORR/COVAR/COVARP → CALCULATE(VAR/SUMX iterator pattern)."""

    def test_window_corr(self):
        result = convert_tableau_formula_to_dax('WINDOW_CORR(SUM([Sales]), SUM([Profit]))')
        self.assertIn('CALCULATE', result)
        # Now uses proper VAR/SUMX iterator pattern (not fake CORREL)
        self.assertIn('VAR _MeanX', result)
        self.assertIn('SUMX', result)
        self.assertIn('DIVIDE(', result)
        self.assertNotIn('0 +', result)

    def test_window_covar(self):
        result = convert_tableau_formula_to_dax('WINDOW_COVAR(SUM([A]), SUM([B]))')
        self.assertIn('CALCULATE', result)
        # Sample covariance: divides by N-1
        self.assertIn('VAR _MeanX', result)
        self.assertIn('_N - 1', result)

    def test_window_covarp(self):
        result = convert_tableau_formula_to_dax('WINDOW_COVARP(SUM([X]), SUM([Y]))')
        self.assertIn('CALCULATE', result)
        # Population covariance: divides by N (not N-1)
        self.assertIn('VAR _MeanX', result)
        self.assertIn('VAR _N', result)
        self.assertNotIn('_N - 1', result)

    def test_window_corr_no_placeholder(self):
        result = convert_tableau_formula_to_dax('WINDOW_CORR(SUM([A]), SUM([B]))')
        self.assertNotIn('no DAX equivalent', result)


class TestDateparseConversion(unittest.TestCase):
    """DATEPARSE(format, string) → FORMAT(DATEVALUE(string), format)."""

    def test_dateparse_with_format(self):
        result = convert_tableau_formula_to_dax('DATEPARSE("yyyy-MM-dd", [DateStr])')
        self.assertIn('FORMAT', result)
        self.assertIn('DATEVALUE', result)

    def test_dateparse_preserves_format(self):
        """Format string should appear in the output (not discarded)."""
        result = convert_tableau_formula_to_dax('DATEPARSE("dd/MM/yyyy", [Col])')
        self.assertIn('dd/MM/yyyy', result)

    def test_dateparse_no_format(self):
        result = convert_tableau_formula_to_dax('DATEPARSE([DateCol])')
        self.assertIn('DATEVALUE', result)


class TestAtan2Conversion(unittest.TestCase):
    """ATAN2(y, x) → quadrant-aware computation."""

    def test_atan2_uses_if(self):
        result = convert_tableau_formula_to_dax('ATAN2([Y], [X])')
        self.assertIn('IF', result)
        self.assertIn('ATAN', result)

    def test_atan2_has_pi(self):
        result = convert_tableau_formula_to_dax('ATAN2([Y], [X])')
        self.assertIn('PI()', result)

    def test_atan2_uses_var(self):
        """Should use VAR for clean code."""
        result = convert_tableau_formula_to_dax('ATAN2([Y], [X])')
        self.assertIn('VAR', result)
        self.assertIn('RETURN', result)

    def test_atan2_no_verify_comment(self):
        """The old 'verify quadrant handling' comment should be gone."""
        result = convert_tableau_formula_to_dax('ATAN2([Y], [X])')
        self.assertNotIn('verify quadrant', result)


class TestRegexpExtractNth(unittest.TestCase):
    """REGEXP_EXTRACT_NTH dedicated converter with smart pattern detection."""

    def test_regexp_extract_nth_complex_pattern_fallback(self):
        """Complex regex patterns (like \\d+) properly fall back to BLANK()."""
        result = convert_tableau_formula_to_dax('REGEXP_EXTRACT_NTH([Text], "\\d+", 1)')
        self.assertIn('BLANK()', result)
        self.assertIn('manual conversion needed', result)

    def test_regexp_extract_nth_delimiter_pattern(self):
        """Delimiter-based patterns use PATHITEM(SUBSTITUTE(...))."""
        result = convert_tableau_formula_to_dax('REGEXP_EXTRACT_NTH([X], "([^-]*)", 2)')
        self.assertIn('PATHITEM', result)
        self.assertIn('SUBSTITUTE', result)


# ════════════════════════════════════════════════════════════════════
#  Sprint 10: Generation Quality
# ════════════════════════════════════════════════════════════════════

class TestCreateFiltersConfig(unittest.TestCase):
    """create_filters_config() should use actual table name."""

    def test_default_table_name(self):
        filters = [{'field': 'Region', 'values': ['East', 'West']}]
        result = create_filters_config(filters)
        self.assertEqual(len(result), 1)
        entity = result[0]['expression']['Column']['Expression']['SourceRef']['Entity']
        self.assertEqual(entity, 'Table1')  # default when no table_name

    def test_custom_table_name(self):
        filters = [{'field': 'Region', 'values': ['East']}]
        result = create_filters_config(filters, table_name='Sales')
        entity = result[0]['expression']['Column']['Expression']['SourceRef']['Entity']
        self.assertEqual(entity, 'Sales')

    def test_from_entity_matches(self):
        filters = [{'field': 'City', 'values': ['Paris']}]
        result = create_filters_config(filters, table_name='Geography')
        from_entity = result[0]['filter']['From'][0]['Entity']
        self.assertEqual(from_entity, 'Geography')

    def test_empty_filters(self):
        result = create_filters_config([], table_name='Orders')
        self.assertEqual(result, [])

    def test_multiple_filters_same_table(self):
        filters = [
            {'field': 'Region', 'values': ['East']},
            {'field': 'City', 'values': ['Paris', 'London']},
        ]
        result = create_filters_config(filters, table_name='Geo')
        self.assertEqual(len(result), 2)
        for f in result:
            self.assertEqual(f['expression']['Column']['Expression']['SourceRef']['Entity'], 'Geo')


class TestPrepFlowAggregations(unittest.TestCase):
    """Prep flow VAR/VARP aggregation mapping fixes."""

    def test_var_maps_to_var(self):
        self.assertEqual(_PREP_AGG_MAP['VAR'], 'var')

    def test_varp_maps_to_varp(self):
        self.assertEqual(_PREP_AGG_MAP['VARP'], 'varp')

    def test_var_not_sum(self):
        self.assertNotEqual(_PREP_AGG_MAP['VAR'], 'sum')

    def test_varp_not_sum(self):
        self.assertNotEqual(_PREP_AGG_MAP['VARP'], 'sum')


class TestPrepFlowJoinMapping(unittest.TestCase):
    """Prep flow notInner join mapping fix."""

    def test_notinner_is_leftanti(self):
        self.assertEqual(_PREP_JOIN_MAP['notInner'], 'leftanti')

    def test_notinner_not_full(self):
        self.assertNotEqual(_PREP_JOIN_MAP['notInner'], 'full')

    def test_left_only_unchanged(self):
        self.assertEqual(_PREP_JOIN_MAP['leftOnly'], 'leftanti')

    def test_right_only_unchanged(self):
        self.assertEqual(_PREP_JOIN_MAP['rightOnly'], 'rightanti')


class TestMQueryFallback(unittest.TestCase):
    """M query fallback generator improvements."""

    def test_fallback_has_try_otherwise(self):
        columns = [{'name': 'ID', 'datatype': 'integer'}, {'name': 'Name', 'datatype': 'string'}]
        result = _gen_m_fallback({'_conn_type': 'CustomDB'}, 'MyTable', columns)
        self.assertIn('try', result)
        self.assertIn('otherwise', result)

    def test_fallback_has_conn_type(self):
        columns = [{'name': 'Col1', 'datatype': 'string'}]
        result = _gen_m_fallback({'_conn_type': 'Splunk'}, 'Events', columns)
        self.assertIn('Splunk', result)

    def test_fallback_has_todo(self):
        columns = [{'name': 'X', 'datatype': 'integer'}]
        result = _gen_m_fallback({'_conn_type': 'Unknown'}, 'T', columns)
        self.assertIn('TODO', result)

    def test_fallback_empty_table_on_error(self):
        columns = [{'name': 'A', 'datatype': 'string'}]
        result = _gen_m_fallback({}, 'T', columns)
        self.assertIn('Empty table on error', result)

    def test_fallback_has_column_names(self):
        columns = [{'name': 'Revenue', 'datatype': 'real'}, {'name': 'Qty', 'datatype': 'integer'}]
        result = _gen_m_fallback({}, 'Sales', columns)
        self.assertIn('"Revenue"', result)
        self.assertIn('"Qty"', result)


# ════════════════════════════════════════════════════════════════════
#  Sprint 11: Assessment & Intelligence
# ════════════════════════════════════════════════════════════════════

class TestAssessmentModernFeatures(unittest.TestCase):
    """Assessment detects Tableau 2024.3+ features."""

    def _make_extracted(self, **kwargs):
        base = {
            'worksheets': [], 'dashboards': [], 'datasources': [],
            'calculations': [], 'parameters': [], 'filters': [],
            'user_filters': [], 'actions': [], 'stories': [],
            'sets': [], 'groups': [], 'bins': [],
            'hierarchies': [], 'sort_orders': [], 'custom_sql': [],
        }
        base.update(kwargs)
        return base

    def test_no_modern_features(self):
        result = _check_migration_scope(self._make_extracted())
        modern_checks = [c for c in result.checks if 'Modern' in c.name]
        self.assertTrue(len(modern_checks) > 0)
        self.assertEqual(modern_checks[0].severity, 'pass')

    def test_dynamic_visibility_detected(self):
        ws = [{'dynamic_visibility': True}]
        result = _check_migration_scope(self._make_extracted(worksheets=ws))
        modern_checks = [c for c in result.checks if 'Modern' in c.name]
        self.assertTrue(len(modern_checks) > 0)
        self.assertEqual(modern_checks[0].severity, 'warn')
        self.assertIn('Dynamic Zone Visibility', modern_checks[0].detail)

    def test_dynamic_parameters_detected(self):
        params = [{'domain_type': 'database', 'name': 'P1'}]
        result = _check_migration_scope(self._make_extracted(parameters=params))
        modern_checks = [c for c in result.checks if 'Modern' in c.name]
        self.assertEqual(modern_checks[0].severity, 'warn')
        self.assertIn('Dynamic Parameters', modern_checks[0].detail)

    def test_rawsql_detected(self):
        calcs = [{'formula': 'RAWSQL_REAL("SELECT 1")'}]
        result = _check_migration_scope(self._make_extracted(calculations=calcs))
        modern_checks = [c for c in result.checks if 'Modern' in c.name]
        self.assertEqual(modern_checks[0].severity, 'warn')
        self.assertIn('RAWSQL', modern_checks[0].detail)

    def test_combined_axes_detected(self):
        ws = [{'axes': {'x': {'combined_axis': True}}}]
        result = _check_migration_scope(self._make_extracted(worksheets=ws))
        modern_checks = [c for c in result.checks if 'Modern' in c.name]
        self.assertEqual(modern_checks[0].severity, 'warn')
        self.assertIn('Combined/Synchronized', modern_checks[0].detail)

    def test_full_assessment_includes_modern(self):
        """run_assessment should include the modern features check."""
        extracted = self._make_extracted()
        report = run_assessment(extracted, workbook_name='TestWB')
        all_checks = []
        for cat in report.categories:
            all_checks.extend(cat.checks)
        modern = [c for c in all_checks if 'Modern' in c.name]
        self.assertTrue(len(modern) > 0)


class TestAssessmentPartialFunctions(unittest.TestCase):
    """WINDOW_CORR/COVAR/COVARP removed from partial functions (now fully converted)."""

    def test_window_corr_not_partial(self):
        from powerbi_import.assessment import _PARTIAL_FUNCTIONS
        # WINDOW_CORR should NOT match _PARTIAL_FUNCTIONS anymore
        self.assertIsNone(_PARTIAL_FUNCTIONS.search('WINDOW_CORR('))

    def test_window_covar_not_partial(self):
        from powerbi_import.assessment import _PARTIAL_FUNCTIONS
        self.assertIsNone(_PARTIAL_FUNCTIONS.search('WINDOW_COVAR('))

    def test_index_not_partial(self):
        """INDEX is now properly converted, should not be in partial list."""
        from powerbi_import.assessment import _PARTIAL_FUNCTIONS
        self.assertIsNone(_PARTIAL_FUNCTIONS.search('INDEX('))

    def test_regexp_extract_nth_still_partial(self):
        from powerbi_import.assessment import _PARTIAL_FUNCTIONS
        self.assertIsNotNone(_PARTIAL_FUNCTIONS.search('REGEXP_EXTRACT_NTH('))


# ════════════════════════════════════════════════════════════════════
#  Sprint 10: Logging in pbip_generator
# ════════════════════════════════════════════════════════════════════

class TestPbipGeneratorLogging(unittest.TestCase):
    """Verify pbip_generator has logging configured."""

    def test_logger_exists(self):
        import powerbi_import.pbip_generator as pg
        self.assertTrue(hasattr(pg, 'logger'))

    def test_logger_is_logger(self):
        import logging
        import powerbi_import.pbip_generator as pg
        self.assertIsInstance(pg.logger, logging.Logger)


if __name__ == '__main__':
    unittest.main()
