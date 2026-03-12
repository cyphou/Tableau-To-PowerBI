"""
Tests for MigrationConfig — Sprint 27 coverage push.

Targets uncovered lines in powerbi_import/config/migration_config.py:
  - from_args() with various argparse Namespace combinations
  - merge_with_args() (CLI overrides config file)
  - _merge() and _merge_nondefault() static helpers
  - All property accessors
  - save() / load_config() convenience function
"""

import argparse
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.config.migration_config import MigrationConfig, load_config


def _make_args(**kwargs):
    """Create an argparse.Namespace with given values (others absent)."""
    return argparse.Namespace(**kwargs)


class TestFromArgs(unittest.TestCase):
    """Test MigrationConfig.from_args() with various CLI arg combinations."""

    def test_from_args_source_fields(self):
        args = _make_args(tableau_file='workbook.twbx', prep='flow.tfl')
        cfg = MigrationConfig.from_args(args)
        self.assertEqual(cfg.tableau_file, 'workbook.twbx')
        self.assertEqual(cfg.prep_flow, 'flow.tfl')

    def test_from_args_output_fields(self):
        args = _make_args(output_dir='/tmp/out', output_format='tmdl')
        cfg = MigrationConfig.from_args(args)
        self.assertEqual(cfg.output_dir, '/tmp/out')
        self.assertEqual(cfg.output_format, 'tmdl')

    def test_from_args_model_fields(self):
        args = _make_args(mode='directquery', culture='fr-FR',
                          calendar_start=2018, calendar_end=2028)
        cfg = MigrationConfig.from_args(args)
        self.assertEqual(cfg.model_mode, 'directquery')
        self.assertEqual(cfg.culture, 'fr-FR')
        self.assertEqual(cfg.calendar_start, 2018)
        self.assertEqual(cfg.calendar_end, 2028)

    def test_from_args_migration_flags(self):
        args = _make_args(
            skip_extraction=True,
            skip_conversion=True,
            dry_run=True,
            rollback=True,
            verbose=True,
            log_file='migration.log',
        )
        cfg = MigrationConfig.from_args(args)
        self.assertTrue(cfg.skip_extraction)
        self.assertTrue(cfg.dry_run)
        self.assertTrue(cfg.rollback)
        self.assertTrue(cfg.verbose)
        self.assertEqual(cfg.log_file, 'migration.log')

    def test_from_args_missing_attrs_use_defaults(self):
        """Missing attributes on Namespace should keep defaults."""
        args = _make_args()  # Empty namespace
        cfg = MigrationConfig.from_args(args)
        self.assertEqual(cfg.model_mode, 'import')
        self.assertEqual(cfg.culture, 'en-US')
        self.assertIsNone(cfg.tableau_file)
        self.assertIsNone(cfg.output_dir)
        self.assertFalse(cfg.dry_run)

    def test_from_args_none_values_keep_defaults(self):
        """Explicitly None values should keep defaults."""
        args = _make_args(
            tableau_file=None, output_dir=None, mode=None,
            culture=None, calendar_start=None, calendar_end=None,
            verbose=False, dry_run=False, log_file=None,
        )
        cfg = MigrationConfig.from_args(args)
        self.assertEqual(cfg.model_mode, 'import')
        self.assertEqual(cfg.culture, 'en-US')
        self.assertEqual(cfg.calendar_start, 2020)
        self.assertEqual(cfg.calendar_end, 2030)
        self.assertFalse(cfg.verbose)
        self.assertIsNone(cfg.log_file)

    def test_from_args_calendar_zero_is_valid(self):
        """calendar_start=0 should be set (not treated as falsy)."""
        args = _make_args(calendar_start=0, calendar_end=0)
        cfg = MigrationConfig.from_args(args)
        self.assertEqual(cfg.calendar_start, 0)
        self.assertEqual(cfg.calendar_end, 0)


class TestMergeWithArgs(unittest.TestCase):
    """Test merge_with_args() — CLI arguments override config file."""

    def test_cli_overrides_config_mode(self):
        file_cfg = MigrationConfig({'model': {'mode': 'import'}})
        args = _make_args(mode='directquery')
        merged = file_cfg.merge_with_args(args)
        self.assertEqual(merged.model_mode, 'directquery')

    def test_cli_does_not_override_unset_values(self):
        """CLI defaults should not override config file values."""
        file_cfg = MigrationConfig({
            'model': {'mode': 'composite', 'culture': 'de-DE'},
        })
        args = _make_args()  # No overrides
        merged = file_cfg.merge_with_args(args)
        self.assertEqual(merged.model_mode, 'composite')
        self.assertEqual(merged.culture, 'de-DE')

    def test_merge_preserves_file_and_applies_cli(self):
        file_cfg = MigrationConfig({
            'source': {'tableau_file': 'file.twbx'},
            'model': {'culture': 'ja-JP'},
        })
        args = _make_args(verbose=True, dry_run=True)
        merged = file_cfg.merge_with_args(args)
        self.assertEqual(merged.tableau_file, 'file.twbx')
        self.assertEqual(merged.culture, 'ja-JP')
        self.assertTrue(merged.verbose)
        self.assertTrue(merged.dry_run)

    def test_merge_cli_calendar_overrides(self):
        file_cfg = MigrationConfig({'model': {'calendar_start': 2015}})
        args = _make_args(calendar_start=2010, calendar_end=2035)
        merged = file_cfg.merge_with_args(args)
        self.assertEqual(merged.calendar_start, 2010)
        self.assertEqual(merged.calendar_end, 2035)


class TestMergeHelpers(unittest.TestCase):
    """Test _merge() and _merge_nondefault() static methods."""

    def test_merge_deep_nested(self):
        target = {'a': {'b': 1, 'c': 2}, 'd': 3}
        source = {'a': {'b': 99}, 'e': 5}
        MigrationConfig._merge(target, source)
        self.assertEqual(target['a']['b'], 99)
        self.assertEqual(target['a']['c'], 2)  # Preserved
        self.assertEqual(target['e'], 5)  # Added

    def test_merge_replaces_non_dict(self):
        target = {'a': 'old'}
        source = {'a': 'new'}
        MigrationConfig._merge(target, source)
        self.assertEqual(target['a'], 'new')

    def test_merge_nondefault_skips_default_values(self):
        target = {'model': {'mode': 'composite'}}
        source = {'model': {'mode': 'import'}}  # Same as default
        defaults = {'model': {'mode': 'import'}}
        MigrationConfig._merge_nondefault(target, source, defaults)
        self.assertEqual(target['model']['mode'], 'composite')  # Unchanged

    def test_merge_nondefault_applies_non_default_values(self):
        target = {'model': {'mode': 'import'}}
        source = {'model': {'mode': 'directquery'}}  # Different from default
        defaults = {'model': {'mode': 'import'}}
        MigrationConfig._merge_nondefault(target, source, defaults)
        self.assertEqual(target['model']['mode'], 'directquery')

    def test_merge_nondefault_flat_keys(self):
        target = {'x': 1}
        source = {'x': 2}
        defaults = {'x': 1}
        MigrationConfig._merge_nondefault(target, source, defaults)
        # source x=2 differs from default x=1 → override applied
        self.assertEqual(target['x'], 2)


class TestPropertyAccessors(unittest.TestCase):
    """Test all property accessors on MigrationConfig."""

    def test_all_source_properties(self):
        cfg = MigrationConfig({
            'source': {'tableau_file': 'wb.twbx', 'prep_flow': 'flow.tfl'},
        })
        self.assertEqual(cfg.tableau_file, 'wb.twbx')
        self.assertEqual(cfg.prep_flow, 'flow.tfl')

    def test_all_output_properties(self):
        cfg = MigrationConfig({
            'output': {
                'directory': '/out',
                'format': 'tmdl',
                'report_name': 'MyReport',
            },
        })
        self.assertEqual(cfg.output_dir, '/out')
        self.assertEqual(cfg.output_format, 'tmdl')
        self.assertEqual(cfg.report_name, 'MyReport')

    def test_all_model_properties(self):
        cfg = MigrationConfig({
            'model': {
                'mode': 'composite',
                'culture': 'pt-BR',
                'calendar_start': 2015,
                'calendar_end': 2025,
            },
        })
        self.assertEqual(cfg.model_mode, 'composite')
        self.assertEqual(cfg.culture, 'pt-BR')
        self.assertEqual(cfg.calendar_start, 2015)
        self.assertEqual(cfg.calendar_end, 2025)

    def test_all_migration_properties(self):
        cfg = MigrationConfig({
            'migration': {
                'skip_extraction': True,
                'dry_run': True,
                'rollback': True,
                'verbose': True,
                'log_file': 'run.log',
            },
        })
        self.assertTrue(cfg.skip_extraction)
        self.assertTrue(cfg.dry_run)
        self.assertTrue(cfg.rollback)
        self.assertTrue(cfg.verbose)
        self.assertEqual(cfg.log_file, 'run.log')

    def test_template_vars_empty_default(self):
        cfg = MigrationConfig()
        self.assertEqual(cfg.template_vars, {})

    def test_template_vars_populated(self):
        cfg = MigrationConfig({
            'connections': {'template_vars': {'HOST': 'db.co', 'PORT': '3306'}},
        })
        self.assertEqual(cfg.template_vars['HOST'], 'db.co')
        self.assertEqual(cfg.template_vars['PORT'], '3306')

    def test_plugins_default_empty(self):
        cfg = MigrationConfig()
        self.assertEqual(cfg.plugins, [])


class TestSaveAndLoad(unittest.TestCase):
    """Test save() and load_config() round-trip."""

    def test_save_creates_file(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = MigrationConfig({'model': {'mode': 'directquery'}})
            path = os.path.join(td, 'sub', 'config.json')
            cfg.save(path)
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data['model']['mode'], 'directquery')

    def test_save_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            orig = MigrationConfig({
                'source': {'tableau_file': 'test.twbx'},
                'model': {'culture': 'fr-FR', 'calendar_start': 2018},
                'connections': {'template_vars': {'DB': 'mydb'}},
            })
            path = os.path.join(td, 'cfg.json')
            orig.save(path)
            loaded = MigrationConfig.from_file(path)
            self.assertEqual(loaded.tableau_file, 'test.twbx')
            self.assertEqual(loaded.culture, 'fr-FR')
            self.assertEqual(loaded.calendar_start, 2018)
            self.assertEqual(loaded.template_vars['DB'], 'mydb')

    def test_load_config_with_file_and_args(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'config.json')
            with open(path, 'w') as f:
                json.dump({'model': {'mode': 'composite', 'culture': 'de-DE'}}, f)
            args = _make_args(verbose=True)
            cfg = load_config(filepath=path, args=args)
            self.assertEqual(cfg.model_mode, 'composite')
            self.assertEqual(cfg.culture, 'de-DE')
            self.assertTrue(cfg.verbose)

    def test_load_config_args_only(self):
        args = _make_args(mode='directquery', culture='ja-JP')
        cfg = load_config(args=args)
        self.assertEqual(cfg.model_mode, 'directquery')
        self.assertEqual(cfg.culture, 'ja-JP')

    def test_load_config_no_inputs(self):
        cfg = load_config()
        self.assertEqual(cfg.model_mode, 'import')


if __name__ == '__main__':
    unittest.main()
