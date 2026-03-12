"""Tests for Sprint 17 — CLI wiring, MigrationProgress, batch summary."""

import json
import os
import sys
import tempfile
import unittest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))


# ── MigrationProgress tests ─────────────────────────────────────────────────

class TestMigrationProgress(unittest.TestCase):
    """Tests for MigrationProgress tracker."""

    def test_basic_flow(self):
        from powerbi_import.progress import MigrationProgress
        p = MigrationProgress(total_steps=3, show_bar=False)
        p.start("Step 1")
        p.complete("done")
        p.start("Step 2")
        p.complete()
        p.start("Step 3")
        p.complete("finished")
        summary = p.summary()
        self.assertEqual(summary['completed'], 3)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(summary['skipped'], 0)

    def test_fail_step(self):
        from powerbi_import.progress import MigrationProgress
        p = MigrationProgress(total_steps=2, show_bar=False)
        p.start("Step 1")
        p.fail("error occurred")
        summary = p.summary()
        self.assertEqual(summary['failed'], 1)
        self.assertEqual(summary['completed'], 0)

    def test_skip_step(self):
        from powerbi_import.progress import MigrationProgress
        p = MigrationProgress(total_steps=2, show_bar=False)
        p.skip("Step 1", "not needed")
        p.start("Step 2")
        p.complete()
        summary = p.summary()
        self.assertEqual(summary['skipped'], 1)
        self.assertEqual(summary['completed'], 1)

    def test_callback_invoked(self):
        from powerbi_import.progress import MigrationProgress
        calls = []
        def on_step(idx, name, status, msg):
            calls.append((idx, name, status, msg))
        p = MigrationProgress(total_steps=2, on_step=on_step, show_bar=False)
        p.start("Extract")
        p.complete("ok")
        self.assertEqual(len(calls), 2)  # start + complete
        self.assertEqual(calls[0][2], 'in_progress')
        self.assertEqual(calls[1][2], 'complete')

    def test_elapsed_tracked(self):
        from powerbi_import.progress import MigrationProgress
        import time
        p = MigrationProgress(total_steps=1, show_bar=False)
        p.start("Step")
        time.sleep(0.01)
        p.complete()
        summary = p.summary()
        self.assertGreater(summary['total_elapsed'], 0)
        self.assertGreater(summary['steps'][0]['elapsed'], 0)


class TestNullProgress(unittest.TestCase):
    """Tests for NullProgress (no-op tracker)."""

    def test_null_progress_no_errors(self):
        from powerbi_import.progress import NullProgress
        p = NullProgress()
        p.start("Step")
        p.complete()
        p.fail("err")
        p.skip("Step", "reason")
        summary = p.summary()
        self.assertEqual(summary['completed'], 0)
        self.assertEqual(summary['steps'], [])


# ── Comparison Report tests ──────────────────────────────────────────────────

class TestComparisonReport(unittest.TestCase):
    """Tests for comparison_report.py."""

    def test_generate_comparison_report(self):
        from powerbi_import.comparison_report import generate_comparison_report
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal extracted data
            extract_dir = os.path.join(tmpdir, 'extract')
            os.makedirs(extract_dir)
            worksheets = [{'name': 'Sheet1', 'fields': ['Sales'], 'mark_type': 'bar'}]
            with open(os.path.join(extract_dir, 'worksheets.json'), 'w') as f:
                json.dump(worksheets, f)
            calcs = [{'name': 'Total Sales', 'formula': 'SUM([Sales])'}]
            with open(os.path.join(extract_dir, 'calculations.json'), 'w') as f:
                json.dump(calcs, f)
            with open(os.path.join(extract_dir, 'datasources.json'), 'w') as f:
                json.dump([], f)

            # Create minimal pbip structure
            pbip_dir = os.path.join(tmpdir, 'project')
            sm_dir = os.path.join(pbip_dir, 'project.SemanticModel', 'definition', 'tables')
            os.makedirs(sm_dir)
            with open(os.path.join(sm_dir, 'TestTable.tmdl'), 'w') as f:
                f.write("table 'TestTable'\n  column 'Sales'\n")
            report_dir = os.path.join(pbip_dir, 'project.Report', 'definition', 'pages', 'ReportSection1', 'visuals', 'v1')
            os.makedirs(report_dir)
            visual = {"$schema": "test", "visual": {"visualType": "clusteredBarChart"}}
            with open(os.path.join(report_dir, 'visual.json'), 'w') as f:
                json.dump(visual, f)

            # Generate
            out_path = os.path.join(tmpdir, 'comparison.html')
            result = generate_comparison_report(extract_dir, pbip_dir, output_path=out_path)
            self.assertIsNotNone(result)
            self.assertTrue(os.path.exists(out_path))
            with open(out_path, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Sheet1', html)
            self.assertIn('Comparison', html)


# ── Telemetry Dashboard tests ────────────────────────────────────────────────

class TestTelemetryDashboard(unittest.TestCase):
    """Tests for telemetry_dashboard.py."""

    def test_generate_dashboard_empty(self):
        from powerbi_import.telemetry_dashboard import generate_dashboard
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_dashboard(tmpdir)
            self.assertIsNotNone(result)
            self.assertTrue(os.path.exists(result))
            with open(result, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Telemetry Dashboard', html)

    def test_generate_dashboard_with_reports(self):
        from powerbi_import.telemetry_dashboard import generate_dashboard
        with tempfile.TemporaryDirectory() as tmpdir:
            report = {
                'report_name': 'TestWorkbook',
                'fidelity_score': 95,
                'items': [
                    {'name': 'Sales', 'status': 'exact', 'notes': ''},
                    {'name': 'Profit', 'status': 'approximate', 'notes': 'fallback applied'},
                ],
            }
            rpath = os.path.join(tmpdir, 'migration_report_Test_20260311.json')
            with open(rpath, 'w') as f:
                json.dump(report, f)

            result = generate_dashboard(tmpdir)
            self.assertTrue(os.path.exists(result))
            with open(result, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('TestWorkbook', html)
            self.assertIn('95', html)


# ── CLI argument parser tests ────────────────────────────────────────────────

class TestCLIArguments(unittest.TestCase):
    """Test new CLI flags are recognized."""

    def test_compare_flag(self):
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args(['test.twbx', '--compare'])
        self.assertTrue(args.compare)

    def test_dashboard_flag(self):
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args(['test.twbx', '--dashboard'])
        self.assertTrue(args.dashboard)

    def test_compare_default_false(self):
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertFalse(args.compare)
        self.assertFalse(args.dashboard)


# ── Batch summary formatting tests ───────────────────────────────────────────

class TestBatchSummaryFormatting(unittest.TestCase):
    """Test batch summary table output."""

    def test_to_dict_has_stats(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from migrate import MigrationStats
        stats = MigrationStats()
        stats.tmdl_tables = 5
        stats.visuals_generated = 10
        d = stats.to_dict()
        self.assertEqual(d['tmdl_tables'], 5)
        self.assertEqual(d['visuals_generated'], 10)

    def test_stats_initial_values(self):
        from migrate import MigrationStats
        stats = MigrationStats()
        self.assertEqual(stats.tmdl_tables, 0)
        self.assertEqual(stats.pages_generated, 0)
        self.assertFalse(stats.theme_applied)


# ── Consolidate reports tests ────────────────────────────────────────────────

class TestConsolidateReports(unittest.TestCase):
    """Tests for the --consolidate feature (run_consolidate_reports)."""

    def test_consolidate_arg_exists(self):
        """--consolidate CLI argument is recognized."""
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args(['--consolidate', '/tmp/test'])
        self.assertEqual(args.consolidate, '/tmp/test')

    def test_consolidate_default_none(self):
        """--consolidate defaults to None."""
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertIsNone(args.consolidate)

    def test_consolidate_nonexistent_dir(self):
        """Non-existent directory returns error code 1."""
        from migrate import run_consolidate_reports
        result = run_consolidate_reports('/nonexistent/path/xyz_9999')
        self.assertEqual(result, 1)

    def test_consolidate_empty_dir(self):
        """Empty directory with no reports returns 1."""
        from migrate import run_consolidate_reports
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_consolidate_reports(tmpdir)
            self.assertEqual(result, 1)

    def test_consolidate_with_reports(self):
        """Directory with migration reports produces consolidated dashboard."""
        from migrate import run_consolidate_reports
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake migration report
            report = {
                "report_name": "TestWorkbook",
                "created_at": "2025-01-01T00:00:00",
                "summary": {
                    "fidelity_score": 95,
                    "total_items": 10,
                    "exact": 9,
                    "approximate": 1,
                    "unsupported": 0,
                },
                "items": [],
            }
            rp = os.path.join(tmpdir, 'migration_report_TestWorkbook_20250101.json')
            with open(rp, 'w', encoding='utf-8') as f:
                json.dump(report, f)

            # Create fake metadata
            meta_dir = os.path.join(tmpdir, 'TestWorkbook')
            os.makedirs(meta_dir, exist_ok=True)
            metadata = {
                "tmdl_stats": {"tables": 3, "measures": 5, "columns": 20, "relationships": 2},
                "generated_output": {"pages": 2, "visuals": 8},
            }
            mp = os.path.join(meta_dir, 'migration_metadata.json')
            with open(mp, 'w', encoding='utf-8') as f:
                json.dump(metadata, f)

            result = run_consolidate_reports(tmpdir)
            self.assertEqual(result, 0)

            # Check dashboard was created
            dash = os.path.join(tmpdir, 'MIGRATION_DASHBOARD.html')
            self.assertTrue(os.path.isfile(dash))

            # Check HTML contains the workbook name
            with open(dash, encoding='utf-8') as f:
                html = f.read()
            self.assertIn('TestWorkbook', html)

    def test_consolidate_multiple_workbooks(self):
        """Consolidation merges multiple workbooks into one dashboard."""
        from migrate import run_consolidate_reports
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ['Sales', 'Marketing', 'Finance']:
                report = {
                    "report_name": name,
                    "created_at": "2025-01-01T00:00:00",
                    "summary": {
                        "fidelity_score": 100,
                        "total_items": 5,
                        "exact": 5,
                        "approximate": 0,
                        "unsupported": 0,
                    },
                    "items": [],
                }
                rp = os.path.join(tmpdir, f'migration_report_{name}_20250101.json')
                with open(rp, 'w', encoding='utf-8') as f:
                    json.dump(report, f)

                meta_dir = os.path.join(tmpdir, name)
                os.makedirs(meta_dir, exist_ok=True)
                metadata = {
                    "tmdl_stats": {"tables": 2, "measures": 3, "columns": 10, "relationships": 1},
                    "generated_output": {"pages": 1, "visuals": 4},
                }
                with open(os.path.join(meta_dir, 'migration_metadata.json'), 'w', encoding='utf-8') as f:
                    json.dump(metadata, f)

            result = run_consolidate_reports(tmpdir)
            self.assertEqual(result, 0)

            dash = os.path.join(tmpdir, 'MIGRATION_DASHBOARD.html')
            self.assertTrue(os.path.isfile(dash))

            with open(dash, encoding='utf-8') as f:
                html = f.read()
            for name in ['Sales', 'Marketing', 'Finance']:
                self.assertIn(name, html)

    def test_consolidate_nested_subdirectories(self):
        """Reports in nested subdirectories are discovered."""
        from migrate import run_consolidate_reports
        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate tiered structure: SIMPLE/migrated/..., COMPLEXE/migrated/...
            for folder, wb_name in [('SIMPLE', 'SalesReport'), ('COMPLEXE', 'LODMaps')]:
                sub = os.path.join(tmpdir, folder, 'migrated')
                os.makedirs(sub, exist_ok=True)
                report = {
                    "report_name": wb_name,
                    "created_at": "2025-01-01T00:00:00",
                    "summary": {
                        "fidelity_score": 98,
                        "total_items": 8,
                        "exact": 8,
                        "approximate": 0,
                        "unsupported": 0,
                    },
                    "items": [],
                }
                rp = os.path.join(sub, f'migration_report_{wb_name}_20250101.json')
                with open(rp, 'w', encoding='utf-8') as f:
                    json.dump(report, f)

                meta_dir = os.path.join(sub, wb_name)
                os.makedirs(meta_dir, exist_ok=True)
                metadata = {
                    "tmdl_stats": {"tables": 2, "measures": 4, "columns": 15, "relationships": 1},
                    "generated_output": {"pages": 1, "visuals": 3},
                }
                with open(os.path.join(meta_dir, 'migration_metadata.json'), 'w', encoding='utf-8') as f:
                    json.dump(metadata, f)

            result = run_consolidate_reports(tmpdir)
            self.assertEqual(result, 0)

            dash = os.path.join(tmpdir, 'MIGRATION_DASHBOARD.html')
            self.assertTrue(os.path.isfile(dash))

            with open(dash, encoding='utf-8') as f:
                html = f.read()
            self.assertIn('SalesReport', html)
            self.assertIn('LODMaps', html)

    def test_consolidate_keeps_latest_report(self):
        """When multiple report JSONs exist for same workbook, latest is used."""
        from migrate import run_consolidate_reports
        with tempfile.TemporaryDirectory() as tmpdir:
            # Older report
            old_report = {
                "report_name": "Sales",
                "created_at": "2025-01-01T00:00:00",
                "summary": {"fidelity_score": 80, "total_items": 5, "exact": 4,
                             "approximate": 1, "unsupported": 0},
                "items": [],
            }
            with open(os.path.join(tmpdir, 'migration_report_Sales_20250101.json'), 'w', encoding='utf-8') as f:
                json.dump(old_report, f)

            # Newer report (higher fidelity)
            new_report = {
                "report_name": "Sales",
                "created_at": "2025-06-01T00:00:00",
                "summary": {"fidelity_score": 99, "total_items": 5, "exact": 5,
                             "approximate": 0, "unsupported": 0},
                "items": [],
            }
            with open(os.path.join(tmpdir, 'migration_report_Sales_20250601.json'), 'w', encoding='utf-8') as f:
                json.dump(new_report, f)

            meta_dir = os.path.join(tmpdir, 'Sales')
            os.makedirs(meta_dir, exist_ok=True)
            with open(os.path.join(meta_dir, 'migration_metadata.json'), 'w', encoding='utf-8') as f:
                json.dump({"tmdl_stats": {"tables": 1}, "generated_output": {"pages": 1}}, f)

            result = run_consolidate_reports(tmpdir)
            self.assertEqual(result, 0)

    def test_consolidate_function_exists(self):
        """run_consolidate_reports is importable."""
        from migrate import run_consolidate_reports
        self.assertTrue(callable(run_consolidate_reports))


if __name__ == '__main__':
    unittest.main()
