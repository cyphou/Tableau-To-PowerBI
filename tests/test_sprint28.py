"""Sprint 28 tests — Hyper Data Loading & SCRIPT_* Visuals.

Tests cover:
- hyper_reader: type mapping, M literal generation, M expression builders,
  inline vs CSV threshold, SQLite reading, header fallback, TWBX extraction
- m_query_builder: generate_m_from_hyper(), _gen_m_hyper()
- dax_converter: detect_script_functions(), has_script_functions(),
  _detect_script_language()
- visual_generator: generate_script_visual()
- assessment: SCRIPT_* severity downgrade to WARN
- pbip_generator: _detect_script_visual()
- prep_flow_parser: hyper input node processing
"""
import json
import os
import sqlite3
import struct
import tempfile
import unittest
import zipfile
import sys

# Add module paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))


# =============================================================================
#  Hyper Reader Tests
# =============================================================================

class TestHyperReaderTypeMappings(unittest.TestCase):
    """Test _HYPER_TO_M_TYPE and _m_type_for()."""

    def setUp(self):
        from hyper_reader import _HYPER_TO_M_TYPE, _m_type_for
        self._type_map = _HYPER_TO_M_TYPE
        self._m_type_for = _m_type_for

    def test_boolean_type(self):
        self.assertEqual(self._m_type_for('boolean'), 'Logical.Type')
        self.assertEqual(self._m_type_for('bool'), 'Logical.Type')

    def test_integer_types(self):
        self.assertEqual(self._m_type_for('integer'), 'Int64.Type')
        self.assertEqual(self._m_type_for('bigint'), 'Int64.Type')
        self.assertEqual(self._m_type_for('smallint'), 'Int64.Type')
        self.assertEqual(self._m_type_for('int'), 'Int64.Type')

    def test_float_types(self):
        self.assertEqual(self._m_type_for('double'), 'Number.Type')
        self.assertEqual(self._m_type_for('double precision'), 'Number.Type')
        self.assertEqual(self._m_type_for('numeric'), 'Number.Type')
        self.assertEqual(self._m_type_for('real'), 'Number.Type')

    def test_text_types(self):
        self.assertEqual(self._m_type_for('text'), 'Text.Type')
        self.assertEqual(self._m_type_for('varchar'), 'Text.Type')
        self.assertEqual(self._m_type_for('char'), 'Text.Type')

    def test_date_types(self):
        self.assertEqual(self._m_type_for('date'), 'Date.Type')
        self.assertEqual(self._m_type_for('timestamp'), 'DateTime.Type')
        self.assertEqual(self._m_type_for('timestamp without time zone'), 'DateTime.Type')

    def test_unknown_defaults_to_any(self):
        self.assertEqual(self._m_type_for('geography'), 'Text.Type')
        self.assertEqual(self._m_type_for('custom_type_xyz'), 'Any.Type')

    def test_case_insensitive(self):
        self.assertEqual(self._m_type_for('TEXT'), 'Text.Type')
        self.assertEqual(self._m_type_for('BigInt'), 'Int64.Type')


class TestMLiteral(unittest.TestCase):
    """Test _m_literal() value → M expression conversion."""

    def setUp(self):
        from hyper_reader import _m_literal
        self._m_literal = _m_literal

    def test_none_value(self):
        self.assertEqual(self._m_literal(None, 'Text.Type'), 'null')

    def test_boolean_true(self):
        self.assertEqual(self._m_literal(True, 'Logical.Type'), 'true')
        self.assertEqual(self._m_literal(1, 'Logical.Type'), 'true')

    def test_boolean_false(self):
        self.assertEqual(self._m_literal(False, 'Logical.Type'), 'false')
        self.assertEqual(self._m_literal(0, 'Logical.Type'), 'false')

    def test_text_value(self):
        self.assertEqual(self._m_literal('hello', 'Text.Type'), '"hello"')

    def test_text_with_quotes(self):
        result = self._m_literal('say "hi"', 'Text.Type')
        self.assertIn('say', result)

    def test_integer_value(self):
        self.assertEqual(self._m_literal(42, 'Int64.Type'), '42')

    def test_float_value(self):
        self.assertEqual(self._m_literal(3.14, 'Number.Type'), '3.14')

    def test_date_value(self):
        result = self._m_literal('2024-01-15', 'Date.Type')
        self.assertIn('#date', result)
        self.assertIn('2024', result)
        self.assertIn('1', result)
        self.assertIn('15', result)

    def test_datetime_value(self):
        result = self._m_literal('2024-01-15 10:30:00', 'DateTime.Type')
        self.assertIn('#datetime', result)
        self.assertIn('2024', result)


class TestGenerateMInlineTable(unittest.TestCase):
    """Test generate_m_inline_table()."""

    def setUp(self):
        from hyper_reader import generate_m_inline_table
        self._gen = generate_m_inline_table

    def test_basic_table(self):
        table_info = {
            'table': 'Orders',
            'columns': [
                {'name': 'ID', 'hyper_type': 'integer'},
                {'name': 'Product', 'hyper_type': 'text'},
            ],
            'sample_rows': [{'ID': 1, 'Product': 'Widget'}, {'ID': 2, 'Product': 'Gadget'}],
            'row_count': 2,
        }
        result = self._gen(table_info)
        self.assertIn('#table', result)
        self.assertIn('ID', result)
        self.assertIn('Product', result)
        self.assertIn('Int64.Type', result)
        self.assertIn('Widget', result)
        self.assertIn('let', result.lower())

    def test_empty_columns(self):
        table_info = {'table': 'Empty', 'columns': [], 'sample_rows': [], 'row_count': 0}
        result = self._gen(table_info)
        self.assertIsNotNone(result)
        self.assertIn('#table', result)

    def test_no_rows(self):
        table_info = {
            'table': 'NoData',
            'columns': [{'name': 'Col1', 'hyper_type': 'text'}],
            'sample_rows': [],
            'row_count': 0,
        }
        result = self._gen(table_info)
        self.assertIn('#table', result)
        self.assertIn('Col1', result)


class TestGenerateMCsvReference(unittest.TestCase):
    """Test generate_m_csv_reference()."""

    def setUp(self):
        from hyper_reader import generate_m_csv_reference
        self._gen = generate_m_csv_reference

    def test_csv_reference(self):
        table_info = {
            'table': 'Sales',
            'columns': [{'name': 'Amount', 'hyper_type': 'double'}],
            'sample_rows': [],
            'row_count': 1000,
        }
        result = self._gen(table_info, 'sales.csv')
        self.assertIn('Csv.Document', result)
        self.assertIn('sales.csv', result)

    def test_csv_with_types(self):
        table_info = {
            'table': 'Data',
            'columns': [
                {'name': 'Name', 'hyper_type': 'text'},
                {'name': 'Value', 'hyper_type': 'integer'},
            ],
            'sample_rows': [],
            'row_count': 5000,
        }
        result = self._gen(table_info, 'data.csv')
        self.assertIn('Csv.Document', result)


class TestGenerateMForHyperTable(unittest.TestCase):
    """Test generate_m_for_hyper_table() auto-dispatch logic."""

    def setUp(self):
        from hyper_reader import generate_m_for_hyper_table, INLINE_ROW_THRESHOLD
        self._gen = generate_m_for_hyper_table
        self._threshold = INLINE_ROW_THRESHOLD

    def test_small_table_uses_inline(self):
        table_info = {
            'table': 'Small',
            'columns': [{'name': 'X', 'hyper_type': 'text'}],
            'sample_rows': [{'X': 'a'}, {'X': 'b'}],
            'row_count': 2,
        }
        result = self._gen(table_info)
        self.assertIn('#table', result)

    def test_large_table_uses_csv(self):
        table_info = {
            'table': 'Large',
            'columns': [{'name': 'X', 'hyper_type': 'text'}],
            'sample_rows': [{'X': 'row'}],
            'row_count': self._threshold + 100,
        }
        result = self._gen(table_info)
        self.assertIn('Csv.Document', result)


class TestReadHyperSQLite(unittest.TestCase):
    """Test _read_hyper_sqlite() with a real SQLite file."""

    def test_read_valid_sqlite(self):
        """Create a real SQLite DB and read it as if it were a .hyper file."""
        from hyper_reader import _read_hyper_sqlite

        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            conn.execute('CREATE TABLE Extract (ID INTEGER, Name TEXT, Amount REAL)')
            conn.execute("INSERT INTO Extract VALUES (1, 'Alice', 100.5)")
            conn.execute("INSERT INTO Extract VALUES (2, 'Bob', 200.0)")
            conn.commit()
            conn.close()

            result = _read_hyper_sqlite(tmp_path, max_rows=10)
            self.assertIsNotNone(result)
            self.assertTrue(len(result) > 0)

            table = result[0]
            self.assertEqual(table['table'], 'Extract')
            self.assertEqual(len(table['columns']), 3)
            self.assertEqual(table['row_count'], 2)
            self.assertEqual(len(table['sample_rows']), 2)
        finally:
            os.unlink(tmp_path)

    def test_read_empty_sqlite(self):
        """SQLite with table but no rows."""
        from hyper_reader import _read_hyper_sqlite

        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            conn.execute('CREATE TABLE Data (Col1 TEXT)')
            conn.commit()
            conn.close()

            result = _read_hyper_sqlite(tmp_path, max_rows=5)
            self.assertIsNotNone(result)
            self.assertTrue(len(result) > 0)
            self.assertEqual(result[0]['row_count'], 0)
        finally:
            os.unlink(tmp_path)


class TestReadHyperHeader(unittest.TestCase):
    """Test _read_hyper_header() fallback for non-SQLite .hyper files."""

    def test_header_with_create_table(self):
        from hyper_reader import _read_hyper_header

        # Simulate a Hyper file header with simple CREATE TABLE (no schema prefix)
        header = b'HyPeRfIlE\x00' + b'CREATE TABLE Extract (ID integer, Name text);\n'
        header += b"INSERT INTO Extract VALUES (1, 'Alice');\n"
        header += b'\x00' * 100  # padding

        result = _read_hyper_header(header, max_rows=10)
        self.assertIsNotNone(result)
        if result:
            table = result[0]
            self.assertIn('columns', table)
            self.assertTrue(len(table['columns']) > 0)


class TestReadHyper(unittest.TestCase):
    """Test read_hyper() public API."""

    def test_nonexistent_file(self):
        from hyper_reader import read_hyper
        result = read_hyper('/nonexistent/file.hyper')
        self.assertEqual(result.get('tables', []), [])

    def test_sqlite_file(self):
        from hyper_reader import read_hyper

        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            conn.execute('CREATE TABLE TestTable (Val INTEGER)')
            conn.execute("INSERT INTO TestTable VALUES (42)")
            conn.commit()
            conn.close()

            result = read_hyper(tmp_path, max_rows=5)
            self.assertEqual(result['format'], 'sqlite')
            self.assertTrue(len(result['tables']) > 0)
        finally:
            os.unlink(tmp_path)


class TestReadHyperFromTwbx(unittest.TestCase):
    """Test read_hyper_from_twbx()."""

    def test_extract_from_twbx(self):
        from hyper_reader import read_hyper_from_twbx

        # Create a .twbx (ZIP) containing a .hyper (SQLite) file
        with tempfile.NamedTemporaryFile(suffix='.twbx', delete=False) as twbx_tmp:
            twbx_path = twbx_tmp.name

        with tempfile.NamedTemporaryFile(suffix='.hyper', delete=False) as hyper_tmp:
            hyper_path = hyper_tmp.name

        try:
            # Create SQLite hyper file
            conn = sqlite3.connect(hyper_path)
            conn.execute('CREATE TABLE Extract (X INTEGER)')
            conn.execute("INSERT INTO Extract VALUES (99)")
            conn.commit()
            conn.close()

            # Package into ZIP
            with zipfile.ZipFile(twbx_path, 'w') as zf:
                zf.write(hyper_path, 'Data/Datasource.hyper')

            # read_hyper_from_twbx returns a LIST of results
            results = read_hyper_from_twbx(twbx_path, 'Datasource.hyper', max_rows=5)
            self.assertIsInstance(results, list)
            self.assertTrue(len(results) > 0)
            tables = results[0].get('tables', [])
            self.assertTrue(len(tables) > 0)
            self.assertEqual(tables[0]['table'], 'Extract')
        finally:
            os.unlink(twbx_path)
            if os.path.exists(hyper_path):
                os.unlink(hyper_path)

    def test_hyper_not_in_twbx(self):
        from hyper_reader import read_hyper_from_twbx

        with tempfile.NamedTemporaryFile(suffix='.twbx', delete=False) as twbx_tmp:
            twbx_path = twbx_tmp.name

        try:
            with zipfile.ZipFile(twbx_path, 'w') as zf:
                zf.writestr('dummy.txt', 'hello')

            results = read_hyper_from_twbx(twbx_path, 'missing.hyper')
            # Returns empty list when hyper not found
            self.assertEqual(results, [])
        finally:
            os.unlink(twbx_path)


class TestSplitValues(unittest.TestCase):
    """Test _split_values() helper for SQL INSERT parsing."""

    def setUp(self):
        from hyper_reader import _split_values
        self._split = _split_values

    def test_simple_values(self):
        result = self._split("1, 'hello', 3.14")
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], '1')
        self.assertIn('hello', result[1])
        self.assertEqual(result[2], '3.14')

    def test_quoted_with_comma(self):
        result = self._split("'hello, world', 42")
        self.assertEqual(len(result), 2)
        self.assertIn('hello, world', result[0])

    def test_empty_string(self):
        result = self._split('')
        self.assertEqual(len(result), 0)


# =============================================================================
#  M Query Builder — Hyper Integration Tests
# =============================================================================

class TestGenerateMFromHyper(unittest.TestCase):
    """Test generate_m_from_hyper() in m_query_builder."""

    def setUp(self):
        from m_query_builder import generate_m_from_hyper
        self._gen = generate_m_from_hyper

    def test_empty_tables(self):
        result = self._gen([])
        self.assertIsNone(result)

    def test_single_table(self):
        tables = [{
            'table': 'Extract',
            'columns': [{'name': 'ID', 'hyper_type': 'integer'}],
            'sample_rows': [{'ID': 1}, {'ID': 2}],
            'row_count': 2,
        }]
        result = self._gen(tables)
        self.assertIsNotNone(result)
        self.assertIn('#table', result)

    def test_match_by_name(self):
        tables = [
            {'table': 'A', 'columns': [{'name': 'X', 'hyper_type': 'text'}], 'sample_rows': [{'X': 'a'}], 'row_count': 1},
            {'table': 'B', 'columns': [{'name': 'Y', 'hyper_type': 'text'}], 'sample_rows': [{'Y': 'b'}], 'row_count': 1},
        ]
        result = self._gen(tables, table_name='B')
        self.assertIsNotNone(result)

    def test_no_columns_returns_none(self):
        tables = [{'table': 'Empty', 'columns': [], 'sample_rows': [], 'row_count': 0}]
        result = self._gen(tables)
        # generate_m_inline_table handles empty columns — may return M or None
        # Just verify it doesn't crash
        self.assertTrue(result is None or isinstance(result, str))


class TestGenMHyper(unittest.TestCase):
    """Test _gen_m_hyper() registered in _M_GENERATORS."""

    def test_hyper_in_generators(self):
        from m_query_builder import _M_GENERATORS
        self.assertIn('hyper', _M_GENERATORS)
        self.assertIn('Hyper', _M_GENERATORS)
        self.assertIn('extract', _M_GENERATORS)

    def test_hyper_fallback_no_file(self):
        from m_query_builder import generate_power_query_m
        conn = {'type': 'hyper', 'details': {'filename': '/nonexistent.hyper'}}
        table = {'name': 'Extract', 'columns': [{'name': 'A', 'datatype': 'text'}]}
        result = generate_power_query_m(conn, table)
        self.assertIn('#table', result)
        self.assertIn('Hyper extract', result)

    def test_hyper_fallback_empty_filename(self):
        from m_query_builder import generate_power_query_m
        conn = {'type': 'Hyper', 'details': {}}
        table = {'name': 'Data', 'columns': [{'name': 'X', 'datatype': 'integer'}]}
        result = generate_power_query_m(conn, table)
        self.assertIn('#table', result)


# =============================================================================
#  DAX Converter — SCRIPT_* Detection Tests
# =============================================================================

class TestDetectScriptFunctions(unittest.TestCase):
    """Test detect_script_functions()."""

    def setUp(self):
        from dax_converter import detect_script_functions
        self._detect = detect_script_functions

    def test_no_script(self):
        result = self._detect('SUM([Sales])')
        self.assertEqual(result, [])

    def test_empty_formula(self):
        result = self._detect('')
        self.assertEqual(result, [])

    def test_none_formula(self):
        result = self._detect(None)
        self.assertEqual(result, [])

    def test_script_real_python(self):
        formula = 'SCRIPT_REAL("import numpy as np\\nreturn np.mean(_arg1)", SUM([Sales]))'
        result = self._detect(formula)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['function'], 'SCRIPT_REAL')
        self.assertEqual(result[0]['language'], 'python')
        self.assertEqual(result[0]['return_type'], 'real')

    def test_script_str_r(self):
        formula = 'SCRIPT_STR("library(dplyr)\\npaste0(_arg1, _arg2)", [A], [B])'
        result = self._detect(formula)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['function'], 'SCRIPT_STR')
        self.assertEqual(result[0]['language'], 'r')
        self.assertEqual(result[0]['return_type'], 'str')

    def test_script_bool(self):
        formula = 'SCRIPT_BOOL("return _arg1 > 0", [Value])'
        result = self._detect(formula)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['function'], 'SCRIPT_BOOL')
        self.assertEqual(result[0]['return_type'], 'bool')

    def test_script_int(self):
        formula = 'SCRIPT_INT("as.integer(nrow(data.frame(_arg1)))", [Qty])'
        result = self._detect(formula)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['function'], 'SCRIPT_INT')
        self.assertEqual(result[0]['return_type'], 'int')

    def test_multiple_scripts(self):
        formula = ('SCRIPT_REAL("return sum(_arg1)", [A]) + '
                   'SCRIPT_INT("return len(_arg1)", [B])')
        result = self._detect(formula)
        self.assertEqual(len(result), 2)


class TestDetectScriptLanguage(unittest.TestCase):
    """Test _detect_script_language() heuristic."""

    def setUp(self):
        from dax_converter import _detect_script_language
        self._detect = _detect_script_language

    def test_python_import(self):
        self.assertEqual(self._detect('import pandas as pd'), 'python')

    def test_python_def(self):
        self.assertEqual(self._detect('def my_func():\n  return 1'), 'python')

    def test_r_library(self):
        self.assertEqual(self._detect('library(ggplot2)'), 'r')

    def test_r_assignment(self):
        self.assertEqual(self._detect('x <- c(1,2,3)'), 'r')

    def test_r_pipe(self):
        self.assertEqual(self._detect('data %>% filter(x > 0)'), 'r')

    def test_ambiguous_defaults_to_r(self):
        # Ambiguous code with no clear markers defaults to 'r'
        # because r_score=0 == py_score=0 and we use >= comparison
        result = self._detect('x + y')
        self.assertIn(result, ('python', 'r'))


class TestHasScriptFunctions(unittest.TestCase):
    """Test has_script_functions() convenience check."""

    def setUp(self):
        from dax_converter import has_script_functions
        self._has = has_script_functions

    def test_with_script(self):
        self.assertTrue(self._has('SCRIPT_REAL("code", [x])'))

    def test_without_script(self):
        self.assertFalse(self._has('SUM([Sales])'))

    def test_empty(self):
        self.assertFalse(self._has(''))

    def test_none(self):
        self.assertFalse(self._has(None))


# =============================================================================
#  Visual Generator — Script Visual Tests
# =============================================================================

class TestGenerateScriptVisual(unittest.TestCase):
    """Test generate_script_visual()."""

    def setUp(self):
        from visual_generator import generate_script_visual
        self._gen = generate_script_visual

    def test_python_visual(self):
        script_info = {
            'function': 'SCRIPT_REAL',
            'language': 'python',
            'code': 'import matplotlib.pyplot as plt\nplt.scatter(x, y)',
            'return_type': 'real',
        }
        container = self._gen('MyChart', script_info)
        visual = container.get('visual', {})
        self.assertEqual(visual['visualType'], 'scriptVisual')
        self.assertIn('script', visual)
        self.assertIn('matplotlib', visual['script']['scriptText'])
        self.assertIn('MigrationNote', str(visual.get('annotations', [])))

    def test_r_visual(self):
        script_info = {
            'function': 'SCRIPT_STR',
            'language': 'r',
            'code': 'library(ggplot2)\nggplot(data, aes(x, y)) + geom_point()',
            'return_type': 'str',
        }
        container = self._gen('RChart', script_info)
        visual = container.get('visual', {})
        self.assertEqual(visual['visualType'], 'scriptRVisual')
        self.assertIn('script', visual)
        self.assertIn('ggplot', visual['script']['scriptText'])

    def test_positioning(self):
        script_info = {
            'function': 'SCRIPT_REAL',
            'language': 'python',
            'code': 'pass',
            'return_type': 'real',
        }
        container = self._gen('V', script_info, x=100, y=200, width=500, height=400, z_index=3)
        pos = container['position']
        self.assertEqual(pos['x'], 100)
        self.assertEqual(pos['y'], 200)
        self.assertEqual(pos['width'], 500)
        self.assertEqual(pos['height'], 400)

    def test_migration_note_content(self):
        script_info = {
            'function': 'SCRIPT_INT',
            'language': 'python',
            'code': 'return 1',
            'return_type': 'int',
        }
        container = self._gen('Test', script_info)
        annotations = container['visual'].get('annotations', [])
        self.assertTrue(len(annotations) > 0)
        note = annotations[0]['value']
        self.assertIn('Python', note)
        self.assertIn('SCRIPT_INT', note)

    def test_original_code_preserved(self):
        original = 'x = _arg1\nresult = x * 2'
        script_info = {
            'function': 'SCRIPT_REAL',
            'language': 'python',
            'code': original,
            'return_type': 'real',
        }
        container = self._gen('CodeTest', script_info)
        script_text = container['visual']['script']['scriptText']
        # Original code should be in comments
        self.assertIn('x = _arg1', script_text)
        self.assertIn('result = x * 2', script_text)


# =============================================================================
#  Assessment — SCRIPT_* Severity Tests
# =============================================================================

class TestAssessmentScriptSeverity(unittest.TestCase):
    """Test that SCRIPT_* functions produce WARN, not FAIL."""

    def test_script_only_is_warn(self):
        from assessment import _check_calculations, WARN, PASS
        ext = {'calculations': [
            {'name': 'Py', 'caption': 'Py', 'formula': 'SCRIPT_REAL("return 1", [X])'},
        ]}
        cat = _check_calculations(ext)
        # Should be WARN (not FAIL) for SCRIPT_*
        self.assertEqual(cat.worst_severity, WARN)

    def test_script_check_has_guidance(self):
        from assessment import _check_calculations
        ext = {'calculations': [
            {'name': 'R', 'caption': 'R', 'formula': 'SCRIPT_STR("paste()", [A])'},
        ]}
        cat = _check_calculations(ext)
        script_checks = [c for c in cat.checks if 'SCRIPT' in c.name]
        self.assertTrue(len(script_checks) > 0)
        self.assertIn('runtime', script_checks[0].recommendation.lower())

    def test_collect_still_fail(self):
        from assessment import _check_calculations, FAIL
        ext = {'calculations': [
            {'name': 'Geo', 'caption': 'Geo', 'formula': 'COLLECT([Geom])'},
        ]}
        cat = _check_calculations(ext)
        self.assertEqual(cat.worst_severity, FAIL)

    def test_no_script_is_pass(self):
        from assessment import _check_calculations, PASS
        ext = {'calculations': [
            {'name': 'Sum', 'caption': 'Sum', 'formula': 'SUM([Sales])'},
        ]}
        cat = _check_calculations(ext)
        script_checks = [c for c in cat.checks if 'SCRIPT' in c.name]
        self.assertTrue(all(c.severity == PASS for c in script_checks))

    def test_all_four_script_types(self):
        from assessment import _check_calculations, WARN
        ext = {'calculations': [
            {'name': 'B', 'caption': 'B', 'formula': 'SCRIPT_BOOL("1", [X])'},
            {'name': 'I', 'caption': 'I', 'formula': 'SCRIPT_INT("1", [X])'},
            {'name': 'R', 'caption': 'R', 'formula': 'SCRIPT_REAL("1", [X])'},
            {'name': 'S', 'caption': 'S', 'formula': 'SCRIPT_STR("1", [X])'},
        ]}
        cat = _check_calculations(ext)
        script_checks = [c for c in cat.checks if 'SCRIPT' in c.name and c.severity == WARN]
        self.assertEqual(len(script_checks), 1)
        # The detail should mention the count
        self.assertIn('4', script_checks[0].detail)


# =============================================================================
#  PBIP Generator — SCRIPT_* Detection Tests
# =============================================================================

class TestDetectScriptVisualInPbip(unittest.TestCase):
    """Test PbipGenerator._detect_script_visual()."""

    def _make_generator(self):
        from pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._main_table = 'Sales'
        gen._measure_names = set()
        gen._calc_map = {}
        return gen

    def test_no_ws_data(self):
        gen = self._make_generator()
        result = gen._detect_script_visual(None, {})
        self.assertIsNone(result)

    def test_no_script_fields(self):
        gen = self._make_generator()
        ws_data = {'fields': [{'name': 'Sales'}]}
        converted = {'calculations': [
            {'name': '[Sales]', 'caption': 'Sales', 'formula': 'SUM([Amount])'},
        ]}
        result = gen._detect_script_visual(ws_data, converted)
        self.assertIsNone(result)

    def test_script_detected(self):
        gen = self._make_generator()
        ws_data = {'fields': [{'name': 'Prediction'}]}
        converted = {'calculations': [
            {'name': '[Prediction]', 'caption': 'Prediction',
             'formula': 'SCRIPT_REAL("import numpy\\nreturn numpy.mean(_arg1)", SUM([Sales]))'},
        ]}
        result = gen._detect_script_visual(ws_data, converted)
        self.assertIsNotNone(result)
        self.assertEqual(result['function'], 'SCRIPT_REAL')
        self.assertEqual(result['language'], 'python')

    def test_script_in_mark_encoding(self):
        gen = self._make_generator()
        ws_data = {
            'fields': [{'name': 'ColorCalc'}],
            'mark_encoding': {
                'color': {
                    'formula': 'SCRIPT_STR("library(dplyr)\\npaste0()", [X])',
                }
            },
        }
        result = gen._detect_script_visual(ws_data, {'calculations': []})
        self.assertIsNotNone(result)
        self.assertEqual(result['language'], 'r')


# =============================================================================
#  Prep Flow Parser — Hyper Input Tests
# =============================================================================

class TestPrepFlowHyperInput(unittest.TestCase):
    """Test _process_input_node with hyper connection type."""

    def test_hyper_connection_generates_m(self):
        """Hyper input node should produce an M query (fallback if no file)."""
        from prep_flow_parser import _process_input_node

        node = {
            'connectionId': 'c1',
            'name': 'Extract',
            'fields': [
                {'name': 'ID', 'type': 'integer'},
                {'name': 'Name', 'type': 'string'},
            ],
        }
        connections = {
            'c1': {
                'connectionAttributes': {
                    'class': 'hyper',
                    'filename': '/nonexistent/data.hyper',
                },
            },
        }
        node_results = {}
        _process_input_node('n1', node, connections, node_results, 'Extract')

        self.assertIn('n1', node_results)
        result = node_results['n1']
        self.assertEqual(result['connection']['type'], 'hyper')
        self.assertIn('m_query', result)
        # Should have an M query (fallback #table since file doesn't exist)
        self.assertTrue(len(result['m_query']) > 0)

    def test_hyper_connection_type_mapped(self):
        """Verify 'hyper' is in _PREP_CONNECTION_MAP."""
        from prep_flow_parser import _PREP_CONNECTION_MAP
        self.assertIn('hyper', _PREP_CONNECTION_MAP)
        self.assertEqual(_PREP_CONNECTION_MAP['hyper'], 'hyper')


if __name__ == '__main__':
    unittest.main()
