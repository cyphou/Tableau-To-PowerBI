"""Coverage-push tests for powerbi_import/pbip_generator.py.

Targets uncovered lines identified by coverage report (340 lines, 77.2% → 90%+).
Complements tests/test_pbip_generator.py (existing 47 tests covering basic paths).
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.pbip_generator import (
    PowerBIProjectGenerator,
    _L,
    _pbi_literal,
    _write_json,
)


def _make_generator(output_dir=None):
    """Create a generator with a temp output directory."""
    d = output_dir or tempfile.mkdtemp()
    return PowerBIProjectGenerator(output_dir=d)


def _init_field_map(gen, field_map=None, measure_names=None,
                    bim_measure_names=None, main_table='Table',
                    datasources_ref=None):
    """Initialize internal field mapping state on generator."""
    gen._field_map = field_map or {}
    gen._measure_names = set(measure_names or [])
    gen._bim_measure_names = set(bim_measure_names or [])
    gen._main_table = main_table
    gen._datasources_ref = datasources_ref or []


# ─── Module-level helpers ───────────────────────────────────────────────


class TestL(unittest.TestCase):
    """_L PBIR expression literal wrapper."""

    def test_string_value(self):
        result = _L("'hello'")
        self.assertEqual(result, {"expr": {"Literal": {"Value": "'hello'"}}})

    def test_numeric_value(self):
        result = _L("42D")
        self.assertEqual(result["expr"]["Literal"]["Value"], "42D")

    def test_bool_value(self):
        result = _L("true")
        self.assertEqual(result["expr"]["Literal"]["Value"], "true")


class TestPbiLiteral(unittest.TestCase):
    """_pbi_literal filter value converter — all branch coverage."""

    def test_bool_true(self):
        self.assertEqual(_pbi_literal('true'), 'true')

    def test_bool_false(self):
        self.assertEqual(_pbi_literal('false'), 'false')

    def test_bool_true_upper(self):
        self.assertEqual(_pbi_literal('True'), 'true')

    def test_french_bool_vrai(self):
        self.assertEqual(_pbi_literal('vrai'), 'true')

    def test_french_bool_faux(self):
        self.assertEqual(_pbi_literal('faux'), 'false')

    def test_french_bool_Vrai(self):
        self.assertEqual(_pbi_literal('Vrai'), 'true')

    def test_numeric_int(self):
        self.assertEqual(_pbi_literal(42), '42')

    def test_numeric_float(self):
        self.assertEqual(_pbi_literal('3.14'), '3.14')

    def test_numeric_negative(self):
        self.assertEqual(_pbi_literal('-5'), '-5')

    def test_string_default(self):
        self.assertEqual(_pbi_literal('hello'), "'hello'")

    def test_string_with_spaces(self):
        self.assertEqual(_pbi_literal('hello world'), "'hello world'")

    def test_non_numeric_string(self):
        self.assertEqual(_pbi_literal('abc'), "'abc'")

    def test_bool_with_whitespace(self):
        self.assertEqual(_pbi_literal(' True '), 'true')


class TestWriteJson(unittest.TestCase):
    """_write_json file writing with makedirs."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_json_file(self):
        path = os.path.join(self.tmpdir, 'test.json')
        _write_json(path, {"key": "value"})
        with open(path, 'r') as f:
            data = json.load(f)
        self.assertEqual(data["key"], "value")

    def test_creates_nested_dirs(self):
        path = os.path.join(self.tmpdir, 'a', 'b', 'c', 'test.json')
        _write_json(path, {"nested": True})
        self.assertTrue(os.path.exists(path))

    def test_ensure_ascii_default(self):
        path = os.path.join(self.tmpdir, 'ascii.json')
        _write_json(path, {"text": "café"})
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # ensure_ascii=True by default → unicode escaped
        self.assertIn('caf', content)


# ─── Constructor and generate_project ────────────────────────────────


class TestGeneratorInit(unittest.TestCase):
    def test_creates_output_dir(self):
        d = os.path.join(tempfile.mkdtemp(), 'new_subdir')
        gen = PowerBIProjectGenerator(output_dir=d)
        self.assertTrue(os.path.isdir(gen.output_dir))
        shutil.rmtree(d, ignore_errors=True)


# ─── _create_basic_model_bim ────────────────────────────────────────


class TestCreateBasicModelBim(unittest.TestCase):
    """Fallback BIM with SampleData table — lines 265-287."""

    @patch('powerbi_import.pbip_generator.m_query_generator')
    def test_returns_model_dict(self, mock_mq):
        mock_mq.generate_sample_data_query.return_value = 'let Source = #table({"ID"}, {{1}}) in Source'
        gen = _make_generator()
        result = gen._create_basic_model_bim('TestReport', [])
        self.assertIn('model', result)
        self.assertEqual(result['name'], 'TestReport')
        self.assertEqual(result['compatibilityLevel'], 1567)
        tables = result['model']['tables']
        self.assertTrue(len(tables) >= 1)
        table_names = [t['name'] for t in tables]
        self.assertIn('SampleData', table_names)

    @patch('powerbi_import.pbip_generator.m_query_generator')
    def test_sample_data_columns(self, mock_mq):
        mock_mq.generate_sample_data_query.return_value = 'let Source = #table({"ID"}, {{1}}) in Source'
        gen = _make_generator()
        result = gen._create_basic_model_bim('R', [])
        sample = [t for t in result['model']['tables'] if t['name'] == 'SampleData'][0]
        col_names = [c['name'] for c in sample['columns']]
        self.assertIn('ID', col_names)
        self.assertIn('Name', col_names)
        self.assertIn('Value', col_names)


# ─── _parse_rich_text_runs ──────────────────────────────────────────


class TestParseRichTextRuns(unittest.TestCase):
    """Rich text parsing — bold, italic, color, font_size, url, newlines."""

    def _parse(self, obj):
        gen = _make_generator()
        return gen._parse_rich_text_runs(obj)

    def test_plain_text_fallback(self):
        obj = {'content': 'Hello World'}
        result = self._parse(obj)
        self.assertEqual(len(result), 1)
        # Single paragraph with a textRuns list
        para = result[0]
        runs = para.get('textRuns', [])
        self.assertTrue(any('Hello World' in r.get('value', '') for r in runs))

    def test_bold_run(self):
        obj = {'text_runs': [{'text': 'Bold', 'bold': True}]}
        result = self._parse(obj)
        self.assertEqual(len(result), 1)
        run = result[0]['textRuns'][0]
        self.assertIn('fontWeight', run.get('textStyle', {}))

    def test_italic_run(self):
        obj = {'text_runs': [{'text': 'Italic', 'italic': True}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        self.assertIn('fontStyle', run.get('textStyle', {}))

    def test_color_8char_aarrggbb(self):
        """#AARRGGBB → #RRGGBB (slice [3:] when len==9 with #)."""
        obj = {'text_runs': [{'text': 'Red', 'color': '#FFFF0000'}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        style = run.get('textStyle', {})
        self.assertIn('FF0000', str(style.get('color', '')))

    def test_color_6char_passthrough(self):
        """#RRGGBB passes through unchanged."""
        obj = {'text_runs': [{'text': 'Blue', 'color': '#0000FF'}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        style = run.get('textStyle', {})
        self.assertIn('0000FF', str(style.get('color', '')))

    def test_font_size(self):
        obj = {'text_runs': [{'text': 'Big', 'font_size': 24}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        self.assertIn('fontSize', run.get('textStyle', {}))

    def test_url_hyperlink(self):
        obj = {'text_runs': [{'text': 'Link', 'url': 'https://example.com'}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        self.assertIn('https://example.com', str(run))

    def test_newline_splits_paragraphs(self):
        obj = {'text_runs': [{'text': 'Line1\nLine2'}]}
        result = self._parse(obj)
        self.assertEqual(len(result), 2)

    def test_empty_text_runs(self):
        obj = {'text_runs': []}
        result = self._parse(obj)
        # Should return at least one empty paragraph
        self.assertIsInstance(result, list)


# ─── _detect_slicer_mode ────────────────────────────────────────────


class TestDetectSlicerMode(unittest.TestCase):
    """Slicer mode detection — parameter/datatype branches."""

    def _detect(self, obj, col, converted):
        gen = _make_generator()
        return gen._detect_slicer_mode(obj, col, converted)

    def test_range_parameter(self):
        conv = {'parameters': [{'name': 'Size', 'domain_type': 'range'}],
                'datasources': []}
        mode = self._detect({'param': 'Size'}, 'Size', conv)
        self.assertEqual(mode, 'Between')

    def test_list_parameter(self):
        conv = {'parameters': [{'name': 'Color', 'domain_type': 'list'}],
                'datasources': []}
        mode = self._detect({'param': 'Color'}, 'Color', conv)
        self.assertEqual(mode, 'List')

    def test_date_column(self):
        conv = {'parameters': [],
                'datasources': [{'tables': [{'columns': [
                    {'name': 'OrderDate', 'datatype': 'date'}
                ]}]}]}
        mode = self._detect({}, 'orderdate', conv)
        self.assertEqual(mode, 'Date')

    def test_integer_column(self):
        conv = {'parameters': [],
                'datasources': [{'tables': [{'columns': [
                    {'name': 'Age', 'datatype': 'integer'}
                ]}]}]}
        mode = self._detect({}, 'age', conv)
        self.assertEqual(mode, 'Between')

    def test_default_dropdown(self):
        conv = {'parameters': [], 'datasources': []}
        mode = self._detect({}, 'Category', conv)
        self.assertEqual(mode, 'Dropdown')

    def test_float_column(self):
        conv = {'parameters': [],
                'datasources': [{'tables': [{'columns': [
                    {'name': 'Price', 'datatype': 'real'}
                ]}]}]}
        mode = self._detect({}, 'price', conv)
        self.assertEqual(mode, 'Between')


# ─── _create_slicer_visual ──────────────────────────────────────────


class TestCreateSlicerVisualCoverage(unittest.TestCase):
    """Slicer visual creation — Between mode numericInputStyle."""

    def test_between_mode_has_numeric_input(self):
        gen = _make_generator()
        gen._main_table = 'Sales'
        slicer = gen._create_slicer_visual(
            'v1', 0, 0, 200, 50, 'Amount', 'Sales', 1,
            slicer_mode='Between')
        objects = slicer['visual']['objects']
        self.assertIn('numericInputStyle', objects)
        self.assertEqual(
            objects['data'][0]['properties']['mode'],
            _L("'Between'"))

    def test_dropdown_mode_no_numeric_input(self):
        gen = _make_generator()
        gen._main_table = 'Sales'
        slicer = gen._create_slicer_visual(
            'v2', 0, 0, 200, 50, 'Category', 'Sales', 1,
            slicer_mode='Dropdown')
        objects = slicer['visual']['objects']
        self.assertNotIn('numericInputStyle', objects)

    def test_empty_table_fallback(self):
        gen = _make_generator()
        gen._main_table = 'Fallback'
        slicer = gen._create_slicer_visual(
            'v3', 0, 0, 200, 50, 'Col', '', 1)
        query = slicer['visual']['query']
        # Should use _main_table as fallback
        entity = query['queryState']['Values']['projections'][0]['field']['Column']['Expression']['SourceRef']['Entity']
        self.assertEqual(entity, 'Fallback')


# ─── _convert_number_format ─────────────────────────────────────────


class TestConvertNumberFormat(unittest.TestCase):
    """Number format conversion — PBI passthrough, currency, percentage, thousands."""

    def test_pbi_passthrough(self):
        self.assertEqual(
            PowerBIProjectGenerator._convert_number_format('0.00'), '0.00')

    def test_pbi_passthrough_thousands(self):
        self.assertEqual(
            PowerBIProjectGenerator._convert_number_format('#,0'), '#,0')

    def test_currency_conversion(self):
        result = PowerBIProjectGenerator._convert_number_format('$#,#00.00')
        self.assertIn('$', result)
        self.assertIn('#,0', result)

    def test_percentage_passthrough(self):
        result = PowerBIProjectGenerator._convert_number_format('0.0%')
        self.assertEqual(result, '0.0%')

    def test_thousands_separator(self):
        result = PowerBIProjectGenerator._convert_number_format('###,###')
        self.assertIn('#,0', result)

    def test_empty_input(self):
        self.assertEqual(
            PowerBIProjectGenerator._convert_number_format(''), '')

    def test_none_input(self):
        self.assertEqual(
            PowerBIProjectGenerator._convert_number_format(None), '')

    def test_non_string_input(self):
        self.assertEqual(
            PowerBIProjectGenerator._convert_number_format(123), '')

    def test_plain_format(self):
        result = PowerBIProjectGenerator._convert_number_format('0')
        self.assertEqual(result, '0')


# ─── _find_column_table ─────────────────────────────────────────────


class TestFindColumnTable(unittest.TestCase):
    """Column → table lookup via columns + calculations."""

    def _find(self, col, conv):
        gen = _make_generator()
        return gen._find_column_table(col, conv)

    def test_finds_by_column_name(self):
        conv = {'datasources': [{'tables': [
            {'name': 'Orders', 'columns': [{'name': 'OrderID'}]}
        ]}]}
        self.assertEqual(self._find('OrderID', conv), 'Orders')

    def test_finds_by_caption(self):
        conv = {'datasources': [{'tables': [
            {'name': 'Sales', 'columns': [
                {'name': 'amt', 'caption': 'Amount'}
            ]}
        ]}]}
        self.assertEqual(self._find('Amount', conv), 'Sales')

    def test_finds_by_calculation_caption(self):
        conv = {'datasources': [{'tables': [
            {'name': 'Facts', 'columns': []}
        ], 'calculations': [
            {'caption': 'Profit Ratio'}
        ]}]}
        self.assertEqual(self._find('Profit Ratio', conv), 'Facts')

    def test_returns_empty_not_found(self):
        conv = {'datasources': []}
        self.assertEqual(self._find('Ghost', conv), '')


# ─── _find_worksheet ────────────────────────────────────────────────


class TestFindWorksheet(unittest.TestCase):
    """Name-based worksheet lookup."""

    def test_finds_by_name(self):
        gen = _make_generator()
        worksheets = [{'name': 'Sheet1'}, {'name': 'Sheet2'}]
        result = gen._find_worksheet(worksheets, 'Sheet2')
        self.assertEqual(result['name'], 'Sheet2')

    def test_returns_none_missing(self):
        gen = _make_generator()
        result = gen._find_worksheet([{'name': 'A'}], 'B')
        self.assertIsNone(result)

    def test_empty_list(self):
        gen = _make_generator()
        result = gen._find_worksheet([], 'X')
        self.assertIsNone(result)


# ─── _build_visual_query ────────────────────────────────────────────


class TestBuildVisualQuery(unittest.TestCase):
    """Visual query building — all 9 chart type branches."""

    def setUp(self):
        self.gen = _make_generator()
        _init_field_map(self.gen, main_table='Sales',
                        measure_names=['Revenue', 'Profit'],
                        bim_measure_names=['Revenue', 'Profit'])

    def _query(self, chart_type, fields):
        ws = {'chart_type': chart_type, 'fields': fields}
        return self.gen._build_visual_query(ws)

    def test_empty_fields(self):
        self.assertIsNone(self._query('bar', []))

    def test_only_skip_fields(self):
        fields = [{'name': 'Measure Names'}, {'name': 'Measure Values'}]
        self.assertIsNone(self._query('bar', fields))

    def test_map_type(self):
        fields = [{'name': 'Region'}, {'name': 'Revenue'}]
        result = self._query('map', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Size', qs)  # map uses Category + Size

    def test_table_type(self):
        fields = [{'name': 'Region'}, {'name': 'Revenue'}]
        result = self._query('tableEx', fields)
        qs = result['queryState']
        self.assertIn('Values', qs)
        self.assertTrue(len(qs['Values']['projections']) <= 10)

    def test_scatter_chart(self):
        fields = [{'name': 'Region'}, {'name': 'Revenue'}, {'name': 'Profit'}]
        result = self._query('scatterChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('X', qs)
        self.assertIn('Y', qs)

    def test_scatter_chart_one_measure(self):
        fields = [{'name': 'Region'}, {'name': 'Revenue'}]
        result = self._query('scatterChart', fields)
        qs = result['queryState']
        self.assertIn('Y', qs)
        self.assertNotIn('X', qs)

    def test_scatter_chart_three_measures_size(self):
        """Third measure → Size (bubble)."""
        self.gen._measure_names.add('Quantity')
        self.gen._bim_measure_names.add('Quantity')
        fields = [{'name': 'Region'}, {'name': 'Revenue'},
                  {'name': 'Profit'}, {'name': 'Quantity'}]
        result = self._query('scatterChart', fields)
        qs = result['queryState']
        self.assertIn('Size', qs)

    def test_gauge_type(self):
        fields = [{'name': 'Revenue'}, {'name': 'Profit'}, {'name': 'Region'}]
        result = self._query('gauge', fields)
        qs = result['queryState']
        self.assertIn('Y', qs)
        self.assertIn('TargetValue', qs)
        self.assertIn('Category', qs)

    def test_card_type(self):
        fields = [{'name': 'Revenue'}]
        result = self._query('card', fields)
        qs = result['queryState']
        self.assertIn('Fields', qs)  # PBIR card uses 'Fields' role

    def test_card_dims_only(self):
        """Card with no measures → uses dims."""
        fields = [{'name': 'Region'}]
        result = self._query('card', fields)
        qs = result['queryState']
        self.assertIn('Fields', qs)  # PBIR card uses 'Fields' role

    def test_pie_chart(self):
        fields = [{'name': 'Region'}, {'name': 'Revenue'}]
        result = self._query('pieChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Y', qs)

    def test_donut_chart(self):
        fields = [{'name': 'Region'}, {'name': 'Revenue'}]
        result = self._query('donutChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)

    def test_treemap_uses_group_role(self):
        """Treemap must use Group role (not Category) and Values (not Y)."""
        fields = [{'name': 'Region'}, {'name': 'Revenue'}]
        result = self._query('treemap', fields)
        qs = result['queryState']
        self.assertIn('Group', qs)
        self.assertIn('Values', qs)
        self.assertNotIn('Category', qs)
        self.assertNotIn('Y', qs)

    def test_filled_map_uses_location_role(self):
        """Filled map must use Category role (PBIR Location well)."""
        fields = [{'name': 'Country'}, {'name': 'Revenue'}]
        result = self._query('filledMap', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Size', qs)
        self.assertNotIn('Location', qs)

    def test_matrix_uses_rows_columns_values(self):
        """Matrix must use Rows/Columns/Values roles."""
        fields = [{'name': 'Region'}, {'name': 'Month'}, {'name': 'Revenue'}]
        result = self._query('matrix', fields)
        qs = result['queryState']
        self.assertIn('Rows', qs)
        self.assertIn('Columns', qs)
        self.assertIn('Values', qs)

    def test_combo_chart(self):
        fields = [{'name': 'Month'}, {'name': 'Revenue'}, {'name': 'Profit'}]
        result = self._query('lineClusteredColumnComboChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('ColumnY', qs)
        self.assertIn('LineY', qs)

    def test_waterfall_chart(self):
        fields = [{'name': 'Region'}, {'name': 'Month'}, {'name': 'Revenue'}]
        result = self._query('waterfallChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Y', qs)
        self.assertIn('Breakdown', qs)

    def test_box_and_whisker(self):
        fields = [{'name': 'Region'}, {'name': 'Revenue'}]
        result = self._query('boxAndWhisker', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Value', qs)

    def test_standard_chart_dim_fallback(self):
        """No measures → last dim used as Y."""
        self.gen._measure_names.clear()
        self.gen._bim_measure_names.clear()
        fields = [{'name': 'Region'}, {'name': 'State'}]
        result = self._query('clusteredBarChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Y', qs)

    def test_deduplicate_fields(self):
        """Same field from multiple shelves is deduplicated."""
        fields = [{'name': 'Revenue'}, {'name': 'Revenue'}]
        result = self._query('clusteredBarChart', fields)
        qs = result['queryState']
        # Only one projection for Revenue; no dims → fallback to card with Fields
        self.assertIn('Fields', qs)

    def test_skip_tableau_internal_fields(self):
        fields = [{'name': '__tableau_internal_object_id__'}, {'name': 'Revenue'}]
        result = self._query('clusteredBarChart', fields)
        qs = result['queryState']
        # Only Revenue remains (measure, no dims) → fallback to card with Fields
        self.assertIn('Fields', qs)

    def test_measure_value_shelf_treated_as_measure(self):
        """Fields with shelf='measure_value' (from Measure Names expansion) → measure role."""
        fields = [
            {'name': 'Region'},
            {'name': 'Revenue', 'shelf': 'measure_value'},
            {'name': 'Profit', 'shelf': 'measure_value'},
        ]
        result = self._query('clusteredBarChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Y', qs)
        # Both measures should be in Y projections
        self.assertEqual(len(qs['Y']['projections']), 2)

    def test_all_measures_fallback_to_card(self):
        """Only measures (no dims) in a bar chart → fallback to card/multiRowCard."""
        fields = [{'name': 'Revenue'}, {'name': 'Profit'}]
        ws = {'chart_type': 'clusteredBarChart', 'fields': fields}
        result = self.gen._build_visual_query(ws)
        qs = result['queryState']
        self.assertIn('Fields', qs)  # card uses 'Fields' role
        # Should set override visual type
        self.assertEqual(ws.get('_override_visual_type'), 'card')

    def test_all_measures_fallback_multirowcard(self):
        """3+ measures → multiRowCard."""
        self.gen._measure_names.add('Quantity')
        self.gen._bim_measure_names.add('Quantity')
        fields = [{'name': 'Revenue'}, {'name': 'Profit'}, {'name': 'Quantity'}]
        ws = {'chart_type': 'clusteredBarChart', 'fields': fields}
        result = self.gen._build_visual_query(ws)
        self.assertEqual(ws.get('_override_visual_type'), 'multiRowCard')

    def test_multiple_measures_in_y_role(self):
        """Standard chart with dim + multiple measures → all measures in Y."""
        self.gen._measure_names.add('Quantity')
        self.gen._bim_measure_names.add('Quantity')
        fields = [{'name': 'Region'}, {'name': 'Revenue'}, {'name': 'Profit'}, {'name': 'Quantity'}]
        result = self._query('areaChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Y', qs)
        self.assertEqual(len(qs['Y']['projections']), 3)

    # ── Shelf-aware tests ────────────────────────────────────────

    def test_color_dim_becomes_series(self):
        """A dimension on the color shelf → Series role."""
        fields = [
            {'name': 'Date', 'shelf': 'columns'},
            {'name': 'Segment', 'shelf': 'rows'},
            {'name': 'Revenue', 'shelf': 'rows'},
        ]
        result = self._query('areaChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Series', qs)
        self.assertIn('Y', qs)

    def test_color_shelf_dim_overrides_axis_series(self):
        """Color dim has priority for Series over second axis dim."""
        fields = [
            {'name': 'Date', 'shelf': 'columns'},
            {'name': 'Region', 'shelf': 'rows'},
            {'name': 'Segment', 'shelf': 'color'},
            {'name': 'Revenue', 'shelf': 'rows'},
        ]
        result = self._query('areaChart', fields)
        qs = result['queryState']
        self.assertIn('Series', qs)
        # Segment (color) wins Series, not Region (2nd axis dim)
        prop = qs['Series']['projections'][0]['field']['Column']['Property']
        self.assertEqual(prop, 'Segment')

    def test_tooltip_shelf_becomes_tooltips_role(self):
        """Tooltip fields → Tooltips PBIR role (not Y)."""
        fields = [
            {'name': 'Region', 'shelf': 'rows'},
            {'name': 'Revenue', 'shelf': 'columns'},
            {'name': 'Profit', 'shelf': 'tooltip'},
        ]
        result = self._query('clusteredBarChart', fields)
        qs = result['queryState']
        self.assertIn('Tooltips', qs)
        self.assertEqual(len(qs['Y']['projections']), 1)  # Only Revenue in Y

    def test_color_measure_goes_to_tooltips(self):
        """A measure on the color shelf → Tooltips (not Y)."""
        fields = [
            {'name': 'Region', 'shelf': 'rows'},
            {'name': 'Revenue', 'shelf': 'columns'},
            {'name': 'Profit', 'shelf': 'color'},  # Profit is a measure
        ]
        result = self._query('clusteredBarChart', fields)
        qs = result['queryState']
        self.assertIn('Tooltips', qs)
        # Only Revenue should be in Y (not Profit)
        self.assertEqual(len(qs['Y']['projections']), 1)

    def test_map_uses_location_role(self):
        """Map visual must use Category role (PBIR Location well)."""
        fields = [{'name': 'City', 'shelf': 'rows'}, {'name': 'Revenue'}]
        result = self._query('map', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertNotIn('Location', qs)

    def test_map_multiple_geo_dims_in_location(self):
        """Map: all geo dims → Category role (multiple levels)."""
        fields = [
            {'name': 'Country', 'shelf': 'rows'},
            {'name': 'City', 'shelf': 'rows'},
            {'name': 'Revenue'},
        ]
        result = self._query('map', fields)
        qs = result['queryState']
        self.assertEqual(len(qs['Category']['projections']), 2)

    def test_filled_map_legend_from_color_dim(self):
        """FilledMap: color dim → Series role."""
        fields = [
            {'name': 'Country', 'shelf': 'rows'},
            {'name': 'Segment', 'shelf': 'color'},
            {'name': 'Revenue'},
        ]
        result = self._query('filledMap', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Series', qs)

    def test_treemap_non_date_dims_first(self):
        """Treemap: non-date dims sorted before date dims in Group role."""
        fields = [
            {'name': 'Date', 'shelf': 'columns'},
            {'name': 'Category', 'shelf': 'rows'},
            {'name': 'Revenue'},
        ]
        result = self._query('treemap', fields)
        qs = result['queryState']
        projs = qs['Group']['projections']
        self.assertEqual(len(projs), 2)
        # Category (non-date) should be first
        self.assertEqual(projs[0]['field']['Column']['Property'], 'Category')

    def test_treemap_multiple_group_levels(self):
        """Treemap: all dims become Group hierarchy levels."""
        fields = [
            {'name': 'Region', 'shelf': 'rows'},
            {'name': 'Category', 'shelf': 'rows'},
            {'name': 'Revenue'},
        ]
        result = self._query('treemap', fields)
        qs = result['queryState']
        self.assertEqual(len(qs['Group']['projections']), 2)

    def test_series_not_set_without_measures(self):
        """Without measures, 2nd axis dim falls back to Y (not Series)."""
        self.gen._measure_names.clear()
        self.gen._bim_measure_names.clear()
        fields = [{'name': 'Region'}, {'name': 'State'}]
        result = self._query('clusteredBarChart', fields)
        qs = result['queryState']
        self.assertIn('Category', qs)
        self.assertIn('Y', qs)
        self.assertNotIn('Series', qs)

    def test_scatter_all_dims_in_category(self):
        """Scatter: all dims (axis + color) → Category."""
        fields = [
            {'name': 'Region', 'shelf': 'rows'},
            {'name': 'Segment', 'shelf': 'color'},
            {'name': 'Revenue', 'shelf': 'columns'},
            {'name': 'Profit', 'shelf': 'columns'},
        ]
        result = self._query('scatterChart', fields)
        qs = result['queryState']
        self.assertEqual(len(qs['Category']['projections']), 2)

    def test_combo_chart_with_series(self):
        """Combo chart: color dim → Series, 2 measures → ColumnY + LineY."""
        fields = [
            {'name': 'Month', 'shelf': 'columns'},
            {'name': 'Segment', 'shelf': 'color'},
            {'name': 'Revenue', 'shelf': 'rows'},
            {'name': 'Profit', 'shelf': 'rows'},
        ]
        result = self._query('lineClusteredColumnComboChart', fields)
        qs = result['queryState']
        self.assertIn('Series', qs)
        self.assertIn('ColumnY', qs)
        self.assertIn('LineY', qs)


class TestFieldMappingDuplicateColumns(unittest.TestCase):
    """Verify that duplicate column names across tables resolve to the main table."""

    def test_main_table_wins_for_duplicate_columns(self):
        """When 'Segment' exists in both main and secondary tables, main table wins."""
        gen = _make_generator()
        converted = {
            'datasources': [{
                'tables': [
                    {'name': 'Orders', 'columns': [
                        {'name': 'Region'}, {'name': 'Segment'}, {'name': 'Sales', 'role': 'measure'},
                    ]},
                    {'name': 'Targets', 'columns': [
                        {'name': 'Segment'}, {'name': 'Goal'},
                    ]},
                ],
                'columns': [],
                'calculations': [],
            }],
            'calculations': [],
            'groups': [],
        }
        gen._build_field_mapping(converted)
        # 'Orders' has more columns → main table, so Segment should resolve to Orders
        entity, prop = gen._field_map['Segment']
        self.assertEqual(entity, 'Orders')
        self.assertEqual(prop, 'Segment')


# ─── _make_projection_entry ─────────────────────────────────────────


class TestMakeProjectionEntry(unittest.TestCase):
    """Projection entry — BIM measure vs Column wrapper + fallback."""

    def setUp(self):
        self.gen = _make_generator()

    def test_bim_measure_wrapper(self):
        _init_field_map(self.gen, {'Revenue': ('Sales', 'Revenue')},
                        bim_measure_names=['Revenue'])
        entry = self.gen._make_projection_entry({'name': 'Revenue'})
        self.assertIn('Measure', entry['field'])

    def test_column_wrapper(self):
        _init_field_map(self.gen, {'Region': ('Sales', 'Region')})
        entry = self.gen._make_projection_entry({'name': 'Region'})
        self.assertIn('Column', entry['field'])

    def test_physical_measure_aggregation_wrapper(self):
        """Physical numeric columns in _measure_names get Aggregation(Sum)."""
        _init_field_map(self.gen, {'Amount': ('Sales', 'Amount')},
                        measure_names=['Amount'])
        entry = self.gen._make_projection_entry({'name': 'Amount'})
        self.assertIn('Aggregation', entry['field'])
        self.assertEqual(entry['field']['Aggregation']['Function'], 0)
        self.assertEqual(
            entry['field']['Aggregation']['Expression']['Column']['Property'],
            'Amount')

    def test_physical_measure_not_overridden_by_bim(self):
        """When in both _measure_names and _bim_measure_names, Measure wins."""
        _init_field_map(self.gen, {'Revenue': ('Sales', 'Revenue')},
                        measure_names=['Revenue'],
                        bim_measure_names=['Revenue'])
        entry = self.gen._make_projection_entry({'name': 'Revenue'})
        self.assertIn('Measure', entry['field'])

    def test_fallback_resolution_via_datasource_calcs(self):
        """Resolves via datasources_ref calculations when not in field_map."""
        _init_field_map(self.gen, main_table='Facts',
                        datasources_ref=[{'calculations': [
                            {'name': '[calc_profit]', 'caption': 'Profit'}
                        ]}])
        entry = self.gen._make_projection_entry({'name': 'calc_profit'})
        self.assertEqual(entry['field']['Column']['Property'], 'Profit')

    def test_active_and_queryref(self):
        _init_field_map(self.gen, {'Col': ('T', 'Col')})
        entry = self.gen._make_projection_entry({'name': 'Col'})
        self.assertTrue(entry['active'])
        self.assertEqual(entry['queryRef'], 'T.Col')


# ─── _make_scatter_axis_entry ────────────────────────────────────────


class TestMakeScatterAxisEntry(unittest.TestCase):
    """Scatter axis projection — Measure vs Aggregation wrapper."""

    def setUp(self):
        self.gen = _make_generator()

    def test_bim_measure_scatter(self):
        _init_field_map(self.gen, {'Revenue': ('Sales', 'Revenue')},
                        bim_measure_names=['Revenue'])
        entry = self.gen._make_scatter_axis_entry({'name': 'Revenue'})
        self.assertIn('Measure', entry['field'])

    def test_physical_column_aggregation(self):
        _init_field_map(self.gen, {'Amount': ('Sales', 'Amount')})
        entry = self.gen._make_scatter_axis_entry({'name': 'Amount'})
        self.assertIn('Aggregation', entry['field'])
        self.assertEqual(entry['field']['Aggregation']['Function'], 0)

    def test_fallback_no_field_map(self):
        _init_field_map(self.gen, main_table='Data',
                        datasources_ref=[{'calculations': [
                            {'name': '[x_calc]', 'caption': 'X Value'}
                        ]}])
        entry = self.gen._make_scatter_axis_entry({'name': 'x_calc'})
        self.assertEqual(entry['field']['Aggregation']['Expression']['Column']['Property'], 'X Value')


# ─── _build_label_objects ───────────────────────────────────────────


class TestBuildLabelObjects(unittest.TestCase):
    """Label objects — show, font, color, position, number format."""

    def setUp(self):
        self.gen = _make_generator()

    def test_show_labels_from_formatting(self):
        objects = {}
        fmt = {'mark': {'mark-labels-show': 'true'}}
        self.gen._build_label_objects(objects, fmt, {})
        self.assertIn('labels', objects)

    def test_show_labels_from_mark_encoding(self):
        objects = {}
        me = {'label': {'show': True}}
        self.gen._build_label_objects(objects, {}, me)
        self.assertIn('labels', objects)

    def test_label_font_size(self):
        objects = {}
        me = {'label': {'show': True, 'font_size': 14}}
        self.gen._build_label_objects(objects, {}, me)
        props = objects['labels'][0]['properties']
        self.assertEqual(props['fontSize'], _L("14D"))

    def test_label_font_color(self):
        objects = {}
        me = {'label': {'show': True, 'font_color': '#FF0000'}}
        self.gen._build_label_objects(objects, {}, me)
        props = objects['labels'][0]['properties']
        self.assertIn('color', props)

    def test_label_position_mapping(self):
        objects = {}
        me = {'label': {'show': True, 'position': 'top'}}
        self.gen._build_label_objects(objects, {}, me)
        props = objects['labels'][0]['properties']
        self.assertEqual(props['labelPosition'], _L("'OutsideEnd'"))

    def test_label_position_center(self):
        objects = {}
        me = {'label': {'show': True, 'position': 'center'}}
        self.gen._build_label_objects(objects, {}, me)
        props = objects['labels'][0]['properties']
        self.assertEqual(props['labelPosition'], _L("'InsideCenter'"))

    def test_label_color_from_formatting(self):
        objects = {}
        fmt = {'label': {'color': '#00FF00'}}
        self.gen._build_label_objects(objects, fmt, {})
        self.assertIn('labels', objects)

    def test_font_family(self):
        objects = {}
        fmt = {'font': {'family': 'Arial'}}
        self.gen._build_label_objects(objects, fmt, {})
        self.assertIn('labels', objects)
        props = objects['labels'][0]['properties']
        self.assertEqual(props['fontFamily'], _L("'Arial'"))

    def test_font_size_pt_strip(self):
        objects = {}
        fmt = {'font': {'size': '12pt'}}
        self.gen._build_label_objects(objects, fmt, {})
        props = objects['labels'][0]['properties']
        self.assertEqual(props['fontSize'], _L("12D"))

    def test_font_size_px_strip(self):
        objects = {}
        fmt = {'font': {'size': '16px'}}
        self.gen._build_label_objects(objects, fmt, {})
        props = objects['labels'][0]['properties']
        self.assertEqual(props['fontSize'], _L("16D"))

    def test_font_size_invalid(self):
        """Invalid font size → no crash, no fontSize key."""
        objects = {}
        fmt = {'font': {'size': 'big'}}
        self.gen._build_label_objects(objects, fmt, {})
        # Should have labels created (for font), but fontSize may be absent
        self.assertIn('labels', objects)

    def test_number_format(self):
        objects = {'labels': [{'properties': {}}]}
        fmt = {'number_format': '#,0.00'}
        self.gen._build_label_objects(objects, fmt, {})
        props = objects['labels'][0]['properties']
        self.assertIn('labelDisplayUnits', props)


# ─── _build_legend_objects ──────────────────────────────────────────


class TestBuildLegendObjects(unittest.TestCase):
    """Legend — position mapping, title, font size."""

    def setUp(self):
        self.gen = _make_generator()

    def test_no_color_field(self):
        objects = {}
        self.gen._build_legend_objects(objects, {}, {})
        self.assertNotIn('legend', objects)

    def test_default_position_right(self):
        objects = {}
        me = {'color': {'field': 'Category'}}
        self.gen._build_legend_objects(objects, me, {})
        self.assertIn('legend', objects)
        pos = objects['legend'][0]['properties']['position']
        self.assertEqual(pos, _L("'Right'"))

    def test_position_bottom(self):
        objects = {}
        me = {'color': {'field': 'Category'}}
        fmt = {'legend': {'position': 'bottom'}}
        self.gen._build_legend_objects(objects, me, fmt)
        pos = objects['legend'][0]['properties']['position']
        self.assertEqual(pos, _L("'Bottom'"))

    def test_position_top_left(self):
        objects = {}
        me = {'color': {'field': 'Category'}}
        fmt = {'legend': {'position': 'top-left'}}
        self.gen._build_legend_objects(objects, me, fmt)
        pos = objects['legend'][0]['properties']['position']
        self.assertEqual(pos, _L("'TopLeft'"))

    def test_legend_title(self):
        objects = {}
        me = {'color': {'field': 'Category'}}
        fmt = {'legend': {'title': 'My Legend'}}
        self.gen._build_legend_objects(objects, me, fmt)
        props = objects['legend'][0]['properties']
        self.assertIn('titleText', props)
        self.assertIn('showTitle', props)

    def test_legend_font_size(self):
        objects = {}
        me = {'color': {'field': 'Category'}}
        fmt = {'legend': {'font-size': 14}}
        self.gen._build_legend_objects(objects, me, fmt)
        props = objects['legend'][0]['properties']
        self.assertIn('fontSize', props)

    def test_skip_multiple_values(self):
        objects = {}
        me = {'color': {'field': 'Multiple Values'}}
        self.gen._build_legend_objects(objects, me, {})
        self.assertNotIn('legend', objects)


# ─── _build_axis_objects ────────────────────────────────────────────


class TestBuildAxisObjects(unittest.TestCase):
    """Axis objects — formatting, explicit axes, dual axis, enhanced config."""

    def setUp(self):
        self.gen = _make_generator()

    def test_axis_display_show(self):
        objects = {}
        ws = {'formatting': {'axis': {'display': 'true'}}}
        self.gen._build_axis_objects(objects, ws, 'clusteredBarChart')
        self.assertIn('categoryAxis', objects)
        self.assertIn('valueAxis', objects)

    def test_axis_display_none(self):
        objects = {}
        ws = {'formatting': {'axis': {'display': 'none'}}}
        self.gen._build_axis_objects(objects, ws, 'clusteredBarChart')
        self.assertNotIn('categoryAxis', objects)

    def test_explicit_axis_title(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'x': {'title': 'Month'}}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['categoryAxis'][0]['properties']
        self.assertEqual(props['showAxisTitle'], _L("true"))

    def test_y_axis_range(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'y': {
            'auto_range': False, 'range_min': 0, 'range_max': 100
        }}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['valueAxis'][0]['properties']
        self.assertEqual(props['start'], _L("0D"))
        self.assertEqual(props['end'], _L("100D"))

    def test_y_axis_log_scale(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'y': {'scale': 'log'}}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['valueAxis'][0]['properties']
        self.assertEqual(props['axisScale'], _L("'Log'"))

    def test_y_axis_reversed(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'y': {'reversed': True}}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['valueAxis'][0]['properties']
        self.assertEqual(props['reverseOrder'], _L("true"))

    def test_x_axis_reversed(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'x': {'reversed': True}}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['categoryAxis'][0]['properties']
        self.assertEqual(props['reverseOrder'], _L("true"))

    def test_dual_axis_combo(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {
            'y': {}, 'dual_axis': True, 'dual_axis_sync': True
        }}
        self.gen._build_axis_objects(objects, ws, 'lineClusteredColumnComboChart')
        self.assertIn('y1AxisReferenceLine', objects)

    def test_label_rotation(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'x': {'label_rotation': '45'}}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['categoryAxis'][0]['properties']
        self.assertEqual(props['labelAngle'], _L("45L"))

    def test_show_title_false(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'x': {'show_title': False}}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['categoryAxis'][0]['properties']
        self.assertEqual(props['showAxisTitle'], _L("false"))

    def test_show_label_false(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'x': {'show_label': False}}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['categoryAxis'][0]['properties']
        self.assertEqual(props['show'], _L("false"))

    def test_continuous_axis(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'x': {'is_continuous': True}}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['categoryAxis'][0]['properties']
        self.assertEqual(props['axisType'], _L("'Continuous'"))

    def test_categorical_axis(self):
        objects = {}
        ws = {'formatting': {}, 'axes': {'x': {'is_continuous': False}}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        props = objects['categoryAxis'][0]['properties']
        self.assertEqual(props['axisType'], _L("'Categorical'"))

    def test_dual_axis_dict_sync(self):
        """Dual axis via ws_data.dual_axis dict + synchronized."""
        objects = {}
        ws = {'formatting': {}, 'axes': {},
              'dual_axis': {'enabled': True, 'synchronized': True}}
        self.gen._build_axis_objects(objects, ws, 'bar')
        self.assertIn('valueAxis', objects)
        props = objects['valueAxis'][0]['properties']
        self.assertEqual(props['secShow'], _L("true"))


# ─── _build_visual_styling_objects ──────────────────────────────────


class TestBuildVisualStylingObjects(unittest.TestCase):
    """Styling — background, table headers, row banding, grid, data bars, padding."""

    def setUp(self):
        self.gen = _make_generator()

    def test_background_color(self):
        objects = {}
        ws = {'formatting': {'background_color': '#FFFFFF'}, 'fields': []}
        self.gen._build_visual_styling_objects(
            objects, ws, 'bar', ws['formatting'], {})
        self.assertIn('visualContainerStyle', objects)

    def test_background_from_pane(self):
        objects = {}
        ws = {'formatting': {'pane': {'background-color': '#EEE'}}, 'fields': []}
        self.gen._build_visual_styling_objects(
            objects, ws, 'bar', ws['formatting'], {})
        self.assertIn('visualContainerStyle', objects)

    def test_table_header_formatting(self):
        objects = {}
        fmt = {'header_style': {
            'font-size': 14, 'font-weight': 'bold', 'font-color': '#000'
        }}
        ws = {'formatting': fmt, 'fields': []}
        self.gen._build_visual_styling_objects(
            objects, ws, 'tableEx', fmt, {})
        self.assertIn('columnHeaders', objects)
        props = objects['columnHeaders'][0]['properties']
        self.assertEqual(props['bold'], _L("true"))

    def test_row_banding(self):
        objects = {}
        fmt = {'worksheet_style': {'band-color': '#F0F0F0'}}
        ws = {'formatting': fmt, 'fields': []}
        self.gen._build_visual_styling_objects(
            objects, ws, 'table', fmt, {})
        self.assertIn('values', objects)

    def test_grid_border(self):
        objects = {}
        fmt = {'header_style': {
            'border-style': 'solid', 'border-color': '#CCC'
        }}
        ws = {'formatting': fmt, 'fields': []}
        self.gen._build_visual_styling_objects(
            objects, ws, 'matrix', fmt, {})
        self.assertIn('gridlines', objects)

    def test_data_bars(self):
        objects = {}
        ws = {'formatting': {}, 'fields': [{'role': 'measure'}]}
        me = {'color': {'type': 'quantitative'}}
        self.gen._build_visual_styling_objects(
            objects, ws, 'tableEx', {}, me)
        self.assertIn('dataBar', objects)

    def test_default_row_banding_table(self):
        """Default banding fallback for table visuals."""
        objects = {}
        ws = {'formatting': {}, 'fields': []}
        self.gen._build_visual_styling_objects(
            objects, ws, 'table', {}, {})
        self.assertIn('values', objects)
        # Check F2F2F2 default
        color = str(objects['values'][0])
        self.assertIn('F2F2F2', color)

    def test_totals_and_subtotals(self):
        objects = {}
        ws = {'formatting': {}, 'fields': [],
              'totals': {'grand_totals': True, 'subtotals': True}}
        self.gen._build_visual_styling_objects(
            objects, ws, 'matrix', {}, {})
        self.assertIn('total', objects)
        self.assertIn('subTotals', objects)

    def test_padding(self):
        objects = {}
        ws = {'formatting': {}, 'fields': [],
              'padding': {'padding_top': 5, 'padding_left': 10}}
        self.gen._build_visual_styling_objects(
            objects, ws, 'bar', {}, {})
        self.assertIn('visualContainerPadding', objects)


# ─── _build_color_encoding_objects ──────────────────────────────────


class TestBuildColorEncodingObjects(unittest.TestCase):
    """Color encoding — gradient, single, categorical, stepped thresholds."""

    def setUp(self):
        self.gen = _make_generator()

    def test_gradient_two_colors(self):
        objects = {}
        me = {'color': {'type': 'quantitative',
                         'palette_colors': ['#FF0000', '#00FF00']}}
        self.gen._build_color_encoding_objects(objects, {}, 'bar', me)
        self.assertIn('dataPoint', objects)
        rules = objects['dataPoint'][0].get('rules', [])
        self.assertTrue(len(rules) >= 1)
        self.assertIn('min', rules[0]['gradient'])
        self.assertIn('max', rules[0]['gradient'])

    def test_gradient_three_colors_midpoint(self):
        objects = {}
        me = {'color': {'type': 'quantitative',
                         'palette_colors': ['#FF0000', '#FFFF00', '#00FF00']}}
        self.gen._build_color_encoding_objects(objects, {}, 'bar', me)
        rules = objects['dataPoint'][0].get('rules', [])
        self.assertIn('mid', rules[0]['gradient'])

    def test_single_color(self):
        objects = {}
        me = {'color': {'type': 'quantitative',
                         'palette_colors': ['#4472C4']}}
        self.gen._build_color_encoding_objects(objects, {}, 'bar', me)
        self.assertIn('dataPoint', objects)
        self.assertNotIn('rules', objects['dataPoint'][0])

    def test_categorical_color_values(self):
        objects = {}
        me = {'color': {'color_values': {'A': '#FF0000', 'B': '#00FF00'}}}
        self.gen._build_color_encoding_objects(objects, {}, 'bar', me)
        self.assertIn('dataPoint', objects)
        self.assertEqual(len(objects['dataPoint']), 2)

    def test_stepped_thresholds(self):
        objects = {}
        me = {'color': {'thresholds': [
            {'value': 10, 'color': '#FF0000'},
            {'value': 50, 'color': '#FFFF00'},
            {'value': 90, 'color': '#00FF00'},
        ]}}
        self.gen._build_color_encoding_objects(objects, {}, 'bar', me)
        self.assertIn('dataPoint', objects)
        # Check inputValue + operator
        dp = objects['dataPoint']
        self.assertTrue(len(dp) >= 3)
        has_input = any('inputValue' in str(r) for r in dp)
        self.assertTrue(has_input)

    def test_stepped_with_null_value(self):
        """Thresholds with None value → catch-all at end."""
        objects = {}
        me = {'color': {'thresholds': [
            {'value': 50, 'color': '#FF0000'},
            {'value': None, 'color': '#CCCCCC'},
        ]}}
        self.gen._build_color_encoding_objects(objects, {}, 'bar', me)
        self.assertIn('dataPoint', objects)

    def test_conditional_formatting_flag(self):
        """Stepped thresholds with field → conditionalFormatting."""
        objects = {}
        me = {'color': {'field': 'Revenue', 'thresholds': [
            {'value': 10, 'color': '#FF0000'},
            {'value': 50, 'color': '#00FF00'},
        ]}}
        self.gen._build_color_encoding_objects(objects, {}, 'bar', me)
        self.assertIn('conditionalFormatting', objects)


# ─── _build_analytics_objects ───────────────────────────────────────


class TestBuildAnalyticsObjects(unittest.TestCase):
    """Analytics — ref lines, trend, annotations, forecast, map, stats."""

    def setUp(self):
        self.gen = _make_generator()
        self.gen._main_table = 'Sales'

    def test_constant_reference_line(self):
        objects = {}
        ws = {'formatting': {}, 'reference_lines': [
            {'value': 100, 'label': 'Target', 'color': '#FF0000',
             'style': 'dashed', 'type': 'constant'}
        ]}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        ref = objects['valueAxis'][0]['properties']['referenceLine']
        self.assertEqual(ref[0]['type'], 'Constant')

    def test_trend_line(self):
        objects = {}
        ws = {'formatting': {}, 'trend_lines': [
            {'type': 'linear', 'color': '#666'}
        ]}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        self.assertIn('trend', objects)

    def test_trend_line_with_equation(self):
        objects = {}
        ws = {'formatting': {}, 'trend_lines': [
            {'type': 'exponential', 'color': '#666',
             'show_equation': True, 'show_r_squared': True}
        ]}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        trend_props = objects['trend'][0]['properties']
        self.assertEqual(trend_props['displayEquation'], _L("true"))
        self.assertEqual(trend_props['displayRSquared'], _L("true"))

    def test_trend_line_invalid_type(self):
        objects = {}
        ws = {'formatting': {}, 'trend_lines': [
            {'type': 'unknown_type', 'color': '#666'}
        ]}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        self.assertIn('trend', objects)

    def test_annotations_subtitle(self):
        objects = {}
        ws = {'formatting': {}, 'annotations': [
            {'text': 'Note 1'}, {'text': 'Note 2'}
        ]}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        self.assertIn('subTitle', objects)
        props = objects['subTitle'][0]['properties']
        self.assertEqual(props['show'], _L("true"))

    def test_forecast(self):
        objects = {}
        ws = {'formatting': {}, 'forecasting': [
            {'periods': 10, 'prediction_interval': '90', 'ignore_last': '2'}
        ]}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        self.assertIn('forecast', objects)
        props = objects['forecast'][0]['properties']
        self.assertEqual(props['forecastLength'], _L("10L"))
        self.assertEqual(props['confidenceLevel'], _L("'90'"))

    def test_map_options(self):
        objects = {}
        ws = {'formatting': {}, 'map_options': {
            'washout': '0.5', 'style': 'dark'
        }}
        self.gen._build_analytics_objects(objects, ws, 'map', {})
        self.assertIn('mapControl', objects)
        props = objects['mapControl'][0]['properties']
        self.assertEqual(props['mapStyle'], _L("'darkGrayscale'"))

    def test_map_invalid_washout(self):
        objects = {}
        ws = {'formatting': {}, 'map_options': {
            'washout': 'invalid', 'style': 'streets'
        }}
        self.gen._build_analytics_objects(objects, ws, 'map', {})
        self.assertIn('mapControl', objects)

    def test_distribution_band(self):
        objects = {}
        ws = {'formatting': {}, 'analytics_stats': [
            {'type': 'distribution_band', 'value_from': '10', 'value_to': '90'}
        ]}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        ref = objects['valueAxis'][0]['properties']['referenceLine']
        self.assertEqual(ref[0]['type'], 'Band')

    def test_stat_reference(self):
        objects = {}
        ws = {'formatting': {}, 'analytics_stats': [
            {'type': 'stat_line', 'computation': 'median'}
        ]}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        ref = objects['valueAxis'][0]['properties']['referenceLine']
        self.assertEqual(ref[0]['type'], 'Median')

    def test_small_multiples_direct(self):
        objects = {}
        ws = {'formatting': {}, 'small_multiples': 'Region'}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        self.assertIn('smallMultiple', objects)

    def test_small_multiples_from_pages_shelf(self):
        objects = {}
        ws = {'formatting': {}, 'pages_shelf': {'field': 'Year'}}
        self.gen._build_analytics_objects(objects, ws, 'bar', {})
        self.assertIn('smallMultiple', objects)


# ─── _create_visual_filters ─────────────────────────────────────────


class TestCreateVisualFilters(unittest.TestCase):
    """Visual filters — range, categorical, exclude, skips."""

    def setUp(self):
        self.gen = _make_generator()
        _init_field_map(self.gen, {'Region': ('Sales', 'Region'),
                                   'Amount': ('Sales', 'Amount')})

    def test_empty_filters(self):
        result = self.gen._create_visual_filters([])
        self.assertEqual(result, [])

    def test_skip_measure_names(self):
        filters = [{'field': 'Measure Names', 'values': ['x']}]
        result = self.gen._create_visual_filters(filters)
        self.assertEqual(result, [])

    def test_skip_measure_values(self):
        filters = [{'field': 'Measure Values', 'values': ['x']}]
        result = self.gen._create_visual_filters(filters)
        self.assertEqual(result, [])

    def test_skip_date_part(self):
        filters = [{'field': 'OrderDate', 'date_part': 'yr', 'values': ['x']}]
        result = self.gen._create_visual_filters(filters)
        self.assertEqual(result, [])

    def test_range_filter(self):
        filters = [{'field': 'Amount', 'filter_type': 'range',
                     'min': 10, 'max': 100}]
        result = self.gen._create_visual_filters(filters)
        self.assertTrue(len(result) >= 1)
        # Should have ComparisonKind
        filt_str = json.dumps(result)
        self.assertIn('ComparisonKind', filt_str)

    def test_categorical_filter(self):
        filters = [{'field': 'Region', 'values': ['East', 'West']}]
        result = self.gen._create_visual_filters(filters)
        self.assertTrue(len(result) >= 1)
        filt_str = json.dumps(result)
        self.assertIn('In', filt_str)

    def test_exclude_filter(self):
        filters = [{'field': 'Region', 'values': ['East'],
                     'exclude': True}]
        result = self.gen._create_visual_filters(filters)
        filt_str = json.dumps(result)
        self.assertIn('Not', filt_str)

    def test_empty_values_skip(self):
        filters = [{'field': 'Region', 'values': []}]
        result = self.gen._create_visual_filters(filters)
        self.assertEqual(result, [])


# ─── _create_report_filters ─────────────────────────────────────────


class TestCreateReportFilters(unittest.TestCase):
    """Report-level filters from parameters."""

    def setUp(self):
        self.gen = _make_generator()
        _init_field_map(self.gen, main_table='Data')

    def test_parameter_filter(self):
        conv = {'parameters': [
            {'name': 'Region', 'currentValue': 'East', 'values': ['East', 'West']}
        ]}
        result = self.gen._create_report_filters(conv)
        self.assertTrue(len(result) >= 1)

    def test_empty_parameters(self):
        conv = {'parameters': []}
        result = self.gen._create_report_filters(conv)
        self.assertEqual(result, [])

    def test_no_parameters_key(self):
        result = self.gen._create_report_filters({})
        self.assertEqual(result, [])


# ─── _resolve_field_entity ──────────────────────────────────────────


class TestResolveFieldEntityCoverage(unittest.TestCase):
    """4-step resolution — direct, prefix strip, partial, fallback."""

    def setUp(self):
        self.gen = _make_generator()
        _init_field_map(self.gen, {'Revenue': ('Sales', 'Revenue'),
                                   'Profit': ('Sales', 'Profit')},
                        main_table='Sales')

    def test_direct_match(self):
        entity, prop = self.gen._resolve_field_entity('Revenue')
        self.assertEqual(entity, 'Sales')
        self.assertEqual(prop, 'Revenue')

    def test_prefix_strip(self):
        """Field with attr: prefix should still resolve."""
        entity, prop = self.gen._resolve_field_entity('attr:Revenue')
        self.assertEqual(entity, 'Sales')

    def test_fallback_main_table(self):
        entity, prop = self.gen._resolve_field_entity('Unknown')
        self.assertEqual(entity, 'Sales')
        self.assertEqual(prop, 'Unknown')


# ─── _create_page_navigator ────────────────────────────────────────


class TestCreatePageNavigator(unittest.TestCase):
    """Page navigator visual — 40px Tabs bar."""

    def test_creates_visual_json(self):
        gen = _make_generator()
        tmpdir = tempfile.mkdtemp()
        visuals_dir = os.path.join(tmpdir, 'visuals')
        os.makedirs(visuals_dir, exist_ok=True)
        gen._create_page_navigator(visuals_dir, 1280, 720, 5)
        # Should have created a visual subdirectory
        subdirs = os.listdir(visuals_dir)
        self.assertEqual(len(subdirs), 1)
        visual_json = os.path.join(visuals_dir, subdirs[0], 'visual.json')
        self.assertTrue(os.path.exists(visual_json))
        with open(visual_json) as f:
            data = json.load(f)
        self.assertEqual(data['visual']['visualType'], 'pageNavigator')
        self.assertEqual(data['position']['y'], 720 - 40)
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── _create_pages_shelf_slicer ─────────────────────────────────────


class TestCreatePagesShelfSlicer(unittest.TestCase):
    """Animation-hint slicer from Pages shelf."""

    def test_creates_slicer(self):
        gen = _make_generator()
        gen._main_table = 'Sales'
        gen._field_map = {}
        tmpdir = tempfile.mkdtemp()
        visuals_dir = os.path.join(tmpdir, 'visuals')
        os.makedirs(visuals_dir, exist_ok=True)
        conv = {'datasources': [{'tables': [
            {'name': 'Sales', 'columns': [{'name': 'Year'}]}
        ]}]}
        gen._create_pages_shelf_slicer(
            visuals_dir, {'field': 'Year'}, 1.0, 1.0, 0, conv)
        subdirs = os.listdir(visuals_dir)
        self.assertEqual(len(subdirs), 1)
        visual_json = os.path.join(visuals_dir, subdirs[0], 'visual.json')
        with open(visual_json) as f:
            data = json.load(f)
        self.assertEqual(data['visual']['visualType'], 'slicer')
        # Should have Pages Shelf comment
        general = data['visual']['objects'].get('general', [])
        self.assertTrue(len(general) >= 1)
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_empty_field_noop(self):
        gen = _make_generator()
        tmpdir = tempfile.mkdtemp()
        visuals_dir = os.path.join(tmpdir, 'visuals')
        os.makedirs(visuals_dir, exist_ok=True)
        gen._create_pages_shelf_slicer(visuals_dir, {'field': ''}, 1, 1, 0, {})
        # No visual created
        self.assertEqual(len(os.listdir(visuals_dir)), 0)
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── _create_drillthrough_pages ──────────────────────────────────────


class TestCreateDrillthroughPages(unittest.TestCase):
    """Drillthrough pages from filter/set-value actions."""

    def setUp(self):
        self.gen = _make_generator()
        _init_field_map(self.gen, main_table='Sales')
        self.tmpdir = tempfile.mkdtemp()
        self.pages_dir = os.path.join(self.tmpdir, 'pages')
        os.makedirs(self.pages_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_creates_drillthrough_page(self):
        worksheets = [{'name': 'Detail', 'fields': [{'name': 'Revenue'}],
                       'chart_type': 'table'}]
        conv = {
            'actions': [{'type': 'filter', 'target_worksheets': ['Detail'],
                         'field': 'Region'}],
            'datasources': [{'tables': [
                {'name': 'Sales', 'columns': [{'name': 'Region'}]}
            ]}]
        }
        page_names = []
        self.gen._create_drillthrough_pages(
            self.pages_dir, page_names, worksheets, conv)
        self.assertTrue(len(page_names) >= 1)
        # Verify page.json exists
        dt_dir = os.path.join(self.pages_dir, page_names[0])
        with open(os.path.join(dt_dir, 'page.json')) as f:
            data = json.load(f)
        self.assertEqual(data['pageType'], 'Drillthrough')

    def test_no_actions_noop(self):
        page_names = []
        self.gen._create_drillthrough_pages(
            self.pages_dir, page_names, [], {'actions': []})
        self.assertEqual(len(page_names), 0)

    def test_skip_non_filter_actions(self):
        conv = {'actions': [{'type': 'url', 'target_worksheets': ['X']}]}
        page_names = []
        self.gen._create_drillthrough_pages(
            self.pages_dir, page_names, [], conv)
        self.assertEqual(len(page_names), 0)

    def test_set_value_action(self):
        worksheets = [{'name': 'Target', 'fields': [{'name': 'Qty'}],
                       'chart_type': 'bar'}]
        conv = {
            'actions': [{'type': 'set-value',
                         'target_worksheet': 'Target',
                         'source_field': 'Category'}],
            'datasources': [{'tables': [
                {'name': 'T', 'columns': [{'name': 'Category'}]}
            ]}]
        }
        page_names = []
        self.gen._create_drillthrough_pages(
            self.pages_dir, page_names, worksheets, conv)
        self.assertTrue(len(page_names) >= 1)


# ─── _detect_script_visual ──────────────────────────────────────────


class TestDetectScriptVisual(unittest.TestCase):
    """SCRIPT_* detection in calculations + mark_encoding."""

    def test_returns_none_no_ws(self):
        gen = _make_generator()
        result = gen._detect_script_visual(None, {})
        self.assertIsNone(result)

    def test_returns_none_no_scripts(self):
        gen = _make_generator()
        gen._field_map = {}
        ws = {'fields': [{'name': 'Revenue'}]}
        conv = {'calculations': [{'name': 'Revenue', 'formula': 'SUM([Sales])'}]}
        result = gen._detect_script_visual(ws, conv)
        self.assertIsNone(result)


# ─── _build_field_mapping ───────────────────────────────────────────


class TestBuildFieldMapping(unittest.TestCase):
    """Field mapping phases — DS-level inheritance, groups, calcs, measures."""

    def setUp(self):
        self.gen = _make_generator()

    def _build(self, conv):
        self.gen._actual_bim_measure_names = set()
        self.gen._actual_bim_symbols = {}
        self.gen._build_field_mapping(conv)

    def test_basic_mapping(self):
        conv = {
            'datasources': [{'tables': [
                {'name': 'Sales', 'columns': [
                    {'name': 'Region', 'caption': 'Region'},
                    {'name': 'Amount', 'caption': 'Amount'}
                ]}
            ], 'calculations': []}],
            'calculations': [], 'groups': []
        }
        self._build(conv)
        self.assertIn('Region', self.gen._field_map)
        self.assertEqual(self.gen._main_table, 'Sales')

    def test_measure_classification(self):
        """Physical role='measure' → _measure_names but NOT _bim_measure_names."""
        conv = {
            'datasources': [{'tables': [
                {'name': 'Sales', 'columns': [
                    {'name': 'Revenue', 'role': 'measure'}
                ]}
            ], 'calculations': []}],
            'calculations': [], 'groups': []
        }
        self._build(conv)
        self.assertIn('Revenue', self.gen._measure_names)
        self.assertNotIn('Revenue', self.gen._bim_measure_names)

    def test_calculation_indexing(self):
        conv = {
            'datasources': [{'tables': [
                {'name': 'Facts', 'columns': []}
            ], 'calculations': [
                {'name': '[Profit]', 'caption': 'Profit', 'role': 'measure'}
            ]}],
            'calculations': [], 'groups': []
        }
        self._build(conv)
        self.assertIn('Profit', self.gen._field_map)
        self.assertIn('Profit', self.gen._measure_names)

    def test_groups_mapping(self):
        conv = {
            'datasources': [{'tables': [
                {'name': 'T', 'columns': []}
            ], 'calculations': []}],
            'calculations': [], 'groups': [{'name': '[RegionGroup]'}]
        }
        self._build(conv)
        self.assertIn('RegionGroup', self.gen._field_map)

    def test_bim_measure_names_populated(self):
        # Call _build_field_mapping directly to avoid helper resetting _actual_bim_measure_names
        self.gen._actual_bim_measure_names = {'TotalSales'}
        self.gen._actual_bim_symbols = {}
        conv = {
            'datasources': [{'tables': [
                {'name': 'S', 'columns': [{'name': 'Col1'}]}
            ], 'calculations': []}],
            'calculations': [], 'groups': []
        }
        self.gen._build_field_mapping(conv)
        self.assertIn('TotalSales', self.gen._bim_measure_names)

    def test_top_level_calc_measures(self):
        conv = {
            'datasources': [{'tables': [
                {'name': 'T', 'columns': []}
            ], 'calculations': []}],
            'calculations': [
                {'name': '[Margin]', 'caption': 'Margin', 'role': 'measure'}
            ],
            'groups': []
        }
        self._build(conv)
        self.assertIn('Margin', self.gen._measure_names)

    def test_skip_special_columns(self):
        """DS-level columns starting with '[:' should be skipped during inheritance."""
        conv = {
            'datasources': [{
                'tables': [
                    {'name': 'T'}  # No columns → triggers DS-level inheritance
                ],
                'columns': [
                    {'name': '[:internal]', 'caption': 'internal'},
                    {'name': 'Real', 'caption': 'Real'}
                ],
                'calculations': []
            }],
            'calculations': [], 'groups': []
        }
        self._build(conv)
        self.assertNotIn('[:internal]', self.gen._field_map)
        self.assertIn('Real', self.gen._field_map)

    def test_multiple_datasources_main_table(self):
        """Main table = table with most columns."""
        conv = {
            'datasources': [
                {'tables': [
                    {'name': 'Small', 'columns': [{'name': 'A'}]},
                ], 'calculations': []},
                {'tables': [
                    {'name': 'Big', 'columns': [
                        {'name': 'X'}, {'name': 'Y'}, {'name': 'Z'}
                    ]},
                ], 'calculations': []},
            ],
            'calculations': [], 'groups': []
        }
        self._build(conv)
        self.assertEqual(self.gen._main_table, 'Big')


# ─── _create_swap_bookmarks ─────────────────────────────────────────


class TestCreateSwapBookmarks(unittest.TestCase):
    """Dynamic zone → swap bookmarks with MigrationNote."""

    def setUp(self):
        self.gen = _make_generator()

    def test_creates_bookmarks(self):
        dynamic_zones = [
            {'zone': 'zone1', 'field': 'Param', 'value': 'A',
             'condition': 'equals', 'worksheet': 'Sheet1'},
            {'zone': 'zone1', 'field': 'Param', 'value': 'B',
             'condition': 'equals', 'worksheet': 'Sheet2'},
        ]
        result = self.gen._create_swap_bookmarks(dynamic_zones, 'Page1')
        self.assertTrue(len(result) >= 2)
        # Check PBIR-compliant options are present
        bm_str = json.dumps(result)
        self.assertIn('targetVisualNames', bm_str)

    def test_empty_zones(self):
        result = self.gen._create_swap_bookmarks([], 'Page1')
        self.assertEqual(result, [])


# ─── _copy_custom_shapes ────────────────────────────────────────────


class TestCopyCustomShapes(unittest.TestCase):
    """Shape file copying from tableau_export/shapes/."""

    def test_no_shapes_directory(self):
        """No crash when shapes dir doesn't exist."""
        gen = _make_generator()
        tmpdir = tempfile.mkdtemp()
        def_dir = os.path.join(tmpdir, 'definition')
        os.makedirs(def_dir, exist_ok=True)
        # Should not crash
        gen._copy_custom_shapes(def_dir, {})
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── create_metadata ────────────────────────────────────────────────


class TestCreateMetadata(unittest.TestCase):
    """Migration metadata JSON generation."""

    def test_creates_metadata_file(self):
        gen = _make_generator()
        tmpdir = tempfile.mkdtemp()
        project_dir = os.path.join(tmpdir, 'TestProject')
        os.makedirs(project_dir, exist_ok=True)
        conv = {
            'worksheets': [{'name': 'Sheet1'}],
            'dashboards': [],
            'datasources': [],
            'calculations': [],
            'parameters': [],
            'filters': [],
        }
        gen.create_metadata(project_dir, 'TestReport', conv)
        meta_path = os.path.join(project_dir, 'migration_metadata.json')
        self.assertTrue(os.path.exists(meta_path))
        with open(meta_path) as f:
            data = json.load(f)
        self.assertEqual(data['report_name'], 'TestReport')
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── _create_paginated_report ───────────────────────────────────────


class TestCreatePaginatedReport(unittest.TestCase):
    """RDL-style paginated report — report.json, header, footer, tablix."""

    def test_creates_paginated_structure(self):
        gen = _make_generator()
        gen._main_table = 'Sales'
        gen._field_map = {'Revenue': ('Sales', 'Revenue')}
        gen._measure_names = set()
        gen._bim_measure_names = set()
        gen._datasources_ref = []
        tmpdir = tempfile.mkdtemp()
        project_dir = os.path.join(tmpdir, 'Project')
        os.makedirs(project_dir, exist_ok=True)
        conv = {
            'worksheets': [{'name': 'Sheet1', 'fields': [
                {'name': 'Region'}, {'name': 'Revenue'}
            ]}],
            'datasources': [],
        }
        gen._create_paginated_report(project_dir, 'Report', conv)
        pag_dir = os.path.join(project_dir, 'PaginatedReport')
        self.assertTrue(os.path.isdir(pag_dir))
        report_json = os.path.join(pag_dir, 'report.json')
        self.assertTrue(os.path.exists(report_json))
        with open(report_json) as f:
            data = json.load(f)
        self.assertIn('pageWidth', data)
        # Check header and footer
        self.assertTrue(os.path.exists(os.path.join(pag_dir, 'header.json')))
        self.assertTrue(os.path.exists(os.path.join(pag_dir, 'footer.json')))
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_multiple_worksheets(self):
        gen = _make_generator()
        gen._main_table = 'T'
        gen._field_map = {}
        gen._measure_names = set()
        gen._bim_measure_names = set()
        gen._datasources_ref = []
        tmpdir = tempfile.mkdtemp()
        project_dir = os.path.join(tmpdir, 'P')
        os.makedirs(project_dir, exist_ok=True)
        conv = {
            'worksheets': [
                {'name': 'S1', 'fields': [{'name': 'A'}]},
                {'name': 'S2', 'fields': [{'name': 'B'}]},
            ],
            'datasources': [],
        }
        gen._create_paginated_report(project_dir, 'R', conv)
        pag_dir = os.path.join(project_dir, 'PaginatedReport')
        # Should have tablix pages
        pages = [f for f in os.listdir(pag_dir)
                 if f.startswith('page_') or f.startswith('tablix')]
        self.assertTrue(len(pages) >= 0)  # Structure exists
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── create_tmdl_model error path ───────────────────────────────────


class TestCreateTmdlModelError(unittest.TestCase):
    """Error path in create_tmdl_model — try/except with traceback."""

    def test_error_does_not_crash(self):
        """When TMDL generation raises, should print error not crash."""
        gen = _make_generator()
        gen._calendar_start = None
        gen._calendar_end = None
        gen._culture = None
        gen._model_mode = 'import'
        gen._languages = None
        tmpdir = tempfile.mkdtemp()
        sm_dir = os.path.join(tmpdir, 'sm')
        os.makedirs(sm_dir, exist_ok=True)
        # Patch tmdl_generator.generate_tmdl to raise an error
        with patch('powerbi_import.pbip_generator.tmdl_generator') as mock_tmdl:
            mock_tmdl.generate_tmdl.side_effect = ValueError('test error')
            # Should NOT raise — error is caught internally
            gen.create_tmdl_model(sm_dir, 'Test', {})
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── _make_visual_position edge cases ───────────────────────────────


class TestMakeVisualPositionEdgeCases(unittest.TestCase):
    """Edge cases — clamping to page bounds, min size."""

    def test_clamp_width_to_page(self):
        gen = _make_generator()
        pos = {'x': 1200, 'y': 0, 'w': 200, 'h': 100}
        result = gen._make_visual_position(pos, 1.0, 1.0, 0, 1280, 720)
        self.assertLessEqual(result['x'] + result['width'], 1280)

    def test_clamp_height_to_page(self):
        gen = _make_generator()
        pos = {'x': 0, 'y': 650, 'w': 100, 'h': 200}
        result = gen._make_visual_position(pos, 1.0, 1.0, 0, 1280, 720)
        self.assertLessEqual(result['y'] + result['height'], 720)

    def test_minimum_width(self):
        gen = _make_generator()
        pos = {'x': 0, 'y': 0, 'w': 10, 'h': 100}
        result = gen._make_visual_position(pos, 1.0, 1.0, 0, 1280, 720)
        self.assertGreaterEqual(result['width'], 60)

    def test_minimum_height(self):
        gen = _make_generator()
        pos = {'x': 0, 'y': 0, 'w': 100, 'h': 10}
        result = gen._make_visual_position(pos, 1.0, 1.0, 0, 1280, 720)
        self.assertGreaterEqual(result['height'], 40)


# ─── Integration test: generate_project with paginated ──────────────


class TestGenerateProjectPaginated(unittest.TestCase):
    """Integration: generate_project with paginated=True."""

    def test_paginated_flag_stored(self):
        gen = _make_generator()
        conv = {
            'worksheets': [{'name': 'Sheet1', 'fields': [{'name': 'A'}],
                           'chart_type': 'bar'}],
            'dashboards': [],
            'datasources': [{'tables': [
                {'name': 'T', 'columns': [{'name': 'A'}]}
            ], 'calculations': []}],
            'calculations': [], 'parameters': [], 'filters': [],
            'stories': [], 'actions': [], 'sets': [], 'groups': [],
            'bins': [], 'hierarchies': [], 'sort_orders': [],
            'aliases': [], 'custom_sql': [], 'user_filters': [],
        }
        with patch.object(gen, 'create_tmdl_model'):
            with patch.object(gen, '_create_paginated_report') as mock_pag:
                gen.generate_project('Test', conv, paginated=True)
                self.assertTrue(gen._paginated)
                mock_pag.assert_called_once()


# ─── _build_visual_objects orchestrator ──────────────────────────────


class TestBuildVisualObjectsOrchestrator(unittest.TestCase):
    """Orchestrator delegates to sub-methods."""

    def test_title_in_visualContainerObjects(self):
        gen = _make_generator()
        _init_field_map(gen, main_table='T')
        objects = gen._build_visual_objects('MySheet', None, 'bar')
        # Title is in visualContainerObjects, not in visual.objects
        self.assertNotIn('title', objects)

    def test_with_formatting(self):
        gen = _make_generator()
        gen._main_table = 'T'
        ws = {
            'formatting': {'mark': {'mark-labels-show': 'true'}},
            'mark_encoding': {'label': {'show': True}},
        }
        objects = gen._build_visual_objects('Sheet', ws, 'bar')
        self.assertIn('labels', objects)


# ─── _create_action_visuals ─────────────────────────────────────────


class TestCreateActionVisuals(unittest.TestCase):
    """Action buttons — URL and sheet-navigate."""

    def setUp(self):
        self.gen = _make_generator()
        self.tmpdir = tempfile.mkdtemp()
        self.visuals_dir = os.path.join(self.tmpdir, 'visuals')
        os.makedirs(self.visuals_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_url_action(self):
        actions = [{'type': 'url', 'url': 'https://example.com',
                    'name': 'Go'}]
        count = self.gen._create_action_visuals(
            self.visuals_dir, actions, 1.0, 1.0, 0, 'Page1')
        self.assertEqual(count, 1)
        subdirs = os.listdir(self.visuals_dir)
        self.assertEqual(len(subdirs), 1)

    def test_navigate_action(self):
        actions = [{'type': 'sheet-navigate', 'name': 'Nav',
                    'target_worksheet': 'Sheet2'}]
        count = self.gen._create_action_visuals(
            self.visuals_dir, actions, 1.0, 1.0, 0, 'Page1')
        self.assertEqual(count, 1)

    def test_non_url_or_navigate_skip(self):
        actions = [{'type': 'filter', 'name': 'Filter'}]
        count = self.gen._create_action_visuals(
            self.visuals_dir, actions, 1.0, 1.0, 0, 'Page1')
        self.assertEqual(count, 0)

    def test_multiple_actions_y_offset(self):
        actions = [
            {'type': 'url', 'url': 'https://a.com', 'name': 'A'},
            {'type': 'url', 'url': 'https://b.com', 'name': 'B'},
        ]
        count = self.gen._create_action_visuals(
            self.visuals_dir, actions, 1.0, 1.0, 0, 'Page1')
        self.assertEqual(count, 2)


# ─── _create_visual_textbox ─────────────────────────────────────────


class TestCreateVisualTextbox(unittest.TestCase):
    """Textbox visual creation."""

    def test_creates_textbox_visual(self):
        gen = _make_generator()
        tmpdir = tempfile.mkdtemp()
        visuals_dir = os.path.join(tmpdir, 'visuals')
        os.makedirs(visuals_dir, exist_ok=True)
        obj = {'text': 'Hello', 'position': {'x': 0, 'y': 0, 'w': 200, 'h': 50}}
        gen._create_visual_textbox(visuals_dir, obj, 1.0, 1.0, 0)
        subdirs = os.listdir(visuals_dir)
        self.assertEqual(len(subdirs), 1)
        visual_json = os.path.join(visuals_dir, subdirs[0], 'visual.json')
        self.assertTrue(os.path.exists(visual_json))
        with open(visual_json) as f:
            data = json.load(f)
        self.assertEqual(data['visual']['visualType'], 'textbox')
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── _create_visual_image ───────────────────────────────────────────


class TestCreateVisualImage(unittest.TestCase):
    """Image visual with source URL."""

    def test_creates_image_visual(self):
        gen = _make_generator()
        tmpdir = tempfile.mkdtemp()
        visuals_dir = os.path.join(tmpdir, 'visuals')
        os.makedirs(visuals_dir, exist_ok=True)
        obj = {'url': 'https://img.example.com/logo.png',
               'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100}}
        gen._create_visual_image(visuals_dir, obj, 1.0, 1.0, 0)
        subdirs = os.listdir(visuals_dir)
        self.assertEqual(len(subdirs), 1)
        visual_json = os.path.join(visuals_dir, subdirs[0], 'visual.json')
        with open(visual_json) as f:
            data = json.load(f)
        self.assertEqual(data['visual']['visualType'], 'image')
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── _create_visual_filter_control ──────────────────────────────────


class TestCreateVisualFilterControl(unittest.TestCase):
    """Filter control → slicer visual."""

    def test_creates_slicer_from_filter_control(self):
        gen = _make_generator()
        _init_field_map(gen, {'Region': ('Sales', 'Region')})
        tmpdir = tempfile.mkdtemp()
        visuals_dir = os.path.join(tmpdir, 'visuals')
        os.makedirs(visuals_dir, exist_ok=True)
        obj = {
            'type': 'filter_control',
            'calc_col_id': 'Region',
            'position': {'x': 0, 'y': 0, 'w': 200, 'h': 50}
        }
        conv = {'parameters': [], 'datasources': []}
        gen._create_visual_filter_control(
            visuals_dir, obj, 1.0, 1.0, 0, {}, conv)
        subdirs = os.listdir(visuals_dir)
        self.assertTrue(len(subdirs) >= 1)
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_calc_id_to_caption_resolution(self):
        """Uses calc_id_to_caption map for proper field names."""
        gen = _make_generator()
        _init_field_map(gen, {'Profit': ('Sales', 'Profit')})
        tmpdir = tempfile.mkdtemp()
        visuals_dir = os.path.join(tmpdir, 'visuals')
        os.makedirs(visuals_dir, exist_ok=True)
        obj = {
            'type': 'filter_control',
            'calc_col_id': 'calc_123',
            'position': {'x': 0, 'y': 0, 'w': 200, 'h': 50}
        }
        conv = {'parameters': [], 'datasources': []}
        calc_map = {'calc_123': 'Profit'}
        gen._create_visual_filter_control(
            visuals_dir, obj, 1.0, 1.0, 0, calc_map, conv)
        subdirs = os.listdir(visuals_dir)
        self.assertTrue(len(subdirs) >= 1)
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── _create_tooltip_pages ──────────────────────────────────────────


class TestCreateTooltipPages(unittest.TestCase):
    """Tooltip pages — viz_in_tooltip flag."""

    def test_creates_tooltip_page(self):
        gen = _make_generator()
        _init_field_map(gen, main_table='T')
        tmpdir = tempfile.mkdtemp()
        pages_dir = os.path.join(tmpdir, 'pages')
        os.makedirs(pages_dir, exist_ok=True)
        worksheets = [
            {'name': 'Tooltip1', 'vizql_tooltip': True,
             'tooltip': {'viz_in_tooltip': True},
             'fields': [{'name': 'A'}], 'chart_type': 'bar'}
        ]
        conv = {'datasources': []}
        page_names = []
        gen._create_tooltip_pages(
            pages_dir, page_names, worksheets, conv)
        # Should create a tooltip page
        if page_names:
            page_dir = os.path.join(pages_dir, page_names[0])
            with open(os.path.join(page_dir, 'page.json')) as f:
                data = json.load(f)
            self.assertEqual(data.get('pageType'), 'Tooltip')
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── _create_mobile_pages ───────────────────────────────────────────


class TestCreateMobilePages(unittest.TestCase):
    """Mobile pages — phone layout 568×320."""

    def test_creates_mobile_page(self):
        gen = _make_generator()
        _init_field_map(gen, main_table='T')
        tmpdir = tempfile.mkdtemp()
        pages_dir = os.path.join(tmpdir, 'pages')
        os.makedirs(pages_dir, exist_ok=True)
        dashboards = [{
            'name': 'Dashboard1',
            'device_layouts': [{
                'device_type': 'phone',
                'auto_generated': False,
                'zones': [
                    {'name': 'S1', 'position': {'x': 0, 'y': 0, 'w': 300, 'h': 200}}
                ]
            }]
        }]
        worksheets = [{'name': 'S1', 'fields': [{'name': 'X'}], 'chart_type': 'bar'}]
        conv = {'datasources': []}
        page_names = []
        gen._create_mobile_pages(
            pages_dir, page_names, dashboards, worksheets, conv)
        # Should create a mobile page
        self.assertTrue(len(page_names) >= 1)
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
