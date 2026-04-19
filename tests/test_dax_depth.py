"""
Tests for Sprint 58 — DAX Conversion Depth.

Covers:
  - SPLIT enhancements (positive index, negative index, 2-arg)
  - REVERSE function (CONCATENATEX pattern)
  - REPEAT → REPT mapping
  - MAKEDATE / MAKETIME / MAKEDATETIME (already exist, regression)
  - ISDATE (regression)
  - SPACE / CHAR (regression)
  - ATTR context-aware (measure vs column)
  - SIZE → COUNTROWS
  - Nested aggregation AGG(IF(...)) → AGGX
  - DATEPARSE
  - String concat + → &
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tableau_export.dax_converter import convert_tableau_formula_to_dax


def _dax(formula, **kwargs):
    """Shorthand for formula conversion with sensible defaults."""
    defaults = {
        'column_name': 'Calc',
        'table_name': 'Sales',
        'calc_map': {},
        'param_map': {},
        'column_table_map': {'Profit': 'Sales', 'Revenue': 'Sales', 'Region': 'Sales', 'Name': 'Sales'},
        'measure_names': set(),
        'is_calc_column': False,
    }
    defaults.update(kwargs)
    return convert_tableau_formula_to_dax(formula, **defaults)


class TestSplitEnhancements(unittest.TestCase):
    def test_split_3_args(self):
        result = _dax('SPLIT("a-b-c", "-", 2)')
        self.assertIn('PATHITEM', result)
        self.assertIn('SUBSTITUTE', result)
        self.assertIn('"a-b-c"', result)
        self.assertIn('2', result)

    def test_split_2_args_defaults_to_1(self):
        result = _dax('SPLIT("a-b", "-")')
        self.assertIn('PATHITEM', result)
        self.assertIn(', 1)', result)

    def test_split_negative_index(self):
        result = _dax('SPLIT("a-b-c", "-", -1)')
        self.assertIn('PATHITEMREVERSE', result)
        self.assertIn(', 1)', result)


class TestReverseFunction(unittest.TestCase):
    def test_reverse_string(self):
        result = _dax('REVERSE([Name])')
        self.assertIn('CONCATENATEX', result)
        self.assertIn('GENERATESERIES', result)
        self.assertIn('MID', result)


class TestRepeatFunction(unittest.TestCase):
    def test_repeat_maps_to_rept(self):
        result = _dax('REPEAT("abc", 3)')
        self.assertIn('REPT', result)
        self.assertIn('"abc"', result)
        self.assertIn('3', result)


class TestMakeDateTimeFunctions(unittest.TestCase):
    def test_makedate(self):
        result = _dax('MAKEDATE(2024, 1, 15)')
        self.assertIn('DATE(', result)

    def test_maketime(self):
        result = _dax('MAKETIME(10, 30, 0)')
        self.assertIn('TIME(', result)

    def test_makedatetime(self):
        result = _dax('MAKEDATETIME(2024, 1, 15)')
        self.assertIn('DATE(', result)


class TestIsDate(unittest.TestCase):
    def test_isdate(self):
        result = _dax('ISDATE("2024-01-15")')
        self.assertIn('NOT(ISERROR(DATEVALUE', result)


class TestSpaceChar(unittest.TestCase):
    def test_space(self):
        result = _dax('SPACE(5)')
        self.assertIn('REPT(" "', result)

    def test_char(self):
        result = _dax('CHAR(65)')
        self.assertIn('UNICHAR(', result)


class TestAttrContextAware(unittest.TestCase):
    def test_attr_column(self):
        result = _dax('ATTR([Region])')
        self.assertIn('SELECTEDVALUE', result)

    def test_attr_measure(self):
        result = _dax('ATTR([Revenue])', measure_names={'Revenue'})
        self.assertNotIn('SELECTEDVALUE', result)
        self.assertIn('[Revenue]', result)


class TestSizeFunction(unittest.TestCase):
    def test_size(self):
        result = _dax('SIZE()')
        self.assertIn('COUNTROWS(ALLSELECTED())', result)


class TestAggIfToAggx(unittest.TestCase):
    def test_sum_if(self):
        result = _dax('SUM(IF([Region] = "West", [Profit], 0))')
        self.assertIn('SUMX', result)
        self.assertIn('IF', result)

    def test_avg_if(self):
        result = _dax('AVG(IF([Region] = "West", [Profit], 0))')
        self.assertIn('AVERAGEX', result)


class TestDateparse(unittest.TestCase):
    def test_dateparse_with_format(self):
        result = _dax('DATEPARSE("yyyy-MM-dd", [Name])')
        # DATEPARSE format arg is a parsing hint — output is DATEVALUE, not FORMAT
        self.assertIn('DATEVALUE', result)
        self.assertNotIn('FORMAT', result)

    def test_dateparse_no_format(self):
        result = _dax('DATEPARSE("", [Name])')
        self.assertIn('DATEVALUE', result)


class TestStringConcat(unittest.TestCase):
    def test_plus_to_ampersand(self):
        result = _dax('[Region] + " " + [Name]', calc_datatype='string',
                       is_calc_column=True)
        self.assertIn('&', result)


if __name__ == '__main__':
    unittest.main()
