"""Coverage push for tableau_export/dax_converter.py — Sprint 39.

Targets the 302 missed lines (73.7% → 90%+) by testing:
 - _reverse_tableau_bracket_escape body (L26-32)
 - Federated prefix stripping (L293)
 - CASE/WHEN → SWITCH body (L452-485)
 - _extract_balanced_call (L585)
 - DATEDIFF fallback (L547)
 - FIND arg reorder (L722)
 - CORR/COVAR/COVARP internals (L771-794)
 - _transform_func_call (L852)
 - ENDSWITH/STARTSWITH/PROPER/SPLIT via internal fns (L868-920)
 - DATEPARSE / ISDATE / ATTR (L951-979)
 - REGEXP_MATCH all branches (L1047-1134)
 - REGEXP_EXTRACT all branches (L1152-1208)
 - REGEXP_EXTRACT_NTH all branches (L1227-1288)
 - REGEXP_REPLACE all branches + anchored (L1315-1387)
 - _fix_ceiling_floor / _fix_startof_calc_columns / _fix_date_literals (L1345-1387)
 - _convert_string_concat body (L1432)
 - _infer_iteration_table (L1485)
 - LOD expressions: nested, no-dim, AGG(CALCULATE) cleanup (L1504-1609)
 - Window functions with frame bounds (L1653-1693)
 - WINDOW_CORR/COVAR/COVARP (L1729-1739)
 - RANK_DENSE/MODIFIED/PERCENTILE (L1770-1782)
 - RUNNING_COUNT/MAX/MIN + TOTAL (L1811-1853)
 - _resolve_columns inner helpers (L1877-1894)
 - AGG(IF/SWITCH) → AGGX + _unwrap_inner_agg (L1949-1990)
 - _convert_agg_expr_to_aggx STDEV/MEDIAN (L1990)
 - generate_combined_field_dax (L2098-2115)
 - detect_script_functions / _detect_script_language / has_script_functions (L2118-2181)
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tableau_export.dax_converter import (
    convert_tableau_formula_to_dax,
    _reverse_tableau_bracket_escape,
    _extract_balanced_call,
    _convert_case_structure,
    _convert_regexp_match,
    _convert_regexp_extract,
    _convert_regexp_extract_nth,
    _convert_regexp_replace,
    _convert_corr_covar,
    _convert_previous_value,
    _convert_lookup,
    _convert_find,
    _convert_str_to_format,
    _convert_float_to_convert,
    _convert_datename,
    _convert_dateparse,
    _convert_isdate,
    _convert_attr,
    _convert_endswith,
    _convert_startswith,
    _convert_proper,
    _convert_split,
    _convert_lod_expressions,
    _convert_window_functions,
    _convert_rank_functions,
    _convert_running_functions,
    _convert_total_function,
    _convert_string_concat,
    _fix_ceiling_floor,
    _fix_startof_calc_columns,
    _fix_date_literals,
    _infer_iteration_table,
    _convert_agg_if_to_aggx,
    _convert_agg_expr_to_aggx,
    _transform_func_call,
    generate_combined_field_dax,
    detect_script_functions,
    has_script_functions,
    _detect_script_language,
    _convert_datediff,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  1. _reverse_tableau_bracket_escape body (L26-32)
# ═══════════════════════════════════════════════════════════════════════════════

class TestReverseBracketEscapeBody(unittest.TestCase):
    """Ensure the reverse-iteration loop body in _reverse_tableau_bracket_escape
    is exercised with orphan ')' in different positions."""

    def test_single_orphan_at_end(self):
        # "Col)" → "Col]"
        self.assertEqual(_reverse_tableau_bracket_escape('Col)'), 'Col]')

    def test_single_orphan_in_middle(self):
        # "Net)Revenue" → "Net]Revenue"
        self.assertEqual(_reverse_tableau_bracket_escape('Net)Revenue'), 'Net]Revenue')

    def test_multiple_orphans_reverse_order(self):
        # "a)b)c" has 2 excess → last two ) → ], reversed
        result = _reverse_tableau_bracket_escape('a)b)c')
        self.assertEqual(result, 'a]b]c')

    def test_mixed_balanced_and_orphan(self):
        # "(a)b)" — 1 open, 2 close → 1 excess, rightmost ) → ]
        result = _reverse_tableau_bracket_escape('(a)b)')
        self.assertEqual(result, '(a)b]')

    def test_no_excess(self):
        # "(a)" — balanced → unchanged
        self.assertEqual(_reverse_tableau_bracket_escape('(a)'), '(a)')

    def test_empty_string(self):
        self.assertEqual(_reverse_tableau_bracket_escape(''), '')


# ═══════════════════════════════════════════════════════════════════════════════
#  2. Federated prefix stripping (L293)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFederatedPrefixStrip(unittest.TestCase):
    """L293 — [federated.xxxID].[Col] prefixes stripped from data-blend refs."""

    def test_federated_prefix_removed(self):
        result = convert_tableau_formula_to_dax(
            'SUM([federated.abc123].[Sales])',
            table_name='Orders'
        )
        self.assertNotIn('federated', result)
        self.assertIn('Sales', result)

    def test_multiple_federated_refs(self):
        result = convert_tableau_formula_to_dax(
            '[federated.id1].[A] + [federated.id2].[B]',
            table_name='T'
        )
        self.assertNotIn('federated', result)
        self.assertIn('A', result)
        self.assertIn('B', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  3. CASE/WHEN → SWITCH body (L452-485)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCaseWhenBody(unittest.TestCase):
    """Exercise the CASE/WHEN/THEN parsing loop (L452-485)."""

    def test_case_two_branches_with_else(self):
        text = "CASE [Region] WHEN 'East' THEN 1 WHEN 'West' THEN 2 ELSE 0 END"
        result = _convert_case_structure(text)
        self.assertIn('SWITCH', result)
        self.assertIn("'East'", result)
        self.assertIn("'West'", result)
        self.assertIn('0', result)

    def test_case_without_else(self):
        text = "CASE [Status] WHEN 'Active' THEN 1 END"
        result = _convert_case_structure(text)
        self.assertIn('SWITCH', result)
        self.assertIn("'Active'", result)
        self.assertIn('1', result)

    def test_case_multiple_branches(self):
        text = "CASE [X] WHEN 'A' THEN 10 WHEN 'B' THEN 20 WHEN 'C' THEN 30 ELSE 99 END"
        result = _convert_case_structure(text)
        self.assertIn('SWITCH', result)
        # All values should appear
        for v in ['10', '20', '30', '99']:
            self.assertIn(v, result)

    def test_case_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            "CASE [Type] WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 0 END",
            table_name='T'
        )
        self.assertIn('SWITCH', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  4. _extract_balanced_call (L585)
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractBalancedCall(unittest.TestCase):
    """Exercise _extract_balanced_call balanced-paren extraction."""

    def test_simple_call(self):
        results = _extract_balanced_call('ZN([Sales])', 'ZN')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][2], '[Sales]')

    def test_nested_parens(self):
        results = _extract_balanced_call('ZN(SUM([X]))', 'ZN')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][2], 'SUM([X])')

    def test_multiple_occurrences(self):
        results = _extract_balanced_call('ZN([A]) + ZN([B])', 'ZN')
        self.assertEqual(len(results), 2)

    def test_no_match(self):
        results = _extract_balanced_call('SUM([X])', 'ZN')
        self.assertEqual(len(results), 0)


# ═══════════════════════════════════════════════════════════════════════════════
#  5. DATEDIFF fallback (L547)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatediffFallback(unittest.TestCase):
    """L547 — DATEDIFF with ≠3 args keeps original."""

    def test_datediff_3_args_reorders(self):
        result = _convert_datediff("DATEDIFF('month', [Start], [End])")
        self.assertIn('MONTH', result)
        self.assertIn('[Start]', result)
        self.assertIn('[End]', result)

    def test_datediff_2_args_fallback(self):
        result = _convert_datediff("DATEDIFF([A], [B])")
        self.assertIn('DATEDIFF', result)
        self.assertIn('[A]', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  6. FIND arg reorder (L722)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindArgReorder(unittest.TestCase):
    """L722 — FIND(string, substring) → FIND(substring, string)."""

    def test_find_args_swapped(self):
        result = _convert_find("FIND([Name], 'Smith')")
        self.assertIn('FIND', result)
        # After swap, 'Smith' comes first
        idx_smith = result.index("'Smith'")
        idx_name = result.index('[Name]')
        self.assertLess(idx_smith, idx_name)

    def test_find_single_arg_unchanged(self):
        result = _convert_find("FIND([X])")
        self.assertIn('FIND', result)

    def test_findnth_converted(self):
        result = _convert_find("FINDNTH([Text], 'abc')")
        self.assertIn('FIND(', result)
        self.assertNotIn('FINDNTH', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  7. CORR / COVAR / COVARP internals (L771-794)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCorrCovarInternals(unittest.TestCase):
    """Exercise _convert_corr_covar internal parsing and fallback."""

    def test_corr_two_args(self):
        result = _convert_corr_covar('CORR([X], [Y])', 'Sales')
        self.assertIn('AVERAGEX', result)
        self.assertIn('SUMX', result)
        self.assertIn('DIVIDE', result)

    def test_covarp_two_args(self):
        result = _convert_corr_covar('COVARP([A], [B])', 'T')
        self.assertIn('COUNTROWS', result)
        self.assertIn('DIVIDE', result)
        self.assertNotIn('- 1', result.split('RETURN')[1].split(',')[0])

    def test_covar_sample_two_args(self):
        result = _convert_corr_covar('COVAR([X], [Y])', 'T')
        self.assertIn('_N - 1', result)

    def test_corr_single_arg_fallback(self):
        result = _convert_corr_covar('CORR([X])', 'T')
        self.assertIn('could not parse', result)
        self.assertIn('0', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  8. _transform_func_call generic transformer (L852)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTransformFuncCall(unittest.TestCase):
    """L852 — generic balanced-paren function call transformer."""

    def test_simple_transform(self):
        result = _transform_func_call('MYFUNC(abc)', 'MYFUNC', lambda args, inner: f'RESULT({inner})')
        self.assertEqual(result, 'RESULT(abc)')

    def test_nested_parens(self):
        result = _transform_func_call('MYFUNC(a(b))', 'MYFUNC', lambda args, inner: f'OK({inner})')
        self.assertEqual(result, 'OK(a(b))')

    def test_no_match(self):
        result = _transform_func_call('OTHER(x)', 'MYFUNC', lambda args, inner: 'FAIL')
        self.assertEqual(result, 'OTHER(x)')


# ═══════════════════════════════════════════════════════════════════════════════
#  9. ENDSWITH / STARTSWITH / PROPER / SPLIT via internal fns (L868-920)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStringFunctionInternals(unittest.TestCase):
    """Exercise internal string converter branches."""

    def test_endswith_two_args(self):
        result = _convert_endswith("ENDSWITH([Name], 'abc')")
        self.assertIn('RIGHT', result)
        self.assertIn('LEN', result)

    def test_endswith_one_arg_fallback(self):
        result = _convert_endswith("ENDSWITH([X])")
        self.assertIn('ENDSWITH', result)

    def test_startswith_two_args(self):
        result = _convert_startswith("STARTSWITH([Name], 'xyz')")
        self.assertIn('LEFT', result)
        self.assertIn('LEN', result)

    def test_startswith_one_arg_fallback(self):
        result = _convert_startswith("STARTSWITH([X])")
        self.assertIn('STARTSWITH', result)

    def test_proper(self):
        result = _convert_proper("PROPER([Name])")
        self.assertIn('UPPER', result)
        self.assertIn('LEFT', result)
        self.assertIn('LOWER', result)
        self.assertIn('MID', result)

    def test_split_three_args(self):
        result = _convert_split('SPLIT([Data], "-", 2)')
        self.assertIn('PATHITEM', result)
        self.assertIn('SUBSTITUTE', result)
        self.assertIn('2', result)

    def test_split_two_args_default_token(self):
        result = _convert_split("SPLIT([Data], '-')")
        self.assertIn('PATHITEM', result)
        self.assertIn('1)', result)

    def test_split_one_arg_fallback(self):
        result = _convert_split("SPLIT([X])")
        self.assertIn('BLANK()', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  10. DATEPARSE / ISDATE / ATTR (L951-979)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDateParseIsdateAttr(unittest.TestCase):
    """Exercise DATEPARSE, ISDATE, ATTR converter branches."""

    def test_dateparse_with_format(self):
        result = _convert_dateparse("DATEPARSE('%Y-%m-%d', [DateStr])")
        self.assertIn('FORMAT', result)
        self.assertIn('DATEVALUE', result)

    def test_dateparse_empty_format(self):
        result = _convert_dateparse("DATEPARSE('', [DateStr])")
        self.assertIn('DATEVALUE', result)

    def test_dateparse_single_arg(self):
        result = _convert_dateparse("DATEPARSE([DateStr])")
        self.assertIn('DATEVALUE', result)

    def test_isdate(self):
        result = _convert_isdate("ISDATE([X])")
        self.assertIn('NOT', result)
        self.assertIn('ISERROR', result)
        self.assertIn('DATEVALUE', result)

    def test_attr_column(self):
        result = _convert_attr("ATTR([Category])")
        self.assertIn('SELECTEDVALUE', result)

    def test_attr_measure(self):
        result = _convert_attr("ATTR([TotalSales])", measure_names={'TotalSales'})
        self.assertEqual(result, '[TotalSales]')

    def test_attr_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            'ATTR([Region])', table_name='Sales',
            column_table_map={'Region': 'Sales'}
        )
        self.assertIn('SELECTEDVALUE', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  11. REGEXP_MATCH all branches (L1047-1134)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegexpMatch(unittest.TestCase):
    """Exercise every branch in _convert_regexp_match."""

    def test_insufficient_args(self):
        result = _convert_regexp_match('REGEXP_MATCH([X])')
        self.assertIn('CONTAINSSTRING', result)

    def test_left_anchor(self):
        # ^ABC → LEFT match
        result = _convert_regexp_match('REGEXP_MATCH([Name], "^ABC")')
        self.assertIn('LEFT', result)
        self.assertIn('ABC', result)

    def test_right_anchor(self):
        # xyz$ → RIGHT match
        result = _convert_regexp_match('REGEXP_MATCH([Name], "xyz$")')
        self.assertIn('RIGHT', result)
        self.assertIn('xyz', result)

    def test_all_digits(self):
        # ^[0-9]+$ → ISNUMBER(VALUE(...))
        result = _convert_regexp_match('REGEXP_MATCH([Code], "^[0-9]+$")')
        self.assertIn('ISNUMBER', result)
        self.assertIn('VALUE', result)

    def test_all_letters_char_class(self):
        # ^[a-zA-Z]+$ → CODE-based check
        result = _convert_regexp_match('REGEXP_MATCH([Name], "^[a-zA-Z]+$")')
        self.assertIn('verify manually', result)

    def test_contains_digit(self):
        # [0-9] → OR of CONTAINSSTRING
        result = _convert_regexp_match('REGEXP_MATCH([Data], "[0-9]")')
        self.assertIn('CONTAINSSTRING', result)
        self.assertIn('"0"', result)
        self.assertIn('"9"', result)

    def test_contains_lowercase(self):
        # [a-z] → CODE-based
        result = _convert_regexp_match('REGEXP_MATCH([X], "[a-z]")')
        self.assertIn('CODE', result)
        self.assertIn('97', result)

    def test_contains_uppercase(self):
        # [A-Z] → CODE-based
        result = _convert_regexp_match('REGEXP_MATCH([X], "[A-Z]")')
        self.assertIn('CODE', result)
        self.assertIn('65', result)

    def test_general_char_class(self):
        # [0-5] → char class check
        result = _convert_regexp_match('REGEXP_MATCH([X], "[0-5]")')
        self.assertIn('character class', result)

    def test_alternation(self):
        # cat|dog → OR of CONTAINSSTRING
        result = _convert_regexp_match('REGEXP_MATCH([Pet], "cat|dog")')
        self.assertIn('CONTAINSSTRING', result)
        self.assertIn('"cat"', result)
        self.assertIn('"dog"', result)
        self.assertIn('||', result)

    def test_simple_literal(self):
        # simple text → CONTAINSSTRING
        result = _convert_regexp_match('REGEXP_MATCH([Name], "hello")')
        self.assertIn('CONTAINSSTRING', result)
        self.assertIn('"hello"', result)

    def test_complex_regex_fallback(self):
        # Complex pattern → CONTAINSSTRING with warning
        result = _convert_regexp_match('REGEXP_MATCH([X], "a.*b")')
        self.assertIn('verify manually', result)

    def test_backslash_d_shorthand(self):
        # \d → normalized to [0-9]
        result = _convert_regexp_match('REGEXP_MATCH([Code], "\\d")')
        self.assertIn('CONTAINSSTRING', result)

    def test_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_MATCH([Email], "^[a-zA-Z]+$")',
            table_name='Users'
        )
        self.assertIn('verify manually', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  12. REGEXP_EXTRACT all branches (L1152-1208)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegexpExtract(unittest.TestCase):
    """Exercise every branch in _convert_regexp_extract."""

    def test_insufficient_args(self):
        result = _convert_regexp_extract('REGEXP_EXTRACT([X])')
        self.assertIn('BLANK()', result)

    def test_prefix_capture(self):
        # "https://(.*)" → MID extraction
        result = _convert_regexp_extract('REGEXP_EXTRACT([URL], "https://(.*)")')
        self.assertIn('MID', result)
        self.assertIn('SEARCH', result)
        self.assertIn('https://', result)

    def test_suffix_capture(self):
        # "(.*)\.csv" → LEFT extraction
        result = _convert_regexp_extract('REGEXP_EXTRACT([File], "(.*).csv")')
        self.assertIn('LEFT', result)
        self.assertIn('SEARCH', result)

    def test_prefix_suffix_capture(self):
        # "start(.*)end" → MID between
        result = _convert_regexp_extract('REGEXP_EXTRACT([X], "start(.*)end")')
        self.assertIn('MID', result)
        self.assertIn('start', result)
        self.assertIn('end', result)

    def test_digit_extraction(self):
        # "([0-9]+)" → digit extraction
        result = _convert_regexp_extract('REGEXP_EXTRACT([Code], "([0-9]+)")')
        self.assertIn('IFERROR', result)
        self.assertIn('FIND', result)

    def test_unknown_pattern_fallback(self):
        # Complex pattern → BLANK()
        result = _convert_regexp_extract('REGEXP_EXTRACT([X], "(?:a|b)+")')
        self.assertIn('BLANK()', result)

    def test_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT([Path], "folder/(.*)")',
            table_name='Files'
        )
        self.assertIn('MID', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  13. REGEXP_EXTRACT_NTH all branches (L1227-1288)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegexpExtractNth(unittest.TestCase):
    """Exercise every branch in _convert_regexp_extract_nth."""

    def test_insufficient_args(self):
        result = _convert_regexp_extract_nth('REGEXP_EXTRACT_NTH([X])')
        self.assertIn('BLANK()', result)
        self.assertIn('insufficient', result)

    def test_delimiter_single_char(self):
        # "([^,]*)" → PATHITEM(SUBSTITUTE(field, ",", "|"), idx)
        result = _convert_regexp_extract_nth('REGEXP_EXTRACT_NTH([Data], "([^,]*)", 3)')
        self.assertIn('PATHITEM', result)
        self.assertIn('SUBSTITUTE', result)
        self.assertIn(',', result)
        self.assertIn('3', result)

    def test_delimiter_multi_char_approx(self):
        # "([^ab]*)" → approximated with first char
        result = _convert_regexp_extract_nth('REGEXP_EXTRACT_NTH([Data], "([^ab]*)", 2)')
        self.assertIn('PATHITEM', result)
        self.assertIn('approximated', result)

    def test_prefix_capture(self):
        # "prefix(.*)" → MID extraction
        result = _convert_regexp_extract_nth('REGEXP_EXTRACT_NTH([X], "ID:(.*)", 1)')
        self.assertIn('MID', result)
        self.assertIn('SEARCH', result)

    def test_alternation_capture(self):
        # "(cat|dog|fish)" → IF chain
        result = _convert_regexp_extract_nth('REGEXP_EXTRACT_NTH([Pet], "(cat|dog|fish)", 1)')
        self.assertIn('IF', result)
        self.assertIn('CONTAINSSTRING', result)
        self.assertIn('"cat"', result)
        self.assertIn('"dog"', result)
        self.assertIn('"fish"', result)

    def test_two_args_default_index(self):
        # 2 args → default index=1
        result = _convert_regexp_extract_nth('REGEXP_EXTRACT_NTH([Data], "([^-]*)")')
        self.assertIn('PATHITEM', result)
        self.assertIn('1', result)

    def test_unknown_pattern_fallback(self):
        result = _convert_regexp_extract_nth('REGEXP_EXTRACT_NTH([X], "(?:complex)+", 2)')
        self.assertIn('BLANK()', result)

    def test_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_EXTRACT_NTH([CSV], "([^,]*)", 2)',
            table_name='Data'
        )
        self.assertIn('PATHITEM', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  14. REGEXP_REPLACE all branches (L1315-1387)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegexpReplace(unittest.TestCase):
    """Exercise every branch in _convert_regexp_replace."""

    def test_simple_literal(self):
        result = _convert_regexp_replace('REGEXP_REPLACE([Name], "old", "new")')
        self.assertIn('SUBSTITUTE', result)
        self.assertIn('"old"', result)

    def test_char_class(self):
        # [aeiou] → chained SUBSTITUTE
        result = _convert_regexp_replace('REGEXP_REPLACE([Text], "[aeiou]", "")')
        self.assertIn('SUBSTITUTE', result)
        self.assertIn('"a"', result)
        self.assertIn('"e"', result)

    def test_alternation_as_literal(self):
        # cat|dog — | is not in _REGEX_META, so treated as simple literal
        result = _convert_regexp_replace('REGEXP_REPLACE([X], "cat|dog", "pet")')
        self.assertIn('SUBSTITUTE', result)
        self.assertIn('"cat|dog"', result)

    def test_anchored_start(self):
        # ^prefix → IF(LEFT...) replacement
        result = _convert_regexp_replace('REGEXP_REPLACE([X], "^abc", "xyz")')
        self.assertIn('IF', result)
        self.assertIn('LEFT', result)

    def test_anchored_end(self):
        # suffix$ → IF(RIGHT...) replacement
        result = _convert_regexp_replace('REGEXP_REPLACE([X], "end$", "new")')
        self.assertIn('IF', result)
        self.assertIn('RIGHT', result)

    def test_complex_fallback(self):
        result = _convert_regexp_replace('REGEXP_REPLACE([X], "a.*b", "c")')
        self.assertIn('verify manually', result)

    def test_fewer_than_3_args(self):
        result = _convert_regexp_replace('REGEXP_REPLACE([X], "pat")')
        self.assertIn('SUBSTITUTE', result)

    def test_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_REPLACE([Name], "[0-9]", "")',
            table_name='People'
        )
        self.assertIn('SUBSTITUTE', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  15. _fix_ceiling_floor / _fix_startof_calc_columns / _fix_date_literals
# ═══════════════════════════════════════════════════════════════════════════════

class TestFixFunctions(unittest.TestCase):
    """L1345-1387 — ceiling/floor significance, STARTOF* for calc columns, date literals."""

    def test_ceiling_single_arg(self):
        result = _fix_ceiling_floor('CEILING([X])')
        self.assertIn('CEILING', result)
        self.assertIn(', 1)', result)

    def test_ceiling_two_args_unchanged(self):
        result = _fix_ceiling_floor('CEILING([X], 10)')
        self.assertIn('CEILING', result)
        self.assertIn('10', result)

    def test_floor_single_arg(self):
        result = _fix_ceiling_floor('FLOOR([X])')
        self.assertIn('FLOOR', result)
        self.assertIn(', 1)', result)

    def test_startof_year(self):
        result = _fix_startof_calc_columns('STARTOFYEAR([Date])')
        self.assertIn('DATE(YEAR([Date]), 1, 1)', result)

    def test_startof_month(self):
        result = _fix_startof_calc_columns('STARTOFMONTH([Date])')
        self.assertIn('DATE(YEAR([Date]), MONTH([Date]), 1)', result)

    def test_startof_quarter(self):
        result = _fix_startof_calc_columns('STARTOFQUARTER([Date])')
        self.assertIn('DATE(', result)
        self.assertIn('MONTH', result)

    def test_date_literal(self):
        result = _fix_date_literals('#2023-06-15#')
        self.assertEqual(result, 'DATE(2023, 6, 15)')

    def test_no_date_literal(self):
        result = _fix_date_literals('[Date]')
        self.assertEqual(result, '[Date]')

    def test_startof_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            'STARTOFMONTH([Date])',
            table_name='Calendar',
            is_calc_column=True,
            column_table_map={'Date': 'Calendar'}
        )
        self.assertIn('DATE(', result)
        self.assertIn('MONTH', result)

    def test_date_literal_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            '#2020-01-15#',
            table_name='T'
        )
        self.assertIn('DATE(2020, 1, 15)', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  16. _convert_string_concat body (L1432)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStringConcatBody(unittest.TestCase):
    """L1432 — + to & conversion respecting numeric context."""

    def test_string_concat(self):
        result = _convert_string_concat('[First] + [Last]')
        self.assertIn('&', result)
        self.assertNotIn('+', result)

    def test_numeric_preserved(self):
        result = _convert_string_concat('[Score] + 1')
        # 1 is numeric → keep +
        self.assertIn('+', result)

    def test_numeric_before_preserved(self):
        result = _convert_string_concat('2 + [Value]')
        self.assertIn('+', result)

    def test_mixed(self):
        # String context + numeric context in same formula
        result = _convert_string_concat('[A] + [B] + 5')
        # [A] + [B] → &, [B] + 5 → + (5 is numeric)
        self.assertIn('&', result)

    def test_string_in_quotes(self):
        result = _convert_string_concat('"hello" + [Name]')
        # After "hello", + should become & (not numeric)
        self.assertIn('&', result)

    def test_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            '[First] + [Last]',
            table_name='People',
            calc_datatype='string'
        )
        self.assertIn('&', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  17. _infer_iteration_table (L1485)
# ═══════════════════════════════════════════════════════════════════════════════

class TestInferIterationTable(unittest.TestCase):
    """L1485 — infer best table from column references."""

    def test_single_table_ref(self):
        result = _infer_iteration_table("'Sales'[Amount]", 'Default')
        self.assertEqual(result, 'Sales')

    def test_multiple_same_table(self):
        result = _infer_iteration_table("'Sales'[A] * 'Sales'[B]", 'Default')
        self.assertEqual(result, 'Sales')

    def test_multiple_tables_most_frequent_wins(self):
        result = _infer_iteration_table("'Sales'[A] + 'Sales'[B] + 'Dim'[C]", 'Default')
        self.assertEqual(result, 'Sales')

    def test_no_table_refs_returns_default(self):
        result = _infer_iteration_table('[Amount]', 'Default')
        self.assertEqual(result, 'Default')


# ═══════════════════════════════════════════════════════════════════════════════
#  18. LOD expressions: nested, no-dim, AGG(CALCULATE) cleanup (L1504-1609)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLODExpressionsAdvanced(unittest.TestCase):
    """Exercise LOD paths not covered by basic tests."""

    def test_fixed_with_dims(self):
        result = _convert_lod_expressions(
            '{FIXED [Region] : SUM([Sales])}',
            'Orders',
            {'Region': 'Geo', 'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)
        self.assertIn("'Geo'[Region]", result)

    def test_fixed_no_dims(self):
        result = _convert_lod_expressions(
            '{FIXED : SUM([Sales])}',
            'Orders',
            {'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn("ALL('Orders')", result)

    def test_include(self):
        result = _convert_lod_expressions(
            '{INCLUDE [State] : AVG([Profit])}',
            'Orders',
            {'State': 'Geo', 'Profit': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertNotIn('ALLEXCEPT', result)

    def test_exclude(self):
        result = _convert_lod_expressions(
            '{EXCLUDE [Product] : COUNT([Orders])}',
            'Sales',
            {'Product': 'Products', 'Orders': 'Sales'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('REMOVEFILTERS', result)

    def test_exclude_no_dims(self):
        result = _convert_lod_expressions(
            '{EXCLUDE : SUM([X])}',
            'T',
            {}
        )
        self.assertIn('CALCULATE', result)

    def test_nested_lod(self):
        result = _convert_lod_expressions(
            '{FIXED [Region] : {INCLUDE [State] : SUM([Sales])}}',
            'Orders',
            {'Region': 'Geo', 'State': 'Geo', 'Sales': 'Orders'}
        )
        # Inner INCLUDE processed first, then FIXED wraps it
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)

    def test_agg_calculate_cleanup(self):
        # SUM(CALCULATE(...)) — cleanup attempted but is_single check is conservative
        result = _convert_lod_expressions(
            'SUM({FIXED [Region] : MAX([Sales])})',
            'T',
            {'Region': 'T', 'Sales': 'T'}
        )
        # LOD is converted to CALCULATE(MAX, ALLEXCEPT)
        self.assertIn('CALCULATE(', result)
        self.assertIn('ALLEXCEPT', result)

    def test_via_main_converter_fixed(self):
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : SUM([Sales])}',
            table_name='Fact',
            column_table_map={'Region': 'Dim', 'Sales': 'Fact'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  19. Window functions with frame bounds (L1653-1693)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWindowFunctionsFrameBounds(unittest.TestCase):
    """L1653-1693 — WINDOW_SUM with frame boundaries → WINDOW function."""

    def test_window_sum_with_frame(self):
        result = _convert_window_functions(
            'WINDOW_SUM(SUM([Sales]), -2, 0)',
            'Orders',
            compute_using=['Date'],
            column_table_map={'Date': 'Calendar'}
        )
        self.assertIn('WINDOW(', result)
        self.assertIn('-2', result)
        self.assertIn('REL', result)
        self.assertIn('ORDERBY', result)

    def test_window_sum_frame_no_compute(self):
        result = _convert_window_functions(
            'WINDOW_SUM(SUM([Sales]), -1, 1)',
            'Orders'
        )
        self.assertIn('WINDOW(', result)
        self.assertIn("ALL('Orders')", result)

    def test_window_count_maps_to_countrows(self):
        result = _convert_window_functions(
            'WINDOW_COUNT(COUNT([ID]), -3, 0)',
            'T',
            compute_using=['Date'],
            column_table_map={'Date': 'T'}
        )
        self.assertIn('WINDOW(', result)

    def test_window_avg_no_frame_with_compute(self):
        result = _convert_window_functions(
            'WINDOW_AVG(AVG([Score]))',
            'T',
            compute_using=['Region'],
            column_table_map={'Region': 'Geo'}
        )
        self.assertIn('ALLEXCEPT', result)

    def test_window_min_no_context(self):
        result = _convert_window_functions(
            'WINDOW_MIN(MIN([Val]))',
            'T'
        )
        self.assertIn("ALL('T')", result)

    def test_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_SUM(SUM([Sales]), -2, 0)',
            table_name='Fact',
            compute_using=['Date'],
            column_table_map={'Date': 'Cal', 'Sales': 'Fact'}
        )
        self.assertIn('WINDOW(', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  20. WINDOW_CORR / WINDOW_COVAR / WINDOW_COVARP (L1729-1739)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWindowCorrCovar(unittest.TestCase):
    """L1729-1739 — WINDOW statistical functions."""

    def test_window_corr(self):
        result = _convert_window_functions(
            'WINDOW_CORR([Sales], [Profit])',
            'T'
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('AVERAGEX', result)
        self.assertIn("ALL('T')", result)

    def test_window_covar_with_compute(self):
        result = _convert_window_functions(
            'WINDOW_COVAR([X], [Y])',
            'T',
            compute_using=['Region'],
            column_table_map={'Region': 'Geo'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)

    def test_window_covarp(self):
        result = _convert_window_functions(
            'WINDOW_COVARP([A], [B])',
            'T'
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('COUNTROWS', result)

    def test_window_corr_insufficient_args(self):
        result = _convert_window_functions(
            'WINDOW_CORR([X])',
            'T'
        )
        self.assertIn('insufficient arguments', result)
        self.assertIn('0', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  21. RANK_DENSE / RANK_MODIFIED / RANK_PERCENTILE (L1770-1782)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRankVariantsInternal(unittest.TestCase):
    """Exercise rank function internals directly."""

    def test_rank_dense(self):
        result = _convert_rank_functions('RANK_DENSE(SUM([Sales]))', 'T')
        self.assertIn('RANKX', result)
        self.assertIn('DENSE', result)
        self.assertIn('ASC', result)

    def test_rank_modified(self):
        result = _convert_rank_functions('RANK_MODIFIED(SUM([Sales]))', 'T')
        self.assertIn('RANKX', result)
        self.assertIn('SKIP', result)
        self.assertIn('RANK_MODIFIED', result)

    def test_rank_percentile(self):
        result = _convert_rank_functions('RANK_PERCENTILE([Score])', 'T')
        self.assertIn('DIVIDE', result)
        self.assertIn('RANKX', result)
        self.assertIn('COUNTROWS', result)

    def test_rank_basic(self):
        result = _convert_rank_functions('RANK(SUM([X]))', 'T')
        self.assertIn('RANKX', result)
        self.assertNotIn('DENSE', result)

    def test_rank_with_compute_using(self):
        result = _convert_rank_functions(
            'RANK_DENSE(SUM([Sales]))', 'T',
            compute_using=['Region'],
            column_table_map={'Region': 'Geo'}
        )
        self.assertIn('ALLEXCEPT', result)
        self.assertIn("'Geo'[Region]", result)


# ═══════════════════════════════════════════════════════════════════════════════
#  22. RUNNING_COUNT / RUNNING_MAX / RUNNING_MIN + TOTAL (L1811-1853)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunningAndTotal(unittest.TestCase):
    """Exercise RUNNING_COUNT/MAX/MIN + TOTAL via internal functions."""

    def test_running_count(self):
        result = _convert_running_functions('RUNNING_COUNT(COUNT([ID]))', 'T')
        self.assertIn('CALCULATE', result)
        self.assertIn('FILTER', result)
        self.assertIn('ALLSELECTED', result)

    def test_running_max(self):
        result = _convert_running_functions('RUNNING_MAX(MAX([Val]))', 'T')
        self.assertIn('CALCULATE', result)
        self.assertIn('RUNNING_MAX', result)  # comment

    def test_running_min(self):
        result = _convert_running_functions('RUNNING_MIN(MIN([Val]))', 'T')
        self.assertIn('CALCULATE', result)
        self.assertIn('RUNNING_MIN', result)

    def test_total_function(self):
        result = _convert_total_function('TOTAL(SUM([Revenue]))', 'Sales')
        self.assertIn('CALCULATE', result)
        self.assertIn("ALL('Sales')", result)

    def test_total_via_main_converter(self):
        # TOTAL is in _SIMPLE_FUNCTION_MAP as TOTAL( → CALCULATE(
        # so the simple map fires first at Phase 3b before the
        # dedicated _convert_total_function at Phase 3h
        result = convert_tableau_formula_to_dax(
            'TOTAL(SUM([Revenue]))',
            table_name='Sales',
            column_table_map={'Revenue': 'Sales'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('Revenue', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  23. _resolve_columns inner helpers (L1877-1894)
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveColumnsInternals(unittest.TestCase):
    """L1877-1894 — column resolution edge cases."""

    def test_column_with_bracket_in_name(self):
        # Column name has ] → should be escaped as ]]
        result = convert_tableau_formula_to_dax(
            '[Sale]]s]',
            table_name='Fact',
            column_table_map={'Sale]s': 'Fact'}
        )
        # Should contain escaped column
        self.assertIn('Fact', result)

    def test_measure_returns_bare_ref(self):
        result = convert_tableau_formula_to_dax(
            '[Total Sales]',
            table_name='Fact',
            measure_names={'Total Sales'},
        )
        self.assertIn('[Total Sales]', result)
        self.assertNotIn("'Fact'", result)

    def test_calc_column_cross_table_uses_related(self):
        result = convert_tableau_formula_to_dax(
            '[City]',
            table_name='Sales',
            column_table_map={'City': 'Geography'},
            is_calc_column=True
        )
        self.assertIn('RELATED', result)
        self.assertIn("'Geography'[City]", result)

    def test_column_in_local_table_preferred(self):
        result = convert_tableau_formula_to_dax(
            '[Amount]',
            table_name='Sales',
            column_table_map={'Amount': 'OtherTable'},
            table_columns={'Amount'}
        )
        self.assertIn("'Sales'[Amount]", result)
        self.assertNotIn('OtherTable', result)

    def test_reversed_bracket_escape_in_column_ref(self):
        # Column name has orphan ) inside brackets [Col)] that maps to Col]
        result = convert_tableau_formula_to_dax(
            '[Col)]',
            table_name='T',
            column_table_map={'Col]': 'T'}
        )
        # Should resolve via bracket escape reversal
        self.assertIn('T', result)

    def test_param_value_inlined_for_measure_in_calc_column(self):
        result = convert_tableau_formula_to_dax(
            '[Param1]',
            table_name='T',
            measure_names={'Param1'},
            is_calc_column=True,
            param_values={'Param1': '42'}
        )
        self.assertIn('42', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  24. AGG(IF/SWITCH) → AGGX + _unwrap_inner_agg (L1949-1990)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAggIfSwitchAggx(unittest.TestCase):
    """L1949-1990 — AGG(IF/SWITCH) and AGG(multi-col expr) converters."""

    def test_sum_switch_to_sumx(self):
        result = _convert_agg_if_to_aggx(
            "SUM(SWITCH('T'[Status], \"A\", 1, 0))",
            'T'
        )
        self.assertIn('SUMX', result)

    def test_agg_expr_multi_column(self):
        result = _convert_agg_expr_to_aggx(
            "SUM('T'[Qty] * 'T'[Price])",
            'T'
        )
        self.assertIn('SUMX', result)
        self.assertIn("'T'", result)

    def test_agg_expr_single_column_unchanged(self):
        result = _convert_agg_expr_to_aggx(
            "SUM('T'[Amount])",
            'T'
        )
        # Single column → no conversion to SUMX
        self.assertIn("SUM('T'[Amount])", result)
        self.assertNotIn('SUMX', result)

    def test_stdev_with_inner_sum_unwrapped(self):
        result = _convert_agg_expr_to_aggx(
            "STDEV.S(SUM('T'[Qty] * 'T'[Price]))",
            'T'
        )
        self.assertIn('STDEVX.S', result)
        # Inner SUM should be unwrapped
        self.assertNotIn('SUM(', result)

    def test_median_multi_col(self):
        result = _convert_agg_expr_to_aggx(
            "MEDIAN('T'[A] + 'T'[B])",
            'T'
        )
        self.assertIn('MEDIANX', result)

    def test_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            "SUM(IF([Status] = 'Active', [Amount], 0))",
            table_name='Orders',
            column_table_map={'Status': 'Orders', 'Amount': 'Orders'}
        )
        self.assertIn('SUMX', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  25. generate_combined_field_dax (L2098-2115)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenerateCombinedFieldDax(unittest.TestCase):
    """L2098-2115 — multi-column concatenation DAX generator."""

    def test_no_fields(self):
        result = generate_combined_field_dax([], 'T')
        self.assertEqual(result, '""')

    def test_single_field(self):
        result = generate_combined_field_dax(['Name'], 'People')
        self.assertEqual(result, "'People'[Name]")

    def test_two_fields(self):
        result = generate_combined_field_dax(['First', 'Last'], 'People')
        self.assertIn("'People'[First]", result)
        self.assertIn("'People'[Last]", result)
        self.assertIn('&', result)
        self.assertIn('" "', result)

    def test_three_fields(self):
        result = generate_combined_field_dax(['A', 'B', 'C'], 'T', '-')
        self.assertIn("'T'[A]", result)
        self.assertIn("'T'[B]", result)
        self.assertIn("'T'[C]", result)
        self.assertIn('"-"', result)
        self.assertIn('&', result)

    def test_custom_separator(self):
        result = generate_combined_field_dax(['X', 'Y'], 'T', ', ')
        self.assertIn('", "', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  26. detect_script_functions / _detect_script_language / has_script_functions
# ═══════════════════════════════════════════════════════════════════════════════

class TestScriptDetection(unittest.TestCase):
    """L2118-2181 — SCRIPT_* function detection and language heuristics."""

    def test_detect_python_script(self):
        formula = 'SCRIPT_REAL("import numpy as np\\nreturn np.mean(_arg1)", SUM([X]))'
        results = detect_script_functions(formula)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['function'], 'SCRIPT_REAL')
        self.assertEqual(results[0]['language'], 'python')
        self.assertEqual(results[0]['return_type'], 'real')

    def test_detect_r_script(self):
        formula = 'SCRIPT_INT("library(dplyr)\\nresult <- sapply(x, mean)", SUM([X]))'
        results = detect_script_functions(formula)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['language'], 'r')
        self.assertEqual(results[0]['return_type'], 'int')

    def test_detect_script_bool(self):
        formula = 'SCRIPT_BOOL("return True", [Flag])'
        results = detect_script_functions(formula)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['return_type'], 'bool')

    def test_detect_script_str(self):
        formula = 'SCRIPT_STR("return str(_arg1)", [Name])'
        results = detect_script_functions(formula)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['return_type'], 'str')

    def test_no_script_functions(self):
        results = detect_script_functions('SUM([Sales])')
        self.assertEqual(len(results), 0)

    def test_empty_formula(self):
        results = detect_script_functions('')
        self.assertEqual(len(results), 0)

    def test_none_formula(self):
        results = detect_script_functions(None)
        self.assertEqual(len(results), 0)

    def test_has_script_functions_true(self):
        self.assertTrue(has_script_functions('SCRIPT_REAL("code", [X])'))

    def test_has_script_functions_false(self):
        self.assertFalse(has_script_functions('SUM([X])'))

    def test_has_script_functions_empty(self):
        self.assertFalse(has_script_functions(''))

    def test_has_script_functions_none(self):
        self.assertFalse(has_script_functions(None))

    def test_detect_language_python_markers(self):
        code = 'import pandas as pd\ndf = pd.DataFrame()'
        self.assertEqual(_detect_script_language(code), 'python')

    def test_detect_language_r_markers(self):
        code = 'library(ggplot2)\ndata.frame(x=1:10)'
        self.assertEqual(_detect_script_language(code), 'r')

    def test_detect_language_equal_scores_defaults_python(self):
        code = 'x = 1'  # No markers for either
        self.assertEqual(_detect_script_language(code), 'python')

    def test_detect_language_mixed_more_python(self):
        code = 'import numpy\nimport pandas\ndef func():\n  return x'
        self.assertEqual(_detect_script_language(code), 'python')

    def test_detect_language_mixed_more_r(self):
        code = 'library(dplyr)\nsapply(x, mean)\ndata.frame(a=1)\nggplot(df)'
        self.assertEqual(_detect_script_language(code), 'r')


# ═══════════════════════════════════════════════════════════════════════════════
#  27. STR / FLOAT via internal functions (L756)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrFloatInternal(unittest.TestCase):
    """L756 — STR → FORMAT, FLOAT → CONVERT via internal fns."""

    def test_str_to_format(self):
        result = _convert_str_to_format('STR([Qty])')
        self.assertEqual(result, 'FORMAT([Qty], "0")')

    def test_float_to_convert(self):
        result = _convert_float_to_convert('FLOAT([X])')
        self.assertEqual(result, 'CONVERT([X], DOUBLE)')


# ═══════════════════════════════════════════════════════════════════════════════
#  28. DATENAME via internal function (L756)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatenameInternal(unittest.TestCase):
    """Exercise DATENAME with various part arguments."""

    def test_datename_year(self):
        result = _convert_datename("DATENAME('year', [Date])")
        self.assertIn('FORMAT', result)
        self.assertIn('YYYY', result)

    def test_datename_quarter(self):
        result = _convert_datename("DATENAME('quarter', [Date])")
        self.assertIn('FORMAT', result)
        self.assertIn('"Q"', result)

    def test_datename_month(self):
        result = _convert_datename("DATENAME('month', [Date])")
        self.assertIn('FORMAT', result)
        self.assertIn('MMMM', result)

    def test_datename_day(self):
        result = _convert_datename("DATENAME('day', [Date])")
        self.assertIn('FORMAT', result)
        self.assertIn('"D"', result)

    def test_datename_weekday(self):
        result = _convert_datename("DATENAME('weekday', [Date])")
        self.assertIn('FORMAT', result)
        self.assertIn('DDDD', result)

    def test_datename_single_arg_fallback(self):
        result = _convert_datename("DATENAME([Date])")
        self.assertIn('DATENAME', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  29. PREVIOUS_VALUE and LOOKUP with compute_using (L638-680)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreviousValueLookupInternal(unittest.TestCase):
    """Exercise PREVIOUS_VALUE and LOOKUP internal functions."""

    def test_previous_value_with_compute_using(self):
        result = _convert_previous_value(
            'PREVIOUS_VALUE(0)',
            'Sales',
            compute_using=['Date'],
            column_table_map={'Date': 'Calendar'}
        )
        self.assertIn('OFFSET(-1', result)
        self.assertIn("ORDERBY('Calendar'[Date])", result)

    def test_previous_value_without_compute_using(self):
        result = _convert_previous_value('PREVIOUS_VALUE(100)', 'T')
        self.assertIn('OFFSET(-1', result)
        self.assertIn('ORDERBY([Value])', result)

    def test_lookup_with_compute_using(self):
        result = _convert_lookup(
            'LOOKUP(SUM([Sales]), -2)',
            'Fact',
            compute_using=['Month'],
            column_table_map={'Month': 'Cal'}
        )
        self.assertIn('OFFSET(-2', result)
        self.assertIn("ORDERBY('Cal'[Month])", result)

    def test_lookup_without_compute_using(self):
        result = _convert_lookup('LOOKUP([X], 1)', 'T')
        self.assertIn('OFFSET(1', result)
        self.assertIn('ORDERBY([Value])', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  30. Pipeline integration — partition_fields compat (L251, L285)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPartitionFieldsCompat(unittest.TestCase):
    """L285 — deprecated partition_fields maps to compute_using."""

    def test_partition_fields_deprecated_param(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_SUM(SUM([Sales]))',
            table_name='Fact',
            partition_fields=['Region'],
            column_table_map={'Region': 'Dim', 'Sales': 'Fact'}
        )
        self.assertIn('ALLEXCEPT', result)
        self.assertIn("'Dim'[Region]", result)


# ═══════════════════════════════════════════════════════════════════════════════
#  31. LOD no-keyword brace pattern
# ═══════════════════════════════════════════════════════════════════════════════

class TestLODNoKeyword(unittest.TestCase):
    """LOD without FIXED/INCLUDE/EXCLUDE → CALCULATE(expr)."""

    def test_lod_no_keyword_via_main(self):
        # {SUM([Sales])} → CALCULATE(SUM([Sales]))
        result = convert_tableau_formula_to_dax(
            '{SUM([Sales])}',
            table_name='T',
            column_table_map={'Sales': 'T'}
        )
        self.assertIn('CALCULATE', result)


# ═══════════════════════════════════════════════════════════════════════════════
#  32. Multi-phase interactions
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiPhaseInteractions(unittest.TestCase):
    """Integration tests combining multiple phases."""

    def test_lod_then_agg_cleanup(self):
        # SUM({FIXED [R] : MAX([S])}) → CALCULATE(MAX([S]), ALLEXCEPT)
        result = convert_tableau_formula_to_dax(
            'SUM({FIXED [Region] : MAX([Sales])})',
            table_name='T',
            column_table_map={'Region': 'T', 'Sales': 'T'}
        )
        self.assertIn('CALCULATE', result)

    def test_regexp_match_with_column_resolution(self):
        result = convert_tableau_formula_to_dax(
            'REGEXP_MATCH([Code], "^[0-9]+$")',
            table_name='Products',
            column_table_map={'Code': 'Products'}
        )
        self.assertIn('ISNUMBER', result)

    def test_case_then_resolve(self):
        result = convert_tableau_formula_to_dax(
            "CASE [Type] WHEN 'A' THEN [Amt1] WHEN 'B' THEN [Amt2] ELSE 0 END",
            table_name='T',
            column_table_map={'Type': 'T', 'Amt1': 'T', 'Amt2': 'T'}
        )
        self.assertIn('SWITCH', result)
        self.assertIn("'T'[Type]", result)

    def test_corr_via_main_converter(self):
        result = convert_tableau_formula_to_dax(
            'CORR([X], [Y])',
            table_name='Data',
            column_table_map={'X': 'Data', 'Y': 'Data'}
        )
        self.assertIn('AVERAGEX', result)
        self.assertIn('DIVIDE', result)

    def test_window_corr_via_main(self):
        result = convert_tableau_formula_to_dax(
            'WINDOW_CORR([Sales], [Profit])',
            table_name='Fact',
            column_table_map={'Sales': 'Fact', 'Profit': 'Fact'}
        )
        self.assertIn('CALCULATE', result)

    def test_running_count_via_main(self):
        # RUNNING_COUNT is in _SIMPLE_FUNCTION_MAP as RUNNING_COUNT( → CALCULATE(
        # so it's handled by simple regex before _convert_running_functions
        result = convert_tableau_formula_to_dax(
            'RUNNING_COUNT(COUNT([ID]))',
            table_name='T',
            column_table_map={'ID': 'T'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('COUNT', result)

    def test_rank_dense_via_main(self):
        result = convert_tableau_formula_to_dax(
            'RANK_DENSE(SUM([Sales]))',
            table_name='T',
            column_table_map={'Sales': 'T'}
        )
        self.assertIn('RANKX', result)
        self.assertIn('DENSE', result)

    def test_rank_percentile_via_main(self):
        result = convert_tableau_formula_to_dax(
            'RANK_PERCENTILE([Score])',
            table_name='T',
            column_table_map={'Score': 'T'}
        )
        self.assertIn('DIVIDE', result)
        self.assertIn('RANKX', result)


if __name__ == '__main__':
    unittest.main()
