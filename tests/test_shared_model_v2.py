"""Tests for shared semantic model v2 features:
- Merge config save/load
- Visual field validation
- Column lineage annotations
- Measure expression risk analyzer
- RLS role consolidation
- Cross-report navigation
- Plugin merge hooks
- Fabric deployment orchestration
"""

import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.shared_model import (
    MergeAssessment, MergeCandidate, MeasureConflict, TableFingerprint,
    assess_merge, merge_semantic_models, build_field_mapping,
    validate_thin_report_fields,
    build_column_lineage, generate_lineage_annotations,
    analyze_measure_risk, MeasureRiskAssessment,
    consolidate_rls_roles, merge_rls_roles, RLSConsolidation,
    build_cross_report_navigation,
)
from powerbi_import.merge_config import (
    save_merge_config, load_merge_config, apply_merge_config,
    get_measure_action,
)


# ═══════════════════════════════════════════════════════════════════
#  Test data factories
# ═══════════════════════════════════════════════════════════════════

def _make_datasource(name, conn_type, server, database, tables, calcs=None, rels=None):
    return {
        'name': name,
        'connection': {'type': conn_type, 'details': {'server': server, 'database': database}},
        'tables': tables,
        'calculations': calcs or [],
        'relationships': rels or [],
    }


def _make_table(name, columns, ttype='table'):
    return {
        'name': name, 'type': ttype,
        'columns': [{'name': c, 'datatype': 'string'} for c in columns],
    }


def _make_measure(caption, formula):
    return {'caption': caption, 'name': caption, 'formula': formula, 'role': 'measure'}


def _make_wb(datasources, worksheets=None, user_filters=None, params=None):
    return {
        'datasources': datasources,
        'worksheets': worksheets or [],
        'dashboards': [], 'calculations': [],
        'parameters': params or [],
        'filters': [], 'stories': [], 'actions': [],
        'sets': [], 'groups': [], 'bins': [],
        'hierarchies': [], 'sort_orders': [], 'aliases': {},
        'custom_sql': [],
        'user_filters': user_filters or [],
    }


def _two_workbooks_with_conflict():
    """Two workbooks sharing Orders table with measure conflict."""
    wb_a = _make_wb([_make_datasource(
        'DS_A', 'sqlserver', 'srv1', 'db1',
        tables=[_make_table('[dbo].[Orders]', ['OrderID', 'Amount', 'Date'])],
        calcs=[_make_measure('Total Sales', 'SUM([Amount])'),
               _make_measure('Order Count', 'COUNT([OrderID])')],
    )], worksheets=[{
        'name': 'Sales Overview',
        'columns': [{'name': 'Total Sales'}, {'name': 'Amount'}],
        'filters': [{'field': 'Date'}],
        'mark_encoding': {'color': {'field': 'Total Sales'}},
    }])

    wb_b = _make_wb([_make_datasource(
        'DS_B', 'sqlserver', 'srv1', 'db1',
        tables=[_make_table('[dbo].[Orders]', ['OrderID', 'Amount', 'Date', 'Region'])],
        calcs=[_make_measure('Total Sales', 'SUMX(Orders, [Qty] * [Price])'),
               _make_measure('Avg Price', 'AVERAGE([Price])')],
    )], worksheets=[{
        'name': 'Product Detail',
        'columns': [{'name': 'Total Sales'}, {'name': 'Region'}],
        'filters': [],
        'mark_encoding': {},
    }])

    return [wb_a, wb_b], ['SalesOverview', 'ProductDetail']


# ═══════════════════════════════════════════════════════════════════
#  Merge Config Tests
# ═══════════════════════════════════════════════════════════════════

class TestMergeConfig(unittest.TestCase):
    """Tests for merge config save/load/apply."""

    def setUp(self):
        self.all_extracted, self.names = _two_workbooks_with_conflict()
        self.assessment = assess_merge(self.all_extracted, self.names)
        self.tmpdir = tempfile.mkdtemp()

    def test_save_config_creates_file(self):
        path = os.path.join(self.tmpdir, 'cfg.json')
        save_merge_config(self.assessment, self.names, path)
        self.assertTrue(os.path.isfile(path))

    def test_save_config_valid_json(self):
        path = os.path.join(self.tmpdir, 'cfg.json')
        save_merge_config(self.assessment, self.names, path)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data['version'], '1.0')
        self.assertEqual(data['workbooks'], self.names)

    def test_save_config_has_table_decisions(self):
        path = os.path.join(self.tmpdir, 'cfg.json')
        save_merge_config(self.assessment, self.names, path)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn('table_decisions', data)
        self.assertTrue(len(data['table_decisions']) > 0)

    def test_save_config_has_measure_decisions(self):
        path = os.path.join(self.tmpdir, 'cfg.json')
        save_merge_config(self.assessment, self.names, path)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn('measure_decisions', data)
        self.assertTrue(len(data['measure_decisions']) > 0)

    def test_load_config_roundtrip(self):
        path = os.path.join(self.tmpdir, 'cfg.json')
        save_merge_config(self.assessment, self.names, path)
        config = load_merge_config(path)
        self.assertEqual(config['workbooks'], self.names)

    def test_load_config_wrong_version(self):
        path = os.path.join(self.tmpdir, 'cfg.json')
        with open(path, 'w') as f:
            json.dump({'version': '99.0'}, f)
        with self.assertRaises(ValueError):
            load_merge_config(path)

    def test_apply_config_skip_table(self):
        path = os.path.join(self.tmpdir, 'cfg.json')
        save_merge_config(self.assessment, self.names, path)
        config = load_merge_config(path)
        # Mark first table decision as skip
        if config['table_decisions']:
            config['table_decisions'][0]['action'] = 'skip'
        original_count = len(self.assessment.merge_candidates)
        assessment_copy = copy.deepcopy(self.assessment)
        apply_merge_config(assessment_copy, config)
        self.assertLessEqual(len(assessment_copy.merge_candidates), original_count)

    def test_apply_config_force_merge(self):
        assessment = copy.deepcopy(self.assessment)
        assessment.recommendation = 'separate'
        config = {'version': '1.0', 'options': {'force_merge': True},
                  'table_decisions': [], 'measure_decisions': [],
                  'parameter_decisions': []}
        apply_merge_config(assessment, config)
        self.assertEqual(assessment.recommendation, 'merge')

    def test_get_measure_action_default(self):
        config = {'measure_decisions': []}
        self.assertEqual(get_measure_action(config, 'Any'), 'namespace')

    def test_get_measure_action_configured(self):
        config = {'measure_decisions': [
            {'measure_name': 'Total', 'action': 'keep_first'}
        ]}
        self.assertEqual(get_measure_action(config, 'Total'), 'keep_first')

    def test_save_config_has_options(self):
        path = os.path.join(self.tmpdir, 'cfg.json')
        save_merge_config(self.assessment, self.names, path)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn('options', data)
        self.assertIn('column_overlap_threshold', data['options'])


# ═══════════════════════════════════════════════════════════════════
#  Visual Field Validation Tests
# ═══════════════════════════════════════════════════════════════════

class TestVisualFieldValidation(unittest.TestCase):
    """Tests for validate_thin_report_fields."""

    def setUp(self):
        self.all_extracted, self.names = _two_workbooks_with_conflict()
        self.assessment = assess_merge(self.all_extracted, self.names)
        self.merged = merge_semantic_models(self.all_extracted, self.assessment, 'Test')

    def test_valid_fields_no_issues(self):
        wb = _make_wb([_make_datasource(
            'DS', 'sqlserver', 'srv1', 'db1',
            tables=[_make_table('[dbo].[Orders]', ['Amount'])],
        )], worksheets=[{
            'name': 'Sheet1',
            'columns': [{'name': 'Amount'}],
            'filters': [],
            'mark_encoding': {},
        }])
        issues = validate_thin_report_fields(wb, self.merged)
        self.assertEqual(len(issues), 0)

    def test_orphaned_column_detected(self):
        wb = _make_wb([_make_datasource(
            'DS', 'sqlserver', 'srv1', 'db1',
            tables=[_make_table('[dbo].[Orders]', ['Amount'])],
        )], worksheets=[{
            'name': 'Sheet1',
            'columns': [{'name': 'NonexistentField'}],
            'filters': [],
            'mark_encoding': {},
        }])
        issues = validate_thin_report_fields(wb, self.merged)
        self.assertTrue(any(i['issue'] == 'orphaned_field' for i in issues))

    def test_orphaned_filter_detected(self):
        wb = _make_wb([_make_datasource(
            'DS', 'sqlserver', 'srv1', 'db1',
            tables=[_make_table('[dbo].[Orders]', ['Amount'])],
        )], worksheets=[{
            'name': 'Sheet1',
            'columns': [],
            'filters': [{'field': 'GhostField'}],
            'mark_encoding': {},
        }])
        issues = validate_thin_report_fields(wb, self.merged)
        self.assertTrue(any(i['issue'] == 'orphaned_filter' for i in issues))

    def test_orphaned_encoding_detected(self):
        wb = _make_wb([_make_datasource(
            'DS', 'sqlserver', 'srv1', 'db1',
            tables=[_make_table('[dbo].[Orders]', ['Amount'])],
        )], worksheets=[{
            'name': 'Sheet1',
            'columns': [],
            'filters': [],
            'mark_encoding': {'size': {'field': 'MissingMeasure'}},
        }])
        issues = validate_thin_report_fields(wb, self.merged)
        self.assertTrue(any(i['issue'] == 'orphaned_encoding' for i in issues))

    def test_field_mapping_resolves_issue(self):
        """If field_mapping maps orphaned field to a valid one, no issue."""
        wb = _make_wb([_make_datasource(
            'DS', 'sqlserver', 'srv1', 'db1',
            tables=[_make_table('[dbo].[Orders]', ['Amount'])],
        )], worksheets=[{
            'name': 'Sheet1',
            'columns': [{'name': 'Total Sales'}],
            'filters': [],
            'mark_encoding': {},
        }])
        mapping = build_field_mapping(self.assessment, 'SalesOverview')
        issues = validate_thin_report_fields(wb, self.merged, mapping)
        # 'Total Sales' should be remapped to 'Total Sales (SalesOverview)' which exists
        total_issues = [i for i in issues if i['field'] == 'Total Sales']
        self.assertEqual(len(total_issues), 0)

    def test_empty_worksheet_no_crash(self):
        wb = _make_wb([], worksheets=[{
            'name': 'Empty', 'columns': [], 'filters': [], 'mark_encoding': {},
        }])
        issues = validate_thin_report_fields(wb, self.merged)
        self.assertIsInstance(issues, list)


# ═══════════════════════════════════════════════════════════════════
#  Column Lineage Tests
# ═══════════════════════════════════════════════════════════════════

class TestColumnLineage(unittest.TestCase):
    """Tests for build_column_lineage and generate_lineage_annotations."""

    def setUp(self):
        self.all_extracted, self.names = _two_workbooks_with_conflict()
        self.assessment = assess_merge(self.all_extracted, self.names)

    def test_lineage_has_shared_table(self):
        lineage = build_column_lineage(self.all_extracted, self.names, self.assessment)
        self.assertIn('[dbo].[Orders]', lineage)

    def test_lineage_shared_table_has_both_workbooks(self):
        lineage = build_column_lineage(self.all_extracted, self.names, self.assessment)
        orders = lineage['[dbo].[Orders]']
        self.assertEqual(len(orders['source_workbooks']), 2)

    def test_lineage_column_sources(self):
        lineage = build_column_lineage(self.all_extracted, self.names, self.assessment)
        cols = lineage['[dbo].[Orders]']['columns']
        # Amount should be in both workbooks
        self.assertIn('Amount', cols)
        self.assertEqual(len(cols['Amount']), 2)
        # Region should be in only ProductDetail
        self.assertIn('Region', cols)
        self.assertEqual(len(cols['Region']), 1)

    def test_lineage_annotations(self):
        lineage = build_column_lineage(self.all_extracted, self.names, self.assessment)
        annotations = generate_lineage_annotations(lineage)
        self.assertIn('[dbo].[Orders]', annotations)
        text = annotations['[dbo].[Orders]']
        self.assertIn('SalesOverview', text)
        self.assertIn('ProductDetail', text)

    def test_lineage_empty_assessment(self):
        assessment = MergeAssessment(workbooks=['WB1'])
        lineage = build_column_lineage([{}], ['WB1'], assessment)
        self.assertIsInstance(lineage, dict)


# ═══════════════════════════════════════════════════════════════════
#  Measure Risk Analyzer Tests
# ═══════════════════════════════════════════════════════════════════

class TestMeasureRiskAnalyzer(unittest.TestCase):
    """Tests for analyze_measure_risk."""

    def test_same_agg_same_col_low_risk(self):
        conflicts = [MeasureConflict(
            name='Total', table='Orders',
            variants={'WB1': 'SUM([Amount])', 'WB2': 'SUM([Amount])'},
        )]
        risks = analyze_measure_risk(conflicts)
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0].risk_level, 'low')

    def test_different_agg_high_risk(self):
        conflicts = [MeasureConflict(
            name='Total', table='Orders',
            variants={'WB1': 'SUM([Amount])', 'WB2': 'COUNT([OrderID])'},
        )]
        risks = analyze_measure_risk(conflicts)
        self.assertEqual(risks[0].risk_level, 'high')

    def test_same_agg_different_cols_medium_risk(self):
        conflicts = [MeasureConflict(
            name='Total', table='Orders',
            variants={'WB1': 'SUM([Amount])', 'WB2': 'SUM([Price])'},
        )]
        risks = analyze_measure_risk(conflicts)
        self.assertEqual(risks[0].risk_level, 'medium')

    def test_no_conflicts_empty_result(self):
        risks = analyze_measure_risk([])
        self.assertEqual(len(risks), 0)

    def test_risk_has_aggregation_types(self):
        conflicts = [MeasureConflict(
            name='Total', table='Orders',
            variants={'WB1': 'SUM([Amount])', 'WB2': 'AVERAGE([Amount])'},
        )]
        risks = analyze_measure_risk(conflicts)
        self.assertIn('WB1', risks[0].aggregation_types)
        self.assertEqual(risks[0].aggregation_types['WB1'], 'SUM')
        self.assertEqual(risks[0].aggregation_types['WB2'], 'AVERAGE')

    def test_complex_formula_detection(self):
        """CALCULATE wrapping makes outer agg the same; inner functions differ → medium."""
        conflicts = [MeasureConflict(
            name='KPI', table='Sales',
            variants={
                'WB1': 'CALCULATE(SUM([Revenue]), FILTER(ALL(Dates), Dates[Year] = 2024))',
                'WB2': 'CALCULATE(COUNT([OrderID]), FILTER(ALL(Dates), Dates[Year] = 2024))',
            },
        )]
        risks = analyze_measure_risk(conflicts)
        # Both use CALCULATE as outer agg, different columns → medium
        self.assertEqual(risks[0].risk_level, 'medium')

    def test_different_inner_agg_without_calculate_high_risk(self):
        """Different aggregation functions without CALCULATE wrapping → high."""
        conflicts = [MeasureConflict(
            name='KPI', table='Sales',
            variants={
                'WB1': 'SUM([Revenue])',
                'WB2': 'COUNT([OrderID])',
            },
        )]
        risks = analyze_measure_risk(conflicts)
        self.assertEqual(risks[0].risk_level, 'high')

    def test_unknown_agg_treated_as_low(self):
        conflicts = [MeasureConflict(
            name='Static', table='T',
            variants={'WB1': '42', 'WB2': '42'},
        )]
        risks = analyze_measure_risk(conflicts)
        self.assertEqual(risks[0].risk_level, 'low')


# ═══════════════════════════════════════════════════════════════════
#  RLS Role Consolidation Tests
# ═══════════════════════════════════════════════════════════════════

class TestRLSConsolidation(unittest.TestCase):
    """Tests for consolidate_rls_roles and merge_rls_roles."""

    def test_single_workbook_keep(self):
        wb = _make_wb([], user_filters=[
            {'name': 'Region', 'table': 'Territory',
             'filter_expression': '[Region] = "East"'},
        ])
        result = consolidate_rls_roles([wb], ['WB1'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action, 'keep')

    def test_same_filter_across_workbooks_merge(self):
        uf = {'name': 'Region', 'table': 'Territory',
              'filter_expression': '[Region] = "East"'}
        wb1 = _make_wb([], user_filters=[uf])
        wb2 = _make_wb([], user_filters=[uf])
        result = consolidate_rls_roles([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action, 'merge')
        self.assertEqual(len(result[0].source_workbooks), 2)

    def test_different_filters_merged_with_or(self):
        wb1 = _make_wb([], user_filters=[
            {'name': 'Region', 'table': 'T',
             'filter_expression': '[Region] = "East"'},
        ])
        wb2 = _make_wb([], user_filters=[
            {'name': 'Region', 'table': 'T',
             'filter_expression': '[Region] = "West"'},
        ])
        result = consolidate_rls_roles([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(result), 1)
        self.assertIn('||', result[0].merged_expression)

    def test_merge_rls_roles_returns_list(self):
        wb1 = _make_wb([], user_filters=[
            {'name': 'RoleA', 'table': 'T', 'filter_expression': 'TRUE()'},
        ])
        merged = merge_rls_roles([wb1], ['WB1'])
        self.assertIsInstance(merged, list)
        self.assertEqual(len(merged), 1)

    def test_no_roles_empty_result(self):
        wb = _make_wb([])
        result = consolidate_rls_roles([wb], ['WB1'])
        self.assertEqual(len(result), 0)

    def test_different_role_names_kept_separate(self):
        wb1 = _make_wb([], user_filters=[
            {'name': 'East', 'table': 'T', 'filter_expression': '[R] = "E"'},
        ])
        wb2 = _make_wb([], user_filters=[
            {'name': 'West', 'table': 'T', 'filter_expression': '[R] = "W"'},
        ])
        result = consolidate_rls_roles([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(result), 2)

    def test_merge_deduplicates_role_names(self):
        uf = {'name': 'Admin', 'table': 'T', 'filter_expression': 'TRUE()'}
        wb1 = _make_wb([], user_filters=[uf])
        wb2 = _make_wb([], user_filters=[uf])
        merged = merge_rls_roles([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(merged), 1)


# ═══════════════════════════════════════════════════════════════════
#  Cross-Report Navigation Tests
# ═══════════════════════════════════════════════════════════════════

class TestCrossReportNavigation(unittest.TestCase):
    """Tests for build_cross_report_navigation."""

    def test_two_reports_have_links(self):
        nav = build_cross_report_navigation(['Sales', 'Marketing'], 'Shared')
        self.assertEqual(len(nav), 2)
        # Sales should link to Marketing
        sales_nav = [n for n in nav if n['report_name'] == 'Sales'][0]
        self.assertEqual(len(sales_nav['navigation_buttons']), 1)
        self.assertEqual(sales_nav['navigation_buttons'][0]['label'], 'Marketing')

    def test_three_reports_each_has_two_links(self):
        nav = build_cross_report_navigation(['A', 'B', 'C'], 'Model')
        for n in nav:
            self.assertEqual(len(n['navigation_buttons']), 2)

    def test_single_report_no_links(self):
        nav = build_cross_report_navigation(['Only'], 'Model')
        self.assertEqual(len(nav), 1)
        self.assertEqual(len(nav[0]['navigation_buttons']), 0)

    def test_navigation_contains_model_name(self):
        nav = build_cross_report_navigation(['A', 'B'], 'MyModel')
        self.assertEqual(nav[0]['model_name'], 'MyModel')

    def test_navigation_target_format(self):
        nav = build_cross_report_navigation(['Sales', 'Marketing'], 'Model')
        btn = nav[0]['navigation_buttons'][0]
        self.assertEqual(btn['target_report'], 'Marketing.Report')
        self.assertEqual(btn['type'], 'navigation')


# ═══════════════════════════════════════════════════════════════════
#  Plugin Merge Hooks Tests
# ═══════════════════════════════════════════════════════════════════

class TestPluginMergeHooks(unittest.TestCase):
    """Tests for merge-related plugin hooks."""

    def test_plugin_base_has_merge_hooks(self):
        from powerbi_import.plugins import PluginBase
        plugin = PluginBase()
        self.assertTrue(hasattr(plugin, 'on_merge_conflict'))
        self.assertTrue(hasattr(plugin, 'on_merge_complete'))
        self.assertTrue(hasattr(plugin, 'transform_merged_dax'))

    def test_merge_conflict_hook_returns_none_by_default(self):
        from powerbi_import.plugins import PluginBase
        result = PluginBase().on_merge_conflict('measure', 'Total', {})
        self.assertIsNone(result)

    def test_transform_merged_dax_passthrough(self):
        from powerbi_import.plugins import PluginBase
        result = PluginBase().transform_merged_dax('M', 'SUM([A])', 'WB1')
        self.assertEqual(result, 'SUM([A])')

    def test_plugin_manager_dispatches_merge_hook(self):
        from powerbi_import.plugins import PluginManager

        class TestPlugin:
            name = 'test'
            def on_merge_conflict(self, conflict_type, name, variants):
                return 'keep_first'

        mgr = PluginManager()
        mgr.register(TestPlugin())
        result = mgr.call_hook('on_merge_conflict',
                               conflict_type='measure',
                               name='Total',
                               variants={'WB1': 'SUM([A])'})
        self.assertEqual(result, 'keep_first')

    def test_plugin_manager_chains_dax_transform(self):
        from powerbi_import.plugins import PluginManager

        class UpperPlugin:
            name = 'upper'
            def transform_merged_dax(self, value):
                return value.upper()

        mgr = PluginManager()
        mgr.register(UpperPlugin())
        result = mgr.apply_transform('transform_merged_dax', 'sum([a])')
        self.assertEqual(result, 'SUM([A])')


# ═══════════════════════════════════════════════════════════════════
#  Fabric Deployment Orchestration Tests
# ═══════════════════════════════════════════════════════════════════

class TestFabricDeploymentOrchestration(unittest.TestCase):
    """Tests for FabricDeployer.deploy_shared_model."""

    def test_deployer_has_shared_model_method(self):
        from powerbi_import.deploy.deployer import FabricDeployer

        class MockClient:
            def list_items(self, ws_id, item_type):
                return {'value': []}
            def post(self, path, data=None):
                return {'id': 'new-id'}
            def put(self, path, data=None):
                return {'id': 'updated-id'}
            def get(self, path):
                return {}

        deployer = FabricDeployer(client=MockClient())
        self.assertTrue(hasattr(deployer, 'deploy_shared_model'))

    def test_deploy_shared_model_missing_dir(self):
        from powerbi_import.deploy.deployer import FabricDeployer

        class MockClient:
            def list_items(self, ws_id, item_type):
                return {'value': []}
            def post(self, path, data=None):
                return {'id': 'new-id'}

        deployer = FabricDeployer(client=MockClient())
        tmpdir = tempfile.mkdtemp()
        result = deployer.deploy_shared_model(
            'workspace-123', tmpdir, 'TestModel', ['Report1'],
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['model_status'], 'not_found')

    def test_deploy_shared_model_success(self):
        from powerbi_import.deploy.deployer import FabricDeployer

        class MockClient:
            def list_items(self, ws_id, item_type):
                return {'value': []}
            def post(self, path, data=None):
                return {'id': 'new-id-123'}
            def put(self, path, data=None):
                return {'id': 'new-id-123'}

        deployer = FabricDeployer(client=MockClient())
        tmpdir = tempfile.mkdtemp()
        # Create model directory structure
        sm_dir = os.path.join(tmpdir, 'TestModel.SemanticModel', 'definition')
        os.makedirs(sm_dir)
        with open(os.path.join(sm_dir, 'model.tmdl'), 'w') as f:
            f.write('model Model\n')
        # Create report directory
        rpt_dir = os.path.join(tmpdir, 'Sales.Report', 'definition')
        os.makedirs(rpt_dir)
        with open(os.path.join(rpt_dir, 'report.json'), 'w') as f:
            json.dump({'version': '4.0'}, f)

        result = deployer.deploy_shared_model(
            'ws-123', tmpdir, 'TestModel', ['Sales'],
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['model_status'], 'deployed')
        self.assertEqual(len(result['reports']), 1)
        self.assertEqual(result['reports'][0]['status'], 'deployed')

    def test_deploy_report_failure_continues(self):
        from powerbi_import.deploy.deployer import FabricDeployer

        call_count = [0]

        class MockClient:
            def list_items(self, ws_id, item_type):
                return {'value': []}
            def post(self, path, data=None):
                call_count[0] += 1
                if call_count[0] == 2:
                    raise RuntimeError("network error")
                return {'id': 'ok'}
            def put(self, path, data=None):
                return {'id': 'ok'}

        deployer = FabricDeployer(client=MockClient())
        tmpdir = tempfile.mkdtemp()
        sm_dir = os.path.join(tmpdir, 'M.SemanticModel', 'definition')
        os.makedirs(sm_dir)
        with open(os.path.join(sm_dir, 'model.tmdl'), 'w') as f:
            f.write('model')
        for name in ['BadReport', 'GoodReport']:
            rdir = os.path.join(tmpdir, f'{name}.Report', 'definition')
            os.makedirs(rdir)
            with open(os.path.join(rdir, 'r.json'), 'w') as f:
                json.dump({}, f)

        result = deployer.deploy_shared_model(
            'ws', tmpdir, 'M', ['BadReport', 'GoodReport'],
        )
        self.assertFalse(result['success'])
        statuses = [r['status'] for r in result['reports']]
        self.assertIn('failed', statuses)
        self.assertIn('deployed', statuses)


# ═══════════════════════════════════════════════════════════════════
#  Integration: import_shared_model with new features
# ═══════════════════════════════════════════════════════════════════

class TestImportSharedModelEnhanced(unittest.TestCase):
    """Verify the enhanced import_shared_model returns new fields."""

    def test_result_has_new_fields(self):
        from powerbi_import.import_to_powerbi import PowerBIImporter
        all_extracted, names = _two_workbooks_with_conflict()
        importer = PowerBIImporter()
        tmpdir = tempfile.mkdtemp()
        result = importer.import_shared_model(
            model_name='TestModel',
            all_converted_objects=all_extracted,
            workbook_names=names,
            output_dir=tmpdir,
            force_merge=True,
        )
        self.assertIn('validation_issues', result)
        self.assertIn('risk_analysis', result)
        self.assertIn('rls_consolidations', result)
        self.assertIn('lineage', result)
        self.assertIn('navigation', result)

    def test_save_merge_config_flag(self):
        from powerbi_import.import_to_powerbi import PowerBIImporter
        all_extracted, names = _two_workbooks_with_conflict()
        importer = PowerBIImporter()
        tmpdir = tempfile.mkdtemp()
        result = importer.import_shared_model(
            model_name='ConfigTest',
            all_converted_objects=all_extracted,
            workbook_names=names,
            output_dir=tmpdir,
            force_merge=True,
            save_config=True,
        )
        config_path = os.path.join(tmpdir, 'ConfigTest', 'merge_config.json')
        self.assertTrue(os.path.isfile(config_path))

    def test_lineage_json_written(self):
        from powerbi_import.import_to_powerbi import PowerBIImporter
        all_extracted, names = _two_workbooks_with_conflict()
        importer = PowerBIImporter()
        tmpdir = tempfile.mkdtemp()
        importer.import_shared_model(
            model_name='LinTest',
            all_converted_objects=all_extracted,
            workbook_names=names,
            output_dir=tmpdir,
            force_merge=True,
        )
        lineage_path = os.path.join(tmpdir, 'LinTest', 'column_lineage.json')
        self.assertTrue(os.path.isfile(lineage_path))


if __name__ == '__main__':
    unittest.main()
