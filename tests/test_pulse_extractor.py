"""
Tests for pulse_extractor module — Sprint 56.

Covers:
  - extract_pulse_metrics from XML
  - _parse_metric_element
  - has_pulse_metrics
  - Time grain mapping
  - Target extraction
  - Filter extraction
  - Edge cases: empty root, no metrics, duplicate names
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tableau_export.pulse_extractor import (
    extract_pulse_metrics,
    _parse_metric_element,
    has_pulse_metrics,
    _TIME_GRAIN_MAP,
)


def _make_xml(xml_str):
    """Parse XML string into ElementTree root."""
    return ET.fromstring(f'<workbook>{xml_str}</workbook>')


class TestTimeGrainMap(unittest.TestCase):
    def test_expected_grains(self):
        for grain in ('day', 'week', 'month', 'quarter', 'year'):
            self.assertIn(grain, _TIME_GRAIN_MAP)

    def test_month_maps_to_monthly(self):
        self.assertEqual(_TIME_GRAIN_MAP['month'], 'Monthly')


class TestHasPulseMetrics(unittest.TestCase):
    def test_none_root(self):
        self.assertFalse(has_pulse_metrics(None))

    def test_no_metrics(self):
        root = _make_xml('<datasources/>')
        self.assertFalse(has_pulse_metrics(root))

    def test_has_metric_element(self):
        root = _make_xml('<metric name="Revenue"/>')
        self.assertTrue(has_pulse_metrics(root))

    def test_has_pulse_metric_element(self):
        root = _make_xml('<pulse-metric name="Cost"/>')
        self.assertTrue(has_pulse_metrics(root))

    def test_has_metrics_container(self):
        root = _make_xml('<metrics><metric name="Profit"/></metrics>')
        self.assertTrue(has_pulse_metrics(root))


class TestParseMetricElement(unittest.TestCase):
    def test_basic_metric(self):
        elem = ET.fromstring(
            '<metric name="Revenue" measure="[Sales]" aggregation="SUM"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['name'], 'Revenue')
        self.assertEqual(result['measure_field'], 'Sales')
        self.assertEqual(result['aggregation'], 'SUM')

    def test_no_name_returns_none(self):
        elem = ET.fromstring('<metric/>')
        result = _parse_metric_element(elem)
        self.assertIsNone(result)

    def test_caption_as_name(self):
        elem = ET.fromstring('<metric caption="My Metric"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['name'], 'My Metric')

    def test_name_from_child_element(self):
        elem = ET.fromstring('<metric><name>Child Name</name></metric>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['name'], 'Child Name')

    def test_time_dimension(self):
        elem = ET.fromstring(
            '<metric name="M1" time-dimension="[Order Date]"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['time_dimension'], 'Order Date')

    def test_time_grain_mapping(self):
        elem = ET.fromstring(
            '<metric name="M1" time-grain="quarter"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['time_grain'], 'Quarterly')

    def test_unknown_time_grain_defaults_monthly(self):
        elem = ET.fromstring(
            '<metric name="M1" time-grain="biweekly"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['time_grain'], 'Monthly')

    def test_target_extraction(self):
        elem = ET.fromstring('''
            <metric name="Revenue">
                <target value="1000000" label="Annual Goal"/>
            </metric>
        ''')
        result = _parse_metric_element(elem)
        self.assertEqual(result['target_value'], 1000000.0)
        self.assertEqual(result['target_label'], 'Annual Goal')

    def test_target_non_numeric(self):
        elem = ET.fromstring('''
            <metric name="M1">
                <target value="not-a-number"/>
            </metric>
        ''')
        result = _parse_metric_element(elem)
        self.assertIsNone(result['target_value'])

    def test_target_empty_value(self):
        elem = ET.fromstring('''
            <metric name="M1">
                <target value=""/>
            </metric>
        ''')
        result = _parse_metric_element(elem)
        self.assertIsNone(result['target_value'])

    def test_filter_extraction(self):
        elem = ET.fromstring('''
            <metric name="M1">
                <filter column="[Region]" type="categorical">
                    <value>West</value>
                    <value>East</value>
                </filter>
            </metric>
        ''')
        result = _parse_metric_element(elem)
        self.assertEqual(len(result['filters']), 1)
        self.assertEqual(result['filters'][0]['field'], 'Region')
        self.assertEqual(result['filters'][0]['values'], ['West', 'East'])

    def test_formula_extraction(self):
        elem = ET.fromstring(
            '<metric name="M1" formula="SUM([Sales])"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['definition_formula'], 'SUM([Sales])')

    def test_number_format(self):
        elem = ET.fromstring(
            '<metric name="M1" number-format="#,##0.00"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['number_format'], '#,##0.00')

    def test_description(self):
        elem = ET.fromstring(
            '<metric name="M1" description="Total revenue metric"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['description'], 'Total revenue metric')

    def test_all_fields_present(self):
        elem = ET.fromstring('<metric name="M1"/>')
        result = _parse_metric_element(elem)
        expected_keys = {
            'name', 'description', 'measure_field', 'time_dimension',
            'time_grain', 'aggregation', 'target_value', 'target_label',
            'filters', 'definition_formula', 'number_format',
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_default_aggregation_sum(self):
        elem = ET.fromstring('<metric name="M1"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['aggregation'], 'SUM')

    def test_column_as_measure(self):
        elem = ET.fromstring('<metric name="M1" column="[Profit]"/>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['measure_field'], 'Profit')

    def test_measure_child_element(self):
        elem = ET.fromstring(
            '<metric name="M1"><measure>[Cost]</measure></metric>')
        result = _parse_metric_element(elem)
        self.assertEqual(result['measure_field'], 'Cost')


class TestExtractPulseMetrics(unittest.TestCase):
    def test_none_root(self):
        self.assertEqual(extract_pulse_metrics(None), [])

    def test_empty_workbook(self):
        root = _make_xml('<datasources/>')
        self.assertEqual(extract_pulse_metrics(root), [])

    def test_single_metric(self):
        root = _make_xml('''
            <metric name="Revenue KPI" measure="[Sales]"
                    time-dimension="[Date]" time-grain="month"
                    aggregation="SUM"/>
        ''')
        result = extract_pulse_metrics(root)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Revenue KPI')
        self.assertEqual(result[0]['time_grain'], 'Monthly')

    def test_multiple_metrics(self):
        root = _make_xml('''
            <metric name="Revenue" measure="[Sales]"/>
            <metric name="Profit" measure="[Profit]"/>
        ''')
        result = extract_pulse_metrics(root)
        self.assertEqual(len(result), 2)

    def test_deduplication(self):
        root = _make_xml('''
            <metric name="Revenue" measure="[Sales]"/>
            <metric name="Revenue" measure="[Sales]"/>
        ''')
        result = extract_pulse_metrics(root)
        self.assertEqual(len(result), 1)

    def test_pulse_metric_element(self):
        root = _make_xml(
            '<pulse-metric name="Cost Metric" measure="[Cost]"/>')
        result = extract_pulse_metrics(root)
        self.assertEqual(len(result), 1)

    def test_metrics_container(self):
        root = _make_xml('''
            <metrics>
                <metric name="M1" measure="[A]"/>
                <metric name="M2" measure="[B]"/>
            </metrics>
        ''')
        result = extract_pulse_metrics(root)
        self.assertEqual(len(result), 2)

    def test_metric_with_filters(self):
        root = _make_xml('''
            <metric name="Filtered KPI" measure="[Sales]">
                <filter column="[Region]" type="categorical">
                    <value>North</value>
                </filter>
            </metric>
        ''')
        result = extract_pulse_metrics(root)
        self.assertEqual(len(result[0]['filters']), 1)

    def test_metric_with_target(self):
        root = _make_xml('''
            <metric name="Revenue Goal" measure="[Sales]">
                <target value="500000" label="Annual Target"/>
            </metric>
        ''')
        result = extract_pulse_metrics(root)
        self.assertEqual(result[0]['target_value'], 500000.0)


if __name__ == '__main__':
    unittest.main()
