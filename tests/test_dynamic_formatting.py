"""Tests for Sprint 124 — Dynamic Formatting, Endorsement, DAX Queries.

Tests:
- Dynamic FORMAT() DAX wrapper generation (K/M/B abbreviation)
- Endorsement classification (certified/promoted/none)
- Sensitivity label inference from column names
- DAX query view generation (SUMMARIZECOLUMNS per measure)
- DAX query export to .dax files
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))


class TestDynamicFormatMeasures(unittest.TestCase):
    """Test _inject_dynamic_format_measures."""

    def test_currency_measure_gets_formatted_variant(self):
        from tmdl_generator import _inject_dynamic_format_measures
        model = {
            'model': {
                'tables': [{
                    'name': 'Sales',
                    'columns': [],
                    'measures': [
                        {'name': 'Revenue', 'expression': 'SUM([Amount])',
                         'formatString': '$#,0.00'},
                    ],
                }]
            }
        }
        _inject_dynamic_format_measures(model)
        measures = model['model']['tables'][0]['measures']
        fmt_measures = [m for m in measures if 'Formatted' in m['name']]
        self.assertEqual(len(fmt_measures), 1)
        self.assertEqual(fmt_measures[0]['name'], 'Revenue Formatted')
        self.assertIn('FORMAT', fmt_measures[0]['expression'])
        self.assertIn('1E9', fmt_measures[0]['expression'])
        self.assertIn('1E6', fmt_measures[0]['expression'])
        self.assertIn('"B"', fmt_measures[0]['expression'])
        self.assertIn('"M"', fmt_measures[0]['expression'])
        self.assertIn('"K"', fmt_measures[0]['expression'])

    def test_euro_currency_gets_formatted(self):
        from tmdl_generator import _inject_dynamic_format_measures
        model = {
            'model': {'tables': [{'name': 'T', 'columns': [], 'measures': [
                {'name': 'Rev', 'expression': 'SUM([X])', 'formatString': '€#,0.00'}
            ]}]}
        }
        _inject_dynamic_format_measures(model)
        measures = model['model']['tables'][0]['measures']
        self.assertEqual(len(measures), 2)
        self.assertIn('€', measures[1]['description'])

    def test_non_currency_not_formatted(self):
        from tmdl_generator import _inject_dynamic_format_measures
        model = {
            'model': {'tables': [{'name': 'T', 'columns': [], 'measures': [
                {'name': 'Count', 'expression': 'COUNT([ID])', 'formatString': '0'}
            ]}]}
        }
        _inject_dynamic_format_measures(model)
        measures = model['model']['tables'][0]['measures']
        self.assertEqual(len(measures), 1)  # No Formatted variant added

    def test_skip_format_wrapper_on_existing_format(self):
        from tmdl_generator import _inject_dynamic_format_measures
        model = {
            'model': {'tables': [{'name': 'T', 'columns': [], 'measures': [
                {'name': 'X', 'expression': 'FORMAT([Y], "$#,0")',
                 'formatString': '$#,0.00'}
            ]}]}
        }
        _inject_dynamic_format_measures(model)
        measures = model['model']['tables'][0]['measures']
        self.assertEqual(len(measures), 1)  # No double-wrapping

    def test_skip_time_intelligence_measures(self):
        from tmdl_generator import _inject_dynamic_format_measures
        model = {
            'model': {'tables': [{'name': 'T', 'columns': [], 'measures': [
                {'name': 'Year To Date', 'expression': 'TOTALYTD([X], [Date])',
                 'formatString': '$#,0.00'}
            ]}]}
        }
        _inject_dynamic_format_measures(model)
        self.assertEqual(len(model['model']['tables'][0]['measures']), 1)

    def test_no_duplicate_formatted_measures(self):
        from tmdl_generator import _inject_dynamic_format_measures
        model = {
            'model': {'tables': [{'name': 'T', 'columns': [], 'measures': [
                {'name': 'Rev', 'expression': 'SUM([X])', 'formatString': '$#,0.00'}
            ]}]}
        }
        _inject_dynamic_format_measures(model)
        _inject_dynamic_format_measures(model)
        fmt = [m for m in model['model']['tables'][0]['measures'] if 'Formatted' in m['name']]
        self.assertEqual(len(fmt), 1)


class TestEndorsementClassification(unittest.TestCase):
    """Test classify_endorsement function."""

    def test_certified_full_fidelity(self):
        from governance import classify_endorsement
        result = classify_endorsement(100, 0, 0)
        self.assertEqual(result['endorsement'], 'certified')
        self.assertEqual(result['confidence'], 100)

    def test_promoted_high_fidelity(self):
        from governance import classify_endorsement
        result = classify_endorsement(95, 3, 0)
        self.assertEqual(result['endorsement'], 'promoted')
        self.assertEqual(result['confidence'], 95)

    def test_none_low_fidelity(self):
        from governance import classify_endorsement
        result = classify_endorsement(70, 10, 0)
        self.assertEqual(result['endorsement'], 'none')
        self.assertIn('manual review', result['reason'])

    def test_none_with_validation_errors(self):
        from governance import classify_endorsement
        result = classify_endorsement(100, 0, 1)
        self.assertEqual(result['endorsement'], 'none')
        self.assertIn('validation error', result['reason'])

    def test_promoted_boundary_90_fidelity(self):
        from governance import classify_endorsement
        result = classify_endorsement(90, 5, 0)
        self.assertEqual(result['endorsement'], 'promoted')

    def test_none_boundary_89_fidelity(self):
        from governance import classify_endorsement
        result = classify_endorsement(89, 0, 0)
        self.assertEqual(result['endorsement'], 'none')

    def test_none_too_many_approximations(self):
        from governance import classify_endorsement
        result = classify_endorsement(95, 6, 0)
        self.assertEqual(result['endorsement'], 'none')


class TestSensitivityLabelInference(unittest.TestCase):
    """Test infer_sensitivity_labels function."""

    def test_email_column(self):
        from governance import infer_sensitivity_labels
        tables = [{'name': 'Customer', 'columns': [
            {'name': 'CustomerEmail', 'dataType': 'String'},
        ]}]
        result = infer_sensitivity_labels(tables)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['label'], 'Confidential')
        self.assertEqual(result[0]['pattern'], 'email')

    def test_ssn_highly_confidential(self):
        from governance import infer_sensitivity_labels
        tables = [{'name': 'Employee', 'columns': [
            {'name': 'SSN', 'dataType': 'String'},
        ]}]
        result = infer_sensitivity_labels(tables)
        self.assertEqual(result[0]['label'], 'Highly Confidential')

    def test_revenue_internal(self):
        from governance import infer_sensitivity_labels
        tables = [{'name': 'Finance', 'columns': [
            {'name': 'Revenue', 'dataType': 'Double'},
        ]}]
        result = infer_sensitivity_labels(tables)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['label'], 'Internal')

    def test_salary_internal(self):
        from governance import infer_sensitivity_labels
        tables = [{'name': 'HR', 'columns': [
            {'name': 'Salary', 'dataType': 'Double'},
        ]}]
        result = infer_sensitivity_labels(tables)
        self.assertEqual(result[0]['label'], 'Internal')

    def test_no_sensitive_columns(self):
        from governance import infer_sensitivity_labels
        tables = [{'name': 'Products', 'columns': [
            {'name': 'ProductID', 'dataType': 'Int64'},
            {'name': 'Category', 'dataType': 'String'},
        ]}]
        result = infer_sensitivity_labels(tables)
        self.assertEqual(len(result), 0)

    def test_multiple_sensitive_columns(self):
        from governance import infer_sensitivity_labels
        tables = [{'name': 'Users', 'columns': [
            {'name': 'Email', 'dataType': 'String'},
            {'name': 'Phone', 'dataType': 'String'},
            {'name': 'SSN', 'dataType': 'String'},
            {'name': 'UserID', 'dataType': 'Int64'},
        ]}]
        result = infer_sensitivity_labels(tables)
        self.assertEqual(len(result), 3)
        labels = {r['label'] for r in result}
        self.assertIn('Confidential', labels)
        self.assertIn('Highly Confidential', labels)

    def test_credit_card_highly_confidential(self):
        from governance import infer_sensitivity_labels
        tables = [{'name': 'Pay', 'columns': [
            {'name': 'CreditCardNumber', 'dataType': 'String'},
        ]}]
        result = infer_sensitivity_labels(tables)
        self.assertEqual(result[0]['label'], 'Highly Confidential')


class TestEndorsementReport(unittest.TestCase):
    """Test generate_endorsement_report function."""

    def test_full_report_certified(self):
        from governance import generate_endorsement_report
        report = generate_endorsement_report(
            {'fidelity_score': 100, 'approximation_count': 0, 'validation_errors': 0},
            [{'name': 'Sales', 'columns': [{'name': 'Revenue', 'dataType': 'Double'}]}],
        )
        self.assertEqual(report['endorsement']['endorsement'], 'certified')
        self.assertEqual(len(report['sensitivity_labels']), 1)
        self.assertEqual(report['overall_sensitivity'], 'Internal')

    def test_report_no_tables(self):
        from governance import generate_endorsement_report
        report = generate_endorsement_report(
            {'fidelity_score': 95, 'approximation_count': 2},
        )
        self.assertEqual(report['endorsement']['endorsement'], 'promoted')
        self.assertEqual(len(report['sensitivity_labels']), 0)


class TestDAXQueryGeneration(unittest.TestCase):
    """Test DAX query view generator."""

    def test_basic_query_generation(self):
        from dax_query_generator import generate_dax_queries
        tables = [{
            'name': 'Sales',
            'columns': [
                {'name': 'Region', 'dataType': 'String'},
                {'name': 'Amount', 'dataType': 'Double'},
            ],
            'measures': [
                {'name': 'Total Sales', 'expression': 'SUM([Amount])'},
            ],
        }]
        queries = generate_dax_queries(tables)
        self.assertEqual(len(queries), 1)
        self.assertIn('SUMMARIZECOLUMNS', queries[0]['dax'])
        self.assertIn('Total Sales', queries[0]['dax'])
        self.assertIn('Region', queries[0]['dax'])

    def test_no_dimension_uses_row(self):
        from dax_query_generator import generate_dax_queries
        tables = [{
            'name': 'Summary',
            'columns': [],
            'measures': [{'name': 'Grand Total', 'expression': 'SUM([X])'}],
        }]
        queries = generate_dax_queries(tables)
        self.assertEqual(len(queries), 1)
        self.assertIn('ROW', queries[0]['dax'])

    def test_skips_calendar_table(self):
        from dax_query_generator import generate_dax_queries
        tables = [
            {'name': 'Calendar', 'columns': [], 'measures': [
                {'name': 'YTD', 'expression': 'TOTALYTD(...)'}
            ]},
            {'name': 'Sales', 'columns': [{'name': 'Category', 'dataType': 'String'}],
             'measures': [{'name': 'Total', 'expression': 'SUM([X])'}]},
        ]
        queries = generate_dax_queries(tables)
        tables_in_queries = {q['table'] for q in queries}
        self.assertNotIn('Calendar', tables_in_queries)

    def test_skips_time_intelligence_folder(self):
        from dax_query_generator import generate_dax_queries
        tables = [{
            'name': 'Sales',
            'columns': [{'name': 'Cat', 'dataType': 'String'}],
            'measures': [
                {'name': 'Rev', 'expression': 'SUM([X])'},
                {'name': 'YTD', 'expression': 'TOTALYTD(...)',
                 'displayFolder': 'Time Intelligence'},
            ],
        }]
        queries = generate_dax_queries(tables)
        meas_names = {q['measure'] for q in queries}
        self.assertIn('Rev', meas_names)
        self.assertNotIn('YTD', meas_names)

    def test_prefers_string_dimension(self):
        from dax_query_generator import generate_dax_queries
        tables = [{
            'name': 'T',
            'columns': [
                {'name': 'ID', 'dataType': 'Int64', 'isKey': True},
                {'name': 'Date', 'dataType': 'DateTime'},
                {'name': 'Category', 'dataType': 'String'},
            ],
            'measures': [{'name': 'M', 'expression': 'SUM([X])'}],
        }]
        queries = generate_dax_queries(tables)
        self.assertIn('Category', queries[0]['dax'])

    def test_skips_hidden_columns(self):
        from dax_query_generator import generate_dax_queries
        tables = [{
            'name': 'T',
            'columns': [
                {'name': 'HiddenCol', 'dataType': 'String', 'isHidden': True},
                {'name': 'VisibleDate', 'dataType': 'DateTime'},
            ],
            'measures': [{'name': 'M', 'expression': 'SUM([X])'}],
        }]
        queries = generate_dax_queries(tables)
        self.assertIn('VisibleDate', queries[0]['dax'])
        self.assertNotIn('HiddenCol', queries[0]['dax'])

    def test_multiple_measures(self):
        from dax_query_generator import generate_dax_queries
        tables = [{
            'name': 'T',
            'columns': [{'name': 'Cat', 'dataType': 'String'}],
            'measures': [
                {'name': 'M1', 'expression': 'SUM([A])'},
                {'name': 'M2', 'expression': 'COUNT([B])'},
                {'name': 'M3', 'expression': 'AVERAGE([C])'},
            ],
        }]
        queries = generate_dax_queries(tables)
        self.assertEqual(len(queries), 3)


class TestDAXQueryExport(unittest.TestCase):
    """Test DAX query export to .dax files."""

    def test_export_creates_files(self):
        from dax_query_generator import generate_dax_queries, export_dax_queries
        tables = [{
            'name': 'Sales',
            'columns': [{'name': 'Region', 'dataType': 'String'}],
            'measures': [{'name': 'Total', 'expression': 'SUM([X])'}],
        }]
        queries = generate_dax_queries(tables)
        with tempfile.TemporaryDirectory() as tmpdir:
            count = export_dax_queries(queries, tmpdir)
            self.assertEqual(count, 1)
            files = os.listdir(tmpdir)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].endswith('.dax'))
            content = open(os.path.join(tmpdir, files[0]), encoding='utf-8').read()
            self.assertIn('SUMMARIZECOLUMNS', content)
            self.assertIn('// Validation Query', content)

    def test_export_empty_queries(self):
        from dax_query_generator import export_dax_queries
        with tempfile.TemporaryDirectory() as tmpdir:
            count = export_dax_queries([], tmpdir)
            self.assertEqual(count, 0)


class TestDAXQuerySummary(unittest.TestCase):
    """Test DAX query summary generation."""

    def test_summary(self):
        from dax_query_generator import generate_dax_queries, generate_query_summary
        tables = [
            {'name': 'Sales', 'columns': [{'name': 'Cat', 'dataType': 'String'}],
             'measures': [{'name': 'M1', 'expression': 'SUM([A])'},
                          {'name': 'M2', 'expression': 'SUM([B])'}]},
            {'name': 'Products', 'columns': [{'name': 'Name', 'dataType': 'String'}],
             'measures': [{'name': 'M3', 'expression': 'COUNT([X])'}]},
        ]
        queries = generate_dax_queries(tables)
        summary = generate_query_summary(queries)
        self.assertEqual(summary['total_queries'], 3)
        self.assertEqual(summary['tables']['Sales'], 2)
        self.assertEqual(summary['tables']['Products'], 1)


if __name__ == '__main__':
    unittest.main()
