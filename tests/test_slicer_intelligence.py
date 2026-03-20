"""
Tests for Sprint 77 — Advanced Slicer & Filter Intelligence.

Covers: filter mode classification (categorical, range, relative-date,
wildcard, top-n, context), 6 slicer modes (Dropdown, List, Between,
Basic, Date, Search), cardinality-based mode selection, context filter
promotion, and slicer visual JSON structure.
"""

import json
import os
import sys
import unittest
import uuid
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from tableau_export.extract_tableau_data import TableauExtractor
from powerbi_import.pbip_generator import PowerBIProjectGenerator


def _make_extractor():
    ext = TableauExtractor.__new__(TableauExtractor)
    ext.workbook_data = {}
    return ext


def _make_generator():
    gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
    gen._field_map = {}
    gen._main_table = 'Table'
    return gen


# ── Filter Mode Classification ─────────────────────────────────────

class TestFilterModeClassification(unittest.TestCase):
    """Tests for extract_filters() filter_mode classification."""

    def _extract(self, filter_xml):
        ext = _make_extractor()
        root = ET.fromstring(f'<root>{filter_xml}</root>')
        ext.extract_filters(root)
        return ext.workbook_data.get('filters', [])

    def test_basic_categorical(self):
        filters = self._extract(
            '<filter column="[Category]" type="categorical">'
            '<value>A</value><value>B</value></filter>')
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]['filter_mode'], 'categorical')
        self.assertEqual(filters[0]['values'], ['A', 'B'])

    def test_range_min_max(self):
        filters = self._extract(
            '<filter column="[Amount]" type="range" min="10" max="100" />')
        self.assertEqual(filters[0]['filter_mode'], 'range')
        self.assertEqual(filters[0]['min'], '10')
        self.assertEqual(filters[0]['max'], '100')

    def test_relative_date(self):
        filters = self._extract(
            '<filter column="[OrderDate]" period="month" period-type="last" count="3" />')
        self.assertEqual(filters[0]['filter_mode'], 'relative-date')
        self.assertEqual(filters[0]['period'], 'month')
        self.assertEqual(filters[0]['period_type'], 'last')
        self.assertEqual(filters[0]['period_count'], 3)

    def test_wildcard(self):
        filters = self._extract(
            '<filter column="[Name]" match="sales" match-type="contains" />')
        self.assertEqual(filters[0]['filter_mode'], 'wildcard')
        self.assertEqual(filters[0]['match'], 'sales')
        self.assertEqual(filters[0]['match_type'], 'contains')

    def test_top_n(self):
        filters = self._extract(
            '<filter column="[Product]"><top>10</top></filter>')
        self.assertEqual(filters[0]['filter_mode'], 'top-n')
        self.assertEqual(filters[0]['top_n_count'], 10)

    def test_context_filter(self):
        filters = self._extract(
            '<filter column="[Region]" context="true">'
            '<value>West</value></filter>')
        self.assertEqual(filters[0]['filter_mode'], 'context')
        self.assertTrue(filters[0]['is_context'])

    def test_exclude_mode(self):
        filters = self._extract(
            '<filter column="[Status]" exclude="true">'
            '<value>Cancelled</value></filter>')
        self.assertTrue(filters[0]['exclude'])
        self.assertEqual(filters[0]['filter_mode'], 'categorical')

    def test_empty_filter(self):
        filters = self._extract('<filter column="[All]" type="all" />')
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]['filter_mode'], 'categorical')

    def test_relative_date_with_anchor(self):
        filters = self._extract(
            '<filter column="[Date]" period="year" period-type="this" '
            'anchor-date="2025-01-01" />')
        self.assertEqual(filters[0]['filter_mode'], 'relative-date')
        self.assertEqual(filters[0]['anchor_date'], '2025-01-01')
        self.assertEqual(filters[0]['period_type'], 'this')

    def test_multiple_filters_mixed(self):
        xml = ('<filter column="[A]"><value>X</value></filter>'
               '<filter column="[B]" min="0" max="50" />'
               '<filter column="[C]" period="day" />')
        filters = self._extract(xml)
        modes = [f['filter_mode'] for f in filters]
        self.assertEqual(modes, ['categorical', 'range', 'relative-date'])


# ── Slicer Mode Detection ─────────────────────────────────────────

class TestSlicerModeDetection(unittest.TestCase):
    """Tests for _detect_slicer_mode() with all 6 modes."""

    def _detect(self, obj=None, column='Col', converted=None):
        gen = _make_generator()
        obj = obj or {}
        converted = converted or {'parameters': [], 'datasources': []}
        return gen._detect_slicer_mode(obj, column, converted)

    def test_default_dropdown(self):
        self.assertEqual(self._detect(), 'Dropdown')

    def test_range_parameter(self):
        converted = {
            'parameters': [{'name': 'Slider', 'domain_type': 'range'}],
            'datasources': []
        }
        self.assertEqual(self._detect(column='Slider', converted=converted), 'Between')

    def test_list_parameter(self):
        converted = {
            'parameters': [{'name': 'Picker', 'domain_type': 'list'}],
            'datasources': []
        }
        self.assertEqual(self._detect(column='Picker', converted=converted), 'List')

    def test_date_column(self):
        converted = {
            'parameters': [],
            'datasources': [{'tables': [{'columns': [
                {'name': 'OrderDate', 'datatype': 'date'}
            ]}]}]
        }
        self.assertEqual(self._detect(column='OrderDate', converted=converted), 'Date')

    def test_numeric_column(self):
        converted = {
            'parameters': [],
            'datasources': [{'tables': [{'columns': [
                {'name': 'Amount', 'datatype': 'real'}
            ]}]}]
        }
        self.assertEqual(self._detect(column='Amount', converted=converted), 'Between')

    def test_filter_mode_relative_date(self):
        obj = {'filter_mode': 'relative-date'}
        self.assertEqual(self._detect(obj=obj), 'Basic')

    def test_filter_mode_wildcard(self):
        obj = {'filter_mode': 'wildcard'}
        self.assertEqual(self._detect(obj=obj), 'Search')

    def test_filter_mode_top_n(self):
        obj = {'filter_mode': 'top-n'}
        self.assertEqual(self._detect(obj=obj), 'List')

    def test_filter_mode_range(self):
        obj = {'filter_mode': 'range'}
        self.assertEqual(self._detect(obj=obj), 'Between')

    def test_datetime_column(self):
        converted = {
            'parameters': [],
            'datasources': [{'tables': [{'columns': [
                {'name': 'ts', 'datatype': 'datetime'}
            ]}]}]
        }
        self.assertEqual(self._detect(column='ts', converted=converted), 'Date')

    def test_low_cardinality_list(self):
        converted = {
            'parameters': [],
            'datasources': [{'tables': [{'columns': [
                {'name': 'Status', 'datatype': 'string', 'cardinality': 5}
            ]}]}]
        }
        self.assertEqual(self._detect(column='Status', converted=converted), 'List')


# ── Slicer Visual JSON Structure ───────────────────────────────────

class TestSlicerVisualJSON(unittest.TestCase):
    """Tests for _create_slicer_visual() JSON output for each mode."""

    def _slicer(self, mode='Dropdown'):
        gen = _make_generator()
        return gen._create_slicer_visual('vid1', 10, 20, 200, 50,
                                          'Category', 'Sales', 0,
                                          slicer_mode=mode)

    def test_dropdown_mode(self):
        s = self._slicer('Dropdown')
        mode_val = s['visual']['objects']['data'][0]['properties']['mode']
        self.assertIn('Dropdown', str(mode_val))

    def test_list_mode(self):
        s = self._slicer('List')
        mode_val = s['visual']['objects']['data'][0]['properties']['mode']
        self.assertIn('List', str(mode_val))

    def test_between_mode_has_numeric_input(self):
        s = self._slicer('Between')
        self.assertIn('numericInputStyle', s['visual']['objects'])

    def test_basic_relative_date_config(self):
        s = self._slicer('Basic')
        self.assertIn('relativeDate', s['visual']['objects'])

    def test_date_mode_maps_to_basic(self):
        s = self._slicer('Date')
        mode_val = s['visual']['objects']['data'][0]['properties']['mode']
        self.assertIn('Basic', str(mode_val))

    def test_search_mode_has_search_enabled(self):
        s = self._slicer('Search')
        self.assertIn('search', s['visual']['objects'])
        search_prop = s['visual']['objects']['search'][0]['properties']
        self.assertIn('enabled', search_prop)

    def test_search_mode_has_selection(self):
        s = self._slicer('Search')
        self.assertIn('selection', s['visual']['objects'])

    def test_query_binding(self):
        s = self._slicer('Dropdown')
        query = s['visual']['query']
        proj = query['queryState']['Values']['projections'][0]
        self.assertEqual(proj['field']['Column']['Property'], 'Category')
        self.assertEqual(
            proj['field']['Column']['Expression']['SourceRef']['Entity'],
            'Sales')

    def test_position(self):
        s = self._slicer()
        self.assertEqual(s['position']['x'], 10)
        self.assertEqual(s['position']['y'], 20)
        self.assertEqual(s['position']['width'], 200)
        self.assertEqual(s['position']['height'], 50)


# ── Visual Filter Creation ─────────────────────────────────────────

class TestVisualFilterCreation(unittest.TestCase):
    """Tests for _create_visual_filters() with extended filter modes."""

    def _make_gen(self):
        gen = _make_generator()
        gen._field_map = {}
        gen._main_table = 'Sales'
        return gen

    def test_relative_date_filter(self):
        gen = self._make_gen()
        filters = gen._create_visual_filters([{
            'field': 'OrderDate',
            'filter_mode': 'relative-date',
            'period': 'month',
            'period_type': 'last',
            'period_count': 6,
        }])
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]['type'], 'RelativeDate')
        where = filters[0]['filter']['Where'][0]['Condition']
        self.assertIn('RelativeDate', where)
        self.assertEqual(where['RelativeDate']['TimeUnitCount'], 6)
        self.assertEqual(where['RelativeDate']['TimeUnit'], 2)  # month

    def test_context_filter_passes_through(self):
        gen = self._make_gen()
        filters = gen._create_visual_filters([{
            'field': 'Region',
            'filter_mode': 'context',
            'values': ['West', 'East'],
        }])
        # Context filters fall through to categorical
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]['type'], 'Categorical')

    def test_range_filter(self):
        gen = self._make_gen()
        filters = gen._create_visual_filters([{
            'field': 'Amount',
            'type': 'range',
            'min': 100,
            'max': 500,
        }])
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]['type'], 'Advanced')

    def test_empty_values_skipped(self):
        gen = self._make_gen()
        filters = gen._create_visual_filters([{
            'field': 'Category',
            'type': 'categorical',
            'values': [],
        }])
        self.assertEqual(len(filters), 0)

    def test_relative_date_period_day(self):
        gen = self._make_gen()
        filters = gen._create_visual_filters([{
            'field': 'Date',
            'filter_mode': 'relative-date',
            'period': 'day',
            'period_type': 'this',
            'period_count': 1,
        }])
        where = filters[0]['filter']['Where'][0]['Condition']
        self.assertEqual(where['RelativeDate']['TimeUnit'], 0)  # day
        self.assertEqual(where['RelativeDate']['RelativeDateFilterType'], 1)  # this

    def test_relative_date_period_year(self):
        gen = self._make_gen()
        filters = gen._create_visual_filters([{
            'field': 'Date',
            'filter_mode': 'relative-date',
            'period': 'year',
            'period_type': 'next',
            'period_count': 2,
        }])
        where = filters[0]['filter']['Where'][0]['Condition']
        self.assertEqual(where['RelativeDate']['TimeUnit'], 4)  # year
        self.assertEqual(where['RelativeDate']['RelativeDateFilterType'], 2)  # next
        self.assertEqual(where['RelativeDate']['TimeUnitCount'], 2)


if __name__ == '__main__':
    unittest.main()
