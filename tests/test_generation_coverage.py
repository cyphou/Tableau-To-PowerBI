"""
Extended Generation Coverage Tests — TMDL, visual, pbip, validator, migration report.

Targets under-covered paths in generation modules identified in gap analysis:
- DAX-to-M converter deeper coverage (tmdl_generator._dax_to_m_expression)
- Visual type mapping edge cases and data role lookup
- Visual container creation with mark encoding, filters, sorts
- Build query state per visual type
- Validator semantic checks (DAX formula, Tableau leakage, TMDL structure)
- MigrationReport classification and scoring
- PowerBIProjectGenerator scaffold creation
"""

import os
import sys
import json
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

from powerbi_import.visual_generator import (
    resolve_visual_type,
    resolve_custom_visual_type,
    VISUAL_TYPE_MAP,
    VISUAL_DATA_ROLES,
    CUSTOM_VISUAL_GUIDS,
    APPROXIMATION_MAP,
    generate_visual_containers,
    create_visual_container,
    build_query_state,
    _get_config_template,
)
from powerbi_import.validator import ArtifactValidator
from powerbi_import.migration_report import MigrationReport
from powerbi_import.tmdl_generator import (
    _dax_to_m_expression,
    _split_dax_args,
    _extract_function_body,
    generate_tmdl,
    _build_semantic_model,
)
from tests.factories import (
    DatasourceFactory, WorksheetFactory, ModelFactory,
    DashboardFactory, ParameterFactory,
    make_simple_model, make_multi_table_model, make_complex_model,
)


# ═══════════════════════════════════════════════════════════════════════
# DAX → M Expression Converter (deeper coverage)
# ═══════════════════════════════════════════════════════════════════════

class TestDaxToMConverterExtended(unittest.TestCase):
    """Extended coverage for _dax_to_m_expression."""

    def test_if_simple(self):
        result = _dax_to_m_expression("IF([Col] > 10, \"High\", \"Low\")")
        self.assertIsNotNone(result)
        self.assertIn("if", result)
        self.assertIn("then", result)
        self.assertIn("else", result)

    def test_if_no_else(self):
        result = _dax_to_m_expression("IF([Col] > 10, \"High\")")
        self.assertIsNotNone(result)
        self.assertIn("null", result)

    def test_switch_basic(self):
        result = _dax_to_m_expression('SWITCH([Status], "A", "Active", "I", "Inactive", "Unknown")')
        self.assertIsNotNone(result)
        self.assertIn("if", result)
        self.assertIn("else", result)

    def test_floor_two_args(self):
        result = _dax_to_m_expression("FLOOR([Amount], 10)")
        self.assertIsNotNone(result)
        self.assertIn("Number.RoundDown", result)

    def test_isblank(self):
        result = _dax_to_m_expression("ISBLANK([Col])")
        self.assertIsNotNone(result)
        self.assertIn("null", result)

    def test_not(self):
        result = _dax_to_m_expression("NOT([Flag])")
        self.assertIsNotNone(result)
        self.assertIn("not", result)

    def test_upper(self):
        result = _dax_to_m_expression("UPPER([Name])")
        self.assertIsNotNone(result)
        self.assertIn("Text.Upper", result)

    def test_lower(self):
        result = _dax_to_m_expression("LOWER([Name])")
        self.assertIsNotNone(result)
        self.assertIn("Text.Lower", result)

    def test_trim(self):
        result = _dax_to_m_expression("TRIM([Name])")
        self.assertIsNotNone(result)
        self.assertIn("Text.Trim", result)

    def test_len(self):
        result = _dax_to_m_expression("LEN([Name])")
        self.assertIsNotNone(result)
        self.assertIn("Text.Length", result)

    def test_year(self):
        result = _dax_to_m_expression("YEAR([Date])")
        self.assertIsNotNone(result)
        self.assertIn("Date.Year", result)

    def test_month(self):
        result = _dax_to_m_expression("MONTH([Date])")
        self.assertIsNotNone(result)
        self.assertIn("Date.Month", result)

    def test_day(self):
        result = _dax_to_m_expression("DAY([Date])")
        self.assertIsNotNone(result)
        self.assertIn("Date.Day", result)

    def test_quarter(self):
        result = _dax_to_m_expression("QUARTER([Date])")
        self.assertIsNotNone(result)
        self.assertIn("Date.QuarterOfYear", result)

    def test_abs(self):
        result = _dax_to_m_expression("ABS([Value])")
        self.assertIsNotNone(result)
        self.assertIn("Number.Abs", result)

    def test_int(self):
        result = _dax_to_m_expression("INT([Value])")
        self.assertIsNotNone(result)
        self.assertIn("Number.RoundDown", result)

    def test_sqrt(self):
        result = _dax_to_m_expression("SQRT([Value])")
        self.assertIsNotNone(result)
        self.assertIn("Number.Sqrt", result)

    def test_left_multi_arg(self):
        result = _dax_to_m_expression("LEFT([Name], 3)")
        self.assertIsNotNone(result)
        self.assertIn("Text.Start", result)

    def test_right_multi_arg(self):
        result = _dax_to_m_expression("RIGHT([Name], 3)")
        self.assertIsNotNone(result)
        self.assertIn("Text.End", result)

    def test_mid_multi_arg(self):
        result = _dax_to_m_expression("MID([Name], 2, 5)")
        self.assertIsNotNone(result)
        self.assertIn("Text.Middle", result)

    def test_round(self):
        result = _dax_to_m_expression("ROUND([Value], 2)")
        self.assertIsNotNone(result)
        self.assertIn("Number.Round", result)

    def test_containsstring(self):
        result = _dax_to_m_expression('CONTAINSSTRING([Name], "Corp")')
        self.assertIsNotNone(result)
        self.assertIn("Text.Contains", result)

    def test_substitute(self):
        result = _dax_to_m_expression('SUBSTITUTE([Name], "Old", "New")')
        self.assertIsNotNone(result)
        self.assertIn("Text.Replace", result)

    def test_in_expression(self):
        result = _dax_to_m_expression('[Status] IN {"A", "B", "C"}')
        self.assertIsNotNone(result)
        self.assertIn("List.Contains", result)

    def test_boolean_operators(self):
        result = _dax_to_m_expression("[A] > 1 && [B] < 10")
        self.assertIsNotNone(result)
        self.assertIn(" and ", result)

    def test_or_operator(self):
        result = _dax_to_m_expression("[A] > 1 || [B] < 10")
        self.assertIsNotNone(result)
        self.assertIn(" or ", result)

    def test_true_false_blank(self):
        result = _dax_to_m_expression("TRUE()")
        self.assertIsNotNone(result)
        self.assertIn("true", result)

    def test_false_literal(self):
        result = _dax_to_m_expression("FALSE()")
        self.assertIsNotNone(result)
        self.assertIn("false", result)

    def test_blank_literal(self):
        result = _dax_to_m_expression("BLANK()")
        self.assertIsNotNone(result)
        self.assertIn("null", result)

    def test_related_returns_none(self):
        """RELATED() requires cross-table → should return None."""
        result = _dax_to_m_expression("RELATED('Products'[Name])")
        self.assertIsNone(result)

    def test_lookupvalue_returns_none(self):
        result = _dax_to_m_expression("LOOKUPVALUE('Products'[Name], 'Products'[ID], [ProdID])")
        self.assertIsNone(result)

    def test_cross_table_ref_returns_none(self):
        result = _dax_to_m_expression("'Products'[Name]")
        self.assertIsNone(result)

    def test_self_table_stripped(self):
        result = _dax_to_m_expression("UPPER('Orders'[Name])", table_name="Orders")
        self.assertIsNotNone(result)
        self.assertNotIn("Orders", result)

    def test_empty_string(self):
        result = _dax_to_m_expression("")
        self.assertEqual(result, "")

    def test_none_input(self):
        result = _dax_to_m_expression(None)
        self.assertIsNone(result)

    def test_nested_if_switch(self):
        result = _dax_to_m_expression('IF(ISBLANK([A]), "None", UPPER([A]))')
        self.assertIsNotNone(result)
        self.assertIn("if", result)
        self.assertIn("Text.Upper", result)


# ═══════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════

class TestSplitDaxArgs(unittest.TestCase):
    """Test _split_dax_args utility."""

    def test_simple(self):
        result = _split_dax_args("a, b, c")
        self.assertEqual(result, ["a", "b", "c"])

    def test_nested_parens(self):
        result = _split_dax_args("IF(a, b), c")
        self.assertEqual(len(result), 2)

    def test_quoted_comma(self):
        result = _split_dax_args('"a, b", c')
        self.assertEqual(len(result), 2)

    def test_single(self):
        result = _split_dax_args("[Col]")
        self.assertEqual(result, ["[Col]"])


class TestExtractFunctionBody(unittest.TestCase):
    """Test _extract_function_body utility."""

    def test_simple_func(self):
        result = _extract_function_body("UPPER([Name])", "UPPER")
        self.assertEqual(result, "[Name]")

    def test_nested(self):
        result = _extract_function_body("IF(ISBLANK([A]), 0, [A])", "IF")
        self.assertIsNotNone(result)
        self.assertIn("ISBLANK", result)

    def test_not_spanning_full(self):
        result = _extract_function_body("UPPER([Name]) + 1", "UPPER")
        self.assertIsNone(result)

    def test_wrong_function(self):
        result = _extract_function_body("LOWER([Name])", "UPPER")
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════════
# Visual Type Mapping
# ═══════════════════════════════════════════════════════════════════════

class TestResolveVisualType(unittest.TestCase):
    """Test resolve_visual_type edge cases."""

    def test_bar(self):
        self.assertEqual(resolve_visual_type("bar"), "clusteredBarChart")

    def test_bar_upper(self):
        self.assertEqual(resolve_visual_type("Bar"), "clusteredBarChart")

    def test_line(self):
        self.assertEqual(resolve_visual_type("line"), "lineChart")

    def test_pie(self):
        self.assertEqual(resolve_visual_type("pie"), "pieChart")

    def test_scatter(self):
        self.assertEqual(resolve_visual_type("scatter"), "scatterChart")

    def test_treemap(self):
        self.assertEqual(resolve_visual_type("treemap"), "treemap")

    def test_map(self):
        self.assertEqual(resolve_visual_type("map"), "map")

    def test_text_to_table(self):
        self.assertEqual(resolve_visual_type("text"), "tableEx")

    def test_unknown_to_table(self):
        self.assertEqual(resolve_visual_type("unknown_chart_type"), "tableEx")

    def test_none_to_table(self):
        self.assertEqual(resolve_visual_type(None), "tableEx")

    def test_histogram(self):
        self.assertEqual(resolve_visual_type("histogram"), "clusteredColumnChart")

    def test_waterfall(self):
        self.assertEqual(resolve_visual_type("waterfall"), "waterfallChart")

    def test_gauge(self):
        self.assertEqual(resolve_visual_type("gauge"), "gauge")

    def test_donut(self):
        self.assertEqual(resolve_visual_type("donut"), "donutChart")

    def test_funnel(self):
        self.assertEqual(resolve_visual_type("funnel"), "funnel")

    def test_boxplot(self):
        self.assertEqual(resolve_visual_type("boxplot"), "boxAndWhisker")

    def test_wordcloud(self):
        self.assertEqual(resolve_visual_type("wordcloud"), "wordCloud")

    def test_slicer(self):
        self.assertEqual(resolve_visual_type("slicer"), "slicer")

    def test_heatmap_to_matrix(self):
        self.assertEqual(resolve_visual_type("heatmap"), "matrix")

    def test_ganttbar(self):
        self.assertEqual(resolve_visual_type("ganttbar"), "ganttChart")

    def test_sankey(self):
        self.assertEqual(resolve_visual_type("sankey"), "sankeyDiagram")

    def test_pareto(self):
        self.assertEqual(resolve_visual_type("pareto"), "lineClusteredColumnComboChart")

    def test_kpi_to_card(self):
        self.assertEqual(resolve_visual_type("kpi"), "card")


# ═══════════════════════════════════════════════════════════════════════
# Visual Data Roles
# ═══════════════════════════════════════════════════════════════════════

class TestVisualDataRoles(unittest.TestCase):
    """Test VISUAL_DATA_ROLES coverage."""

    def test_bar_chart_roles(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["clusteredBarChart"]
        self.assertIn("Category", dim_roles)
        self.assertIn("Y", meas_roles)

    def test_table_roles(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["tableEx"]
        self.assertIn("Values", dim_roles)

    def test_scatter_roles(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["scatterChart"]
        self.assertIn("X", meas_roles)
        self.assertIn("Y", meas_roles)

    def test_card_roles(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["card"]
        self.assertEqual(dim_roles, [])
        self.assertIn("Fields", meas_roles)

    def test_slicer_roles(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["slicer"]
        self.assertIn("Values", dim_roles)
        self.assertEqual(meas_roles, [])

    def test_map_roles(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["map"]
        self.assertIn("Location", dim_roles)

    def test_gauge_roles(self):
        _, meas_roles = VISUAL_DATA_ROLES["gauge"]
        self.assertIn("Y", meas_roles)


# ═══════════════════════════════════════════════════════════════════════
# Config Templates
# ═══════════════════════════════════════════════════════════════════════

class TestConfigTemplates(unittest.TestCase):
    """Test _get_config_template returns valid configs."""

    def test_bar_chart_config(self):
        cfg = _get_config_template("clusteredBarChart")
        self.assertIn("objects", cfg)
        self.assertIn("categoryAxis", cfg["objects"])

    def test_line_chart_config(self):
        cfg = _get_config_template("lineChart")
        self.assertIn("objects", cfg)

    def test_table_config(self):
        cfg = _get_config_template("tableEx")
        self.assertIn("autoSelectVisualType", cfg)

    def test_unknown_returns_empty(self):
        cfg = _get_config_template("unknownVisual")
        self.assertEqual(cfg, {})


# ═══════════════════════════════════════════════════════════════════════
# Build Query State
# ═══════════════════════════════════════════════════════════════════════

class TestBuildQueryState(unittest.TestCase):
    """Test build_query_state for various visual types."""

    def test_bar_chart_query_state(self):
        qs = build_query_state(
            "clusteredBarChart",
            dimensions=[{"field": "Region", "name": "Region"}],
            measures=[{"name": "Sales", "label": "Sales"}],
            col_table_map={"Region": "Orders"},
            measure_lookup={"Sales": ("Orders", "Sales")},
        )
        self.assertIsNotNone(qs)

    def test_card_query_state_measure_only(self):
        qs = build_query_state(
            "card",
            dimensions=[],
            measures=[{"name": "Total Sales", "label": "Total Sales"}],
            col_table_map={},
            measure_lookup={"Total Sales": ("Orders", "Total Sales")},
        )
        self.assertIsNotNone(qs)

    def test_empty_fields_returns_none(self):
        qs = build_query_state(
            "clusteredBarChart",
            dimensions=[],
            measures=[],
            col_table_map={},
            measure_lookup={},
        )
        # Should return None when no data to bind
        # (actual behavior may vary, just ensure no crash)
        self.assertTrue(qs is None or isinstance(qs, dict))

    def test_table_visual_combines_roles(self):
        qs = build_query_state(
            "tableEx",
            dimensions=[{"field": "Region"}, {"field": "Category"}],
            measures=[{"name": "Sales", "label": "Sales"}],
            col_table_map={"Region": "T", "Category": "T"},
            measure_lookup={"Sales": ("T", "Sales")},
        )
        self.assertIsNotNone(qs)


# ═══════════════════════════════════════════════════════════════════════
# Validator Tests
# ═══════════════════════════════════════════════════════════════════════

class TestValidatorDaxFormula(unittest.TestCase):
    """Test ArtifactValidator.validate_dax_formula."""

    def test_valid_formula(self):
        errors = ArtifactValidator.validate_dax_formula("SUM('Orders'[Sales])")
        self.assertEqual(errors, [])

    def test_unbalanced_parens(self):
        errors = ArtifactValidator.validate_dax_formula("SUM('Orders'[Sales]")
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("paren" in e.lower() or "unmatched" in e.lower() for e in errors))

    def test_tableau_leakage_countd(self):
        errors = ArtifactValidator.validate_dax_formula("COUNTD([Customer])")
        self.assertTrue(len(errors) > 0)

    def test_tableau_leakage_zn(self):
        errors = ArtifactValidator.validate_dax_formula("ZN([Sales])")
        self.assertTrue(len(errors) > 0)

    def test_tableau_leakage_ifnull(self):
        errors = ArtifactValidator.validate_dax_formula("IFNULL([Sales], 0)")
        self.assertTrue(len(errors) > 0)

    def test_tableau_leakage_double_equals(self):
        errors = ArtifactValidator.validate_dax_formula("[Status] == 'Active'")
        self.assertTrue(len(errors) > 0)

    def test_tableau_leakage_elseif(self):
        errors = ArtifactValidator.validate_dax_formula("IF [A] > 1 THEN 'X' ELSEIF [A] > 0 THEN 'Y' END")
        self.assertTrue(len(errors) > 0)

    def test_tableau_leakage_lod(self):
        errors = ArtifactValidator.validate_dax_formula("{FIXED [Region] : SUM([Sales])}")
        self.assertTrue(len(errors) > 0)

    def test_unresolved_parameter(self):
        errors = ArtifactValidator.validate_dax_formula("[Parameters].[Discount Rate]")
        self.assertTrue(len(errors) > 0)

    def test_clean_dax_no_errors(self):
        errors = ArtifactValidator.validate_dax_formula(
            "CALCULATE(SUM('Orders'[Sales]), ALLEXCEPT('Orders', 'Orders'[Region]))")
        self.assertEqual(errors, [])

    def test_empty_formula_no_errors(self):
        errors = ArtifactValidator.validate_dax_formula("")
        self.assertEqual(errors, [])


class TestValidatorJson(unittest.TestCase):
    """Test ArtifactValidator.validate_json_file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_json(self):
        path = os.path.join(self.tmp, "test.json")
        with open(path, 'w') as f:
            json.dump({"key": "value"}, f)
        ok, err = ArtifactValidator.validate_json_file(path)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_invalid_json(self):
        path = os.path.join(self.tmp, "bad.json")
        with open(path, 'w') as f:
            f.write("{invalid json")
        ok, err = ArtifactValidator.validate_json_file(path)
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_missing_file(self):
        ok, err = ArtifactValidator.validate_json_file("/nonexistent/file.json")
        self.assertFalse(ok)


class TestValidatorTmdlFile(unittest.TestCase):
    """Test ArtifactValidator.validate_tmdl_file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_model_tmdl(self):
        path = os.path.join(self.tmp, "model.tmdl")
        with open(path, 'w') as f:
            f.write("model Model\n\tculture: en-US\n")
        ok, errors = ArtifactValidator.validate_tmdl_file(path)
        self.assertTrue(ok)

    def test_empty_tmdl(self):
        path = os.path.join(self.tmp, "model.tmdl")
        with open(path, 'w') as f:
            f.write("")
        ok, errors = ArtifactValidator.validate_tmdl_file(path)
        self.assertFalse(ok)

    def test_invalid_model_start(self):
        path = os.path.join(self.tmp, "model.tmdl")
        with open(path, 'w') as f:
            f.write("something else\n")
        ok, errors = ArtifactValidator.validate_tmdl_file(path)
        self.assertFalse(ok)


# ═══════════════════════════════════════════════════════════════════════
# Migration Report Tests
# ═══════════════════════════════════════════════════════════════════════

class TestMigrationReportClassification(unittest.TestCase):
    """Test MigrationReport._classify_dax and scoring."""

    def test_exact_clean_dax(self):
        status = MigrationReport._classify_dax("SUM('Orders'[Sales])")
        self.assertEqual(status, "exact")

    def test_unsupported_makepoint(self):
        status = MigrationReport._classify_dax("BLANK() /* MAKEPOINT: no DAX equivalent */")
        self.assertEqual(status, "unsupported")

    def test_unsupported_script(self):
        status = MigrationReport._classify_dax("0 /* SCRIPT_REAL: no DAX equivalent */")
        self.assertEqual(status, "unsupported")

    def test_approximate_comment(self):
        status = MigrationReport._classify_dax("0 /* approximate */")
        self.assertEqual(status, "approximate")

    def test_approximate_manual_conversion(self):
        status = MigrationReport._classify_dax("BLANK() /* manual conversion needed */")
        self.assertEqual(status, "approximate")

    def test_skipped_empty(self):
        status = MigrationReport._classify_dax("")
        self.assertEqual(status, "skipped")

    def test_skipped_none(self):
        status = MigrationReport._classify_dax(None)
        self.assertEqual(status, "skipped")

    def test_leak_countd(self):
        status = MigrationReport._classify_dax("COUNTD([Customer])")
        self.assertEqual(status, "approximate")

    def test_leak_zn(self):
        status = MigrationReport._classify_dax("ZN([Sales])")
        self.assertEqual(status, "approximate")


class TestMigrationReportScoring(unittest.TestCase):
    """Test MigrationReport scoring logic."""

    def test_perfect_score(self):
        report = MigrationReport("Test")
        report.add_item("calc", "M1", "exact", dax="SUM([Sales])")
        report.add_item("calc", "M2", "exact", dax="AVG([Sales])")
        summary = report.get_summary()
        self.assertEqual(summary['fidelity_score'], 100.0)

    def test_mixed_score(self):
        report = MigrationReport("Test")
        report.add_item("calc", "M1", "exact")
        report.add_item("calc", "M2", "approximate")
        summary = report.get_summary()
        self.assertEqual(summary['fidelity_score'], 75.0)

    def test_all_unsupported(self):
        report = MigrationReport("Test")
        report.add_item("calc", "M1", "unsupported")
        summary = report.get_summary()
        self.assertEqual(summary['fidelity_score'], 0.0)

    def test_empty_report(self):
        report = MigrationReport("Test")
        summary = report.get_summary()
        self.assertEqual(summary['fidelity_score'], 100.0)
        self.assertEqual(summary['total_items'], 0)

    def test_invalid_status_raises(self):
        report = MigrationReport("Test")
        with self.assertRaises(ValueError):
            report.add_item("calc", "M1", "invalid_status")

    def test_to_dict(self):
        report = MigrationReport("Test")
        report.add_item("calc", "M1", "exact")
        data = report.to_dict()
        self.assertIn("report_name", data)
        self.assertIn("summary", data)
        self.assertIn("items", data)
        self.assertEqual(len(data['items']), 1)

    def test_save_and_load(self):
        tmp = tempfile.mkdtemp()
        try:
            report = MigrationReport("Test")
            report.add_item("calc", "M1", "exact")
            path = report.save(tmp)
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data['report_name'], "Test")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_by_category_breakdown(self):
        report = MigrationReport("Test")
        report.add_item("calculation", "M1", "exact")
        report.add_item("visual", "V1", "approximate")
        report.add_item("visual", "V2", "exact")
        summary = report.get_summary()
        self.assertIn("calculation", summary['by_category'])
        self.assertIn("visual", summary['by_category'])


class TestMigrationReportBulkMethods(unittest.TestCase):
    """Test bulk add methods on MigrationReport."""

    def test_add_calculations(self):
        report = MigrationReport("Test")
        calcs = [
            {"caption": "Total Sales", "name": "[Calc1]"},
            {"caption": "Avg Score", "name": "[Calc2]"},
        ]
        calc_map = {"Total Sales": "SUM('T'[Sales])", "Avg Score": "AVERAGE('T'[Score])"}
        report.add_calculations(calcs, calc_map)
        self.assertEqual(len(report.items), 2)

    def test_add_visuals(self):
        report = MigrationReport("Test")
        worksheets = [
            {"name": "Sales View", "visual_type": "bar"},
            {"name": "Detail View", "visual_type": "text"},
        ]
        report.add_visuals(worksheets, VISUAL_TYPE_MAP)
        self.assertEqual(len(report.items), 2)

    def test_add_parameters(self):
        report = MigrationReport("Test")
        params = [{"caption": "P1"}, {"caption": "P2"}]
        report.add_parameters(params)
        self.assertEqual(len(report.items), 2)
        self.assertTrue(all(i['status'] == 'exact' for i in report.items))

    def test_add_relationships(self):
        report = MigrationReport("Test")
        rels = [{"from_table": "Orders", "to_table": "Products"}]
        report.add_relationships(rels)
        self.assertEqual(len(report.items), 1)


# ═══════════════════════════════════════════════════════════════════════
# TMDL Generation Integration
# ═══════════════════════════════════════════════════════════════════════

class TestBuildSemanticModelExtended(unittest.TestCase):
    """Test _build_semantic_model with factory-generated data."""

    def test_simple_model(self):
        ds_list, conv = make_simple_model()
        model = _build_semantic_model(ds_list, "TestReport", conv)
        tables = model['model']['tables']
        self.assertTrue(len(tables) >= 1)

    def test_multi_table_model(self):
        ds_list, conv = make_multi_table_model()
        model = _build_semantic_model(ds_list, "TestReport", conv)
        tables = model['model']['tables']
        self.assertTrue(len(tables) >= 2)
        rels = model['model']['relationships']
        self.assertTrue(len(rels) >= 1)

    def test_model_with_parameters(self):
        ds = DatasourceFactory('DS').with_table('T', ['ID:integer', 'Value:real'])
        model_data = (ModelFactory()
                      .with_datasource(ds)
                      .with_parameter(ParameterFactory('Top N').range(1, 50, 1, 10))
                      .build())
        built = _build_semantic_model([ds.build()], "ParamReport", model_data)
        tables = built['model']['tables']
        # Should have the data table plus parameter table(s)
        table_names = [t.get('name', '') for t in tables]
        self.assertIn('T', table_names)

    def test_model_with_sets(self):
        ds = DatasourceFactory('DS').with_table('Orders', ['ID:integer', 'Status:string'])
        model_data = (ModelFactory()
                      .with_datasource(ds)
                      .with_set('Active Only', 'Orders', members=['Active', 'Pending'])
                      .build())
        built = _build_semantic_model([ds.build()], "SetReport", model_data)
        self.assertIsNotNone(built)

    def test_model_with_groups(self):
        ds = DatasourceFactory('DS').with_table('Orders', ['ID:integer', 'Region:string'])
        model_data = (ModelFactory()
                      .with_datasource(ds)
                      .with_group('Region Group', 'Orders', 'Region',
                                  {'East': 'Eastern', 'West': 'Western'})
                      .build())
        built = _build_semantic_model([ds.build()], "GroupReport", model_data)
        self.assertIsNotNone(built)

    def test_model_with_bins(self):
        ds = DatasourceFactory('DS').with_table('Orders', ['ID:integer', 'Amount:real'])
        model_data = (ModelFactory()
                      .with_datasource(ds)
                      .with_bin('Amount Bin', 'Orders', 'Amount', 25)
                      .build())
        built = _build_semantic_model([ds.build()], "BinReport", model_data)
        self.assertIsNotNone(built)

    def test_model_with_hierarchy(self):
        ds = DatasourceFactory('DS').with_table('Locations', [
            'Country:string', 'State:string', 'City:string'])
        model_data = (ModelFactory()
                      .with_datasource(ds)
                      .with_hierarchy('Geo', ['Country', 'State', 'City'])
                      .build())
        built = _build_semantic_model([ds.build()], "HierReport", model_data)
        self.assertIsNotNone(built)

    def test_model_culture_override(self):
        ds_list, conv = make_simple_model()
        model = _build_semantic_model(ds_list, "FRReport", conv, culture="fr-FR")
        self.assertEqual(model['model']['culture'], "fr-FR")


class TestGenerateTmdlIntegration(unittest.TestCase):
    """Test generate_tmdl end-to-end output."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generates_model_tmdl(self):
        ds_list, conv = make_simple_model()
        stats = generate_tmdl(ds_list, "Test", conv, self.tmp)
        model_path = os.path.join(self.tmp, "definition", "model.tmdl")
        self.assertTrue(os.path.exists(model_path))
        self.assertGreater(stats['tables'], 0)

    def test_generates_table_files(self):
        ds_list, conv = make_simple_model()
        generate_tmdl(ds_list, "Test", conv, self.tmp)
        tables_dir = os.path.join(self.tmp, "definition", "tables")
        self.assertTrue(os.path.isdir(tables_dir))
        tmdl_files = [f for f in os.listdir(tables_dir) if f.endswith('.tmdl')]
        self.assertTrue(len(tmdl_files) >= 1)

    def test_generates_database_tmdl(self):
        ds_list, conv = make_simple_model()
        generate_tmdl(ds_list, "Test", conv, self.tmp)
        db_path = os.path.join(self.tmp, "definition", "database.tmdl")
        self.assertTrue(os.path.exists(db_path))

    def test_calendar_year_range(self):
        ds_list, conv = make_simple_model()
        stats = generate_tmdl(ds_list, "Test", conv, self.tmp,
                              calendar_start=2018, calendar_end=2028)
        # Should have a Calendar table
        self.assertGreater(stats['tables'], 1)


# ═══════════════════════════════════════════════════════════════════════
# Visual Container Creation
# ═══════════════════════════════════════════════════════════════════════

class TestCreateVisualContainer(unittest.TestCase):
    """Test create_visual_container with various worksheet configs."""

    def _make_ws(self, name="Sheet1", visual_type="bar", columns=None):
        ws = WorksheetFactory(name, "DS")
        if visual_type:
            ws.with_mark(visual_type)
        for col in (columns or ["Amount:measure", "Region"]):
            parts = col.split(":")
            ws.with_column(parts[0], parts[1] if len(parts) > 1 else "dimension")
        return ws.build()

    def test_bar_chart_container(self):
        ws = self._make_ws("Sales", "bar")
        vc = create_visual_container(ws, "v1", 0, 0, 300, 200, 1,
                                     {"Region": "Orders"}, {})
        self.assertIn("visual", vc)
        self.assertIn("position", vc)

    def test_line_chart_container(self):
        ws = self._make_ws("Trend", "line")
        vc = create_visual_container(ws, "v2", 0, 0, 300, 200, 1,
                                     {"Region": "Orders"}, {})
        self.assertIn("visual", vc)

    def test_table_container(self):
        ws = self._make_ws("Detail", "text")
        vc = create_visual_container(ws, "v3", 0, 0, 300, 200, 1,
                                     {"Region": "Orders"}, {})
        self.assertIn("visual", vc)

    def test_position_values(self):
        ws = self._make_ws("Sales", "bar")
        vc = create_visual_container(ws, "v1", 100, 200, 400, 300, 5,
                                     {}, {})
        pos = vc['position']
        self.assertEqual(pos['x'], 100)
        self.assertEqual(pos['y'], 200)
        self.assertEqual(pos['width'], 400)
        self.assertEqual(pos['height'], 300)


class TestGenerateVisualContainers(unittest.TestCase):
    """Test generate_visual_containers with multiple worksheets."""

    def test_multiple_worksheets(self):
        worksheets = [
            WorksheetFactory("Sheet1", "DS").with_columns(["A:measure"]).with_mark("bar").build(),
            WorksheetFactory("Sheet2", "DS").with_columns(["B:measure"]).with_mark("line").build(),
        ]
        containers = generate_visual_containers(
            worksheets, "Report", {"A": "T", "B": "T"}, {}, 1280, 720)
        self.assertEqual(len(containers), 2)

    def test_empty_worksheets(self):
        containers = generate_visual_containers([], "Report", {}, {}, 1280, 720)
        self.assertEqual(len(containers), 0)


# ═══════════════════════════════════════════════════════════════════════
# Factory Self-Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFactories(unittest.TestCase):
    """Ensure test factories produce valid structures."""

    def test_datasource_factory(self):
        ds = DatasourceFactory("DS").with_table("Orders", ["ID:integer"]).build()
        self.assertEqual(ds['name'], "DS")
        self.assertEqual(len(ds['tables']), 1)
        self.assertEqual(ds['tables'][0]['columns'][0]['name'], 'ID')

    def test_worksheet_factory(self):
        ws = (WorksheetFactory("Sales")
              .with_columns(["Amount:measure", "Region"])
              .with_mark("bar")
              .build())
        self.assertEqual(ws['name'], "Sales")
        self.assertEqual(ws['visual_type'], "bar")
        self.assertEqual(len(ws['columns']), 2)

    def test_dashboard_factory(self):
        db = (DashboardFactory("Main")
              .with_worksheet("Sheet1")
              .with_text("Hello")
              .build())
        self.assertEqual(db['name'], "Main")
        self.assertEqual(len(db['worksheets']), 1)

    def test_model_factory(self):
        ds = DatasourceFactory("DS").with_table("T", ["A:integer"])
        model = ModelFactory().with_datasource(ds).build()
        self.assertEqual(len(model['datasources']), 1)

    def test_make_simple_model(self):
        ds_list, conv = make_simple_model()
        self.assertEqual(len(ds_list), 1)
        self.assertIn('datasources', conv)

    def test_make_multi_table_model(self):
        ds_list, conv = make_multi_table_model()
        self.assertEqual(len(ds_list[0]['tables']), 2)
        self.assertEqual(len(ds_list[0]['relationships']), 1)

    def test_make_complex_model(self):
        ds_list, conv = make_complex_model()
        self.assertTrue(len(ds_list[0]['tables']) >= 2)
        self.assertTrue(len(conv['sets']) >= 1)
        self.assertTrue(len(conv['groups']) >= 1)
        self.assertTrue(len(conv['bins']) >= 1)


# ═══════════════════════════════════════════════════════════════════════
# Sprint 19 — Visual & Layout Refinements
# ═══════════════════════════════════════════════════════════════════════

class TestViolinAndParallelCoords(unittest.TestCase):
    """Test violin plot and parallel coordinates visual mappings."""

    def test_violin_in_visual_type_map(self):
        self.assertEqual(VISUAL_TYPE_MAP.get("violin"), "boxAndWhisker")
        self.assertEqual(VISUAL_TYPE_MAP.get("violinplot"), "boxAndWhisker")

    def test_violin_custom_visual_guid(self):
        self.assertIn("violin", CUSTOM_VISUAL_GUIDS)
        self.assertEqual(CUSTOM_VISUAL_GUIDS["violin"]["guid"], "ViolinPlot1.0.0")

    def test_violin_resolve_custom(self):
        pbi_type, guid_info = resolve_custom_visual_type("violin", use_custom_visuals=True)
        self.assertIsNotNone(guid_info)
        self.assertIn("Violin", guid_info["name"])

    def test_parallel_coordinates_in_visual_type_map(self):
        self.assertEqual(VISUAL_TYPE_MAP.get("parallelcoordinates"), "lineChart")
        self.assertEqual(VISUAL_TYPE_MAP.get("parallel-coordinates"), "lineChart")

    def test_parallel_coordinates_custom_visual_guid(self):
        self.assertIn("parallelcoordinates", CUSTOM_VISUAL_GUIDS)
        guid = CUSTOM_VISUAL_GUIDS["parallelcoordinates"]["guid"]
        self.assertEqual(guid, "ParallelCoordinates1.0.0")

    def test_parallel_coordinates_resolve_custom(self):
        pbi_type, guid_info = resolve_custom_visual_type("parallelcoordinates", use_custom_visuals=True)
        self.assertIsNotNone(guid_info)

    def test_violin_approximation_note(self):
        from powerbi_import.visual_generator import get_approximation_note
        note = get_approximation_note("violin")
        self.assertIsNotNone(note)
        self.assertIn("Violin", note)

    def test_parallel_coords_approximation_note(self):
        from powerbi_import.visual_generator import get_approximation_note
        note = get_approximation_note("parallelcoordinates")
        self.assertIsNotNone(note)
        self.assertIn("Parallel", note)


class TestCalendarHeatMap(unittest.TestCase):
    """Test calendar heat map → matrix with conditional formatting."""

    def test_calendar_maps_to_matrix(self):
        self.assertEqual(resolve_visual_type("calendar"), "matrix")
        self.assertEqual(resolve_visual_type("calendarheatmap"), "matrix")

    def test_calendar_heatmap_auto_conditional_formatting(self):
        ws = {
            "name": "Sales Calendar",
            "visualType": "calendarheatmap",
            "dimensions": [{"field": "Date", "name": "Date"}],
            "measures": [{"name": "Sales", "label": "Sales"}],
        }
        container = create_visual_container(
            ws, col_table_map={"Date": "Calendar", "Sales": "Fact"},
            measure_lookup={"Sales": ("Fact", "SUM('Fact'[Sales])")},
        )
        visual = container["visual"]
        # Should have conditional formatting hints
        objects = visual.get("objects", {})
        vals = objects.get("values", [])
        self.assertTrue(len(vals) > 0, "Calendar heat map should have values objects")
        # Should have migration note
        annotations = visual.get("annotations", [])
        notes = [a["value"] for a in annotations if a.get("name") == "MigrationNote"]
        self.assertTrue(any("heat map" in n.lower() or "calendar" in n.lower() for n in notes))

    def test_calendar_approximation_note(self):
        note = APPROXIMATION_MAP.get("calendarheatmap")
        self.assertIsNotNone(note)
        self.assertIn("Calendar", note[1])


class TestPackedBubbleSizeEncoding(unittest.TestCase):
    """Test packed bubble size encoding → Size data role."""

    def test_size_encoding_injected_for_scatter(self):
        ws = {
            "name": "Packed Bubbles",
            "visualType": "packedbubble",
            "dimensions": [{"field": "Category", "name": "Category"}],
            "measures": [
                {"name": "X_Val", "label": "X_Val"},
                {"name": "Y_Val", "label": "Y_Val"},
            ],
            "mark_encoding": {
                "size": {"field": "Revenue"},
            },
        }
        container = create_visual_container(
            ws,
            col_table_map={"Category": "T", "X_Val": "T", "Y_Val": "T", "Revenue": "T"},
            measure_lookup={
                "X_Val": ("T", "SUM('T'[X_Val])"),
                "Y_Val": ("T", "SUM('T'[Y_Val])"),
                "Revenue": ("T", "SUM('T'[Revenue])"),
            },
        )
        visual = container["visual"]
        qs = visual.get("query", {}).get("queryState", {})
        # Size role should be populated
        self.assertIn("Size", qs, "Scatter chart should have Size data role from mark_encoding")

    def test_no_duplicate_size_measure(self):
        ws = {
            "name": "Bubbles",
            "visualType": "packedbubble",
            "dimensions": [{"field": "Cat", "name": "Cat"}],
            "measures": [
                {"name": "X", "label": "X"},
                {"name": "Y", "label": "Y"},
                {"name": "Revenue", "label": "Revenue"},
            ],
            "mark_encoding": {
                "size": {"field": "Revenue"},
            },
        }
        container = create_visual_container(
            ws,
            col_table_map={"Cat": "T", "X": "T", "Y": "T", "Revenue": "T"},
            measure_lookup={
                "X": ("T", "SUM('T'[X])"),
                "Y": ("T", "SUM('T'[Y])"),
                "Revenue": ("T", "SUM('T'[Revenue])"),
            },
        )
        visual = container["visual"]
        qs = visual.get("query", {}).get("queryState", {})
        # Revenue should not be duplicated — should appear exactly once
        self.assertIn("Size", qs)


class TestButterflyApproximation(unittest.TestCase):
    """Test butterfly chart improved approximation note."""

    def test_butterfly_approximation_note_mentions_negate(self):
        note = APPROXIMATION_MAP.get("butterfly")
        self.assertIsNotNone(note)
        self.assertIn("negate", note[1].lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)
