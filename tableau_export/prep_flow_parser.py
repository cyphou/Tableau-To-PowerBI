"""
Tableau Prep Flow Parser (.tfl / .tflx)

Parses Tableau Prep flow files and converts them to Power Query M expressions
using the transform generators from m_query_builder.py.

Tableau Prep flows are JSON files (not XML like .twb) with:
- nodes: dict of step nodes (input, transform, output) forming a DAG
- connections: dict of data source connection definitions

Supported step types:
- Input: LoadCsv, LoadExcel, LoadSql, LoadJson, LoadHyper, LoadGoogle
- Clean (SuperTransform): RenameColumn, RemoveColumn, DuplicateColumn,
  ChangeColumnType, FilterOperation, FilterValues, FilterRange,
  ReplaceValues, SplitColumn, MergeColumns, AddColumn, CleanOperation,
  FillValues, ReplaceNulls, ConditionalColumn, GroupReplace
- Aggregate: groupByFields + aggregateFields
- Join: inner, left, right, full, leftOnly, rightOnly
- Union: automatic or manual field mapping
- Pivot: columnsToRows (unpivot), rowsToColumns (pivot)
- Output: PublishExtract, SaveToFile, SaveToDatabase
"""

import logging
import os
import json

logger = logging.getLogger(__name__)
import zipfile
import re
from collections import OrderedDict

# Import M query generators
import sys
sys.path.insert(0, os.path.dirname(__file__))
from m_query_builder import (
    generate_power_query_m,
    generate_m_from_hyper,
    inject_m_steps,
    m_transform_rename,
    m_transform_remove_columns,
    m_transform_select_columns,
    m_transform_duplicate_column,
    m_transform_split_by_delimiter,
    m_transform_merge_columns,
    m_transform_replace_value,
    m_transform_replace_nulls,
    m_transform_trim,
    m_transform_clean,
    m_transform_upper,
    m_transform_lower,
    m_transform_proper_case,
    m_transform_fill_down,
    m_transform_fill_up,
    m_transform_filter_values,
    m_transform_exclude_values,
    m_transform_filter_range,
    m_transform_filter_nulls,
    m_transform_filter_contains,
    m_transform_distinct,
    m_transform_top_n,
    m_transform_aggregate,
    m_transform_unpivot,
    m_transform_unpivot_other,
    m_transform_pivot,
    m_transform_join,
    m_transform_union,
    m_transform_sort,
    m_transform_add_column,
    m_transform_conditional_column,
    m_transform_add_index,
    m_transform_promote_headers,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  TABLEAU PREP TYPE MAPPINGS
# ═══════════════════════════════════════════════════════════════════════════════

# Prep connection class → m_query_builder connection type
_PREP_CONNECTION_MAP = {
    'csv': 'textscan',
    'excel': 'excel-direct',
    'excel-direct': 'excel-direct',
    'sqlserver': 'sqlserver',
    'postgres': 'postgres',
    'mysql': 'mysql',
    'oracle': 'oracle',
    'bigquery': 'bigquery',
    'snowflake': 'snowflake',
    'redshift': 'redshift',
    'teradata': 'teradata',
    'saphana': 'saphana',
    'databricks': 'databricks',
    'spark': 'spark',
    'json': 'json',
    'hyper': 'hyper',
    'google-sheets': 'google-sheets',
    'salesforce': 'salesforce',
    'azure_sql_dw': 'azure_sql_dw',
    'odata': 'OData',
    'google-analytics': 'Google Analytics',
    'azure-blob': 'Azure Blob',
    'adls': 'ADLS',
    'wasbs': 'Azure Blob Storage',
}

# Prep data type → Power Query M type
_PREP_TYPE_MAP = {
    'string': 'text',
    'integer': 'number',
    'real': 'number',
    'date': 'date',
    'datetime': 'datetime',
    'boolean': 'logical',
}

# Prep aggregation → m_transform_aggregate aggregation key
_PREP_AGG_MAP = {
    'SUM': 'sum',
    'AVG': 'avg',
    'MEDIAN': 'median',
    'COUNT': 'count',
    'COUNTD': 'countd',
    'MIN': 'min',
    'MAX': 'max',
    'STDEV': 'stdev',
    'STDEVP': 'stdev',
    'VAR': 'var',
    'VARP': 'varp',
}

# Prep join type → m_transform_join join kind
_PREP_JOIN_MAP = {
    'inner': 'inner',
    'left': 'left',
    'right': 'right',
    'full': 'full',
    'leftOnly': 'leftanti',
    'rightOnly': 'rightanti',
    'notInner': 'leftanti',  # exclusive left (Tableau "not inner")
}


# ═══════════════════════════════════════════════════════════════════════════════
#  FLOW FILE READER
# ═══════════════════════════════════════════════════════════════════════════════

def _read_tflx_zip(filepath):
    """Extract and parse the flow JSON from inside a .tflx ZIP archive.

    Tableau Prep saves flow data in ZIP archives. The flow JSON can be
    stored as a file named ``*.tfl`` or simply ``flow`` (no extension).
    """
    with zipfile.ZipFile(filepath, 'r') as z:
        names = z.namelist()
        # Prefer a file ending in .tfl
        for name in names:
            if name.endswith('.tfl'):
                with z.open(name) as f:
                    return json.loads(f.read().decode('utf-8'))
        # Fallback: look for a file named 'flow' (Prep 2020.3+ format)
        if 'flow' in names:
            with z.open('flow') as f:
                return json.loads(f.read().decode('utf-8'))
    raise ValueError(f"No .tfl or 'flow' entry found inside {filepath}")


def read_prep_flow(filepath):
    """
    Read a Tableau Prep flow file (.tfl or .tflx) and return the parsed JSON.

    Auto-detects ZIP archives even when the file has a .tfl extension
    (some Prep exports save .tflx content with a .tfl extension).

    Args:
        filepath: Path to .tfl or .tflx file

    Returns:
        dict: Parsed flow JSON with 'nodes' and 'connections'
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.tflx':
        return _read_tflx_zip(filepath)

    if ext == '.tfl':
        # Auto-detect ZIP archives saved with .tfl extension
        if zipfile.is_zipfile(filepath):
            return _read_tflx_zip(filepath)
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    raise ValueError(f"Unsupported file extension: {ext} (expected .tfl or .tflx)")


# ═══════════════════════════════════════════════════════════════════════════════
#  FLOW GRAPH TRAVERSAL
# ═══════════════════════════════════════════════════════════════════════════════

def _get_node_type(node):
    """Extract the semantic node type from the versioned nodeType string.

    e.g. '.v2018_3_3.SuperTransform' → 'SuperTransform'
         '.v1.LoadCsv' → 'LoadCsv'
    """
    node_type = node.get('nodeType', '')
    parts = node_type.rsplit('.', 1)
    return parts[-1] if parts else node_type


def _topological_sort(nodes):
    """
    Topological sort of flow nodes (DAG traversal).

    Returns:
        list of node IDs in execution order (inputs first, outputs last)
    """
    # Build adjacency: node_id → [next_node_ids]
    graph = {}
    in_degree = {}

    for nid, node in nodes.items():
        if nid not in graph:
            graph[nid] = []
        if nid not in in_degree:
            in_degree[nid] = 0

        for edge in node.get('nextNodes', []):
            next_id = edge.get('nextNodeId', '')
            if next_id:
                graph[nid].append(next_id)
                if next_id not in graph:
                    graph[next_id] = []
                in_degree[next_id] = in_degree.get(next_id, 0) + 1

    # Kahn's algorithm
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    sorted_ids = []

    while queue:
        nid = queue.pop(0)
        sorted_ids.append(nid)
        for next_id in graph.get(nid, []):
            in_degree[next_id] -= 1
            if in_degree[next_id] == 0:
                queue.append(next_id)

    return sorted_ids


def _find_upstream_nodes(nodes, node_id):
    """Find all node IDs that have nextNodes pointing to node_id."""
    upstream = []
    for nid, node in nodes.items():
        for edge in node.get('nextNodes', []):
            if edge.get('nextNodeId') == node_id:
                upstream.append(nid)
    return upstream


# ═══════════════════════════════════════════════════════════════════════════════
#  INPUT NODE → CONNECTION + TABLE
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_input_node(node, connections):
    """
    Parse an input node into a connection dict and table dict
    compatible with generate_power_query_m().

    Returns:
        (connection_dict, table_dict)
    """
    conn_id = node.get('connectionId', '')
    conn_def = connections.get(conn_id, {})
    conn_attrs = conn_def.get('connectionAttributes', {})
    node_conn_attrs = node.get('connectionAttributes', {})

    # Merge connection-level and node-level attributes
    all_attrs = {**conn_attrs, **node_conn_attrs}

    # Map Prep connection class to m_query_builder type
    conn_class = all_attrs.get('class', '').lower()
    conn_type = _PREP_CONNECTION_MAP.get(conn_class, conn_class)

    # Build table name
    table_name = node.get('name', 'Table')
    db_table = all_attrs.get('table', table_name)

    # Build columns from fields
    columns = []
    for field in node.get('fields', []):
        columns.append({
            'name': field.get('name', ''),
            'datatype': field.get('type', 'string'),
        })

    # Build connection dict for m_query_builder
    connection = {
        'type': conn_type,
        'details': {
            'server': all_attrs.get('server', ''),
            'port': all_attrs.get('port', ''),
            'database': all_attrs.get('dbname', all_attrs.get('database', '')),
            'schema': all_attrs.get('schema', ''),
            'filename': all_attrs.get('filename', ''),
            'directory': all_attrs.get('directory', ''),
            'warehouse': all_attrs.get('warehouse', ''),
            'project': all_attrs.get('project', ''),
            'dataset': all_attrs.get('dataset', ''),
        }
    }

    table = {
        'name': db_table,
        'columns': columns,
    }

    return connection, table


# ═══════════════════════════════════════════════════════════════════════════════
#  CLEAN STEP (SuperTransform) → M STEPS
# ═══════════════════════════════════════════════════════════════════════════════

# Pre-compiled patterns for Prep expression → M conversion
_RE_IF = re.compile(r'\bIF\b', re.IGNORECASE)
_RE_THEN = re.compile(r'\bTHEN\b', re.IGNORECASE)
_RE_ELSE = re.compile(r'\bELSE\b', re.IGNORECASE)
_RE_ELSEIF = re.compile(r'\bELSEIF\b', re.IGNORECASE)
_RE_END = re.compile(r'(?<!\[)\bEND\b(?!\s*\w*\])', re.IGNORECASE)
_RE_AND = re.compile(r'\bAND\b', re.IGNORECASE)
_RE_OR = re.compile(r'\bOR\b', re.IGNORECASE)
_RE_NOT = re.compile(r'\bNOT\b', re.IGNORECASE)
_RE_ISNULL = re.compile(r'\bISNULL\s*\(', re.IGNORECASE)
_RE_CONTAINS = re.compile(r'\bCONTAINS\s*\(', re.IGNORECASE)
_RE_LEN = re.compile(r'\bLEN\s*\(', re.IGNORECASE)
_RE_UPPER = re.compile(r'\bUPPER\s*\(', re.IGNORECASE)
_RE_LOWER = re.compile(r'\bLOWER\s*\(', re.IGNORECASE)
_RE_TRIM = re.compile(r'\bTRIM\s*\(', re.IGNORECASE)
_RE_LEFT = re.compile(r'\bLEFT\s*\(', re.IGNORECASE)
_RE_RIGHT = re.compile(r'\bRIGHT\s*\(', re.IGNORECASE)


def _convert_prep_expression_to_m(expression):
    """
    Convert a Tableau Prep calculation expression to a Power Query M expression.

    Simple conversions for common patterns. Complex formulas may need manual review.
    """
    if not expression:
        return '""'

    expr = expression.strip()

    # Basic column references: [Column] → [Column] (same in M for row context)
    # Tableau Prep IF/THEN/ELSE → M if/then/else (pre-compiled patterns)
    expr = _RE_ELSEIF.sub('else if', expr)  # ELSEIF before ELSE/IF
    expr = _RE_IF.sub('if', expr)
    expr = _RE_THEN.sub('then', expr)
    expr = _RE_ELSE.sub('else', expr)
    expr = _RE_END.sub('', expr)
    expr = _RE_AND.sub('and', expr)
    expr = _RE_OR.sub('or', expr)
    expr = _RE_NOT.sub('not', expr)

    # Comparison operators
    expr = expr.replace('!=', '<>')
    expr = expr.replace('==', '=')

    # NULL handling
    expr = _RE_ISNULL.sub('(null = ', expr)

    # String functions
    expr = _RE_CONTAINS.sub('Text.Contains(', expr)
    expr = _RE_LEN.sub('Text.Length(', expr)
    expr = _RE_UPPER.sub('Text.Upper(', expr)
    expr = _RE_LOWER.sub('Text.Lower(', expr)
    expr = _RE_TRIM.sub('Text.Trim(', expr)
    expr = _RE_LEFT.sub('Text.Start(', expr)
    expr = _RE_RIGHT.sub('Text.End(', expr)

    return expr


def _parse_clean_actions(node):
    """
    Parse SuperTransform actions into M transformation steps.

    Consecutive RenameColumn actions are batched into a single
    Table.RenameColumns step for cleaner M output.

    Returns:
        list of (step_name, step_expression) tuples
    """
    steps = []
    action_group = node.get('beforeActionGroup', node.get('actionGroup', {}))
    actions = list(action_group.get('actions', []))

    # Also check afterActionGroup
    after_group = node.get('afterActionGroup', {})
    actions.extend(after_group.get('actions', []))

    # Track step counter for unique step names
    step_counter = {}

    # Batch consecutive renames
    pending_renames = {}

    def flush_renames():
        """Emit a batched rename step if any are pending."""
        if pending_renames:
            steps.append(m_transform_rename(dict(pending_renames)))
            pending_renames.clear()

    for action in actions:
        action_type = action.get('actionType', '')
        # Extract semantic type: '.v1.RenameColumn' → 'RenameColumn'
        sem_type = action_type.rsplit('.', 1)[-1] if '.' in action_type else action_type

        if sem_type == 'RenameColumn':
            old_name = action.get('columnName', '')
            new_name = action.get('newColumnName', '')
            if old_name and new_name:
                pending_renames[old_name] = new_name
            continue

        # Flush any pending renames before processing a non-rename action
        flush_renames()

        step = _convert_action_to_m_step(sem_type, action, step_counter)
        if step:
            if isinstance(step, list):
                steps.extend(step)
            else:
                steps.append(step)

    # Flush any trailing renames
    flush_renames()

    return steps


def _convert_action_to_m_step(action_type, action, counter):
    """
    Convert a single Prep action to an M transformation step.

    Returns:
        (step_name, step_expression) tuple, list of tuples, or None
    """

    if action_type == 'RenameColumn':
        old_name = action.get('columnName', '')
        new_name = action.get('newColumnName', '')
        if old_name and new_name:
            return m_transform_rename({old_name: new_name})

    elif action_type == 'RemoveColumn':
        col = action.get('columnName', '')
        if col:
            return m_transform_remove_columns([col])

    elif action_type == 'DuplicateColumn':
        col = action.get('columnName', '')
        new_col = action.get('newColumnName', f'{col}_copy')
        if col:
            return m_transform_duplicate_column(col, new_col)

    elif action_type == 'ChangeColumnType':
        col = action.get('columnName', '')
        new_type = action.get('newType', 'string')
        m_type = _PREP_TYPE_MAP.get(new_type, 'text')
        n = counter.get('type', 0)
        counter['type'] = n + 1
        step_name = f'#"Changed Type {n}"' if n > 0 else '#"Changed Type"'
        return (step_name,
                f'Table.TransformColumnTypes({{prev}}, {{{{"{col}", type {m_type}}}}})')

    elif action_type == 'FilterOperation':
        expr = action.get('filterExpression', '')
        filter_type = action.get('filterType', 'keep')
        m_expr = _convert_prep_expression_to_m(expr)
        n = counter.get('filter', 0)
        counter['filter'] = n + 1
        step_name = f'#"Filtered Rows {n}"' if n > 0 else '#"Filtered Rows"'
        if filter_type == 'remove':
            return (step_name,
                    f'Table.SelectRows({{prev}}, each not ({m_expr}))')
        return (step_name,
                f'Table.SelectRows({{prev}}, each {m_expr})')

    elif action_type == 'FilterValues':
        col = action.get('columnName', '')
        values = action.get('values', [])
        filter_type = action.get('filterType', 'keep')
        if col and values:
            if filter_type == 'remove':
                return m_transform_exclude_values(col, values)
            return m_transform_filter_values(col, values)

    elif action_type == 'FilterRange':
        col = action.get('columnName', '')
        min_val = action.get('min')
        max_val = action.get('max')
        if col:
            return m_transform_filter_range(col, min_val, max_val)

    elif action_type == 'ReplaceValues':
        col = action.get('columnName', '')
        old_val = action.get('oldValue', '')
        new_val = action.get('newValue', '')
        if col:
            return m_transform_replace_value(col, old_val, new_val)

    elif action_type == 'ReplaceNulls':
        col = action.get('columnName', '')
        replacement = action.get('replacement', '')
        if col:
            return m_transform_replace_nulls(col, replacement)

    elif action_type == 'SplitColumn':
        col = action.get('columnName', '')
        delimiter = action.get('delimiter', ',')
        if col:
            return m_transform_split_by_delimiter(col, delimiter)

    elif action_type == 'MergeColumns':
        columns = action.get('columns', [])
        separator = action.get('separator', ' ')
        new_col = action.get('newColumnName', 'Merged')
        if columns:
            return m_transform_merge_columns(columns, new_col, separator)

    elif action_type == 'AddColumn':
        col_name = action.get('columnName', 'NewColumn')
        expression = action.get('expression', '')
        m_expr = _convert_prep_expression_to_m(expression)
        # M Table.AddColumn requires 'each' prefix for row-context expressions
        if not m_expr.strip().startswith('each'):
            m_expr = f'each {m_expr}'
        return m_transform_add_column(col_name, m_expr)

    elif action_type == 'CleanOperation':
        col = action.get('columnName', '')
        operation = action.get('operation', '').lower()
        if col:
            if operation == 'trim':
                return m_transform_trim([col])
            elif operation == 'upper':
                return m_transform_upper([col])
            elif operation == 'lower':
                return m_transform_lower([col])
            elif operation == 'proper':
                return m_transform_proper_case([col])
            elif operation in ('removeletters', 'removenumbers', 'removepunctuation'):
                return m_transform_clean([col])

    elif action_type == 'FillValues':
        col = action.get('columnName', '')
        direction = action.get('direction', 'down').lower()
        if col:
            if direction == 'up':
                return m_transform_fill_up([col])
            return m_transform_fill_down([col])

    elif action_type == 'GroupReplace':
        col = action.get('columnName', '')
        groupings = action.get('groupings', [])
        if col and groupings:
            # Convert groupings to replace steps
            result_steps = []
            for g in groupings:
                old_val = g.get('from', '')
                new_val = g.get('to', '')
                if old_val and new_val:
                    result_steps.append(m_transform_replace_value(col, old_val, new_val))
            return result_steps if result_steps else None

    elif action_type == 'ConditionalColumn':
        new_col = action.get('newColumnName', 'Conditional')
        rules = action.get('rules', [])
        default = action.get('defaultValue', 'null')
        if rules:
            conditions = []
            for rule in rules:
                condition = _convert_prep_expression_to_m(rule.get('condition', ''))
                value = rule.get('value', '""')
                if isinstance(value, str) and not value.startswith('"'):
                    value = f'"{value}"'
                conditions.append((f'each {condition}', str(value)))
            return m_transform_conditional_column(new_col, conditions, str(default))

    elif action_type == 'ExtractValues':
        # Regex or pattern extraction → Table.TransformColumns with Text.Select / regex
        col = action.get('columnName', '')
        pattern = action.get('pattern', '')
        new_col = action.get('newColumnName', f'{col}_extracted')
        if col:
            m_pattern = pattern.replace('\\', '\\\\') if pattern else '.*'
            n = counter.get('extract', 0)
            counter['extract'] = n + 1
            step_name = f'#"Extracted {n}"' if n > 0 else '#"Extracted Values"'
            # Use Table.AddColumn with a regex-like Text approach
            return (step_name,
                    f'Table.AddColumn({{prev}}, "{new_col}", '
                    f'each Text.Select([{col}], {{"a".."z", "A".."Z", "0".."9"}}), type text)')

    elif action_type == 'CustomCalculation':
        # Full custom calculation expression in Prep
        col_name = action.get('columnName', action.get('newColumnName', 'Calc'))
        expression = action.get('expression', '')
        m_expr = _convert_prep_expression_to_m(expression)
        if not m_expr.strip().startswith('each'):
            m_expr = f'each {m_expr}'
        return m_transform_add_column(col_name, m_expr)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  AGGREGATE STEP → M STEP
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_aggregate_node(node):
    """Convert an Aggregate node to an m_transform_aggregate step."""
    group_fields = [f.get('name', '') for f in node.get('groupByFields', [])]
    agg_fields = []
    for af in node.get('aggregateFields', []):
        agg = af.get('aggregation', 'SUM').upper()
        agg_fields.append({
            'name': af.get('newColumnName', af.get('name', '')),
            'column': af.get('name', ''),
            'agg': _PREP_AGG_MAP.get(agg, 'sum'),
        })

    if group_fields or agg_fields:
        return m_transform_aggregate(group_fields, agg_fields)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  JOIN STEP → M STEPS
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_m_table_ref(name):
    """Clean a node name into a valid Power Query M table reference.

    Strips file extension, replaces spaces, and wraps in #"..." if needed.
    """
    # Strip common file extensions
    for ext in ('.csv', '.xlsx', '.xls', '.json', '.hyper', '.tde'):
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
            break
    # Replace spaces with underscores for the table name
    clean = name.replace(' ', '_')
    return clean


def _parse_join_node(node, right_table_name, right_fields):
    """
    Convert a Join node to m_transform_join steps.

    Returns:
        list of (step_name, step_expression) tuples (join + expand)
    """
    join_type = _PREP_JOIN_MAP.get(node.get('joinType', 'inner'), 'inner')
    conditions = node.get('joinConditions', [])

    left_keys = [c.get('leftColumn', '') for c in conditions]
    right_keys = [c.get('rightColumn', '') for c in conditions]

    # Fields to expand from right table
    expand_fields = [f.get('name', '') for f in right_fields
                     if f.get('name', '') not in right_keys]

    if left_keys and right_keys:
        # Use cleaned M table reference
        m_ref = _clean_m_table_ref(right_table_name)
        return m_transform_join(
            m_ref, left_keys, right_keys,
            join_type, expand_fields
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  UNION STEP → M STEP
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_union_node(node, upstream_table_names):
    """Convert a Union node to an m_transform_union step."""
    if upstream_table_names:
        return m_transform_union(upstream_table_names)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  PIVOT STEP → M STEP
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_pivot_node(node):
    """Convert a Pivot node to an M step (unpivot or pivot)."""
    pivot_type = node.get('pivotType', '')

    if pivot_type == 'columnsToRows':
        # Unpivot
        pivot_fields = [f.get('name', '') for f in node.get('pivotFields', [])]
        values_name = node.get('pivotValuesName', 'Value')
        names_name = node.get('pivotNamesName', 'Attribute')
        if pivot_fields:
            return m_transform_unpivot(pivot_fields, names_name, values_name)

    elif pivot_type == 'rowsToColumns':
        # Pivot
        key_field = node.get('pivotKeyField', {}).get('name', '')
        value_field = node.get('pivotValueField', {}).get('name', '')
        agg = node.get('aggregation', 'SUM').lower()
        if key_field and value_field:
            return m_transform_pivot(key_field, value_field, agg)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN FLOW PARSER — CONVERTS ENTIRE FLOW TO DATASOURCES
# ═══════════════════════════════════════════════════════════════════════════════

def parse_prep_flow(filepath):
    """
    Parse a Tableau Prep flow file and convert to datasource definitions
    compatible with the Power BI generation pipeline.

    Each output node in the flow produces one datasource/table with a
    complete M query that chains all upstream transformations.

    Args:
        filepath: Path to .tfl or .tflx file

    Returns:
        list of datasource dicts, each with:
        - name: datasource name
        - tables: [{name, columns, m_query}]
        - connections: [connection_dict]
        - columns_metadata: []
        - calculations: []
    """
    flow = read_prep_flow(filepath)
    nodes = flow.get('nodes', {})
    connections = flow.get('connections', {})

    if not nodes:
        print("  ⚠ No nodes found in Prep flow")
        return []

    # Topological sort to process in order
    sorted_ids = _topological_sort(nodes)

    # Track per-node results: node_id → {connection, table, m_query, fields}
    node_results = {}
    # Track secondary branch nodes that need to be emitted as separate queries
    # (e.g. right side of joins, extra union inputs)
    secondary_branch_ids = set()

    for nid in sorted_ids:
        _process_prep_node(nid, nodes, connections, node_results, secondary_branch_ids)

    # Collect output nodes into datasources
    return _collect_prep_datasources(sorted_ids, nodes, node_results, secondary_branch_ids)


def _process_prep_node(nid, nodes, connections, node_results, secondary_branch_ids):
    """Process a single Prep flow node (input/transform/output) and store result in node_results."""
    node = nodes.get(nid, {})
    base_type = node.get('baseType', '')
    sem_type = _get_node_type(node)
    node_name = node.get('name', nid[:8])

    if base_type == 'input':
        _process_input_node(nid, node, connections, node_results, node_name)

    elif base_type == 'transform':
        upstream_ids = _find_upstream_nodes(nodes, nid)
        _process_transform_node(nid, node, nodes, upstream_ids, sem_type,
                                node_results, secondary_branch_ids, node_name)

    elif base_type == 'output':
        if upstream_ids := _find_upstream_nodes(nodes, nid):
            if upstream_ids[0] in node_results:
                node_results[nid] = {
                    **node_results[upstream_ids[0]],
                    'name': node_name,
                    'is_output': True,
                }
                print(f"    ✓ Output: {node_name}")


def _process_input_node(nid, node, connections, node_results, node_name):
    """Process an input node: parse connection and generate base M query.

    For Hyper connections, attempts to read actual schema/data via
    ``hyper_reader`` to produce a richer M expression.
    """
    connection, table = _parse_input_node(node, connections)
    conn_type = connection.get('type', '')

    m_query = None
    # For hyper sources, try to read actual data first
    if conn_type.lower() in ('hyper', 'extract'):
        filename = connection.get('details', {}).get('filename', '')
        if filename:
            try:
                from hyper_reader import read_hyper
                result = read_hyper(filename, max_rows=20)
                hyper_tables = result.get('tables', [])
                if hyper_tables:
                    m_query = generate_m_from_hyper(
                        hyper_tables, table.get('name'))
            except (ImportError, OSError, KeyError, ValueError) as exc:
                logger.debug('Hyper read failed for %s: %s', node_name, exc)

    if m_query is None:
        m_query = generate_power_query_m(connection, table)

    node_results[nid] = {
        'connection': connection,
        'table': table,
        'name': node_name,
        'm_query': m_query,
        'fields': node.get('fields', []),
    }
    print(f"    ✓ Input: {node_name} ({connection.get('type', '?')})")


def _process_transform_node(nid, node, nodes, upstream_ids, sem_type,
                            node_results, secondary_branch_ids, node_name):
    """Dispatch a transform node to its specific handler based on semantic type."""

    if sem_type in ('SuperTransform',):
        # Clean step — chain onto upstream M query
        if upstream_ids and upstream_ids[0] in node_results:
            upstream = node_results[upstream_ids[0]]
            steps = _parse_clean_actions(node)
            m_query = upstream['m_query']
            if steps:
                m_query = inject_m_steps(m_query, steps)
            node_results[nid] = {
                **upstream,
                'name': node_name,
                'm_query': m_query,
            }
            print(f"    ✓ Clean: {node_name} ({len(steps)} actions)")

    elif sem_type == 'Aggregate':
        if upstream_ids and upstream_ids[0] in node_results:
            upstream = node_results[upstream_ids[0]]
            step = _parse_aggregate_node(node)
            m_query = upstream['m_query']
            if step:
                m_query = inject_m_steps(m_query, [step])
            node_results[nid] = {
                **upstream,
                'name': node_name,
                'm_query': m_query,
            }
            print(f"    ✓ Aggregate: {node_name}")

    elif sem_type == 'Join':
        # Join needs two upstream sources
        left_id = node.get('leftNodeId')
        right_id = node.get('rightNodeId')

        # Fallback: use upstream_ids order
        if not left_id and len(upstream_ids) >= 2:
            left_id = upstream_ids[0]
            right_id = upstream_ids[1]
        elif not left_id and len(upstream_ids) == 1:
            left_id = upstream_ids[0]

        if left_id and left_id in node_results:
            left = node_results[left_id]
            right_name = 'RightTable'
            right_fields = []

            if right_id and right_id in node_results:
                right = node_results[right_id]
                right_name = right.get('name', 'RightTable')
                right_fields = right.get('fields', [])
                # Mark the right branch for emission as a separate query
                secondary_branch_ids.add(right_id)

            join_steps = _parse_join_node(node, right_name, right_fields)
            m_query = left['m_query']
            if join_steps:
                m_query = inject_m_steps(m_query, join_steps)

            node_results[nid] = {
                **left,
                'name': node_name,
                'm_query': m_query,
            }
            print(f"    ✓ Join: {node_name} ({node.get('joinType', 'inner')})")

    elif sem_type == 'Union':
        upstream_names = []
        for uid in upstream_ids:
            if uid in node_results:
                raw_name = node_results[uid].get('name', uid[:8])
                upstream_names.append(_clean_m_table_ref(raw_name))
                # Mark all union inputs as secondary branches
                secondary_branch_ids.add(uid)

        # For union, take first upstream as base
        if upstream_ids and upstream_ids[0] in node_results:
            upstream = node_results[upstream_ids[0]]
            step = _parse_union_node(node, upstream_names)
            m_query = upstream['m_query']
            if step:
                m_query = inject_m_steps(m_query, [step])
            node_results[nid] = {
                **upstream,
                'name': node_name,
                'm_query': m_query,
            }
            print(f"    ✓ Union: {node_name} ({len(upstream_names)} inputs)")

    elif sem_type == 'Pivot':
        if upstream_ids and upstream_ids[0] in node_results:
            upstream = node_results[upstream_ids[0]]
            step = _parse_pivot_node(node)
            m_query = upstream['m_query']
            if step:
                m_query = inject_m_steps(m_query, [step])
            node_results[nid] = {
                **upstream,
                'name': node_name,
                'm_query': m_query,
            }
            print(f"    ✓ Pivot: {node_name} ({node.get('pivotType', '?')})")

    elif sem_type in ('Script', 'RunScript', 'RunCommand'):
        # Script step (Python/R) — not directly convertible; pass through with comment
        if upstream_ids and upstream_ids[0] in node_results:
            upstream = node_results[upstream_ids[0]]
            script_lang = node.get('scriptLanguage', node.get('language', 'Python'))
            comment_step = (
                '#"Script Warning"',
                f'Table.AddColumn({{prev}}, "__script_warning", '
                f'each "/* {script_lang} script step not auto-converted — '
                f'manual migration required */", type text)'
            )
            m_query = inject_m_steps(upstream['m_query'], [comment_step])
            node_results[nid] = {
                **upstream,
                'name': node_name,
                'm_query': m_query,
            }
            print(f"    ⚠ Script step ({script_lang}): {node_name} — manual migration required")

    elif sem_type in ('Prediction', 'TabPy', 'Einstein'):
        # Prediction / ML step — not convertible; pass through with warning
        if upstream_ids and upstream_ids[0] in node_results:
            upstream = node_results[upstream_ids[0]]
            comment_step = (
                '#"Prediction Warning"',
                f'Table.AddColumn({{prev}}, "__prediction_warning", '
                f'each "/* ML/prediction step not auto-converted — '
                f'use Power BI AutoML or Python visual */", type text)'
            )
            m_query = inject_m_steps(upstream['m_query'], [comment_step])
            node_results[nid] = {
                **upstream,
                'name': node_name,
                'm_query': m_query,
            }
            print(f"    ⚠ Prediction step: {node_name} — manual migration required")

    elif sem_type == 'CrossJoin':
        # Cross join (no key condition) → Table.Join with no key
        if upstream_ids and len(upstream_ids) >= 2:
            left_id = upstream_ids[0]
            right_id = upstream_ids[1]
            if left_id in node_results and right_id in node_results:
                left = node_results[left_id]
                right = node_results[right_id]
                right_name = _clean_m_table_ref(right.get('name', 'RightTable'))
                secondary_branch_ids.add(right_id)
                cross_step = (
                    '#"Cross Join"',
                    f'Table.Join({{prev}}, {{}}, {right_name}, {{}}, JoinKind.FullOuter)'
                )
                m_query = inject_m_steps(left['m_query'], [cross_step])
                node_results[nid] = {
                    **left,
                    'name': node_name,
                    'm_query': m_query,
                }
                print(f"    ✓ Cross Join: {node_name}")

    elif sem_type in ('PublishedDataSource', 'LoadPublishedDataSource'):
        # Published data source input — reference as external table
        ds_name = node.get('publishedDatasourceName',
                           node.get('datasourceName', node_name))
        table_ref = _clean_m_table_ref(ds_name)
        m_query = (
            f'let\n'
            f'    // Published Data Source: {ds_name}\n'
            f'    // TODO: Replace with actual Power BI dataset reference\n'
            f'    Source = #"{table_ref}"\n'
            f'in\n    Source'
        )
        node_results[nid] = {
            'connection': {'type': 'published', 'details': {}},
            'table': {'name': table_ref, 'columns': []},
            'name': node_name,
            'm_query': m_query,
            'fields': node.get('fields', []),
        }
        print(f"    ✓ Published DS Input: {node_name} → {ds_name}")

    else:
        # Unknown transform — pass through
        if upstream_ids and upstream_ids[0] in node_results:
            node_results[nid] = {
                **node_results[upstream_ids[0]],
                'name': node_name,
            }
            print(f"    ⚠ Unsupported step: {sem_type} ({node_name}) — passed through")


def _collect_prep_datasources(sorted_ids, nodes, node_results, secondary_branch_ids):
    """Collect processed node results into datasource definitions for the PBI pipeline."""
    datasources = []

    # First, emit secondary branch nodes (join right-tables, union extras)
    # so their queries exist in the model for the main query to reference
    for sec_id in secondary_branch_ids:
        if sec_id in node_results:
            result = node_results[sec_id]
            raw_name = result.get('name', 'SecondaryTable')
            table_name = _clean_m_table_ref(raw_name)
            columns = []
            for f in result.get('fields', []):
                columns.append({
                    'name': f.get('name', ''),
                    'datatype': f.get('type', 'string'),
                })

            datasource = {
                'name': f'prep.{table_name}',
                'caption': raw_name,
                'tables': [{
                    'name': table_name,
                    'columns': columns,
                }],
                'connection': result.get('connection', {}),
                'connection_map': {},
                'connections': [result.get('connection', {})],
                'columns_metadata': [],
                'calculations': [],
                'relationships': [],
                'm_query_override': result.get('m_query', ''),
                'is_prep_source': True,
            }
            datasources.append(datasource)
            print(f"    + Secondary table emitted: {table_name}")

    # Then collect output nodes
    for nid, result in node_results.items():
        if result.get('is_output', False):
            ds_name = result.get('name', 'PrepOutput')
            table_name = ds_name.replace(' ', '_')
            columns = []
            for f in result.get('fields', []):
                columns.append({
                    'name': f.get('name', ''),
                    'datatype': f.get('type', 'string'),
                })

            datasource = {
                'name': f'prep.{table_name}',
                'caption': ds_name,
                'tables': [{
                    'name': table_name,
                    'columns': columns,
                }],
                'connection': result.get('connection', {}),
                'connection_map': {},
                'connections': [result.get('connection', {})],
                'columns_metadata': [],
                'calculations': [],
                'relationships': [],
                'm_query_override': result.get('m_query', ''),
                'is_prep_source': True,
            }
            datasources.append(datasource)

    # If no output nodes, use all leaf nodes (nodes with no outgoing edges)
    if not datasources:
        for nid in sorted_ids:
            node = nodes.get(nid, {})
            if not node.get('nextNodes') and nid in node_results:
                result = node_results[nid]
                ds_name = result.get('name', 'PrepOutput')
                table_name = ds_name.replace(' ', '_')
                datasource = {
                    'name': f'prep.{table_name}',
                    'caption': ds_name,
                    'tables': [{
                        'name': table_name,
                        'columns': [{'name': f.get('name', ''), 'datatype': f.get('type', 'string')}
                                    for f in result.get('fields', [])],
                    }],
                    'connection': result.get('connection', {}),
                    'connection_map': {},
                    'connections': [result.get('connection', {})],
                    'columns_metadata': [],
                    'calculations': [],
                    'relationships': [],
                    'm_query_override': result.get('m_query', ''),
                    'is_prep_source': True,
                }
                datasources.append(datasource)

    return datasources


# ═══════════════════════════════════════════════════════════════════════════════
#  MERGE PREP DATASOURCES WITH TWB DATASOURCES
# ═══════════════════════════════════════════════════════════════════════════════

def merge_prep_with_workbook(prep_datasources, twb_datasources):
    """
    Merge Tableau Prep flow datasources with TWB datasources.

    When a TWB references a Prep-produced data source (by matching table names),
    the Prep's M query (with all transformation steps) replaces the simple
    source query from the TWB extraction.

    Args:
        prep_datasources: list from parse_prep_flow()
        twb_datasources: list from TWB extraction

    Returns:
        list of merged datasources (TWB datasources enhanced with Prep M queries)
    """
    # Build lookup: table_name → prep M query
    prep_queries = {}
    for pds in prep_datasources:
        for table in pds.get('tables', []):
            tname = table.get('name', '')
            m_query = pds.get('m_query_override', '')
            if tname and m_query:
                prep_queries[tname] = m_query
                # Also index by caption/datasource name
                caption = pds.get('caption', '')
                if caption:
                    prep_queries[caption] = m_query
                    prep_queries[caption.replace(' ', '_')] = m_query

    if not prep_queries:
        # No Prep data to merge — return TWB datasources plus any standalone Prep datasources
        return twb_datasources + prep_datasources

    # Enhance TWB datasources with Prep M queries
    merged = []
    matched_prep_tables = set()

    for ds in twb_datasources:
        # Check each table in the datasource
        for table in ds.get('tables', []):
            tname = table.get('name', '')
            if tname in prep_queries:
                # Replace the M query with the Prep-enriched version
                ds['m_query_overrides'] = ds.get('m_query_overrides', {})
                ds['m_query_overrides'][tname] = prep_queries[tname]
                matched_prep_tables.add(tname)
                print(f"    ✓ Matched Prep flow → TWB table: {tname}")
        merged.append(ds)

    # Add unmatched Prep datasources as standalone tables
    for pds in prep_datasources:
        for table in pds.get('tables', []):
            tname = table.get('name', '')
            if tname not in matched_prep_tables:
                merged.append(pds)
                print(f"    + Added standalone Prep datasource: {tname}")
                break

    return merged
