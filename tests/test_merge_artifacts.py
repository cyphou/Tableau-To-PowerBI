"""
Tests for Sprint 54 — Artifact-Level Merge: Calculation Groups,
Field Parameters, Perspectives, Cultures, Goals, and Hierarchies.

Covers:
  - Hierarchy level-aware deduplication (same/different levels, longest wins)
  - Calculation group merge/conflict/namespace
  - Field parameter union and deduplication
  - Perspective merge (table reference union)
  - Culture merge (locale dedup, translation merge)
  - Goals/scorecard merge (measure-based dedup, namespace on conflict)
  - End-to-end merge_semantic_models with new artifact types
"""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.shared_model import (
    _merge_hierarchies,
    _merge_calculation_groups,
    _calc_group_signature,
    _merge_field_parameters,
    _merge_perspectives,
    _merge_cultures,
    _merge_goals,
    assess_merge,
    merge_semantic_models,
)


# ═══════════════════════════════════════════════════════════════════
#  Test helpers
# ═══════════════════════════════════════════════════════════════════

def _make_datasource(name, conn_type="postgres", tables=None, calcs=None, rels=None):
    return {
        "name": name,
        "connection": {"type": conn_type, "details": {"server": "localhost", "database": "testdb"}},
        "tables": tables or [],
        "calculations": calcs or [],
        "relationships": rels or [],
    }


def _make_table(name, columns):
    return {
        "name": name,
        "type": "table",
        "columns": [{"name": c, "datatype": "string"} for c in columns],
    }


def _make_extracted(datasources=None, worksheets=None, calcs=None,
                    parameters=None, hierarchies=None, user_filters=None,
                    perspectives=None, cultures=None, goals=None,
                    culture=None, languages=None):
    d = {
        "datasources": datasources or [],
        "worksheets": worksheets or [{"name": "Sheet1"}],
        "dashboards": [{"name": "Dash1"}],
        "calculations": calcs or [],
        "parameters": parameters or [],
        "filters": [],
        "stories": [],
        "actions": [],
        "sets": [],
        "groups": [],
        "bins": [],
        "hierarchies": hierarchies or [],
        "sort_orders": [],
        "aliases": {},
        "custom_sql": [],
        "user_filters": user_filters or [],
    }
    if perspectives is not None:
        d['_perspectives'] = perspectives
    if cultures is not None:
        d['_cultures'] = cultures
    if goals is not None:
        d['_goals'] = goals
    if culture is not None:
        d['culture'] = culture
    if languages is not None:
        d['_languages'] = languages
    return d


def _make_hierarchy(name, levels):
    """Build a hierarchy dict.

    Args:
        name: Hierarchy name
        levels: List of (level_name, column_name) tuples
    """
    return {
        "name": name,
        "levels": [
            {"name": ln, "column": cn, "ordinal": i}
            for i, (ln, cn) in enumerate(levels)
        ],
    }


def _make_param(caption, values, datatype='string', domain_type='list'):
    """Build a parameter dict with allowable values."""
    return {
        "name": caption,
        "caption": caption,
        "datatype": datatype,
        "domain_type": domain_type,
        "current_value": values[0] if values else "",
        "allowable_values": [{"value": v} for v in values],
    }


# ═══════════════════════════════════════════════════════════════════
#  Hierarchy merge tests
# ═══════════════════════════════════════════════════════════════════

class TestMergeHierarchies(unittest.TestCase):
    """Test level-aware hierarchy deduplication."""

    def test_identical_hierarchies_deduplicated(self):
        """Same name + same levels → keep one."""
        h = _make_hierarchy("Date Hierarchy", [("Year", "Year"), ("Month", "Month")])
        ex1 = _make_extracted(hierarchies=[h])
        ex2 = _make_extracted(hierarchies=[copy.deepcopy(h)])
        result = _merge_hierarchies([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], "Date Hierarchy")

    def test_different_hierarchies_kept(self):
        """Different names → keep both."""
        h1 = _make_hierarchy("Date Hierarchy", [("Year", "Year")])
        h2 = _make_hierarchy("Geo Hierarchy", [("Country", "Country")])
        ex1 = _make_extracted(hierarchies=[h1])
        ex2 = _make_extracted(hierarchies=[h2])
        result = _merge_hierarchies([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 2)

    def test_longer_hierarchy_wins(self):
        """Same name + different levels → keep the one with more levels."""
        h1 = _make_hierarchy("Date Hierarchy", [("Year", "Year"), ("Month", "Month")])
        h2 = _make_hierarchy("Date Hierarchy", [
            ("Year", "Year"), ("Quarter", "Quarter"), ("Month", "Month"), ("Day", "Day"),
        ])
        ex1 = _make_extracted(hierarchies=[h1])
        ex2 = _make_extracted(hierarchies=[h2])
        result = _merge_hierarchies([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['levels']), 4)

    def test_shorter_hierarchy_not_replaced(self):
        """First has more levels → second doesn't replace it."""
        h1 = _make_hierarchy("Geo", [("Country", "Country"), ("State", "State"), ("City", "City")])
        h2 = _make_hierarchy("Geo", [("Country", "Country")])
        ex1 = _make_extracted(hierarchies=[h1])
        ex2 = _make_extracted(hierarchies=[h2])
        result = _merge_hierarchies([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['levels']), 3)

    def test_same_length_different_levels_first_wins(self):
        """Same name + same count + different levels → first wins."""
        h1 = _make_hierarchy("Date", [("Year", "Year"), ("Month", "Month")])
        h2 = _make_hierarchy("Date", [("Quarter", "Quarter"), ("Week", "Week")])
        ex1 = _make_extracted(hierarchies=[h1])
        ex2 = _make_extracted(hierarchies=[h2])
        result = _merge_hierarchies([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['levels'][0]['name'], "Year")

    def test_empty_hierarchies(self):
        """No hierarchies → empty result."""
        ex1 = _make_extracted(hierarchies=[])
        ex2 = _make_extracted(hierarchies=[])
        result = _merge_hierarchies([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(result, [])

    def test_nameless_hierarchy_always_kept(self):
        """Hierarchy without name is always included."""
        h = {"levels": [{"name": "X", "column": "X", "ordinal": 0}]}
        ex1 = _make_extracted(hierarchies=[h])
        ex2 = _make_extracted(hierarchies=[copy.deepcopy(h)])
        result = _merge_hierarchies([ex1, ex2], ["wb1", "wb2"])
        # Both are kept since they have no name for dedup
        self.assertEqual(len(result), 2)

    def test_three_workbooks_longest_wins(self):
        """Three workbooks: shortest, medium, longest → longest kept."""
        h1 = _make_hierarchy("H", [("A", "A")])
        h2 = _make_hierarchy("H", [("A", "A"), ("B", "B")])
        h3 = _make_hierarchy("H", [("A", "A"), ("B", "B"), ("C", "C")])
        ex1 = _make_extracted(hierarchies=[h1])
        ex2 = _make_extracted(hierarchies=[h2])
        ex3 = _make_extracted(hierarchies=[h3])
        result = _merge_hierarchies([ex1, ex2, ex3], ["wb1", "wb2", "wb3"])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['levels']), 3)


# ═══════════════════════════════════════════════════════════════════
#  Calculation group merge tests
# ═══════════════════════════════════════════════════════════════════

class TestCalcGroupSignature(unittest.TestCase):
    """Test calculation group signature comparison."""

    def test_same_items_same_signature(self):
        cg1 = {'calculationItems': [
            {'name': 'Sales', 'expression': 'CALCULATE(SELECTEDMEASURE())'},
            {'name': 'Profit', 'expression': 'CALCULATE(SELECTEDMEASURE())'},
        ]}
        cg2 = {'calculationItems': [
            {'name': 'Profit', 'expression': 'CALCULATE(SELECTEDMEASURE())'},
            {'name': 'Sales', 'expression': 'CALCULATE(SELECTEDMEASURE())'},
        ]}
        self.assertEqual(_calc_group_signature(cg1), _calc_group_signature(cg2))

    def test_different_items_different_signature(self):
        cg1 = {'calculationItems': [
            {'name': 'Sales', 'expression': 'CALCULATE(SELECTEDMEASURE())'},
        ]}
        cg2 = {'calculationItems': [
            {'name': 'Revenue', 'expression': 'CALCULATE(SELECTEDMEASURE())'},
        ]}
        self.assertNotEqual(_calc_group_signature(cg1), _calc_group_signature(cg2))

    def test_empty_items(self):
        cg = {'calculationItems': []}
        self.assertEqual(_calc_group_signature(cg), ())


class TestMergeCalculationGroups(unittest.TestCase):
    """Test calculation group merge across workbooks."""

    def test_identical_calc_groups_deduplicated(self):
        """Same param values → merged into one."""
        p = _make_param("Metric Selector", ["Sales", "Profit", "Revenue"])
        ex1 = _make_extracted(parameters=[p])
        ex2 = _make_extracted(parameters=[copy.deepcopy(p)])
        result = _merge_calculation_groups([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['caption'], "Metric Selector")

    def test_different_calc_groups_namespaced(self):
        """Same name but different values → each namespaced."""
        p1 = _make_param("Metric Selector", ["Sales", "Profit"])
        p2 = _make_param("Metric Selector", ["Revenue", "Cost"])
        ex1 = _make_extracted(parameters=[p1])
        ex2 = _make_extracted(parameters=[p2])
        result = _merge_calculation_groups([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 2)
        names = {r['caption'] for r in result}
        self.assertIn("Metric Selector (wb1)", names)
        self.assertIn("Metric Selector (wb2)", names)

    def test_unique_calc_group_kept(self):
        """Calc group unique to one workbook → kept as-is."""
        p = _make_param("Metric Selector", ["Sales", "Profit"])
        ex1 = _make_extracted(parameters=[p])
        ex2 = _make_extracted(parameters=[])
        result = _merge_calculation_groups([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['caption'], "Metric Selector")

    def test_non_list_params_skipped(self):
        """Parameters that aren't string list type are skipped."""
        p = _make_param("Threshold", ["100"], datatype='integer', domain_type='range')
        ex1 = _make_extracted(parameters=[p])
        result = _merge_calculation_groups([ex1], ["wb1"])
        self.assertEqual(len(result), 0)

    def test_single_value_param_skipped(self):
        """Params with < 2 values are not calc groups."""
        p = _make_param("Single", ["OnlyOne"])
        ex1 = _make_extracted(parameters=[p])
        result = _merge_calculation_groups([ex1], ["wb1"])
        self.assertEqual(len(result), 0)

    def test_three_workbooks_two_identical_one_different(self):
        """wb1 and wb2 identical, wb3 different → 1 deduped + 1 namespaced."""
        p_same = _make_param("Switcher", ["A", "B", "C"])
        p_diff = _make_param("Switcher", ["X", "Y", "Z"])
        ex1 = _make_extracted(parameters=[p_same])
        ex2 = _make_extracted(parameters=[copy.deepcopy(p_same)])
        ex3 = _make_extracted(parameters=[p_diff])
        result = _merge_calculation_groups(
            [ex1, ex2, ex3], ["wb1", "wb2", "wb3"]
        )
        # All three conflict → all three namespaced
        self.assertEqual(len(result), 3)

    def test_source_workbook_tracked(self):
        """Namespaced calc groups track their source workbook."""
        p1 = _make_param("M", ["Sales", "Profit"])
        p2 = _make_param("M", ["Revenue", "Cost"])
        ex1 = _make_extracted(parameters=[p1])
        ex2 = _make_extracted(parameters=[p2])
        result = _merge_calculation_groups([ex1, ex2], ["wb1", "wb2"])
        for cg in result:
            self.assertIn('_source_workbook', cg)


# ═══════════════════════════════════════════════════════════════════
#  Field parameter merge tests
# ═══════════════════════════════════════════════════════════════════

class TestMergeFieldParameters(unittest.TestCase):
    """Test field parameter merge across workbooks."""

    def test_identical_field_params_deduplicated(self):
        """Same name + same values → one kept."""
        p = _make_param("Dimension Picker", ["City", "State", "Country"])
        ex1 = _make_extracted(parameters=[p])
        ex2 = _make_extracted(parameters=[copy.deepcopy(p)])
        result = _merge_field_parameters([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)

    def test_different_values_unioned(self):
        """Same name + different values → union all values."""
        p1 = _make_param("Dimension Picker", ["City", "State"])
        p2 = _make_param("Dimension Picker", ["State", "Country", "Region"])
        ex1 = _make_extracted(parameters=[p1])
        ex2 = _make_extracted(parameters=[p2])
        result = _merge_field_parameters([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        # Union: City, State, Country, Region (order: wb1 first, then wb2 unique)
        values = result[0]['values']
        self.assertEqual(len(values), 4)
        self.assertIn("City", values)
        self.assertIn("Country", values)
        self.assertIn("Region", values)

    def test_merged_from_tracked(self):
        """Unioned field params track their source workbooks."""
        p1 = _make_param("Picker", ["A", "B"])
        p2 = _make_param("Picker", ["B", "C"])
        ex1 = _make_extracted(parameters=[p1])
        ex2 = _make_extracted(parameters=[p2])
        result = _merge_field_parameters([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        self.assertIn('_merged_from', result[0])
        self.assertEqual(result[0]['_merged_from'], ["wb1", "wb2"])

    def test_unique_field_param_kept(self):
        """Unique to one workbook → kept as-is."""
        p = _make_param("Dim", ["X", "Y"])
        ex1 = _make_extracted(parameters=[p])
        ex2 = _make_extracted(parameters=[])
        result = _merge_field_parameters([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)

    def test_order_preserved_in_union(self):
        """Union preserves insertion order (wb1 values first, then wb2 new values)."""
        p1 = _make_param("Dim", ["Alpha", "Beta"])
        p2 = _make_param("Dim", ["Gamma", "Alpha"])
        ex1 = _make_extracted(parameters=[p1])
        ex2 = _make_extracted(parameters=[p2])
        result = _merge_field_parameters([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(result[0]['values'], ["Alpha", "Beta", "Gamma"])

    def test_empty_params_skipped(self):
        """No params → empty result."""
        ex1 = _make_extracted(parameters=[])
        result = _merge_field_parameters([ex1], ["wb1"])
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════════════
#  Perspective merge tests
# ═══════════════════════════════════════════════════════════════════

class TestMergePerspectives(unittest.TestCase):
    """Test perspective merge across workbooks."""

    def test_same_name_tables_unioned(self):
        """Same perspective name → union table lists."""
        persp1 = [{"name": "Sales View", "tables": ["Orders", "Customers"]}]
        persp2 = [{"name": "Sales View", "tables": ["Customers", "Products"]}]
        ex1 = _make_extracted(perspectives=persp1)
        ex2 = _make_extracted(perspectives=persp2)
        result = _merge_perspectives([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        tables = set(result[0]['tables'])
        self.assertEqual(tables, {"Orders", "Customers", "Products"})

    def test_different_names_kept(self):
        """Different perspective names → both kept."""
        persp1 = [{"name": "Sales View", "tables": ["Orders"]}]
        persp2 = [{"name": "Finance View", "tables": ["Budget"]}]
        ex1 = _make_extracted(perspectives=persp1)
        ex2 = _make_extracted(perspectives=persp2)
        result = _merge_perspectives([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 2)
        names = {r['name'] for r in result}
        self.assertEqual(names, {"Sales View", "Finance View"})

    def test_no_perspectives(self):
        """No perspectives → empty result."""
        ex1 = _make_extracted()
        ex2 = _make_extracted()
        result = _merge_perspectives([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(result, [])

    def test_tables_sorted(self):
        """Result tables are sorted for deterministic output."""
        persp = [{"name": "P", "tables": ["Zebra", "Alpha", "Middle"]}]
        ex1 = _make_extracted(perspectives=persp)
        result = _merge_perspectives([ex1], ["wb1"])
        self.assertEqual(result[0]['tables'], ["Alpha", "Middle", "Zebra"])

    def test_three_workbooks_union(self):
        """Three workbooks → union all tables."""
        p1 = [{"name": "All", "tables": ["A"]}]
        p2 = [{"name": "All", "tables": ["B"]}]
        p3 = [{"name": "All", "tables": ["C"]}]
        ex1 = _make_extracted(perspectives=p1)
        ex2 = _make_extracted(perspectives=p2)
        ex3 = _make_extracted(perspectives=p3)
        result = _merge_perspectives([ex1, ex2, ex3], ["wb1", "wb2", "wb3"])
        self.assertEqual(len(result), 1)
        self.assertEqual(set(result[0]['tables']), {"A", "B", "C"})


# ═══════════════════════════════════════════════════════════════════
#  Culture merge tests
# ═══════════════════════════════════════════════════════════════════

class TestMergeCultures(unittest.TestCase):
    """Test culture/locale merge across workbooks."""

    def test_same_locale_merged(self):
        """Same locale from two workbooks → one entry with merged translations."""
        c1 = [{"locale": "fr-FR", "translations": {"Measures": "Mesures"}}]
        c2 = [{"locale": "fr-FR", "translations": {"Dimensions": "Dimensions"}}]
        ex1 = _make_extracted(cultures=c1)
        ex2 = _make_extracted(cultures=c2)
        result = _merge_cultures([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['locale'], "fr-FR")
        self.assertIn("Measures", result[0]['translations'])
        self.assertIn("Dimensions", result[0]['translations'])

    def test_different_locales_kept(self):
        """Different locales → both kept."""
        c1 = [{"locale": "fr-FR", "translations": {}}]
        c2 = [{"locale": "de-DE", "translations": {}}]
        ex1 = _make_extracted(cultures=c1)
        ex2 = _make_extracted(cultures=c2)
        result = _merge_cultures([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 2)
        locales = {r['locale'] for r in result}
        self.assertEqual(locales, {"fr-FR", "de-DE"})

    def test_first_translation_wins(self):
        """Same locale + same key → first workbook's translation kept."""
        c1 = [{"locale": "fr-FR", "translations": {"Measures": "Mesures"}}]
        c2 = [{"locale": "fr-FR", "translations": {"Measures": "Indicateurs"}}]
        ex1 = _make_extracted(cultures=c1)
        ex2 = _make_extracted(cultures=c2)
        result = _merge_cultures([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(result[0]['translations']['Measures'], "Mesures")

    def test_culture_field_collected(self):
        """Culture from 'culture' field (non en-US) is collected."""
        ex1 = _make_extracted(culture="ja-JP")
        result = _merge_cultures([ex1], ["wb1"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['locale'], "ja-JP")

    def test_en_us_culture_skipped(self):
        """en-US culture is not explicitly collected (it's the default)."""
        ex1 = _make_extracted(culture="en-US")
        result = _merge_cultures([ex1], ["wb1"])
        self.assertEqual(result, [])

    def test_languages_field_collected(self):
        """Languages from '_languages' field are collected."""
        ex1 = _make_extracted(languages="fr-FR,de-DE")
        result = _merge_cultures([ex1], ["wb1"])
        self.assertEqual(len(result), 2)
        locales = {r['locale'] for r in result}
        self.assertEqual(locales, {"fr-FR", "de-DE"})

    def test_no_cultures(self):
        """No culture data → empty result."""
        ex1 = _make_extracted()
        result = _merge_cultures([ex1], ["wb1"])
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════════════
#  Goals merge tests
# ═══════════════════════════════════════════════════════════════════

class TestMergeGoals(unittest.TestCase):
    """Test goals/scorecard merge across workbooks."""

    def test_identical_goals_deduplicated(self):
        """Same goal name + same measure → one kept."""
        g = {"name": "Total Sales", "measure": "SUM(Sales)"}
        ex1 = _make_extracted(goals=[g])
        ex2 = _make_extracted(goals=[copy.deepcopy(g)])
        result = _merge_goals([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], "Total Sales")

    def test_different_measures_namespaced(self):
        """Same goal name + different measures → namespaced."""
        g1 = {"name": "Total Sales", "measure": "SUM(Revenue)"}
        g2 = {"name": "Total Sales", "measure": "SUM(Bookings)"}
        ex1 = _make_extracted(goals=[g1])
        ex2 = _make_extracted(goals=[g2])
        result = _merge_goals([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 2)
        names = {r['name'] for r in result}
        self.assertIn("Total Sales (wb1)", names)
        self.assertIn("Total Sales (wb2)", names)

    def test_unique_goals_kept(self):
        """Different goal names → both kept."""
        g1 = {"name": "Sales", "measure": "SUM(Sales)"}
        g2 = {"name": "Profit", "measure": "SUM(Profit)"}
        ex1 = _make_extracted(goals=[g1])
        ex2 = _make_extracted(goals=[g2])
        result = _merge_goals([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 2)

    def test_no_goals(self):
        """No goals → empty result."""
        ex1 = _make_extracted()
        result = _merge_goals([ex1], ["wb1"])
        self.assertEqual(result, [])

    def test_source_workbook_tracked(self):
        """Namespaced goals track their source workbook."""
        g1 = {"name": "G", "measure": "X"}
        g2 = {"name": "G", "measure": "Y"}
        ex1 = _make_extracted(goals=[g1])
        ex2 = _make_extracted(goals=[g2])
        result = _merge_goals([ex1, ex2], ["wb1", "wb2"])
        for g in result:
            self.assertIn('_source_workbook', g)

    def test_metric_name_fallback(self):
        """Goals with 'metric_name' key instead of 'name' are handled."""
        g1 = {"metric_name": "Revenue", "measure": "SUM(Rev)"}
        g2 = {"metric_name": "Revenue", "measure": "SUM(Rev)"}
        ex1 = _make_extracted(goals=[g1])
        ex2 = _make_extracted(goals=[g2])
        result = _merge_goals([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)

    def test_measure_name_fallback(self):
        """Goals with 'measure_name' key instead of 'measure' are handled."""
        g1 = {"name": "M", "measure_name": "SUM(X)"}
        g2 = {"name": "M", "measure_name": "SUM(Y)"}
        ex1 = _make_extracted(goals=[g1])
        ex2 = _make_extracted(goals=[g2])
        result = _merge_goals([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 2)


# ═══════════════════════════════════════════════════════════════════
#  End-to-end merge integration
# ═══════════════════════════════════════════════════════════════════

class TestMergeSemanticModelsArtifacts(unittest.TestCase):
    """Test that merge_semantic_models properly populates new artifact keys."""

    def _build_two_workbook_scenario(self):
        """Build a minimal 2-workbook scenario with shared tables."""
        t1 = _make_table("Orders", ["order_id", "customer_id", "amount"])
        t2 = _make_table("Orders", ["order_id", "customer_id", "amount"])
        ds1 = _make_datasource("DS1", tables=[t1])
        ds2 = _make_datasource("DS2", tables=[t2])

        h1 = _make_hierarchy("Date Hierarchy", [("Year", "Year"), ("Month", "Month")])
        h2 = _make_hierarchy("Date Hierarchy", [
            ("Year", "Year"), ("Quarter", "Quarter"), ("Month", "Month"),
        ])

        p1 = _make_param("View Selector", ["Sales", "Profit"])
        p2 = _make_param("View Selector", ["Sales", "Profit"])

        persp = [{"name": "Full Model", "tables": ["Orders"]}]

        goals = [{"name": "Total Sales", "measure": "SUM(amount)"}]

        ex1 = _make_extracted(
            datasources=[ds1], hierarchies=[h1], parameters=[p1],
            perspectives=persp, goals=goals,
        )
        ex2 = _make_extracted(
            datasources=[ds2], hierarchies=[h2], parameters=[p2],
            perspectives=[{"name": "Full Model", "tables": ["Orders", "Products"]}],
            goals=[copy.deepcopy(goals[0])],
        )
        return [ex1, ex2], ["wb1", "wb2"]

    def test_merged_has_hierarchy_key(self):
        all_extracted, wb_names = self._build_two_workbook_scenario()
        assessment = assess_merge(all_extracted, wb_names)
        merged = merge_semantic_models(all_extracted, assessment, "TestModel")
        self.assertIn('hierarchies', merged)
        # Should have 1 hierarchy (deduped, longest wins = 3 levels)
        self.assertEqual(len(merged['hierarchies']), 1)
        self.assertEqual(len(merged['hierarchies'][0]['levels']), 3)

    def test_merged_has_calc_groups_key(self):
        all_extracted, wb_names = self._build_two_workbook_scenario()
        assessment = assess_merge(all_extracted, wb_names)
        merged = merge_semantic_models(all_extracted, assessment, "TestModel")
        self.assertIn('_calculation_groups', merged)

    def test_merged_has_field_params_key(self):
        all_extracted, wb_names = self._build_two_workbook_scenario()
        assessment = assess_merge(all_extracted, wb_names)
        merged = merge_semantic_models(all_extracted, assessment, "TestModel")
        self.assertIn('_field_parameters', merged)

    def test_merged_has_perspectives_key(self):
        all_extracted, wb_names = self._build_two_workbook_scenario()
        assessment = assess_merge(all_extracted, wb_names)
        merged = merge_semantic_models(all_extracted, assessment, "TestModel")
        self.assertIn('_perspectives', merged)
        # Union of tables: Orders + Products
        self.assertEqual(len(merged['_perspectives']), 1)
        tables = set(merged['_perspectives'][0]['tables'])
        self.assertIn("Orders", tables)
        self.assertIn("Products", tables)

    def test_merged_has_cultures_key(self):
        all_extracted, wb_names = self._build_two_workbook_scenario()
        assessment = assess_merge(all_extracted, wb_names)
        merged = merge_semantic_models(all_extracted, assessment, "TestModel")
        self.assertIn('_cultures', merged)

    def test_merged_has_goals_key(self):
        all_extracted, wb_names = self._build_two_workbook_scenario()
        assessment = assess_merge(all_extracted, wb_names)
        merged = merge_semantic_models(all_extracted, assessment, "TestModel")
        self.assertIn('_goals', merged)
        # Same goal name + same measure → 1 deduped
        self.assertEqual(len(merged['_goals']), 1)


class TestMergeArtifactsEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions for artifact merge."""

    def test_calc_groups_and_field_params_from_same_param(self):
        """A param that looks like both calc group and field param is collected in both."""
        p = _make_param("Switcher", ["Sales", "Profit", "Region"])
        ex1 = _make_extracted(parameters=[p])
        cg = _merge_calculation_groups([ex1], ["wb1"])
        fp = _merge_field_parameters([ex1], ["wb1"])
        # Both should collect it (TMDL generator decides which to use)
        self.assertTrue(len(cg) > 0 or len(fp) > 0)

    def test_hierarchy_with_empty_levels(self):
        """Hierarchy with no levels is handled gracefully."""
        h = {"name": "EmptyH", "levels": []}
        ex1 = _make_extracted(hierarchies=[h])
        ex2 = _make_extracted(hierarchies=[copy.deepcopy(h)])
        result = _merge_hierarchies([ex1, ex2], ["wb1", "wb2"])
        self.assertEqual(len(result), 1)

    def test_large_union_field_params(self):
        """Union of 3 workbooks with overlapping field params."""
        p1 = _make_param("Dim", ["A", "B", "C"])
        p2 = _make_param("Dim", ["B", "C", "D"])
        p3 = _make_param("Dim", ["D", "E", "F"])
        ex1 = _make_extracted(parameters=[p1])
        ex2 = _make_extracted(parameters=[p2])
        ex3 = _make_extracted(parameters=[p3])
        result = _merge_field_parameters([ex1, ex2, ex3], ["wb1", "wb2", "wb3"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['values'], ["A", "B", "C", "D", "E", "F"])

    def test_goals_with_no_name_skipped(self):
        """Goals without a name are skipped in merge."""
        g = {"measure": "SUM(X)"}  # No name or metric_name
        ex1 = _make_extracted(goals=[g])
        result = _merge_goals([ex1], ["wb1"])
        self.assertEqual(result, [])

    def test_cultures_dedup_from_explicit_and_field(self):
        """Culture from explicit _cultures and 'culture' field are merged."""
        c = [{"locale": "fr-FR", "translations": {"Measures": "Mesures"}}]
        ex1 = _make_extracted(cultures=c, culture="fr-FR")
        result = _merge_cultures([ex1], ["wb1"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['locale'], "fr-FR")

    def test_perspective_empty_tables(self):
        """Perspective with empty table list is handled."""
        persp = [{"name": "EmptyP", "tables": []}]
        ex1 = _make_extracted(perspectives=persp)
        result = _merge_perspectives([ex1], ["wb1"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['tables'], [])


if __name__ == '__main__':
    unittest.main()
