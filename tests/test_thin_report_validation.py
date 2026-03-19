"""
Tests for Sprint 57 — Thin Report Binding Validation & Cross-Report Integrity.

Covers:
  - validate_field_references (resolved, unresolved table, unresolved field, suggestion)
  - validate_drillthrough_targets (found, missing, cross-report)
  - validate_filter_references (resolved, unresolved)
  - validate_parameter_references (resolved, unresolved)
  - validate_cross_report_navigation (found, missing)
  - generate_thin_report_validation (summary)
  - _collect_model_fields helper
  - _find_closest_match helper
  - Edge cases: empty inputs, namespaced measures
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.thin_report_generator import (
    validate_field_references,
    validate_drillthrough_targets,
    validate_filter_references,
    validate_parameter_references,
    validate_cross_report_navigation,
    generate_thin_report_validation,
    _collect_model_fields,
    _find_closest_match,
)


def _make_model(tables=None):
    """Helper to build a minimal merged model."""
    return {'tables': tables or []}


def _make_table(name, columns=None, measures=None, is_param=False):
    return {
        'name': name,
        'columns': [{'name': c} for c in (columns or [])],
        'measures': [{'name': m} for m in (measures or [])],
        'is_parameter': is_param,
    }


class TestCollectModelFields(unittest.TestCase):
    def test_basic(self):
        model = _make_model([
            _make_table('Sales', ['Region', 'Date'], ['Revenue']),
        ])
        info = _collect_model_fields(model)
        self.assertIn('Sales', info['tables'])
        self.assertIn('Region', info['columns']['Sales'])
        self.assertIn('Revenue', info['measures']['Sales'])

    def test_parameter_table(self):
        model = _make_model([
            _make_table('DateParameter', is_param=True),
        ])
        info = _collect_model_fields(model)
        self.assertIn('DateParameter', info['parameters'])

    def test_empty_model(self):
        info = _collect_model_fields({'tables': []})
        self.assertEqual(info['tables'], set())

    def test_multiple_tables(self):
        model = _make_model([
            _make_table('T1', ['A'], ['M1']),
            _make_table('T2', ['B'], ['M2']),
        ])
        info = _collect_model_fields(model)
        self.assertEqual(len(info['tables']), 2)


class TestFindClosestMatch(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(_find_closest_match('Sales', {'Sales', 'Cost'}), 'Sales')

    def test_case_insensitive(self):
        self.assertEqual(_find_closest_match('sales', {'Sales', 'Cost'}), 'Sales')

    def test_substring_match(self):
        result = _find_closest_match('Revenu', {'Revenue', 'Cost'})
        self.assertEqual(result, 'Revenue')

    def test_no_match(self):
        result = _find_closest_match('XYZ', {'ABC', 'DEF'})
        self.assertEqual(result, '')

    def test_empty_candidates(self):
        self.assertEqual(_find_closest_match('test', set()), '')


class TestValidateFieldReferences(unittest.TestCase):
    def test_resolved_field(self):
        model = _make_model([_make_table('Sales', ['Region'], ['Revenue'])])
        visuals = [{'visual_id': 'v1', 'page': 'p1',
                    'fields': [{'table': 'Sales', 'column': 'Revenue'}]}]
        results = validate_field_references(visuals, model)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'resolved')

    def test_unresolved_table(self):
        model = _make_model([_make_table('Sales', ['Region'])])
        visuals = [{'visual_id': 'v1', 'page': 'p1',
                    'fields': [{'table': 'Sale', 'column': 'Col'}]}]
        results = validate_field_references(visuals, model)
        self.assertEqual(results[0]['status'], 'unresolved_table')
        self.assertEqual(results[0]['suggestion'], 'Sales')

    def test_unresolved_field(self):
        model = _make_model([_make_table('Sales', ['Region'], ['Revenue'])])
        visuals = [{'visual_id': 'v1', 'page': 'p1',
                    'fields': [{'table': 'Sales', 'column': 'Missing'}]}]
        results = validate_field_references(visuals, model)
        self.assertEqual(results[0]['status'], 'unresolved_field')

    def test_string_field_ref(self):
        model = _make_model([_make_table('Sales', ['Region'])])
        visuals = [{'visual_id': 'v1', 'fields': ["Sales[Region]"]}]
        results = validate_field_references(visuals, model)
        self.assertEqual(results[0]['status'], 'resolved')

    def test_bare_field_name(self):
        model = _make_model([_make_table('Sales', ['Revenue'])])
        visuals = [{'visual_id': 'v1', 'fields': ['Revenue']}]
        results = validate_field_references(visuals, model)
        self.assertEqual(results[0]['status'], 'resolved')

    def test_bare_field_not_found(self):
        model = _make_model([_make_table('Sales', ['Revenue'])])
        visuals = [{'visual_id': 'v1', 'fields': ['Missing']}]
        results = validate_field_references(visuals, model)
        self.assertEqual(results[0]['status'], 'unresolved_field')

    def test_multiple_visuals(self):
        model = _make_model([_make_table('T', ['A', 'B'])])
        visuals = [
            {'visual_id': 'v1', 'fields': [{'table': 'T', 'column': 'A'}]},
            {'visual_id': 'v2', 'fields': [{'table': 'T', 'column': 'C'}]},
        ]
        results = validate_field_references(visuals, model)
        self.assertEqual(results[0]['status'], 'resolved')
        self.assertEqual(results[1]['status'], 'unresolved_field')

    def test_empty_visuals(self):
        model = _make_model([_make_table('T', ['A'])])
        results = validate_field_references([], model)
        self.assertEqual(len(results), 0)

    def test_namespaced_measure(self):
        model = _make_model([
            _make_table('Sales', measures=['Revenue (wb1)', 'Revenue (wb2)']),
        ])
        visuals = [{'visual_id': 'v1',
                    'fields': [{'table': 'Sales', 'column': 'Revenue (wb1)'}]}]
        results = validate_field_references(visuals, model)
        self.assertEqual(results[0]['status'], 'resolved')

    def test_suggestion_for_unresolved(self):
        model = _make_model([_make_table('Sales', ['Revenue'])])
        visuals = [{'visual_id': 'v1',
                    'fields': [{'table': 'Sales', 'column': 'Revenues'}]}]
        results = validate_field_references(visuals, model)
        self.assertEqual(results[0]['status'], 'unresolved_field')
        self.assertEqual(results[0]['suggestion'], 'Revenue')


class TestValidateDrillthroughTargets(unittest.TestCase):
    def test_found_target(self):
        pages = [
            {'name': 'Overview', 'drillthrough_target': 'Detail'},
            {'name': 'Detail'},
        ]
        results = validate_drillthrough_targets(pages)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'found')

    def test_missing_target(self):
        pages = [
            {'name': 'Overview', 'drillthrough_target': 'NonExistent'},
        ]
        results = validate_drillthrough_targets(pages)
        self.assertEqual(results[0]['status'], 'missing')

    def test_no_drillthrough(self):
        pages = [{'name': 'Page1'}]
        results = validate_drillthrough_targets(pages)
        self.assertEqual(len(results), 0)

    def test_cross_report_bundle(self):
        pages = [
            {'name': 'Overview', 'drillthrough_target': 'Other Detail'},
        ]
        bundle = [[{'name': 'Other Detail'}]]
        results = validate_drillthrough_targets(pages, bundle_reports=bundle)
        self.assertEqual(results[0]['status'], 'found')


class TestValidateFilterReferences(unittest.TestCase):
    def test_resolved(self):
        model = _make_model([_make_table('Sales', ['Region'])])
        filters = [{'table': 'Sales', 'column': 'Region'}]
        results = validate_filter_references(filters, model)
        self.assertEqual(results[0]['status'], 'resolved')

    def test_unresolved_table(self):
        model = _make_model([_make_table('Sales', ['Region'])])
        filters = [{'table': 'Missing', 'column': 'Region'}]
        results = validate_filter_references(filters, model)
        self.assertEqual(results[0]['status'], 'unresolved_table')

    def test_unresolved_column(self):
        model = _make_model([_make_table('Sales', ['Region'])])
        filters = [{'table': 'Sales', 'column': 'Missing'}]
        results = validate_filter_references(filters, model)
        self.assertEqual(results[0]['status'], 'unresolved_field')

    def test_field_key_fallback(self):
        model = _make_model([_make_table('Sales', ['Region'])])
        filters = [{'table': 'Sales', 'field': 'Region'}]
        results = validate_filter_references(filters, model)
        self.assertEqual(results[0]['status'], 'resolved')

    def test_no_table_searches_all(self):
        model = _make_model([_make_table('Sales', ['Region'])])
        filters = [{'column': 'Region'}]
        results = validate_filter_references(filters, model)
        self.assertEqual(results[0]['status'], 'resolved')

    def test_empty_filters(self):
        results = validate_filter_references([], _make_model())
        self.assertEqual(len(results), 0)


class TestValidateParameterReferences(unittest.TestCase):
    def test_resolved(self):
        model = _make_model([_make_table('DateParameter', is_param=True)])
        results = validate_parameter_references(['DateParameter'], model)
        self.assertEqual(results[0]['status'], 'resolved')

    def test_unresolved(self):
        model = _make_model([_make_table('Sales')])
        results = validate_parameter_references(['MissingParam'], model)
        self.assertEqual(results[0]['status'], 'unresolved')

    def test_empty(self):
        results = validate_parameter_references([], _make_model())
        self.assertEqual(len(results), 0)


class TestValidateCrossReportNavigation(unittest.TestCase):
    def test_found(self):
        actions = [{'type': 'navigate', 'target_report': 'Sales', 'name': 'Go Sales'}]
        results = validate_cross_report_navigation(actions, ['Sales', 'Cost'])
        self.assertEqual(results[0]['status'], 'found')

    def test_missing(self):
        actions = [{'type': 'navigate', 'target_report': 'Missing', 'name': 'Go'}]
        results = validate_cross_report_navigation(actions, ['Sales'])
        self.assertEqual(results[0]['status'], 'missing')

    def test_non_navigate_action_skipped(self):
        actions = [{'type': 'filter', 'target_report': 'X'}]
        results = validate_cross_report_navigation(actions, ['X'])
        self.assertEqual(len(results), 0)

    def test_empty_target(self):
        actions = [{'type': 'navigate', 'target_report': ''}]
        results = validate_cross_report_navigation(actions, ['Sales'])
        self.assertEqual(len(results), 0)


class TestGenerateThinReportValidation(unittest.TestCase):
    def test_full_summary(self):
        model = _make_model([
            _make_table('Sales', ['Region', 'Date'], ['Revenue']),
        ])
        report_data = {
            'visuals': [
                {'visual_id': 'v1', 'page': 'p1',
                 'fields': [{'table': 'Sales', 'column': 'Revenue'},
                            {'table': 'Sales', 'column': 'Missing'}]},
            ],
            'pages': [
                {'name': 'Overview', 'drillthrough_target': 'Detail'},
                {'name': 'Detail'},
            ],
            'filters': [{'table': 'Sales', 'column': 'Region'}],
            'slicer_params': ['Sales'],
            'actions': [{'type': 'navigate', 'target_report': 'Other', 'name': 'a'}],
        }
        result = generate_thin_report_validation(
            report_data, model, bundle_report_names=['Other'])
        self.assertEqual(result['total_fields_checked'], 2)
        self.assertEqual(result['resolved_fields'], 1)
        self.assertEqual(result['unresolved_fields'], 1)
        self.assertEqual(result['drillthrough_gaps'], 0)
        self.assertEqual(result['filter_gaps'], 0)
        self.assertEqual(result['navigation_gaps'], 0)

    def test_empty_report(self):
        model = _make_model()
        result = generate_thin_report_validation({}, model)
        self.assertEqual(result['total_fields_checked'], 0)
        self.assertEqual(result['drillthrough_gaps'], 0)
        self.assertEqual(result['filter_gaps'], 0)

    def test_all_unresolved(self):
        model = _make_model([_make_table('T1', ['A'])])
        report_data = {
            'visuals': [
                {'visual_id': 'v1',
                 'fields': [{'table': 'Missing', 'column': 'X'}]},
            ],
            'pages': [{'name': 'P', 'drillthrough_target': 'Gone'}],
            'filters': [{'table': 'Bad', 'column': 'Y'}],
            'slicer_params': ['NoParam'],
            'actions': [{'type': 'navigate', 'target_report': 'None', 'name': 'b'}],
        }
        result = generate_thin_report_validation(report_data, model)
        self.assertEqual(result['unresolved_fields'], 1)
        self.assertEqual(result['drillthrough_gaps'], 1)
        self.assertEqual(result['filter_gaps'], 1)
        self.assertEqual(result['navigation_gaps'], 1)


if __name__ == '__main__':
    unittest.main()
