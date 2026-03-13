"""
Tests for datasource_extractor.py — Sprint 27 coverage push.

Targets uncovered lines:
  - _detect_csv_delimiter()               lines 22-41
  - _read_csv_header_from_twbx()          lines 44-71
  - _parse_connection_class() textscan    lines 191-197
  - _parse_connection_class() fallback    line 212
  - _build_connection_map()               lines 246-296
  - extract_tables_with_columns() phases  lines 330-474
  - extract_relationships()               lines 550-643+
"""

import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))

from datasource_extractor import (
    _detect_csv_delimiter,
    _read_csv_header_from_twbx,
    _parse_connection_class,
    _build_connection_map,
    extract_connection_details,
    extract_datasource,
    extract_tables_with_columns,
    extract_column_metadata,
    extract_calculations,
    extract_relationships,
)


# ═══════════════════════════════════════════════════════════════════
# _detect_csv_delimiter
# ═══════════════════════════════════════════════════════════════════

class TestDetectCsvDelimiter(unittest.TestCase):
    """Test CSV delimiter auto-detection."""

    def test_comma_delimiter(self):
        self.assertEqual(_detect_csv_delimiter('Name,Age,City'), ',')

    def test_semicolon_delimiter(self):
        self.assertEqual(_detect_csv_delimiter('Name;Age;City'), ';')

    def test_tab_delimiter(self):
        self.assertEqual(_detect_csv_delimiter('Name\tAge\tCity'), '\t')

    def test_pipe_delimiter(self):
        self.assertEqual(_detect_csv_delimiter('Name|Age|City'), '|')

    def test_empty_returns_comma(self):
        self.assertEqual(_detect_csv_delimiter(''), ',')

    def test_none_returns_comma(self):
        self.assertEqual(_detect_csv_delimiter(None), ',')

    def test_no_delimiter_returns_comma(self):
        self.assertEqual(_detect_csv_delimiter('SingleColumn'), ',')

    def test_mixed_prefers_sniffer_result(self):
        # csv.Sniffer may pick comma over semicolons; just verify we get a result
        result = _detect_csv_delimiter('A;B;C;D,E')
        self.assertIn(result, (',', ';'))


# ═══════════════════════════════════════════════════════════════════
# _read_csv_header_from_twbx
# ═══════════════════════════════════════════════════════════════════

class TestReadCsvHeaderFromTwbx(unittest.TestCase):
    """Test reading CSV header from inside .twbx archives."""

    def test_reads_csv_from_twbx(self):
        with tempfile.TemporaryDirectory() as td:
            twbx = os.path.join(td, 'test.twbx')
            with zipfile.ZipFile(twbx, 'w') as z:
                z.writestr('Data/sales.csv', 'Name,Revenue,Region\nrow1,100,US')
            result = _read_csv_header_from_twbx(twbx, 'Data', 'sales.csv')
            self.assertEqual(result, 'Name,Revenue,Region')

    def test_reads_csv_partial_path_match(self):
        with tempfile.TemporaryDirectory() as td:
            twbx = os.path.join(td, 'test.twbx')
            with zipfile.ZipFile(twbx, 'w') as z:
                z.writestr('some/path/data.csv', 'A;B;C\n1;2;3')
            result = _read_csv_header_from_twbx(twbx, '', 'data.csv')
            self.assertEqual(result, 'A;B;C')

    def test_returns_none_for_nonexistent_file(self):
        result = _read_csv_header_from_twbx('/nonexistent/path.twbx', '', 'x.csv')
        self.assertIsNone(result)

    def test_returns_none_for_non_twbx(self):
        with tempfile.NamedTemporaryFile(suffix='.twb', delete=False) as f:
            f.write(b'<workbook/>')
            path = f.name
        try:
            result = _read_csv_header_from_twbx(path, '', 'x.csv')
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_returns_none_for_none_path(self):
        result = _read_csv_header_from_twbx(None, '', 'x.csv')
        self.assertIsNone(result)

    def test_returns_none_if_csv_not_in_archive(self):
        with tempfile.TemporaryDirectory() as td:
            twbx = os.path.join(td, 'test.twbx')
            with zipfile.ZipFile(twbx, 'w') as z:
                z.writestr('other.twb', '<workbook/>')
            result = _read_csv_header_from_twbx(twbx, '', 'missing.csv')
            self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# _parse_connection_class
# ═══════════════════════════════════════════════════════════════════

class TestParseConnectionClass(unittest.TestCase):
    """Test connection class parsing for various connector types."""

    def test_excel_connection(self):
        xml = '<connection class="excel-direct" filename="sales.xlsx" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'Excel')
        self.assertEqual(result['details']['filename'], 'sales.xlsx')

    def test_excel_with_named_conn(self):
        xml = '<connection class="excel-direct" filename="sales.xlsx" />'
        named = ET.fromstring('<named-connection caption="Sales File" />')
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem, named_conn=named)
        self.assertEqual(result['details']['caption'], 'Sales File')

    def test_textscan_connection(self):
        xml = '<connection class="textscan" filename="data.csv" directory="/data" separator=";" charset="utf-8" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'CSV')
        self.assertEqual(result['details']['delimiter'], ';')
        self.assertEqual(result['details']['filename'], 'data.csv')

    def test_textscan_auto_detect_delimiter(self):
        """When no separator attr, delimiter is auto-detected from twbx."""
        xml = '<connection class="textscan" filename="data.csv" directory="Data" />'
        elem = ET.fromstring(xml)
        with tempfile.TemporaryDirectory() as td:
            twbx = os.path.join(td, 'test.twbx')
            with zipfile.ZipFile(twbx, 'w') as z:
                z.writestr('Data/data.csv', 'A\tB\tC\n1\t2\t3')
            result = _parse_connection_class(elem, twbx_path=twbx)
            self.assertEqual(result['type'], 'CSV')
            self.assertEqual(result['details']['delimiter'], '\t')

    def test_textscan_no_twbx_defaults_comma(self):
        xml = '<connection class="textscan" filename="data.csv" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['details']['delimiter'], ',')

    def test_sqlserver_connection(self):
        xml = '<connection class="sqlserver" server="db.co" dbname="sales" authentication="sspi" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'SQL Server')
        self.assertEqual(result['details']['server'], 'db.co')
        self.assertEqual(result['details']['database'], 'sales')

    def test_postgres_connection(self):
        xml = '<connection class="postgres" server="pg.co" port="5433" dbname="analytics" username="admin" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'PostgreSQL')
        self.assertEqual(result['details']['port'], '5433')

    def test_bigquery_connection(self):
        xml = '<connection class="bigquery" project="my-proj" dataset="ds1" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'BigQuery')
        self.assertEqual(result['details']['project'], 'my-proj')

    def test_oracle_connection(self):
        xml = '<connection class="oracle" server="ora.co" service="ORCL" port="1521" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'Oracle')
        self.assertEqual(result['details']['service'], 'ORCL')

    def test_mysql_connection(self):
        xml = '<connection class="mysql" server="mysql.co" port="3307" dbname="app" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'MySQL')
        self.assertEqual(result['details']['port'], '3307')

    def test_snowflake_connection(self):
        xml = '<connection class="snowflake" server="sf.co" dbname="db" schema="pub" warehouse="wh" role="analyst" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'Snowflake')
        self.assertEqual(result['details']['warehouse'], 'wh')

    def test_sapbw_connection(self):
        xml = '<connection class="sapbw" server="sap.co" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'SAP BW')

    def test_unknown_connector_fallback(self):
        xml = '<connection class="teradata" server="td.co" custom="val" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'TERADATA')
        self.assertEqual(result['details']['server'], 'td.co')
        self.assertEqual(result['details']['custom'], 'val')

    def test_geojson_connection(self):
        xml = '<connection class="ogrdirect" filename="map.geojson" directory="/maps" />'
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'GeoJSON')

    def test_sqlproxy_connection(self):
        xml = ('<connection class="sqlproxy" channel="https" server="si-mytableau.edf.fr" '
               'port="443" dbname="E_Formation" server-ds-friendly-name="E_Formation" />')
        elem = ET.fromstring(xml)
        result = _parse_connection_class(elem)
        self.assertEqual(result['type'], 'Tableau Server')
        self.assertEqual(result['details']['server'], 'si-mytableau.edf.fr')
        self.assertEqual(result['details']['port'], '443')
        self.assertEqual(result['details']['dbname'], 'E_Formation')
        self.assertEqual(result['details']['channel'], 'https')
        self.assertEqual(result['details']['server_ds_name'], 'E_Formation')


# ═══════════════════════════════════════════════════════════════════
# _build_connection_map
# ═══════════════════════════════════════════════════════════════════

class TestBuildConnectionMap(unittest.TestCase):
    """Test connection map construction from datasource XML."""

    def test_federated_with_named_connections(self):
        xml = '''
        <datasource name="ds1">
          <connection class="federated">
            <named-connections>
              <named-connection name="conn1" caption="Sales DB">
                <connection class="sqlserver" server="db.co" dbname="sales" />
              </named-connection>
              <named-connection name="conn2">
                <connection class="postgres" server="pg.co" dbname="analytics" />
              </named-connection>
            </named-connections>
          </connection>
        </datasource>
        '''
        ds_elem = ET.fromstring(xml)
        conn_map = _build_connection_map(ds_elem)
        self.assertIn('conn1', conn_map)
        self.assertIn('conn2', conn_map)
        self.assertEqual(conn_map['conn1']['type'], 'SQL Server')
        self.assertEqual(conn_map['conn2']['type'], 'PostgreSQL')

    def test_no_connection_returns_empty(self):
        xml = '<datasource name="ds1" />'
        ds_elem = ET.fromstring(xml)
        conn_map = _build_connection_map(ds_elem)
        self.assertEqual(conn_map, {})

    def test_non_federated_connection(self):
        xml = '''
        <datasource name="ds1">
          <connection class="sqlserver" server="db.co" dbname="sales">
            <named-connection name="conn1">
              <connection class="sqlserver" server="db.co" dbname="sales" />
            </named-connection>
          </connection>
        </datasource>
        '''
        ds_elem = ET.fromstring(xml)
        conn_map = _build_connection_map(ds_elem)
        self.assertIn('conn1', conn_map)


# ═══════════════════════════════════════════════════════════════════
# extract_tables_with_columns — phase 2 (ds-level cols), phase 3 (metadata)
# ═══════════════════════════════════════════════════════════════════

class TestExtractTablesWithColumns(unittest.TestCase):
    """Test table extraction with column population fallbacks."""

    def test_basic_table_with_columns(self):
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="table" name="Orders" connection="conn1">
              <columns>
                <column name="OrderID" datatype="integer" ordinal="0" />
                <column name="Amount" datatype="real" ordinal="1" />
              </columns>
            </relation>
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        tables = extract_tables_with_columns(ds)
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]['name'], 'Orders')
        self.assertEqual(len(tables[0]['columns']), 2)

    def test_phase2_cols_map_fallback(self):
        """Tables with no nested columns use <cols><map> + <column> elements."""
        xml = '''
        <datasource>
          <connection class="federated">
            <cols>
              <map key="[OrderID]" value="[Orders].[OrderID]" />
              <map key="[Amount]" value="[Orders].[Amount]" />
            </cols>
            <relation type="table" name="Orders" connection="conn1" />
          </connection>
          <column name="[OrderID]" datatype="integer" role="dimension" />
          <column name="[Amount]" datatype="real" role="measure" />
        </datasource>
        '''
        ds = ET.fromstring(xml)
        tables = extract_tables_with_columns(ds)
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0]['columns']), 2)
        col_names = {c['name'] for c in tables[0]['columns']}
        self.assertIn('OrderID', col_names)
        self.assertIn('Amount', col_names)

    def test_phase2_skips_calculations(self):
        """Columns with <calculation> children should be skipped in fallback."""
        xml = '''
        <datasource>
          <connection class="federated">
            <cols>
              <map key="[OrderID]" value="[Orders].[OrderID]" />
            </cols>
            <relation type="table" name="Orders" connection="conn1" />
          </connection>
          <column name="[OrderID]" datatype="integer" />
          <column name="[Profit]" datatype="real">
            <calculation class="tableau" formula="[Revenue] - [Cost]" />
          </column>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        tables = extract_tables_with_columns(ds)
        self.assertEqual(len(tables), 1)
        # Only OrderID should appear (Profit is a calculation)
        col_names = {c['name'] for c in tables[0]['columns']}
        self.assertIn('OrderID', col_names)
        self.assertNotIn('Profit', col_names)

    def test_phase3_metadata_records_fallback(self):
        """Tables with no columns fall back to <metadata-record> elements."""
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="table" name="Customers" connection="conn1" />
            <metadata-records>
              <metadata-record class="column">
                <remote-name>CustID</remote-name>
                <local-name>[CustID]</local-name>
                <parent-name>[Customers]</parent-name>
                <local-type>integer</local-type>
                <ordinal>0</ordinal>
                <contains-null>false</contains-null>
              </metadata-record>
              <metadata-record class="column">
                <remote-name>Name</remote-name>
                <local-name>[Name]</local-name>
                <parent-name>[Customers]</parent-name>
                <local-type>string</local-type>
                <ordinal>1</ordinal>
              </metadata-record>
            </metadata-records>
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        tables = extract_tables_with_columns(ds)
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0]['columns']), 2)
        self.assertEqual(tables[0]['columns'][0]['name'], 'CustID')
        self.assertFalse(tables[0]['columns'][0]['nullable'])

    def test_phase4_last_resort_ds_columns(self):
        """Tables with no columns after phase 3 use ds-level <column> elements."""
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="table" name="Products" connection="conn1" />
          </connection>
          <column name="[ProdID]" datatype="integer" />
          <column name="[ProdName]" datatype="string" />
        </datasource>
        '''
        ds = ET.fromstring(xml)
        tables = extract_tables_with_columns(ds)
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0]['columns']), 2)

    def test_deduplication_keeps_most_columns(self):
        """Duplicate table names keep the version with more columns."""
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="table" name="Orders" connection="conn1">
              <columns>
                <column name="ID" datatype="integer" />
              </columns>
            </relation>
            <relation type="table" name="Orders" connection="conn1">
              <columns>
                <column name="ID" datatype="integer" />
                <column name="Amount" datatype="real" />
              </columns>
            </relation>
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        tables = extract_tables_with_columns(ds)
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0]['columns']), 2)

    def test_skips_join_relations(self):
        """Only type='table' relations are extracted, not joins."""
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="join" join="inner">
              <relation type="table" name="Orders" connection="conn1">
                <columns><column name="ID" datatype="integer" /></columns>
              </relation>
              <relation type="table" name="Products" connection="conn1">
                <columns><column name="ProdID" datatype="integer" /></columns>
              </relation>
            </relation>
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        tables = extract_tables_with_columns(ds)
        self.assertEqual(len(tables), 2)
        names = {t['name'] for t in tables}
        self.assertEqual(names, {'Orders', 'Products'})

    def test_role_override_from_ds_columns(self):
        """Phase 2.5: Role overrides from datasource-level <column> elements."""
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="table" name="Orders" connection="conn1">
              <columns>
                <column name="RowID" datatype="integer" ordinal="0" />
              </columns>
            </relation>
          </connection>
          <column name="[RowID]" role="dimension" />
        </datasource>
        '''
        ds = ET.fromstring(xml)
        tables = extract_tables_with_columns(ds)
        self.assertEqual(tables[0]['columns'][0]['role'], 'dimension')


# ═══════════════════════════════════════════════════════════════════
# extract_relationships
# ═══════════════════════════════════════════════════════════════════

class TestExtractRelationships(unittest.TestCase):
    """Test relationship extraction from Tableau join XML."""

    def test_simple_join(self):
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="join" join="inner">
              <relation type="table" name="Orders" />
              <relation type="table" name="Products" />
              <clause>
                <expression op="=">
                  <expression op="[Orders].[ProductID]" />
                  <expression op="[Products].[ProductID]" />
                </expression>
              </clause>
            </relation>
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        rels = extract_relationships(ds)
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]['type'], 'inner')
        self.assertEqual(rels[0]['left']['table'], 'Orders')
        self.assertEqual(rels[0]['left']['column'], 'ProductID')
        self.assertEqual(rels[0]['right']['table'], 'Products')
        self.assertEqual(rels[0]['right']['column'], 'ProductID')

    def test_bare_column_format(self):
        """Bare [Column] format infers table from child relations."""
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="join" join="left">
              <relation type="table" name="Orders" />
              <relation type="table" name="Customers" />
              <clause>
                <expression op="=">
                  <expression op="[CustID]" />
                  <expression op="[CustID]" />
                </expression>
              </clause>
            </relation>
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        rels = extract_relationships(ds)
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]['left']['table'], 'Orders')
        self.assertEqual(rels[0]['right']['table'], 'Customers')

    def test_multiple_clauses(self):
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="join" join="inner">
              <relation type="table" name="A" />
              <relation type="table" name="B" />
              <clause>
                <expression op="=">
                  <expression op="[A].[ID]" />
                  <expression op="[B].[ID]" />
                </expression>
              </clause>
              <clause>
                <expression op="=">
                  <expression op="[A].[Date]" />
                  <expression op="[B].[Date]" />
                </expression>
              </clause>
            </relation>
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        rels = extract_relationships(ds)
        self.assertEqual(len(rels), 2)

    def test_deduplication(self):
        """Same relationship should not appear twice."""
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="join" join="inner">
              <relation type="table" name="A" />
              <relation type="table" name="B" />
              <clause>
                <expression op="=">
                  <expression op="[A].[ID]" />
                  <expression op="[B].[ID]" />
                </expression>
              </clause>
            </relation>
            <relation type="join" join="inner">
              <relation type="table" name="A" />
              <relation type="table" name="B" />
              <clause>
                <expression op="=">
                  <expression op="[A].[ID]" />
                  <expression op="[B].[ID]" />
                </expression>
              </clause>
            </relation>
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        rels = extract_relationships(ds)
        self.assertEqual(len(rels), 1)

    def test_no_joins_returns_empty(self):
        xml = '''
        <datasource>
          <connection class="federated">
            <relation type="table" name="Orders" />
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        rels = extract_relationships(ds)
        self.assertEqual(rels, [])

    def test_object_graph_relationships(self):
        """Modern Tableau object-graph relationship format."""
        xml = '''
        <datasource>
          <object-graph>
            <relationship expression="[Orders].[CustID] = [Customers].[CustID]" type="Left" />
          </object-graph>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        rels = extract_relationships(ds)
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]['left']['table'], 'Orders')
        self.assertEqual(rels[0]['right']['table'], 'Customers')


# ═══════════════════════════════════════════════════════════════════
# extract_datasource (integration)
# ═══════════════════════════════════════════════════════════════════

class TestExtractDatasource(unittest.TestCase):
    """Integration test for the full extract_datasource function."""

    def test_full_extraction(self):
        xml = '''
        <datasource name="Sales Data" caption="Sales Data">
          <connection class="federated">
            <named-connections>
              <named-connection name="conn1">
                <connection class="sqlserver" server="db.co" dbname="sales" />
              </named-connection>
            </named-connections>
            <relation type="table" name="Orders" connection="conn1">
              <columns>
                <column name="ID" datatype="integer" ordinal="0" />
                <column name="Revenue" datatype="real" ordinal="1" />
              </columns>
            </relation>
          </connection>
          <column name="[Profit]" datatype="real" role="measure" caption="Profit">
            <calculation class="tableau" formula="[Revenue] - [Cost]" />
          </column>
        </datasource>
        '''
        ds_elem = ET.fromstring(xml)
        ds = extract_datasource(ds_elem)
        self.assertEqual(ds['name'], 'Sales Data')
        self.assertEqual(ds['caption'], 'Sales Data')
        self.assertEqual(ds['connection']['type'], 'SQL Server')
        self.assertGreater(len(ds['tables']), 0)
        self.assertGreater(len(ds['calculations']), 0)
        self.assertIn('connection_map', ds)


# ═══════════════════════════════════════════════════════════════════
# extract_calculations
# ═══════════════════════════════════════════════════════════════════

class TestExtractCalculations(unittest.TestCase):
    """Test calculation extraction from datasource XML."""

    def test_basic_calculation(self):
        xml = '''
        <datasource>
          <column name="[Profit]" datatype="real" role="measure" caption="Profit">
            <calculation class="tableau" formula="[Revenue] - [Cost]" />
          </column>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        calcs = extract_calculations(ds)
        self.assertEqual(len(calcs), 1)
        self.assertEqual(calcs[0]['caption'], 'Profit')
        self.assertEqual(calcs[0]['formula'], '[Revenue] - [Cost]')

    def test_skips_empty_formula(self):
        xml = '''
        <datasource>
          <column name="[Empty]" datatype="real">
            <calculation class="tableau" formula="   " />
          </column>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        calcs = extract_calculations(ds)
        self.assertEqual(len(calcs), 0)

    def test_skips_categorical_bin(self):
        xml = '''
        <datasource>
          <column name="[Group]" datatype="string">
            <calculation class="categorical-bin" formula="" />
          </column>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        calcs = extract_calculations(ds)
        self.assertEqual(len(calcs), 0)

    def test_table_calc_addressing(self):
        xml = '''
        <datasource>
          <column name="[RunSum]" datatype="real" role="measure" caption="RunSum">
            <calculation class="tableau" formula="RUNNING_SUM(SUM([Revenue]))">
              <table-calc type="Cumulative" ordering-type="Rows">
                <addressing-field name="[Date]" />
                <partitioning-field name="[Region]" />
              </table-calc>
            </calculation>
          </column>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        calcs = extract_calculations(ds)
        self.assertEqual(len(calcs), 1)
        self.assertIn('table_calc_addressing', calcs[0])
        self.assertEqual(calcs[0]['table_calc_addressing'], ['Date'])
        self.assertEqual(calcs[0]['table_calc_partitioning'], ['Region'])
        self.assertEqual(calcs[0]['table_calc_type'], 'Cumulative')


# ═══════════════════════════════════════════════════════════════════
# extract_column_metadata
# ═══════════════════════════════════════════════════════════════════

class TestExtractColumnMetadata(unittest.TestCase):
    """Test column metadata extraction."""

    def test_column_with_all_attributes(self):
        xml = '''
        <datasource>
          <column name="[City]" caption="City" datatype="string"
                  role="dimension" type="nominal" hidden="true"
                  semantic-role="[Geographical].[City]"
                  default-format="#,##0" />
        </datasource>
        '''
        ds = ET.fromstring(xml)
        cols = extract_column_metadata(ds)
        self.assertEqual(len(cols), 1)
        c = cols[0]
        self.assertEqual(c['name'], '[City]')
        self.assertEqual(c['caption'], 'City')
        self.assertTrue(c['hidden'])
        self.assertEqual(c['semantic_role'], '[Geographical].[City]')

    def test_column_with_calculation(self):
        xml = '''
        <datasource>
          <column name="[Profit]" datatype="real">
            <calculation class="tableau" formula="[Rev] - [Cost]" />
          </column>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        cols = extract_column_metadata(ds)
        self.assertEqual(len(cols), 1)
        self.assertIsNotNone(cols[0]['calculation'])
        self.assertEqual(cols[0]['calculation']['formula'], '[Rev] - [Cost]')


# ═══════════════════════════════════════════════════════════════════
# extract_connection_details
# ═══════════════════════════════════════════════════════════════════

class TestExtractConnectionDetails(unittest.TestCase):
    """Test connection details extraction."""

    def test_no_connection_returns_unknown(self):
        xml = '<datasource name="ds1" />'
        ds = ET.fromstring(xml)
        result = extract_connection_details(ds)
        self.assertEqual(result['type'], 'Unknown')

    def test_federated_with_named_conn(self):
        xml = '''
        <datasource>
          <connection class="federated">
            <named-connection name="conn1">
              <connection class="postgres" server="pg.co" dbname="db" />
            </named-connection>
          </connection>
        </datasource>
        '''
        ds = ET.fromstring(xml)
        result = extract_connection_details(ds)
        self.assertEqual(result['type'], 'PostgreSQL')


if __name__ == '__main__':
    unittest.main()
