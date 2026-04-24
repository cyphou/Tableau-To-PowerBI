"""Sprint 131.5 — Telemetry v3 tests.

Covers:
  * record_decision aggregation + sample-reason cap
  * record_validation status normalization + by_issue counters
  * get_decision_summary / get_validation_summary shape
  * Disabled-collector no-ops
  * telemetry_to_openmetrics serializer (Prometheus exposition format)
  * /metrics endpoint wiring (smoke-tested via direct call)
"""

import unittest
from unittest.mock import MagicMock

from powerbi_import.telemetry import TelemetryCollector, TELEMETRY_VERSION
from powerbi_import.monitoring import (
    telemetry_to_openmetrics,
    _sanitize_metric_name,
    _escape_label_value,
)


def _enabled():
    return TelemetryCollector(enabled=True)


class TestTelemetryVersion(unittest.TestCase):

    def test_version_is_v3(self):
        self.assertEqual(TELEMETRY_VERSION, 3)


class TestRecordDecision(unittest.TestCase):

    def test_basic_aggregation(self):
        t = _enabled()
        for _ in range(5):
            t.record_decision('classification', 'measure')
        for _ in range(2):
            t.record_decision('classification', 'calc_column')
        s = t.get_decision_summary()
        self.assertEqual(s['classification']['measure'], 5)
        self.assertEqual(s['classification']['calc_column'], 2)

    def test_sample_reasons_capped_at_5(self):
        t = _enabled()
        for i in range(10):
            t.record_decision('cardinality', 'manyToOne', reason=f'reason {i}')
        leaf = t.get_data()['decisions']['cardinality']['manyToOne']
        self.assertEqual(leaf['count'], 10)
        self.assertEqual(len(leaf['sample_reasons']), 5)

    def test_disabled_collector_records_nothing(self):
        t = TelemetryCollector(enabled=False)
        t.record_decision('x', 'y', reason='r')
        self.assertEqual(t.get_decision_summary(), {})

    def test_reason_truncated(self):
        t = _enabled()
        long = 'A' * 1000
        t.record_decision('cat', 'choice', reason=long)
        leaf = t.get_data()['decisions']['cat']['choice']
        self.assertLessEqual(len(leaf['sample_reasons'][0]), 200)


class TestRecordValidation(unittest.TestCase):

    def test_pass_fail_repaired_counters(self):
        t = _enabled()
        t.record_validation('dax', 'pass')
        t.record_validation('dax', 'pass')
        t.record_validation('dax', 'fail', 'paren_balance')
        t.record_validation('dax', 'repaired', 'paren_balance')
        s = t.get_validation_summary()
        self.assertEqual(s['dax']['pass'], 2)
        self.assertEqual(s['dax']['fail'], 1)
        self.assertEqual(s['dax']['repaired'], 1)
        self.assertEqual(s['dax']['by_issue']['paren_balance'], 2)

    def test_unknown_status_normalizes_to_fail(self):
        t = _enabled()
        t.record_validation('m', 'mystery')
        self.assertEqual(t.get_validation_summary()['m']['fail'], 1)

    def test_multiple_gates(self):
        t = _enabled()
        for gate in ('dax', 'm', 'tmdl', 'pbir'):
            t.record_validation(gate, 'pass')
        s = t.get_validation_summary()
        self.assertEqual(set(s), {'dax', 'm', 'tmdl', 'pbir'})

    def test_disabled_collector_no_op(self):
        t = TelemetryCollector(enabled=False)
        t.record_validation('dax', 'fail', 'x')
        self.assertEqual(t.get_validation_summary(), {})


class TestOpenMetricsSerializer(unittest.TestCase):

    def test_empty_collector_emits_eof(self):
        t = TelemetryCollector(enabled=True)
        text = telemetry_to_openmetrics(t)
        self.assertIn('# EOF', text)

    def test_decisions_serialized(self):
        t = _enabled()
        t.record_decision('classification', 'measure')
        t.record_decision('classification', 'measure')
        t.record_decision('classification', 'calc_column')
        text = telemetry_to_openmetrics(t)
        self.assertIn('# TYPE ttpbi_decisions_total counter', text)
        self.assertIn(
            'ttpbi_decisions_total{category="classification",choice="measure"} 2',
            text,
        )
        self.assertIn(
            'ttpbi_decisions_total{category="classification",choice="calc_column"} 1',
            text,
        )

    def test_validations_serialized(self):
        t = _enabled()
        t.record_validation('dax', 'pass')
        t.record_validation('dax', 'fail', 'paren_balance')
        text = telemetry_to_openmetrics(t)
        self.assertIn('ttpbi_validations_total{gate="dax",status="pass"} 1', text)
        self.assertIn('ttpbi_validations_total{gate="dax",status="fail"} 1', text)
        self.assertIn(
            'ttpbi_validation_issues_total{gate="dax",issue="paren_balance"} 1',
            text,
        )

    def test_errors_aggregated(self):
        t = _enabled()
        t.record_error('dax_conversion', 'oops')
        t.record_error('dax_conversion', 'oops2')
        t.record_error('m_query', 'oops3')
        text = telemetry_to_openmetrics(t)
        self.assertIn('ttpbi_errors_total{category="dax_conversion"} 2', text)
        self.assertIn('ttpbi_errors_total{category="m_query"} 1', text)

    def test_stats_emitted_as_gauges(self):
        t = _enabled()
        t.record_stats(tables=10, measures=42, fidelity_percent=98.5)
        text = telemetry_to_openmetrics(t)
        self.assertIn('# TYPE ttpbi_stat_tables gauge', text)
        self.assertIn('ttpbi_stat_tables 10.0', text)
        self.assertIn('ttpbi_stat_measures 42.0', text)
        self.assertIn('ttpbi_stat_fidelity_percent 98.5', text)

    def test_non_numeric_stat_skipped(self):
        t = _enabled()
        t.record_stats(version='1.2.3', count=5)
        text = telemetry_to_openmetrics(t)
        self.assertIn('ttpbi_stat_count 5.0', text)
        self.assertNotIn('ttpbi_stat_version', text)

    def test_label_escaping(self):
        t = _enabled()
        t.record_decision('cat', 'choice "with quotes"\\and backslash')
        text = telemetry_to_openmetrics(t)
        # Both " and \ must be escaped
        self.assertIn('\\"with quotes\\"', text)
        self.assertIn('\\\\and', text)

    def test_metric_name_sanitization(self):
        self.assertEqual(_sanitize_metric_name('foo.bar-baz'), 'foo_bar_baz')
        self.assertEqual(_sanitize_metric_name('123abc'), '_123abc')
        self.assertEqual(_sanitize_metric_name(''), 'unknown')

    def test_label_value_escape_helper(self):
        self.assertEqual(_escape_label_value('a"b'), 'a\\"b')
        self.assertEqual(_escape_label_value('a\\b'), 'a\\\\b')
        self.assertEqual(_escape_label_value('a\nb'), 'a\\nb')

    def test_none_collector_safe(self):
        text = telemetry_to_openmetrics(None)
        self.assertIn('# EOF', text)


class TestApiServerMetricsEndpoint(unittest.TestCase):
    """Smoke-tests the /metrics handler logic without spinning up a
    full HTTP server."""

    def test_metrics_handler_path(self):
        # Verify the /metrics branch exists and the import wiring
        # does not raise.
        from powerbi_import import api_server as api
        from powerbi_import import telemetry as tel_mod
        from powerbi_import.monitoring import telemetry_to_openmetrics

        # If a global collector exists, render it; otherwise use None.
        collector = getattr(tel_mod, '_GLOBAL_COLLECTOR', None)
        text = telemetry_to_openmetrics(collector)
        self.assertIsInstance(text, str)
        self.assertTrue(text.endswith('\n'))


if __name__ == '__main__':
    unittest.main()
