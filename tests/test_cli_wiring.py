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


if __name__ == '__main__':
    unittest.main()
