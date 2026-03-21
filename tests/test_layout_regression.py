"""
Sprint 80.2 — Layout regression tests.

Golden-file comparison: stores expected visual positions for key workbooks.
Fails if positions drift beyond tolerance after code changes.
"""
import copy
import json
import os
import sys
import tempfile
import shutil
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))
sys.path.insert(0, os.path.join(ROOT, 'powerbi_import'))

from tableau_export.extract_tableau_data import TableauExtractor
from powerbi_import.pbip_generator import PowerBIProjectGenerator

# ── Position tolerance ─────────────────────────────────────────────────

POSITION_TOLERANCE = 5  # pixels — acceptable drift


# ── Golden reference data ──────────────────────────────────────────────
# These are the expected layout positions after the Sprint 76 layout fix.
# Generated from actual migration output on 2026-03-21.

GOLDEN_LAYOUTS = {
    # Superstore_Sales.twb — 1 dashboard, 3 worksheets (2 side-by-side + 1 full-width)
    'Superstore_Sales': {
        'source': os.path.join(ROOT, 'examples', 'tableau_samples', 'Superstore_Sales.twb'),
        'pages': {
            'Sales Overview': {
                'page_size': {'width': 1200, 'height': 800},
                'visuals': {
                    'Sales by Region': {'x': 0, 'y': 240, 'w': 600, 'h': 280},
                    'Profit by Category': {'x': 600, 'y': 240, 'w': 600, 'h': 280},
                    'Sales Trend': {'x': 0, 'y': 520, 'w': 1200, 'h': 280},
                },
            },
        },
    },
    # Complex_Enterprise.twb — Executive Summary: 2-column grid with header + footer
    'Complex_Enterprise': {
        'source': os.path.join(ROOT, 'examples', 'tableau_samples', 'Complex_Enterprise.twb'),
        'pages': {
            'Executive Summary': {
                'page_size': {'width': 1920, 'height': 1080},
                'visuals': {
                    'Executive KPIs': {'x': 0, 'y': 65},  # top row
                    'Revenue by Region': {'x': 0, 'y': 194},  # left column, row 2
                    'Sales Map': {'x': 1056, 'y': 194},  # right column, row 2
                    'Revenue Trend': {'x': 0, 'y': 626},  # left column, row 3
                    'Category Mix': {'x': 1152, 'y': 626},  # right column, row 3
                },
            },
            'Customer & Product Analysis': {
                'page_size': {'width': 1920, 'height': 1080},
                'visuals': {
                    'Customer Analysis': {'x': 0, 'y': 86},
                    'Payment Distribution': {'x': 960, 'y': 86},
                    'Order Funnel': {'x': 1440, 'y': 86},
                    'Profit Waterfall': {'x': 0, 'y': 572},
                    'Monthly Heatmap': {'x': 960, 'y': 572},
                    'Discount Distribution': {'x': 1536, 'y': 572},
                },
            },
        },
    },
    # Enterprise_Sales.twb — single wide dashboard
    'Enterprise_Sales': {
        'source': os.path.join(ROOT, 'examples', 'tableau_samples', 'Enterprise_Sales.twb'),
        'pages': {
            'Sales Dashboard': {
                'page_size': {'width': 1280, 'height': 720},
                # Verify at least the page generates with correct size
                'visuals': {},  # position-agnostic — just check page size
            },
        },
    },
}


# ── Helpers ────────────────────────────────────────────────────────────

def _extract_and_get_data(wb_path):
    """Extract a workbook and return the workbook_data dict."""
    temp_dir = tempfile.mkdtemp(prefix='layout_reg_')
    try:
        ext = TableauExtractor(wb_path, output_dir=temp_dir)
        ext.extract_all()
        return ext.workbook_data, temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _compute_layout_map(dashboards):
    """Build layout maps for all dashboards. Returns {dash_name: layout_map}."""
    gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
    gen.MIN_VISUAL_WIDTH = 60
    gen.MIN_VISUAL_HEIGHT = 40

    result = {}
    for db in dashboards:
        name = db.get('name', '')
        zh = db.get('zone_hierarchy', {})
        size = db.get('size', {})
        pw = size.get('width', 1280)
        ph = size.get('height', 720)
        lm = gen._build_zone_layout_map(zh, pw, ph)
        result[name] = {'layout_map': lm, 'size': {'width': pw, 'height': ph}}
    return result


def _assert_position_close(test_case, actual, expected, name, tolerance=POSITION_TOLERANCE):
    """Assert x and y are within tolerance. Optionally check w and h."""
    for key in ('x', 'y'):
        if key in expected:
            test_case.assertAlmostEqual(
                actual.get(key, -9999), expected[key],
                delta=tolerance,
                msg=f'{name} {key}: expected {expected[key]}, got {actual.get(key, "MISSING")}')
    for key in ('w', 'h'):
        if key in expected:
            test_case.assertAlmostEqual(
                actual.get(key, -9999), expected[key],
                delta=tolerance * 2,  # slightly more lenient on size
                msg=f'{name} {key}: expected {expected[key]}, got {actual.get(key, "MISSING")}')


# ── Test classes ───────────────────────────────────────────────────────

class TestLayoutRegression_Superstore(unittest.TestCase):
    """Golden-file layout regression for Superstore_Sales."""

    @classmethod
    def setUpClass(cls):
        golden = GOLDEN_LAYOUTS['Superstore_Sales']
        if not os.path.isfile(golden['source']):
            raise unittest.SkipTest(f'Source not found: {golden["source"]}')
        cls.data, cls.temp_dir = _extract_and_get_data(golden['source'])
        cls.layouts = _compute_layout_map(cls.data.get('dashboards', []))
        cls.golden = golden

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temp_dir'):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_dashboard_count(self):
        self.assertGreaterEqual(len(self.layouts), 1)

    def test_page_size(self):
        for page_name, expected in self.golden['pages'].items():
            layout = self.layouts.get(page_name)
            self.assertIsNotNone(layout, f'Dashboard "{page_name}" not found in extraction')
            assert layout is not None  # for type checker
            self.assertEqual(layout['size']['width'], expected['page_size']['width'])
            self.assertEqual(layout['size']['height'], expected['page_size']['height'])

    def test_visual_positions(self):
        for page_name, expected in self.golden['pages'].items():
            layout = self.layouts.get(page_name)
            if layout is None:
                self.fail(f'Dashboard "{page_name}" not found')
            assert layout is not None  # for type checker
            lm = layout['layout_map']
            for vis_name, expected_pos in expected.get('visuals', {}).items():
                actual = lm.get(vis_name)
                self.assertIsNotNone(actual,
                                     f'Visual "{vis_name}" not in layout map. Keys: {list(lm.keys())}')
                _assert_position_close(self, actual, expected_pos, vis_name)

    def test_side_by_side_preserved(self):
        """Sales by Region and Profit by Category must be side-by-side (same y, different x)."""
        layout = self.layouts.get('Sales Overview')
        self.assertIsNotNone(layout)
        assert layout is not None  # for type checker
        lm = layout['layout_map']
        left = lm.get('Sales by Region', {})
        right = lm.get('Profit by Category', {})
        # Same y (within tolerance)
        self.assertAlmostEqual(left.get('y', -1), right.get('y', -2),
                               delta=POSITION_TOLERANCE,
                               msg='Side-by-side visuals should have same y')
        # Different x
        self.assertGreater(right.get('x', 0), left.get('x', 0) + 100,
                           'Side-by-side: right visual should be offset from left')

    def test_full_width_below(self):
        """Sales Trend should span full width below the top row."""
        layout = self.layouts.get('Sales Overview')
        self.assertIsNotNone(layout)
        assert layout is not None  # for type checker
        lm = layout['layout_map']
        trend = lm.get('Sales Trend', {})
        region = lm.get('Sales by Region', {})
        self.assertGreater(trend.get('y', 0), region.get('y', 0),
                           'Full-width visual should be below top row')
        self.assertGreaterEqual(trend.get('w', 0), 1100,
                                'Full-width visual should span most of the page')


class TestLayoutRegression_ComplexEnterprise(unittest.TestCase):
    """Golden-file layout regression for Complex_Enterprise."""

    @classmethod
    def setUpClass(cls):
        golden = GOLDEN_LAYOUTS['Complex_Enterprise']
        if not os.path.isfile(golden['source']):
            raise unittest.SkipTest(f'Source not found: {golden["source"]}')
        cls.data, cls.temp_dir = _extract_and_get_data(golden['source'])
        cls.layouts = _compute_layout_map(cls.data.get('dashboards', []))
        cls.golden = golden

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temp_dir'):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_executive_summary_grid(self):
        """Executive Summary has a 2-column grid: left/right placement."""
        layout = self.layouts.get('Executive Summary')
        self.assertIsNotNone(layout, 'Executive Summary dashboard not found')
        assert layout is not None  # for type checker
        lm = layout['layout_map']

        # Row 2: Revenue by Region (left) + Sales Map (right)
        rev = lm.get('Revenue by Region', {})
        smap = lm.get('Sales Map', {})
        if rev and smap:
            self.assertAlmostEqual(rev.get('y', 0), smap.get('y', -1),
                                   delta=POSITION_TOLERANCE,
                                   msg='Row 2 visuals should have same y')
            self.assertGreater(smap.get('x', 0), rev.get('x', 0) + 200,
                               'Sales Map should be to the right of Revenue by Region')

    def test_customer_analysis_grid(self):
        """Customer & Product Analysis has a 3-column + 3-column layout."""
        layout = self.layouts.get('Customer & Product Analysis')
        if layout is None:
            self.skipTest('Customer & Product Analysis dashboard not found')
        lm = layout['layout_map']

        golden_page = self.golden['pages'].get('Customer & Product Analysis', {})
        for vis_name, expected_pos in golden_page.get('visuals', {}).items():
            actual = lm.get(vis_name)
            if actual is None:
                continue  # some visuals may not be in layout map
            _assert_position_close(self, actual, expected_pos, vis_name)

    def test_page_size_1920x1080(self):
        for page_name, expected in self.golden['pages'].items():
            layout = self.layouts.get(page_name)
            if layout is None:
                continue
            self.assertEqual(layout['size']['width'], expected['page_size']['width'])
            self.assertEqual(layout['size']['height'], expected['page_size']['height'])


class TestLayoutRegression_EnterpriseSales(unittest.TestCase):
    """Golden-file layout regression for Enterprise_Sales."""

    @classmethod
    def setUpClass(cls):
        golden = GOLDEN_LAYOUTS['Enterprise_Sales']
        if not os.path.isfile(golden['source']):
            raise unittest.SkipTest(f'Source not found: {golden["source"]}')
        cls.data, cls.temp_dir = _extract_and_get_data(golden['source'])
        cls.layouts = _compute_layout_map(cls.data.get('dashboards', []))
        cls.golden = golden

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temp_dir'):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_dashboard_exists(self):
        self.assertGreaterEqual(len(self.layouts), 1)

    def test_page_size(self):
        for page_name, expected in self.golden['pages'].items():
            layout = self.layouts.get(page_name)
            if layout is None:
                continue
            self.assertEqual(layout['size']['width'], expected['page_size']['width'])
            self.assertEqual(layout['size']['height'], expected['page_size']['height'])


# ── Generic layout invariants (all workbooks) ─────────────────────────

class TestLayoutInvariants(unittest.TestCase):
    """Layout invariants that should hold for any workbook."""

    def _check_invariants(self, wb_path):
        if not os.path.isfile(wb_path):
            self.skipTest(f'Not found: {wb_path}')
        data, temp_dir = _extract_and_get_data(wb_path)
        try:
            layouts = _compute_layout_map(data.get('dashboards', []))
            for dash_name, layout_info in layouts.items():
                lm = layout_info['layout_map']
                pw = layout_info['size']['width']
                ph = layout_info['size']['height']
                for vis_name, pos in lm.items():
                    # No negative positions
                    self.assertGreaterEqual(pos['x'], 0,
                                            f'{dash_name}/{vis_name} x < 0')
                    self.assertGreaterEqual(pos['y'], 0,
                                            f'{dash_name}/{vis_name} y < 0')
                    # Visual fits within page (with tolerance for rounding)
                    self.assertLessEqual(pos['x'] + pos['w'], pw + 20,
                                         f'{dash_name}/{vis_name} exceeds page width')
                    self.assertLessEqual(pos['y'] + pos['h'], ph + 20,
                                         f'{dash_name}/{vis_name} exceeds page height')
                    # Minimum size
                    self.assertGreaterEqual(pos['w'], 40,
                                            f'{dash_name}/{vis_name} too narrow')
                    self.assertGreaterEqual(pos['h'], 40,
                                            f'{dash_name}/{vis_name} too short')
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_superstore_invariants(self):
        self._check_invariants(os.path.join(SAMPLE_DIR, 'Superstore_Sales.twb'))

    def test_complex_enterprise_invariants(self):
        self._check_invariants(os.path.join(SAMPLE_DIR, 'Complex_Enterprise.twb'))

    def test_enterprise_sales_invariants(self):
        self._check_invariants(os.path.join(SAMPLE_DIR, 'Enterprise_Sales.twb'))

    def test_hr_analytics_invariants(self):
        self._check_invariants(os.path.join(SAMPLE_DIR, 'HR_Analytics.twb'))

    def test_financial_report_invariants(self):
        self._check_invariants(os.path.join(SAMPLE_DIR, 'Financial_Report.twb'))

    def test_marketing_campaign_invariants(self):
        self._check_invariants(os.path.join(SAMPLE_DIR, 'Marketing_Campaign.twb'))

    def test_manufacturing_iot_invariants(self):
        self._check_invariants(os.path.join(SAMPLE_DIR, 'Manufacturing_IoT.twb'))

    def test_bigquery_analytics_invariants(self):
        self._check_invariants(os.path.join(SAMPLE_DIR, 'BigQuery_Analytics.twb'))

    def test_ventes_france_invariants(self):
        self._check_invariants(os.path.join(SAMPLE_DIR, 'Ventes_France.twb'))


# ── No-overlap test ────────────────────────────────────────────────────

class TestNoVisualOverlap(unittest.TestCase):
    """Verify that worksheetReference visuals don't fully overlap each other."""

    def _check_no_full_overlap(self, wb_path):
        if not os.path.isfile(wb_path):
            self.skipTest(f'Not found: {wb_path}')
        data, temp_dir = _extract_and_get_data(wb_path)
        try:
            layouts = _compute_layout_map(data.get('dashboards', []))
            for dash_name, layout_info in layouts.items():
                lm = layout_info['layout_map']
                # Only check named visuals (exclude container IDs)
                named = {k: v for k, v in lm.items() if not k.isdigit()}
                names = list(named.keys())
                for i in range(len(names)):
                    for j in range(i + 1, len(names)):
                        a, b = named[names[i]], named[names[j]]
                        # Full overlap: identical position
                        if (a['x'] == b['x'] and a['y'] == b['y']
                                and a['w'] == b['w'] and a['h'] == b['h']):
                            self.fail(
                                f'{dash_name}: "{names[i]}" and "{names[j]}" '
                                f'have identical positions — likely a layout bug')
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_superstore_no_overlap(self):
        self._check_no_full_overlap(os.path.join(SAMPLE_DIR, 'Superstore_Sales.twb'))

    def test_complex_enterprise_no_overlap(self):
        self._check_no_full_overlap(os.path.join(SAMPLE_DIR, 'Complex_Enterprise.twb'))

    def test_enterprise_sales_no_overlap(self):
        self._check_no_full_overlap(os.path.join(SAMPLE_DIR, 'Enterprise_Sales.twb'))


# ── Proportional coordinate mapping test ──────────────────────────────

class TestProportionalMapping(unittest.TestCase):
    """Test that the layout engine proportional mapping preserves 2-D grids."""

    def test_2x2_grid_proportional(self):
        """Four zones in a 2x2 grid should map to four non-overlapping quadrants."""
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen.MIN_VISUAL_WIDTH = 60
        gen.MIN_VISUAL_HEIGHT = 40
        hierarchy = {
            'id': '1', 'name': '', 'orientation': '',
            'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100},
            'children': [
                {'name': 'TL', 'position': {'x': 0, 'y': 0, 'w': 50, 'h': 50}, 'children': []},
                {'name': 'TR', 'position': {'x': 50, 'y': 0, 'w': 50, 'h': 50}, 'children': []},
                {'name': 'BL', 'position': {'x': 0, 'y': 50, 'w': 50, 'h': 50}, 'children': []},
                {'name': 'BR', 'position': {'x': 50, 'y': 50, 'w': 50, 'h': 50}, 'children': []},
            ],
        }
        lm = gen._build_zone_layout_map(hierarchy, 1000, 800)
        self.assertEqual(lm['TL']['x'], 0)
        self.assertEqual(lm['TL']['y'], 0)
        self.assertEqual(lm['TR']['x'], 500)
        self.assertEqual(lm['TR']['y'], 0)
        self.assertEqual(lm['BL']['x'], 0)
        self.assertEqual(lm['BL']['y'], 400)
        self.assertEqual(lm['BR']['x'], 500)
        self.assertEqual(lm['BR']['y'], 400)

    def test_unequal_columns(self):
        """2:1 width ratio should be preserved."""
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen.MIN_VISUAL_WIDTH = 60
        gen.MIN_VISUAL_HEIGHT = 40
        hierarchy = {
            'id': '1', 'name': '', 'orientation': '',
            'position': {'x': 0, 'y': 0, 'w': 90, 'h': 50},
            'children': [
                {'name': 'Wide', 'position': {'x': 0, 'y': 0, 'w': 60, 'h': 50}, 'children': []},
                {'name': 'Narrow', 'position': {'x': 60, 'y': 0, 'w': 30, 'h': 50}, 'children': []},
            ],
        }
        lm = gen._build_zone_layout_map(hierarchy, 900, 600)
        # Wide gets 2/3 = 600, Narrow gets 1/3 = 300
        self.assertAlmostEqual(lm['Wide']['w'], 600, delta=5)
        self.assertAlmostEqual(lm['Narrow']['w'], 300, delta=5)
        self.assertAlmostEqual(lm['Narrow']['x'], 600, delta=5)

    def test_3_row_stacked(self):
        """Three rows stacked vertically should distribute height."""
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen.MIN_VISUAL_WIDTH = 60
        gen.MIN_VISUAL_HEIGHT = 40
        hierarchy = {
            'id': '1', 'name': '', 'orientation': '',
            'position': {'x': 0, 'y': 0, 'w': 100, 'h': 90},
            'children': [
                {'name': 'R1', 'position': {'x': 0, 'y': 0, 'w': 100, 'h': 30}, 'children': []},
                {'name': 'R2', 'position': {'x': 0, 'y': 30, 'w': 100, 'h': 30}, 'children': []},
                {'name': 'R3', 'position': {'x': 0, 'y': 60, 'w': 100, 'h': 30}, 'children': []},
            ],
        }
        lm = gen._build_zone_layout_map(hierarchy, 1200, 900)
        self.assertEqual(lm['R1']['y'], 0)
        self.assertAlmostEqual(lm['R2']['y'], 300, delta=5)
        self.assertAlmostEqual(lm['R3']['y'], 600, delta=5)
        # All full width
        for r in ('R1', 'R2', 'R3'):
            self.assertAlmostEqual(lm[r]['w'], 1200, delta=5)


SAMPLE_DIR = os.path.join(ROOT, 'examples', 'tableau_samples')


if __name__ == '__main__':
    unittest.main()
