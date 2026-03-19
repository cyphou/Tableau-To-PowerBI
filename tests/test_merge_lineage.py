"""Unit tests for lineage metadata injection and TMDL annotation round-trip."""

import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _make_wb(name, tables, calcs=None, params=None, hierarchies=None,
             goals=None, calc_groups=None, field_params=None,
             perspectives=None, cultures=None):
    """Build a minimal workbook converted_objects dict."""
    return {
        'datasources': [{
            'name': f'DS_{name}',
            'connection': {'class': 'textscan'},
            'tables': tables,
            'relationships': [],
            'calculations': [],
        }],
        'calculations': calcs or [],
        'parameters': params or [],
        'hierarchies': hierarchies or [],
        'goals': goals or [],
        'calculation_groups': calc_groups or [],
        'field_parameters': field_params or [],
        'perspectives': perspectives or [],
        'cultures': cultures or [],
        'worksheets': [], 'dashboards': [], 'filters': [],
        'stories': [], 'actions': [], 'sets': [], 'groups': [],
        'bins': [], 'sort_orders': [], 'aliases': [], 'custom_sql': [],
        'user_filters': [],
    }


def _table(name, cols=None):
    cols = cols or [{'name': 'id', 'datatype': 'int64'}]
    return {'name': name, 'columns': cols}


class TestTableLineage(unittest.TestCase):
    """Lineage metadata on merged tables."""

    def setUp(self):
        from powerbi_import.shared_model import assess_merge, merge_semantic_models
        t = _table('SharedTable')
        wb1 = _make_wb('WB1', [copy.deepcopy(t)])
        wb2 = _make_wb('WB2', [copy.deepcopy(t)])
        assess = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        assess.isolated_tables = {}
        self.merged = merge_semantic_models([wb1, wb2], assess, 'TestModel')

    def _tables(self):
        return self.merged.get('datasources', [{}])[0].get('tables', [])

    def test_shared_table_has_source_workbooks(self):
        for t in self._tables():
            if t['name'] == 'SharedTable':
                self.assertIn('_source_workbooks', t)
                self.assertEqual(sorted(t['_source_workbooks']), ['WB1', 'WB2'])
                return
        self.fail("SharedTable not found in merged tables")

    def test_shared_table_has_merge_action(self):
        for t in self._tables():
            if t['name'] == 'SharedTable':
                self.assertEqual(t.get('_merge_action'), 'deduplicated')
                return
        self.fail("SharedTable not found")

    def test_unique_table_has_source_workbook(self):
        wb1 = _make_wb('WB1', [_table('OnlyInWB1')])
        wb2 = _make_wb('WB2', [_table('OnlyInWB2')])
        from powerbi_import.shared_model import assess_merge, merge_semantic_models
        assess = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        assess.isolated_tables = {}
        merged = merge_semantic_models([wb1, wb2], assess, 'M')
        tables = merged.get('datasources', [{}])[0].get('tables', [])
        for t in tables:
            if t['name'] == 'OnlyInWB1':
                self.assertEqual(t.get('_source_workbooks'), ['WB1'])
                self.assertEqual(t.get('_merge_action'), 'unique')
                return
        self.fail("OnlyInWB1 not found")

    def test_relationship_lineage(self):
        wb1 = _make_wb('WB1', [_table('A'), _table('B')])
        wb1['datasources'][0]['relationships'] = [
            {'from_table': 'A', 'from_column': 'id', 'to_table': 'B', 'to_column': 'id', 'join_type': 'left'}
        ]
        wb2 = _make_wb('WB2', [_table('A'), _table('B')])
        wb2['datasources'][0]['relationships'] = [
            {'from_table': 'A', 'from_column': 'id', 'to_table': 'B', 'to_column': 'id', 'join_type': 'left'}
        ]
        from powerbi_import.shared_model import assess_merge, merge_semantic_models
        assess = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        assess.isolated_tables = {}
        merged = merge_semantic_models([wb1, wb2], assess, 'M')
        rels = merged.get('datasources', [{}])[0].get('relationships', [])
        self.assertGreater(len(rels), 0)
        for r in rels:
            self.assertIn('_source_workbooks', r)


class TestCalculationLineage(unittest.TestCase):
    """Lineage metadata on merged calculations."""

    def test_duplicate_calc_lineage(self):
        from powerbi_import.shared_model import assess_merge, merge_semantic_models
        calc = {'name': 'Total', 'caption': 'Total', 'formula': 'SUM([Sales])', 'role': 'measure'}
        wb1 = _make_wb('WB1', [_table('T')], calcs=[copy.deepcopy(calc)])
        wb2 = _make_wb('WB2', [_table('T')], calcs=[copy.deepcopy(calc)])
        assess = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        assess.isolated_tables = {}
        merged = merge_semantic_models([wb1, wb2], assess, 'M')
        matched = [c for c in merged.get('calculations', []) if c.get('caption') == 'Total']
        self.assertGreater(len(matched), 0)
        c = matched[0]
        self.assertEqual(c.get('_merge_action'), 'deduplicated')
        self.assertIn('WB1', c['_source_workbooks'])
        self.assertIn('WB2', c['_source_workbooks'])

    def test_unique_calc_lineage(self):
        from powerbi_import.shared_model import assess_merge, merge_semantic_models
        wb1 = _make_wb('WB1', [_table('T')], calcs=[
            {'name': 'C1', 'caption': 'C1', 'formula': 'SUM([A])', 'role': 'measure'}
        ])
        wb2 = _make_wb('WB2', [_table('T')], calcs=[
            {'name': 'C2', 'caption': 'C2', 'formula': 'SUM([B])', 'role': 'measure'}
        ])
        assess = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        assess.isolated_tables = {}
        merged = merge_semantic_models([wb1, wb2], assess, 'M')
        c1 = [c for c in merged.get('calculations', []) if c.get('caption') == 'C1']
        self.assertGreater(len(c1), 0)
        self.assertEqual(c1[0].get('_merge_action'), 'unique')
        self.assertEqual(c1[0].get('_source_workbooks'), ['WB1'])

    def test_conflicting_calc_gets_namespaced(self):
        from powerbi_import.shared_model import assess_merge, merge_semantic_models
        wb1 = _make_wb('WB1', [_table('T')], calcs=[
            {'name': 'Metric', 'caption': 'Metric', 'formula': 'SUM([A])', 'role': 'measure'}
        ])
        wb2 = _make_wb('WB2', [_table('T')], calcs=[
            {'name': 'Metric', 'caption': 'Metric', 'formula': 'SUM([B])', 'role': 'measure'}
        ])
        assess = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        assess.isolated_tables = {}
        merged = merge_semantic_models([wb1, wb2], assess, 'M')
        calcs = merged.get('calculations', [])
        namespaced = [c for c in calcs if 'namespaced' in c.get('_merge_action', '')]
        # At least one should be namespaced if there's a conflict
        self.assertGreater(len(namespaced), 0)


class TestParameterLineage(unittest.TestCase):
    """Lineage metadata on merged parameters."""

    def test_duplicate_param_lineage(self):
        from powerbi_import.shared_model import assess_merge, merge_semantic_models
        param = {'name': 'P1', 'caption': 'P1', 'value': '10', 'data_type': 'integer'}
        wb1 = _make_wb('WB1', [_table('T')], params=[copy.deepcopy(param)])
        wb2 = _make_wb('WB2', [_table('T')], params=[copy.deepcopy(param)])
        assess = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        assess.isolated_tables = {}
        merged = merge_semantic_models([wb1, wb2], assess, 'M')
        params = merged.get('parameters', [])
        matched = [p for p in params if p.get('caption') == 'P1']
        self.assertGreater(len(matched), 0)
        self.assertEqual(matched[0].get('_merge_action'), 'deduplicated')
        self.assertIn('WB1', matched[0]['_source_workbooks'])
        self.assertIn('WB2', matched[0]['_source_workbooks'])

    def test_unique_param_lineage(self):
        from powerbi_import.shared_model import assess_merge, merge_semantic_models
        wb1 = _make_wb('WB1', [_table('T')], params=[
            {'name': 'PA', 'caption': 'PA', 'value': '5', 'data_type': 'integer'}
        ])
        wb2 = _make_wb('WB2', [_table('T')], params=[
            {'name': 'PB', 'caption': 'PB', 'value': '9', 'data_type': 'integer'}
        ])
        assess = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        assess.isolated_tables = {}
        merged = merge_semantic_models([wb1, wb2], assess, 'M')
        matched = [p for p in merged.get('parameters', []) if p.get('caption') == 'PA']
        self.assertGreater(len(matched), 0)
        self.assertEqual(matched[0].get('_merge_action'), 'unique')


class TestHierarchyLineage(unittest.TestCase):
    """Lineage metadata on merged hierarchies."""

    def test_duplicate_hierarchy_lineage(self):
        from powerbi_import.shared_model import assess_merge, merge_semantic_models
        h = {'name': 'Geo', 'levels': [{'name': 'Country'}, {'name': 'State'}, {'name': 'City'}]}
        wb1 = _make_wb('WB1', [_table('T')], hierarchies=[copy.deepcopy(h)])
        wb2 = _make_wb('WB2', [_table('T')], hierarchies=[copy.deepcopy(h)])
        assess = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        assess.isolated_tables = {}
        merged = merge_semantic_models([wb1, wb2], assess, 'M')
        hiers = merged.get('hierarchies', [])
        matched = [hr for hr in hiers if hr.get('name') == 'Geo']
        self.assertGreater(len(matched), 0)
        self.assertEqual(matched[0].get('_merge_action'), 'deduplicated')
        self.assertIn('WB1', matched[0]['_source_workbooks'])
        self.assertIn('WB2', matched[0]['_source_workbooks'])


class TestExtractLineage(unittest.TestCase):
    """Test the extract_lineage() function."""

    def test_extracts_table_lineage(self):
        from powerbi_import.shared_model import extract_lineage
        merged = {
            'datasources': [{'tables': [
                {'name': 'T1', '_source_workbooks': ['A', 'B'], '_merge_action': 'deduplicated'},
                {'name': 'T2', '_source_workbooks': ['A'], '_merge_action': 'unique'},
            ]}],
            'calculations': [],
            'parameters': [],
            'hierarchies': [],
        }
        records = extract_lineage(merged)
        table_recs = [r for r in records if r['type'] == 'table']
        self.assertEqual(len(table_recs), 2)
        t1 = [r for r in table_recs if r['name'] == 'T1'][0]
        self.assertEqual(t1['merge_action'], 'deduplicated')
        self.assertEqual(sorted(t1['source_workbooks']), ['A', 'B'])

    def test_extracts_calculation_lineage(self):
        from powerbi_import.shared_model import extract_lineage
        merged = {
            'datasources': [{'tables': []}],
            'calculations': [
                {'caption': 'M1', '_source_workbooks': ['X'], '_merge_action': 'unique'},
            ],
            'parameters': [],
            'hierarchies': [],
        }
        records = extract_lineage(merged)
        calc_recs = [r for r in records if r['type'] == 'calculation']
        self.assertEqual(len(calc_recs), 1)
        self.assertEqual(calc_recs[0]['name'], 'M1')

    def test_extracts_parameter_lineage(self):
        from powerbi_import.shared_model import extract_lineage
        merged = {
            'datasources': [{'tables': []}],
            'calculations': [],
            'parameters': [
                {'caption': 'P1', '_source_workbooks': ['A', 'B'], '_merge_action': 'deduplicated'},
            ],
            'hierarchies': [],
        }
        records = extract_lineage(merged)
        param_recs = [r for r in records if r['type'] == 'parameter']
        self.assertEqual(len(param_recs), 1)
        self.assertIn('A', param_recs[0]['source_workbooks'])

    def test_empty_merged_returns_empty(self):
        from powerbi_import.shared_model import extract_lineage
        merged = {'datasources': [{'tables': []}], 'calculations': [], 'parameters': [], 'hierarchies': []}
        records = extract_lineage(merged)
        self.assertEqual(len(records), 0)

    def test_lineage_without_source_workbooks_has_empty_list(self):
        from powerbi_import.shared_model import extract_lineage
        merged = {
            'datasources': [{'tables': [{'name': 'T1'}]}],
            'calculations': [{'caption': 'C1'}],
            'parameters': [],
            'hierarchies': [],
        }
        records = extract_lineage(merged)
        # Records are still created but with empty source_workbooks
        for rec in records:
            self.assertEqual(rec['source_workbooks'], [])


class TestTMDLAnnotationRoundTrip(unittest.TestCase):
    """TMDL annotations written and readable."""

    def test_migration_source_annotation_written(self):
        from powerbi_import.tmdl_generator import generate_tmdl
        datasources = [{
            'name': 'DS',
            'connection': {'class': 'textscan'},
            'tables': [{
                'name': 'Sales',
                'columns': [{'name': 'Amount', 'datatype': 'double', 'role': 'measure'}],
                '_source_workbooks': ['WB1', 'WB2'],
                '_merge_action': 'deduplicated',
            }],
            'relationships': [],
        }]
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': [], 'parameters': [], 'user_filters': [],
            '_datasources': datasources,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            sm_dir = os.path.join(tmpdir, 'TestModel.SemanticModel')
            os.makedirs(sm_dir, exist_ok=True)
            generate_tmdl(datasources, 'TestModel', extra, sm_dir)
            tables_dir = os.path.join(sm_dir, 'definition', 'tables')
            if os.path.isdir(tables_dir):
                for f in os.listdir(tables_dir):
                    if 'Sales' in f:
                        with open(os.path.join(tables_dir, f), 'r', encoding='utf-8') as fh:
                            content = fh.read()
                        self.assertIn('MigrationSource', content)
                        self.assertIn('WB1', content)
                        self.assertIn('WB2', content)
                        self.assertIn('MergeAction', content)
                        self.assertIn('deduplicated', content)
                        return
            self.fail("Sales.tmdl not found")

    def test_merge_action_annotation_on_measure(self):
        from powerbi_import.tmdl_generator import generate_tmdl
        datasources = [{
            'name': 'DS',
            'connection': {'class': 'textscan'},
            'tables': [{
                'name': 'Data',
                'columns': [{'name': 'Val', 'datatype': 'double', 'role': 'measure'}],
            }],
            'relationships': [],
            'calculations': [{
                'name': 'TotalVal',
                'caption': 'TotalVal',
                'formula': 'SUM([Val])',
                'role': 'measure',
                '_source_workbooks': ['WB_A'],
                '_merge_action': 'unique',
            }],
        }]
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': [], 'parameters': [], 'user_filters': [],
            '_datasources': datasources,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            sm_dir = os.path.join(tmpdir, 'TestModel.SemanticModel')
            os.makedirs(sm_dir, exist_ok=True)
            generate_tmdl(datasources, 'TestModel', extra, sm_dir)
            tables_dir = os.path.join(sm_dir, 'definition', 'tables')
            if os.path.isdir(tables_dir):
                for f in os.listdir(tables_dir):
                    fpath = os.path.join(tables_dir, f)
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        content = fh.read()
                    if 'TotalVal' in content and 'MigrationSource' in content:
                        self.assertIn('WB_A', content)
                        self.assertIn('unique', content)
                        return
            self.fail("TotalVal measure with MigrationSource not found")

    def test_no_annotation_without_lineage(self):
        from powerbi_import.tmdl_generator import generate_tmdl
        datasources = [{
            'name': 'DS',
            'connection': {'class': 'textscan'},
            'tables': [{'name': 'Plain', 'columns': [{'name': 'x', 'datatype': 'string'}]}],
            'relationships': [],
        }]
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': [], 'parameters': [], 'user_filters': [],
            '_datasources': datasources,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            sm_dir = os.path.join(tmpdir, 'TestModel.SemanticModel')
            os.makedirs(sm_dir, exist_ok=True)
            generate_tmdl(datasources, 'TestModel', extra, sm_dir)
            tables_dir = os.path.join(sm_dir, 'definition', 'tables')
            if os.path.isdir(tables_dir):
                for f in os.listdir(tables_dir):
                    if 'Plain' in f:
                        with open(os.path.join(tables_dir, f), 'r', encoding='utf-8') as fh:
                            content = fh.read()
                        self.assertNotIn('MigrationSource', content)
                        self.assertNotIn('MergeAction', content)
                        return


class TestLineageHTMLReport(unittest.TestCase):
    """Lineage section in HTML merge report."""

    def test_lineage_section_contains_table(self):
        from powerbi_import.merge_report_html import _build_lineage_section
        merged = {
            'datasources': [{'tables': [
                {'name': 'T1', '_source_workbooks': ['A'], '_merge_action': 'unique'},
            ]}],
            'calculations': [],
            'parameters': [],
            'hierarchies': [],
        }
        html = _build_lineage_section(merged, ['A'])
        self.assertIn('Lineage', html)
        self.assertIn('T1', html)
        self.assertIn('Unique', html)

    def test_lineage_section_shows_multiple_sources(self):
        from powerbi_import.merge_report_html import _build_lineage_section
        merged = {
            'datasources': [{'tables': [
                {'name': 'Shared', '_source_workbooks': ['WB1', 'WB2'], '_merge_action': 'deduplicated'},
            ]}],
            'calculations': [],
            'parameters': [],
            'hierarchies': [],
        }
        html = _build_lineage_section(merged, ['WB1', 'WB2'])
        self.assertIn('WB1', html)
        self.assertIn('WB2', html)
        self.assertIn('Deduplicated', html)

    def test_empty_lineage_produces_section(self):
        from powerbi_import.merge_report_html import _build_lineage_section
        merged = {'datasources': [{'tables': []}], 'calculations': [], 'parameters': [], 'hierarchies': []}
        html = _build_lineage_section(merged, ['A'])
        # Empty lineage may produce empty string or minimal section
        self.assertIsInstance(html, str)

    def test_lineage_section_includes_calculations(self):
        from powerbi_import.merge_report_html import _build_lineage_section
        merged = {
            'datasources': [{'tables': []}],
            'calculations': [
                {'caption': 'MyCalc', '_source_workbooks': ['WB1'], '_merge_action': 'unique'},
            ],
            'parameters': [],
            'hierarchies': [],
        }
        html = _build_lineage_section(merged, ['WB1'])
        self.assertIn('MyCalc', html)


if __name__ == '__main__':
    unittest.main()
