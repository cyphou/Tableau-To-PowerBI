"""Sprint 128.1 — DAX optimizer property/round-trip tests.

Property: for any DAX formula in our random corpus, every rule in
``optimize_dax`` must:
  * preserve balanced parentheses,
  * preserve string-literal contents byte-for-byte (escaped ``""`` intact),
  * never introduce Tableau function leakage.

Uses stdlib ``random.seed`` for reproducibility (no `hypothesis` dep).
This guards against the v28.5.x class of bugs (re.match tail-drop,
unprotected re.sub against DAX text).
"""

import os
import random
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from powerbi_import.dax_optimizer import (
    optimize_dax,
    _protect_string_literals,
    _restore_string_literals,
    _rule_isblank_to_coalesce,
    _rule_nested_if_to_switch,
    _rule_redundant_calculate,
    _rule_constant_fold,
    _rule_simplify_sumx,
)


_TABLEAU_LEAK_PATTERNS = [
    r'\bDATETRUNC\s*\(',
    r'\bIFNULL\s*\(',
    r'\bZN\s*\(',
    r'\bATTR\s*\(',
    r'\{FIXED\b',
    r'\{INCLUDE\b',
    r'\{EXCLUDE\b',
]


def _balanced(formula):
    """True if parens are balanced ignoring those inside string literals."""
    protected, _ = _protect_string_literals(formula)
    depth = 0
    for ch in protected:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _has_tableau_leak(formula):
    return any(re.search(p, formula) for p in _TABLEAU_LEAK_PATTERNS)


def _string_literals(formula):
    """Extract string literal contents (including the quotes) in order."""
    return re.findall(r'"(?:[^"]|"")*"', formula)


# ── Random formula generation ───────────────────────────────────────


def _gen_atom(rng):
    choices = [
        lambda: f"'T{rng.randint(1,3)}'[Col{rng.randint(1,5)}]",
        lambda: f"[Measure{rng.randint(1,4)}]",
        lambda: str(rng.randint(0, 100)),
        lambda: f'"str{rng.randint(1,5)}"',
        # String literal with escaped double-quote (the v28.5.x foot-gun)
        lambda: f'"text with ""escaped"" quote {rng.randint(1,9)}"',
        lambda: '"path/to/file"',
        lambda: '"2024-01-01"',
    ]
    return rng.choice(choices)()


def _gen_aggr(rng, depth=0):
    a = _gen_atom(rng)
    fn = rng.choice(['SUM', 'AVERAGE', 'COUNT', 'MAX', 'MIN', 'DISTINCTCOUNT'])
    return f'{fn}({a})'


def _gen_calc(rng, depth=0):
    if depth > 3:
        return _gen_aggr(rng)
    inner = _gen_aggr(rng) if rng.random() < 0.5 else _gen_calc(rng, depth + 1)
    if rng.random() < 0.4:
        col = f"'T{rng.randint(1,3)}'[Col{rng.randint(1,5)}]"
        val = rng.choice([str(rng.randint(0, 50)),
                          '"approved"', '"denied"', '"with ""quote"""'])
        return f'CALCULATE({inner}, {col} = {val})'
    return f'CALCULATE({inner})'


def _gen_if_chain(rng, depth=0):
    if depth > 3:
        return _gen_atom(rng)
    cond_col = f"'T1'[Col{rng.randint(1,3)}]"
    val = rng.choice(['"a"', '"b"', '"c"', '"d"', '"with ""quote"""'])
    then_branch = _gen_atom(rng)
    if rng.random() < 0.6 and depth < 3:
        else_branch = _gen_if_chain(rng, depth + 1)
    else:
        else_branch = _gen_atom(rng)
    return f'IF({cond_col} = {val}, {then_branch}, {else_branch})'


def _gen_isblank(rng):
    expr = _gen_aggr(rng)
    default = rng.choice(['0', 'BLANK()', '"n/a"', '"with ""quote"""'])
    # Alternate the two arg orders the rule recognises
    if rng.random() < 0.5:
        return f'IF(ISBLANK({expr}), {default}, {expr})'
    return f'IF(ISBLANK({expr}), {expr}, {default})'


def _gen_formula(rng):
    g = rng.choice([_gen_aggr, _gen_calc, _gen_if_chain, _gen_isblank])
    return g(rng)


# ── Tests ────────────────────────────────────────────────────────────


class TestProtectRestoreRoundTrip(unittest.TestCase):
    """The protect/restore helper itself must be byte-perfect."""

    def test_round_trip_simple(self):
        f = 'IF([X] = "hello", 1, 0)'
        prot, lits = _protect_string_literals(f)
        self.assertNotIn('hello', prot)
        self.assertEqual(_restore_string_literals(prot, lits), f)

    def test_round_trip_escaped_quotes(self):
        f = 'IF([X] = "with ""inner"" quote", 1, 0)'
        prot, lits = _protect_string_literals(f)
        self.assertEqual(_restore_string_literals(prot, lits), f)

    def test_round_trip_multiple_literals(self):
        f = 'CONCATENATE("a", CONCATENATE("b ""c""", "d"))'
        prot, lits = _protect_string_literals(f)
        self.assertEqual(len(lits), 3)
        self.assertEqual(_restore_string_literals(prot, lits), f)

    def test_round_trip_no_literals(self):
        f = 'SUM([Sales]) + 1'
        prot, lits = _protect_string_literals(f)
        self.assertEqual(prot, f)
        self.assertEqual(lits, [])
        self.assertEqual(_restore_string_literals(prot, lits), f)


class TestPropertyPreservation(unittest.TestCase):
    """Across 200 random formulas every individual rule must preserve
    invariants (balanced parens, string literal byte-equality, no
    Tableau leakage)."""

    CORPUS_SIZE = 200

    def _corpus(self):
        rng = random.Random(2026)
        return [_gen_formula(rng) for _ in range(self.CORPUS_SIZE)]

    def _assert_invariants(self, original, transformed, rule_name):
        self.assertTrue(
            _balanced(transformed),
            f'{rule_name} produced unbalanced parens for {original!r} → {transformed!r}'
        )
        self.assertFalse(
            _has_tableau_leak(transformed),
            f'{rule_name} introduced Tableau leak in {transformed!r}'
        )
        # Every literal that survives the rewrite must match an original
        # literal byte-for-byte (rules may drop literals, never corrupt)
        orig_lits = set(_string_literals(original))
        new_lits = set(_string_literals(transformed))
        for lit in new_lits:
            self.assertIn(
                lit, orig_lits,
                f'{rule_name} corrupted a string literal: {lit!r} not in {orig_lits}'
            )

    def test_isblank_to_coalesce_invariants(self):
        for f in self._corpus():
            out = _rule_isblank_to_coalesce(f)
            self._assert_invariants(f, out, 'isblank_to_coalesce')

    def test_nested_if_to_switch_invariants(self):
        for f in self._corpus():
            out = _rule_nested_if_to_switch(f)
            self._assert_invariants(f, out, 'nested_if_to_switch')

    def test_redundant_calculate_invariants(self):
        for f in self._corpus():
            out = _rule_redundant_calculate(f)
            self._assert_invariants(f, out, 'redundant_calculate')

    def test_constant_fold_invariants(self):
        for f in self._corpus():
            out = _rule_constant_fold(f)
            self._assert_invariants(f, out, 'constant_fold')

    def test_simplify_sumx_invariants(self):
        for f in self._corpus():
            out = _rule_simplify_sumx(f)
            self._assert_invariants(f, out, 'simplify_sumx')

    def test_full_pipeline_invariants(self):
        for f in self._corpus():
            out, _ = optimize_dax(f)
            self._assert_invariants(f, out, 'optimize_dax')


class TestRegressionTraps(unittest.TestCase):
    """Specific shapes that would have caught the v28.5.x bugs."""

    def test_redundant_calculate_does_not_drop_tail(self):
        """The re.match tail-drop bug (74fbdde3): formula with trailing
        text after CALCULATE(...) must not lose that tail."""
        f = 'CALCULATE(SUM([X])) + 1'
        out = _rule_redundant_calculate(f)
        # Either left untouched OR collapsed AND tail preserved
        self.assertTrue(
            '+ 1' in out or out == f,
            f'redundant_calculate dropped trailing "+ 1": {out!r}'
        )

    def test_constant_fold_preserves_date_string(self):
        """The string-literal regex collision (74fbdde3): a date string
        that *looks* like an arithmetic expression must survive intact."""
        f = 'IF([D] >= "2024-01-01", 1, 0)'
        out = _rule_constant_fold(f)
        self.assertIn('"2024-01-01"', out)

    def test_constant_fold_preserves_arithmetic_in_string(self):
        f = '"price = 1 + 1"'
        out = _rule_constant_fold(f)
        self.assertIn('"price = 1 + 1"', out)


if __name__ == '__main__':
    unittest.main()
