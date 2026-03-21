"""
Tests for Sprint 52 — Extraction & DAX Gap Closure.

Covers:
  - VAR/VARP aggregation in M query builder
  - INDEX, LTRIM, RTRIM DAX conversions (already existed - validation tests)
  - Prep flow aggregation mapping for VAR/VARP
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tableau_export.m_query_builder import _M_AGG_MAP
from tableau_export.dax_converter import convert_tableau_formula_to_dax


class TestMQueryAggMapVarVarp(unittest.TestCase):
    """Verify VAR and VARP entries exist in _M_AGG_MAP."""

    def test_var_in_map(self):
        self.assertIn('var', _M_AGG_MAP)
        func_name, m_type = _M_AGG_MAP['var']
        # VAR is now special-cased (None) — variance uses StdDev² in code
        self.assertIsNone(func_name)
        self.assertEqual(m_type, 'type number')

    def test_varp_in_map(self):
        self.assertIn('varp', _M_AGG_MAP)
        func_name, m_type = _M_AGG_MAP['varp']
        # VARP is now special-cased (None) — population variance via custom formula
        self.assertIsNone(func_name)
        self.assertEqual(m_type, 'type number')

    def test_existing_agg_map_entries(self):
        """Ensure common aggregation entries still exist."""
        for key in ('sum', 'avg', 'min', 'max', 'count', 'countd', 'stdev', 'median'):
            self.assertIn(key, _M_AGG_MAP, f"Missing key: {key}")


class TestDaxLtrimRtrim(unittest.TestCase):
    """Verify LTRIM and RTRIM are mapped in DAX converter."""

    def test_ltrim(self):
        result = convert_tableau_formula_to_dax("LTRIM([Name])")
        self.assertIn("TRIM", result.upper())

    def test_rtrim(self):
        result = convert_tableau_formula_to_dax("RTRIM([Name])")
        self.assertIn("TRIM", result.upper())


class TestDaxIndex(unittest.TestCase):
    """Verify INDEX function is handled (mapped to RANKX comment)."""

    def test_index_in_formula(self):
        # INDEX() has no direct DAX equivalent, but should be handled
        result = convert_tableau_formula_to_dax("INDEX()")
        # It should produce some output without error
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


class TestPrepFlowAggMapping(unittest.TestCase):
    """Verify prep flow parser aggregation mappings include VAR/VARP."""

    def test_prep_aggregation_map(self):
        from tableau_export.prep_flow_parser import _PREP_AGG_MAP
        self.assertIn('VAR', _PREP_AGG_MAP)
        self.assertIn('VARP', _PREP_AGG_MAP)
        self.assertEqual(_PREP_AGG_MAP['VAR'], 'var')
        self.assertEqual(_PREP_AGG_MAP['VARP'], 'varp')

    def test_prep_join_map_not_inner(self):
        from tableau_export.prep_flow_parser import _PREP_JOIN_MAP
        self.assertIn('notInner', _PREP_JOIN_MAP)
        self.assertEqual(_PREP_JOIN_MAP['notInner'], 'leftanti')


if __name__ == '__main__':
    unittest.main()
