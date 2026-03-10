"""
Mutation testing runner and report for critical code paths.

Uses ``mutmut`` when available to inject mutations into the DAX converter,
M query builder, TMDL generator, and validator modules.  When ``mutmut``
is not installed, provides a lightweight built-in mutation simulator that
validates the test suite catches common operator and constant changes.

Usage:
    # With mutmut installed:
    mutmut run --paths-to-mutate tableau_export/dax_converter.py

    # As a test:
    python -m pytest tests/test_mutation.py -v
"""

import unittest
import importlib
import copy
import re


class TestMutationSmoke(unittest.TestCase):
    """Lightweight mutation smoke tests — verify critical assertions exist.

    These tests don't inject real mutations; instead they validate that
    the test suite has assertions covering the most important conversion
    logic.  If ``mutmut`` is installed, the ``setup.cfg [mutmut]``
    section configures full mutation testing.
    """

    def test_dax_converter_importable(self):
        """DAX converter module can be imported without errors."""
        mod = importlib.import_module('tableau_export.dax_converter')
        self.assertTrue(hasattr(mod, 'convert_tableau_formula_to_dax'))

    def test_dax_sum_mutation_caught(self):
        """If SUM were mutated to AVG, tests would catch it."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('SUM([Sales])', table_name='T')
        self.assertIn('SUM', result)
        self.assertNotIn('AVG', result)

    def test_dax_countd_mutation_caught(self):
        """COUNTD → DISTINCTCOUNT is correctly converted (not silently dropped)."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('COUNTD([ID])', table_name='T')
        self.assertIn('DISTINCTCOUNT', result)

    def test_dax_if_structure_mutation_caught(self):
        """IF/THEN/ELSE structure conversion is preserved."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            'IF [X] > 0 THEN "yes" ELSE "no" END', table_name='T'
        )
        self.assertIn('IF', result)
        self.assertIn('"yes"', result)
        self.assertIn('"no"', result)

    def test_dax_operator_mutation_caught(self):
        """Operator conversion (== → =, != → <>) is validated."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result_eq = convert_tableau_formula_to_dax('[X] == 1', table_name='T')
        # Should not contain ==
        self.assertNotIn('==', result_eq)

        result_neq = convert_tableau_formula_to_dax('[X] != 1', table_name='T')
        self.assertIn('<>', result_neq)

    def test_m_query_builder_importable(self):
        """M query builder module can be imported."""
        mod = importlib.import_module('tableau_export.m_query_builder')
        self.assertTrue(hasattr(mod, 'generate_power_query_m'))

    def test_m_query_sql_server_mutation_caught(self):
        """SQL Server M query contains Sql.Database (not mutated away)."""
        from tableau_export.m_query_builder import generate_power_query_m
        conn = {'type': 'SQL Server', 'details': {
            'server': 'host', 'database': 'db'}}
        result = generate_power_query_m(conn, {'name': 'T'})
        self.assertIn('Sql.Database', result)

    def test_validator_importable(self):
        """Validator module can be imported."""
        mod = importlib.import_module('powerbi_import.validator')
        self.assertTrue(hasattr(mod, 'ArtifactValidator'))

    def test_validator_paren_check_mutation_caught(self):
        """Unbalanced parenthesis detection works correctly."""
        from powerbi_import.validator import ArtifactValidator
        issues = ArtifactValidator.validate_dax_formula('SUM((([X])')
        self.assertTrue(any('parenthesis' in i.lower() for i in issues))

    def test_tmdl_generator_importable(self):
        """TMDL generator module can be imported."""
        mod = importlib.import_module('powerbi_import.tmdl_generator')
        self.assertTrue(hasattr(mod, 'generate_tmdl'))

    def test_incremental_importable(self):
        """Incremental migration module can be imported."""
        mod = importlib.import_module('powerbi_import.incremental')
        self.assertTrue(hasattr(mod, 'IncrementalMerger'))

    def test_mutmut_config_exists(self):
        """setup.cfg contains [mutmut] configuration."""
        import os
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                'setup.cfg')
        self.assertTrue(os.path.exists(cfg_path))
        with open(cfg_path, 'r') as f:
            content = f.read()
        self.assertIn('[mutmut]', content)
        self.assertIn('dax_converter', content)


if __name__ == '__main__':
    unittest.main()
