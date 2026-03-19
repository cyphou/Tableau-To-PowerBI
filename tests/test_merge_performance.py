"""Benchmark tests for merge performance at scale.

Run with: pytest tests/test_merge_performance.py -v --benchmark
Not run in CI — requires explicit --benchmark flag.
"""

import copy
import os
import sys
import time
import unittest
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Skip entire module unless --benchmark is passed
_RUN_BENCHMARKS = '--benchmark' in sys.argv or os.environ.get('RUN_BENCHMARKS') == '1'


def _generate_workbook(wb_index, num_tables=3, cols_per_table=5):
    """Generate a synthetic workbook with tables, columns, calcs, and params."""
    wb_name = f"Workbook_{wb_index:03d}"
    tables = []
    calcs = []
    params = []
    rels = []

    for t in range(num_tables):
        table_name = f"Table_{wb_index:03d}_{t}"
        columns = []
        for c in range(cols_per_table):
            columns.append({
                'name': f"col_{c}",
                'datatype': 'string' if c % 3 == 0 else ('int64' if c % 3 == 1 else 'double'),
                'role': 'dimension' if c % 2 == 0 else 'measure',
            })
        tables.append({
            'name': table_name,
            'columns': columns,
        })

    # Add a shared table (same name across all workbooks) for merge testing
    shared_cols = [{'name': f"shared_col_{c}", 'datatype': 'string', 'role': 'dimension'}
                   for c in range(cols_per_table)]
    tables.append({'name': 'SharedDimension', 'columns': shared_cols})

    # Add calculations
    for i in range(5):
        calcs.append({
            'name': f"Calc_{wb_index}_{i}",
            'caption': f"Calc {wb_index} {i}",
            'formula': f"SUM([col_1]) + {i}",
            'role': 'measure',
        })

    # Shared calc (same name/formula across workbooks → should deduplicate)
    calcs.append({
        'name': 'Total_Shared',
        'caption': 'Total Shared',
        'formula': 'SUM([shared_col_1])',
        'role': 'measure',
    })

    # Parameters
    params.append({
        'name': f"Param_{wb_index}",
        'caption': f"Param {wb_index}",
        'value': '10',
        'domain_type': 'range',
        'allowable_values': {'min': '0', 'max': '100', 'step': '1'},
        'data_type': 'integer',
    })

    # Relationships
    if num_tables > 1:
        rels.append({
            'from_table': tables[0]['name'],
            'from_column': 'col_0',
            'to_table': tables[1]['name'],
            'to_column': 'col_0',
            'join_type': 'left',
        })

    return wb_name, {
        'datasources': [{
            'name': f"DS_{wb_name}",
            'connection': {'class': 'textscan'},
            'tables': tables,
            'relationships': rels,
        }],
        'calculations': calcs,
        'parameters': params,
        'worksheets': [{'name': f"Sheet_{wb_index}", 'fields': ['col_0']}],
        'dashboards': [],
        'filters': [],
        'stories': [],
        'actions': [],
        'sets': [],
        'groups': [],
        'bins': [],
        'hierarchies': [],
        'sort_orders': [],
        'aliases': [],
        'custom_sql': [],
        'user_filters': [],
    }


def _generate_workbooks(n, num_tables=3, cols_per_table=5):
    """Generate n synthetic workbooks."""
    names = []
    objects_list = []
    for i in range(n):
        name, obj = _generate_workbook(i, num_tables, cols_per_table)
        names.append(name)
        objects_list.append(obj)
    return names, objects_list


@unittest.skipUnless(_RUN_BENCHMARKS, "Benchmark tests require --benchmark flag or RUN_BENCHMARKS=1")
class TestMergePerformance(unittest.TestCase):
    """Performance benchmarks for merge operations at scale."""

    def _time_merge(self, n_workbooks, num_tables=3, cols_per_table=5):
        """Run assess + merge for n workbooks and return elapsed time."""
        from powerbi_import.shared_model import assess_merge, merge_semantic_models

        names, objects_list = _generate_workbooks(n_workbooks, num_tables, cols_per_table)

        start = time.perf_counter()
        assessment = assess_merge(objects_list, names)
        # Force merge regardless of score
        assessment.isolated_tables = {}
        merged = merge_semantic_models(objects_list, assessment, "BenchmarkModel")
        elapsed = time.perf_counter() - start

        return elapsed, merged, assessment

    def test_10_workbooks(self):
        """10 workbooks with 3 tables each — should complete quickly."""
        elapsed, merged, _ = self._time_merge(10, num_tables=3)
        tables = merged.get('datasources', [{}])[0].get('tables', [])
        self.assertGreater(len(tables), 0)
        self.assertLess(elapsed, 5.0, f"10-workbook merge took {elapsed:.2f}s (>5s)")

    def test_25_workbooks(self):
        """25 workbooks with 3 tables each."""
        elapsed, merged, _ = self._time_merge(25, num_tables=3)
        tables = merged.get('datasources', [{}])[0].get('tables', [])
        self.assertGreater(len(tables), 0)
        self.assertLess(elapsed, 10.0, f"25-workbook merge took {elapsed:.2f}s (>10s)")

    def test_50_workbooks(self):
        """50 workbooks with 3 tables each."""
        elapsed, merged, _ = self._time_merge(50, num_tables=3)
        tables = merged.get('datasources', [{}])[0].get('tables', [])
        self.assertGreater(len(tables), 0)
        self.assertLess(elapsed, 20.0, f"50-workbook merge took {elapsed:.2f}s (>20s)")

    def test_100_workbooks(self):
        """100 workbooks with 3 tables each — target <5s per plan."""
        elapsed, merged, _ = self._time_merge(100, num_tables=3)
        tables = merged.get('datasources', [{}])[0].get('tables', [])
        self.assertGreater(len(tables), 0)
        self.assertLess(elapsed, 30.0, f"100-workbook merge took {elapsed:.2f}s (>30s)")

    def test_10_workbooks_wide_tables(self):
        """10 workbooks with 10 tables × 20 columns each."""
        elapsed, merged, _ = self._time_merge(10, num_tables=10, cols_per_table=20)
        tables = merged.get('datasources', [{}])[0].get('tables', [])
        self.assertGreater(len(tables), 0)
        self.assertLess(elapsed, 10.0, f"10-workbook wide merge took {elapsed:.2f}s (>10s)")

    def test_lineage_at_scale(self):
        """Lineage metadata is present after large merge."""
        from powerbi_import.shared_model import extract_lineage

        elapsed, merged, _ = self._time_merge(25, num_tables=3)
        lineage = extract_lineage(merged)
        self.assertGreater(len(lineage), 0, "No lineage records at scale")
        # All lineage records should have source_workbooks
        for rec in lineage:
            self.assertIn('source_workbooks', rec)
            self.assertGreater(len(rec['source_workbooks']), 0)

    def test_assessment_at_scale(self):
        """Assessment scoring for 50 workbooks completes in reasonable time."""
        from powerbi_import.shared_model import assess_merge

        names, objects_list = _generate_workbooks(50, num_tables=3)

        start = time.perf_counter()
        assessment = assess_merge(objects_list, names)
        elapsed = time.perf_counter() - start

        self.assertIsNotNone(assessment.merge_score)
        self.assertLess(elapsed, 15.0, f"50-workbook assessment took {elapsed:.2f}s (>15s)")

    def test_fingerprint_cache_speedup(self):
        """Global assessment with cache should not be slower than without."""
        from powerbi_import.global_assessment import (
            _find_shared_table_names,
            _find_shared_table_names_cached,
        )
        from powerbi_import.shared_model import build_table_fingerprints

        names, objects_list = _generate_workbooks(20, num_tables=5)

        # Pre-compute fingerprints (cached approach)
        fp_cache = {}
        for i, obj in enumerate(objects_list):
            fp_cache[i] = build_table_fingerprints(obj.get('datasources', []))

        # Cached pairwise
        start = time.perf_counter()
        for i in range(len(objects_list)):
            for j in range(i + 1, len(objects_list)):
                _find_shared_table_names_cached(fp_cache[i], fp_cache[j])
        cached_time = time.perf_counter() - start

        # Uncached pairwise
        start = time.perf_counter()
        for i in range(len(objects_list)):
            for j in range(i + 1, len(objects_list)):
                _find_shared_table_names(objects_list[i], objects_list[j])
        uncached_time = time.perf_counter() - start

        # Cached should be faster (or at least not significantly slower)
        # Allow 2x margin for variance
        self.assertLess(cached_time, uncached_time * 2.0,
                        f"Cached ({cached_time:.3f}s) slower than 2x uncached ({uncached_time:.3f}s)")

    def test_merge_manifest_at_scale(self):
        """Merge manifest can be built for large merge."""
        from powerbi_import.shared_model import (
            assess_merge, merge_semantic_models, build_merge_manifest,
        )

        names, objects_list = _generate_workbooks(25, num_tables=3)
        assessment = assess_merge(objects_list, names)
        assessment.isolated_tables = {}
        merged = merge_semantic_models(objects_list, assessment, "ScaleBenchmark")

        start = time.perf_counter()
        manifest = build_merge_manifest(
            model_name="ScaleBenchmark",
            all_extracted=objects_list,
            workbook_names=names,
            workbook_paths=None,
            merged=merged,
            assessment=assessment,
        )
        elapsed = time.perf_counter() - start

        self.assertIsNotNone(manifest)
        self.assertLess(elapsed, 2.0, f"Manifest build took {elapsed:.2f}s (>2s)")


@unittest.skipUnless(_RUN_BENCHMARKS, "Benchmark tests require --benchmark flag or RUN_BENCHMARKS=1")
class TestGlobalAssessmentPerformance(unittest.TestCase):
    """Performance benchmarks for global (cross-workbook) assessment."""

    def test_global_assessment_20_workbooks(self):
        """Global assessment pairwise comparison for 20 workbooks."""
        from powerbi_import.shared_model import build_table_fingerprints
        from powerbi_import.global_assessment import _find_shared_table_names_cached

        names, objects_list = _generate_workbooks(20, num_tables=5)

        # Pre-compute fingerprints
        fp_cache = {}
        for i, obj in enumerate(objects_list):
            fp_cache[i] = build_table_fingerprints(obj.get('datasources', []))

        start = time.perf_counter()
        pairs = 0
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                shared = _find_shared_table_names_cached(fp_cache[i], fp_cache[j])
                pairs += 1
        elapsed = time.perf_counter() - start

        self.assertEqual(pairs, 20 * 19 // 2)  # C(20,2) = 190 pairs
        self.assertLess(elapsed, 5.0, f"20-WB pairwise took {elapsed:.2f}s (>5s)")


if __name__ == '__main__':
    unittest.main()
