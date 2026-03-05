"""
Unit tests for pbip_generator.py — Power BI Project generation.

Tests utility methods (_clean_field_name, _make_visual_position,
_build_visual_objects, _is_measure_field, _create_bookmarks,
_create_slicer_visual, _resolve_field_entity) and structural integrity
of generated visual JSON.
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pbip_generator import PowerBIProjectGenerator


# ═══════════════════════════════════════════════════════════════════════
# Helpers — create an instance without writing to disk
# ═══════════════════════════════════════════════════════════════════════

def _make_generator():
    """Create a PowerBIProjectGenerator with temp dirs."""
    return PowerBIProjectGenerator(
        converted_dir=tempfile.mkdtemp(),
        output_dir=tempfile.mkdtemp()
    )


# ═══════════════════════════════════════════════════════════════════════
# _clean_field_name
# ═══════════════════════════════════════════════════════════════════════

class TestCleanFieldName(unittest.TestCase):
    """Test _clean_field_name removes Tableau derivation prefixes."""

    def setUp(self):
        self.gen = _make_generator()

    def test_none_prefix(self):
        self.assertEqual(self.gen._clean_field_name("none:Sales"), "Sales")

    def test_sum_prefix(self):
        self.assertEqual(self.gen._clean_field_name("sum:Amount"), "Amount")

    def test_avg_prefix(self):
        self.assertEqual(self.gen._clean_field_name("avg:Price"), "Price")

    def test_count_prefix(self):
        self.assertEqual(self.gen._clean_field_name("count:Rows"), "Rows")

    def test_min_max_prefix(self):
        self.assertEqual(self.gen._clean_field_name("min:Date"), "Date")
        self.assertEqual(self.gen._clean_field_name("max:Date"), "Date")

    def test_usr_prefix(self):
        self.assertEqual(self.gen._clean_field_name("usr:Custom Field"), "Custom Field")

    def test_year_prefix(self):
        self.assertEqual(self.gen._clean_field_name("yr:OrderDate"), "OrderDate")

    def test_attr_prefix(self):
        self.assertEqual(self.gen._clean_field_name("attr:Region"), "Region")

    def test_nk_suffix_removed(self):
        self.assertEqual(self.gen._clean_field_name("Sales:nk"), "Sales")

    def test_qk_suffix_removed(self):
        self.assertEqual(self.gen._clean_field_name("Date:qk"), "Date")

    def test_no_prefix_unchanged(self):
        self.assertEqual(self.gen._clean_field_name("Sales"), "Sales")

    def test_combined_prefix_and_suffix(self):
        result = self.gen._clean_field_name("sum:Revenue:nk")
        self.assertEqual(result, "Revenue")


# ═══════════════════════════════════════════════════════════════════════
# _make_visual_position
# ═══════════════════════════════════════════════════════════════════════

class TestMakeVisualPosition(unittest.TestCase):
    """Test _make_visual_position coordinate scaling."""

    def setUp(self):
        self.gen = _make_generator()

    def test_basic_scaling(self):
        pos = {"x": 100, "y": 50, "w": 400, "h": 300}
        result = self.gen._make_visual_position(pos, 2.0, 1.5, 1)
        self.assertEqual(result["x"], 200)
        self.assertEqual(result["y"], 75)
        self.assertEqual(result["width"], 800)
        self.assertEqual(result["height"], 450)

    def test_z_order(self):
        pos = {"x": 0, "y": 0, "w": 100, "h": 100}
        result = self.gen._make_visual_position(pos, 1.0, 1.0, 3)
        self.assertEqual(result["z"], 3000)
        self.assertEqual(result["tabOrder"], 3000)

    def test_missing_dimensions_defaults(self):
        pos = {}
        result = self.gen._make_visual_position(pos, 1.0, 1.0, 0)
        self.assertEqual(result["x"], 0)
        self.assertEqual(result["y"], 0)
        self.assertEqual(result["height"], 200)  # default h
        self.assertEqual(result["width"], 300)   # default w

    def test_rounding(self):
        pos = {"x": 33, "y": 17, "w": 123, "h": 89}
        result = self.gen._make_visual_position(pos, 1.33, 0.77, 1)
        # All should be rounded to int
        for key in ("x", "y", "width", "height"):
            self.assertIsInstance(result[key], int)


# ═══════════════════════════════════════════════════════════════════════
# _is_measure_field
# ═══════════════════════════════════════════════════════════════════════

class TestIsMeasureField(unittest.TestCase):
    """Test _is_measure_field detection."""

    def setUp(self):
        self.gen = _make_generator()

    def test_known_measure(self):
        self.gen._measure_names = {"Total Sales", "Profit Ratio"}
        self.assertTrue(self.gen._is_measure_field("Total Sales"))

    def test_known_measure_with_brackets(self):
        self.gen._measure_names = {"Total Sales"}
        self.assertTrue(self.gen._is_measure_field("[Total Sales]"))

    def test_unknown_field(self):
        self.gen._measure_names = {"Total Sales"}
        self.assertFalse(self.gen._is_measure_field("Region"))

    def test_no_measure_names_set(self):
        # No _measure_names attribute
        self.assertFalse(self.gen._is_measure_field("Sales"))


# ═══════════════════════════════════════════════════════════════════════
# _build_visual_objects
# ═══════════════════════════════════════════════════════════════════════

class TestBuildVisualObjects(unittest.TestCase):
    """Test _build_visual_objects — title, labels, legend, axes."""

    def setUp(self):
        self.gen = _make_generator()

    def test_title_present(self):
        result = self.gen._build_visual_objects("My Chart", None, "clusteredBarChart")
        self.assertIn("title", result)
        title_value = result["title"][0]["properties"]["text"]["expr"]["Literal"]["Value"]
        self.assertIn("My Chart", title_value)

    def test_no_ws_data_only_title(self):
        result = self.gen._build_visual_objects("Chart", None, "lineChart")
        self.assertIn("title", result)
        # Without ws_data, no extra objects
        self.assertNotIn("labels", result)
        self.assertNotIn("legend", result)

    def test_labels_enabled(self):
        ws_data = {
            "formatting": {"mark": {"mark-labels-show": "true"}},
            "mark_encoding": {}
        }
        result = self.gen._build_visual_objects("C", ws_data, "barChart")
        self.assertIn("labels", result)
        label_show = result["labels"][0]["properties"]["show"]["expr"]["Literal"]["Value"]
        self.assertEqual(label_show, "true")

    def test_legend_with_color_field(self):
        ws_data = {
            "formatting": {},
            "mark_encoding": {"color": {"field": "Category"}}
        }
        result = self.gen._build_visual_objects("C", ws_data, "barChart")
        self.assertIn("legend", result)

    def test_no_legend_for_measure_values(self):
        ws_data = {
            "formatting": {},
            "mark_encoding": {"color": {"field": "Multiple Values"}}
        }
        result = self.gen._build_visual_objects("C", ws_data, "barChart")
        self.assertNotIn("legend", result)

    def test_background_color(self):
        ws_data = {
            "formatting": {"background_color": "#FFFFFF"},
            "mark_encoding": {}
        }
        result = self.gen._build_visual_objects("C", ws_data, "barChart")
        self.assertIn("visualContainerStyle", result)

    def test_reference_lines(self):
        ws_data = {
            "formatting": {},
            "mark_encoding": {},
            "reference_lines": [
                {"value": 500, "label": "Target", "color": "#FF0000"}
            ]
        }
        result = self.gen._build_visual_objects("C", ws_data, "barChart")
        self.assertIn("valueAxis", result)
        ref_lines = result["valueAxis"][0]["properties"].get("referenceLine", [])
        self.assertEqual(len(ref_lines), 1)
        self.assertEqual(ref_lines[0]["value"], "500")

    def test_conditional_formatting_gradient(self):
        ws_data = {
            "formatting": {},
            "mark_encoding": {
                "color": {
                    "field": "Sales",
                    "type": "quantitative",
                    "palette": "green-gold",
                    "palette_colors": ["#00FF00", "#FFD700"]
                }
            }
        }
        result = self.gen._build_visual_objects("C", ws_data, "barChart")
        self.assertIn("dataPoint", result)

    def test_axes_from_axes_data(self):
        ws_data = {
            "formatting": {},
            "mark_encoding": {},
            "axes": {
                "x": {"title": "Date"},
                "y": {"title": "Revenue"}
            }
        }
        result = self.gen._build_visual_objects("C", ws_data, "lineChart")
        cat_title = result["categoryAxis"][0]["properties"]["titleText"]["expr"]["Literal"]["Value"]
        val_title = result["valueAxis"][0]["properties"]["titleText"]["expr"]["Literal"]["Value"]
        self.assertIn("Date", cat_title)
        self.assertIn("Revenue", val_title)


# ═══════════════════════════════════════════════════════════════════════
# _create_bookmarks
# ═══════════════════════════════════════════════════════════════════════

class TestCreateBookmarks(unittest.TestCase):
    """Test _create_bookmarks from Tableau stories."""

    def setUp(self):
        self.gen = _make_generator()

    def test_empty_stories(self):
        result = self.gen._create_bookmarks([])
        self.assertEqual(result, [])

    def test_single_story_point(self):
        stories = [{
            "name": "MyStory",
            "story_points": [{"caption": "Overview"}]
        }]
        result = self.gen._create_bookmarks(stories)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["displayName"], "Overview")
        self.assertTrue(result[0]["name"].startswith("Bookmark_"))

    def test_multiple_story_points(self):
        stories = [{
            "name": "Sales Story",
            "story_points": [
                {"caption": "Point 1"},
                {"caption": "Point 2"},
                {"caption": "Point 3"},
            ]
        }]
        result = self.gen._create_bookmarks(stories)
        self.assertEqual(len(result), 3)

    def test_default_caption(self):
        stories = [{
            "name": "MyStory",
            "story_points": [{}]  # No caption
        }]
        result = self.gen._create_bookmarks(stories)
        self.assertIn("MyStory", result[0]["displayName"])

    def test_exploration_state_structure(self):
        stories = [{"name": "S", "story_points": [{"caption": "C"}]}]
        result = self.gen._create_bookmarks(stories)
        self.assertIn("explorationState", result[0])
        self.assertEqual(result[0]["explorationState"]["version"], "1.0")


# ═══════════════════════════════════════════════════════════════════════
# _create_slicer_visual
# ═══════════════════════════════════════════════════════════════════════

class TestCreateSlicerVisual(unittest.TestCase):
    """Test _create_slicer_visual."""

    def setUp(self):
        self.gen = _make_generator()

    def test_slicer_structure(self):
        result = self.gen._create_slicer_visual(
            "abc123", 10, 20, 200, 50, "Region", "Orders", 1
        )
        self.assertEqual(result["name"], "abc123")
        self.assertEqual(result["visual"]["visualType"], "slicer")
        self.assertEqual(result["position"]["x"], 10)
        self.assertEqual(result["position"]["y"], 20)
        self.assertEqual(result["position"]["width"], 200)
        self.assertEqual(result["position"]["height"], 50)

    def test_slicer_has_query_binding(self):
        result = self.gen._create_slicer_visual(
            "xyz", 0, 0, 100, 30, "Category", "Products", 0
        )
        query = result["visual"].get("query")
        self.assertIsNotNone(query)
        qs = query["queryState"]["Values"]["projections"][0]
        self.assertEqual(qs["field"]["Column"]["Property"], "Category")

    def test_slicer_dropdown_mode(self):
        result = self.gen._create_slicer_visual(
            "s1", 0, 0, 100, 30, "Status", "T", 0
        )
        data_obj = result["visual"]["objects"]["data"][0]
        mode = data_obj["properties"]["mode"]["expr"]["Literal"]["Value"]
        self.assertIn("Dropdown", mode)

    def test_slicer_schema(self):
        result = self.gen._create_slicer_visual(
            "s1", 0, 0, 100, 30, "X", "T", 0
        )
        self.assertIn("visualContainer", result["$schema"])


# ═══════════════════════════════════════════════════════════════════════
# _resolve_field_entity
# ═══════════════════════════════════════════════════════════════════════

class TestResolveFieldEntity(unittest.TestCase):
    """Test _resolve_field_entity field → (table, column) resolution."""

    def setUp(self):
        self.gen = _make_generator()

    def test_direct_match(self):
        self.gen._field_map = {"Sales": ("Orders", "Sales")}
        entity, prop = self.gen._resolve_field_entity("Sales")
        self.assertEqual(entity, "Orders")
        self.assertEqual(prop, "Sales")

    def test_bracket_stripped(self):
        self.gen._field_map = {"Sales": ("Orders", "Sales")}
        entity, prop = self.gen._resolve_field_entity("[Sales]")
        self.assertEqual(entity, "Orders")

    def test_fallback_no_map(self):
        self.gen._main_table = "DefaultTable"
        entity, prop = self.gen._resolve_field_entity("Unknown")
        self.assertEqual(entity, "DefaultTable")
        self.assertEqual(prop, "Unknown")


# ═══════════════════════════════════════════════════════════════════════
# Full project generation (integration — writes to temp dir)
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateProject(unittest.TestCase):
    """Integration test — generate a full .pbip project from mock data."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.gen = PowerBIProjectGenerator(
            converted_dir=tempfile.mkdtemp(),
            output_dir=self.output_dir
        )
        self.objects = {
            "worksheets": [
                {"name": "Sheet1", "fields": [
                    {"name": "Category", "shelf": "rows"},
                    {"name": "Sales", "shelf": "columns"}
                ], "chart_type": "clusteredBarChart", "formatting": {},
                 "mark_encoding": {}, "filters": []}
            ],
            "dashboards": [
                {"name": "Dashboard1", "width": 1000, "height": 800,
                 "objects": [
                     {"type": "worksheet", "worksheetName": "Sheet1",
                      "position": {"x": 0, "y": 0, "w": 500, "h": 400}}
                 ], "colors": []}
            ],
            "datasources": [
                {
                    "name": "Sample",
                    "connection": {"type": "CSV", "details": {"filename": "data.csv"}},
                    "tables": [{"name": "Data", "columns": [
                        {"name": "Category", "datatype": "string"},
                        {"name": "Sales", "datatype": "real"},
                    ]}],
                    "calculations": [],
                    "relationships": []
                }
            ],
            "calculations": [],
            "parameters": [],
            "filters": [],
            "stories": [],
            "sets": [],
            "groups": [],
            "bins": [],
            "hierarchies": [],
            "user_filters": [],
            "actions": [],
            "custom_sql": [],
            "sort_orders": [],
            "aliases": [],
        }

    def tearDown(self):
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def _generate(self):
        """Generate project, suppressing emoji-laden stdout."""
        old_stdout = sys.stdout
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
        try:
            self.gen.generate_project("Test", self.objects)
        finally:
            sys.stdout = old_stdout

    def test_project_creates_pbip_file(self):
        self._generate()
        pbip_path = os.path.join(self.output_dir, "Test", "Test.pbip")
        self.assertTrue(os.path.exists(pbip_path))

    def test_project_creates_report_dir(self):
        self._generate()
        report_dir = os.path.join(self.output_dir, "Test", "Test.Report")
        self.assertTrue(os.path.isdir(report_dir))

    def test_project_creates_semantic_model(self):
        self._generate()
        sm_dir = os.path.join(self.output_dir, "Test", "Test.SemanticModel")
        self.assertTrue(os.path.isdir(sm_dir))

    def test_pbip_contains_valid_json(self):
        self._generate()
        pbip_path = os.path.join(self.output_dir, "Test", "Test.pbip")
        with open(pbip_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn("version", data)

    def test_metadata_created(self):
        self._generate()
        meta_path = os.path.join(self.output_dir, "Test", "migration_metadata.json")
        self.assertTrue(os.path.exists(meta_path))
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        self.assertIn("objects_converted", meta)
        self.assertEqual(meta["objects_converted"]["worksheets"], 1)
        self.assertEqual(meta["objects_converted"]["dashboards"], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
