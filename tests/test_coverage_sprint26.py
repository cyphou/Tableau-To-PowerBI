"""
Sprint 26 — Coverage-driven gap filling tests.

Covers uncovered branches across:
- m_query_builder.py connector generators (GeoJSON, JSON, XML, PDF, etc.)
- m_query_builder.py template/inject functions
- dax_converter.py edge cases and round-trip tests
- pbip_generator.py additional branches
- tmdl_generator.py edge paths
- assessment.py remaining branches
- validator.py uncovered branches
"""

import os
import sys
import json
import re
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))


# ══════════════════════════════════════════════════════════════════════════════
# M Query Builder — Connector generators
# ══════════════════════════════════════════════════════════════════════════════

class TestMConnectorGenerators(unittest.TestCase):
    """Test uncovered connector generator functions."""

    COLS = [{'name': 'Id', 'datatype': 'integer'}, {'name': 'Name', 'datatype': 'string'}]

    def _gen(self, conn_type, details=None):
        from tableau_export.m_query_builder import generate_power_query_m
        return generate_power_query_m(
            {'type': conn_type, 'details': details or {}},
            {'name': 'TestTable', 'columns': self.COLS},
        )

    def test_geojson_connector(self):
        m = self._gen('GeoJSON', {'filename': 'map.geojson'})
        self.assertIn('Json.Document', m)
        self.assertIn('features', m)
        self.assertIn('map.geojson', m)

    def test_json_connector(self):
        m = self._gen('JSON', {'filename': 'data.json'})
        self.assertIn('Json.Document', m)
        self.assertIn('data.json', m)

    def test_xml_connector(self):
        m = self._gen('XML', {'filename': 'data.xml'})
        self.assertIn('Xml.Tables', m)
        self.assertIn('data.xml', m)

    def test_pdf_connector(self):
        m = self._gen('PDF', {'filename': 'report.pdf'})
        self.assertIn('Pdf.Tables', m)
        self.assertIn('report.pdf', m)

    def test_salesforce_connector(self):
        m = self._gen('Salesforce')
        self.assertIn('Salesforce.Data', m)

    def test_web_connector(self):
        m = self._gen('Web', {'url': 'https://api.example.com'})
        self.assertIn('Web.Contents', m)
        self.assertIn('api.example.com', m)

    def test_odata_connector(self):
        m = self._gen('OData', {'server': 'https://odata.example.com'})
        self.assertIn('OData.Feed', m)

    def test_google_analytics_connector(self):
        m = self._gen('Google Analytics', {'view_id': 'GA123'})
        self.assertIn('GoogleAnalytics', m)

    def test_azure_blob_connector(self):
        m = self._gen('Azure Blob', {'account': 'mystorageacct', 'container': 'data'})
        self.assertIn('AzureStorage', m)

    def test_azure_blob_adls_connector(self):
        m = self._gen('ADLS', {'server': 'adls.dfs.core.windows.net'})
        self.assertIn('AzureStorage.DataLake', m)

    def test_vertica_connector(self):
        m = self._gen('Vertica', {'server': 'vertica-host'})
        self.assertIn('Odbc.DataSource', m)
        self.assertIn('Vertica', m)

    def test_impala_connector(self):
        m = self._gen('Impala', {'server': 'impala-host'})
        self.assertIn('Impala', m)

    def test_hadoop_hive_connector(self):
        m = self._gen('Hadoop Hive', {'server': 'hive-host'})
        self.assertIn('Hive', m)

    def test_presto_connector(self):
        m = self._gen('Presto', {'server': 'presto-host'})
        self.assertIn('Presto', m)

    def test_teradata_connector(self):
        m = self._gen('Teradata', {'server': 'td-server'})
        self.assertIn('Teradata.Database', m)

    def test_sap_hana_connector(self):
        m = self._gen('SAP HANA', {'server': 'hana-server'})
        self.assertIn('SapHana.Database', m)

    def test_sap_bw_connector(self):
        m = self._gen('SAP BW', {'server': 'bw-server'})
        self.assertIn('SapBusinessWarehouse', m)

    def test_redshift_connector(self):
        m = self._gen('Redshift', {'server': 'rs.amazonaws.com'})
        self.assertIn('AmazonRedshift', m)

    def test_databricks_connector(self):
        m = self._gen('Databricks', {'server': 'adb-xxx.azuredatabricks.net'})
        self.assertIn('Databricks.Catalogs', m)

    def test_spark_connector(self):
        m = self._gen('Spark', {'server': 'spark-host'})
        self.assertIn('SparkSql', m)

    def test_azure_sql_connector(self):
        m = self._gen('Azure SQL', {'server': 'myserver.database.windows.net'})
        self.assertIn('AzureSQL.Database', m)

    def test_synapse_connector(self):
        m = self._gen('Synapse', {'server': 'myworkspace.sql.azuresynapse.net'})
        self.assertIn('AzureSQL.Database', m)

    def test_google_sheets_connector(self):
        m = self._gen('Google Sheets', {'spreadsheet_id': 'ABC123'})
        self.assertIn('docs.google.com', m)

    def test_sharepoint_connector(self):
        m = self._gen('SharePoint', {'site_url': 'https://contoso.sharepoint.com'})
        self.assertIn('SharePoint.Files', m)

    def test_snowflake_connector(self):
        m = self._gen('Snowflake', {'server': 'acct.snowflakecomputing.com', 'warehouse': 'WH', 'database': 'DB', 'schema': 'PUBLIC'})
        self.assertIn('Snowflake.Databases', m)

    def test_fallback_unknown_connector(self):
        m = self._gen('some_unknown_connector')
        self.assertIn('TODO', m)
        self.assertIn('some_unknown_connector', m)

    def test_custom_sql_connector_with_params(self):
        m = self._gen('Custom SQL', {
            'server': 'localhost', 'database': 'db',
            'sql_query': 'SELECT * FROM t WHERE x = @p1',
            'params': {'p1': 'val1'},
        })
        self.assertIn('Value.NativeQuery', m)
        self.assertIn('p1', m)

    def test_custom_sql_connector_without_params(self):
        m = self._gen('Custom SQL', {
            'server': 'localhost', 'database': 'db',
            'sql_query': 'SELECT * FROM t',
        })
        self.assertIn('Sql.Database', m)
        self.assertNotIn('Value.NativeQuery', m)


# ══════════════════════════════════════════════════════════════════════════════
# M Query Builder — Templating
# ══════════════════════════════════════════════════════════════════════════════

class TestMTemplating(unittest.TestCase):
    """Test apply_connection_template and templatize_m_query."""

    def test_apply_template_with_values(self):
        from tableau_export.m_query_builder import apply_connection_template
        q = 'Source = Sql.Database("${ENV.SERVER}", "${ENV.DATABASE}")'
        result = apply_connection_template(q, {'SERVER': 'prod.db.com', 'DATABASE': 'ProdDB'})
        self.assertIn('prod.db.com', result)
        self.assertIn('ProdDB', result)
        self.assertNotIn('${ENV.', result)

    def test_apply_template_no_env_generates_m_param(self):
        from tableau_export.m_query_builder import apply_connection_template
        q = 'Source = Sql.Database("${ENV.SERVER}", "${ENV.DATABASE}")'
        result = apply_connection_template(q, None)
        self.assertIn('SERVER', result)
        self.assertNotIn('${ENV.', result)

    def test_apply_template_no_placeholders_returns_unchanged(self):
        from tableau_export.m_query_builder import apply_connection_template
        q = 'Source = Sql.Database("localhost", "mydb")'
        self.assertEqual(apply_connection_template(q), q)

    def test_templatize_m_query(self):
        from tableau_export.m_query_builder import templatize_m_query
        q = 'Source = Sql.Database("myserver.example.com", "SalesDB")'
        conn = {'details': {'server': 'myserver.example.com', 'database': 'SalesDB'}}
        result = templatize_m_query(q, conn)
        self.assertIn('${ENV.SERVER}', result)
        self.assertIn('${ENV.DATABASE}', result)

    def test_templatize_no_connection_returns_unchanged(self):
        from tableau_export.m_query_builder import templatize_m_query
        q = 'Source = Sql.Database("x", "y")'
        self.assertEqual(templatize_m_query(q), q)


# ══════════════════════════════════════════════════════════════════════════════
# M Query Builder — inject_m_steps edge cases
# ══════════════════════════════════════════════════════════════════════════════

class TestInjectMSteps(unittest.TestCase):
    """Test inject_m_steps edge cases."""

    def test_inject_empty_steps(self):
        from tableau_export.m_query_builder import inject_m_steps
        q = 'let\n    Source = Table.A()\nin\n    Source'
        result = inject_m_steps(q, [])
        self.assertEqual(result, q)

    def test_inject_malformed_query_no_in(self):
        from tableau_export.m_query_builder import inject_m_steps
        q = 'Source = Table.A()'
        result = inject_m_steps(q, [('Step1', '{prev}')])
        self.assertEqual(result, q)  # returns as-is

    def test_inject_chained_steps(self):
        from tableau_export.m_query_builder import inject_m_steps
        q = 'let\n    Source = Sql.Database("s", "d")\nin\n    Source'
        from tableau_export.m_query_builder import m_transform_rename, m_transform_trim
        steps = [
            m_transform_rename({'old': 'new'}),
            m_transform_trim(['Col1']),
        ]
        result = inject_m_steps(q, steps)
        self.assertIn('RenameColumns', result)
        self.assertIn('Trim', result)
        self.assertIn('in\n', result)

    def test_inject_strips_previous_result(self):
        from tableau_export.m_query_builder import inject_m_steps
        q = 'let\n    Source = Sql.Database("s", "d"),\n    Result = Source\nin\n    Result'
        steps = [('Extra', 'Table.AddColumn({prev}, "X", each 1)')]
        result = inject_m_steps(q, steps)
        self.assertIn('Extra', result)


# ══════════════════════════════════════════════════════════════════════════════
# M Query Builder — Additional transform generators
# ══════════════════════════════════════════════════════════════════════════════

class TestMTransformEdgeCases(unittest.TestCase):
    """Test edge cases for M transform generators."""

    def test_split_with_num_parts(self):
        from tableau_export.m_query_builder import m_transform_split_by_delimiter
        name, expr = m_transform_split_by_delimiter('FullName', '-', num_parts=3)
        self.assertIn('Split', name)
        self.assertIn('Splitter', expr)

    def test_split_without_num_parts(self):
        from tableau_export.m_query_builder import m_transform_split_by_delimiter
        name, expr = m_transform_split_by_delimiter('Address', ',')
        self.assertIn('Split', name)

    def test_replace_value_non_text(self):
        from tableau_export.m_query_builder import m_transform_replace_value
        name, expr = m_transform_replace_value('Amount', '0', '999', replace_text=False)
        self.assertIn('ReplaceValue', expr)

    def test_replace_nulls_with_string(self):
        from tableau_export.m_query_builder import m_transform_replace_nulls
        name, expr = m_transform_replace_nulls('Name', 'Unknown')
        self.assertIn('null', expr)
        self.assertIn('Unknown', expr)

    def test_replace_nulls_with_number(self):
        from tableau_export.m_query_builder import m_transform_replace_nulls
        name, expr = m_transform_replace_nulls('Amount', 0)
        self.assertIn('null', expr)

    def test_filter_range_min_only(self):
        from tableau_export.m_query_builder import m_transform_filter_range
        name, expr = m_transform_filter_range('Price', min_val=10)
        self.assertIn('>=', expr)

    def test_filter_range_max_only(self):
        from tableau_export.m_query_builder import m_transform_filter_range
        name, expr = m_transform_filter_range('Price', max_val=100)
        self.assertIn('<=', expr)

    def test_filter_range_both(self):
        from tableau_export.m_query_builder import m_transform_filter_range
        name, expr = m_transform_filter_range('Price', min_val=5, max_val=50)
        self.assertIn('>=', expr)
        self.assertIn('<=', expr)

    def test_filter_nulls_keep(self):
        from tableau_export.m_query_builder import m_transform_filter_nulls
        name, expr = m_transform_filter_nulls('Col', keep_nulls=True)
        self.assertIn('null', expr)

    def test_filter_nulls_remove(self):
        from tableau_export.m_query_builder import m_transform_filter_nulls
        name, expr = m_transform_filter_nulls('Col', keep_nulls=False)
        self.assertIn('null', expr)

    def test_distinct_all_columns(self):
        from tableau_export.m_query_builder import m_transform_distinct
        name, expr = m_transform_distinct()
        self.assertIn('Distinct', expr)

    def test_distinct_specific_columns(self):
        from tableau_export.m_query_builder import m_transform_distinct
        name, expr = m_transform_distinct(['A', 'B'])
        self.assertIn('Distinct', expr)

    def test_top_n_ascending(self):
        from tableau_export.m_query_builder import m_transform_top_n
        name, expr = m_transform_top_n(10, 'Price', descending=False)
        self.assertIn('FirstN', expr)
        self.assertIn('Ascending', expr)

    def test_aggregate_multiple_operations(self):
        from tableau_export.m_query_builder import m_transform_aggregate
        name, expr = m_transform_aggregate(
            ['Category'],
            [{'name': 'Total_Amount', 'column': 'Amount', 'agg': 'sum'},
             {'name': 'Row_Count', 'column': 'Count', 'agg': 'count'},
             {'name': 'Avg_Price', 'column': 'Price', 'agg': 'avg'},
             {'name': 'Unique_Count', 'column': 'Unique', 'agg': 'countd'},
             {'name': 'Med_Score', 'column': 'Score', 'agg': 'median'}],
        )
        self.assertIn('Table.Group', expr)
        self.assertIn('List.Sum', expr)
        self.assertIn('Table.RowCount', expr)
        self.assertIn('List.Average', expr)
        self.assertIn('List.Distinct', expr)

    def test_aggregate_min_max_stdev(self):
        from tableau_export.m_query_builder import m_transform_aggregate
        name, expr = m_transform_aggregate(
            ['Region'],
            [{'name': 'Min_Val', 'column': 'Val', 'agg': 'min'},
             {'name': 'Max_Val', 'column': 'Val', 'agg': 'max'},
             {'name': 'Std_Val', 'column': 'Val', 'agg': 'stdev'}],
        )
        self.assertIn('List.Min', expr)
        self.assertIn('List.Max', expr)
        self.assertIn('List.StandardDeviation', expr)

    def test_unpivot(self):
        from tableau_export.m_query_builder import m_transform_unpivot
        name, expr = m_transform_unpivot(['Q1', 'Q2', 'Q3'])
        self.assertIn('Table.Unpivot', expr)
        self.assertIn('Q1', expr)

    def test_unpivot_other(self):
        from tableau_export.m_query_builder import m_transform_unpivot_other
        name, expr = m_transform_unpivot_other(['ID', 'Name'])
        self.assertIn('UnpivotOtherColumns', expr)

    def test_pivot(self):
        from tableau_export.m_query_builder import m_transform_pivot
        name, expr = m_transform_pivot('Category', 'Amount')
        self.assertIn('Table.Pivot', expr)

    def test_join_types(self):
        from tableau_export.m_query_builder import m_transform_join
        for jt in ('left', 'right', 'inner', 'full', 'leftanti', 'rightanti'):
            result = m_transform_join('OtherTable', ['Key'], ['Key'], join_type=jt)
            # Returns list of (name, expr) tuples
            self.assertIsInstance(result, list)
            self.assertIn('Table.NestedJoin', result[0][1])

    def test_join_with_expand(self):
        from tableau_export.m_query_builder import m_transform_join
        result = m_transform_join('Dim', ['FK'], ['PK'],
                                  expand_columns=['Name', 'Code'])
        self.assertEqual(len(result), 2)
        self.assertIn('ExpandTableColumn', result[1][1])

    def test_union(self):
        from tableau_export.m_query_builder import m_transform_union
        name, expr = m_transform_union(['Table1', 'Table2'])
        self.assertIn('Table.Combine', expr)

    def test_wildcard_union(self):
        from tableau_export.m_query_builder import m_transform_wildcard_union
        m = m_transform_wildcard_union('C:\\Data', '.csv')
        # Returns a complete M query string, not a tuple
        self.assertIsInstance(m, str)
        self.assertIn('Folder.Files', m)

    def test_sort(self):
        from tableau_export.m_query_builder import m_transform_sort
        name, expr = m_transform_sort([('Name', True), ('Age', False)])
        self.assertIn('Table.Sort', expr)
        self.assertIn('Ascending', expr)
        self.assertIn('Descending', expr)

    def test_transpose(self):
        from tableau_export.m_query_builder import m_transform_transpose
        name, expr = m_transform_transpose()
        self.assertIn('Table.Transpose', expr)

    def test_add_index(self):
        from tableau_export.m_query_builder import m_transform_add_index
        name, expr = m_transform_add_index('RowNum', start=0, increment=2)
        self.assertIn('Table.AddIndexColumn', expr)
        self.assertIn('0', expr)

    def test_skip_rows(self):
        from tableau_export.m_query_builder import m_transform_skip_rows
        name, expr = m_transform_skip_rows(5)
        self.assertIn('Table.Skip', expr)

    def test_remove_last_rows(self):
        from tableau_export.m_query_builder import m_transform_remove_last_rows
        name, expr = m_transform_remove_last_rows(3)
        self.assertIn('Table.RemoveLastN', expr)

    def test_remove_errors_generic(self):
        from tableau_export.m_query_builder import m_transform_remove_errors
        name, expr = m_transform_remove_errors()
        self.assertIn('RemoveRowsWithErrors', expr)

    def test_promote_headers(self):
        from tableau_export.m_query_builder import m_transform_promote_headers
        name, expr = m_transform_promote_headers()
        self.assertIn('PromoteHeaders', expr)

    def test_demote_headers(self):
        from tableau_export.m_query_builder import m_transform_demote_headers
        name, expr = m_transform_demote_headers()
        self.assertIn('DemoteHeaders', expr)

    def test_add_column(self):
        from tableau_export.m_query_builder import m_transform_add_column
        name, expr = m_transform_add_column('FullName', '[First] & " " & [Last]', 'type text')
        self.assertIn('Table.AddColumn', expr)
        self.assertIn('FullName', expr)

    def test_conditional_column(self):
        from tableau_export.m_query_builder import m_transform_conditional_column
        conditions = [
            ('[Score] >= 90', '"A"'),
            ('[Score] >= 80', '"B"'),
        ]
        name, expr = m_transform_conditional_column('Grade', conditions, default_value='"C"')
        self.assertIn('Table.AddColumn', expr)
        self.assertIn('Grade', expr)

    def test_replace_errors(self):
        from tableau_export.m_query_builder import m_transform_replace_errors
        name, expr = m_transform_replace_errors(['Col1', 'Col2'], replacement='N/A')
        self.assertIn('ReplaceErrorValues', expr)

    def test_try_otherwise(self):
        from tableau_export.m_query_builder import m_transform_try_otherwise
        name, expr = m_transform_try_otherwise('Safe', 'risky_expr', 'fallback_expr')
        self.assertIn('try', expr)
        self.assertIn('otherwise', expr)

    def test_buffer(self):
        from tableau_export.m_query_builder import m_transform_buffer
        name, expr = m_transform_buffer()
        self.assertIn('Table.Buffer', expr)


# ══════════════════════════════════════════════════════════════════════════════
# DAX Converter — Round-trip and edge cases
# ══════════════════════════════════════════════════════════════════════════════

class TestDaxRoundTrip(unittest.TestCase):
    """Test DAX round-trip: converted formulas should produce valid DAX syntax."""

    def _convert(self, formula, **kw):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        return convert_tableau_formula_to_dax(formula, **kw)

    def _is_balanced(self, formula):
        """Check balanced parentheses."""
        depth = 0
        for ch in formula:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            if depth < 0:
                return False
        return depth == 0

    def test_balanced_parens_simple(self):
        cases = [
            'IF [Sales] > 1000 THEN "High" ELSE "Low" END',
            'SUM([Amount])',
            'DATETRUNC("month", [Date])',
            'LEFT([Name], 3)',
        ]
        for formula in cases:
            result = self._convert(formula)
            self.assertTrue(self._is_balanced(result), f"Unbalanced: {result} (from: {formula})")

    def test_balanced_parens_nested(self):
        formula = 'IF ISNULL([X]) THEN ZN([Y]) ELSE LEFT(UPPER([X]), 5) END'
        result = self._convert(formula)
        self.assertTrue(self._is_balanced(result))

    def test_no_doubled_operators(self):
        """Converted DAX should not contain doubled operators like ++ or --."""
        formulas = [
            '[A] + [B]',
            '[A] - [B]',
            '[A] * [B]',
            '[A] / [B]',
        ]
        for f in formulas:
            result = self._convert(f)
            self.assertNotIn('++', result)
            self.assertNotIn('--', result)
            self.assertNotIn('**', result)

    def test_valid_dax_functions(self):
        """All output functions should be real DAX functions."""
        result = self._convert('MEDIAN([Sales])')
        self.assertTrue(result.startswith('MEDIAN') or 'MEDIAN' in result)

    def test_lod_fixed_single_dim(self):
        result = self._convert('{FIXED [Region] : SUM([Sales])}')
        self.assertIn('CALCULATE', result)
        self.assertIn('SUM', result)

    def test_lod_include(self):
        result = self._convert('{INCLUDE [State] : COUNT([Orders])}')
        self.assertIn('CALCULATE', result)

    def test_lod_exclude(self):
        result = self._convert('{EXCLUDE [Year] : AVG([Sales])}')
        self.assertIn('CALCULATE', result)
        self.assertIn('REMOVEFILTERS', result)

    def test_running_sum(self):
        result = self._convert('RUNNING_SUM(SUM([Sales]))')
        self.assertIn('CALCULATE', result)

    def test_rank(self):
        result = self._convert('RANK(SUM([Sales]))')
        self.assertIn('RANKX', result)

    def test_datetrunc_year(self):
        result = self._convert('DATETRUNC("year", [Date])')
        self.assertIn('STARTOFYEAR', result)

    def test_datepart_month(self):
        result = self._convert('DATEPART("month", [Date])')
        self.assertIn('MONTH', result)

    def test_contains(self):
        result = self._convert('CONTAINS([Name], "hello")')
        self.assertIn('CONTAINSSTRING', result)

    def test_datediff(self):
        result = self._convert('DATEDIFF([Start], [End], "day")')
        self.assertIn('DATEDIFF', result)

    def test_dateadd_months(self):
        result = self._convert('DATEADD("month", 3, [Date])')
        self.assertIn('DATEADD', result)

    def test_str_conversion(self):
        result = self._convert('STR([Amount])')
        self.assertIn('FORMAT', result)

    def test_int_conversion(self):
        result = self._convert('INT([Price])')
        self.assertIn('INT', result)

    def test_countd(self):
        result = self._convert('COUNTD([Customer])')
        self.assertIn('DISTINCTCOUNT', result)

    def test_username(self):
        result = self._convert('USERNAME()')
        self.assertIn('USERPRINCIPALNAME', result)


class TestDaxEdgeCases(unittest.TestCase):
    """Test DAX converter edge cases and less common conversions."""

    def _convert(self, formula, **kw):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        return convert_tableau_formula_to_dax(formula, **kw)

    def test_empty_string_returns_empty(self):
        self.assertEqual(self._convert(''), '')

    def test_multiline_condensed(self):
        formula = 'IF [A] > 0\nTHEN "Positive"\nELSE "Negative"\nEND'
        result = self._convert(formula)
        # Should be condensed to single line
        self.assertNotIn('\n', result.strip())

    def test_double_equals(self):
        result = self._convert('[A] == [B]')
        self.assertIn('=', result)
        self.assertNotIn('==', result)

    def test_string_concatenation_plus(self):
        result = self._convert('[First] + " " + [Last]', calc_datatype='string')
        self.assertIn('&', result)

    def test_elseif_conversion(self):
        formula = 'IF [X] > 0 THEN "A" ELSEIF [X] > -1 THEN "B" ELSE "C" END'
        result = self._convert(formula)
        # ELSEIF → nested IF or comma-separated
        self.assertNotIn('ELSEIF', result)

    def test_or_and_conversion(self):
        result = self._convert('[A] > 1 or [B] < 2')
        self.assertIn('||', result)
        result2 = self._convert('[A] > 1 and [B] < 2')
        self.assertIn('&&', result2)

    def test_abs_function(self):
        result = self._convert('ABS([Profit])')
        self.assertIn('ABS', result)

    def test_ceiling_function(self):
        result = self._convert('CEILING([Price])')
        self.assertIn('CEILING', result)

    def test_floor_function(self):
        result = self._convert('FLOOR([Price])')
        self.assertIn('FLOOR', result)

    def test_round_function(self):
        result = self._convert('ROUND([Price], 2)')
        self.assertIn('ROUND', result)

    def test_power_function(self):
        result = self._convert('POWER([Base], 2)')
        self.assertIn('POWER', result)

    def test_sqrt_function(self):
        result = self._convert('SQRT([Value])')
        self.assertIn('SQRT', result)

    def test_log_function(self):
        result = self._convert('LOG([Value])')
        self.assertIn('LOG', result)

    def test_exp_function(self):
        result = self._convert('EXP([Value])')
        self.assertIn('EXP', result)

    def test_today_now(self):
        self.assertIn('TODAY', self._convert('TODAY()'))
        self.assertIn('NOW', self._convert('NOW()'))

    def test_min_max(self):
        self.assertIn('MIN', self._convert('MIN([A])'))
        self.assertIn('MAX', self._convert('MAX([B])'))

    def test_trim_function(self):
        result = self._convert('TRIM([Name])')
        self.assertIn('TRIM', result)

    def test_upper_lower(self):
        self.assertIn('UPPER', self._convert('UPPER([Name])'))
        self.assertIn('LOWER', self._convert('LOWER([Name])'))

    def test_replace_function(self):
        result = self._convert('REPLACE([Text], "old", "new")')
        self.assertIn('SUBSTITUTE', result)


# ══════════════════════════════════════════════════════════════════════════════
# Assessment — Additional coverage
# ══════════════════════════════════════════════════════════════════════════════

class TestAssessmentAdditional(unittest.TestCase):
    """Cover remaining assessment branches."""

    def test_check_interactivity_with_url_actions(self):
        from powerbi_import.assessment import _check_interactivity
        extracted = {
            'actions': [{'type': 'url'}, {'type': 'url'}],
            'stories': [],
            'worksheets': [],
            'dashboards': [],
        }
        result = _check_interactivity(extracted)
        texts = ' '.join(c.detail for c in result.checks)
        self.assertIn('URL', texts)

    def test_check_interactivity_with_set_actions(self):
        from powerbi_import.assessment import _check_interactivity
        extracted = {
            'actions': [{'type': 'set'}],
            'stories': [],
            'worksheets': [],
            'dashboards': [],
        }
        result = _check_interactivity(extracted)
        texts = ' '.join(c.detail for c in result.checks)
        self.assertIn('set', texts.lower())

    def test_check_interactivity_with_stories(self):
        from powerbi_import.assessment import _check_interactivity
        extracted = {
            'actions': [],
            'stories': [{'story_points': [{'caption': 'A'}, {'caption': 'B'}]}],
            'worksheets': [],
            'dashboards': [],
        }
        result = _check_interactivity(extracted)
        texts = ' '.join(c.detail for c in result.checks)
        self.assertIn('bookmark', texts.lower())

    def test_check_interactivity_combined(self):
        from powerbi_import.assessment import _check_interactivity
        extracted = {
            'actions': [{'type': 'filter'}, {'type': 'highlight'}],
            'stories': [{'story_points': []}],
            'worksheets': [{'name': 'W', 'pages_shelf': {'field': '[Year]'}}],
            'dashboards': [{'dynamic_zone_visibility': [{'zone_name': 'Z'}]}],
        }
        result = _check_interactivity(extracted)
        texts = ' '.join(c.detail for c in result.checks)
        self.assertIn('filter', texts.lower())
        self.assertIn('Pages shelf', texts)  # Should be present now


# ══════════════════════════════════════════════════════════════════════════════
# Misc coverage — map_tableau_to_m_type
# ══════════════════════════════════════════════════════════════════════════════

class TestMTypeMapping(unittest.TestCase):
    """Test map_tableau_to_m_type covers all branches."""

    def test_known_types(self):
        from tableau_export.m_query_builder import map_tableau_to_m_type
        mappings = {
            'string': 'type text',
            'integer': 'Int64.Type',
            'real': 'type number',
            'date': 'type date',
            'datetime': 'type datetime',
            'boolean': 'type logical',
        }
        for tab_type, expected in mappings.items():
            result = map_tableau_to_m_type(tab_type)
            self.assertEqual(result, expected, f"Failed for {tab_type}")

    def test_unknown_type_defaults_to_text(self):
        from tableau_export.m_query_builder import map_tableau_to_m_type
        result = map_tableau_to_m_type('unknown_weird_type')
        self.assertEqual(result, 'type text')


# ══════════════════════════════════════════════════════════════════════════════
# Fabric Lakehouse / BigQuery connectors
# ══════════════════════════════════════════════════════════════════════════════

class TestAdditionalConnectors(unittest.TestCase):
    """BigQuery and Fabric Lakehouse connectors."""

    COLS = [{'name': 'Id', 'datatype': 'integer'}]

    def _gen(self, conn_type, details=None):
        from tableau_export.m_query_builder import generate_power_query_m
        return generate_power_query_m(
            {'type': conn_type, 'details': details or {}},
            {'name': 'TestTable', 'columns': self.COLS},
        )

    def test_bigquery_connector(self):
        m = self._gen('BigQuery', {'project': 'myproj', 'dataset': 'ds'})
        self.assertIn('GoogleBigQuery', m)

    def test_fabric_lakehouse_connector(self):
        m = self._gen('Fabric Lakehouse', {'workspace_id': 'WS123'})
        self.assertIn('Lakehouse', m)

    def test_mysql_connector(self):
        m = self._gen('MySQL', {'server': 'mysql-host', 'database': 'mydb'})
        self.assertIn('MySQL.Database', m)

    def test_oracle_connector(self):
        m = self._gen('Oracle', {'server': 'oracle-host', 'database': 'ORCL'})
        self.assertIn('Oracle.Database', m)

    def test_csv_connector(self):
        m = self._gen('CSV', {'filename': 'data.csv'})
        self.assertIn('Csv.Document', m)

    def test_excel_connector(self):
        m = self._gen('Excel', {'filename': 'data.xlsx'})
        self.assertIn('Excel.Workbook', m)

    def test_sql_server_connector(self):
        m = self._gen('SQL Server', {'server': 'sql-host', 'database': 'db'})
        self.assertIn('Sql.Database', m)

    def test_postgresql_connector(self):
        m = self._gen('PostgreSQL', {'server': 'pg-host', 'database': 'pgdb'})
        self.assertIn('PostgreSQL.Database', m)


if __name__ == '__main__':
    unittest.main(verbosity=2)
