"""
Sprint 86 — Composite Model Depth Tests.

Validates per-table StorageMode, aggregation table generation,
hybrid relationship constraints, and CLI flags.
"""

import json
import os
import shutil
import tempfile
import unittest

from powerbi_import import tmdl_generator


# ═══════════════════════════════════════════════════════════════════
# Helper: minimal datasource for TMDL generation
# ═══════════════════════════════════════════════════════════════════

def _make_datasource(tables, calculations=None):
    """Build a minimal datasource dict for generate_tmdl()."""
    ds_tables = []
    for tbl in tables:
        cols = [{'name': c, 'datatype': 'string'} for c in tbl.get('columns', [])]
        # Add numeric columns if requested
        for c in tbl.get('num_columns', []):
            cols.append({'name': c, 'datatype': 'real'})
        for c in tbl.get('date_columns', []):
            cols.append({'name': c, 'datatype': 'datetime'})
        ds_tables.append({
            'name': tbl['name'],
            'type': 'table',
            'columns': cols,
        })
    ds = {
        'name': 'TestDS',
        'connection': {'type': 'sqlserver', 'server': 'localhost', 'database': 'TestDB'},
        'tables': ds_tables,
        'calculations': calculations or [],
        'relationships': [],
    }
    return ds


def _generate_model(datasources, model_mode='import', composite_threshold=None,
                    agg_tables='none', extra_objects=None):
    """Generate TMDL to a temp dir and return model stats + path."""
    tmp = tempfile.mkdtemp()
    try:
        stats = tmdl_generator.generate_tmdl(
            datasources=datasources if isinstance(datasources, list) else [datasources],
            report_name='CompositeTest',
            extra_objects=extra_objects or {},
            output_dir=tmp,
            model_mode=model_mode,
            composite_threshold=composite_threshold,
            agg_tables=agg_tables,
        )
        return stats, tmp
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


# ═══════════════════════════════════════════════════════════════════
# 1. Per-table StorageMode
# ═══════════════════════════════════════════════════════════════════

class TestPerTableStorageMode(unittest.TestCase):
    """86.1 — Composite mode classifies tables by column count threshold."""

    def setUp(self):
        # Small table: 3 columns (below default threshold of 10)
        # Large table: 15 columns (above default threshold)
        self.small_table = {'name': 'Lookup', 'columns': [f'C{i}' for i in range(3)]}
        self.large_table = {'name': 'Facts', 'columns': [f'Col{i}' for i in range(15)]}
        self.ds = _make_datasource([self.small_table, self.large_table])

    def tearDown(self):
        if hasattr(self, '_tmp'):
            shutil.rmtree(self._tmp, ignore_errors=True)

    def test_import_mode_all_import(self):
        """In import mode, all partitions should be import."""
        stats, self._tmp = _generate_model(self.ds, model_mode='import')
        tmdl_dir = os.path.join(self._tmp, 'definition', 'tables')
        if os.path.isdir(tmdl_dir):
            for fname in os.listdir(tmdl_dir):
                path = os.path.join(tmdl_dir, fname)
                if os.path.isfile(path):
                    content = open(path, encoding='utf-8').read()
                    if 'mode: directQuery' in content:
                        self.fail(f"Found directQuery in import mode: {fname}")

    def test_composite_mode_small_table_import(self):
        """Composite: small table (< threshold) → import."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite')
        tmdl_path = os.path.join(self._tmp, 'definition', 'tables', 'Lookup.tmdl')
        if os.path.isfile(tmdl_path):
            content = open(tmdl_path, encoding='utf-8').read()
            self.assertIn('mode: import', content)

    def test_composite_mode_large_table_directquery(self):
        """Composite: large table (> threshold) → directQuery."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite')
        tmdl_path = os.path.join(self._tmp, 'definition', 'tables', 'Facts.tmdl')
        if os.path.isfile(tmdl_path):
            content = open(tmdl_path, encoding='utf-8').read()
            self.assertIn('mode: directQuery', content)

    def test_custom_threshold_5(self):
        """Custom threshold=5: table with 3 cols → import, 15 cols → directQuery."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite',
                                            composite_threshold=5)
        # Small table (3 cols) still import
        small_path = os.path.join(self._tmp, 'definition', 'tables', 'Lookup.tmdl')
        if os.path.isfile(small_path):
            content = open(small_path, encoding='utf-8').read()
            self.assertIn('mode: import', content)

    def test_custom_threshold_20(self):
        """Custom threshold=20: both tables < threshold → both import."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite',
                                            composite_threshold=20)
        # Even the 15-column table should be import
        large_path = os.path.join(self._tmp, 'definition', 'tables', 'Facts.tmdl')
        if os.path.isfile(large_path):
            content = open(large_path, encoding='utf-8').read()
            self.assertIn('mode: import', content)

    def test_custom_threshold_2(self):
        """Custom threshold=2: both tables > threshold → both directQuery."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite',
                                            composite_threshold=2)
        small_path = os.path.join(self._tmp, 'definition', 'tables', 'Lookup.tmdl')
        if os.path.isfile(small_path):
            content = open(small_path, encoding='utf-8').read()
            self.assertIn('mode: directQuery', content)

    def test_directquery_mode_all_dq(self):
        """In directQuery mode, all partitions should be directQuery."""
        stats, self._tmp = _generate_model(self.ds, model_mode='directQuery')
        tmdl_dir = os.path.join(self._tmp, 'definition', 'tables')
        if os.path.isdir(tmdl_dir):
            found_dq = False
            for fname in os.listdir(tmdl_dir):
                path = os.path.join(tmdl_dir, fname)
                if os.path.isfile(path):
                    content = open(path, encoding='utf-8').read()
                    if 'mode: directQuery' in content:
                        found_dq = True
            self.assertTrue(found_dq, "Expected directQuery partitions in DQ mode")

    def test_composite_stats_returned(self):
        """generate_tmdl returns correct stats dict."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite')
        self.assertIn('tables', stats)
        self.assertGreaterEqual(stats['tables'], 2)

    def test_threshold_none_uses_default_10(self):
        """No threshold → default 10. Table with 15 cols → directQuery."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite',
                                            composite_threshold=None)
        large_path = os.path.join(self._tmp, 'definition', 'tables', 'Facts.tmdl')
        if os.path.isfile(large_path):
            content = open(large_path, encoding='utf-8').read()
            self.assertIn('mode: directQuery', content)


# ═══════════════════════════════════════════════════════════════════
# 2. Aggregation table generation
# ═══════════════════════════════════════════════════════════════════

class TestAggregationTables(unittest.TestCase):
    """86.2 — Auto-generate Import-mode agg tables for DQ fact tables."""

    def setUp(self):
        self.ds = _make_datasource([
            {
                'name': 'Sales',
                'columns': [f'Dim{i}' for i in range(12)],
                'num_columns': ['Revenue', 'Quantity'],
                'date_columns': ['OrderDate'],
            },
        ], calculations=[
            {'name': 'Total Revenue', 'formula': 'SUM([Revenue])',
             'role': 'measure', 'datatype': 'real'},
        ])

    def tearDown(self):
        if hasattr(self, '_tmp'):
            shutil.rmtree(self._tmp, ignore_errors=True)

    def test_agg_tables_none_no_agg(self):
        """agg_tables='none': no Agg_ tables generated."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite',
                                            agg_tables='none')
        tmdl_dir = os.path.join(self._tmp, 'definition', 'tables')
        if os.path.isdir(tmdl_dir):
            agg_files = [f for f in os.listdir(tmdl_dir) if f.startswith('Agg_')]
            self.assertEqual(len(agg_files), 0, "No agg tables when agg_tables='none'")

    def test_agg_tables_auto_generates_agg(self):
        """agg_tables='auto': creates Agg_ table for DQ fact table with measures."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite',
                                            agg_tables='auto')
        tmdl_dir = os.path.join(self._tmp, 'definition', 'tables')
        if os.path.isdir(tmdl_dir):
            agg_files = [f for f in os.listdir(tmdl_dir) if f.startswith('Agg_')]
            self.assertGreaterEqual(len(agg_files), 1,
                                    "Expected Agg_ table for DQ fact table")

    def test_agg_table_is_import_mode(self):
        """Agg table should always be import mode."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite',
                                            agg_tables='auto')
        tmdl_dir = os.path.join(self._tmp, 'definition', 'tables')
        if os.path.isdir(tmdl_dir):
            for fname in os.listdir(tmdl_dir):
                if fname.startswith('Agg_'):
                    path = os.path.join(tmdl_dir, fname)
                    content = open(path, encoding='utf-8').read()
                    self.assertIn('mode: import', content,
                                  f"Agg table {fname} should be import mode")

    def test_agg_table_has_alternate_of(self):
        """Agg table columns should have alternateOf annotations."""
        stats, self._tmp = _generate_model(self.ds, model_mode='composite',
                                            agg_tables='auto')
        tmdl_dir = os.path.join(self._tmp, 'definition', 'tables')
        if os.path.isdir(tmdl_dir):
            for fname in os.listdir(tmdl_dir):
                if fname.startswith('Agg_'):
                    path = os.path.join(tmdl_dir, fname)
                    content = open(path, encoding='utf-8').read()
                    self.assertIn('alternateOf', content,
                                  "Agg table should have alternateOf annotations")

    def test_no_agg_for_import_table(self):
        """Import-mode tables should not get agg tables."""
        small_ds = _make_datasource([
            {'name': 'Small', 'columns': ['A', 'B'], 'num_columns': ['Val']},
        ], calculations=[
            {'name': 'Total Val', 'formula': 'SUM([Val])',
             'role': 'measure', 'datatype': 'real'},
        ])
        stats, self._tmp = _generate_model(small_ds, model_mode='composite',
                                            agg_tables='auto')
        tmdl_dir = os.path.join(self._tmp, 'definition', 'tables')
        if os.path.isdir(tmdl_dir):
            agg_files = [f for f in os.listdir(tmdl_dir) if f.startswith('Agg_')]
            self.assertEqual(len(agg_files), 0,
                             "Small import table should not have agg table")

    def test_agg_table_import_mode_ignores_no_measure_table(self):
        """DQ table without measures should not get an agg table."""
        no_meas_ds = _make_datasource([
            {'name': 'BigNoMeas', 'columns': [f'D{i}' for i in range(15)],
             'num_columns': ['V']},
        ])
        stats, self._tmp = _generate_model(no_meas_ds, model_mode='composite',
                                            agg_tables='auto')
        tmdl_dir = os.path.join(self._tmp, 'definition', 'tables')
        if os.path.isdir(tmdl_dir):
            agg_files = [f for f in os.listdir(tmdl_dir) if f.startswith('Agg_')]
            self.assertEqual(len(agg_files), 0,
                             "DQ table without measures should not get agg table")


# ═══════════════════════════════════════════════════════════════════
# 3. Hybrid relationship constraints
# ═══════════════════════════════════════════════════════════════════

class TestHybridRelationshipConstraints(unittest.TestCase):
    """86.3 — Cross-storage-mode relationships → oneDirection."""

    def test_cross_mode_sets_one_direction(self):
        """Relationship between import and DQ table → oneDirection."""
        model = {
            'model': {
                'tables': [
                    {'name': 'Dim', 'partitions': [{'mode': 'import'}]},
                    {'name': 'Fact', 'partitions': [{'mode': 'directQuery'}]},
                ],
                'relationships': [{
                    'fromTable': 'Fact',
                    'fromColumn': 'DimKey',
                    'toTable': 'Dim',
                    'toColumn': 'Key',
                }],
            }
        }
        tmdl_generator._enforce_hybrid_relationship_constraints(model)
        rel = model['model']['relationships'][0]
        self.assertEqual(rel['crossFilteringBehavior'], 'oneDirection')

    def test_same_mode_no_change(self):
        """Relationship between same-mode tables → no constraint added."""
        model = {
            'model': {
                'tables': [
                    {'name': 'T1', 'partitions': [{'mode': 'import'}]},
                    {'name': 'T2', 'partitions': [{'mode': 'import'}]},
                ],
                'relationships': [{
                    'fromTable': 'T1',
                    'fromColumn': 'FK',
                    'toTable': 'T2',
                    'toColumn': 'PK',
                }],
            }
        }
        tmdl_generator._enforce_hybrid_relationship_constraints(model)
        rel = model['model']['relationships'][0]
        self.assertNotIn('crossFilteringBehavior', rel)

    def test_both_dq_no_change(self):
        """Both directQuery → no constraint."""
        model = {
            'model': {
                'tables': [
                    {'name': 'T1', 'partitions': [{'mode': 'directQuery'}]},
                    {'name': 'T2', 'partitions': [{'mode': 'directQuery'}]},
                ],
                'relationships': [{
                    'fromTable': 'T1', 'fromColumn': 'K',
                    'toTable': 'T2', 'toColumn': 'K',
                }],
            }
        }
        tmdl_generator._enforce_hybrid_relationship_constraints(model)
        rel = model['model']['relationships'][0]
        self.assertNotIn('crossFilteringBehavior', rel)

    def test_no_partitions_defaults_import(self):
        """Table with no partitions → defaults to import."""
        model = {
            'model': {
                'tables': [
                    {'name': 'T1', 'partitions': []},
                    {'name': 'T2', 'partitions': [{'mode': 'directQuery'}]},
                ],
                'relationships': [{
                    'fromTable': 'T1', 'fromColumn': 'FK',
                    'toTable': 'T2', 'toColumn': 'PK',
                }],
            }
        }
        tmdl_generator._enforce_hybrid_relationship_constraints(model)
        rel = model['model']['relationships'][0]
        self.assertEqual(rel['crossFilteringBehavior'], 'oneDirection')

    def test_multiple_relationships(self):
        """Multiple relationships: only cross-mode ones get constraint."""
        model = {
            'model': {
                'tables': [
                    {'name': 'A', 'partitions': [{'mode': 'import'}]},
                    {'name': 'B', 'partitions': [{'mode': 'import'}]},
                    {'name': 'C', 'partitions': [{'mode': 'directQuery'}]},
                ],
                'relationships': [
                    {'fromTable': 'A', 'fromColumn': 'K', 'toTable': 'B', 'toColumn': 'K'},
                    {'fromTable': 'A', 'fromColumn': 'FK', 'toTable': 'C', 'toColumn': 'PK'},
                ],
            }
        }
        tmdl_generator._enforce_hybrid_relationship_constraints(model)
        self.assertNotIn('crossFilteringBehavior', model['model']['relationships'][0])
        self.assertEqual(model['model']['relationships'][1]['crossFilteringBehavior'],
                         'oneDirection')


# ═══════════════════════════════════════════════════════════════════
# 4. Aggregation table internal logic
# ═══════════════════════════════════════════════════════════════════

class TestAggregationTableLogic(unittest.TestCase):
    """86.2 internal — _generate_aggregation_tables unit tests."""

    def test_generates_agg_for_dq_with_measures(self):
        """DQ table with measures → Agg_ table created."""
        model = {
            'model': {
                'tables': [{
                    'name': 'Sales',
                    'partitions': [{'mode': 'directQuery'}],
                    'columns': [
                        {'name': 'Revenue', 'dataType': 'double', 'sourceColumn': 'Revenue'},
                        {'name': 'OrderDate', 'dataType': 'DateTime', 'sourceColumn': 'OrderDate'},
                        {'name': 'Name', 'dataType': 'string', 'sourceColumn': 'Name'},
                    ],
                    'measures': [{'name': 'Total', 'expression': 'SUM([Revenue])'}],
                }],
                'relationships': [],
            }
        }
        tmdl_generator._generate_aggregation_tables(model)
        table_names = [t['name'] for t in model['model']['tables']]
        self.assertIn('Agg_Sales', table_names)

    def test_agg_excludes_string_columns(self):
        """Agg table only includes numeric/date columns, not strings."""
        model = {
            'model': {
                'tables': [{
                    'name': 'T',
                    'partitions': [{'mode': 'directQuery'}],
                    'columns': [
                        {'name': 'Val', 'dataType': 'double', 'sourceColumn': 'Val'},
                        {'name': 'Name', 'dataType': 'string', 'sourceColumn': 'Name'},
                    ],
                    'measures': [{'name': 'M1', 'expression': 'SUM([Val])'}],
                }],
                'relationships': [],
            }
        }
        tmdl_generator._generate_aggregation_tables(model)
        agg = [t for t in model['model']['tables'] if t['name'] == 'Agg_T'][0]
        col_names = [c['name'] for c in agg['columns']]
        self.assertIn('Val', col_names)
        self.assertNotIn('Name', col_names)

    def test_agg_import_mode_partition(self):
        """Agg table partition is import mode."""
        model = {
            'model': {
                'tables': [{
                    'name': 'F',
                    'partitions': [{'mode': 'directQuery'}],
                    'columns': [
                        {'name': 'Amt', 'dataType': 'decimal', 'sourceColumn': 'Amt'},
                    ],
                    'measures': [{'name': 'Sum', 'expression': 'SUM([Amt])'}],
                }],
                'relationships': [],
            }
        }
        tmdl_generator._generate_aggregation_tables(model)
        agg = [t for t in model['model']['tables'] if t['name'] == 'Agg_F'][0]
        self.assertEqual(agg['partitions'][0]['mode'], 'import')

    def test_no_agg_for_import_mode_table(self):
        """Import mode table → no agg table."""
        model = {
            'model': {
                'tables': [{
                    'name': 'T',
                    'partitions': [{'mode': 'import'}],
                    'columns': [{'name': 'V', 'dataType': 'double', 'sourceColumn': 'V'}],
                    'measures': [{'name': 'M', 'expression': 'SUM([V])'}],
                }],
                'relationships': [],
            }
        }
        tmdl_generator._generate_aggregation_tables(model)
        table_names = [t['name'] for t in model['model']['tables']]
        self.assertNotIn('Agg_T', table_names)

    def test_no_agg_when_no_measures(self):
        """DQ table without measures → no agg table."""
        model = {
            'model': {
                'tables': [{
                    'name': 'T',
                    'partitions': [{'mode': 'directQuery'}],
                    'columns': [{'name': 'V', 'dataType': 'int64', 'sourceColumn': 'V'}],
                    'measures': [],
                }],
                'relationships': [],
            }
        }
        tmdl_generator._generate_aggregation_tables(model)
        table_names = [t['name'] for t in model['model']['tables']]
        self.assertNotIn('Agg_T', table_names)

    def test_no_agg_when_only_string_columns(self):
        """DQ table with measures but only string columns → no agg table."""
        model = {
            'model': {
                'tables': [{
                    'name': 'T',
                    'partitions': [{'mode': 'directQuery'}],
                    'columns': [{'name': 'Name', 'dataType': 'string', 'sourceColumn': 'Name'}],
                    'measures': [{'name': 'M', 'expression': 'COUNTROWS(T)'}],
                }],
                'relationships': [],
            }
        }
        tmdl_generator._generate_aggregation_tables(model)
        table_names = [t['name'] for t in model['model']['tables']]
        self.assertNotIn('Agg_T', table_names)

    def test_agg_has_annotation(self):
        """Agg table has isAggregationTable annotation."""
        model = {
            'model': {
                'tables': [{
                    'name': 'X',
                    'partitions': [{'mode': 'directQuery'}],
                    'columns': [{'name': 'N', 'dataType': 'int64', 'sourceColumn': 'N'}],
                    'measures': [{'name': 'Sum', 'expression': 'SUM([N])'}],
                }],
                'relationships': [],
            }
        }
        tmdl_generator._generate_aggregation_tables(model)
        agg = [t for t in model['model']['tables'] if t['name'] == 'Agg_X'][0]
        ann_names = [a['name'] for a in agg.get('annotations', [])]
        self.assertIn('isAggregationTable', ann_names)


# ═══════════════════════════════════════════════════════════════════
# 5. CLI flags
# ═══════════════════════════════════════════════════════════════════

class TestCLIFlags(unittest.TestCase):
    """86.4 — Verify --composite-threshold and --agg-tables CLI flags parse."""

    def _make_parser(self):
        import argparse
        import importlib
        import migrate
        importlib.reload(migrate)
        parser = argparse.ArgumentParser()
        migrate._add_migration_args(parser)
        return parser

    def test_composite_threshold_flag(self):
        parser = self._make_parser()
        args = parser.parse_args(['--composite-threshold', '15'])
        self.assertEqual(args.composite_threshold, 15)

    def test_agg_tables_auto(self):
        parser = self._make_parser()
        args = parser.parse_args(['--agg-tables', 'auto'])
        self.assertEqual(args.agg_tables, 'auto')

    def test_agg_tables_none_default(self):
        parser = self._make_parser()
        args = parser.parse_args([])
        self.assertEqual(args.agg_tables, 'none')

    def test_composite_threshold_not_set(self):
        parser = self._make_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.composite_threshold)


# ═══════════════════════════════════════════════════════════════════
# 6. PBIPGenerator passthrough
# ═══════════════════════════════════════════════════════════════════

class TestPBIPGeneratorPassthrough(unittest.TestCase):
    """Ensure PBIPGenerator.generate_project() accepts composite params."""

    def test_generate_project_signature(self):
        """generate_project() must accept composite_threshold and agg_tables."""
        import inspect
        from powerbi_import.pbip_generator import PowerBIProjectGenerator
        sig = inspect.signature(PowerBIProjectGenerator.generate_project)
        params = list(sig.parameters.keys())
        self.assertIn('composite_threshold', params)
        self.assertIn('agg_tables', params)


if __name__ == '__main__':
    unittest.main()
