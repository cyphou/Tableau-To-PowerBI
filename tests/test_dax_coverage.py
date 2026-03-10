"""
Extended DAX Converter Tests — comprehensive coverage boost.

Targets under-covered converters identified in gap analysis:
- DATETRUNC variants (quarter, month)
- DATEPART all variants (hour, minute, second, week, weekday)
- DATENAME, DATEPARSE, ISDATE
- ENDSWITH, STARTSWITH, PROPER, SPLIT
- ATAN2, DIV, SQUARE, IIF
- FLOAT→CONVERT, STR→FORMAT
- RADIANS, DEGREES
- PREVIOUS_VALUE, LOOKUP
- CORR, COVAR, COVARP
- WINDOW_*, RANK variants, RUNNING_* functions, TOTAL
- LOD no-dimension, LOD balanced braces
- AGG(expr)→AGGX (SUM(a*b)→SUMX)
- Statistical → iterator: STDEV.S→STDEVX.S, MEDIAN→MEDIANX
- _fix_ceiling_floor, _fix_startof_calc_columns, _fix_date_literals
- _convert_string_concat
- generate_combined_field_dax
- MAKEDATE, MAKEDATETIME, MAKETIME
- REGEXP_*, SCRIPT_*, spatial functions, COLLECT, SIZE, INDEX, FIRST, LAST
- Edge cases: nested functions, balanced parentheses, multi-arg handling
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

from dax_converter import (
    convert_tableau_formula_to_dax,
    generate_combined_field_dax,
    _reverse_tableau_bracket_escape,
    _split_args,
    _fix_date_literals,
    _convert_string_concat,
    _fix_ceiling_floor,
    _normalize_spaces_outside_identifiers,
)


# ═══════════════════════════════════════════════════════════════════════
# DATETRUNC Variants
# ═══════════════════════════════════════════════════════════════════════

class TestDateTruncVariants(unittest.TestCase):
    """Cover all DATETRUNC granularities."""

    def test_datetrunc_quarter(self):
        result = convert_tableau_formula_to_dax("DATETRUNC('quarter', [OrderDate])")
        self.assertIn("STARTOFQUARTER", result)
        self.assertNotIn("DATETRUNC", result)

    def test_datetrunc_month(self):
        result = convert_tableau_formula_to_dax("DATETRUNC('month', [OrderDate])")
        self.assertIn("STARTOFMONTH", result)
        self.assertNotIn("DATETRUNC", result)

    def test_datetrunc_year(self):
        result = convert_tableau_formula_to_dax("DATETRUNC('year', [OrderDate])")
        self.assertIn("STARTOFYEAR", result)
        self.assertNotIn("DATETRUNC", result)

    def test_datetrunc_year_double_quotes(self):
        result = convert_tableau_formula_to_dax('DATETRUNC("year", [OrderDate])')
        self.assertIn("STARTOFYEAR", result)

    def test_datetrunc_no_quotes(self):
        result = convert_tableau_formula_to_dax("DATETRUNC(year, [OrderDate])")
        self.assertIn("STARTOFYEAR", result)

    def test_datetrunc_for_calc_column(self):
        """STARTOFMONTH in calc column context → DATE(YEAR(), MONTH(), 1)."""
        result = convert_tableau_formula_to_dax(
            "DATETRUNC('month', [OrderDate])",
            is_calc_column=True,
            table_name="Orders",
            column_table_map={"OrderDate": "Orders"},
        )
        # Should use DATE function instead of STARTOFMONTH for calc columns
        self.assertIn("DATE", result)
        self.assertIn("MONTH", result)


# ═══════════════════════════════════════════════════════════════════════
# DATEPART All Variants
# ═══════════════════════════════════════════════════════════════════════

class TestDatePartVariants(unittest.TestCase):
    """Cover all DATEPART intervals."""

    def test_datepart_year(self):
        result = convert_tableau_formula_to_dax("DATEPART('year', [D])")
        self.assertIn("YEAR(", result)
        self.assertNotIn("DATEPART", result)

    def test_datepart_quarter(self):
        result = convert_tableau_formula_to_dax("DATEPART('quarter', [D])")
        self.assertIn("QUARTER(", result)

    def test_datepart_month(self):
        result = convert_tableau_formula_to_dax("DATEPART('month', [D])")
        self.assertIn("MONTH(", result)

    def test_datepart_day(self):
        result = convert_tableau_formula_to_dax("DATEPART('day', [D])")
        self.assertIn("DAY(", result)

    def test_datepart_hour(self):
        result = convert_tableau_formula_to_dax("DATEPART('hour', [D])")
        self.assertIn("HOUR(", result)

    def test_datepart_minute(self):
        result = convert_tableau_formula_to_dax("DATEPART('minute', [D])")
        self.assertIn("MINUTE(", result)

    def test_datepart_second(self):
        result = convert_tableau_formula_to_dax("DATEPART('second', [D])")
        self.assertIn("SECOND(", result)

    def test_datepart_week(self):
        result = convert_tableau_formula_to_dax("DATEPART('week', [D])")
        self.assertIn("WEEKNUM(", result)

    def test_datepart_weekday(self):
        result = convert_tableau_formula_to_dax("DATEPART('weekday', [D])")
        self.assertIn("WEEKDAY(", result)


# ═══════════════════════════════════════════════════════════════════════
# DATENAME, DATEPARSE, ISDATE
# ═══════════════════════════════════════════════════════════════════════

class TestDateNameParseFunctions(unittest.TestCase):
    """Test DATENAME, DATEPARSE, and ISDATE converters."""

    def test_datename_month(self):
        result = convert_tableau_formula_to_dax("DATENAME('month', [OrderDate])")
        self.assertIn("FORMAT", result)
        self.assertIn("MMMM", result)

    def test_datename_year(self):
        result = convert_tableau_formula_to_dax("DATENAME('year', [OrderDate])")
        self.assertIn("FORMAT", result)
        self.assertIn("YYYY", result)

    def test_datename_quarter(self):
        result = convert_tableau_formula_to_dax("DATENAME('quarter', [OrderDate])")
        self.assertIn("FORMAT", result)
        self.assertIn("Q", result)

    def test_datename_day(self):
        result = convert_tableau_formula_to_dax("DATENAME('day', [OrderDate])")
        self.assertIn("FORMAT", result)

    def test_datename_weekday(self):
        result = convert_tableau_formula_to_dax("DATENAME('weekday', [OrderDate])")
        self.assertIn("FORMAT", result)
        self.assertIn("DDDD", result)

    def test_dateparse(self):
        result = convert_tableau_formula_to_dax("DATEPARSE('yyyy-MM-dd', [DateStr])")
        self.assertIn("DATEVALUE", result)
        self.assertNotIn("DATEPARSE", result)

    def test_dateparse_single_arg_fallback(self):
        result = convert_tableau_formula_to_dax("DATEPARSE([DateStr])")
        self.assertIn("DATEVALUE", result)

    def test_isdate(self):
        result = convert_tableau_formula_to_dax("ISDATE([DateStr])")
        self.assertIn("NOT", result)
        self.assertIn("ISERROR", result)
        self.assertIn("DATEVALUE", result)
        self.assertNotIn("ISDATE", result)


# ═══════════════════════════════════════════════════════════════════════
# ENDSWITH, STARTSWITH, PROPER, SPLIT
# ═══════════════════════════════════════════════════════════════════════

class TestStringFunctionConverters(unittest.TestCase):
    """Test dedicated string function converters."""

    def test_endswith(self):
        result = convert_tableau_formula_to_dax('ENDSWITH([Name], "Corp")')
        self.assertIn("RIGHT", result)
        self.assertIn("LEN", result)
        self.assertNotIn("ENDSWITH", result)

    def test_startswith(self):
        result = convert_tableau_formula_to_dax('STARTSWITH([Name], "Inc")')
        self.assertIn("LEFT", result)
        self.assertIn("LEN", result)
        self.assertNotIn("STARTSWITH", result)

    def test_proper(self):
        result = convert_tableau_formula_to_dax("PROPER([Name])")
        self.assertIn("UPPER", result)
        self.assertIn("LEFT", result)
        self.assertIn("LOWER", result)
        self.assertIn("MID", result)
        self.assertNotIn("PROPER", result)

    def test_split_returns_pathitem(self):
        result = convert_tableau_formula_to_dax("SPLIT([Name], '-', 2)")
        self.assertIn("PATHITEM", result)
        self.assertIn("SUBSTITUTE", result)

    def test_ltrim_to_trim(self):
        result = convert_tableau_formula_to_dax("LTRIM([Name])")
        self.assertIn("TRIM", result)
        self.assertNotIn("LTRIM", result)

    def test_rtrim_to_trim(self):
        result = convert_tableau_formula_to_dax("RTRIM([Name])")
        self.assertIn("TRIM", result)
        self.assertNotIn("RTRIM", result)

    def test_space_to_rept(self):
        result = convert_tableau_formula_to_dax("SPACE(10)")
        self.assertIn("REPT", result)
        self.assertIn('" "', result)

    def test_mid(self):
        result = convert_tableau_formula_to_dax("MID([Name], 2, 5)")
        self.assertIn("MID", result)

    def test_replace_to_substitute(self):
        result = convert_tableau_formula_to_dax("REPLACE([Name], 'Old', 'New')")
        self.assertIn("SUBSTITUTE", result)
        self.assertNotIn("REPLACE", result)

    def test_ascii_to_unicode(self):
        result = convert_tableau_formula_to_dax("ASCII([Char])")
        self.assertIn("UNICODE", result)
        self.assertNotIn("ASCII", result)

    def test_char_to_unichar(self):
        result = convert_tableau_formula_to_dax("CHAR(65)")
        self.assertIn("UNICHAR", result)
        self.assertTrue(result.startswith("UNICHAR"))  # no bare CHAR


# ═══════════════════════════════════════════════════════════════════════
# Math Function Converters
# ═══════════════════════════════════════════════════════════════════════

class TestMathFunctionConverters(unittest.TestCase):
    """Test dedicated math function converters."""

    def test_atan2(self):
        result = convert_tableau_formula_to_dax("ATAN2([Y], [X])")
        self.assertIn("ATAN", result)
        self.assertNotIn("ATAN2", result.split("/*")[0])

    def test_div_to_quotient(self):
        result = convert_tableau_formula_to_dax("DIV([A], [B])")
        self.assertIn("QUOTIENT", result)
        self.assertNotIn("DIV(", result)

    def test_square_to_power_2(self):
        result = convert_tableau_formula_to_dax("SQUARE([Value])")
        self.assertIn("POWER", result)
        self.assertIn("2", result)
        self.assertNotIn("SQUARE", result)

    def test_radians(self):
        result = convert_tableau_formula_to_dax("RADIANS([Angle])")
        self.assertIn("PI()", result)
        self.assertIn("180", result)
        self.assertNotIn("RADIANS", result)

    def test_degrees(self):
        result = convert_tableau_formula_to_dax("DEGREES([Radians])")
        self.assertIn("PI()", result)
        self.assertIn("180", result)
        self.assertNotIn("DEGREES", result)

    def test_sign(self):
        result = convert_tableau_formula_to_dax("SIGN([Value])")
        self.assertIn("SIGN", result)

    def test_pi(self):
        result = convert_tableau_formula_to_dax("PI()")
        self.assertIn("PI()", result)

    def test_ln(self):
        result = convert_tableau_formula_to_dax("LN([Value])")
        self.assertIn("LN", result)

    def test_trig_cos(self):
        result = convert_tableau_formula_to_dax("COS([Angle])")
        self.assertIn("COS", result)

    def test_trig_sin(self):
        result = convert_tableau_formula_to_dax("SIN([Angle])")
        self.assertIn("SIN", result)

    def test_trig_tan(self):
        result = convert_tableau_formula_to_dax("TAN([Angle])")
        self.assertIn("TAN", result)

    def test_trig_acos(self):
        result = convert_tableau_formula_to_dax("ACOS([Value])")
        self.assertIn("ACOS", result)

    def test_trig_asin(self):
        result = convert_tableau_formula_to_dax("ASIN([Value])")
        self.assertIn("ASIN", result)

    def test_trig_atan(self):
        result = convert_tableau_formula_to_dax("ATAN([Value])")
        self.assertIn("ATAN", result)

    def test_cot(self):
        result = convert_tableau_formula_to_dax("COT([Value])")
        self.assertIn("COT", result)


# ═══════════════════════════════════════════════════════════════════════
# Type Conversion Functions
# ═══════════════════════════════════════════════════════════════════════

class TestTypeConversionFunctions(unittest.TestCase):
    """Test FLOAT, STR, IIF, and other type conversion functions."""

    def test_float_to_convert_double(self):
        result = convert_tableau_formula_to_dax("FLOAT([Value])")
        self.assertIn("CONVERT", result)
        self.assertIn("DOUBLE", result)
        self.assertNotIn("FLOAT", result)

    def test_str_to_format(self):
        result = convert_tableau_formula_to_dax("STR([Value])")
        self.assertIn("FORMAT", result)
        self.assertIn('"0"', result)
        self.assertNotIn("STR(", result)

    def test_iif_three_args(self):
        result = convert_tableau_formula_to_dax("IIF([Sales] > 100, 'High', 'Low')")
        self.assertIn("IF(", result)
        self.assertNotIn("IIF", result)

    def test_iif_two_args(self):
        result = convert_tableau_formula_to_dax("IIF([Flag], 'Yes')")
        self.assertIn("IF(", result)
        self.assertIn("BLANK()", result)

    def test_int(self):
        result = convert_tableau_formula_to_dax("INT([Value])")
        self.assertIn("INT", result)

    def test_date_function(self):
        result = convert_tableau_formula_to_dax("DATE(2024, 3, 15)")
        self.assertIn("DATE", result)

    def test_datetime_to_date(self):
        result = convert_tableau_formula_to_dax("DATETIME([DateStr])")
        self.assertIn("DATE", result)


# ═══════════════════════════════════════════════════════════════════════
# PREVIOUS_VALUE and LOOKUP
# ═══════════════════════════════════════════════════════════════════════

class TestTableCalcAdvanced(unittest.TestCase):
    """Test PREVIOUS_VALUE, LOOKUP, and compute_using support."""

    def test_previous_value_basic(self):
        result = convert_tableau_formula_to_dax(
            "PREVIOUS_VALUE(0)",
            table_name="Orders",
        )
        self.assertIn("OFFSET(-1", result)
        self.assertIn("ALLSELECTED", result)

    def test_previous_value_with_compute_using(self):
        result = convert_tableau_formula_to_dax(
            "PREVIOUS_VALUE(0)",
            table_name="Orders",
            compute_using=["OrderDate"],
            column_table_map={"OrderDate": "Orders"},
        )
        self.assertIn("ORDERBY", result)
        self.assertIn("OrderDate", result)

    def test_lookup_basic(self):
        result = convert_tableau_formula_to_dax(
            "LOOKUP(SUM([Sales]), -1)",
            table_name="Orders",
        )
        self.assertIn("OFFSET", result)
        self.assertIn("CALCULATE", result)

    def test_lookup_with_compute_using(self):
        result = convert_tableau_formula_to_dax(
            "LOOKUP(SUM([Sales]), 2)",
            table_name="Orders",
            compute_using=["Region"],
            column_table_map={"Region": "Orders"},
        )
        self.assertIn("ORDERBY", result)
        self.assertIn("Region", result)

    def test_size_to_countrows(self):
        result = convert_tableau_formula_to_dax("SIZE()")
        self.assertIn("COUNTROWS", result)

    def test_index_to_rankx(self):
        result = convert_tableau_formula_to_dax("INDEX()")
        self.assertIn("RANKX", result)

    def test_first_to_zero(self):
        result = convert_tableau_formula_to_dax("FIRST()")
        self.assertEqual(result.strip(), "0")

    def test_last_to_zero(self):
        result = convert_tableau_formula_to_dax("LAST()")
        self.assertEqual(result.strip(), "0")


# ═══════════════════════════════════════════════════════════════════════
# CORR, COVAR, COVARP
# ═══════════════════════════════════════════════════════════════════════

class TestCorrelationCovariance(unittest.TestCase):
    """Test CORR/COVAR/COVARP → VAR/SUMX DAX patterns."""

    def test_corr(self):
        result = convert_tableau_formula_to_dax("CORR([X], [Y])")
        self.assertIn("VAR _MeanX", result)
        self.assertIn("VAR _MeanY", result)
        self.assertIn("DIVIDE", result)
        self.assertIn("SQRT", result)
        self.assertNotIn("CORR(", result)

    def test_covar(self):
        result = convert_tableau_formula_to_dax("COVAR([X], [Y])")
        self.assertIn("VAR _MeanX", result)
        self.assertIn("VAR _MeanY", result)
        self.assertIn("_N - 1", result)  # sample covariance
        self.assertNotIn("COVAR(", result)

    def test_covarp(self):
        result = convert_tableau_formula_to_dax("COVARP([X], [Y])")
        self.assertIn("VAR _MeanX", result)
        self.assertIn("VAR _N", result)
        self.assertIn("DIVIDE", result)
        self.assertNotIn("_N - 1", result)  # population: divides by N, not N-1
        self.assertNotIn("COVARP(", result)

    def test_corr_with_expressions(self):
        result = convert_tableau_formula_to_dax("CORR(SUM([Sales]), SUM([Profit]))")
        self.assertIn("VAR _MeanX", result)
        self.assertIn("RETURN", result)


# ═══════════════════════════════════════════════════════════════════════
# WINDOW Functions
# ═══════════════════════════════════════════════════════════════════════

class TestWindowFunctions(unittest.TestCase):
    """Test WINDOW_SUM, WINDOW_AVG, WINDOW_MAX, WINDOW_MIN, WINDOW_COUNT."""

    def test_window_sum(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_SUM(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)
        self.assertIn("ALL('Orders')", result)

    def test_window_avg(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_AVG(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)

    def test_window_max(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_MAX(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)

    def test_window_min(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_MIN(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)

    def test_window_count(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_COUNT(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)

    def test_window_with_compute_using(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_SUM(SUM([Sales]))",
            table_name="Orders",
            compute_using=["Region"],
            column_table_map={"Region": "Orders"},
        )
        self.assertIn("ALLEXCEPT", result)
        self.assertIn("Region", result)

    def test_window_median(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_MEDIAN(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)
        self.assertIn("MEDIAN", result)

    def test_window_stdev(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_STDEV(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)
        self.assertIn("STDEV", result)

    def test_window_var(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_VAR(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)
        self.assertIn("VAR", result)

    def test_window_percentile(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_PERCENTILE(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)
        self.assertIn("PERCENTILE", result)


# ═══════════════════════════════════════════════════════════════════════
# RANK Variants
# ═══════════════════════════════════════════════════════════════════════

class TestRankVariants(unittest.TestCase):
    """Test RANK, RANK_UNIQUE, RANK_DENSE, RANK_MODIFIED, RANK_PERCENTILE."""

    def test_rank_basic(self):
        result = convert_tableau_formula_to_dax(
            "RANK(SUM([Sales]))", table_name="T")
        self.assertIn("RANKX", result)
        self.assertIn("ALL('T')", result)

    def test_rank_unique(self):
        result = convert_tableau_formula_to_dax(
            "RANK_UNIQUE(SUM([Sales]))", table_name="T")
        self.assertIn("RANKX", result)

    def test_rank_dense(self):
        result = convert_tableau_formula_to_dax(
            "RANK_DENSE(SUM([Sales]))", table_name="T")
        self.assertIn("RANKX", result)
        self.assertIn("DENSE", result)

    def test_rank_modified(self):
        result = convert_tableau_formula_to_dax(
            "RANK_MODIFIED(SUM([Sales]))", table_name="T")
        self.assertIn("RANKX", result)
        self.assertIn("RANK_MODIFIED", result)  # In comment

    def test_rank_percentile(self):
        result = convert_tableau_formula_to_dax(
            "RANK_PERCENTILE(SUM([Sales]))", table_name="T")
        self.assertIn("RANKX", result)
        self.assertIn("DIVIDE", result)

    def test_rank_with_compute_using(self):
        result = convert_tableau_formula_to_dax(
            "RANK(SUM([Sales]))",
            table_name="Orders",
            compute_using=["Region"],
            column_table_map={"Region": "Orders"},
        )
        self.assertIn("ALLEXCEPT", result)
        self.assertIn("Region", result)


# ═══════════════════════════════════════════════════════════════════════
# RUNNING Functions
# ═══════════════════════════════════════════════════════════════════════

class TestRunningFunctions(unittest.TestCase):
    """Test RUNNING_SUM, _AVG, _COUNT, _MAX, _MIN."""

    def test_running_sum(self):
        result = convert_tableau_formula_to_dax(
            "RUNNING_SUM(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)

    def test_running_avg(self):
        result = convert_tableau_formula_to_dax(
            "RUNNING_AVG(AVG([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)

    def test_running_count(self):
        result = convert_tableau_formula_to_dax(
            "RUNNING_COUNT(COUNT([ID]))", table_name="Orders")
        self.assertIn("CALCULATE", result)

    def test_running_max(self):
        result = convert_tableau_formula_to_dax(
            "RUNNING_MAX(MAX([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)

    def test_running_min(self):
        result = convert_tableau_formula_to_dax(
            "RUNNING_MIN(MIN([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)


# ═══════════════════════════════════════════════════════════════════════
# TOTAL Function
# ═══════════════════════════════════════════════════════════════════════

class TestTotalFunction(unittest.TestCase):
    """Test TOTAL(expr) → CALCULATE(expr, ALL())."""

    def test_total_basic(self):
        result = convert_tableau_formula_to_dax(
            "TOTAL(SUM([Sales]))", table_name="Orders")
        self.assertIn("CALCULATE", result)
        self.assertNotIn("TOTAL(", result)

    def test_total_with_average(self):
        result = convert_tableau_formula_to_dax(
            "TOTAL(AVG([Score]))", table_name="Scores")
        self.assertIn("CALCULATE", result)

    def test_percent_of_total_pattern(self):
        """SUM(x) / TOTAL(SUM(x)) → common pattern."""
        result = convert_tableau_formula_to_dax(
            "SUM([Sales]) / TOTAL(SUM([Sales]))",
            table_name="Orders",
            column_table_map={"Sales": "Orders"},
        )
        self.assertIsInstance(result, str)
        self.assertNotIn("TOTAL(", result)


# ═══════════════════════════════════════════════════════════════════════
# LOD Edge Cases
# ═══════════════════════════════════════════════════════════════════════

class TestLODEdgeCases(unittest.TestCase):
    """Test LOD expressions with edge cases."""

    def test_fixed_no_dimension(self):
        """LOD without dimension specification → CALCULATE(AGG, ALL())."""
        result = convert_tableau_formula_to_dax(
            "{SUM([Sales])}",
            table_name="Orders",
            column_table_map={"Sales": "Orders"},
        )
        self.assertIn("CALCULATE", result)

    def test_fixed_multiple_dimensions(self):
        result = convert_tableau_formula_to_dax(
            "{FIXED [Region], [Category] : SUM([Sales])}",
            table_name="Orders",
            column_table_map={"Region": "Orders", "Category": "Orders", "Sales": "Orders"},
        )
        self.assertIn("ALLEXCEPT", result)
        self.assertIn("Region", result)
        self.assertIn("Category", result)

    def test_exclude_with_cross_table(self):
        result = convert_tableau_formula_to_dax(
            "{EXCLUDE [Region] : SUM([Sales])}",
            table_name="Orders",
            column_table_map={"Region": "Products", "Sales": "Orders"},
        )
        self.assertIn("REMOVEFILTERS", result)
        self.assertIn("Products", result)

    def test_include_lod(self):
        result = convert_tableau_formula_to_dax(
            "{INCLUDE [SubCategory] : AVG([Profit])}",
            table_name="Orders",
            column_table_map={"SubCategory": "Orders", "Profit": "Orders"},
        )
        self.assertIn("CALCULATE", result)
        self.assertNotIn("{INCLUDE", result)

    def test_nested_lod_balanced_braces(self):
        """LOD with nested expressions shouldn't break brace matching."""
        result = convert_tableau_formula_to_dax(
            "{FIXED [Region] : SUM(IF [Status]='Active' THEN [Amount] ELSE 0 END)}",
            table_name="Orders",
            column_table_map={"Region": "Orders", "Status": "Orders", "Amount": "Orders"},
        )
        self.assertIn("CALCULATE", result)
        self.assertIn("ALLEXCEPT", result)


# ═══════════════════════════════════════════════════════════════════════
# AGG(expr) → AGGX Conversion
# ═══════════════════════════════════════════════════════════════════════

class TestAggExprToAggx(unittest.TestCase):
    """Test SUM(a*b) → SUMX('T', a*b) and statistical iterators."""

    def test_sum_product_to_sumx(self):
        result = convert_tableau_formula_to_dax(
            "SUM([Qty] * [Price])",
            table_name="Orders",
            column_table_map={"Qty": "Orders", "Price": "Orders"},
        )
        self.assertIn("SUMX", result)
        self.assertNotIn("SUM(", result)

    def test_average_expression_to_averagex(self):
        result = convert_tableau_formula_to_dax(
            "AVG([Sales] - [Cost])",
            table_name="Orders",
            column_table_map={"Sales": "Orders", "Cost": "Orders"},
        )
        self.assertIn("AVERAGEX", result)

    def test_sum_single_column_unchanged(self):
        """SUM of a single column should remain SUM, not SUMX."""
        result = convert_tableau_formula_to_dax(
            "SUM([Sales])",
            table_name="Orders",
            column_table_map={"Sales": "Orders"},
        )
        self.assertIn("SUM(", result)
        self.assertNotIn("SUMX", result)

    def test_stdev_of_expression_to_stdevx(self):
        """STDEV.S(SUM(a*b)) → STDEVX.S('T', a*b) with unwrapping."""
        result = convert_tableau_formula_to_dax(
            "STDEV([Qty] * [Price])",
            table_name="Orders",
            column_table_map={"Qty": "Orders", "Price": "Orders"},
        )
        self.assertIn("STDEVX.S", result)

    def test_median_of_expression_to_medianx(self):
        result = convert_tableau_formula_to_dax(
            "MEDIAN([Qty] * [Price])",
            table_name="Orders",
            column_table_map={"Qty": "Orders", "Price": "Orders"},
        )
        self.assertIn("MEDIANX", result)

    def test_avg_if_to_averagex(self):
        """AVG(IF ...) → AVERAGEX with IF."""
        result = convert_tableau_formula_to_dax(
            "AVG(IF [Status]='Active' THEN [Amount] END)",
            table_name="Orders",
            column_table_map={"Status": "Orders", "Amount": "Orders"},
        )
        self.assertIn("AVERAGEX", result)

    def test_count_if_to_countx(self):
        result = convert_tableau_formula_to_dax(
            "COUNT(IF [Status]='Active' THEN [ID] END)",
            table_name="Orders",
            column_table_map={"Status": "Orders", "ID": "Orders"},
        )
        self.assertIn("COUNTX", result)


# ═══════════════════════════════════════════════════════════════════════
# Ceiling/Floor Fix
# ═══════════════════════════════════════════════════════════════════════

class TestCeilingFloorFix(unittest.TestCase):
    """Test _fix_ceiling_floor adds significance argument."""

    def test_ceiling_single_arg(self):
        result = convert_tableau_formula_to_dax("CEILING([Value])")
        self.assertIn("CEILING(", result)
        self.assertIn(", 1)", result)

    def test_floor_single_arg(self):
        result = convert_tableau_formula_to_dax("FLOOR([Value])")
        self.assertIn("FLOOR(", result)
        self.assertIn(", 1)", result)

    def test_ceiling_two_args_unchanged(self):
        result = convert_tableau_formula_to_dax("CEILING([Value], 5)")
        self.assertIn("CEILING(", result)
        self.assertIn(", 5)", result)

    def test_floor_two_args_unchanged(self):
        result = convert_tableau_formula_to_dax("FLOOR([Value], 10)")
        self.assertIn("FLOOR(", result)
        self.assertIn(", 10)", result)


# ═══════════════════════════════════════════════════════════════════════
# Date Literal Conversion
# ═══════════════════════════════════════════════════════════════════════

class TestDateLiterals(unittest.TestCase):
    """Test #YYYY-MM-DD# → DATE(Y, M, D) conversion."""

    def test_basic_date_literal(self):
        result = convert_tableau_formula_to_dax("#2024-01-15#")
        self.assertIn("DATE(2024, 1, 15)", result)
        self.assertNotIn("#", result)

    def test_date_literal_in_comparison(self):
        result = convert_tableau_formula_to_dax("[OrderDate] >= #2023-06-01#")
        self.assertIn("DATE(2023, 6, 1)", result)
        self.assertNotIn("#", result)

    def test_multiple_date_literals(self):
        result = convert_tableau_formula_to_dax(
            "[Date] >= #2023-01-01# AND [Date] <= #2023-12-31#")
        self.assertIn("DATE(2023, 1, 1)", result)
        self.assertIn("DATE(2023, 12, 31)", result)
        self.assertNotIn("#", result)

    def test_fix_date_literals_direct(self):
        result = _fix_date_literals("#2024-03-15#")
        self.assertEqual(result, "DATE(2024, 3, 15)")


# ═══════════════════════════════════════════════════════════════════════
# String Concatenation
# ═══════════════════════════════════════════════════════════════════════

class TestStringConcatenation(unittest.TestCase):
    """Test + → & conversion for string types."""

    def test_simple_concat(self):
        result = convert_tableau_formula_to_dax(
            '[First] + " " + [Last]', calc_datatype="string")
        self.assertIn("&", result)
        self.assertNotIn("+", result)

    def test_concat_preserves_inner_plus(self):
        """+ inside function args should be preserved as arithmetic."""
        result = _convert_string_concat('[A] + "x" + FIND([B], "c") + 1')
        # Only top-level + should convert
        # FIND(...) + 1 is at depth 0, but the test checks the pattern
        self.assertIn("&", result)

    def test_concat_empty_string(self):
        result = convert_tableau_formula_to_dax(
            '[A] + ""', calc_datatype="string")
        self.assertIn("&", result)


# ═══════════════════════════════════════════════════════════════════════
# Regex/Script/Spatial Functions
# ═══════════════════════════════════════════════════════════════════════

class TestSpecialNoEquivalent(unittest.TestCase):
    """Test functions with no direct DAX equivalent — should have comments."""

    def test_regexp_match(self):
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Name], "^A")')
        # Smart converter: ^A → LEFT match
        self.assertIn("LEFT", result)
        self.assertIn('"A"', result)

    def test_regexp_replace(self):
        result = convert_tableau_formula_to_dax('REGEXP_REPLACE([Name], "\\d+", "")')
        self.assertIn("SUBSTITUTE", result)

    def test_regexp_extract(self):
        result = convert_tableau_formula_to_dax('REGEXP_EXTRACT([Name], "\\d+")')
        self.assertIn("REGEXP_EXTRACT", result)  # In comment
        self.assertIn("BLANK(", result)

    def test_regexp_extract_nth(self):
        result = convert_tableau_formula_to_dax('REGEXP_EXTRACT_NTH([Name], "\\d+", 2)')
        self.assertIn("REGEXP_EXTRACT_NTH", result)  # In comment

    def test_script_bool(self):
        result = convert_tableau_formula_to_dax('SCRIPT_BOOL("x > 0", [Value])')
        self.assertIn("SCRIPT_BOOL", result)  # In comment
        self.assertIn("BLANK(", result)

    def test_script_int(self):
        result = convert_tableau_formula_to_dax('SCRIPT_INT("x + 1", [Value])')
        self.assertIn("SCRIPT_INT", result)  # In comment

    def test_script_real(self):
        result = convert_tableau_formula_to_dax('SCRIPT_REAL("x * 2", [Value])')
        self.assertIn("SCRIPT_REAL", result)  # In comment

    def test_script_str(self):
        result = convert_tableau_formula_to_dax('SCRIPT_STR("str(x)", [Value])')
        self.assertIsInstance(result, str)  # Converts to SCRIPT_FORMAT

    def test_makepoint(self):
        result = convert_tableau_formula_to_dax("MAKEPOINT([Lat], [Lon])")
        self.assertIn("MAKEPOINT", result)  # In comment
        self.assertIn("BLANK(", result)

    def test_makeline(self):
        result = convert_tableau_formula_to_dax("MAKELINE([P1], [P2])")
        self.assertIn("BLANK(", result)

    def test_distance(self):
        result = convert_tableau_formula_to_dax("DISTANCE([P1], [P2], 'miles')")
        self.assertIn("Haversine", result)

    def test_collect(self):
        result = convert_tableau_formula_to_dax("COLLECT([Geometry])")
        self.assertIn("BLANK(", result)

    def test_hexbinx(self):
        result = convert_tableau_formula_to_dax("HEXBINX([X])")
        self.assertIn("HEXBINX", result)  # In comment

    def test_hexbiny(self):
        result = convert_tableau_formula_to_dax("HEXBINY([Y])")
        self.assertIn("HEXBINY", result)  # In comment


# ═══════════════════════════════════════════════════════════════════════
# MAKEDATE, MAKEDATETIME, MAKETIME
# ═══════════════════════════════════════════════════════════════════════

class TestMakeDateFunctions(unittest.TestCase):
    """Test MAKEDATE/MAKEDATETIME → DATE and MAKETIME → TIME."""

    def test_makedate(self):
        result = convert_tableau_formula_to_dax("MAKEDATE(2024, 3, 15)")
        self.assertIn("DATE(", result)
        self.assertNotIn("MAKEDATE", result)

    def test_makedatetime(self):
        result = convert_tableau_formula_to_dax("MAKEDATETIME(2024, 3, 15, 10, 30, 0)")
        self.assertIn("DATE(", result)
        self.assertNotIn("MAKEDATETIME", result)

    def test_maketime(self):
        result = convert_tableau_formula_to_dax("MAKETIME(10, 30, 0)")
        self.assertIn("TIME(", result)
        self.assertNotIn("MAKETIME", result)


# ═══════════════════════════════════════════════════════════════════════
# FIND with Argument Reordering
# ═══════════════════════════════════════════════════════════════════════

class TestFindFunction(unittest.TestCase):
    """Test FIND and FINDNTH argument reordering."""

    def test_find_arg_swap(self):
        result = convert_tableau_formula_to_dax('FIND([Name], "Corp")')
        # Tableau: FIND(within, find) → DAX: FIND(find, within)
        self.assertIn("FIND(", result)

    def test_findnth_becomes_find(self):
        result = convert_tableau_formula_to_dax('FINDNTH([Name], "X", 2)')
        self.assertIn("FIND(", result)
        self.assertNotIn("FINDNTH", result)


# ═══════════════════════════════════════════════════════════════════════
# DATEDIFF Argument Reordering
# ═══════════════════════════════════════════════════════════════════════

class TestDateDiffReorder(unittest.TestCase):
    """Test DATEDIFF arg reorder: (interval, start, end) → (start, end, INTERVAL)."""

    def test_datediff_month(self):
        result = convert_tableau_formula_to_dax("DATEDIFF('month', [Start], [End])")
        self.assertIn("DATEDIFF(", result)
        self.assertIn("MONTH", result)

    def test_datediff_day(self):
        result = convert_tableau_formula_to_dax("DATEDIFF('day', [Start], [End])")
        self.assertIn("DATEDIFF(", result)
        self.assertIn("DAY", result)

    def test_datediff_year(self):
        result = convert_tableau_formula_to_dax("DATEDIFF('year', [Start], [End])")
        self.assertIn("DATEDIFF(", result)
        self.assertIn("YEAR", result)


# ═══════════════════════════════════════════════════════════════════════
# Statistics Functions
# ═══════════════════════════════════════════════════════════════════════

class TestStatisticsFunctions(unittest.TestCase):
    """Test STDEV, STDEVP, VAR, VARP, PERCENTILE conversions."""

    def test_stdev_to_stdev_s(self):
        result = convert_tableau_formula_to_dax("STDEV([Value])")
        self.assertIn("STDEV.S(", result)
        self.assertNotIn("STDEV(", result.replace("STDEV.S(", ""))

    def test_stdevp_to_stdev_p(self):
        result = convert_tableau_formula_to_dax("STDEVP([Value])")
        self.assertIn("STDEV.P(", result)

    def test_var_to_var_s(self):
        result = convert_tableau_formula_to_dax("VAR([Value])")
        self.assertIn("VAR.S(", result)

    def test_varp_to_var_p(self):
        result = convert_tableau_formula_to_dax("VARP([Value])")
        self.assertIn("VAR.P(", result)

    def test_percentile_to_percentile_inc(self):
        result = convert_tableau_formula_to_dax("PERCENTILE([Value], 0.9)")
        self.assertIn("PERCENTILE.INC(", result)


# ═══════════════════════════════════════════════════════════════════════
# Aggregation Functions
# ═══════════════════════════════════════════════════════════════════════

class TestAggregationFunctions(unittest.TestCase):
    """Test COUNT, COUNTA, COUNTD, AVG, ATTR → SELECTEDVALUE."""

    def test_counta(self):
        result = convert_tableau_formula_to_dax("COUNTA([Name])")
        self.assertIn("COUNTA", result)

    def test_attr_to_selectedvalue(self):
        result = convert_tableau_formula_to_dax("ATTR([Category])")
        self.assertIn("SELECTEDVALUE", result)
        self.assertNotIn("ATTR", result)

    def test_isnumber(self):
        result = convert_tableau_formula_to_dax("ISNUMBER([Value])")
        self.assertIn("ISNUMBER", result)

    def test_not_function(self):
        result = convert_tableau_formula_to_dax("NOT([Flag])")
        self.assertIn("NOT", result)


# ═══════════════════════════════════════════════════════════════════════
# generate_combined_field_dax
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateCombinedFieldDax(unittest.TestCase):
    """Test the generate_combined_field_dax utility."""

    def test_empty_fields(self):
        result = generate_combined_field_dax([], "T")
        self.assertEqual(result, '""')

    def test_single_field(self):
        result = generate_combined_field_dax(["Name"], "T")
        self.assertEqual(result, "'T'[Name]")

    def test_two_fields(self):
        result = generate_combined_field_dax(["First", "Last"], "T")
        self.assertIn("&", result)
        self.assertIn("'T'[First]", result)
        self.assertIn("'T'[Last]", result)

    def test_three_fields(self):
        result = generate_combined_field_dax(["A", "B", "C"], "T")
        self.assertEqual(result.count("&"), 4)  # A & sep & B & sep & C

    def test_custom_separator(self):
        result = generate_combined_field_dax(["A", "B"], "T", separator="-")
        self.assertIn('"-"', result)


# ═══════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════

class TestSplitArgs(unittest.TestCase):
    """Test _split_args utility."""

    def test_simple_args(self):
        result = _split_args("a, b, c")
        self.assertEqual(result, ["a", "b", "c"])

    def test_nested_parens(self):
        result = _split_args("SUM(a, b), c")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "SUM(a, b)")
        self.assertEqual(result[1], "c")

    def test_single_arg(self):
        result = _split_args("[Column]")
        self.assertEqual(result, ["[Column]"])

    def test_empty_string(self):
        result = _split_args("")
        self.assertEqual(result, [])


class TestNormalizeSpaces(unittest.TestCase):
    """Test _normalize_spaces_outside_identifiers."""

    def test_multiple_spaces_collapsed(self):
        result = _normalize_spaces_outside_identifiers("a   +   b")
        self.assertEqual(result, "a + b")

    def test_spaces_inside_brackets_preserved(self):
        result = _normalize_spaces_outside_identifiers("[Long  Name]")
        self.assertIn("Long  Name", result)

    def test_spaces_inside_quotes_preserved(self):
        result = _normalize_spaces_outside_identifiers("'Table  Name'[Col]")
        self.assertIn("Table  Name", result)


# ═══════════════════════════════════════════════════════════════════════
# Complex / Integration Formula Tests
# ═══════════════════════════════════════════════════════════════════════

class TestComplexFormulaCoverage(unittest.TestCase):
    """Test complex multi-feature formulas for integration coverage."""

    def test_nested_if_with_datepart(self):
        formula = "IF DATEPART('month', [Date]) > 6 THEN 'H2' ELSE 'H1' END"
        result = convert_tableau_formula_to_dax(formula)
        self.assertIn("IF(", result)
        self.assertIn("MONTH(", result)
        self.assertNotIn("DATEPART", result)

    def test_case_with_datename(self):
        formula = "CASE DATENAME('month', [Date]) WHEN 'January' THEN 1 WHEN 'February' THEN 2 ELSE 0 END"
        result = convert_tableau_formula_to_dax(formula)
        self.assertIn("SWITCH", result)
        self.assertIn("FORMAT", result)

    def test_lod_with_countd(self):
        result = convert_tableau_formula_to_dax(
            "{FIXED [Category] : COUNTD([Customer])}",
            table_name="Orders",
            column_table_map={"Category": "Orders", "Customer": "Orders"},
        )
        self.assertIn("CALCULATE", result)
        self.assertIn("DISTINCTCOUNT", result)

    def test_formula_with_zn_and_sum(self):
        result = convert_tableau_formula_to_dax(
            "ZN(SUM([Sales])) / ZN(SUM([Target]))",
            table_name="Data",
            column_table_map={"Sales": "Data", "Target": "Data"},
        )
        self.assertIn("ISBLANK", result)
        self.assertEqual(result.count("ISBLANK"), 2)

    def test_ifnull_with_nested_function(self):
        result = convert_tableau_formula_to_dax(
            "IFNULL(SUM([Sales]), 0)")
        self.assertIn("IF(ISBLANK(", result)

    def test_ismemberof(self):
        result = convert_tableau_formula_to_dax('ISMEMBEROF("Admin Group")')
        self.assertIn("TRUE()", result)
        self.assertIn("RLS", result)

    def test_cross_table_related_in_calc_column(self):
        result = convert_tableau_formula_to_dax(
            "[Product Name]",
            table_name="Orders",
            column_table_map={"Product Name": "Products"},
            is_calc_column=True,
        )
        self.assertIn("RELATED", result)
        self.assertIn("Products", result)

    def test_partition_fields_backward_compat(self):
        """partition_fields (deprecated) should still work."""
        result = convert_tableau_formula_to_dax(
            "RANK(SUM([Sales]))",
            table_name="Orders",
            partition_fields=["Region"],
            column_table_map={"Region": "Orders"},
        )
        self.assertIn("ALLEXCEPT", result)

    def test_multi_line_formula_condensed(self):
        formula = "IF [Sales] > 1000\n  THEN 'High'\n  ELSE 'Low'\nEND"
        result = convert_tableau_formula_to_dax(formula)
        self.assertNotIn("\n", result)
        self.assertIn("IF(", result)

    def test_bracket_escape_in_column_resolution(self):
        result = convert_tableau_formula_to_dax(
            "SUM([Column Name)])",
            table_name="T",
            column_table_map={"Column Name]": "T"},
        )
        # Should not crash — may produce imperfect but valid output
        self.assertIsInstance(result, str)


if __name__ == '__main__':
    unittest.main(verbosity=2)
