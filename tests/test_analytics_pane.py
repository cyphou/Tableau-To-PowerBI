"""Tests for Sprint 123 — Analytics Pane & Trend Lines.

Tests:
- Trend line regressionType mapping (5 types + polynomial order)
- Distribution band percentile/stddev generation
- Forecast seasonality + model mapping
- Clustering MigrationNote on visual subtitle
- R² DAX measure generation
- Confidence interval conversion
"""

import json
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))


class TestTrendLineRegressionType(unittest.TestCase):
    """Test trend line generation in _build_analytics_objects."""

    def _build(self, ws_data, visual_type='lineChart'):
        from pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._main_table = 'Sales'
        objects = {}
        formatting = {}
        gen._build_analytics_objects(objects, ws_data, visual_type, formatting)
        return objects

    def test_linear_trend_line(self):
        ws = {'trend_lines': [{'type': 'linear', 'color': '#FF0000'}]}
        obj = self._build(ws)
        self.assertIn('trend', obj)
        props = obj['trend'][0]['properties']
        self.assertIn('regressionType', props)
        self.assertIn('Linear', str(props['regressionType']))

    def test_exponential_trend_line(self):
        ws = {'trend_lines': [{'type': 'exponential', 'color': '#00FF00'}]}
        obj = self._build(ws)
        props = obj['trend'][0]['properties']
        self.assertIn('Exponential', str(props['regressionType']))

    def test_logarithmic_trend_line(self):
        ws = {'trend_lines': [{'type': 'logarithmic'}]}
        obj = self._build(ws)
        props = obj['trend'][0]['properties']
        self.assertIn('Logarithmic', str(props['regressionType']))

    def test_polynomial_trend_line_with_order(self):
        ws = {'trend_lines': [{'type': 'polynomial', 'order': 3}]}
        obj = self._build(ws)
        props = obj['trend'][0]['properties']
        self.assertIn('Polynomial', str(props['regressionType']))
        self.assertIn('polynomialOrder', props)
        self.assertIn('3', str(props['polynomialOrder']))

    def test_power_trend_line(self):
        ws = {'trend_lines': [{'type': 'power'}]}
        obj = self._build(ws)
        props = obj['trend'][0]['properties']
        self.assertIn('Power', str(props['regressionType']))

    def test_display_equation(self):
        ws = {'trend_lines': [{'type': 'linear', 'show_equation': True}]}
        obj = self._build(ws)
        props = obj['trend'][0]['properties']
        self.assertIn('displayEquation', props)

    def test_display_r_squared(self):
        ws = {'trend_lines': [{'type': 'linear', 'show_r_squared': True}]}
        obj = self._build(ws)
        props = obj['trend'][0]['properties']
        self.assertIn('displayRSquared', props)

    def test_confidence_band_on_trend(self):
        ws = {'trend_lines': [{'type': 'linear', 'show_confidence': True}]}
        obj = self._build(ws)
        props = obj['trend'][0]['properties']
        self.assertIn('confidenceBand', props)

    def test_unknown_type_defaults_linear(self):
        ws = {'trend_lines': [{'type': 'unknown_type'}]}
        obj = self._build(ws)
        props = obj['trend'][0]['properties']
        self.assertIn('Linear', str(props['regressionType']))

    def test_multiple_trend_lines(self):
        ws = {'trend_lines': [
            {'type': 'linear'},
            {'type': 'exponential'},
        ]}
        obj = self._build(ws)
        self.assertEqual(len(obj['trend']), 2)


class TestDistributionBands(unittest.TestCase):
    """Test distribution band and confidence interval generation."""

    def _build(self, ws_data):
        from pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._main_table = 'Sales'
        objects = {}
        gen._build_analytics_objects(objects, ws_data, 'lineChart', {})
        return objects

    def test_stddev_band(self):
        ws = {'analytics_stats': [
            {'type': 'distribution_band', 'computation': 'standard deviation',
             'value_from': '-1', 'value_to': '1'}
        ]}
        obj = self._build(ws)
        ref_lines = obj['valueAxis'][0]['properties']['referenceLine']
        self.assertEqual(len(ref_lines), 1)
        self.assertEqual(ref_lines[0]['type'], 'Band')
        self.assertIn('Std Dev', str(ref_lines[0].get('displayName', '')))

    def test_percentile_band(self):
        ws = {'analytics_stats': [
            {'type': 'distribution_band', 'computation': 'percentile',
             'value_from': '25', 'value_to': '75'}
        ]}
        obj = self._build(ws)
        ref_lines = obj['valueAxis'][0]['properties']['referenceLine']
        self.assertEqual(ref_lines[0]['type'], 'Band')
        self.assertIn('Percentile', str(ref_lines[0].get('displayName', '')))

    def test_iqr_band(self):
        ws = {'analytics_stats': [
            {'type': 'distribution_band', 'computation': 'iqr',
             'value_from': '25', 'value_to': '75'}
        ]}
        obj = self._build(ws)
        ref_lines = obj['valueAxis'][0]['properties']['referenceLine']
        self.assertEqual(ref_lines[0]['type'], 'Band')

    def test_confidence_interval(self):
        ws = {'analytics_stats': [
            {'type': 'confidence_interval', 'level': '95'}
        ]}
        obj = self._build(ws)
        ref_lines = obj['valueAxis'][0]['properties']['referenceLine']
        self.assertEqual(ref_lines[0]['type'], 'Band')
        self.assertIn('95% CI', str(ref_lines[0].get('displayName', '')))

    def test_stat_line_median(self):
        ws = {'analytics_stats': [
            {'type': 'stat_line', 'stat': 'median'}
        ]}
        obj = self._build(ws)
        ref_lines = obj['valueAxis'][0]['properties']['referenceLine']
        self.assertEqual(ref_lines[0]['type'], 'Median')

    def test_stat_line_percentile_with_value(self):
        ws = {'analytics_stats': [
            {'type': 'stat_reference', 'computation': 'percentile', 'value': '90'}
        ]}
        obj = self._build(ws)
        ref_lines = obj['valueAxis'][0]['properties']['referenceLine']
        self.assertEqual(ref_lines[0]['type'], 'Percentile')
        self.assertIn('90', str(ref_lines[0].get('percentile', '')))

    def test_stat_line_min_max(self):
        ws = {'analytics_stats': [
            {'type': 'stat_line', 'stat': 'min'},
            {'type': 'stat_line', 'stat': 'max'},
        ]}
        obj = self._build(ws)
        ref_lines = obj['valueAxis'][0]['properties']['referenceLine']
        types = [r['type'] for r in ref_lines]
        self.assertIn('Min', types)
        self.assertIn('Max', types)


class TestForecastConfig(unittest.TestCase):
    """Test forecast configuration generation."""

    def _build(self, ws_data):
        from pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._main_table = 'Sales'
        objects = {}
        gen._build_analytics_objects(objects, ws_data, 'lineChart', {})
        return objects

    def test_basic_forecast(self):
        ws = {'forecasting': [{
            'enabled': True, 'periods': 10,
            'prediction_interval': '95', 'model': 'automatic',
        }]}
        obj = self._build(ws)
        self.assertIn('forecast', obj)
        props = obj['forecast'][0]['properties']
        self.assertIn('10', str(props['forecastLength']))

    def test_forecast_seasonality_auto(self):
        ws = {'forecasting': [{'periods': 5, 'model': 'automatic'}]}
        obj = self._build(ws)
        props = obj['forecast'][0]['properties']
        self.assertIn('seasonality', props)
        self.assertIn('Auto', str(props['seasonality']))

    def test_forecast_seasonality_multiplicative(self):
        ws = {'forecasting': [{'periods': 5, 'model': 'multiplicative'}]}
        obj = self._build(ws)
        props = obj['forecast'][0]['properties']
        self.assertIn('Multiplicative', str(props['seasonality']))

    def test_forecast_seasonality_additive(self):
        ws = {'forecasting': [{'periods': 5, 'model': 'additive'}]}
        obj = self._build(ws)
        props = obj['forecast'][0]['properties']
        self.assertIn('Additive', str(props['seasonality']))

    def test_forecast_back_periods(self):
        ws = {'forecasting': [{'periods': 5, 'periods_back': 3, 'model': 'automatic'}]}
        obj = self._build(ws)
        props = obj['forecast'][0]['properties']
        self.assertIn('forecastBackLength', props)
        self.assertIn('3', str(props['forecastBackLength']))

    def test_forecast_no_prediction_bands(self):
        ws = {'forecasting': [{
            'periods': 5, 'model': 'automatic',
            'show_prediction_bands': False,
        }]}
        obj = self._build(ws)
        props = obj['forecast'][0]['properties']
        self.assertIn('none', str(props['confidenceBandStyle']))

    def test_forecast_ignore_last(self):
        ws = {'forecasting': [{
            'periods': 5, 'model': 'automatic',
            'ignore_last': '2',
        }]}
        obj = self._build(ws)
        props = obj['forecast'][0]['properties']
        self.assertIn('ignoreLast', props)


class TestClusteringMigrationNote(unittest.TestCase):
    """Test clustering → MigrationNote on visual subtitle."""

    def _build(self, ws_data):
        from pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._main_table = 'Sales'
        objects = {}
        gen._build_analytics_objects(objects, ws_data, 'scatterChart', {})
        return objects

    def test_clustering_note(self):
        ws = {'clustering': [{'num_clusters': '4', 'variables': ['Sales', 'Profit']}]}
        obj = self._build(ws)
        self.assertIn('subTitle', obj)
        text = str(obj['subTitle'][0]['properties'].get('text', ''))
        self.assertIn('clustering', text.lower())
        self.assertIn('k-means', text.lower())

    def test_clustering_auto_clusters(self):
        ws = {'clustering': [{'num_clusters': 'auto', 'variables': []}]}
        obj = self._build(ws)
        text = str(obj['subTitle'][0]['properties'].get('text', ''))
        self.assertIn('auto', text)

    def test_clustering_does_not_overwrite_annotations(self):
        """When both clustering and annotations exist, clustering takes priority."""
        ws = {
            'clustering': [{'num_clusters': '3', 'variables': ['A']}],
            'annotations': [{'text': 'Some note'}],
        }
        obj = self._build(ws)
        # Clustering wins — annotations section is skipped when clustering present
        text = str(obj['subTitle'][0]['properties'].get('text', ''))
        self.assertIn('clustering', text.lower())


class TestRSquaredMeasure(unittest.TestCase):
    """Test R² DAX measure generation."""

    def test_r_squared_measure_created(self):
        from tmdl_generator import _inject_r_squared_measures
        model = {
            'model': {
                'tables': [{
                    'name': 'Sales',
                    'columns': [
                        {'name': 'Region', 'dataType': 'String'},
                        {'name': 'Amount', 'dataType': 'Double'},
                    ],
                    'measures': [
                        {'name': 'Total Sales', 'expression': 'SUM([Amount])'},
                    ],
                }]
            }
        }
        worksheets = [{
            'name': 'Sales Trend',
            'trend_lines': [{'type': 'linear', 'show_r_squared': True}],
            'fields': [
                {'name': 'Total Sales'},
                {'name': 'Region'},
            ],
        }]
        _inject_r_squared_measures(model, worksheets, 'Sales', {'Total Sales': 'Sales', 'Region': 'Sales'})
        measures = model['model']['tables'][0]['measures']
        r2_measures = [m for m in measures if m['name'].startswith('R²')]
        self.assertEqual(len(r2_measures), 1)
        self.assertIn('CORREL', r2_measures[0]['expression'])
        self.assertEqual(r2_measures[0]['displayFolder'], 'Analytics')

    def test_no_r_squared_when_not_requested(self):
        from tmdl_generator import _inject_r_squared_measures
        model = {
            'model': {
                'tables': [{'name': 'Sales', 'columns': [], 'measures': [
                    {'name': 'Total', 'expression': 'SUM([A])'}
                ]}]
            }
        }
        worksheets = [{
            'name': 'Sheet1',
            'trend_lines': [{'type': 'linear', 'show_r_squared': False}],
            'fields': [{'name': 'Total'}],
        }]
        _inject_r_squared_measures(model, worksheets, 'Sales', {})
        measures = model['model']['tables'][0]['measures']
        r2 = [m for m in measures if m['name'].startswith('R²')]
        self.assertEqual(len(r2), 0)

    def test_no_duplicate_r_squared(self):
        from tmdl_generator import _inject_r_squared_measures
        model = {
            'model': {
                'tables': [{'name': 'T', 'columns': [], 'measures': [
                    {'name': 'M', 'expression': 'SUM([X])'}
                ]}]
            }
        }
        ws = [{'name': 'S', 'trend_lines': [{'type': 'linear', 'show_r_squared': True}],
               'fields': [{'name': 'M'}]}]
        _inject_r_squared_measures(model, ws, 'T', {})
        _inject_r_squared_measures(model, ws, 'T', {})
        r2 = [m for m in model['model']['tables'][0]['measures'] if m['name'].startswith('R²')]
        self.assertEqual(len(r2), 1)


if __name__ == '__main__':
    unittest.main()
