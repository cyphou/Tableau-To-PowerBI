"""Sprint 129.4 — Tests for powerbi_import.m_validator."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from powerbi_import.m_validator import (
    validate_m_query,
    MQueryValidator,
    _strip_strings_and_comments,
)


class TestEmptyAndTrivial(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(validate_m_query(''), ['empty M expression'])

    def test_whitespace_only(self):
        self.assertEqual(validate_m_query('   \n  '), ['empty M expression'])

    def test_simple_let_in(self):
        m = 'let Source = 1 in Source'
        self.assertEqual(validate_m_query(m), [])

    def test_single_expr_no_let(self):
        # Non-let expressions are valid
        self.assertEqual(validate_m_query('Table.FromRows({})'), [])


class TestBrackets(unittest.TestCase):

    def test_balanced_parens(self):
        self.assertEqual(validate_m_query('let x = Func(1, 2) in x'), [])

    def test_unmatched_open_paren(self):
        issues = validate_m_query('let x = Func(1, 2 in x')
        self.assertTrue(any('unmatched opening "("' in i for i in issues))

    def test_unmatched_close_paren(self):
        issues = validate_m_query('let x = Func(1, 2)) in x')
        self.assertTrue(any('unmatched closing ")"' in i for i in issues))

    def test_balanced_brackets(self):
        self.assertEqual(
            validate_m_query('let x = #table({"A"}, {{1}})[A] in x'), []
        )

    def test_unmatched_close_bracket(self):
        issues = validate_m_query('let x = Record[a]] in x')
        self.assertTrue(any('"]"' in i for i in issues))

    def test_balanced_braces(self):
        self.assertEqual(validate_m_query('let x = {1, 2, 3} in x'), [])

    def test_unmatched_brace(self):
        issues = validate_m_query('let x = {1, 2 in x')
        self.assertTrue(any('"{"' in i for i in issues))

    def test_mismatched_brackets(self):
        issues = validate_m_query('let x = (1, 2] in x')
        self.assertTrue(any('mismatched' in i for i in issues))


class TestStringLiterals(unittest.TestCase):

    def test_simple_string(self):
        self.assertEqual(validate_m_query('let x = "hello" in x'), [])

    def test_escaped_quote_in_string(self):
        # M escapes internal quotes by doubling
        self.assertEqual(validate_m_query('let x = "say ""hi""" in x'), [])

    def test_unterminated_string(self):
        issues = validate_m_query('let x = "no close in x')
        self.assertTrue(any('unterminated string' in i for i in issues))

    def test_brackets_inside_string_dont_count(self):
        # The [ and ( inside the string must NOT be counted as opens
        m = 'let x = "this has ( and [ inside" in x'
        self.assertEqual(validate_m_query(m), [])

    def test_let_inside_string_dont_count(self):
        m = 'let x = "the word let appears here in text" in x'
        # 1 let, 1 in — string contents ignored
        self.assertEqual(validate_m_query(m), [])


class TestQuotedIdentifiers(unittest.TestCase):

    def test_simple_quoted_id(self):
        m = 'let #"My Step" = 1 in #"My Step"'
        self.assertEqual(validate_m_query(m), [])

    def test_quoted_id_with_special_chars(self):
        m = 'let #"a/b(c)" = 1 in #"a/b(c)"'
        self.assertEqual(validate_m_query(m), [])

    def test_unterminated_quoted_id(self):
        m = 'let #"never closed = 1 in x'
        issues = validate_m_query(m)
        self.assertTrue(any('unterminated quoted identifier' in i for i in issues))

    def test_brackets_inside_quoted_id_ignored(self):
        m = 'let #"step (1) [draft]" = 1 in #"step (1) [draft]"'
        self.assertEqual(validate_m_query(m), [])


class TestLetIn(unittest.TestCase):

    def test_balanced_let_in(self):
        self.assertEqual(validate_m_query('let a = 1 in a'), [])

    def test_two_let_two_in(self):
        m = 'let a = let b = 1 in b in a'
        self.assertEqual(validate_m_query(m), [])

    def test_let_without_in(self):
        issues = validate_m_query('let a = 1, b = 2')
        self.assertTrue(any('unbalanced let/in' in i for i in issues))

    def test_in_without_let(self):
        issues = validate_m_query('1 in 2')
        self.assertTrue(any('unbalanced let/in' in i for i in issues))


class TestComments(unittest.TestCase):

    def test_line_comment_ignored(self):
        m = 'let x = 1 // unbalanced ( inside comment\nin x'
        self.assertEqual(validate_m_query(m), [])

    def test_block_comment_ignored(self):
        m = 'let x = 1 /* unbalanced ( and let in here */ in x'
        self.assertEqual(validate_m_query(m), [])


class TestTrailingComma(unittest.TestCase):

    def test_trailing_comma_before_in(self):
        issues = validate_m_query('let a = 1, in a')
        self.assertTrue(any('trailing comma' in i for i in issues))

    def test_no_trailing_comma_ok(self):
        self.assertEqual(validate_m_query('let a = 1 in a'), [])


class TestRealWorldM(unittest.TestCase):

    def test_realistic_table_query(self):
        m = '''let
    Source = Sql.Database("server", "db"),
    Sales = Source{[Schema="dbo",Item="Sales"]}[Data],
    #"Filtered Rows" = Table.SelectRows(Sales, each [Amount] > 0),
    #"Renamed" = Table.RenameColumns(#"Filtered Rows", {{"Amount", "Sales Amount"}})
in
    #"Renamed"'''
        self.assertEqual(validate_m_query(m), [])

    def test_realistic_with_string_literal_containing_brackets(self):
        m = '''let
    Source = Csv.Document(File.Contents("C:\\path\\to\\file.csv")),
    #"Promoted" = Table.PromoteHeaders(Source, [PromoteAllScalars=true])
in
    #"Promoted"'''
        self.assertEqual(validate_m_query(m), [])

    def test_inline_table(self):
        m = ('let Source = #table({"A","B"}, '
             '{{1,"x"},{2,"y"},{3,"z"}}) in Source')
        self.assertEqual(validate_m_query(m), [])


class TestStripHelper(unittest.TestCase):
    """Internal helper: ensure string/comment stripping preserves length
    and line breaks (so error positions stay accurate)."""

    def test_length_preserved(self):
        m = 'let x = "abc" in x'
        out = _strip_strings_and_comments(m)
        self.assertEqual(len(out), len(m))

    def test_newlines_preserved_in_block_comment(self):
        m = 'let /* line1\nline2 */ x = 1 in x'
        out = _strip_strings_and_comments(m)
        self.assertEqual(out.count('\n'), m.count('\n'))


class TestMQueryValidatorClass(unittest.TestCase):

    def test_validate(self):
        self.assertEqual(MQueryValidator.validate('let a = 1 in a'), [])

    def test_is_valid_true(self):
        self.assertTrue(MQueryValidator.is_valid('let a = 1 in a'))

    def test_is_valid_false(self):
        self.assertFalse(MQueryValidator.is_valid('let a = 1'))


if __name__ == '__main__':
    unittest.main()
