"""Tests for powerbi_import.comparison_report — side-by-side HTML report.

Covers _load_extracted(), _load_pbip(), _compare_worksheets(),
_compare_calculations(), _compare_datasources(), generate_comparison_report(),
and main() CLI.
"""

import json
import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from comparison_report import (
    _load_json,
    _load_extracted,
    _load_pbip,
    _compare_worksheets,
    _compare_calculations,
    _compare_datasources,
    generate_comparison_report,
    main,
)


class TestLoadJson(unittest.TestCase):
    """Test _load_json helper."""

    def test_load_valid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                         delete=False, encoding='utf-8') as tmp:
            json.dump({"key": "value"}, tmp)
            tmp_path = tmp.name
        try:
            result = _load_json(tmp_path)
            self.assertEqual(result, {"key": "value"})
        finally:
            os.unlink(tmp_path)

    def test_load_missing_file(self):
        result = _load_json('/nonexistent/path.json')
        self.assertEqual(result, {})

    def test_load_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                         delete=False, encoding='utf-8') as tmp:
            tmp.write("not valid json {{{")
            tmp_path = tmp.name
        try:
            result = _load_json(tmp_path)
            self.assertEqual(result, {})
        finally:
            os.unlink(tmp_path)


class TestLoadExtracted(unittest.TestCase):
    """Test _load_extracted() function."""

    def test_loads_all_json_files(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_extract_')
        try:
            # Create minimal extracted JSON files
            for name in ('worksheets', 'calculations', 'datasources',
                         'parameters', 'filters', 'dashboards'):
                with open(os.path.join(tmpdir, f'{name}.json'), 'w') as f:
                    json.dump([{'name': name}], f)

            result = _load_extracted(tmpdir)
            self.assertIn('worksheets', result)
            self.assertEqual(len(result['worksheets']), 1)
            self.assertIn('calculations', result)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_handles_missing_files(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_extract_')
        try:
            result = _load_extracted(tmpdir)
            # Should return empty collections for missing files
            self.assertIsInstance(result, dict)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestLoadPbip(unittest.TestCase):
    """Test _load_pbip() function."""

    def test_loads_pbip_structure(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_pbip_')
        try:
            # Create a minimal .pbip-like directory structure
            report_dir = os.path.join(tmpdir, 'Report.report')
            pages_dir = os.path.join(report_dir, 'pages', 'page1')
            visuals_dir = os.path.join(pages_dir, 'visuals', 'v1')
            os.makedirs(visuals_dir)

            # Create visual.json
            with open(os.path.join(visuals_dir, 'visual.json'), 'w') as f:
                json.dump({'visualType': 'barChart', 'title': 'My Bar'}, f)

            # Create page.json
            with open(os.path.join(pages_dir, 'page.json'), 'w') as f:
                json.dump({'displayName': 'Page 1'}, f)

            result = _load_pbip(tmpdir)
            self.assertIsInstance(result, dict)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_loads_empty_dir(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_pbip_')
        try:
            result = _load_pbip(tmpdir)
            self.assertIsInstance(result, dict)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_loads_tmdl_files(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_pbip_')
        try:
            # Create TMDL-like structure
            sm_dir = os.path.join(tmpdir, 'Model.SemanticModel', 'definition', 'tables')
            os.makedirs(sm_dir)
            with open(os.path.join(sm_dir, 'Orders.tmdl'), 'w') as f:
                f.write('table Orders\n  column OrderID : int64\n')

            result = _load_pbip(tmpdir)
            self.assertIsInstance(result, dict)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestCompareWorksheets(unittest.TestCase):
    """Test _compare_worksheets() function."""

    def test_compare_with_data(self):
        extracted = {
            'worksheets': [
                {'name': 'Sheet 1', 'columns': [
                    {'name': 'Amount', 'type': 'measure'},
                    {'name': 'Category', 'type': 'dimension'},
                ]},
            ]
        }
        pbip = {
            'visuals': [
                {'title': 'Sheet 1', 'visualType': 'barChart'},
            ]
        }
        result = _compare_worksheets(extracted, pbip)
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 1)

    def test_compare_empty(self):
        result = _compare_worksheets({}, {})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_compare_unmatched_worksheets(self):
        extracted = {
            'worksheets': [
                {'name': 'Sheet A', 'columns': []},
                {'name': 'Sheet B', 'columns': []},
            ]
        }
        pbip = {'visuals': []}
        result = _compare_worksheets(extracted, pbip)
        self.assertIsInstance(result, list)


class TestCompareCalculations(unittest.TestCase):
    """Test _compare_calculations() function."""

    def test_compare_with_calculations(self):
        extracted = {
            'calculations': [
                {'name': 'Total Sales', 'formula': 'SUM([Amount])'},
                {'name': 'Profit', 'formula': '[Revenue] - [Cost]'},
            ]
        }
        pbip = {
            'measures': [
                {'name': 'Total Sales', 'expression': 'SUM(Orders[Amount])'},
            ]
        }
        result = _compare_calculations(extracted, pbip)
        self.assertIsInstance(result, list)

    def test_compare_no_calculations(self):
        result = _compare_calculations({}, {})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)


class TestCompareDatasources(unittest.TestCase):
    """Test _compare_datasources() function."""

    def test_compare_with_datasources(self):
        extracted = {
            'datasources': [
                {'name': 'Sales Data', 'connection': {'type': 'SQL Server'},
                 'tables': [{'name': 'Orders', 'columns': ['OrderID', 'Amount']}]},
            ]
        }
        result = _compare_datasources(extracted)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Sales Data')
        self.assertEqual(result[0]['table_count'], 1)
        self.assertEqual(result[0]['column_count'], 2)

    def test_compare_empty_datasources(self):
        result = _compare_datasources({})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_compare_datasources_dict_wrapper(self):
        extracted = {
            'datasources': {'datasources': [
                {'name': 'DS', 'connection': {'class': 'postgres'},
                 'tables': []}
            ]}
        }
        result = _compare_datasources(extracted)
        self.assertEqual(len(result), 1)


class TestGenerateComparisonReport(unittest.TestCase):
    """Test generate_comparison_report() end-to-end."""

    def test_generates_html_file(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_cmp_')
        try:
            # Create extraction directory
            extract_dir = os.path.join(tmpdir, 'extract')
            os.makedirs(extract_dir)
            for name in ('worksheets', 'calculations', 'datasources',
                         'parameters', 'filters'):
                with open(os.path.join(extract_dir, f'{name}.json'), 'w') as f:
                    json.dump([], f)

            # Create PBIP directory (minimal)
            pbip_dir = os.path.join(tmpdir, 'pbip')
            os.makedirs(pbip_dir)

            output_path = os.path.join(tmpdir, 'comparison.html')
            result = generate_comparison_report(extract_dir, pbip_dir, output_path)

            self.assertTrue(os.path.exists(result))
            with open(result, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('<!DOCTYPE html>', content)
            self.assertIn('Comparison Report', content)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_generates_default_output_path(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_cmp_')
        try:
            extract_dir = os.path.join(tmpdir, 'extract')
            pbip_dir = os.path.join(tmpdir, 'pbip')
            os.makedirs(extract_dir)
            os.makedirs(pbip_dir)

            for name in ('worksheets', 'calculations', 'datasources'):
                with open(os.path.join(extract_dir, f'{name}.json'), 'w') as f:
                    json.dump([], f)

            result = generate_comparison_report(extract_dir, pbip_dir)
            self.assertTrue(os.path.exists(result))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_with_migration_report(self):
        """Picks up migration_report_*.json from pbip dir."""
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_cmp_')
        try:
            extract_dir = os.path.join(tmpdir, 'extract')
            pbip_dir = os.path.join(tmpdir, 'pbip')
            os.makedirs(extract_dir)
            os.makedirs(pbip_dir)

            for name in ('worksheets', 'calculations', 'datasources'):
                with open(os.path.join(extract_dir, f'{name}.json'), 'w') as f:
                    json.dump([], f)

            # Create a migration report
            report = {
                'workbook_name': 'TestWB',
                'fidelity_score': 85,
                'items': [{'name': 'Sheet 1', 'status': 'migrated'}],
            }
            with open(os.path.join(pbip_dir, 'migration_report_test.json'), 'w') as f:
                json.dump(report, f)

            result = generate_comparison_report(extract_dir, pbip_dir)
            self.assertTrue(os.path.exists(result))
            with open(result, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('html', content.lower())
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestComparisonReportMain(unittest.TestCase):
    """Test main() CLI entry point."""

    def test_main_with_args(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_cli_')
        try:
            extract_dir = os.path.join(tmpdir, 'extract')
            pbip_dir = os.path.join(tmpdir, 'pbip')
            os.makedirs(extract_dir)
            os.makedirs(pbip_dir)
            output = os.path.join(tmpdir, 'out.html')

            for name in ('worksheets', 'calculations', 'datasources'):
                with open(os.path.join(extract_dir, f'{name}.json'), 'w') as f:
                    json.dump([], f)

            with patch('sys.argv', ['comparison_report.py',
                                     extract_dir, pbip_dir,
                                     '--output', output]):
                main()

            self.assertTrue(os.path.exists(output))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
