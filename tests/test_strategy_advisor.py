"""
Tests for Migration Strategy Advisor (powerbi_import.strategy_advisor).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.strategy_advisor import (
    StrategySignal, StrategyRecommendation,
    recommend_strategy, print_recommendation,
    _classify_calculations,
)


# ── Helper ──────────────────────────────────────────────────────────

def _make_extracted(conn_type='Excel', tables=None, calculations=None,
                    custom_sql=None):
    tables = tables or [{'name': 'T1', 'columns': [{'name': 'c1', 'datatype': 'string'}]}]
    return {
        'datasources': [{'name': 'DS1', 'connection': {'type': conn_type},
                          'tables': tables, 'columns': []}],
        'calculations': calculations or [],
        'custom_sql': custom_sql or [],
    }


# ═══════════════════════════════════════════════════════════════════
#  Data class tests
# ═══════════════════════════════════════════════════════════════════

class TestStrategyRecommendation(unittest.TestCase):
    def test_import_connection_mode(self):
        rec = StrategyRecommendation(strategy='import')
        self.assertEqual(rec.connection_mode, 'Import')

    def test_directquery_connection_mode(self):
        rec = StrategyRecommendation(strategy='directquery')
        self.assertEqual(rec.connection_mode, 'DirectQuery')

    def test_composite_connection_mode(self):
        rec = StrategyRecommendation(strategy='composite')
        self.assertIn('Composite', rec.connection_mode)


# ═══════════════════════════════════════════════════════════════════
#  Simple workbook → Import
# ═══════════════════════════════════════════════════════════════════

class TestSimpleWorkbook(unittest.TestCase):
    def test_sql_server_import(self):
        ext = _make_extracted('SQL Server')
        rec = recommend_strategy(ext)
        self.assertEqual(rec.strategy, 'import')

    def test_excel_import(self):
        ext = _make_extracted('Excel')
        rec = recommend_strategy(ext)
        self.assertEqual(rec.strategy, 'import')

    def test_csv_import(self):
        ext = _make_extracted('CSV')
        rec = recommend_strategy(ext)
        self.assertEqual(rec.strategy, 'import')

    def test_few_tables(self):
        tables = [{'name': f'T{i}', 'columns': [{'name': 'c1'}]} for i in range(3)]
        ext = _make_extracted('Excel', tables=tables)
        rec = recommend_strategy(ext)
        self.assertEqual(rec.strategy, 'import')


# ═══════════════════════════════════════════════════════════════════
#  Complex workbook → DirectQuery
# ═══════════════════════════════════════════════════════════════════

class TestComplexWorkbook(unittest.TestCase):
    def test_bigquery_directquery(self):
        # Need enough tables to avoid the few_tables import signal outweighing
        tables = [{'name': f'T{i}', 'columns': [{'name': f'c{j}'} for j in range(10)]}
                  for i in range(8)]
        ext = _make_extracted('BigQuery', tables=tables)
        rec = recommend_strategy(ext)
        self.assertIn(rec.strategy, ('directquery', 'composite'))

    def test_custom_sql_signal(self):
        ext = _make_extracted('Excel', custom_sql=[{'query': 'SELECT 1'}])
        rec = recommend_strategy(ext)
        dq_signal = [s for s in rec.signals if s.name == 'custom_sql']
        self.assertEqual(len(dq_signal), 1)
        self.assertEqual(dq_signal[0].favours, 'directquery')

    def test_many_tables(self):
        tables = [{'name': f'T{i}', 'columns': [{'name': 'c1'}]} for i in range(10)]
        ext = _make_extracted('Excel', tables=tables)
        rec = recommend_strategy(ext)
        many_sig = [s for s in rec.signals if s.name == 'many_tables']
        self.assertEqual(len(many_sig), 1)

    def test_many_columns(self):
        tables = [{'name': 'T1', 'columns': [{'name': f'c{i}'} for i in range(80)]}]
        ext = _make_extracted('Excel', tables=tables)
        rec = recommend_strategy(ext)
        col_sig = [s for s in rec.signals if s.name == 'many_columns']
        self.assertEqual(len(col_sig), 1)

    def test_lod_complex_calcs(self):
        calcs = [{'name': 'L', 'formula': '{FIXED [R] : SUM([S])}', 'role': 'measure'}]
        ext = _make_extracted('Excel', calculations=calcs)
        rec = recommend_strategy(ext)
        cc = [s for s in rec.signals if s.name == 'complex_calcs']
        self.assertEqual(len(cc), 1)

    def test_prep_flow_signal(self):
        ext = _make_extracted('Excel')
        rec = recommend_strategy(ext, prep_flow=True)
        pf = [s for s in rec.signals if s.name == 'prep_flow']
        self.assertEqual(len(pf), 1)
        self.assertEqual(pf[0].favours, 'directquery')

    def test_multiple_complex_signals_directquery(self):
        tables = [{'name': f'T{i}', 'columns': [{'name': f'c{j}'} for j in range(20)]}
                  for i in range(10)]
        calcs = [
            {'name': 'L', 'formula': '{FIXED [R] : SUM([S])}', 'role': 'measure'},
            {'name': 'R', 'formula': 'REGEXP_MATCH([N], "^A")', 'role': 'measure'},
        ]
        ext = _make_extracted('BigQuery', tables=tables, calculations=calcs,
                              custom_sql=[{'query': 'SELECT *'}])
        rec = recommend_strategy(ext, prep_flow=True)
        self.assertEqual(rec.strategy, 'directquery')


# ═══════════════════════════════════════════════════════════════════
#  Mixed workbook → Composite
# ═══════════════════════════════════════════════════════════════════

class TestMixedWorkbook(unittest.TestCase):
    def test_simple_with_custom_sql_both(self):
        ext = _make_extracted('Excel', custom_sql=[{'query': 'SELECT 1'}])
        rec = recommend_strategy(ext)
        # Close scores → composite
        self.assertIn(rec.strategy, ('import', 'composite'))

    def test_tight_margin(self):
        ext = _make_extracted('Excel')
        rec = recommend_strategy(ext, margin=100)
        self.assertEqual(rec.strategy, 'composite')


# ═══════════════════════════════════════════════════════════════════
#  Classification and edge cases
# ═══════════════════════════════════════════════════════════════════

class TestClassifyCalculations(unittest.TestCase):
    def test_measure_with_aggregation(self):
        calcs = [{'name': 'Total', 'formula': 'SUM([Amount])', 'role': 'measure'}]
        cols, measures = _classify_calculations(calcs)
        self.assertEqual(len(measures), 1)
        self.assertEqual(len(cols), 0)

    def test_calc_column_dimension(self):
        calcs = [{'name': 'Status', 'formula': '[IsActive]', 'role': 'dimension',
                  'datatype': 'string'}]
        cols, measures = _classify_calculations(calcs)
        self.assertEqual(len(cols), 1)
        self.assertEqual(len(measures), 0)

    def test_empty_formula_skipped(self):
        calcs = [{'name': 'X', 'formula': '', 'role': 'measure'}]
        cols, measures = _classify_calculations(calcs)
        self.assertEqual(len(cols) + len(measures), 0)


class TestEdgeCases(unittest.TestCase):
    def test_empty_extracted(self):
        ext = {'datasources': [], 'calculations': [], 'custom_sql': []}
        rec = recommend_strategy(ext)
        self.assertIn(rec.strategy, ('import', 'composite'))

    def test_no_datasources(self):
        ext = {'datasources': [], 'calculations': [], 'custom_sql': []}
        rec = recommend_strategy(ext)
        self.assertIsNotNone(rec.strategy)

    def test_unknown_connector(self):
        ext = _make_extracted('UnknownDB')
        rec = recommend_strategy(ext)
        # No signal from an unknown connector
        conn_signals = [s for s in rec.signals if 'connector' in s.name]
        self.assertEqual(len(conn_signals), 0)

    def test_custom_thresholds(self):
        tables = [{'name': f'T{i}', 'columns': [{'name': 'c1'}]} for i in range(3)]
        ext = _make_extracted('Excel', tables=tables)
        rec = recommend_strategy(ext, table_threshold=2)
        many = [s for s in rec.signals if s.name == 'many_tables']
        self.assertEqual(len(many), 1)


class TestPrintRecommendation(unittest.TestCase):
    def test_print_import(self):
        rec = recommend_strategy(_make_extracted('Excel'))
        # Should not raise
        print_recommendation(rec)

    def test_print_directquery(self):
        ext = _make_extracted('BigQuery', custom_sql=[{'q': 'SELECT 1'}])
        rec = recommend_strategy(ext, prep_flow=True)
        print_recommendation(rec)

    def test_long_description_truncated(self):
        sig = StrategySignal('test', 'A' * 100, 'import', weight=3)
        rec = StrategyRecommendation(
            strategy='import', import_score=5, directquery_score=0,
            signals=[sig], summary='test')
        print_recommendation(rec)


if __name__ == '__main__':
    unittest.main()
