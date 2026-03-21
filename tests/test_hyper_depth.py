"""
Hyper File Depth — Tests for CSV export, datasource enrichment,
relationship inference, strategy advisor integration, and --check-hyper CLI.
"""

import argparse
import csv
import os
import shutil
import sys
import tempfile
import unittest

# Ensure tableau_export is importable
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_TAB = os.path.join(_ROOT, 'tableau_export')
if _TAB not in sys.path:
    sys.path.insert(0, _TAB)

from hyper_reader import (
    export_hyper_to_csv,
    generate_m_for_hyper_table,
    infer_hyper_relationships,
    generate_m_inline_table,
    generate_m_csv_reference,
    INLINE_ROW_THRESHOLD,
)
from datasource_extractor import enrich_datasource_from_hyper


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _sample_table(name='Orders', cols=None, rows=None, row_count=None, stats=None):
    """Build a minimal Hyper table dict."""
    if cols is None:
        cols = [
            {'name': 'OrderID', 'hyper_type': 'integer'},
            {'name': 'Amount', 'hyper_type': 'double'},
            {'name': 'CustomerID', 'hyper_type': 'integer'},
        ]
    if rows is None:
        rows = [
            {'OrderID': 1, 'Amount': 99.5, 'CustomerID': 10},
            {'OrderID': 2, 'Amount': 50.0, 'CustomerID': 20},
        ]
    return {
        'table': name,
        'columns': cols,
        'column_count': len(cols),
        'sample_rows': rows,
        'sample_row_count': len(rows),
        'row_count': row_count if row_count is not None else len(rows),
        'column_stats': stats or {},
    }


def _sample_datasource(tables=None):
    """Build a minimal datasource dict."""
    if tables is None:
        tables = [{
            'name': 'Orders',
            'columns': [
                {'name': 'OrderID', 'datatype': 'string'},
                {'name': 'Amount', 'datatype': 'string'},
                {'name': 'CustomerID', 'datatype': 'string'},
            ],
        }]
    return {
        'name': 'DS1',
        'caption': 'DS1',
        'connection': {'type': 'hyper'},
        'connection_map': {},
        'tables': tables,
        'calculations': [],
        'columns': [],
        'relationships': [],
    }


# ═══════════════════════════════════════════════════════════════════
# 1. CSV Export
# ═══════════════════════════════════════════════════════════════════

class TestCsvExport(unittest.TestCase):
    """Verify export_hyper_to_csv writes valid CSV files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_basic_export(self):
        tbl = _sample_table()
        path = export_hyper_to_csv(tbl, self.tmp)
        self.assertIsNotNone(path)
        self.assertTrue(os.path.isfile(path))
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(header, ['OrderID', 'Amount', 'CustomerID'])
            rows = list(reader)
            self.assertEqual(len(rows), 2)

    def test_custom_filename(self):
        tbl = _sample_table()
        path = export_hyper_to_csv(tbl, self.tmp, csv_filename='my_data.csv')
        self.assertTrue(path.endswith('my_data.csv'))

    def test_empty_rows_returns_none(self):
        tbl = _sample_table(rows=[])
        result = export_hyper_to_csv(tbl, self.tmp)
        self.assertIsNone(result)

    def test_no_columns_returns_none(self):
        tbl = _sample_table(cols=[])
        result = export_hyper_to_csv(tbl, self.tmp)
        self.assertIsNone(result)

    def test_sanitises_filename(self):
        tbl = _sample_table(name='schema:table<1>')
        path = export_hyper_to_csv(tbl, self.tmp)
        self.assertIsNotNone(path)
        basename = os.path.basename(path)
        self.assertNotIn(':', basename)
        self.assertNotIn('<', basename)

    def test_creates_subdirectory(self):
        sub = os.path.join(self.tmp, 'nested', 'dir')
        tbl = _sample_table()
        path = export_hyper_to_csv(tbl, sub)
        self.assertTrue(os.path.isfile(path))


# ═══════════════════════════════════════════════════════════════════
# 2. generate_m_for_hyper_table with output_dir
# ═══════════════════════════════════════════════════════════════════

class TestMGenerationWithCsvExport(unittest.TestCase):
    """Verify M generation exports CSV for large tables."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_inline_under_threshold(self):
        tbl = _sample_table(row_count=10)
        m = generate_m_for_hyper_table(tbl, output_dir=self.tmp)
        self.assertIn('#table(', m)
        # No CSV file should be created
        csvs = [f for f in os.listdir(self.tmp) if f.endswith('.csv')]
        self.assertEqual(len(csvs), 0)

    def test_csv_over_threshold(self):
        tbl = _sample_table(row_count=INLINE_ROW_THRESHOLD + 100)
        m = generate_m_for_hyper_table(tbl, output_dir=self.tmp)
        self.assertIn('Csv.Document', m)
        # CSV file should exist
        csvs = [f for f in os.listdir(self.tmp) if f.endswith('.csv')]
        self.assertEqual(len(csvs), 1)

    def test_csv_without_output_dir(self):
        """When no output_dir, should still return Csv.Document M."""
        tbl = _sample_table(row_count=INLINE_ROW_THRESHOLD + 100)
        m = generate_m_for_hyper_table(tbl)
        self.assertIn('Csv.Document', m)

    def test_custom_row_limit(self):
        tbl = _sample_table(row_count=5)
        m = generate_m_for_hyper_table(tbl, row_limit=3, output_dir=self.tmp)
        self.assertIn('Csv.Document', m)


# ═══════════════════════════════════════════════════════════════════
# 3. Relationship Inference
# ═══════════════════════════════════════════════════════════════════

class TestRelationshipInference(unittest.TestCase):
    """Verify infer_hyper_relationships finds FK candidates."""

    def test_matching_column_names(self):
        orders = _sample_table('Orders', row_count=1000, stats={
            'CustomerID': {'distinct_count': 200},
        })
        customers = _sample_table(
            'Customers',
            cols=[
                {'name': 'CustomerID', 'hyper_type': 'integer'},
                {'name': 'Name', 'hyper_type': 'text'},
            ],
            rows=[],
            row_count=50,
            stats={'CustomerID': {'distinct_count': 50}},
        )
        rels = infer_hyper_relationships([orders, customers])
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]['cardinality'], 'manyToOne')
        # The smaller distinct count side should be the "to" (PK)
        self.assertEqual(rels[0]['to_table'], 'Customers')

    def test_no_shared_columns(self):
        t1 = _sample_table('A', cols=[{'name': 'X', 'hyper_type': 'int'}])
        t2 = _sample_table('B', cols=[{'name': 'Y', 'hyper_type': 'int'}])
        rels = infer_hyper_relationships([t1, t2])
        self.assertEqual(len(rels), 0)

    def test_single_table(self):
        rels = infer_hyper_relationships([_sample_table()])
        self.assertEqual(len(rels), 0)

    def test_empty_list(self):
        rels = infer_hyper_relationships([])
        self.assertEqual(len(rels), 0)

    def test_multiple_shared_columns(self):
        t1 = _sample_table('Fact', cols=[
            {'name': 'ProductID', 'hyper_type': 'integer'},
            {'name': 'RegionID', 'hyper_type': 'integer'},
        ], row_count=10000, stats={
            'ProductID': {'distinct_count': 100},
            'RegionID': {'distinct_count': 20},
        })
        t2 = _sample_table('DimProduct', cols=[
            {'name': 'ProductID', 'hyper_type': 'integer'},
        ], row_count=100, stats={
            'ProductID': {'distinct_count': 100},
        })
        t3 = _sample_table('DimRegion', cols=[
            {'name': 'RegionID', 'hyper_type': 'integer'},
        ], row_count=20, stats={
            'RegionID': {'distinct_count': 20},
        })
        rels = infer_hyper_relationships([t1, t2, t3])
        self.assertEqual(len(rels), 2)

    def test_deduplication(self):
        """Same column pair should not produce duplicate relationships."""
        t1 = _sample_table('A', cols=[
            {'name': 'ID', 'hyper_type': 'integer'},
        ], row_count=100, stats={'ID': {'distinct_count': 100}})
        t2 = _sample_table('B', cols=[
            {'name': 'ID', 'hyper_type': 'integer'},
        ], row_count=50, stats={'ID': {'distinct_count': 50}})
        rels = infer_hyper_relationships([t1, t2])
        self.assertEqual(len(rels), 1)

    def test_fallback_to_row_count(self):
        """When no stats, use row count for direction."""
        t1 = _sample_table('Big', cols=[
            {'name': 'Key', 'hyper_type': 'integer'},
        ], row_count=1000)
        t2 = _sample_table('Small', cols=[
            {'name': 'Key', 'hyper_type': 'integer'},
        ], row_count=10)
        rels = infer_hyper_relationships([t1, t2])
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]['from_table'], 'Big')
        self.assertEqual(rels[0]['to_table'], 'Small')


# ═══════════════════════════════════════════════════════════════════
# 4. Datasource Enrichment
# ═══════════════════════════════════════════════════════════════════

class TestDatasourceEnrichment(unittest.TestCase):
    """Verify enrich_datasource_from_hyper bridges Hyper data to datasource."""

    def test_enriches_row_count(self):
        ds = _sample_datasource()
        hyper_tables = [_sample_table('Orders', row_count=5000)]
        enrich_datasource_from_hyper(ds, hyper_tables)
        self.assertEqual(ds['tables'][0].get('hyper_row_count'), 5000)
        self.assertTrue(ds.get('hyper_enriched'))

    def test_refines_column_type(self):
        ds = _sample_datasource()
        hyper_tables = [_sample_table('Orders')]
        enrich_datasource_from_hyper(ds, hyper_tables)
        # OrderID was 'string' in ds, should be refined to 'integer' from hyper
        col = ds['tables'][0]['columns'][0]
        self.assertEqual(col['datatype'], 'integer')

    def test_preserves_non_string_types(self):
        ds = _sample_datasource(tables=[{
            'name': 'Orders',
            'columns': [{'name': 'Amount', 'datatype': 'real'}],
        }])
        hyper_tables = [_sample_table('Orders')]
        enrich_datasource_from_hyper(ds, hyper_tables)
        # 'real' should not be overwritten
        self.assertEqual(ds['tables'][0]['columns'][0]['datatype'], 'real')

    def test_empty_hyper_tables(self):
        ds = _sample_datasource()
        enrich_datasource_from_hyper(ds, [])
        self.assertFalse(ds.get('hyper_enriched', False))

    def test_schema_prefix_normalisation(self):
        """Table 'Extract.Extract' in hyper should match 'Extract' in datasource."""
        ds = _sample_datasource(tables=[{
            'name': 'Extract',
            'columns': [{'name': 'Col1', 'datatype': 'string'}],
        }])
        hyper_tables = [{
            'table': 'Extract.Extract',
            'columns': [{'name': 'Col1', 'hyper_type': 'bigint'}],
            'row_count': 100,
            'column_stats': {},
        }]
        enrich_datasource_from_hyper(ds, hyper_tables)
        self.assertEqual(ds['tables'][0].get('hyper_row_count'), 100)
        self.assertEqual(ds['tables'][0]['columns'][0]['datatype'], 'integer')

    def test_attaches_column_stats(self):
        ds = _sample_datasource()
        stats = {'OrderID': {'distinct_count': 500, 'min': 1, 'max': 500}}
        hyper_tables = [_sample_table('Orders', stats=stats)]
        enrich_datasource_from_hyper(ds, hyper_tables)
        self.assertIn('hyper_column_stats', ds['tables'][0])
        self.assertEqual(ds['tables'][0]['hyper_column_stats']['OrderID']['distinct_count'], 500)

    def test_total_rows_metadata(self):
        ds = _sample_datasource()
        hyper_tables = [
            _sample_table('Orders', row_count=1000),
            _sample_table('Products', row_count=200),
        ]
        enrich_datasource_from_hyper(ds, hyper_tables)
        self.assertEqual(ds['hyper_total_rows'], 1200)
        self.assertEqual(ds['hyper_table_count'], 2)


# ═══════════════════════════════════════════════════════════════════
# 5. Strategy Advisor — Hyper Signal
# ═══════════════════════════════════════════════════════════════════

class TestStrategyAdvisorHyper(unittest.TestCase):
    """Verify strategy advisor uses Hyper row counts."""

    def test_large_hyper_favours_directquery(self):
        from powerbi_import.strategy_advisor import recommend_strategy
        extracted = {
            'datasources': [{'connection': {'type': 'hyper'}, 'tables': [],
                             'hyper_total_rows': 15_000_000}],
            'calculations': [],
            'custom_sql': [],
        }
        rec = recommend_strategy(extracted)
        signal_names = [s.name for s in rec.signals]
        self.assertIn('hyper_large', signal_names)

    def test_small_hyper_favours_import(self):
        from powerbi_import.strategy_advisor import recommend_strategy
        extracted = {
            'datasources': [{'connection': {'type': 'hyper'}, 'tables': [
                {'name': 'T1', 'columns': [], 'hyper_row_count': 5000}
            ]}],
            'calculations': [],
            'custom_sql': [],
        }
        rec = recommend_strategy(extracted)
        signal_names = [s.name for s in rec.signals]
        self.assertIn('hyper_small', signal_names)

    def test_no_hyper_no_signal(self):
        from powerbi_import.strategy_advisor import recommend_strategy
        extracted = {
            'datasources': [{'connection': {'type': 'sqlserver'},
                             'tables': [{'name': 'T', 'columns': []}]}],
            'calculations': [],
            'custom_sql': [],
        }
        rec = recommend_strategy(extracted)
        signal_names = [s.name for s in rec.signals]
        hyper_signals = [s for s in signal_names if s.startswith('hyper_')]
        self.assertEqual(len(hyper_signals), 0)

    def test_hyper_files_key(self):
        """Hyper row counts from extracted hyper_files should be detected."""
        from powerbi_import.strategy_advisor import recommend_strategy
        extracted = {
            'datasources': [{'connection': {'type': 'hyper'}, 'tables': []}],
            'calculations': [],
            'custom_sql': [],
            'hyper_files': [{'tables': [{'row_count': 2_000_000}]}],
        }
        rec = recommend_strategy(extracted)
        signal_names = [s.name for s in rec.signals]
        self.assertIn('hyper_medium', signal_names)


# ═══════════════════════════════════════════════════════════════════
# 6. CLI --check-hyper flag
# ═══════════════════════════════════════════════════════════════════

class TestCheckHyperCli(unittest.TestCase):
    """Verify --check-hyper flag is accepted."""

    def test_flag_parsed(self):
        sys.path.insert(0, _ROOT)
        import importlib
        import migrate
        importlib.reload(migrate)
        parser = argparse.ArgumentParser()
        migrate._add_enterprise_args(parser)
        args = parser.parse_args(['--check-hyper'])
        self.assertTrue(args.check_hyper)

    def test_flag_default_false(self):
        sys.path.insert(0, _ROOT)
        import importlib
        import migrate
        importlib.reload(migrate)
        parser = argparse.ArgumentParser()
        migrate._add_enterprise_args(parser)
        args = parser.parse_args([])
        self.assertFalse(args.check_hyper)


if __name__ == '__main__':
    unittest.main()
