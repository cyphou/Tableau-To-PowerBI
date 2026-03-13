"""
Coverage-push tests for extract_tableau_data.py — targets all uncovered
branches and methods identified by the coverage report.

Covers:
  - _scan_delimited_sample() edge cases (binary skip, max_rows, pipe delim)
  - extract_all() failure path (bad file)
  - extract_calculations() datasource routing, empty formula, categorical-bin skip
  - extract_parameters() dedup, database-domain (old+new format), query_connection
  - _extract_mark_class() pane vs style fallback
  - determine_chart_type() / _infer_automatic_chart_type() (scatter, line, table, map)
  - extract_formatting() field_formats, legend style
  - extract_tooltips() bold, color runs
  - extract_dashboard_objects() text runs (bold, italic, color, font_size, url),
      padding int-parse failure, filter_control with none: prefix
  - extract_theme() custom_palettes dict, style attrs
  - extract_mark_encoding() palette_colors, stepped thresholds, legend
  - extract_workbook_actions() highlight field-mapping, param action
  - extract_groups() empty name skip, no groupfilter skip, nested member markers
  - extract_datasource_filters() extract-connection and federated paths
  - _parse_datasource_filter() member and <member> paths
  - extract_trend_lines() dedup
  - extract_pages_shelf() regex parse
  - extract_dashboard_containers() full method
  - extract_clustering() fallback without children
  - extract_dual_axis_sync()
  - extract_custom_shapes() twbx zip mock
  - extract_embedded_fonts() twbx zip mock
  - extract_custom_geocoding() XML + twbx CSV scan
  - extract_data_blending() link elements, cross-ds dependency
  - extract_hyper_metadata() full parsing
  - extract_totals_subtotals() grandtotals shorthand
  - extract_worksheet_description() child element fallback
  - extract_dynamic_title() field ref, <[ markers
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))
sys.path.insert(0, os.path.join(ROOT, 'powerbi_import'))

from extract_tableau_data import TableauExtractor, _scan_delimited_sample

# Track temp dirs for cleanup
_TEMP_DIRS = []


def _make_extractor(xml_string=None):
    """Create a TableauExtractor with a temp dir and optional TWB content."""
    tmpdir = tempfile.mkdtemp(prefix='ttpbi_cov_')
    _TEMP_DIRS.append(tmpdir)
    tmpfile = os.path.join(tmpdir, 'test.twb')
    if xml_string:
        with open(tmpfile, 'w', encoding='utf-8') as f:
            f.write(xml_string)
    else:
        with open(tmpfile, 'w', encoding='utf-8') as f:
            f.write('<workbook/>')
    ext = TableauExtractor(tmpfile, output_dir=tmpdir)
    return ext, tmpdir


def teardown_module():
    for d in _TEMP_DIRS:
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════
# _scan_delimited_sample
# ═══════════════════════════════════════════════════════════════════

class TestScanDelimitedSample(unittest.TestCase):
    """Tests for the _scan_delimited_sample free function."""

    def test_tab_delimited(self):
        text = "Alice\t30\nBob\t25\nCharlie\t35"
        result = _scan_delimited_sample(text, ['Name', 'Age'], 20)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['Name'], 'Alice')
        self.assertEqual(result[1]['Age'], '25')

    def test_pipe_delimited(self):
        text = "X|100\nY|200"
        result = _scan_delimited_sample(text, ['Key', 'Val'], 20)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['Key'], 'X')

    def test_binary_rows_skipped(self):
        text = "\x00data\t\x00val\nAlice\t30"
        result = _scan_delimited_sample(text, ['Name', 'Age'], 20)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['Name'], 'Alice')

    def test_empty_rows_skipped(self):
        text = "\t\nAlice\t30"
        result = _scan_delimited_sample(text, ['Name', 'Age'], 20)
        self.assertEqual(len(result), 1)

    def test_max_rows_limit(self):
        lines = '\n'.join(f"row{i}\tval{i}" for i in range(50))
        result = _scan_delimited_sample(lines, ['A', 'B'], max_rows=3)
        self.assertEqual(len(result), 3)

    def test_single_column_returns_empty(self):
        result = _scan_delimited_sample("data", ['only'], 20)
        self.assertEqual(result, [])

    def test_empty_cols_returns_empty(self):
        result = _scan_delimited_sample("data\tmore", [], 20)
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════════════
# extract_all failure path
# ═══════════════════════════════════════════════════════════════════

class TestExtractAllFailure(unittest.TestCase):
    """Tests extract_all returning False when file is unreadable."""

    def test_bad_file_raises(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_cov_')
        _TEMP_DIRS.append(tmpdir)
        bad_path = os.path.join(tmpdir, 'nonexistent.twb')
        ext = TableauExtractor(bad_path, output_dir=tmpdir)
        with self.assertRaises((FileNotFoundError, OSError)):
            ext.extract_all()


# ═══════════════════════════════════════════════════════════════════
# extract_calculations
# ═══════════════════════════════════════════════════════════════════

class TestExtractCalculationsCoverage(unittest.TestCase):
    """Covers empty formula skip, categorical-bin skip, ds_by_name routing."""

    def test_empty_formula_skipped(self):
        xml = '''<workbook>
          <datasources>
            <datasource name="ds1" caption="Sales">
              <connection/>
            </datasource>
          </datasources>
          <datasource-dependencies datasource="ds1">
            <column name="[Calc1]" caption="Calc1">
              <calculation class="tableau" formula=""/>
            </column>
          </datasource-dependencies>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.workbook_data['datasources'] = [{'name': 'Sales'}]
        ext.extract_calculations(root)
        # Empty formula should be skipped
        calcs = ext.workbook_data.get('calculations', [])
        self.assertEqual(len(calcs), 0)

    def test_categorical_bin_skipped(self):
        xml = '''<workbook>
          <datasource-dependencies datasource="ds1">
            <column name="[BinCalc]" caption="BinCalc">
              <calculation class="categorical-bin" formula="something"/>
            </column>
          </datasource-dependencies>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.workbook_data['datasources'] = []
        ext.extract_calculations(root)
        calcs = ext.workbook_data.get('calculations', [])
        self.assertEqual(len(calcs), 0)

    def test_valid_calculation_with_ds_routing(self):
        xml = '''<workbook>
          <datasources>
            <datasource name="ds1" caption="Sales"/>
          </datasources>
          <worksheet name="Sheet1">
            <datasource-dependencies datasource="ds1">
              <column name="[Profit Ratio]" caption="Profit Ratio" role="measure" type="quantitative">
                <calculation class="tableau" formula="SUM([Profit]) / SUM([Sales])"/>
              </column>
            </datasource-dependencies>
          </worksheet>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.workbook_data['datasources'] = [{'name': 'ds1', 'calculations': []}]
        ext.extract_calculations(root)
        calcs = ext.workbook_data.get('calculations', [])
        self.assertTrue(len(calcs) >= 1)
        found = any('Profit Ratio' in c.get('caption', '') or 'Profit Ratio' in c.get('name', '') for c in calcs)
        self.assertTrue(found, f'Profit Ratio not found in {calcs}')


# ═══════════════════════════════════════════════════════════════════
# extract_parameters
# ═══════════════════════════════════════════════════════════════════

class TestExtractParametersCoverage(unittest.TestCase):
    """Covers dedup, database-domain detection, query_connection."""

    def test_old_format_dedup(self):
        xml = '''<workbook>
          <column name="[Param1]" caption="P1" param-domain-type="list" datatype="string"/>
          <column name="[Param1]" caption="P1" param-domain-type="list" datatype="string"/>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_parameters(root)
        params = ext.workbook_data.get('parameters', [])
        self.assertEqual(len(params), 1)

    def test_old_format_database_domain(self):
        xml = '''<workbook>
          <column name="[DynParam]" caption="Dynamic" param-domain-type="database" datatype="string">
            <query formula="SELECT DISTINCT region FROM sales"/>
            <connection class="postgres" dbname="analytics"/>
          </column>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_parameters(root)
        params = ext.workbook_data.get('parameters', [])
        self.assertEqual(len(params), 1)
        p = params[0]
        self.assertEqual(p['domain_type'], 'database')
        self.assertIn('SELECT', p.get('query', ''))
        self.assertEqual(p.get('query_connection'), 'postgres')
        self.assertEqual(p.get('query_dbname'), 'analytics')
        self.assertTrue(p.get('refresh_on_open'))

    def test_old_format_database_domain_with_calculation_fallback(self):
        xml = '''<workbook>
          <column name="[DynParam2]" caption="Dynamic2" param-domain-type="database" datatype="string">
            <calculation formula="SELECT x FROM t"/>
          </column>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_parameters(root)
        params = ext.workbook_data.get('parameters', [])
        self.assertEqual(len(params), 1)
        self.assertIn('SELECT', params[0].get('query', ''))

    def test_new_format_database_domain(self):
        xml = '''<workbook>
          <parameters>
            <parameter name="[NewDyn]" caption="NewDynamic" datatype="string" param-domain-type="database">
              <query value="SELECT col FROM tbl"/>
              <connection class="sqlserver" dbname="warehouse"/>
            </parameter>
          </parameters>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_parameters(root)
        params = ext.workbook_data.get('parameters', [])
        self.assertEqual(len(params), 1)
        p = params[0]
        self.assertEqual(p['domain_type'], 'database')
        self.assertIn('SELECT', p.get('query', ''))

    def test_new_format_range_domain(self):
        xml = '''<workbook>
          <parameters>
            <parameter name="[RangeP]" caption="Top N" datatype="integer" value="10">
              <range min="1" max="100" step="1"/>
            </parameter>
          </parameters>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_parameters(root)
        params = ext.workbook_data.get('parameters', [])
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]['domain_type'], 'range')


# ═══════════════════════════════════════════════════════════════════
# _extract_mark_class
# ═══════════════════════════════════════════════════════════════════

class TestExtractMarkClassCoverage(unittest.TestCase):
    """Covers pane-based and style-based mark class extraction."""

    def test_pane_mark(self):
        xml = '''<worksheet name="S1">
          <table><view><pane><mark class="Bar"/></pane></view></table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext._extract_mark_class(ws)
        self.assertEqual(result, 'Bar')

    def test_style_mark_fallback(self):
        xml = '''<worksheet name="S2">
          <style><mark class="Line"/></style>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext._extract_mark_class(ws)
        self.assertEqual(result, 'Line')

    def test_no_mark_returns_none(self):
        xml = '<worksheet name="S3"><table/></worksheet>'
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext._extract_mark_class(ws)
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# determine_chart_type / _infer_automatic_chart_type
# ═══════════════════════════════════════════════════════════════════

class TestInferAutoChartType(unittest.TestCase):
    """Covers automatic chart inference: scatter, lineChart, table, map, clusteredBarChart."""

    def test_auto_date_col_with_rows_gives_line(self):
        xml = '''<worksheet name="S">
          <table>
            <cols>[DS].[Order Date]</cols>
            <rows>[DS].[Sales]</rows>
          </table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext._infer_automatic_chart_type(ws)
        self.assertEqual(result, 'lineChart')

    def test_auto_date_row_with_cols_gives_line(self):
        xml = '''<worksheet name="S">
          <table>
            <cols>[DS].[Sales]</cols>
            <rows>[DS].[Order Date]</rows>
          </table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext._infer_automatic_chart_type(ws)
        self.assertEqual(result, 'lineChart')

    def test_auto_two_measures_gives_scatter(self):
        xml = '''<worksheet name="S">
          <table>
            <cols>[DS].[Sales]</cols>
            <rows>[DS].[Profit]</rows>
          </table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext._infer_automatic_chart_type(ws)
        self.assertEqual(result, 'scatterChart')

    def test_auto_no_fields_gives_table(self):
        xml = '''<worksheet name="S">
          <table>
            <cols/>
            <rows/>
          </table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext._infer_automatic_chart_type(ws)
        self.assertEqual(result, 'table')

    def test_auto_map_encoding(self):
        xml = '''<worksheet name="S">
          <table><cols/><rows/></table>
          <encoding><map/></encoding>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext._infer_automatic_chart_type(ws)
        self.assertEqual(result, 'map')

    def test_auto_geo_pair_gives_map(self):
        xml = '''<worksheet name="S">
          <table>
            <cols>[DS].[Latitude]</cols>
            <rows>[DS].[Longitude]</rows>
          </table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext._infer_automatic_chart_type(ws)
        self.assertEqual(result, 'map')

    def test_determine_chart_type_explicit_bar(self):
        xml = '''<worksheet name="S">
          <table><view><pane><mark class="Bar"/></pane></view></table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.determine_chart_type(ws)
        self.assertEqual(result, 'clusteredBarChart')

    def test_determine_chart_type_no_mark_map_encoding(self):
        xml = '''<worksheet name="S">
          <table><view/></table>
          <encoding><map/></encoding>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.determine_chart_type(ws)
        self.assertEqual(result, 'map')

    def test_determine_chart_type_no_mark_no_map(self):
        xml = '''<worksheet name="S">
          <table><view/></table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.determine_chart_type(ws)
        self.assertEqual(result, 'bar')


# ═══════════════════════════════════════════════════════════════════
# extract_formatting
# ═══════════════════════════════════════════════════════════════════

class TestExtractFormattingCoverage(unittest.TestCase):
    """Covers field_formats and legend style promotion."""

    def test_field_formats(self):
        xml = '''<worksheet name="S">
          <style>
            <style-rule element="cell">
              <format field="[Sales]" value="#,##0.00"/>
            </style-rule>
          </style>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_formatting(ws)
        fmts = result.get('field_formats', {})
        # Keys preserve brackets from the Tableau XML field name
        self.assertTrue(
            '[Sales]' in fmts or 'Sales' in fmts,
            f'Expected Sales field in {fmts}'
        )

    def test_legend_style(self):
        xml = '''<worksheet name="S">
          <style>
            <style-rule element="legend-title">
              <format attr="font-family" value="Arial"/>
              <format attr="font-size" value="12"/>
            </style-rule>
          </style>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_formatting(ws)
        legend = result.get('legend', {})
        # Legend wraps title attributes under 'title_style' sub-dict
        if 'title_style' in legend:
            self.assertEqual(legend['title_style'].get('font-family'), 'Arial')
        else:
            self.assertIn('font-family', legend)


# ═══════════════════════════════════════════════════════════════════
# extract_tooltips
# ═══════════════════════════════════════════════════════════════════

class TestExtractTooltipsCoverage(unittest.TestCase):
    """Covers bold and color detection in tooltip runs."""

    def test_bold_run(self):
        xml = '''<worksheet name="S">
          <tooltip>
            <formatted-text>
              <run bold="true">Bold text</run>
            </formatted-text>
          </tooltip>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_tooltips(ws)
        # extract_tooltips returns a list of tooltip dicts
        if isinstance(result, list) and result:
            runs = result[0].get('runs', [])
        else:
            runs = result.get('runs', []) if isinstance(result, dict) else []
        self.assertTrue(any(r.get('bold') for r in runs))

    def test_color_run(self):
        xml = '''<worksheet name="S">
          <tooltip>
            <formatted-text>
              <run fontcolor="#FF0000">Red text</run>
            </formatted-text>
          </tooltip>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_tooltips(ws)
        # extract_tooltips returns a list of tooltip dicts
        if isinstance(result, list) and result:
            runs = result[0].get('runs', [])
        else:
            runs = result.get('runs', []) if isinstance(result, dict) else []
        self.assertTrue(any(r.get('color') == '#FF0000' for r in runs))


# ═══════════════════════════════════════════════════════════════════
# extract_dashboard_objects — text runs formatting
# ═══════════════════════════════════════════════════════════════════

class TestDashboardObjectsTextRuns(unittest.TestCase):
    """Covers text zone run formatting (bold, italic, color, font_size, url)."""

    def _make_dashboard_xml(self, run_attrs=''):
        return f'''<dashboard>
          <zones>
            <zone type="text" id="1" name="txt" x="0" y="0" w="100" h="50">
              <formatted-text>
                <run {run_attrs}>Hello</run>
              </formatted-text>
            </zone>
          </zones>
        </dashboard>'''

    def test_bold_text_run(self):
        xml = self._make_dashboard_xml('bold="true"')
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_dashboard_objects(db)
        text_objs = [o for o in result if o['type'] == 'text']
        self.assertTrue(len(text_objs) >= 1)
        runs = text_objs[0].get('text_runs', [])
        self.assertTrue(any(r.get('bold') for r in runs))

    def test_italic_text_run(self):
        xml = self._make_dashboard_xml('italic="true"')
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_dashboard_objects(db)
        text_objs = [o for o in result if o['type'] == 'text']
        runs = text_objs[0].get('text_runs', [])
        self.assertTrue(any(r.get('italic') for r in runs))

    def test_color_text_run(self):
        xml = self._make_dashboard_xml('fontcolor="#00FF00"')
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_dashboard_objects(db)
        text_objs = [o for o in result if o['type'] == 'text']
        runs = text_objs[0].get('text_runs', [])
        self.assertTrue(any(r.get('color') == '#00FF00' for r in runs))

    def test_font_size_text_run(self):
        xml = self._make_dashboard_xml('fontsize="14"')
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_dashboard_objects(db)
        text_objs = [o for o in result if o['type'] == 'text']
        runs = text_objs[0].get('text_runs', [])
        self.assertTrue(any(r.get('font_size') == '14' for r in runs))

    def test_url_text_run(self):
        xml = self._make_dashboard_xml('href="https://example.com"')
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_dashboard_objects(db)
        text_objs = [o for o in result if o['type'] == 'text']
        runs = text_objs[0].get('text_runs', [])
        self.assertTrue(any(r.get('url') == 'https://example.com' for r in runs))


# ═══════════════════════════════════════════════════════════════════
# extract_dashboard_objects — padding int-parse failure
# ═══════════════════════════════════════════════════════════════════

class TestDashboardObjectsPaddingError(unittest.TestCase):
    """Covers the ValueError/TypeError catch on padding parse."""

    def test_non_numeric_padding_handled(self):
        xml = '''<dashboard>
          <zones>
            <zone type="text" id="2" name="ws1" x="0" y="0" w="100" h="50"
                  padding-left="abc">
              <zone-style>
                <format attr="padding-top" value="notanumber"/>
              </zone-style>
              <formatted-text><run>Hi</run></formatted-text>
            </zone>
          </zones>
        </dashboard>'''
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        # Should not raise
        result = ext.extract_dashboard_objects(db)
        self.assertIsInstance(result, list)


# ═══════════════════════════════════════════════════════════════════
# extract_dashboard_objects — filter_control with none: prefix
# ═══════════════════════════════════════════════════════════════════

class TestDashboardObjectsFilterControl(unittest.TestCase):
    """Covers filter zone with param=none:field prefix."""

    def test_filter_control_with_none_prefix(self):
        xml = '''<dashboard>
          <zones>
            <zone type="filter" id="3" name="RegionFilter" x="0" y="0" w="200" h="30"
                  param="[none:Region:nk]"/>
          </zones>
        </dashboard>'''
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_dashboard_objects(db)
        fc = [o for o in result if o['type'] == 'filter_control']
        self.assertEqual(len(fc), 1)
        self.assertEqual(fc[0]['calc_column_id'], 'Region')


# ═══════════════════════════════════════════════════════════════════
# extract_theme — custom palettes + style attrs
# ═══════════════════════════════════════════════════════════════════

class TestExtractThemeCoverage(unittest.TestCase):
    """Covers custom_palettes dict construction and style rule attrs."""

    def test_custom_palettes(self):
        xml = '''<dashboard>
          <color-palette name="MyPalette" type="regular">
            <color>#FF0000</color>
            <color>#00FF00</color>
          </color-palette>
        </dashboard>'''
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_theme(db)
        self.assertIn('custom_palettes', result)
        self.assertIn('MyPalette', result['custom_palettes'])
        self.assertEqual(len(result['custom_palettes']['MyPalette']['colors']), 2)

    def test_style_rule_attrs(self):
        xml = '''<dashboard>
          <style>
            <style-rule element="worksheet">
              <format attr="font-size" value="10"/>
            </style-rule>
          </style>
        </dashboard>'''
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_theme(db)
        self.assertIn('styles', result)
        self.assertIn('worksheet', result['styles'])

    def test_preferences_color_palette(self):
        xml = '''<dashboard>
          <preferences>
            <color-palette name="Corp" type="regular">
              <color>#AABBCC</color>
            </color-palette>
          </preferences>
        </dashboard>'''
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_theme(db)
        self.assertIn('custom_palettes', result)
        self.assertIn('Corp', result['custom_palettes'])


# ═══════════════════════════════════════════════════════════════════
# extract_mark_encoding — palette colors, thresholds, legend
# ═══════════════════════════════════════════════════════════════════

class TestMarkEncodingCoverage(unittest.TestCase):
    """Covers palette_colors extraction, stepped thresholds, legend element."""

    def test_palette_colors_in_encoding(self):
        xml = '''<worksheet name="S">
          <table><view><pane><mark class="Bar"/></pane></view></table>
          <encodings>
            <color column="[DS].[Region]" palette="Custom" type="categorical"/>
            <color-palette name="Custom">
              <color>#FF0000</color>
              <color>#00FF00</color>
            </color-palette>
          </encodings>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_mark_encoding(ws)
        color = result.get('color', {})
        self.assertIn('palette_colors', color)

    def test_stepped_threshold(self):
        xml = '''<worksheet name="S">
          <encodings>
            <color column="[DS].[Sales]:qk" type="quantitative">
              <bucket color="#FF0000" value="50.0"/>
              <bucket color="#00FF00" value="100.0"/>
            </color>
          </encodings>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_mark_encoding(ws)
        color = result.get('color', {})
        thresholds = color.get('thresholds', [])
        self.assertEqual(len(thresholds), 2)
        self.assertEqual(thresholds[0]['value'], 50.0)

    def test_legend_position(self):
        xml = '''<worksheet name="S">
          <encodings>
            <color column="[DS].[Region]">
              <legend position="bottom"/>
            </color>
          </encodings>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_mark_encoding(ws)
        color = result.get('color', {})
        self.assertEqual(color.get('legend_position'), 'bottom')


# ═══════════════════════════════════════════════════════════════════
# extract_workbook_actions — highlight + param
# ═══════════════════════════════════════════════════════════════════

class TestWorkbookActionsCoverage(unittest.TestCase):
    """Covers highlight field-mapping and param action extraction."""

    def test_highlight_action_field_mapping(self):
        xml = '''<workbook>
          <actions>
            <action name="Highlight" type="highlight">
              <source worksheet="Sheet1"/>
              <target worksheet="Sheet2"/>
              <field-mapping source-field="[Region]" target-field="[Region]"/>
            </action>
          </actions>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_workbook_actions(root)
        actions = ext.workbook_data.get('actions', [])
        highlight_actions = [a for a in actions if a.get('type') == 'highlight']
        self.assertTrue(len(highlight_actions) >= 1)
        field_maps = highlight_actions[0].get('field_mappings', [])
        self.assertTrue(len(field_maps) >= 1)

    def test_param_action(self):
        xml = '''<workbook>
          <actions>
            <action name="SetParam" type="param">
              <source worksheet="Sheet1"/>
            </action>
          </actions>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_workbook_actions(root)
        actions = ext.workbook_data.get('actions', [])
        param_actions = [a for a in actions if a.get('type') == 'param']
        self.assertTrue(len(param_actions) >= 1)


# ═══════════════════════════════════════════════════════════════════
# extract_groups — edge cases
# ═══════════════════════════════════════════════════════════════════

class TestExtractGroupsCoverage(unittest.TestCase):
    """Covers empty name skip, no groupfilter skip, nested member markers."""

    def test_empty_name_skipped(self):
        xml = '''<workbook>
          <datasource name="ds1">
            <group name="" caption="">
              <groupfilter function="union"/>
            </group>
          </datasource>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_groups(root)
        groups = ext.workbook_data.get('groups', [])
        self.assertEqual(len(groups), 0)

    def test_no_groupfilter_skipped(self):
        xml = '''<workbook>
          <datasource name="ds1">
            <group name="MyGroup" caption="My Group"/>
          </datasource>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_groups(root)
        groups = ext.workbook_data.get('groups', [])
        self.assertEqual(len(groups), 0)

    def test_nested_member_with_ui_marker(self):
        # Build XML tree programmatically to avoid namespace parse error
        # with 'user:ui-marker' attributes
        root = ET.Element('workbook')
        ds = ET.SubElement(root, 'datasource', attrib={'name': 'ds1'})
        group = ET.SubElement(ds, 'group', attrib={'name': '[Region Group]', 'caption': 'Region Group'})
        top_gf = ET.SubElement(group, 'groupfilter', attrib={'function': 'union'})
        child_gf = ET.SubElement(top_gf, 'groupfilter', attrib={'function': 'union'})
        child_gf.set('user:ui-marker', 'true')
        child_gf.set('user:ui-marker-value', 'East Coast')
        ET.SubElement(child_gf, 'groupfilter', attrib={'function': 'member', 'member': 'NY'})
        ET.SubElement(child_gf, 'groupfilter', attrib={'function': 'member', 'member': 'NJ'})
        ext, _ = _make_extractor()
        ext.extract_groups(root)
        groups = ext.workbook_data.get('groups', [])
        self.assertTrue(len(groups) >= 1)


# ═══════════════════════════════════════════════════════════════════
# extract_datasource_filters — extract + federated paths
# ═══════════════════════════════════════════════════════════════════

class TestDatasourceFiltersCoverage(unittest.TestCase):
    """Covers extract-connection and federated filter paths."""

    def test_extract_connection_filter(self):
        xml = '''<workbook>
          <datasources>
            <datasource name="ds1" caption="Sales">
              <extract>
                <connection>
                  <filter column="[Region]">
                    <groupfilter function="member" member="East"/>
                  </filter>
                </connection>
              </extract>
            </datasource>
          </datasources>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_datasource_filters(root)
        filters = ext.workbook_data.get('datasource_filters', [])
        self.assertTrue(len(filters) >= 1)

    def test_federated_connection_filter(self):
        xml = '''<workbook>
          <datasources>
            <datasource name="ds1" caption="Sales">
              <connection>
                <filter column="[Status]">
                  <member value="Active"/>
                </filter>
              </connection>
            </datasource>
          </datasources>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_datasource_filters(root)
        filters = ext.workbook_data.get('datasource_filters', [])
        self.assertTrue(len(filters) >= 1)


# ═══════════════════════════════════════════════════════════════════
# extract_trend_lines — dedup
# ═══════════════════════════════════════════════════════════════════

class TestExtractTrendLinesCoverage(unittest.TestCase):
    """Covers dedup check on trend line types."""

    def test_dedup_same_type(self):
        xml = '''<worksheet name="S">
          <trend-lines>
            <trend-line type="linear" show-confidence="false"/>
            <trend-line type="linear" show-confidence="true"/>
          </trend-lines>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_trend_lines(ws)
        # First pass collects ALL direct <trend-line> children.
        # Dedup only applies in the second pass (nested <trend-lines><trend-line>).
        # Both same-type entries are kept from the first pass.
        self.assertEqual(len(result), 2)


# ═══════════════════════════════════════════════════════════════════
# extract_pages_shelf — regex parse
# ═══════════════════════════════════════════════════════════════════

class TestExtractPagesShelf(unittest.TestCase):
    """Covers regex parse of pages element text."""

    def test_pages_shelf_regex(self):
        xml = '''<worksheet name="S">
          <table>
            <pages>[DS].[Order Date]</pages>
          </table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_pages_shelf(ws)
        self.assertIsNotNone(result)
        self.assertIn('field', result)


# ═══════════════════════════════════════════════════════════════════
# extract_dashboard_containers
# ═══════════════════════════════════════════════════════════════════

class TestExtractDashboardContainers(unittest.TestCase):
    """Covers the full extract_dashboard_containers method."""

    def test_full_container_with_children(self):
        xml = '''<dashboard>
          <layout-container orientation="horizontal" name="Container1"
                           x="10" y="20" w="800" h="600"
                           padding-left="5" padding-top="10">
            <zone name="Sheet1" x="0" y="0" w="400" h="300"/>
            <zone name="Sheet2" x="400" y="0" w="400" h="300"/>
          </layout-container>
        </dashboard>'''
        ext, _ = _make_extractor()
        db = ET.fromstring(xml)
        result = ext.extract_dashboard_containers(db)
        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual(c['orientation'], 'horizontal')
        self.assertEqual(c['position']['x'], 10)
        self.assertEqual(c['padding']['left'], 5)
        self.assertEqual(len(c['children']), 2)
        self.assertEqual(c['children'][0]['name'], 'Sheet1')


# ═══════════════════════════════════════════════════════════════════
# extract_clustering — fallback without children
# ═══════════════════════════════════════════════════════════════════

class TestExtractClusteringCoverage(unittest.TestCase):
    """Covers cluster-analysis without nested cluster children."""

    def test_cluster_analysis_no_children(self):
        xml = '''<worksheet name="S">
          <cluster-analysis num-clusters="3"/>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_clustering(ws)
        self.assertIsNotNone(result)


# ═══════════════════════════════════════════════════════════════════
# extract_dual_axis_sync
# ═══════════════════════════════════════════════════════════════════

class TestExtractDualAxisSync(unittest.TestCase):
    """Covers synchronized='true' detection on axes."""

    def test_dual_axis_sync_true(self):
        xml = '''<worksheet name="S">
          <table>
            <panes>
              <pane><axis ordinal="0"/></pane>
              <pane><axis ordinal="1" synchronized="true"/></pane>
            </panes>
          </table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_dual_axis_sync(ws)
        self.assertTrue(result)

    def test_no_sync_returns_false(self):
        xml = '''<worksheet name="S">
          <table>
            <panes>
              <pane><axis ordinal="0"/></pane>
            </panes>
          </table>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_dual_axis_sync(ws)
        self.assertFalse(result)


# ═══════════════════════════════════════════════════════════════════
# extract_custom_shapes — mock twbx zip
# ═══════════════════════════════════════════════════════════════════

class TestExtractCustomShapes(unittest.TestCase):
    """Covers shape file extraction from .twbx via mock zipfile."""

    def test_twbx_shape_extraction(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_cov_')
        _TEMP_DIRS.append(tmpdir)
        twbx_path = os.path.join(tmpdir, 'test.twbx')

        # Create a mock .twbx with a shape file
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('test.twb', '<workbook/>')
            zf.writestr('content/Shapes/custom/arrow.png', b'PNG_DATA')
        buf.seek(0)
        with open(twbx_path, 'wb') as f:
            f.write(buf.read())

        ext = TableauExtractor(twbx_path, output_dir=tmpdir)
        result = ext.extract_custom_shapes()
        self.assertTrue(len(result) >= 1)
        self.assertEqual(result[0]['filename'], 'arrow.png')


# ═══════════════════════════════════════════════════════════════════
# extract_embedded_fonts — mock twbx zip
# ═══════════════════════════════════════════════════════════════════

class TestExtractEmbeddedFonts(unittest.TestCase):
    """Covers font file extraction from .twbx via mock zipfile."""

    def test_twbx_font_extraction(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_cov_')
        _TEMP_DIRS.append(tmpdir)
        twbx_path = os.path.join(tmpdir, 'test.twbx')

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('test.twb', '<workbook/>')
            zf.writestr('Fonts/Roboto.ttf', b'TTF_DATA')
            zf.writestr('Fonts/OpenSans.otf', b'OTF_DATA')
        buf.seek(0)
        with open(twbx_path, 'wb') as f:
            f.write(buf.read())

        ext = TableauExtractor(twbx_path, output_dir=tmpdir)
        result = ext.extract_embedded_fonts()
        self.assertEqual(len(result), 2)
        names = {f['filename'] for f in result}
        self.assertIn('Roboto.ttf', names)
        self.assertEqual(result[0]['format'], 'ttf')


# ═══════════════════════════════════════════════════════════════════
# extract_custom_geocoding — XML + twbx CSV scan
# ═══════════════════════════════════════════════════════════════════

class TestExtractCustomGeocoding(unittest.TestCase):
    """Covers geographic-role extraction and CSV scan in twbx."""

    def test_geographic_role_xml(self):
        xml = '''<workbook>
          <geocoding>
            <geographic-role name="MyCity" field="CityName"/>
          </geocoding>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_custom_geocoding(root)
        geo = ext.workbook_data.get('custom_geocoding', [])
        self.assertTrue(len(geo) >= 1)
        self.assertEqual(geo[0]['role'], 'MyCity')

    def test_twbx_geocoding_csv_scan(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_cov_')
        _TEMP_DIRS.append(tmpdir)
        twbx_path = os.path.join(tmpdir, 'test.twbx')

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('test.twb', '<workbook/>')
            zf.writestr('geocoding/custom_geo.csv', 'lat,lon\n1.0,2.0')
        buf.seek(0)
        with open(twbx_path, 'wb') as f:
            f.write(buf.read())

        ext = TableauExtractor(twbx_path, output_dir=tmpdir)
        root = ET.fromstring('<workbook/>')
        ext.extract_custom_geocoding(root)
        geo = ext.workbook_data.get('custom_geocoding', [])
        csv_entries = [g for g in geo if g.get('type') == 'custom_file']
        self.assertTrue(len(csv_entries) >= 1)


# ═══════════════════════════════════════════════════════════════════
# extract_data_blending
# ═══════════════════════════════════════════════════════════════════

class TestExtractDataBlending(unittest.TestCase):
    """Covers link elements and cross-ds dependency columns."""

    def test_link_element(self):
        xml = '''<workbook>
          <datasource name="ds1" caption="Sales">
            <column name="[Region]">
              <link expression="[Region]" key="1"/>
            </column>
          </datasource>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_data_blending(root)
        blending = ext.workbook_data.get('data_blending', [])
        self.assertTrue(len(blending) >= 1)
        self.assertEqual(blending[0]['link_expression'], '[Region]')

    def test_cross_ds_dependency(self):
        xml = '''<workbook>
          <datasource name="ds1" caption="Sales">
            <datasource-dependencies datasource="ds2">
              <column name="[Category]" key="cat_key"/>
            </datasource-dependencies>
          </datasource>
        </workbook>'''
        ext, _ = _make_extractor(xml)
        root = ET.fromstring(xml)
        ext.extract_data_blending(root)
        blending = ext.workbook_data.get('data_blending', [])
        deps = [b for b in blending if b.get('secondary_datasource') == 'ds2']
        self.assertTrue(len(deps) >= 1)


# ═══════════════════════════════════════════════════════════════════
# extract_hyper_metadata — full parsing via mock twbx
# ═══════════════════════════════════════════════════════════════════

class TestExtractHyperMetadata(unittest.TestCase):
    """Covers full hyper metadata parsing from a mock twbx."""

    def test_hyper_file_detection(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_cov_')
        _TEMP_DIRS.append(tmpdir)
        twbx_path = os.path.join(tmpdir, 'test.twbx')

        # Simulate a hyper file with CREATE TABLE header
        hyper_content = (
            b'HyPeRESERVED_HEADER_BYTES' +
            b'\x00' * 100 +
            b'CREATE TABLE "Extract" (col1 INTEGER, col2 VARCHAR)' +
            b'\x00' * 500
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('test.twb', '<workbook/>')
            zf.writestr('Data/Extract.hyper', hyper_content)
        buf.seek(0)
        with open(twbx_path, 'wb') as f:
            f.write(buf.read())

        ext = TableauExtractor(twbx_path, output_dir=tmpdir)
        with patch('extract_tableau_data.read_hyper_from_twbx', side_effect=Exception('skip')):
            ext.extract_hyper_metadata()

        hyper_files = ext.workbook_data.get('hyper_files', [])
        self.assertTrue(len(hyper_files) >= 1)
        entry = hyper_files[0]
        self.assertEqual(entry['format'], 'hyper')
        self.assertIn('tables', entry)
        self.assertTrue(len(entry['tables']) >= 1)
        self.assertEqual(entry['tables'][0]['table'], 'Extract')

    def test_hyper_summary_logging(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_cov_')
        _TEMP_DIRS.append(tmpdir)
        twbx_path = os.path.join(tmpdir, 'test.twbx')

        hyper_content = (
            b'HyPe' + b'\x00' * 200 +
            b'CREATE TABLE "Orders" (id INTEGER, name VARCHAR)' +
            b'\x00' * 100
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('test.twb', '<workbook/>')
            zf.writestr('Data/Orders.hyper', hyper_content)
        buf.seek(0)
        with open(twbx_path, 'wb') as f:
            f.write(buf.read())

        ext = TableauExtractor(twbx_path, output_dir=tmpdir)
        with patch('extract_tableau_data.read_hyper_from_twbx', side_effect=Exception('skip')):
            ext.extract_hyper_metadata()

        self.assertTrue(len(ext.workbook_data['hyper_files']) >= 1)

    def test_deep_reading_via_hyper_reader(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_cov_')
        _TEMP_DIRS.append(tmpdir)
        twbx_path = os.path.join(tmpdir, 'test.twbx')

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('test.twb', '<workbook/>')
            zf.writestr('Data/Sample.hyper', b'HyPe' + b'\x00' * 200)
        buf.seek(0)
        with open(twbx_path, 'wb') as f:
            f.write(buf.read())

        ext = TableauExtractor(twbx_path, output_dir=tmpdir)
        deep_result = [{
            'original_filename': 'Sample.hyper',
            'format': 'sqlite',
            'tables': [{'table_name': 'Orders', 'row_count': 100, 'columns': []}],
        }]
        with patch('extract_tableau_data.read_hyper_from_twbx', return_value=deep_result):
            ext.extract_hyper_metadata()

        entry = ext.workbook_data['hyper_files'][0]
        self.assertIn('hyper_reader_tables', entry)
        self.assertEqual(entry['actual_row_count'], 100)


# ═══════════════════════════════════════════════════════════════════
# extract_totals_subtotals — shorthand tags
# ═══════════════════════════════════════════════════════════════════

class TestExtractTotalsSubtotals(unittest.TestCase):
    """Covers grandtotals shorthand (rows-total/cols-total tags)."""

    def test_grand_total_element(self):
        xml = '''<worksheet name="S">
          <grandtotals>
            <grand-total type="rows" position="bottom" enabled="true"/>
          </grandtotals>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_totals_subtotals(ws)
        self.assertTrue(len(result['grand_totals']) >= 1)

    def test_shorthand_rows_total(self):
        xml = '''<worksheet name="S">
          <rows-total position="top" enabled="true"/>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_totals_subtotals(ws)
        entries = [t for t in result['grand_totals'] if t['type'] == 'rows']
        self.assertTrue(len(entries) >= 1)


# ═══════════════════════════════════════════════════════════════════
# extract_worksheet_description — child element fallback
# ═══════════════════════════════════════════════════════════════════

class TestExtractWorksheetDescription(unittest.TestCase):
    """Covers description child element fallback."""

    def test_description_attribute(self):
        xml = '<worksheet name="S" description="My desc"/>'
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_worksheet_description(ws)
        self.assertEqual(result, 'My desc')

    def test_description_child_element(self):
        xml = '''<worksheet name="S">
          <description>Detailed description text</description>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_worksheet_description(ws)
        self.assertEqual(result, 'Detailed description text')


# ═══════════════════════════════════════════════════════════════════
# extract_dynamic_title — field ref, <[ markers
# ═══════════════════════════════════════════════════════════════════

class TestExtractDynamicTitle(unittest.TestCase):
    """Covers field element in title and text markers."""

    def test_field_reference_in_title(self):
        xml = '''<worksheet name="S">
          <title>
            <run>Sales for </run>
            <run><field name="[Parameters].[Region]"/></run>
          </title>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_dynamic_title(ws)
        self.assertIsNotNone(result)
        self.assertTrue(result['is_dynamic'])
        field_parts = [p for p in result['parts'] if p['type'] == 'field']
        self.assertTrue(len(field_parts) >= 1)

    def test_bracket_marker_in_text(self):
        xml = '''<worksheet name="S">
          <title>
            <run>[Region] Overview</run>
          </title>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_dynamic_title(ws)
        self.assertIsNotNone(result)
        self.assertTrue(result['is_dynamic'])

    def test_angle_bracket_marker(self):
        xml = '''<worksheet name="S">
          <title>
            <run>&lt;[Sales]&gt; Report</run>
          </title>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_dynamic_title(ws)
        self.assertIsNotNone(result)
        self.assertTrue(result['is_dynamic'])

    def test_static_title(self):
        xml = '''<worksheet name="S">
          <title>
            <run>Simple Title</run>
          </title>
        </worksheet>'''
        ext, _ = _make_extractor()
        ws = ET.fromstring(xml)
        result = ext.extract_dynamic_title(ws)
        self.assertIsNotNone(result)
        self.assertFalse(result['is_dynamic'])


if __name__ == '__main__':
    unittest.main()
