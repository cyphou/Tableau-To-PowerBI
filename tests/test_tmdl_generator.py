"""
Unit tests for tmdl_generator.py — TMDL semantic model generation.

Tests utility functions, semantic model building, Calendar table,
perspectives, cultures, theme, and TMDL file writers.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.tmdl_generator import (
    _quote_name,
    _tmdl_datatype,
    _tmdl_summarize,
    _safe_filename,
    _get_format_string,
    _get_display_folder,
    _map_semantic_role_to_category,
    generate_theme_json,
    _build_semantic_model,
    _add_date_table,
    _write_tmdl_files,
    _write_perspectives_tmdl,
    _write_culture_tmdl,
    _write_database_tmdl,
    _write_model_tmdl,
    _write_relationships_tmdl,
    _write_table_tmdl,
    generate_tmdl,
)


# ═══════════════════════════════════════════════════════════════════════
# Utility Functions (Pure — No I/O)
# ═══════════════════════════════════════════════════════════════════════

class TestQuoteName(unittest.TestCase):
    """Test _quote_name for TMDL identifier quoting."""

    def test_simple_name_no_quoting(self):
        self.assertEqual(_quote_name("Sales"), "Sales")

    def test_name_with_underscore(self):
        self.assertEqual(_quote_name("order_id"), "order_id")

    def test_name_with_spaces(self):
        self.assertEqual(_quote_name("Sales Data"), "'Sales Data'")

    def test_name_with_apostrophe(self):
        self.assertEqual(_quote_name("O'Brien"), "'O''Brien'")

    def test_name_with_special_chars(self):
        self.assertEqual(_quote_name("Sales (2024)"), "'Sales (2024)'")

    def test_name_with_hyphen(self):
        self.assertEqual(_quote_name("fact-table"), "'fact-table'")

    def test_name_with_dots(self):
        self.assertEqual(_quote_name("dbo.Sales"), "'dbo.Sales'")

    def test_empty_string(self):
        result = _quote_name("")
        self.assertEqual(result, "")

    def test_numeric_only(self):
        self.assertEqual(_quote_name("123"), "123")


class TestTmdlDatatype(unittest.TestCase):
    """Test _tmdl_datatype type mapping."""

    def test_int64_capitals(self):
        self.assertEqual(_tmdl_datatype("Int64"), "int64")

    def test_int64_lowercase(self):
        self.assertEqual(_tmdl_datatype("int64"), "int64")

    def test_string(self):
        self.assertEqual(_tmdl_datatype("String"), "string")

    def test_double(self):
        self.assertEqual(_tmdl_datatype("Double"), "double")

    def test_datetime(self):
        self.assertEqual(_tmdl_datatype("DateTime"), "dateTime")

    def test_boolean(self):
        self.assertEqual(_tmdl_datatype("Boolean"), "boolean")

    def test_decimal(self):
        self.assertEqual(_tmdl_datatype("Decimal"), "decimal")

    def test_binary(self):
        self.assertEqual(_tmdl_datatype("Binary"), "binary")

    def test_unknown_defaults_to_string(self):
        self.assertEqual(_tmdl_datatype("SomeUnknownType"), "string")

    def test_empty_defaults_to_string(self):
        self.assertEqual(_tmdl_datatype(""), "string")


class TestTmdlSummarize(unittest.TestCase):
    """Test _tmdl_summarize mapping."""

    def test_sum(self):
        self.assertEqual(_tmdl_summarize("sum"), "sum")

    def test_none(self):
        self.assertEqual(_tmdl_summarize("none"), "none")

    def test_count(self):
        self.assertEqual(_tmdl_summarize("count"), "count")

    def test_unknown_defaults_to_none(self):
        self.assertEqual(_tmdl_summarize("unknown"), "none")

    def test_mixed_case(self):
        self.assertEqual(_tmdl_summarize("SUM"), "sum")


class TestSafeFilename(unittest.TestCase):
    """Test _safe_filename for stripping forbidden chars."""

    def test_normal_name(self):
        self.assertEqual(_safe_filename("Sales"), "Sales")

    def test_name_with_slash(self):
        self.assertEqual(_safe_filename("Sales/Data"), "Sales_Data")

    def test_name_with_colon(self):
        self.assertEqual(_safe_filename("Col:Name"), "Col_Name")

    def test_name_with_question_mark(self):
        self.assertEqual(_safe_filename("Sales?"), "Sales_")

    def test_name_with_all_forbidden(self):
        result = _safe_filename('<>:"/\\|?*')
        self.assertNotIn('<', result)
        self.assertNotIn('>', result)
        self.assertNotIn(':', result)
        self.assertNotIn('"', result)
        self.assertNotIn('/', result)
        self.assertNotIn('|', result)
        self.assertNotIn('?', result)
        self.assertNotIn('*', result)


class TestGetFormatString(unittest.TestCase):
    """Test _get_format_string format mapping."""

    def test_integer(self):
        self.assertEqual(_get_format_string("integer"), "0")

    def test_real(self):
        self.assertEqual(_get_format_string("real"), "#,0.00")

    def test_date(self):
        self.assertEqual(_get_format_string("date"), "Short Date")

    def test_datetime(self):
        self.assertEqual(_get_format_string("datetime"), "General Date")

    def test_boolean(self):
        self.assertEqual(_get_format_string("boolean"), "True/False")

    def test_percentage(self):
        self.assertEqual(_get_format_string("percentage"), "0.00%")

    def test_currency(self):
        self.assertEqual(_get_format_string("currency"), "$#,0.00")

    def test_unknown_defaults_to_zero(self):
        self.assertEqual(_get_format_string("unknown"), "0")


class TestGetDisplayFolder(unittest.TestCase):
    """Test _get_display_folder folder assignment."""

    def test_dimension_role(self):
        self.assertEqual(_get_display_folder("string", "dimension"), "Dimensions")

    def test_real_type(self):
        self.assertEqual(_get_display_folder("real", "measure"), "Measures")

    def test_integer_type(self):
        self.assertEqual(_get_display_folder("integer", ""), "Measures")

    def test_date_type(self):
        self.assertEqual(_get_display_folder("date", ""), "Time Intelligence")

    def test_datetime_type(self):
        self.assertEqual(_get_display_folder("datetime", ""), "Time Intelligence")

    def test_boolean_type(self):
        self.assertEqual(_get_display_folder("boolean", ""), "Flags")

    def test_string_defaults_to_calculations(self):
        self.assertEqual(_get_display_folder("string", ""), "Calculations")


class TestMapSemanticRole(unittest.TestCase):
    """Test _map_semantic_role_to_category geo role mapping."""

    def test_city_role(self):
        self.assertEqual(_map_semantic_role_to_category("[City].[Name]"), "City")

    def test_country_role(self):
        self.assertEqual(_map_semantic_role_to_category("[Country].[Name]"), "Country")

    def test_state_role(self):
        self.assertEqual(_map_semantic_role_to_category("[State].[Name]"), "StateOrProvince")

    def test_latitude_role(self):
        self.assertEqual(_map_semantic_role_to_category("[Latitude]"), "Latitude")

    def test_longitude_role(self):
        self.assertEqual(_map_semantic_role_to_category("[Longitude]"), "Longitude")

    def test_zipcode_role(self):
        self.assertEqual(_map_semantic_role_to_category("[ZipCode].[Name]"), "PostalCode")

    def test_no_role_city_col_name(self):
        self.assertEqual(_map_semantic_role_to_category("", "city"), "City")

    def test_no_role_latitude_col_name(self):
        self.assertEqual(_map_semantic_role_to_category("", "latitude"), "Latitude")

    def test_no_role_longitude_col_name(self):
        self.assertEqual(_map_semantic_role_to_category("", "lng"), "Longitude")

    def test_no_role_country_col_name(self):
        self.assertEqual(_map_semantic_role_to_category("", "country"), "Country")

    def test_no_role_postal_code_col_name(self):
        self.assertEqual(_map_semantic_role_to_category("", "postal_code"), "PostalCode")

    def test_no_role_zip_code_col_name(self):
        self.assertEqual(_map_semantic_role_to_category("", "zip"), "PostalCode")

    def test_no_role_region_col_name(self):
        self.assertEqual(_map_semantic_role_to_category("", "region"), "StateOrProvince")

    def test_no_match_returns_none(self):
        self.assertIsNone(_map_semantic_role_to_category("", "order_id"))

    def test_empty_both_returns_none(self):
        self.assertIsNone(_map_semantic_role_to_category(""))


# ═══════════════════════════════════════════════════════════════════════
# Theme Generation
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateThemeJson(unittest.TestCase):
    """Test generate_theme_json theme builder."""

    def test_default_theme(self):
        theme = generate_theme_json()
        self.assertEqual(theme["name"], "Tableau Migration Theme")
        self.assertIn("dataColors", theme)
        self.assertEqual(len(theme["dataColors"]), 12)
        self.assertIn("textClasses", theme)
        self.assertIn("callout", theme["textClasses"])

    def test_custom_colors(self):
        theme = generate_theme_json({"colors": ["#FF0000", "#00FF00", "#0000FF"]})
        self.assertTrue(len(theme["dataColors"]) >= 3)
        self.assertIn("#FF0000", theme["dataColors"])

    def test_custom_font(self):
        theme = generate_theme_json({"font_family": "Arial"})
        self.assertEqual(theme["textClasses"]["callout"]["fontFace"], "Arial")

    def test_none_input(self):
        theme = generate_theme_json(None)
        self.assertIsInstance(theme, dict)
        self.assertIn("dataColors", theme)

    def test_empty_dict(self):
        theme = generate_theme_json({})
        self.assertIsInstance(theme, dict)
        self.assertEqual(len(theme["dataColors"]), 12)


# ═══════════════════════════════════════════════════════════════════════
# Semantic Model Building
# ═══════════════════════════════════════════════════════════════════════

class TestBuildSemanticModel(unittest.TestCase):
    """Test _build_semantic_model model creation."""

    def _build(self, *args, **kwargs):
        """Wrapper that redirects stdout to avoid cp1252 Unicode errors."""
        old_stdout = sys.stdout
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
        try:
            return _build_semantic_model(*args, **kwargs)
        finally:
            sys.stdout = old_stdout

    def _make_datasource(self, tables=None, calculations=None, relationships=None):
        """Helper to build a minimal datasource dict."""
        return {
            "name": "TestDS",
            "caption": "Test Datasource",
            "connection": {"type": "CSV", "details": {"filename": "test.csv"}},
            "tables": tables or [],
            "calculations": calculations or [],
            "columns": [],
            "relationships": relationships or [],
            "connection_map": {},
        }

    def _make_table(self, name="Orders", columns=None):
        """Helper to build a minimal table dict."""
        return {
            "name": name,
            "type": "table",
            "columns": columns or [
                {"name": "OrderID", "datatype": "integer"},
                {"name": "Amount", "datatype": "real"},
                {"name": "Date", "datatype": "datetime"},
            ],
        }

    def test_empty_datasources(self):
        model = self._build([], report_name="Empty")
        self.assertEqual(model["name"], "Empty")
        self.assertIn("model", model)

    def test_single_table(self):
        ds = self._make_datasource(tables=[self._make_table()])
        model = self._build([ds], report_name="Test")
        tables = model["model"]["tables"]
        # Should have Orders + Calendar (auto-generated from DateTime column)
        table_names = [t["name"] for t in tables]
        self.assertIn("Orders", table_names)

    def test_multiple_tables(self):
        ds = self._make_datasource(tables=[
            self._make_table("Orders"),
            self._make_table("Products", [
                {"name": "ProductID", "datatype": "integer"},
                {"name": "ProductName", "datatype": "string"},
            ]),
        ])
        model = self._build([ds])
        table_names = [t["name"] for t in model["model"]["tables"]]
        self.assertIn("Orders", table_names)
        self.assertIn("Products", table_names)

    def test_calculations_become_measures(self):
        ds = self._make_datasource(
            tables=[self._make_table()],
            calculations=[{
                "name": "[Calculation_001]",
                "caption": "Total Sales",
                "formula": "SUM([Amount])",
                "role": "measure",
                "datatype": "real",
            }],
        )
        model = self._build([ds])
        # Find the measure in the first table
        orders = [t for t in model["model"]["tables"] if t["name"] == "Orders"][0]
        measure_names = [m["name"] for m in orders.get("measures", [])]
        self.assertIn("Total Sales", measure_names)

    def test_date_table_auto_generated(self):
        ds = self._make_datasource(tables=[self._make_table()])
        model = self._build([ds])
        table_names = [t["name"] for t in model["model"]["tables"]]
        self.assertIn("Calendar", table_names)

    def test_no_date_table_if_no_datetime(self):
        ds = self._make_datasource(tables=[
            self._make_table("Products", [
                {"name": "ProductID", "datatype": "integer"},
                {"name": "ProductName", "datatype": "string"},
            ]),
        ])
        model = self._build([ds])
        table_names = [t["name"] for t in model["model"]["tables"]]
        self.assertNotIn("Calendar", table_names)

    def test_perspectives_auto_generated(self):
        ds = self._make_datasource(tables=[
            self._make_table("Orders"),
            self._make_table("Products", [
                {"name": "ProductID", "datatype": "integer"},
            ]),
        ])
        model = self._build([ds])
        perspectives = model["model"].get("perspectives", [])
        self.assertTrue(len(perspectives) >= 1)
        self.assertEqual(perspectives[0]["name"], "Full Model")

    def test_relationships_from_datasource(self):
        ds = self._make_datasource(
            tables=[
                self._make_table("Orders"),
                self._make_table("Customers", [
                    {"name": "CustomerID", "datatype": "integer"},
                    {"name": "Name", "datatype": "string"},
                ]),
            ],
            relationships=[{
                "join_type": "left",
                "from_table": "Orders",
                "to_table": "Customers",
                "from_column": "CustomerID",
                "to_column": "CustomerID",
                "raw_from_count": 1000,
                "raw_to_count": 100,
            }],
        )
        model = self._build([ds])
        rels = model["model"]["relationships"]
        # Should have at least the explicit relationship (+ possibly Calendar)
        self.assertTrue(len(rels) >= 1)

    def test_duplicate_table_deduplication(self):
        ds = self._make_datasource(tables=[
            self._make_table("Orders"),
            self._make_table("Orders"),  # duplicate
        ])
        model = self._build([ds])
        order_tables = [t for t in model["model"]["tables"] if t["name"] == "Orders"]
        self.assertEqual(len(order_tables), 1)


# ═══════════════════════════════════════════════════════════════════════
# Calendar / Date Table
# ═══════════════════════════════════════════════════════════════════════

class TestAddDateTable(unittest.TestCase):
    """Test _add_date_table Calendar auto-generation."""

    def test_adds_calendar_for_datetime_column(self):
        model = {
            "model": {
                "tables": [{
                    "name": "Sales",
                    "columns": [
                        {"name": "Date", "dataType": "dateTime", "sourceColumn": "Date"},
                        {"name": "Amount", "dataType": "double", "sourceColumn": "Amount"},
                    ],
                    "partitions": [],
                    "measures": [],
                }],
                "relationships": [],
            }
        }
        _add_date_table(model)
        table_names = [t["name"] for t in model["model"]["tables"]]
        self.assertIn("Calendar", table_names)

    def test_calendar_has_sortbycolumn(self):
        model = {
            "model": {
                "tables": [{
                    "name": "Sales",
                    "columns": [
                        {"name": "Date", "dataType": "dateTime", "sourceColumn": "Date"},
                    ],
                    "partitions": [],
                    "measures": [],
                }],
                "relationships": [],
            }
        }
        _add_date_table(model)
        cal = [t for t in model["model"]["tables"] if t["name"] == "Calendar"][0]
        month_name_col = [c for c in cal["columns"] if c["name"] == "MonthName"][0]
        day_name_col = [c for c in cal["columns"] if c["name"] == "DayName"][0]
        self.assertEqual(month_name_col.get("sortByColumn"), "Month")
        self.assertEqual(day_name_col.get("sortByColumn"), "DayOfWeek")

    def test_calendar_has_iskey(self):
        model = {
            "model": {
                "tables": [{
                    "name": "Sales",
                    "columns": [
                        {"name": "Date", "dataType": "dateTime", "sourceColumn": "Date"},
                    ],
                    "partitions": [],
                    "measures": [],
                }],
                "relationships": [],
            }
        }
        _add_date_table(model)
        cal = [t for t in model["model"]["tables"] if t["name"] == "Calendar"][0]
        date_col = [c for c in cal["columns"] if c["name"] == "Date"][0]
        self.assertTrue(date_col.get("isKey"))

    def test_calendar_creates_relationship(self):
        model = {
            "model": {
                "tables": [{
                    "name": "Sales",
                    "columns": [
                        {"name": "OrderDate", "dataType": "DateTime", "sourceColumn": "OrderDate"},
                    ],
                    "partitions": [],
                    "measures": [],
                }],
                "relationships": [],
            }
        }
        _add_date_table(model)
        rels = model["model"]["relationships"]
        cal_rels = [r for r in rels if "Calendar" in r.get("toTable", "")]
        self.assertTrue(len(cal_rels) >= 1)

    def test_no_calendar_relationship_without_datetime(self):
        """_add_date_table always adds Calendar, but no relationship without DateTime cols."""
        model = {
            "model": {
                "tables": [{
                    "name": "Products",
                    "columns": [
                        {"name": "Name", "dataType": "string", "sourceColumn": "Name"},
                    ],
                    "partitions": [],
                    "measures": [],
                }],
                "relationships": [],
            }
        }
        _add_date_table(model)
        # Calendar table is always added by _add_date_table
        table_names = [t["name"] for t in model["model"]["tables"]]
        self.assertIn("Calendar", table_names)
        # But no relationship should be created (no DateTime columns in Products)
        cal_rels = [r for r in model["model"]["relationships"] if "Calendar" in r.get("toTable", "")]
        self.assertEqual(len(cal_rels), 0)


# ═══════════════════════════════════════════════════════════════════════
# TMDL File Writers (I/O — uses temp dirs)
# ═══════════════════════════════════════════════════════════════════════

class TestTmdlFileWriters(unittest.TestCase):
    """Test TMDL file writing functions."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_perspectives_tmdl(self):
        perspectives = [{"name": "Full Model", "tables": ["Orders", "Products"]}]
        _write_perspectives_tmdl(self.tmpdir, perspectives)
        path = os.path.join(self.tmpdir, "perspectives.tmdl")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("perspective", content)
        self.assertIn("perspectiveTable Orders", content)
        self.assertIn("perspectiveTable Products", content)

    def test_write_perspectives_with_special_names(self):
        perspectives = [{"name": "Full Model", "tables": ["Sales Data", "O'Brien"]}]
        _write_perspectives_tmdl(self.tmpdir, perspectives)
        path = os.path.join(self.tmpdir, "perspectives.tmdl")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("'Sales Data'", content)
        self.assertIn("'O''Brien'", content)

    def test_write_culture_tmdl(self):
        tables = [{"name": "Orders", "columns": [{"name": "Amount"}]}]
        _write_culture_tmdl(self.tmpdir, "fr-FR", tables)
        path = os.path.join(self.tmpdir, "fr-FR.tmdl")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("culture", content)
        self.assertIn("fr-FR", content)
        self.assertIn("linguisticMetadata", content)

    def test_write_database_tmdl(self):
        _write_database_tmdl(self.tmpdir, {"compatibilityLevel": 1600})
        path = os.path.join(self.tmpdir, "database.tmdl")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("database", content)
        self.assertIn("1600", content)

    def test_write_database_upgrades_compat_level(self):
        _write_database_tmdl(self.tmpdir, {"compatibilityLevel": 1400})
        with open(os.path.join(self.tmpdir, "database.tmdl"), "r") as f:
            content = f.read()
        # Should be clamped to at least 1600
        self.assertIn("1600", content)

    def test_write_model_tmdl_basic(self):
        model = {"culture": "en-US"}
        tables = [{"name": "Orders"}, {"name": "Products"}]
        _write_model_tmdl(self.tmpdir, model, tables)
        path = os.path.join(self.tmpdir, "model.tmdl")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("model Model", content)
        self.assertIn("ref table Orders", content)
        self.assertIn("ref table Products", content)

    def test_write_model_tmdl_with_roles(self):
        model = {"culture": "en-US"}
        tables = [{"name": "Orders"}]
        roles = [{"name": "Admin"}]
        _write_model_tmdl(self.tmpdir, model, tables, roles=roles)
        with open(os.path.join(self.tmpdir, "model.tmdl"), "r") as f:
            content = f.read()
        self.assertIn("ref role Admin", content)

    def test_write_model_tmdl_with_perspectives(self):
        model = {"culture": "en-US", "perspectives": [{"name": "Full Model"}]}
        tables = [{"name": "Orders"}]
        _write_model_tmdl(self.tmpdir, model, tables)
        with open(os.path.join(self.tmpdir, "model.tmdl"), "r") as f:
            content = f.read()
        self.assertIn("ref perspective", content)

    def test_write_model_tmdl_with_culture_ref(self):
        model = {"culture": "fr-FR"}
        tables = [{"name": "Orders"}]
        _write_model_tmdl(self.tmpdir, model, tables)
        with open(os.path.join(self.tmpdir, "model.tmdl"), "r") as f:
            content = f.read()
        self.assertIn("ref culture", content)

    def test_write_relationships_tmdl(self):
        rels = [{
            "name": "rel_1",
            "fromTable": "Orders",
            "fromColumn": "ProductID",
            "toTable": "Products",
            "toColumn": "ProductID",
            "crossFilteringBehavior": "oneDirection",
            "cardinality": "manyToOne",
        }]
        _write_relationships_tmdl(self.tmpdir, rels)
        path = os.path.join(self.tmpdir, "relationships.tmdl")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("relationship", content)
        self.assertIn("Orders", content)
        self.assertIn("Products", content)

    def test_write_table_tmdl(self):
        table = {
            "name": "Orders",
            "lineageTag": "test-tag",
            "columns": [{
                "name": "OrderID",
                "dataType": "int64",
                "sourceColumn": "OrderID",
                "lineageTag": "col-tag",
                "summarizeBy": "none",
            }],
            "measures": [{
                "name": "Total Sales",
                "lineageTag": "meas-tag",
                "expression": "SUM('Orders'[Amount])",
            }],
            "partitions": [{
                "source": {"type": "m", "expression": "let\n    Source = null\nin\n    Source"},
                "mode": "import",
            }],
            "hierarchies": [],
        }
        tables_dir = os.path.join(self.tmpdir, "tables")
        os.makedirs(tables_dir, exist_ok=True)
        _write_table_tmdl(tables_dir, table)
        path = os.path.join(tables_dir, "Orders.tmdl")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("table Orders", content)
        self.assertIn("column OrderID", content)
        self.assertIn("measure 'Total Sales'", content)

    def test_write_tmdl_files_full(self):
        model_data = {
            "model": {
                "culture": "fr-FR",
                "compatibilityLevel": 1567,
                "tables": [{
                    "name": "Sales",
                    "lineageTag": "t1",
                    "columns": [{
                        "name": "Amount",
                        "dataType": "double",
                        "sourceColumn": "Amount",
                        "lineageTag": "c1",
                        "summarizeBy": "sum",
                    }],
                    "measures": [],
                    "partitions": [{"source": {"type": "m", "expression": "let\n    Source = null\nin\n    Source"}, "mode": "import"}],
                    "hierarchies": [],
                }],
                "relationships": [],
                "roles": [],
                "perspectives": [{"name": "Full Model", "tables": ["Sales"]}],
            }
        }
        def_dir = _write_tmdl_files(model_data, self.tmpdir)

        # Check all expected files exist
        self.assertTrue(os.path.exists(os.path.join(def_dir, "database.tmdl")))
        self.assertTrue(os.path.exists(os.path.join(def_dir, "model.tmdl")))
        self.assertTrue(os.path.exists(os.path.join(def_dir, "relationships.tmdl")))
        self.assertTrue(os.path.exists(os.path.join(def_dir, "expressions.tmdl")))
        self.assertTrue(os.path.exists(os.path.join(def_dir, "diagramLayout.json")))
        self.assertTrue(os.path.exists(os.path.join(def_dir, "perspectives.tmdl")))
        self.assertTrue(os.path.exists(os.path.join(def_dir, "tables", "Sales.tmdl")))

        # Check culture file
        culture_path = os.path.join(def_dir, "cultures", "fr-FR.tmdl")
        self.assertTrue(os.path.exists(culture_path))

        # Check diagramLayout is empty JSON
        with open(os.path.join(def_dir, "diagramLayout.json"), "r") as f:
            self.assertEqual(json.load(f), {})


# ═══════════════════════════════════════════════════════════════════════
# generate_tmdl Integration Test
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateTmdl(unittest.TestCase):
    """Integration test for generate_tmdl entry point."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _generate(self, *args, **kwargs):
        """Wrapper that redirects stdout to avoid cp1252 Unicode errors."""
        old_stdout = sys.stdout
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
        try:
            return generate_tmdl(*args, **kwargs)
        finally:
            sys.stdout = old_stdout

    def test_generates_valid_output(self):
        datasources = [{
            "name": "TestDS",
            "caption": "Test",
            "connection": {"type": "CSV", "details": {"filename": "test.csv"}},
            "tables": [{
                "name": "Orders",
                "type": "table",
                "columns": [
                    {"name": "OrderID", "datatype": "integer"},
                    {"name": "Amount", "datatype": "real"},
                ],
            }],
            "calculations": [],
            "columns": [],
            "relationships": [],
            "connection_map": {},
        }]
        stats = self._generate(datasources, "TestReport", None, self.tmpdir)
        self.assertIsInstance(stats, dict)
        self.assertIn("tables", stats)
        self.assertGreaterEqual(stats["tables"], 1)

    def test_stats_include_all_counts(self):
        datasources = [{
            "name": "DS",
            "caption": "DS",
            "connection": {"type": "CSV", "details": {"filename": "data.csv"}},
            "tables": [{
                "name": "T1",
                "type": "table",
                "columns": [
                    {"name": "ID", "datatype": "integer"},
                    {"name": "Val", "datatype": "real"},
                ],
            }],
            "calculations": [{
                "name": "[Calculation_1]",
                "caption": "TotalVal",
                "formula": "SUM([Val])",
                "role": "measure",
                "datatype": "real",
            }],
            "columns": [],
            "relationships": [],
            "connection_map": {},
        }]
        stats = self._generate(datasources, "Test", None, self.tmpdir)
        for key in ["tables", "columns", "measures", "relationships"]:
            self.assertIn(key, stats)


if __name__ == '__main__':
    unittest.main(verbosity=2)
