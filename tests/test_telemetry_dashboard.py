"""Tests for powerbi_import.telemetry_dashboard — HTML dashboard generation.

Covers _load_reports(), _esc(), generate_dashboard(), and main() CLI.
"""

import json
import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from telemetry_dashboard import (
    _load_reports,
    _esc,
    generate_dashboard,
    main,
)


class TestEsc(unittest.TestCase):
    """Test _esc() HTML helper."""

    def test_escapes_html(self):
        self.assertEqual(_esc('<script>'), '&lt;script&gt;')

    def test_escapes_ampersand(self):
        self.assertEqual(_esc('a & b'), 'a &amp; b')

    def test_empty_returns_empty(self):
        self.assertEqual(_esc(''), '')

    def test_none_returns_empty(self):
        self.assertEqual(_esc(None), '')

    def test_numeric_converted(self):
        self.assertEqual(_esc(42), '42')


class TestLoadReports(unittest.TestCase):
    """Test _load_reports() function."""

    def test_loads_reports_from_directory(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            report = {
                'workbook_name': 'Sales',
                'fidelity_score': 90,
                'items': [{'name': 'Sheet 1', 'status': 'migrated'}],
            }
            with open(os.path.join(tmpdir, 'migration_report_sales.json'), 'w') as f:
                json.dump(report, f)

            reports = _load_reports(tmpdir)
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0]['workbook_name'], 'Sales')
            self.assertIn('_file', reports[0])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_loads_nested_reports(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            sub = os.path.join(tmpdir, 'project1')
            os.makedirs(sub)
            with open(os.path.join(sub, 'migration_report_p1.json'), 'w') as f:
                json.dump({'workbook_name': 'P1', 'fidelity_score': 80}, f)

            reports = _load_reports(tmpdir)
            self.assertEqual(len(reports), 1)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_empty_directory(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            reports = _load_reports(tmpdir)
            self.assertEqual(reports, [])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_skips_invalid_json(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            with open(os.path.join(tmpdir, 'migration_report_bad.json'), 'w') as f:
                f.write('not json {{{')
            reports = _load_reports(tmpdir)
            self.assertEqual(reports, [])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_loads_multiple_reports_sorted(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            for name in ('migration_report_a.json', 'migration_report_b.json'):
                with open(os.path.join(tmpdir, name), 'w') as f:
                    json.dump({'workbook_name': name, 'fidelity_score': 75}, f)

            reports = _load_reports(tmpdir)
            self.assertEqual(len(reports), 2)
            # Should be sorted alphabetically
            self.assertIn('_a', reports[0]['_file'])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestGenerateDashboard(unittest.TestCase):
    """Test generate_dashboard() function."""

    def test_generates_html_with_reports(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            report = {
                'workbook_name': 'Sales Dashboard',
                'fidelity_score': 92,
                'timestamp': '2025-01-15T10:00:00',
                'items': [
                    {'name': 'Sheet 1', 'status': 'migrated', 'notes': ''},
                    {'name': 'Sheet 2', 'status': 'partial', 'notes': 'manual review needed'},
                    {'name': 'Sheet 3', 'status': 'skipped', 'notes': 'unsupported feature'},
                ],
            }
            with open(os.path.join(tmpdir, 'migration_report_sales.json'), 'w') as f:
                json.dump(report, f)

            output = os.path.join(tmpdir, 'dashboard.html')
            result = generate_dashboard(tmpdir, output)

            self.assertEqual(result, output)
            self.assertTrue(os.path.exists(output))

            with open(output, 'r', encoding='utf-8') as f:
                html = f.read()

            self.assertIn('<!DOCTYPE html>', html)
            self.assertIn('Migration Observability Dashboard', html)
            self.assertIn('Sales Dashboard', html)
            self.assertIn('92', html)
            # Status distribution table
            self.assertIn('migrated', html)
            # Common issues
            self.assertIn('Unsupported feature', html)
            self.assertIn('Manual review needed', html)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_generates_empty_dashboard(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            output = os.path.join(tmpdir, 'dashboard.html')
            result = generate_dashboard(tmpdir, output)

            self.assertTrue(os.path.exists(result))
            with open(result, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Total Migrations', html)
            # With 0 reports, should still show 0
            self.assertIn('>0<', html)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_default_output_path(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            result = generate_dashboard(tmpdir)
            expected = os.path.join(tmpdir, 'telemetry_dashboard.html')
            self.assertEqual(result, expected)
            self.assertTrue(os.path.exists(expected))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_fidelity_bar_coloring(self):
        """High, medium, low fidelity get different colors."""
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            for fid in [95, 60, 30]:
                with open(os.path.join(tmpdir, f'migration_report_{fid}.json'), 'w') as f:
                    json.dump({'workbook_name': f'WB{fid}', 'fidelity_score': fid, 'items': []}, f)

            output = os.path.join(tmpdir, 'dash.html')
            generate_dashboard(tmpdir, output)

            with open(output, 'r', encoding='utf-8') as f:
                html = f.read()

            # Green for 95%, orange for 60%, red for 30%
            self.assertIn('#4caf50', html)
            self.assertIn('#ff9800', html)
            self.assertIn('#f44336', html)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_issue_categories_fallback(self):
        """Items with 'fallback' in notes trigger Fallback category."""
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            report = {
                'workbook_name': 'Test',
                'fidelity_score': 80,
                'items': [
                    {'name': 'V1', 'status': 'partial', 'notes': 'Fallback to bar chart'},
                ],
            }
            with open(os.path.join(tmpdir, 'migration_report_t.json'), 'w') as f:
                json.dump(report, f)

            output = os.path.join(tmpdir, 'dash.html')
            generate_dashboard(tmpdir, output)

            with open(output, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Fallback applied', html)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_overall_fidelity_fallback_key(self):
        """Uses 'overall_fidelity' when 'fidelity_score' is absent."""
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dash_')
        try:
            report = {
                'report_name': 'LegacyReport',
                'overall_fidelity': 77,
                'items': [],
            }
            with open(os.path.join(tmpdir, 'migration_report_leg.json'), 'w') as f:
                json.dump(report, f)

            output = os.path.join(tmpdir, 'dash.html')
            generate_dashboard(tmpdir, output)

            with open(output, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('77', html)
            self.assertIn('LegacyReport', html)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestDashboardMain(unittest.TestCase):
    """Test main() CLI entry point."""

    def test_main_with_args(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dcli_')
        try:
            output = os.path.join(tmpdir, 'out.html')
            with patch('sys.argv', ['telemetry_dashboard.py', tmpdir, '-o', output]):
                main()
            self.assertTrue(os.path.exists(output))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_main_default_output(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_dcli_')
        try:
            with patch('sys.argv', ['telemetry_dashboard.py', tmpdir]):
                main()
            self.assertTrue(os.path.exists(
                os.path.join(tmpdir, 'telemetry_dashboard.html')
            ))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
