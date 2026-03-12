"""Tests for powerbi_import.import_to_powerbi — import orchestrator.

Covers PowerBIImporter._load_converted_objects(), import_all() paths,
generate_powerbi_project() error handling, and main() CLI.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from import_to_powerbi import PowerBIImporter, main


class TestPowerBIImporterInit(unittest.TestCase):
    """Test constructor defaults."""

    def test_default_source_dir(self):
        imp = PowerBIImporter()
        self.assertEqual(imp.source_dir, 'tableau_export/')

    def test_custom_source_dir(self):
        imp = PowerBIImporter('/custom/dir')
        self.assertEqual(imp.source_dir, '/custom/dir')


class TestLoadConvertedObjects(unittest.TestCase):
    """Test _load_converted_objects() file loading."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_loads_existing_json(self):
        ds = [{'name': 'src', 'tables': []}]
        with open(os.path.join(self.tmpdir, 'datasources.json'), 'w') as f:
            json.dump(ds, f)
        imp = PowerBIImporter(self.tmpdir)
        data = imp._load_converted_objects()
        self.assertEqual(data['datasources'], ds)

    def test_missing_files_default_to_empty(self):
        imp = PowerBIImporter(self.tmpdir)
        data = imp._load_converted_objects()
        self.assertEqual(data['datasources'], [])
        self.assertEqual(data['worksheets'], [])
        self.assertIsInstance(data['aliases'], dict)

    def test_invalid_json_defaults(self):
        with open(os.path.join(self.tmpdir, 'datasources.json'), 'w') as f:
            f.write('not json')
        imp = PowerBIImporter(self.tmpdir)
        data = imp._load_converted_objects()
        self.assertEqual(data['datasources'], [])

    def test_loads_all_16_keys(self):
        imp = PowerBIImporter(self.tmpdir)
        data = imp._load_converted_objects()
        expected_keys = {
            'datasources', 'worksheets', 'dashboards', 'calculations',
            'parameters', 'filters', 'stories', 'actions', 'sets',
            'groups', 'bins', 'hierarchies', 'sort_orders', 'aliases',
            'custom_sql', 'user_filters',
        }
        self.assertEqual(set(data.keys()), expected_keys)

    def test_aliases_default_is_dict(self):
        imp = PowerBIImporter(self.tmpdir)
        data = imp._load_converted_objects()
        self.assertIsInstance(data['aliases'], dict)

    def test_other_keys_default_is_list(self):
        imp = PowerBIImporter(self.tmpdir)
        data = imp._load_converted_objects()
        for key in ['datasources', 'worksheets', 'filters', 'stories']:
            self.assertIsInstance(data[key], list, f"{key} should default to list")


class TestImportAll(unittest.TestCase):
    """Test import_all() orchestration."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.imp = PowerBIImporter(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_datasources_prints_error(self):
        """import_all with no datasources should print error and return early."""
        with patch('builtins.print') as mock_print:
            self.imp.import_all()
        calls = [str(c) for c in mock_print.call_args_list]
        error_found = any('[ERROR]' in c for c in calls)
        self.assertTrue(error_found)

    def test_report_name_from_dashboard(self):
        ds = [{'name': 'src', 'tables': []}]
        with open(os.path.join(self.tmpdir, 'datasources.json'), 'w') as f:
            json.dump(ds, f)
        dash = [{'name': 'Sales Dashboard'}]
        with open(os.path.join(self.tmpdir, 'dashboards.json'), 'w') as f:
            json.dump(dash, f)
        with patch.object(self.imp, 'generate_powerbi_project') as mock_gen:
            self.imp.import_all()
        mock_gen.assert_called_once()
        args = mock_gen.call_args
        self.assertEqual(args[0][0], 'Sales Dashboard')

    def test_default_report_name(self):
        ds = [{'name': 'src'}]
        with open(os.path.join(self.tmpdir, 'datasources.json'), 'w') as f:
            json.dump(ds, f)
        with patch.object(self.imp, 'generate_powerbi_project') as mock_gen:
            self.imp.import_all()
        args = mock_gen.call_args
        self.assertEqual(args[0][0], 'Report')

    def test_custom_report_name(self):
        ds = [{'name': 'src'}]
        with open(os.path.join(self.tmpdir, 'datasources.json'), 'w') as f:
            json.dump(ds, f)
        with patch.object(self.imp, 'generate_powerbi_project') as mock_gen:
            self.imp.import_all(report_name='Custom')
        args = mock_gen.call_args
        self.assertEqual(args[0][0], 'Custom')

    def test_skip_pbip_generation(self):
        ds = [{'name': 'src'}]
        with open(os.path.join(self.tmpdir, 'datasources.json'), 'w') as f:
            json.dump(ds, f)
        with patch.object(self.imp, 'generate_powerbi_project') as mock_gen:
            self.imp.import_all(generate_pbip=False)
        mock_gen.assert_not_called()


class TestGeneratePowerBIProject(unittest.TestCase):
    """Test generate_powerbi_project() method."""

    def test_calls_generator(self):
        imp = PowerBIImporter()
        converted = {'datasources': [{'name': 'ds'}], 'worksheets': []}
        with patch('import_to_powerbi.PowerBIProjectGenerator') as MockGen:
            mock_instance = MagicMock()
            mock_instance.generate_project.return_value = '/out/report'
            MockGen.return_value = mock_instance
            imp.generate_powerbi_project('Report', converted)
        MockGen.assert_called_once()
        mock_instance.generate_project.assert_called_once()

    def test_custom_output_dir(self):
        imp = PowerBIImporter()
        converted = {'datasources': [{'name': 'ds'}]}
        with patch('import_to_powerbi.PowerBIProjectGenerator') as MockGen:
            mock_instance = MagicMock()
            mock_instance.generate_project.return_value = '/out/path'
            MockGen.return_value = mock_instance
            imp.generate_powerbi_project('Report', converted, output_dir='/custom/out')
        call_kwargs = MockGen.call_args
        # On Windows, os.path.abspath('/custom/out') adds drive letter
        self.assertIn('custom', str(call_kwargs).lower())

    def test_exception_handled_gracefully(self):
        imp = PowerBIImporter()
        converted = {'datasources': [{'name': 'ds'}]}
        with patch('import_to_powerbi.PowerBIProjectGenerator') as MockGen:
            MockGen.side_effect = Exception('test error')
            with patch('builtins.print') as mock_print:
                imp.generate_powerbi_project('Report', converted)
            calls = [str(c) for c in mock_print.call_args_list]
            warn_found = any('WARN' in c for c in calls)
            self.assertTrue(warn_found)

    def test_passes_calendar_params(self):
        imp = PowerBIImporter()
        converted = {'datasources': [{'name': 'ds'}]}
        with patch('import_to_powerbi.PowerBIProjectGenerator') as MockGen:
            mock_instance = MagicMock()
            mock_instance.generate_project.return_value = '/path'
            MockGen.return_value = mock_instance
            imp.generate_powerbi_project('R', converted,
                                         calendar_start=2018, calendar_end=2028,
                                         culture='fr-FR', model_mode='directquery')
        gen_call = mock_instance.generate_project.call_args
        self.assertEqual(gen_call.kwargs.get('calendar_start', gen_call[1].get('calendar_start')), 2018)


class TestMain(unittest.TestCase):
    """Test main() CLI entry point."""

    @patch('import_to_powerbi.PowerBIImporter')
    def test_main_default(self, MockImporter):
        mock_inst = MagicMock()
        MockImporter.return_value = mock_inst
        with patch('sys.argv', ['import_to_powerbi.py']):
            main()
        mock_inst.import_all.assert_called_once_with(generate_pbip=True)

    @patch('import_to_powerbi.PowerBIImporter')
    def test_main_no_pbip(self, MockImporter):
        mock_inst = MagicMock()
        MockImporter.return_value = mock_inst
        with patch('sys.argv', ['import_to_powerbi.py', '--no-pbip']):
            main()
        mock_inst.import_all.assert_called_once_with(generate_pbip=False)


if __name__ == '__main__':
    unittest.main()
