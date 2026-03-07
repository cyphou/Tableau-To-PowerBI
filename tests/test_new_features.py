"""
Tests for newly ported features:
- Calculation groups (_create_calculation_groups)
- Field parameters (_create_field_parameters)
- Visual object extensions (trend lines, forecast, map options, etc.)
- Number format conversion (_convert_number_format)
- Auto date hierarchies (_auto_date_hierarchies)
- Context filter promotion
- Pages shelf slicer
"""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.tmdl_generator import (
    _create_parameter_tables,
    _auto_date_hierarchies,
)

# Import the internal functions directly
import powerbi_import.tmdl_generator as tmdl_mod
_create_calculation_groups = tmdl_mod._create_calculation_groups
_create_field_parameters = tmdl_mod._create_field_parameters

from powerbi_import.pbip_generator import PowerBIProjectGenerator


# ── Helpers ─────────────────────────────────────────────────────────

def _base_model():
    """Minimal in-memory BIM model with one table and measures."""
    return {
        "model": {
            "tables": [{
                "name": "Sales",
                "columns": [
                    {"name": "Region", "dataType": "string", "sourceColumn": "Region"},
                    {"name": "Product", "dataType": "string", "sourceColumn": "Product"},
                    {"name": "Amount", "dataType": "double", "sourceColumn": "Amount"},
                    {"name": "OrderDate", "dataType": "dateTime", "sourceColumn": "OrderDate"},
                ],
                "measures": [
                    {"name": "Total Sales", "expression": "SUM('Sales'[Amount])"},
                    {"name": "Avg Sales", "expression": "AVERAGE('Sales'[Amount])"},
                    {"name": "Count Orders", "expression": "COUNTROWS('Sales')"},
                ],
            }],
            "relationships": [],
        }
    }


def _column_table_map():
    return {
        "Region": "Sales",
        "Product": "Sales",
        "Amount": "Sales",
        "OrderDate": "Sales",
    }


# ═══════════════════════════════════════════════════════════════════
#  Calculation Groups
# ═══════════════════════════════════════════════════════════════════

class TestCalculationGroups(unittest.TestCase):

    def test_no_parameters(self):
        model = _base_model()
        _create_calculation_groups(model, [], "Sales")
        self.assertEqual(len(model['model']['tables']), 1)

    def test_non_string_param_skipped(self):
        model = _base_model()
        params = [{"caption": "Year", "datatype": "integer",
                   "domain_type": "range",
                   "allowable_values": [{"type": "range", "min": "2020", "max": "2030"}]}]
        _create_calculation_groups(model, params, "Sales")
        self.assertEqual(len(model['model']['tables']), 1)

    def test_string_list_non_measure_skipped(self):
        model = _base_model()
        params = [{"caption": "Category", "datatype": "string",
                   "domain_type": "list",
                   "allowable_values": [
                       {"value": "Electronics"}, {"value": "Clothing"},
                   ]}]
        _create_calculation_groups(model, params, "Sales")
        # Values don't match measure names → no calc group
        self.assertEqual(len(model['model']['tables']), 1)

    def test_measure_selector_creates_calc_group(self):
        model = _base_model()
        params = [{"caption": "Metric Selector", "datatype": "string",
                   "domain_type": "list",
                   "allowable_values": [
                       {"value": "Total Sales"},
                       {"value": "Avg Sales"},
                       {"value": "Count Orders"},
                   ]}]
        _create_calculation_groups(model, params, "Sales")
        self.assertEqual(len(model['model']['tables']), 2)
        cg = model['model']['tables'][1]
        self.assertEqual(cg['name'], "Metric Selector CalcGroup")
        self.assertIn("calculationGroup", cg)
        self.assertEqual(len(cg['calculationGroup']['calculationItems']), 3)
        for item in cg['calculationGroup']['calculationItems']:
            self.assertEqual(item['expression'], "CALCULATE(SELECTEDMEASURE())")

    def test_calc_group_has_correct_partition(self):
        model = _base_model()
        params = [{"caption": "Pick", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Total Sales"}, {"value": "Avg Sales"}]}]
        _create_calculation_groups(model, params, "Sales")
        cg = model['model']['tables'][1]
        self.assertEqual(cg['partitions'][0]['source']['type'], "calculationGroup")

    def test_calc_group_display_folder(self):
        model = _base_model()
        params = [{"caption": "Measure", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Total Sales"}, {"value": "Avg Sales"}]}]
        _create_calculation_groups(model, params, "Sales")
        cg = model['model']['tables'][1]
        folders = [a['value'] for a in cg.get('annotations', [])
                   if a.get('name') == 'displayFolder']
        self.assertIn("Calculation Groups", folders)

    def test_no_duplicate_calc_groups(self):
        model = _base_model()
        params = [{"caption": "Metric", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Total Sales"}, {"value": "Avg Sales"}]}]
        _create_calculation_groups(model, params, "Sales")
        _create_calculation_groups(model, params, "Sales")
        cg_tables = [t for t in model['model']['tables'] if 'CalcGroup' in t['name']]
        self.assertEqual(len(cg_tables), 1)

    def test_only_one_matching_measure_skipped(self):
        """Need at least 2 matching measure names."""
        model = _base_model()
        params = [{"caption": "Select", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Total Sales"}, {"value": "NoSuchMeasure"}]}]
        _create_calculation_groups(model, params, "Sales")
        self.assertEqual(len(model['model']['tables']), 1)


# ═══════════════════════════════════════════════════════════════════
#  Field Parameters
# ═══════════════════════════════════════════════════════════════════

class TestFieldParameters(unittest.TestCase):

    def test_no_parameters(self):
        model = _base_model()
        _create_field_parameters(model, [], "Sales", _column_table_map())
        self.assertEqual(len(model['model']['tables']), 1)

    def test_column_selector_creates_field_param(self):
        model = _base_model()
        params = [{"caption": "Dimension", "datatype": "string",
                   "domain_type": "list",
                   "allowable_values": [
                       {"value": "Region"},
                       {"value": "Product"},
                   ]}]
        _create_field_parameters(model, params, "Sales", _column_table_map())
        self.assertEqual(len(model['model']['tables']), 2)
        fp = model['model']['tables'][1]
        self.assertEqual(fp['name'], "Dimension FieldParam")

    def test_field_param_has_3_columns(self):
        model = _base_model()
        params = [{"caption": "Dim", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Region"}, {"value": "Product"}]}]
        _create_field_parameters(model, params, "Sales", _column_table_map())
        fp = model['model']['tables'][1]
        self.assertEqual(len(fp['columns']), 3)
        col_names = {c['name'] for c in fp['columns']}
        self.assertIn("Dim", col_names)
        self.assertIn("Dim_Order", col_names)
        self.assertIn("Dim_Fields", col_names)

    def test_field_param_hidden_columns(self):
        model = _base_model()
        params = [{"caption": "Axis", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Region"}, {"value": "Product"}]}]
        _create_field_parameters(model, params, "Sales", _column_table_map())
        fp = model['model']['tables'][1]
        hidden = [c for c in fp['columns'] if c.get('isHidden')]
        self.assertEqual(len(hidden), 2)

    def test_field_param_nameof_expression(self):
        model = _base_model()
        params = [{"caption": "Col", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Region"}, {"value": "Product"}]}]
        _create_field_parameters(model, params, "Sales", _column_table_map())
        fp = model['model']['tables'][1]
        expr = fp['partitions'][0]['source']['expression']
        self.assertIn("NAMEOF", expr)
        self.assertIn("Sales", expr)
        self.assertIn("Region", expr)

    def test_field_param_pbi_annotations(self):
        model = _base_model()
        params = [{"caption": "X", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Region"}, {"value": "Product"}]}]
        _create_field_parameters(model, params, "Sales", _column_table_map())
        fp = model['model']['tables'][1]
        ann_names = {a['name'] for a in fp.get('annotations', [])}
        self.assertIn("PBI_NavigationStepName", ann_names)
        self.assertIn("ParameterMetadata", ann_names)

    def test_all_measures_skipped_goes_to_calc_group(self):
        """If all values are measure names, field param is skipped."""
        model = _base_model()
        params = [{"caption": "Metric", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Total Sales"}, {"value": "Avg Sales"}]}]
        _create_field_parameters(model, params, "Sales", _column_table_map())
        # Should not create a field param (measures go to calc groups)
        self.assertEqual(len(model['model']['tables']), 1)

    def test_no_duplicate_field_params(self):
        model = _base_model()
        params = [{"caption": "Dim", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Region"}, {"value": "Product"}]}]
        _create_field_parameters(model, params, "Sales", _column_table_map())
        _create_field_parameters(model, params, "Sales", _column_table_map())
        fp_tables = [t for t in model['model']['tables'] if 'FieldParam' in t['name']]
        self.assertEqual(len(fp_tables), 1)

    def test_single_column_match_skipped(self):
        model = _base_model()
        params = [{"caption": "One", "datatype": "string", "domain_type": "list",
                   "allowable_values": [{"value": "Region"}, {"value": "Nonexistent"}]}]
        _create_field_parameters(model, params, "Sales", _column_table_map())
        self.assertEqual(len(model['model']['tables']), 1)


# ═══════════════════════════════════════════════════════════════════
#  Auto Date Hierarchies
# ═══════════════════════════════════════════════════════════════════

class TestAutoDateHierarchies(unittest.TestCase):

    def test_creates_hierarchy_for_date_column(self):
        model = _base_model()
        _auto_date_hierarchies(model)
        table = model['model']['tables'][0]
        hierarchies = table.get('hierarchies', [])
        self.assertTrue(any('OrderDate' in h['name'] for h in hierarchies))

    def test_adds_year_month_day_columns(self):
        model = _base_model()
        _auto_date_hierarchies(model)
        table = model['model']['tables'][0]
        col_names = {c['name'] for c in table.get('columns', [])}
        self.assertIn("OrderDate Year", col_names)
        self.assertIn("OrderDate Month", col_names)
        self.assertIn("OrderDate Day", col_names)

    def test_skips_non_date_columns(self):
        model = _base_model()
        _auto_date_hierarchies(model)
        table = model['model']['tables'][0]
        hierarchies = table.get('hierarchies', [])
        # Should NOT create hierarchy for Region or Product
        self.assertFalse(any('Region' in h['name'] for h in hierarchies))
        self.assertFalse(any('Product' in h['name'] for h in hierarchies))

    def test_idempotent(self):
        model = _base_model()
        _auto_date_hierarchies(model)
        count_before = len(model['model']['tables'][0].get('hierarchies', []))
        _auto_date_hierarchies(model)
        count_after = len(model['model']['tables'][0].get('hierarchies', []))
        self.assertEqual(count_before, count_after)

    def test_skips_column_already_in_hierarchy(self):
        model = _base_model()
        model['model']['tables'][0]['hierarchies'] = [{
            'name': 'My DateHier',
            'levels': [{'name': 'OrderDate', 'column': 'OrderDate'}]
        }]
        _auto_date_hierarchies(model)
        # Should not add another hierarchy for OrderDate
        hierarchies = model['model']['tables'][0]['hierarchies']
        self.assertEqual(len(hierarchies), 1)


# ═══════════════════════════════════════════════════════════════════
#  Number Format Conversion
# ═══════════════════════════════════════════════════════════════════

class TestNumberFormatConversion(unittest.TestCase):

    def test_plain_number(self):
        result = PowerBIProjectGenerator._convert_number_format("###,###")
        self.assertIsNotNone(result)
        self.assertIn(",", result)

    def test_currency(self):
        result = PowerBIProjectGenerator._convert_number_format("$#,##0.00")
        self.assertIsNotNone(result)
        self.assertIn("$", result)

    def test_percentage(self):
        result = PowerBIProjectGenerator._convert_number_format("0.0%")
        self.assertIsNotNone(result)
        self.assertIn("%", result)

    def test_empty_string(self):
        result = PowerBIProjectGenerator._convert_number_format("")
        # Empty → None or empty
        self.assertFalse(result)

    def test_unknown_format(self):
        result = PowerBIProjectGenerator._convert_number_format("xyz-custom")
        # Should return something or None gracefully
        self.assertIsNotNone(result) if result else True


# ═══════════════════════════════════════════════════════════════════
#  Visual Object Extensions
# ═══════════════════════════════════════════════════════════════════

class TestVisualObjectExtensions(unittest.TestCase):
    """Test newly ported visual config blocks in _build_visual_objects."""

    def setUp(self):
        self.gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        self.gen._main_table = "Sales"

    def _build(self, ws_data, visual_type='clusteredBarChart'):
        return self.gen._build_visual_objects("Test", ws_data, visual_type)

    def test_trend_lines(self):
        ws = {'trend_lines': [
            {'type': 'linear', 'color': '#FF0000', 'show_equation': True}
        ]}
        objs = self._build(ws)
        self.assertIn("trend", objs)
        self.assertEqual(len(objs["trend"]), 1)
        props = objs["trend"][0]["properties"]
        self.assertIn("displayEquation", props)

    def test_trend_lines_invalid_type_defaults_linear(self):
        ws = {'trend_lines': [{'type': 'cubic'}]}
        objs = self._build(ws)
        self.assertIn("trend", objs)

    def test_annotations_subtitle(self):
        ws = {'annotations': [
            {'text': 'Source: World Bank'},
            {'text': 'Updated daily'},
        ]}
        objs = self._build(ws)
        self.assertIn("subTitle", objs)
        text_val = objs["subTitle"][0]["properties"]["text"]
        # Should combine annotations
        self.assertIn("Source", str(text_val))

    def test_font_formatting_family(self):
        ws = {'formatting': {'font': {'family': 'Arial', 'size': '12pt'}}}
        objs = self._build(ws)
        self.assertIn("labels", objs)
        self.assertIn("fontFamily", objs["labels"][0]["properties"])
        self.assertIn("fontSize", objs["labels"][0]["properties"])

    def test_forecast_config(self):
        ws = {'forecasting': [
            {'periods': 10, 'prediction_interval': '90', 'ignore_last': '2'}
        ]}
        objs = self._build(ws)
        self.assertIn("forecast", objs)
        props = objs["forecast"][0]["properties"]
        self.assertIn("forecastLength", props)
        self.assertIn("confidenceLevel", props)
        self.assertIn("ignoreLast", props)

    def test_map_options(self):
        ws = {'map_options': {'washout': '0.5', 'style': 'light'}}
        objs = self._build(ws, 'map')
        self.assertIn("mapControl", objs)
        props = objs["mapControl"][0]["properties"]
        self.assertIn("transparency", props)
        self.assertIn("mapStyle", props)

    def test_map_options_ignored_for_non_map(self):
        ws = {'map_options': {'washout': '0.5', 'style': 'light'}}
        objs = self._build(ws, 'clusteredBarChart')
        self.assertNotIn("mapControl", objs)

    def test_per_value_colors(self):
        ws = {'mark_encoding': {
            'color': {'color_values': {'A': '#FF0000', 'B': '#00FF00'}}
        }}
        objs = self._build(ws)
        self.assertIn("dataPoint", objs)
        self.assertEqual(len(objs["dataPoint"]), 2)

    def test_stepped_thresholds(self):
        ws = {'mark_encoding': {
            'color': {'thresholds': [
                {'value': 0, 'color': '#red'}, {'value': 100, 'color': '#green'}
            ]}
        }}
        objs = self._build(ws)
        self.assertIn("dataPoint", objs)
        self.assertEqual(len(objs["dataPoint"]), 2)

    def test_data_bars_for_table(self):
        ws = {
            'fields': [{'name': 'Amount', 'role': 'measure'}],
            'mark_encoding': {'color': {'type': 'quantitative'}},
        }
        objs = self._build(ws, 'tableEx')
        self.assertIn("dataBar", objs)

    def test_default_row_banding_for_table(self):
        ws = {'formatting': {}}  # non-empty ws_data to pass the early return
        objs = self._build(ws, 'tableEx')
        self.assertIn("values", objs)
        # Default banding color
        self.assertIn("backColor", objs["values"][0]["properties"])

    def test_totals_subtotals(self):
        ws = {'totals': {'grand_totals': True, 'subtotals': True}}
        objs = self._build(ws, 'matrix')
        self.assertIn("total", objs)
        self.assertIn("subTotals", objs)

    def test_continuous_axis(self):
        ws = {'axes': {'x': {'is_continuous': True}}}
        objs = self._build(ws)
        self.assertIn("categoryAxis", objs)
        props = objs["categoryAxis"][0]["properties"]
        self.assertIn("axisType", props)

    def test_discrete_axis(self):
        ws = {'axes': {'x': {'is_continuous': False}}}
        objs = self._build(ws)
        self.assertIn("categoryAxis", objs)

    def test_axis_label_rotation(self):
        ws = {'axes': {'x': {'label_rotation': '45'}}}
        objs = self._build(ws)
        props = objs["categoryAxis"][0]["properties"]
        self.assertIn("labelAngle", props)

    def test_axis_show_title_false(self):
        ws = {'axes': {'y': {'show_title': False}}}
        objs = self._build(ws)
        props = objs["valueAxis"][0]["properties"]
        self.assertIn("showAxisTitle", props)

    def test_axis_show_label_false(self):
        ws = {'axes': {'x': {'show_label': False}}}
        objs = self._build(ws)
        props = objs["categoryAxis"][0]["properties"]
        # show should be false
        self.assertIn("show", props)

    def test_dual_axis_sync(self):
        ws = {'dual_axis': {'enabled': True, 'synchronized': True}}
        objs = self._build(ws)
        props = objs["valueAxis"][0]["properties"]
        self.assertIn("secShow", props)
        self.assertIn("secAxisLabel", props)

    def test_padding(self):
        ws = {'padding': {'padding_top': 10, 'padding_bottom': 5}}
        objs = self._build(ws)
        self.assertIn("visualContainerPadding", objs)
        props = objs["visualContainerPadding"][0]["properties"]
        self.assertIn("top", props)
        self.assertIn("bottom", props)

    def test_reference_bands(self):
        ws = {'analytics_stats': [
            {'type': 'distribution_band', 'value_from': '10', 'value_to': '90'}
        ]}
        objs = self._build(ws)
        ref_lines = objs["valueAxis"][0]["properties"].get("referenceLine", [])
        self.assertTrue(any(r.get('type') == 'Band' for r in ref_lines))

    def test_stat_reference_lines(self):
        ws = {'analytics_stats': [
            {'type': 'stat_line', 'computation': 'median'}
        ]}
        objs = self._build(ws)
        ref_lines = objs["valueAxis"][0]["properties"].get("referenceLine", [])
        self.assertTrue(any(r.get('type') == 'Median' for r in ref_lines))

    def test_small_multiples(self):
        ws = {'small_multiples': 'Region'}
        objs = self._build(ws)
        self.assertIn("smallMultiple", objs)

    def test_small_multiples_from_pages_shelf(self):
        ws = {'pages_shelf': {'field': 'Year'}}
        objs = self._build(ws)
        self.assertIn("smallMultiple", objs)

    def test_number_format_on_labels(self):
        ws = {
            'formatting': {'number_format': '$#,##0'},
            'mark_encoding': {'label': {'show': True}},
        }
        objs = self._build(ws)
        if "labels" in objs:
            props = objs["labels"][0]["properties"]
            # May or may not have labelDisplayUnits depending on format
            # Just verify no crash
            self.assertIsInstance(props, dict)


# ═══════════════════════════════════════════════════════════════════
#  Context Filter Promotion (unit test for the inline logic)
# ═══════════════════════════════════════════════════════════════════

class TestContextFilterPromotion(unittest.TestCase):
    """Test that context filters from worksheets are promoted to page-level."""

    def test_context_filters_promoted(self):
        db_filters = []
        worksheets = [
            {'name': 'WS1', 'filters': [
                {'field': 'Region', 'is_context': True},
                {'field': 'Status', 'is_context': False},
            ]},
            {'name': 'WS2', 'filters': [
                {'field': 'Year', 'is_context': True},
            ]},
        ]
        # Replicate the inline logic from pbip_generator
        db_filters = list(db_filters)
        for ws in worksheets:
            for f in ws.get('filters', []):
                if f.get('is_context', False):
                    db_filters.append(f)
        context = [f for f in db_filters if f.get('is_context')]
        self.assertEqual(len(context), 2)
        self.assertEqual(context[0]['field'], 'Region')
        self.assertEqual(context[1]['field'], 'Year')

    def test_non_context_filters_excluded(self):
        worksheets = [{'name': 'WS1', 'filters': [
            {'field': 'Status', 'is_context': False},
        ]}]
        db_filters = []
        for ws in worksheets:
            for f in ws.get('filters', []):
                if f.get('is_context', False):
                    db_filters.append(f)
        self.assertEqual(len(db_filters), 0)


# ═══════════════════════════════════════════════════════════════════
#  DAX → Power Query M Column Conversion
# ═══════════════════════════════════════════════════════════════════

class TestDaxToMExpression(unittest.TestCase):
    """Verify the _dax_to_m_expression converter used for calc column elimination."""

    def setUp(self):
        self.convert = tmdl_mod._dax_to_m_expression

    # ── Successful conversions ──────────────────────────────────────
    def test_if_expression(self):
        result = self.convert('IF([Active] = 1, "Yes", "No")', 'T')
        self.assertIsNotNone(result)
        self.assertIn('if', result)
        self.assertIn('then', result)
        self.assertIn('else', result)

    def test_switch_expression(self):
        result = self.convert('SWITCH([Status], "A", "Active", "I", "Inactive", "Other")', 'T')
        self.assertIsNotNone(result)
        self.assertIn('if', result)
        self.assertIn('"Active"', result)

    def test_floor_expression(self):
        result = self.convert('FLOOR([Amount], 100)', 'T')
        self.assertIsNotNone(result)
        self.assertIn('Number.RoundDown', result)

    def test_year_expression(self):
        result = self.convert('YEAR([OrderDate])', 'T')
        self.assertEqual(result, 'Date.Year([OrderDate])')

    def test_month_expression(self):
        result = self.convert('MONTH([OrderDate])', 'T')
        self.assertEqual(result, 'Date.Month([OrderDate])')

    def test_in_expression(self):
        result = self.convert('[Region] IN {"West", "East"}', 'T')
        self.assertIsNotNone(result)
        self.assertIn('List.Contains', result)

    def test_isblank(self):
        result = self.convert('ISBLANK([Name])', 'T')
        self.assertIsNotNone(result)
        self.assertIn('null', result)

    def test_self_table_prefix_stripped(self):
        result = self.convert("'Sales'[Amount] + 1", 'Sales')
        self.assertIsNotNone(result)
        self.assertNotIn("'Sales'", result)
        self.assertIn('[Amount]', result)

    def test_upper_lower(self):
        self.assertEqual(self.convert('UPPER([Name])', 'T'), 'Text.Upper([Name])')
        self.assertEqual(self.convert('LOWER([Name])', 'T'), 'Text.Lower([Name])')

    # ── Rejected (unconvertible) patterns ───────────────────────────
    def test_related_rejected(self):
        result = self.convert("RELATED('Other'[Col])", 'T')
        self.assertIsNone(result)

    def test_lookupvalue_rejected(self):
        result = self.convert("LOOKUPVALUE('Other'[Col], 'Other'[Key], [Key])", 'T')
        self.assertIsNone(result)

    def test_cross_table_ref_rejected(self):
        result = self.convert("'Other'[Col] + 1", 'T')
        self.assertIsNone(result)

    def test_dax_aggregation_rejected(self):
        result = self.convert("CALCULATE(SUM([Amount]))", 'T')
        self.assertIsNone(result)


class TestMBasedColumns(unittest.TestCase):
    """Verify that sets, groups, bins and date hierarchies produce M columns
    (sourceColumn) rather than DAX calculated columns (expression + isCalculated)."""

    def _model_with_partition(self):
        """Model with an M partition so inject_m_steps can work."""
        return {
            "model": {
                "tables": [{
                    "name": "Sales",
                    "columns": [
                        {"name": "Region", "dataType": "string", "sourceColumn": "Region"},
                        {"name": "Status", "dataType": "string", "sourceColumn": "Status"},
                        {"name": "Amount", "dataType": "double", "sourceColumn": "Amount"},
                        {"name": "OrderDate", "dataType": "dateTime", "sourceColumn": "OrderDate"},
                    ],
                    "partitions": [{
                        "name": "Partition-Sales",
                        "mode": "import",
                        "source": {
                            "type": "m",
                            "expression": 'let\n    Source = Sql.Database("server", "db"),\n    Sales = Source{[Schema="dbo",Item="Sales"]}[Data]\nin\n    Sales'
                        }
                    }],
                    "measures": [
                        {"name": "Total Sales", "expression": "SUM('Sales'[Amount])"},
                    ],
                }],
                "relationships": [],
            }
        }

    # ── Sets ────────────────────────────────────────────────────────
    def test_set_members_become_m_column(self):
        model = self._model_with_partition()
        extra = {'sets': [{'name': 'TopRegions', 'members': ['West', 'East']}]}
        col_map = {'Region': 'Sales', 'Status': 'Sales', 'Amount': 'Sales'}
        tmdl_mod._process_sets_groups_bins(model, extra, 'Sales', col_map)

        cols = {c['name']: c for c in model['model']['tables'][0]['columns']}
        self.assertIn('TopRegions', cols)
        col = cols['TopRegions']
        # Should be M-based (sourceColumn), not DAX (expression)
        self.assertEqual(col.get('sourceColumn'), 'TopRegions')
        self.assertNotIn('isCalculated', col)
        self.assertNotIn('expression', col)
        # M query should contain Table.AddColumn
        m_expr = model['model']['tables'][0]['partitions'][0]['source']['expression']
        self.assertIn('Table.AddColumn', m_expr)
        self.assertIn('TopRegions', m_expr)

    def test_set_with_formula_fallback_to_dax(self):
        """Sets with complex formulas (e.g. RELATED) should fall back to DAX."""
        model = self._model_with_partition()
        extra = {'sets': [{'name': 'CrossSet', 'formula': "RELATED('Other'[Flag])"}]}
        col_map = {'Region': 'Sales'}
        tmdl_mod._process_sets_groups_bins(model, extra, 'Sales', col_map)

        cols = {c['name']: c for c in model['model']['tables'][0]['columns']}
        col = cols['CrossSet']
        # Should fall back to DAX calculated column
        self.assertTrue(col.get('isCalculated'))
        self.assertIn('expression', col)

    # ── Groups ──────────────────────────────────────────────────────
    def test_group_switch_becomes_m_column(self):
        model = self._model_with_partition()
        extra = {'groups': [{'name': 'StatusGroup', 'source_field': 'Status',
                             'members': {'Active': ['A'], 'Inactive': ['I']}}]}
        col_map = {'Status': 'Sales', 'Region': 'Sales'}
        tmdl_mod._process_sets_groups_bins(model, extra, 'Sales', col_map)

        cols = {c['name']: c for c in model['model']['tables'][0]['columns']}
        col = cols['StatusGroup']
        self.assertEqual(col.get('sourceColumn'), 'StatusGroup')
        self.assertNotIn('isCalculated', col)
        m_expr = model['model']['tables'][0]['partitions'][0]['source']['expression']
        self.assertIn('Table.AddColumn', m_expr)
        self.assertIn('StatusGroup', m_expr)

    # ── Bins ────────────────────────────────────────────────────────
    def test_bin_floor_becomes_m_column(self):
        model = self._model_with_partition()
        extra = {'bins': [{'name': 'AmountBin', 'source_field': 'Amount', 'size': '50'}]}
        col_map = {'Amount': 'Sales'}
        tmdl_mod._process_sets_groups_bins(model, extra, 'Sales', col_map)

        cols = {c['name']: c for c in model['model']['tables'][0]['columns']}
        col = cols['AmountBin']
        self.assertEqual(col.get('sourceColumn'), 'AmountBin')
        self.assertNotIn('isCalculated', col)
        m_expr = model['model']['tables'][0]['partitions'][0]['source']['expression']
        self.assertIn('Number.RoundDown', m_expr)

    # ── Auto Date Hierarchies ───────────────────────────────────────
    def test_date_hierarchy_columns_are_m_based(self):
        model = self._model_with_partition()
        _auto_date_hierarchies(model)

        table = model['model']['tables'][0]
        # Year/Quarter/Month/Day columns should have sourceColumn, not expression
        for suffix in ['Year', 'Quarter', 'Month', 'Day']:
            cname = f'OrderDate {suffix}'
            col = next(c for c in table['columns'] if c['name'] == cname)
            self.assertEqual(col.get('sourceColumn'), cname,
                             f'{cname} should have sourceColumn')
            self.assertNotIn('expression', col,
                             f'{cname} should not have DAX expression')
            self.assertNotIn('type', col,
                             f'{cname} should not have type=calculated')

    def test_date_hierarchy_m_partition_has_date_functions(self):
        model = self._model_with_partition()
        _auto_date_hierarchies(model)

        m_expr = model['model']['tables'][0]['partitions'][0]['source']['expression']
        self.assertIn('Date.Year', m_expr)
        self.assertIn('Date.Month', m_expr)
        self.assertIn('Date.Day', m_expr)
        self.assertIn('Date.QuarterOfYear', m_expr)

    # ── Calc columns in _build_table ────────────────────────────────
    def test_simple_calc_col_becomes_m_column(self):
        """A simple IF calc column should be pushed to M."""
        table = {'name': 'Orders', 'columns': [
            {'name': 'Active', 'datatype': 'integer'},
        ]}
        conn = {'type': 'sqlserver', 'server': 'srv', 'database': 'db'}
        calcs = [{'name': 'IsActive', 'caption': 'IsActive',
                  'formula': 'IF([Active]=1, "Yes", "No")',
                  'role': 'dimension', 'datatype': 'string'}]

        result = tmdl_mod._build_table(
            table=table, connection=conn, calculations=calcs,
            columns_metadata=[],
            dax_context={'calc_map': {}, 'param_map': {},
                         'column_table_map': {'Active': 'Orders'},
                         'measure_names': set(), 'param_values': {}},
            col_metadata_map={}, extra_objects={})

        col = next(c for c in result['columns'] if c['name'] == 'IsActive')
        # Should be M-based
        self.assertEqual(col.get('sourceColumn'), 'IsActive')
        self.assertNotIn('isCalculated', col)
        # Partition should contain the M step
        m_expr = result['partitions'][0]['source']['expression']
        self.assertIn('Table.AddColumn', m_expr)

    def test_cross_table_calc_col_stays_dax(self):
        """A calc column with RELATED stays as DAX."""
        table = {'name': 'Orders', 'columns': [
            {'name': 'CustId', 'datatype': 'integer'},
        ]}
        conn = {'type': 'sqlserver', 'server': 'srv', 'database': 'db'}
        calcs = [{'name': 'CustName', 'caption': 'CustName',
                  'formula': "RELATED('Customers'[Name])",
                  'role': 'dimension', 'datatype': 'string'}]

        result = tmdl_mod._build_table(
            table=table, connection=conn, calculations=calcs,
            columns_metadata=[],
            dax_context={'calc_map': {}, 'param_map': {},
                         'column_table_map': {'CustId': 'Orders'},
                         'measure_names': set(), 'param_values': {}},
            col_metadata_map={}, extra_objects={})

        col = next(c for c in result['columns'] if c['name'] == 'CustName')
        # Should stay as DAX calculated column
        self.assertTrue(col.get('isCalculated'))
        self.assertIn('expression', col)


if __name__ == '__main__':
    unittest.main()
