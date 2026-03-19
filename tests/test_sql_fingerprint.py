"""Unit tests for SQL normalization and custom SQL fingerprinting."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.shared_model import (
    _normalize_sql,
    _hash_sql,
    build_table_fingerprints,
    build_custom_sql_fingerprints,
)


class TestNormalizeSql(unittest.TestCase):
    """Test SQL normalization for comparison."""

    def test_collapse_whitespace(self):
        sql = "SELECT  *\n  FROM   table1\n WHERE  id = 1"
        result = _normalize_sql(sql)
        self.assertEqual(result, "select * from table1 where id = 1")

    def test_case_fold(self):
        self.assertEqual(_normalize_sql("SELECT * FROM Users"), "select * from users")

    def test_strip_trailing_semicolon(self):
        self.assertEqual(_normalize_sql("SELECT 1;"), "select 1")
        self.assertEqual(_normalize_sql("SELECT 1;;"), "select 1")

    def test_strip_whitespace(self):
        self.assertEqual(_normalize_sql("  SELECT 1  "), "select 1")

    def test_empty_string(self):
        self.assertEqual(_normalize_sql(""), "")

    def test_none_like(self):
        self.assertEqual(_normalize_sql(""), "")

    def test_tabs_and_newlines(self):
        sql = "SELECT\t*\r\nFROM\ttable1"
        self.assertEqual(_normalize_sql(sql), "select * from table1")

    def test_equivalent_queries_normalize_same(self):
        q1 = "SELECT * FROM   orders  WHERE region = 'East'"
        q2 = "select *\n  from orders\n  where region = 'East'"
        self.assertEqual(_normalize_sql(q1), _normalize_sql(q2))


class TestHashSql(unittest.TestCase):
    """Test SQL hashing."""

    def test_same_query_same_hash(self):
        q1 = "SELECT * FROM orders"
        q2 = "select *   from   orders"
        self.assertEqual(_hash_sql(q1), _hash_sql(q2))

    def test_different_query_different_hash(self):
        self.assertNotEqual(
            _hash_sql("SELECT * FROM orders"),
            _hash_sql("SELECT * FROM customers"),
        )

    def test_hash_length(self):
        h = _hash_sql("SELECT 1")
        self.assertEqual(len(h), 16)

    def test_hash_is_hex(self):
        h = _hash_sql("SELECT 1")
        int(h, 16)  # Should not raise

    def test_empty_sql_hash(self):
        h = _hash_sql("")
        self.assertEqual(len(h), 16)

    def test_semicolon_irrelevant(self):
        self.assertEqual(_hash_sql("SELECT 1;"), _hash_sql("SELECT 1"))


class TestBuildTableFingerprints(unittest.TestCase):
    """Test table fingerprinting including custom SQL."""

    def _ds(self, tables, conn=None):
        conn = conn or {'class': 'textscan', 'type': 'textscan', 'details': {}}
        return [{'connection': conn, 'tables': tables}]

    def test_basic_table_fingerprint(self):
        tables = [{'name': 'Orders', 'columns': [{'name': 'id'}]}]
        fps = build_table_fingerprints(self._ds(tables))
        self.assertIn('Orders', fps)

    def test_custom_sql_table_fingerprint(self):
        tables = [{'name': 'CustomQuery', 'custom_sql': 'SELECT * FROM orders WHERE active = 1'}]
        fps = build_table_fingerprints(self._ds(tables))
        # Custom SQL tables should still appear in fingerprints
        self.assertGreater(len(fps), 0)

    def test_identical_custom_sql_same_fingerprint(self):
        sql = "SELECT * FROM orders WHERE region = 'East'"
        ds1 = self._ds([{'name': 'Q1', 'custom_sql': sql}])
        ds2 = self._ds([{'name': 'Q2', 'custom_sql': sql}])
        fp1 = build_table_fingerprints(ds1)
        fp2 = build_table_fingerprints(ds2)
        # Both should produce fingerprints
        self.assertGreater(len(fp1), 0)
        self.assertGreater(len(fp2), 0)

    def test_different_custom_sql_different_fingerprint(self):
        ds1 = self._ds([{'name': 'Q1', 'custom_sql': 'SELECT * FROM orders'}])
        ds2 = self._ds([{'name': 'Q2', 'custom_sql': 'SELECT * FROM customers'}])
        fp1 = build_table_fingerprints(ds1)
        fp2 = build_table_fingerprints(ds2)
        # Fingerprint keys should differ
        keys1 = set(fp1.keys())
        keys2 = set(fp2.keys())
        self.assertNotEqual(keys1, keys2)

    def test_empty_datasources(self):
        fps = build_table_fingerprints([])
        self.assertEqual(fps, {})

    def test_table_with_query_field(self):
        tables = [{'name': 'QT', 'query': 'SELECT id FROM tbl'}]
        fps = build_table_fingerprints(self._ds(tables))
        self.assertGreater(len(fps), 0)

    def test_multiple_tables_mixed(self):
        tables = [
            {'name': 'Physical', 'columns': [{'name': 'id'}]},
            {'name': 'SQL', 'custom_sql': 'SELECT * FROM raw'},
        ]
        fps = build_table_fingerprints(self._ds(tables))
        self.assertGreater(len(fps), 1)


class TestBuildCustomSqlFingerprints(unittest.TestCase):
    """Test dedicated custom SQL fingerprint builder."""

    def _ds(self, tables, conn=None):
        conn = conn or {'class': 'sqlserver', 'details': {'server': 'srv', 'database': 'db'}}
        return [{'connection': conn, 'tables': tables}]

    def test_custom_sql_found(self):
        tables = [{'name': 'Q', 'custom_sql': 'SELECT * FROM orders'}]
        fps = build_custom_sql_fingerprints(self._ds(tables))
        self.assertGreater(len(fps), 0)

    def test_no_sql_returns_empty(self):
        tables = [{'name': 'T', 'columns': [{'name': 'id'}]}]
        fps = build_custom_sql_fingerprints(self._ds(tables))
        self.assertEqual(len(fps), 0)

    def test_equivalent_sql_same_hash_key(self):
        q1 = "SELECT * FROM   orders"
        q2 = "select *\nfrom orders"
        ds1 = self._ds([{'name': 'A', 'custom_sql': q1}])
        ds2 = self._ds([{'name': 'B', 'custom_sql': q2}])
        fp1 = build_custom_sql_fingerprints(ds1)
        fp2 = build_custom_sql_fingerprints(ds2)
        self.assertEqual(set(fp1.keys()), set(fp2.keys()))

    def test_query_field_also_detected(self):
        tables = [{'name': 'Q', 'query': 'SELECT id FROM tbl'}]
        fps = build_custom_sql_fingerprints(self._ds(tables))
        self.assertGreater(len(fps), 0)

    def test_empty_datasources(self):
        fps = build_custom_sql_fingerprints([])
        self.assertEqual(len(fps), 0)

    def test_multiple_sql_tables(self):
        tables = [
            {'name': 'Q1', 'custom_sql': 'SELECT * FROM a'},
            {'name': 'Q2', 'custom_sql': 'SELECT * FROM b'},
        ]
        fps = build_custom_sql_fingerprints(self._ds(tables))
        self.assertEqual(len(fps), 2)


if __name__ == '__main__':
    unittest.main()
