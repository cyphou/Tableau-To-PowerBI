"""
Tests for Sprint 51 — Semantic Model Merge Extensions.

Covers:
  - SQL normalization and hashing
  - Custom SQL fingerprinting
  - Fuzzy table name matching
  - RLS conflict detection
  - Cross-workbook relationship suggestion
  - Merge preview dry-run
  - HTML merge assessment report generation
  - Enhanced _remap_fields in ThinReportGenerator
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.shared_model import (
    _normalize_sql,
    _hash_sql,
    build_custom_sql_fingerprints,
    _normalize_table_name_fuzzy,
    fuzzy_table_match,
    detect_rls_conflicts,
    suggest_cross_workbook_relationships,
    merge_preview,
    assess_merge,
    merge_semantic_models,
)
from powerbi_import.merge_assessment import (
    generate_merge_html_report,
    generate_merge_report,
    print_merge_summary,
)


def _make_datasource(name, conn_type="postgres", tables=None, calcs=None, rels=None):
    return {
        "name": name,
        "connection": {"type": conn_type, "details": {"server": "localhost", "database": "testdb"}},
        "tables": tables or [],
        "calculations": calcs or [],
        "relationships": rels or [],
    }


def _make_table(name, columns, custom_sql=None):
    t = {
        "name": name,
        "type": "table",
        "columns": [{"name": c, "datatype": "string"} for c in columns],
    }
    if custom_sql:
        t["custom_sql"] = custom_sql
    return t


def _make_extracted(datasources=None, worksheets=None, calcs=None, user_filters=None, actions=None):
    return {
        "datasources": datasources or [],
        "worksheets": worksheets or [{"name": "Sheet1"}],
        "dashboards": [{"name": "Dash1"}],
        "calculations": calcs or [],
        "parameters": [],
        "filters": [],
        "actions": actions or [],
        "sets": [],
        "groups": [],
        "user_filters": user_filters or [],
    }


# ─── SQL normalization ───

class TestNormalizeSql(unittest.TestCase):
    def test_basic_normalization(self):
        sql = "  SELECT   *   FROM  orders  ;"
        result = _normalize_sql(sql)
        self.assertEqual(result, "select * from orders")

    def test_case_fold(self):
        self.assertEqual(_normalize_sql("SELECT Id FROM Users"), "select id from users")

    def test_collapse_whitespace(self):
        sql = "SELECT\n  id,\n  name\nFROM  users"
        result = _normalize_sql(sql)
        self.assertEqual(result, "select id, name from users")

    def test_strip_semicolons(self):
        self.assertEqual(_normalize_sql("SELECT 1;;"), "select 1")

    def test_empty_input(self):
        self.assertEqual(_normalize_sql(""), "")
        self.assertEqual(_normalize_sql(None), "")


class TestHashSql(unittest.TestCase):
    def test_deterministic(self):
        h1 = _hash_sql("SELECT * FROM t")
        h2 = _hash_sql("SELECT * FROM t")
        self.assertEqual(h1, h2)

    def test_case_insensitive(self):
        h1 = _hash_sql("SELECT * FROM t")
        h2 = _hash_sql("select * from t")
        self.assertEqual(h1, h2)

    def test_whitespace_insensitive(self):
        h1 = _hash_sql("SELECT * FROM t")
        h2 = _hash_sql("  SELECT  *  FROM  t  ;")
        self.assertEqual(h1, h2)

    def test_different_queries(self):
        h1 = _hash_sql("SELECT * FROM orders")
        h2 = _hash_sql("SELECT * FROM products")
        self.assertNotEqual(h1, h2)


class TestBuildCustomSqlFingerprints(unittest.TestCase):
    def test_single_custom_sql(self):
        ds = _make_datasource("DS", tables=[
            _make_table("custom", ["id", "val"], custom_sql="SELECT id, val FROM source"),
        ])
        result = build_custom_sql_fingerprints([ds])
        self.assertEqual(len(result), 1)
        key = list(result.keys())[0]
        sql_text, table, conn = result[key]
        self.assertIn("SELECT", sql_text)

    def test_duplicate_sql_deduplication(self):
        ds1 = _make_datasource("DS1", tables=[
            _make_table("t1", ["id"], custom_sql="SELECT id FROM src"),
        ])
        ds2 = _make_datasource("DS2", tables=[
            _make_table("t2", ["id"], custom_sql="SELECT id FROM src"),
        ])
        result = build_custom_sql_fingerprints([ds1, ds2])
        self.assertEqual(len(result), 1)  # Same SQL → same hash

    def test_no_custom_sql(self):
        ds = _make_datasource("DS", tables=[
            _make_table("t1", ["id"]),
        ])
        result = build_custom_sql_fingerprints([ds])
        self.assertEqual(len(result), 0)


# ─── Fuzzy table matching ───

class TestNormalizeTableNameFuzzy(unittest.TestCase):
    def test_strip_schema(self):
        self.assertEqual(_normalize_table_name_fuzzy("dbo.Orders"), "orders")

    def test_strip_brackets(self):
        self.assertEqual(_normalize_table_name_fuzzy("[dbo].[Orders]"), "orders")

    def test_remove_separators(self):
        self.assertEqual(_normalize_table_name_fuzzy("order_lines"), "orderlines")
        self.assertEqual(_normalize_table_name_fuzzy("order-lines"), "orderlines")
        self.assertEqual(_normalize_table_name_fuzzy("order lines"), "orderlines")

    def test_empty(self):
        self.assertEqual(_normalize_table_name_fuzzy(""), "")


class TestFuzzyTableMatch(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(fuzzy_table_match("orders", "orders"), 1.0)

    def test_case_insensitive(self):
        self.assertEqual(fuzzy_table_match("Orders", "ORDERS"), 1.0)

    def test_schema_prefix(self):
        self.assertEqual(fuzzy_table_match("dbo.Orders", "Orders"), 1.0)

    def test_containment(self):
        score = fuzzy_table_match("Order", "OrderDetails")
        self.assertGreater(score, 0.3)
        self.assertLess(score, 1.0)

    def test_bigram_similarity(self):
        score = fuzzy_table_match("CustomerOrders", "CustOrders")
        self.assertGreater(score, 0.0)

    def test_no_match(self):
        score = fuzzy_table_match("abc", "xyz")
        self.assertLess(score, 0.3)

    def test_empty_name(self):
        self.assertEqual(fuzzy_table_match("", "orders"), 0.0)
        self.assertEqual(fuzzy_table_match("orders", ""), 0.0)


# ─── RLS conflict detection ───

class TestDetectRlsConflicts(unittest.TestCase):
    def test_no_conflicts(self):
        ext = _make_extracted(user_filters=[
            {"name": "Region", "table": "Regions", "formula": "[Region] = USERNAME()"}
        ])
        result = detect_rls_conflicts([ext], ["WB1"])
        self.assertEqual(result, [])

    def test_same_expression_no_conflict(self):
        ext1 = _make_extracted(user_filters=[
            {"name": "Region", "table": "Regions", "formula": "[Region] = USERNAME()"}
        ])
        ext2 = _make_extracted(user_filters=[
            {"name": "Region", "table": "Regions", "formula": "[Region] = USERNAME()"}
        ])
        result = detect_rls_conflicts([ext1, ext2], ["WB1", "WB2"])
        self.assertEqual(result, [])

    def test_different_expression_conflict(self):
        ext1 = _make_extracted(user_filters=[
            {"name": "Region", "table": "regions", "formula": "[Region] = 'East'"}
        ])
        ext2 = _make_extracted(user_filters=[
            {"name": "Region", "table": "regions", "formula": "[Region] = 'West'"}
        ])
        result = detect_rls_conflicts([ext1, ext2], ["WB1", "WB2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['role_name'], "Region")
        self.assertIn("WB1", result[0]['variants'])
        self.assertIn("WB2", result[0]['variants'])

    def test_list_values_handled(self):
        ext1 = _make_extracted(user_filters=[
            {"name": "Region", "table": "t", "values": ["East", "Central"]}
        ])
        ext2 = _make_extracted(user_filters=[
            {"name": "Region", "table": "t", "values": ["West"]}
        ])
        result = detect_rls_conflicts([ext1, ext2], ["WB1", "WB2"])
        self.assertEqual(len(result), 1)


# ─── Cross-workbook relationship suggestions ───

class TestSuggestCrossWorkbookRelationships(unittest.TestCase):
    def test_suggest_matching_id_columns(self):
        merged = {
            "datasources": [{
                "tables": [
                    _make_table("orders", ["order_id", "customer_id", "amount"]),
                    _make_table("customers", ["customer_id", "name"]),
                ],
                "relationships": [],
            }],
        }
        suggestions = suggest_cross_workbook_relationships(merged)
        self.assertGreater(len(suggestions), 0)
        cols = [s['from_column'] for s in suggestions]
        self.assertIn("customer_id", cols)

    def test_skip_existing_relationship(self):
        merged = {
            "datasources": [{
                "tables": [
                    _make_table("orders", ["order_id", "customer_id"]),
                    _make_table("customers", ["customer_id", "name"]),
                ],
                "relationships": [{
                    "from_table": "orders",
                    "to_table": "customers",
                    "from_column": "customer_id",
                    "to_column": "customer_id",
                }],
            }],
        }
        suggestions = suggest_cross_workbook_relationships(merged)
        # customer_id already has a relationship, should be skipped
        customer_id_suggestions = [s for s in suggestions if s['from_column'] == 'customer_id']
        self.assertEqual(len(customer_id_suggestions), 0)

    def test_no_key_columns(self):
        merged = {
            "datasources": [{
                "tables": [
                    _make_table("t1", ["name", "age"]),
                    _make_table("t2", ["city", "state"]),
                ],
                "relationships": [],
            }],
        }
        suggestions = suggest_cross_workbook_relationships(merged)
        self.assertEqual(len(suggestions), 0)

    def test_high_confidence_for_id_suffix(self):
        merged = {
            "datasources": [{
                "tables": [
                    _make_table("orders", ["product_id"]),
                    _make_table("products", ["product_id", "name"]),
                ],
                "relationships": [],
            }],
        }
        suggestions = suggest_cross_workbook_relationships(merged)
        id_suggestions = [s for s in suggestions if s['from_column'] == 'product_id']
        self.assertTrue(len(id_suggestions) > 0)
        self.assertEqual(id_suggestions[0]['confidence'], 'high')


# ─── Merge preview ───

class TestMergePreview(unittest.TestCase):
    def test_basic_preview(self):
        ds1 = _make_datasource("DS1", tables=[
            _make_table("orders", ["order_id", "amount", "customer_id"]),
        ])
        ds2 = _make_datasource("DS2", tables=[
            _make_table("orders", ["order_id", "amount", "date"]),
        ])
        ext1 = _make_extracted(datasources=[ds1])
        ext2 = _make_extracted(datasources=[ds2])

        result = merge_preview([ext1, ext2], ["WB1", "WB2"])
        self.assertIn('assessment', result)
        self.assertIn('rls_conflicts', result)
        self.assertIn('relationship_suggestions', result)
        self.assertIn('actions', result)
        self.assertIn('total_actions', result)
        self.assertIsInstance(result['total_actions'], int)

    def test_preview_with_rls(self):
        ds = _make_datasource("DS", tables=[_make_table("t", ["id"])])
        ext1 = _make_extracted(
            datasources=[ds],
            user_filters=[{"name": "R", "table": "t", "formula": "X"}],
        )
        ext2 = _make_extracted(
            datasources=[ds],
            user_filters=[{"name": "R", "table": "t", "formula": "Y"}],
        )
        result = merge_preview([ext1, ext2], ["WB1", "WB2"])
        self.assertEqual(len(result['rls_conflicts']), 1)


# ─── HTML merge report ───

class TestMergeHtmlReport(unittest.TestCase):
    def test_generate_html_report(self):
        ds1 = _make_datasource("DS", tables=[
            _make_table("orders", ["id", "amount"]),
        ])
        ds2 = _make_datasource("DS", tables=[
            _make_table("orders", ["id", "amount", "date"]),
        ])
        ext1 = _make_extracted(datasources=[ds1])
        ext2 = _make_extracted(datasources=[ds2])
        assessment = assess_merge([ext1, ext2], ["WB1", "WB2"])

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'merge.html')
            out = generate_merge_html_report(assessment, path)
            self.assertTrue(os.path.exists(out))
            with open(out, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Merge Assessment', html)
            self.assertIn('orders', html)

    def test_html_with_rls_conflicts(self):
        ds = _make_datasource("DS", tables=[_make_table("t", ["id"])])
        ext1 = _make_extracted(datasources=[ds])
        ext2 = _make_extracted(datasources=[ds])
        assessment = assess_merge([ext1, ext2], ["WB1", "WB2"])

        rls_conflicts = [{"role_name": "TestRole", "table": "t", "variants": {"WB1": "X", "WB2": "Y"}}]
        rel_suggestions = [{"from_table": "a", "from_column": "aid", "to_table": "b", "to_column": "aid", "confidence": "high"}]

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'merge.html')
            generate_merge_html_report(assessment, path, rls_conflicts, rel_suggestions)
            with open(path, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('TestRole', html)
            self.assertIn('Suggested Relationships', html)


# ─── Enhanced _remap_fields ───

class TestRemapFieldsEnhanced(unittest.TestCase):
    """Test the enhanced _remap_fields method in ThinReportGenerator."""

    def _get_generator(self):
        from powerbi_import.thin_report_generator import ThinReportGenerator
        return ThinReportGenerator.__new__(ThinReportGenerator)

    def test_remap_list_mark_encoding(self):
        gen = self._get_generator()
        converted = {
            "worksheets": [{
                "name": "S1",
                "columns": [],
                "filters": [],
                "mark_encoding": {
                    "color": [
                        {"field": "Sales", "type": "quantitative"},
                        {"field": "Profit", "type": "quantitative"},
                    ],
                },
                "sort_fields": [],
            }],
            "calculations": [],
            "filters": [],
            "actions": [],
        }
        mapping = {"Sales": "Sales (WB1)"}
        result = gen._remap_fields(converted, mapping)
        colors = result['worksheets'][0]['mark_encoding']['color']
        self.assertEqual(colors[0]['field'], "Sales (WB1)")
        self.assertEqual(colors[1]['field'], "Profit")  # unchanged

    def test_remap_dict_mark_encoding(self):
        gen = self._get_generator()
        converted = {
            "worksheets": [{
                "name": "S1",
                "columns": [],
                "filters": [],
                "mark_encoding": {
                    "color": {"field": "Sales", "type": "quantitative"},
                },
                "sort_fields": [],
            }],
            "calculations": [],
            "filters": [],
            "actions": [],
        }
        mapping = {"Sales": "Sales (WB1)"}
        result = gen._remap_fields(converted, mapping)
        self.assertEqual(result['worksheets'][0]['mark_encoding']['color']['field'], "Sales (WB1)")

    def test_remap_sort_fields(self):
        gen = self._get_generator()
        converted = {
            "worksheets": [{
                "name": "S1",
                "columns": [],
                "filters": [],
                "mark_encoding": {},
                "sort_fields": [{"field": "Revenue", "direction": "asc"}],
            }],
            "calculations": [],
            "filters": [],
            "actions": [],
        }
        mapping = {"Revenue": "Revenue (WB1)"}
        result = gen._remap_fields(converted, mapping)
        self.assertEqual(result['worksheets'][0]['sort_fields'][0]['field'], "Revenue (WB1)")

    def test_remap_action_target_fields(self):
        gen = self._get_generator()
        converted = {
            "worksheets": [{"name": "S1", "columns": [], "filters": [], "mark_encoding": {}}],
            "calculations": [],
            "filters": [],
            "actions": [
                {"type": "filter", "source_field": "Region", "target_field": "Zone", "field": "Region"},
            ],
        }
        mapping = {"Region": "Region (WB1)"}
        result = gen._remap_fields(converted, mapping)
        self.assertEqual(result['actions'][0]['source_field'], "Region (WB1)")
        self.assertEqual(result['actions'][0]['field'], "Region (WB1)")
        self.assertEqual(result['actions'][0]['target_field'], "Zone")  # not in mapping

    def test_empty_mapping_returns_same(self):
        gen = self._get_generator()
        converted = {"worksheets": [], "calculations": [], "filters": [], "actions": []}
        result = gen._remap_fields(converted, {})
        self.assertEqual(result, converted)


if __name__ == '__main__':
    unittest.main()
