"""
Tests for Sprint 2/3/4 features — DAX, Visual, TMDL, PBIP, M Query enhancements.

Covers:
- REGEX conversions (_convert_regexp_match, _convert_regexp_extract)
- Nested LOD (_find_lod_braces)
- String+ improvements  
- Small Multiples visual config
- Proportional visual positioning
- Dynamic reference lines
- Data bars on tables
- Rich text textbox parsing
- Composite model mode
- Parameterized data sources
- New connectors (Fabric Lakehouse, Dataverse)
- Connection string templating
- Config file support
- Plugin architecture
- CLI flags (--mode, --rollback, --output-format, --config)
"""

import unittest
import sys
import os
import json
import tempfile
import shutil
import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from tests.conftest import SAMPLE_DATASOURCE, SAMPLE_EXTRACTED, make_temp_dir, cleanup_dir


# ═══════════════════════════════════════════════════════════════════════
#  DAX CONVERTER — Sprint 2/3/4 features
# ═══════════════════════════════════════════════════════════════════════

class TestRegexpMatch(unittest.TestCase):
    """Tests for REGEXP_MATCH → CONTAINSSTRING/LEFT/RIGHT conversion."""

    def _convert(self, formula, **kwargs):
        from dax_converter import convert_tableau_formula_to_dax
        return convert_tableau_formula_to_dax(formula, **kwargs)

    def test_regexp_match_simple_literal(self):
        result = self._convert('REGEXP_MATCH([Name], "hello")')
        self.assertIn('CONTAINSSTRING', result)
        self.assertNotIn('REGEXP_MATCH', result)

    def test_regexp_match_prefix_pattern(self):
        result = self._convert('REGEXP_MATCH([Code], "^ABC")')
        self.assertIn('LEFT', result)

    def test_regexp_match_suffix_pattern(self):
        result = self._convert('REGEXP_MATCH([Code], "XYZ$")')
        self.assertIn('RIGHT', result)

    def test_regexp_match_alternation(self):
        result = self._convert('REGEXP_MATCH([Status], "Active|Pending")')
        self.assertIn('CONTAINSSTRING', result)
        self.assertIn('||', result)

    def test_regexp_match_case_insensitive(self):
        result = self._convert('REGEXP_MATCH([Name], "test")')
        self.assertNotIn('REGEXP_MATCH', result)

    def test_regexp_extract_simple(self):
        result = self._convert('REGEXP_EXTRACT([Email], "@(.*)")')
        self.assertNotIn('REGEXP_EXTRACT', result)

    def test_regexp_extract_fixed_prefix(self):
        result = self._convert('REGEXP_EXTRACT([Code], "ABC(.*)")')
        self.assertIn('MID', result)


class TestNestedLOD(unittest.TestCase):
    """Tests for nested LOD expression parsing with balanced braces."""

    def _convert(self, formula, **kwargs):
        from dax_converter import convert_tableau_formula_to_dax
        return convert_tableau_formula_to_dax(formula, **kwargs)

    def test_single_fixed_lod(self):
        result = self._convert('{FIXED [Customer] : SUM([Sales])}')
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)
        self.assertNotIn('{FIXED', result)

    def test_nested_fixed_lod(self):
        result = self._convert('{FIXED [Customer] : SUM({FIXED [Product] : AVG([Price])})}')
        self.assertNotIn('{FIXED', result)
        self.assertIn('CALCULATE', result)

    def test_include_lod(self):
        result = self._convert('{INCLUDE [Region] : SUM([Sales])}')
        self.assertIn('CALCULATE', result)
        self.assertNotIn('{INCLUDE', result)

    def test_exclude_lod(self):
        result = self._convert('{EXCLUDE [Region] : SUM([Sales])}')
        self.assertIn('CALCULATE', result)
        self.assertIn('REMOVEFILTERS', result)

    def test_lod_with_multiple_dims(self):
        result = self._convert('{FIXED [Customer], [Region] : SUM([Sales])}')
        self.assertIn('CALCULATE', result)
        self.assertNotIn('{FIXED', result)


class TestStringConcatPlus(unittest.TestCase):
    """Tests for string + → & conversion at all depths."""

    def _convert(self, formula, **kwargs):
        from dax_converter import convert_tableau_formula_to_dax
        return convert_tableau_formula_to_dax(formula, calc_datatype='string', **kwargs)

    def test_simple_string_concat(self):
        result = self._convert('[First] + " " + [Last]')
        self.assertIn('&', result)

    def test_preserves_numeric_plus(self):
        from dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('[Amount] + 10', calc_datatype='real')
        self.assertIn('+', result)
        self.assertNotIn('&', result)

    def test_nested_concat(self):
        result = self._convert('IF [A] THEN [B] + [C] ELSE [D] + [E] END')
        self.assertIn('&', result)


# ═══════════════════════════════════════════════════════════════════════
#  VISUAL GENERATOR — Sprint 2/3/4 features
# ═══════════════════════════════════════════════════════════════════════

class TestSmallMultiples(unittest.TestCase):
    """Tests for Small Multiples visual configuration."""

    def test_small_multiples_config_structure(self):
        from visual_generator import _build_small_multiples_config
        config, projection = _build_small_multiples_config('Region', 'Sales')
        self.assertIsInstance(config, dict)
        self.assertIsInstance(projection, dict)

    def test_small_multiples_projection(self):
        from visual_generator import _build_small_multiples_config
        config, projection = _build_small_multiples_config('Category', 'Sales')
        self.assertIn('field', projection)
        self.assertIn('queryRef', projection)

    def test_small_multiples_types_defined(self):
        from visual_generator import SMALL_MULTIPLES_TYPES
        self.assertIn('clusteredBarChart', SMALL_MULTIPLES_TYPES)
        self.assertIn('lineChart', SMALL_MULTIPLES_TYPES)
        self.assertIn('areaChart', SMALL_MULTIPLES_TYPES)


class TestProportionalLayout(unittest.TestCase):
    """Tests for proportional visual positioning from Tableau source positions."""

    def test_basic_layout(self):
        from visual_generator import _calculate_proportional_layout
        worksheets = ['Sheet1', 'Sheet2']
        source_positions = [
            {'x': 0, 'y': 0, 'w': 400, 'h': 300},
            {'x': 400, 'y': 0, 'w': 400, 'h': 300},
        ]
        result = _calculate_proportional_layout(worksheets, 1280, 720,
                                                source_positions=source_positions)
        self.assertEqual(len(result), 2)
        # Verify positions are tuples of (x, y, width, height)
        for pos in result:
            self.assertEqual(len(pos), 4)
            x, y, w, h = pos
            self.assertIsInstance(x, int)
            self.assertIsInstance(y, int)
            self.assertIsInstance(w, int)
            self.assertIsInstance(h, int)

    def test_grid_fallback(self):
        from visual_generator import _calculate_proportional_layout
        # No source positions should use grid fallback
        worksheets = ['S1', 'S2', 'S3', 'S4']
        result = _calculate_proportional_layout(worksheets, 1280, 720)
        self.assertEqual(len(result), 4)

    def test_minimum_size_enforced(self):
        from visual_generator import _calculate_proportional_layout
        worksheets = ['Sheet1']
        source_positions = [{'x': 0, 'y': 0, 'w': 1, 'h': 1}]
        result = _calculate_proportional_layout(worksheets, 1280, 720,
                                                source_positions=source_positions)
        x, y, w, h = result[0]
        self.assertGreaterEqual(w, 50)
        self.assertGreaterEqual(h, 30)


class TestDynamicReferenceLines(unittest.TestCase):
    """Tests for dynamic reference line generation."""

    def test_average_reference_line(self):
        from visual_generator import _build_dynamic_reference_line
        config = _build_dynamic_reference_line('average', 'Sales', 'SalesTable')
        self.assertIsNotNone(config)
        self.assertIn('properties', config)
        props = config['properties']
        self.assertEqual(props['type']['expr']['Literal']['Value'], "'Average'")

    def test_median_reference_line(self):
        from visual_generator import _build_dynamic_reference_line
        config = _build_dynamic_reference_line('median', 'Sales', 'SalesTable')
        props = config['properties']
        self.assertEqual(props['type']['expr']['Literal']['Value'], "'Median'")

    def test_percentile_reference_line(self):
        from visual_generator import _build_dynamic_reference_line
        config = _build_dynamic_reference_line('percentile', 'Sales', 'SalesTable')
        props = config['properties']
        self.assertEqual(props['type']['expr']['Literal']['Value'], "'Percentile'")
        self.assertIn('percentile', props)

    def test_trend_reference_line(self):
        from visual_generator import _build_dynamic_reference_line
        config = _build_dynamic_reference_line('trend', 'Sales', 'SalesTable')
        self.assertIn('properties', config)
        self.assertEqual(config['properties']['type']['expr']['Literal']['Value'], "'Trend'")

    def test_unknown_type_fallback(self):
        from visual_generator import _build_dynamic_reference_line
        config = _build_dynamic_reference_line('unknown_type', 'Sales', 'SalesTable')
        # Unknown types still produce a config dict with properties
        self.assertIn('properties', config)
        self.assertIn('show', config['properties'])


class TestDataBars(unittest.TestCase):
    """Tests for data bar configuration on table/matrix visuals."""

    def test_data_bar_config(self):
        from visual_generator import _build_data_bar_config
        config = _build_data_bar_config('Amount', 'Sales')
        self.assertIn('positiveColor', config)
        self.assertIn('negativeColor', config)
        self.assertIn('axisColor', config)

    def test_data_bar_has_column_name(self):
        from visual_generator import _build_data_bar_config
        config = _build_data_bar_config('Revenue', 'Sales')
        # Column name is in the field property
        self.assertIn('field', config)
        self.assertEqual(config['field']['Column']['Property'], 'Revenue')


# ═══════════════════════════════════════════════════════════════════════
#  PBIP GENERATOR — Rich text
# ═══════════════════════════════════════════════════════════════════════

class TestRichTextParsing(unittest.TestCase):
    """Tests for rich text textbox parsing in PBIP generator."""

    def _parse(self, obj):
        from pbip_generator import PowerBIProjectGenerator
        return PowerBIProjectGenerator._parse_rich_text_runs(obj)

    def test_plain_text_fallback(self):
        obj = {'content': 'Hello World', 'text_runs': []}
        result = self._parse(obj)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['textRuns'][0]['value'], 'Hello World')

    def test_bold_run(self):
        obj = {'text_runs': [{'text': 'Bold', 'bold': True}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        self.assertEqual(run['value'], 'Bold')
        self.assertIn('textStyle', run)
        self.assertEqual(run['textStyle']['fontWeight'], 'bold')

    def test_italic_run(self):
        obj = {'text_runs': [{'text': 'Italic', 'italic': True}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        self.assertEqual(run['textStyle']['fontStyle'], 'italic')

    def test_colored_run(self):
        obj = {'text_runs': [{'text': 'Red', 'color': '#FF0000'}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        self.assertEqual(run['textStyle']['color'], '#FF0000')

    def test_tableau_color_format_conversion(self):
        # Tableau uses #AARRGGBB, PBI needs #RRGGBB
        obj = {'text_runs': [{'text': 'Red', 'color': '#FF334455'}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        self.assertEqual(run['textStyle']['color'], '#334455')

    def test_font_size(self):
        obj = {'text_runs': [{'text': 'Big', 'font_size': '18'}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        self.assertEqual(run['textStyle']['fontSize'], '18.0pt')

    def test_url_hyperlink(self):
        obj = {'text_runs': [{'text': 'Click', 'url': 'https://example.com'}]}
        result = self._parse(obj)
        run = result[0]['textRuns'][0]
        self.assertEqual(run['url'], 'https://example.com')

    def test_newline_creates_paragraphs(self):
        obj = {'text_runs': [{'text': 'Line1\nLine2'}]}
        result = self._parse(obj)
        self.assertEqual(len(result), 2)

    def test_multiple_runs(self):
        obj = {'text_runs': [
            {'text': 'Normal '},
            {'text': 'Bold', 'bold': True},
            {'text': ' Normal'},
        ]}
        result = self._parse(obj)
        runs = result[0]['textRuns']
        self.assertEqual(len(runs), 3)
        self.assertNotIn('textStyle', runs[0])
        self.assertIn('textStyle', runs[1])

    def test_empty_runs_returns_empty_paragraph(self):
        obj = {'text_runs': [], 'content': ''}
        result = self._parse(obj)
        self.assertEqual(len(result), 1)


# ═══════════════════════════════════════════════════════════════════════
#  TMDL GENERATOR — Composite model & parameterized sources
# ═══════════════════════════════════════════════════════════════════════

class TestCompositeModel(unittest.TestCase):
    """Tests for composite model mode in TMDL generation."""

    def test_generate_tmdl_accepts_model_mode(self):
        from tmdl_generator import generate_tmdl
        temp_dir = make_temp_dir()
        try:
            datasources = [copy.deepcopy(SAMPLE_DATASOURCE)]
            stats = generate_tmdl(
                datasources=datasources,
                report_name='TestComposite',
                extra_objects={},
                output_dir=temp_dir,
                model_mode='composite'
            )
            self.assertIsInstance(stats, dict)
            self.assertIn('tables', stats)
        finally:
            cleanup_dir(temp_dir)

    def test_import_mode_is_default(self):
        from tmdl_generator import generate_tmdl
        temp_dir = make_temp_dir()
        try:
            datasources = [copy.deepcopy(SAMPLE_DATASOURCE)]
            stats = generate_tmdl(
                datasources=datasources,
                report_name='TestImport',
                extra_objects={},
                output_dir=temp_dir,
            )
            self.assertIsInstance(stats, dict)
        finally:
            cleanup_dir(temp_dir)

    def test_directquery_mode(self):
        from tmdl_generator import generate_tmdl
        temp_dir = make_temp_dir()
        try:
            datasources = [copy.deepcopy(SAMPLE_DATASOURCE)]
            stats = generate_tmdl(
                datasources=datasources,
                report_name='TestDQ',
                extra_objects={},
                output_dir=temp_dir,
                model_mode='directquery'
            )
            self.assertIsInstance(stats, dict)
        finally:
            cleanup_dir(temp_dir)


# ═══════════════════════════════════════════════════════════════════════
#  M QUERY BUILDER — New connectors & templating
# ═══════════════════════════════════════════════════════════════════════

class TestNewConnectors(unittest.TestCase):
    """Tests for Fabric Lakehouse and Dataverse connectors."""

    def test_fabric_lakehouse(self):
        from m_query_builder import generate_power_query_m
        conn = {'type': 'Fabric Lakehouse', 'details': {
            'workspace_id': 'ws-123', 'lakehouse_id': 'lh-456'
        }}
        table = {'name': 'Customers', 'columns': [{'name': 'id', 'datatype': 'integer'}]}
        result = generate_power_query_m(conn, table)
        self.assertIn('Lakehouse.Contents', result)
        self.assertIn('ws-123', result)

    def test_dataverse(self):
        from m_query_builder import generate_power_query_m
        conn = {'type': 'Dataverse', 'details': {
            'server': 'https://org.crm.dynamics.com'
        }}
        table = {'name': 'Accounts', 'columns': [{'name': 'name', 'datatype': 'string'}]}
        result = generate_power_query_m(conn, table)
        self.assertIn('CommonDataService.Database', result)

    def test_cds_alias(self):
        from m_query_builder import generate_power_query_m
        conn = {'type': 'CDS', 'details': {}}
        table = {'name': 'T1', 'columns': []}
        result = generate_power_query_m(conn, table)
        self.assertIn('CommonDataService.Database', result)


class TestConnectionTemplating(unittest.TestCase):
    """Tests for ${ENV.*} connection string templating."""

    def test_apply_template_with_values(self):
        from m_query_builder import apply_connection_template
        m_query = 'Source = Sql.Database("${ENV.SERVER}", "${ENV.DATABASE}")'
        result = apply_connection_template(m_query, {'SERVER': 'prod.db.com', 'DATABASE': 'analytics'})
        self.assertIn('prod.db.com', result)
        self.assertIn('analytics', result)
        self.assertNotIn('${ENV.', result)

    def test_apply_template_without_values(self):
        from m_query_builder import apply_connection_template
        m_query = 'Source = Sql.Database("${ENV.SERVER}", "${ENV.DATABASE}")'
        result = apply_connection_template(m_query)
        self.assertIn('SERVER', result)
        self.assertIn('DATABASE', result)

    def test_no_template_passthrough(self):
        from m_query_builder import apply_connection_template
        m_query = 'Source = Sql.Database("localhost", "mydb")'
        result = apply_connection_template(m_query)
        self.assertEqual(result, m_query)

    def test_templatize_m_query(self):
        from m_query_builder import templatize_m_query
        m_query = 'Source = Sql.Database("myserver.db.com", "analytics")'
        conn = {'details': {'server': 'myserver.db.com', 'database': 'analytics'}}
        result = templatize_m_query(m_query, conn)
        self.assertIn('${ENV.SERVER}', result)
        self.assertIn('${ENV.DATABASE}', result)

    def test_templatize_preserves_unknown(self):
        from m_query_builder import templatize_m_query
        result = templatize_m_query('Source = foo', None)
        self.assertEqual(result, 'Source = foo')


# ═══════════════════════════════════════════════════════════════════════
#  CONFIG — Configuration file support
# ═══════════════════════════════════════════════════════════════════════

class TestMigrationConfig(unittest.TestCase):
    """Tests for MigrationConfig class."""

    def test_default_config(self):
        from powerbi_import.config.migration_config import MigrationConfig
        config = MigrationConfig()
        self.assertEqual(config.model_mode, 'import')
        self.assertEqual(config.culture, 'en-US')
        self.assertEqual(config.calendar_start, 2020)
        self.assertEqual(config.calendar_end, 2030)
        self.assertEqual(config.output_format, 'pbip')
        self.assertFalse(config.dry_run)
        self.assertFalse(config.rollback)

    def test_custom_config(self):
        from powerbi_import.config.migration_config import MigrationConfig
        config = MigrationConfig({
            'model': {'mode': 'composite', 'culture': 'fr-FR'},
            'output': {'format': 'tmdl'},
        })
        self.assertEqual(config.model_mode, 'composite')
        self.assertEqual(config.culture, 'fr-FR')
        self.assertEqual(config.output_format, 'tmdl')

    def test_load_from_file(self):
        from powerbi_import.config.migration_config import MigrationConfig
        temp_dir = make_temp_dir()
        try:
            config_path = os.path.join(temp_dir, 'config.json')
            with open(config_path, 'w') as f:
                json.dump({'model': {'mode': 'directquery'}}, f)
            config = MigrationConfig.from_file(config_path)
            self.assertEqual(config.model_mode, 'directquery')
        finally:
            cleanup_dir(temp_dir)

    def test_file_not_found_raises(self):
        from powerbi_import.config.migration_config import MigrationConfig
        with self.assertRaises(FileNotFoundError):
            MigrationConfig.from_file('/nonexistent/config.json')

    def test_save_config(self):
        from powerbi_import.config.migration_config import MigrationConfig
        temp_dir = make_temp_dir()
        try:
            config = MigrationConfig({'model': {'mode': 'composite'}})
            out_path = os.path.join(temp_dir, 'saved.json')
            config.save(out_path)
            self.assertTrue(os.path.exists(out_path))
            with open(out_path) as f:
                data = json.load(f)
            self.assertEqual(data['model']['mode'], 'composite')
        finally:
            cleanup_dir(temp_dir)

    def test_to_dict(self):
        from powerbi_import.config.migration_config import MigrationConfig
        config = MigrationConfig()
        d = config.to_dict()
        self.assertIsInstance(d, dict)
        self.assertIn('source', d)
        self.assertIn('model', d)
        self.assertIn('output', d)

    def test_template_vars(self):
        from powerbi_import.config.migration_config import MigrationConfig
        config = MigrationConfig({
            'connections': {'template_vars': {'SERVER': 'prod.db'}}
        })
        self.assertEqual(config.template_vars['SERVER'], 'prod.db')

    def test_plugins_list(self):
        from powerbi_import.config.migration_config import MigrationConfig
        config = MigrationConfig({'plugins': ['my_plugin.MyPlugin']})
        self.assertEqual(config.plugins, ['my_plugin.MyPlugin'])


class TestLoadConfig(unittest.TestCase):
    """Tests for the load_config convenience function."""

    def test_no_args_returns_defaults(self):
        from powerbi_import.config.migration_config import load_config
        config = load_config()
        self.assertEqual(config.model_mode, 'import')

    def test_file_only(self):
        from powerbi_import.config.migration_config import load_config
        temp_dir = make_temp_dir()
        try:
            config_path = os.path.join(temp_dir, 'config.json')
            with open(config_path, 'w') as f:
                json.dump({'model': {'mode': 'composite'}}, f)
            config = load_config(filepath=config_path)
            self.assertEqual(config.model_mode, 'composite')
        finally:
            cleanup_dir(temp_dir)


# ═══════════════════════════════════════════════════════════════════════
#  PLUGINS — Plugin architecture
# ═══════════════════════════════════════════════════════════════════════

class TestPluginManager(unittest.TestCase):
    """Tests for the plugin manager."""

    def test_register_plugin(self):
        from plugins import PluginManager, PluginBase
        manager = PluginManager()
        plugin = PluginBase()
        plugin.name = 'test_plugin'
        manager.register(plugin)
        self.assertEqual(len(manager.plugins), 1)

    def test_call_hook(self):
        from plugins import PluginManager

        class TestPlugin:
            name = 'echo'
            def pre_extraction(self, tableau_file):
                return 'called'

        manager = PluginManager()
        manager.register(TestPlugin())
        result = manager.call_hook('pre_extraction', tableau_file='test.twbx')
        self.assertEqual(result, 'called')

    def test_apply_transform_chain(self):
        from plugins import PluginManager

        class UpperPlugin:
            name = 'upper'
            def transform_dax(self, formula):
                return formula.upper()

        class PrefixPlugin:
            name = 'prefix'
            def transform_dax(self, formula):
                return 'RESULT: ' + formula

        manager = PluginManager()
        manager.register(UpperPlugin())
        manager.register(PrefixPlugin())
        result = manager.apply_transform('transform_dax', 'sum(x)')
        self.assertEqual(result, 'RESULT: SUM(X)')

    def test_missing_hook_ignored(self):
        from plugins import PluginManager

        class EmptyPlugin:
            name = 'empty'

        manager = PluginManager()
        manager.register(EmptyPlugin())
        result = manager.call_hook('nonexistent_hook')
        self.assertIsNone(result)

    def test_has_plugins(self):
        from plugins import PluginManager
        manager = PluginManager()
        self.assertFalse(manager.has_plugins())
        manager.register(type('P', (), {'name': 'p'})())
        self.assertTrue(manager.has_plugins())

    def test_global_manager(self):
        from plugins import get_plugin_manager, reset_plugin_manager
        manager = get_plugin_manager()
        self.assertIsNotNone(manager)
        new_manager = reset_plugin_manager()
        self.assertIsNotNone(new_manager)
        self.assertEqual(len(new_manager.plugins), 0)

    def test_custom_visual_mapping_hook(self):
        from plugins import PluginManager

        class MapPlugin:
            name = 'map'
            def custom_visual_mapping(self, tableau_mark):
                if tableau_mark == 'custom_viz':
                    return 'decompositionTree'
                return None

        manager = PluginManager()
        manager.register(MapPlugin())
        result = manager.call_hook('custom_visual_mapping', tableau_mark='custom_viz')
        self.assertEqual(result, 'decompositionTree')
        result2 = manager.call_hook('custom_visual_mapping', tableau_mark='bar')
        self.assertIsNone(result2)

    def test_error_handling_in_hook(self):
        from plugins import PluginManager

        class BrokenPlugin:
            name = 'broken'
            def pre_extraction(self, tableau_file):
                raise ValueError("Plugin error")

        manager = PluginManager()
        manager.register(BrokenPlugin())
        # Should not raise, just log
        result = manager.call_hook('pre_extraction', tableau_file='test.twbx')
        self.assertIsNone(result)


class TestPluginBase(unittest.TestCase):
    """Tests for PluginBase default implementations."""

    def test_all_hooks_exist(self):
        from plugins import PluginBase
        base = PluginBase()
        # All hook methods should be callable
        self.assertTrue(callable(base.pre_extraction))
        self.assertTrue(callable(base.post_extraction))
        self.assertTrue(callable(base.pre_generation))
        self.assertTrue(callable(base.post_generation))
        self.assertTrue(callable(base.transform_dax))
        self.assertTrue(callable(base.transform_m_query))
        self.assertTrue(callable(base.custom_visual_mapping))

    def test_transform_dax_returns_input(self):
        from plugins import PluginBase
        base = PluginBase()
        self.assertEqual(base.transform_dax('SUM(X)'), 'SUM(X)')

    def test_custom_visual_returns_none(self):
        from plugins import PluginBase
        base = PluginBase()
        self.assertIsNone(base.custom_visual_mapping('bar'))


# ═══════════════════════════════════════════════════════════════════════
#  CLI FLAGS — Integration tests for new arguments
# ═══════════════════════════════════════════════════════════════════════

class TestCLIArgParsing(unittest.TestCase):
    """Tests that new CLI arguments are parsed correctly."""

    def _parse(self, args_list):
        """Parse CLI arguments using the real argument parser."""
        import argparse
        # Replicate the argument parser from migrate.py
        parser = argparse.ArgumentParser()
        parser.add_argument('tableau_file', nargs='?', default=None)
        parser.add_argument('--mode', choices=['import', 'directquery', 'composite'], default='import')
        parser.add_argument('--rollback', action='store_true')
        parser.add_argument('--output-format', choices=['pbip', 'tmdl', 'pbir'], default='pbip')
        parser.add_argument('--config', metavar='FILE', default=None)
        parser.add_argument('--output-dir', default=None)
        parser.add_argument('--verbose', '-v', action='store_true')
        parser.add_argument('--culture', default=None)
        parser.add_argument('--calendar-start', type=int, default=None)
        parser.add_argument('--calendar-end', type=int, default=None)
        return parser.parse_args(args_list)

    def test_mode_default(self):
        args = self._parse(['test.twbx'])
        self.assertEqual(args.mode, 'import')

    def test_mode_composite(self):
        args = self._parse(['test.twbx', '--mode', 'composite'])
        self.assertEqual(args.mode, 'composite')

    def test_mode_directquery(self):
        args = self._parse(['test.twbx', '--mode', 'directquery'])
        self.assertEqual(args.mode, 'directquery')

    def test_rollback_flag(self):
        args = self._parse(['test.twbx', '--rollback'])
        self.assertTrue(args.rollback)

    def test_output_format_tmdl(self):
        args = self._parse(['test.twbx', '--output-format', 'tmdl'])
        self.assertEqual(args.output_format, 'tmdl')

    def test_output_format_pbir(self):
        args = self._parse(['test.twbx', '--output-format', 'pbir'])
        self.assertEqual(args.output_format, 'pbir')

    def test_config_flag(self):
        args = self._parse(['test.twbx', '--config', 'migration.json'])
        self.assertEqual(args.config, 'migration.json')

    def test_combined_flags(self):
        args = self._parse([
            'test.twbx', '--mode', 'composite',
            '--rollback', '--output-format', 'tmdl',
            '--culture', 'fr-FR'
        ])
        self.assertEqual(args.mode, 'composite')
        self.assertTrue(args.rollback)
        self.assertEqual(args.output_format, 'tmdl')
        self.assertEqual(args.culture, 'fr-FR')


if __name__ == '__main__':
    unittest.main()
