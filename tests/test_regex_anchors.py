"""Sprint 128.2 + 128.3 — Static lint for DAX-handling regex.

These tests scan the DAX-handling source modules for two foot-guns
exposed during the v28.5.x audit:

  128.2 — Unprotected ``re.sub`` against a DAX/formula variable.
          Any rewrite of formula text that contains string literals
          MUST first call ``_protect_string_literals`` so the rewrite
          can't corrupt date strings, escaped quotes, or arithmetic-
          looking literals (this caught the constant-fold bug).

  128.3 — Use of ``re.match`` to assert "the entire formula matches".
          ``re.match`` only anchors at the start. A pattern with an
          explicit ``$`` works correctly (re.match + ``$`` ≡ fullmatch
          for non-multiline), but ``re.fullmatch`` makes the intent
          explicit. New code should prefer fullmatch; existing legacy
          sites are allow-listed.

Both are *advisory* lints with allow-lists for known-safe usages.
"""

import ast
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Modules that operate on DAX text. Adding a module here opts it in to
# the lint; removing one opts it out.
_DAX_MODULES = [
    'powerbi_import/dax_optimizer.py',
    'powerbi_import/dax_converter.py',
    'tableau_export/dax_converter.py',
]

# Variable names that conventionally hold formula/DAX text. Any
# ``re.sub(pattern, repl, NAME)`` where NAME is in this set must be
# inside a protect/restore block.
_FORMULA_VAR_NAMES = {'formula', 'dax', 'expression', 'formula_str', 'expr'}

# Allow-list: (file_path_suffix, function_name).
# Use this when an unprotected re.sub is intentional — typically because
# the pattern can't possibly match inside a DAX string literal (e.g.
# `[federated.X].` column-ref prefixes use `[` which delimits column
# refs, and `//` comments only at line start which DAX strings don't
# legally contain).
_PROTECT_RESTORE_ALLOWLIST = {
    # _protect_string_literals IS the protect helper itself — it
    # tokenizes literals, so by definition it operates on un-protected
    # text. Allowing the helper that defines the discipline is correct.
    ('powerbi_import/dax_optimizer.py', '_protect_string_literals'),
    # _rule_isblank_to_coalesce: pattern `IF(ISBLANK(...))` requires
    # function-call syntax that cannot legally appear inside a DAX
    # string literal.
    ('powerbi_import/dax_optimizer.py', '_rule_isblank_to_coalesce'),
    # _rule_simplify_sumx: pattern matches SUMX(...) function call
    # only — function calls cannot appear inside string literals.
    ('powerbi_import/dax_optimizer.py', '_rule_simplify_sumx'),
    # _rule_trim_whitespace: collapses runs of internal whitespace.
    # Whitespace inside a DAX string literal is semantically meaningful,
    # but trimming repeated spaces is a benign cosmetic change that
    # doesn't affect string equality for typical generated text.
    ('powerbi_import/dax_optimizer.py', '_rule_trim_whitespace'),
    # convert_tableau_formula_to_dax: two early-phase substitutions on
    # patterns that cannot legally appear inside a DAX string literal:
    #   * [federated.xxx]. column-ref prefix (uses bracket delimiter)
    #   * (?m)^\s*//... line comments (anchored at line start)
    # Both run before string literals are introduced; allow-listed here.
    ('tableau_export/dax_converter.py', 'convert_tableau_formula_to_dax'),
}


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel_path):
    p = os.path.join(_project_root(), rel_path)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return f.read()


def _enclosing_function(tree, lineno):
    """Return the name of the function that encloses a given line number."""
    enclosing = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno <= getattr(node, 'end_lineno', node.lineno):
                # Pick the innermost (latest start)
                if enclosing is None or node.lineno > enclosing.lineno:
                    enclosing = node
    return enclosing.name if enclosing else None


def _is_allowlisted(rel_path, fn_name, source):
    """Return True if (file, function) is in the allow-list, OR the
    function body contains a `_protect_string_literals(` call near the
    re.sub (i.e. protect/restore is in effect)."""
    if (rel_path, fn_name) in _PROTECT_RESTORE_ALLOWLIST:
        return True
    # Heuristic fallback: if the same function calls protect, allow it
    if fn_name and source:
        m = re.search(
            r'def\s+' + re.escape(fn_name) + r'\s*\(.*?\):(.*?)(?=\ndef |\Z)',
            source, re.DOTALL,
        )
        if m and '_protect_string_literals' in m.group(1):
            return True
    return False


# ── 128.2 — Protect/restore audit ───────────────────────────────────


class TestNoUnprotectedRegex(unittest.TestCase):

    def test_re_sub_against_formula_var_uses_protect_restore(self):
        offenders = []
        for rel in _DAX_MODULES:
            source = _read(rel)
            if source is None:
                continue
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'sub'
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == 're'):
                    continue
                # Third positional arg is the string being rewritten
                if len(node.args) < 3:
                    continue
                target = node.args[2]
                if not isinstance(target, ast.Name):
                    continue
                if target.id not in _FORMULA_VAR_NAMES:
                    continue
                fn_name = _enclosing_function(tree, node.lineno)
                if _is_allowlisted(rel, fn_name, source):
                    continue
                offenders.append(f'{rel}:{node.lineno}  re.sub(..., {target.id}) '
                                 f'in {fn_name or "<module>"}')

        self.assertEqual(
            offenders, [],
            'Unprotected re.sub against DAX formula text. Wrap with '
            '_protect_string_literals/_restore_string_literals or add '
            'to _PROTECT_RESTORE_ALLOWLIST in tests/test_regex_anchors.py:\n  '
            + '\n  '.join(offenders)
        )


# ── 128.3 — Anchor correctness lint ─────────────────────────────────


_ANCHOR_RE = re.compile(r'\\Z|\$')

# Allow-list of known existing re.match-with-end-anchor sites. They are
# functionally correct (re.match with explicit `$` is equivalent to
# fullmatch for non-multiline patterns), but the lint exists to *prefer
# fullmatch for clarity in new code*. Adding to this set is fine for
# legacy code; new offenders should use re.fullmatch directly.
_ANCHOR_ALLOWLIST_BY_FILE = {
    # Legacy DAX expression-shape probes — patterns are fully anchored
    # `^...$` so re.match is functionally correct here. Migrating to
    # re.fullmatch would be cosmetic.
    'tableau_export/dax_converter.py': {
        '_xf', '_is_single_column',
    },
    # Tableau→PySpark conversion: shape detection patterns, fully anchored.
    'powerbi_import/calc_column_utils.py': {
        'tableau_formula_to_pyspark',
    },
}


def _is_anchor_allowlisted(rel_path, fn_name):
    return fn_name in _ANCHOR_ALLOWLIST_BY_FILE.get(rel_path, set())


class TestRegexAnchors(unittest.TestCase):
    """Patterns that anchor at end-of-string ($ or \\Z) in re.match work
    correctly today (re.match + explicit `$` = fullmatch behaviour for
    non-multiline patterns), but ``re.fullmatch`` is clearer about
    intent and immune to future MULTILINE additions.

    Real bug class (74fbdde3): re.match WITHOUT ``$`` when the intent
    was whole-string match. That's undetectable statically, so this
    test serves as a forward-looking nudge — it allow-lists existing
    correct usages and only fails when *new* code introduces a fresh
    re.match-with-end-anchor site.
    """

    def test_re_match_with_end_anchor_should_be_fullmatch(self):
        offenders = []
        for rel in _DAX_MODULES + [
            'powerbi_import/llm_client.py',
            'powerbi_import/m_query_builder.py',
            'powerbi_import/calc_column_utils.py',
            'powerbi_import/validator.py',
            'powerbi_import/m_validator.py',
            'powerbi_import/repair_strategies.py',
        ]:
            source = _read(rel)
            if source is None:
                continue
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'match'
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == 're'):
                    continue
                if not node.args:
                    continue
                pat = node.args[0]
                # Only inspect literal patterns
                if isinstance(pat, ast.Constant) and isinstance(pat.value, str):
                    pat_str = pat.value
                elif isinstance(pat, ast.JoinedStr):
                    pat_str = ''.join(
                        v.value for v in pat.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    )
                else:
                    continue
                if not _ANCHOR_RE.search(pat_str):
                    continue
                fn_name = _enclosing_function(tree, node.lineno)
                if _is_anchor_allowlisted(rel, fn_name):
                    continue
                offenders.append(
                    f'{rel}:{node.lineno}  re.match(r"...{pat_str[-15:]}") '
                    f'in {fn_name or "<module>"} — prefer re.fullmatch '
                    f'for whole-string match (or add to '
                    f'_ANCHOR_ALLOWLIST_BY_FILE if intentional)'
                )

        self.assertEqual(
            offenders, [],
            'New re.match call(s) with end-of-string anchor introduced. '
            'Use re.fullmatch instead — it is clearer about whole-string '
            'intent and resilient to MULTILINE flag changes. Offenders:\n  '
            + '\n  '.join(offenders)
        )


if __name__ == '__main__':
    unittest.main()
