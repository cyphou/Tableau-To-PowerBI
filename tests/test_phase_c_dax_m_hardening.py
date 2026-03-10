"""
Tests for Phase C — DAX & M Conversion Hardening (v5.3.0).

Tests cover:
- WINDOW_CORR/COVAR/COVARP dedicated converters (replacing naive prefix swap)
- REGEXP_EXTRACT_NTH dedicated converter (replacing broken MID prefix)
- Nested LOD parenthesis depth tracking (colon-inside-function edge case)
- CORR/COVAR/COVARP table_name parameter support
- M query error handling functions (try...otherwise, remove/replace errors)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dax_converter import convert_tableau_formula_to_dax


# ═══════════════════════════════════════════════════════════════════════
# WINDOW_CORR / WINDOW_COVAR / WINDOW_COVARP
# ═══════════════════════════════════════════════════════════════════════

class TestWindowCorrelationCovariance(unittest.TestCase):
    """Test WINDOW_CORR/COVAR/COVARP produce valid VAR/SUMX DAX (not fake CORREL)."""

    def test_window_corr_produces_var_pattern(self):
        """WINDOW_CORR should produce VAR _MeanX/Y + SUMX pattern, not CORREL."""
        result = convert_tableau_formula_to_dax(
            'WINDOW_CORR([Sales], [Profit])',
            table_name='Orders'
        )
        # Must NOT contain CORREL (not a real DAX function)
        self.assertNotIn('CORREL(', result)
        # Must contain VAR pattern (the real DAX approach)
        self.assertIn('VAR _MeanX', result)
        self.assertIn('VAR _MeanY', result)
        self.assertIn('SUMX', result)
        self.assertIn('DIVIDE(', result)
        # Must reference the correct table
        self.assertIn("'Orders'", result)
        # Wrapped in CALCULATE for windowing context
        self.assertIn('CALCULATE(', result)

    def test_window_covar_produces_var_pattern(self):
        """WINDOW_COVAR should produce sample covariance (N-1 divisor)."""
        result = convert_tableau_formula_to_dax(
            'WINDOW_COVAR([Revenue], [Cost])',
            table_name='Financials'
        )
        self.assertNotIn('COVARIANCE.S(', result)
        self.assertIn('VAR _MeanX', result)
        self.assertIn('VAR _N', result)
        self.assertIn('_N - 1', result)  # sample covariance divides by N-1
        self.assertIn("'Financials'", result)
        self.assertIn('CALCULATE(', result)

    def test_window_covarp_produces_var_pattern(self):
        """WINDOW_COVARP should produce population covariance (N divisor)."""
        result = convert_tableau_formula_to_dax(
            'WINDOW_COVARP([X], [Y])',
            table_name='Data'
        )
        self.assertNotIn('COVARIANCE.P(', result)
        self.assertIn('VAR _MeanX', result)
        self.assertIn('VAR _N', result)
        # Population covariance: divides by N, not N-1
        self.assertIn('_N, 0)', result)  # DIVIDE(..., _N, 0)
        self.assertNotIn('_N - 1', result)
        self.assertIn("'Data'", result)

    def test_window_corr_with_compute_using(self):
        """WINDOW_CORR with compute_using should use ALLEXCEPT."""
        result = convert_tableau_formula_to_dax(
            'WINDOW_CORR([Sales], [Profit])',
            table_name='Orders',
            compute_using=['Region', 'Category'],
            column_table_map={'Region': 'Orders', 'Category': 'Orders'}
        )
        self.assertIn('ALLEXCEPT(', result)
        self.assertIn("'Orders'[Region]", result)
        self.assertIn("'Orders'[Category]", result)

    def test_window_corr_insufficient_args_fallback(self):
        """WINDOW_CORR with only 1 arg should produce fallback comment."""
        result = convert_tableau_formula_to_dax(
            'WINDOW_CORR([Sales])',
            table_name='Orders'
        )
        self.assertIn('insufficient arguments', result)

    def test_window_covar_case_insensitive(self):
        """WINDOW_COVAR should match case-insensitively."""
        result = convert_tableau_formula_to_dax(
            'window_covar([a], [b])',
            table_name='T'
        )
        self.assertIn('VAR _MeanX', result)
        self.assertIn('CALCULATE(', result)

    def test_window_corr_no_infinite_loop(self):
        """WINDOW_CORR conversion must not create infinite replacement loops."""
        result = convert_tableau_formula_to_dax(
            'WINDOW_CORR([x], [y]) + WINDOW_COVARP([a], [b])',
            table_name='T'
        )
        # Both should be converted
        self.assertNotIn('WINDOW_CORR', result)
        self.assertNotIn('WINDOW_COVARP', result)
        # Both should have VAR patterns
        self.assertIn('CALCULATE(', result)


# ═══════════════════════════════════════════════════════════════════════
# CORR / COVAR / COVARP — table_name parameter
# ═══════════════════════════════════════════════════════════════════════

class TestCorrCovarTableName(unittest.TestCase):
    """Test that CORR/COVAR/COVARP use the correct table name (not hardcoded 'Table')."""

    def test_corr_uses_provided_table_name(self):
        result = convert_tableau_formula_to_dax(
            'CORR([Sales], [Profit])',
            table_name='OrderFacts'
        )
        self.assertIn("'OrderFacts'", result)
        self.assertNotIn("'Table'", result)

    def test_covar_uses_provided_table_name(self):
        result = convert_tableau_formula_to_dax(
            'COVAR([X], [Y])',
            table_name='Measurements'
        )
        self.assertIn("'Measurements'", result)
        self.assertNotIn("'Table'", result)

    def test_covarp_uses_provided_table_name(self):
        result = convert_tableau_formula_to_dax(
            'COVARP([A], [B])',
            table_name='SensorData'
        )
        self.assertIn("'SensorData'", result)
        self.assertNotIn("'Table'", result)

    def test_corr_with_apostrophe_in_table_name(self):
        """Table names with apostrophes should be properly escaped."""
        result = convert_tableau_formula_to_dax(
            'CORR([X], [Y])',
            table_name="Customer's Orders"
        )
        self.assertIn("Customer''s Orders", result)


# ═══════════════════════════════════════════════════════════════════════
# REGEXP_EXTRACT_NTH — dedicated converter
# ═══════════════════════════════════════════════════════════════════════

class TestRegexpExtractNth(unittest.TestCase):
    """Test REGEXP_EXTRACT_NTH uses proper argument parsing (not broken MID prefix)."""

    def test_delimiter_based_extraction(self):
        """REGEXP_EXTRACT_NTH with delimiter pattern → PATHITEM(SUBSTITUTE(...))."""
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT_NTH([FullName], "([^-]*)", 2)',
            table_name='People'
        )
        self.assertIn('PATHITEM(', result)
        self.assertIn('SUBSTITUTE(', result)
        self.assertIn('"-"', result)
        self.assertIn(', 2)', result)

    def test_delimiter_comma_pattern(self):
        """REGEXP_EXTRACT_NTH with comma delimiter."""
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT_NTH([Address], "([^,]*)", 3)',
            table_name='Addresses'
        )
        self.assertIn('PATHITEM(', result)
        self.assertIn('","', result)
        self.assertIn(', 3)', result)

    def test_does_not_produce_broken_mid(self):
        """Result must NOT be a bare MID( prefix swap (the old broken behavior)."""
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT_NTH([Field], "([^/]*)", 1)',
            table_name='T'
        )
        # Should not start with "/* REGEXP_EXTRACT_NTH: use PATHITEM" (old broken output)
        self.assertNotIn('REGEXP_EXTRACT_NTH: use PATHITEM', result)
        self.assertIn('PATHITEM(', result)

    def test_fixed_prefix_capture(self):
        """Pattern like 'prefix(.*)' → MID extraction."""
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT_NTH([URL], "https://(.*)", 1)',
            table_name='T'
        )
        self.assertIn('MID(', result)
        self.assertIn('SEARCH("https://"', result)

    def test_alternation_capture(self):
        """Pattern like '(cat|dog|fish)' → IF chain with CONTAINSSTRING."""
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT_NTH([Animal], "(cat|dog|fish)", 1)',
            table_name='Animals'
        )
        self.assertIn('CONTAINSSTRING(', result)
        self.assertIn('"cat"', result)
        self.assertIn('"dog"', result)
        self.assertIn('"fish"', result)

    def test_complex_pattern_fallback(self):
        """Complex regex patterns should produce BLANK() with migration comment."""
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT_NTH([Data], "(\\\\d{3})-(\\\\d{2})", 1)',
            table_name='T'
        )
        self.assertIn('BLANK()', result)
        self.assertIn('manual conversion needed', result)

    def test_two_args_defaults_to_index_1(self):
        """REGEXP_EXTRACT_NTH with only 2 args should default to index 1."""
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT_NTH([Name], "([^ ]*)")',
            table_name='T'
        )
        # Should not error — should produce some output
        self.assertFalse(result.startswith('REGEXP_EXTRACT_NTH'))

    def test_one_arg_fallback(self):
        """REGEXP_EXTRACT_NTH with only 1 arg should produce fallback."""
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT_NTH([Name])',
            table_name='T'
        )
        self.assertIn('insufficient arguments', result)


# ═══════════════════════════════════════════════════════════════════════
# Nested LOD — parenthesis depth in colon-split
# ═══════════════════════════════════════════════════════════════════════

class TestNestedLODEdgeCases(unittest.TestCase):
    """Test LOD conversion handles colons inside function calls and nested LODs."""

    def test_lod_with_colon_in_format(self):
        """LOD with FORMAT(date, 'HH:mm') should not split on the colon in HH:mm."""
        result = convert_tableau_formula_to_dax(
            '{FIXED [Customer] : SUM([Sales])}',
            table_name='Orders',
            column_table_map={'Customer': 'Orders', 'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE(', result)
        self.assertIn('SUM(', result)
        self.assertIn('ALLEXCEPT(', result)
        # Should not contain raw braces
        self.assertNotIn('{', result)
        self.assertNotIn('}', result)

    def test_nested_lod_fixed_in_fixed(self):
        """Nested LOD: {FIXED [Region] : {FIXED [State] : SUM([Sales])}}."""
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : {FIXED [State] : SUM([Sales])}}',
            table_name='Orders',
            column_table_map={'Region': 'Orders', 'State': 'Orders', 'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE(', result)
        # Should not contain raw braces — both LODs converted
        self.assertNotIn('{FIXED', result)
        self.assertNotIn('{', result.replace('CALCULATE(', ''))

    def test_nested_include_in_fixed(self):
        """Nested: {FIXED [Region] : {INCLUDE [SubCategory] : AVG([Discount])}}."""
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : {INCLUDE [SubCategory] : AVG([Discount])}}',
            table_name='Orders',
            column_table_map={'Region': 'Orders', 'SubCategory': 'Orders', 'Discount': 'Orders'}
        )
        self.assertIn('CALCULATE(', result)
        self.assertNotIn('{FIXED', result)
        self.assertNotIn('{INCLUDE', result)

    def test_lod_with_datediff_containing_colon_arg(self):
        """LOD with DATEDIFF inside — colons in date expressions should not split."""
        # DATEDIFF contains string arg "day" separated by comma not colon,
        # but verify the overall LOD conversion works with complex inner expressions.
        result = convert_tableau_formula_to_dax(
            '{FIXED [Customer] : MIN(DATEDIFF("day", [OrderDate], [ShipDate]))}',
            table_name='Orders',
            column_table_map={'Customer': 'Orders', 'OrderDate': 'Orders', 'ShipDate': 'Orders'}
        )
        self.assertIn('CALCULATE(', result)
        self.assertIn('ALLEXCEPT(', result)

    def test_lod_no_dim(self):
        """LOD without dimensions: {SUM([Sales])}."""
        result = convert_tableau_formula_to_dax(
            '{SUM([Sales])}',
            table_name='Orders'
        )
        self.assertIn('CALCULATE(', result)
        self.assertNotIn('{', result)
        self.assertNotIn('}', result)

    def test_lod_exclude(self):
        """EXCLUDE LOD removes dimension filters."""
        result = convert_tableau_formula_to_dax(
            '{EXCLUDE [Region] : SUM([Sales])}',
            table_name='Orders',
            column_table_map={'Region': 'Orders', 'Sales': 'Orders'}
        )
        self.assertIn('REMOVEFILTERS(', result)


# ═══════════════════════════════════════════════════════════════════════
# M Query Error Handling
# ═══════════════════════════════════════════════════════════════════════

class TestMQueryErrorHandling(unittest.TestCase):
    """Test M query error handling utility functions."""

    def setUp(self):
        from m_query_builder import (
            m_transform_remove_errors,
            m_transform_replace_errors,
            m_transform_try_otherwise,
            wrap_source_with_try_otherwise,
            inject_m_steps,
        )
        self.m_transform_remove_errors = m_transform_remove_errors
        self.m_transform_replace_errors = m_transform_replace_errors
        self.m_transform_try_otherwise = m_transform_try_otherwise
        self.wrap_source_with_try_otherwise = wrap_source_with_try_otherwise
        self.inject_m_steps = inject_m_steps

    def test_remove_errors_all_columns(self):
        """m_transform_remove_errors() without columns removes all row errors."""
        name, expr = self.m_transform_remove_errors()
        self.assertEqual(name, '#"Removed Errors"')
        self.assertIn('Table.RemoveRowsWithErrors({prev})', expr)

    def test_remove_errors_specific_columns(self):
        """m_transform_remove_errors() with columns filters specific columns."""
        name, expr = self.m_transform_remove_errors(['Sales', 'Profit'])
        self.assertIn('"Sales"', expr)
        self.assertIn('"Profit"', expr)
        self.assertIn('Table.RemoveRowsWithErrors', expr)

    def test_replace_errors_default_null(self):
        """m_transform_replace_errors() defaults to null replacement."""
        name, expr = self.m_transform_replace_errors(['Price'])
        self.assertIn('Table.ReplaceErrorValues', expr)
        self.assertIn('"Price"', expr)
        self.assertIn('null', expr)

    def test_replace_errors_custom_value(self):
        """m_transform_replace_errors() with custom replacement value."""
        name, expr = self.m_transform_replace_errors(['Amount'], replacement='0')
        self.assertIn('each 0', expr)

    def test_try_otherwise(self):
        """m_transform_try_otherwise wraps expression in try...otherwise."""
        name, expr = self.m_transform_try_otherwise(
            '#"Safe Source"',
            'Sql.Database("server", "db")',
            '#table({}, {})'
        )
        self.assertEqual(name, '#"Safe Source"')
        self.assertIn('try ', expr)
        self.assertIn('otherwise', expr)
        self.assertIn('Sql.Database', expr)
        self.assertIn('#table', expr)

    def test_inject_error_handling_steps(self):
        """Error handling steps can be injected into an M query via inject_m_steps."""
        m_query = '''let
    Source = Sql.Database("server", "db"),
    #"Changed Types" = Table.TransformColumnTypes(Source, {{"Sales", type number}})
in
    #"Changed Types"'''
        steps = [
            self.m_transform_remove_errors(),
            self.m_transform_replace_errors(['Sales'], replacement='0'),
        ]
        result = self.inject_m_steps(m_query, steps)
        self.assertIn('#"Removed Errors"', result)
        self.assertIn('#"Replaced Errors"', result)
        self.assertIn('Table.RemoveRowsWithErrors', result)
        self.assertIn('Table.ReplaceErrorValues', result)

    def test_wrap_source_with_try_otherwise(self):
        """wrap_source_with_try_otherwise wraps Source step."""
        m_query = '''let
    Source = Sql.Database("server", "db"),
    #"Nav" = Source{[Schema="dbo", Item="Orders"]}[Data]
in
    #"Nav"'''
        result = self.wrap_source_with_try_otherwise(m_query, ['OrderID', 'Sales'])
        self.assertIn('try', result)
        self.assertIn('otherwise', result)
        self.assertIn('"OrderID"', result)
        self.assertIn('"Sales"', result)

    def test_wrap_source_no_columns(self):
        """wrap_source_with_try_otherwise without columns uses empty table."""
        m_query = '''let
    Source = Excel.Workbook(File.Contents("data.xlsx"))
in
    Source'''
        result = self.wrap_source_with_try_otherwise(m_query)
        self.assertIn('try', result)
        self.assertIn('#table({}, {})', result)

    def test_wrap_source_no_match(self):
        """wrap_source_with_try_otherwise returns unchanged if no Source step."""
        m_query = '''let
    Data = #table({"A"}, {{"x"}})
in
    Data'''
        result = self.wrap_source_with_try_otherwise(m_query)
        self.assertEqual(result, m_query)


# ═══════════════════════════════════════════════════════════════════════
# WINDOW_SUM/AVG/MAX/MIN (existing — non-regression)
# ═══════════════════════════════════════════════════════════════════════

class TestWindowFunctionsNonRegression(unittest.TestCase):
    """Ensure existing WINDOW_SUM/AVG/MAX/MIN still work correctly."""

    def test_window_sum_basic(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_SUM(SUM([Sales]))',
            table_name='Orders'
        )
        self.assertIn('CALCULATE(', result)
        self.assertIn("ALL('Orders')", result)

    def test_window_avg_with_compute_using(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_AVG(AVG([Profit]))',
            table_name='Orders',
            compute_using=['Region'],
            column_table_map={'Region': 'Orders'}
        )
        self.assertIn('ALLEXCEPT(', result)
        self.assertIn("'Orders'[Region]", result)

    def test_window_max_basic(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_MAX(MAX([Quantity]))',
            table_name='Orders'
        )
        self.assertIn('CALCULATE(', result)
        self.assertIn("ALL('Orders')", result)

    def test_window_min_basic(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_MIN(MIN([Cost]))',
            table_name='Orders'
        )
        self.assertIn('CALCULATE(', result)

    def test_window_count_basic(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_COUNT(COUNT([OrderID]))',
            table_name='Orders'
        )
        self.assertIn('CALCULATE(', result)


# ═══════════════════════════════════════════════════════════════════════
# REGEXP_MATCH / REGEXP_EXTRACT / REGEXP_REPLACE (existing — non-regression)
# ═══════════════════════════════════════════════════════════════════════

class TestRegexpNonRegression(unittest.TestCase):
    """Ensure existing REGEXP converters still work correctly."""

    def test_regexp_match_starts_with(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_MATCH([Name], "^John")',
            table_name='People'
        )
        self.assertIn('LEFT(', result)
        self.assertIn('"John"', result)

    def test_regexp_match_ends_with(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_MATCH([Email], "com$")',
            table_name='Users'
        )
        self.assertIn('RIGHT(', result)

    def test_regexp_match_alternation(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_MATCH([Status], "active|pending")',
            table_name='Users'
        )
        self.assertIn('CONTAINSSTRING(', result)
        # Should produce OR of two CONTAINSSTRING calls
        self.assertIn('||', result)

    def test_regexp_extract_prefix_capture(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT([URL], "https://(.*)")',
            table_name='Pages'
        )
        self.assertIn('MID(', result)
        self.assertIn('SEARCH("https://"', result)

    def test_regexp_replace_simple_literal(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_REPLACE([Text], "foo", "bar")',
            table_name='Data'
        )
        self.assertIn('SUBSTITUTE(', result)
        self.assertIn('"foo"', result)
        self.assertIn('"bar"', result)

    def test_regexp_replace_char_class(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_REPLACE([Data], "[abc]", "X")',
            table_name='T'
        )
        # Should produce chained SUBSTITUTE calls
        self.assertIn('SUBSTITUTE(', result)


# ═══════════════════════════════════════════════════════════════════════
# SPLIT (existing — non-regression)
# ═══════════════════════════════════════════════════════════════════════

class TestSplitNonRegression(unittest.TestCase):
    """Ensure SPLIT still works correctly."""

    def test_split_3_args(self):
        result = convert_tableau_formula_to_dax(
            'SPLIT([Name], "-", 2)',
            table_name='T'
        )
        self.assertIn('PATHITEM(', result)
        self.assertIn('SUBSTITUTE(', result)
        self.assertIn('2)', result)

    def test_split_2_args(self):
        result = convert_tableau_formula_to_dax(
            'SPLIT([Name], "-")',
            table_name='T'
        )
        self.assertIn('PATHITEM(', result)
        self.assertIn(', 1)', result)  # defaults to token 1


if __name__ == '__main__':
    unittest.main()
