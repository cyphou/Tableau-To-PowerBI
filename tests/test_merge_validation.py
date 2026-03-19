"""Tests for Sprint 55 — Post-Merge Safety: Cycle Detection,
Column Type Validation & DAX Integrity.

Covers:
- Relationship cycle detection (detect_merge_cycles)
- Column type compatibility matrix (check_type_compatibility, detect_type_conflicts)
- DAX reference validation (validate_merged_dax_references)
- RELATED/LOOKUPVALUE cardinality audit (validate_dax_relationship_functions)
- Validation summary report (generate_merge_validation_report)
- _find_closest helper
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.shared_model import (
    check_type_compatibility,
    detect_merge_cycles,
    detect_type_conflicts,
    validate_merged_dax_references,
    validate_dax_relationship_functions,
    generate_merge_validation_report,
    _find_closest,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_merged(*rels, tables=None, calcs=None, params=None):
    """Build a minimal merged dict with relationships, tables, and calcs."""
    if tables is None:
        tables = []
    ds = {'tables': tables, 'relationships': list(rels)}
    return {
        'datasources': [ds],
        'calculations': calcs or [],
        'parameters': params or [],
    }


def _rel(from_table, from_col, to_table, to_col, cardinality='manyToOne'):
    return {
        'from_table': from_table,
        'from_column': from_col,
        'to_table': to_table,
        'to_column': to_col,
        'cardinality': cardinality,
    }


def _table(name, columns=None, type_history=None):
    t = {'name': name, 'columns': columns or []}
    if type_history:
        t['_column_type_history'] = type_history
    return t


def _col(name, datatype='string'):
    return {'name': name, 'datatype': datatype}


def _calc(name, formula, classification='measure'):
    return {'caption': name, 'dax_formula': formula, 'classification': classification}


# ═══════════════════════════════════════════════════════════════════════════
#  Test: Cycle Detection
# ═══════════════════════════════════════════════════════════════════════════

class TestDetectMergeCycles(unittest.TestCase):
    """Tests for detect_merge_cycles()."""

    def test_no_relationships_no_cycles(self):
        merged = _make_merged()
        self.assertEqual(detect_merge_cycles(merged), [])

    def test_linear_chain_no_cycle(self):
        merged = _make_merged(
            _rel('A', 'id', 'B', 'a_id'),
            _rel('B', 'id', 'C', 'b_id'),
            _rel('C', 'id', 'D', 'c_id'),
        )
        self.assertEqual(detect_merge_cycles(merged), [])

    def test_simple_2_node_cycle(self):
        merged = _make_merged(
            _rel('A', 'id', 'B', 'a_id'),
            _rel('B', 'id', 'A', 'b_id'),
        )
        cycles = detect_merge_cycles(merged)
        self.assertGreaterEqual(len(cycles), 1)
        # At least one cycle should involve both A and B
        flat = [node for cycle in cycles for node in cycle]
        self.assertIn('A', flat)
        self.assertIn('B', flat)

    def test_3_node_cycle(self):
        merged = _make_merged(
            _rel('Orders', 'id', 'Products', 'order_id'),
            _rel('Products', 'id', 'Suppliers', 'product_id'),
            _rel('Suppliers', 'id', 'Orders', 'supplier_id'),
        )
        cycles = detect_merge_cycles(merged)
        self.assertGreaterEqual(len(cycles), 1)

    def test_disconnected_components_no_cycle(self):
        merged = _make_merged(
            _rel('A', 'id', 'B', 'a_id'),
            _rel('C', 'id', 'D', 'c_id'),
        )
        self.assertEqual(detect_merge_cycles(merged), [])

    def test_self_loop(self):
        merged = _make_merged(
            _rel('A', 'id', 'A', 'parent_id'),
        )
        cycles = detect_merge_cycles(merged)
        self.assertGreaterEqual(len(cycles), 1)

    def test_cycle_with_branch(self):
        """Cycle A→B→C→A with branch B→D (no cycle on D)."""
        merged = _make_merged(
            _rel('A', 'id', 'B', 'a_id'),
            _rel('B', 'id', 'C', 'b_id'),
            _rel('C', 'id', 'A', 'c_id'),
            _rel('B', 'id', 'D', 'b_id'),
        )
        cycles = detect_merge_cycles(merged)
        self.assertGreaterEqual(len(cycles), 1)

    def test_left_right_format(self):
        """Cycle using left/right relationship format."""
        merged = {
            'datasources': [{
                'tables': [],
                'relationships': [
                    {'left': {'table': 'X', 'column': 'id'},
                     'right': {'table': 'Y', 'column': 'x_id'}},
                    {'left': {'table': 'Y', 'column': 'id'},
                     'right': {'table': 'X', 'column': 'y_id'}},
                ],
            }],
            'calculations': [],
            'parameters': [],
        }
        cycles = detect_merge_cycles(merged)
        self.assertGreaterEqual(len(cycles), 1)

    def test_empty_datasources(self):
        merged = {'datasources': [], 'calculations': [], 'parameters': []}
        self.assertEqual(detect_merge_cycles(merged), [])


# ═══════════════════════════════════════════════════════════════════════════
#  Test: Column Type Compatibility
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckTypeCompatibility(unittest.TestCase):
    """Tests for check_type_compatibility()."""

    def test_same_type_ok(self):
        for t in ('boolean', 'integer', 'real', 'string', 'datetime', 'currency'):
            self.assertEqual(check_type_compatibility(t, t), 'ok')

    def test_safe_promotions(self):
        self.assertEqual(check_type_compatibility('boolean', 'integer'), 'ok')
        self.assertEqual(check_type_compatibility('integer', 'real'), 'ok')
        self.assertEqual(check_type_compatibility('integer', 'string'), 'ok')
        self.assertEqual(check_type_compatibility('real', 'string'), 'ok')
        self.assertEqual(check_type_compatibility('boolean', 'string'), 'ok')
        self.assertEqual(check_type_compatibility('currency', 'real'), 'ok')

    def test_safe_promotion_reverse(self):
        """Reverse direction should also be ok (wider type absorbs)."""
        self.assertEqual(check_type_compatibility('real', 'integer'), 'ok')
        self.assertEqual(check_type_compatibility('string', 'boolean'), 'ok')

    def test_datetime_numeric_error(self):
        self.assertEqual(check_type_compatibility('datetime', 'boolean'), 'error')
        self.assertEqual(check_type_compatibility('datetime', 'integer'), 'error')
        self.assertEqual(check_type_compatibility('datetime', 'real'), 'error')

    def test_datetime_numeric_reverse(self):
        self.assertEqual(check_type_compatibility('integer', 'datetime'), 'error')

    def test_datetime_string_ok(self):
        self.assertEqual(check_type_compatibility('datetime', 'string'), 'ok')

    def test_case_insensitive(self):
        self.assertEqual(check_type_compatibility('Boolean', 'INTEGER'), 'ok')

    def test_int64_alias(self):
        self.assertEqual(check_type_compatibility('int64', 'real'), 'ok')
        self.assertEqual(check_type_compatibility('int64', 'string'), 'ok')


class TestDetectTypeConflicts(unittest.TestCase):
    """Tests for detect_type_conflicts()."""

    def test_no_conflicts(self):
        merged = _make_merged(
            tables=[_table('T', [_col('A', 'integer')])]
        )
        self.assertEqual(detect_type_conflicts(merged), [])

    def test_no_type_history_no_warning(self):
        merged = _make_merged(
            tables=[_table('T', [_col('A', 'integer')])]
        )
        self.assertEqual(detect_type_conflicts(merged), [])

    def test_warning_on_datetime_integer(self):
        merged = _make_merged(
            tables=[_table('T', [_col('A', 'string')],
                           type_history={'a': ['datetime', 'integer']})]
        )
        warnings = detect_type_conflicts(merged)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]['level'], 'error')
        self.assertEqual(warnings[0]['column'], 'a')

    def test_ok_promotion_no_warning(self):
        merged = _make_merged(
            tables=[_table('T', [_col('A', 'real')],
                           type_history={'a': ['integer', 'real']})]
        )
        warnings = detect_type_conflicts(merged)
        self.assertEqual(len(warnings), 0)

    def test_multiple_conflicts(self):
        merged = _make_merged(
            tables=[_table('T', [_col('X'), _col('Y')],
                           type_history={
                               'x': ['datetime', 'boolean'],
                               'y': ['integer', 'real'],
                           })]
        )
        warnings = detect_type_conflicts(merged)
        # Only datetime↔boolean should flag, integer↔real is ok
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]['column'], 'x')


# ═══════════════════════════════════════════════════════════════════════════
#  Test: DAX Reference Validation
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateMergedDaxReferences(unittest.TestCase):
    """Tests for validate_merged_dax_references()."""

    def test_valid_ref_no_errors(self):
        merged = _make_merged(
            tables=[_table('Sales', [_col('Amount')])],
            calcs=[_calc('Total', "SUM('Sales'[Amount])")]
        )
        errors = validate_merged_dax_references(merged)
        self.assertEqual(errors, [])

    def test_missing_table_error(self):
        merged = _make_merged(
            tables=[_table('Sales', [_col('Amount')])],
            calcs=[_calc('Total', "SUM('Orders'[Quantity])")]
        )
        errors = validate_merged_dax_references(merged)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['status'], 'error_table')
        self.assertEqual(errors[0]['table'], 'Orders')

    def test_missing_column_error(self):
        merged = _make_merged(
            tables=[_table('Sales', [_col('Amount')])],
            calcs=[_calc('Total', "SUM('Sales'[Quantity])")]
        )
        errors = validate_merged_dax_references(merged)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['status'], 'error_column')
        self.assertEqual(errors[0]['column'], 'Quantity')

    def test_suggestion_for_close_table(self):
        merged = _make_merged(
            tables=[_table('Sales', [_col('Amount')])],
            calcs=[_calc('Total', "SUM('Sale'[Amount])")]
        )
        errors = validate_merged_dax_references(merged)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['suggestion'], 'Sales')

    def test_suggestion_for_close_column(self):
        merged = _make_merged(
            tables=[_table('Sales', [_col('Amount')])],
            calcs=[_calc('Total', "SUM('Sales'[Amoun])")]
        )
        errors = validate_merged_dax_references(merged)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['suggestion'], 'Amount')

    def test_multiple_refs_in_formula(self):
        merged = _make_merged(
            tables=[_table('Sales', [_col('Amount'), _col('Qty')])],
            calcs=[_calc('M', "'Sales'[Amount] * 'Sales'[Qty]")]
        )
        errors = validate_merged_dax_references(merged)
        self.assertEqual(errors, [])

    def test_no_calcs_no_errors(self):
        merged = _make_merged(tables=[_table('T', [_col('C')])])
        self.assertEqual(validate_merged_dax_references(merged), [])

    def test_parameter_table_recognized(self):
        merged = _make_merged(
            tables=[_table('Sales', [_col('Amount')])],
            calcs=[_calc('X', "SUM('Sales'[Amount])")],
            params=[{'caption': 'Threshold', 'name': 'p'}]
        )
        errors = validate_merged_dax_references(merged)
        self.assertEqual(errors, [])

    def test_empty_formula_no_error(self):
        merged = _make_merged(
            tables=[_table('T', [_col('C')])],
            calcs=[{'caption': 'M', 'dax_formula': '', 'classification': 'measure'}]
        )
        self.assertEqual(validate_merged_dax_references(merged), [])


# ═══════════════════════════════════════════════════════════════════════════
#  Test: RELATED / LOOKUPVALUE Cardinality Audit
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateDaxRelationshipFunctions(unittest.TestCase):
    """Tests for validate_dax_relationship_functions()."""

    def test_related_with_many_to_one_ok(self):
        merged = _make_merged(
            _rel('Sales', 'ProductID', 'Products', 'ID', 'manyToOne'),
            tables=[_table('Sales', [_col('ProductID')]),
                    _table('Products', [_col('ID'), _col('Name')])],
            calcs=[_calc('ProdName', "RELATED('Products'[Name])",
                         classification='calculated_column')]
        )
        mismatches = validate_dax_relationship_functions(merged)
        self.assertEqual(mismatches, [])

    def test_related_with_many_to_many_warns(self):
        merged = _make_merged(
            _rel('Sales', 'CustID', 'Customers', 'ID', 'manyToMany'),
            tables=[_table('Sales', [_col('CustID')]),
                    _table('Customers', [_col('ID'), _col('Name')])],
            calcs=[_calc('CName', "RELATED('Customers'[Name])")]
        )
        mismatches = validate_dax_relationship_functions(merged)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]['function'], 'RELATED')
        self.assertEqual(mismatches[0]['actual'], 'manyToMany')

    def test_related_no_relationship_error(self):
        merged = _make_merged(
            tables=[_table('Sales', [_col('CustID')]),
                    _table('Products', [_col('ID')])],
            calcs=[_calc('PName', "RELATED('Products'[ID])")]
        )
        mismatches = validate_dax_relationship_functions(merged)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]['actual'], 'no_relationship')

    def test_lookupvalue_with_many_to_one_info(self):
        merged = _make_merged(
            _rel('Sales', 'ProdID', 'Products', 'ID', 'manyToOne'),
            tables=[_table('Sales', [_col('ProdID')]),
                    _table('Products', [_col('ID'), _col('Name')])],
            calcs=[_calc('PName', "LOOKUPVALUE('Products'[Name], 'Products'[ID], 1)")]
        )
        mismatches = validate_dax_relationship_functions(merged)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]['function'], 'LOOKUPVALUE')
        self.assertEqual(mismatches[0]['status'], 'info')

    def test_no_dax_functions_no_issues(self):
        merged = _make_merged(
            _rel('A', 'id', 'B', 'a_id'),
            tables=[_table('A', [_col('id')]), _table('B', [_col('a_id')])],
            calcs=[_calc('M', "SUM('A'[id])")]
        )
        self.assertEqual(validate_dax_relationship_functions(merged), [])

    def test_multiple_related_functions(self):
        merged = _make_merged(
            _rel('Sales', 'PID', 'Products', 'ID', 'manyToOne'),
            tables=[_table('Sales', [_col('PID')]),
                    _table('Products', [_col('ID'), _col('Name'), _col('Cat')])],
            calcs=[_calc('Info',
                         "RELATED('Products'[Name]) & RELATED('Products'[Cat])")]
        )
        # Both RELATED calls should be valid with manyToOne
        mismatches = validate_dax_relationship_functions(merged)
        self.assertEqual(mismatches, [])


# ═══════════════════════════════════════════════════════════════════════════
#  Test: Validation Summary Report
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateMergeValidationReport(unittest.TestCase):
    """Tests for generate_merge_validation_report()."""

    def test_clean_merge_score_100(self):
        merged = _make_merged(
            _rel('A', 'id', 'B', 'a_id'),
            tables=[_table('A', [_col('id')]), _table('B', [_col('a_id')])],
            calcs=[_calc('M', "SUM('A'[id])")]
        )
        report = generate_merge_validation_report(merged)
        self.assertEqual(report['score'], 100)
        self.assertTrue(report['passed'])
        self.assertEqual(report['cycles'], [])
        self.assertEqual(report['dax_errors'], [])

    def test_cycle_reduces_score(self):
        merged = _make_merged(
            _rel('A', 'id', 'B', 'a_id'),
            _rel('B', 'id', 'A', 'b_id'),
            tables=[_table('A', [_col('id')]), _table('B', [_col('a_id')])],
        )
        report = generate_merge_validation_report(merged)
        self.assertLess(report['score'], 100)
        self.assertFalse(report['passed'])
        self.assertGreater(report['counts']['cycles'], 0)

    def test_dax_errors_reduce_score(self):
        merged = _make_merged(
            tables=[_table('Sales', [_col('Amount')])],
            calcs=[_calc('Bad', "SUM('Missing'[Col])")]
        )
        report = generate_merge_validation_report(merged)
        self.assertLess(report['score'], 100)
        self.assertGreater(report['counts']['dax_errors'], 0)

    def test_type_error_fails_passed(self):
        merged = _make_merged(
            tables=[_table('T', [_col('X')],
                           type_history={'x': ['datetime', 'boolean']})]
        )
        report = generate_merge_validation_report(merged)
        self.assertFalse(report['passed'])
        self.assertGreater(report['counts']['type_errors'], 0)

    def test_type_warning_does_not_block(self):
        """Type warnings don't block (passed still True if no errors/cycles)."""
        merged = _make_merged(
            tables=[_table('T', [_col('X')],
                           type_history={'x': ['string', 'integer']})]
        )
        report = generate_merge_validation_report(merged)
        # string↔integer promotion is 'ok' via safe promotion, so no warning
        # Let's use a truly non-standard type that isn't in matrix
        merged2 = _make_merged(
            tables=[_table('T', [_col('X')],
                           type_history={'x': ['custom_type', 'integer']})]
        )
        report2 = generate_merge_validation_report(merged2)
        # custom_type isn't in matrix → defaults to 'warn'
        self.assertTrue(report2['passed'])  # warnings don't block

    def test_report_keys(self):
        merged = _make_merged()
        report = generate_merge_validation_report(merged)
        for key in ('cycles', 'type_warnings', 'dax_errors',
                    'cardinality_mismatches', 'counts', 'score', 'passed'):
            self.assertIn(key, report)

    def test_counts_keys(self):
        merged = _make_merged()
        report = generate_merge_validation_report(merged)
        for key in ('cycles', 'type_errors', 'type_warnings',
                    'dax_errors', 'cardinality_mismatches'):
            self.assertIn(key, report['counts'])

    def test_score_clamped_at_zero(self):
        """Score never goes below 0 even with many issues."""
        merged = _make_merged(
            _rel('A', 'id', 'B', 'a_id'),
            _rel('B', 'id', 'A', 'b_id'),
            tables=[
                _table('T', [_col('X')],
                       type_history={'x': ['datetime', 'boolean']}),
                _table('A', [_col('id')]),
                _table('B', [_col('a_id')]),
            ],
            calcs=[
                _calc('M1', "SUM('Missing1'[C])"),
                _calc('M2', "SUM('Missing2'[C])"),
                _calc('M3', "SUM('Missing3'[C])"),
                _calc('M4', "SUM('Missing4'[C])"),
                _calc('M5', "SUM('Missing5'[C])"),
                _calc('M6', "SUM('Missing6'[C])"),
                _calc('M7', "SUM('Missing7'[C])"),
                _calc('M8', "SUM('Missing8'[C])"),
            ],
        )
        report = generate_merge_validation_report(merged)
        self.assertEqual(report['score'], 0)


# ═══════════════════════════════════════════════════════════════════════════
#  Test: _find_closest helper
# ═══════════════════════════════════════════════════════════════════════════

class TestFindClosest(unittest.TestCase):
    """Tests for _find_closest()."""

    def test_exact_match(self):
        self.assertEqual(_find_closest('Sales', {'Sales', 'Orders'}), 'Sales')

    def test_close_match(self):
        self.assertEqual(_find_closest('Sale', {'Sales', 'Orders'}), 'Sales')

    def test_no_close_match(self):
        result = _find_closest('XYZZY', {'Sales', 'Orders'})
        self.assertIsNone(result)

    def test_empty_candidates(self):
        self.assertIsNone(_find_closest('test', set()))

    def test_case_insensitive(self):
        result = _find_closest('sales', {'Sales', 'Orders'})
        self.assertEqual(result, 'Sales')


# ═══════════════════════════════════════════════════════════════════════════
#  Test: _merge_columns_into type history tracking
# ═══════════════════════════════════════════════════════════════════════════

class TestMergeColumnsTypeHistory(unittest.TestCase):
    """Tests that _merge_columns_into populates _column_type_history."""

    def test_type_history_populated(self):
        from powerbi_import.shared_model import _merge_columns_into
        existing = {'columns': [{'name': 'Amount', 'datatype': 'integer'}]}
        new_table = {'columns': [{'name': 'Amount', 'datatype': 'real'}]}
        _merge_columns_into(existing, new_table)
        history = existing.get('_column_type_history', {})
        self.assertIn('amount', history)
        self.assertEqual(len(history['amount']), 2)
        self.assertIn('integer', history['amount'])
        self.assertIn('real', history['amount'])

    def test_type_history_new_column_no_history(self):
        from powerbi_import.shared_model import _merge_columns_into
        existing = {'columns': [{'name': 'A', 'datatype': 'string'}]}
        new_table = {'columns': [{'name': 'B', 'datatype': 'integer'}]}
        _merge_columns_into(existing, new_table)
        history = existing.get('_column_type_history', {})
        # New column added but only appears once — no conflict to track
        self.assertIn('a', history)

    def test_wider_type_wins(self):
        from powerbi_import.shared_model import _merge_columns_into
        existing = {'columns': [{'name': 'Val', 'datatype': 'integer'}]}
        new_table = {'columns': [{'name': 'Val', 'datatype': 'real'}]}
        _merge_columns_into(existing, new_table)
        # Wider type (real) should win
        col = [c for c in existing['columns'] if c['name'] == 'Val'][0]
        self.assertEqual(col['datatype'], 'real')


# ═══════════════════════════════════════════════════════════════════════════
#  Test: Edge cases and integration
# ═══════════════════════════════════════════════════════════════════════════

class TestMergeValidationEdgeCases(unittest.TestCase):
    """Edge case tests for merge validation functions."""

    def test_cycle_detection_with_many_relationships(self):
        """No false positives in large star schema."""
        rels = [_rel(f'Dim{i}', 'id', 'Fact', f'dim{i}_id') for i in range(20)]
        merged = _make_merged(*rels)
        self.assertEqual(detect_merge_cycles(merged), [])

    def test_dax_validation_with_complex_formula(self):
        merged = _make_merged(
            tables=[
                _table('Sales', [_col('Amount'), _col('Qty')]),
                _table('Products', [_col('Name'), _col('Cat')]),
            ],
            calcs=[_calc('Complex',
                         "CALCULATE(SUM('Sales'[Amount]), "
                         "FILTER('Products', 'Products'[Cat] = \"A\"))")]
        )
        errors = validate_merged_dax_references(merged)
        self.assertEqual(errors, [])

    def test_validation_report_with_empty_model(self):
        merged = _make_merged()
        report = generate_merge_validation_report(merged)
        self.assertEqual(report['score'], 100)
        self.assertTrue(report['passed'])

    def test_validation_report_cardinality_counted(self):
        merged = _make_merged(
            tables=[_table('S', [_col('PID')]),
                    _table('P', [_col('ID'), _col('Name')])],
            calcs=[_calc('X', "RELATED('P'[Name])")]
        )
        report = generate_merge_validation_report(merged)
        # No relationship defined → RELATED error
        self.assertGreater(report['counts']['cardinality_mismatches'], 0)


if __name__ == '__main__':
    unittest.main()
