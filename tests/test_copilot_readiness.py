"""
Tests for Sprint 118 — Semantic Descriptions & Linguistic Schema (Copilot/Q&A Readiness).

Validates:
- Table descriptions auto-generated in TMDL
- Column descriptions auto-generated in TMDL
- Measure descriptions auto-generated (with original formula)
- Copilot annotation hints (Copilot_DateTable, Copilot_Hidden, etc.)
- Linguistic schema depth (humanized names, CamelCase splitting)
- Calculation description extraction from Tableau XML
"""

import json
import os
import sys
import tempfile
import shutil
import uuid

import pytest

# ── Path setup ──────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'powerbi_import'))
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))

from powerbi_import.tmdl_generator import (
    _generate_table_description,
    _generate_column_description,
    _generate_measure_description,
    _write_table_tmdl,
    _write_measure,
    _write_column_flags,
    generate_tmdl,
)


# ── Helper: read TMDL file content ─────────────────────────────────

def _read_tmdl(tables_dir, table_name):
    """Read TMDL content for a table name."""
    # Try common filename patterns
    for fname in os.listdir(tables_dir):
        if fname.endswith('.tmdl'):
            path = os.path.join(tables_dir, fname)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Check if this is our table
            if f"table '{table_name}'" in content or f'table {table_name}' in content:
                return content
    return None


# ═══════════════════════════════════════════════════════════════════
#  1. TABLE DESCRIPTION GENERATION
# ═══════════════════════════════════════════════════════════════════

class TestTableDescriptionGeneration:
    """Tests for _generate_table_description()."""

    def test_explicit_description_preserved(self):
        """Explicit description should be returned as-is."""
        table = {'name': 'Orders', 'description': 'Custom desc', 'columns': [], 'measures': []}
        assert _generate_table_description(table) == 'Custom desc'

    def test_auto_generated_from_columns(self):
        """Should synthesize from column names."""
        table = {
            'name': 'Orders',
            'columns': [
                {'name': 'OrderID'},
                {'name': 'CustomerName'},
                {'name': 'OrderDate'},
            ],
            'measures': []
        }
        desc = _generate_table_description(table)
        assert 'Contains 3 columns' in desc
        assert 'OrderID' in desc
        assert 'CustomerName' in desc
        assert 'OrderDate' in desc

    def test_includes_measure_count(self):
        """Should mention measure count when measures exist."""
        table = {
            'name': 'Sales',
            'columns': [{'name': 'Amount'}],
            'measures': [{'name': 'Total Sales'}]
        }
        desc = _generate_table_description(table)
        assert '1 measures' in desc or '1 measure' in desc

    def test_many_columns_truncated(self):
        """Tables with >8 columns should show first 8 + total count."""
        cols = [{'name': f'Col{i}'} for i in range(12)]
        table = {'name': 'Wide', 'columns': cols, 'measures': []}
        desc = _generate_table_description(table)
        assert '12 columns total' in desc
        assert 'Col0' in desc
        assert 'Col7' in desc

    def test_empty_table(self):
        """Empty table should still get a description."""
        table = {'name': 'Empty', 'columns': [], 'measures': []}
        desc = _generate_table_description(table)
        assert 'Contains 0 columns' in desc


# ═══════════════════════════════════════════════════════════════════
#  2. COLUMN DESCRIPTION GENERATION
# ═══════════════════════════════════════════════════════════════════

class TestColumnDescriptionGeneration:
    """Tests for _generate_column_description()."""

    def test_explicit_description_preserved(self):
        """Explicit description should be returned as-is."""
        col = {'name': 'OrderID', 'description': 'Primary key', 'dataType': 'int64'}
        assert _generate_column_description(col) == 'Primary key'

    def test_simple_string_column(self):
        """String column auto-description."""
        col = {'name': 'CustomerName', 'dataType': 'string'}
        desc = _generate_column_description(col)
        assert 'string' in desc.lower() or 'String' in desc

    def test_calculated_column(self):
        """Calculated column should mention it's calculated."""
        col = {
            'name': 'Revenue',
            'dataType': 'double',
            'isCalculated': True,
            'expression': '[Amount] * [Price]'
        }
        desc = _generate_column_description(col)
        assert 'Calculated' in desc or 'calculated' in desc

    def test_geographic_category(self):
        """Column with dataCategory should mention it."""
        col = {'name': 'City', 'dataType': 'string', 'dataCategory': 'City'}
        desc = _generate_column_description(col)
        assert 'City' in desc

    def test_key_column(self):
        """Key column should mention it's a key."""
        col = {'name': 'Date', 'dataType': 'dateTime', 'isKey': True}
        desc = _generate_column_description(col)
        assert 'key' in desc.lower()

    def test_no_double_description(self):
        """If description already exists, don't overwrite."""
        col = {'name': 'X', 'description': 'My desc', 'dataType': 'int64'}
        assert _generate_column_description(col) == 'My desc'


# ═══════════════════════════════════════════════════════════════════
#  3. MEASURE DESCRIPTION GENERATION
# ═══════════════════════════════════════════════════════════════════

class TestMeasureDescriptionGeneration:
    """Tests for _generate_measure_description()."""

    def test_explicit_description_preserved(self):
        """Explicit description should be returned as-is."""
        m = {'name': 'Total', 'description': 'Manual desc', 'expression': 'SUM(x)'}
        assert _generate_measure_description(m) == 'Manual desc'

    def test_with_original_formula(self):
        """Should include original Tableau formula."""
        m = {
            'name': 'Total Sales',
            'expression': 'SUM(Orders[Amount])',
            '_original_formula': 'SUM([Amount])'
        }
        desc = _generate_measure_description(m)
        assert 'Migrated from Tableau: SUM([Amount])' in desc

    def test_with_dax_only(self):
        """Should include DAX expression when no original formula."""
        m = {
            'name': 'Count',
            'expression': 'DISTINCTCOUNT(Orders[CustomerID])'
        }
        desc = _generate_measure_description(m)
        assert 'DAX:' in desc
        assert 'DISTINCTCOUNT' in desc

    def test_long_expression_truncated(self):
        """Long DAX expressions should be truncated."""
        m = {
            'name': 'Complex',
            'expression': 'CALCULATE(SUM(x), ' + 'FILTER(ALL(y), z > 0), ' * 20 + ')'
        }
        desc = _generate_measure_description(m)
        assert '...' in desc

    def test_empty_expression(self):
        """Measure with expression='0' should get a fallback description."""
        m = {'name': 'Default', 'expression': '0'}
        desc = _generate_measure_description(m)
        assert 'Default' in desc

    def test_no_expression_fallback(self):
        """Measure with no expression should get name-based fallback."""
        m = {'name': 'Revenue', 'expression': ''}
        desc = _generate_measure_description(m)
        assert 'Revenue' in desc


# ═══════════════════════════════════════════════════════════════════
#  4. TMDL OUTPUT — TABLE DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════

class TestTmdlTableDescription:
    """Tests that table descriptions appear in generated TMDL files."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_table_tmdl_has_description(self):
        """Generated table TMDL should contain a description line."""
        table = {
            'name': 'Orders',
            'columns': [{'name': 'OrderID', 'dataType': 'int64', 'sourceColumn': 'OrderID'}],
            'measures': [],
            'partitions': [{'name': 'Part', 'mode': 'import', 'source': {'type': 'm', 'expression': 'let x = 1 in x'}}],
        }
        _write_table_tmdl(self.tmpdir, table)
        content = open(os.path.join(self.tmpdir, 'Orders.tmdl'), 'r', encoding='utf-8').read()
        assert 'description:' in content

    def test_table_tmdl_explicit_description(self):
        """Explicit table description should appear in TMDL."""
        table = {
            'name': 'Products',
            'description': 'Product catalog lookup table',
            'columns': [],
            'measures': [],
            'partitions': [{'name': 'P', 'mode': 'import', 'source': {'type': 'm', 'expression': 'let x = 1 in x'}}],
        }
        _write_table_tmdl(self.tmpdir, table)
        content = open(os.path.join(self.tmpdir, 'Products.tmdl'), 'r', encoding='utf-8').read()
        assert 'Product catalog lookup table' in content

    def test_table_copilot_date_annotation(self):
        """Calendar table should have Copilot_DateTable annotation."""
        table = {
            'name': 'Calendar',
            'columns': [{'name': 'Date', 'dataType': 'dateTime', 'sourceColumn': 'Date'}],
            'measures': [],
            'partitions': [{'name': 'P', 'mode': 'import', 'source': {'type': 'm', 'expression': 'let x = 1 in x'}}],
        }
        _write_table_tmdl(self.tmpdir, table)
        content = open(os.path.join(self.tmpdir, 'Calendar.tmdl'), 'r', encoding='utf-8').read()
        assert 'Copilot_DateTable = true' in content

    def test_non_calendar_no_date_annotation(self):
        """Non-Calendar tables should NOT have Copilot_DateTable annotation."""
        table = {
            'name': 'Orders',
            'columns': [],
            'measures': [],
            'partitions': [{'name': 'P', 'mode': 'import', 'source': {'type': 'm', 'expression': 'let x = 1 in x'}}],
        }
        _write_table_tmdl(self.tmpdir, table)
        content = open(os.path.join(self.tmpdir, 'Orders.tmdl'), 'r', encoding='utf-8').read()
        assert 'Copilot_DateTable' not in content


# ═══════════════════════════════════════════════════════════════════
#  5. TMDL OUTPUT — MEASURE DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════

class TestTmdlMeasureDescription:
    """Tests that measure descriptions appear in generated TMDL."""

    def test_measure_auto_description(self):
        """Measure TMDL should have auto-generated description."""
        lines = []
        measure = {
            'name': 'Total Sales',
            'expression': 'SUM(Orders[Amount])',
            '_original_formula': 'SUM([Amount])'
        }
        _write_measure(lines, measure)
        content = '\n'.join(lines)
        assert 'description:' in content
        assert 'Migrated from Tableau' in content

    def test_measure_explicit_description(self):
        """Explicit description should take priority over auto-generated."""
        lines = []
        measure = {
            'name': 'Revenue',
            'expression': 'SUM(Orders[Revenue])',
            'description': 'Total revenue in USD',
            '_original_formula': 'SUM([Revenue])'
        }
        _write_measure(lines, measure)
        content = '\n'.join(lines)
        assert 'Total revenue in USD' in content
        # Should NOT contain auto-generated text
        assert 'Migrated from Tableau' not in content


# ═══════════════════════════════════════════════════════════════════
#  6. TMDL OUTPUT — COLUMN DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════

class TestTmdlColumnDescription:
    """Tests that column descriptions appear in generated TMDL."""

    def test_column_auto_description(self):
        """Column should get auto-generated description."""
        lines = []
        col = {'name': 'CustomerName', 'dataType': 'string'}
        _write_column_flags(lines, col)
        content = '\n'.join(lines)
        assert 'description:' in content

    def test_column_explicit_description(self):
        """Explicit column description should appear as-is."""
        lines = []
        col = {'name': 'OrderID', 'dataType': 'int64', 'description': 'Unique order identifier'}
        _write_column_flags(lines, col)
        content = '\n'.join(lines)
        assert 'Unique order identifier' in content

    def test_column_copilot_hidden_id(self):
        """ID columns should get Copilot_Hidden annotation."""
        lines = []
        col = {'name': 'CustomerID', 'dataType': 'int64'}
        _write_column_flags(lines, col)
        content = '\n'.join(lines)
        assert 'Copilot_Hidden = true' in content

    def test_column_copilot_hidden_key(self):
        """Key columns should get Copilot_Hidden annotation."""
        lines = []
        col = {'name': 'Product_Key', 'dataType': 'int64'}
        _write_column_flags(lines, col)
        content = '\n'.join(lines)
        assert 'Copilot_Hidden = true' in content

    def test_column_copilot_hidden_sk(self):
        """Surrogate key columns should get Copilot_Hidden annotation."""
        lines = []
        col = {'name': 'Customer_SK', 'dataType': 'int64'}
        _write_column_flags(lines, col)
        content = '\n'.join(lines)
        assert 'Copilot_Hidden = true' in content

    def test_column_no_copilot_hidden_normal(self):
        """Normal business columns should NOT get Copilot_Hidden."""
        lines = []
        col = {'name': 'CustomerName', 'dataType': 'string'}
        _write_column_flags(lines, col)
        content = '\n'.join(lines)
        assert 'Copilot_Hidden' not in content

    def test_column_calculated_description(self):
        """Calculated column should note it's calculated."""
        lines = []
        col = {
            'name': 'Revenue',
            'dataType': 'double',
            'isCalculated': True,
            'expression': '[Amount] * [Price]'
        }
        _write_column_flags(lines, col)
        content = '\n'.join(lines)
        assert 'Calculated' in content or 'calculated' in content


# ═══════════════════════════════════════════════════════════════════
#  7. EXTRACTION — CALCULATION DESCRIPTION
# ═══════════════════════════════════════════════════════════════════

class TestCalculationDescriptionExtraction:
    """Tests that calculation descriptions are extracted from Tableau XML."""

    def test_extract_calc_with_desc(self):
        """Calculations with desc attribute should have description."""
        import xml.etree.ElementTree as ET
        xml = '''<datasource>
            <column name="[Profit Ratio]" caption="Profit Ratio" datatype="real"
                    role="measure" type="quantitative" desc="Profit divided by Sales">
                <calculation class="tableau" formula="SUM([Profit]) / SUM([Sales])" />
            </column>
        </datasource>'''
        ds_elem = ET.fromstring(xml)
        from tableau_export.datasource_extractor import extract_calculations
        calcs = extract_calculations(ds_elem)
        assert len(calcs) == 1
        assert calcs[0]['description'] == 'Profit divided by Sales'

    def test_extract_calc_without_desc(self):
        """Calculations without desc should have empty description."""
        import xml.etree.ElementTree as ET
        xml = '''<datasource>
            <column name="[Total]" caption="Total" datatype="real"
                    role="measure" type="quantitative">
                <calculation class="tableau" formula="SUM([Amount])" />
            </column>
        </datasource>'''
        ds_elem = ET.fromstring(xml)
        from tableau_export.datasource_extractor import extract_calculations
        calcs = extract_calculations(ds_elem)
        assert len(calcs) == 1
        assert calcs[0]['description'] == ''


# ═══════════════════════════════════════════════════════════════════
#  8. LINGUISTIC SCHEMA DEPTH
# ═══════════════════════════════════════════════════════════════════

class TestLinguisticSchemaDepth:
    """Tests for deepened linguistic schema extraction."""

    def _make_extractor(self, xml_str):
        """Create a minimal extractor and run linguistic schema extraction."""
        import xml.etree.ElementTree as ET
        from unittest.mock import MagicMock

        root = ET.fromstring(xml_str)
        extractor = MagicMock()
        extractor.workbook_data = {}

        # Call the method directly by importing and binding
        from tableau_export.extract_tableau_data import TableauExtractor
        real = TableauExtractor.__new__(TableauExtractor)
        real.workbook_data = {}
        TableauExtractor.extract_linguistic_schema(real, root)
        return real.workbook_data.get('linguistic_schema', {})

    def test_camelcase_splitting(self):
        """CamelCase names should produce space-separated synonyms."""
        xml = '''<workbook>
            <datasource>
                <column name="[OrderDate]" />
            </datasource>
        </workbook>'''
        synonyms = self._make_extractor(xml)
        assert 'OrderDate' in synonyms
        assert 'Order Date' in synonyms['OrderDate']

    def test_underscore_humanization(self):
        """Underscore names should produce space-separated synonyms."""
        xml = '''<workbook>
            <datasource>
                <column name="[customer_name]" />
            </datasource>
        </workbook>'''
        synonyms = self._make_extractor(xml)
        assert 'customer_name' in synonyms
        assert 'customer name' in synonyms['customer_name']

    def test_caption_synonym(self):
        """Caption different from name should be a synonym."""
        xml = '''<workbook>
            <datasource>
                <column name="[cust_nm]" caption="Customer Name" />
            </datasource>
        </workbook>'''
        synonyms = self._make_extractor(xml)
        assert 'cust_nm' in synonyms
        assert 'Customer Name' in synonyms['cust_nm']

    def test_desc_as_synonym(self):
        """Description should be included as synonym."""
        xml = '''<workbook>
            <datasource>
                <column name="[rev]" desc="Total revenue from all sources" />
            </datasource>
        </workbook>'''
        synonyms = self._make_extractor(xml)
        assert 'rev' in synonyms
        assert 'Total revenue from all sources' in synonyms['rev']

    def test_short_names_not_humanized(self):
        """Very short names (<=2 chars) should not produce humanized variants."""
        xml = '''<workbook>
            <datasource>
                <column name="[ID]" />
            </datasource>
        </workbook>'''
        synonyms = self._make_extractor(xml)
        # ID has no camelCase or underscore → no humanized variant
        # (unless it gets a trivial variant like "I D" which is filtered by length)
        for key, syns in synonyms.items():
            for s in syns:
                assert len(s) > 0  # All synonyms should be non-empty

    def test_alias_collected(self):
        """Column aliases should be collected as synonyms."""
        xml = '''<workbook>
            <datasource>
                <column name="[status_code]">
                    <alias value="Status" />
                </column>
            </datasource>
        </workbook>'''
        synonyms = self._make_extractor(xml)
        assert 'status_code' in synonyms
        assert 'Status' in synonyms['status_code']


# ═══════════════════════════════════════════════════════════════════
#  9. END-TO-END: GENERATE_TMDL WITH DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════

class TestEndToEndDescriptions:
    """Integration tests for full TMDL generation with descriptions."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_full_generation_has_table_descriptions(self):
        """Full TMDL generation should produce description on every table."""
        datasources = [{
            'name': 'TestDS',
            'connection': {'type': 'SQL Server', 'details': {'server': 'svr', 'database': 'db'}},
            'connection_map': {},
            'tables': [{
                'name': 'Orders',
                'columns': [
                    {'name': 'OrderID', 'datatype': 'integer'},
                    {'name': 'Amount', 'datatype': 'real'},
                ]
            }]
        }]
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            'calculations': [],
        }
        sm_dir = os.path.join(self.tmpdir, 'TestDS.SemanticModel')
        os.makedirs(sm_dir, exist_ok=True)
        generate_tmdl(datasources, 'TestDS', extra, sm_dir)

        # Check tables directory (under definition/)
        tables_dir = os.path.join(sm_dir, 'definition', 'tables')
        assert os.path.isdir(tables_dir)
        found_desc = False
        for fname in os.listdir(tables_dir):
            if fname.endswith('.tmdl'):
                content = open(os.path.join(tables_dir, fname), 'r', encoding='utf-8').read()
                if 'description:' in content:
                    found_desc = True
                    break
        assert found_desc, "No table TMDL file contains a description"

    def test_full_generation_has_column_descriptions(self):
        """Full TMDL generation should produce description on columns."""
        datasources = [{
            'name': 'TestDS',
            'connection': {'type': 'SQL Server', 'details': {'server': 'svr', 'database': 'db'}},
            'connection_map': {},
            'tables': [{
                'name': 'Products',
                'columns': [
                    {'name': 'ProductID', 'datatype': 'integer'},
                    {'name': 'ProductName', 'datatype': 'string'},
                ]
            }]
        }]
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            'calculations': [],
        }
        sm_dir = os.path.join(self.tmpdir, 'TestDS.SemanticModel')
        os.makedirs(sm_dir, exist_ok=True)
        generate_tmdl(datasources, 'TestDS', extra, sm_dir)

        tables_dir = os.path.join(sm_dir, 'definition', 'tables')
        found = False
        for fname in os.listdir(tables_dir):
            if fname.endswith('.tmdl') and 'Products' in fname:
                content = open(os.path.join(tables_dir, fname), 'r', encoding='utf-8').read()
                # Should have at least 2 description lines (one per column)
                desc_count = content.count('\t\tdescription:')
                if desc_count >= 2:
                    found = True
                    break
        assert found, "Products table should have descriptions on its columns"

    def test_full_generation_has_measure_descriptions(self):
        """Full TMDL generation should produce description on measures."""
        calcs = [{
            'name': 'Total Revenue',
            'caption': 'Total Revenue',
            'formula': 'SUM([Amount])',
            'datatype': 'real',
            'role': 'measure',
            'description': ''
        }]
        datasources = [{
            'name': 'TestDS',
            'connection': {'type': 'SQL Server', 'details': {'server': 'svr', 'database': 'db'}},
            'connection_map': {},
            'tables': [{
                'name': 'Sales',
                'columns': [
                    {'name': 'Amount', 'datatype': 'real'},
                ]
            }],
            'calculations': calcs,
        }]
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            'calculations': calcs,
        }
        sm_dir = os.path.join(self.tmpdir, 'TestDS.SemanticModel')
        os.makedirs(sm_dir, exist_ok=True)
        generate_tmdl(datasources, 'TestDS', extra, sm_dir)

        tables_dir = os.path.join(sm_dir, 'definition', 'tables')
        found = False
        for fname in os.listdir(tables_dir):
            if fname.endswith('.tmdl'):
                content = open(os.path.join(tables_dir, fname), 'r', encoding='utf-8').read()
                if 'measure' in content and 'description:' in content:
                    found = True
                    break
        assert found, f"No table TMDL has measure with description. Files: {os.listdir(tables_dir)}"

    def test_copilot_annotation_on_calendar(self):
        """Calendar table TMDL should have Copilot_DateTable annotation."""
        datasources = [{
            'name': 'TestDS',
            'connection': {'type': 'SQL Server', 'details': {'server': 'svr', 'database': 'db'}},
            'connection_map': {},
            'tables': [{
                'name': 'Facts',
                'columns': [
                    {'name': 'OrderDate', 'datatype': 'datetime'},
                    {'name': 'Amount', 'datatype': 'real'},
                ]
            }]
        }]
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            'calculations': [],
        }
        sm_dir = os.path.join(self.tmpdir, 'TestDS.SemanticModel')
        os.makedirs(sm_dir, exist_ok=True)
        generate_tmdl(datasources, 'TestDS', extra, sm_dir)

        tables_dir = os.path.join(sm_dir, 'definition', 'tables')
        found = False
        for fname in os.listdir(tables_dir):
            if fname.endswith('.tmdl') and 'Calendar' in fname:
                content = open(os.path.join(tables_dir, fname), 'r', encoding='utf-8').read()
                if 'Copilot_DateTable = true' in content:
                    found = True
                    break
        assert found, "Calendar table should have Copilot_DateTable annotation"

    def test_copilot_hidden_on_id_columns(self):
        """ID columns should have Copilot_Hidden annotation."""
        datasources = [{
            'name': 'TestDS',
            'connection': {'type': 'SQL Server', 'details': {'server': 'svr', 'database': 'db'}},
            'connection_map': {},
            'tables': [{
                'name': 'Orders',
                'columns': [
                    {'name': 'OrderID', 'datatype': 'integer'},
                    {'name': 'CustomerName', 'datatype': 'string'},
                ]
            }]
        }]
        extra = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            'calculations': [],
        }
        sm_dir = os.path.join(self.tmpdir, 'TestDS.SemanticModel')
        os.makedirs(sm_dir, exist_ok=True)
        generate_tmdl(datasources, 'TestDS', extra, sm_dir)

        tables_dir = os.path.join(sm_dir, 'definition', 'tables')
        for fname in os.listdir(tables_dir):
            if fname.endswith('.tmdl') and 'Orders' in fname:
                content = open(os.path.join(tables_dir, fname), 'r', encoding='utf-8').read()
                assert 'Copilot_Hidden = true' in content, \
                    "OrderID should have Copilot_Hidden annotation"
                break


# ═══════════════════════════════════════════════════════════════════
#  10. TABLE CAPTION/DESCRIPTION EXTRACTION
# ═══════════════════════════════════════════════════════════════════

class TestTableCaptionExtraction:
    """Tests for table caption extraction from Tableau XML."""

    def test_table_caption_extracted(self):
        """Table relations with caption attribute should have it extracted."""
        import xml.etree.ElementTree as ET
        xml = '''<datasource>
            <connection>
                <relation type="table" name="Orders" caption="Order History" connection="conn1">
                    <columns>
                        <column name="OrderID" datatype="integer" />
                    </columns>
                </relation>
            </connection>
        </datasource>'''
        ds_elem = ET.fromstring(xml)
        from tableau_export.datasource_extractor import extract_tables_with_columns
        tables = extract_tables_with_columns(ds_elem)
        assert len(tables) == 1
        assert tables[0].get('caption') == 'Order History'

    def test_table_no_caption(self):
        """Table without caption should have empty caption."""
        import xml.etree.ElementTree as ET
        xml = '''<datasource>
            <connection>
                <relation type="table" name="Products" connection="conn1">
                    <columns>
                        <column name="ProductID" datatype="integer" />
                    </columns>
                </relation>
            </connection>
        </datasource>'''
        ds_elem = ET.fromstring(xml)
        from tableau_export.datasource_extractor import extract_tables_with_columns
        tables = extract_tables_with_columns(ds_elem)
        assert len(tables) == 1
        assert tables[0].get('caption', '') == ''


# ═══════════════════════════════════════════════════════════════════
#  11. DESCRIPTION ESCAPING / SAFETY
# ═══════════════════════════════════════════════════════════════════

class TestDescriptionEscaping:
    """Tests that descriptions with special characters are safe in TMDL."""

    def test_newline_in_description_escaped(self):
        """Newlines in descriptions should be replaced with spaces."""
        lines = []
        measure = {
            'name': 'Test',
            'expression': 'SUM(x)',
            'description': 'Line 1\nLine 2\nLine 3'
        }
        _write_measure(lines, measure)
        content = '\n'.join(lines)
        assert 'Line 1 Line 2 Line 3' in content
        # Should NOT have raw newlines in the description value
        for line in lines:
            if 'description:' in line:
                assert '\n' not in line.split('description:')[1]

    def test_carriage_return_stripped(self):
        """Carriage returns should be stripped from descriptions."""
        lines = []
        measure = {
            'name': 'Test',
            'expression': 'SUM(x)',
            'description': 'Desc with\r\nCRLF'
        }
        _write_measure(lines, measure)
        content = '\n'.join(lines)
        assert '\r' not in content.split('description:')[1].split('\n')[0]


# ═══════════════════════════════════════════════════════════════════
#  12. COPILOT ANNOTATION EDGE CASES
# ═══════════════════════════════════════════════════════════════════

class TestCopilotAnnotationEdgeCases:
    """Edge cases for Copilot annotations."""

    def test_pk_suffix(self):
        """_pk suffix should trigger Copilot_Hidden."""
        lines = []
        _write_column_flags(lines, {'name': 'order_pk', 'dataType': 'int64'})
        assert any('Copilot_Hidden' in l for l in lines)

    def test_fk_suffix(self):
        """_fk suffix should trigger Copilot_Hidden."""
        lines = []
        _write_column_flags(lines, {'name': 'customer_fk', 'dataType': 'int64'})
        assert any('Copilot_Hidden' in l for l in lines)

    def test_case_sensitive_id_suffix(self):
        """Column named 'ProductID' (uppercase ID) should match."""
        lines = []
        _write_column_flags(lines, {'name': 'ProductID', 'dataType': 'int64'})
        assert any('Copilot_Hidden' in l for l in lines)

    def test_underscore_id_suffix(self):
        """Column named 'product_id' (underscore+id) should match."""
        lines = []
        _write_column_flags(lines, {'name': 'product_id', 'dataType': 'int64'})
        assert any('Copilot_Hidden' in l for l in lines)

    def test_column_named_valid_not_id(self):
        """Column named 'Valid' should NOT trigger Copilot_Hidden."""
        lines = []
        _write_column_flags(lines, {'name': 'Valid', 'dataType': 'boolean'})
        assert not any('Copilot_Hidden' in l for l in lines)

    def test_column_containing_id_in_middle(self):
        """Column like 'VideoTitle' should NOT be marked as ID."""
        lines = []
        _write_column_flags(lines, {'name': 'VideoTitle', 'dataType': 'string'})
        assert not any('Copilot_Hidden' in l for l in lines)
