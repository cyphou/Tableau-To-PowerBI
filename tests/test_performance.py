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

from dax_converter import convert_tableau_formula_to_dax
from m_query_builder import generate_power_query_m
from m_query_builder import generate_power_query_m, inject_m_steps
from m_query_builder import m_transform_rename, m_transform_filter_values
from tmdl_generator import generate_tmdl
from visual_generator import generate_visual_containers
from import_to_powerbi import PowerBIImporter


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
THRESHOLD_TMDL_100_MEASURES = 10.0 # 100 measures TMDL generation
THRESHOLD_IMPORT_PIPELINE = 15.0   # Full import pipeline (small workbook)


class TestDaxConverterPerformance(unittest.TestCase):
    """Performance benchmarks for DAX conversion."""

    def test_single_conversion_speed(self):
        start = time.perf_counter()
        convert_tableau_formula_to_dax('SUM([Sales])')
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, THRESHOLD_DAX_SINGLE,
                        f"Single DAX conversion took {elapsed:.4f}s (threshold: {THRESHOLD_DAX_SINGLE}s)")

    def test_batch_100_formulas(self):
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
        conn = {'type': 'SQL Server', 'details': {'server': 'localhost', 'database': 'test'}}
        table = {'name': 'T1', 'columns': [{'name': 'id', 'datatype': 'integer'}]}
        start = time.perf_counter()
        generate_power_query_m(conn, table)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, THRESHOLD_M_QUERY_SINGLE)

    def test_batch_100_queries(self):
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


class TestTmdl100MeasuresPerformance(unittest.TestCase):
    """Benchmark 100-measure workbook TMDL generation."""

    def test_100_measures(self):
        tables = []
        for t in range(5):
            cols = [{'name': f'col_{t}_{c}', 'datatype': 'string'} for c in range(10)]
            cols[0]['datatype'] = 'integer'
            tables.append({'name': f'Table_{t}', 'columns': cols})
        ds = {
            'name': 'BigDS',
            'connection': {'type': 'SQL Server', 'details': {'server': 's', 'database': 'd'}},
            'connection_map': {},
            'tables': tables,
        }
        # 100 calculations
        calc_map = {}
        for i in range(100):
            calc_map[f'Measure_{i}'] = f'SUM([col_0_{i % 10}])'

        temp_dir = make_temp_dir()
        try:
            start = time.perf_counter()
            generate_tmdl([ds], 'PerfMeasures', calc_map, temp_dir)
            elapsed = time.perf_counter() - start
            self.assertLess(elapsed, THRESHOLD_TMDL_100_MEASURES,
                            f"100-measure TMDL took {elapsed:.2f}s")
        finally:
            cleanup_dir(temp_dir)


class TestImportPipelinePerformance(unittest.TestCase):
    """Benchmark the full import pipeline end-to-end."""

    def _create_source_dir(self, temp_dir, n_worksheets=5, n_tables=3, n_calcs=10):
        """Write extracted JSON files to simulate a small Tableau export."""
        import json as _json

        tables = []
        for t in range(n_tables):
            cols = [{'name': f'col{c}', 'datatype': 'string'} for c in range(8)]
            cols[0]['datatype'] = 'integer'
            cols[1]['datatype'] = 'datetime'
            tables.append({'name': f'Table{t}', 'columns': cols})

        datasources = [{
            'name': 'DS',
            'connection': {'type': 'SQL Server', 'details': {'server': 's', 'database': 'd'}},
            'connection_map': {},
            'tables': tables,
        }]

        worksheets = []
        for i in range(n_worksheets):
            worksheets.append({
                'name': f'Sheet{i}',
                'mark_type': 'bar',
                'fields': [{'name': f'col{j}'} for j in range(3)],
                'mark_encoding': {},
                'filters': [],
                'datasource': 'DS',
            })

        calculations = [
            {'name': f'Calc{i}', 'caption': f'Calc{i}', 'formula': f'SUM([col{i % 8}])'}
            for i in range(n_calcs)
        ]

        files = {
            'datasources.json': datasources,
            'worksheets.json': worksheets,
            'calculations.json': calculations,
            'dashboards.json': [],
            'parameters.json': [],
            'filters.json': [],
            'stories.json': [],
            'actions.json': [],
            'sets.json': [],
            'groups.json': [],
            'bins.json': [],
            'hierarchies.json': [],
            'sort_orders.json': [],
            'aliases.json': [],
            'custom_sql.json': [],
            'user_filters.json': [],
        }
        for fname, data in files.items():
            with open(os.path.join(temp_dir, fname), 'w', encoding='utf-8') as f:
                _json.dump(data, f)

    def test_full_pipeline_small_workbook(self):
        """Full import pipeline for a small workbook should be fast."""
        src_dir = make_temp_dir()
        out_dir = make_temp_dir()
        try:
            self._create_source_dir(src_dir)
            importer = PowerBIImporter(source_dir=src_dir)
            start = time.perf_counter()
            importer.import_all(
                generate_pbip=True,
                report_name='PerfTest',
                output_dir=out_dir,
            )
            elapsed = time.perf_counter() - start
            self.assertLess(elapsed, THRESHOLD_IMPORT_PIPELINE,
                            f"Full pipeline took {elapsed:.2f}s")
        finally:
            cleanup_dir(src_dir)
            cleanup_dir(out_dir)


if __name__ == '__main__':
    unittest.main()
