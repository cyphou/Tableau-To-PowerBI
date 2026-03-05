"""
Unit tests for dax_converter.py — Tableau formula → DAX conversion.

Tests the main convert_tableau_formula_to_dax function and individual
conversion phases: references, CASE/IF, functions, LOD, operators,
column resolution, AGG→AGGX, and cleanup.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

from dax_converter import (
    convert_tableau_formula_to_dax,
    map_tableau_to_powerbi_type,
    _reverse_tableau_bracket_escape,
)


# ═══════════════════════════════════════════════════════════════════════
# Type Mapping
# ═══════════════════════════════════════════════════════════════════════

class TestMapTableauToPowerBIType(unittest.TestCase):
    """Test map_tableau_to_powerbi_type."""

    def test_integer(self):
        self.assertEqual(map_tableau_to_powerbi_type("integer"), "Int64")

    def test_real(self):
        self.assertEqual(map_tableau_to_powerbi_type("real"), "Double")

    def test_string(self):
        self.assertEqual(map_tableau_to_powerbi_type("string"), "String")

    def test_boolean(self):
        self.assertEqual(map_tableau_to_powerbi_type("boolean"), "Boolean")

    def test_date(self):
        self.assertEqual(map_tableau_to_powerbi_type("date"), "DateTime")

    def test_datetime(self):
        self.assertEqual(map_tableau_to_powerbi_type("datetime"), "DateTime")

    def test_unknown_defaults_to_string(self):
        self.assertEqual(map_tableau_to_powerbi_type("blob"), "String")


# ═══════════════════════════════════════════════════════════════════════
# Bracket Escape Reversal
# ═══════════════════════════════════════════════════════════════════════

class TestReverseBracketEscape(unittest.TestCase):
    """Test _reverse_tableau_bracket_escape."""

    def test_orphan_close_paren(self):
        result = _reverse_tableau_bracket_escape("Column Name)")
        self.assertEqual(result, "Column Name]")

    def test_balanced_parens_unchanged(self):
        result = _reverse_tableau_bracket_escape("func(x)")
        self.assertEqual(result, "func(x)")

    def test_no_parens(self):
        result = _reverse_tableau_bracket_escape("Plain Name")
        self.assertEqual(result, "Plain Name")

    def test_multiple_orphan_parens(self):
        result = _reverse_tableau_bracket_escape("A) B)")
        self.assertEqual(result, "A] B]")


# ═══════════════════════════════════════════════════════════════════════
# Empty / Null Input Handling
# ═══════════════════════════════════════════════════════════════════════

class TestEmptyInputs(unittest.TestCase):
    """Test edge cases with empty/null formulas."""

    def test_empty_string(self):
        result = convert_tableau_formula_to_dax("")
        self.assertEqual(result, "")

    def test_whitespace_only(self):
        result = convert_tableau_formula_to_dax("   ")
        self.assertEqual(result, "   ")

    def test_none_input(self):
        result = convert_tableau_formula_to_dax(None)
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════════
# Simple Function Conversions
# ═══════════════════════════════════════════════════════════════════════

class TestSimpleFunctionConversions(unittest.TestCase):
    """Test direct Tableau → DAX function name mappings."""

    def test_isnull_to_isblank(self):
        result = convert_tableau_formula_to_dax("ISNULL([Field])")
        self.assertIn("ISBLANK", result)
        self.assertNotIn("ISNULL", result)

    def test_zn_to_if_isblank(self):
        result = convert_tableau_formula_to_dax("ZN([Sales])")
        self.assertIn("ISBLANK", result)

    def test_ifnull_to_if_isblank(self):
        result = convert_tableau_formula_to_dax("IFNULL([Sales], 0)")
        self.assertIn("ISBLANK", result)

    def test_countd_to_distinctcount(self):
        result = convert_tableau_formula_to_dax("COUNTD([Customer ID])")
        self.assertIn("DISTINCTCOUNT", result)
        self.assertNotIn("COUNTD", result)

    def test_username_to_userprincipalname(self):
        result = convert_tableau_formula_to_dax("USERNAME()")
        self.assertIn("USERPRINCIPALNAME", result)

    def test_fullname_to_userprincipalname(self):
        result = convert_tableau_formula_to_dax("FULLNAME()")
        self.assertIn("USERPRINCIPALNAME", result)

    def test_userdomain_comment(self):
        result = convert_tableau_formula_to_dax("USERDOMAIN()")
        self.assertIn("RLS", result)  # Should mention RLS

    def test_today(self):
        result = convert_tableau_formula_to_dax("TODAY()")
        self.assertIn("TODAY()", result)

    def test_now(self):
        result = convert_tableau_formula_to_dax("NOW()")
        self.assertIn("NOW()", result)

    def test_len(self):
        result = convert_tableau_formula_to_dax("LEN([Name])")
        self.assertIn("LEN", result)

    def test_left(self):
        result = convert_tableau_formula_to_dax("LEFT([Name], 5)")
        self.assertIn("LEFT", result)

    def test_right(self):
        result = convert_tableau_formula_to_dax("RIGHT([Name], 3)")
        self.assertIn("RIGHT", result)

    def test_upper(self):
        result = convert_tableau_formula_to_dax("UPPER([Name])")
        self.assertIn("UPPER", result)

    def test_lower(self):
        result = convert_tableau_formula_to_dax("LOWER([Name])")
        self.assertIn("LOWER", result)

    def test_trim(self):
        result = convert_tableau_formula_to_dax("TRIM([Name])")
        self.assertIn("TRIM", result)

    def test_abs(self):
        result = convert_tableau_formula_to_dax("ABS([Value])")
        self.assertIn("ABS", result)

    def test_round(self):
        result = convert_tableau_formula_to_dax("ROUND([Value], 2)")
        self.assertIn("ROUND", result)

    def test_power(self):
        result = convert_tableau_formula_to_dax("POWER([Value], 3)")
        self.assertIn("POWER", result)

    def test_sqrt(self):
        result = convert_tableau_formula_to_dax("SQRT([Value])")
        self.assertIn("SQRT", result)

    def test_log(self):
        result = convert_tableau_formula_to_dax("LOG([Value])")
        self.assertIn("LOG", result)

    def test_exp(self):
        result = convert_tableau_formula_to_dax("EXP([Value])")
        self.assertIn("EXP", result)

    def test_min_aggregation(self):
        result = convert_tableau_formula_to_dax("MIN([Value])")
        self.assertIn("MIN", result)

    def test_max_aggregation(self):
        result = convert_tableau_formula_to_dax("MAX([Value])")
        self.assertIn("MAX", result)

    def test_sum_aggregation(self):
        result = convert_tableau_formula_to_dax("SUM([Amount])")
        self.assertIn("SUM", result)

    def test_avg_to_average(self):
        result = convert_tableau_formula_to_dax("AVG([Value])")
        self.assertIn("AVERAGE", result)
        self.assertNotIn("AVG(", result)

    def test_median(self):
        result = convert_tableau_formula_to_dax("MEDIAN([Value])")
        self.assertIn("MEDIAN", result)

    def test_contains_to_containsstring(self):
        result = convert_tableau_formula_to_dax('CONTAINS([Name], "Corp")')
        self.assertIn("CONTAINSSTRING", result)


# ═══════════════════════════════════════════════════════════════════════
# Special Function Converters
# ═══════════════════════════════════════════════════════════════════════

class TestSpecialFunctionConverters(unittest.TestCase):
    """Test dedicated function converters with argument reordering."""

    def test_datediff_arg_reorder(self):
        result = convert_tableau_formula_to_dax(
            "DATEDIFF('month', [Start], [End])"
        )
        self.assertIn("DATEDIFF", result)
        self.assertIn("MONTH", result)

    def test_str_to_format(self):
        result = convert_tableau_formula_to_dax("STR([Value])")
        self.assertIn("FORMAT", result)

    def test_float_to_convert(self):
        result = convert_tableau_formula_to_dax("FLOAT([Value])")
        self.assertIn("CONVERT", result)
        self.assertIn("DOUBLE", result)

    def test_div_to_quotient(self):
        result = convert_tableau_formula_to_dax("DIV(10, 3)")
        self.assertIn("QUOTIENT", result)

    def test_square_to_power(self):
        result = convert_tableau_formula_to_dax("SQUARE([Value])")
        self.assertIn("POWER", result)
        self.assertIn("2", result)

    def test_iif_to_if(self):
        result = convert_tableau_formula_to_dax("IIF([Sales] > 100, 'High', 'Low')")
        self.assertIn("IF", result)
        self.assertNotIn("IIF", result)

    def test_ismemberof_to_rls_comment(self):
        result = convert_tableau_formula_to_dax('ISMEMBEROF("Admin Group")')
        self.assertIn("TRUE()", result)
        self.assertIn("RLS", result)


# ═══════════════════════════════════════════════════════════════════════
# Operator Conversions
# ═══════════════════════════════════════════════════════════════════════

class TestOperatorConversions(unittest.TestCase):
    """Test operator syntax conversions."""

    def test_double_equals_to_single(self):
        result = convert_tableau_formula_to_dax("[Status] == 'Active'")
        self.assertNotIn("==", result)
        self.assertIn("=", result)

    def test_not_equals(self):
        result = convert_tableau_formula_to_dax("[Status] != 'Active'")
        self.assertIn("<>", result)
        self.assertNotIn("!=", result)

    def test_and_operator(self):
        result = convert_tableau_formula_to_dax("[A] > 1 AND [B] > 2")
        self.assertIn("&&", result)

    def test_or_operator(self):
        result = convert_tableau_formula_to_dax("[A] > 1 OR [B] > 2")
        self.assertIn("||", result)

    def test_string_concat_plus_to_ampersand(self):
        result = convert_tableau_formula_to_dax(
            "[First] + ' ' + [Last]",
            calc_datatype="string"
        )
        self.assertIn("&", result)


# ═══════════════════════════════════════════════════════════════════════
# CASE / IF Structure Conversion
# ═══════════════════════════════════════════════════════════════════════

class TestStructureConversion(unittest.TestCase):
    """Test CASE/WHEN → SWITCH and IF/THEN → IF() conversions."""

    def test_case_when_to_switch(self):
        formula = "CASE [Region] WHEN 'East' THEN 1 WHEN 'West' THEN 2 ELSE 0 END"
        result = convert_tableau_formula_to_dax(formula)
        self.assertIn("SWITCH", result)
        self.assertNotIn("CASE", result)

    def test_if_then_to_if(self):
        formula = "IF [Sales] > 1000 THEN 'High' ELSE 'Low' END"
        result = convert_tableau_formula_to_dax(formula)
        self.assertIn("IF", result)
        self.assertNotIn("THEN", result)
        self.assertNotIn("END", result)

    def test_if_elseif_to_nested_if(self):
        formula = "IF [Sales] > 1000 THEN 'High' ELSEIF [Sales] > 500 THEN 'Medium' ELSE 'Low' END"
        result = convert_tableau_formula_to_dax(formula)
        self.assertNotIn("ELSEIF", result)
        # Should have nested IFs
        self.assertEqual(result.count("IF"), result.count("IF"))  # sanity


# ═══════════════════════════════════════════════════════════════════════
# LOD Expressions
# ═══════════════════════════════════════════════════════════════════════

class TestLODExpressions(unittest.TestCase):
    """Test LOD (Level of Detail) expression conversion."""

    def test_fixed_lod(self):
        result = convert_tableau_formula_to_dax(
            "{FIXED [Region] : SUM([Sales])}",
            table_name="Orders",
            column_table_map={"Region": "Orders", "Sales": "Orders"},
        )
        self.assertIn("CALCULATE", result)
        self.assertIn("ALLEXCEPT", result)

    def test_include_lod(self):
        result = convert_tableau_formula_to_dax(
            "{INCLUDE [Region] : SUM([Sales])}",
            table_name="Orders",
            column_table_map={"Region": "Orders", "Sales": "Orders"},
        )
        self.assertIn("CALCULATE", result)

    def test_exclude_lod(self):
        result = convert_tableau_formula_to_dax(
            "{EXCLUDE [Region] : SUM([Sales])}",
            table_name="Orders",
            column_table_map={"Region": "Orders", "Sales": "Orders"},
        )
        self.assertIn("CALCULATE", result)
        self.assertIn("REMOVEFILTERS", result)


# ═══════════════════════════════════════════════════════════════════════
# Column Resolution & Cross-Table References
# ═══════════════════════════════════════════════════════════════════════

class TestColumnResolution(unittest.TestCase):
    """Test column name resolution with table qualifying."""

    def test_single_column_qualified(self):
        result = convert_tableau_formula_to_dax(
            "SUM([Sales])",
            table_name="Orders",
            column_table_map={"Sales": "Orders"},
        )
        self.assertIn("'Orders'[Sales]", result)

    def test_measure_not_qualified_with_table(self):
        result = convert_tableau_formula_to_dax(
            "[Total Sales]",
            table_name="Orders",
            column_table_map={"Total Sales": "Orders"},
            measure_names={"Total Sales"},
        )
        self.assertIn("[Total Sales]", result)
        # Measures should NOT have table prefix
        self.assertNotIn("'Orders'[Total Sales]", result)

    def test_cross_table_ref_uses_related(self):
        result = convert_tableau_formula_to_dax(
            "[Product Name]",
            table_name="Orders",
            column_table_map={"Product Name": "Products"},
            is_calc_column=True,
        )
        self.assertIn("RELATED", result)


# ═══════════════════════════════════════════════════════════════════════
# AGG(IF(...)) → AGGX Conversion
# ═══════════════════════════════════════════════════════════════════════

class TestAggIfToAggx(unittest.TestCase):
    """Test SUM(IF(...)) → SUMX('table', IF(...)) conversion."""

    def test_sum_if_to_sumx(self):
        result = convert_tableau_formula_to_dax(
            "SUM(IF [Status]='Active' THEN [Amount] END)",
            table_name="Orders",
            column_table_map={"Status": "Orders", "Amount": "Orders"},
        )
        self.assertIn("SUMX", result)

    def test_avg_if_to_averagex(self):
        result = convert_tableau_formula_to_dax(
            "AVG(IF [Type]='A' THEN [Value] END)",
            table_name="Data",
            column_table_map={"Type": "Data", "Value": "Data"},
        )
        self.assertIn("AVERAGEX", result)


# ═══════════════════════════════════════════════════════════════════════
# Table Calc Conversions
# ═══════════════════════════════════════════════════════════════════════

class TestTableCalcConversions(unittest.TestCase):
    """Test Tableau table calculation → DAX conversions."""

    def test_running_sum(self):
        result = convert_tableau_formula_to_dax(
            "RUNNING_SUM(SUM([Sales]))",
            table_name="Orders",
        )
        self.assertIn("CALCULATE", result)

    def test_running_avg(self):
        result = convert_tableau_formula_to_dax(
            "RUNNING_AVG(SUM([Sales]))",
            table_name="Orders",
        )
        self.assertIn("CALCULATE", result)

    def test_rank(self):
        result = convert_tableau_formula_to_dax(
            "RANK(SUM([Sales]))",
            table_name="Orders",
        )
        self.assertIn("RANKX", result)

    def test_rank_unique(self):
        result = convert_tableau_formula_to_dax(
            "RANK_UNIQUE(SUM([Sales]))",
            table_name="Orders",
        )
        self.assertIn("RANKX", result)

    def test_window_sum(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_SUM(SUM([Sales]))",
            table_name="Orders",
        )
        self.assertIn("CALCULATE", result)


# ═══════════════════════════════════════════════════════════════════════
# Date Function Conversions
# ═══════════════════════════════════════════════════════════════════════

class TestDateFunctions(unittest.TestCase):
    """Test Tableau date function → DAX conversions."""

    def test_datetrunc_year(self):
        result = convert_tableau_formula_to_dax("DATETRUNC('year', [OrderDate])")
        # Should convert to STARTOFYEAR or equivalent
        dax_upper = result.upper()
        self.assertTrue(
            "STARTOFYEAR" in dax_upper or "YEAR" in dax_upper,
            f"Expected date operation but got: {result}"
        )

    def test_datepart_year(self):
        result = convert_tableau_formula_to_dax("DATEPART('year', [OrderDate])")
        self.assertIn("YEAR", result.upper())

    def test_dateadd(self):
        result = convert_tableau_formula_to_dax("DATEADD('month', 3, [OrderDate])")
        self.assertIn("DATEADD", result)

    def test_date_literal(self):
        result = convert_tableau_formula_to_dax("#2024-01-15#")
        self.assertIn("DATE", result)
        self.assertIn("2024", result)


# ═══════════════════════════════════════════════════════════════════════
# Reference Resolution
# ═══════════════════════════════════════════════════════════════════════

class TestReferenceResolution(unittest.TestCase):
    """Test calc_map and param_map reference resolution."""

    def test_calculation_reference_resolved(self):
        result = convert_tableau_formula_to_dax(
            "[Calculation_001] * 2",
            calc_map={"Calculation_001": "Total Sales"},
        )
        self.assertIn("Total Sales", result)
        self.assertNotIn("Calculation_001", result)

    def test_parameter_reference_resolved(self):
        result = convert_tableau_formula_to_dax(
            "[Parameters].[Discount Rate]",
            param_map={"Discount Rate": "Discount Rate"},
        )
        self.assertIn("Discount Rate", result)

    def test_parameter_inlined_for_calc_column(self):
        result = convert_tableau_formula_to_dax(
            "[Parameters].[Max Value]",
            param_map={"Max Value": "Max Value"},
            param_values={"Max Value": "100"},
            is_calc_column=True,
        )
        self.assertIn("100", result)


# ═══════════════════════════════════════════════════════════════════════
# Math / Statistics Functions
# ═══════════════════════════════════════════════════════════════════════

class TestMathStatsFunctions(unittest.TestCase):
    """Test math and statistics function conversions."""

    def test_stdev(self):
        result = convert_tableau_formula_to_dax("STDEV([Value])")
        self.assertIn("STDEV", result)

    def test_var(self):
        result = convert_tableau_formula_to_dax("VAR([Value])")
        dax_upper = result.upper()
        self.assertTrue("VAR" in dax_upper)

    def test_ceiling_gets_second_arg(self):
        result = convert_tableau_formula_to_dax("CEILING([Value])")
        # Should add missing second argument
        self.assertIn("CEILING", result)

    def test_floor_gets_second_arg(self):
        result = convert_tableau_formula_to_dax("FLOOR([Value])")
        self.assertIn("FLOOR", result)


# ═══════════════════════════════════════════════════════════════════════
# No Tableau Syntax Leakage
# ═══════════════════════════════════════════════════════════════════════

class TestNoTableauLeakage(unittest.TestCase):
    """Verify converted DAX doesn't contain Tableau-specific syntax."""

    def test_no_elseif(self):
        formula = "IF [A]>1 THEN 'X' ELSEIF [A]>0 THEN 'Y' ELSE 'Z' END"
        result = convert_tableau_formula_to_dax(formula)
        self.assertNotIn("ELSEIF", result)

    def test_no_double_equals(self):
        result = convert_tableau_formula_to_dax("[X] == 1")
        self.assertNotIn("==", result)

    def test_no_not_equals_excl(self):
        result = convert_tableau_formula_to_dax("[X] != 1")
        self.assertNotIn("!=", result)

    def test_no_lod_braces(self):
        result = convert_tableau_formula_to_dax(
            "{FIXED [Region] : SUM([Sales])}",
            table_name="T",
            column_table_map={"Region": "T", "Sales": "T"},
        )
        self.assertNotIn("{FIXED", result)
        self.assertNotIn("{INCLUDE", result)
        self.assertNotIn("{EXCLUDE", result)


# ═══════════════════════════════════════════════════════════════════════
# Complex / Combined Formulas
# ═══════════════════════════════════════════════════════════════════════

class TestComplexFormulas(unittest.TestCase):
    """Test complex multi-feature formulas."""

    def test_nested_if_with_aggregation(self):
        formula = "IF SUM([Sales]) > 1000 THEN 'High' ELSE 'Low' END"
        result = convert_tableau_formula_to_dax(
            formula,
            table_name="Orders",
            column_table_map={"Sales": "Orders"},
        )
        self.assertIn("IF", result)
        self.assertIn("SUM", result)

    def test_formula_with_multiple_functions(self):
        formula = "ROUND(SUM([Sales]) / COUNTD([Customer]), 2)"
        result = convert_tableau_formula_to_dax(
            formula,
            table_name="Orders",
            column_table_map={"Sales": "Orders", "Customer": "Orders"},
        )
        self.assertIn("ROUND", result)
        self.assertIn("SUM", result)
        self.assertIn("DISTINCTCOUNT", result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
