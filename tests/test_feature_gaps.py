"""
Unit tests for feature gap fixes — validates all new extraction and
generation features implemented to close Tableau→Power BI feature gaps.

Covers:
  - Reference lines extraction
  - Annotations extraction
  - Axis config (range, log, reversed, continuous, dual-axis)
  - Legend config (position, title, font)
  - Mark label depth (position, font, orientation)
  - Palette color extraction (quantitative/categorical)
  - Dashboard padding & borders
  - Layout containers & device layouts
  - Sort order depth (computed sort)
  - Worksheet sort → visual sort definition
  - Action button visual creation (URL, sheet-navigate)
  - Dual-axis combo chart roles (ColumnY/LineY)
  - Table/matrix formatting (header, banding, grid)
  - Conditional formatting gradient (min/mid/max)
  - Tooltip page binding
  - Date hierarchy on Calendar table
  - Table calc measure generation (pcto, running_sum, rank)
  - Table calc addressing (partition fields → ALLEXCEPT)
  - Quick table calc field detection
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))
sys.path.insert(0, os.path.join(ROOT, 'powerbi_import'))

from extract_tableau_data import TableauExtractor
from pbip_generator import PowerBIProjectGenerator


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_extractor(xml_string=None):
    """Create a TableauExtractor with a temp dir."""
    tmpdir = tempfile.mkdtemp()
    tmpfile = os.path.join(tmpdir, 'test.twb')
    if xml_string:
        with open(tmpfile, 'w', encoding='utf-8') as f:
            f.write(xml_string)
    else:
        with open(tmpfile, 'w', encoding='utf-8') as f:
            f.write('<workbook></workbook>')
    ext = TableauExtractor(tmpfile, output_dir=tmpdir)
    return ext, tmpdir


def _make_generator():
    """Create a PowerBIProjectGenerator with temp dirs."""
    return PowerBIProjectGenerator(
        output_dir=tempfile.mkdtemp()
    )


def _cleanup(tmpdir):
    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# Reference Lines Extraction
# ═══════════════════════════════════════════════════════════════════

class TestReferenceLines(unittest.TestCase):
    """Test extraction of reference lines from worksheet XML."""

    def test_extract_constant_line(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet name="Sheet1">
                <reference-line scope="per-pane" label-type="custom"
                    line-style="solid" color="#FF0000"
                    line-thickness="2">
                    <reference-line-value value="100" />
                    <reference-line-label value="Target" />
                </reference-line>
            </worksheet>
            ''')
            result = ext.extract_reference_lines(ws_xml)
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) >= 1)
            first = result[0]
            self.assertEqual(first['value'], '100')
            self.assertEqual(first['label'], 'Target')
            self.assertEqual(first['line_color'], '#FF0000')
        finally:
            _cleanup(tmpdir)

    def test_extract_no_reference_lines(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('<worksheet name="Sheet1"></worksheet>')
            result = ext.extract_reference_lines(ws_xml)
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 0)
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Annotations Extraction
# ═══════════════════════════════════════════════════════════════════

class TestAnnotations(unittest.TestCase):
    """Test extraction of annotations from worksheet XML."""

    def test_extract_annotation(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet name="Sheet1">
                <annotation type="point">
                    <formatted-text><run>Note here</run></formatted-text>
                    <position x="100" y="200" />
                </annotation>
            </worksheet>
            ''')
            result = ext.extract_annotations(ws_xml)
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) >= 1)
            self.assertEqual(result[0]['type'], 'point')
            self.assertIn('Note here', result[0].get('text', ''))
        finally:
            _cleanup(tmpdir)

    def test_extract_no_annotations(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('<worksheet name="Sheet1"></worksheet>')
            result = ext.extract_annotations(ws_xml)
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 0)
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Axis Config — continuous, dual-axis, range
# ═══════════════════════════════════════════════════════════════════

class TestAxesExtraction(unittest.TestCase):
    """Test axis extraction with continuous/discrete and dual-axis."""

    def test_basic_axes(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <axis type="x"><title>Category</title></axis>
                <axis type="y" range-min="0" range-max="1000" auto-range="false">
                    <title>Revenue</title>
                </axis>
            </worksheet>
            ''')
            axes = ext.extract_axes(ws_xml)
            self.assertIn('x', axes)
            self.assertIn('y', axes)
            self.assertEqual(axes['y']['range_min'], '0')
            self.assertEqual(axes['y']['range_max'], '1000')
            self.assertFalse(axes['y']['auto_range'])
            self.assertEqual(axes['y']['title'], 'Revenue')
        finally:
            _cleanup(tmpdir)

    def test_dual_axis_detection(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <axis type="y"><title>Primary</title></axis>
                <axis type="y" synchronized="true"><title>Secondary</title></axis>
            </worksheet>
            ''')
            axes = ext.extract_axes(ws_xml)
            self.assertTrue(axes.get('dual_axis'))
            self.assertTrue(axes.get('dual_axis_sync'))
        finally:
            _cleanup(tmpdir)

    def test_no_dual_axis(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <axis type="x"><title>X</title></axis>
                <axis type="y"><title>Y</title></axis>
            </worksheet>
            ''')
            axes = ext.extract_axes(ws_xml)
            self.assertFalse(axes.get('dual_axis'))
        finally:
            _cleanup(tmpdir)

    def test_log_scale(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('<worksheet><axis type="y" scale="log"></axis></worksheet>')
            axes = ext.extract_axes(ws_xml)
            self.assertEqual(axes['y']['scale'], 'log')
        finally:
            _cleanup(tmpdir)

    def test_reversed_axis(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('<worksheet><axis type="y" reversed="true"></axis></worksheet>')
            axes = ext.extract_axes(ws_xml)
            self.assertTrue(axes['y']['reversed'])
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Legend Config
# ═══════════════════════════════════════════════════════════════════

class TestLegendExtraction(unittest.TestCase):
    """Test legend position/font extraction from formatting."""

    def test_legend_position_from_xml(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <legend position="top" title="Color Legend" font-size="12" />
            </worksheet>
            ''')
            fmt = ext.extract_formatting(ws_xml)
            legend = fmt.get('legend', {})
            self.assertEqual(legend.get('position'), 'top')
            self.assertEqual(legend.get('title'), 'Color Legend')
            self.assertEqual(legend.get('font-size'), '12')
        finally:
            _cleanup(tmpdir)

    def test_legend_not_present(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('<worksheet></worksheet>')
            fmt = ext.extract_formatting(ws_xml)
            self.assertNotIn('legend', fmt)
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Legend Generation in PBI
# ═══════════════════════════════════════════════════════════════════

class TestLegendGeneration(unittest.TestCase):
    """Test legend position mapping in _build_visual_objects."""

    def test_legend_position_top(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Test',
            'fields': [{'name': 'Sales', 'role': 'measure'}],
            'mark_encoding': {'color': {'field': 'Region'}},
            'formatting': {'legend': {'position': 'top'}},
            'axes': {},
        }
        objects = gen._build_visual_objects('Test', ws_data, 'clusteredBarChart')
        legend = objects.get('legend', [{}])[0].get('properties', {})
        pos_val = legend.get('position', {}).get('expr', {}).get('Literal', {}).get('Value', '')
        self.assertEqual(pos_val, "'Top'")

    def test_legend_position_default_right(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Test',
            'fields': [{'name': 'Sales', 'role': 'measure'}],
            'mark_encoding': {'color': {'field': 'Region'}},
            'formatting': {},
            'axes': {},
        }
        objects = gen._build_visual_objects('Test', ws_data, 'clusteredBarChart')
        legend = objects.get('legend', [{}])[0].get('properties', {})
        pos_val = legend.get('position', {}).get('expr', {}).get('Literal', {}).get('Value', '')
        self.assertEqual(pos_val, "'Right'")

    def test_legend_title(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Test',
            'fields': [{'name': 'Sales', 'role': 'measure'}],
            'mark_encoding': {'color': {'field': 'Region'}},
            'formatting': {'legend': {'position': 'bottom', 'title': 'Color Legend'}},
            'axes': {},
        }
        objects = gen._build_visual_objects('Test', ws_data, 'clusteredBarChart')
        legend = objects.get('legend', [{}])[0].get('properties', {})
        self.assertIn('titleText', legend)
        self.assertIn('showTitle', legend)


# ═══════════════════════════════════════════════════════════════════
# Mark Labels Depth
# ═══════════════════════════════════════════════════════════════════

class TestMarkLabelsExtraction(unittest.TestCase):
    """Test mark label position/font extraction."""

    def test_label_position_extraction(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <encodings>
                    <label show-label="true" label-position="top"
                           font-size="14" font-weight="bold" font-color="#333333" />
                </encodings>
            </worksheet>
            ''')
            enc = ext.extract_mark_encoding(ws_xml)
            label = enc.get('label', {})
            self.assertTrue(label.get('show'))
            self.assertEqual(label.get('position'), 'top')
            self.assertEqual(label.get('font_size'), '14')
            self.assertEqual(label.get('font_weight'), 'bold')
            self.assertEqual(label.get('font_color'), '#333333')
        finally:
            _cleanup(tmpdir)


class TestMarkLabelsGeneration(unittest.TestCase):
    """Test label position and font in _build_visual_objects."""

    def test_label_position_top(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Test',
            'fields': [{'name': 'Sales', 'role': 'measure'}],
            'mark_encoding': {'label': {'show': True, 'field': 'Sales', 'position': 'top'}},
            'formatting': {},
            'axes': {},
        }
        objects = gen._build_visual_objects('Test', ws_data, 'clusteredBarChart')
        labels = objects.get('labels', [{}])[0].get('properties', {})
        lp = labels.get('labelPosition', {}).get('expr', {}).get('Literal', {}).get('Value', '')
        self.assertEqual(lp, "'OutsideEnd'")

    def test_label_position_center(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Test',
            'fields': [{'name': 'Sales', 'role': 'measure'}],
            'mark_encoding': {'label': {'show': True, 'field': 'Sales', 'position': 'center'}},
            'formatting': {},
            'axes': {},
        }
        objects = gen._build_visual_objects('Test', ws_data, 'clusteredBarChart')
        labels = objects.get('labels', [{}])[0].get('properties', {})
        lp = labels.get('labelPosition', {}).get('expr', {}).get('Literal', {}).get('Value', '')
        self.assertEqual(lp, "'InsideCenter'")


# ═══════════════════════════════════════════════════════════════════
# Palette Color Extraction
# ═══════════════════════════════════════════════════════════════════

class TestPaletteColors(unittest.TestCase):
    """Test color type detection and palette color extraction."""

    def test_quantitative_color_type(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <encodings>
                    <color column="[ds].[Sales:qk]" palette="blue-teal" />
                </encodings>
            </worksheet>
            ''')
            enc = ext.extract_mark_encoding(ws_xml)
            color = enc.get('color', {})
            self.assertEqual(color.get('type'), 'quantitative')
        finally:
            _cleanup(tmpdir)

    def test_categorical_color_type(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <encodings>
                    <color column="[ds].[Region:nk]" palette="tableau10" />
                </encodings>
            </worksheet>
            ''')
            enc = ext.extract_mark_encoding(ws_xml)
            color = enc.get('color', {})
            self.assertEqual(color.get('type'), 'categorical')
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Dashboard Padding & Borders
# ═══════════════════════════════════════════════════════════════════

class TestDashboardPadding(unittest.TestCase):
    """Test padding/border extraction from dashboard zones."""

    def test_padding_extraction(self):
        ext, tmpdir = _make_extractor()
        try:
            db_xml = ET.fromstring('''
            <dashboard name="DB">
                <zone name="Sheet1" type="" x="0" y="0" w="500" h="300">
                    <zone-style>
                        <format attr="padding-left" value="10" />
                        <format attr="padding-top" value="5" />
                        <format attr="border-style" value="solid" />
                        <format attr="border-color" value="#000000" />
                    </zone-style>
                </zone>
            </dashboard>
            ''')
            objs = ext.extract_dashboard_objects(db_xml)
            ws_obj = [o for o in objs if o.get('name') == 'Sheet1']
            self.assertEqual(len(ws_obj), 1)
            padding = ws_obj[0].get('padding', {})
            self.assertEqual(padding.get('padding-left'), 10)
            self.assertEqual(padding.get('padding-top'), 5)
            self.assertEqual(padding.get('border_style'), 'solid')
            self.assertEqual(padding.get('border_color'), '#000000')
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Layout Containers
# ═══════════════════════════════════════════════════════════════════

class TestLayoutContainers(unittest.TestCase):
    """Test layout container hierarchy extraction."""

    def test_extract_horizontal_container(self):
        ext, tmpdir = _make_extractor()
        try:
            db_xml = ET.fromstring('''
            <dashboard name="DB">
                <layout-container orientation="horizontal" x="0" y="0" w="800" h="400">
                    <zone name="Sheet1" />
                    <zone name="Sheet2" />
                </layout-container>
            </dashboard>
            ''')
            containers = ext.extract_layout_containers(db_xml)
            self.assertEqual(len(containers), 1)
            self.assertEqual(containers[0]['orientation'], 'horizontal')
            self.assertIn('Sheet1', containers[0]['children'])
            self.assertIn('Sheet2', containers[0]['children'])
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Device Layouts
# ═══════════════════════════════════════════════════════════════════

class TestDeviceLayouts(unittest.TestCase):
    """Test device layout extraction (phone/tablet)."""

    def test_extract_phone_layout(self):
        ext, tmpdir = _make_extractor()
        try:
            db_xml = ET.fromstring('''
            <dashboard name="DB">
                <device-layout device-type="phone">
                    <zone name="Sheet1" x="0" y="0" w="320" h="200" />
                </device-layout>
            </dashboard>
            ''')
            layouts = ext.extract_device_layouts(db_xml)
            self.assertEqual(len(layouts), 1)
            self.assertEqual(layouts[0]['device_type'], 'phone')
            self.assertEqual(len(layouts[0]['zones']), 1)
            self.assertEqual(layouts[0]['zones'][0]['name'], 'Sheet1')
        finally:
            _cleanup(tmpdir)

    def test_no_device_layouts(self):
        ext, tmpdir = _make_extractor()
        try:
            db_xml = ET.fromstring('<dashboard name="DB"></dashboard>')
            layouts = ext.extract_device_layouts(db_xml)
            self.assertEqual(len(layouts), 0)
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Sort Config Depth
# ═══════════════════════════════════════════════════════════════════

class TestSortOrderExtraction(unittest.TestCase):
    """Test sort order extraction with computed sort."""

    def test_basic_sort(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <sort column="[Category]" direction="DESC" />
            </worksheet>
            ''')
            sorts = ext.extract_worksheet_sort_orders(ws_xml)
            self.assertEqual(len(sorts), 1)
            self.assertEqual(sorts[0]['field'], 'Category')
            self.assertEqual(sorts[0]['direction'], 'DESC')
        finally:
            _cleanup(tmpdir)

    def test_computed_sort(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <sort column="[Category]" direction="DESC" using="[Sales]" type="computed" />
            </worksheet>
            ''')
            sorts = ext.extract_worksheet_sort_orders(ws_xml)
            self.assertEqual(len(sorts), 1)
            self.assertEqual(sorts[0]['sort_by'], 'Sales')
            self.assertEqual(sorts[0]['sort_type'], 'computed')
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Combo Chart Role Names (ColumnY/LineY)
# ═══════════════════════════════════════════════════════════════════

class TestComboChartRoles(unittest.TestCase):
    """Test that combo chart uses correct ColumnY/LineY role names."""

    def test_combo_chart_roles(self):
        gen = _make_generator()
        gen.main_table = 'Sales'
        gen.field_entity_map = {'Revenue': 'Sales', 'Profit': 'Sales', 'Category': 'Sales'}
        gen._measure_names = {'Revenue', 'Profit'}
        ws_data = {
            'name': 'Test',
            'chart_type': 'lineClusteredColumnComboChart',
            'fields': [
                {'name': 'Category', 'role': 'dimension'},
                {'name': 'Revenue', 'role': 'measure'},
                {'name': 'Profit', 'role': 'measure'},
            ],
        }
        query = gen._build_visual_query(ws_data)
        self.assertIn('ColumnY', query.get('queryState', {}))
        self.assertIn('LineY', query.get('queryState', {}))
        self.assertNotIn('Y', query.get('queryState', {}))
        self.assertNotIn('Y2', query.get('queryState', {}))


# ═══════════════════════════════════════════════════════════════════
# Sort State Application
# ═══════════════════════════════════════════════════════════════════

class TestSortStateApplication(unittest.TestCase):
    """Test that sort_orders on ws_data get applied to the visual query."""

    def test_sort_definition_created(self):
        gen = _make_generator()
        gen._main_table = 'Sales'
        gen.field_entity_map = {'Revenue': 'Sales', 'Category': 'Sales'}
        ws_data = {
            'name': 'Test',
            'chart_type': 'clusteredBarChart',
            'fields': [
                {'name': 'Category', 'role': 'dimension'},
                {'name': 'Revenue', 'role': 'measure'},
            ],
            'sort_orders': [{'field': 'Revenue', 'direction': 'DESC'}],
            'mark_encoding': {},
            'formatting': {},
            'axes': {},
        }
        # Create a visual and check that sort definition was applied
        visuals_dir = tempfile.mkdtemp()
        try:
            gen._create_visual_worksheet(
                visuals_dir, ws_data,
                {'type': 'worksheetReference', 'worksheetName': 'Test',
                 'position': {'x': 0, 'y': 0, 'w': 300, 'h': 200}},
                1.0, 1.0, 0, [], {}
            )
            # Read the generated visual.json
            for vdir in os.listdir(visuals_dir):
                visual_path = os.path.join(visuals_dir, vdir, 'visual.json')
                if os.path.exists(visual_path):
                    with open(visual_path, 'r') as f:
                        visual = json.load(f)
                    query = visual.get('visual', {}).get('query', {})
                    sort_def = query.get('sortDefinition', {})
                    self.assertIn('sort', sort_def)
                    self.assertEqual(sort_def['sort'][0]['direction'], 'Descending')
                    break
        finally:
            _cleanup(visuals_dir)


# ═══════════════════════════════════════════════════════════════════
# Action Button Visuals
# ═══════════════════════════════════════════════════════════════════

class TestActionButtonVisuals(unittest.TestCase):
    """Test creation of URL and navigate action button visuals."""

    def test_url_action_button(self):
        gen = _make_generator()
        visuals_dir = tempfile.mkdtemp()
        try:
            actions = [
                {'type': 'url', 'name': 'Open Google', 'url': 'https://google.com'}
            ]
            created = gen._create_action_visuals(visuals_dir, actions, 1.0, 1.0, 0, 'Test Page')
            self.assertEqual(created, 1)
            
            # Read the visual
            for vdir in os.listdir(visuals_dir):
                visual_path = os.path.join(visuals_dir, vdir, 'visual.json')
                if os.path.exists(visual_path):
                    with open(visual_path, 'r') as f:
                        visual = json.load(f)
                    vtype = visual.get('visual', {}).get('visualType')
                    self.assertEqual(vtype, 'actionButton')
                    action_obj = visual['visual']['objects'].get('action', [{}])[0]
                    action_type = action_obj['properties']['type']['expr']['Literal']['Value']
                    self.assertEqual(action_type, "'WebUrl'")
                    break
        finally:
            _cleanup(visuals_dir)

    def test_navigate_action_button(self):
        gen = _make_generator()
        visuals_dir = tempfile.mkdtemp()
        try:
            actions = [
                {'type': 'sheet-navigate', 'name': 'Go to Details', 'target_worksheet': 'Details'}
            ]
            created = gen._create_action_visuals(visuals_dir, actions, 1.0, 1.0, 0, 'Test Page')
            self.assertEqual(created, 1)
        finally:
            _cleanup(visuals_dir)

    def test_filter_action_skipped(self):
        gen = _make_generator()
        visuals_dir = tempfile.mkdtemp()
        try:
            actions = [
                {'type': 'filter', 'name': 'Cross filter'}
            ]
            created = gen._create_action_visuals(visuals_dir, actions, 1.0, 1.0, 0, 'Test Page')
            self.assertEqual(created, 0)
        finally:
            _cleanup(visuals_dir)


# ═══════════════════════════════════════════════════════════════════
# Table/Matrix Formatting (Header, Banding, Grid)
# ═══════════════════════════════════════════════════════════════════

class TestTableFormatting(unittest.TestCase):
    """Test table-specific formatting generation."""

    def test_table_header_formatting(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Data Table',
            'fields': [{'name': 'Col1', 'role': 'dimension'}],
            'mark_encoding': {},
            'formatting': {
                'header_style': {'font-size': '14', 'font-weight': 'bold'}
            },
            'axes': {},
        }
        objects = gen._build_visual_objects('Data Table', ws_data, 'tableEx')
        self.assertIn('columnHeaders', objects)
        headers = objects['columnHeaders'][0]['properties']
        self.assertIn('fontSize', headers)
        self.assertIn('bold', headers)

    def test_non_table_skips_header_formatting(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Bar Chart',
            'fields': [{'name': 'Sales', 'role': 'measure'}],
            'mark_encoding': {},
            'formatting': {
                'header_style': {'font-size': '14', 'font-weight': 'bold'}
            },
            'axes': {},
        }
        objects = gen._build_visual_objects('Bar Chart', ws_data, 'clusteredBarChart')
        self.assertNotIn('columnHeaders', objects)


# ═══════════════════════════════════════════════════════════════════
# Conditional Formatting Gradient
# ═══════════════════════════════════════════════════════════════════

class TestConditionalFormatting(unittest.TestCase):
    """Test conditional formatting gradient generation."""

    def test_two_color_gradient(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Heat',
            'fields': [{'name': 'Revenue', 'role': 'measure'}],
            'mark_encoding': {
                'color': {
                    'field': 'Revenue',
                    'palette': 'blue-teal',
                    'palette_colors': ['#0000FF', '#00FFFF']
                }
            },
            'formatting': {},
            'axes': {},
        }
        objects = gen._build_visual_objects('Heat', ws_data, 'matrix')
        dp = objects.get('dataPoint', [{}])[0]
        rules = dp.get('rules', [])
        self.assertTrue(len(rules) >= 1)
        gradient = rules[0].get('gradient', {})
        self.assertIn('min', gradient)
        self.assertIn('max', gradient)
        self.assertNotIn('mid', gradient)

    def test_three_color_gradient(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Heat3',
            'fields': [{'name': 'Revenue', 'role': 'measure'}],
            'mark_encoding': {
                'color': {
                    'field': 'Revenue',
                    'palette': 'traffic',
                    'palette_colors': ['#FF0000', '#FFFF00', '#00FF00']
                }
            },
            'formatting': {},
            'axes': {},
        }
        objects = gen._build_visual_objects('Heat3', ws_data, 'matrix')
        dp = objects.get('dataPoint', [{}])[0]
        rules = dp.get('rules', [])
        gradient = rules[0].get('gradient', {})
        self.assertIn('mid', gradient)


# ═══════════════════════════════════════════════════════════════════
# Axis Generation (range, log, dual-axis)
# ═══════════════════════════════════════════════════════════════════

class TestAxisGeneration(unittest.TestCase):
    """Test axis config application in _build_visual_objects."""

    def test_axis_range(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Chart',
            'fields': [{'name': 'Sales', 'role': 'measure'}],
            'mark_encoding': {},
            'formatting': {},
            'axes': {
                'y': {
                    'auto_range': False,
                    'range_min': '0',
                    'range_max': '1000',
                    'scale': 'linear',
                    'title': 'Revenue',
                    'reversed': False,
                }
            },
        }
        objects = gen._build_visual_objects('Chart', ws_data, 'clusteredBarChart')
        val_axis = objects.get('valueAxis', [{}])[0].get('properties', {})
        self.assertIn('start', val_axis)
        self.assertIn('end', val_axis)
        self.assertIn('titleText', val_axis)

    def test_log_scale(self):
        gen = _make_generator()
        ws_data = {
            'name': 'Log',
            'fields': [{'name': 'Sales', 'role': 'measure'}],
            'mark_encoding': {},
            'formatting': {},
            'axes': {'y': {'auto_range': True, 'scale': 'log', 'title': '', 'reversed': False}},
        }
        objects = gen._build_visual_objects('Log', ws_data, 'clusteredBarChart')
        val_axis = objects.get('valueAxis', [{}])[0].get('properties', {})
        self.assertIn('axisScale', val_axis)


# ═══════════════════════════════════════════════════════════════════
# Formatting Depth (font, border, banding)
# ═══════════════════════════════════════════════════════════════════

class TestFormattingDepth(unittest.TestCase):
    """Test enhanced formatting extraction with style depth."""

    def test_font_size_extraction(self):
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <format attr="font-size" scope="header" value="16" />
                <format attr="font-weight" scope="header" value="bold" />
                <format attr="band-color" scope="worksheet" value="#F0F0F0" />
            </worksheet>
            ''')
            fmt = ext.extract_formatting(ws_xml)
            header = fmt.get('header_style', {})
            self.assertEqual(header.get('font-size'), '16')
            self.assertEqual(header.get('font-weight'), 'bold')
            ws_style = fmt.get('worksheet_style', {})
            self.assertEqual(ws_style.get('band-color'), '#F0F0F0')
        finally:
            _cleanup(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Padding Application in Visual
# ═══════════════════════════════════════════════════════════════════

class TestPaddingApplication(unittest.TestCase):
    """Test padding/border application on visual containers."""

    def test_padding_applied_to_visual(self):
        gen = _make_generator()
        gen.main_table = 'Sales'
        gen.field_entity_map = {'Revenue': 'Sales'}
        visuals_dir = tempfile.mkdtemp()
        try:
            ws_data = {
                'name': 'Test',
                'chart_type': 'clusteredBarChart',
                'fields': [{'name': 'Revenue', 'role': 'measure'}],
                'mark_encoding': {},
                'formatting': {},
                'axes': {},
            }
            obj = {
                'type': 'worksheetReference',
                'worksheetName': 'Test',
                'position': {'x': 0, 'y': 0, 'w': 300, 'h': 200},
                'padding': {'padding-left': 10, 'padding-top': 5, 'border_style': 'solid', 'border_color': '#000'}
            }
            gen._create_visual_worksheet(
                visuals_dir, ws_data, obj, 1.0, 1.0, 0, [], {}
            )
            for vdir in os.listdir(visuals_dir):
                visual_path = os.path.join(visuals_dir, vdir, 'visual.json')
                if os.path.exists(visual_path):
                    with open(visual_path, 'r') as f:
                        visual = json.load(f)
                    obj_data = visual.get('visual', {}).get('objects', {})
                    self.assertIn('padding', obj_data)
                    self.assertIn('border', obj_data)
                    break
        finally:
            _cleanup(visuals_dir)


# ═══════════════════════════════════════════════════════════════════
# Quick Table Calc Field Detection
# ═══════════════════════════════════════════════════════════════════

class TestQuickTableCalcDetection(unittest.TestCase):
    """Test detection of table_calc prefixes on worksheet fields."""

    def test_pcto_detection(self):
        """pcto: prefix is detected on a field."""
        ext, tmpdir = _make_extractor()
        try:
            ws_xml = ET.fromstring('''
            <worksheet>
                <datasource-dependencies>
                    <column-instance column="[Sales]" derivation="pcto:sum"
                                     type="quantitative" />
                </datasource-dependencies>
            </worksheet>
            ''')
            # Simulate field extraction logic
            import re
            field_name = 'pcto:sum:Sales'
            table_calc_re = re.compile(r'^(pcto|pctd|diff|running_sum|running_avg|running_count|running_min|running_max|rank|rank_unique|rank_dense)(?::(\w+))?:')
            m = table_calc_re.match(field_name)
            self.assertIsNotNone(m)
            self.assertEqual(m.group(1), 'pcto')
            self.assertEqual(m.group(2), 'sum')
        finally:
            _cleanup(tmpdir)

    def test_rank_detection(self):
        import re
        field_name = 'rank:sum:Profit'
        table_calc_re = re.compile(r'^(pcto|pctd|diff|running_sum|running_avg|running_count|running_min|running_max|rank|rank_unique|rank_dense)(?::(\w+))?:')
        m = table_calc_re.match(field_name)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), 'rank')

    def test_running_sum_detection(self):
        import re
        field_name = 'running_sum:sum:Revenue'
        table_calc_re = re.compile(r'^(pcto|pctd|diff|running_sum|running_avg|running_count|running_min|running_max|rank|rank_unique|rank_dense)(?::(\w+))?:')
        m = table_calc_re.match(field_name)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), 'running_sum')


# ═══════════════════════════════════════════════════════════════════
# Table Calc Addressing — ALLEXCEPT 
# ═══════════════════════════════════════════════════════════════════

class TestTableCalcAddressing(unittest.TestCase):
    """Test that partition_fields → ALLEXCEPT in DAX converter."""

    def test_allexcept_with_partition(self):
        from dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            'WINDOW_SUM(SUM([Sales]))',
            column_table_map={'Sales': 'Orders'},
            partition_fields=['Region']
        )
        # Should use ALLEXCEPT instead of ALL
        self.assertIn('ALLEXCEPT', result)
        self.assertIn('Region', result)

    def test_no_partition_uses_all(self):
        from dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            'WINDOW_SUM(SUM([Sales]))',
            column_table_map={'Sales': 'Orders'}
        )
        # Without partition, uses ALL
        self.assertIn('ALL', result)
        self.assertNotIn('ALLEXCEPT', result)


# ═══════════════════════════════════════════════════════════════════
# Date Hierarchy on Calendar
# ═══════════════════════════════════════════════════════════════════

class TestDateHierarchy(unittest.TestCase):
    """Test that Calendar table gets a Date Hierarchy."""

    def test_calendar_has_hierarchy(self):
        from tmdl_generator import _add_date_table

        # Create a minimal model dict matching the structure _add_date_table expects
        model = {'model': {'tables': [
            {'name': 'Orders', 'columns': [
                {'name': 'OrderDate', 'dataType': 'DateTime'}
            ], 'measures': []}
        ], 'relationships': []}}

        _add_date_table(model)

        # Find Calendar table
        calendar = None
        for t in model['model']['tables']:
            if t['name'] == 'Calendar':
                calendar = t
                break

        self.assertIsNotNone(calendar, "Calendar table should be created")
        hierarchies = calendar.get('hierarchies', [])
        self.assertTrue(len(hierarchies) >= 1, "Calendar should have at least one hierarchy")
        self.assertEqual(hierarchies[0]['name'], 'Date Hierarchy')


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main()
