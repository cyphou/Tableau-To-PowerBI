"""
Property-based tests for DAX formula conversion robustness.

Uses ``hypothesis`` for fuzzing when available; falls back to a lightweight
built-in generator when the library is not installed (no external
dependency required).

These tests verify that ``convert_tableau_formula_to_dax`` never raises
an unhandled exception, always returns a string, and preserves basic
structural invariants regardless of the input.
"""

import re
import string
import random
import unittest

from tableau_export.dax_converter import convert_tableau_formula_to_dax

# ── Try importing hypothesis; fall back gracefully ────────────────

try:
    from hypothesis import given, settings, HealthCheck
    from hypothesis import strategies as st
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


# ── Lightweight built-in fuzzer (no dependencies) ─────────────────

# Tableau function names that appear in real formulas
_TABLEAU_FUNCTIONS = [
    'SUM', 'AVG', 'COUNT', 'COUNTD', 'MIN', 'MAX', 'MEDIAN',
    'IF', 'IIF', 'CASE', 'ZN', 'IFNULL', 'ISNULL',
    'DATETRUNC', 'DATEPART', 'DATEDIFF', 'DATEADD',
    'LEFT', 'RIGHT', 'MID', 'UPPER', 'LOWER', 'LEN', 'TRIM',
    'CONTAINS', 'FIND', 'REPLACE', 'SPLIT',
    'ROUND', 'CEILING', 'FLOOR', 'ABS', 'POWER', 'SQRT', 'LOG',
    'RUNNING_SUM', 'RUNNING_AVG', 'RANK', 'WINDOW_SUM',
    'ATTR', 'LOOKUP', 'PREVIOUS_VALUE',
    'STR', 'INT', 'FLOAT', 'DATE', 'DATETIME',
    'TODAY', 'NOW', 'YEAR', 'MONTH', 'DAY',
]

_OPERATORS = ['+', '-', '*', '/', '==', '!=', '>', '<', '>=', '<=',
              ' AND ', ' OR ', ' and ', ' or ']

_COLUMN_NAMES = ['[Sales]', '[Profit]', '[Date]', '[Name]', '[Qty]',
                 '[Category]', '[Region]', '[ID]']


def _random_formula(rng=None):
    """Generate a random Tableau-like formula string."""
    if rng is None:
        rng = random.Random()
    depth = rng.randint(0, 3)
    return _random_expr(rng, depth)


def _random_expr(rng, depth):
    """Recursively generate a random expression."""
    if depth <= 0 or rng.random() < 0.3:
        # Terminal: column ref, number, string, or constant
        choice = rng.randint(0, 3)
        if choice == 0:
            return rng.choice(_COLUMN_NAMES)
        elif choice == 1:
            return str(rng.randint(-999, 999))
        elif choice == 2:
            chars = rng.choices(string.ascii_letters + ' ', k=rng.randint(0, 10))
            return '"' + ''.join(chars) + '"'
        else:
            return rng.choice(['TRUE', 'FALSE', 'NULL', 'TODAY()', 'NOW()'])

    # Non-terminal: function call, binary op, or IF
    choice = rng.randint(0, 2)
    if choice == 0:
        func = rng.choice(_TABLEAU_FUNCTIONS)
        n_args = rng.randint(1, 3)
        args = ', '.join(_random_expr(rng, depth - 1) for _ in range(n_args))
        return f'{func}({args})'
    elif choice == 1:
        left = _random_expr(rng, depth - 1)
        right = _random_expr(rng, depth - 1)
        op = rng.choice(_OPERATORS)
        return f'{left} {op} {right}'
    else:
        cond = _random_expr(rng, depth - 1)
        then = _random_expr(rng, depth - 1)
        els = _random_expr(rng, depth - 1)
        return f'IF {cond} THEN {then} ELSE {els} END'


# ── Property-based tests ─────────────────────────────────────────

class TestDAXPropertyBased(unittest.TestCase):
    """Property-based tests: DAX conversion never crashes."""

    # Number of random formulas per built-in fuzz test
    FUZZ_ITERATIONS = 200

    def test_builtin_fuzz_returns_string(self):
        """Randomly generated formulas always produce a string result."""
        rng = random.Random(42)
        for _ in range(self.FUZZ_ITERATIONS):
            formula = _random_formula(rng)
            result = convert_tableau_formula_to_dax(formula)
            self.assertIsInstance(result, str,
                                 f'Non-string result for formula: {formula!r}')

    def test_builtin_fuzz_no_exception(self):
        """Converter never raises an unhandled exception on random input."""
        rng = random.Random(123)
        for _ in range(self.FUZZ_ITERATIONS):
            formula = _random_formula(rng)
            try:
                convert_tableau_formula_to_dax(
                    formula,
                    column_name='FuzzCol',
                    table_name='FuzzTable',
                    calc_map={'[calc1]': 'Calc One'},
                    param_map={'Param1': 'My Param'},
                    column_table_map={'Sales': 'Orders', 'Profit': 'Orders'},
                    measure_names={'Total Sales'},
                )
            except Exception as exc:
                self.fail(f'Exception on formula {formula!r}: {exc}')

    def test_builtin_fuzz_balanced_parens(self):
        """Output DAX should have balanced parentheses (when input does)."""
        rng = random.Random(456)
        for _ in range(self.FUZZ_ITERATIONS):
            formula = _random_formula(rng)
            # Only check when input has balanced parens
            if formula.count('(') != formula.count(')'):
                continue
            result = convert_tableau_formula_to_dax(formula, table_name='T')
            open_count = result.count('(')
            close_count = result.count(')')
            self.assertEqual(open_count, close_count,
                             f'Unbalanced parens in output for {formula!r}: {result!r}')

    def test_builtin_fuzz_no_empty_result(self):
        """Non-empty input should produce non-empty output."""
        rng = random.Random(789)
        for _ in range(self.FUZZ_ITERATIONS):
            formula = _random_formula(rng)
            if not formula.strip():
                continue
            result = convert_tableau_formula_to_dax(formula)
            self.assertTrue(len(result.strip()) > 0,
                            f'Empty result for formula: {formula!r}')

    def test_edge_case_empty_input(self):
        """Empty and whitespace-only inputs are handled gracefully."""
        for inp in ['', ' ', '\n', '\t', '   \n  ']:
            result = convert_tableau_formula_to_dax(inp)
            self.assertIsInstance(result, str)

    def test_edge_case_deeply_nested(self):
        """Deeply nested expressions don't crash."""
        formula = '[X]'
        for _ in range(8):
            formula = f'IF({formula} > 0, {formula}, 0)'
        result = convert_tableau_formula_to_dax(formula, table_name='T')
        self.assertIsInstance(result, str)

    def test_edge_case_special_characters(self):
        """Formulas with special characters don't crash."""
        specials = [
            "[Col with spaces]", "[Col'apostrophe]", "[Col\"quotes\"]",
            "SUM([日本語])", "[αβγ] + [δεζ]", "[Col\ttab]",
            "[Col\nnewline]", "[Col\\backslash]", "1/0",
            "'' + ''", '"\\"escaped\\""',
        ]
        for formula in specials:
            result = convert_tableau_formula_to_dax(formula)
            self.assertIsInstance(result, str)

    def test_edge_case_very_long_formula(self):
        """Very long formulas are handled without timeout."""
        parts = [f'[Col{i}]' for i in range(200)]
        formula = ' + '.join(parts)
        result = convert_tableau_formula_to_dax(formula, table_name='BigTable')
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_edge_case_unicode_function_names(self):
        """Unicode mixed into function names doesn't crash."""
        formulas = [
            'SÜM([X])',   # umlaut in function name
            'IF [X] > 0 THEN "Ñ" ELSE "ß" END',
            'DATETRUNC("month", [Дата])',
        ]
        for formula in formulas:
            result = convert_tableau_formula_to_dax(formula)
            self.assertIsInstance(result, str)


# ── Hypothesis-powered tests (only run when hypothesis is installed) ──

if HAS_HYPOTHESIS:
    # Strategy for Tableau-like formulas
    _tableau_formula_strategy = st.recursive(
        st.one_of(
            st.sampled_from(_COLUMN_NAMES),
            st.integers(min_value=-999, max_value=999).map(str),
            st.text(alphabet=string.ascii_letters + ' ', min_size=0,
                    max_size=10).map(lambda s: f'"{s}"'),
            st.sampled_from(['TRUE', 'FALSE', 'NULL', 'TODAY()', 'NOW()']),
        ),
        lambda children: st.one_of(
            st.tuples(
                st.sampled_from(_TABLEAU_FUNCTIONS),
                st.lists(children, min_size=1, max_size=3),
            ).map(lambda t: f'{t[0]}({", ".join(t[1])})'),
            st.tuples(children, st.sampled_from(_OPERATORS), children)
            .map(lambda t: f'{t[0]} {t[1]} {t[2]}'),
        ),
        max_leaves=20,
    )

    class TestDAXHypothesis(unittest.TestCase):
        """Hypothesis-powered property-based tests."""

        @given(formula=_tableau_formula_strategy)
        @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
        def test_hypothesis_never_crashes(self, formula):
            """No formula ever causes an unhandled exception."""
            result = convert_tableau_formula_to_dax(formula, table_name='T')
            self.assertIsInstance(result, str)

        @given(formula=_tableau_formula_strategy)
        @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
        def test_hypothesis_returns_nonempty(self, formula):
            """Non-empty formulas produce non-empty DAX."""
            if not formula.strip():
                return
            result = convert_tableau_formula_to_dax(formula, table_name='T')
            self.assertGreater(len(result.strip()), 0)

        @given(text=st.text(min_size=0, max_size=100))
        @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
        def test_hypothesis_arbitrary_text(self, text):
            """Completely arbitrary text never crashes the converter."""
            result = convert_tableau_formula_to_dax(text)
            self.assertIsInstance(result, str)


if __name__ == '__main__':
    unittest.main()
