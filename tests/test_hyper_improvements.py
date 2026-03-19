"""Tests for Hyper file improvements — Options A/B/C/D.

Option A: tableauhyperapi integration (optional dependency)
Option B: Multi-schema support (Extract.Extract, public.Orders)
Option C: Configurable row limit (--hyper-rows)
Option D: Metadata enrichment (column stats, file metadata, recommendations)
"""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tableau_export.hyper_reader import (
    INLINE_ROW_THRESHOLD,
    _compute_column_stats_sqlite,
    _m_literal,
    _m_type_for,
    _read_hyper_api,
    _read_hyper_sqlite,
    generate_m_csv_reference,
    generate_m_for_hyper_table,
    generate_m_inline_table,
    get_hyper_metadata,
    read_hyper,
)


def _create_sqlite_hyper(path, table_name='Orders', schema=None, rows=None):
    """Create a minimal SQLite-based .hyper file for testing."""
    conn = sqlite3.connect(path)
    c = conn.cursor()
    qualified = f'"{table_name}"'
    c.execute(f'CREATE TABLE {qualified} (id INTEGER, name TEXT, amount REAL)')
    if rows:
        for r in rows:
            c.execute(f'INSERT INTO {qualified} VALUES (?, ?, ?)', r)
    else:
        c.execute(f'INSERT INTO {qualified} VALUES (1, "Alice", 100.5)')
        c.execute(f'INSERT INTO {qualified} VALUES (2, "Bob", 200.0)')
        c.execute(f'INSERT INTO {qualified} VALUES (3, "Carol", 150.75)')
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════
#  Option A: tableauhyperapi integration
# ═══════════════════════════════════════════════════════════════════


class TestHyperApiReader(unittest.TestCase):
    """Tests for _read_hyper_api (Option A)."""

    def test_returns_none_without_package(self):
        """When tableauhyperapi is not installed, returns None."""
        result = _read_hyper_api('/fake/path.hyper', max_rows=5)
        self.assertIsNone(result)

    @patch('tableau_export.hyper_reader._read_hyper_api')
    def test_read_hyper_tries_api_first(self, mock_api):
        """read_hyper() calls _read_hyper_api before SQLite."""
        mock_api.return_value = [
            {'table': 'T', 'columns': [{'name': 'id', 'hyper_type': 'int'}],
             'column_count': 1, 'sample_rows': [], 'sample_row_count': 0,
             'row_count': 10, 'column_stats': {}}
        ]
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            f.write(b'SQLite format 3\0')
            path = f.name
        try:
            result = read_hyper(path, max_rows=5)
            self.assertEqual(result['format'], 'hyper_api')
            self.assertEqual(len(result['tables']), 1)
        finally:
            os.unlink(path)

    def test_api_reader_handles_exception(self):
        """_read_hyper_api returns None on any exception from the package."""
        # Since tableauhyperapi is not installed, this exercises the ImportError path
        result = _read_hyper_api('/nonexistent.hyper')
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
#  Option B: Multi-schema support
# ═══════════════════════════════════════════════════════════════════


class TestMultiSchemaSupport(unittest.TestCase):
    """Tests for multi-schema table discovery in SQLite reader (Option B)."""

    def test_standard_table_found(self):
        """Standard unqualified table is discovered."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            _create_sqlite_hyper(path, 'Orders')
            tables = _read_hyper_sqlite(path, max_rows=5)
            self.assertIsNotNone(tables)
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0]['table'], 'Orders')
            self.assertEqual(tables[0]['row_count'], 3)
        finally:
            os.unlink(path)

    def test_column_stats_present(self):
        """Tables include column_stats key (Option D integration)."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            _create_sqlite_hyper(path, 'Orders')
            tables = _read_hyper_sqlite(path, max_rows=5)
            self.assertIn('column_stats', tables[0])
            stats = tables[0]['column_stats']
            self.assertIn('id', stats)
            self.assertEqual(stats['id']['distinct_count'], 3)
        finally:
            os.unlink(path)

    def test_schema_qualified_tables_not_duplicated(self):
        """Schema discovery doesn't duplicate already-found tables."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            _create_sqlite_hyper(path, 'Extract')
            tables = _read_hyper_sqlite(path, max_rows=5)
            # Should have exactly one entry for 'Extract', not duplicated
            table_names = [t['table'] for t in tables]
            self.assertEqual(table_names.count('Extract'), 1)
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
#  Option C: Configurable row limit
# ═══════════════════════════════════════════════════════════════════


class TestConfigurableRowLimit(unittest.TestCase):
    """Tests for configurable max_rows (Option C)."""

    def test_max_rows_respected(self):
        """Only max_rows sample rows are returned."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            rows = [(i, f'Name{i}', float(i * 10)) for i in range(50)]
            _create_sqlite_hyper(path, 'Big', rows=rows)
            tables = _read_hyper_sqlite(path, max_rows=5)
            self.assertEqual(tables[0]['sample_row_count'], 5)
            self.assertEqual(tables[0]['row_count'], 50)
        finally:
            os.unlink(path)

    def test_zero_max_rows_no_samples(self):
        """max_rows=0 returns no sample data."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            _create_sqlite_hyper(path, 'T')
            tables = _read_hyper_sqlite(path, max_rows=0)
            self.assertEqual(tables[0]['sample_row_count'], 0)
            self.assertEqual(tables[0]['sample_rows'], [])
        finally:
            os.unlink(path)

    def test_generate_m_inline_below_threshold(self):
        """Small table generates inline #table() expression."""
        table_info = {
            'table': 'T',
            'columns': [{'name': 'id', 'hyper_type': 'int'}],
            'sample_rows': [{'id': 1}, {'id': 2}],
            'row_count': 2,
        }
        m = generate_m_for_hyper_table(table_info, row_limit=500)
        self.assertIn('#table', m)
        self.assertNotIn('Csv.Document', m)

    def test_generate_m_csv_above_threshold(self):
        """Large table generates Csv.Document() expression."""
        table_info = {
            'table': 'T',
            'columns': [{'name': 'id', 'hyper_type': 'int'}],
            'sample_rows': [],
            'row_count': 1000,
        }
        m = generate_m_for_hyper_table(table_info, row_limit=500)
        self.assertIn('Csv.Document', m)

    def test_custom_row_limit_overrides_threshold(self):
        """row_limit parameter overrides INLINE_ROW_THRESHOLD."""
        table_info = {
            'table': 'T',
            'columns': [{'name': 'id', 'hyper_type': 'int'}],
            'sample_rows': [],
            'row_count': 100,
        }
        # Default threshold is 500 — 100 rows should be inline
        m1 = generate_m_for_hyper_table(table_info, row_limit=500)
        self.assertIn('#table', m1)
        # But with row_limit=50, 100 rows exceeds → CSV
        m2 = generate_m_for_hyper_table(table_info, row_limit=50)
        self.assertIn('Csv.Document', m2)

    def test_read_hyper_passes_max_rows(self):
        """read_hyper respects max_rows parameter."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            rows = [(i, f'N{i}', float(i)) for i in range(30)]
            _create_sqlite_hyper(path, 'T', rows=rows)
            result = read_hyper(path, max_rows=3)
            tables = result.get('tables', [])
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0]['sample_row_count'], 3)
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
#  Option D: Metadata enrichment
# ═══════════════════════════════════════════════════════════════════


class TestMetadataEnrichment(unittest.TestCase):
    """Tests for metadata enrichment (Option D)."""

    def test_file_metadata_present(self):
        """read_hyper includes file-level metadata."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            _create_sqlite_hyper(path, 'T')
            result = read_hyper(path, max_rows=1)
            self.assertIn('metadata', result)
            meta = result['metadata']
            self.assertIn('file_size_bytes', meta)
            self.assertGreater(meta['file_size_bytes'], 0)
            self.assertIn('last_modified', meta)
        finally:
            os.unlink(path)

    def test_column_stats_min_max(self):
        """Column stats include min/max values."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            rows = [(1, 'A', 10.0), (2, 'B', 20.0), (3, 'C', 30.0)]
            _create_sqlite_hyper(path, 'T', rows=rows)
            tables = _read_hyper_sqlite(path, max_rows=5)
            stats = tables[0]['column_stats']
            self.assertEqual(stats['amount']['min'], 10.0)
            self.assertEqual(stats['amount']['max'], 30.0)
            self.assertEqual(stats['name']['distinct_count'], 3)
        finally:
            os.unlink(path)

    def test_get_hyper_metadata_summary(self):
        """get_hyper_metadata returns enriched summary."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            _create_sqlite_hyper(path, 'T')
            meta = get_hyper_metadata(path, max_rows=0)
            self.assertEqual(meta['total_tables'], 1)
            self.assertEqual(meta['total_rows'], 3)
            self.assertGreater(meta['file_size_bytes'], 0)
            self.assertIsInstance(meta['recommendations'], list)
            self.assertEqual(len(meta['tables']), 1)
            self.assertEqual(meta['tables'][0]['name'], 'T')
        finally:
            os.unlink(path)

    def test_metadata_large_data_recommendation(self):
        """get_hyper_metadata recommends DirectQuery for large row counts."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            _create_sqlite_hyper(path, 'T')
            # Patch the result to simulate large data
            with patch('tableau_export.hyper_reader.read_hyper') as mock_read:
                mock_read.return_value = {
                    'tables': [{'table': 'T', 'row_count': 15_000_000,
                                'column_count': 3, 'column_stats': {}}],
                    'format': 'sqlite',
                    'metadata': {'file_size_bytes': 1_000_000, 'last_modified': 0},
                }
                meta = get_hyper_metadata(path, max_rows=0)
                self.assertTrue(any('DirectQuery' in r for r in meta['recommendations']))
        finally:
            os.unlink(path)

    def test_metadata_high_cardinality_recommendation(self):
        """get_hyper_metadata flags high-cardinality columns."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            _create_sqlite_hyper(path, 'T')
            with patch('tableau_export.hyper_reader.read_hyper') as mock_read:
                mock_read.return_value = {
                    'tables': [{
                        'table': 'T', 'row_count': 100,
                        'column_count': 1,
                        'column_stats': {'id': {'distinct_count': 2_000_000}},
                    }],
                    'format': 'sqlite',
                    'metadata': {'file_size_bytes': 100, 'last_modified': 0},
                }
                meta = get_hyper_metadata(path, max_rows=0)
                self.assertTrue(any('cardinality' in r for r in meta['recommendations']))
        finally:
            os.unlink(path)

    def test_metadata_nonexistent_file(self):
        """get_hyper_metadata handles missing files gracefully."""
        meta = get_hyper_metadata('/nonexistent/file.hyper', max_rows=0)
        self.assertEqual(meta['total_tables'], 0)
        self.assertEqual(meta['total_rows'], 0)

    def test_compute_column_stats_sqlite_empty_table(self):
        """Column stats on empty table returns zero distinct."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            conn = sqlite3.connect(path)
            c = conn.cursor()
            c.execute('CREATE TABLE T (id INTEGER, name TEXT)')
            conn.commit()
            stats = _compute_column_stats_sqlite(
                c, '"T"',
                [{'name': 'id', 'hyper_type': 'int'}, {'name': 'name', 'hyper_type': 'text'}],
            )
            conn.close()
            self.assertEqual(stats['id']['distinct_count'], 0)
            self.assertIsNone(stats['id']['min'])
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
#  Integration: read_hyper format detection
# ═══════════════════════════════════════════════════════════════════


class TestReadHyperFormatDetection(unittest.TestCase):
    """Tests for format detection in read_hyper()."""

    def test_sqlite_format_detected(self):
        """SQLite-based hyper files report 'sqlite' format."""
        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as f:
            path = f.name
        try:
            _create_sqlite_hyper(path, 'T')
            result = read_hyper(path, max_rows=1)
            # Format is either 'sqlite' or 'hyper_api' (if tableauhyperapi installed)
            self.assertIn(result['format'], ('sqlite', 'hyper_api'))
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_empty(self):
        """Nonexistent file returns empty tables."""
        result = read_hyper('/nonexistent.hyper', max_rows=5)
        self.assertEqual(result['tables'], [])
        self.assertEqual(result['format'], 'unknown')


if __name__ == '__main__':
    unittest.main()
