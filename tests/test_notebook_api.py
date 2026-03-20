"""Tests for the notebook_api module (Sprint 72).

Covers: MigrationSession lifecycle, load/assess/preview/generate pipeline,
DAX override persistence, visual type override, notebook generation,
and output format compatibility.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

from powerbi_import.notebook_api import (
    MigrationSession,
    _make_markdown_cell,
    _make_code_cell,
)


class TestMigrationSessionInit(unittest.TestCase):
    """Test MigrationSession initialization and defaults."""

    def test_fresh_session(self):
        s = MigrationSession()
        self.assertIsNone(s._workbook_path)
        self.assertIsNone(s._extracted)
        self.assertEqual(s._dax_overrides, {})
        self.assertEqual(s._visual_overrides, {})

    def test_default_config(self):
        s = MigrationSession()
        cfg = s.get_config()
        self.assertEqual(cfg['calendar_start'], 2020)
        self.assertEqual(cfg['calendar_end'], 2030)
        self.assertEqual(cfg['culture'], 'en-US')
        self.assertEqual(cfg['mode'], 'import')

    def test_configure_updates(self):
        s = MigrationSession()
        result = s.configure(calendar_start=2018, culture='fr-FR')
        self.assertEqual(result['calendar_start'], 2018)
        self.assertEqual(result['culture'], 'fr-FR')
        # Other defaults preserved
        self.assertEqual(result['mode'], 'import')

    def test_configure_ignores_unknown(self):
        s = MigrationSession()
        result = s.configure(unknown_key='value')
        self.assertNotIn('unknown_key', result)


class TestRequireLoaded(unittest.TestCase):
    """Test that methods raise when no workbook is loaded."""

    def test_assess_requires_load(self):
        s = MigrationSession()
        with self.assertRaises(RuntimeError):
            s.assess()

    def test_preview_dax_requires_load(self):
        s = MigrationSession()
        with self.assertRaises(RuntimeError):
            s.preview_dax()

    def test_preview_m_requires_load(self):
        s = MigrationSession()
        with self.assertRaises(RuntimeError):
            s.preview_m()

    def test_preview_visuals_requires_load(self):
        s = MigrationSession()
        with self.assertRaises(RuntimeError):
            s.preview_visuals()

    def test_generate_requires_load(self):
        s = MigrationSession()
        with self.assertRaises(RuntimeError):
            s.generate()

    def test_validate_requires_generate(self):
        s = MigrationSession()
        with self.assertRaises(RuntimeError):
            s.validate()

    def test_deploy_requires_generate(self):
        s = MigrationSession()
        with self.assertRaises(RuntimeError):
            s.deploy('workspace-id')


class TestDaxOverrides(unittest.TestCase):
    """Test DAX override CRUD operations."""

    def test_edit_dax_stores_override(self):
        s = MigrationSession()
        s.edit_dax('Total Sales', 'SUM(Sales[Amount])')
        self.assertEqual(s.get_dax_overrides(), {
            'Total Sales': 'SUM(Sales[Amount])'
        })

    def test_edit_dax_overwrites(self):
        s = MigrationSession()
        s.edit_dax('M1', 'SUM(T[A])')
        s.edit_dax('M1', 'AVERAGE(T[A])')
        self.assertEqual(s.get_dax_overrides()['M1'], 'AVERAGE(T[A])')

    def test_clear_dax_override(self):
        s = MigrationSession()
        s.edit_dax('M1', 'SUM(A)')
        s.clear_dax_override('M1')
        self.assertEqual(s.get_dax_overrides(), {})

    def test_clear_nonexistent_override_no_error(self):
        s = MigrationSession()
        s.clear_dax_override('NoSuch')  # should not raise

    def test_multiple_overrides(self):
        s = MigrationSession()
        s.edit_dax('A', '1')
        s.edit_dax('B', '2')
        s.edit_dax('C', '3')
        self.assertEqual(len(s.get_dax_overrides()), 3)


class TestVisualOverrides(unittest.TestCase):
    """Test visual type override operations."""

    def test_override_visual_type(self):
        s = MigrationSession()
        s.override_visual_type('Sales Map', 'filledMap')
        self.assertEqual(s._visual_overrides, {'Sales Map': 'filledMap'})

    def test_override_visual_type_replaces(self):
        s = MigrationSession()
        s.override_visual_type('Chart1', 'lineChart')
        s.override_visual_type('Chart1', 'barChart')
        self.assertEqual(s._visual_overrides['Chart1'], 'barChart')


class TestPreviewDax(unittest.TestCase):
    """Test DAX preview with mock extracted data."""

    def _make_session_with_data(self):
        s = MigrationSession()
        s._extracted = {
            'calculations': [
                {'name': 'Total Sales', 'formula': 'SUM([Sales])'},
                {'name': 'Profit Ratio', 'formula': 'SUM([Profit]) / SUM([Sales])'},
                {'name': 'Empty', 'formula': ''},
            ],
            'datasources': [
                {
                    'name': 'DS1',
                    'tables': [
                        {
                            'name': 'Orders',
                            'columns': [
                                {'name': 'Sales'},
                                {'name': 'Profit'},
                            ]
                        }
                    ]
                }
            ],
        }
        return s

    def test_preview_returns_list(self):
        s = self._make_session_with_data()
        result = s.preview_dax()
        self.assertIsInstance(result, list)
        # Empty formula should be skipped
        self.assertEqual(len(result), 2)

    def test_preview_has_fields(self):
        s = self._make_session_with_data()
        result = s.preview_dax()
        for item in result:
            self.assertIn('name', item)
            self.assertIn('tableau_formula', item)
            self.assertIn('dax_formula', item)
            self.assertIn('status', item)

    def test_override_reflected_in_preview(self):
        s = self._make_session_with_data()
        s.edit_dax('Total Sales', 'CUSTOM_DAX()')
        result = s.preview_dax()
        ts = [r for r in result if r['name'] == 'Total Sales'][0]
        self.assertEqual(ts['dax_formula'], 'CUSTOM_DAX()')
        self.assertEqual(ts['status'], 'overridden')


class TestPreviewM(unittest.TestCase):
    """Test M query preview with mock extracted data."""

    def test_preview_m_returns_list(self):
        s = MigrationSession()
        s._extracted = {
            'datasources': [
                {
                    'name': 'DS1',
                    'connection': {'class': 'sqlserver', 'server': 'localhost', 'dbname': 'test'},
                    'tables': [
                        {'name': 'Orders'},
                    ]
                }
            ],
            'calculations': [],
        }
        result = s.preview_m()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIn('m_expression', result[0])
        self.assertEqual(result[0]['table'], 'Orders')

    def test_preview_m_empty_datasources(self):
        s = MigrationSession()
        s._extracted = {'datasources': [], 'calculations': []}
        result = s.preview_m()
        self.assertEqual(result, [])


class TestPreviewVisuals(unittest.TestCase):
    """Test visual mapping preview with mock data."""

    def test_preview_returns_list(self):
        s = MigrationSession()
        s._extracted = {
            'worksheets': [
                {'name': 'Sheet1', 'mark_type': 'bar', 'fields': ['f1', 'f2']},
                {'name': 'Sheet2', 'mark_type': 'line', 'fields': ['f3']},
            ]
        }
        result = s.preview_visuals()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['worksheet'], 'Sheet1')
        self.assertEqual(result[0]['field_count'], 2)
        self.assertFalse(result[0]['overridden'])

    def test_visual_override_reflected(self):
        s = MigrationSession()
        s._extracted = {
            'worksheets': [
                {'name': 'Map1', 'mark_type': 'map', 'fields': []},
            ]
        }
        s.override_visual_type('Map1', 'filledMap')
        result = s.preview_visuals()
        self.assertEqual(result[0]['pbi_visual_type'], 'filledMap')
        self.assertTrue(result[0]['overridden'])


class TestNotebookGeneration(unittest.TestCase):
    """Test Jupyter notebook .ipynb generation."""

    def test_generate_notebook_creates_file(self):
        s = MigrationSession()
        with tempfile.TemporaryDirectory() as tmpdir:
            wb_path = os.path.join(tmpdir, 'test.twbx')
            out_path = os.path.join(tmpdir, 'test_migration.ipynb')
            result = s.generate_notebook(wb_path, output_path=out_path)
            self.assertEqual(result, out_path)
            self.assertTrue(os.path.exists(out_path))

    def test_notebook_is_valid_json(self):
        s = MigrationSession()
        with tempfile.TemporaryDirectory() as tmpdir:
            wb_path = os.path.join(tmpdir, 'test.twbx')
            out_path = os.path.join(tmpdir, 'notebook.ipynb')
            s.generate_notebook(wb_path, output_path=out_path)
            with open(out_path, 'r', encoding='utf-8') as f:
                nb = json.load(f)
            self.assertEqual(nb['nbformat'], 4)
            self.assertIn('cells', nb)

    def test_notebook_has_8_code_cells(self):
        s = MigrationSession()
        with tempfile.TemporaryDirectory() as tmpdir:
            wb_path = os.path.join(tmpdir, 'sample.twbx')
            out_path = os.path.join(tmpdir, 'nb.ipynb')
            s.generate_notebook(wb_path, output_path=out_path)
            with open(out_path, 'r', encoding='utf-8') as f:
                nb = json.load(f)
            code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
            self.assertEqual(len(code_cells), 8)

    def test_notebook_has_markdown_cells(self):
        s = MigrationSession()
        with tempfile.TemporaryDirectory() as tmpdir:
            wb_path = os.path.join(tmpdir, 'sample.twbx')
            out_path = os.path.join(tmpdir, 'nb.ipynb')
            s.generate_notebook(wb_path, output_path=out_path)
            with open(out_path, 'r', encoding='utf-8') as f:
                nb = json.load(f)
            md_cells = [c for c in nb['cells'] if c['cell_type'] == 'markdown']
            self.assertGreater(len(md_cells), 0)

    def test_notebook_contains_workbook_path(self):
        s = MigrationSession()
        with tempfile.TemporaryDirectory() as tmpdir:
            wb_path = os.path.join(tmpdir, 'My Workbook.twbx')
            out_path = os.path.join(tmpdir, 'nb.ipynb')
            s.generate_notebook(wb_path, output_path=out_path)
            with open(out_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('My Workbook', content)

    def test_notebook_default_output_path(self):
        s = MigrationSession()
        with tempfile.TemporaryDirectory() as tmpdir:
            wb_path = os.path.join(tmpdir, 'sales.twbx')
            result = s.generate_notebook(wb_path)
            expected = os.path.join(tmpdir, 'sales_migration.ipynb')
            self.assertEqual(result, expected)
            self.assertTrue(os.path.exists(expected))


class TestCellHelpers(unittest.TestCase):
    """Test _make_markdown_cell and _make_code_cell."""

    def test_markdown_cell_structure(self):
        cell = _make_markdown_cell('# Title')
        self.assertEqual(cell['cell_type'], 'markdown')
        self.assertEqual(cell['source'], ['# Title'])

    def test_code_cell_structure(self):
        cell = _make_code_cell('print("hello")')
        self.assertEqual(cell['cell_type'], 'code')
        self.assertEqual(cell['outputs'], [])
        self.assertIsNone(cell['execution_count'])

    def test_code_cell_has_source(self):
        cell = _make_code_cell('x = 1\ny = 2')
        self.assertEqual(cell['source'], ['x = 1\ny = 2'])


class TestListApproximated(unittest.TestCase):
    """Test list_approximated filtering."""

    def test_returns_only_approximated(self):
        s = MigrationSession()
        s._extracted = {
            'calculations': [
                {'name': 'Good', 'formula': 'SUM([Sales])'},
                {'name': 'Bad', 'formula': 'MAKEPOINT([Lat], [Lon])'},
            ],
            'datasources': [
                {'name': 'DS1', 'tables': [
                    {'name': 'T', 'columns': [
                        {'name': 'Sales'}, {'name': 'Lat'}, {'name': 'Lon'}
                    ]}
                ]}
            ],
        }
        approx = s.list_approximated()
        self.assertIsInstance(approx, list)
        # MAKEPOINT produces BLANK( which triggers approximated status
        names = [a['name'] for a in approx]
        self.assertIn('Bad', names)
        self.assertNotIn('Good', names)


if __name__ == '__main__':
    unittest.main()
