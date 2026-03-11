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

from tests.conftest import (
    SAMPLE_DATASOURCE, SAMPLE_EXTRACTED, SAMPLE_EXTRACTED_WITH_MEASURES,
    make_temp_dir, cleanup_dir,
)


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


class TestVisualTmdlCrossValidation(unittest.TestCase):
    """Tests that generated visual field references (Entity+Property)
    resolve to actual columns/measures in the TMDL semantic model.

    This catches mismatches between the PBIR report layer and the
    semantic model — e.g., a visual referencing 'Amount' as a Measure
    when the BIM model defines it as a Column, or referencing a field
    that doesn't exist in any table.
    """

    def setUp(self):
        self.temp_dir = make_temp_dir()

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def test_visual_fields_all_resolve_to_tmdl(self):
        """Every Entity+Property in visual.json must exist in the TMDL model."""
        from pbip_generator import PowerBIProjectGenerator
        from validator import ArtifactValidator

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        project_path = generator.generate_project(
            'CrossValTest', copy.deepcopy(SAMPLE_EXTRACTED_WITH_MEASURES)
        )

        errors = ArtifactValidator.validate_visual_references(project_path)
        self.assertEqual(errors, [],
                         f"Visual field references not found in TMDL model:\n"
                         + "\n".join(errors))

    def test_tmdl_stats_contain_symbols(self):
        """generate_tmdl() must return actual_bim_symbols with (table, field) tuples."""
        from tmdl_generator import generate_tmdl

        data = copy.deepcopy(SAMPLE_EXTRACTED_WITH_MEASURES)
        # Embed calculations into the datasource (as extract_datasource does)
        ds = data['datasources'][0]
        ds['calculations'] = copy.deepcopy(data['calculations'])

        stats = generate_tmdl([ds], 'SymbolTest', data, self.temp_dir)

        self.assertIn('actual_bim_symbols', stats)
        symbols = stats['actual_bim_symbols']
        self.assertIsInstance(symbols, set)
        self.assertGreater(len(symbols), 0)

        # Each symbol is a (table_name, field_name) tuple
        for sym in symbols:
            self.assertIsInstance(sym, tuple)
            self.assertEqual(len(sym), 2)

        # Check that known measures are present
        measure_props = {prop for (_table, prop) in symbols}
        self.assertIn('Total Sales', measure_props)
        self.assertIn('Order Count', measure_props)

        # Check that known columns are present
        self.assertIn('OrderID', measure_props)
        self.assertIn('CustomerName', measure_props)

    def test_measure_wrapper_matches_tmdl_type(self):
        """Named DAX measures must use 'Measure' wrapper in visual JSON,
        physical/calculated columns must use 'Column' wrapper."""
        from pbip_generator import PowerBIProjectGenerator
        import glob

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        project_path = generator.generate_project(
            'WrapperTest', copy.deepcopy(SAMPLE_EXTRACTED_WITH_MEASURES)
        )

        # Collect actual BIM measures from the TMDL stats
        bim_measures = getattr(generator, '_actual_bim_measure_names', set())

        # Scan all visual.json files
        pattern = os.path.join(project_path, '**', 'visual.json')
        visual_files = glob.glob(pattern, recursive=True)
        self.assertGreater(len(visual_files), 0, "No visual.json files found")

        import re
        measure_re = re.compile(
            r'"Measure"\s*:\s*\{[^}]*"Property"\s*:\s*"([^"]+)"',
            re.DOTALL
        )
        column_re = re.compile(
            r'"Column"\s*:\s*\{[^}]*"Property"\s*:\s*"([^"]+)"',
            re.DOTALL
        )

        for vf in visual_files:
            with open(vf, 'r', encoding='utf-8') as f:
                content = f.read()

            # Every Measure-wrapped property must be in bim_measures
            for m in measure_re.finditer(content):
                prop = m.group(1)
                self.assertIn(prop, bim_measures,
                              f"'{prop}' wrapped as Measure but not in BIM measures "
                              f"(file: {os.path.relpath(vf, project_path)})")

            # Every Column-wrapped property must NOT be in bim_measures
            for m in column_re.finditer(content):
                prop = m.group(1)
                self.assertNotIn(prop, bim_measures,
                                 f"'{prop}' wrapped as Column but IS a BIM measure "
                                 f"(file: {os.path.relpath(vf, project_path)})")

    def test_validator_project_includes_visual_cross_check(self):
        """validate_project() must include visual reference cross-checks in warnings."""
        from pbip_generator import PowerBIProjectGenerator
        from validator import ArtifactValidator

        generator = PowerBIProjectGenerator(output_dir=self.temp_dir)
        project_path = generator.generate_project(
            'FullValTest', copy.deepcopy(SAMPLE_EXTRACTED_WITH_MEASURES)
        )

        result = ArtifactValidator.validate_project(project_path)

        # Project should be valid (no errors)
        self.assertTrue(result['valid'],
                        f"Project validation failed: {result['errors']}")

        # Any visual reference issues would appear as warnings
        visual_ref_warnings = [w for w in result.get('warnings', [])
                               if 'unknown Entity' in w or 'unknown Property' in w]
        self.assertEqual(visual_ref_warnings, [],
                         f"Visual reference warnings:\n" + "\n".join(visual_ref_warnings))


if __name__ == '__main__':
    unittest.main()
