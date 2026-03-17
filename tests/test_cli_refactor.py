"""Tests for Sprint 45 — CLI Refactoring & Function Decomposition.

Validates that the refactored helper functions extracted from large
monolithic functions (main, _build_argument_parser, run_batch_migration,
import_shared_model, _build_visual_query) behave correctly.
"""

import argparse
import os
import sys
import unittest
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))


# ── _build_argument_parser helper tests ──────────────────────────────────────

class TestArgumentParserHelpers(unittest.TestCase):
    """Tests for the 9 _add_*_args helpers and the dispatcher."""

    def _get_parser(self):
        import migrate
        return migrate._build_argument_parser()

    def test_parser_returns_argparse_parser(self):
        parser = self._get_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)

    def test_source_args_present(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertEqual(args.tableau_file, 'test.twbx')

    def test_output_args_present(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--output-dir', '/tmp/out', '--verbose'])
        self.assertEqual(args.output_dir, '/tmp/out')
        self.assertTrue(args.verbose)

    def test_batch_args_present(self):
        parser = self._get_parser()
        args = parser.parse_args(['--batch', '/tmp/dir'])
        self.assertEqual(args.batch, '/tmp/dir')

    def test_migration_args_present(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--dry-run', '--culture', 'fr-FR'])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.culture, 'fr-FR')

    def test_calendar_args(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--calendar-start', '2018',
                                  '--calendar-end', '2028'])
        self.assertEqual(args.calendar_start, 2018)
        self.assertEqual(args.calendar_end, 2028)

    def test_report_args_present(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--compare', '--dashboard'])
        self.assertTrue(args.compare)
        self.assertTrue(args.dashboard)

    def test_deploy_args_present(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--deploy', 'WS123'])
        self.assertEqual(args.deploy, 'WS123')

    def test_server_args_present(self):
        parser = self._get_parser()
        args = parser.parse_args(['--server', 'https://tab.example.com',
                                  '--workbook', 'Sales'])
        self.assertEqual(args.server, 'https://tab.example.com')
        self.assertEqual(args.workbook, 'Sales')

    def test_enterprise_args_present(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--parallel', '4', '--resume'])
        self.assertEqual(args.parallel, 4)
        self.assertTrue(args.resume)

    def test_shared_model_args_present(self):
        parser = self._get_parser()
        args = parser.parse_args(['--shared-model', 'a.twbx', 'b.twbx'])
        self.assertEqual(args.shared_model, ['a.twbx', 'b.twbx'])

    def test_all_groups_registered(self):
        """Every expected argument should parse without error."""
        parser = self._get_parser()
        args = parser.parse_args([
            'test.twbx', '--prep', 'flow.tfl', '--output-dir', '/tmp',
            '--verbose', '--dry-run', '--culture', 'en-US',
            '--calendar-start', '2020', '--calendar-end', '2030',
            '--compare', '--deploy', 'WS1', '--parallel', '2',
        ])
        self.assertEqual(args.tableau_file, 'test.twbx')
        self.assertEqual(args.prep, 'flow.tfl')
        self.assertEqual(args.deploy, 'WS1')
        self.assertEqual(args.parallel, 2)


# ── _run_single_migration helper tests ───────────────────────────────────────

class TestSingleMigrationHelpers(unittest.TestCase):
    """Tests for helpers extracted from main()'s single-file pipeline."""

    def test_print_single_migration_header(self):
        import migrate
        args = argparse.Namespace(
            tableau_file='test.twbx', prep=None, output_dir=None,
            dry_run=False, calendar_start=None, calendar_end=None,
            culture=None, mode='import', output_format='pbip',
            rollback=False, telemetry=False,
        )
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            migrate._print_single_migration_header(args)
            output = mock_out.getvalue()
        self.assertIn('TABLEAU TO POWER BI MIGRATION', output)
        self.assertIn('test.twbx', output)

    def test_print_header_with_options(self):
        import migrate
        args = argparse.Namespace(
            tableau_file='wb.twbx', prep='flow.tfl', output_dir='/tmp/out',
            dry_run=True, calendar_start=2018, calendar_end=2028,
            culture='fr-FR', mode='directquery', output_format='pbix',
            rollback=True, telemetry=True,
        )
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            migrate._print_single_migration_header(args)
            output = mock_out.getvalue()
        self.assertIn('wb.twbx', output)
        self.assertIn('flow.tfl', output)
        self.assertIn('/tmp/out', output)
        self.assertIn('DRY RUN', output)
        self.assertIn('2018', output)
        self.assertIn('fr-FR', output)
        self.assertIn('directquery', output)
        self.assertIn('Rollback', output)
        self.assertIn('Telemetry', output)

    def test_init_telemetry_disabled(self):
        import migrate
        args = argparse.Namespace(telemetry=False)
        result = migrate._init_telemetry(args)
        self.assertIsNone(result)

    def test_finalize_telemetry_none(self):
        """Finalize with None telemetry should not raise."""
        import migrate
        migrate._finalize_telemetry(None, True, {})  # should not raise


# ── _print_batch_summary tests ──────────────────────────────────────────────

class TestPrintBatchSummary(unittest.TestCase):
    """Tests for _print_batch_summary extracted from run_batch_migration."""

    def test_basic_summary(self):
        import migrate
        results = {
            'Workbook1': {'success': True, 'fidelity': 85,
                          'stats': {'tmdl_tables': 3, 'visuals_generated': 5}},
            'Workbook2': {'success': False, 'fidelity': None,
                          'stats': {}},
        }
        duration = timedelta(seconds=42)
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            with patch.object(migrate, 'run_batch_html_dashboard', return_value=None):
                succeeded, failed = migrate._print_batch_summary(results, duration, '/tmp/out')
        output = mock_out.getvalue()
        self.assertEqual(succeeded, 1)
        self.assertEqual(failed, 1)
        self.assertIn('Workbook1', output)
        self.assertIn('Workbook2', output)
        self.assertIn('OK', output)
        self.assertIn('FAIL', output)

    def test_all_succeeded(self):
        import migrate
        results = {
            'A': {'success': True, 'fidelity': 90, 'stats': {}},
            'B': {'success': True, 'fidelity': 80, 'stats': {}},
        }
        with patch('sys.stdout', new_callable=StringIO):
            with patch.object(migrate, 'run_batch_html_dashboard', return_value=None):
                s, f = migrate._print_batch_summary(results, timedelta(seconds=10), '/tmp')
        self.assertEqual(s, 2)
        self.assertEqual(f, 0)

    def test_aggregate_fidelity(self):
        import migrate
        results = {
            'A': {'success': True, 'fidelity': 60, 'stats': {}},
            'B': {'success': True, 'fidelity': 100, 'stats': {}},
        }
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            with patch.object(migrate, 'run_batch_html_dashboard', return_value=None):
                migrate._print_batch_summary(results, timedelta(seconds=5), '/tmp')
        output = mock_out.getvalue()
        self.assertIn('80.0%', output)  # avg of 60 and 100
        self.assertIn('60%', output)    # min
        self.assertIn('100%', output)   # max


# ── _classify_shelf_fields tests ─────────────────────────────────────────────

class TestClassifyShelfFields(unittest.TestCase):
    """Tests for _classify_shelf_fields extracted from _build_visual_query."""

    def _get_generator(self):
        from pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._measure_names = set()
        gen._field_map = {}
        return gen

    def test_rows_dims(self):
        gen = self._get_generator()
        fields = [{'name': 'Region', 'shelf': 'rows'}]
        result = gen._classify_shelf_fields(fields)
        self.assertEqual(len(result['rows_dims']), 1)
        self.assertEqual(result['rows_dims'][0]['name'], 'Region')

    def test_measure_value_shelf(self):
        gen = self._get_generator()
        gen._measure_names = {'Sales'}
        fields = [{'name': 'Sales', 'shelf': 'measure_value'}]
        result = gen._classify_shelf_fields(fields)
        self.assertEqual(len(result['expanded_meas']), 1)

    def test_color_dim_vs_meas(self):
        gen = self._get_generator()
        gen._measure_names = {'Profit'}
        fields = [
            {'name': 'Category', 'shelf': 'color'},
            {'name': 'Profit', 'shelf': 'color'},
        ]
        result = gen._classify_shelf_fields(fields)
        self.assertEqual(len(result['color_dims']), 1)
        self.assertEqual(len(result['color_meas']), 1)

    def test_tooltip_and_size(self):
        gen = self._get_generator()
        fields = [
            {'name': 'Info', 'shelf': 'tooltip'},
            {'name': 'Amount', 'shelf': 'size'},
        ]
        result = gen._classify_shelf_fields(fields)
        self.assertEqual(len(result['tooltip_fields']), 1)
        self.assertEqual(len(result['size_fields']), 1)

    def test_no_shelf_fallback(self):
        gen = self._get_generator()
        gen._measure_names = {'Revenue'}
        fields = [
            {'name': 'City', 'shelf': ''},
            {'name': 'Revenue', 'shelf': ''},
        ]
        result = gen._classify_shelf_fields(fields)
        self.assertEqual(len(result['other_dims']), 1)
        self.assertEqual(len(result['other_meas']), 1)

    def test_text_shelf(self):
        gen = self._get_generator()
        fields = [{'name': 'Label', 'shelf': 'text'}]
        result = gen._classify_shelf_fields(fields)
        self.assertEqual(len(result['text_fields']), 1)

    def test_columns_classification(self):
        gen = self._get_generator()
        gen._measure_names = {'Total'}
        fields = [
            {'name': 'Date', 'shelf': 'columns'},
            {'name': 'Total', 'shelf': 'columns'},
        ]
        result = gen._classify_shelf_fields(fields)
        self.assertEqual(len(result['cols_dims']), 1)
        self.assertEqual(len(result['cols_meas']), 1)

    def test_empty_fields(self):
        gen = self._get_generator()
        result = gen._classify_shelf_fields([])
        for key in result:
            self.assertEqual(len(result[key]), 0)


# ── import_shared_model refactoring tests ────────────────────────────────────

class TestSharedModelHelpers(unittest.TestCase):
    """Tests for helpers extracted from import_shared_model."""

    def test_create_model_explorer_report_creates_files(self):
        import tempfile
        import json
        from import_to_powerbi import PowerBIImporter

        gen = PowerBIImporter.__new__(PowerBIImporter)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.stdout', new_callable=StringIO):
                gen._create_model_explorer_report(tmpdir, 'TestModel')

            # Check .pbip file
            pbip_path = os.path.join(tmpdir, 'TestModel.pbip')
            self.assertTrue(os.path.exists(pbip_path))
            with open(pbip_path, 'r', encoding='utf-8') as f:
                pbip = json.load(f)
            self.assertIn('artifacts', pbip)

            # Check report directory
            report_dir = os.path.join(tmpdir, 'TestModel_Model.Report')
            self.assertTrue(os.path.isdir(report_dir))

            # Check .platform
            platform = os.path.join(report_dir, '.platform')
            self.assertTrue(os.path.exists(platform))
            with open(platform, 'r', encoding='utf-8') as f:
                plat = json.load(f)
            self.assertEqual(plat['metadata']['type'], 'Report')

            # Check definition.pbir
            pbir = os.path.join(report_dir, 'definition.pbir')
            self.assertTrue(os.path.exists(pbir))
            with open(pbir, 'r', encoding='utf-8') as f:
                pbir_data = json.load(f)
            self.assertIn('byPath', pbir_data['datasetReference'])

            # Check report.json
            report_json = os.path.join(report_dir, 'definition', 'report.json')
            self.assertTrue(os.path.exists(report_json))

    def test_save_shared_model_artifacts(self):
        import tempfile
        import json
        from import_to_powerbi import PowerBIImporter

        gen = PowerBIImporter.__new__(PowerBIImporter)

        # Create minimal assessment mock
        assessment = MagicMock()
        assessment.overall_score = 80
        assessment.recommendation = 'merge'
        assessment.table_overlaps = []
        assessment.column_overlaps = []
        assessment.measure_conflicts = []
        assessment.relationship_conflicts = []
        assessment.workbook_scores = {}
        assessment.isolated_tables = {}
        assessment.to_dict.return_value = {
            'overall_score': 80, 'recommendation': 'merge',
            'table_overlaps': [], 'column_overlaps': [],
            'measure_conflicts': [], 'relationship_conflicts': [],
            'workbook_scores': {}, 'isolated_tables': {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.stdout', new_callable=StringIO):
                with patch('powerbi_import.merge_report_html.generate_merge_html_report'):
                    with patch.dict('sys.modules', {'merge_report_html': MagicMock()}):
                        gen._save_shared_model_artifacts(
                            tmpdir, assessment, lineage=None,
                            save_config=False, workbook_names=['wb1'],
                            all_converted_objects=[{}], merged={},
                            model_name='TestModel',
                        )

            # Merge assessment JSON should exist
            assess_path = os.path.join(tmpdir, 'merge_assessment.json')
            self.assertTrue(os.path.exists(assess_path))


# ── _run_single_migration integration test ───────────────────────────────────

class TestRunSingleMigrationExists(unittest.TestCase):
    """Verify _run_single_migration is callable."""

    def test_function_exists(self):
        import migrate
        self.assertTrue(callable(migrate._run_single_migration))

    def test_function_signature(self):
        import inspect
        import migrate
        sig = inspect.signature(migrate._run_single_migration)
        self.assertIn('args', sig.parameters)


if __name__ == '__main__':
    unittest.main()
