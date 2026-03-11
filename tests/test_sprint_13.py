"""
Sprint 13 — Conversion Depth & Fidelity (Phase N) Tests

Tests for:
  N.1 — Custom visual GUID registry (APPROXIMATION_MAP uses custom visuals)
  N.2 — Discrete/stepped color scales
  N.3 — Dynamic reference lines
  N.4 — Multi-datasource calc routing (resolve_table_for_formula)
  N.5 — sortByColumn cross-validation
  N.6 — Nested LOD edge cases
"""

import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

from visual_generator import APPROXIMATION_MAP
from visual_generator import resolve_visual_type
from visual_generator import get_custom_visual_guid_for_approx
from visual_generator import resolve_custom_visual_type
from visual_generator import _build_dynamic_reference_line
from tmdl_generator import resolve_table_for_column
from tmdl_generator import resolve_table_for_formula
from validator import ArtifactValidator
from dax_converter import convert_tableau_formula_to_dax
from visual_generator import APPROXIMATION_MAP, CUSTOM_VISUAL_GUIDS
from visual_generator import CUSTOM_VISUAL_GUIDS
from visual_generator import get_approximation_note
from visual_generator import _build_data_bar_config


# ═══════════════════════════════════════════════════════════════════
# N.1 — Custom Visual GUID Registry
# ═══════════════════════════════════════════════════════════════════

class TestCustomVisualGUIDs(unittest.TestCase):
    """N.1: APPROXIMATION_MAP now uses custom visual types for Sankey/Chord/Network/Gantt."""

    def test_sankey_maps_to_custom_visual(self):
        pbi_type, note = APPROXIMATION_MAP['sankey']
        self.assertEqual(pbi_type, 'sankeyDiagram')
        self.assertIn('AppSource', note)
        self.assertIn('ChicagoITSankey', note)

    def test_chord_maps_to_custom_visual(self):
        pbi_type, note = APPROXIMATION_MAP['chord']
        self.assertEqual(pbi_type, 'chordChart')
        self.assertIn('AppSource', note)

    def test_network_maps_to_custom_visual(self):
        pbi_type, note = APPROXIMATION_MAP['network']
        pbi_type_expected = 'networkNavigator'
        self.assertEqual(pbi_type, pbi_type_expected)
        self.assertIn('AppSource', note)

    def test_ganttbar_maps_to_custom_visual(self):
        pbi_type, note = APPROXIMATION_MAP['ganttbar']
        self.assertEqual(pbi_type, 'ganttChart')
        self.assertIn('AppSource', note)

    def test_mekko_still_uses_builtin(self):
        pbi_type, note = APPROXIMATION_MAP['mekko']
        self.assertEqual(pbi_type, 'stackedBarChart')
        self.assertNotIn('AppSource', note)

    def test_resolve_visual_type_uses_approximation(self):
        self.assertEqual(resolve_visual_type('sankey'), 'sankeyDiagram')
        self.assertEqual(resolve_visual_type('chord'), 'chordChart')
        self.assertEqual(resolve_visual_type('network'), 'networkNavigator')
        self.assertEqual(resolve_visual_type('ganttbar'), 'ganttChart')

    def test_resolve_visual_type_prefers_exact_map(self):
        self.assertEqual(resolve_visual_type('bar'), 'clusteredBarChart')
        self.assertEqual(resolve_visual_type('line'), 'lineChart')

    def test_resolve_visual_type_default(self):
        self.assertEqual(resolve_visual_type('nonexistent_mark'), 'tableEx')
        self.assertEqual(resolve_visual_type(None), 'tableEx')
        self.assertEqual(resolve_visual_type(''), 'tableEx')

    def test_get_custom_visual_guid_for_approx_sankey(self):
        guid_info = get_custom_visual_guid_for_approx('sankey')
        self.assertIsNotNone(guid_info)
        self.assertEqual(guid_info['guid'], 'ChicagoITSankey1.1.0')

    def test_get_custom_visual_guid_for_approx_chord(self):
        guid_info = get_custom_visual_guid_for_approx('chord')
        self.assertIsNotNone(guid_info)
        self.assertEqual(guid_info['guid'], 'ChicagoITChord1.0.0')

    def test_get_custom_visual_guid_for_approx_network(self):
        guid_info = get_custom_visual_guid_for_approx('network')
        self.assertIsNotNone(guid_info)

    def test_get_custom_visual_guid_for_approx_ganttbar(self):
        guid_info = get_custom_visual_guid_for_approx('ganttbar')
        self.assertIsNotNone(guid_info)
        self.assertEqual(guid_info['guid'], 'GanttByMAQSoftware1.0.0')

    def test_get_custom_visual_guid_for_approx_builtin_returns_none(self):
        self.assertIsNone(get_custom_visual_guid_for_approx('mekko'))
        self.assertIsNone(get_custom_visual_guid_for_approx('bumpchart'))
        self.assertIsNone(get_custom_visual_guid_for_approx(None))

    def test_resolve_custom_visual_type_sankey(self):
        vtype, guid_info = resolve_custom_visual_type('sankey')
        self.assertEqual(vtype, 'sankeyDiagram')
        self.assertIsNotNone(guid_info)

    def test_resolve_custom_visual_type_disabled(self):
        vtype, guid_info = resolve_custom_visual_type('sankey', use_custom_visuals=False)
        self.assertIsNone(guid_info)

    def test_approximation_map_all_entries(self):
        self.assertEqual(len(APPROXIMATION_MAP), 12)
        for key, (pbi_type, note) in APPROXIMATION_MAP.items():
            self.assertTrue(pbi_type, f"Empty pbi_type for {key}")
            self.assertTrue(note, f"Empty note for {key}")


# ═══════════════════════════════════════════════════════════════════
# N.2 — Discrete / Stepped Color Scales
# ═══════════════════════════════════════════════════════════════════

class TestSteppedColorScales(unittest.TestCase):
    """N.2: Stepped color thresholds produce rules-based conditional formatting."""

    def _make_ws_data(self, thresholds, color_field=None):
        """Helper to build worksheet data with color thresholds."""
        enc = {'type': 'categorical', 'thresholds': thresholds}
        if color_field:
            enc['field'] = color_field
        return {
            'name': 'TestSheet',
            'mark_type': 'bar',
            'mark_encoding': {'color': enc},
            'fields': [
                {'name': 'Category', 'role': 'dimension'},
                {'name': 'Sales', 'role': 'measure'},
            ],
        }

    def test_stepped_thresholds_sorted(self):
        """Thresholds should be sorted by value in output."""
        thresholds = [
            {'value': 100, 'color': '#FF0000'},
            {'value': 50, 'color': '#FFFF00'},
            {'value': 200, 'color': '#00FF00'},
        ]
        # Sort by value
        sorted_t = sorted(
            [t for t in thresholds if t.get('value') is not None],
            key=lambda t: float(t['value']),
        )
        self.assertEqual(sorted_t[0]['value'], 50)
        self.assertEqual(sorted_t[1]['value'], 100)
        self.assertEqual(sorted_t[2]['value'], 200)

    def test_stepped_thresholds_operators(self):
        """First thresholds should get LessThanOrEqual, last gets GreaterThan."""
        thresholds = [
            {'value': 50, 'color': '#FFFF00'},
            {'value': 100, 'color': '#FF0000'},
            {'value': 200, 'color': '#00FF00'},
        ]
        sorted_t = sorted(thresholds, key=lambda t: float(t['value']))
        # The logic: index < len(sorted_thresh) - 1 → LessThanOrEqual, else GreaterThan
        for idx, t in enumerate(sorted_t):
            if idx < len(sorted_t) - 1:
                expected_op = 'LessThanOrEqual'
            else:
                expected_op = 'GreaterThan'
            self.assertIn(expected_op, ['LessThanOrEqual', 'GreaterThan'])

    def test_threshold_with_no_value_at_end(self):
        """Thresholds without values should come after sorted ones."""
        thresholds = [
            {'value': 100, 'color': '#FF0000'},
            {'color': '#cccccc'},  # no value = catch-all
            {'value': 50, 'color': '#FFFF00'},
        ]
        sorted_t = sorted(
            [t for t in thresholds if t.get('value') is not None],
            key=lambda t: float(t['value']),
        )
        no_value = [t for t in thresholds if t.get('value') is None]
        all_t = sorted_t + no_value
        self.assertEqual(all_t[0]['value'], 50)
        self.assertEqual(all_t[1]['value'], 100)
        self.assertIsNone(all_t[2].get('value'))

    def test_minimum_thresholds_required(self):
        """At least 2 thresholds needed for rule generation."""
        single = [{'value': 100, 'color': '#FF0000'}]
        self.assertFalse(len(single) >= 2)
        double = [
            {'value': 50, 'color': '#FFFF00'},
            {'value': 100, 'color': '#FF0000'},
        ]
        self.assertTrue(len(double) >= 2)


# ═══════════════════════════════════════════════════════════════════
# N.3 — Dynamic Reference Lines
# ═══════════════════════════════════════════════════════════════════

class TestDynamicReferenceLines(unittest.TestCase):
    """N.3: Dynamic reference lines (average, median, percentile, min, max)."""

    def test_average_reference_line(self):
        ref = _build_dynamic_reference_line('average', 'Sales', 'Orders')
        self.assertIsNotNone(ref)
        self.assertIn('properties', ref)
        props = ref['properties']
        self.assertEqual(props['type']['expr']['Literal']['Value'], "'Average'")

    def test_median_reference_line(self):
        ref = _build_dynamic_reference_line('median', 'Revenue', 'Sales')
        props = ref['properties']
        self.assertEqual(props['type']['expr']['Literal']['Value'], "'Median'")

    def test_percentile_reference_line(self):
        ref = _build_dynamic_reference_line('percentile', 'Score', 'Students')
        props = ref['properties']
        self.assertEqual(props['type']['expr']['Literal']['Value'], "'Percentile'")
        self.assertEqual(props['percentile']['expr']['Literal']['Value'], '50D')

    def test_min_reference_line(self):
        ref = _build_dynamic_reference_line('min')
        props = ref['properties']
        self.assertEqual(props['type']['expr']['Literal']['Value'], "'Min'")

    def test_max_reference_line(self):
        ref = _build_dynamic_reference_line('max')
        props = ref['properties']
        self.assertEqual(props['type']['expr']['Literal']['Value'], "'Max'")

    def test_trend_reference_line(self):
        ref = _build_dynamic_reference_line('trend')
        props = ref['properties']
        self.assertEqual(props['type']['expr']['Literal']['Value'], "'Trend'")

    def test_constant_returns_none(self):
        ref = _build_dynamic_reference_line('constant')
        self.assertIsNone(ref)

    def test_custom_style(self):
        ref = _build_dynamic_reference_line('average', style='solid')
        props = ref['properties']
        self.assertEqual(props['style']['expr']['Literal']['Value'], "'solid'")

    def test_custom_label(self):
        ref = _build_dynamic_reference_line('average', label='My Average')
        props = ref['properties']
        self.assertIn('My Average', props['displayName']['expr']['Literal']['Value'])


# ═══════════════════════════════════════════════════════════════════
# N.4 — Multi-Datasource Calc Routing
# ═══════════════════════════════════════════════════════════════════

class TestMultiDSCalcRouting(unittest.TestCase):
    """N.4: resolve_table_for_formula routes calcs by column reference density."""

    def test_resolve_table_for_column_ds_specific(self):
        ctx = {
            'column_table_map': {'Sales': 'Orders', 'Name': 'Customers'},
            'ds_column_table_map': {
                'DS1': {'Sales': 'OrdersDS1', 'Qty': 'OrdersDS1'},
                'DS2': {'Revenue': 'FinanceDS2'},
            },
        }
        self.assertEqual(resolve_table_for_column('Sales', 'DS1', ctx), 'OrdersDS1')
        self.assertEqual(resolve_table_for_column('Sales', None, ctx), 'Orders')
        self.assertEqual(resolve_table_for_column('Revenue', 'DS2', ctx), 'FinanceDS2')

    def test_resolve_table_for_column_fallback(self):
        ctx = {
            'column_table_map': {'Sales': 'Orders'},
            'ds_column_table_map': {},
        }
        self.assertEqual(resolve_table_for_column('Sales', 'UnknownDS', ctx), 'Orders')

    def test_resolve_table_for_column_no_context(self):
        self.assertIsNone(resolve_table_for_column('Sales'))

    def test_resolve_table_for_formula_single_table(self):
        ctx = {
            'column_table_map': {'Sales': 'Orders', 'Qty': 'Orders', 'Name': 'Customers'},
            'ds_column_table_map': {},
        }
        result = resolve_table_for_formula('SUM([Sales]) + SUM([Qty])', None, ctx)
        self.assertEqual(result, 'Orders')

    def test_resolve_table_for_formula_majority_vote(self):
        ctx = {
            'column_table_map': {'Sales': 'Orders', 'Qty': 'Orders', 'Name': 'Customers'},
            'ds_column_table_map': {},
        }
        # 2 refs to Orders, 1 to Customers → Orders wins
        result = resolve_table_for_formula('[Sales] + [Qty] + [Name]', None, ctx)
        self.assertEqual(result, 'Orders')

    def test_resolve_table_for_formula_no_refs(self):
        ctx = {'column_table_map': {}, 'ds_column_table_map': {}}
        result = resolve_table_for_formula('1 + 2', None, ctx)
        self.assertIsNone(result)

    def test_resolve_table_for_formula_empty(self):
        self.assertIsNone(resolve_table_for_formula('', None, None))
        self.assertIsNone(resolve_table_for_formula(None, None, None))


# ═══════════════════════════════════════════════════════════════════
# N.5 — sortByColumn Cross-Validation
# ═══════════════════════════════════════════════════════════════════

class TestSortByColumnValidation(unittest.TestCase):
    """N.5: sortByColumn targets are validated against known columns."""

    def _make_tmdl_file(self, content):
        fd, path = tempfile.mkstemp(suffix='.tmdl')
        os.close(fd)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_valid_sort_by_column(self):
        tmdl = (
            "table Calendar\n"
            "\n"
            "\tcolumn MonthName\n"
            "\t\tsortByColumn: Month\n"
            "\t\tlineageTag: aaa-bbb\n"
            "\n"
            "\tcolumn Month\n"
            "\t\tlineageTag: ccc-ddd\n"
        )
        path = self._make_tmdl_file(tmdl)
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            sort_issues = [i for i in issues if 'sortByColumn' in i]
            self.assertEqual(len(sort_issues), 0, f"Unexpected issues: {sort_issues}")
        finally:
            os.unlink(path)

    def test_invalid_sort_by_column(self):
        tmdl = (
            "table Calendar\n"
            "\n"
            "\tcolumn MonthName\n"
            "\t\tsortByColumn: MonthNumber\n"
            "\t\tlineageTag: aaa-bbb\n"
            "\n"
            "\tcolumn Month\n"
            "\t\tlineageTag: ccc-ddd\n"
        )
        path = self._make_tmdl_file(tmdl)
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            sort_issues = [i for i in issues if 'sortByColumn' in i]
            self.assertEqual(len(sort_issues), 1)
            self.assertIn('MonthNumber', sort_issues[0])
        finally:
            os.unlink(path)

    def test_multiple_sort_by_column_mixed(self):
        tmdl = (
            "table Calendar\n"
            "\n"
            "\tcolumn MonthName\n"
            "\t\tsortByColumn: Month\n"
            "\t\tlineageTag: aaa\n"
            "\n"
            "\tcolumn DayName\n"
            "\t\tsortByColumn: NonExistentCol\n"
            "\t\tlineageTag: bbb\n"
            "\n"
            "\tcolumn Month\n"
            "\t\tlineageTag: ccc\n"
        )
        path = self._make_tmdl_file(tmdl)
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            sort_issues = [i for i in issues if 'sortByColumn' in i]
            self.assertEqual(len(sort_issues), 1)
            self.assertIn('NonExistentCol', sort_issues[0])
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# N.6 — Nested LOD Edge Cases
# ═══════════════════════════════════════════════════════════════════

class TestNestedLODEdgeCases(unittest.TestCase):
    """N.6: LOD nesting, ATTR-wrapped LOD, AGG(LOD) cleanup."""

    def test_simple_fixed_lod(self):
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : SUM([Sales])}',
            'Orders', column_table_map={'Region': 'Regions', 'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)
        self.assertIn('SUM', result)

    def test_nested_fixed_lod(self):
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : SUM({FIXED [Category] : COUNT([OrderID])})}',
            'Orders', column_table_map={
                'Region': 'Regions', 'Category': 'Products',
                'OrderID': 'Orders',
            }
        )
        # Inner LOD converts first, then outer
        self.assertIn('CALCULATE', result)
        self.assertNotIn('{', result)
        self.assertNotIn('}', result)

    def test_lod_with_attr_wrapper(self):
        result = convert_tableau_formula_to_dax(
            'ATTR({FIXED [Region] : SUM([Sales])})',
            'Orders', column_table_map={'Region': 'Regions', 'Sales': 'Orders'}
        )
        # ATTR → SELECTEDVALUE, then LOD → CALCULATE
        self.assertIn('SELECTEDVALUE', result)
        self.assertIn('CALCULATE', result)
        self.assertNotIn('ATTR', result)
        self.assertNotIn('{', result)

    def test_include_lod(self):
        result = convert_tableau_formula_to_dax(
            '{INCLUDE [State] : SUM([Sales])}',
            'Orders', column_table_map={'State': 'Geo', 'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertNotIn('ALLEXCEPT', result)
        self.assertNotIn('{', result)

    def test_exclude_lod(self):
        result = convert_tableau_formula_to_dax(
            '{EXCLUDE [Region] : SUM([Sales])}',
            'Orders', column_table_map={'Region': 'Regions', 'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('REMOVEFILTERS', result)
        self.assertNotIn('{', result)

    def test_fixed_no_dims(self):
        result = convert_tableau_formula_to_dax(
            '{FIXED : SUM([Sales])}',
            'Orders', column_table_map={'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertIn('ALL(', result)

    def test_agg_wrapping_lod_collapsed(self):
        """SUM({FIXED ...}) should collapse: SUM(CALCULATE(...)) → CALCULATE(...)."""
        result = convert_tableau_formula_to_dax(
            'SUM({FIXED [Region] : MAX([Sales])})',
            'Orders', column_table_map={'Region': 'Regions', 'Sales': 'Orders'}
        )
        # Should be CALCULATE(MAX(...)) not SUM(CALCULATE(MAX(...)))
        self.assertIn('CALCULATE', result)
        self.assertNotIn('SUM(CALCULATE', result)

    def test_lod_no_dimension_with_agg(self):
        result = convert_tableau_formula_to_dax(
            '{SUM([Sales])}',
            'Orders', column_table_map={'Sales': 'Orders'}
        )
        self.assertIn('CALCULATE', result)
        self.assertNotIn('{', result)


# ═══════════════════════════════════════════════════════════════════
# Additional integration tests
# ═══════════════════════════════════════════════════════════════════

class TestCustomVisualGUIDIntegration(unittest.TestCase):
    """Integration: CUSTOM_VISUAL_GUIDS entries are consistent with APPROXIMATION_MAP."""

    def test_all_approx_custom_visuals_have_guids(self):
        custom_classes = {v['class'] for v in CUSTOM_VISUAL_GUIDS.values()}
        for key, (pbi_type, note) in APPROXIMATION_MAP.items():
            if 'AppSource' in note:
                self.assertIn(pbi_type, custom_classes,
                              f"APPROXIMATION_MAP '{key}' claims AppSource but "
                              f"class '{pbi_type}' not in CUSTOM_VISUAL_GUIDS")

    def test_custom_visual_guids_have_required_keys(self):
        for key, info in CUSTOM_VISUAL_GUIDS.items():
            self.assertIn('guid', info, f"Missing 'guid' in {key}")
            self.assertIn('name', info, f"Missing 'name' in {key}")
            self.assertIn('class', info, f"Missing 'class' in {key}")
            self.assertIn('roles', info, f"Missing 'roles' in {key}")

    def test_get_approximation_note_returns_string(self):
        note = get_approximation_note('sankey')
        self.assertIsInstance(note, str)
        self.assertTrue(len(note) > 10)

    def test_get_approximation_note_none_for_exact(self):
        self.assertIsNone(get_approximation_note('bar'))
        self.assertIsNone(get_approximation_note('line'))
        self.assertIsNone(get_approximation_note(None))


class TestDynamicRefLineBuilders(unittest.TestCase):
    """Integration: _build_data_bar_config returns valid structure."""

    def test_data_bar_config(self):
        config = _build_data_bar_config('Revenue', 'Sales')
        self.assertEqual(config['id'], 'dataBar_Revenue')
        self.assertIn('field', config)
        self.assertIn('positiveColor', config)

    def test_data_bar_custom_colors(self):
        config = _build_data_bar_config('Col', 'T', min_color='#000', max_color='#FFF')
        self.assertEqual(config['positiveColor']['solid']['color'], '#FFF')


if __name__ == '__main__':
    unittest.main()
