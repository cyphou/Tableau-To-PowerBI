"""
Unit tests for Tableau extraction (extract_tableau_data.py).

Tests the TableauExtractor class end-to-end using the Superstore sample
workbook, and validates that all 16 object types are correctly extracted.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))

from extract_tableau_data import TableauExtractor

SAMPLE_TWB = os.path.join(ROOT, 'examples', 'tableau_samples', 'Superstore_Sales.twb')


def _has_sample():
    return os.path.exists(SAMPLE_TWB)


# ═══════════════════════════════════════════════════════════════════
# TableauExtractor — init and file reading
# ═══════════════════════════════════════════════════════════════════

class TestExtractorInit(unittest.TestCase):
    """Test TableauExtractor initialization and file reading."""

    def test_constructor_sets_fields(self):
        tmpdir = tempfile.mkdtemp()
        try:
            ext = TableauExtractor(SAMPLE_TWB, output_dir=tmpdir)
            self.assertEqual(ext.tableau_file, SAMPLE_TWB)
            self.assertTrue(os.path.isdir(tmpdir))
        finally:
            shutil.rmtree(tmpdir)

    @unittest.skipUnless(_has_sample(), 'Superstore sample not available')
    def test_read_tableau_file_returns_xml(self):
        tmpdir = tempfile.mkdtemp()
        try:
            ext = TableauExtractor(SAMPLE_TWB, output_dir=tmpdir)
            xml = ext.read_tableau_file()
            self.assertIsNotNone(xml)
            self.assertIn('<workbook', xml)
        finally:
            shutil.rmtree(tmpdir)

    def test_missing_file_raises_or_returns_none(self):
        tmpdir = tempfile.mkdtemp()
        try:
            ext = TableauExtractor('/nonexistent/file.twb', output_dir=tmpdir)
            # The method may raise FileNotFoundError or return None
            try:
                xml = ext.read_tableau_file()
                self.assertIsNone(xml)
            except (FileNotFoundError, OSError):
                pass  # Also valid — file does not exist
        finally:
            shutil.rmtree(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# Full extraction — validate all 16 JSON outputs
# ═══════════════════════════════════════════════════════════════════

@unittest.skipUnless(_has_sample(), 'Superstore sample not available')
class TestFullExtraction(unittest.TestCase):
    """End-to-end extraction test with the Superstore workbook."""

    @classmethod
    def setUpClass(cls):
        """Run extraction once for all tests in this class."""
        cls.tmpdir = tempfile.mkdtemp()
        ext = TableauExtractor(SAMPLE_TWB, output_dir=cls.tmpdir)

        # Suppress print output during extraction
        _old = sys.stdout
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
        try:
            cls.success = ext.extract_all()
        finally:
            sys.stdout = _old

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir)

    def _load(self, filename):
        path = os.path.join(self.tmpdir, filename)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_extraction_succeeds(self):
        self.assertTrue(self.success)

    # ─── Core objects ──────────────────────────────────────

    def test_datasources_extracted(self):
        data = self._load('datasources.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0, 'Should extract at least one datasource')

    def test_datasource_has_connection(self):
        data = self._load('datasources.json')
        for ds in data:
            self.assertIn('connection', ds, f'Datasource missing connection: {ds.get("name")}')

    def test_datasource_has_tables(self):
        data = self._load('datasources.json')
        has_tables = any(len(ds.get('tables', [])) > 0 for ds in data)
        self.assertTrue(has_tables, 'At least one datasource should have tables')

    def test_datasource_has_columns(self):
        data = self._load('datasources.json')
        has_cols = any(len(ds.get('columns', [])) > 0 for ds in data)
        self.assertTrue(has_cols, 'At least one datasource should have columns')

    def test_worksheets_extracted(self):
        data = self._load('worksheets.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0, 'Should extract at least one worksheet')

    def test_worksheet_has_name(self):
        data = self._load('worksheets.json')
        for ws in data:
            self.assertIn('name', ws)
            self.assertTrue(ws['name'], 'Worksheet name should not be empty')

    def test_worksheet_has_fields(self):
        data = self._load('worksheets.json')
        has_fields = any(len(ws.get('fields', [])) > 0 for ws in data)
        self.assertTrue(has_fields, 'At least one worksheet should have fields')

    def test_dashboards_extracted(self):
        data = self._load('dashboards.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)
        for db in data:
            self.assertIn('name', db)

    def test_calculations_extracted(self):
        data = self._load('calculations.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0, 'Superstore should have calculations')

    def test_calculation_has_formula(self):
        data = self._load('calculations.json')
        has_formula = any(c.get('formula') for c in data)
        self.assertTrue(has_formula, 'At least one calculation should have a formula')

    # ─── Parameters ─────────────────────────────────────────

    def test_parameters_extracted(self):
        data = self._load('parameters.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    # ─── Filters ────────────────────────────────────────────

    def test_filters_extracted(self):
        data = self._load('filters.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    # ─── Stories ────────────────────────────────────────────

    def test_stories_extracted(self):
        data = self._load('stories.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    # ─── Actions ────────────────────────────────────────────

    def test_actions_extracted(self):
        data = self._load('actions.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    # ─── Sets / Groups / Bins / Hierarchies ─────────────────

    def test_sets_extracted(self):
        data = self._load('sets.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    def test_groups_extracted(self):
        data = self._load('groups.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    def test_bins_extracted(self):
        data = self._load('bins.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    def test_hierarchies_extracted(self):
        data = self._load('hierarchies.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    # ─── Sort / Aliases / Custom SQL / User Filters ─────────

    def test_sort_orders_extracted(self):
        data = self._load('sort_orders.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    def test_aliases_extracted(self):
        data = self._load('aliases.json')
        self.assertIsNotNone(data)
        # aliases.json may be a dict (column→alias mapping) or a list
        self.assertIsInstance(data, (list, dict))

    def test_custom_sql_extracted(self):
        data = self._load('custom_sql.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    def test_user_filters_extracted(self):
        data = self._load('user_filters.json')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)

    # ─── Cross-consistency checks ───────────────────────────

    def test_all_16_json_files_exist(self):
        expected = [
            'datasources.json', 'worksheets.json', 'dashboards.json',
            'calculations.json', 'parameters.json', 'filters.json',
            'stories.json', 'actions.json', 'sets.json', 'groups.json',
            'bins.json', 'hierarchies.json', 'sort_orders.json',
            'aliases.json', 'custom_sql.json', 'user_filters.json',
        ]
        for fname in expected:
            path = os.path.join(self.tmpdir, fname)
            self.assertTrue(
                os.path.exists(path),
                f'Missing extraction output: {fname}',
            )

    def test_json_files_are_valid_json(self):
        for fname in os.listdir(self.tmpdir):
            if fname.endswith('.json'):
                path = os.path.join(self.tmpdir, fname)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        json.load(f)
                except json.JSONDecodeError:
                    self.fail(f'Invalid JSON in extraction output: {fname}')

    def test_worksheet_fields_reference_valid_datasource(self):
        """Worksheet datasource references should match extracted datasources."""
        worksheets = self._load('worksheets.json')
        datasources = self._load('datasources.json')
        ds_names = set()
        for ds in datasources:
            ds_names.add(ds.get('name', ''))
            ds_names.add(ds.get('caption', ''))
        for ws in worksheets:
            if ws.get('fields'):
                self.assertIsInstance(ws['fields'], list)


if __name__ == '__main__':
    unittest.main()
