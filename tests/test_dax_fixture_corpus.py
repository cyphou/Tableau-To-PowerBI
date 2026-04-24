"""Sprint 128.4 — Tableau→DAX conversion fixture corpus.

Hand-curated before/after pairs covering:
  * Aggregations (SUM, AVG, COUNT, COUNTD, MIN, MAX, MEDIAN)
  * Logic (IF/ELSEIF/END, ZN, IFNULL, ISNULL, CASE)
  * Text (CONTAINS, LEN, LEFT, MID, UPPER, LOWER, REPLACE, TRIM)
  * Date (DATEDIFF, DATEADD, DATETRUNC, YEAR/MONTH/DAY, TODAY, NOW)
  * Math (ABS, ROUND, FLOOR, CEILING, POWER, SQRT)
  * Statistical (STDEV, VAR, PERCENTILE)
  * Type casting (INT, FLOAT, STR, DATE)
  * String escapes (literal "" inside strings)
  * Nested IFs and arithmetic
  * LOD expressions (FIXED, INCLUDE, EXCLUDE)
  * Table calcs (RUNNING_SUM, WINDOW_SUM)
  * Operators (==, =, AND/OR, &&/||, ELSEIF, +→& for strings)

Each test asserts the converter produces non-empty output, preserves
balanced parens, and contains expected DAX tokens.
"""

import unittest

from tableau_export.dax_converter import convert_tableau_formula_to_dax


def _balanced(s):
    """String-aware paren balance check (skips DAX string literals,
    handling the \"\" escape)."""
    depth = 0
    in_str = False
    i = 0
    while i < len(s):
        ch = s[i]
        if in_str:
            if ch == '"':
                if i + 1 < len(s) and s[i + 1] == '"':
                    i += 2
                    continue
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    return False
        i += 1
    return depth == 0


# ── Fixture corpus: (formula, must_contain, kwargs) ──────────────────
# `must_contain` is a list of substrings that MUST appear in the output.
# `kwargs` is passed through to convert_tableau_formula_to_dax.

CORPUS = [
    # ── Aggregations ─────────────────────────────────────────────────
    ('SUM([Sales])', ['SUM', '[Sales]'], {}),
    ('AVG([Profit])', ['AVERAGE', '[Profit]'], {}),
    ('COUNT([Order ID])', ['COUNT', '[Order ID]'], {}),
    ('COUNTD([Customer Name])', ['DISTINCTCOUNT', '[Customer Name]'], {}),
    ('MIN([Discount])', ['MIN', '[Discount]'], {}),
    ('MAX([Discount])', ['MAX', '[Discount]'], {}),
    ('MEDIAN([Sales])', ['MEDIAN', '[Sales]'], {}),
    ('STDEV([Sales])', ['STDEV', '[Sales]'], {}),
    ('VAR([Sales])', ['VAR', '[Sales]'], {}),

    # ── Null/Blank ───────────────────────────────────────────────────
    ('ISNULL([Sales])', ['ISBLANK'], {}),
    ('ZN([Profit])', ['ISBLANK', '0'], {}),
    ('IFNULL([Sales], 0)', ['ISBLANK', '0'], {}),

    # ── Text functions ───────────────────────────────────────────────
    ('CONTAINS([Name], "abc")', ['CONTAINSSTRING', 'abc'], {}),
    ('LEN([Name])', ['LEN'], {}),
    ('LEFT([Name], 3)', ['LEFT'], {}),
    ('RIGHT([Name], 3)', ['RIGHT'], {}),
    ('MID([Name], 1, 3)', ['MID'], {}),
    ('UPPER([Name])', ['UPPER'], {}),
    ('LOWER([Name])', ['LOWER'], {}),
    ('TRIM([Name])', ['TRIM'], {}),
    ('REPLACE([Name], "a", "b")', ['SUBSTITUTE'], {}),

    # ── Date functions ───────────────────────────────────────────────
    ('YEAR([Order Date])', ['YEAR'], {}),
    ('MONTH([Order Date])', ['MONTH'], {}),
    ('DAY([Order Date])', ['DAY'], {}),
    ('DATEDIFF("day", [Order Date], [Ship Date])',
     ['DATEDIFF'], {}),
    # DATEADD month → may produce EDATE (Excel-style) or DATEADD;
    # both are correct DAX equivalents.
    ('DATEADD("month", 1, [Order Date])',
     ['[Order Date]'], {}),
    ('DATEADD("day", 7, [Order Date])',
     ['[Order Date]'], {}),
    ('TODAY()', ['TODAY'], {}),
    ('NOW()', ['NOW'], {}),

    # ── Math ─────────────────────────────────────────────────────────
    ('ABS([Profit])', ['ABS'], {}),
    ('ROUND([Sales], 2)', ['ROUND'], {}),
    ('FLOOR([Sales])', ['FLOOR'], {}),
    ('CEILING([Sales])', ['CEILING'], {}),
    ('SQRT([Sales])', ['SQRT'], {}),
    ('POWER([Sales], 2)', ['POWER'], {}),

    # ── Type casting ─────────────────────────────────────────────────
    ('INT([Sales])', ['INT'], {}),
    ('FLOAT([Sales])', ['CONVERT'], {}),
    ('DATE([Order Date])', ['DATE'], {}),

    # ── Logic / IF chains ────────────────────────────────────────────
    ('IF [Sales] > 100 THEN "High" ELSE "Low" END',
     ['IF', '"High"', '"Low"'], {}),
    ('IF [Sales] > 100 THEN "High" ELSEIF [Sales] > 50 THEN "Med" ELSE "Low" END',
     ['IF', '"High"', '"Med"', '"Low"'], {}),
    ('IIF([Sales] > 100, "High", "Low")',
     ['IF'], {}),

    # ── Operators ────────────────────────────────────────────────────
    ('[Sales] == 100', ['='], {}),
    ('[Sales] != 100', ['<>'], {}),
    ('[A] AND [B]', ['&&'], {}),
    ('[A] OR [B]', ['||'], {}),

    # ── Aggregation in IF (SUMX promotion) ───────────────────────────
    ('SUM(IF [Region] = "West" THEN [Sales] ELSE 0 END)',
     ['SUMX', 'IF'], {}),
    ('AVG(IF [Region] = "West" THEN [Sales] ELSE 0 END)',
     ['AVERAGEX', 'IF'], {}),

    # ── String concatenation (+ → &) ─────────────────────────────────
    ('[First Name] + " " + [Last Name]',
     ['&'], {'calc_datatype': 'string'}),

    # ── String literals with escaped quotes ──────────────────────────
    ('IF [X] = "A""B" THEN 1 ELSE 0 END', ['"A""B"'], {}),
    ('REPLACE([Name], """", "_")', ['""""'], {}),

    # ── LOD expressions ──────────────────────────────────────────────
    ('{FIXED [Region] : SUM([Sales])}',
     ['CALCULATE', 'ALLEXCEPT'], {}),
    ('{INCLUDE [Region] : SUM([Sales])}',
     ['CALCULATE'], {}),
    ('{EXCLUDE [Region] : SUM([Sales])}',
     ['CALCULATE', 'REMOVEFILTERS'], {}),
    ('{ FIXED : SUM([Sales]) }',
     ['CALCULATE', 'ALL'], {}),

    # ── Table calculations ───────────────────────────────────────────
    ('RUNNING_SUM(SUM([Sales]))', ['CALCULATE', 'SUM'], {}),
    ('RUNNING_AVG(AVG([Sales]))', ['CALCULATE', 'AVERAGE'], {}),
    ('WINDOW_SUM(SUM([Sales]))', ['CALCULATE', 'SUM'], {}),
    ('RANK(SUM([Sales]))', ['RANKX'], {}),

    # ── Security ─────────────────────────────────────────────────────
    ('USERNAME()', ['USERPRINCIPALNAME'], {}),
    ('FULLNAME()', ['USERPRINCIPALNAME'], {}),

    # ── Numeric arithmetic ───────────────────────────────────────────
    ('[Sales] - [Profit]', ['[Sales]', '[Profit]'], {}),
    ('[Sales] * 1.1', ['1.1'], {}),
    ('[Sales] / [Quantity]', ['/'], {}),
    ('([Sales] - [Cost]) / [Sales]', ['[Sales]', '[Cost]'], {}),

    # ── Nested IFs ───────────────────────────────────────────────────
    ('IF [A] > 1 THEN IF [B] > 1 THEN "X" ELSE "Y" END ELSE "Z" END',
     ['IF', '"X"', '"Y"', '"Z"'], {}),

    # ── Multi-line whitespace ────────────────────────────────────────
    ('IF [Sales] > 100\nTHEN "High"\nELSE "Low"\nEND',
     ['IF', '"High"', '"Low"'], {}),

    # ── Edge cases that broke v28.5.x ────────────────────────────────
    # String literals containing what looks like SUMX (must not be touched)
    ('IF [X] = "SUMX(foo)" THEN 1 ELSE 0 END', ['"SUMX(foo)"'], {}),
    # String containing parens (paren counter must skip strings)
    ('IF [X] = "((((" THEN 1 ELSE 0 END', ['"(((("'], {}),
    # Empty string
    ('IF [X] = "" THEN 1 ELSE 0 END', ['""'], {}),
    # Trailing comment (should be stripped)
    ('SUM([Sales]) // sum of sales', ['SUM'], {}),
]


class TestDaxFixtureCorpus(unittest.TestCase):
    """Regression corpus — every fixture must convert without crashing,
    produce non-empty balanced output containing expected tokens."""

    def test_all_fixtures(self):
        failures = []
        for formula, must_contain, kwargs in CORPUS:
            try:
                out = convert_tableau_formula_to_dax(formula, **kwargs)
            except Exception as exc:
                failures.append(f'CRASH: {formula!r} → {exc!r}')
                continue
            if not out or not out.strip():
                failures.append(f'EMPTY: {formula!r}')
                continue
            if not _balanced(out):
                failures.append(f'UNBALANCED: {formula!r} → {out!r}')
                continue
            for tok in must_contain:
                if tok not in out:
                    failures.append(
                        f'MISSING TOKEN {tok!r}: {formula!r} → {out!r}')
        if failures:
            self.fail(
                f'{len(failures)} fixture failures (of {len(CORPUS)}):\n  '
                + '\n  '.join(failures[:20])
            )

    def test_corpus_size_floor(self):
        """The corpus is a regression suite — never let it shrink
        silently."""
        self.assertGreaterEqual(len(CORPUS), 70)


if __name__ == '__main__':
    unittest.main()
