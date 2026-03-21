"""
Sprint 80.3 — Performance regression tests.

Benchmark: batch migration of sample workbooks must complete within budget.
Single workbook migration must be fast. No regression vs v21 baseline.
"""
import glob
import os
import sys
import tempfile
import shutil
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))
sys.path.insert(0, os.path.join(ROOT, 'powerbi_import'))

from tableau_export.extract_tableau_data import TableauExtractor
from powerbi_import.import_to_powerbi import PowerBIImporter

SAMPLE_DIR = os.path.join(ROOT, 'examples', 'tableau_samples')
REAL_WORLD_DIR = os.path.join(ROOT, 'examples', 'real_world')

# ── Budget thresholds ─────────────────────────────────────────────────

SINGLE_WB_MAX_SECONDS = 5.0       # Single workbook: max 5s
BATCH_10_MAX_SECONDS = 45.0       # 10 sample workbooks: max 45s
EXTRACTION_MAX_SECONDS = 2.0      # Extraction-only: max 2s per workbook
GENERATION_MAX_SECONDS = 3.0      # Generation-only: max 3s per workbook


def _find_workbooks(directory, limit=None):
    paths = []
    for ext in ('*.twb', '*.twbx'):
        paths.extend(glob.glob(os.path.join(directory, ext)))
    paths = [p for p in paths if not os.path.basename(p).startswith('~')]
    paths = sorted(paths)
    if limit:
        paths = paths[:limit]
    return paths


def _migrate_one(wb_path, output_dir):
    """Full extract→generate for one workbook. Returns elapsed seconds."""
    basename = os.path.splitext(os.path.basename(wb_path))[0]
    temp_extract = tempfile.mkdtemp(prefix=f'perf_ext_{basename}_')
    try:
        t0 = time.perf_counter()

        ext = TableauExtractor(wb_path, output_dir=temp_extract)
        ok = ext.extract_all()
        if not ok:
            return -1.0  # extraction failed

        imp = PowerBIImporter(source_dir=temp_extract)
        imp.import_all(
            generate_pbip=True,
            report_name=basename,
            output_dir=output_dir,
        )
        return time.perf_counter() - t0
    finally:
        shutil.rmtree(temp_extract, ignore_errors=True)


# ── Test classes ───────────────────────────────────────────────────────

class TestSingleWorkbookPerformance(unittest.TestCase):
    """Each sample workbook should migrate in under SINGLE_WB_MAX_SECONDS."""

    def _time_workbook(self, filename):
        wb_path = os.path.join(SAMPLE_DIR, filename)
        if not os.path.isfile(wb_path):
            self.skipTest(f'Not found: {wb_path}')
        temp = tempfile.mkdtemp(prefix='perf_single_')
        try:
            elapsed = _migrate_one(wb_path, temp)
            self.assertGreater(elapsed, 0, f'Migration failed for {filename}')
            self.assertLess(elapsed, SINGLE_WB_MAX_SECONDS,
                            f'{filename} took {elapsed:.2f}s (budget: {SINGLE_WB_MAX_SECONDS}s)')
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def test_superstore_sales(self):
        self._time_workbook('Superstore_Sales.twb')

    def test_enterprise_sales(self):
        self._time_workbook('Enterprise_Sales.twb')

    def test_financial_report(self):
        self._time_workbook('Financial_Report.twb')

    def test_hr_analytics(self):
        self._time_workbook('HR_Analytics.twb')

    def test_complex_enterprise(self):
        self._time_workbook('Complex_Enterprise.twb')


class TestExtractionPerformance(unittest.TestCase):
    """Extraction phase alone should be fast."""

    def _time_extraction(self, filename):
        wb_path = os.path.join(SAMPLE_DIR, filename)
        if not os.path.isfile(wb_path):
            self.skipTest(f'Not found: {wb_path}')
        temp = tempfile.mkdtemp(prefix='perf_extract_')
        try:
            t0 = time.perf_counter()
            ext = TableauExtractor(wb_path, output_dir=temp)
            ext.extract_all()
            elapsed = time.perf_counter() - t0
            self.assertLess(elapsed, EXTRACTION_MAX_SECONDS,
                            f'Extraction of {filename} took {elapsed:.2f}s '
                            f'(budget: {EXTRACTION_MAX_SECONDS}s)')
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def test_superstore_extraction(self):
        self._time_extraction('Superstore_Sales.twb')

    def test_complex_enterprise_extraction(self):
        self._time_extraction('Complex_Enterprise.twb')

    def test_enterprise_sales_extraction(self):
        self._time_extraction('Enterprise_Sales.twb')

    def test_bigquery_analytics_extraction(self):
        self._time_extraction('BigQuery_Analytics.twb')

    def test_marketing_campaign_extraction(self):
        self._time_extraction('Marketing_Campaign.twb')


class TestGenerationPerformance(unittest.TestCase):
    """Generation phase alone should be fast."""

    def _time_generation(self, filename):
        wb_path = os.path.join(SAMPLE_DIR, filename)
        if not os.path.isfile(wb_path):
            self.skipTest(f'Not found: {wb_path}')
        temp_ext = tempfile.mkdtemp(prefix='perf_genext_')
        temp_out = tempfile.mkdtemp(prefix='perf_genout_')
        try:
            # Extract first (not timed)
            ext = TableauExtractor(wb_path, output_dir=temp_ext)
            ext.extract_all()

            basename = os.path.splitext(os.path.basename(wb_path))[0]

            # Time generation only
            t0 = time.perf_counter()
            imp = PowerBIImporter(source_dir=temp_ext)
            imp.import_all(
                generate_pbip=True,
                report_name=basename,
                output_dir=temp_out,
            )
            elapsed = time.perf_counter() - t0
            self.assertLess(elapsed, GENERATION_MAX_SECONDS,
                            f'Generation of {filename} took {elapsed:.2f}s '
                            f'(budget: {GENERATION_MAX_SECONDS}s)')
        finally:
            shutil.rmtree(temp_ext, ignore_errors=True)
            shutil.rmtree(temp_out, ignore_errors=True)

    def test_superstore_generation(self):
        self._time_generation('Superstore_Sales.twb')

    def test_complex_enterprise_generation(self):
        self._time_generation('Complex_Enterprise.twb')

    def test_hr_analytics_generation(self):
        self._time_generation('HR_Analytics.twb')


class TestBatchPerformance(unittest.TestCase):
    """Batch migration of all 10 sample workbooks should be fast."""

    def test_batch_10_samples(self):
        wbs = _find_workbooks(SAMPLE_DIR)
        if len(wbs) < 5:
            self.skipTest('Not enough sample workbooks')

        temp = tempfile.mkdtemp(prefix='perf_batch_')
        try:
            t0 = time.perf_counter()
            for wb_path in wbs:
                elapsed = _migrate_one(wb_path, temp)
                self.assertGreater(elapsed, 0,
                                   f'Migration failed: {os.path.basename(wb_path)}')
            total = time.perf_counter() - t0
            self.assertLess(total, BATCH_10_MAX_SECONDS,
                            f'Batch of {len(wbs)} workbooks took {total:.2f}s '
                            f'(budget: {BATCH_10_MAX_SECONDS}s)')
        finally:
            shutil.rmtree(temp, ignore_errors=True)


class TestRealWorldPerformance(unittest.TestCase):
    """Spot-check a few real-world workbooks for performance."""

    def _time_real_world(self, filename):
        wb_path = os.path.join(REAL_WORLD_DIR, filename)
        if not os.path.isfile(wb_path):
            self.skipTest(f'Not found: {filename}')
        temp = tempfile.mkdtemp(prefix='perf_rw_')
        try:
            elapsed = _migrate_one(wb_path, temp)
            self.assertGreater(elapsed, 0, f'Migration failed for {filename}')
            self.assertLess(elapsed, SINGLE_WB_MAX_SECONDS,
                            f'{filename} took {elapsed:.2f}s (budget: {SINGLE_WB_MAX_SECONDS}s)')
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def test_feedback_dashboard(self):
        self._time_real_world('feedback_dashboard.twb')

    def test_sample_superstore(self):
        self._time_real_world('sample-superstore.twb')

    def test_vishnu_dashboard(self):
        self._time_real_world('vishnu_dashboard.twb')

    def test_global_superstores(self):
        self._time_real_world('global_superstores_db.twb')

    def test_filtering(self):
        self._time_real_world('filtering.twb')


if __name__ == '__main__':
    unittest.main()
