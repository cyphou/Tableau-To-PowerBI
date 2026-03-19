"""
Tests for merge_config module — Sprint 56.

Covers:
  - save_merge_config / load_merge_config round-trip
  - apply_merge_config table decisions
  - apply_merge_config measure decisions
  - Config version validation
  - Default options
  - Edge cases: empty config, invalid JSON, forward compatibility
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.merge_config import (
    save_merge_config,
    load_merge_config,
    apply_merge_config,
    _CONFIG_VERSION,
)


def _make_mock_assessment(merge_candidates=None, unique_tables=None,
                          measure_conflicts=None, parameter_conflicts=None):
    """Create a mock assessment object."""
    assessment = MagicMock()
    assessment.merge_score = 85
    assessment.recommendation = 'merge'
    assessment.merge_candidates = merge_candidates or []
    assessment.unique_tables = unique_tables or {}
    assessment.unique_table_count = 0
    assessment.measure_conflicts = measure_conflicts or []
    assessment.parameter_conflicts = parameter_conflicts or []
    return assessment


def _make_mock_candidate(table_name, sources=None, overlap=0.9, conflicts=None):
    """Create a mock merge candidate."""
    mc = MagicMock()
    mc.table_name = table_name
    mc.sources = sources or [('wb1', 'fp1', 100)]
    mc.column_overlap = overlap
    mc.conflicts = conflicts or []
    return mc


def _make_mock_measure_conflict(name, variants=None):
    """Create a mock measure conflict."""
    mc = MagicMock()
    mc.name = name
    mc.variants = variants or {'wb1': 'SUM(Sales)', 'wb2': 'AVG(Sales)'}
    return mc


class TestSaveLoadRoundTrip(unittest.TestCase):
    def test_basic_round_trip(self):
        assessment = _make_mock_assessment(
            merge_candidates=[
                _make_mock_candidate('Orders', sources=[('wb1', 'fp1', 100), ('wb2', 'fp2', 100)]),
            ],
            unique_tables={'wb1': ['Products']},
            measure_conflicts=[_make_mock_measure_conflict('Total Sales')],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'config.json')
            save_merge_config(assessment, ['wb1', 'wb2'], path)
            config = load_merge_config(path)

        self.assertEqual(config['version'], _CONFIG_VERSION)
        self.assertEqual(config['workbooks'], ['wb1', 'wb2'])
        self.assertEqual(config['merge_score'], 85)
        self.assertGreater(len(config['table_decisions']), 0)

    def test_table_decisions_structure(self):
        assessment = _make_mock_assessment(
            merge_candidates=[_make_mock_candidate('Orders')],
            unique_tables={'wb1': ['Unique1']},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'config.json')
            save_merge_config(assessment, ['wb1'], path)
            config = load_merge_config(path)

        merge_td = [td for td in config['table_decisions']
                     if td['action'] == 'merge']
        include_td = [td for td in config['table_decisions']
                       if td['action'] == 'include']
        self.assertEqual(len(merge_td), 1)
        self.assertEqual(merge_td[0]['table_name'], 'Orders')
        self.assertEqual(len(include_td), 1)
        self.assertEqual(include_td[0]['table_name'], 'Unique1')

    def test_measure_decisions_structure(self):
        assessment = _make_mock_assessment(
            measure_conflicts=[_make_mock_measure_conflict('Revenue')],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'config.json')
            save_merge_config(assessment, ['wb1', 'wb2'], path)
            config = load_merge_config(path)

        self.assertEqual(len(config['measure_decisions']), 1)
        self.assertEqual(config['measure_decisions'][0]['measure_name'], 'Revenue')
        self.assertEqual(config['measure_decisions'][0]['action'], 'namespace')

    def test_options_present(self):
        assessment = _make_mock_assessment()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'config.json')
            save_merge_config(assessment, [], path)
            config = load_merge_config(path)

        self.assertIn('options', config)
        self.assertIn('force_merge', config['options'])
        self.assertIn('column_overlap_threshold', config['options'])
        self.assertIn('auto_namespace', config['options'])


class TestLoadMergeConfig(unittest.TestCase):
    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_merge_config('/nonexistent/config.json')

    def test_wrong_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'config.json')
            with open(path, 'w') as f:
                json.dump({'version': '99.0'}, f)
            with self.assertRaises(ValueError):
                load_merge_config(path)

    def test_valid_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'config.json')
            with open(path, 'w') as f:
                json.dump({'version': _CONFIG_VERSION}, f)
            config = load_merge_config(path)
            self.assertEqual(config['version'], _CONFIG_VERSION)


class TestApplyMergeConfig(unittest.TestCase):
    def test_skip_table(self):
        mc = _make_mock_candidate('SkipMe', sources=[('wb1', 'fp', 100)])
        assessment = _make_mock_assessment(merge_candidates=[mc])
        config = {
            'table_decisions': [
                {'table_name': 'SkipMe', 'action': 'skip'},
            ],
            'measure_decisions': [],
            'options': {},
        }
        apply_merge_config(assessment, config)
        self.assertEqual(len(assessment.merge_candidates), 0)

    def test_merge_table_kept(self):
        mc = _make_mock_candidate('KeepMe')
        assessment = _make_mock_assessment(merge_candidates=[mc])
        config = {
            'table_decisions': [
                {'table_name': 'KeepMe', 'action': 'merge'},
            ],
            'measure_decisions': [],
            'options': {},
        }
        apply_merge_config(assessment, config)
        self.assertEqual(len(assessment.merge_candidates), 1)

    def test_exclude_unique_table(self):
        assessment = _make_mock_assessment(
            unique_tables={'wb1': ['ExcludeMe', 'KeepMe']})
        config = {
            'table_decisions': [
                {'table_name': 'ExcludeMe', 'action': 'exclude'},
            ],
            'measure_decisions': [],
            'options': {},
        }
        apply_merge_config(assessment, config)
        self.assertNotIn('ExcludeMe', assessment.unique_tables['wb1'])
        self.assertIn('KeepMe', assessment.unique_tables['wb1'])

    def test_force_merge_option(self):
        assessment = _make_mock_assessment()
        assessment.recommendation = 'separate'
        config = {
            'table_decisions': [],
            'measure_decisions': [],
            'options': {'force_merge': True},
        }
        apply_merge_config(assessment, config)
        self.assertEqual(assessment.recommendation, 'merge')

    def test_config_stored_on_assessment(self):
        assessment = _make_mock_assessment()
        config = {
            'table_decisions': [],
            'measure_decisions': [],
            'options': {},
        }
        apply_merge_config(assessment, config)
        self.assertEqual(assessment._merge_config, config)

    def test_no_table_decision_defaults_to_merge(self):
        mc = _make_mock_candidate('Unknown')
        assessment = _make_mock_assessment(merge_candidates=[mc])
        config = {
            'table_decisions': [],
            'measure_decisions': [],
            'options': {},
        }
        apply_merge_config(assessment, config)
        self.assertEqual(len(assessment.merge_candidates), 1)

    def test_unique_table_count_updated(self):
        mc = _make_mock_candidate('T1')
        assessment = _make_mock_assessment(
            merge_candidates=[mc],
            unique_tables={'wb1': ['U1']})
        config = {
            'table_decisions': [],
            'measure_decisions': [],
            'options': {},
        }
        apply_merge_config(assessment, config)
        self.assertEqual(assessment.unique_table_count, 2)


class TestSaveCreatesDirectory(unittest.TestCase):
    def test_nested_dir_created(self):
        assessment = _make_mock_assessment()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'sub', 'dir', 'config.json')
            save_merge_config(assessment, [], path)
            self.assertTrue(os.path.exists(path))


class TestParameterDecisions(unittest.TestCase):
    def test_parameter_conflicts_saved(self):
        assessment = _make_mock_assessment(
            parameter_conflicts=[
                {'name': 'Param1', 'variants': {'wb1': '10', 'wb2': '20'}},
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'config.json')
            save_merge_config(assessment, ['wb1', 'wb2'], path)
            config = load_merge_config(path)
        self.assertEqual(len(config['parameter_decisions']), 1)
        self.assertEqual(config['parameter_decisions'][0]['parameter_name'], 'Param1')


if __name__ == '__main__':
    unittest.main()
