"""Tests for Sprint 92 — Deep Extraction: Tableau 2024+ Features.

Covers:
- Dynamic zone visibility condition extraction and bookmark generation
- Table extension extraction and M query generation
- Multi-connection blend M query generation
- Linguistic schema extraction and TMDL culture synonyms
"""
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))


class TestDynamicZoneVisibility(unittest.TestCase):
    """Tests for dynamic zone visibility extraction and bookmark mapping."""

    def _make_dashboard_xml(self, zones_xml):
        return ET.fromstring(f'<dashboard name="Dash1">{zones_xml}</dashboard>')

    def test_extract_basic_dynamic_zone(self):
        from tableau_export.extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        xml = self._make_dashboard_xml('''
            <zone name="Sheet1" id="1">
                <dynamic-zone-visibility field="[Parameters].[Show]"
                    value="true" condition="equals" default="true"/>
            </zone>
        ''')
        zones = ext.extract_dynamic_zone_visibility(xml)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0]['zone_name'], 'Sheet1')
        self.assertEqual(zones[0]['field'], '[Parameters].[Show]')
        self.assertEqual(zones[0]['value'], 'true')
        self.assertEqual(zones[0]['condition'], 'equals')
        self.assertTrue(zones[0]['default_visible'])

    def test_extract_hidden_by_default_zone(self):
        from tableau_export.extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        xml = self._make_dashboard_xml('''
            <zone name="Detail" id="2">
                <dynamic-zone-visibility field="[Toggle]"
                    value="1" condition="equals" default="false"/>
            </zone>
        ''')
        zones = ext.extract_dynamic_zone_visibility(xml)
        self.assertEqual(len(zones), 1)
        self.assertFalse(zones[0]['default_visible'])

    def test_extract_multiple_dynamic_zones(self):
        from tableau_export.extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        xml = self._make_dashboard_xml('''
            <zone name="A" id="1">
                <dynamic-zone-visibility field="[F1]" value="x" condition="equals"/>
            </zone>
            <zone name="B" id="2">
                <dynamic-zone-visibility field="[F1]" value="y" condition="equals"/>
            </zone>
        ''')
        zones = ext.extract_dynamic_zone_visibility(xml)
        self.assertEqual(len(zones), 2)
        self.assertEqual(zones[0]['zone_name'], 'A')
        self.assertEqual(zones[1]['zone_name'], 'B')

    def test_no_dynamic_zones(self):
        from tableau_export.extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        xml = self._make_dashboard_xml('<zone name="Static" id="1"/>')
        zones = ext.extract_dynamic_zone_visibility(xml)
        self.assertEqual(zones, [])

    def test_swap_bookmarks_include_visibility_state(self):
        from powerbi_import.pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        dynamic_zones = [
            {'zone_name': 'Sales', 'field': '[Toggle]', 'value': '1',
             'condition': 'equals', 'default_visible': True},
            {'zone_name': 'Profit', 'field': '[Toggle]', 'value': '2',
             'condition': 'equals', 'default_visible': False},
        ]
        bookmarks = gen._create_swap_bookmarks(dynamic_zones, 'Page1')
        self.assertEqual(len(bookmarks), 2)
        # First bookmark shows Sales, hides Profit
        vis0 = bookmarks[0]['explorationState']['visualsVisibility']
        self.assertTrue(vis0['Sales'])
        self.assertFalse(vis0['Profit'])
        # Second bookmark shows Profit, hides Sales
        vis1 = bookmarks[1]['explorationState']['visualsVisibility']
        self.assertFalse(vis1['Sales'])
        self.assertTrue(vis1['Profit'])

    def test_swap_bookmark_has_target_visual_name(self):
        from powerbi_import.pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        dynamic_zones = [
            {'zone_name': 'Chart', 'field': '[P]', 'value': 'A',
             'condition': 'equals', 'default_visible': True},
        ]
        bookmarks = gen._create_swap_bookmarks(dynamic_zones, 'PageX')
        self.assertEqual(bookmarks[0]['options']['targetVisualName'], 'Chart')
        self.assertEqual(bookmarks[0]['explorationState']['activeSection'], 'PageX')


class TestTableExtensions(unittest.TestCase):
    """Tests for Tableau 2024.2+ table extension extraction."""

    def test_extract_basic_table_extension(self):
        from tableau_export.datasource_extractor import extract_table_extensions
        xml = ET.fromstring('''
        <datasource>
            <table-extension type="einstein-discovery" name="Predictions">
                <connection url="https://api.example.com/predict"/>
                <column name="[Score]" datatype="real"/>
                <column name="[Label]" datatype="string"/>
            </table-extension>
        </datasource>
        ''')
        exts = extract_table_extensions(xml)
        self.assertEqual(len(exts), 1)
        self.assertEqual(exts[0]['name'], 'Predictions')
        self.assertEqual(exts[0]['extension_type'], 'einstein-discovery')
        self.assertEqual(exts[0]['endpoint'], 'https://api.example.com/predict')
        self.assertEqual(len(exts[0]['schema']), 2)

    def test_extract_extension_without_endpoint(self):
        from tableau_export.datasource_extractor import extract_table_extensions
        xml = ET.fromstring('''
        <datasource>
            <table-extension type="custom-api" name="Custom">
                <column name="[Data]" datatype="string"/>
            </table-extension>
        </datasource>
        ''')
        exts = extract_table_extensions(xml)
        self.assertEqual(len(exts), 1)
        self.assertEqual(exts[0]['endpoint'], '')
        self.assertEqual(exts[0]['extension_type'], 'custom-api')

    def test_no_table_extensions(self):
        from tableau_export.datasource_extractor import extract_table_extensions
        xml = ET.fromstring('<datasource><relation type="table" name="T1"/></datasource>')
        exts = extract_table_extensions(xml)
        self.assertEqual(exts, [])

    def test_multiple_extensions(self):
        from tableau_export.datasource_extractor import extract_table_extensions
        xml = ET.fromstring('''
        <datasource>
            <table-extension type="api" name="Ext1">
                <connection url="https://a.com"/>
            </table-extension>
            <table-extension type="ml" name="Ext2">
                <connection url="https://b.com"/>
                <column name="[Pred]" datatype="real"/>
            </table-extension>
        </datasource>
        ''')
        exts = extract_table_extensions(xml)
        self.assertEqual(len(exts), 2)
        self.assertEqual(exts[0]['name'], 'Ext1')
        self.assertEqual(exts[1]['name'], 'Ext2')

    def test_m_query_for_extension_with_endpoint(self):
        from tableau_export.m_query_builder import generate_table_extension_query
        ext = {
            'name': 'Predictions',
            'extension_type': 'einstein-discovery',
            'endpoint': 'https://api.example.com/predict',
            'schema': [
                {'name': 'Score', 'datatype': 'real'},
                {'name': 'Label', 'datatype': 'string'},
            ],
            'config': {}
        }
        m = generate_table_extension_query(ext)
        self.assertIn('Web.Contents', m)
        self.assertIn('https://api.example.com/predict', m)
        self.assertIn('Number.Type', m)
        self.assertIn('Text.Type', m)

    def test_m_query_for_extension_without_endpoint(self):
        from tableau_export.m_query_builder import generate_table_extension_query
        ext = {
            'name': 'Custom',
            'extension_type': 'custom-api',
            'endpoint': '',
            'schema': [{'name': 'Value', 'datatype': 'string'}],
            'config': {}
        }
        m = generate_table_extension_query(ext)
        self.assertIn('MigrationNote', m)
        self.assertIn('#table', m)


class TestMultiConnectionBlending(unittest.TestCase):
    """Tests for multi-connection blend M query generation."""

    def test_blend_with_link_columns(self):
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('Orders', 'Returns',
                                        [{'primary': 'OrderID', 'secondary': 'OrderID'}])
        self.assertIn('Table.NestedJoin', m)
        self.assertIn('"OrderID"', m)
        self.assertIn('JoinKind.LeftOuter', m)
        self.assertIn('Table.ExpandTableColumn', m)

    def test_blend_multiple_keys(self):
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('Sales', 'Targets',
                                        [{'primary': 'Region', 'secondary': 'Region'},
                                         {'primary': 'Year', 'secondary': 'Year'}])
        self.assertIn('"Region"', m)
        self.assertIn('"Year"', m)

    def test_blend_inner_join(self):
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('A', 'B',
                                        [{'primary': 'Key', 'secondary': 'Key'}],
                                        join_kind='inner')
        self.assertIn('JoinKind.Inner', m)

    def test_blend_full_join(self):
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('A', 'B',
                                        [{'primary': 'K', 'secondary': 'K'}],
                                        join_kind='full')
        self.assertIn('JoinKind.FullOuter', m)

    def test_blend_no_link_columns_combines(self):
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('A', 'B', [])
        self.assertIn('Table.Combine', m)
        self.assertNotIn('Table.NestedJoin', m)

    def test_blend_column_key_fallback(self):
        """Tests that 'column' key is used when 'primary'/'secondary' missing."""
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('X', 'Y',
                                        [{'column': 'ID'}])
        self.assertIn('"ID"', m)


class TestLinguisticSchema(unittest.TestCase):
    """Tests for linguistic schema extraction and TMDL culture generation."""

    def test_extract_synonyms_from_captions(self):
        from tableau_export.extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        ext.workbook_data = {}
        xml = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <column name="[Sales Amount]" caption="Revenue" datatype="real"/>
                <column name="[Cust_Name]" caption="Customer Name" datatype="string"/>
                <column name="[ID]" datatype="integer"/>
            </datasource>
        </workbook>
        ''')
        ext.extract_linguistic_schema(xml)
        schema = ext.workbook_data['linguistic_schema']
        self.assertIn('Sales Amount', schema)
        self.assertIn('Revenue', schema['Sales Amount'])
        self.assertIn('Cust_Name', schema)
        self.assertIn('Customer Name', schema['Cust_Name'])
        # ID has no caption different from name
        self.assertNotIn('ID', schema)

    def test_extract_synonyms_from_description(self):
        from tableau_export.extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        ext.workbook_data = {}
        xml = ET.fromstring('''
        <workbook>
            <datasource name="ds1">
                <column name="[Qty]" desc="Quantity Ordered" datatype="integer"/>
            </datasource>
        </workbook>
        ''')
        ext.extract_linguistic_schema(xml)
        self.assertIn('Qty', ext.workbook_data['linguistic_schema'])
        self.assertIn('Quantity Ordered', ext.workbook_data['linguistic_schema']['Qty'])

    def test_empty_workbook_no_synonyms(self):
        from tableau_export.extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        ext.workbook_data = {}
        xml = ET.fromstring('<workbook/>')
        ext.extract_linguistic_schema(xml)
        self.assertEqual(ext.workbook_data['linguistic_schema'], {})

    def test_culture_tmdl_includes_synonyms(self):
        from powerbi_import.tmdl_generator import _write_culture_tmdl
        with tempfile.TemporaryDirectory() as tmp:
            synonyms = {
                'Revenue': ['Sales Amount', 'Income'],
                'Qty': ['Quantity'],
            }
            _write_culture_tmdl(tmp, 'en-US', [], linguistic_synonyms=synonyms)
            path = os.path.join(tmp, 'en-US.tmdl')
            self.assertTrue(os.path.exists(path))
            content = open(path, encoding='utf-8').read()
            self.assertIn('Entities', content)
            self.assertIn('Revenue', content)
            self.assertIn('Sales Amount', content)

    def test_culture_tmdl_without_synonyms(self):
        from powerbi_import.tmdl_generator import _write_culture_tmdl
        with tempfile.TemporaryDirectory() as tmp:
            _write_culture_tmdl(tmp, 'fr-FR', [])
            path = os.path.join(tmp, 'fr-FR.tmdl')
            content = open(path, encoding='utf-8').read()
            self.assertNotIn('Entities', content)
            self.assertIn('DynamicImprovement', content)


class TestExtractTableExtensionsIntegration(unittest.TestCase):
    """Integration tests for extract_table_extensions in the main extractor."""

    def test_extract_table_extensions_method(self):
        from tableau_export.extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        ext.workbook_data = {}
        root = ET.fromstring('''
        <workbook>
            <datasource caption="MyDS">
                <table-extension type="external-api" name="APIData">
                    <connection url="https://data.example.com/v1"/>
                    <column name="[Result]" datatype="string"/>
                </table-extension>
            </datasource>
        </workbook>
        ''')
        ext.extract_table_extensions(root)
        te = ext.workbook_data['table_extensions']
        self.assertEqual(len(te), 1)
        self.assertEqual(te[0]['datasource'], 'MyDS')
        self.assertEqual(te[0]['name'], 'APIData')

    def test_no_extensions_returns_empty(self):
        from tableau_export.extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        ext.workbook_data = {}
        root = ET.fromstring('<workbook><datasource name="ds"/></workbook>')
        ext.extract_table_extensions(root)
        self.assertEqual(ext.workbook_data['table_extensions'], [])


class TestBlendQueryValid(unittest.TestCase):
    """Validates that blend M queries are syntactically well-formed."""

    def test_blend_has_let_in_structure(self):
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('Q1', 'Q2', [{'primary': 'K', 'secondary': 'K'}])
        self.assertTrue(m.startswith('let'))
        self.assertIn('\nin\n', m)

    def test_combine_has_let_in_structure(self):
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('Q1', 'Q2', [])
        self.assertTrue(m.startswith('let'))
        self.assertIn('\nin\n', m)

    def test_right_join(self):
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('A', 'B', [{'primary': 'X', 'secondary': 'X'}],
                                        join_kind='right')
        self.assertIn('JoinKind.RightOuter', m)

    def test_leftanti_join(self):
        from tableau_export.m_query_builder import generate_blend_merge_query
        m = generate_blend_merge_query('A', 'B', [{'primary': 'X', 'secondary': 'X'}],
                                        join_kind='leftanti')
        self.assertIn('JoinKind.LeftAnti', m)


if __name__ == '__main__':
    unittest.main()
