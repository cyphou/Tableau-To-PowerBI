"""
Tests for Sprint 61 — M Transform Expansion.

Covers:
  - Regex extraction (gen_extract_regex)
  - JSON parsing (gen_parse_json)
  - XML parsing (gen_parse_xml)
  - Connection parameterization (parameterize_connection)
  - inject_m_steps integration with new transforms
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tableau_export.m_query_builder import (
    gen_extract_regex,
    gen_parse_json,
    gen_parse_xml,
    parameterize_connection,
    inject_m_steps,
)


class TestRegexExtract(unittest.TestCase):
    def test_basic(self):
        name, expr = gen_extract_regex('Email', r'@(.+)$', 1)
        self.assertEqual(name, 'Regex_Email')
        self.assertIn('Text.RegexExtract', expr)
        self.assertIn('{prev}', expr)
        self.assertIn('"Email"', expr)

    def test_default_group(self):
        name, expr = gen_extract_regex('Col', r'\d+')
        self.assertIn(', 0)', expr)

    def test_inject_into_m(self):
        m = 'let\n    Source = Table.FromRows({})\nin\n    Source'
        steps = [gen_extract_regex('A', r'\d+')]
        result = inject_m_steps(m, steps)
        self.assertIn('Text.RegexExtract', result)
        self.assertNotIn('{prev}', result)


class TestParseJson(unittest.TestCase):
    def test_basic(self):
        name, expr = gen_parse_json('Payload')
        self.assertEqual(name, 'ParseJSON_Payload')
        self.assertIn('Json.Document', expr)
        self.assertIn('{prev}', expr)

    def test_inject_into_m(self):
        m = 'let\n    Source = Table.FromRows({})\nin\n    Source'
        steps = [gen_parse_json('Data')]
        result = inject_m_steps(m, steps)
        self.assertIn('Json.Document', result)
        self.assertNotIn('{prev}', result)


class TestParseXml(unittest.TestCase):
    def test_basic(self):
        name, expr = gen_parse_xml('Response')
        self.assertEqual(name, 'ParseXML_Response')
        self.assertIn('Xml.Tables', expr)
        self.assertIn('{prev}', expr)

    def test_inject_into_m(self):
        m = 'let\n    Source = Table.FromRows({})\nin\n    Source'
        steps = [gen_parse_xml('XML')]
        result = inject_m_steps(m, steps)
        self.assertIn('Xml.Tables', result)


class TestParameterizeConnection(unittest.TestCase):
    def test_basic_replacement(self):
        m = 'let\n    Source = Sql.Database("myserver", "mydb")\nin\n    Source'
        result = parameterize_connection(m, {'myserver': 'P_Server', 'mydb': 'P_Database'})
        self.assertIn('#"P_Server"', result)
        self.assertIn('#"P_Database"', result)
        self.assertNotIn('"myserver"', result)

    def test_no_params(self):
        m = 'let\n    Source = X\nin\n    Source'
        result = parameterize_connection(m, None)
        self.assertEqual(result, m)

    def test_empty_map(self):
        m = 'let\n    Source = X\nin\n    Source'
        result = parameterize_connection(m, {})
        self.assertEqual(result, m)

    def test_partial_match(self):
        m = 'let\n    Source = Sql.Database("server1", "db_prod")\nin\n    Source'
        result = parameterize_connection(m, {'server1': 'P_Server'})
        self.assertIn('#"P_Server"', result)
        self.assertIn('"db_prod"', result)  # Unchanged


class TestChainedTransforms(unittest.TestCase):
    def test_multiple_transforms(self):
        m = 'let\n    Source = Table.FromRows({})\nin\n    Source'
        steps = [
            gen_extract_regex('Email', r'@(.+)$', 1),
            gen_parse_json('Payload'),
        ]
        result = inject_m_steps(m, steps)
        self.assertIn('Text.RegexExtract', result)
        self.assertIn('Json.Document', result)
        self.assertNotIn('{prev}', result)


if __name__ == '__main__':
    unittest.main()
