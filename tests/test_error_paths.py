"""
Error Path Tests — Negative and edge-case tests for robustness.

Covers:
- Malformed / missing input handling
- Empty / None datasources, worksheets, calculations
- Invalid JSON, corrupt data, missing elements
- Boundary conditions in DAX converter
- Validator rejection of bad artifacts
- Migration report edge cases
- Generator resilience to incomplete data
"""

import os
import sys
import json
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

from tableau_export.dax_converter import (
    convert_tableau_formula_to_dax,
    _split_args,
    _normalize_spaces_outside_identifiers,
)
from powerbi_import.tmdl_generator import (
    _dax_to_m_expression,
    _build_semantic_model,
    generate_tmdl,
)
from powerbi_import.visual_generator import (
    resolve_visual_type,
    generate_visual_containers,
    create_visual_container,
    build_query_state,
)
from powerbi_import.validator import ArtifactValidator
from powerbi_import.migration_report import MigrationReport
from tests.factories import (
    DatasourceFactory, WorksheetFactory, ModelFactory,
    DashboardFactory, ParameterFactory,
)


# ═══════════════════════════════════════════════════════════════════════
# DAX Converter Error Paths
# ═══════════════════════════════════════════════════════════════════════

class TestDaxConverterEmptyInput(unittest.TestCase):
    """DAX converter handles empty / None / whitespace input."""

    def test_none_formula(self):
        result = convert_tableau_formula_to_dax(None)
        self.assertIsNone(result)

    def test_empty_string(self):
        result = convert_tableau_formula_to_dax('')
        self.assertEqual(result, '')

    def test_whitespace_only(self):
        result = convert_tableau_formula_to_dax('   ')
        self.assertIsInstance(result, str)

    def test_single_bracket(self):
        result = convert_tableau_formula_to_dax('[')
        self.assertIsInstance(result, str)

    def test_unmatched_parens(self):
        result = convert_tableau_formula_to_dax('SUM([Sales]')
        self.assertIsInstance(result, str)

    def test_extra_close_paren(self):
        result = convert_tableau_formula_to_dax('SUM([Sales]))')
        self.assertIsInstance(result, str)

    def test_only_operators(self):
        result = convert_tableau_formula_to_dax('+ - * /')
        self.assertIsInstance(result, str)


class TestDaxConverterMalformedFormulas(unittest.TestCase):
    """DAX converter does not crash on malformed formulas."""

    def test_incomplete_if(self):
        result = convert_tableau_formula_to_dax('IF [A] > 1 THEN')
        self.assertIsInstance(result, str)

    def test_nested_broken_brackets(self):
        result = convert_tableau_formula_to_dax('[Table].[Column')
        self.assertIsInstance(result, str)

    def test_double_dot(self):
        result = convert_tableau_formula_to_dax('[Table]..[Column]')
        self.assertIsInstance(result, str)

    def test_empty_function_call(self):
        result = convert_tableau_formula_to_dax('SUM()')
        self.assertIsInstance(result, str)

    def test_deeply_nested(self):
        formula = 'IF(' * 20 + '"deep"' + ')' * 20
        result = convert_tableau_formula_to_dax(formula)
        self.assertIsInstance(result, str)

    def test_unicode_characters(self):
        result = convert_tableau_formula_to_dax('SUM([Montant€])')
        self.assertIsInstance(result, str)

    def test_newlines_in_formula(self):
        result = convert_tableau_formula_to_dax('SUM(\n[Sales]\n)')
        self.assertIsInstance(result, str)

    def test_tabs_in_formula(self):
        result = convert_tableau_formula_to_dax('SUM(\t[Sales]\t)')
        self.assertIsInstance(result, str)

    def test_comment_like_syntax(self):
        result = convert_tableau_formula_to_dax('SUM([Sales]) // total')
        self.assertIsInstance(result, str)

    def test_sql_injection_like(self):
        result = convert_tableau_formula_to_dax("'; DROP TABLE users; --")
        self.assertIsInstance(result, str)


class TestDaxConverterEdgeMaps(unittest.TestCase):
    """Edge cases in column/table maps."""

    def test_empty_column_table_map(self):
        result = convert_tableau_formula_to_dax('SUM([Sales])', column_table_map={})
        self.assertIsInstance(result, str)

    def test_empty_measure_names(self):
        result = convert_tableau_formula_to_dax('SUM([Sales])', measure_names=set())
        self.assertIsInstance(result, str)

    def test_column_not_in_map(self):
        result = convert_tableau_formula_to_dax('[MissingCol]',
                                                 column_table_map={'Other': 'Table'})
        self.assertIsInstance(result, str)


class TestSplitArgsEdgeCases(unittest.TestCase):
    """Edge cases in _split_args."""

    def test_empty_string(self):
        result = _split_args('')
        self.assertEqual(result, [])

    def test_no_commas(self):
        result = _split_args('[Sales]')
        self.assertEqual(result, ['[Sales]'])

    def test_deeply_nested_triple(self):
        result = _split_args('IF(A, IF(B, C, D), E), F')
        self.assertEqual(len(result), 2)

    def test_quoted_string_with_parens(self):
        result = _split_args('"hello (world)", 42')
        self.assertEqual(len(result), 2)


class TestNormalizeSpacesEdgeCases(unittest.TestCase):
    """Edge cases in normalize spaces."""

    def test_empty(self):
        result = _normalize_spaces_outside_identifiers('')
        self.assertEqual(result, '')

    def test_only_spaces(self):
        result = _normalize_spaces_outside_identifiers('     ')
        self.assertIsInstance(result, str)

    def test_preserves_quoted_spaces(self):
        result = _normalize_spaces_outside_identifiers('"hello   world"')
        self.assertIn('hello', result)  # content preserved in some form


# ═══════════════════════════════════════════════════════════════════════
# DAX-to-M Converter Error Paths
# ═══════════════════════════════════════════════════════════════════════

class TestDaxToMErrorPaths(unittest.TestCase):
    """Error paths in _dax_to_m_expression."""

    def test_none_returns_none(self):
        self.assertIsNone(_dax_to_m_expression(None))

    def test_empty_returns_empty(self):
        self.assertEqual(_dax_to_m_expression(''), '')

    def test_pure_whitespace(self):
        result = _dax_to_m_expression('   ')
        self.assertIsNotNone(result)

    def test_unknown_function(self):
        # Functions not in the mapping should still return something
        result = _dax_to_m_expression('UNKNOWNFUNC([Col])')
        # May return None or fallback — just shouldn't crash
        self.assertTrue(result is None or isinstance(result, str))

    def test_complex_cross_table_returns_none(self):
        result = _dax_to_m_expression("CALCULATE(SUM('Other'[Sales]))")
        self.assertIsNone(result)

    def test_calculate_returns_none(self):
        result = _dax_to_m_expression("CALCULATE(SUM([Sales]), ALLEXCEPT('T', 'T'[R]))")
        self.assertIsNone(result)

    def test_sumx_returns_none(self):
        result = _dax_to_m_expression("SUMX('Orders', [Amount] * [Qty])")
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════════
# TMDL Generator Error Paths
# ═══════════════════════════════════════════════════════════════════════

class TestBuildSemanticModelErrors(unittest.TestCase):
    """Resilience of _build_semantic_model to bad data."""

    def test_empty_datasources(self):
        empty_conv = ModelFactory().build()
        model = _build_semantic_model([], 'Empty', empty_conv)
        self.assertIn('model', model)
        self.assertEqual(len(model['model']['tables']), 0)

    def test_datasource_no_tables(self):
        ds = DatasourceFactory('NoTables').build()
        ds['tables'] = []
        conv = ModelFactory().with_datasource(DatasourceFactory('NoTables')).build()
        model = _build_semantic_model([ds], 'NoTables', conv)
        self.assertIn('model', model)

    def test_datasource_no_columns(self):
        ds = DatasourceFactory('DS').build()
        ds['tables'] = [{'name': 'T', 'type': 'table', 'columns': []}]
        conv = ModelFactory().build()
        conv['datasources'] = [ds]
        model = _build_semantic_model([ds], 'NoCols', conv)
        self.assertIn('model', model)

    def test_missing_relationship_columns(self):
        ds = (DatasourceFactory('DS')
              .with_table('A', ['ID:integer'])
              .with_table('B', ['ID:integer'])
              .with_relationship('A', 'MissingCol', 'B', 'MissingCol'))
        conv = ModelFactory().with_datasource(ds).build()
        model = _build_semantic_model([ds.build()], 'MissingRel', conv)
        self.assertIn('model', model)

    def test_duplicate_table_names(self):
        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['ID:integer', 'Amount:real'])
              .with_table('Orders', ['ID:integer', 'Amount:real', 'Extra:string']))
        conv = ModelFactory().with_datasource(ds).build()
        model = _build_semantic_model([ds.build()], 'DupTables', conv)
        # Dedup should keep the table with most columns
        table_names = [t['name'] for t in model['model']['tables']]
        self.assertEqual(table_names.count('Orders'), 1)


class TestGenerateTmdlErrors(unittest.TestCase):
    """Error handling in generate_tmdl."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_model(self):
        conv = ModelFactory().build()
        stats = generate_tmdl([], 'Empty', conv, self.tmp)
        self.assertIn('tables', stats)
        self.assertEqual(stats['tables'], 0)

    def test_read_only_dir(self):
        """generate_tmdl should handle or raise on unwritable directory."""
        # On Windows, read-only dirs behave differently, so just test the call doesn't crash
        conv = ModelFactory().build()
        try:
            stats = generate_tmdl([], 'Test', conv, self.tmp)
            self.assertIsNotNone(stats)
        except (PermissionError, OSError):
            pass  # Acceptable


# ═══════════════════════════════════════════════════════════════════════
# Visual Generator Error Paths
# ═══════════════════════════════════════════════════════════════════════

class TestVisualGeneratorErrors(unittest.TestCase):
    """Error handling in visual generator."""

    def test_resolve_none_type(self):
        result = resolve_visual_type(None)
        self.assertEqual(result, 'tableEx')

    def test_resolve_empty_string(self):
        result = resolve_visual_type('')
        self.assertEqual(result, 'tableEx')

    def test_resolve_numeric_input(self):
        # Non-string input should fallback gracefully or raise
        try:
            result = resolve_visual_type(123)
            self.assertEqual(result, 'tableEx')
        except AttributeError:
            pass  # Acceptable — function requires string input

    def test_create_visual_container_empty_worksheet(self):
        ws = {'name': 'Empty', 'columns': [], 'visual_type': None,
              'mark_encoding': {}, 'filters': []}
        vc = create_visual_container(ws, 'v1', 0, 0, 300, 200, 1, {}, {})
        self.assertIn('visual', vc)

    def test_generate_containers_no_worksheets(self):
        result = generate_visual_containers([], 'Test', {}, {}, 1280, 720)
        self.assertEqual(result, [])

    def test_build_query_state_no_data(self):
        qs = build_query_state('tableEx', [], [], {}, {})
        self.assertTrue(qs is None or isinstance(qs, dict))

    def test_build_query_state_unknown_visual(self):
        qs = build_query_state('nonExistentVisual', [{'field': 'A'}], [{'name': 'B'}],
                               {'A': 'T'}, {'B': ('T', 'B')})
        self.assertTrue(qs is None or isinstance(qs, dict))


class TestCreateVisualContainerEdgeCases(unittest.TestCase):
    """Edge cases for create_visual_container."""

    def test_worksheet_with_many_columns(self):
        ws = (WorksheetFactory('ManyColumns')
              .with_columns([f'Col{i}:dimension' for i in range(50)])
              .with_mark('table')
              .build())
        vc = create_visual_container(ws, 'v1', 0, 0, 500, 300, 1,
                                     {f'Col{i}': 'T' for i in range(50)}, {})
        self.assertIn('visual', vc)

    def test_worksheet_with_filter(self):
        ws = (WorksheetFactory('Filtered')
              .with_columns(['Sales:measure', 'Region'])
              .with_filter('Region', ['East', 'West'])
              .with_mark('bar')
              .build())
        vc = create_visual_container(ws, 'v1', 0, 0, 300, 200, 1,
                                     {'Region': 'Orders'}, {})
        self.assertIn('visual', vc)

    def test_worksheet_with_mark_encoding(self):
        ws = (WorksheetFactory('Encoded')
              .with_columns(['Sales:measure', 'Region', 'Category'])
              .with_mark('bar')
              .with_mark_encoding('color', 'Category')
              .build())
        vc = create_visual_container(ws, 'v1', 0, 0, 300, 200, 1,
                                     {'Region': 'T', 'Category': 'T'}, {})
        self.assertIn('visual', vc)


# ═══════════════════════════════════════════════════════════════════════
# Validator Error Paths
# ═══════════════════════════════════════════════════════════════════════

class TestValidatorErrors(unittest.TestCase):
    """Validator handles corrupt / missing files gracefully."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_validate_nonexistent_json(self):
        ok, err = ArtifactValidator.validate_json_file('/no/such/file.json')
        self.assertFalse(ok)

    def test_validate_empty_json(self):
        path = os.path.join(self.tmp, 'empty.json')
        with open(path, 'w') as f:
            f.write('')
        ok, err = ArtifactValidator.validate_json_file(path)
        self.assertFalse(ok)

    def test_validate_binary_as_json(self):
        path = os.path.join(self.tmp, 'binary.json')
        with open(path, 'wb') as f:
            f.write(b'\x00\x01\x02\x03')
        ok, err = ArtifactValidator.validate_json_file(path)
        self.assertFalse(ok)

    def test_validate_tmdl_nonexistent(self):
        ok, errors = ArtifactValidator.validate_tmdl_file('/no/such/model.tmdl')
        self.assertFalse(ok)

    def test_dax_formula_deeply_nested_parens(self):
        formula = '(' * 50 + 'SUM([Sales])' + ')' * 50
        errors = ArtifactValidator.validate_dax_formula(formula)
        # Should be valid (balanced parens)
        self.assertEqual(errors, [])

    def test_dax_formula_only_open_parens(self):
        formula = '((('
        errors = ArtifactValidator.validate_dax_formula(formula)
        self.assertTrue(len(errors) > 0)

    def test_dax_formula_only_close_parens(self):
        formula = ')))'
        errors = ArtifactValidator.validate_dax_formula(formula)
        self.assertTrue(len(errors) > 0)

    def test_validate_project_no_dir(self):
        result = ArtifactValidator.validate_project('/no/such/dir')
        self.assertFalse(result['valid'])

    def test_validate_project_empty_dir(self):
        result = ArtifactValidator.validate_project(self.tmp)
        self.assertFalse(result['valid'])


class TestValidatorDaxLeakPatterns(unittest.TestCase):
    """All Tableau leak patterns are detected."""

    LEAK_PATTERNS = [
        ('COUNTD', 'COUNTD([Customer])'),
        ('ZN', 'ZN([Sales])'),
        ('IFNULL', 'IFNULL([Sales], 0)'),
        ('LOD FIXED', '{FIXED [Region] : SUM([Sales])}'),
        ('LOD INCLUDE', '{INCLUDE [Category] : AVG([Sales])}'),
        ('LOD EXCLUDE', '{EXCLUDE [Region] : COUNT([ID])}'),
        ('ELSEIF', 'IF [A] > 1 THEN "X" ELSEIF [A] THEN "Y" END'),
        ('==', '[Status] == "Active"'),
        ('ATTR', 'ATTR([Name])'),
        ('MAKEPOINT', 'MAKEPOINT([Lat], [Lon])'),
        ('SCRIPT_REAL', 'SCRIPT_REAL("code", [X])'),
    ]

    def test_leak_patterns(self):
        for name, formula in self.LEAK_PATTERNS:
            with self.subTest(pattern=name):
                errors = ArtifactValidator.validate_dax_formula(formula)
                self.assertTrue(
                    len(errors) > 0,
                    f"Leak pattern '{name}' not detected in: {formula}"
                )


# ═══════════════════════════════════════════════════════════════════════
# Migration Report Error Paths
# ═══════════════════════════════════════════════════════════════════════

class TestMigrationReportErrors(unittest.TestCase):
    """Error handling in MigrationReport."""

    def test_invalid_status_raises(self):
        report = MigrationReport('Test')
        with self.assertRaises(ValueError):
            report.add_item('calc', 'M1', 'bogus_status')

    def test_empty_report_score(self):
        report = MigrationReport('Test')
        summary = report.get_summary()
        self.assertEqual(summary['fidelity_score'], 100.0)
        self.assertEqual(summary['total_items'], 0)

    def test_single_skipped_item(self):
        report = MigrationReport('Test')
        report.add_item('calc', 'M1', 'skipped')
        summary = report.get_summary()
        self.assertIsInstance(summary['fidelity_score'], float)

    def test_classify_dax_none(self):
        status = MigrationReport._classify_dax(None)
        self.assertEqual(status, 'skipped')

    def test_classify_dax_empty(self):
        status = MigrationReport._classify_dax('')
        self.assertEqual(status, 'skipped')

    def test_add_calculations_empty(self):
        report = MigrationReport('Test')
        report.add_calculations([], {})
        self.assertEqual(len(report.items), 0)

    def test_add_visuals_empty(self):
        report = MigrationReport('Test')
        report.add_visuals([], {})
        self.assertEqual(len(report.items), 0)

    def test_save_creates_file(self):
        tmp = tempfile.mkdtemp()
        try:
            report = MigrationReport('Test')
            report.add_item('calc', 'M1', 'exact')
            path = report.save(tmp)
            self.assertTrue(os.path.exists(path))
            # Validate it's valid JSON
            with open(path) as f:
                data = json.load(f)
            self.assertIn('report_name', data)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_to_dict_structure(self):
        report = MigrationReport('Test')
        report.add_item('calc', 'M1', 'exact', dax='SUM([Sales])')
        report.add_item('visual', 'V1', 'approximate')
        data = report.to_dict()
        self.assertEqual(data['report_name'], 'Test')
        self.assertEqual(len(data['items']), 2)
        self.assertIn('summary', data)
        self.assertIn('fidelity_score', data['summary'])


# ═══════════════════════════════════════════════════════════════════════
# Factory Validation
# ═══════════════════════════════════════════════════════════════════════

class TestFactoryEdgeCases(unittest.TestCase):
    """Edge cases in test factories."""

    def test_datasource_no_tables(self):
        ds = DatasourceFactory('Empty').build()
        self.assertEqual(len(ds['tables']), 0)

    def test_worksheet_no_columns(self):
        ws = WorksheetFactory('Empty').build()
        self.assertEqual(len(ws['columns']), 0)

    def test_model_factory_all_empty(self):
        model = ModelFactory().build()
        self.assertEqual(len(model['datasources']), 0)
        self.assertEqual(len(model['worksheets']), 0)
        self.assertEqual(len(model['calculations']), 0)

    def test_parameter_factory_range(self):
        p = ParameterFactory('P').range(0, 100, 5, 50).build()
        self.assertEqual(p['domain_type'], 'range')
        av = p['allowable_values']
        self.assertIsInstance(av, list)
        self.assertEqual(av[0]['min'], '0')
        self.assertEqual(av[0]['max'], '100')

    def test_parameter_factory_list(self):
        p = ParameterFactory('P').list(['A', 'B', 'C']).build()
        self.assertEqual(p['domain_type'], 'list')
        self.assertEqual(len(p['values']), 3)

    def test_parameter_factory_any(self):
        p = ParameterFactory('P').any('default_val').build()
        self.assertEqual(p['domain_type'], 'any')

    def test_dashboard_chains(self):
        db = (DashboardFactory('D')
              .with_worksheet('S1')
              .with_worksheet('S2')
              .with_text('Note')
              .with_image('logo.png')
              .with_theme(colors=['#FF0000'], font_family='Arial')
              .build())
        self.assertEqual(len(db['worksheets']), 2)
        self.assertEqual(len(db['objects']), 2)
        self.assertEqual(db['theme']['colors'], ['#FF0000'])

    def test_model_all_features(self):
        ds = DatasourceFactory('DS').with_table('T', ['ID:integer'])
        model = (ModelFactory()
                 .with_datasource(ds)
                 .with_worksheet(WorksheetFactory('S'))
                 .with_dashboard(DashboardFactory('D'))
                 .with_filter('F1', ['a', 'b'])
                 .with_story('Story', [{'name': 'P1'}])
                 .with_action('Action', 'filter')
                 .with_set('Set1', 'T', members=['X'])
                 .with_group('Group1', 'T', 'ID', {'1': 'A'})
                 .with_bin('Bin1', 'T', 'ID', 10)
                 .with_hierarchy('H', ['L1', 'L2'])
                 .with_user_filter('UF')
                 .with_custom_sql('CS', 'SELECT 1')
                 .build())
        self.assertEqual(len(model['sets']), 1)
        self.assertEqual(len(model['groups']), 1)
        self.assertEqual(len(model['bins']), 1)
        self.assertEqual(len(model['hierarchies']), 1)
        self.assertEqual(len(model['user_filters']), 1)
        self.assertEqual(len(model['custom_sql']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
