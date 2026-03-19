"""
Tests for alerts_generator module — Sprint 56.

Covers:
  - extract_alerts from parameters, calculations, reference lines
  - generate_alert_rules output format
  - save_alert_rules file I/O
  - operator mapping
  - frequency mapping
  - edge cases: empty input, no matches, numeric parsing failures
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.alerts_generator import (
    extract_alerts,
    generate_alert_rules,
    save_alert_rules,
    _extract_from_parameters,
    _extract_from_calculations,
    _extract_from_reference_lines,
    _infer_measure_from_param,
    _infer_measure_from_worksheet,
    _lookup_param_value,
    _OPERATOR_MAP,
    _FREQUENCY_MAP,
)


class TestOperatorMap(unittest.TestCase):
    """Verify operator mapping completeness."""

    def test_all_expected_operators(self):
        for key in ('above', 'below', '>', '<', '>=', '<=', '=', '==', '!='):
            self.assertIn(key, _OPERATOR_MAP)

    def test_above_maps_to_greater_than(self):
        self.assertEqual(_OPERATOR_MAP['above'], 'greaterThan')

    def test_below_maps_to_less_than(self):
        self.assertEqual(_OPERATOR_MAP['below'], 'lessThan')


class TestFrequencyMap(unittest.TestCase):
    def test_all_expected_frequencies(self):
        for key in ('once', 'always', 'daily', 'hourly'):
            self.assertIn(key, _FREQUENCY_MAP)


class TestExtractFromParameters(unittest.TestCase):
    def test_alert_keyword_parameter(self):
        data = {
            'parameters': [
                {'name': 'Sales Threshold', 'value': '100.5'},
            ],
            'calculations': [],
        }
        alerts = []
        _extract_from_parameters(data, alerts)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['threshold'], 100.5)
        self.assertIn('Threshold', alerts[0]['name'])
        self.assertEqual(alerts[0]['operator'], 'greaterThan')

    def test_min_keyword_sets_less_than(self):
        data = {
            'parameters': [
                {'name': 'Min Alert Level', 'value': '50'},
            ],
            'calculations': [],
        }
        alerts = []
        _extract_from_parameters(data, alerts)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['operator'], 'lessThan')

    def test_upper_keyword_sets_greater_than(self):
        data = {
            'parameters': [
                {'name': 'Upper Limit', 'value': '200'},
            ],
            'calculations': [],
        }
        alerts = []
        _extract_from_parameters(data, alerts)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['operator'], 'greaterThan')

    def test_non_numeric_parameter_skipped(self):
        data = {
            'parameters': [
                {'name': 'Alert Text', 'value': 'not-a-number'},
            ],
        }
        alerts = []
        _extract_from_parameters(data, alerts)
        self.assertEqual(len(alerts), 0)

    def test_no_alert_keyword_skipped(self):
        data = {
            'parameters': [
                {'name': 'Regular Param', 'value': '100'},
            ],
        }
        alerts = []
        _extract_from_parameters(data, alerts)
        self.assertEqual(len(alerts), 0)

    def test_parameter_with_current_value(self):
        data = {
            'parameters': [
                {'name': 'Warning Level', 'current_value': '75.0'},
            ],
            'calculations': [],
        }
        alerts = []
        _extract_from_parameters(data, alerts)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['threshold'], 75.0)

    def test_parameters_as_dict(self):
        data = {
            'parameters': {
                'parameters': [
                    {'name': 'Goal Target', 'value': '90'},
                ]
            },
            'calculations': [],
        }
        alerts = []
        _extract_from_parameters(data, alerts)
        self.assertEqual(len(alerts), 1)

    def test_none_value_skipped(self):
        data = {
            'parameters': [
                {'name': 'Alert Empty', 'value': None},
            ],
        }
        alerts = []
        _extract_from_parameters(data, alerts)
        self.assertEqual(len(alerts), 0)

    def test_caption_fallback(self):
        data = {
            'parameters': [
                {'caption': 'Benchmark Value', 'value': '50'},
            ],
            'calculations': [],
        }
        alerts = []
        _extract_from_parameters(data, alerts)
        self.assertEqual(len(alerts), 1)


class TestExtractFromCalculations(unittest.TestCase):
    def test_if_threshold_pattern(self):
        data = {
            'calculations': [
                {
                    'caption': 'Alert Flag',
                    'formula': 'IF [Sales] > 100 THEN "Alert" END',
                },
            ],
        }
        alerts = []
        _extract_from_calculations(data, alerts)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['measure'], 'Sales')
        self.assertEqual(alerts[0]['threshold'], 100.0)

    def test_parameter_reference_lookup(self):
        data = {
            'calculations': [
                {
                    'caption': 'Threshold Check',
                    'formula': 'IF [Revenue] > [Parameters].[My Threshold] THEN 1 END',
                },
            ],
            'parameters': [
                {'name': 'My Threshold', 'value': '250'},
            ],
        }
        alerts = []
        _extract_from_calculations(data, alerts)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['threshold'], 250.0)

    def test_no_alert_keyword_no_param_ref_skipped(self):
        data = {
            'calculations': [
                {
                    'caption': 'Regular Calc',
                    'formula': 'SUM([Sales])',
                },
            ],
        }
        alerts = []
        _extract_from_calculations(data, alerts)
        self.assertEqual(len(alerts), 0)

    def test_calculations_as_dict(self):
        data = {
            'calculations': {
                'calculations': [
                    {
                        'caption': 'Alert Test',
                        'formula': 'IF [Profit] > 500 THEN 1 END',
                    },
                ]
            },
        }
        alerts = []
        _extract_from_calculations(data, alerts)
        self.assertEqual(len(alerts), 1)

    def test_empty_formula_skipped(self):
        data = {
            'calculations': [
                {'caption': 'Alert Empty', 'formula': ''},
            ],
        }
        alerts = []
        _extract_from_calculations(data, alerts)
        self.assertEqual(len(alerts), 0)


class TestExtractFromReferenceLines(unittest.TestCase):
    def test_reference_line_with_target_label(self):
        data = {
            'worksheets': [
                {
                    'name': 'Sales Sheet',
                    'reference_lines': [
                        {'value': '1000', 'label': 'Target Sales'},
                    ],
                    'fields': [{'name': 'Revenue', 'role': 'measure'}],
                },
            ],
        }
        alerts = []
        _extract_from_reference_lines(data, alerts)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['threshold'], 1000.0)
        self.assertEqual(alerts[0]['measure'], 'Revenue')

    def test_non_threshold_label_skipped(self):
        data = {
            'worksheets': [
                {
                    'name': 'Sheet1',
                    'reference_lines': [
                        {'value': '50', 'label': 'Average'},
                    ],
                    'fields': [],
                },
            ],
        }
        alerts = []
        _extract_from_reference_lines(data, alerts)
        self.assertEqual(len(alerts), 0)

    def test_non_numeric_value_skipped(self):
        data = {
            'worksheets': [
                {
                    'name': 'Sheet1',
                    'reference_lines': [
                        {'value': 'abc', 'label': 'Target'},
                    ],
                    'fields': [],
                },
            ],
        }
        alerts = []
        _extract_from_reference_lines(data, alerts)
        self.assertEqual(len(alerts), 0)

    def test_worksheets_as_dict(self):
        data = {
            'worksheets': {
                'worksheets': [
                    {
                        'name': 'WS1',
                        'reference_lines': [
                            {'value': '200', 'label': 'Goal Line'},
                        ],
                        'fields': [],
                    },
                ]
            },
        }
        alerts = []
        _extract_from_reference_lines(data, alerts)
        self.assertEqual(len(alerts), 1)


class TestExtractAlerts(unittest.TestCase):
    def test_empty_data(self):
        self.assertEqual(extract_alerts({}), [])

    def test_combined_sources(self):
        data = {
            'parameters': [
                {'name': 'Alert Threshold', 'value': '100'},
            ],
            'calculations': [
                {
                    'caption': 'Violation Flag',
                    'formula': 'IF [Sales] > 500 THEN 1 END',
                },
            ],
            'worksheets': [
                {
                    'name': 'Sheet1',
                    'reference_lines': [
                        {'value': '300', 'label': 'Target reference'},
                    ],
                    'fields': [],
                },
            ],
        }
        alerts = extract_alerts(data)
        self.assertGreaterEqual(len(alerts), 2)  # at least param + ref line

    def test_source_field_populated(self):
        data = {
            'parameters': [
                {'name': 'Critical Threshold', 'value': '99'},
            ],
            'calculations': [],
        }
        alerts = extract_alerts(data)
        self.assertTrue(any('parameter:' in a['source'] for a in alerts))


class TestGenerateAlertRules(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(generate_alert_rules([]), [])

    def test_rule_structure(self):
        alerts = [
            {
                'name': 'Test Alert',
                'measure': 'Revenue',
                'operator': 'greaterThan',
                'threshold': 100,
                'frequency': 'atMostOncePerDay',
                'source': 'parameter:test',
            }
        ]
        rules = generate_alert_rules(alerts)
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(rule['name'], 'Test Alert')
        self.assertEqual(rule['condition']['operator'], 'greaterThan')
        self.assertEqual(rule['condition']['threshold'], 100)
        self.assertEqual(rule['measure'], 'Revenue')
        self.assertTrue(rule['isEnabled'])
        self.assertIn('migrationNote', rule)

    def test_multiple_alerts(self):
        alerts = [
            {'name': f'Alert {i}', 'measure': 'M', 'operator': 'greaterThan',
             'threshold': i * 10, 'frequency': 'once', 'source': 'test'}
            for i in range(5)
        ]
        rules = generate_alert_rules(alerts)
        self.assertEqual(len(rules), 5)

    def test_default_values(self):
        alerts = [{'name': 'Minimal', 'measure': 'X'}]
        rules = generate_alert_rules(alerts)
        self.assertEqual(rules[0]['condition']['operator'], 'greaterThan')
        self.assertEqual(rules[0]['condition']['threshold'], 0)
        self.assertEqual(rules[0]['frequency'], 'atMostOncePerDay')


class TestSaveAlertRules(unittest.TestCase):
    def test_save_and_load(self):
        rules = [
            {
                'name': 'Test',
                'condition': {'operator': 'greaterThan', 'threshold': 50},
                'measure': 'Sales',
                'frequency': 'once',
                'isEnabled': True,
                'migrationSource': 'test',
                'migrationNote': 'note',
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_alert_rules(rules, tmpdir)
            self.assertTrue(os.path.exists(path))
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(len(data['alertRules']), 1)
            self.assertIn('migrationNote', data)

    def test_empty_rules_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_alert_rules([], tmpdir)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(len(data['alertRules']), 0)


class TestHelpers(unittest.TestCase):
    def test_infer_measure_from_param(self):
        data = {
            'calculations': [
                {'caption': 'Revenue Check', 'formula': 'IF [Sales] > [Parameters].[Threshold] THEN 1'},
            ],
        }
        result = _infer_measure_from_param('Threshold', data)
        self.assertEqual(result, 'Revenue Check')

    def test_infer_measure_from_param_not_found(self):
        result = _infer_measure_from_param('Missing', {'calculations': []})
        self.assertEqual(result, 'Unknown')

    def test_infer_measure_from_worksheet_with_role(self):
        ws = {'fields': [{'name': 'Profit', 'role': 'measure'}]}
        self.assertEqual(_infer_measure_from_worksheet(ws), 'Profit')

    def test_infer_measure_from_worksheet_bracket_notation(self):
        ws = {'fields': ['[Revenue]']}
        self.assertEqual(_infer_measure_from_worksheet(ws), 'Revenue')

    def test_infer_measure_from_worksheet_empty(self):
        self.assertIsNone(_infer_measure_from_worksheet({'fields': []}))

    def test_lookup_param_value_found(self):
        data = {'parameters': [{'name': 'Threshold', 'value': '42.5'}]}
        self.assertEqual(_lookup_param_value('Threshold', data), 42.5)

    def test_lookup_param_value_not_found(self):
        data = {'parameters': [{'name': 'Other', 'value': '10'}]}
        self.assertIsNone(_lookup_param_value('Missing', data))

    def test_lookup_param_value_non_numeric(self):
        data = {'parameters': [{'name': 'Alert Param', 'value': 'text'}]}
        self.assertIsNone(_lookup_param_value('Alert Param', data))


if __name__ == '__main__':
    unittest.main()
