"""
Unit tests for extract_tableau_data.py — Sprint 27 coverage push.

Covers individual extraction methods on TableauExtractor plus utility functions.
Uses XML snippets parsed with ET.fromstring() to test each method in isolation.
"""

import io
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))

from extract_tableau_data import (
    TableauExtractor,
    _clean_field_ref,
    _strip_brackets,
    _split_sql_values,
    _scan_delimited_sample,
)


# ═══════════════════════════════════════════════════════════════════
# Utility functions
# ═══════════════════════════════════════════════════════════════════

class TestCleanFieldRef(unittest.TestCase):
    def test_derivation_prefix(self):
        self.assertEqual(_clean_field_ref('none:Ship Mode:nk'), 'Ship Mode')

    def test_year_prefix(self):
        self.assertEqual(_clean_field_ref('yr:Order Date:ok'), 'Order Date')

    def test_table_calc_prefix(self):
        self.assertEqual(_clean_field_ref('pcto:sum:Sales:nk'), 'Sales')

    def test_running_sum_prefix(self):
        self.assertEqual(_clean_field_ref('running_sum:sum:Profit'), 'Profit')

    def test_no_prefix(self):
        self.assertEqual(_clean_field_ref('Revenue'), 'Revenue')

    def test_trunc_prefix(self):
        self.assertEqual(_clean_field_ref('trunc:Date'), 'Date')


class TestStripBrackets(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_strip_brackets('[Region]'), 'Region')

    def test_nested(self):
        self.assertEqual(_strip_brackets('[ds].[field]'), 'ds.field')


class TestSplitSqlValues(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(_split_sql_values("1, 'hello', NULL"),
                         ['1', "'hello'", 'NULL'])

    def test_comma_in_quote(self):
        result = _split_sql_values("'hello, world', 42")
        self.assertEqual(result[0], "'hello, world'")
        self.assertEqual(result[1], '42')

    def test_empty(self):
        self.assertEqual(_split_sql_values(''), [])


class TestScanDelimitedSample(unittest.TestCase):
    def test_tab_delimited(self):
        cols = ['A', 'B', 'C']
        text = "x\ty\tz\n1\t2\t3\n"
        result = _scan_delimited_sample(text, cols, 5)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['A'], 'x')

    def test_too_few_columns(self):
        result = _scan_delimited_sample("a\tb", ['X'], 5)
        self.assertEqual(result, [])

    def test_empty_lines_skipped(self):
        cols = ['A', 'B']
        text = "\t\n"
        result = _scan_delimited_sample(text, cols, 5)
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════════════
# Helper — create a minimal extractor (no real file needed)
# ═══════════════════════════════════════════════════════════════════

def _make_extractor(tmpdir=None):
    """Create a TableauExtractor with a dummy path."""
    d = tmpdir or tempfile.mkdtemp()
    dummy = os.path.join(d, 'dummy.twb')
    with open(dummy, 'w') as f:
        f.write('<workbook/>')
    ext = TableauExtractor(dummy, output_dir=d)
    return ext


# ═══════════════════════════════════════════════════════════════════
# read_tableau_file
# ═══════════════════════════════════════════════════════════════════

class TestReadTableauFile(unittest.TestCase):
    def test_read_twbx_zip(self):
        with tempfile.TemporaryDirectory() as d:
            twbx = os.path.join(d, 'test.twbx')
            xml_body = '<workbook><worksheets/></workbook>'
            with zipfile.ZipFile(twbx, 'w') as z:
                z.writestr('test.twb', xml_body)
            ext = TableauExtractor(twbx, output_dir=d)
            content = ext.read_tableau_file()
            self.assertIn('<workbook>', content)

    def test_read_twb_direct(self):
        with tempfile.TemporaryDirectory() as d:
            twb = os.path.join(d, 'test.twb')
            with open(twb, 'w', encoding='utf-8') as f:
                f.write('<workbook/>')
            ext = TableauExtractor(twb, output_dir=d)
            self.assertIsNotNone(ext.read_tableau_file())

    def test_unsupported_ext_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, 'test.txt')
            with open(bad, 'w') as f:
                f.write('hello')
            ext = TableauExtractor(bad, output_dir=d)
            self.assertIsNone(ext.read_tableau_file())


# ═══════════════════════════════════════════════════════════════════
# determine_chart_type / _map_tableau_mark_to_type / _infer_automatic
# ═══════════════════════════════════════════════════════════════════

class TestDetermineChartType(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_explicit_bar_mark(self):
        ws = ET.fromstring('<worksheet><pane><mark class="Bar"/></pane></worksheet>')
        self.assertEqual(self.ext.determine_chart_type(ws), 'clusteredBarChart')

    def test_style_mark_fallback(self):
        ws = ET.fromstring('<worksheet><style><mark class="Line"/></style></worksheet>')
        self.assertEqual(self.ext.determine_chart_type(ws), 'lineChart')

    def test_map_encoding_fallback(self):
        ws = ET.fromstring('<worksheet><encoding><map/></encoding></worksheet>')
        self.assertEqual(self.ext.determine_chart_type(ws), 'map')

    def test_no_mark_defaults_to_bar(self):
        ws = ET.fromstring('<worksheet></worksheet>')
        self.assertEqual(self.ext.determine_chart_type(ws), 'bar')

    def test_automatic_with_date_is_line(self):
        ws = ET.fromstring('''
        <worksheet>
            <pane><mark class="Automatic"/></pane>
            <table>
                <cols>[ds].[yr:Order Date:ok]</cols>
                <rows>[ds].[sum:Sales:qk]</rows>
            </table>
        </worksheet>''')
        self.assertEqual(self.ext.determine_chart_type(ws), 'lineChart')

    def test_automatic_no_fields_is_table(self):
        ws = ET.fromstring('''
        <worksheet>
            <pane><mark class="Automatic"/></pane>
            <table><cols></cols><rows></rows></table>
        </worksheet>''')
        self.assertEqual(self.ext.determine_chart_type(ws), 'table')


class TestMapTableauMarkToType(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_known_marks(self):
        cases = {
            'Pie': 'pieChart', 'Area': 'areaChart', 'Treemap': 'treemap',
            'Funnel': 'funnel', 'Waterfall': 'waterfallChart',
            'Box Plot': 'boxAndWhisker', 'Packed Bubble': 'scatterChart',
            'Donut': 'donutChart', 'KPI': 'card', 'Polygon': 'filledMap',
            'Word Cloud': 'wordCloud', 'Gauge': 'gauge',
        }
        for mark, expected in cases.items():
            self.assertEqual(self.ext._map_tableau_mark_to_type(mark), expected,
                             f'Failed for {mark}')

    def test_unknown_defaults_to_bar(self):
        self.assertEqual(self.ext._map_tableau_mark_to_type('UnknownType'),
                         'clusteredBarChart')


class TestInferAutomaticChartType(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_map_encoding(self):
        ws = ET.fromstring('''
        <worksheet>
            <encoding><map/></encoding>
            <table><cols>[ds].[none:Region:nk]</cols><rows>[ds].[none:Sales:qk]</rows></table>
        </worksheet>''')
        self.assertEqual(self.ext._infer_automatic_chart_type(ws), 'map')

    def test_geo_pair_is_map(self):
        ws = ET.fromstring('''
        <worksheet>
            <table>
                <cols>[ds].[none:Latitude:qk]</cols>
                <rows>[ds].[none:Longitude:qk]</rows>
            </table>
        </worksheet>''')
        self.assertEqual(self.ext._infer_automatic_chart_type(ws), 'map')

    def test_two_measures_is_scatter(self):
        ws = ET.fromstring('''
        <worksheet>
            <table>
                <cols>[ds].[sum:Sales:qk]</cols>
                <rows>[ds].[sum:Profit:qk]</rows>
            </table>
        </worksheet>''')
        self.assertEqual(self.ext._infer_automatic_chart_type(ws), 'scatterChart')

    def test_dimension_and_measure_is_bar(self):
        ws = ET.fromstring('''
        <worksheet>
            <table>
                <cols>[ds].[none:Region:nk]</cols>
                <rows>[ds].[sum:Sales:qk]</rows>
            </table>
        </worksheet>''')
        self.assertEqual(self.ext._infer_automatic_chart_type(ws), 'clusteredBarChart')


# ═══════════════════════════════════════════════════════════════════
# extract_worksheet_fields
# ═══════════════════════════════════════════════════════════════════

class TestExtractWorksheetFields(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_rows_cols_fields(self):
        ws = ET.fromstring('''
        <worksheet>
            <table>
                <cols>[ds].[none:Category:nk]</cols>
                <rows>[ds].[sum:Sales:qk]</rows>
            </table>
        </worksheet>''')
        fields = self.ext.extract_worksheet_fields(ws)
        self.assertEqual(len(fields), 2)
        names = [f['name'] for f in fields]
        self.assertIn('Category', names)
        self.assertIn('Sales', names)

    def test_table_calc_field(self):
        ws = ET.fromstring('''
        <worksheet>
            <table>
                <cols>[ds].[pcto:sum:Sales:nk]</cols>
                <rows></rows>
            </table>
        </worksheet>''')
        fields = self.ext.extract_worksheet_fields(ws)
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]['name'], 'Sales')
        self.assertEqual(fields[0]['table_calc'], 'pcto')

    def test_encoding_fields(self):
        ws = ET.fromstring('''
        <worksheet>
            <table><cols></cols><rows></rows></table>
            <encodings>
                <color column="[ds].[none:Region:nk]"/>
                <size column="[ds].[sum:Amount:qk]"/>
            </encodings>
        </worksheet>''')
        fields = self.ext.extract_worksheet_fields(ws)
        shelves = [f['shelf'] for f in fields]
        self.assertIn('color', shelves)
        self.assertIn('size', shelves)


# ═══════════════════════════════════════════════════════════════════
# extract_worksheet_filters
# ═══════════════════════════════════════════════════════════════════

class TestExtractWorksheetFilters(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_categorical_member(self):
        ws = ET.fromstring('''
        <worksheet>
            <filter column="[ds].[none:Region:nk]">
                <groupfilter function="member" member="West"/>
            </filter>
        </worksheet>''')
        filters = self.ext.extract_worksheet_filters(ws)
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]['type'], 'categorical')
        self.assertEqual(filters[0]['values'], ['West'])

    def test_categorical_union(self):
        ws = ET.fromstring('''
        <worksheet>
            <filter column="[ds].[none:Status:nk]">
                <groupfilter function="union">
                    <groupfilter function="member" member="Active"/>
                    <groupfilter function="member" member="Pending"/>
                </groupfilter>
            </filter>
        </worksheet>''')
        filters = self.ext.extract_worksheet_filters(ws)
        self.assertEqual(len(filters), 1)
        self.assertEqual(set(filters[0]['values']), {'Active', 'Pending'})

    def test_range_filter(self):
        ws = ET.fromstring('''
        <worksheet>
            <filter column="[ds].[none:Amount:qk]">
                <groupfilter function="range" from="100" to="500"/>
            </filter>
        </worksheet>''')
        filters = self.ext.extract_worksheet_filters(ws)
        self.assertEqual(filters[0]['type'], 'range')
        self.assertEqual(filters[0]['min'], '100')
        self.assertEqual(filters[0]['max'], '500')

    def test_except_filter(self):
        ws = ET.fromstring('''
        <worksheet>
            <filter column="[ds].[none:Region:nk]">
                <groupfilter function="except">
                    <groupfilter function="member" member="South"/>
                </groupfilter>
            </filter>
        </worksheet>''')
        filters = self.ext.extract_worksheet_filters(ws)
        self.assertTrue(filters[0]['exclude'])

    def test_date_part_detection(self):
        ws = ET.fromstring('''
        <worksheet>
            <filter column="[ds].[yr:Order Date:ok]">
                <groupfilter function="member" member="2024"/>
            </filter>
        </worksheet>''')
        filters = self.ext.extract_worksheet_filters(ws)
        self.assertEqual(filters[0]['date_part'], 'yr')

    def test_no_bracket_column(self):
        ws = ET.fromstring('''
        <worksheet>
            <filter column="SimpleCol">
                <groupfilter function="member" member="X"/>
            </filter>
        </worksheet>''')
        filters = self.ext.extract_worksheet_filters(ws)
        self.assertEqual(filters[0]['field'], 'SimpleCol')


# ═══════════════════════════════════════════════════════════════════
# extract_formatting
# ═══════════════════════════════════════════════════════════════════

class TestExtractFormatting(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_style_rule(self):
        el = ET.fromstring('''
        <worksheet>
            <style-rule element="cell">
                <format attr="font-size" value="12"/>
            </style-rule>
        </worksheet>''')
        fmt = self.ext.extract_formatting(el)
        self.assertIn('cell', fmt)
        self.assertEqual(fmt['cell']['font-size'], '12')

    def test_background_color(self):
        el = ET.fromstring('''
        <worksheet>
            <pane><format attr="fill-color" value="#FF0000"/></pane>
        </worksheet>''')
        fmt = self.ext.extract_formatting(el)
        self.assertEqual(fmt.get('background_color'), '#FF0000')

    def test_legend_info(self):
        el = ET.fromstring('''
        <worksheet>
            <legend position="right" title="Color Legend"/>
        </worksheet>''')
        fmt = self.ext.extract_formatting(el)
        self.assertIn('legend', fmt)
        self.assertEqual(fmt['legend']['position'], 'right')


# ═══════════════════════════════════════════════════════════════════
# extract_tooltips
# ═══════════════════════════════════════════════════════════════════

class TestExtractTooltips(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_text_tooltip_with_runs(self):
        ws = ET.fromstring('''
        <worksheet>
            <tooltip>
                <formatted-text>
                    <run bold="true">Sales: </run>
                    <run>[Amount]</run>
                </formatted-text>
            </tooltip>
        </worksheet>''')
        tips = self.ext.extract_tooltips(ws)
        self.assertEqual(len(tips), 1)
        self.assertEqual(tips[0]['type'], 'text')
        self.assertTrue(any(r.get('bold') for r in tips[0]['runs']))

    def test_viz_in_tooltip(self):
        ws = ET.fromstring('''
        <worksheet>
            <tooltip viz="DetailSheet"/>
        </worksheet>''')
        tips = self.ext.extract_tooltips(ws)
        self.assertEqual(len(tips), 1)
        self.assertEqual(tips[0]['type'], 'viz_in_tooltip')


# ═══════════════════════════════════════════════════════════════════
# extract_dashboard_objects
# ═══════════════════════════════════════════════════════════════════

class TestExtractDashboardObjects(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_text_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone type="text" id="1" x="0" y="0" w="200" h="50">
                <formatted-text><run>Hello World</run></formatted-text>
            </zone>
        </dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0]['type'], 'text')
        self.assertEqual(objs[0]['content'], 'Hello World')

    def test_image_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone type="bitmap" id="2" x="0" y="0" w="100" h="100">
                <zone-style><format attr="image" value="logo.png"/></zone-style>
            </zone>
        </dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(objs[0]['type'], 'image')
        self.assertEqual(objs[0]['source'], 'logo.png')

    def test_web_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone type="web" id="3" x="0" y="0" w="300" h="200" url="https://example.com"/>
        </dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(objs[0]['type'], 'web')
        self.assertEqual(objs[0]['url'], 'https://example.com')

    def test_blank_zone(self):
        db = ET.fromstring('''
        <dashboard><zone type="empty" id="4" x="0" y="0" w="50" h="50"/></dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(objs[0]['type'], 'blank')

    def test_nav_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone type="nav" id="5" x="0" y="0" w="100" h="30" target-sheet="Page2"/>
        </dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(objs[0]['type'], 'navigation_button')
        self.assertEqual(objs[0]['target_sheet'], 'Page2')

    def test_download_zone(self):
        db = ET.fromstring('''
        <dashboard><zone type="export" id="6" x="0" y="0" w="80" h="30"/></dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(objs[0]['type'], 'download_button')

    def test_extension_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone type="extension" id="7" x="0" y="0" w="400" h="300" extension-id="com.tableau.ext"/>
        </dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(objs[0]['type'], 'extension')
        self.assertEqual(objs[0]['extension_id'], 'com.tableau.ext')

    def test_filter_control_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone type="filter" name="Filter1" id="8" x="0" y="0" w="150" h="30"
                  param="none:Region:nk"/>
        </dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(objs[0]['type'], 'filter_control')
        self.assertEqual(objs[0]['calc_column_id'], 'Region')

    def test_worksheet_reference_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone name="Sales Chart" id="9" x="10" y="10" w="500" h="400"/>
        </dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(objs[0]['type'], 'worksheetReference')
        self.assertEqual(objs[0]['worksheetName'], 'Sales Chart')

    def test_floating_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone name="Float" id="10" x="0" y="0" w="100" h="100" is-floating="true"/>
        </dashboard>''')
        objs = self.ext.extract_dashboard_objects(db)
        self.assertEqual(objs[0]['layout'], 'floating')


# ═══════════════════════════════════════════════════════════════════
# extract_mark_encoding
# ═══════════════════════════════════════════════════════════════════

class TestExtractMarkEncoding(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_color_encoding_quantitative(self):
        ws = ET.fromstring('''
        <worksheet>
            <encodings>
                <color column="[ds].[sum:Profit:qk]" palette="green-blue"/>
            </encodings>
        </worksheet>''')
        enc = self.ext.extract_mark_encoding(ws)
        self.assertIn('color', enc)
        self.assertEqual(enc['color']['type'], 'quantitative')
        self.assertEqual(enc['color']['palette'], 'green-blue')

    def test_color_with_thresholds(self):
        ws = ET.fromstring('''
        <worksheet>
            <encodings>
                <color column="[ds].[none:Score:nk]">
                    <bucket color="#FF0000" value="50"/>
                    <bucket color="#00FF00" value="100"/>
                </color>
            </encodings>
        </worksheet>''')
        enc = self.ext.extract_mark_encoding(ws)
        self.assertEqual(len(enc['color']['thresholds']), 2)
        self.assertEqual(enc['color']['thresholds'][0]['value'], 50.0)

    def test_size_encoding(self):
        ws = ET.fromstring('''
        <worksheet>
            <encodings>
                <size column="[ds].[sum:Amount:qk]"/>
            </encodings>
        </worksheet>''')
        enc = self.ext.extract_mark_encoding(ws)
        self.assertIn('size', enc)
        self.assertEqual(enc['size']['field'], 'Amount')

    def test_shape_encoding(self):
        ws = ET.fromstring('''
        <worksheet>
            <encodings>
                <shape column="[ds].[none:Category:nk]"/>
            </encodings>
        </worksheet>''')
        enc = self.ext.extract_mark_encoding(ws)
        self.assertIn('shape', enc)

    def test_label_encoding(self):
        ws = ET.fromstring('''
        <worksheet>
            <encodings>
                <label column="[ds].[sum:Sales:qk]" show-label="true"
                       label-position="top" font-size="10"/>
            </encodings>
        </worksheet>''')
        enc = self.ext.extract_mark_encoding(ws)
        self.assertTrue(enc['label']['show'])
        self.assertEqual(enc['label']['position'], 'top')


# ═══════════════════════════════════════════════════════════════════
# extract_reference_lines
# ═══════════════════════════════════════════════════════════════════

class TestExtractReferenceLines(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_simple_line(self):
        ws = ET.fromstring('''
        <worksheet>
            <reference-line value="100" label="Target" axis="y"
                           style="dashed" computation="constant"/>
        </worksheet>''')
        lines = self.ext.extract_reference_lines(ws)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['value'], '100')
        self.assertEqual(lines[0]['label'], 'Target')
        self.assertFalse(lines[0]['is_band'])

    def test_band_with_two_values(self):
        ws = ET.fromstring('''
        <worksheet>
            <reference-line>
                <reference-line-value value="50"/>
                <reference-line-value value="150"/>
            </reference-line>
        </worksheet>''')
        lines = self.ext.extract_reference_lines(ws)
        self.assertTrue(lines[0]['is_band'])
        self.assertEqual(lines[0]['value_from'], '50')
        self.assertEqual(lines[0]['value_to'], '150')

    def test_reference_band_element(self):
        ws = ET.fromstring('''
        <worksheet>
            <reference-band value-from="10" value-to="90" color="#E0E0E0"/>
        </worksheet>''')
        lines = self.ext.extract_reference_lines(ws)
        self.assertEqual(lines[0]['type'], 'band')

    def test_reference_distribution(self):
        ws = ET.fromstring('''
        <worksheet>
            <reference-distribution computation="percentile" percentile="95"/>
        </worksheet>''')
        lines = self.ext.extract_reference_lines(ws)
        self.assertEqual(lines[0]['type'], 'distribution')


# ═══════════════════════════════════════════════════════════════════
# extract_annotations
# ═══════════════════════════════════════════════════════════════════

class TestExtractAnnotations(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_text_annotation(self):
        ws = ET.fromstring('''
        <worksheet>
            <annotation type="point">
                <formatted-text><run>Peak Sales</run></formatted-text>
                <point x="100" y="200"/>
            </annotation>
        </worksheet>''')
        anns = self.ext.extract_annotations(ws)
        self.assertEqual(len(anns), 1)
        self.assertEqual(anns[0]['text'], 'Peak Sales')
        self.assertEqual(anns[0]['position']['x'], '100')

    def test_empty_annotation_skipped(self):
        ws = ET.fromstring('''
        <worksheet>
            <annotation type="point">
                <formatted-text></formatted-text>
            </annotation>
        </worksheet>''')
        anns = self.ext.extract_annotations(ws)
        self.assertEqual(len(anns), 0)


# ═══════════════════════════════════════════════════════════════════
# extract_workbook_actions
# ═══════════════════════════════════════════════════════════════════

class TestExtractWorkbookActions(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        # Redirect stdout
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_filter_action(self):
        root = ET.fromstring('''
        <workbook>
            <action type="filter" name="FilterRegion">
                <source worksheet="Sheet1"/>
                <target worksheet="Sheet2"/>
                <field-mapping source-field="[Region]" target-field="[Region]"/>
            </action>
        </workbook>''')
        self.ext.extract_workbook_actions(root)
        actions = self.ext.workbook_data['actions']
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['type'], 'filter')
        self.assertEqual(len(actions[0]['field_mappings']), 1)

    def test_highlight_action(self):
        root = ET.fromstring('''
        <workbook>
            <action type="highlight" name="HighlightCat">
                <source worksheet="Sheet1"/>
            </action>
        </workbook>''')
        self.ext.extract_workbook_actions(root)
        self.assertEqual(self.ext.workbook_data['actions'][0]['type'], 'highlight')

    def test_url_action(self):
        root = ET.fromstring('''
        <workbook>
            <action type="url" name="GoToSite" url="https://example.com"/>
        </workbook>''')
        self.ext.extract_workbook_actions(root)
        self.assertEqual(self.ext.workbook_data['actions'][0]['url'], 'https://example.com')

    def test_param_action(self):
        root = ET.fromstring('''
        <workbook>
            <action type="param" name="SetParam" param="[Parameter 1]"
                    source-field="[Region]"/>
        </workbook>''')
        self.ext.extract_workbook_actions(root)
        act = self.ext.workbook_data['actions'][0]
        self.assertEqual(act['parameter'], '[Parameter 1]')
        self.assertEqual(act['source_field'], 'Region')

    def test_set_value_action(self):
        root = ET.fromstring('''
        <workbook>
            <action type="set-value" name="UpdateSet">
                <set name="[TopCustomers]" field="[Customer]" behavior="assign"/>
            </action>
        </workbook>''')
        self.ext.extract_workbook_actions(root)
        act = self.ext.workbook_data['actions'][0]
        self.assertEqual(act['target_set'], 'TopCustomers')
        self.assertEqual(act['assign_behavior'], 'assign')

    def test_clearing_and_run_on(self):
        root = ET.fromstring('''
        <workbook>
            <action type="filter" name="Auto" clearing="keep" run-on="select"/>
        </workbook>''')
        self.ext.extract_workbook_actions(root)
        act = self.ext.workbook_data['actions'][0]
        self.assertEqual(act['clearing'], 'keep')
        self.assertEqual(act['run_on'], 'select')


# ═══════════════════════════════════════════════════════════════════
# extract_sets
# ═══════════════════════════════════════════════════════════════════

class TestExtractSets(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_set_by_members(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <column name="[TopRegions]" caption="Top Regions" datatype="boolean">
                    <set>
                        <member value="West"/>
                        <member value="East"/>
                    </set>
                </column>
            </datasource>
        </workbook>''')
        self.ext.extract_sets(root)
        s = self.ext.workbook_data['sets']
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]['members'], ['West', 'East'])

    def test_set_by_formula(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <column name="[HighValue]" datatype="boolean">
                    <set formula="[Sales] > 1000"/>
                </column>
            </datasource>
        </workbook>''')
        self.ext.extract_sets(root)
        self.assertEqual(self.ext.workbook_data['sets'][0]['formula'], '[Sales] > 1000')

    def test_set_detected_by_name(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <column name="[my-set-filter]" datatype="boolean"/>
            </datasource>
        </workbook>''')
        self.ext.extract_sets(root)
        self.assertEqual(len(self.ext.workbook_data['sets']), 1)


# ═══════════════════════════════════════════════════════════════════
# extract_groups
# ═══════════════════════════════════════════════════════════════════

class TestExtractGroups(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_combined_group(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <group name="[CombinedField]" caption="Combined Field">
                    <groupfilter function="crossjoin">
                        <groupfilter function="level-members" level="[none:City:nk]"/>
                        <groupfilter function="level-members" level="[none:State:nk]"/>
                    </groupfilter>
                </group>
            </datasource>
        </workbook>''')
        self.ext.extract_groups(root)
        g = self.ext.workbook_data['groups']
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]['group_type'], 'combined')
        self.assertIn('City', g[0]['source_fields'])

    def test_values_group(self):
        root = ET.fromstring('''
        <workbook xmlns:user="http://www.tableausoftware.com/xml/user">
            <datasource name="ds1">
                <group name="[Region Group]" caption="Region Group">
                    <groupfilter function="union">
                        <groupfilter function="union">
                            <groupfilter function="member" level="[Region]"
                                         member="West" user:ui-marker="true"
                                         user:ui-marker-value="Western"/>
                            <groupfilter function="member" level="[Region]" member="West"/>
                        </groupfilter>
                    </groupfilter>
                </group>
            </datasource>
        </workbook>''')
        self.ext.extract_groups(root)
        g = self.ext.workbook_data['groups']
        self.assertEqual(g[0]['group_type'], 'values')

    def test_unknown_group_type(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <group name="[Other]" caption="Other">
                    <groupfilter function="someNewType"/>
                </group>
            </datasource>
        </workbook>''')
        self.ext.extract_groups(root)
        g = self.ext.workbook_data['groups']
        self.assertEqual(g[0]['group_type'], 'someNewType')


# ═══════════════════════════════════════════════════════════════════
# extract_bins
# ═══════════════════════════════════════════════════════════════════

class TestExtractBins(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_bin_extraction(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <column name="[AgeBin]" caption="Age (bin)" datatype="integer">
                    <bin source="[Age]" size="5"/>
                </column>
            </datasource>
        </workbook>''')
        self.ext.extract_bins(root)
        b = self.ext.workbook_data['bins']
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]['source_field'], 'Age')
        self.assertEqual(b[0]['size'], '5')


# ═══════════════════════════════════════════════════════════════════
# extract_hierarchies
# ═══════════════════════════════════════════════════════════════════

class TestExtractHierarchies(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_hierarchy(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <drill-path name="Location">
                    <field name="[Country]"/>
                    <field name="[State]"/>
                    <field name="[City]"/>
                </drill-path>
            </datasource>
        </workbook>''')
        self.ext.extract_hierarchies(root)
        h = self.ext.workbook_data['hierarchies']
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]['levels'], ['Country', 'State', 'City'])


# ═══════════════════════════════════════════════════════════════════
# extract_sort_orders
# ═══════════════════════════════════════════════════════════════════

class TestExtractSortOrders(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_manual_sort(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <sort column="[Priority]" direction="ASC" type="manual">
                    <value>High</value>
                    <value>Medium</value>
                    <value>Low</value>
                </sort>
            </datasource>
        </workbook>''')
        self.ext.extract_sort_orders(root)
        s = self.ext.workbook_data['sort_orders']
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]['sort_type'], 'manual')
        self.assertEqual(s[0]['manual_values'], ['High', 'Medium', 'Low'])

    def test_computed_sort(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <sort column="[Category]" direction="DESC" type="computed"
                      sort-using="[sum:Sales]"/>
            </datasource>
        </workbook>''')
        self.ext.extract_sort_orders(root)
        s = self.ext.workbook_data['sort_orders']
        self.assertEqual(s[0]['sort_using'], '[sum:Sales]')


# ═══════════════════════════════════════════════════════════════════
# extract_aliases
# ═══════════════════════════════════════════════════════════════════

class TestExtractAliases(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_alias_extraction(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <column name="[Status]">
                    <aliases>
                        <alias key="A" value="Active"/>
                        <alias key="I" value="Inactive"/>
                    </aliases>
                </column>
            </datasource>
        </workbook>''')
        self.ext.extract_aliases(root)
        a = self.ext.workbook_data['aliases']
        self.assertIn('Status', a)
        self.assertEqual(a['Status']['A'], 'Active')


# ═══════════════════════════════════════════════════════════════════
# extract_user_filters
# ═══════════════════════════════════════════════════════════════════

class TestExtractUserFilters(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self.ext.workbook_data['datasources'] = []
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_user_filter_element(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1" caption="Sales">
                <user-filter name="[RegionFilter]" column="[Region]">
                    <member user="alice@company.com" value="West"/>
                    <member user="bob@company.com" value="East"/>
                </user-filter>
            </datasource>
        </workbook>''')
        self.ext.extract_user_filters(root)
        uf = self.ext.workbook_data['user_filters']
        self.assertEqual(len(uf), 1)
        self.assertEqual(uf[0]['type'], 'user_filter')
        self.assertEqual(len(uf[0]['user_mappings']), 2)

    def test_calculated_security(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1" caption="Sales">
                <column name="[RLS Rule]" caption="RLS Rule">
                    <calculation formula="IF USERNAME() = [Manager] THEN TRUE ELSE FALSE END"/>
                </column>
            </datasource>
        </workbook>''')
        self.ext.extract_user_filters(root)
        uf = self.ext.workbook_data['user_filters']
        self.assertEqual(len(uf), 1)
        self.assertEqual(uf[0]['type'], 'calculated_security')
        self.assertIn('USERNAME', uf[0]['functions_used'])

    def test_ismemberof_groups(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1" caption="Sales">
                <column name="[GroupFilter]" caption="GroupFilter">
                    <calculation formula="ISMEMBEROF('Sales Team') OR ISMEMBEROF('Admin')"/>
                </column>
            </datasource>
        </workbook>''')
        self.ext.extract_user_filters(root)
        uf = self.ext.workbook_data['user_filters']
        groups = uf[0]['ismemberof_groups']
        self.assertIn('Sales Team', groups)
        self.assertIn('Admin', groups)


# ═══════════════════════════════════════════════════════════════════
# extract_datasource_filters / _parse_datasource_filter
# ═══════════════════════════════════════════════════════════════════

class TestExtractDatasourceFilters(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_categorical_filter(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1" caption="Sales">
                <filter column="[Region]" class="categorical" type="included">
                    <groupfilter member="West"/>
                    <groupfilter member="East"/>
                </filter>
            </datasource>
        </workbook>''')
        self.ext.extract_datasource_filters(root)
        f = self.ext.workbook_data['datasource_filters']
        self.assertEqual(len(f), 1)
        self.assertIn('West', f[0]['values'])

    def test_parse_filter_no_column(self):
        filt = ET.fromstring('<filter class="categorical"/>')
        result = TableauExtractor._parse_datasource_filter(filt, 'ds1')
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# extract_trend_lines
# ═══════════════════════════════════════════════════════════════════

class TestExtractTrendLines(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_linear_trend(self):
        ws = ET.fromstring('''
        <worksheet>
            <trend-line type="linear" color="#0000FF"
                       show-equation="true" show-r-squared="true"/>
        </worksheet>''')
        tl = self.ext.extract_trend_lines(ws)
        self.assertEqual(len(tl), 1)
        self.assertEqual(tl[0]['type'], 'linear')
        self.assertTrue(tl[0]['show_equation'])

    def test_nested_trend_lines(self):
        ws = ET.fromstring('''
        <worksheet>
            <trend-lines>
                <trend-line type="polynomial" per-color="true"/>
            </trend-lines>
        </worksheet>''')
        tl = self.ext.extract_trend_lines(ws)
        self.assertEqual(len(tl), 1)
        self.assertTrue(tl[0]['per_color'])


# ═══════════════════════════════════════════════════════════════════
# extract_pages_shelf
# ═══════════════════════════════════════════════════════════════════

class TestExtractPagesShelf(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_pages_field(self):
        ws = ET.fromstring('<worksheet><pages>[ds].[Year]</pages></worksheet>')
        p = self.ext.extract_pages_shelf(ws)
        self.assertEqual(p['field'], 'Year')
        self.assertEqual(p['datasource'], 'ds')

    def test_no_pages(self):
        ws = ET.fromstring('<worksheet/>')
        p = self.ext.extract_pages_shelf(ws)
        self.assertEqual(p, {})


# ═══════════════════════════════════════════════════════════════════
# extract_table_calcs
# ═══════════════════════════════════════════════════════════════════

class TestExtractTableCalcs(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_table_calc(self):
        ws = ET.fromstring('''
        <worksheet>
            <table-calc column="[Sales]" type="Across" ordering-type="Rows"
                        direction="left-to-right">
                <compute-using>Region</compute-using>
                <order-by column="[Date]" direction="ASC"/>
            </table-calc>
        </worksheet>''')
        tc = self.ext.extract_table_calcs(ws)
        self.assertEqual(len(tc), 1)
        self.assertEqual(tc[0]['field'], 'Sales')
        self.assertIn('Region', tc[0]['compute_using'])
        self.assertEqual(tc[0]['order_by'][0]['field'], 'Date')


# ═══════════════════════════════════════════════════════════════════
# extract_forecasting
# ═══════════════════════════════════════════════════════════════════

class TestExtractForecasting(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_forecast(self):
        ws = ET.fromstring('''
        <worksheet>
            <forecast forecast-forward="12" prediction-interval="90"
                     model="multiplicative" show-prediction-bands="true"/>
        </worksheet>''')
        fc = self.ext.extract_forecasting(ws)
        self.assertEqual(len(fc), 1)
        self.assertEqual(fc[0]['periods'], 12)
        self.assertEqual(fc[0]['model'], 'multiplicative')

    def test_forecast_model_fallback(self):
        ws = ET.fromstring('''
        <worksheet>
            <forecast-model periods="6" model="additive"/>
        </worksheet>''')
        fc = self.ext.extract_forecasting(ws)
        self.assertEqual(len(fc), 1)
        self.assertEqual(fc[0]['periods'], 6)


# ═══════════════════════════════════════════════════════════════════
# extract_map_options
# ═══════════════════════════════════════════════════════════════════

class TestExtractMapOptions(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_map_options(self):
        ws = ET.fromstring('''
        <worksheet>
            <map-options washout="0.5" style="satellite" pan-zoom="true" unit="km">
                <map-layer name="Base" enabled="true"/>
            </map-options>
        </worksheet>''')
        mo = self.ext.extract_map_options(ws)
        self.assertEqual(mo['washout'], '0.5')
        self.assertEqual(mo['style'], 'satellite')
        self.assertEqual(len(mo['layers']), 1)

    def test_no_map_options(self):
        ws = ET.fromstring('<worksheet/>')
        self.assertEqual(self.ext.extract_map_options(ws), {})


# ═══════════════════════════════════════════════════════════════════
# extract_clustering
# ═══════════════════════════════════════════════════════════════════

class TestExtractClustering(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_cluster(self):
        ws = ET.fromstring('''
        <worksheet>
            <cluster num-clusters="4">
                <variable column="[Sales]"/>
                <variable column="[Profit]"/>
            </cluster>
        </worksheet>''')
        cl = self.ext.extract_clustering(ws)
        self.assertEqual(len(cl), 1)
        self.assertEqual(cl[0]['num_clusters'], '4')
        self.assertEqual(len(cl[0]['variables']), 2)


# ═══════════════════════════════════════════════════════════════════
# extract_dual_axis_sync
# ═══════════════════════════════════════════════════════════════════

class TestExtractDualAxisSync(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_dual_axis(self):
        ws = ET.fromstring('''
        <worksheet>
            <axis type="y"/><axis type="y" synchronized="true"/>
        </worksheet>''')
        da = self.ext.extract_dual_axis_sync(ws)
        self.assertTrue(da['enabled'])
        self.assertTrue(da['synchronized'])

    def test_no_dual_axis(self):
        ws = ET.fromstring('<worksheet/>')
        da = self.ext.extract_dual_axis_sync(ws)
        self.assertEqual(da, {})


# ═══════════════════════════════════════════════════════════════════
# extract_totals_subtotals
# ═══════════════════════════════════════════════════════════════════

class TestExtractTotalsSubtotals(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_grand_totals(self):
        ws = ET.fromstring('''
        <worksheet>
            <grandtotals>
                <grand-total type="rows" position="bottom" enabled="true"/>
            </grandtotals>
        </worksheet>''')
        t = self.ext.extract_totals_subtotals(ws)
        self.assertEqual(len(t['grand_totals']), 1)
        self.assertTrue(t['grand_totals'][0]['enabled'])

    def test_rows_total_shorthand(self):
        ws = ET.fromstring('''
        <worksheet><rows-total position="bottom" enabled="true"/></worksheet>''')
        t = self.ext.extract_totals_subtotals(ws)
        self.assertEqual(len(t['grand_totals']), 1)


# ═══════════════════════════════════════════════════════════════════
# extract_show_hide_headers
# ═══════════════════════════════════════════════════════════════════

class TestExtractShowHideHeaders(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_hidden_row_headers(self):
        ws = ET.fromstring('''
        <worksheet>
            <style show-row-headers="false" show-col-headers="true"/>
        </worksheet>''')
        h = self.ext.extract_show_hide_headers(ws)
        self.assertFalse(h['rows'])
        self.assertTrue(h['columns'])

    def test_table_show_header_false(self):
        ws = ET.fromstring('''
        <worksheet><table show-header="false"/></worksheet>''')
        h = self.ext.extract_show_hide_headers(ws)
        self.assertFalse(h['rows'])


# ═══════════════════════════════════════════════════════════════════
# extract_dynamic_title
# ═══════════════════════════════════════════════════════════════════

class TestExtractDynamicTitle(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_static_title(self):
        ws = ET.fromstring('''
        <worksheet><title><run>Sales Report</run></title></worksheet>''')
        dt = self.ext.extract_dynamic_title(ws)
        self.assertFalse(dt['is_dynamic'])
        self.assertEqual(dt['parts'][0]['value'], 'Sales Report')

    def test_dynamic_title_with_field(self):
        ws = ET.fromstring('''
        <worksheet>
            <title>
                <run>Sales for </run>
                <run><field name="[Region]"/></run>
            </title>
        </worksheet>''')
        dt = self.ext.extract_dynamic_title(ws)
        self.assertTrue(dt['is_dynamic'])

    def test_no_title(self):
        ws = ET.fromstring('<worksheet/>')
        self.assertIsNone(self.ext.extract_dynamic_title(ws))


# ═══════════════════════════════════════════════════════════════════
# extract_show_hide_containers
# ═══════════════════════════════════════════════════════════════════

class TestExtractShowHideContainers(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_show_hide_button(self):
        db = ET.fromstring('''
        <dashboard>
            <zone name="FilterPanel" id="1">
                <show-hide-button default-state="hide" style="arrow"/>
            </zone>
        </dashboard>''')
        c = self.ext.extract_show_hide_containers(db)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]['default_state'], 'hide')


# ═══════════════════════════════════════════════════════════════════
# extract_dynamic_zone_visibility
# ═══════════════════════════════════════════════════════════════════

class TestExtractDynamicZoneVisibility(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_dynamic_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone name="ConditionalChart" id="1">
                <dynamic-zone-visibility field="[ShowDetail]" value="true"
                                         condition="equals" default="false"/>
            </zone>
        </dashboard>''')
        z = self.ext.extract_dynamic_zone_visibility(db)
        self.assertEqual(len(z), 1)
        self.assertEqual(z[0]['field'], '[ShowDetail]')
        self.assertFalse(z[0]['default_visible'])


# ═══════════════════════════════════════════════════════════════════
# extract_floating_tiled
# ═══════════════════════════════════════════════════════════════════

class TestExtractFloatingTiled(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_floating_zone(self):
        db = ET.fromstring('''
        <dashboard>
            <zone name="Logo" id="1" is-floating="true" x="10" y="20" w="100" h="50"/>
            <zone name="Chart" id="2" x="0" y="0" w="800" h="600"/>
        </dashboard>''')
        fl = self.ext.extract_floating_tiled(db)
        self.assertEqual(len(fl), 2)
        self.assertTrue(fl[0]['is_floating'])
        self.assertFalse(fl[1]['is_floating'])


# ═══════════════════════════════════════════════════════════════════
# extract_analytics_pane_stats
# ═══════════════════════════════════════════════════════════════════

class TestExtractAnalyticsPaneStats(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_stat_line(self):
        ws = ET.fromstring('''
        <worksheet><stat-line stat="mean" scope="per-pane"/></worksheet>''')
        stats = self.ext.extract_analytics_pane_stats(ws)
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]['type'], 'stat_line')
        self.assertEqual(stats[0]['stat'], 'mean')

    def test_distribution_band(self):
        ws = ET.fromstring('''
        <worksheet>
            <distribution-band computation="percentile" value-from="25" value-to="75"/>
        </worksheet>''')
        stats = self.ext.extract_analytics_pane_stats(ws)
        self.assertEqual(stats[0]['type'], 'distribution_band')

    def test_confidence_interval(self):
        ws = ET.fromstring('''
        <worksheet><confidence-interval level="99"/></worksheet>''')
        stats = self.ext.extract_analytics_pane_stats(ws)
        self.assertEqual(stats[0]['type'], 'confidence_interval')
        self.assertEqual(stats[0]['level'], '99')

    def test_stat_reference_from_ref_line(self):
        ws = ET.fromstring('''
        <worksheet>
            <reference-line computation="median" value="" scope="per-pane"/>
        </worksheet>''')
        stats = self.ext.extract_analytics_pane_stats(ws)
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]['computation'], 'median')


# ═══════════════════════════════════════════════════════════════════
# extract_layout_containers / extract_device_layouts / extract_theme
# ═══════════════════════════════════════════════════════════════════

class TestExtractLayoutContainers(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_layout_container(self):
        db = ET.fromstring('''
        <dashboard>
            <layout-container orientation="horizontal" x="0" y="0" w="800" h="200">
                <zone name="Chart1"/>
                <zone name="Chart2"/>
            </layout-container>
        </dashboard>''')
        lc = self.ext.extract_layout_containers(db)
        self.assertEqual(len(lc), 1)
        self.assertEqual(lc[0]['orientation'], 'horizontal')
        self.assertEqual(len(lc[0]['children']), 2)


class TestExtractDeviceLayouts(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_phone_layout(self):
        db = ET.fromstring('''
        <dashboard>
            <device-layout device-type="phone" auto-generated="true">
                <zone name="Chart1" x="0" y="0" w="375" h="500"/>
            </device-layout>
        </dashboard>''')
        dl = self.ext.extract_device_layouts(db)
        self.assertEqual(len(dl), 1)
        self.assertEqual(dl[0]['device_type'], 'phone')
        self.assertTrue(dl[0]['auto_generated'])


class TestExtractTheme(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_color_palette(self):
        db = ET.fromstring('''
        <dashboard>
            <preferences>
                <color-palette>
                    <color>#FF0000</color>
                    <color>#00FF00</color>
                </color-palette>
            </preferences>
        </dashboard>''')
        theme = self.ext.extract_theme(db)
        self.assertEqual(theme['color_palette'], ['#FF0000', '#00FF00'])

    def test_custom_named_palette(self):
        db = ET.fromstring('''
        <dashboard>
            <color-palette name="MyPalette" type="sequential">
                <color>#AAA</color>
                <color>#BBB</color>
            </color-palette>
        </dashboard>''')
        theme = self.ext.extract_theme(db)
        self.assertIn('MyPalette', theme['custom_palettes'])


# ═══════════════════════════════════════════════════════════════════
# extract_story_points / extract_allowable_values
# ═══════════════════════════════════════════════════════════════════

class TestExtractStoryPoints(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_story_points(self):
        story = ET.fromstring('''
        <story>
            <story-point captured-sheet="Overview">
                <caption>Introduction</caption>
                <description>First slide</description>
                <filter column="[Region]"><value>West</value></filter>
            </story-point>
        </story>''')
        sp = self.ext.extract_story_points(story)
        self.assertEqual(len(sp), 1)
        self.assertEqual(sp[0]['caption'], 'Introduction')
        self.assertEqual(sp[0]['filters_state'][0]['field'], 'Region')


class TestExtractAllowableValues(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()

    def test_old_format_members(self):
        param = ET.fromstring('''
        <column param-domain-type="list">
            <members>
                <member value="Option A" alias="A"/>
                <member value="Option B"/>
            </members>
        </column>''')
        vals = self.ext.extract_allowable_values(param)
        self.assertEqual(len(vals), 2)
        self.assertEqual(vals[0]['alias'], 'A')

    def test_new_format_domain(self):
        param = ET.fromstring('''
        <parameter>
            <domain>
                <member value="&quot;All&quot;" alias="&quot;All&quot;"/>
            </domain>
        </parameter>''')
        vals = self.ext.extract_allowable_values(param)
        self.assertEqual(len(vals), 1)
        self.assertEqual(vals[0]['value'], 'All')

    def test_range(self):
        param = ET.fromstring('''
        <column param-domain-type="range">
            <range min="0" max="100" granularity="1"/>
        </column>''')
        vals = self.ext.extract_allowable_values(param)
        self.assertEqual(len(vals), 1)
        self.assertEqual(vals[0]['type'], 'range')
        self.assertEqual(vals[0]['min'], '0')


# ═══════════════════════════════════════════════════════════════════
# Hyper metadata extraction
# ═══════════════════════════════════════════════════════════════════

class TestExtractHyperSampleRows(unittest.TestCase):
    def test_insert_statements(self):
        text = '''CREATE TABLE "Extract" (col1 text, col2 integer)
INSERT INTO "Extract" VALUES ('hello', 42), ('world', 99)'''
        cols = [{'name': 'col1'}, {'name': 'col2'}]
        rows = TableauExtractor._extract_hyper_sample_rows(text, 'Extract', cols, 5)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['col1'], 'hello')
        self.assertEqual(rows[1]['col2'], '99')

    def test_no_inserts_fallback(self):
        text = "col1\tcol2\nA\tB\n"
        cols = [{'name': 'col1'}, {'name': 'col2'}]
        rows = TableauExtractor._extract_hyper_sample_rows(text, 'Missing', cols, 5)
        # Falls back to delimited scan
        self.assertIsInstance(rows, list)


# ═══════════════════════════════════════════════════════════════════
# extract_custom_sql / extract_published_datasources
# ═══════════════════════════════════════════════════════════════════

class TestExtractCustomSql(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_custom_sql_extraction(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <relation type="text" name="Custom SQL">SELECT * FROM orders</relation>
            </datasource>
        </workbook>''')
        self.ext.extract_custom_sql(root)
        sql = self.ext.workbook_data['custom_sql']
        self.assertEqual(len(sql), 1)
        self.assertIn('SELECT', sql[0]['query'])


class TestExtractPublishedDatasources(unittest.TestCase):
    def setUp(self):
        self.ext = _make_extractor()
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_repo_location(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="Published" caption="Shared Sales">
                <repository-location site="default" path="/datasources/sales" id="abc123"/>
            </datasource>
        </workbook>''')
        self.ext.extract_published_datasources(root)
        pub = self.ext.workbook_data['published_datasources']
        self.assertEqual(len(pub), 1)
        self.assertEqual(pub[0]['name'], 'Shared Sales')

    def test_sqlproxy_connection(self):
        root = ET.fromstring('''
        <workbook>
            <datasource name="ProxiedDS" caption="Proxied">
                <connection class="sqlproxy" server="tableau.company.com" dbname="/shared/ds"/>
            </datasource>
        </workbook>''')
        self.ext.extract_published_datasources(root)
        pub = self.ext.workbook_data['published_datasources']
        self.assertEqual(len(pub), 1)


if __name__ == '__main__':
    unittest.main()
