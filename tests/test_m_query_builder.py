"""
Unit tests for m_query_builder.py — Power Query M generation and transforms.

Tests connector generators, inject_m_steps chaining, type mapping,
and all 40+ transformation step generators.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

from m_query_builder import (
    map_tableau_to_m_type,
    generate_power_query_m,
    inject_m_steps,
    # Column operations
    m_transform_rename,
    m_transform_remove_columns,
    m_transform_select_columns,
    m_transform_duplicate_column,
    m_transform_reorder_columns,
    m_transform_split_by_delimiter,
    m_transform_merge_columns,
    # Value operations
    m_transform_replace_value,
    m_transform_replace_nulls,
    m_transform_trim,
    m_transform_clean,
    m_transform_upper,
    m_transform_lower,
    m_transform_proper_case,
    m_transform_fill_down,
    m_transform_fill_up,
    # Filter operations
    m_transform_filter_values,
    m_transform_exclude_values,
    m_transform_filter_range,
    m_transform_filter_nulls,
    m_transform_filter_contains,
    m_transform_distinct,
    m_transform_top_n,
    # Aggregate
    m_transform_aggregate,
    # Pivot
    m_transform_unpivot,
    m_transform_unpivot_other,
    m_transform_pivot,
    # Join
    m_transform_join,
    m_transform_buffer,
    # Union
    m_transform_union,
    m_transform_wildcard_union,
    # Reshape
    m_transform_sort,
    m_transform_transpose,
    m_transform_add_index,
    m_transform_skip_rows,
    m_transform_remove_last_rows,
    m_transform_remove_errors,
    m_transform_promote_headers,
    m_transform_demote_headers,
    # Calculated
    m_transform_add_column,
    m_transform_conditional_column,
)


# ═══════════════════════════════════════════════════════════════════════
# Type Mapping
# ═══════════════════════════════════════════════════════════════════════

class TestMapTableauToMType(unittest.TestCase):
    """Test map_tableau_to_m_type."""

    def test_integer(self):
        self.assertEqual(map_tableau_to_m_type("integer"), "Int64.Type")

    def test_real(self):
        self.assertEqual(map_tableau_to_m_type("real"), "type number")

    def test_string(self):
        self.assertEqual(map_tableau_to_m_type("string"), "type text")

    def test_boolean(self):
        self.assertEqual(map_tableau_to_m_type("boolean"), "type logical")

    def test_date(self):
        self.assertEqual(map_tableau_to_m_type("date"), "type date")

    def test_datetime(self):
        self.assertEqual(map_tableau_to_m_type("datetime"), "type datetime")

    def test_case_insensitive(self):
        self.assertEqual(map_tableau_to_m_type("STRING"), "type text")
        self.assertEqual(map_tableau_to_m_type("Integer"), "Int64.Type")

    def test_unknown_defaults_to_text(self):
        self.assertEqual(map_tableau_to_m_type("unknown_type"), "type text")

    def test_currency(self):
        self.assertEqual(map_tableau_to_m_type("currency"), "Currency.Type")


# ═══════════════════════════════════════════════════════════════════════
# Connector Generators
# ═══════════════════════════════════════════════════════════════════════

class TestGeneratePowerQueryM(unittest.TestCase):
    """Test generate_power_query_m for different connector types."""

    def _make_columns(self, *names_types):
        return [{"name": n, "datatype": t} for n, t in names_types]

    def test_sql_server(self):
        conn = {"type": "SQL Server", "details": {"server": "myhost", "database": "mydb"}}
        table = {"name": "Orders", "columns": []}
        result = generate_power_query_m(conn, table)
        self.assertIn("Sql.Database", result)
        self.assertIn("myhost", result)
        self.assertIn("mydb", result)
        self.assertIn("let", result)
        self.assertIn("in", result)

    def test_postgresql(self):
        conn = {"type": "PostgreSQL", "details": {"server": "pghost", "port": "5433", "database": "pgdb"}}
        table = {"name": "Users", "columns": []}
        result = generate_power_query_m(conn, table)
        self.assertIn("PostgreSQL.Database", result)
        self.assertIn("pghost:5433", result)

    def test_csv(self):
        cols = self._make_columns(("Name", "string"), ("Value", "real"))
        conn = {"type": "CSV", "details": {"filename": "data.csv", "delimiter": ","}}
        table = {"name": "Data", "columns": cols}
        result = generate_power_query_m(conn, table)
        self.assertIn("Csv.Document", result)
        self.assertIn("data.csv", result)
        self.assertIn("Table.TransformColumnTypes", result)

    def test_excel(self):
        cols = self._make_columns(("ID", "integer"), ("Amount", "real"))
        conn = {"type": "Excel", "details": {"filename": "report.xlsx"}}
        table = {"name": "Sheet1", "columns": cols}
        result = generate_power_query_m(conn, table)
        self.assertIn("Excel.Workbook", result)
        self.assertIn("report.xlsx", result)

    def test_bigquery(self):
        conn = {"type": "BigQuery", "details": {"project": "proj", "dataset": "ds"}}
        table = {"name": "Events", "columns": []}
        result = generate_power_query_m(conn, table)
        self.assertIn("GoogleBigQuery.Database", result)
        self.assertIn("proj", result)
        self.assertIn("ds", result)

    def test_mysql(self):
        conn = {"type": "MySQL", "details": {"server": "mysqlhost", "database": "shop"}}
        table = {"name": "Products", "columns": []}
        result = generate_power_query_m(conn, table)
        self.assertIn("MySQL.Database", result)
        self.assertIn("mysqlhost", result)

    def test_unknown_type_fallback(self):
        conn = {"type": "UnknownDB", "details": {}}
        table = {"name": "T", "columns": []}
        result = generate_power_query_m(conn, table)
        # Should produce a fallback comment
        self.assertIn("let", result)
        self.assertIn("in", result)

    def test_custom_sql(self):
        conn = {"type": "Custom SQL", "details": {"server": "host", "database": "db"}}
        table = {"name": "Q", "columns": []}
        result = generate_power_query_m(conn, table)
        self.assertIn("let", result)


# ═══════════════════════════════════════════════════════════════════════
# inject_m_steps
# ═══════════════════════════════════════════════════════════════════════

class TestInjectMSteps(unittest.TestCase):
    """Test inject_m_steps — chaining, idempotency, edge cases."""

    _BASE_QUERY = (
        "let\n"
        "    Source = Sql.Database(\"host\", \"db\"),\n"
        "    Result = Source\n"
        "in\n"
        "    Result"
    )

    def test_empty_steps_returns_unchanged(self):
        result = inject_m_steps(self._BASE_QUERY, [])
        self.assertEqual(result, self._BASE_QUERY)

    def test_single_step_injected(self):
        steps = [('#"Renamed Columns"', 'Table.RenameColumns({prev}, {{"A", "B"}})')]
        result = inject_m_steps(self._BASE_QUERY, steps)
        self.assertIn('#"Renamed Columns"', result)
        self.assertIn("Table.RenameColumns(Source", result)
        self.assertIn("Result = #\"Renamed Columns\"", result)
        self.assertTrue(result.endswith("in\n    Result"))

    def test_multiple_steps_chained(self):
        steps = [
            ('#"Step1"', 'Table.SelectRows({prev}, each true)'),
            ('#"Step2"', 'Table.AddColumn({prev}, "X", each 1)'),
        ]
        result = inject_m_steps(self._BASE_QUERY, steps)
        # Step1 references Source
        self.assertIn('Table.SelectRows(Source', result)
        # Step2 references Step1
        self.assertIn('Table.AddColumn(#"Step1"', result)
        # Result references Step2
        self.assertIn('Result = #"Step2"', result)

    def test_prev_placeholder_replaced(self):
        steps = [('#"A"', '{prev}')]
        result = inject_m_steps(self._BASE_QUERY, steps)
        self.assertNotIn("{prev}", result)
        self.assertIn("#\"A\" = Source", result)

    def test_idempotent_double_injection(self):
        steps1 = [('#"First"', 'Table.RemoveColumns({prev}, {{"X"}})')]
        intermediate = inject_m_steps(self._BASE_QUERY, steps1)
        steps2 = [('#"Second"', 'Table.AddColumn({prev}, "Y", each 1)')]
        result = inject_m_steps(intermediate, steps2)
        # Both steps should be present
        self.assertIn('#"First"', result)
        self.assertIn('#"Second"', result)
        # Result references the last step
        self.assertIn('Result = #"Second"', result)

    def test_malformed_query_no_in(self):
        bad = "Source = 42"
        result = inject_m_steps(bad, [('#"X"', 'foo')])
        # Returns unchanged
        self.assertEqual(result, bad)


# ═══════════════════════════════════════════════════════════════════════
# Column Transform Steps
# ═══════════════════════════════════════════════════════════════════════

class TestColumnTransforms(unittest.TestCase):
    """Test column transform step generators."""

    def test_rename(self):
        name, expr = m_transform_rename({"OldName": "NewName"})
        self.assertIn("Renamed Columns", name)
        self.assertIn("Table.RenameColumns", expr)
        self.assertIn("OldName", expr)
        self.assertIn("NewName", expr)
        self.assertIn("{prev}", expr)

    def test_rename_multiple(self):
        name, expr = m_transform_rename({"A": "X", "B": "Y"})
        self.assertIn("A", expr)
        self.assertIn("Y", expr)

    def test_remove_columns(self):
        name, expr = m_transform_remove_columns(["Col1", "Col2"])
        self.assertIn("Removed Columns", name)
        self.assertIn("Table.RemoveColumns", expr)
        self.assertIn("Col1", expr)
        self.assertIn("Col2", expr)

    def test_select_columns(self):
        name, expr = m_transform_select_columns(["A", "B"])
        self.assertIn("Selected Columns", name)
        self.assertIn("Table.SelectColumns", expr)

    def test_duplicate_column(self):
        name, expr = m_transform_duplicate_column("Source", "Copy")
        self.assertIn("Duplicated Column", name)
        self.assertIn("Table.DuplicateColumn", expr)
        self.assertIn("Source", expr)
        self.assertIn("Copy", expr)

    def test_reorder_columns(self):
        name, expr = m_transform_reorder_columns(["C", "B", "A"])
        self.assertIn("Reordered Columns", name)
        self.assertIn("Table.ReorderColumns", expr)

    def test_split_by_delimiter(self):
        name, expr = m_transform_split_by_delimiter("Name", ",")
        self.assertIn("Split Name", name)
        self.assertIn("Table.SplitColumn", expr)
        self.assertIn('Splitter.SplitTextByDelimiter', expr)

    def test_split_by_delimiter_with_parts(self):
        name, expr = m_transform_split_by_delimiter("Name", "-", 3)
        self.assertIn("3", expr)

    def test_merge_columns(self):
        name, expr = m_transform_merge_columns(["First", "Last"], "FullName", " ")
        self.assertIn("Merged Columns", name)
        self.assertIn("Table.CombineColumns", expr)
        self.assertIn("FullName", expr)


# ═══════════════════════════════════════════════════════════════════════
# Value Transform Steps
# ═══════════════════════════════════════════════════════════════════════

class TestValueTransforms(unittest.TestCase):
    """Test value transform step generators."""

    def test_replace_value_text(self):
        name, expr = m_transform_replace_value("Col", "old", "new")
        self.assertIn("Replaced Values", name)
        self.assertIn("Table.ReplaceValue", expr)
        self.assertIn("Replacer.ReplaceText", expr)

    def test_replace_value_not_text(self):
        name, expr = m_transform_replace_value("Col", 0, 1, replace_text=False)
        self.assertIn("Replacer.ReplaceValue", expr)

    def test_replace_nulls(self):
        name, expr = m_transform_replace_nulls("Sales", 0)
        self.assertIn("Replaced Nulls", name)
        self.assertIn("null", expr)

    def test_replace_nulls_string(self):
        name, expr = m_transform_replace_nulls("Name", "N/A")
        self.assertIn('"N/A"', expr)

    def test_trim(self):
        name, expr = m_transform_trim(["Name", "City"])
        self.assertIn("Trimmed Text", name)
        self.assertIn("Text.Trim", expr)
        self.assertIn("Name", expr)
        self.assertIn("City", expr)

    def test_clean(self):
        name, expr = m_transform_clean(["Notes"])
        self.assertIn("Cleaned Text", name)
        self.assertIn("Text.Clean", expr)

    def test_upper(self):
        name, expr = m_transform_upper(["Name"])
        self.assertIn("Uppercased", name)
        self.assertIn("Text.Upper", expr)

    def test_lower(self):
        name, expr = m_transform_lower(["Name"])
        self.assertIn("Lowercased", name)
        self.assertIn("Text.Lower", expr)

    def test_proper_case(self):
        name, expr = m_transform_proper_case(["Name"])
        self.assertIn("Proper Cased", name)
        self.assertIn("Text.Proper", expr)

    def test_fill_down(self):
        name, expr = m_transform_fill_down(["Region"])
        self.assertIn("Filled Down", name)
        self.assertIn("Table.FillDown", expr)

    def test_fill_up(self):
        name, expr = m_transform_fill_up(["Region"])
        self.assertIn("Filled Up", name)
        self.assertIn("Table.FillUp", expr)


# ═══════════════════════════════════════════════════════════════════════
# Filter Transform Steps
# ═══════════════════════════════════════════════════════════════════════

class TestFilterTransforms(unittest.TestCase):
    """Test filter transform step generators."""

    def test_filter_single_value(self):
        name, expr = m_transform_filter_values("Status", ["Active"])
        self.assertIn("Filtered Rows", name)
        self.assertIn("Table.SelectRows", expr)
        self.assertIn('"Active"', expr)
        # Single value uses = operator
        self.assertIn("=", expr)

    def test_filter_multiple_values(self):
        name, expr = m_transform_filter_values("Status", ["Active", "Pending"])
        self.assertIn("List.Contains", expr)

    def test_exclude_single_value(self):
        name, expr = m_transform_exclude_values("Status", ["Closed"])
        self.assertIn("Excluded Rows", name)
        self.assertIn("<>", expr)

    def test_exclude_multiple_values(self):
        name, expr = m_transform_exclude_values("Status", ["Closed", "Cancelled"])
        self.assertIn("not List.Contains", expr)

    def test_filter_range_min_only(self):
        name, expr = m_transform_filter_range("Sales", min_val=100)
        self.assertIn("Filtered Range", name)
        self.assertIn(">= 100", expr)

    def test_filter_range_max_only(self):
        name, expr = m_transform_filter_range("Sales", max_val=500)
        self.assertIn("<= 500", expr)

    def test_filter_range_both(self):
        name, expr = m_transform_filter_range("Sales", min_val=100, max_val=500)
        self.assertIn(">= 100", expr)
        self.assertIn("<= 500", expr)

    def test_filter_nulls_exclude(self):
        name, expr = m_transform_filter_nulls("Col")
        self.assertIn("Filtered Nulls", name)
        self.assertIn("<> null", expr)

    def test_filter_nulls_keep(self):
        name, expr = m_transform_filter_nulls("Col", keep_nulls=True)
        self.assertIn("= null", expr)

    def test_filter_contains(self):
        name, expr = m_transform_filter_contains("Name", "Corp")
        self.assertIn("Filtered Contains", name)
        self.assertIn("Text.Contains", expr)
        self.assertIn("Corp", expr)

    def test_distinct_all(self):
        name, expr = m_transform_distinct()
        self.assertIn("Removed Duplicates", name)
        self.assertIn("Table.Distinct", expr)

    def test_distinct_specific_columns(self):
        name, expr = m_transform_distinct(["ID", "Name"])
        self.assertIn("Table.Distinct", expr)
        self.assertIn("ID", expr)

    def test_top_n_descending(self):
        name, expr = m_transform_top_n(10, "Sales", descending=True)
        self.assertIn("Top N", name)
        self.assertIn("Table.FirstN", expr)
        self.assertIn("Order.Descending", expr)

    def test_top_n_ascending(self):
        name, expr = m_transform_top_n(5, "Date", descending=False)
        self.assertIn("Order.Ascending", expr)


# ═══════════════════════════════════════════════════════════════════════
# Aggregate Transform Steps
# ═══════════════════════════════════════════════════════════════════════

class TestAggregateTransform(unittest.TestCase):
    """Test aggregate / group-by transform."""

    def test_sum_aggregation(self):
        name, expr = m_transform_aggregate(
            ["Region"],
            [{"name": "TotalSales", "column": "Sales", "agg": "sum"}]
        )
        self.assertIn("Grouped Rows", name)
        self.assertIn("Table.Group", expr)
        self.assertIn("List.Sum", expr)
        self.assertIn("TotalSales", expr)

    def test_count_aggregation(self):
        name, expr = m_transform_aggregate(
            ["Category"],
            [{"name": "Count", "column": "ID", "agg": "count"}]
        )
        self.assertIn("Table.RowCount", expr)

    def test_countd_aggregation(self):
        name, expr = m_transform_aggregate(
            ["Category"],
            [{"name": "UniqueCount", "column": "Customer", "agg": "countd"}]
        )
        self.assertIn("List.Distinct", expr)
        self.assertIn("List.Count", expr)

    def test_average_aggregation(self):
        name, expr = m_transform_aggregate(
            ["Region"],
            [{"name": "AvgSales", "column": "Sales", "agg": "avg"}]
        )
        self.assertIn("List.Average", expr)

    def test_multiple_aggregations(self):
        name, expr = m_transform_aggregate(
            ["Region", "Category"],
            [
                {"name": "Total", "column": "Sales", "agg": "sum"},
                {"name": "Avg", "column": "Sales", "agg": "average"},
            ]
        )
        self.assertIn("List.Sum", expr)
        self.assertIn("List.Average", expr)

    def test_min_max_aggregation(self):
        name, expr = m_transform_aggregate(
            ["Year"],
            [
                {"name": "MinVal", "column": "Value", "agg": "min"},
                {"name": "MaxVal", "column": "Value", "agg": "max"},
            ]
        )
        self.assertIn("List.Min", expr)
        self.assertIn("List.Max", expr)


# ═══════════════════════════════════════════════════════════════════════
# Pivot / Unpivot Transform Steps
# ═══════════════════════════════════════════════════════════════════════

class TestPivotTransforms(unittest.TestCase):
    """Test pivot and unpivot transforms."""

    def test_unpivot(self):
        name, expr = m_transform_unpivot(["Q1", "Q2", "Q3", "Q4"])
        self.assertIn("Unpivoted Columns", name)
        self.assertIn("Table.Unpivot", expr)
        self.assertIn("Attribute", expr)
        self.assertIn("Value", expr)

    def test_unpivot_custom_names(self):
        name, expr = m_transform_unpivot(["A", "B"], "Quarter", "Amount")
        self.assertIn("Quarter", expr)
        self.assertIn("Amount", expr)

    def test_unpivot_other(self):
        name, expr = m_transform_unpivot_other(["ID", "Name"])
        self.assertIn("Unpivoted Other Columns", name)
        self.assertIn("Table.UnpivotOtherColumns", expr)

    def test_pivot(self):
        name, expr = m_transform_pivot("Category", "Amount")
        self.assertIn("Pivoted Column", name)
        self.assertIn("Table.Pivot", expr)
        self.assertIn("Category", expr)
        self.assertIn("Amount", expr)


# ═══════════════════════════════════════════════════════════════════════
# Join Transform Steps
# ═══════════════════════════════════════════════════════════════════════

class TestJoinTransform(unittest.TestCase):
    """Test join transform."""

    def test_left_join_returns_list(self):
        result = m_transform_join("RightTable", ["ID"], ["ID"], "left")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)  # No expansion
        name, expr = result[0]
        self.assertIn("Joined", name)
        self.assertIn("Table.NestedJoin", expr)
        self.assertIn("JoinKind.LeftOuter", expr)

    def test_inner_join(self):
        result = m_transform_join("RightTable", ["ID"], ["ID"], "inner")
        name, expr = result[0]
        self.assertIn("JoinKind.Inner", expr)

    def test_full_join(self):
        result = m_transform_join("RightTable", ["ID"], ["ID"], "full")
        name, expr = result[0]
        self.assertIn("JoinKind.FullOuter", expr)

    def test_join_with_expansion(self):
        result = m_transform_join(
            "RightTable", ["ID"], ["ID"], "left",
            expand_columns=["Name", "Value"]
        )
        self.assertEqual(len(result), 2)  # join + expand
        expand_name, expand_expr = result[1]
        self.assertIn("Expanded", expand_name)
        self.assertIn("Table.ExpandTableColumn", expand_expr)
        self.assertIn("Name", expand_expr)

    def test_multi_key_join(self):
        result = m_transform_join("Ref", ["A", "B"], ["X", "Y"], "inner")
        name, expr = result[0]
        self.assertIn('"A"', expr)
        self.assertIn('"B"', expr)


# ═══════════════════════════════════════════════════════════════════════
# Union Transform Steps
# ═══════════════════════════════════════════════════════════════════════

class TestUnionTransforms(unittest.TestCase):
    """Test union transforms."""

    def test_union(self):
        name, expr = m_transform_union(["Table1", "Table2", "Table3"])
        self.assertIn("Combined Tables", name)
        self.assertIn("Table.Combine", expr)
        self.assertIn("Table1", expr)
        self.assertIn("Table3", expr)

    def test_wildcard_union(self):
        result = m_transform_wildcard_union("C:/Data/Folder", ".csv", ",")
        self.assertIsInstance(result, str)
        self.assertIn("Folder.Files", result)
        self.assertIn("Csv.Document", result)
        self.assertIn("C:\\Data\\Folder", result)


# ═══════════════════════════════════════════════════════════════════════
# Reshape Transform Steps
# ═══════════════════════════════════════════════════════════════════════

class TestReshapeTransforms(unittest.TestCase):
    """Test reshape transform steps."""

    def test_sort_ascending(self):
        name, expr = m_transform_sort([("Name", False)])
        self.assertIn("Sorted Rows", name)
        self.assertIn("Table.Sort", expr)
        self.assertIn("Order.Ascending", expr)

    def test_sort_descending(self):
        name, expr = m_transform_sort([("Sales", True)])
        self.assertIn("Order.Descending", expr)

    def test_sort_multiple(self):
        name, expr = m_transform_sort([("Region", False), ("Sales", True)])
        self.assertIn("Region", expr)
        self.assertIn("Sales", expr)

    def test_transpose(self):
        name, expr = m_transform_transpose()
        self.assertIn("Transposed Table", name)
        self.assertIn("Table.Transpose", expr)

    def test_add_index_defaults(self):
        name, expr = m_transform_add_index()
        self.assertIn("Added Index", name)
        self.assertIn("Table.AddIndexColumn", expr)
        self.assertIn('"Index"', expr)

    def test_add_index_custom(self):
        name, expr = m_transform_add_index("RowNum", 0, 1)
        self.assertIn("RowNum", expr)

    def test_skip_rows(self):
        name, expr = m_transform_skip_rows(5)
        self.assertIn("Skipped Rows", name)
        self.assertIn("Table.Skip", expr)
        self.assertIn("5", expr)

    def test_remove_last_rows(self):
        name, expr = m_transform_remove_last_rows(3)
        self.assertIn("Removed Last Rows", name)
        self.assertIn("Table.RemoveLastN", expr)

    def test_remove_errors(self):
        name, expr = m_transform_remove_errors()
        self.assertIn("Removed Errors", name)
        self.assertIn("Table.RemoveRowsWithErrors", expr)

    def test_promote_headers(self):
        name, expr = m_transform_promote_headers()
        self.assertIn("Promoted Headers", name)
        self.assertIn("Table.PromoteHeaders", expr)

    def test_demote_headers(self):
        name, expr = m_transform_demote_headers()
        self.assertIn("Demoted Headers", name)
        self.assertIn("Table.DemoteHeaders", expr)


# ═══════════════════════════════════════════════════════════════════════
# Calculated Column Transform Steps
# ═══════════════════════════════════════════════════════════════════════

class TestCalculatedTransforms(unittest.TestCase):
    """Test calculated column transforms."""

    def test_add_column(self):
        name, expr = m_transform_add_column("Total", "each [Price] * [Qty]")
        self.assertIn("Added Total", name)
        self.assertIn("Table.AddColumn", expr)
        self.assertIn("Total", expr)
        self.assertIn("[Price] * [Qty]", expr)

    def test_add_column_with_type(self):
        name, expr = m_transform_add_column("N", "each 1", "type number")
        self.assertIn("type number", expr)

    def test_conditional_column(self):
        name, expr = m_transform_conditional_column(
            "Tier",
            [('[Sales] > 1000', '"High"'), ('[Sales] > 500', '"Medium"')],
            '"Low"'
        )
        self.assertIn("Added Tier", name)
        self.assertIn("Table.AddColumn", expr)
        self.assertIn("if", expr)
        self.assertIn("then", expr)
        self.assertIn("else", expr)
        self.assertIn('"High"', expr)
        self.assertIn('"Low"', expr)

    def test_conditional_column_null_default(self):
        name, expr = m_transform_conditional_column(
            "Flag",
            [('[Active] = true', '"Yes"')],
            None
        )
        self.assertIn("null", expr)


# ═══════════════════════════════════════════════════════════════════════
# Step format — all transforms return (name, expr) with {prev}
# ═══════════════════════════════════════════════════════════════════════

class TestStepFormat(unittest.TestCase):
    """Verify all transform functions produce correct tuple format."""

    def _check_step(self, step):
        """Assert step is a tuple with (str_name, str_expr_with_prev)."""
        self.assertIsInstance(step, tuple, f"Expected tuple but got {type(step)}")
        self.assertEqual(len(step), 2)
        name, expr = step
        self.assertIsInstance(name, str)
        self.assertIsInstance(expr, str)
        self.assertIn("{prev}", expr, f"Expression should contain {{prev}}: {expr}")

    def test_rename_format(self):
        self._check_step(m_transform_rename({"A": "B"}))

    def test_remove_columns_format(self):
        self._check_step(m_transform_remove_columns(["X"]))

    def test_filter_values_format(self):
        self._check_step(m_transform_filter_values("C", ["V"]))

    def test_aggregate_format(self):
        self._check_step(m_transform_aggregate(
            ["G"], [{"name": "S", "column": "V", "agg": "sum"}]
        ))

    def test_unpivot_format(self):
        self._check_step(m_transform_unpivot(["A"]))

    def test_sort_format(self):
        self._check_step(m_transform_sort([("A", True)]))

    def test_add_column_format(self):
        self._check_step(m_transform_add_column("N", "each 1"))

    def test_distinct_format(self):
        self._check_step(m_transform_distinct())

    def test_transpose_format(self):
        self._check_step(m_transform_transpose())

    def test_skip_rows_format(self):
        self._check_step(m_transform_skip_rows(1))


# ═══════════════════════════════════════════════════════════════════════
# Integration: inject transforms into generated M query
# ═══════════════════════════════════════════════════════════════════════

class TestInjectTransformIntegration(unittest.TestCase):
    """End-to-end: generate query then inject transforms."""

    def test_csv_with_rename_and_filter(self):
        conn = {"type": "CSV", "details": {"filename": "data.csv"}}
        cols = [{"name": "Name", "datatype": "string"}, {"name": "Sales", "datatype": "real"}]
        table = {"name": "Data", "columns": cols}

        base = generate_power_query_m(conn, table)
        steps = [
            m_transform_rename({"Name": "CustomerName"}),
            m_transform_filter_values("CustomerName", ["Alice", "Bob"]),
        ]
        result = inject_m_steps(base, steps)

        self.assertIn("Csv.Document", result)
        self.assertIn("Table.RenameColumns", result)
        self.assertIn("Table.SelectRows", result)
        self.assertIn("Result = #\"Filtered Rows\"", result)
        self.assertTrue(result.strip().endswith("Result"))

    def test_sql_with_aggregate_and_sort(self):
        conn = {"type": "SQL Server", "details": {"server": "s", "database": "d"}}
        table = {"name": "Orders", "columns": []}

        base = generate_power_query_m(conn, table)
        steps = [
            m_transform_aggregate(
                ["Region"],
                [{"name": "Total", "column": "Sales", "agg": "sum"}]
            ),
            m_transform_sort([("Total", True)]),
        ]
        result = inject_m_steps(base, steps)

        self.assertIn("Sql.Database", result)
        self.assertIn("Table.Group", result)
        self.assertIn("Table.Sort", result)

    def test_join_steps_injected(self):
        base = (
            "let\n"
            "    Source = Sql.Database(\"h\", \"d\"),\n"
            "    Result = Source\n"
            "in\n"
            "    Result"
        )
        join_steps = m_transform_join(
            "LookupTable", ["ID"], ["ID"], "left",
            expand_columns=["Name"]
        )
        result = inject_m_steps(base, join_steps)
        self.assertIn("Table.NestedJoin", result)
        self.assertIn("Table.ExpandTableColumn", result)


# ═══════════════════════════════════════════════════════════════════════
# Sprint 18 — Custom SQL Params, Query Folding, Buffer
# ═══════════════════════════════════════════════════════════════════════

class TestCustomSqlParamBinding(unittest.TestCase):
    """Test custom SQL with parameter binding via Value.NativeQuery."""

    def test_custom_sql_with_params(self):
        conn = {"type": "Custom SQL", "details": {
            "server": "host", "database": "db",
            "params": {"Region": "West", "Year": "2024"}
        }}
        table = {"name": "Q", "columns": []}
        result = generate_power_query_m(conn, table)
        self.assertIn("Value.NativeQuery", result)
        self.assertIn('Region="West"', result)
        self.assertIn('Year="2024"', result)
        self.assertIn("EnableFolding=true", result)

    def test_custom_sql_without_params(self):
        conn = {"type": "Custom SQL", "details": {
            "server": "host", "database": "db"
        }}
        table = {"name": "Q", "columns": []}
        result = generate_power_query_m(conn, table)
        self.assertNotIn("Value.NativeQuery", result)
        self.assertIn("Sql.Database", result)

    def test_custom_sql_empty_params(self):
        conn = {"type": "Custom SQL", "details": {
            "server": "host", "database": "db", "params": {}
        }}
        table = {"name": "Q", "columns": []}
        result = generate_power_query_m(conn, table)
        self.assertNotIn("Value.NativeQuery", result)


class TestQueryFoldingBuffer(unittest.TestCase):
    """Test Table.Buffer for query folding hints."""

    def test_buffer_standalone(self):
        step_name, step_expr = m_transform_buffer()
        self.assertEqual(step_name, '#"Buffered Table"')
        self.assertIn("Table.Buffer({prev})", step_expr)

    def test_buffer_with_ref(self):
        step_name, step_expr = m_transform_buffer("LookupTable")
        self.assertIn("Table.Buffer(LookupTable)", step_expr)

    def test_join_with_buffer_right(self):
        steps = m_transform_join(
            "LookupTable", ["ID"], ["ID"], "left",
            buffer_right=True
        )
        self.assertEqual(len(steps), 1)
        self.assertIn("Table.Buffer(LookupTable)", steps[0][1])
        self.assertIn("Table.NestedJoin", steps[0][1])

    def test_join_without_buffer_right(self):
        steps = m_transform_join(
            "LookupTable", ["ID"], ["ID"], "left",
            buffer_right=False
        )
        self.assertNotIn("Table.Buffer", steps[0][1])

    def test_buffer_injected_into_query(self):
        base = (
            "let\n"
            "    Source = Sql.Database(\"h\", \"d\"),\n"
            "    Result = Source\n"
            "in\n"
            "    Result"
        )
        buf_step = m_transform_buffer()
        result = inject_m_steps(base, [buf_step])
        self.assertIn("Table.Buffer(Source)", result)


# ═══════════════════════════════════════════════════════════════════════
# sqlproxy / Tableau Server Published Datasource
# ═══════════════════════════════════════════════════════════════════════

class TestSqlproxyConnector(unittest.TestCase):
    """Tests for the sqlproxy (Tableau Server) connector."""

    def _make_columns(self, *names_types):
        return [{"name": n, "datatype": t} for n, t in names_types]

    def test_sqlproxy_generates_valid_m(self):
        conn = {
            "type": "Tableau Server",
            "details": {
                "server": "si-mytableau.edf.fr",
                "port": "443",
                "dbname": "E_Formation_courbe_puissance",
                "channel": "https",
                "server_ds_name": "E_Formation_courbe_puissance",
            },
        }
        cols = self._make_columns(("Region", "string"), ("Value", "real"))
        table = {"name": "Extract", "columns": cols}
        result = generate_power_query_m(conn, table)
        self.assertIn("let", result)
        self.assertIn("in", result)
        self.assertIn("Tableau Server Published Datasource", result)
        self.assertIn("si-mytableau.edf.fr", result)
        self.assertIn("E_Formation_courbe_puissance", result)
        # Should contain connection templates
        self.assertIn("SQL Server", result)
        self.assertIn("Oracle", result)
        self.assertIn("PostgreSQL", result)
        # Should have sample data (not empty fallback)
        self.assertIn("#table(", result)
        self.assertIn('"Region"', result)

    def test_sqlproxy_via_type_key(self):
        """sqlproxy and SQLPROXY type keys should also work."""
        conn = {"type": "sqlproxy", "details": {"server": "tab.co", "dbname": "ds1"}}
        table = {"name": "T1", "columns": self._make_columns(("A", "string"))}
        result = generate_power_query_m(conn, table)
        self.assertIn("Tableau Server Published Datasource", result)

    def test_sqlproxy_no_trailing_comma(self):
        """Generated M must not have a comma before 'in'."""
        conn = {"type": "Tableau Server", "details": {"server": "s", "dbname": "d"}}
        cols = self._make_columns(("X", "integer"))
        table = {"name": "T", "columns": cols}
        result = generate_power_query_m(conn, table)
        # Find the line before 'in' — it should not end with a comma
        lines = result.strip().split('\n')
        for i, line in enumerate(lines):
            if line.strip() == 'in':
                prev = lines[i - 1].rstrip()
                self.assertFalse(prev.endswith(','),
                                 f"Line before 'in' ends with comma: {prev!r}")

    def test_sqlproxy_empty_columns(self):
        conn = {"type": "Tableau Server", "details": {"server": "s"}}
        table = {"name": "T", "columns": []}
        result = generate_power_query_m(conn, table)
        self.assertIn("let", result)
        self.assertIn("in", result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
