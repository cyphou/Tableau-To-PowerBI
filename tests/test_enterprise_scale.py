"""
Sprint 90 — Enterprise Scale Tests.

Validates parallel batch processing, memory-efficient generation,
and large-scale operation characteristics.
"""

import os
import shutil
import tempfile
import time
import unittest

from powerbi_import import tmdl_generator


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _synthetic_workbook(wb_id, n_tables=5, n_measures=10):
    """Generate a synthetic extracted workbook dict."""
    tables = []
    calcs = []
    for t in range(n_tables):
        cols = [{'name': f'Col{c}', 'datatype': 'string'} for c in range(8)]
        cols.append({'name': f'Amount{t}', 'datatype': 'real'})
        tables.append({
            'name': f'Table{t}_WB{wb_id}',
            'type': 'table',
            'columns': cols,
        })
    for m in range(n_measures):
        calcs.append({
            'name': f'Measure{m}_WB{wb_id}',
            'formula': f'SUM([Amount{m % n_tables}])',
            'role': 'measure',
            'datatype': 'real',
        })
    return {
        'datasources': [{
            'name': f'DS_WB{wb_id}',
            'connection': {'type': 'SQL Server', 'details': {'server': 'svr', 'database': 'db'}},
            'tables': tables,
            'calculations': calcs,
            'relationships': [],
        }],
        'worksheets': [{'name': f'Sheet1_WB{wb_id}', 'fields': ['Col0']}],
        'calculations': calcs,
        'parameters': [],
    }


# ═══════════════════════════════════════════════════════════════════
# 1. TMDL generation at scale
# ═══════════════════════════════════════════════════════════════════

class TestScaleGeneration(unittest.TestCase):
    """Verify TMDL generation works for many tables."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_20_tables_generation(self):
        """Generate TMDL with 20 tables."""
        wb = _synthetic_workbook(1, n_tables=20, n_measures=20)
        stats = tmdl_generator.generate_tmdl(
            datasources=wb['datasources'],
            report_name='Scale20',
            extra_objects={},
            output_dir=self.tmp,
        )
        self.assertGreaterEqual(stats['tables'], 20)
        self.assertGreaterEqual(stats['measures'], 10)

    def test_50_tables_generation(self):
        """Generate TMDL with 50 tables."""
        wb = _synthetic_workbook(1, n_tables=50, n_measures=30)
        stats = tmdl_generator.generate_tmdl(
            datasources=wb['datasources'],
            report_name='Scale50',
            extra_objects={},
            output_dir=self.tmp,
        )
        self.assertGreaterEqual(stats['tables'], 50)

    def test_generation_time_reasonable(self):
        """50 tables should complete in < 10 seconds."""
        wb = _synthetic_workbook(1, n_tables=50, n_measures=50)
        start = time.time()
        tmdl_generator.generate_tmdl(
            datasources=wb['datasources'],
            report_name='TimeBench',
            extra_objects={},
            output_dir=self.tmp,
        )
        elapsed = time.time() - start
        self.assertLess(elapsed, 10.0, f"Generation took {elapsed:.1f}s (> 10s)")


# ═══════════════════════════════════════════════════════════════════
# 2. Parallel batch infrastructure
# ═══════════════════════════════════════════════════════════════════

class TestParallelBatch(unittest.TestCase):
    """Verify parallel batch CLI flags and infrastructure."""

    def test_workers_alias(self):
        """--workers N should be accepted as alias for --parallel."""
        import argparse
        import importlib
        import migrate
        importlib.reload(migrate)
        parser = argparse.ArgumentParser()
        migrate._add_enterprise_args(parser)
        args = parser.parse_args(['--workers', '4'])
        self.assertEqual(args.parallel, 4)

    def test_parallel_flag(self):
        """--parallel N should work."""
        import argparse
        import importlib
        import migrate
        importlib.reload(migrate)
        parser = argparse.ArgumentParser()
        migrate._add_enterprise_args(parser)
        args = parser.parse_args(['--parallel', '8'])
        self.assertEqual(args.parallel, 8)

    def test_concurrent_futures_available(self):
        """concurrent.futures should be importable."""
        import concurrent.futures
        self.assertTrue(hasattr(concurrent.futures, 'ThreadPoolExecutor'))

    def test_sync_flag(self):
        """--sync flag should be accepted."""
        import argparse
        import importlib
        import migrate
        importlib.reload(migrate)
        parser = argparse.ArgumentParser()
        migrate._add_deploy_args(parser)
        args = parser.parse_args(['--sync'])
        self.assertTrue(args.sync)


# ═══════════════════════════════════════════════════════════════════
# 3. Multi-workbook batch simulation
# ═══════════════════════════════════════════════════════════════════

class TestBatchSimulation(unittest.TestCase):
    """Simulate batch migration of multiple synthetic workbooks."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_10_workbook_sequential(self):
        """Migrate 10 synthetic workbooks sequentially."""
        success = 0
        for i in range(10):
            wb = _synthetic_workbook(i, n_tables=3, n_measures=5)
            out_dir = os.path.join(self.tmp, f'wb{i}')
            os.makedirs(out_dir, exist_ok=True)
            try:
                stats = tmdl_generator.generate_tmdl(
                    datasources=wb['datasources'],
                    report_name=f'WB{i}',
                    extra_objects={},
                    output_dir=out_dir,
                )
                if stats['tables'] >= 3:
                    success += 1
            except Exception:
                pass
        self.assertEqual(success, 10)

    def test_batch_under_5_seconds(self):
        """10 workbooks × 3 tables should complete in < 5 seconds."""
        start = time.time()
        for i in range(10):
            wb = _synthetic_workbook(i, n_tables=3, n_measures=5)
            out_dir = os.path.join(self.tmp, f'wb{i}')
            os.makedirs(out_dir, exist_ok=True)
            tmdl_generator.generate_tmdl(
                datasources=wb['datasources'],
                report_name=f'WB{i}',
                extra_objects={},
                output_dir=out_dir,
            )
        elapsed = time.time() - start
        self.assertLess(elapsed, 5.0, f"Batch took {elapsed:.1f}s (> 5s)")


# ═══════════════════════════════════════════════════════════════════
# 4. Enterprise guide documentation
# ═══════════════════════════════════════════════════════════════════

class TestEnterpriseGuide(unittest.TestCase):
    """Verify enterprise guide document exists and has content."""

    def test_guide_exists(self):
        self.assertTrue(os.path.isfile('docs/ENTERPRISE_GUIDE.md'))

    def test_guide_has_sections(self):
        with open('docs/ENTERPRISE_GUIDE.md', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Discovery', content)
        self.assertIn('Assessment', content)
        self.assertIn('Batch Migration', content)
        self.assertIn('Deployment', content)
        self.assertIn('Live Sync', content)

    def test_guide_mentions_workers(self):
        with open('docs/ENTERPRISE_GUIDE.md', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('--workers', content)


if __name__ == '__main__':
    unittest.main()
