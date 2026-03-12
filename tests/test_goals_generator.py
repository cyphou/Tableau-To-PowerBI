"""Tests for powerbi_import.goals_generator — PBI Goals/Scorecard JSON.

Covers generate_goals_json(), _build_goal(), and write_goals_artifact().
"""

import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from goals_generator import (
    generate_goals_json,
    _build_goal,
    write_goals_artifact,
    _CADENCE_REFRESH,
)


class TestCadenceRefresh(unittest.TestCase):
    """Verify cadence-to-ISO-duration mapping."""

    def test_all_cadences_present(self):
        for cadence in ('Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly'):
            self.assertIn(cadence, _CADENCE_REFRESH)

    def test_daily_is_p1d(self):
        self.assertEqual(_CADENCE_REFRESH['Daily'], 'P1D')


class TestBuildGoal(unittest.TestCase):
    """Test _build_goal() function."""

    def test_basic_goal(self):
        metric = {
            'name': 'Revenue',
            'measure_field': 'SUM(Sales)',
            'aggregation': 'SUM',
            'time_grain': 'Monthly',
        }
        goal = _build_goal(metric, 0, 'sc-123')
        self.assertIsNotNone(goal)
        self.assertEqual(goal['name'], 'Revenue')
        self.assertEqual(goal['scorecardId'], 'sc-123')
        self.assertEqual(goal['ordinal'], 0)
        self.assertEqual(goal['cadence'], 'Monthly')
        self.assertEqual(goal['refreshSchedule'], 'P1M')
        self.assertIn('connectedMeasure', goal)
        self.assertEqual(goal['connectedMeasure']['measure'], 'SUM(Sales)')

    def test_goal_with_target(self):
        metric = {
            'name': 'Revenue',
            'target_value': 100000,
            'target_label': '100K',
        }
        goal = _build_goal(metric, 1, 'sc-456')
        self.assertIn('target', goal)
        self.assertEqual(goal['target']['value'], 100000)
        self.assertEqual(goal['target']['label'], '100K')

    def test_goal_with_time_dimension(self):
        metric = {'name': 'Qty', 'time_dimension': 'OrderDate'}
        goal = _build_goal(metric, 0, 'sc')
        self.assertEqual(goal['timeDimension'], 'OrderDate')

    def test_goal_with_filters(self):
        metric = {
            'name': 'Sales',
            'filters': [
                {'field': 'Region', 'operator': 'In', 'values': ['East', 'West']},
            ],
        }
        goal = _build_goal(metric, 0, 'sc')
        self.assertEqual(len(goal['filters']), 1)
        self.assertEqual(goal['filters'][0]['field'], 'Region')

    def test_goal_with_number_format(self):
        metric = {'name': 'Revenue', 'number_format': '#,##0'}
        goal = _build_goal(metric, 0, 'sc')
        self.assertEqual(goal['numberFormat'], '#,##0')

    def test_goal_missing_name_returns_none(self):
        metric = {'measure_field': 'SUM(X)'}
        goal = _build_goal(metric, 0, 'sc')
        self.assertIsNone(goal)

    def test_goal_empty_name_returns_none(self):
        metric = {'name': ''}
        goal = _build_goal(metric, 0, 'sc')
        self.assertIsNone(goal)

    def test_migration_annotation(self):
        metric = {'name': 'Revenue', 'aggregation': 'SUM'}
        goal = _build_goal(metric, 0, 'sc')
        self.assertIn('annotations', goal)
        note = goal['annotations'][0]
        self.assertEqual(note['name'], 'MigrationNote')
        self.assertIn('Revenue', note['value'])
        self.assertIn('SUM', note['value'])

    def test_unknown_cadence_defaults_to_p1m(self):
        metric = {'name': 'X', 'time_grain': 'Biweekly'}
        goal = _build_goal(metric, 0, 'sc')
        self.assertEqual(goal['refreshSchedule'], 'P1M')

    def test_no_measure_field_no_connected_measure(self):
        metric = {'name': 'Manual Goal'}
        goal = _build_goal(metric, 0, 'sc')
        self.assertNotIn('connectedMeasure', goal)


class TestGenerateGoalsJson(unittest.TestCase):
    """Test generate_goals_json() function."""

    def test_generates_scorecard(self):
        metrics = [
            {'name': 'Revenue', 'measure_field': 'SUM(Amount)', 'aggregation': 'SUM'},
            {'name': 'Orders', 'measure_field': 'COUNT(OrderID)', 'aggregation': 'COUNT'},
        ]
        scorecard = generate_goals_json(metrics, 'Sales Report')
        self.assertIsNotNone(scorecard)
        self.assertEqual(scorecard['name'], 'Sales Report Scorecard')
        self.assertEqual(len(scorecard['goals']), 2)
        self.assertIn('id', scorecard)
        self.assertIn('createdTime', scorecard)

    def test_empty_metrics_returns_none(self):
        result = generate_goals_json([], 'Test')
        self.assertIsNone(result)

    def test_none_metrics_returns_none(self):
        result = generate_goals_json(None, 'Test')
        self.assertIsNone(result)

    def test_workspace_id_included(self):
        metrics = [{'name': 'M1'}]
        scorecard = generate_goals_json(metrics, 'R', workspace_id='ws-001')
        self.assertEqual(scorecard['workspaceId'], 'ws-001')

    def test_workspace_id_absent_by_default(self):
        metrics = [{'name': 'M1'}]
        scorecard = generate_goals_json(metrics, 'R')
        self.assertNotIn('workspaceId', scorecard)

    def test_skips_metrics_without_name(self):
        metrics = [
            {'name': 'Good'},
            {'measure_field': 'SUM(X)'},  # no name
            {'name': ''},  # empty name
        ]
        scorecard = generate_goals_json(metrics, 'R')
        self.assertEqual(len(scorecard['goals']), 1)

    def test_description_mentions_count(self):
        metrics = [{'name': 'A'}, {'name': 'B'}]
        sc = generate_goals_json(metrics, 'R')
        self.assertIn('2 goals', sc['description'])

    def test_default_report_name(self):
        metrics = [{'name': 'X'}]
        sc = generate_goals_json(metrics)
        self.assertEqual(sc['name'], 'Report Scorecard')


class TestWriteGoalsArtifact(unittest.TestCase):
    """Test write_goals_artifact() function."""

    def test_writes_json_file(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_goals_')
        try:
            scorecard = {
                'id': 'sc-1',
                'name': 'Test Scorecard',
                'goals': [{'name': 'G1'}],
            }
            result = write_goals_artifact(scorecard, tmpdir)
            self.assertIsNotNone(result)
            self.assertTrue(os.path.exists(result))
            self.assertTrue(result.endswith('scorecard.json'))

            with open(result, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data['name'], 'Test Scorecard')
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_creates_goals_subdir(self):
        tmpdir = tempfile.mkdtemp(prefix='ttpbi_test_goals_')
        try:
            scorecard = {'id': 'sc-1', 'goals': []}
            write_goals_artifact(scorecard, tmpdir)
            self.assertTrue(os.path.isdir(os.path.join(tmpdir, 'goals')))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_none_scorecard_returns_none(self):
        result = write_goals_artifact(None, '/tmp/whatever')
        self.assertIsNone(result)

    def test_empty_scorecard_returns_none(self):
        result = write_goals_artifact({}, '/tmp/whatever')
        # Empty dict is falsy — should return None
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
