"""
Snapshot (golden file) tests for TMDL, M query, and PBIR output stability.

Captures the output of key generation functions and compares against
stored snapshots to detect unintended output changes.

Workflow:
  1. First run: generates snapshot files in tests/snapshots/
  2. Subsequent runs: compares output against stored snapshots
  3. To update snapshots: delete the file and re-run tests, or
     set UPDATE_SNAPSHOTS=1 environment variable
"""

import unittest
import sys
import os
import json
import copy
import re
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from tests.conftest import SAMPLE_DATASOURCE, SAMPLE_EXTRACTED, make_temp_dir, cleanup_dir

from m_query_builder import generate_power_query_m
from dax_converter import convert_tableau_formula_to_dax
from tmdl_generator import generate_tmdl


SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), 'snapshots')
UPDATE_SNAPSHOTS = os.environ.get('UPDATE_SNAPSHOTS', '').lower() in ('1', 'true', 'yes')

# Regex to match UUIDs (8-4-4-4-12 hex)
_UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)
_UUID_PLACEHOLDER = '00000000-0000-0000-0000-000000000000'


def _normalize_uuids(text):
    """Replace all UUIDs with a stable placeholder for snapshot comparison."""
    return _UUID_RE.sub(_UUID_PLACEHOLDER, text)


def _ensure_snapshots_dir():
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)


def _snapshot_path(name):
    return os.path.join(SNAPSHOTS_DIR, name)


def _save_snapshot(name, content):
    _ensure_snapshots_dir()
    with open(_snapshot_path(name), 'w', encoding='utf-8') as f:
        f.write(content)


def _load_snapshot(name):
    path = _snapshot_path(name)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class SnapshotTestCase(unittest.TestCase):
    """Base class with snapshot assertion helper."""

    def assertMatchesSnapshot(self, content, snapshot_name):
        """Compare content against a stored snapshot.

        On first run (no snapshot file), saves the content as the new snapshot.
        On subsequent runs, asserts exact match.
        If UPDATE_SNAPSHOTS env var is set, updates the snapshot.
        """
        existing = _load_snapshot(snapshot_name)
        if existing is None or UPDATE_SNAPSHOTS:
            _save_snapshot(snapshot_name, content)
            if existing is None:
                self.skipTest(f"Snapshot '{snapshot_name}' created — re-run to verify")
            return

        # Compare with stored snapshot (UUIDs normalized to avoid non-determinism)
        norm_content = _normalize_uuids(content)
        norm_existing = _normalize_uuids(existing)
        if norm_content != norm_existing:
            # Find first difference for helpful error message
            content_lines = norm_content.splitlines(keepends=True)
            existing_lines = norm_existing.splitlines(keepends=True)
            for i, (a, b) in enumerate(zip(content_lines, existing_lines), 1):
                if a != b:
                    self.fail(
                        f"Snapshot mismatch in '{snapshot_name}' at line {i}:\n"
                        f"  Expected: {b.rstrip()}\n"
                        f"  Got:      {a.rstrip()}"
                    )
            # Length difference
            if len(content_lines) != len(existing_lines):
                self.fail(
                    f"Snapshot mismatch in '{snapshot_name}': "
                    f"expected {len(existing_lines)} lines, got {len(content_lines)}"
                )


class TestMQuerySnapshots(SnapshotTestCase):
    """Snapshot tests for Power Query M generation."""

    def test_sql_server_m_query(self):
        conn = {'type': 'SQL Server', 'details': {'server': 'localhost', 'database': 'TestDB'}}
        table = {'name': 'Orders', 'columns': [
            {'name': 'OrderID', 'datatype': 'integer'},
            {'name': 'CustomerName', 'datatype': 'string'},
            {'name': 'OrderDate', 'datatype': 'datetime'},
        ]}
        result = generate_power_query_m(conn, table)
        self.assertMatchesSnapshot(result, 'sql_server_m_query.txt')

    def test_postgresql_m_query(self):
        conn = {'type': 'PostgreSQL', 'details': {
            'server': 'db.example.com', 'port': '5432', 'database': 'analytics'
        }}
        table = {'name': 'events', 'columns': [
            {'name': 'id', 'datatype': 'integer'},
            {'name': 'event_name', 'datatype': 'string'},
            {'name': 'created_at', 'datatype': 'datetime'},
        ]}
        result = generate_power_query_m(conn, table)
        self.assertMatchesSnapshot(result, 'postgresql_m_query.txt')

    def test_csv_m_query(self):
        conn = {'type': 'CSV', 'details': {'filename': 'data.csv', 'delimiter': ','}}
        table = {'name': 'data', 'columns': [
            {'name': 'id', 'datatype': 'integer'},
            {'name': 'name', 'datatype': 'string'},
            {'name': 'value', 'datatype': 'real'},
        ]}
        result = generate_power_query_m(conn, table)
        self.assertMatchesSnapshot(result, 'csv_m_query.txt')

    def test_bigquery_m_query(self):
        conn = {'type': 'BigQuery', 'details': {'project': 'my-project', 'dataset': 'analytics'}}
        table = {'name': 'users', 'columns': [
            {'name': 'user_id', 'datatype': 'integer'},
            {'name': 'email', 'datatype': 'string'},
        ]}
        result = generate_power_query_m(conn, table)
        self.assertMatchesSnapshot(result, 'bigquery_m_query.txt')

    def test_snowflake_m_query(self):
        conn = {'type': 'Snowflake', 'details': {
            'server': 'org.snowflakecomputing.com',
            'database': 'ANALYTICS', 'warehouse': 'WH_PROD', 'schema': 'PUBLIC'
        }}
        table = {'name': 'FACT_SALES', 'columns': [
            {'name': 'SALE_ID', 'datatype': 'integer'},
            {'name': 'AMOUNT', 'datatype': 'real'},
        ]}
        result = generate_power_query_m(conn, table)
        self.assertMatchesSnapshot(result, 'snowflake_m_query.txt')


class TestDAXSnapshots(SnapshotTestCase):
    """Snapshot tests for DAX conversion output stability."""

    def test_fixed_lod_snapshot(self):
        result = convert_tableau_formula_to_dax('{FIXED [Customer] : SUM([Sales])}')
        self.assertMatchesSnapshot(result, 'dax_fixed_lod.txt')

    def test_running_sum_snapshot(self):
        result = convert_tableau_formula_to_dax('RUNNING_SUM(SUM([Sales]))')
        self.assertMatchesSnapshot(result, 'dax_running_sum.txt')

    def test_complex_if_snapshot(self):
        formula = (
            'IF [Status] = "Active" THEN SUM([Amount]) '
            'ELSEIF [Status] = "Pending" THEN SUM([Amount]) * 0.5 '
            'ELSE 0 END'
        )
        result = convert_tableau_formula_to_dax(formula)
        self.assertMatchesSnapshot(result, 'dax_complex_if.txt')

    def test_countd_snapshot(self):
        result = convert_tableau_formula_to_dax('COUNTD([CustomerID])')
        self.assertMatchesSnapshot(result, 'dax_countd.txt')

    def test_datetrunc_snapshot(self):
        result = convert_tableau_formula_to_dax('DATETRUNC("month", [OrderDate])')
        self.assertMatchesSnapshot(result, 'dax_datetrunc.txt')


class TestTmdlFileSnapshots(SnapshotTestCase):
    """Snapshot tests for TMDL file generation."""

    def test_simple_model_tmdl(self):
        temp_dir = make_temp_dir()
        try:
            ds = copy.deepcopy(SAMPLE_DATASOURCE)
            generate_tmdl([ds], 'SnapshotTest', {}, temp_dir)

            # Read model.tmdl
            model_path = os.path.join(temp_dir, 'definition', 'model.tmdl')
            if os.path.exists(model_path):
                with open(model_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.assertMatchesSnapshot(content, 'tmdl_model.txt')
        finally:
            cleanup_dir(temp_dir)

    def test_database_tmdl(self):
        temp_dir = make_temp_dir()
        try:
            ds = copy.deepcopy(SAMPLE_DATASOURCE)
            generate_tmdl([ds], 'SnapshotDB', {}, temp_dir)

            db_path = os.path.join(temp_dir, 'definition', 'database.tmdl')
            if os.path.exists(db_path):
                with open(db_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.assertMatchesSnapshot(content, 'tmdl_database.txt')
        finally:
            cleanup_dir(temp_dir)


if __name__ == '__main__':
    unittest.main()
