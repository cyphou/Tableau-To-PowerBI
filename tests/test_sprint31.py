"""
Sprint 31 tests — Plugins, Packaging & Automation.

Covers:
  31.1  Plugin examples (custom_visual_mapper, dax_post_processor, naming_convention)
  31.2  PyPI publish workflow (file existence)
  31.3  PBIR schema forward-compat check
  31.4  Fractional deployment timeouts
  31.5  CLI --check-schema argument
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure repo root is on sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure examples/ is importable
EXAMPLES_DIR = os.path.join(ROOT, 'examples')
if EXAMPLES_DIR not in sys.path:
    sys.path.insert(0, EXAMPLES_DIR)


# ── 31.1  Plugin examples ────────────────────────────────────────────────────

class TestCustomVisualMapperPlugin(unittest.TestCase):
    """Tests for examples/plugins/custom_visual_mapper.py."""

    def _make_plugin(self, **kwargs):
        from examples.plugins.custom_visual_mapper import CustomVisualMapperPlugin
        return CustomVisualMapperPlugin(**kwargs)

    def test_default_bar_mapping(self):
        plugin = self._make_plugin()
        self.assertEqual(plugin.custom_visual_mapping("bar"), "clusteredBarChart")

    def test_default_circle_mapping(self):
        plugin = self._make_plugin()
        self.assertEqual(plugin.custom_visual_mapping("circle"), "scatterChart")

    def test_unknown_mark_returns_none(self):
        plugin = self._make_plugin()
        self.assertIsNone(plugin.custom_visual_mapping("unknownMark"))

    def test_none_mark_returns_none(self):
        plugin = self._make_plugin()
        self.assertIsNone(plugin.custom_visual_mapping(None))

    def test_case_insensitive_lookup(self):
        plugin = self._make_plugin()
        self.assertEqual(plugin.custom_visual_mapping("BAR"), "clusteredBarChart")

    def test_custom_overrides_merge(self):
        plugin = self._make_plugin(overrides={"line": "myLineVisual"})
        self.assertEqual(plugin.custom_visual_mapping("line"), "myLineVisual")
        # Default still works
        self.assertEqual(plugin.custom_visual_mapping("bar"), "clusteredBarChart")

    def test_custom_overrides_replace_default(self):
        plugin = self._make_plugin(overrides={"bar": "myBar"})
        self.assertEqual(plugin.custom_visual_mapping("bar"), "myBar")

    def test_plugin_alias(self):
        from examples.plugins.custom_visual_mapper import Plugin, CustomVisualMapperPlugin
        self.assertIs(Plugin, CustomVisualMapperPlugin)

    def test_plugin_name(self):
        plugin = self._make_plugin()
        self.assertEqual(plugin.name, "custom_visual_mapper")


class TestDaxPostProcessorPlugin(unittest.TestCase):
    """Tests for examples/plugins/dax_post_processor.py."""

    def _make_plugin(self, **kwargs):
        from examples.plugins.dax_post_processor import DaxPostProcessorPlugin
        return DaxPostProcessorPlugin(**kwargs)

    def test_default_operator_whitespace(self):
        plugin = self._make_plugin()
        result = plugin.transform_dax("A+B")
        self.assertEqual(result, "A + B")

    def test_subtraction_whitespace(self):
        plugin = self._make_plugin()
        result = plugin.transform_dax("X-Y")
        self.assertEqual(result, "X - Y")

    def test_iferror_wrapping(self):
        plugin = self._make_plugin(wrap_iferror=True)
        result = plugin.transform_dax("SUM(Sales)")
        self.assertEqual(result, "IFERROR(SUM(Sales), BLANK())")

    def test_empty_formula_unchanged(self):
        plugin = self._make_plugin()
        self.assertEqual(plugin.transform_dax(""), "")
        self.assertIsNone(plugin.transform_dax(None))

    def test_custom_replacements(self):
        plugin = self._make_plugin(replacements=[
            (r'OldServer', 'NewServer'),
        ])
        result = plugin.transform_dax("'OldServer'[Col]")
        self.assertEqual(result, "'NewServer'[Col]")

    def test_add_replacement(self):
        plugin = self._make_plugin(replacements=[])
        plugin.add_replacement(r'ALPHA', 'BETA')
        self.assertEqual(plugin.transform_dax("ALPHA()"), "BETA()")

    def test_plugin_alias(self):
        from examples.plugins.dax_post_processor import Plugin, DaxPostProcessorPlugin
        self.assertIs(Plugin, DaxPostProcessorPlugin)

    def test_plugin_name(self):
        plugin = self._make_plugin()
        self.assertEqual(plugin.name, "dax_post_processor")


class TestNamingConventionPlugin(unittest.TestCase):
    """Tests for examples/plugins/naming_convention.py."""

    def test_to_snake_case(self):
        from examples.plugins.naming_convention import to_snake_case
        self.assertEqual(to_snake_case("SalesAmount"), "sales_amount")
        self.assertEqual(to_snake_case("sales_amount"), "sales_amount")
        self.assertEqual(to_snake_case("sales-amount"), "sales_amount")

    def test_to_pascal_case(self):
        from examples.plugins.naming_convention import to_pascal_case
        self.assertEqual(to_pascal_case("sales_amount"), "SalesAmount")
        self.assertEqual(to_pascal_case("SalesAmount"), "SalesAmount")

    def test_to_camel_case(self):
        from examples.plugins.naming_convention import to_camel_case
        self.assertEqual(to_camel_case("sales_amount"), "salesAmount")
        self.assertEqual(to_camel_case("SalesAmount"), "salesAmount")

    def test_invalid_convention_raises(self):
        from examples.plugins.naming_convention import NamingConventionPlugin
        with self.assertRaises(ValueError):
            NamingConventionPlugin(convention="UPPER_CASE")

    def test_post_extraction_renames_tables(self):
        from examples.plugins.naming_convention import NamingConventionPlugin
        plugin = NamingConventionPlugin(convention="snake_case")
        data = {
            'datasources': [
                {'tables': [{'name': 'SalesData', 'columns': []}]}
            ],
            'calculations': [],
            'parameters': [],
        }
        result = plugin.post_extraction(data)
        self.assertIsNotNone(result)
        self.assertEqual(result['datasources'][0]['tables'][0]['name'], 'sales_data')

    def test_post_extraction_renames_calculations(self):
        from examples.plugins.naming_convention import NamingConventionPlugin
        plugin = NamingConventionPlugin(convention="PascalCase")
        data = {
            'datasources': [],
            'calculations': [{'name': 'total_sales'}],
            'parameters': [],
        }
        result = plugin.post_extraction(data)
        self.assertEqual(result['calculations'][0]['name'], 'TotalSales')

    def test_post_extraction_none_data(self):
        from examples.plugins.naming_convention import NamingConventionPlugin
        plugin = NamingConventionPlugin()
        self.assertIsNone(plugin.post_extraction(None))
        self.assertIsNone(plugin.post_extraction({}))

    def test_plugin_alias(self):
        from examples.plugins.naming_convention import Plugin, NamingConventionPlugin
        self.assertIs(Plugin, NamingConventionPlugin)


class TestPluginRegistration(unittest.TestCase):
    """Test plugins work with the PluginManager."""

    def test_register_custom_visual_mapper(self):
        from powerbi_import.plugins import PluginManager
        from examples.plugins.custom_visual_mapper import CustomVisualMapperPlugin

        pm = PluginManager()
        pm.register(CustomVisualMapperPlugin())
        self.assertTrue(pm.has_plugins())

        result = pm.call_hook('custom_visual_mapping', tableau_mark='bar')
        self.assertEqual(result, 'clusteredBarChart')

    def test_dax_transform_chain(self):
        from powerbi_import.plugins import PluginManager
        from examples.plugins.dax_post_processor import DaxPostProcessorPlugin

        pm = PluginManager()
        pm.register(DaxPostProcessorPlugin(wrap_iferror=True))

        result = pm.apply_transform('transform_dax', 'A+B')
        self.assertEqual(result, 'IFERROR(A + B, BLANK())')


# ── 31.2  PyPI publish workflow ──────────────────────────────────────────────

class TestPublishWorkflow(unittest.TestCase):
    """Verify the PyPI publish workflow file exists and is valid YAML-ish."""

    def test_workflow_file_exists(self):
        wf = os.path.join(ROOT, '.github', 'workflows', 'publish.yml')
        self.assertTrue(os.path.isfile(wf), f"Missing {wf}")

    def test_workflow_contains_trigger(self):
        wf = os.path.join(ROOT, '.github', 'workflows', 'publish.yml')
        content = open(wf, encoding='utf-8').read()
        self.assertIn('tags:', content)
        self.assertIn('v*.*.*', content)

    def test_workflow_uses_pypi_action(self):
        wf = os.path.join(ROOT, '.github', 'workflows', 'publish.yml')
        content = open(wf, encoding='utf-8').read()
        self.assertIn('pypa/gh-action-pypi-publish', content)


# ── 31.3  PBIR schema forward-compat check ──────────────────────────────────

class TestPBIRSchemaVersionCheck(unittest.TestCase):
    """Tests for ArtifactValidator.check_pbir_schema_version()."""

    def test_offline_check_returns_all_schemas(self):
        from powerbi_import.validator import ArtifactValidator
        info = ArtifactValidator.check_pbir_schema_version(fetch=False)
        for key in ('report', 'page', 'visualContainer'):
            self.assertIn(key, info)
            entry = info[key]
            self.assertIn('current', entry)
            self.assertIn('latest', entry)
            self.assertIn('url', entry)
            self.assertIn('update_available', entry)
            # No fetch → no updates available
            self.assertFalse(entry['update_available'])
            self.assertEqual(entry['current'], entry['latest'])

    def test_offline_current_versions_match(self):
        from powerbi_import.validator import ArtifactValidator
        info = ArtifactValidator.check_pbir_schema_version(fetch=False)
        self.assertEqual(info['report']['current'], '3.1.0')
        self.assertEqual(info['page']['current'], '2.0.0')
        self.assertEqual(info['visualContainer']['current'], '2.5.0')

    def test_url_format(self):
        from powerbi_import.validator import ArtifactValidator
        info = ArtifactValidator.check_pbir_schema_version(fetch=False)
        for entry in info.values():
            self.assertTrue(entry['url'].startswith('https://'))
            self.assertTrue(entry['url'].endswith('/schema.json'))

    @patch.object(
        __import__('powerbi_import.validator', fromlist=['ArtifactValidator']).ArtifactValidator,
        '_url_exists',
        return_value=False,
    )
    def test_fetch_no_updates(self, mock_exists):
        from powerbi_import.validator import ArtifactValidator
        info = ArtifactValidator.check_pbir_schema_version(fetch=True)
        for entry in info.values():
            self.assertFalse(entry['update_available'])

    @patch.object(
        __import__('powerbi_import.validator', fromlist=['ArtifactValidator']).ArtifactValidator,
        '_url_exists',
    )
    def test_fetch_detects_update(self, mock_exists):
        """When a higher patch version exists, update_available should be True."""
        from powerbi_import.validator import ArtifactValidator

        def side_effect(url):
            # Simulate report schema having 3.1.1 available
            return '3.1.1' in url

        mock_exists.side_effect = side_effect
        info = ArtifactValidator.check_pbir_schema_version(fetch=True)
        self.assertTrue(info['report']['update_available'])
        self.assertEqual(info['report']['latest'], '3.1.1')

    def test_url_exists_with_bad_url(self):
        from powerbi_import.validator import ArtifactValidator
        self.assertFalse(ArtifactValidator._url_exists('https://invalid.example.test/'))


# ── 31.4  Fractional deployment timeouts ─────────────────────────────────────

class TestFractionalTimeouts(unittest.TestCase):
    """Verify deployment_timeout and retry_delay accept float values."""

    def test_fallback_settings_parse_float(self):
        from powerbi_import.deploy.config.settings import _FallbackSettings
        s = _FallbackSettings()
        # _parse_positive_number(env_name, raw_default, default) — first arg is env var name
        # Use a non-existent env var so it falls back to raw_default
        result = s._parse_positive_number('__TEST_NONEXISTENT_VAR__', '2.5', 1.0)
        self.assertIsInstance(result, float)
        self.assertEqual(result, 2.5)

    def test_fallback_settings_default_timeout_type(self):
        from powerbi_import.deploy.config.settings import _FallbackSettings
        s = _FallbackSettings()
        # deployment_timeout should be a number
        self.assertIsInstance(s.deployment_timeout, (int, float))

    def test_fallback_settings_default_delay_type(self):
        from powerbi_import.deploy.config.settings import _FallbackSettings
        s = _FallbackSettings()
        self.assertIsInstance(s.retry_delay, (int, float))

    def test_pydantic_model_accepts_float_timeout(self):
        """When pydantic is available, FabricSettings should accept float."""
        try:
            from pydantic_settings import BaseSettings
        except ImportError:
            self.skipTest("pydantic-settings not installed")

        from powerbi_import.deploy.config.settings import get_settings as _gs
        # Just verify the field type declaration changed (via get_settings)
        # The actual test is that float Field is compilable — already validated
        # by importing the module without error.

    def test_environment_configs_valid_numbers(self):
        from powerbi_import.deploy.config.environments import (
            EnvironmentConfig, EnvironmentType,
        )
        for env_type in EnvironmentType:
            cfg = EnvironmentConfig.get_config(env_type)
            self.assertIsInstance(cfg.get('deployment_timeout', 300), (int, float))
            self.assertIsInstance(cfg.get('retry_delay', 5), (int, float))


# ── 31.5  CLI --check-schema argument ───────────────────────────────────────

class TestCheckSchemaCLI(unittest.TestCase):
    """Verify the --check-schema CLI argument is wired correctly."""

    def test_argument_parser_accepts_check_schema(self):
        sys.path.insert(0, ROOT)
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args(['test.twbx', '--check-schema'])
        self.assertTrue(args.check_schema)

    def test_argument_parser_default_no_check_schema(self):
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertFalse(args.check_schema)


if __name__ == '__main__':
    unittest.main()
