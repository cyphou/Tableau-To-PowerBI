"""Tests for the observability features (Sprint 74).

Covers: telemetry v2 events, JSONL load, dashboard generation with
tabs/search/sort/portfolio/bottleneck, backward compat with v1.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.telemetry import TelemetryCollector, TELEMETRY_VERSION
from powerbi_import.telemetry_dashboard import (
    generate_dashboard,
    _load_reports,
    _load_telemetry_events,
    _analyze_bottlenecks,
    _compute_portfolio_progress,
)


# ── Telemetry v2 ──────────────────────────────────────────

class TestTelemetryVersion(unittest.TestCase):
    def test_version_is_2(self):
        # Bumped to v3 in Sprint 131 (decisions + validations buckets).
        self.assertEqual(TELEMETRY_VERSION, 3)

    def test_collector_includes_version(self):
        t = TelemetryCollector(enabled=True)
        self.assertEqual(t.get_data()['telemetry_version'], 3)


class TestRecordEvent(unittest.TestCase):
    def test_record_event_enabled(self):
        t = TelemetryCollector(enabled=True)
        t.record_event('workbook_start', workbook='Sales')
        events = t.get_data()['events']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['type'], 'workbook_start')
        self.assertEqual(events[0]['workbook'], 'Sales')
        self.assertIn('ts', events[0])

    def test_record_event_disabled(self):
        t = TelemetryCollector(enabled=False)
        t.record_event('workbook_start', workbook='Sales')
        self.assertEqual(t.get_data()['events'], [])

    def test_multiple_events(self):
        t = TelemetryCollector(enabled=True)
        t.record_event('visual_converted', visual='bar', pbi='clusteredBarChart')
        t.record_event('measure_converted', name='Total', status='exact')
        t.record_event('workbook_end', fidelity=92.5)
        self.assertEqual(len(t.get_data()['events']), 3)

    def test_event_truncates_long_strings(self):
        t = TelemetryCollector(enabled=True)
        t.record_event('test', detail='x' * 500)
        self.assertEqual(len(t.get_data()['events'][0]['detail']), 200)

    def test_event_skips_none_values(self):
        t = TelemetryCollector(enabled=True)
        t.record_event('test', a=1, b=None, c='ok')
        ev = t.get_data()['events'][0]
        self.assertNotIn('b', ev)
        self.assertEqual(ev['a'], 1)
        self.assertEqual(ev['c'], 'ok')

    def test_events_list_in_data(self):
        t = TelemetryCollector(enabled=True)
        data = t.get_data()
        self.assertIn('events', data)
        self.assertIsInstance(data['events'], list)


class TestTelemetrySaveWithEvents(unittest.TestCase):
    def test_save_includes_events(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False) as f:
            log_path = f.name
        try:
            t = TelemetryCollector(enabled=True, log_path=log_path)
            t.start()
            t.record_event('test_event', key='value')
            t.finish()
            t.save()

            with open(log_path, 'r') as f:
                data = json.loads(f.readline())
            self.assertEqual(len(data['events']), 1)
            self.assertEqual(data['events'][0]['type'], 'test_event')
        finally:
            os.unlink(log_path)


class TestTelemetryBackwardCompat(unittest.TestCase):
    """Ensure existing stats and errors still work."""

    def test_record_stats(self):
        t = TelemetryCollector(enabled=True)
        t.record_stats(tables=5, columns=20)
        self.assertEqual(t.get_data()['stats']['tables'], 5)

    def test_record_error(self):
        t = TelemetryCollector(enabled=True)
        t.record_error('dax_conversion', 'ZN not found')
        self.assertEqual(len(t.get_data()['errors']), 1)


# ── JSONL Loading ─────────────────────────────────────────

class TestLoadTelemetryEvents(unittest.TestCase):
    def test_load_empty(self):
        result = _load_telemetry_events('/nonexistent/path/abc123.json')
        self.assertEqual(result, [])

    def test_load_valid_jsonl(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False, encoding='utf-8') as f:
            f.write(json.dumps({'session_id': 'a', 'events': []}) + '\n')
            f.write(json.dumps({'session_id': 'b', 'events': [{'type': 'x'}]}) + '\n')
            path = f.name
        try:
            entries = _load_telemetry_events(path)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]['session_id'], 'a')
        finally:
            os.unlink(path)

    def test_load_skips_bad_lines(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False, encoding='utf-8') as f:
            f.write(json.dumps({'session_id': 'a'}) + '\n')
            f.write('not json\n')
            f.write(json.dumps({'session_id': 'c'}) + '\n')
            path = f.name
        try:
            entries = _load_telemetry_events(path)
            self.assertEqual(len(entries), 2)
        finally:
            os.unlink(path)


# ── Dashboard Generation ──────────────────────────────────

class TestGenerateDashboard(unittest.TestCase):
    def test_generates_html_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'dash.html')
            result = generate_dashboard(tmpdir, output_path=out)
            self.assertEqual(result, out)
            self.assertTrue(os.path.exists(out))

    def test_html_contains_tabs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'dash.html')
            generate_dashboard(tmpdir, output_path=out)
            with open(out, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('data-tab="overview"', html)
            self.assertIn('data-tab="portfolio"', html)
            self.assertIn('data-tab="bottlenecks"', html)
            self.assertIn('data-tab="telemetry"', html)

    def test_html_contains_javascript(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'dash.html')
            generate_dashboard(tmpdir, output_path=out)
            with open(out, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('<script>', html)
            self.assertIn('filterTable', html)
            self.assertIn('sortTable', html)

    def test_html_contains_search_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock report
            report = {
                'workbook_name': 'Sales',
                'fidelity_score': 85,
                'items': [{'name': 'V1', 'status': 'migrated', 'notes': ''}],
                'timestamp': '2025-01-01T00:00:00',
            }
            os.makedirs(os.path.join(tmpdir, 'Sales'), exist_ok=True)
            with open(os.path.join(tmpdir, 'Sales', 'migration_report_Sales.json'), 'w') as f:
                json.dump(report, f)

            out = os.path.join(tmpdir, 'dash.html')
            generate_dashboard(tmpdir, output_path=out)
            with open(out, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('search-runs', html)
            self.assertIn('Sales', html)

    def test_dashboard_with_telemetry_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'telemetry.jsonl')
            with open(log_path, 'w') as f:
                f.write(json.dumps({
                    'session_id': 'abc',
                    'timestamp': '2025-01-01T10:00:00',
                    'duration_seconds': 5.2,
                    'platform': 'win32',
                    'events': [{'type': 'workbook_start'}],
                    'errors': [],
                }) + '\n')

            out = os.path.join(tmpdir, 'dash.html')
            generate_dashboard(tmpdir, output_path=out, telemetry_log=log_path)
            with open(out, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('abc', html)  # session id
            self.assertIn('5.2', html)  # duration

    def test_default_output_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_dashboard(tmpdir)
            expected = os.path.join(tmpdir, 'telemetry_dashboard.html')
            self.assertEqual(result, expected)


# ── Bottleneck Analysis ───────────────────────────────────

class TestAnalyzeBottlenecks(unittest.TestCase):
    def test_no_bottlenecks(self):
        reports = [{'items': [{'status': 'migrated', 'notes': ''}]}]
        result = _analyze_bottlenecks(reports, [])
        self.assertEqual(result, [])

    def test_partial_items_detected(self):
        reports = [{'items': [
            {'status': 'partial', 'type': 'visual', 'notes': 'Fallback'},
            {'status': 'partial', 'type': 'visual', 'notes': 'Gap'},
        ]}]
        result = _analyze_bottlenecks(reports, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['count'], 2)
        self.assertEqual(result[0]['category'], 'visual')

    def test_error_events_detected(self):
        entries = [{'errors': [
            {'category': 'dax', 'message': 'ZN not converted'},
            {'category': 'dax', 'message': 'MAKEPOINT unsupported'},
        ]}]
        result = _analyze_bottlenecks([], entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['count'], 2)

    def test_sorted_by_count(self):
        reports = [{'items': [
            {'status': 'failed', 'type': 'calc', 'notes': ''},
            {'status': 'skipped', 'type': 'visual', 'notes': ''},
            {'status': 'skipped', 'type': 'visual', 'notes': ''},
        ]}]
        result = _analyze_bottlenecks(reports, [])
        self.assertEqual(result[0]['category'], 'visual')  # 2 > 1


# ── Portfolio Progress ────────────────────────────────────

class TestComputePortfolioProgress(unittest.TestCase):
    def test_empty(self):
        p = _compute_portfolio_progress([])
        self.assertEqual(p['total'], 0)
        self.assertEqual(p['pct_complete'], 0)

    def test_all_completed(self):
        reports = [
            {'fidelity_score': 90},
            {'fidelity_score': 85},
            {'fidelity_score': 95},
        ]
        p = _compute_portfolio_progress(reports)
        self.assertEqual(p['completed'], 3)
        self.assertEqual(p['partial'], 0)
        self.assertEqual(p['pct_complete'], 100.0)

    def test_mixed(self):
        reports = [
            {'fidelity_score': 90},
            {'fidelity_score': 60},
            {'overall_fidelity': 0},
        ]
        p = _compute_portfolio_progress(reports)
        self.assertEqual(p['completed'], 1)
        self.assertEqual(p['partial'], 1)
        self.assertEqual(p['pending'], 1)

    def test_string_fidelity(self):
        reports = [{'fidelity_score': '85'}]
        p = _compute_portfolio_progress(reports)
        self.assertEqual(p['completed'], 1)


if __name__ == '__main__':
    unittest.main()
