"""
Tests for Sprint 79 — Conditional Formatting & Theme Depth.

Covers: diverging 3-stop gradient, sequential 2-stop gradient, stepped
color from thresholds, categorical color assignment, theme font mapping,
theme background/border/foreground, assessment formatting coverage metric.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from powerbi_import import visual_generator as vg
from powerbi_import.tmdl_generator import generate_theme_json
from powerbi_import.assessment import _check_visuals


# ── Diverging 3-Stop Gradient ─────────────────────────────────────

class TestDivergingGradient(unittest.TestCase):
    """Tests for 3-stop linearGradient3 from quantitative color encoding."""

    def _decorate(self, color_encoding):
        ws = {
            'name': 'S1',
            'referenceLines': [],
            'reference_lines': [],
            'mark_encoding': {'color': color_encoding},
            'axes': {},
        }
        visual_obj = {}
        vg._apply_visual_decorations(ws, 'bar', 'clusteredBarChart', 'S1', {}, visual_obj)
        return visual_obj

    def test_three_stop_gradient(self):
        obj = self._decorate({
            'type': 'quantitative',
            'palette_colors': ['#FF0000', '#FFFFFF', '#0000FF'],
        })
        dp = obj.get('objects', {}).get('dataPoint', [{}])
        fill = dp[0].get('properties', {}).get('fillRule', {})
        self.assertIn('linearGradient3', fill)
        grad = fill['linearGradient3']
        self.assertEqual(grad['min']['color'], '#FF0000')
        self.assertEqual(grad['mid']['color'], '#FFFFFF')
        self.assertEqual(grad['max']['color'], '#0000FF')

    def test_four_colors_uses_first_mid_last(self):
        obj = self._decorate({
            'type': 'quantitative',
            'palette_colors': ['#A', '#B', '#C', '#D'],
        })
        dp = obj.get('objects', {}).get('dataPoint', [{}])
        fill = dp[0].get('properties', {}).get('fillRule', {})
        self.assertIn('linearGradient3', fill)
        grad = fill['linearGradient3']
        self.assertEqual(grad['min']['color'], '#A')
        self.assertEqual(grad['max']['color'], '#D')


# ── Sequential 2-Stop Gradient ────────────────────────────────────

class TestSequentialGradient(unittest.TestCase):
    """Tests for 2-stop linearGradient2."""

    def _decorate(self, color_encoding):
        ws = {
            'name': 'S1',
            'referenceLines': [],
            'reference_lines': [],
            'mark_encoding': {'color': color_encoding},
            'axes': {},
        }
        visual_obj = {}
        vg._apply_visual_decorations(ws, 'bar', 'clusteredBarChart', 'S1', {}, visual_obj)
        return visual_obj

    def test_two_stop_gradient(self):
        obj = self._decorate({
            'type': 'quantitative',
            'palette_colors': ['#FFFFFF', '#0000FF'],
        })
        dp = obj.get('objects', {}).get('dataPoint', [{}])
        fill = dp[0].get('properties', {}).get('fillRule', {})
        self.assertIn('linearGradient2', fill)
        grad = fill['linearGradient2']
        self.assertEqual(grad['min']['color'], '#FFFFFF')
        self.assertEqual(grad['max']['color'], '#0000FF')

    def test_single_color_no_gradient(self):
        obj = self._decorate({
            'type': 'quantitative',
            'palette_colors': ['#FF0000'],
        })
        dp = obj.get('objects', {}).get('dataPoint', [{}])
        props = dp[0].get('properties', {}) if dp else {}
        fill = props.get('fillRule', {})
        self.assertNotIn('linearGradient2', fill)
        self.assertNotIn('linearGradient3', fill)


# ── Stepped Color from Thresholds ─────────────────────────────────

class TestSteppedColor(unittest.TestCase):
    """Tests for steppedColor from threshold-based encoding."""

    def _decorate(self, color_encoding):
        ws = {
            'name': 'S1',
            'referenceLines': [],
            'reference_lines': [],
            'mark_encoding': {'color': color_encoding},
            'axes': {},
        }
        visual_obj = {}
        vg._apply_visual_decorations(ws, 'bar', 'clusteredBarChart', 'S1', {}, visual_obj)
        return visual_obj

    def test_thresholds_produce_steps(self):
        obj = self._decorate({
            'type': 'quantitative',
            'thresholds': [
                {'value': 0, 'color': '#FF0000'},
                {'value': 50, 'color': '#FFFF00'},
                {'value': 100, 'color': '#00FF00'},
            ],
        })
        dp = obj.get('objects', {}).get('dataPoint', [{}])
        fill = dp[0].get('properties', {}).get('fillRule', {})
        self.assertIn('steppedColor', fill)
        self.assertEqual(len(fill['steppedColor']['steps']), 3)

    def test_threshold_values(self):
        obj = self._decorate({
            'type': 'quantitative',
            'thresholds': [
                {'value': 10, 'color': '#A'},
                {'value': 90, 'color': '#B'},
            ],
        })
        dp = obj.get('objects', {}).get('dataPoint', [{}])
        fill = dp[0].get('properties', {}).get('fillRule', {})
        steps = fill['steppedColor']['steps']
        self.assertEqual(steps[0]['inputValue'], 10)
        self.assertEqual(steps[0]['color'], '#A')
        self.assertEqual(steps[1]['inputValue'], 90)


# ── Categorical Color Assignment ──────────────────────────────────

class TestCategoricalColor(unittest.TestCase):
    """Tests for per-category sentimentColors from categorical encoding."""

    def _decorate(self, color_encoding):
        ws = {
            'name': 'S1',
            'referenceLines': [],
            'reference_lines': [],
            'mark_encoding': {'color': color_encoding},
            'axes': {},
        }
        visual_obj = {}
        vg._apply_visual_decorations(ws, 'bar', 'clusteredBarChart', 'S1', {}, visual_obj)
        return visual_obj

    def test_categorical_colors(self):
        obj = self._decorate({
            'type': 'categorical',
            'palette_colors': ['#FF0000', '#0000FF'],
        })
        sent = obj.get('objects', {}).get('sentimentColors', [])
        self.assertTrue(len(sent) > 0)

    def test_empty_categorical_no_sentiment(self):
        obj = self._decorate({
            'type': 'categorical',
            'palette_colors': [],
        })
        self.assertNotIn('sentimentColors', obj.get('objects', {}))


# ── Theme Font Mapping ─────────────────────────────────────────────

class TestThemeFontMapping(unittest.TestCase):
    """Tests for Tableau → web-safe font mapping in generate_theme_json()."""

    def test_tableau_book_to_segoe_ui(self):
        theme = generate_theme_json({'font_family': 'Tableau Book'})
        self.assertIn('Segoe UI', json.dumps(theme))

    def test_tableau_light_to_segoe_ui_light(self):
        theme = generate_theme_json({'font_family': 'Tableau Light'})
        self.assertIn('Segoe UI Light', json.dumps(theme))

    def test_tableau_semibold_to_segoe_ui_semibold(self):
        theme = generate_theme_json({'font_family': 'Tableau Semibold'})
        self.assertIn('Segoe UI Semibold', json.dumps(theme))

    def test_tableau_bold_to_segoe_ui_bold(self):
        theme = generate_theme_json({'font_family': 'Tableau Bold'})
        self.assertIn('Segoe UI Bold', json.dumps(theme))

    def test_unknown_font_passthrough(self):
        theme = generate_theme_json({'font_family': 'Comic Sans MS'})
        self.assertIn('Comic Sans MS', json.dumps(theme))

    def test_benton_sans_to_segoe_ui(self):
        theme = generate_theme_json({'font_family': 'Benton Sans'})
        self.assertIn('Segoe UI', json.dumps(theme))

    def test_no_font(self):
        theme = generate_theme_json({})
        self.assertIn('Segoe UI', json.dumps(theme))


# ── Theme Background / Border ─────────────────────────────────────

class TestThemeBackgroundBorder(unittest.TestCase):
    """Tests for theme background color, border color/width."""

    def test_background_color_in_theme(self):
        theme = generate_theme_json({'background_color': '#F0F0F0'})
        self.assertEqual(theme['background'], '#F0F0F0')

    def test_foreground_color_in_theme(self):
        theme = generate_theme_json({'foreground_color': '#333333'})
        self.assertEqual(theme['foreground'], '#333333')

    def test_border_color_in_theme(self):
        theme = generate_theme_json({
            'border_color': '#CCCCCC',
            'border_width': 2,
        })
        border = theme['visualStyles']['*']['*'].get('border', [])
        self.assertTrue(len(border) > 0)
        self.assertEqual(border[0]['color'], '#CCCCCC')
        self.assertEqual(border[0]['width'], 2)

    def test_no_extras_when_none(self):
        theme = generate_theme_json()
        self.assertIn('name', theme)
        self.assertEqual(theme['background'], '#FFFFFF')

    def test_invalid_color_ignored(self):
        theme = generate_theme_json({'background_color': 'not-a-color'})
        self.assertEqual(theme['background'], '#FFFFFF')


# ── Assessment Formatting Coverage ─────────────────────────────────

class TestAssessmentFormattingCoverage(unittest.TestCase):
    """Tests for formatting coverage sub-metric in _check_visuals()."""

    def _assess(self, worksheets, dashboards=None):
        extracted = {
            'worksheets': worksheets,
            'dashboards': dashboards or [],
        }
        result = _check_visuals(extracted)
        return result.checks

    def test_color_encoded_counted(self):
        checks = self._assess([{
            'name': 'S1',
            'mark_type': 'bar',
            'chart_type': 'bar',
            'fields': ['Category'],
            'mark_encoding': {'color': {'field': 'Region', 'type': 'categorical'}},
        }])
        fmt_checks = [c for c in checks
                       if 'format' in (c.detail or '').lower()
                       or 'color' in (c.detail or '').lower()]
        self.assertTrue(len(fmt_checks) >= 1)

    def test_no_encoding_no_crash(self):
        checks = self._assess([{
            'name': 'S1',
            'mark_type': 'text',
            'chart_type': 'text',
            'fields': ['Value'],
            'mark_encoding': {},
        }])
        self.assertIsInstance(checks, list)

    def test_conditional_formatting_counted(self):
        checks = self._assess([{
            'name': 'S1',
            'mark_type': 'bar',
            'chart_type': 'bar',
            'fields': ['X'],
            'mark_encoding': {},
            'conditionalFormatting': [{'field': 'Sales', 'mode': 'gradient'}],
        }])
        fmt_checks = [c for c in checks
                       if 'format' in (c.detail or '').lower()]
        self.assertTrue(len(fmt_checks) >= 1)


if __name__ == '__main__':
    unittest.main()
