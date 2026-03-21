"""Tests for gap optimization fixes — Sprint 84b (gap closure).

Covers:
- LTRIM → left-trim only (MID-based)
- RTRIM → right-trim only (LEFT-based)
- INDEX() → ROWNUMBER() (DAX 2024+)
- REGEXP_MATCH: ^literal$ exact match, .+/.* always-true
- REGEXP_MATCH: ^literal$ with special chars
- SPLIT → PATHITEM/SUBSTITUTE (already working)
- Nested LOD regression guard
"""

import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tableau_export.dax_converter import convert_tableau_formula_to_dax


class TestLTRIM(unittest.TestCase):
    """LTRIM → left-trim only (preserves trailing spaces)."""

    def test_ltrim_basic(self):
        result = convert_tableau_formula_to_dax('LTRIM([Name])')
        self.assertIn('MID', result)
        self.assertNotEqual(result, 'TRIM([Name])')

    def test_ltrim_not_trim(self):
        """LTRIM should NOT simply become TRIM."""
        result = convert_tableau_formula_to_dax('LTRIM([Field])')
        # Should contain MID-based pattern, not just TRIM
        self.assertIn('MID', result)

    def test_ltrim_in_expression(self):
        result = convert_tableau_formula_to_dax('LTRIM([Name]) + " suffix"')
        self.assertIn('MID', result)

    def test_ltrim_nested(self):
        result = convert_tableau_formula_to_dax('UPPER(LTRIM([Name]))')
        self.assertIn('MID', result)
        self.assertIn('UPPER', result)


class TestRTRIM(unittest.TestCase):
    """RTRIM → right-trim only (preserves leading spaces)."""

    def test_rtrim_basic(self):
        result = convert_tableau_formula_to_dax('RTRIM([Name])')
        self.assertIn('LEFT', result)
        self.assertNotEqual(result, 'TRIM([Name])')

    def test_rtrim_not_trim(self):
        """RTRIM should NOT simply become TRIM."""
        result = convert_tableau_formula_to_dax('RTRIM([Field])')
        self.assertIn('LEFT', result)

    def test_rtrim_in_expression(self):
        result = convert_tableau_formula_to_dax('RTRIM([Name]) + " suffix"')
        self.assertIn('LEFT', result)

    def test_rtrim_nested(self):
        result = convert_tableau_formula_to_dax('LOWER(RTRIM([Name]))')
        self.assertIn('LEFT', result)
        self.assertIn('LOWER', result)


class TestTRIM_unchanged(unittest.TestCase):
    """Regular TRIM should still work as TRIM."""

    def test_trim_basic(self):
        result = convert_tableau_formula_to_dax('TRIM([Name])')
        self.assertIn('TRIM', result)


class TestIndexROWNUMBER(unittest.TestCase):
    """INDEX() → ROWNUMBER() (DAX 2024+, more accurate than RANKX)."""

    def test_index_basic(self):
        result = convert_tableau_formula_to_dax('INDEX()')
        self.assertIn('ROWNUMBER', result)

    def test_index_comment(self):
        result = convert_tableau_formula_to_dax('INDEX()')
        self.assertIn('INDEX', result)  # comment preserved

    def test_index_in_if(self):
        result = convert_tableau_formula_to_dax('IF INDEX() = 1 THEN "First" ELSE "Other" END')
        self.assertIn('ROWNUMBER', result)
        self.assertIn('IF', result)

    def test_index_divided_by_size(self):
        result = convert_tableau_formula_to_dax('INDEX() / SIZE()')
        self.assertIn('ROWNUMBER', result)
        self.assertIn('COUNTROWS', result)

    def test_index_not_hardcoded_value(self):
        """INDEX() should not reference hardcoded [Value]."""
        result = convert_tableau_formula_to_dax('INDEX()')
        self.assertNotIn('[Value]', result)


class TestRegexpMatchExactMatch(unittest.TestCase):
    """REGEXP_MATCH: ^literal$ → exact equality check."""

    def test_exact_match(self):
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Status], "^Active$")')
        self.assertIn('=', result)
        self.assertIn('Active', result)
        # Should be an exact match, not CONTAINSSTRING
        self.assertNotIn('CONTAINSSTRING', result)

    def test_exact_match_number(self):
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Code], "^ABC123$")')
        self.assertIn('=', result)
        self.assertIn('ABC123', result)

    def test_dot_plus_non_empty(self):
        """REGEXP_MATCH(field, ".+") → LEN(field) > 0 (non-empty check)."""
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Name], ".+")')
        self.assertIn('LEN', result)
        self.assertIn('> 0', result)

    def test_dot_star_any(self):
        """REGEXP_MATCH(field, ".*") → TRUE() (matches any string)."""
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Name], ".*")')
        self.assertIn('TRUE', result)

    def test_caret_dot_star_dollar(self):
        """REGEXP_MATCH(field, "^.*$") → TRUE()."""
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Name], "^.*$")')
        self.assertIn('TRUE', result)

    def test_caret_dot_plus_dollar(self):
        """REGEXP_MATCH(field, "^.+$") → LEN > 0."""
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Name], "^.+$")')
        self.assertIn('LEN', result)

    def test_left_match_still_works(self):
        """Existing ^literal pattern still works."""
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Code], "^ABC")')
        self.assertIn('LEFT', result)
        self.assertIn('ABC', result)

    def test_right_match_still_works(self):
        """Existing literal$ pattern still works."""
        result = convert_tableau_formula_to_dax('REGEXP_MATCH([Code], "xyz$")')
        self.assertIn('RIGHT', result)
        self.assertIn('xyz', result)


class TestSplitPathitem(unittest.TestCase):
    """SPLIT → PATHITEM/SUBSTITUTE (verify it's not BLANK)."""

    def test_split_3_args(self):
        result = convert_tableau_formula_to_dax('SPLIT([Email], "@", 2)')
        self.assertIn('PATHITEM', result)
        self.assertIn('SUBSTITUTE', result)
        self.assertNotIn('BLANK', result)

    def test_split_2_args(self):
        result = convert_tableau_formula_to_dax('SPLIT([Name], " ")')
        self.assertIn('PATHITEM', result)

    def test_split_negative_index(self):
        result = convert_tableau_formula_to_dax('SPLIT([Path], "/", -1)')
        self.assertIn('PATHITEMREVERSE', result)


class TestNestedLOD(unittest.TestCase):
    """Nested LOD expressions: {FIXED ... : {INCLUDE ... : AGG}}."""

    def test_nested_fixed_include(self):
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : {INCLUDE [State] : SUM([Sales])}}',
            table_name='Orders',
            column_table_map={'Region': 'Orders', 'State': 'Orders', 'Sales': 'Orders'}
        )
        # Inner {INCLUDE} should be processed first as CALCULATE
        self.assertIn('CALCULATE', result)
        # Outer {FIXED} should wrap with ALLEXCEPT
        self.assertIn('ALLEXCEPT', result)

    def test_nested_fixed_fixed(self):
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : SUM({FIXED [State] : SUM([Sales])})}',
            table_name='Orders',
            column_table_map={'Region': 'Orders', 'State': 'Orders', 'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)

    def test_single_fixed(self):
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : SUM([Sales])}',
            table_name='Orders',
            column_table_map={'Region': 'Orders', 'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)
        self.assertIn('SUM', result)

    def test_exclude_expression(self):
        result = convert_tableau_formula_to_dax(
            '{EXCLUDE [State] : SUM([Sales])}',
            table_name='Orders',
            column_table_map={'State': 'Orders', 'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('REMOVEFILTERS', result)


if __name__ == '__main__':
    unittest.main()
