"""
Phase D+E Tests — Visual Fidelity + Coverage for Untested Functions

Tests for:
- Phase D: New visual config templates, approximation map, migration notes, fallback partition
- Phase E: tmdl_generator relationship functions, pbip_generator visual creators, etc.
"""

import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from powerbi_import.visual_generator import _get_config_template, VISUAL_DATA_ROLES
from powerbi_import.visual_generator import APPROXIMATION_MAP, get_approximation_note
from powerbi_import.visual_generator import create_visual_container
from powerbi_import.tmdl_generator import _write_partition
from powerbi_import.tmdl_generator import _deactivate_ambiguous_paths
from powerbi_import.tmdl_generator import _detect_many_to_many
from powerbi_import.tmdl_generator import _replace_related_with_lookupvalue
from powerbi_import.tmdl_generator import _fix_related_for_many_to_many
from powerbi_import.tmdl_generator import _infer_cross_table_relationships
from powerbi_import.pbip_generator import PowerBIProjectGenerator
from powerbi_import.visual_generator import resolve_visual_type


# ═══════════════════════════════════════════════════════════════════
# Phase D — Visual Fidelity Tests
# ═══════════════════════════════════════════════════════════════════


class TestVisualConfigTemplates(unittest.TestCase):
    """Test that all visual types with data roles have config templates."""

    def setUp(self):
        self._get_config = _get_config_template
        self._roles = VISUAL_DATA_ROLES

    def test_hundredPercentStackedAreaChart_has_template(self):
        config = self._get_config("hundredPercentStackedAreaChart")
        self.assertIn("objects", config)
        self.assertIn("categoryAxis", config["objects"])
        self.assertIn("legend", config["objects"])

    def test_sunburst_has_template(self):
        config = self._get_config("sunburst")
        self.assertIn("objects", config)
        self.assertIn("legend", config["objects"])

    def test_decompositionTree_has_template(self):
        config = self._get_config("decompositionTree")
        self.assertIn("objects", config)
        self.assertIn("tree", config["objects"])

    def test_shapeMap_has_template(self):
        config = self._get_config("shapeMap")
        self.assertIn("objects", config)
        self.assertIn("legend", config["objects"])
        self.assertIn("dataPoint", config["objects"])

    def test_all_data_role_types_have_templates(self):
        """Every visual type in VISUAL_DATA_ROLES should have a non-empty config template."""
        missing = []
        for vtype in self._roles:
            config = self._get_config(vtype)
            if not config:
                missing.append(vtype)
        # Allow some pass-through types (table, pivotTable etc already have templates)
        # but the 4 new ones should NOT appear in missing
        for new_type in ["hundredPercentStackedAreaChart", "sunburst", "decompositionTree", "shapeMap"]:
            self.assertNotIn(new_type, missing, f"{new_type} should have a config template")

    def test_existing_templates_unchanged(self):
        """Verify existing templates still work after the addition."""
        config = self._get_config("clusteredBarChart")
        self.assertIn("categoryAxis", config["objects"])
        config = self._get_config("pieChart")
        self.assertIn("legend", config["objects"])


class TestApproximationMap(unittest.TestCase):
    """Test the APPROXIMATION_MAP and get_approximation_note function."""

    def setUp(self):
        self._map = APPROXIMATION_MAP
        self._note = get_approximation_note

    def test_map_has_known_entries(self):
        self.assertIn("mekko", self._map)
        self.assertIn("sankey", self._map)
        self.assertIn("butterfly", self._map)
        self.assertIn("waffle", self._map)
        self.assertIn("pareto", self._map)
        self.assertIn("bumpchart", self._map)

    def test_map_entries_are_tuples(self):
        for key, val in self._map.items():
            self.assertIsInstance(val, tuple, f"{key} should be a tuple")
            self.assertEqual(len(val), 2, f"{key} should have (pbi_type, note)")
            self.assertIsInstance(val[0], str)
            self.assertIsInstance(val[1], str)

    def test_get_approximation_note_sankey(self):
        note = self._note("sankey")
        self.assertIsNotNone(note)
        self.assertIn("Sankey", note)

    def test_get_approximation_note_exact_match(self):
        """Exact PBI types should return None (not approximated)."""
        self.assertIsNone(self._note("clusteredBarChart"))
        self.assertIsNone(self._note("lineChart"))
        self.assertIsNone(self._note("pieChart"))

    def test_get_approximation_note_none_input(self):
        self.assertIsNone(self._note(None))
        self.assertIsNone(self._note(""))

    def test_get_approximation_note_case_insensitive(self):
        # The map uses lowercase keys, function lowercases input
        note = self._note("SANKEY")
        # Should match if function lowercases
        # APPROXIMATION_MAP uses lowercase keys, get_approximation_note lowercases
        self.assertIsNotNone(note)


class TestMigrationNoteOnVisuals(unittest.TestCase):
    """Test that approximation-mapped visuals get migration note annotations."""

    def test_sankey_visual_has_annotation(self):
        ws = {"name": "Test Sankey", "visualType": "sankey",
              "dataFields": [{"field": "A", "role": "dimension"}]}
        result = create_visual_container(ws)
        visual = result.get("visual", {})
        annotations = visual.get("annotations", [])
        self.assertTrue(len(annotations) > 0, "Sankey visual should have migration annotation")
        self.assertEqual(annotations[0]["name"], "MigrationNote")

    def test_exact_type_has_no_annotation(self):
        ws = {"name": "Test Bar", "visualType": "bar",
              "dataFields": [{"field": "A", "role": "dimension"}]}
        result = create_visual_container(ws)
        visual = result.get("visual", {})
        annotations = visual.get("annotations", [])
        self.assertEqual(len(annotations), 0, "Exact PBI type should have no annotation")

    def test_butterfly_visual_has_annotation(self):
        ws = {"name": "Test Butterfly", "visualType": "butterfly",
              "dataFields": [{"field": "A", "role": "dimension"}]}
        result = create_visual_container(ws)
        visual = result.get("visual", {})
        annotations = visual.get("annotations", [])
        self.assertTrue(len(annotations) > 0)
        self.assertIn("Butterfly", annotations[0]["value"])


class TestFallbackPartition(unittest.TestCase):
    """Test that fallback M partition uses #table instead of null."""

    def test_fallback_produces_empty_table(self):
        lines = []
        source = {"type": "m", "expression": ""}
        _write_partition(lines, "TestPartition", source)
        content = "\n".join(lines)
        self.assertIn("#table(type table [], {})", content)
        self.assertNotIn("Source = null", content)

    def test_fallback_has_todo_comment(self):
        lines = []
        source = {"type": "m", "expression": ""}
        _write_partition(lines, "TestPartition", source)
        content = "\n".join(lines)
        self.assertIn("TODO: Configure data source", content)


# ═══════════════════════════════════════════════════════════════════
# Phase E — Coverage Tests for tmdl_generator relationship functions
# ═══════════════════════════════════════════════════════════════════


class TestDeactivateAmbiguousPaths(unittest.TestCase):
    """Test _deactivate_ambiguous_paths (Union-Find cycle detection)."""

    def setUp(self):
        self._deactivate = _deactivate_ambiguous_paths

    def _make_model(self, relationships):
        return {"model": {"tables": [], "relationships": relationships}}

    def test_no_relationships(self):
        model = self._make_model([])
        self._deactivate(model)
        self.assertEqual(len(model["model"]["relationships"]), 0)

    def test_no_cycle_keeps_all_active(self):
        rels = [
            {"name": "r1", "fromTable": "A", "fromColumn": "id", "toTable": "B", "toColumn": "id"},
            {"name": "r2", "fromTable": "B", "fromColumn": "id", "toTable": "C", "toColumn": "id"},
        ]
        model = self._make_model(rels)
        self._deactivate(model)
        # No cycles → all remain active
        for r in rels:
            self.assertNotEqual(r.get("isActive"), False)

    def test_cycle_deactivates_one(self):
        rels = [
            {"name": "r1", "fromTable": "A", "fromColumn": "id", "toTable": "B", "toColumn": "id"},
            {"name": "r2", "fromTable": "B", "fromColumn": "id", "toTable": "C", "toColumn": "id"},
            {"name": "r3", "fromTable": "C", "fromColumn": "id", "toTable": "A", "toColumn": "id"},
        ]
        model = self._make_model(rels)
        self._deactivate(model)
        deactivated = [r for r in rels if r.get("isActive") == False]
        self.assertEqual(len(deactivated), 1, "One relationship should be deactivated in a 3-node cycle")

    def test_calendar_deactivated_first(self):
        """Calendar relationships should be deactivated before original ones."""
        rels = [
            {"name": "original_1", "fromTable": "A", "fromColumn": "id", "toTable": "B", "toColumn": "id"},
            {"name": "original_2", "fromTable": "B", "fromColumn": "id", "toTable": "C", "toColumn": "id"},
            {"name": "Calendar_date", "fromTable": "C", "fromColumn": "date", "toTable": "A", "toColumn": "date"},
        ]
        model = self._make_model(rels)
        self._deactivate(model)
        deactivated = [r for r in rels if r.get("isActive") == False]
        self.assertEqual(len(deactivated), 1)
        self.assertTrue(deactivated[0]["name"].startswith("Calendar_"))

    def test_inferred_deactivated_before_original(self):
        rels = [
            {"name": "original_1", "fromTable": "A", "fromColumn": "id", "toTable": "B", "toColumn": "id"},
            {"name": "original_2", "fromTable": "B", "fromColumn": "id", "toTable": "C", "toColumn": "id"},
            {"name": "inferred_ac", "fromTable": "C", "fromColumn": "id", "toTable": "A", "toColumn": "id"},
        ]
        model = self._make_model(rels)
        self._deactivate(model)
        deactivated = [r for r in rels if r.get("isActive") == False]
        self.assertEqual(len(deactivated), 1)
        self.assertTrue(deactivated[0]["name"].startswith("inferred_"))

    def test_already_inactive_skipped(self):
        rels = [
            {"name": "r1", "fromTable": "A", "fromColumn": "id", "toTable": "B", "toColumn": "id"},
            {"name": "r2", "fromTable": "B", "fromColumn": "id", "toTable": "C", "toColumn": "id", "isActive": False},
            {"name": "r3", "fromTable": "C", "fromColumn": "id", "toTable": "A", "toColumn": "id"},
        ]
        model = self._make_model(rels)
        self._deactivate(model)
        # r2 already inactive, so the cycle A-B-C-A still exists via r1,r3
        # Since r2 is skipped, the tree is A-B (via r1), then C-A (via r3) — no cycle
        # No additional deactivation should happen
        newly_deactivated = [r for r in rels if r.get("isActive") == False and r["name"] != "r2"]
        self.assertEqual(len(newly_deactivated), 0)


class TestDetectManyToMany(unittest.TestCase):
    """Test _detect_many_to_many cardinality detection."""

    def setUp(self):
        self._detect = _detect_many_to_many

    def _make_model(self, relationships):
        return {"model": {"tables": [], "relationships": relationships}}

    def test_full_join_sets_many_to_many(self):
        rels = [{"fromTable": "A", "toTable": "B", "toColumn": "id", "joinType": "full"}]
        model = self._make_model(rels)
        self._detect(model, [])
        self.assertEqual(rels[0]["fromCardinality"], "many")
        self.assertEqual(rels[0]["toCardinality"], "many")
        self.assertEqual(rels[0]["crossFilteringBehavior"], "bothDirections")

    def test_left_join_sets_many_to_many(self):
        """Non-Calendar tables default to manyToMany (cannot verify uniqueness)."""
        rels = [{"fromTable": "A", "toTable": "B", "toColumn": "id", "joinType": "left"}]
        model = self._make_model(rels)
        self._detect(model, [])
        self.assertEqual(rels[0]["fromCardinality"], "many")
        self.assertEqual(rels[0]["toCardinality"], "many")
        self.assertEqual(rels[0]["crossFilteringBehavior"], "bothDirections")

    def test_inner_join_sets_many_to_many(self):
        """Non-Calendar tables default to manyToMany (cannot verify uniqueness)."""
        rels = [{"fromTable": "A", "toTable": "B", "toColumn": "id", "joinType": "inner"}]
        model = self._make_model(rels)
        self._detect(model, [])
        self.assertEqual(rels[0]["toCardinality"], "many")

    def test_default_join_type(self):
        rels = [{"fromTable": "A", "toTable": "B", "toColumn": "id"}]
        model = self._make_model(rels)
        self._detect(model, [])
        # Default: manyToMany (cannot verify uniqueness without data)
        self.assertEqual(rels[0]["toCardinality"], "many")

    def test_calendar_table_sets_many_to_one(self):
        """Calendar table is guaranteed unique — keeps manyToOne."""
        rels = [{"fromTable": "Orders", "toTable": "Calendar", "toColumn": "Date", "joinType": "left"}]
        model = self._make_model(rels)
        self._detect(model, [])
        self.assertEqual(rels[0]["toCardinality"], "one")
        self.assertEqual(rels[0]["crossFilteringBehavior"], "singleDirection")


class TestReplaceRelatedWithLookupvalue(unittest.TestCase):
    """Test _replace_related_with_lookupvalue string transformation."""

    def setUp(self):
        self._replace = _replace_related_with_lookupvalue

    def test_replaces_related_for_m2m_table(self):
        expr = "RELATED('Products'[Category])"
        m2m = {"Products": ("ProductID", "Orders", "ProductID")}
        result = self._replace(expr, m2m)
        self.assertIn("LOOKUPVALUE", result)
        self.assertIn("Products", result)
        self.assertIn("Category", result)
        self.assertNotIn("RELATED", result)

    def test_keeps_related_for_non_m2m_table(self):
        expr = "RELATED('Customers'[Name])"
        m2m = {"Products": ("ProductID", "Orders", "ProductID")}
        result = self._replace(expr, m2m)
        self.assertIn("RELATED", result)

    def test_multiple_related_calls(self):
        expr = "RELATED('Products'[Price]) + RELATED('Products'[Qty])"
        m2m = {"Products": ("ProductID", "Orders", "ProductID")}
        result = self._replace(expr, m2m)
        self.assertEqual(result.count("LOOKUPVALUE"), 2)
        self.assertNotIn("RELATED", result)

    def test_empty_expression(self):
        result = self._replace("", {})
        self.assertEqual(result, "")


class TestFixRelatedForManyToMany(unittest.TestCase):
    """Test _fix_related_for_many_to_many end-to-end pattern."""

    def setUp(self):
        self._fix = _fix_related_for_many_to_many

    def test_replaces_in_measures(self):
        model = {"model": {"tables": [
            {"name": "Orders", "columns": [], "measures": [
                {"name": "ProductCat", "expression": "RELATED('Products'[Category])"}
            ]},
            {"name": "Products", "columns": [], "measures": []},
        ], "relationships": [
            {"fromTable": "Orders", "fromColumn": "ProdID",
             "toTable": "Products", "toColumn": "ProdID",
             "fromCardinality": "many", "toCardinality": "many"}
        ]}}
        self._fix(model)
        expr = model["model"]["tables"][0]["measures"][0]["expression"]
        self.assertIn("LOOKUPVALUE", expr)
        self.assertNotIn("RELATED", expr)

    def test_no_m2m_no_change(self):
        model = {"model": {"tables": [
            {"name": "Orders", "columns": [], "measures": [
                {"name": "CustName", "expression": "RELATED('Customers'[Name])"}
            ]},
        ], "relationships": [
            {"fromTable": "Orders", "fromColumn": "CustID",
             "toTable": "Customers", "toColumn": "CustID",
             "fromCardinality": "many", "toCardinality": "one"}
        ]}}
        self._fix(model)
        expr = model["model"]["tables"][0]["measures"][0]["expression"]
        self.assertIn("RELATED", expr)


class TestInferCrossTableRelationships(unittest.TestCase):
    """Test _infer_cross_table_relationships."""

    def setUp(self):
        self._infer = _infer_cross_table_relationships

    def test_infers_from_measure_cross_ref(self):
        model = {"model": {
            "tables": [
                {"name": "Orders", "columns": [
                    {"name": "ProductID"}, {"name": "Amount"}
                ], "measures": [
                    {"name": "ProdName", "expression": "RELATED('Products'[Name])"}
                ]},
                {"name": "Products", "columns": [
                    {"name": "ProductID"}, {"name": "Name"}
                ], "measures": []},
            ],
            "relationships": [],
            "roles": [],
        }}
        self._infer(model)
        rels = model["model"]["relationships"]
        self.assertGreaterEqual(len(rels), 1, "Should infer a relationship")

    def test_no_inference_when_relationship_exists(self):
        model = {"model": {
            "tables": [
                {"name": "Orders", "columns": [
                    {"name": "ProductID"}
                ], "measures": [
                    {"name": "ProdName", "expression": "RELATED('Products'[Name])"}
                ]},
                {"name": "Products", "columns": [
                    {"name": "ProductID"}, {"name": "Name"}
                ], "measures": []},
            ],
            "relationships": [
                {"fromTable": "Orders", "fromColumn": "ProductID",
                 "toTable": "Products", "toColumn": "ProductID"}
            ],
            "roles": [],
        }}
        initial_count = len(model["model"]["relationships"])
        self._infer(model)
        self.assertEqual(len(model["model"]["relationships"]), initial_count)


# ═══════════════════════════════════════════════════════════════════
# Phase E — Coverage Tests for pbip_generator functions
# ═══════════════════════════════════════════════════════════════════


class TestCreateReportFilters(unittest.TestCase):
    """Test PBIPGenerator._create_report_filters."""

    def _make_generator(self):
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._field_map = {"Price": ("Products", "Price")}
        return gen

    def test_creates_filter_from_parameter(self):
        gen = self._make_generator()
        objs = {"parameters": [{"caption": "Price", "value": "100"}]}
        filters = gen._create_report_filters(objs)
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]["type"], "Categorical")

    def test_skips_param_without_value(self):
        gen = self._make_generator()
        objs = {"parameters": [{"caption": "Empty", "value": ""}]}
        filters = gen._create_report_filters(objs)
        self.assertEqual(len(filters), 0)

    def test_skips_param_without_name(self):
        gen = self._make_generator()
        objs = {"parameters": [{"value": "42"}]}
        filters = gen._create_report_filters(objs)
        self.assertEqual(len(filters), 0)

    def test_empty_parameters(self):
        gen = self._make_generator()
        filters = gen._create_report_filters({"parameters": []})
        self.assertEqual(len(filters), 0)


class TestCreateVisualTextbox(unittest.TestCase):
    """Test PBIPGenerator._create_visual_textbox writes valid JSON."""

    def _make_generator(self):
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        return gen

    def test_textbox_writes_json(self):
        gen = self._make_generator()
        with tempfile.TemporaryDirectory() as tmpdir:
            obj = {"position": {"x": 10, "y": 20, "w": 200, "h": 50}, "text": "Hello"}
            gen._create_visual_textbox(tmpdir, obj, 1.0, 1.0, 0)
            # Should create one visual directory with visual.json
            dirs = os.listdir(tmpdir)
            self.assertEqual(len(dirs), 1)
            vj = os.path.join(tmpdir, dirs[0], "visual.json")
            self.assertTrue(os.path.exists(vj))
            with open(vj, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["visual"]["visualType"], "textbox")


class TestCreateVisualImage(unittest.TestCase):
    """Test PBIPGenerator._create_visual_image writes valid JSON."""

    def _make_generator(self):
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        return gen

    def test_image_writes_json(self):
        gen = self._make_generator()
        with tempfile.TemporaryDirectory() as tmpdir:
            obj = {"position": {"x": 0, "y": 0, "w": 400, "h": 300}, "source": "https://example.com/img.png"}
            gen._create_visual_image(tmpdir, obj, 1.0, 1.0, 0)
            dirs = os.listdir(tmpdir)
            self.assertEqual(len(dirs), 1)
            vj = os.path.join(tmpdir, dirs[0], "visual.json")
            with open(vj, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["visual"]["visualType"], "image")


class TestCreatePaginatedReport(unittest.TestCase):
    """Test PBIPGenerator._create_paginated_report."""

    def _make_generator(self):
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._field_map = {}
        return gen

    def test_paginated_creates_directory(self):
        gen = self._make_generator()
        with tempfile.TemporaryDirectory() as tmpdir:
            converted = {
                "worksheets": [{"name": "Sheet1", "fields": []}],
                "datasources": [{"name": "ds1"}],
            }
            result = gen._create_paginated_report(tmpdir, "TestReport", converted)
            # Should return a path and create the directory
            self.assertTrue(os.path.isdir(result))


# ═══════════════════════════════════════════════════════════════════
# Non-Regression — Existing visual types still work
# ═══════════════════════════════════════════════════════════════════


class TestVisualTypeNonRegression(unittest.TestCase):
    """Verify that the Phase D changes don't break existing visual mappings."""

    def test_resolve_bar(self):
        self.assertEqual(resolve_visual_type("bar"), "clusteredBarChart")

    def test_resolve_line(self):
        self.assertEqual(resolve_visual_type("line"), "lineChart")

    def test_resolve_none(self):
        self.assertEqual(resolve_visual_type(None), "tableEx")

    def test_resolve_unknown(self):
        self.assertEqual(resolve_visual_type("nonexistent_xyz"), "tableEx")


if __name__ == '__main__':
    unittest.main()
