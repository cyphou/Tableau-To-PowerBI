"""
Sprint 24 — Enterprise & Scale Features Tests

Covers:
- --resume: skip already-completed workbooks
- --jsonl-log: structured JSONL event logging
- --manifest: per-workbook config overrides
- --parallel: parallel batch migration
- _migrate_single_workbook helper function
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from migrate import (
    _build_argument_parser,
    _migrate_single_workbook,
    run_batch_migration,
    ExitCode,
)


class TestCLIArguments(unittest.TestCase):
    """Test that Sprint 24 CLI arguments are properly defined."""

    def setUp(self):
        self.parser = _build_argument_parser()

    def test_parallel_arg_accepted(self):
        args = self.parser.parse_args(['test.twbx', '--parallel', '4'])
        self.assertEqual(args.parallel, 4)

    def test_parallel_default_none(self):
        args = self.parser.parse_args(['test.twbx'])
        self.assertIsNone(args.parallel)

    def test_resume_flag(self):
        args = self.parser.parse_args(['test.twbx', '--resume'])
        self.assertTrue(args.resume)

    def test_resume_default_false(self):
        args = self.parser.parse_args(['test.twbx'])
        self.assertFalse(args.resume)

    def test_manifest_arg_accepted(self):
        args = self.parser.parse_args(['test.twbx', '--manifest', 'manifest.json'])
        self.assertEqual(args.manifest, 'manifest.json')

    def test_manifest_default_none(self):
        args = self.parser.parse_args(['test.twbx'])
        self.assertIsNone(args.manifest)

    def test_jsonl_log_arg_accepted(self):
        args = self.parser.parse_args(['test.twbx', '--jsonl-log', 'events.jsonl'])
        self.assertEqual(args.jsonl_log, 'events.jsonl')

    def test_jsonl_log_default_none(self):
        args = self.parser.parse_args(['test.twbx'])
        self.assertIsNone(args.jsonl_log)


class TestResumeLogic(unittest.TestCase):
    """Test --resume skips workbooks with existing .pbip output."""

    def test_resume_skips_completed_workbook(self):
        """When .pbip exists in output dir, resume should skip that workbook."""
        with tempfile.TemporaryDirectory() as td:
            # Create batch source dir with two .twbx files
            src = os.path.join(td, 'source')
            os.makedirs(src)
            twb1 = os.path.join(src, 'done.twbx')
            twb2 = os.path.join(src, 'pending.twbx')
            for f in [twb1, twb2]:
                with open(f, 'w') as fh:
                    fh.write('<workbook/>')

            # Create output dir with existing .pbip for 'done'
            out = os.path.join(td, 'output')
            done_dir = os.path.join(out, 'done')
            os.makedirs(done_dir)
            with open(os.path.join(done_dir, 'done.pbip'), 'w') as fh:
                fh.write('{}')

            # Mock the actual migration to track which workbooks are processed
            with patch('migrate._migrate_single_workbook') as mock_migrate:
                mock_migrate.return_value = {
                    'success': True, 'stats': {}, 'fidelity': 100,
                    'report_name': 'pending', 'output_dir': out,
                    'metadata_path': os.path.join(out, 'pending', 'migration_metadata.json'),
                }
                with patch('migrate.run_batch_html_dashboard'):
                    result = run_batch_migration(
                        batch_dir=src, output_dir=out, resume=True
                    )

                # Only 'pending' should be migrated
                self.assertEqual(mock_migrate.call_count, 1)
                call_args = mock_migrate.call_args
                self.assertEqual(call_args[1]['basename'], 'pending')

    def test_resume_all_completed_returns_success(self):
        """When all workbooks are already completed, return SUCCESS."""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'source')
            os.makedirs(src)
            twb = os.path.join(src, 'done.twbx')
            with open(twb, 'w') as fh:
                fh.write('<workbook/>')

            out = os.path.join(td, 'output')
            done_dir = os.path.join(out, 'done')
            os.makedirs(done_dir)
            with open(os.path.join(done_dir, 'done.pbip'), 'w') as fh:
                fh.write('{}')

            result = run_batch_migration(batch_dir=src, output_dir=out, resume=True)
            self.assertEqual(result, ExitCode.SUCCESS)


class TestJSONLLogging(unittest.TestCase):
    """Test --jsonl-log writes structured events."""

    def test_jsonl_batch_events_written(self):
        """JSONL log should contain batch_start and batch_end events."""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'source')
            os.makedirs(src)
            twb = os.path.join(src, 'test.twbx')
            with open(twb, 'w') as fh:
                fh.write('<workbook/>')

            out = os.path.join(td, 'output')
            log_path = os.path.join(td, 'events.jsonl')

            with patch('migrate._migrate_single_workbook') as mock_migrate:
                mock_migrate.return_value = {
                    'success': True, 'stats': {}, 'fidelity': 95,
                    'report_name': 'test', 'output_dir': out,
                    'metadata_path': os.path.join(out, 'test', 'migration_metadata.json'),
                }
                with patch('migrate.run_batch_html_dashboard'):
                    run_batch_migration(
                        batch_dir=src, output_dir=out, jsonl_log=log_path
                    )

            # Read JSONL events
            with open(log_path, 'r', encoding='utf-8') as f:
                events = [json.loads(line) for line in f if line.strip()]

            event_types = [e['event'] for e in events]
            self.assertIn('batch_start', event_types)
            self.assertIn('workbook_start', event_types)
            self.assertIn('workbook_end', event_types)
            self.assertIn('batch_end', event_types)

            # batch_start should have workbook_count
            batch_start = next(e for e in events if e['event'] == 'batch_start')
            self.assertEqual(batch_start['workbook_count'], 1)

            # workbook_end should have success and duration
            wb_end = next(e for e in events if e['event'] == 'workbook_end')
            self.assertTrue(wb_end['success'])
            self.assertIn('duration_sec', wb_end)

    def test_jsonl_resume_skip_event(self):
        """When resume skips a workbook, a resume_skip event should be logged."""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'source')
            os.makedirs(src)
            twb = os.path.join(src, 'done.twbx')
            with open(twb, 'w') as fh:
                fh.write('<workbook/>')

            out = os.path.join(td, 'output')
            done_dir = os.path.join(out, 'done')
            os.makedirs(done_dir)
            with open(os.path.join(done_dir, 'done.pbip'), 'w') as fh:
                fh.write('{}')

            log_path = os.path.join(td, 'events.jsonl')
            run_batch_migration(
                batch_dir=src, output_dir=out, resume=True, jsonl_log=log_path
            )

            with open(log_path, 'r', encoding='utf-8') as f:
                events = [json.loads(line) for line in f if line.strip()]

            event_types = [e['event'] for e in events]
            self.assertIn('resume_skip', event_types)


class TestManifestConfig(unittest.TestCase):
    """Test --manifest per-workbook config overrides."""

    def test_manifest_overrides_culture(self):
        """Manifest should override culture for specific workbooks."""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'source')
            os.makedirs(src)
            twb = os.path.join(src, 'report.twbx')
            with open(twb, 'w') as fh:
                fh.write('<workbook/>')

            out = os.path.join(td, 'output')
            manifest = [{'file': 'report.twbx', 'culture': 'fr-FR', 'calendar_start': 2020}]

            with patch('migrate._migrate_single_workbook') as mock_migrate:
                mock_migrate.return_value = {
                    'success': True, 'stats': {}, 'fidelity': 100,
                    'report_name': 'report', 'output_dir': out,
                    'metadata_path': os.path.join(out, 'report', 'migration_metadata.json'),
                }
                with patch('migrate.run_batch_html_dashboard'):
                    run_batch_migration(
                        batch_dir=src, output_dir=out, manifest=manifest
                    )

                call_args = mock_migrate.call_args
                self.assertEqual(call_args[1]['wb_culture'], 'fr-FR')
                self.assertEqual(call_args[1]['wb_cal_start'], 2020)

    def test_manifest_fallback_to_defaults(self):
        """When a workbook has no manifest entry, use default config."""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'source')
            os.makedirs(src)
            twb = os.path.join(src, 'other.twbx')
            with open(twb, 'w') as fh:
                fh.write('<workbook/>')

            out = os.path.join(td, 'output')
            manifest = [{'file': 'report.twbx', 'culture': 'fr-FR'}]

            with patch('migrate._migrate_single_workbook') as mock_migrate:
                mock_migrate.return_value = {
                    'success': True, 'stats': {}, 'fidelity': 100,
                    'report_name': 'other', 'output_dir': out,
                    'metadata_path': os.path.join(out, 'other', 'migration_metadata.json'),
                }
                with patch('migrate.run_batch_html_dashboard'):
                    run_batch_migration(
                        batch_dir=src, output_dir=out,
                        culture='en-US', manifest=manifest
                    )

                call_args = mock_migrate.call_args
                # Should use the default culture, not the manifest entry for 'report.twbx'
                self.assertEqual(call_args[1]['wb_culture'], 'en-US')


class TestParallelBatch(unittest.TestCase):
    """Test --parallel flag enables concurrent migration."""

    def test_parallel_batch_processes_workbooks(self):
        """Parallel mode should migrate all workbooks."""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'source')
            os.makedirs(src)
            for name in ['a.twbx', 'b.twbx', 'c.twbx']:
                with open(os.path.join(src, name), 'w') as fh:
                    fh.write('<workbook/>')

            out = os.path.join(td, 'output')

            with patch('migrate._migrate_single_workbook') as mock_migrate:
                mock_migrate.return_value = {
                    'success': True, 'stats': {}, 'fidelity': 100,
                    'report_name': 'test', 'output_dir': out,
                    'metadata_path': os.path.join(out, 'test', 'migration_metadata.json'),
                }
                with patch('migrate.run_batch_html_dashboard'):
                    result = run_batch_migration(
                        batch_dir=src, output_dir=out, parallel=2
                    )

                self.assertEqual(result, ExitCode.SUCCESS)
                self.assertEqual(mock_migrate.call_count, 3)

    def test_sequential_when_parallel_is_none(self):
        """Without --parallel, workbooks should be processed sequentially."""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'source')
            os.makedirs(src)
            with open(os.path.join(src, 'a.twbx'), 'w') as fh:
                fh.write('<workbook/>')

            out = os.path.join(td, 'output')

            with patch('migrate._migrate_single_workbook') as mock_migrate:
                mock_migrate.return_value = {
                    'success': True, 'stats': {}, 'fidelity': 100,
                    'report_name': 'a', 'output_dir': out,
                    'metadata_path': os.path.join(out, 'a', 'migration_metadata.json'),
                }
                with patch('migrate.run_batch_html_dashboard'):
                    result = run_batch_migration(
                        batch_dir=src, output_dir=out
                    )

                self.assertEqual(result, ExitCode.SUCCESS)
                self.assertEqual(mock_migrate.call_count, 1)


class TestMigrateSingleWorkbook(unittest.TestCase):
    """Test the _migrate_single_workbook helper function."""

    def test_extraction_failure_returns_false(self):
        """When extraction fails, result should indicate failure."""
        with tempfile.TemporaryDirectory() as td:
            with patch('migrate.run_extraction', return_value=False):
                result = _migrate_single_workbook(
                    tableau_file='fake.twbx',
                    basename='fake',
                    workbook_output_dir=td,
                    display_name='fake',
                    skip_extraction=False,
                    wb_prep=None,
                    wb_cal_start=None,
                    wb_cal_end=None,
                    wb_culture=None,
                )
                self.assertFalse(result['success'])
                self.assertEqual(result['error'], 'extraction')

    def test_skip_extraction_skips_extract(self):
        """When skip_extraction=True, extraction should be skipped."""
        with tempfile.TemporaryDirectory() as td:
            with patch('migrate.run_extraction') as mock_extract, \
                 patch('migrate.run_generation', return_value=True), \
                 patch('migrate.run_migration_report', return_value={'fidelity_score': 90}):
                result = _migrate_single_workbook(
                    tableau_file='fake.twbx',
                    basename='fake',
                    workbook_output_dir=td,
                    display_name='fake',
                    skip_extraction=True,
                    wb_prep=None,
                    wb_cal_start=2020,
                    wb_cal_end=2030,
                    wb_culture='en-US',
                )
                mock_extract.assert_not_called()
                self.assertTrue(result['success'])
                self.assertEqual(result['fidelity'], 90)

    def test_full_pipeline_success(self):
        """Successful extraction + generation + report → success."""
        with tempfile.TemporaryDirectory() as td:
            with patch('migrate.run_extraction', return_value=True), \
                 patch('migrate.run_generation', return_value=True), \
                 patch('migrate.run_migration_report', return_value={'fidelity_score': 95}):
                result = _migrate_single_workbook(
                    tableau_file='test.twbx',
                    basename='test',
                    workbook_output_dir=td,
                    display_name='test',
                    skip_extraction=False,
                    wb_prep=None,
                    wb_cal_start=None,
                    wb_cal_end=None,
                    wb_culture=None,
                )
                self.assertTrue(result['success'])
                self.assertEqual(result['fidelity'], 95)
                self.assertEqual(result['report_name'], 'test')


class TestManifestCLIParsing(unittest.TestCase):
    """Test manifest loading from CLI --manifest flag."""

    def test_manifest_file_loaded_in_main(self):
        """--manifest should load JSON and pass to run_batch_migration."""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'source')
            os.makedirs(src)
            twb = os.path.join(src, 'wb.twbx')
            with open(twb, 'w') as fh:
                fh.write('<workbook/>')

            manifest_path = os.path.join(td, 'manifest.json')
            manifest_data = [{'file': 'wb.twbx', 'culture': 'de-DE'}]
            with open(manifest_path, 'w') as fh:
                json.dump(manifest_data, fh)

            from migrate import main
            with patch('sys.argv', ['migrate.py', '--batch', src, '--manifest', manifest_path,
                                    '--output-dir', os.path.join(td, 'out')]):
                with patch('migrate.run_batch_migration') as mock_batch:
                    mock_batch.return_value = ExitCode.SUCCESS
                    main()
                    call_kwargs = mock_batch.call_args[1]
                    self.assertEqual(call_kwargs['manifest'], manifest_data)


class TestBatchNonExistentDir(unittest.TestCase):
    """Test batch migration with non-existent directory."""

    def test_nonexistent_batch_dir_returns_error(self):
        result = run_batch_migration('/nonexistent/path/that/does/not/exist')
        self.assertEqual(result, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
