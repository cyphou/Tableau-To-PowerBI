"""
Tests for powerbi_import.m_query_generator — sample data M query generation.
"""

import unittest

from powerbi_import.m_query_generator import (
    generate_m_query_from_datasource,
    generate_sql_query,
    generate_excel_query,
    generate_csv_query,
    generate_web_query,
    generate_json_query,
    generate_sample_data_query,
    get_column_type_mapping,
)


class TestGenerateSqlQuery(unittest.TestCase):
    """Tests for SQL connector M query generation."""

    def test_sql_query_contains_server_and_database(self):
        conn = {
            'connectionDetails': {'server': 'srv.db.windows.net', 'database': 'SalesDB'},
        }
        result = generate_sql_query(conn, 'Orders')
        self.assertIn('srv.db.windows.net', result)
        self.assertIn('SalesDB', result)
        self.assertIn('Sql.Database', result)

    def test_sql_query_uses_table_name(self):
        conn = {'connectionDetails': {'server': 's', 'database': 'd'}}
        result = generate_sql_query(conn, 'MyTable')
        self.assertIn('MyTable', result)

    def test_sql_query_defaults_when_missing_details(self):
        conn = {}
        result = generate_sql_query(conn, 'T')
        self.assertIn('YourServer', result)
        self.assertIn('YourDatabase', result)

    def test_sql_query_is_valid_let_in(self):
        conn = {'connectionDetails': {'server': 's', 'database': 'd'}}
        result = generate_sql_query(conn, 'T')
        self.assertTrue(result.strip().startswith('let'))
        self.assertTrue(result.strip().endswith('Result'))


class TestGenerateExcelQuery(unittest.TestCase):
    """Tests for Excel connector M query generation."""

    def test_excel_query_contains_workbook_call(self):
        conn = {}
        result = generate_excel_query(conn, 'Sheet1')
        self.assertIn('Excel.Workbook', result)

    def test_excel_query_uses_sheet_name(self):
        result = generate_excel_query({}, 'SalesData')
        self.assertIn('SalesData', result)

    def test_excel_query_promotes_headers(self):
        result = generate_excel_query({}, 'S')
        self.assertIn('PromoteHeaders', result)


class TestGenerateCsvQuery(unittest.TestCase):
    """Tests for CSV connector M query generation."""

    def test_csv_query_contains_csv_document(self):
        result = generate_csv_query({}, 'data')
        self.assertIn('Csv.Document', result)

    def test_csv_query_includes_table_name_in_path(self):
        result = generate_csv_query({}, 'employees')
        self.assertIn('employees.csv', result)

    def test_csv_query_specifies_utf8(self):
        result = generate_csv_query({}, 'x')
        self.assertIn('65001', result)


class TestGenerateWebQuery(unittest.TestCase):
    """Tests for Web connector M query generation."""

    def test_web_query_uses_web_contents(self):
        result = generate_web_query({}, 'api_data')
        self.assertIn('Web.Contents', result)

    def test_web_query_parses_json(self):
        result = generate_web_query({}, 'api_data')
        self.assertIn('Json.Document', result)


class TestGenerateJsonQuery(unittest.TestCase):
    """Tests for JSON file M query generation."""

    def test_json_query_reads_file(self):
        result = generate_json_query({}, 'config')
        self.assertIn('Json.Document', result)
        self.assertIn('File.Contents', result)

    def test_json_query_uses_table_name_in_path(self):
        result = generate_json_query({}, 'products')
        self.assertIn('products.json', result)

    def test_json_query_handles_list_or_record(self):
        result = generate_json_query({}, 'x')
        self.assertIn('Value.Is', result)
        self.assertIn('Table.FromRecords', result)


class TestGenerateSampleDataQuery(unittest.TestCase):
    """Tests for fallback sample data M query generation."""

    def test_sample_query_with_known_columns(self):
        ds = {
            'tables': [
                {
                    'name': 'Orders',
                    'columns': [
                        {'name': 'OrderID'},
                        {'name': 'Amount'},
                        {'name': 'OrderDate'},
                    ],
                }
            ]
        }
        result = generate_sample_data_query('Orders', ds)
        self.assertIn('"OrderID"', result)
        self.assertIn('"Amount"', result)
        self.assertIn('"OrderDate"', result)
        self.assertIn('#table', result)

    def test_sample_query_uses_default_columns(self):
        result = generate_sample_data_query('UnknownTable', {'tables': []})
        self.assertIn('"ID"', result)
        self.assertIn('"Name"', result)
        self.assertIn('"Value"', result)

    def test_sample_query_generates_5_rows(self):
        ds = {'tables': [{'name': 'T', 'columns': [{'name': 'x'}]}]}
        result = generate_sample_data_query('T', ds)
        # Each row starts with { — count data rows
        lines = [l.strip() for l in result.split('\n') if l.strip().startswith('{') and ',' in l]
        self.assertGreaterEqual(len(lines), 5)

    def test_sample_query_id_column_generates_numbers(self):
        ds = {'tables': [{'name': 'T', 'columns': [{'name': 'CustomerID'}]}]}
        result = generate_sample_data_query('T', ds)
        # Should have numeric values 1-5
        self.assertIn('{1}', result)
        self.assertIn('{5}', result)

    def test_sample_query_date_column_generates_dates(self):
        ds = {'tables': [{'name': 'T', 'columns': [{'name': 'sale_date'}]}]}
        result = generate_sample_data_query('T', ds)
        self.assertIn('#date(2024', result)

    def test_sample_query_includes_todo_comment(self):
        result = generate_sample_data_query('T', {'tables': []})
        self.assertIn('TODO', result)


class TestGenerateMQueryFromDatasource(unittest.TestCase):
    """Tests for the router function that dispatches to type-specific generators."""

    def _ds(self, conn_type):
        return {
            'dataSource': {
                'connectionType': conn_type,
                'connectionDetails': {'server': 's', 'database': 'd'},
            },
            'tables': [],
        }

    def test_sql_routing(self):
        result = generate_m_query_from_datasource(self._ds('SQL Server'), 'T')
        self.assertIn('Sql.Database', result)

    def test_postgres_routing(self):
        result = generate_m_query_from_datasource(self._ds('PostgreSQL'), 'T')
        self.assertIn('Sql.Database', result)

    def test_mysql_routing(self):
        result = generate_m_query_from_datasource(self._ds('MySQL'), 'T')
        self.assertIn('Sql.Database', result)

    def test_oracle_routing(self):
        result = generate_m_query_from_datasource(self._ds('Oracle'), 'T')
        self.assertIn('Sql.Database', result)

    def test_excel_routing(self):
        result = generate_m_query_from_datasource(self._ds('Excel'), 'T')
        self.assertIn('Excel.Workbook', result)

    def test_csv_routing(self):
        result = generate_m_query_from_datasource(self._ds('CSV'), 'T')
        self.assertIn('Csv.Document', result)

    def test_text_routing(self):
        result = generate_m_query_from_datasource(self._ds('Text File'), 'T')
        self.assertIn('Csv.Document', result)

    def test_web_routing(self):
        result = generate_m_query_from_datasource(self._ds('Web'), 'T')
        self.assertIn('Web.Contents', result)

    def test_json_routing(self):
        result = generate_m_query_from_datasource(self._ds('JSON'), 'T')
        self.assertIn('Json.Document', result)

    def test_unknown_falls_back_to_sample(self):
        result = generate_m_query_from_datasource(self._ds('UnknownDB'), 'T')
        self.assertIn('#table', result)

    def test_empty_datasource(self):
        result = generate_m_query_from_datasource({}, 'T')
        self.assertIn('#table', result)


class TestColumnTypeMapping(unittest.TestCase):
    """Tests for Tableau → M type mapping dictionary."""

    def test_mapping_has_all_expected_types(self):
        mapping = get_column_type_mapping()
        expected_keys = {'string', 'integer', 'real', 'decimal', 'boolean', 'date', 'datetime', 'time', 'spatial'}
        self.assertEqual(set(mapping.keys()), expected_keys)

    def test_string_maps_to_text(self):
        self.assertEqual(get_column_type_mapping()['string'], 'type text')

    def test_integer_maps_to_int64(self):
        self.assertEqual(get_column_type_mapping()['integer'], 'Int64.Type')

    def test_boolean_maps_to_logical(self):
        self.assertEqual(get_column_type_mapping()['boolean'], 'type logical')

    def test_date_maps_to_date(self):
        self.assertEqual(get_column_type_mapping()['date'], 'type date')

    def test_spatial_maps_to_text(self):
        self.assertEqual(get_column_type_mapping()['spatial'], 'type text')


if __name__ == '__main__':
    unittest.main()
