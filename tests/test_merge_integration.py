"""
End-to-end integration tests for the shared semantic model merge pipeline.

Uses actual example workbooks from examples/tableau_samples/ to exercise
the full extract → merge → generate → validate flow.

These tests verify:
- Multi-workbook extraction
- Merge assessment scoring
- Table/measure/relationship deduplication
- TMDL/PBIR output structure
- Lineage metadata propagation
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

# Ensure project root is importable
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from powerbi_import.shared_model import (
    assess_merge,
    merge_semantic_models,
    build_merge_manifest,
    extract_lineage,
    generate_merge_validation_report,
)

_SAMPLES_DIR = os.path.join(_project_root, 'examples', 'tableau_samples')
_SAMPLE_FILES = [
    os.path.join(_SAMPLES_DIR, 'Superstore_Sales.twb'),
    os.path.join(_SAMPLES_DIR, 'Financial_Report.twb'),
    os.path.join(_SAMPLES_DIR, 'Marketing_Campaign.twb'),
]
_SAMPLES_EXIST = all(os.path.isfile(f) for f in _SAMPLE_FILES)


def _extract_workbook(twb_path: str, output_dir: str) -> dict:
    """Extract a workbook and return converted_objects."""
    sys.path.insert(0, os.path.join(_project_root, 'tableau_export'))
    sys.path.insert(0, os.path.join(_project_root, 'powerbi_import'))
    from extract_tableau_data import TableauExtractor
    from import_to_powerbi import PowerBIImporter

    extractor = TableauExtractor(twb_path, output_dir=output_dir)
    extractor.extract_all()
    importer = PowerBIImporter(source_dir=output_dir)
    return importer._load_converted_objects()


@unittest.skipUnless(_SAMPLES_EXIST, "Sample workbooks not available")
class TestMergeIntegration(unittest.TestCase):
    """Integration tests using real example workbooks."""

    @classmethod
    def setUpClass(cls):
        """Extract all sample workbooks once."""
        cls.temp_dirs = []
        cls.all_converted = []
        cls.workbook_names = []

        for wb_path in _SAMPLE_FILES:
            basename = os.path.splitext(os.path.basename(wb_path))[0]
            cls.workbook_names.append(basename)
            temp_dir = tempfile.mkdtemp(prefix=f'test_merge_{basename}_')
            cls.temp_dirs.append(temp_dir)
            converted = _extract_workbook(wb_path, temp_dir)
            cls.all_converted.append(converted)

        # Run assessment
        cls.assessment = assess_merge(cls.all_converted, cls.workbook_names)

        # Force merge even with low overlap (sample workbooks have different
        # data sources so all tables would be classified as isolated)
        # Clear isolated tables to allow all tables into the merged model
        cls.assessment.isolated_tables = {}

        # Run merge
        cls.merged = merge_semantic_models(
            cls.all_converted, cls.assessment, 'TestSharedModel'
        )

    @classmethod
    def tearDownClass(cls):
        for td in cls.temp_dirs:
            shutil.rmtree(td, ignore_errors=True)

    def test_extraction_produces_datasources(self):
        """Each workbook extracts at least one datasource."""
        for i, name in enumerate(self.workbook_names):
            ds = self.all_converted[i].get('datasources', [])
            self.assertTrue(len(ds) >= 1, f"{name}: no datasources extracted")

    def test_assessment_produces_score(self):
        """Assessment produces a merge score 0-100."""
        self.assertIsInstance(self.assessment.merge_score, int)
        self.assertGreaterEqual(self.assessment.merge_score, 0)
        self.assertLessEqual(self.assessment.merge_score, 100)

    def test_assessment_has_recommendation(self):
        score = self.assessment.recommendation
        self.assertIn(score, ('merge', 'partial', 'separate'))

    def test_merged_has_datasource(self):
        """Merged output has exactly one datasource."""
        ds = self.merged.get('datasources', [])
        self.assertEqual(len(ds), 1)

    def test_merged_has_tables(self):
        """Merged datasource has at least one table."""
        ds = self.merged['datasources'][0]
        tables = ds.get('tables', [])
        self.assertGreater(len(tables), 0)

    def test_merged_tables_have_columns(self):
        """Every merged table has columns."""
        ds = self.merged['datasources'][0]
        for table in ds.get('tables', []):
            cols = table.get('columns', [])
            self.assertGreater(len(cols), 0,
                               f"Table '{table.get('name')}' has no columns")

    def test_merged_tables_have_lineage(self):
        """Merged tables have _source_workbooks metadata."""
        ds = self.merged['datasources'][0]
        for table in ds.get('tables', []):
            src = table.get('_source_workbooks', [])
            self.assertIsInstance(src, list)
            self.assertGreater(len(src), 0,
                               f"Table '{table.get('name')}' has no _source_workbooks")

    def test_merged_tables_have_merge_action(self):
        """Merged tables have _merge_action metadata."""
        ds = self.merged['datasources'][0]
        for table in ds.get('tables', []):
            action = table.get('_merge_action', '')
            self.assertIn(action, ('deduplicated', 'unique', ''),
                          f"Table '{table.get('name')}' unexpected action: {action}")

    def test_lineage_extraction(self):
        """extract_lineage returns records for all artifact types."""
        records = extract_lineage(self.merged)
        self.assertGreater(len(records), 0)
        types_found = {r['type'] for r in records}
        self.assertIn('table', types_found)

    def test_lineage_records_have_source_workbooks(self):
        """All lineage records have source_workbooks list."""
        records = extract_lineage(self.merged)
        for r in records:
            self.assertIsInstance(r.get('source_workbooks'), list,
                                 f"Record '{r.get('name')}' has no source_workbooks list")

    def test_validation_report(self):
        """Post-merge validation produces a report with score."""
        report = generate_merge_validation_report(self.merged)
        self.assertIn('score', report)
        self.assertIsInstance(report['score'], int)
        self.assertGreaterEqual(report['score'], 0)

    def test_merge_manifest(self):
        """Merge manifest can be built from merged output."""
        manifest = build_merge_manifest(
            'TestSharedModel',
            self.all_converted,
            self.workbook_names,
            _SAMPLE_FILES,
            self.merged,
            self.assessment,
            validation_score=95,
        )
        self.assertEqual(manifest.model_name, 'TestSharedModel')
        self.assertEqual(len(manifest.workbooks), len(self.workbook_names))
        self.assertGreater(manifest.artifact_counts['tables'], 0)

    def test_tmdl_generation(self):
        """TMDL + PBIR output can be generated from merged data."""
        from import_to_powerbi import PowerBIImporter

        output_dir = tempfile.mkdtemp(prefix='test_merge_output_')
        try:
            importer = PowerBIImporter()
            result = importer.import_shared_model(
                model_name='TestSharedModel',
                all_converted_objects=self.all_converted,
                workbook_names=self.workbook_names,
                output_dir=output_dir,
                force_merge=True,
            )
            model_path = result.get('model_path', '')
            self.assertTrue(model_path, "No model_path in result")

            # model_path IS the .SemanticModel directory itself
            self.assertTrue(model_path.endswith('.SemanticModel'),
                            f"model_path should end with .SemanticModel: {model_path}")
            model_dir = os.path.join(model_path, 'definition')
            self.assertTrue(
                os.path.isfile(os.path.join(model_dir, 'model.tmdl')),
                "model.tmdl not found"
            )
            tables_dir = os.path.join(model_dir, 'tables')
            self.assertTrue(os.path.isdir(tables_dir), "tables/ dir not found")
            tmdl_files = [f for f in os.listdir(tables_dir) if f.endswith('.tmdl')]
            self.assertGreater(len(tmdl_files), 0, "No table .tmdl files")

            # Check thin reports were generated (inside project_dir, parent of .SemanticModel)
            project_dir = os.path.dirname(model_path)
            report_dirs = [d for d in os.listdir(project_dir) if d.endswith('.Report')]
            self.assertGreater(len(report_dirs), 0, "No thin report directories")

        finally:
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_unique_vs_dedup_tables(self):
        """At least some tables are unique or deduplicated."""
        ds = self.merged['datasources'][0]
        actions = [t.get('_merge_action', '') for t in ds.get('tables', [])]
        self.assertTrue(
            any(a in ('unique', 'deduplicated') for a in actions),
            f"No unique/deduplicated tables; got {actions}"
        )


@unittest.skipUnless(_SAMPLES_EXIST, "Sample workbooks not available")
class TestTwoWorkbookMerge(unittest.TestCase):
    """Focused integration test: merge exactly 2 workbooks."""

    def test_two_workbook_merge(self):
        """Merge Superstore + Financial produces valid output."""
        td1 = tempfile.mkdtemp(prefix='test_2wb_1_')
        td2 = tempfile.mkdtemp(prefix='test_2wb_2_')
        try:
            c1 = _extract_workbook(_SAMPLE_FILES[0], td1)
            c2 = _extract_workbook(_SAMPLE_FILES[1], td2)
            names = ['Superstore_Sales', 'Financial_Report']

            assessment = assess_merge([c1, c2], names)
            self.assertIsInstance(assessment.merge_score, int)

            # Force merge (different data sources = low overlap)
            assessment.isolated_tables = {}
            merged = merge_semantic_models([c1, c2], assessment, 'TwoWBModel')
            ds = merged.get('datasources', [{}])[0]
            self.assertGreater(len(ds.get('tables', [])), 0)

            # Lineage check
            records = extract_lineage(merged)
            self.assertGreater(len(records), 0)
        finally:
            shutil.rmtree(td1, ignore_errors=True)
            shutil.rmtree(td2, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
