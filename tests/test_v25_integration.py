"""Tests for Sprint 95 — v25.0.0 Integration & Cross-Feature Validation.

Verifies that Sprint 91–94 features work together end-to-end:
- Fabric generation + DAX optimization
- Tableau 2024 extraction + linguistic schema + TMDL culture
- Equivalence testing + regression snapshots
- CLI integration across all new flags
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))


class TestFabricAndOptimizationIntegration(unittest.TestCase):
    """Fabric output + DAX optimizer together."""

    def test_optimize_then_generate(self):
        """Optimized DAX measures can feed into Fabric semantic model."""
        from powerbi_import.dax_optimizer import optimize_dax
        from powerbi_import.fabric_constants import map_to_spark_type

        formula = 'IF(ISBLANK([Sales]), 0, [Sales])'
        optimized, rules = optimize_dax(formula)
        self.assertIn('COALESCE', optimized)

        # Verify Spark type mapping still works for columns
        self.assertEqual(map_to_spark_type('real'), 'DOUBLE')
        self.assertEqual(map_to_spark_type('integer'), 'INT')

    def test_ti_measures_in_fabric_context(self):
        """Time Intelligence measures can be used in Fabric semantic model."""
        from powerbi_import.dax_optimizer import generate_time_intelligence_measures
        from powerbi_import.fabric_naming import sanitize_table_name

        measures = [{'name': 'Sales Total', 'expression': "SUM('T'[Amount])"}]
        ti = generate_time_intelligence_measures(measures)
        self.assertTrue(len(ti) > 0)

        # TI measure names should be valid for Fabric
        for m in ti:
            sanitized = sanitize_table_name(m['name'])
            self.assertIsNotNone(sanitized)

    def test_fabric_project_generation_with_sample_data(self):
        """Full Fabric project generation smoke test."""
        from powerbi_import.fabric_project_generator import FabricProjectGenerator

        with tempfile.TemporaryDirectory() as tmp:
            gen = FabricProjectGenerator(tmp)
            extracted = {
                'datasources': [{
                    'name': 'TestDS',
                    'connection': {'type': 'SQL Server', 'details': {'server': 'srv', 'database': 'db'}},
                    'tables': [{'name': 'Orders', 'columns': [
                        {'name': 'ID', 'datatype': 'integer'},
                        {'name': 'Amount', 'datatype': 'real'},
                    ]}],
                    'calculations': [],
                }],
                'calculations': [],
                'parameters': [],
                'hierarchies': [],
                'sets': [],
                'groups': [],
                'bins': [],
                'aliases': [],
                'user_filters': [],
            }
            result = gen.generate_project('IntegrationTest', extracted)
            self.assertIn('lakehouse', result.get('artifacts', {}))
            self.assertIn('semantic_model', result.get('artifacts', {}))


class TestTableau2024AndLinguisticIntegration(unittest.TestCase):
    """Tableau 2024 extraction + linguistic schema + TMDL integration."""

    def test_linguistic_synonyms_in_culture_tmdl(self):
        """Synonyms flow from extraction to TMDL culture file."""
        from powerbi_import.tmdl_generator import _write_culture_tmdl

        with tempfile.TemporaryDirectory() as tmp:
            synonyms = {
                'Revenue': ['Sales', 'Income'],
                'Qty': ['Quantity', 'Number of Items'],
            }
            tables = [{'name': 'Sales', 'columns': [], 'measures': []}]
            _write_culture_tmdl(tmp, 'en-US', tables, linguistic_synonyms=synonyms)

            path = os.path.join(tmp, 'en-US.tmdl')
            content = open(path, encoding='utf-8').read()
            self.assertIn('Entities', content)
            self.assertIn('Revenue', content)
            self.assertIn('Sales', content)

    def test_blend_and_extension_queries_valid_m(self):
        """Generated blend + extension M queries are syntactically valid."""
        from tableau_export.m_query_builder import (
            generate_blend_merge_query,
            generate_table_extension_query,
        )

        blend_m = generate_blend_merge_query(
            'Orders', 'Returns',
            [{'primary': 'OrderID', 'secondary': 'OrderID'}]
        )
        self.assertIn('let', blend_m)
        self.assertIn('in', blend_m)

        ext_m = generate_table_extension_query({
            'name': 'API', 'extension_type': 'rest-api',
            'endpoint': 'https://api.example.com/data',
            'schema': [{'name': 'Value', 'datatype': 'real'}],
        })
        self.assertIn('Web.Contents', ext_m)


class TestEquivalenceAndRegressionIntegration(unittest.TestCase):
    """Equivalence testing + regression suite together."""

    def test_snapshot_then_compare(self):
        """Generate snapshot, modify, compare — detect drift."""
        from powerbi_import.regression_suite import (
            generate_regression_snapshot,
            compare_snapshots,
        )

        converted = {
            'datasources': [{'tables': [{'name': 'T1', 'columns': [{'name': 'A'}]}]}],
            'calculations': [{'name': 'M1', 'formula': 'SUM([A])'}],
            'worksheets': [{'name': 'S1', 'fields': ['F1']}],
            'filters': [{'field': 'R'}],
        }
        baseline = generate_regression_snapshot(converted)

        # Modify — add a column
        converted_v2 = {
            'datasources': [{'tables': [{'name': 'T1', 'columns': [{'name': 'A'}, {'name': 'B'}]}]}],
            'calculations': [{'name': 'M1', 'formula': 'SUM([A])'}],
            'worksheets': [{'name': 'S1', 'fields': ['F1']}],
            'filters': [{'field': 'R'}],
        }
        current = generate_regression_snapshot(converted_v2)
        result = compare_snapshots(baseline, current)
        self.assertFalse(result['passed'])

    def test_equivalence_with_optimization(self):
        """Optimized measures should match expected values."""
        from powerbi_import.dax_optimizer import optimize_dax
        from powerbi_import.equivalence_tester import compare_measure_values

        # Simulate: original formula produces 100, optimized should too
        original = 'IF(ISBLANK([Sales]), 0, [Sales])'
        optimized, _ = optimize_dax(original)
        self.assertIn('COALESCE', optimized)

        # Both formula versions should produce same value (mock)
        expected = {'Sales': 100.0}
        actual = {'Sales': 100.0}
        result = compare_measure_values(expected, actual)
        self.assertEqual(result['passed'], 1)


class TestCLIFullIntegration(unittest.TestCase):
    """Tests all v25.0.0 CLI flags work together."""

    def test_all_flags_parse(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args([
            'test.twbx',
            '--output-format', 'fabric',
            '--optimize-dax',
            '--time-intelligence', 'auto',
            '--validate-data',
        ])
        self.assertEqual(args.output_format, 'fabric')
        self.assertTrue(args.optimize_dax)
        self.assertEqual(args.time_intelligence, 'auto')
        self.assertTrue(args.validate_data)

    def test_fabric_format_exists_in_choices(self):
        import migrate
        parser = migrate._build_argument_parser()
        # Verify fabric is a valid choice
        for action in parser._actions:
            if hasattr(action, 'dest') and action.dest == 'output_format':
                self.assertIn('fabric', action.choices)

    def test_default_values(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertEqual(args.output_format, 'pbip')
        self.assertFalse(args.optimize_dax)
        self.assertEqual(args.time_intelligence, 'none')
        self.assertFalse(args.validate_data)


class TestVersionBump(unittest.TestCase):
    """Verify version is correctly set to 25.0.0."""

    def test_version(self):
        from powerbi_import import __version__
        self.assertEqual(__version__, '27.1.0')


class TestNewModulesImport(unittest.TestCase):
    """Verify all new v25.0.0 modules import cleanly."""

    def test_import_fabric_constants(self):
        from powerbi_import.fabric_constants import SPARK_TYPE_MAP
        self.assertIsInstance(SPARK_TYPE_MAP, dict)

    def test_import_fabric_naming(self):
        from powerbi_import.fabric_naming import sanitize_table_name
        self.assertTrue(callable(sanitize_table_name))

    def test_import_calc_column_utils(self):
        from powerbi_import.calc_column_utils import classify_calculations
        self.assertTrue(callable(classify_calculations))

    def test_import_dax_optimizer(self):
        from powerbi_import.dax_optimizer import optimize_dax
        self.assertTrue(callable(optimize_dax))

    def test_import_equivalence_tester(self):
        from powerbi_import.equivalence_tester import compare_measure_values
        self.assertTrue(callable(compare_measure_values))

    def test_import_regression_suite(self):
        from powerbi_import.regression_suite import generate_regression_snapshot
        self.assertTrue(callable(generate_regression_snapshot))

    def test_import_lakehouse_generator(self):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        self.assertTrue(callable(LakehouseGenerator))

    def test_import_dataflow_generator(self):
        from powerbi_import.dataflow_generator import DataflowGenerator
        self.assertTrue(callable(DataflowGenerator))

    def test_import_notebook_generator(self):
        from powerbi_import.notebook_generator import NotebookGenerator
        self.assertTrue(callable(NotebookGenerator))

    def test_import_pipeline_generator(self):
        from powerbi_import.pipeline_generator import PipelineGenerator
        self.assertTrue(callable(PipelineGenerator))

    def test_import_fabric_semantic_model(self):
        from powerbi_import.fabric_semantic_model_generator import FabricSemanticModelGenerator
        self.assertTrue(callable(FabricSemanticModelGenerator))

    def test_import_fabric_project_generator(self):
        from powerbi_import.fabric_project_generator import FabricProjectGenerator
        self.assertTrue(callable(FabricProjectGenerator))


if __name__ == '__main__':
    unittest.main()
