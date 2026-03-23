"""Sprint 109 — TDSX Hyper data inlining tests.

Validates that .hyper extract data from .twbx/.tdsx archives is inlined
into TMDL partition M expressions via generate_m_from_hyper().
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))


class TestHyperFilesLoadedInPipeline(unittest.TestCase):
    """hyper_files.json is loaded by _load_converted_objects()."""

    def test_hyper_files_key_present(self):
        import tempfile
        from import_to_powerbi import PowerBIImporter
        with tempfile.TemporaryDirectory() as tmpdir:
            imp = PowerBIImporter(tmpdir)
            data = imp._load_converted_objects()
            self.assertIn('hyper_files', data)
            self.assertEqual(data['hyper_files'], [])

    def test_hyper_files_loaded_from_json(self):
        import tempfile
        from import_to_powerbi import PowerBIImporter
        sample = [{'path': 'Data/Extract.hyper', 'filename': 'Extract.hyper',
                    'tables': [{'table': 'Extract', 'columns': []}]}]
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'hyper_files.json'), 'w') as f:
                json.dump(sample, f)
            imp = PowerBIImporter(tmpdir)
            data = imp._load_converted_objects()
            self.assertEqual(len(data['hyper_files']), 1)
            self.assertEqual(data['hyper_files'][0]['filename'], 'Extract.hyper')


class TestHyperInliningInTMDL(unittest.TestCase):
    """TMDL generator inlines hyper data into partition M expressions."""

    def _make_datasource(self, table_name='Extract', conn_type='hyper'):
        return {
            'name': 'TestDS',
            'connection': {'type': conn_type, 'details': {}},
            'connection_map': {},
            'tables': [{
                'name': table_name,
                'columns': [
                    {'name': 'ID', 'datatype': 'integer'},
                    {'name': 'Name', 'datatype': 'string'},
                ],
            }],
            'calculations': [],
            'relationships': [],
            'columns': [],
        }

    def _make_hyper_files(self, table_name='Extract'):
        return [{
            'path': 'Data/Extract.hyper',
            'filename': 'Extract.hyper',
            'hyper_reader_tables': [{
                'table': table_name,
                'columns': [
                    {'name': 'ID', 'hyper_type': 'integer'},
                    {'name': 'Name', 'hyper_type': 'text'},
                ],
                'sample_rows': [
                    {'ID': 1, 'Name': 'Alice'},
                    {'ID': 2, 'Name': 'Bob'},
                    {'ID': 3, 'Name': 'Charlie'},
                ],
                'row_count': 3,
            }],
        }]

    def _read_all_tmdl(self, tmpdir):
        table_dir = os.path.join(tmpdir, 'definition', 'tables')
        content = ''
        if os.path.isdir(table_dir):
            for tf in os.listdir(table_dir):
                if tf.endswith('.tmdl'):
                    with open(os.path.join(table_dir, tf), 'r', encoding='utf-8') as f:
                        content += f.read()
        return content

    def test_hyper_data_inlined_into_partition(self):
        from tmdl_generator import generate_tmdl
        import tempfile

        ds = self._make_datasource()
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            '_datasources': [ds], '_worksheets': [],
            'hyper_files': self._make_hyper_files(),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_tmdl(
                datasources=[ds],
                report_name='TestReport',
                extra_objects=extra,
                output_dir=tmpdir,
            )
            self.assertEqual(stats['tables'], 1)
            content = self._read_all_tmdl(tmpdir)
            self.assertIn('Alice', content, "Hyper inline data should contain 'Alice'")
            self.assertIn('Bob', content, "Hyper inline data should contain 'Bob'")

    def test_no_hyper_files_uses_fallback(self):
        from tmdl_generator import generate_tmdl
        import tempfile

        ds = self._make_datasource()
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            '_datasources': [ds], '_worksheets': [],
            'hyper_files': [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_tmdl(
                datasources=[ds],
                report_name='TestReport',
                extra_objects=extra,
                output_dir=tmpdir,
            )
            self.assertEqual(stats['tables'], 1)
            content = self._read_all_tmdl(tmpdir)
            self.assertIn('TODO', content)

    def test_hyper_inlining_skipped_when_prep_override_exists(self):
        from tmdl_generator import generate_tmdl
        import tempfile

        ds = self._make_datasource()
        ds['m_query_overrides'] = {
            'Extract': 'let\n    Source = Sql.Database("server", "db")\nin\n    Source'
        }
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            '_datasources': [ds], '_worksheets': [],
            'hyper_files': self._make_hyper_files(),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_tmdl(
                datasources=[ds],
                report_name='TestReport',
                extra_objects=extra,
                output_dir=tmpdir,
            )
            content = self._read_all_tmdl(tmpdir)
            self.assertIn('Sql.Database', content)
            self.assertNotIn('Alice', content)

    def test_hyper_inlining_with_extract_connection_type(self):
        from tmdl_generator import generate_tmdl
        import tempfile

        ds = self._make_datasource(conn_type='extract')
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            '_datasources': [ds], '_worksheets': [],
            'hyper_files': self._make_hyper_files(),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_tmdl(
                datasources=[ds],
                report_name='TestReport',
                extra_objects=extra,
                output_dir=tmpdir,
            )
            content = self._read_all_tmdl(tmpdir)
            self.assertIn('Alice', content)

    def test_hyper_inlining_with_dataengine_type(self):
        from tmdl_generator import generate_tmdl
        import tempfile

        ds = self._make_datasource(conn_type='dataengine')
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            '_datasources': [ds], '_worksheets': [],
            'hyper_files': self._make_hyper_files(),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_tmdl(
                datasources=[ds],
                report_name='TestReport',
                extra_objects=extra,
                output_dir=tmpdir,
            )
            content = self._read_all_tmdl(tmpdir)
            self.assertIn('Alice', content)

    def test_non_hyper_connection_untouched(self):
        from tmdl_generator import generate_tmdl
        import tempfile

        ds = self._make_datasource(conn_type='sqlserver')
        ds['connection'] = {
            'type': 'sqlserver',
            'details': {'server': 'localhost', 'database': 'testdb'},
        }
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            '_datasources': [ds], '_worksheets': [],
            'hyper_files': self._make_hyper_files(),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_tmdl(
                datasources=[ds],
                report_name='TestReport',
                extra_objects=extra,
                output_dir=tmpdir,
            )
            content = self._read_all_tmdl(tmpdir)
            # SQL Server connection should NOT have inline hyper data
            self.assertNotIn('Alice', content)

    def test_case_insensitive_table_matching(self):
        from tmdl_generator import generate_tmdl
        import tempfile

        ds = self._make_datasource(table_name='extract')  # lowercase
        hyper_files = self._make_hyper_files(table_name='Extract')  # PascalCase
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            '_datasources': [ds], '_worksheets': [],
            'hyper_files': hyper_files,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_tmdl(
                datasources=[ds],
                report_name='TestReport',
                extra_objects=extra,
                output_dir=tmpdir,
            )
            content = self._read_all_tmdl(tmpdir)
            self.assertIn('Alice', content)

    def test_multiple_tables_matched(self):
        """Multiple tables in one hyper file should all be inlined."""
        from tmdl_generator import generate_tmdl
        import tempfile

        ds = {
            'name': 'MultiDS',
            'connection': {'type': 'hyper', 'details': {}},
            'connection_map': {},
            'tables': [
                {'name': 'Orders', 'columns': [{'name': 'OrderID', 'datatype': 'integer'}]},
                {'name': 'Products', 'columns': [{'name': 'ProdName', 'datatype': 'string'}]},
            ],
            'calculations': [],
            'relationships': [],
            'columns': [],
        }
        hyper_files = [{
            'path': 'Data/Extract.hyper',
            'filename': 'Extract.hyper',
            'hyper_reader_tables': [
                {
                    'table': 'Orders',
                    'columns': [{'name': 'OrderID', 'hyper_type': 'integer'}],
                    'sample_rows': [{'OrderID': 100}, {'OrderID': 200}],
                    'row_count': 2,
                },
                {
                    'table': 'Products',
                    'columns': [{'name': 'ProdName', 'hyper_type': 'text'}],
                    'sample_rows': [{'ProdName': 'Widget'}],
                    'row_count': 1,
                },
            ],
        }]
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            '_datasources': [ds], '_worksheets': [],
            'hyper_files': hyper_files,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_tmdl(
                datasources=[ds],
                report_name='TestReport',
                extra_objects=extra,
                output_dir=tmpdir,
            )
            self.assertEqual(stats['tables'], 2)
            content = self._read_all_tmdl(tmpdir)
            self.assertIn('100', content)
            self.assertIn('Widget', content)


class TestGenerateMFromHyper(unittest.TestCase):
    """Unit tests for generate_m_from_hyper()."""

    def test_returns_m_with_inline_data(self):
        from m_query_builder import generate_m_from_hyper
        tables = [{
            'table': 'Orders',
            'columns': [
                {'name': 'OrderID', 'hyper_type': 'integer'},
                {'name': 'Product', 'hyper_type': 'text'},
            ],
            'sample_rows': [
                {'OrderID': 1, 'Product': 'Widget'},
                {'OrderID': 2, 'Product': 'Gadget'},
            ],
            'row_count': 2,
        }]
        result = generate_m_from_hyper(tables, table_name='Orders')
        self.assertIsNotNone(result)
        self.assertIn('Widget', result)
        self.assertIn('Gadget', result)

    def test_returns_none_for_empty(self):
        from m_query_builder import generate_m_from_hyper
        self.assertIsNone(generate_m_from_hyper([]))
        self.assertIsNone(generate_m_from_hyper(None))

    def test_matches_by_table_name(self):
        from m_query_builder import generate_m_from_hyper
        tables = [
            {'table': 'A', 'columns': [{'name': 'x', 'hyper_type': 'text'}],
             'sample_rows': [{'x': 'aaa'}], 'row_count': 1},
            {'table': 'B', 'columns': [{'name': 'y', 'hyper_type': 'text'}],
             'sample_rows': [{'y': 'bbb'}], 'row_count': 1},
        ]
        result = generate_m_from_hyper(tables, table_name='B')
        self.assertIsNotNone(result)
        self.assertIn('bbb', result)

    def test_uses_first_table_when_no_match(self):
        from m_query_builder import generate_m_from_hyper
        tables = [
            {'table': 'Only', 'columns': [{'name': 'z', 'hyper_type': 'text'}],
             'sample_rows': [{'z': 'zzz'}], 'row_count': 1},
        ]
        result = generate_m_from_hyper(tables, table_name='NonExistent')
        self.assertIsNotNone(result)
        self.assertIn('zzz', result)

    def test_no_sample_rows_produces_empty_table(self):
        from m_query_builder import generate_m_from_hyper
        tables = [{
            'table': 'Empty',
            'columns': [{'name': 'col1', 'hyper_type': 'text'}],
            'sample_rows': [],
            'row_count': 0,
        }]
        result = generate_m_from_hyper(tables)
        self.assertIsNotNone(result)
        self.assertIn('#table', result)


if __name__ == '__main__':
    unittest.main()
