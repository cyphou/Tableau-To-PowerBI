"""
Sprint 84 — Conversion Accuracy Depth tests.

Covers:
  84.1  Prep VAR/VARP → correct M variance formulas
  84.2  Prep notInner → leftanti (already mapped, regression guard)
  84.3  Bump chart → RANKX measure auto-injection
  84.4  PDF connector depth (page range, table selection)
  84.5  Salesforce SOQL depth (API version, SOQL passthrough, relationships)
  84.6  REGEX → M fallback (Text.RegexMatch / Extract / Replace)
"""

import unittest

# ═══════════════════════════════════════════════════════════════════
# 84.1  Prep VAR / VARP
# ═══════════════════════════════════════════════════════════════════

from tableau_export.m_query_builder import m_transform_aggregate, _M_AGG_MAP


class TestPrepVariance(unittest.TestCase):
    """84.1 — VAR + VARP generate correct M formulas (not StdDev approximation)."""

    def test_var_agg_map_entry_is_special(self):
        """VAR must NOT map to List.StandardDeviation (previous bug)."""
        func, _ = _M_AGG_MAP['var']
        self.assertIsNone(func, 'VAR should be special-cased (None in map)')

    def test_varp_agg_map_entry_is_special(self):
        func, _ = _M_AGG_MAP['varp']
        self.assertIsNone(func, 'VARP should be special-cased (None in map)')

    def test_var_generates_stddev_squared(self):
        """Sample variance = Number.Power(List.StandardDeviation(...), 2)."""
        _, expr = m_transform_aggregate(
            ['Region'],
            [{'name': 'Sales_Var', 'column': 'Sales', 'agg': 'var'}],
        )
        self.assertIn('Number.Power(List.StandardDeviation([Sales]), 2)', expr)

    def test_varp_generates_population_variance(self):
        """Population variance = avg((x - mean)²)."""
        _, expr = m_transform_aggregate(
            ['Region'],
            [{'name': 'Sales_VarP', 'column': 'Sales', 'agg': 'varp'}],
        )
        self.assertIn('List.Average(List.Transform(', expr)
        self.assertIn('Number.Power(x - List.Average([Sales]), 2)', expr)

    def test_var_step_name(self):
        step_name, _ = m_transform_aggregate(
            ['Region'],
            [{'name': 'V', 'column': 'Amount', 'agg': 'var'}],
        )
        self.assertEqual(step_name, '#"Grouped Rows"')

    def test_varp_step_name(self):
        step_name, _ = m_transform_aggregate(
            ['Region'],
            [{'name': 'VP', 'column': 'Amount', 'agg': 'varp'}],
        )
        self.assertEqual(step_name, '#"Grouped Rows"')

    def test_var_with_other_aggs(self):
        """VAR together with SUM/COUNT should produce correct mix."""
        _, expr = m_transform_aggregate(
            ['Region'],
            [
                {'name': 'Total', 'column': 'Sales', 'agg': 'sum'},
                {'name': 'Variance', 'column': 'Sales', 'agg': 'var'},
                {'name': 'Cnt', 'column': 'Sales', 'agg': 'count'},
            ],
        )
        self.assertIn('List.Sum([Sales])', expr)
        self.assertIn('Number.Power(List.StandardDeviation([Sales]), 2)', expr)
        self.assertIn('Table.RowCount(_)', expr)

    def test_stdev_still_uses_list_standard_deviation(self):
        """STDEV should still use List.StandardDeviation directly."""
        _, expr = m_transform_aggregate(
            ['Region'],
            [{'name': 'SD', 'column': 'Sales', 'agg': 'stdev'}],
        )
        self.assertIn('List.StandardDeviation([Sales])', expr)
        self.assertNotIn('Number.Power', expr)


# ═══════════════════════════════════════════════════════════════════
# 84.2  Prep notInner → leftanti
# ═══════════════════════════════════════════════════════════════════

from tableau_export.prep_flow_parser import _PREP_JOIN_MAP


class TestPrepNotInner(unittest.TestCase):
    """84.2 — notInner must map to leftanti."""

    def test_not_inner_maps_to_leftanti(self):
        self.assertEqual(_PREP_JOIN_MAP['notInner'], 'leftanti')

    def test_left_only_maps_to_leftanti(self):
        self.assertEqual(_PREP_JOIN_MAP['leftOnly'], 'leftanti')

    def test_right_only_maps_to_rightanti(self):
        self.assertEqual(_PREP_JOIN_MAP['rightOnly'], 'rightanti')

    def test_inner_maps_to_inner(self):
        self.assertEqual(_PREP_JOIN_MAP['inner'], 'inner')

    def test_full_maps_to_full(self):
        self.assertEqual(_PREP_JOIN_MAP['full'], 'full')


# ═══════════════════════════════════════════════════════════════════
# 84.3  Bump chart RANKX injection
# ═══════════════════════════════════════════════════════════════════

from powerbi_import.visual_generator import (
    create_visual_container,
    get_auto_generated_measures,
    clear_auto_generated_measures,
)


class TestBumpChartRankx(unittest.TestCase):
    """84.3 — Bump chart should auto-inject RANKX measure."""

    def setUp(self):
        clear_auto_generated_measures()

    def test_bump_chart_injects_rank_measure(self):
        ws = {
            'name': 'Ranking Over Time',
            'visualType': 'bumpchart',
            'dimensions': [{'field': 'Year', 'name': 'Year'}],
            'measures': [{'name': 'Revenue', 'label': 'Revenue',
                          'expression': 'SUM(Revenue)'}],
            'mark_encoding': {},
        }
        ctm = {'Year': 'Sales', 'Revenue': 'Sales'}
        ml = {}
        create_visual_container(ws, col_table_map=ctm, measure_lookup=ml)
        auto = get_auto_generated_measures()
        self.assertEqual(len(auto), 1)
        self.assertEqual(auto[0]['name'], '_bump_rank_Revenue')
        self.assertIn('RANKX', auto[0]['expression'])
        self.assertIn('ALL(', auto[0]['expression'])

    def test_bump_chart_rank_measure_uses_first_measure(self):
        ws = {
            'name': 'Multi Measure Bump',
            'visualType': 'bumpchart',
            'dimensions': [{'field': 'Month', 'name': 'Month'}],
            'measures': [
                {'name': 'Profit', 'label': 'Profit', 'expression': 'SUM(Profit)'},
                {'name': 'Sales', 'label': 'Sales', 'expression': 'SUM(Sales)'},
            ],
            'mark_encoding': {},
        }
        ctm = {'Month': 'Data', 'Profit': 'Data', 'Sales': 'Data'}
        create_visual_container(ws, col_table_map=ctm, measure_lookup={})
        auto = get_auto_generated_measures()
        self.assertEqual(auto[0]['name'], '_bump_rank_Profit')

    def test_bump_chart_no_measures_no_crash(self):
        ws = {
            'name': 'Empty Bump',
            'visualType': 'bumpchart',
            'dimensions': [{'field': 'Date', 'name': 'Date'}],
            'measures': [],
            'mark_encoding': {},
        }
        create_visual_container(ws, col_table_map={'Date': 'T'}, measure_lookup={})
        auto = get_auto_generated_measures()
        self.assertEqual(len(auto), 0)  # No measure → no rank injection

    def test_non_bump_chart_no_rank_injection(self):
        ws = {
            'name': 'Normal Line',
            'visualType': 'line',
            'dimensions': [{'field': 'Year', 'name': 'Year'}],
            'measures': [{'name': 'Sales', 'label': 'Sales',
                          'expression': 'SUM(Sales)'}],
            'mark_encoding': {},
        }
        create_visual_container(ws, col_table_map={'Year': 'T'}, measure_lookup={})
        auto = get_auto_generated_measures()
        self.assertEqual(len(auto), 0)

    def test_bump_chart_approximation_note_updated(self):
        from powerbi_import.visual_generator import APPROXIMATION_MAP
        note = APPROXIMATION_MAP.get('bumpchart', (None, ''))[1]
        self.assertIn('RANKX', note)

    def test_clear_auto_generated_measures(self):
        ws = {
            'name': 'B', 'visualType': 'bumpchart',
            'dimensions': [{'field': 'X', 'name': 'X'}],
            'measures': [{'name': 'M', 'label': 'M', 'expression': 'SUM(M)'}],
            'mark_encoding': {},
        }
        create_visual_container(ws, col_table_map={'X': 'T'}, measure_lookup={})
        self.assertGreater(len(get_auto_generated_measures()), 0)
        clear_auto_generated_measures()
        self.assertEqual(len(get_auto_generated_measures()), 0)


# ═══════════════════════════════════════════════════════════════════
# 84.4  PDF connector depth
# ═══════════════════════════════════════════════════════════════════

from tableau_export.m_query_builder import _gen_m_pdf


class TestPdfConnectorDepth(unittest.TestCase):
    """84.4 — PDF connector: page range, table selection."""

    def test_default_pdf_first_table(self):
        m = _gen_m_pdf({'filename': 'report.pdf'}, 'Sales', [])
        self.assertIn('Pdf.Tables(', m)
        self.assertIn('{0}', m)  # table index 0

    def test_pdf_start_page(self):
        m = _gen_m_pdf({'filename': 'r.pdf', 'start_page': 3}, 'T', [])
        self.assertIn('[StartPage=3]', m)

    def test_pdf_end_page(self):
        m = _gen_m_pdf({'filename': 'r.pdf', 'end_page': 10}, 'T', [])
        self.assertIn('[EndPage=10]', m)

    def test_pdf_start_and_end_page(self):
        m = _gen_m_pdf({'filename': 'r.pdf', 'start_page': 2, 'end_page': 5}, 'T', [])
        self.assertIn('[StartPage=2]', m)
        self.assertIn('[EndPage=5]', m)

    def test_pdf_table_index(self):
        m = _gen_m_pdf({'filename': 'r.pdf', 'table_index': 3}, 'T', [])
        self.assertIn('{3}', m)

    def test_pdf_no_pages_no_options(self):
        """Without page options, no options appear in Pdf.Tables call."""
        m = _gen_m_pdf({'filename': 'x.pdf'}, 'T', [])
        # Should have Pdf.Tables(File.Contents(...)) without extra options
        self.assertNotIn('StartPage', m)
        self.assertNotIn('EndPage', m)


# ═══════════════════════════════════════════════════════════════════
# 84.5  Salesforce SOQL depth
# ═══════════════════════════════════════════════════════════════════

from tableau_export.m_query_builder import _gen_m_salesforce


class TestSalesforceConnectorDepth(unittest.TestCase):
    """84.5 — Salesforce: SOQL passthrough, API version, relationship traversal."""

    def test_basic_salesforce_table(self):
        m = _gen_m_salesforce({}, 'Account', [])
        self.assertIn('Salesforce.Data()', m)
        self.assertIn('[Name="Account"]', m)

    def test_soql_passthrough(self):
        m = _gen_m_salesforce(
            {'soql': 'SELECT Id, Name FROM Account WHERE Active__c = true'},
            'Account', [],
        )
        self.assertIn('Value.NativeQuery(', m)
        self.assertIn('SELECT Id, Name FROM Account', m)

    def test_api_version(self):
        m = _gen_m_salesforce({'api_version': '58.0'}, 'Lead', [])
        self.assertIn('[ApiVersion="58.0"]', m)

    def test_api_version_with_soql(self):
        m = _gen_m_salesforce(
            {'api_version': '57.0', 'soql': 'SELECT Id FROM Contact'},
            'Contact', [],
        )
        self.assertIn('[ApiVersion="57.0"]', m)
        self.assertIn('Value.NativeQuery(', m)

    def test_relationship_traversal(self):
        m = _gen_m_salesforce(
            {'relationships': [
                {'column': 'Account', 'expand': ['AccountName', 'Industry']},
            ]},
            'Opportunity', [],
        )
        self.assertIn('Table.ExpandRecordColumn(', m)
        self.assertIn('"Account"', m)
        self.assertIn('"AccountName"', m)
        self.assertIn('"Industry"', m)

    def test_multiple_relationships(self):
        m = _gen_m_salesforce(
            {'relationships': [
                {'column': 'Owner', 'expand': ['OwnerName']},
                {'column': 'Account', 'expand': ['AccountName']},
            ]},
            'Opportunity', [],
        )
        # Both expand steps present
        self.assertIn('Expanded Owner', m)
        self.assertIn('Expanded Account', m)

    def test_no_soql_no_api_no_rels(self):
        m = _gen_m_salesforce({}, 'Lead', [])
        self.assertNotIn('Value.NativeQuery', m)
        self.assertNotIn('ApiVersion', m)
        self.assertNotIn('ExpandRecordColumn', m)


# ═══════════════════════════════════════════════════════════════════
# 84.6  REGEX → M fallback
# ═══════════════════════════════════════════════════════════════════

from tableau_export.m_query_builder import (
    m_regex_match,
    m_regex_extract,
    m_regex_replace,
    convert_tableau_regex_to_m,
)


class TestRegexMFallback(unittest.TestCase):
    """84.6 — REGEX functions → Power Query M Text.Regex* equivalents."""

    def test_regex_match_step(self):
        name, expr = m_regex_match('Email', r'^[a-z]+@')
        self.assertIn('Text.RegexMatch(', expr)
        self.assertIn('[Email]', expr)
        self.assertIn('type logical', expr)

    def test_regex_extract_step(self):
        name, expr = m_regex_extract('URL', r'https?://([^/]+)', 'Domain')
        self.assertIn('Text.RegexExtract(', expr)
        self.assertIn('[URL]', expr)
        self.assertIn('"Domain"', expr)

    def test_regex_replace_step(self):
        name, expr = m_regex_replace('Phone', r'[^0-9]', '')
        self.assertIn('Text.RegexReplace(', expr)
        self.assertIn('[Phone]', expr)

    def test_convert_regexp_match(self):
        result = convert_tableau_regex_to_m(
            'REGEXP_MATCH([Email], "^[a-z]+@example\\.com$")', 'is_example'
        )
        self.assertIsNotNone(result)
        name, expr = result
        self.assertIn('Text.RegexMatch(', expr)
        self.assertIn('[Email]', expr)

    def test_convert_regexp_extract(self):
        result = convert_tableau_regex_to_m(
            'REGEXP_EXTRACT([URL], "(https?://[^/]+)")', 'Domain'
        )
        self.assertIsNotNone(result)
        name, expr = result
        self.assertIn('Text.RegexExtract(', expr)
        self.assertIn('"Domain"', expr)

    def test_convert_regexp_extract_nth(self):
        result = convert_tableau_regex_to_m(
            'REGEXP_EXTRACT_NTH([Path], "([^/]+)", 2)', 'Segment'
        )
        self.assertIsNotNone(result)
        name, expr = result
        self.assertIn('Text.RegexExtract(', expr)

    def test_convert_regexp_replace(self):
        result = convert_tableau_regex_to_m(
            'REGEXP_REPLACE([Name], "[^a-zA-Z]", "")', 'CleanName'
        )
        self.assertIsNotNone(result)
        name, expr = result
        self.assertIn('Text.RegexReplace(', expr)

    def test_convert_non_regex_returns_none(self):
        result = convert_tableau_regex_to_m('SUM([Sales])', 'Total')
        self.assertIsNone(result)

    def test_convert_empty_formula_returns_none(self):
        result = convert_tableau_regex_to_m('', 'X')
        self.assertIsNone(result)

    def test_regex_match_try_otherwise(self):
        """Regex steps use try/otherwise for graceful fallback."""
        _, expr = m_regex_match('Col', r'\d+')
        self.assertIn('try', expr)
        self.assertIn('otherwise', expr)

    def test_regex_extract_try_otherwise(self):
        _, expr = m_regex_extract('Col', r'(\d+)')
        self.assertIn('try', expr)
        self.assertIn('otherwise null', expr)

    def test_regex_replace_try_otherwise(self):
        _, expr = m_regex_replace('Col', r'\s+', ' ')
        self.assertIn('try', expr)
        self.assertIn('otherwise', expr)


if __name__ == '__main__':
    unittest.main()
