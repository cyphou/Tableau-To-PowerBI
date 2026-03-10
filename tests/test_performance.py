"""
Performance benchmark tests for the migration pipeline.

Measures execution time and throughput for key operations
to detect performance regressions.
"""

import unittest
import sys
import os
import time
import copy
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from tests.conftest import SAMPLE_DATASOURCE, SAMPLE_EXTRACTED, make_temp_dir, cleanup_dir


# ── Performance thresholds (seconds) ─────────────────────────────────
# These are generous limits — real execution should be much faster.
# They exist to catch extreme regressions, not micro-optimizations.

THRESHOLD_DAX_SINGLE = 0.05        # Single DAX conversion
THRESHOLD_DAX_BATCH_100 = 2.0      # 100 DAX conversions
THRESHOLD_M_QUERY_SINGLE = 0.05    # Single M query generation
THRESHOLD_M_QUERY_BATCH_100 = 2.0  # 100 M queries
THRESHOLD_TMDL_SMALL = 5.0         # Small model TMDL generation
THRESHOLD_TMDL_LARGE = 30.0        # Large model (50 tables) TMDL generation
THRESHOLD_VISUAL_BATCH_20 = 2.0    # 20 visual containers


class TestDaxConverterPerformance(unittest.TestCase):
    """Performance benchmarks for DAX conversion."""

    def test_single_conversion_speed(self):
        from dax_converter import convert_tableau_formula_to_dax
        start = time.perf_counter()
        convert_tableau_formula_to_dax('SUM([Sales])')
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, THRESHOLD_DAX_SINGLE,
                        f"Single DAX conversion took {elapsed:.4f}s (threshold: {THRESHOLD_DAX_SINGLE}s)")

    def test_batch_100_formulas(self):
        from dax_converter import convert_tableau_formula_to_dax
        formulas = [
            'SUM([Amount])',
            'IF [Status] = "Active" THEN 1 ELSE 0 END',
            'DATEDIFF("month", [Start], [End])',
            '{FIXED [Customer] : SUM([Sales])}',
            'COUNTD([OrderID])',
            'RUNNING_SUM(SUM([Sales]))',
            'RANK(SUM([Revenue]))',
            'CONTAINS([Name], "test")',
            'ZN([Value])',
            'DATETRUNC("month", [Date])',
        ] * 10  # 100 formulas

        start = time.perf_counter()
        for f in formulas:
            convert_tableau_formula_to_dax(f)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, THRESHOLD_DAX_BATCH_100,
                        f"100 DAX conversions took {elapsed:.4f}s (threshold: {THRESHOLD_DAX_BATCH_100}s)")

    def test_complex_nested_formula(self):
        from dax_converter import convert_tableau_formula_to_dax
        complex_formula = (
            'IF {FIXED [Customer] : SUM([Sales])} > 1000 '
            'THEN "High" '
            'ELSEIF {FIXED [Customer] : SUM([Sales])} > 500 '
            'THEN "Medium" '
            'ELSE "Low" END'
        )
        start = time.perf_counter()
        for _ in range(10):
            convert_tableau_formula_to_dax(complex_formula)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0)


class TestMQueryPerformance(unittest.TestCase):
    """Performance benchmarks for M query generation."""

    def test_single_query_speed(self):
        from m_query_builder import generate_power_query_m
        conn = {'type': 'SQL Server', 'details': {'server': 'localhost', 'database': 'test'}}
        table = {'name': 'T1', 'columns': [{'name': 'id', 'datatype': 'integer'}]}
        start = time.perf_counter()
        generate_power_query_m(conn, table)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, THRESHOLD_M_QUERY_SINGLE)

    def test_batch_100_queries(self):
        from m_query_builder import generate_power_query_m
        connectors = [
            ('SQL Server', {'server': 'srv', 'database': 'db'}),
            ('PostgreSQL', {'server': 'srv', 'port': '5432', 'database': 'db'}),
            ('CSV', {'filename': 'data.csv', 'delimiter': ','}),
            ('BigQuery', {'project': 'proj', 'dataset': 'ds'}),
            ('Snowflake', {'server': 'acc.snowflake.com', 'database': 'DB', 'warehouse': 'WH'}),
        ] * 20  # 100 queries

        cols = [{'name': f'col{i}', 'datatype': 'string'} for i in range(5)]
        start = time.perf_counter()
        for conn_type, details in connectors:
            conn = {'type': conn_type, 'details': details}
            generate_power_query_m(conn, {'name': 'T1', 'columns': cols})
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, THRESHOLD_M_QUERY_BATCH_100)

    def test_inject_steps_performance(self):
        from m_query_builder import generate_power_query_m, inject_m_steps
        from m_query_builder import m_transform_rename, m_transform_filter_values
        conn = {'type': 'CSV', 'details': {'filename': 'f.csv', 'delimiter': ','}}
        cols = [{'name': f'col{i}', 'datatype': 'string'} for i in range(10)]
        m_query = generate_power_query_m(conn, {'name': 'T1', 'columns': cols})

        steps = []
        for i in range(20):
            steps.append(m_transform_rename({f'col{i}': f'renamed_{i}'}))

        start = time.perf_counter()
        result = inject_m_steps(m_query, steps)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0)
        self.assertIn('renamed_', result)


class TestTmdlPerformance(unittest.TestCase):
    """Performance benchmarks for TMDL generation."""

    def _make_datasource(self, n_tables=5, n_cols=10):
        """Create a datasource with multiple tables."""
        tables = []
        for t in range(n_tables):
            cols = [{'name': f'col_{t}_{c}', 'datatype': 'string'} for c in range(n_cols)]
            cols[0]['datatype'] = 'integer'
            if n_cols > 1:
                cols[1]['datatype'] = 'datetime'
            tables.append({'name': f'Table_{t}', 'columns': cols})
        return {
            'name': f'DS_{n_tables}',
            'connection': {'type': 'SQL Server', 'details': {'server': 'srv', 'database': 'db'}},
            'connection_map': {},
            'tables': tables,
        }

    def test_small_model_generation(self):
        from tmdl_generator import generate_tmdl
        temp_dir = make_temp_dir()
        try:
            ds = self._make_datasource(n_tables=3, n_cols=5)
            start = time.perf_counter()
            generate_tmdl([ds], 'PerfSmall', {}, temp_dir)
            elapsed = time.perf_counter() - start
            self.assertLess(elapsed, THRESHOLD_TMDL_SMALL,
                            f"Small TMDL generation took {elapsed:.2f}s")
        finally:
            cleanup_dir(temp_dir)

    def test_large_model_generation(self):
        from tmdl_generator import generate_tmdl
        temp_dir = make_temp_dir()
        try:
            ds = self._make_datasource(n_tables=50, n_cols=15)
            start = time.perf_counter()
            generate_tmdl([ds], 'PerfLarge', {}, temp_dir)
            elapsed = time.perf_counter() - start
            self.assertLess(elapsed, THRESHOLD_TMDL_LARGE,
                            f"Large TMDL generation took {elapsed:.2f}s")
        finally:
            cleanup_dir(temp_dir)


class TestVisualPerformance(unittest.TestCase):
    """Performance benchmarks for visual container generation."""

    def test_batch_20_visuals(self):
        from visual_generator import generate_visual_containers
        worksheets = [
            {
                'name': f'Sheet {i}',
                'mark_type': 'bar',
                'columns': [
                    {'name': f'Dim{i}', 'type': 'dimension'},
                    {'name': f'Meas{i}', 'type': 'measure'},
                ],
            }
            for i in range(20)
        ]
        temp_dir = make_temp_dir()
        try:
            start = time.perf_counter()
            generate_visual_containers(worksheets, temp_dir)
            elapsed = time.perf_counter() - start
            self.assertLess(elapsed, THRESHOLD_VISUAL_BATCH_20)
        finally:
            cleanup_dir(temp_dir)


if __name__ == '__main__':
    unittest.main()
