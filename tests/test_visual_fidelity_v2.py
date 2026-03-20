"""
Tests for Sprint 78 — Visual Fidelity Depth.

Covers: stacked bar orientation, dual-axis → combo chart, reference band
shading, data label formatting, mark size → bubble size, trend line
preservation.
"""

import json
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from tableau_export.extract_tableau_data import TableauExtractor
from powerbi_import import visual_generator as vg


def _make_extractor():
    ext = TableauExtractor.__new__(TableauExtractor)
    ext.workbook_data = {}
    return ext


# ── Stacked Bar Orientation ────────────────────────────────────────

class TestStackedBarOrientation(unittest.TestCase):
    """Tests for _detect_bar_orientation() with stacked variants."""

    def _make_ws_xml(self, cols_text='', rows_text=''):
        """Build a minimal <worksheet> XML element with cols/rows shelves."""
        xml = (f'<worksheet><table>'
               f'<cols>{cols_text}</cols>'
               f'<rows>{rows_text}</rows>'
               f'</table></worksheet>')
        return ET.fromstring(xml)

    def test_stacked_bar_to_column(self):
        ext = _make_extractor()
        ws = self._make_ws_xml(
            cols_text='[OrderDB].[Category]',
            rows_text='[OrderDB].[sum:Sales:qk]')
        result = ext._detect_bar_orientation(ws, 'stackedBarChart')
        self.assertEqual(result, 'stackedColumnChart')

    def test_100pct_stacked_bar_to_column(self):
        ext = _make_extractor()
        ws = self._make_ws_xml(
            cols_text='[OrderDB].[Region]',
            rows_text='[OrderDB].[sum:Amount:qk]')
        result = ext._detect_bar_orientation(ws, 'hundredPercentStackedBarChart')
        self.assertEqual(result, 'hundredPercentStackedColumnChart')

    def test_clustered_bar_to_column(self):
        ext = _make_extractor()
        ws = self._make_ws_xml(
            cols_text='[OrderDB].[Category]',
            rows_text='[OrderDB].[sum:Sales:qk]')
        result = ext._detect_bar_orientation(ws, 'clusteredBarChart')
        self.assertEqual(result, 'clusteredColumnChart')

    def test_bar_stays_bar_when_measure_on_cols(self):
        ext = _make_extractor()
        ws = self._make_ws_xml(
            cols_text='[OrderDB].[sum:Sales:qk]',
            rows_text='[OrderDB].[Category]')
        result = ext._detect_bar_orientation(ws, 'stackedBarChart')
        self.assertEqual(result, 'stackedBarChart')

    def test_clustered_bar_stays_when_no_shelf_pattern(self):
        ext = _make_extractor()
        ws = self._make_ws_xml(cols_text='', rows_text='')
        result = ext._detect_bar_orientation(ws, 'clusteredBarChart')
        self.assertEqual(result, 'clusteredBarChart')


# ── Dual-Axis → Combo Chart ───────────────────────────────────────

class TestDualAxisComboChart(unittest.TestCase):
    """Tests for dual-axis detection in create_visual_container()."""

    def _container(self, axes_data=None, visual_type='bar'):
        ws = {
            'name': 'Sheet1',
            'visualType': visual_type,
            'fields': ['Category', 'SUM(Sales)'],
            'mark_type': visual_type,
            'axes': axes_data or {},
            'mark_encoding': {},
            'filters': [],
        }
        return vg.create_visual_container(ws)

    def test_dual_axis_sets_combo_type(self):
        c = self._container(axes_data={'dual_axis': True})
        self.assertEqual(c['visual']['visualType'],
                         'lineClusteredColumnComboChart')

    def test_no_dual_axis_keeps_original(self):
        c = self._container(axes_data={})
        self.assertNotEqual(c['visual']['visualType'],
                            'lineClusteredColumnComboChart')


# ── Reference Band Shading ────────────────────────────────────────

class TestReferenceBandShading(unittest.TestCase):
    """Tests for reference band rendering in _apply_visual_decorations()."""

    def _decorate(self, reference_lines):
        ws = {
            'name': 'S1',
            'referenceLines': reference_lines,
            'reference_lines': reference_lines,
            'mark_encoding': {},
            'axes': {},
        }
        visual_obj = {}
        vg._apply_visual_decorations(ws, 'bar', 'clusteredBarChart', 'S1', {}, visual_obj)
        return visual_obj

    def test_band_has_start_and_end(self):
        obj = self._decorate([{
            'type': 'band',
            'values': [40, 80],
            'color': '#AABBCC',
        }])
        bands = obj.get('objects', {}).get('referenceBand', [])
        self.assertEqual(len(bands), 1)

    def test_band_color(self):
        obj = self._decorate([{
            'type': 'band',
            'values': [0, 100],
            'color': '#FF0000',
            'opacity': 0.5,
        }])
        bands = obj.get('objects', {}).get('referenceBand', [])
        self.assertEqual(len(bands), 1)
        props = bands[0].get('properties', {})
        self.assertIn('#FF0000', str(props))

    def test_line_not_treated_as_band(self):
        obj = self._decorate([{
            'type': 'constant',
            'value': 50,
        }])
        bands = obj.get('objects', {}).get('referenceBand', [])
        self.assertEqual(len(bands), 0)


# ── Data Label Formatting ─────────────────────────────────────────

class TestDataLabelFormatting(unittest.TestCase):
    """Tests for data label formatting from mark_encoding."""

    def _decorate(self, mark_encoding):
        ws = {
            'name': 'S1',
            'referenceLines': [],
            'reference_lines': [],
            'mark_encoding': mark_encoding,
            'axes': {},
        }
        visual_obj = {}
        vg._apply_visual_decorations(ws, 'bar', 'clusteredBarChart', 'S1', {}, visual_obj)
        return visual_obj

    def test_label_enabled(self):
        obj = self._decorate({'label': {'show': True, 'text': 'SUM(Sales)'}})
        self.assertIn('labels', obj.get('objects', {}))

    def test_label_font_size(self):
        obj = self._decorate({'label': {'show': True, 'font_size': 14}})
        labels = obj.get('objects', {}).get('labels', [{}])
        props = labels[0].get('properties', {})
        self.assertIn('fontSize', str(props))

    def test_label_font_color(self):
        obj = self._decorate({'label': {'show': True, 'font_color': '#333333'}})
        labels = obj.get('objects', {}).get('labels', [{}])
        props = labels[0].get('properties', {})
        self.assertIn('#333333', str(props))

    def test_label_position_top(self):
        obj = self._decorate({'label': {'show': True, 'position': 'top'}})
        labels = obj.get('objects', {}).get('labels', [{}])
        props = labels[0].get('properties', {})
        self.assertIn('OutsideEnd', str(props))

    def test_label_position_center(self):
        obj = self._decorate({'label': {'show': True, 'position': 'center'}})
        labels = obj.get('objects', {}).get('labels', [{}])
        props = labels[0].get('properties', {})
        self.assertIn('InsideCenter', str(props))

    def test_no_label_encoding(self):
        obj = self._decorate({})
        self.assertNotIn('labels', obj.get('objects', {}))


# ── Trend Line Preservation ───────────────────────────────────────

class TestTrendLinePreservation(unittest.TestCase):
    """Tests for trend line → PBI trend configuration."""

    def _decorate_trend(self, trend_lines):
        ws = {
            'name': 'S1',
            'referenceLines': [],
            'reference_lines': [],
            'mark_encoding': {},
            'trendLines': trend_lines,
            'trend_lines': trend_lines,
            'axes': {},
        }
        visual_obj = {}
        vg._apply_visual_decorations(ws, 'line', 'lineChart', 'S1', {}, visual_obj)
        return visual_obj

    def test_linear_trend(self):
        obj = self._decorate_trend([{'regression_type': 'linear'}])
        self.assertIn('trend', obj.get('objects', {}))

    def test_exponential_trend(self):
        obj = self._decorate_trend([{'regression_type': 'exponential'}])
        trend = obj.get('objects', {}).get('trend', [{}])
        props = trend[0].get('properties', {})
        self.assertIn('Exponential', str(props))

    def test_polynomial_trend(self):
        obj = self._decorate_trend([{'regression_type': 'polynomial', 'order': 3}])
        trend = obj.get('objects', {}).get('trend', [{}])
        props = trend[0].get('properties', {})
        self.assertIn('Polynomial', str(props))
        self.assertIn('polynomialOrder', str(props))

    def test_no_trend_lines(self):
        obj = self._decorate_trend([])
        self.assertNotIn('trend', obj.get('objects', {}))


# ── Mark Size → Bubble Size ───────────────────────────────────────

class TestMarkSizeBubble(unittest.TestCase):
    """Tests for mark_encoding.size → PBI bubbles configuration."""

    def _decorate(self, pbi_type, mark_encoding):
        ws = {
            'name': 'S1',
            'referenceLines': [],
            'reference_lines': [],
            'mark_encoding': mark_encoding,
            'axes': {},
        }
        visual_obj = {}
        vg._apply_visual_decorations(ws, 'circle', pbi_type, 'S1', {}, visual_obj)
        return visual_obj

    def test_scatter_gets_bubbles(self):
        obj = self._decorate('scatterChart', {'size': {'field': 'Profit'}})
        self.assertIn('bubbles', obj.get('objects', {}))

    def test_non_scatter_no_bubbles(self):
        obj = self._decorate('lineChart', {'size': {'field': 'Profit'}})
        self.assertNotIn('bubbles', obj.get('objects', {}))

    def test_no_size_encoding(self):
        obj = self._decorate('scatterChart', {})
        self.assertNotIn('bubbles', obj.get('objects', {}))


# ── Y2 Axis for Combo Charts ──────────────────────────────────────

class TestY2AxisComboChart(unittest.TestCase):
    """Tests for secondary axis (valueAxis2) in combo charts."""

    def _decorate(self, axes_data, pbi_type='lineClusteredColumnComboChart'):
        ws = {
            'name': 'S1',
            'referenceLines': [],
            'reference_lines': [],
            'mark_encoding': {},
            'axes': axes_data,
        }
        visual_obj = {}
        vg._apply_visual_decorations(ws, 'bar', pbi_type, 'S1', {}, visual_obj)
        return visual_obj

    def test_y2_axis_present(self):
        obj = self._decorate({'dual_axis': True, 'dual_axis_sync': False})
        self.assertIn('valueAxis2', obj.get('objects', {}))

    def test_no_y2_when_not_combo(self):
        obj = self._decorate({'dual_axis': True}, pbi_type='lineChart')
        self.assertNotIn('valueAxis2', obj.get('objects', {}))


if __name__ == '__main__':
    unittest.main()
