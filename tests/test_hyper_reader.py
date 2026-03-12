"""Tests for tableau_export/hyper_reader.py — Sprint 30 coverage push."""

import os
import sqlite3
import tempfile
import unittest
import zipfile

from tableau_export.hyper_reader import (
    INLINE_ROW_THRESHOLD,
    _m_literal,
    _m_type_for,
    _parse_inserts,
    _read_hyper_header,
    _read_hyper_sqlite,
    _split_values,
    generate_m_csv_reference,
    generate_m_for_hyper_table,
    generate_m_inline_table,
    read_hyper,
    read_hyper_from_twbx,
)


# ── _m_type_for ────────────────────────────────────────────────────


class TestMTypeFor(unittest.TestCase):
    def test_known_types(self):
        self.assertEqual(_m_type_for('text'), 'Text.Type')
        self.assertEqual(_m_type_for('INTEGER'), 'Int64.Type')
        self.assertEqual(_m_type_for('boolean'), 'Logical.Type')
        self.assertEqual(_m_type_for('date'), 'Date.Type')
        self.assertEqual(_m_type_for('timestamp'), 'DateTime.Type')
        self.assertEqual(_m_type_for('timestamptz'), 'DateTimeZone.Type')

    def test_unknown_type_returns_any(self):
        self.assertEqual(_m_type_for('xml_blob'), 'Any.Type')

    def test_whitespace_stripped(self):
        self.assertEqual(_m_type_for('  float  '), 'Number.Type')


# ── _m_literal ─────────────────────────────────────────────────────


class TestMLiteral(unittest.TestCase):
    def test_none_returns_null(self):
        self.assertEqual(_m_literal(None), 'null')

    def test_logical_true(self):
        self.assertEqual(_m_literal(True, 'Logical.Type'), 'true')

    def test_logical_false(self):
        self.assertEqual(_m_literal(False, 'Logical.Type'), 'false')

    def test_logical_zero_is_false(self):
        self.assertEqual(_m_literal(0, 'Logical.Type'), 'false')

    def test_int64(self):
        self.assertEqual(_m_literal(42, 'Int64.Type'), '42')

    def test_number(self):
        self.assertEqual(_m_literal(3.14, 'Number.Type'), '3.14')

    def test_date_iso(self):
        result = _m_literal('2024-01-15', 'Date.Type')
        self.assertEqual(result, '#date(2024, 01, 15)')

    def test_date_non_iso_fallback(self):
        result = _m_literal('not-a-date', 'Date.Type')
        self.assertEqual(result, '"not-a-date"')

    def test_datetime_iso(self):
        result = _m_literal('2024-03-15 10:30:45', 'DateTime.Type')
        self.assertEqual(result, '#datetime(2024, 03, 15, 10, 30, 45)')

    def test_datetimezone(self):
        result = _m_literal('2024-03-15 10:30:45', 'DateTimeZone.Type')
        self.assertEqual(result, '#datetime(2024, 03, 15, 10, 30, 45)')

    def test_datetime_non_iso_fallback(self):
        result = _m_literal('not-a-datetime', 'DateTime.Type')
        self.assertEqual(result, '"not-a-datetime"')

    def test_text_default(self):
        self.assertEqual(_m_literal('hello'), '"hello"')

    def test_text_escapes_quotes(self):
        self.assertEqual(_m_literal('say "hi"'), '"say ""hi"""')


# ── _split_values ──────────────────────────────────────────────────


class TestSplitValues(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(_split_values("1, 'abc', 3"), ['1', "'abc'", '3'])

    def test_quoted_comma(self):
        result = _split_values("'a,b', 2")
        self.assertEqual(result, ["'a,b'", '2'])

    def test_empty(self):
        self.assertEqual(_split_values(''), [])

    def test_null(self):
        self.assertEqual(_split_values("NULL, 'x'"), ['NULL', "'x'"])


# ── _read_hyper_sqlite ─────────────────────────────────────────────


class TestReadHyperSqlite(unittest.TestCase):
    def _create_test_db(self, rows=None):
        """Create a temp SQLite DB and return path."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute(
            'CREATE TABLE orders (id INTEGER, product TEXT, amount REAL)'
        )
        for r in (rows or []):
            conn.execute('INSERT INTO orders VALUES (?, ?, ?)', r)
        conn.commit()
        conn.close()
        return path

    def test_reads_sqlite_db(self):
        path = self._create_test_db([(1, 'Widget', 9.99), (2, 'Gadget', 19.99)])
        try:
            tables = _read_hyper_sqlite(path, max_rows=10)
            self.assertIsNotNone(tables)
            self.assertEqual(len(tables), 1)
            t = tables[0]
            self.assertEqual(t['table'], 'orders')
            self.assertEqual(t['column_count'], 3)
            self.assertEqual(t['row_count'], 2)
            self.assertEqual(len(t['sample_rows']), 2)
            self.assertEqual(t['sample_rows'][0]['product'], 'Widget')
        finally:
            os.unlink(path)

    def test_empty_table(self):
        path = self._create_test_db([])
        try:
            tables = _read_hyper_sqlite(path, max_rows=5)
            self.assertIsNotNone(tables)
            self.assertEqual(tables[0]['row_count'], 0)
            self.assertEqual(tables[0]['sample_rows'], [])
        finally:
            os.unlink(path)

    def test_max_rows_limit(self):
        rows = [(i, f'item{i}', float(i)) for i in range(50)]
        path = self._create_test_db(rows)
        try:
            tables = _read_hyper_sqlite(path, max_rows=5)
            self.assertEqual(len(tables[0]['sample_rows']), 5)
            self.assertEqual(tables[0]['row_count'], 50)
        finally:
            os.unlink(path)

    def test_non_sqlite_file_returns_none(self):
        fd, path = tempfile.mkstemp(suffix='.hyper')
        os.write(fd, b'HyPe\x00not-a-sqlite-file-at-all')
        os.close(fd)
        try:
            result = _read_hyper_sqlite(path)
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_no_tables_returns_none(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.close()
        try:
            result = _read_hyper_sqlite(path)
            self.assertIsNone(result)
        finally:
            os.unlink(path)


# ── _read_hyper_header ─────────────────────────────────────────────


class TestReadHyperHeader(unittest.TestCase):
    def test_parses_create_table(self):
        text = (
            'HyPe\x00CREATE TABLE "Orders" (id integer, name text)\n'
            'INSERT INTO "Orders" VALUES (1, \'Alice\')\n'
        )
        raw = text.encode('utf-8')
        tables = _read_hyper_header(raw, max_rows=5)
        self.assertIsNotNone(tables)
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]['table'], 'Orders')
        self.assertEqual(len(tables[0]['columns']), 2)
        self.assertGreater(len(tables[0]['sample_rows']), 0)

    def test_no_create_returns_none(self):
        raw = b'HyPe\x00\x00\x00just random binary data'
        result = _read_hyper_header(raw)
        self.assertIsNone(result)

    def test_unicode_error_returns_none(self):
        # Passing empty bytes should return None
        result = _read_hyper_header(b'')
        self.assertIsNone(result)


# ── _parse_inserts ─────────────────────────────────────────────────


class TestParseInserts(unittest.TestCase):
    def test_basic_insert(self):
        text = "INSERT INTO orders VALUES (1, 'Widget', 9.99)"
        columns = [
            {'name': 'id', 'hyper_type': 'integer'},
            {'name': 'product', 'hyper_type': 'text'},
            {'name': 'amount', 'hyper_type': 'real'},
        ]
        rows = _parse_inserts(text, 'orders', columns, 10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], '1')
        self.assertEqual(rows[0]['product'], 'Widget')

    def test_null_value(self):
        text = "INSERT INTO t VALUES (NULL, 'x')"
        columns = [
            {'name': 'a', 'hyper_type': 'text'},
            {'name': 'b', 'hyper_type': 'text'},
        ]
        rows = _parse_inserts(text, 't', columns, 10)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['a'])

    def test_max_rows_respected(self):
        text = (
            "INSERT INTO t VALUES (1, 'a'), (2, 'b'), (3, 'c'), (4, 'd')"
        )
        columns = [
            {'name': 'id', 'hyper_type': 'integer'},
            {'name': 'val', 'hyper_type': 'text'},
        ]
        rows = _parse_inserts(text, 't', columns, 2)
        self.assertEqual(len(rows), 2)


# ── read_hyper ─────────────────────────────────────────────────────


class TestReadHyper(unittest.TestCase):
    def test_nonexistent_file(self):
        result = read_hyper('/nonexistent/path.hyper')
        self.assertEqual(result['tables'], [])
        self.assertEqual(result['format'], 'unknown')

    def test_none_path(self):
        result = read_hyper(None)
        self.assertEqual(result['tables'], [])

    def test_empty_path(self):
        result = read_hyper('')
        self.assertEqual(result['tables'], [])

    def test_sqlite_format_detected(self):
        """Real SQLite file → format='sqlite'."""
        fd, path = tempfile.mkstemp(suffix='.hyper')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute('CREATE TABLE t (id INTEGER, name TEXT)')
        conn.execute("INSERT INTO t VALUES (1, 'Alice')")
        conn.commit()
        conn.close()
        try:
            result = read_hyper(path)
            self.assertEqual(result['format'], 'sqlite')
            self.assertEqual(len(result['tables']), 1)
            self.assertEqual(result['tables'][0]['table'], 't')
        finally:
            os.unlink(path)

    def test_hyper_format_header_fallback(self):
        """File with HyPe magic + CREATE TABLE → header scan."""
        content = (
            b'HyPe\x00\x00\x00\x00'
            b'CREATE TABLE "data" (id integer, val text)\n'
            b"INSERT INTO \"data\" VALUES (1, 'test')\n"
        )
        fd, path = tempfile.mkstemp(suffix='.hyper')
        os.write(fd, content)
        os.close(fd)
        try:
            result = read_hyper(path)
            self.assertEqual(result['format'], 'hyper')
            self.assertGreater(len(result['tables']), 0)
        finally:
            os.unlink(path)

    def test_unknown_format(self):
        """File with unknown magic bytes → unknown format."""
        fd, path = tempfile.mkstemp(suffix='.hyper')
        os.write(fd, b'\x00\x00\x00\x00random binary data')
        os.close(fd)
        try:
            result = read_hyper(path)
            self.assertEqual(result['format'], 'unknown')
        finally:
            os.unlink(path)


# ── read_hyper_from_twbx ──────────────────────────────────────────


class TestReadHyperFromTwbx(unittest.TestCase):
    def _create_twbx_with_hyper(self, hyper_data, hyper_name='Data/Extract.hyper'):
        """Create a temp .twbx ZIP containing a .hyper entry."""
        fd, path = tempfile.mkstemp(suffix='.twbx')
        os.close(fd)
        with zipfile.ZipFile(path, 'w') as zf:
            zf.writestr(hyper_name, hyper_data)
        return path

    def test_reads_hyper_from_twbx(self):
        # Create a SQLite-based hyper file content
        fd, hyper_path = tempfile.mkstemp(suffix='.hyper')
        os.close(fd)
        conn = sqlite3.connect(hyper_path)
        conn.execute('CREATE TABLE t (a INTEGER)')
        conn.execute('INSERT INTO t VALUES (42)')
        conn.commit()
        conn.close()
        with open(hyper_path, 'rb') as f:
            hyper_bytes = f.read()
        os.unlink(hyper_path)

        twbx_path = self._create_twbx_with_hyper(hyper_bytes)
        try:
            results = read_hyper_from_twbx(twbx_path)
            self.assertEqual(len(results), 1)
            self.assertIn('archive_path', results[0])
            self.assertIn('original_filename', results[0])
        finally:
            os.unlink(twbx_path)

    def test_filter_by_hyper_filename(self):
        fd, hyper_path = tempfile.mkstemp(suffix='.hyper')
        os.close(fd)
        conn = sqlite3.connect(hyper_path)
        conn.execute('CREATE TABLE t (x TEXT)')
        conn.commit()
        conn.close()
        with open(hyper_path, 'rb') as f:
            hyper_bytes = f.read()
        os.unlink(hyper_path)

        fd, twbx_path = tempfile.mkstemp(suffix='.twbx')
        os.close(fd)
        with zipfile.ZipFile(twbx_path, 'w') as zf:
            zf.writestr('Data/Extract.hyper', hyper_bytes)
            zf.writestr('Data/Other.hyper', hyper_bytes)
        try:
            results = read_hyper_from_twbx(twbx_path, hyper_filename='Extract.hyper')
            self.assertEqual(len(results), 1)
            self.assertIn('Extract.hyper', results[0]['original_filename'])
        finally:
            os.unlink(twbx_path)

    def test_nonexistent_twbx(self):
        results = read_hyper_from_twbx('/nonexistent/file.twbx')
        self.assertEqual(results, [])

    def test_none_path(self):
        self.assertEqual(read_hyper_from_twbx(None), [])

    def test_not_a_zip(self):
        fd, path = tempfile.mkstemp(suffix='.twbx')
        os.write(fd, b'not a zip file')
        os.close(fd)
        try:
            results = read_hyper_from_twbx(path)
            self.assertEqual(results, [])
        finally:
            os.unlink(path)


# ── generate_m_inline_table ────────────────────────────────────────


class TestGenerateMInlineTable(unittest.TestCase):
    def test_basic_inline_table(self):
        info = {
            'table': 'Sales',
            'columns': [
                {'name': 'id', 'hyper_type': 'integer'},
                {'name': 'product', 'hyper_type': 'text'},
            ],
            'sample_rows': [
                {'id': 1, 'product': 'Widget'},
                {'id': 2, 'product': 'Gadget'},
            ],
        }
        m = generate_m_inline_table(info)
        self.assertIn('#table(', m)
        self.assertIn('Int64.Type', m)
        self.assertIn('Text.Type', m)
        self.assertIn('"Widget"', m)
        self.assertIn('"Gadget"', m)
        self.assertIn('let', m)
        self.assertIn('in', m)

    def test_empty_columns(self):
        info = {'table': 'Empty', 'columns': [], 'sample_rows': []}
        m = generate_m_inline_table(info)
        self.assertIn('No columns found', m)

    def test_no_rows(self):
        info = {
            'table': 'Schema',
            'columns': [{'name': 'x', 'hyper_type': 'text'}],
            'sample_rows': [],
        }
        m = generate_m_inline_table(info)
        self.assertIn('{}', m)
        self.assertIn('[x]', m)

    def test_null_values(self):
        info = {
            'table': 'WithNulls',
            'columns': [{'name': 'a', 'hyper_type': 'text'}],
            'sample_rows': [{'a': None}],
        }
        m = generate_m_inline_table(info)
        self.assertIn('null', m)


# ── generate_m_csv_reference ──────────────────────────────────────


class TestGenerateMCsvReference(unittest.TestCase):
    def test_basic_csv_reference(self):
        info = {
            'table': 'BigData',
            'columns': [
                {'name': 'id', 'hyper_type': 'integer'},
                {'name': 'value', 'hyper_type': 'real'},
            ],
        }
        m = generate_m_csv_reference(info)
        self.assertIn('Csv.Document', m)
        self.assertIn('BigData.csv', m)
        self.assertIn('Int64.Type', m)
        self.assertIn('Number.Type', m)

    def test_custom_csv_filename(self):
        info = {
            'table': 'T',
            'columns': [{'name': 'x', 'hyper_type': 'text'}],
        }
        m = generate_m_csv_reference(info, csv_filename='custom.csv')
        self.assertIn('custom.csv', m)
        self.assertNotIn('T.csv', m)


# ── generate_m_for_hyper_table ─────────────────────────────────────


class TestGenerateMForHyperTable(unittest.TestCase):
    def test_small_table_uses_inline(self):
        info = {
            'table': 'Small',
            'columns': [{'name': 'id', 'hyper_type': 'integer'}],
            'sample_rows': [{'id': 1}],
            'row_count': 10,
        }
        m = generate_m_for_hyper_table(info)
        self.assertIn('#table(', m)
        self.assertNotIn('Csv.Document', m)

    def test_large_table_uses_csv(self):
        info = {
            'table': 'Big',
            'columns': [{'name': 'id', 'hyper_type': 'integer'}],
            'sample_rows': [],
            'row_count': INLINE_ROW_THRESHOLD + 1,
        }
        m = generate_m_for_hyper_table(info)
        self.assertIn('Csv.Document', m)

    def test_threshold_boundary_uses_inline(self):
        info = {
            'table': 'Edge',
            'columns': [{'name': 'id', 'hyper_type': 'integer'}],
            'sample_rows': [],
            'row_count': INLINE_ROW_THRESHOLD,
        }
        m = generate_m_for_hyper_table(info)
        # At threshold, should use inline
        self.assertIn('#table(', m)


if __name__ == '__main__':
    unittest.main()
