"""
Tests for powerbi_import/visual_generator.py

Covers:
- Visual type mapping (60+ types)
- Data role definitions
- Config template generation (PBIR-native objects)
- Visual container creation
- Query state building with role-based projections
- Slicer sync groups
- Cross-filtering disable
- Action button navigation (page + URL)
- TopN and categorical visual filters
- Sort state migration
- Reference lines (constant lines)
- Conditional formatting integration
- Grid layout positioning
"""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'powerbi_import'))

from powerbi_import.visual_generator import (
    resolve_visual_type,
    generate_visual_containers,
    create_visual_container,
    create_projections,
    create_prototype_query,
    create_filters_config,
    create_page_layout,
    build_query_state,
    VISUAL_TYPE_MAP,
    VISUAL_DATA_ROLES,
    _get_config_template,
    _build_visual_filters,
)


class TestVisualTypeMapping(unittest.TestCase):
    """Test the 60+ visual type mappings."""

    def test_bar_types(self):
        self.assertEqual(resolve_visual_type("bar"), "clusteredBarChart")
        self.assertEqual(resolve_visual_type("stacked-bar"), "stackedBarChart")
        self.assertEqual(resolve_visual_type("100-stacked-bar"), "hundredPercentStackedBarChart")

    def test_column_types(self):
        self.assertEqual(resolve_visual_type("column"), "clusteredColumnChart")
        self.assertEqual(resolve_visual_type("histogram"), "clusteredColumnChart")
        self.assertEqual(resolve_visual_type("stacked-column"), "stackedColumnChart")

    def test_line_area(self):
        self.assertEqual(resolve_visual_type("line"), "lineChart")
        self.assertEqual(resolve_visual_type("area"), "areaChart")
        self.assertEqual(resolve_visual_type("sparkline"), "lineChart")

    def test_pie_donut_funnel(self):
        self.assertEqual(resolve_visual_type("pie"), "pieChart")
        self.assertEqual(resolve_visual_type("donut"), "donutChart")
        self.assertEqual(resolve_visual_type("semicircle"), "donutChart")
        self.assertEqual(resolve_visual_type("funnel"), "funnel")

    def test_scatter_bubble(self):
        self.assertEqual(resolve_visual_type("scatter"), "scatterChart")
        self.assertEqual(resolve_visual_type("bubble"), "scatterChart")
        self.assertEqual(resolve_visual_type("circle"), "scatterChart")
        self.assertEqual(resolve_visual_type("packedbubble"), "scatterChart")

    def test_map_types(self):
        self.assertEqual(resolve_visual_type("map"), "map")
        self.assertEqual(resolve_visual_type("polygon"), "map")

    def test_table_matrix(self):
        self.assertEqual(resolve_visual_type("table"), "tableEx")
        self.assertEqual(resolve_visual_type("text"), "tableEx")
        self.assertEqual(resolve_visual_type("automatic"), "tableEx")
        self.assertEqual(resolve_visual_type("pivot"), "pivotTable")
        self.assertEqual(resolve_visual_type("heatmap"), "matrix")

    def test_kpi_card_gauge(self):
        self.assertEqual(resolve_visual_type("kpi"), "card")
        self.assertEqual(resolve_visual_type("gauge"), "gauge")
        self.assertEqual(resolve_visual_type("bullet"), "gauge")

    def test_treemap_hierarchy(self):
        self.assertEqual(resolve_visual_type("treemap"), "treemap")
        self.assertEqual(resolve_visual_type("square"), "treemap")
        self.assertEqual(resolve_visual_type("sunburst"), "sunburst")

    def test_waterfall_box(self):
        self.assertEqual(resolve_visual_type("waterfall"), "waterfallChart")
        self.assertEqual(resolve_visual_type("boxplot"), "boxAndWhisker")

    def test_combo_types(self):
        self.assertEqual(resolve_visual_type("combo"), "lineStackedColumnComboChart")
        self.assertEqual(resolve_visual_type("dualaxis"), "lineClusteredColumnComboChart")
        self.assertEqual(resolve_visual_type("pareto"), "lineClusteredColumnComboChart")

    def test_slicer_filter(self):
        self.assertEqual(resolve_visual_type("slicer"), "slicer")
        self.assertEqual(resolve_visual_type("filter_control"), "slicer")
        self.assertEqual(resolve_visual_type("listbox"), "slicer")

    def test_specialty(self):
        self.assertEqual(resolve_visual_type("wordcloud"), "wordCloud")
        self.assertEqual(resolve_visual_type("ribbon"), "ribbonChart")
        self.assertEqual(resolve_visual_type("sankey"), "sankeyDiagram")

    def test_textbox_image_button(self):
        self.assertEqual(resolve_visual_type("textbox"), "textbox")
        self.assertEqual(resolve_visual_type("image"), "image")
        self.assertEqual(resolve_visual_type("button"), "actionButton")

    def test_unknown_type_fallback(self):
        self.assertEqual(resolve_visual_type("unknown_xyz"), "tableEx")

    def test_none_type(self):
        self.assertEqual(resolve_visual_type(None), "tableEx")

    def test_case_insensitive(self):
        self.assertEqual(resolve_visual_type("LINE"), "lineChart")
        self.assertEqual(resolve_visual_type("PieChart"), "pieChart")


class TestDataRoles(unittest.TestCase):
    """Test VISUAL_DATA_ROLES definitions."""

    def test_common_types_have_roles(self):
        for vt in ["clusteredBarChart", "lineChart", "pieChart", "tableEx",
                    "scatterChart", "card", "slicer", "map", "gauge"]:
            self.assertIn(vt, VISUAL_DATA_ROLES, f"Missing roles for {vt}")

    def test_card_has_no_dimensions(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["card"]
        self.assertEqual(dim_roles, [])
        self.assertIn("Fields", meas_roles)

    def test_slicer_has_only_dimensions(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["slicer"]
        self.assertEqual(meas_roles, [])
        self.assertIn("Values", dim_roles)

    def test_bar_chart_roles(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["clusteredBarChart"]
        self.assertIn("Category", dim_roles)
        self.assertIn("Y", meas_roles)

    def test_scatter_chart_roles(self):
        dim_roles, meas_roles = VISUAL_DATA_ROLES["scatterChart"]
        self.assertIn("X", meas_roles)
        self.assertIn("Y", meas_roles)
        self.assertIn("Category", dim_roles)


class TestConfigTemplates(unittest.TestCase):
    """Test PBIR-native config templates."""

    def test_bar_chart_template(self):
        config = _get_config_template("clusteredBarChart")
        self.assertIn("objects", config)
        self.assertIn("categoryAxis", config["objects"])
        self.assertIn("valueAxis", config["objects"])

    def test_line_chart_template_has_markers(self):
        config = _get_config_template("lineChart")
        objs = config.get("objects", {})
        dp = objs.get("dataPoint", [{}])
        props = dp[0].get("properties", {})
        self.assertIn("showMarkers", props)

    def test_pie_chart_has_labels(self):
        config = _get_config_template("pieChart")
        objs = config.get("objects", {})
        self.assertIn("labels", objs)

    def test_card_template(self):
        config = _get_config_template("card")
        self.assertIn("objects", config)
        objs = config["objects"]
        self.assertIn("labels", objs)

    def test_slicer_template(self):
        config = _get_config_template("slicer")
        self.assertIn("objects", config)

    def test_unknown_type_returns_empty(self):
        config = _get_config_template("nonexistent_visual_type")
        self.assertEqual(config, {})

    def test_table_template_has_auto_select(self):
        config = _get_config_template("tableEx")
        self.assertTrue(config.get("autoSelectVisualType"))

    def test_templates_use_pbir_expressions(self):
        """Verify templates use PBIR expression objects, not plain values."""
        config = _get_config_template("clusteredBarChart")
        axis = config["objects"]["categoryAxis"][0]["properties"]["show"]
        self.assertIn("expr", axis)
        self.assertIn("Literal", axis["expr"])


class TestVisualContainerCreation(unittest.TestCase):
    """Test create_visual_container() function."""

    def _make_worksheet(self, **kwargs):
        base = {"name": "TestVisual", "visualType": "bar", "dataFields": []}
        base.update(kwargs)
        return base

    def test_basic_container_structure(self):
        ws = self._make_worksheet()
        container = create_visual_container(ws, x=10, y=20, width=400, height=300, z_index=1)
        self.assertIn("$schema", container)
        self.assertIn("name", container)
        self.assertIn("position", container)
        self.assertIn("visual", container)
        pos = container["position"]
        self.assertEqual(pos["x"], 10)
        self.assertEqual(pos["y"], 20)
        self.assertEqual(pos["width"], 400)
        self.assertEqual(pos["height"], 300)

    def test_visual_type_resolved(self):
        ws = self._make_worksheet(visualType="bar")
        container = create_visual_container(ws)
        self.assertEqual(container["visual"]["visualType"], "clusteredBarChart")

    def test_title_set(self):
        ws = self._make_worksheet(name="Sales by Region")
        container = create_visual_container(ws)
        title = container["visual"]["visualContainerObjects"]["title"]
        self.assertTrue(len(title) > 0)

    def test_subtitle_set(self):
        ws = self._make_worksheet(subtitle="Q1 2025")
        container = create_visual_container(ws)
        self.assertIn("subTitle", container["visual"]["visualContainerObjects"])

    def test_no_subtitle_when_empty(self):
        ws = self._make_worksheet()
        container = create_visual_container(ws)
        self.assertNotIn("subTitle", container["visual"].get("visualContainerObjects", {}))


class TestSlicerSyncGroups(unittest.TestCase):
    """Test slicer sync group generation."""

    def test_sync_group_added(self):
        ws = {"name": "Date Slicer", "visualType": "slicer",
              "syncGroup": "DateGroup", "dataFields": []}
        container = create_visual_container(ws)
        self.assertIn("syncGroup", container)
        self.assertEqual(container["syncGroup"]["groupName"], "DateGroup")
        self.assertTrue(container["syncGroup"]["syncField"])
        self.assertTrue(container["syncGroup"]["syncFilters"])

    def test_filter_scope_as_sync_group(self):
        ws = {"name": "Region Slicer", "visualType": "slicer",
              "filterScope": "RegionScope", "dataFields": []}
        container = create_visual_container(ws)
        self.assertIn("syncGroup", container)
        self.assertEqual(container["syncGroup"]["groupName"], "RegionScope")

    def test_no_sync_group_for_non_slicer(self):
        ws = {"name": "Chart", "visualType": "bar",
              "syncGroup": "GroupX", "dataFields": []}
        container = create_visual_container(ws)
        self.assertNotIn("syncGroup", container)

    def test_no_sync_group_when_empty(self):
        ws = {"name": "Slicer", "visualType": "slicer", "dataFields": []}
        container = create_visual_container(ws)
        self.assertNotIn("syncGroup", container)


class TestCrossFilteringDisable(unittest.TestCase):
    """Test cross-filtering disable behavior."""

    def test_disabled_via_interactions(self):
        ws = {"name": "Visual", "visualType": "bar",
              "interactions": {"disabled": True}, "dataFields": []}
        container = create_visual_container(ws)
        self.assertIn("filterConfig", container)
        self.assertTrue(container["filterConfig"]["disabled"])

    def test_disabled_via_crossfilter(self):
        ws = {"name": "Visual", "visualType": "line",
              "crossFilter": {"disabled": True}, "dataFields": []}
        container = create_visual_container(ws)
        self.assertIn("filterConfig", container)

    def test_not_disabled_by_default(self):
        ws = {"name": "Visual", "visualType": "bar", "dataFields": []}
        container = create_visual_container(ws)
        self.assertNotIn("filterConfig", container)


class TestActionButtonNavigation(unittest.TestCase):
    """Test action button page and URL navigation."""

    def test_page_navigation(self):
        ws = {"name": "Nav Button", "visualType": "button",
              "navigation": {"sheet": "Page2"}, "dataFields": []}
        container = create_visual_container(ws)
        action = container["visual"].get("objects", {}).get("action", [])
        self.assertTrue(len(action) > 0)
        props = action[0]["properties"]
        self.assertIn("PageNavigation", json.dumps(props))

    def test_url_navigation(self):
        ws = {"name": "Link", "visualType": "button",
              "navigation": {"url": "https://example.com"}, "dataFields": []}
        container = create_visual_container(ws)
        action = container["visual"].get("objects", {}).get("action", [])
        self.assertTrue(len(action) > 0)
        props = action[0]["properties"]
        self.assertIn("WebUrl", json.dumps(props))

    def test_action_fallback(self):
        ws = {"name": "Nav", "visualType": "button",
              "action": {"pageName": "Overview"}, "dataFields": []}
        container = create_visual_container(ws)
        action = container["visual"].get("objects", {}).get("action", [])
        self.assertTrue(len(action) > 0)


class TestVisualFilters(unittest.TestCase):
    """Test visual-level filter construction including TopN."""

    def test_topn_filter(self):
        filters = [{"field": "Product", "type": "topN", "count": 5}]
        result = _build_visual_filters(filters, {"Product": "Sales"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "TopN")
        self.assertEqual(result[0]["itemCount"], 5)

    def test_categorical_filter(self):
        filters = [{"field": "Region", "type": "basic", "values": ["East", "West"]}]
        result = _build_visual_filters(filters, {"Region": "Sales"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "Categorical")

    def test_empty_filters(self):
        result = _build_visual_filters([], {})
        self.assertEqual(result, [])


class TestSortState(unittest.TestCase):
    """Test sort order migration."""

    def test_ascending_sort(self):
        ws = {"name": "V", "visualType": "bar",
              "sortBy": [{"field": "Revenue", "direction": "ascending"}],
              "dataFields": []}
        container = create_visual_container(ws, col_table_map={"Revenue": "Sales"})
        sort_def = container["visual"].get("query", {}).get("sortDefinition", {})
        self.assertIn("sort", sort_def)
        self.assertEqual(sort_def["sort"][0]["direction"], "Ascending")

    def test_descending_sort(self):
        ws = {"name": "V", "visualType": "bar",
              "sortBy": [{"field": "Revenue", "direction": "descending"}],
              "dataFields": []}
        container = create_visual_container(ws, col_table_map={"Revenue": "Sales"})
        sort_def = container["visual"]["query"]["sortDefinition"]
        self.assertEqual(sort_def["sort"][0]["direction"], "Descending")


class TestReferenceLines(unittest.TestCase):
    """Test reference/constant line migration."""

    def test_reference_line(self):
        ws = {"name": "V", "visualType": "bar",
              "referenceLines": [{"value": 100, "label": "Target", "color": "#00FF00"}],
              "dataFields": []}
        container = create_visual_container(ws)
        objs = container["visual"].get("objects", {})
        self.assertIn("constantLine", objs)
        self.assertEqual(len(objs["constantLine"]), 1)


class TestBuildQueryState(unittest.TestCase):
    """Test the build_query_state function with role-based projections."""

    def test_bar_chart_query_state(self):
        dims = [{"field": "Region", "name": "Region"}]
        meas = [{"expression": "Sum(Revenue)", "name": "Revenue"}]
        ctm = {"Region": "Sales", "Revenue": "Sales"}
        qs = build_query_state("clusteredBarChart", dims, meas, ctm, {})
        self.assertIn("Category", qs)
        self.assertIn("Y", qs)

    def test_card_has_only_measures(self):
        meas = [{"expression": "Sum(Revenue)", "name": "Total Revenue"}]
        ctm = {"Revenue": "Sales"}
        qs = build_query_state("card", [], meas, ctm, {})
        self.assertIn("Fields", qs)

    def test_table_uses_values_role(self):
        dims = [{"field": "Name", "name": "Name"}]
        meas = [{"expression": "Count(Id)", "name": "Count"}]
        ctm = {"Name": "People", "Id": "People"}
        qs = build_query_state("tableEx", dims, meas, ctm, {})
        self.assertIn("Values", qs)

    def test_empty_returns_none(self):
        qs = build_query_state("clusteredBarChart", [], [], {}, {})
        self.assertIsNone(qs)

    def test_measure_lookup_used(self):
        meas = [{"name": "Total Sales"}]
        ml = {"Total Sales": ("Sales", "SUM('Sales'[Revenue])")}
        qs = build_query_state("card", [], meas, {}, ml)
        self.assertIn("Fields", qs)
        proj = qs["Fields"]["projections"][0]
        self.assertIn("Measure", proj["field"])


class TestGenerateVisualContainers(unittest.TestCase):
    """Test the generate_visual_containers batch function."""

    def test_generates_containers(self):
        worksheets = [
            {"name": "Sheet1", "visualType": "bar", "dataFields": []},
            {"name": "Sheet2", "visualType": "line", "dataFields": []},
        ]
        containers = generate_visual_containers(worksheets)
        self.assertEqual(len(containers), 2)

    def test_grid_layout_positioning(self):
        worksheets = [{"name": f"S{i}", "visualType": "bar", "dataFields": []} for i in range(5)]
        containers = generate_visual_containers(worksheets)
        # After 4 visuals in a row (x wraps after >1000), y should increase
        positions = [c["position"] for c in containers]
        # Verify that at some point y increases (row wrap)
        y_values = [p["y"] for p in positions]
        self.assertGreater(max(y_values), min(y_values))

    def test_max_20_visuals(self):
        worksheets = [{"name": f"S{i}", "visualType": "bar", "dataFields": []} for i in range(25)]
        containers = generate_visual_containers(worksheets)
        self.assertEqual(len(containers), 20)

    def test_passes_col_table_map(self):
        worksheets = [{"name": "S", "visualType": "bar",
                       "dimensions": [{"field": "X"}],
                       "measures": [{"expression": "Sum(Y)"}],
                       "dataFields": []}]
        ctm = {"X": "T", "Y": "T"}
        containers = generate_visual_containers(worksheets, col_table_map=ctm)
        self.assertEqual(len(containers), 1)


class TestLegacyFunctions(unittest.TestCase):
    """Test legacy helper functions."""

    def test_create_projections(self):
        ws = {"dataFields": [
            {"name": "Region", "role": "category"},
            {"name": "Sales", "role": "values"},
        ]}
        proj = create_projections(ws)
        self.assertIn("category", proj)
        self.assertIn("values", proj)

    def test_create_projections_default(self):
        ws = {"dataFields": []}
        proj = create_projections(ws)
        self.assertIn("values", proj)

    def test_create_prototype_query(self):
        ws = {"dataFields": [{"name": "Region"}, {"name": "Sales"}]}
        query = create_prototype_query(ws)
        self.assertEqual(query["Version"], 2)
        self.assertTrue(len(query["Select"]) >= 2)

    def test_create_filters_config(self):
        filters = [{"field": "Region", "values": ["East", "West"]}]
        config = create_filters_config(filters)
        self.assertEqual(len(config), 1)

    def test_create_page_layout(self):
        layout = create_page_layout([])
        self.assertEqual(layout["width"], 1280)
        self.assertEqual(layout["height"], 720)


if __name__ == '__main__':
    unittest.main()
