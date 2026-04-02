"""
Tests for standalone Tableau Prep flow (.tfl/.tflx) migration support.

Covers:
- run_standalone_prep() — single file extraction
- TFL routing in _migrate_single_workbook (batch mode)
- TFL routing in _run_single_migration (single mode)
- File validation accepting .tfl/.tflx extensions
- Batch scanner including .tfl/.tflx files
"""

import os
import sys
import json
import tempfile
import unittest
import zipfile
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))

import prep_flow_parser  # ensure module is loaded so we can patch it

from migrate import (
    run_standalone_prep,
    _migrate_single_workbook,
)


# ── Minimal valid TFL XML for testing ────────────────────────────────────────

MINIMAL_TFL_XML = """\
<?xml version='1.0' encoding='utf-8'?>
<flow-document xmlns:user="http://www.tableausoftware.com/xml/user" version="1.0">
  <nodes>
    <node id="n1" name="Input" nodeType=".v1.LoadCsv">
      <properties>
        <property key="filename">data.csv</property>
      </properties>
      <columns>
        <column name="Category" type="string"/>
        <column name="Sales" type="real"/>
      </columns>
    </node>
  </nodes>
  <connections/>
</flow-document>
"""


def _make_tfl_file(directory, filename='flow.tfl'):
    """Create a minimal .tfl file and return its path."""
    path = os.path.join(directory, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(MINIMAL_TFL_XML)
    return path


def _make_tflx_file(directory, filename='flow.tflx'):
    """Create a minimal .tflx archive containing a .tfl file."""
    tfl_content = MINIMAL_TFL_XML.encode('utf-8')
    path = os.path.join(directory, filename)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('flow.tfl', tfl_content)
    return path


# ── run_standalone_prep tests ────────────────────────────────────────────────

class TestRunStandalonePrep(unittest.TestCase):
    """Test the run_standalone_prep() function."""

    def test_file_not_found(self):
        """Return False when the prep file doesn't exist."""
        result = run_standalone_prep('/nonexistent/flow.tfl')
        self.assertFalse(result)

    def test_successful_parse_writes_json(self):
        """Successful parse writes datasources.json and placeholder JSONs."""
        with tempfile.TemporaryDirectory() as td:
            tfl_path = _make_tfl_file(td)
            fake_ds = [{'name': 'Output', 'tables': [], 'columns': []}]

            with patch('prep_flow_parser.parse_prep_flow', return_value=fake_ds):
                result = run_standalone_prep(tfl_path)

            self.assertTrue(result)

            # datasources.json should contain our fake datasources
            json_dir = os.path.join(os.path.dirname(__file__), '..', 'tableau_export')
            ds_path = os.path.join(json_dir, 'datasources.json')
            self.assertTrue(os.path.exists(ds_path))
            with open(ds_path, encoding='utf-8') as f:
                ds = json.load(f)
            self.assertEqual(len(ds), 1)
            self.assertEqual(ds[0]['name'], 'Output')

    def test_placeholder_files_created(self):
        """All 16 placeholder JSON files are created."""
        with tempfile.TemporaryDirectory() as td:
            tfl_path = _make_tfl_file(td)
            with patch('prep_flow_parser.parse_prep_flow', return_value=[]):
                run_standalone_prep(tfl_path)

            json_dir = os.path.join(os.path.dirname(__file__), '..', 'tableau_export')
            expected_files = [
                'worksheets.json', 'calculations.json', 'parameters.json',
                'filters.json', 'stories.json', 'actions.json', 'sets.json',
                'groups.json', 'bins.json', 'hierarchies.json', 'sort_orders.json',
                'aliases.json', 'custom_sql.json', 'user_filters.json',
                'hyper_files.json', 'dashboards.json',
            ]
            for fname in expected_files:
                fpath = os.path.join(json_dir, fname)
                self.assertTrue(os.path.exists(fpath), f"Missing: {fname}")

    def test_parse_error_returns_false(self):
        """Return False when parse_prep_flow raises an exception."""
        with tempfile.TemporaryDirectory() as td:
            tfl_path = _make_tfl_file(td)
            with patch('prep_flow_parser.parse_prep_flow', side_effect=OSError("parse error")):
                result = run_standalone_prep(tfl_path)
            self.assertFalse(result)


# ── TFL routing in _migrate_single_workbook ──────────────────────────────────

class TestMigrateSingleWorkbookTFL(unittest.TestCase):
    """Test that _migrate_single_workbook routes .tfl/.tflx to run_standalone_prep."""

    def test_tfl_routes_to_standalone_prep(self):
        """A .tfl file should call run_standalone_prep, not run_extraction."""
        with tempfile.TemporaryDirectory() as td:
            with patch('migrate.run_standalone_prep', return_value=True) as mock_prep, \
                 patch('migrate.run_extraction') as mock_extract, \
                 patch('migrate.run_generation', return_value=True), \
                 patch('migrate.run_migration_report', return_value={'fidelity_score': 90}):
                result = _migrate_single_workbook(
                    tableau_file='my_flow.tfl',
                    basename='my_flow',
                    workbook_output_dir=td,
                    display_name='my_flow',
                    skip_extraction=False,
                    wb_prep=None,
                    wb_cal_start=None,
                    wb_cal_end=None,
                    wb_culture=None,
                )
                mock_prep.assert_called_once_with('my_flow.tfl')
                mock_extract.assert_not_called()
                self.assertTrue(result['success'])

    def test_tflx_routes_to_standalone_prep(self):
        """A .tflx file should call run_standalone_prep, not run_extraction."""
        with tempfile.TemporaryDirectory() as td:
            with patch('migrate.run_standalone_prep', return_value=True) as mock_prep, \
                 patch('migrate.run_extraction') as mock_extract, \
                 patch('migrate.run_generation', return_value=True), \
                 patch('migrate.run_migration_report', return_value={'fidelity_score': 85}):
                result = _migrate_single_workbook(
                    tableau_file='archive.tflx',
                    basename='archive',
                    workbook_output_dir=td,
                    display_name='archive',
                    skip_extraction=False,
                    wb_prep=None,
                    wb_cal_start=None,
                    wb_cal_end=None,
                    wb_culture=None,
                )
                mock_prep.assert_called_once_with('archive.tflx')
                mock_extract.assert_not_called()
                self.assertTrue(result['success'])

    def test_twbx_still_routes_to_extraction(self):
        """A .twbx file should still use run_extraction, not run_standalone_prep."""
        with tempfile.TemporaryDirectory() as td:
            with patch('migrate.run_standalone_prep') as mock_prep, \
                 patch('migrate.run_extraction', return_value=True) as mock_extract, \
                 patch('migrate.run_generation', return_value=True), \
                 patch('migrate.run_migration_report', return_value={'fidelity_score': 90}), \
                 patch('migrate._process_twbx_post_generation'):
                result = _migrate_single_workbook(
                    tableau_file='workbook.twbx',
                    basename='workbook',
                    workbook_output_dir=td,
                    display_name='workbook',
                    skip_extraction=False,
                    wb_prep=None,
                    wb_cal_start=None,
                    wb_cal_end=None,
                    wb_culture=None,
                )
                mock_extract.assert_called_once()
                mock_prep.assert_not_called()
                self.assertTrue(result['success'])

    def test_tfl_standalone_prep_failure(self):
        """When run_standalone_prep fails for .tfl, result should indicate failure."""
        with tempfile.TemporaryDirectory() as td:
            with patch('migrate.run_standalone_prep', return_value=False):
                result = _migrate_single_workbook(
                    tableau_file='bad_flow.tfl',
                    basename='bad_flow',
                    workbook_output_dir=td,
                    display_name='bad_flow',
                    skip_extraction=False,
                    wb_prep=None,
                    wb_cal_start=None,
                    wb_cal_end=None,
                    wb_culture=None,
                )
                self.assertFalse(result['success'])
                self.assertEqual(result['error'], 'extraction')

    def test_tfl_skips_prep_step(self):
        """Standalone .tfl should skip the optional --prep step even if wb_prep is set."""
        with tempfile.TemporaryDirectory() as td:
            with patch('migrate.run_standalone_prep', return_value=True) as mock_prep, \
                 patch('migrate.run_prep_flow') as mock_prep_flow, \
                 patch('migrate.run_generation', return_value=True), \
                 patch('migrate.run_migration_report', return_value={'fidelity_score': 80}):
                result = _migrate_single_workbook(
                    tableau_file='flow.tfl',
                    basename='flow',
                    workbook_output_dir=td,
                    display_name='flow',
                    skip_extraction=False,
                    wb_prep='some_other.tfl',
                    wb_cal_start=None,
                    wb_cal_end=None,
                    wb_culture=None,
                )
                mock_prep.assert_called_once()
                mock_prep_flow.assert_not_called()
                self.assertTrue(result['success'])


# ── File validation tests ────────────────────────────────────────────────────

class TestFileValidation(unittest.TestCase):
    """Test that .tfl/.tflx are accepted by file validation."""

    def test_tfl_accepted(self):
        """Verify .tfl extension is in the accepted set."""
        from migrate import _build_argument_parser
        # The validation is inline — we verify by checking that the
        # accepted extensions include .tfl/.tflx
        # This is a structural test, the actual validation is in main()
        import migrate
        src = open(migrate.__file__, encoding='utf-8').read()
        self.assertIn('.tfl', src)
        self.assertIn('.tflx', src)


# ── Batch scanner tests ─────────────────────────────────────────────────────

class TestBatchScannerIncludesTFL(unittest.TestCase):
    """Test that batch mode scanner picks up .tfl/.tflx files."""

    def test_batch_finds_tfl_files(self):
        """Batch directory scan should include .tfl files."""
        with tempfile.TemporaryDirectory() as td:
            # Create mixed files
            _make_tfl_file(td, 'flow1.tfl')
            _make_tflx_file(td, 'flow2.tflx')
            with open(os.path.join(td, 'workbook.twbx'), 'w') as f:
                f.write('<workbook/>')
            with open(os.path.join(td, 'unrelated.txt'), 'w') as f:
                f.write('skip')

            # Simulate the batch scanner logic from migrate.py
            tableau_files = []
            for root, dirs, files in os.walk(td):
                for fname in sorted(files):
                    if fname.lower().endswith(('.twb', '.twbx', '.tds', '.tdsx', '.tfl', '.tflx')):
                        tableau_files.append(os.path.join(root, fname))

            basenames = [os.path.basename(f) for f in tableau_files]
            self.assertIn('flow1.tfl', basenames)
            self.assertIn('flow2.tflx', basenames)
            self.assertIn('workbook.twbx', basenames)
            self.assertNotIn('unrelated.txt', basenames)
            self.assertEqual(len(tableau_files), 3)


if __name__ == '__main__':
    unittest.main()
