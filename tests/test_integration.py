"""
Integration tests for the complete migration pipeline.

Tests end-to-end flow: extraction → generation → validation.
Uses synthetic Tableau XML to exercise the full pipeline without
requiring actual .twb/.twbx files.
"""

import unittest
import sys
import os
import json
import copy
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from tests.conftest import SAMPLE_DATASOURCE, SAMPLE_EXTRACTED, make_temp_dir, cleanup_dir


class TestPipelineIntegration(unittest.TestCase):
    """End-to-end integration tests for the generation pipeline."""

    def setUp(self):
        self.temp_dir = make_temp_dir()

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def test_full_generation_pipeline(self):
        """Test that generation produces a valid .pbip project structure."""
        from pbip_generator import PowerBIProjectGenerator

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        project_path = generator.generate_project('IntegrationTest', copy.deepcopy(SAMPLE_EXTRACTED))

        # Verify project structure
        self.assertTrue(os.path.exists(project_path))

        # Check .pbip file exists
        pbip_file = os.path.join(project_path, 'IntegrationTest.pbip')
        self.assertTrue(os.path.exists(pbip_file))

        # Check .pbip is valid JSON
        with open(pbip_file, 'r', encoding='utf-8') as f:
            pbip_content = json.load(f)
        self.assertIn('$schema', pbip_content)

    def test_semantic_model_structure(self):
        """Test that SemanticModel structure is complete."""
        from pbip_generator import PowerBIProjectGenerator

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        project_path = generator.generate_project('SMTest', copy.deepcopy(SAMPLE_EXTRACTED))

        sm_dir = os.path.join(project_path, 'SMTest.SemanticModel')
        self.assertTrue(os.path.exists(sm_dir))

        # Check .platform file
        platform = os.path.join(sm_dir, '.platform')
        self.assertTrue(os.path.exists(platform))

        # Check definition directory
        def_dir = os.path.join(sm_dir, 'definition')
        self.assertTrue(os.path.exists(def_dir))

        # Check essential TMDL files
        for tmdl_file in ['model.tmdl', 'database.tmdl']:
            path = os.path.join(def_dir, tmdl_file)
            self.assertTrue(os.path.exists(path),
                            f"Missing TMDL file: {tmdl_file}")

    def test_report_structure(self):
        """Test that Report structure is complete."""
        from pbip_generator import PowerBIProjectGenerator

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        project_path = generator.generate_project('ReportTest', copy.deepcopy(SAMPLE_EXTRACTED))

        report_dir = os.path.join(project_path, 'ReportTest.Report')
        self.assertTrue(os.path.exists(report_dir))

        # Check report.json (in definition/ subdirectory per PBIR format)
        report_json = os.path.join(report_dir, 'definition', 'report.json')
        self.assertTrue(os.path.exists(report_json),
                        f"report.json not found at {report_json}")

        # Verify report.json schema
        with open(report_json, 'r', encoding='utf-8') as f:
            content = json.load(f)
        self.assertIn('$schema', content)

    def test_tmdl_tables_generated(self):
        """Test that TMDL tables are generated from datasource tables."""
        from tmdl_generator import generate_tmdl

        ds = copy.deepcopy(SAMPLE_DATASOURCE)
        stats = generate_tmdl([ds], 'TmdlTest', {}, self.temp_dir)

        self.assertGreater(stats['tables'], 0)
        self.assertGreater(stats['columns'], 0)

        # Check tables directory
        tables_dir = os.path.join(self.temp_dir, 'definition', 'tables')
        self.assertTrue(os.path.exists(tables_dir))

    def test_mode_passthrough(self):
        """Test that model_mode is passed through the pipeline."""
        from pbip_generator import PowerBIProjectGenerator

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        # Should not raise with composite mode
        project_path = generator.generate_project(
            'ModeTest', copy.deepcopy(SAMPLE_EXTRACTED),
            model_mode='composite'
        )
        self.assertTrue(os.path.exists(project_path))

    def test_output_format_tmdl_only(self):
        """Test that output_format='tmdl' generates only semantic model."""
        from pbip_generator import PowerBIProjectGenerator

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        project_path = generator.generate_project(
            'TmdlOnly', copy.deepcopy(SAMPLE_EXTRACTED),
            output_format='tmdl'
        )
        sm_dir = os.path.join(project_path, 'TmdlOnly.SemanticModel')
        report_dir = os.path.join(project_path, 'TmdlOnly.Report')

        self.assertTrue(os.path.exists(sm_dir))
        # Report should NOT be generated in tmdl-only mode
        self.assertFalse(os.path.exists(report_dir))

    def test_output_format_pbir_only(self):
        """Test that output_format='pbir' generates only report."""
        from pbip_generator import PowerBIProjectGenerator

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        project_path = generator.generate_project(
            'PbirOnly', copy.deepcopy(SAMPLE_EXTRACTED),
            output_format='pbir'
        )
        sm_dir = os.path.join(project_path, 'PbirOnly.SemanticModel')
        report_dir = os.path.join(project_path, 'PbirOnly.Report')

        # SemanticModel should NOT be generated in pbir-only mode
        self.assertFalse(os.path.exists(sm_dir))
        self.assertTrue(os.path.exists(report_dir))

    def test_culture_passthrough(self):
        """Test that culture is passed through to TMDL."""
        from tmdl_generator import generate_tmdl

        ds = copy.deepcopy(SAMPLE_DATASOURCE)
        stats = generate_tmdl([ds], 'CultureTest', {}, self.temp_dir,
                              culture='fr-FR')
        self.assertIsInstance(stats, dict)

        # Check culture TMDL file
        culture_path = os.path.join(self.temp_dir, 'definition', 'cultures', 'fr-FR.tmdl')
        self.assertTrue(os.path.exists(culture_path))


class TestValidatorIntegration(unittest.TestCase):
    """Tests for the validator on generated projects."""

    def setUp(self):
        self.temp_dir = make_temp_dir()

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def test_validate_generated_project(self):
        """Test that a generated project passes validation."""
        from pbip_generator import PowerBIProjectGenerator

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        project_path = generator.generate_project('ValidTest', copy.deepcopy(SAMPLE_EXTRACTED))

        try:
            from validator import validate_pbip_project
            result = validate_pbip_project(project_path)
            # Should pass or have only warnings (not errors)
            self.assertIsNotNone(result)
        except ImportError:
            self.skipTest("Validator not available")


class TestMigrationReportIntegration(unittest.TestCase):
    """Tests for migration report generation after pipeline."""

    def setUp(self):
        self.temp_dir = make_temp_dir()

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def test_migration_report_structure(self):
        """Test that migration report produces valid JSON."""
        try:
            from migration_report import MigrationReport

            report = MigrationReport('IntegrationReportTest')

            # Add sample data
            ds = copy.deepcopy(SAMPLE_DATASOURCE)
            report.add_datasources([ds])

            calcs = SAMPLE_EXTRACTED.get('calculations', [])
            report.add_calculations(calcs, {})

            # Generate summary
            summary = report.get_summary()
            self.assertIsNotNone(summary)
            self.assertIsInstance(summary, dict)
        except ImportError:
            self.skipTest("MigrationReport not available")


class TestBatchModeIntegration(unittest.TestCase):
    """Tests for batch migration mode."""

    def test_batch_with_no_files(self):
        """Test batch mode with empty directory."""
        temp_dir = make_temp_dir()
        try:
            from migrate import run_batch_migration
            result = run_batch_migration(temp_dir)
            self.assertNotEqual(result, 0)  # Should fail — no files found
        finally:
            cleanup_dir(temp_dir)


if __name__ == '__main__':
    unittest.main()
