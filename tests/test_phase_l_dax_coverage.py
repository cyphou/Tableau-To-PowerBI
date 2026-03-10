"""Phase L — DAX Conversion Coverage Hardening.

50 new tests covering untested and under-tested DAX conversion patterns.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tableau_export.dax_converter import convert_tableau_formula_to_dax


class TestIndexInCompound(unittest.TestCase):
    """INDEX() in compound formulas."""

    def test_index_standalone(self):
        result = convert_tableau_formula_to_dax('INDEX()')
        self.assertIn('RANKX', result)

    def test_index_in_if(self):
        result = convert_tableau_formula_to_dax('IF INDEX() = 1 THEN "First" ELSE "Other" END')
        self.assertIn('RANKX', result)
        self.assertIn('IF', result)

    def test_index_divided_by_size(self):
        result = convert_tableau_formula_to_dax('INDEX() / SIZE()')
        self.assertIn('RANKX', result)
        self.assertIn('COUNTROWS', result)


class TestSizeInCompound(unittest.TestCase):
    """SIZE() in compound formulas."""

    def test_size_standalone(self):
        result = convert_tableau_formula_to_dax('SIZE()')
        self.assertIn('COUNTROWS', result)
        self.assertIn('ALLSELECTED', result)

    def test_size_in_if(self):
        result = convert_tableau_formula_to_dax('IF SIZE() > 10 THEN "Large" ELSE "Small" END')
        self.assertIn('COUNTROWS', result)


class TestFirstLastInCompound(unittest.TestCase):
    """FIRST()/LAST() in compound formulas."""

    def test_first_standalone(self):
        result = convert_tableau_formula_to_dax('FIRST()')
        self.assertIn('0', result)

    def test_last_standalone(self):
        result = convert_tableau_formula_to_dax('LAST()')
        self.assertIn('0', result)

    def test_first_in_if(self):
        result = convert_tableau_formula_to_dax('IF FIRST() = 0 THEN [Sales] END')
        self.assertIn('IF', result)

    def test_last_in_if(self):
        result = convert_tableau_formula_to_dax('IF LAST() = 0 THEN [Sales] END')
        self.assertIn('IF', result)


class TestRankVariants(unittest.TestCase):
    """RANK_MODIFIED, RANK_PERCENTILE with compute_using."""

    def test_rank_modified_basic(self):
        result = convert_tableau_formula_to_dax('RANK_MODIFIED(SUM([Sales]))')
        self.assertIn('RANKX', result)

    def test_rank_modified_with_compute_using(self):
        result = convert_tableau_formula_to_dax(
            'RANK_MODIFIED(SUM([Sales]))',
            compute_using=['Region']
        )
        self.assertIn('RANKX', result)

    def test_rank_percentile_with_compute_using(self):
        result = convert_tableau_formula_to_dax(
            'RANK_PERCENTILE(SUM([Sales]))',
            compute_using=['Region']
        )
        self.assertIn('RANKX', result)
        self.assertIn('DIVIDE', result)


class TestWindowStatistical(unittest.TestCase):
    """WINDOW_STDEVP, WINDOW_VARP, WINDOW_CORR/COVAR/COVARP."""

    def test_window_stdevp(self):
        result = convert_tableau_formula_to_dax('WINDOW_STDEVP(SUM([Sales]))')
        # Output uses STDEVX.P iterator pattern
        self.assertIn('STDEVX.P', result)

    def test_window_varp(self):
        result = convert_tableau_formula_to_dax('WINDOW_VARP(SUM([Sales]))')
        self.assertIn('VAR.P', result)

    def test_window_corr(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_CORR(SUM([X]), SUM([Y]))',
            table_name='Sales'
        )
        # Should produce VAR/SUMX correlation pattern
        self.assertNotIn('WINDOW_CORR', result)

    def test_window_covar(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_COVAR(SUM([X]), SUM([Y]))',
            table_name='Sales'
        )
        self.assertNotIn('WINDOW_COVAR', result)

    def test_window_covarp(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_COVARP(SUM([X]), SUM([Y]))',
            table_name='Sales'
        )
        self.assertNotIn('WINDOW_COVARP', result)


class TestTableCalcEdgeCases(unittest.TestCase):
    """LOOKUP, PREVIOUS_VALUE, RUNNING_*, TOTAL edge cases."""

    def test_lookup_zero_offset(self):
        result = convert_tableau_formula_to_dax('LOOKUP(SUM([Sales]), 0)')
        self.assertNotIn('LOOKUP', result)

    def test_previous_value_nonzero_seed(self):
        result = convert_tableau_formula_to_dax('PREVIOUS_VALUE(100)')
        self.assertNotIn('PREVIOUS_VALUE', result)

    def test_running_sum_nested_expr(self):
        result = convert_tableau_formula_to_dax('RUNNING_SUM(SUM([Sales]) * 2)')
        self.assertIn('CALCULATE', result)

    def test_total_countd(self):
        result = convert_tableau_formula_to_dax('TOTAL(COUNTD([Customer]))')
        self.assertIn('CALCULATE', result)

    def test_running_sum_with_compute_using(self):
        result = convert_tableau_formula_to_dax(
            'RUNNING_SUM(SUM([Sales]))',
            compute_using=['Date'],
            table_name='Orders'
        )
        self.assertIn('CALCULATE', result)


class TestDateConverterEdgeCases(unittest.TestCase):
    """DATEDIFF with all interval types, DATENAME, DATEPARSE."""

    def test_datediff_second(self):
        result = convert_tableau_formula_to_dax('DATEDIFF([Start], [End], "second")')
        self.assertIn('DATEDIFF', result)
        # Interval arg is preserved as a string literal
        self.assertIn('second', result.lower())

    def test_datediff_quarter(self):
        result = convert_tableau_formula_to_dax('DATEDIFF([Start], [End], "quarter")')
        self.assertIn('DATEDIFF', result)
        self.assertIn('quarter', result.lower())

    def test_datename_hour(self):
        result = convert_tableau_formula_to_dax('DATENAME("hour", [DateTime])')
        # Should produce HOUR() or FORMAT pattern
        self.assertNotIn('DATENAME', result)

    def test_dateparse_us_format(self):
        result = convert_tableau_formula_to_dax('DATEPARSE("MM/dd/yyyy", [DateStr])')
        self.assertNotIn('DATEPARSE', result)


class TestStringConverterEdgeCases(unittest.TestCase):
    """STR, FLOAT, ENDSWITH, STARTSWITH, SPLIT, FIND edge cases."""

    def test_str_with_expression(self):
        result = convert_tableau_formula_to_dax('STR(SUM([Sales]))')
        self.assertIn('FORMAT', result)

    def test_float_nested(self):
        result = convert_tableau_formula_to_dax('FLOAT(INT([Value]))')
        # Should have at least one conversion
        self.assertNotIn('FLOAT', result)

    def test_endswith_column_arg(self):
        result = convert_tableau_formula_to_dax('ENDSWITH([Name], "son")')
        self.assertNotIn('ENDSWITH', result)

    def test_startswith_column_arg(self):
        result = convert_tableau_formula_to_dax('STARTSWITH([Name], "Dr")')
        self.assertNotIn('STARTSWITH', result)

    def test_find_three_args(self):
        result = convert_tableau_formula_to_dax('FIND([Name], "X", 3)')
        # FIND is preserved as valid DAX FIND
        self.assertIn('FIND', result)


class TestLODCombos(unittest.TestCase):
    """LOD expressions combined with other patterns."""

    def test_lod_ratio(self):
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : SUM([Sales])} / {FIXED : SUM([Sales])}',
            table_name='Orders'
        )
        self.assertIn('CALCULATE', result)
        self.assertNotIn('{FIXED', result)

    def test_exclude_lod(self):
        result = convert_tableau_formula_to_dax(
            '{EXCLUDE [SubCat] : SUM([Sales])}',
            table_name='Orders'
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('REMOVEFILTERS', result)

    def test_include_lod_with_median(self):
        result = convert_tableau_formula_to_dax(
            '{INCLUDE [SubCat] : MEDIAN([Score])}',
            table_name='Orders'
        )
        self.assertIn('CALCULATE', result)

    def test_lod_with_date_literal(self):
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : SUM(IF [Date] >= #2024-01-01# THEN [Sales] END)}',
            table_name='Orders'
        )
        self.assertIn('DATE(2024', result)


class TestOperatorsAndCaseInsensitivity(unittest.TestCase):
    """Operator conversion ordering and case-insensitive function names."""

    def test_lowercase_sum(self):
        result = convert_tableau_formula_to_dax('sum([sales])')
        self.assertIn('SUM', result)

    def test_mixed_case_isnull(self):
        result = convert_tableau_formula_to_dax('IsNull([Field])')
        self.assertIn('ISBLANK', result)

    def test_all_operators_combined(self):
        result = convert_tableau_formula_to_dax('[A] != [B] AND [C] == [D]')
        self.assertIn('<>', result)
        self.assertNotIn('!=', result)
        # == should become =
        self.assertNotIn('==', result)

    def test_and_or_conversion(self):
        result = convert_tableau_formula_to_dax('IF [A] > 1 or [B] < 2 THEN 1 END')
        self.assertIn('||', result)

    def test_neq_and_eq_in_same_formula(self):
        result = convert_tableau_formula_to_dax('IF [A] != 1 AND [B] == 2 THEN "X" END')
        self.assertIn('<>', result)
        self.assertNotIn('!=', result)

    def test_deep_nested_if(self):
        result = convert_tableau_formula_to_dax(
            'IF IF [A]>1 THEN [B] ELSE [C] END > 10 THEN "Hi" ELSE "Lo" END'
        )
        self.assertIn('IF', result)
        # Should produce valid nested IF
        self.assertNotIn('THEN', result)

    def test_string_concat_with_nested_functions(self):
        result = convert_tableau_formula_to_dax(
            '[First] + " (" + STR([Age]) + ")"',
            calc_datatype='string'
        )
        self.assertIn('&', result)


class TestSpatialPlaceholders(unittest.TestCase):
    """Untested spatial functions: BUFFER, AREA, INTERSECTION."""

    def test_buffer(self):
        result = convert_tableau_formula_to_dax('BUFFER([Shape], 10)')
        self.assertIn('BUFFER', result.upper())
        # Should contain a comment about no DAX equivalent
        self.assertIn('spatial', result.lower())

    def test_area(self):
        result = convert_tableau_formula_to_dax('AREA([Shape])')
        self.assertIn('AREA', result.upper())

    def test_intersection(self):
        result = convert_tableau_formula_to_dax('INTERSECTION([S1], [S2])')
        self.assertIn('INTERSECTION', result.upper())


class TestRegexpSmartPatterns(unittest.TestCase):
    """REGEXP_MATCH smart patterns, REGEXP_EXTRACT_NTH, REGEXP_REPLACE."""

    def test_regexp_match_ends_with(self):
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Email], ".*\\.com$")')
        # Complex regex falls back to CONTAINSSTRING with comment
        self.assertIn('CONTAINSSTRING', result)

    def test_regexp_extract_nth_delimiter(self):
        result = convert_tableau_formula_to_dax('REGEXP_EXTRACT_NTH([Path], "([^/]*)", 2)')
        self.assertNotIn('REGEXP_EXTRACT_NTH', result)

    def test_regexp_replace_char_class(self):
        result = convert_tableau_formula_to_dax('REGEXP_REPLACE([Phone], "[^0-9]", "")')
        self.assertNotIn('REGEXP_REPLACE', result)


class TestMultipleFunctionsInFormula(unittest.TestCase):
    """Multiple function calls in a single formula."""

    def test_sum_and_countd(self):
        result = convert_tableau_formula_to_dax('SUM([Sales]) / COUNTD([Customer])')
        self.assertIn('SUM', result)
        self.assertIn('DISTINCTCOUNT', result)

    def test_agg_if_aggx_combo(self):
        result = convert_tableau_formula_to_dax(
            'SUM(IF [Type]="A" THEN [Sales] END)',
            table_name='Orders'
        )
        self.assertIn('SUMX', result)

    def test_percent_of_total_pattern(self):
        result = convert_tableau_formula_to_dax(
            'SUM([Sales]) / TOTAL(SUM([Sales]))',
            table_name='Orders'
        )
        self.assertIn('SUM', result)
        self.assertIn('CALCULATE', result)


class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_empty_formula_with_compute_using(self):
        result = convert_tableau_formula_to_dax('', compute_using=['Region'])
        self.assertEqual(result, '')

    def test_none_formula(self):
        result = convert_tableau_formula_to_dax(None)
        # None input returns None
        self.assertIsNone(result)

    def test_date_literal_in_if(self):
        result = convert_tableau_formula_to_dax(
            'IF [Date] >= #2024-01-01# THEN "Yes" ELSE "No" END'
        )
        self.assertIn('DATE(2024', result)
        self.assertNotIn('#', result)

    def test_multiline_formula(self):
        result = convert_tableau_formula_to_dax(
            'IF [A] > 1\nTHEN [B]\nELSE [C]\nEND'
        )
        self.assertIn('IF', result)
        # Should be condensed to single line
        self.assertNotIn('\n', result)


if __name__ == '__main__':
    unittest.main()
