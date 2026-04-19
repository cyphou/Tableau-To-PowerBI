"""
TMDL (Tabular Model Definition Language) Generator

Converts extracted Tableau data directly into TMDL files
for the Power BI SemanticModel.

Handles:
- Physical tables with M query partitions
- DAX measures and calculated columns
- Relationships (manyToOne, manyToMany)
- Hierarchies, sets, groups, bins
- Parameter tables (What-If)
- Date table with time intelligence
- Geographic data categories
- RLS roles from Tableau user filters

Generated structure:
  definition/
    database.tmdl
    model.tmdl
    relationships.tmdl
    expressions.tmdl
    roles.tmdl (if RLS)
    tables/
      {TableName}.tmdl
"""

import sys
import os
import re
import uuid
import json
import logging
import shutil
import time

logger = logging.getLogger(__name__)

# Add path to import from tableau_export
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
from datasource_extractor import (
    generate_power_query_m,
    convert_tableau_formula_to_dax,
    map_tableau_to_powerbi_type
)
from m_query_builder import (
    inject_m_steps,
    m_transform_rename,
    m_transform_remove_columns,
    m_transform_filter_values,
    m_transform_filter_nulls,
    m_transform_add_column,
    wrap_source_with_try_otherwise,
    generate_m_from_hyper,
)


# ════════════════════════════════════════════════════════════════════
#  TABLEAU DERIVATION PREFIX CLEANING
#  Secondary defense against Tableau internal field names leaking
# ════════════════════════════════════════════════════════════════════

_RE_TMDL_DERIVATION_PREFIX = re.compile(
    r'^(none|sum|avg|count|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc|tyr|tqr|tmn|tdy|twk):'
)
_RE_TMDL_TYPE_SUFFIX = re.compile(r':(nk|qk|ok|fn|tn)$')


def _clean_tableau_field_ref(raw):
    """Strip Tableau derivation prefixes and type suffixes from a field name.

    Defensive secondary filter applied in the TMDL generator to catch any
    Tableau internal names that leaked through extraction.
    """
    clean = _RE_TMDL_DERIVATION_PREFIX.sub('', raw)
    return _RE_TMDL_TYPE_SUFFIX.sub('', clean)


# ════════════════════════════════════════════════════════════════════
#  DAX → POWER QUERY M EXPRESSION CONVERTER
#  Eliminates DAX calculated columns in favour of M Table.AddColumn
# ════════════════════════════════════════════════════════════════════

# M type strings matching DAX/BIM dataType values
_DAX_TO_M_TYPE = {
    'Boolean': 'type logical', 'boolean': 'type logical',
    'String': 'type text', 'string': 'type text',
    'Double': 'type number', 'double': 'type number',
    'Decimal': 'type number', 'decimal': 'type number',
    'Int64': 'Int64.Type', 'int64': 'Int64.Type',
    'DateTime': 'type datetime', 'dateTime': 'type datetime',
    'datetime': 'type datetime',
    'Date': 'type date', 'date': 'type date',
    'Time': 'type time', 'time': 'type time',
}


def _split_dax_args(s):
    """Split a string at top-level commas, respecting parentheses and quotes."""
    parts, depth, current, in_str = [], 0, [], False
    for ch in s:
        if in_str:
            current.append(ch)
            if ch == '"':
                in_str = False
        elif ch == '"':
            current.append(ch)
            in_str = True
        elif ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    parts.append(''.join(current).strip())
    return parts


def _extract_function_body(expr, func_name):
    """Extract the content between balanced parens for a named DAX function.

    Only matches if the function call spans the entire expression.
    Returns the inner content string, or None.
    """
    pattern = re.compile(r'^' + re.escape(func_name) + r'\s*\(', re.IGNORECASE)
    m = pattern.match(expr)
    if not m:
        return None
    start = m.end() - 1  # opening '('
    depth, in_str = 0, False
    for i in range(start, len(expr)):
        ch = expr[i]
        if in_str:
            if ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                if expr[i + 1:].strip() == '':
                    return expr[start + 1:i]
                return None  # function doesn't span full expression
    return None


# Characters that are NOT valid in M generalized identifiers inside [...].
# Letters (incl. accented), digits, spaces, and underscores are OK;
# dots and everything else (. / ( ) ' " + @ # $ % ^ & * ! ~ ` < > ? ; : { } | \ - ,) needs quoting.
# Dots are the record-field-access operator in M, so [Stat.util.] is parsed as
# nested access — must be quoted as [#"Stat.util."].
_M_SPECIAL_CHARS = set('./()\'"+@#$%^&*!~`<>?;:{}|\\,-')


def _quote_m_identifiers(m_expr):
    """Quote [field] references containing chars invalid in M generalized identifiers.

    Converts [Pays/Région] → [#"Pays/Région"], leaves [Normal Col] unchanged.
    Skips already-quoted [#"..."] and record literals (contain '=').
    """
    if not m_expr:
        return m_expr

    def _replacer(match):
        name = match.group(1)
        # Skip already-quoted identifiers
        if name.startswith('#"'):
            return match.group(0)
        # Skip record literals (contain '=')
        if '=' in name:
            return match.group(0)
        # Check if quoting is needed
        if any(ch in _M_SPECIAL_CHARS for ch in name):
            return f'[#"{name}"]'
        return match.group(0)

    return re.sub(r'\[([^\]]+)\]', _replacer, m_expr)


def _dax_to_m_expression(dax_expr, table_name=''):
    """Convert a DAX calculated-column expression to Power Query M.

    Handles IF, SWITCH, FLOOR, ISBLANK, IN {}, string/date/math functions,
    simple arithmetic, column references, and boolean operators.

    Returns the M expression string on success, or *None* if the expression
    contains cross-table references or DAX constructs with no M equivalent
    (RELATED, LOOKUPVALUE, CALCULATE, etc.).
    """
    if not dax_expr:
        return dax_expr
    expr = dax_expr.strip()
    if not expr:
        return expr

    # ── Reject unconvertible patterns ───────────────────────────────
    upper = expr.upper()
    if 'RELATED(' in upper or 'LOOKUPVALUE(' in upper:
        return None

    # Remove self-table qualifications: 'TableName'[Col] → [Col]
    if table_name:
        expr = re.sub(r"'" + re.escape(table_name) + r"'\[", '[', expr)
    # Any remaining cross-table refs → bail
    if re.search(r"'[^']+'\[", expr):
        return None

    # ── IF(cond, true_val [, false_val]) ────────────────────────────
    body = _extract_function_body(expr, 'IF')
    if body is not None:
        args = _split_dax_args(body)
        if len(args) >= 2:
            cond = _dax_to_m_expression(args[0], table_name)
            true_v = _dax_to_m_expression(args[1], table_name)
            false_v = _dax_to_m_expression(args[2], table_name) if len(args) >= 3 else 'null'
            if cond is not None and true_v is not None and false_v is not None:
                return f'if {cond} then {true_v} else {false_v}'
        return None

    # ── SWITCH(expr, v1, r1, …, default) ────────────────────────────
    body = _extract_function_body(expr, 'SWITCH')
    if body is not None:
        args = _split_dax_args(body)
        if len(args) >= 3:
            sw = _dax_to_m_expression(args[0], table_name)
            if sw is None:
                return None
            parts = []
            i = 1
            while i + 1 < len(args):
                v = _dax_to_m_expression(args[i], table_name)
                r = _dax_to_m_expression(args[i + 1], table_name)
                if v is None or r is None:
                    return None
                parts.append(f'if {sw} = {v} then {r}')
                i += 2
            default_v = (_dax_to_m_expression(args[-1], table_name)
                         if len(args) % 2 == 0 else '"Other"')
            if default_v is None:
                return None
            return ' else '.join(parts) + f' else {default_v}'
        return None

    # ── FLOOR(x, n) → Number.RoundDown(x / n) * n ──────────────────
    body = _extract_function_body(expr, 'FLOOR')
    if body is not None:
        args = _split_dax_args(body)
        if len(args) == 2:
            x = _dax_to_m_expression(args[0], table_name)
            if x is None:
                return None
            n = args[1].strip()
            return f'Number.RoundDown({x} / {n}) * {n}'
        return None

    # ── ISBLANK(x) → (x = null) ────────────────────────────────────
    body = _extract_function_body(expr, 'ISBLANK')
    if body is not None:
        inner = _dax_to_m_expression(body, table_name)
        return f'({inner} = null)' if inner is not None else None

    # ── NOT(x) → not x ─────────────────────────────────────────────
    body = _extract_function_body(expr, 'NOT')
    if body is not None:
        inner = _dax_to_m_expression(body, table_name)
        return f'not ({inner})' if inner is not None else None

    # ── Single-argument DAX → M function map ────────────────────────
    _SINGLE = [
        ('UPPER', 'Text.Upper'), ('LOWER', 'Text.Lower'),
        ('TRIM', 'Text.Trim'), ('LEN', 'Text.Length'),
        ('YEAR', 'Date.Year'), ('MONTH', 'Date.Month'),
        ('DAY', 'Date.Day'), ('QUARTER', 'Date.QuarterOfYear'),
        ('ABS', 'Number.Abs'), ('INT', 'Number.RoundDown'),
        ('SQRT', 'Number.Sqrt'),
    ]
    for dax_fn, m_fn in _SINGLE:
        body = _extract_function_body(expr, dax_fn)
        if body is not None:
            inner = _dax_to_m_expression(body, table_name)
            return f'{m_fn}({inner})' if inner is not None else None

    # ── Multi-argument DAX → M function map ─────────────────────────
    _MULTI = [
        ('LEFT', 'Text.Start'), ('RIGHT', 'Text.End'),
        ('ROUND', 'Number.Round'),
        ('CONTAINSSTRING', 'Text.Contains'),
    ]
    for dax_fn, m_fn in _MULTI:
        body = _extract_function_body(expr, dax_fn)
        if body is not None:
            args = _split_dax_args(body)
            converted = [_dax_to_m_expression(a, table_name) for a in args]
            if any(c is None for c in converted):
                return None
            return f'{m_fn}({", ".join(converted)})'

    # MID → Text.Middle with 1-based to 0-based start position adjustment
    body = _extract_function_body(expr, 'MID')
    if body is not None:
        args = _split_dax_args(body)
        if len(args) >= 3:
            converted = [_dax_to_m_expression(a, table_name) for a in args]
            if any(c is None for c in converted):
                return None
            return f'Text.Middle({converted[0]}, {converted[1]} - 1, {converted[2]})'

    # SUBSTITUTE → Text.Replace (ignore optional 4th arg: instance_num)
    body = _extract_function_body(expr, 'SUBSTITUTE')
    if body is not None:
        args = _split_dax_args(body)
        if len(args) >= 3:
            converted = [_dax_to_m_expression(a, table_name) for a in args[:3]]
            if any(c is None for c in converted):
                return None
            return f'Text.Replace({", ".join(converted)})'

    # ── DATEDIFF(start, end, interval) → Duration.Days/Months/Years ──
    body = _extract_function_body(expr, 'DATEDIFF')
    if body is not None:
        args = _split_dax_args(body)
        if len(args) == 3:
            start_m = _dax_to_m_expression(args[0], table_name)
            end_m = _dax_to_m_expression(args[1], table_name)
            interval = args[2].strip().upper()
            if start_m is not None and end_m is not None:
                if interval == 'DAY':
                    return f'Duration.Days({end_m} - {start_m})'
                elif interval == 'MONTH':
                    return f'(Date.Year({end_m})*12 + Date.Month({end_m})) - (Date.Year({start_m})*12 + Date.Month({start_m}))'
                elif interval == 'YEAR':
                    return f'Date.Year({end_m}) - Date.Year({start_m})'
                elif interval == 'QUARTER':
                    return f'(Date.Year({end_m})*4 + Date.QuarterOfYear({end_m})) - (Date.Year({start_m})*4 + Date.QuarterOfYear({start_m}))'
                elif interval in ('HOUR', 'MINUTE', 'SECOND'):
                    return f'Duration.TotalSeconds({end_m} - {start_m})'
                # Unsupported interval
                return None
        return None

    # ── DATE(y, m, d) → #date(y, m, d) ─────────────────────────────
    body = _extract_function_body(expr, 'DATE')
    if body is not None:
        args = _split_dax_args(body)
        if len(args) == 3:
            y = _dax_to_m_expression(args[0], table_name)
            mo = _dax_to_m_expression(args[1], table_name)
            d = _dax_to_m_expression(args[2], table_name)
            if y is not None and mo is not None and d is not None:
                return f'#date({y}, {mo}, {d})'
        return None

    # ── [expr] IN {val1, val2, …} → List.Contains({…}, expr) ───────
    in_match = re.match(r'^(.+?)\s+IN\s+(\{.+\})\s*$', expr, re.IGNORECASE)
    if in_match:
        col_m = _dax_to_m_expression(in_match.group(1), table_name)
        if col_m is not None:
            # M uses double-quoted strings only — convert any DAX/Tableau
            # single-quoted literals like {'High', 'Low'} to {"High", "Low"}
            set_expr = re.sub(r"'([^']*)'", r'"\1"', in_match.group(2))
            return f'List.Contains({set_expr}, {col_m})'
        return None

    # ── Leaf expression (literals, column refs, operators) ──────────
    result = expr
    result = result.replace('&&', ' and ').replace('||', ' or ')
    result = re.sub(r'\bTRUE\s*\(\s*\)', 'true', result, flags=re.IGNORECASE)
    result = re.sub(r'\bFALSE\s*\(\s*\)', 'false', result, flags=re.IGNORECASE)
    result = re.sub(r'\bBLANK\s*\(\s*\)', 'null', result, flags=re.IGNORECASE)

    # Remaining DAX function calls → not convertible
    if re.search(r'\b[A-Z_]{2,}\s*\(', result):
        return None
    return _quote_m_identifiers(result)


def _inject_m_steps_into_partition(table, steps):
    """Inject M transformation steps into a table's M partition."""
    if not steps:
        return False
    for partition in table.get('partitions', []):
        source = partition.get('source', {})
        if source.get('type') == 'm' and source.get('expression'):
            source['expression'] = inject_m_steps(source['expression'], steps)
            return True
    return False


def resolve_table_for_column(column_name, datasource_name=None, dax_context=None):
    """Resolve which table a column belongs to, with optional datasource scoping.

    When a worksheet uses multiple datasources, ``datasource_name`` narrows
    the lookup to the tables that belong to that particular datasource.
    Falls back to the global ``column_table_map`` if no datasource-specific
    match is found.

    Args:
        column_name: Column name to resolve.
        datasource_name: Optional datasource name to scope the lookup.
        dax_context: DAX context dict containing ``column_table_map`` and
            ``ds_column_table_map``.

    Returns:
        str or None: Resolved table name, or *None* if unresolved.
    """
    if not dax_context:
        return None
    # Try datasource-specific lookup first
    if datasource_name:
        ds_map = dax_context.get('ds_column_table_map', {}).get(datasource_name, {})
        if column_name in ds_map:
            return ds_map[column_name]
    # Fallback to global map
    return dax_context.get('column_table_map', {}).get(column_name)


def resolve_table_for_formula(formula, datasource_name=None, dax_context=None):
    """Resolve the best target table for a DAX formula based on column references.

    Analyses ``[ColumnName]`` references in the formula and determines which
    table is referenced most frequently.  Useful for routing calculations that
    reference columns from multiple datasources.

    Args:
        formula: DAX formula string.
        datasource_name: Optional datasource name to scope the lookup.
        dax_context: DAX context dict.

    Returns:
        str or None: Best-fit table name, or *None* if unresolved.
    """
    if not formula or not dax_context:
        return None
    col_refs = re.findall(r'\[([^\]]+)\]', formula)
    if not col_refs:
        return None
    table_counts = {}
    for col in col_refs:
        tbl = resolve_table_for_column(col, datasource_name, dax_context)
        if tbl:
            table_counts[tbl] = table_counts.get(tbl, 0) + 1
    if not table_counts:
        return None
    return max(table_counts, key=lambda k: table_counts[k])


# ════════════════════════════════════════════════════════════════════
#  SELF-HEALING — SEMANTIC MODEL VALIDATION & REPAIR
# ════════════════════════════════════════════════════════════════════

def _self_heal_model(model, recovery=None):
    """Run post-generation semantic validation and auto-repair.

    Checks for common issues that would prevent the .pbip from opening
    in Power BI Desktop, and applies corrective strategies:

      1. Broken column references in measures → hide measure + MigrationNote
      2. Duplicate table names → auto-suffix with _2, _3, ...
      3. Orphan measures (table missing) → reassign to first available table
      4. Circular relationships → deactivate weakest link (delegate to existing)
      5. Empty table names → skip
      6. Measures referencing non-existent tables → rewrite table ref

    Args:
        model: Complete semantic model dict
        recovery: Optional RecoveryReport instance for logging repairs

    Returns:
        int: Number of repairs applied
    """
    repairs = 0
    tables = model.get('model', {}).get('tables', [])
    relationships = model.get('model', {}).get('relationships', [])

    # Build lookup of known tables and their columns
    table_names = set()
    table_columns = {}
    for t in tables:
        tname = t.get('name', '')
        if tname:
            table_names.add(tname)
            table_columns[tname] = {c.get('name', '') for c in t.get('columns', [])}

    # 1. Deduplicate table names
    seen_names = {}
    for t in tables:
        tname = t.get('name', '')
        if not tname:
            continue
        if tname in seen_names:
            suffix = 2
            new_name = f"{tname}_{suffix}"
            while new_name in seen_names or new_name in table_names:
                suffix += 1
                new_name = f"{tname}_{suffix}"
            old_name = tname
            t['name'] = new_name
            table_names.add(new_name)
            table_columns[new_name] = table_columns.pop(old_name, set())
            seen_names[new_name] = t
            # Rewrite relationship references
            for rel in relationships:
                if rel.get('fromTable') == old_name:
                    rel['fromTable'] = new_name
                if rel.get('toTable') == old_name:
                    rel['toTable'] = new_name
            repairs += 1
            print(f"  ⚕ Self-heal: Renamed duplicate table '{old_name}' → '{new_name}'")
            if recovery:
                recovery.record('tmdl', 'duplicate_table',
                                item_name=old_name,
                                description=f"Duplicate table name '{old_name}'",
                                action=f"Renamed to '{new_name}'",
                                severity='warning')
        else:
            seen_names[tname] = t

    # 2. Validate measure column references
    measure_names_in_model = set()
    for t in tables:
        for m in t.get('measures', []):
            measure_names_in_model.add(m.get('name', ''))

    all_columns = set()
    for cols in table_columns.values():
        all_columns.update(cols)

    for t in tables:
        tname = t.get('name', '')
        for measure in t.get('measures', []):
            expr = measure.get('expression', '')
            if not expr:
                continue
            # Check for references to columns using [ColumnName] pattern
            refs = re.findall(r'\[([^\]]+)\]', expr)
            broken = False
            for ref in refs:
                # Skip if it's a known measure or known column
                if ref in measure_names_in_model or ref in all_columns:
                    continue
                # Skip DAX keywords/functions
                if ref.upper() in ('VALUE', 'FORMAT', 'YEAR', 'MONTH', 'DAY',
                                   'HOUR', 'MINUTE', 'SECOND', 'DATE'):
                    continue
                # This reference doesn't resolve — mark as broken
                broken = True
                break

            if broken:
                measure['isHidden'] = True
                measure.setdefault('annotations', []).append({
                    'name': 'MigrationNote',
                    'value': f'Self-heal: measure contains unresolved column reference [{ref}]. Review and fix manually.'
                })
                repairs += 1
                mname = measure.get('name', '?')
                print(f"  ⚕ Self-heal: Hidden measure '{mname}' (broken ref [{ref}])")
                if recovery:
                    recovery.record('tmdl', 'broken_column_ref',
                                    item_name=mname,
                                    description=f"Measure references non-existent column [{ref}]",
                                    action="Measure hidden with MigrationNote",
                                    severity='warning',
                                    follow_up=f"Fix column reference [{ref}] in measure '{mname}'")

    # 3. Orphan measures — measures on tables that got removed
    #    (shouldn't normally happen, but defensive)
    main_table = tables[0] if tables else None
    for t in list(tables):
        tname = t.get('name', '')
        if not tname and t.get('measures'):
            # Table has no name — move measures to main table
            if main_table and main_table is not t:
                for m in t.get('measures', []):
                    m.setdefault('annotations', []).append({
                        'name': 'MigrationNote',
                        'value': f'Self-heal: orphan measure reassigned from unnamed table.'
                    })
                    main_table.setdefault('measures', []).append(m)
                    repairs += 1
                    print(f"  ⚕ Self-heal: Reassigned orphan measure '{m.get('name', '?')}' to '{main_table.get('name', '')}'")
                    if recovery:
                        recovery.record('tmdl', 'orphan_measure',
                                        item_name=m.get('name', '?'),
                                        description="Measure on unnamed table",
                                        action=f"Reassigned to '{main_table.get('name', '')}'",
                                        severity='info')
                t['measures'] = []

    # 4. Remove empty-name tables (defensive)
    original_count = len(tables)
    model['model']['tables'] = [t for t in tables if t.get('name', '').strip()]
    removed = original_count - len(model['model']['tables'])
    if removed:
        repairs += removed
        print(f"  ⚕ Self-heal: Removed {removed} unnamed table(s)")
        if recovery:
            recovery.record('tmdl', 'empty_table_name',
                            description=f"Removed {removed} table(s) with empty names",
                            action="Tables removed from model",
                            severity='warning')

    # 5. Circular relationship detection already handled by _deactivate_ambiguous_paths
    #    but log to recovery report if any were deactivated
    deactivated = [r for r in relationships if r.get('isActive') == False]
    for rel in deactivated:
        if recovery:
            desc = (f"{rel.get('fromTable','')}.{rel.get('fromColumn','')} → "
                    f"{rel.get('toTable','')}.{rel.get('toColumn','')}")
            recovery.record('relationship', 'deactivated_ambiguous',
                            item_name=desc,
                            description="Relationship creates ambiguous path (cycle)",
                            action="Deactivated to break cycle",
                            severity='info')

    # 6. Wrap bare column references in measures with MAX()
    #    When a measure references a calculated column from the same table
    #    without aggregation (e.g. inside IF, SWITCH), PBI errors with
    #    "single value cannot be determined".  Wrapping in MAX() is safe
    #    because LOD-derived calc columns have one value per filter context.
    _HEAL_AGG_RE = re.compile(
        r'\b(?:SUM|AVERAGE|MIN|MAX|COUNT|COUNTA|COUNTBLANK|DISTINCTCOUNT|'
        r'SUMX|AVERAGEX|MINX|MAXX|COUNTX|COUNTAX|CALCULATE|FILTER|'
        r'LOOKUPVALUE|RELATED|RANKX|PERCENTILE|MEDIAN|STDEV|VAR|'
        r'ALLEXCEPT|REMOVEFILTERS|ALL|VALUES|HASONEVALUE|SELECTEDVALUE|'
        r'EARLIER|EARLIEST|CONCATENATEX|TOPN|ADDCOLUMNS|SUMMARIZE|'
        r'GENERATE|GENERATEALL|TREATAS|USERELATIONSHIP|CROSSFILTER|'
        r'TOTALYTD|TOTALQTD|TOTALMTD|DATESYTD|DATESMTD|DATESQTD|'
        r'DATEADD|DATESBETWEEN|DATESINPERIOD|SAMEPERIODLASTYEAR|'
        r'PREVIOUSDAY|PREVIOUSMONTH|PREVIOUSQUARTER|PREVIOUSYEAR|'
        r'NEXTDAY|NEXTMONTH|NEXTQUARTER|NEXTYEAR|PARALLELPERIOD|'
        r'STARTOFMONTH|STARTOFQUARTER|STARTOFYEAR|'
        r'ENDOFMONTH|ENDOFQUARTER|ENDOFYEAR|'
        r'FIRSTDATE|LASTDATE|FIRSTNONBLANK|LASTNONBLANK|'
        r'CLOSINGBALANCEMONTH|CLOSINGBALANCEQUARTER|CLOSINGBALANCEYEAR|'
        r'OPENINGBALANCEMONTH|OPENINGBALANCEQUARTER|OPENINGBALANCEYEAR|'
        r'COUNTROWS|DIVIDE|DISTINCTCOUNTNOBLANK|COMBINEVALUES|CONTAINS|'
        r'PATH|PATHITEM|SELECTCOLUMNS)\s*\(',
        re.IGNORECASE
    )
    _TABLE_COL_RE = re.compile(r"'((?:[^']|'')+)'\[([^\]]+)\]")

    for t in model.get('model', {}).get('tables', []):
        tname = t.get('name', '')
        col_names = {c.get('name', '') for c in t.get('columns', []) if c.get('name')}
        local_measures = {m.get('name', '') for m in t.get('measures', []) if m.get('name')}
        # Boolean columns need special wrapping: MAX() doesn't support
        # Boolean type in DAX.  Use MAX(IF(col, 1, 0)) instead.
        bool_cols = {c.get('name', '') for c in t.get('columns', [])
                     if (c.get('dataType', '') or '').lower() == 'boolean'
                     and c.get('name')}

        for measure in t.get('measures', []):
            expr = measure.get('expression', '')
            if not expr:
                continue
            # Find all 'Table'[Column] references in the expression
            refs = list(_TABLE_COL_RE.finditer(expr))
            if not refs:
                continue

            # Process refs in reverse order to preserve positions
            new_expr = expr
            wrapped_any = False
            for ref_match in reversed(refs):
                ref_table = ref_match.group(1).replace("''", "'")
                ref_col = ref_match.group(2)

                # Only wrap refs to columns (not measures) in same table
                if ref_table != tname:
                    continue
                if ref_col in local_measures:
                    continue
                if ref_col not in col_names:
                    continue

                # Backward paren walk: check if ANY enclosing function is an
                # aggregation/iterator/time-intelligence function.
                # Tracks paren depth to correctly skip sibling clauses.
                # E.g. SUMX('T', IF('T'[Col]>0, ...)) — IF is nearest paren
                # but SUMX provides row context at a higher nesting level.
                prefix = new_expr[:ref_match.start()]
                inside_agg = False
                depth = 0
                for i in range(len(prefix) - 1, -1, -1):
                    if prefix[i] == ')':
                        depth += 1
                    elif prefix[i] == '(':
                        if depth > 0:
                            depth -= 1
                        else:
                            # Found an unclosed paren — extract the
                            # function name immediately before '(' and
                            # check ONLY that name (not the entire prefix).
                            func_prefix = prefix[:i].rstrip()
                            fname_m = re.search(r'(\w+)\s*$', func_prefix)
                            if fname_m and _HEAL_AGG_RE.search(fname_m.group(1) + '('):
                                inside_agg = True
                                break
                if inside_agg:
                    continue

                # Wrap: 'Table'[Col] → MAX('Table'[Col])
                # For Boolean columns, MAX() is invalid — use MAX(IF(col, 1, 0))
                # which converts TRUE/FALSE → 1/0 before aggregation.
                ref_text = ref_match.group(0)
                if ref_col in bool_cols:
                    new_expr = (new_expr[:ref_match.start()] +
                                f'MAX(IF({ref_text}, 1, 0))' +
                                new_expr[ref_match.end():])
                else:
                    new_expr = (new_expr[:ref_match.start()] +
                                f'MAX({ref_text})' +
                                new_expr[ref_match.end():])
                wrapped_any = True

            if wrapped_any:
                measure['expression'] = new_expr
                repairs += 1
                mname = measure.get('name', '?')
                print(f"  ⚕ Self-heal: Wrapped bare column refs in measure '{mname}' with MAX()")
                if recovery:
                    recovery.record('tmdl', 'bare_column_ref_in_measure',
                                    item_name=mname,
                                    description=f"Measure references column without aggregation",
                                    action="Wrapped bare column references in MAX()",
                                    severity='info',
                                    follow_up=f"Review measure '{mname}' — MAX() may not be the best aggregation")

    # 7. M query self-repair — ensure all M partitions have try/otherwise wrapping
    for t in model.get('model', {}).get('tables', []):
        tname = t.get('name', '')
        for part in t.get('partitions', []):
            src = part.get('source', {})
            if src.get('type') != 'm':
                continue
            m_expr = src.get('expression', '')
            if not m_expr or 'try' in m_expr:
                continue  # Already wrapped or empty
            # Only wrap partitions that have a 'let ... in' structure
            if 'let' not in m_expr.lower():
                continue
            col_names = [c.get('name', '') for c in t.get('columns', []) if c.get('name')]
            wrapped = wrap_source_with_try_otherwise(m_expr, col_names)
            if wrapped != m_expr:
                src['expression'] = wrapped
                repairs += 1
                if recovery:
                    recovery.record('m_query', 'try_otherwise_wrap',
                                    item_name=tname,
                                    description=f"M partition for '{tname}' lacks error handling",
                                    action="Wrapped Source with try...otherwise fallback",
                                    severity='info')

    return repairs


# ════════════════════════════════════════════════════════════════════
#  PUBLIC ENTRY POINT
# ════════════════════════════════════════════════════════════════════

def generate_tmdl(datasources, report_name, extra_objects, output_dir,
                  calendar_start=None, calendar_end=None, culture=None,
                  model_mode='import', languages=None,
                  composite_threshold=None, agg_tables='none'):
    """
    Main entry point: directly convert extracted Tableau data to TMDL files.

    Args:
        datasources: List of datasources with connections, tables, calculations
        report_name: Name of the report
        extra_objects: Dict with hierarchies, sets, groups, bins, aliases,
                       parameters, user_filters, _datasources
        output_dir: Path to the SemanticModel folder
        calendar_start: Start year for Calendar table (default: 2020)
        calendar_end: End year for Calendar table (default: 2030)
        culture: Override culture/locale (default: en-US)
        model_mode: 'import', 'directquery', or 'composite'
                    Controls partition mode for all tables
        languages: Comma-separated additional locales (e.g. 'fr-FR,de-DE')
        composite_threshold: Column count threshold for composite mode.
                    Tables with more columns than this → directQuery, fewer → import.
                    Default: 10 columns.
        agg_tables: 'auto' to generate Import-mode aggregation tables for
                    directQuery fact tables, 'none' to skip (default).

    Returns:
        dict: Statistics about the generated model
    """
    if extra_objects is None:
        extra_objects = {}

    # Step 1: Build the semantic model
    model = _build_semantic_model(datasources, report_name, extra_objects,
                                  calendar_start=calendar_start,
                                  calendar_end=calendar_end,
                                  culture=culture,
                                  model_mode=model_mode,
                                  composite_threshold=composite_threshold,
                                  agg_tables=agg_tables)

    # Step 1b: Self-healing — validate and auto-repair common issues
    from powerbi_import.recovery_report import RecoveryReport
    recovery = RecoveryReport(report_name)
    repair_count = _self_heal_model(model, recovery=recovery)

    # Attach languages metadata for _write_tmdl_files
    if languages:
        model['model']['_languages'] = languages

    # Attach linguistic synonyms for Q&A support
    linguistic_synonyms = extra_objects.get('linguistic_schema', {})
    if linguistic_synonyms:
        model['model']['_linguistic_synonyms'] = linguistic_synonyms

    # Step 2a: Collect stats and symbols BEFORE writing (the writer
    #          clears column/measure data from tables to free memory).
    tables = model.get('model', {}).get('tables', [])
    rels = model.get('model', {}).get('relationships', [])

    actual_bim_measures = set()
    actual_bim_symbols = set()
    total_columns = 0
    total_measures = 0
    total_hierarchies = 0
    for t in tables:
        tname = t.get('name', '')
        for m in t.get('measures', []):
            mname = m.get('name', '')
            if mname:
                actual_bim_measures.add(mname)
                actual_bim_symbols.add((tname, mname))
        for c in t.get('columns', []):
            cname = c.get('name', '')
            if cname:
                actual_bim_symbols.add((tname, cname))
        total_columns += len(t.get('columns', []))
        total_measures += len(t.get('measures', []))
        total_hierarchies += len(t.get('hierarchies', []))

    # Step 2b: Write TMDL files (clears column/measure data afterward)
    _write_tmdl_files(model, output_dir)

    # Step 2c: Build lineage map — Tableau source → PBI target mapping
    lineage = _build_lineage_map(tables, rels, extra_objects, datasources)

    # Step 3: Return pre-computed stats
    stats = {
        'tables': len(tables),
        'columns': total_columns,
        'measures': total_measures,
        'relationships': len(rels),
        'hierarchies': total_hierarchies,
        'roles': len(model.get('model', {}).get('roles', [])),
        'actual_bim_measures': actual_bim_measures,
        'actual_bim_symbols': actual_bim_symbols,
        'self_heal_repairs': repair_count,
        'recovery_summary': recovery.get_summary() if recovery.has_repairs else None,
        'lineage': lineage,
    }
    return stats


def _build_lineage_map(tables, relationships, extra_objects, datasources):
    """Build a lineage map tracking Tableau source → PBI target for every object.

    Returns:
        dict with 'tables', 'calculations', 'relationships', 'worksheets' lineage entries.
    """
    extra = extra_objects or {}
    lineage = {
        'tables': [],
        'calculations': [],
        'relationships': [],
        'worksheets': [],
    }

    # Table lineage: Tableau datasource.table → PBI table
    ds_names = {}
    for ds in (datasources or []):
        ds_name = ds.get('name', '')
        for tbl in ds.get('tables', []):
            tname = tbl.get('name', '')
            if tname:
                ds_names[tname] = ds_name

    for t in (tables or []):
        pbi_name = t.get('name', '')
        if pbi_name:
            lineage['tables'].append({
                'tableau_datasource': ds_names.get(pbi_name, ''),
                'tableau_table': pbi_name,
                'pbi_table': pbi_name,
            })

    # Calculation lineage: Tableau calc → PBI measure or calculated column
    calcs = extra.get('calculations', [])
    for t in (tables or []):
        pbi_table = t.get('name', '')
        for m in t.get('measures', []):
            mname = m.get('name', '')
            # Find source Tableau calculation
            source_calc = ''
            for c in calcs:
                cap = c.get('caption', c.get('name', '')).replace('[', '').replace(']', '')
                if cap == mname:
                    source_calc = c.get('formula', c.get('name', ''))
                    break
            lineage['calculations'].append({
                'tableau_calculation': source_calc or mname,
                'pbi_table': pbi_table,
                'pbi_object': mname,
                'pbi_type': 'measure',
            })
        for col in t.get('columns', []):
            if col.get('type') == 'calculated':
                cname = col.get('name', '')
                lineage['calculations'].append({
                    'tableau_calculation': cname,
                    'pbi_table': pbi_table,
                    'pbi_object': cname,
                    'pbi_type': 'calculatedColumn',
                })

    # Relationship lineage
    for rel in (relationships or []):
        lineage['relationships'].append({
            'from': f"{rel.get('fromTable', '')}[{rel.get('fromColumn', '')}]",
            'to': f"{rel.get('toTable', '')}[{rel.get('toColumn', '')}]",
            'cardinality': rel.get('crossFilteringBehavior', rel.get('cardinality', '')),
        })

    # Worksheet lineage (from extra_objects)
    for ws in extra.get('worksheets', []):
        ws_name = ws.get('name', '')
        if ws_name:
            lineage['worksheets'].append({
                'tableau_worksheet': ws_name,
                'pbi_page': ws_name,
            })

    return lineage


# ════════════════════════════════════════════════════════════════════
#  SEMANTIC MODEL BUILDING
# ════════════════════════════════════════════════════════════════════

def _build_semantic_model(datasources, report_name="Report", extra_objects=None,
                          calendar_start=None, calendar_end=None, culture=None,
                          model_mode='import', composite_threshold=None,
                          agg_tables='none'):
    """
    Build a complete semantic model from extracted Tableau datasources.

    Produces tables, partitions with M queries, DAX measures, calculated
    columns, relationships, hierarchies, sets/groups/bins, parameters,
    date table, geographic data categories, hidden columns, and RLS roles.

    Orchestrator that delegates to focused sub-functions.
    """
    if extra_objects is None:
        extra_objects = {}

    effective_culture = culture or "en-US"

    model = {
        "name": report_name,
        "compatibilityLevel": 1550,
        "model": {
            "culture": effective_culture,
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "tables": [],
            "relationships": [],
            "roles": []
        }
    }

    # Store calendar options for _add_date_table
    model['_calendar_start'] = calendar_start
    model['_calendar_end'] = calendar_end

    # Store model mode for partition generation
    model['_model_mode'] = model_mode or 'import'
    model['_composite_threshold'] = composite_threshold
    model['_agg_tables'] = agg_tables or 'none'

    # Store raw datasources for M parameter generation (server/database)
    model['_datasources'] = datasources

    # Phase 1-2c: Collect tables, build context mappings
    ctx = _collect_semantic_context(datasources, extra_objects)

    # Phase 3: Create tables
    _create_semantic_tables(model, ctx, datasources, extra_objects)

    # Phase 4: Create and validate relationships
    _create_and_validate_relationships(model, datasources)

    # Phases 5-12: Enrichments (sets, date table, hierarchies, params, RLS, etc.)
    _apply_semantic_enrichments(model, extra_objects, ctx['main_table_name'],
                                ctx['column_table_map'], datasources)

    # Phase 13: Composite model post-processing
    if (model_mode or 'import') == 'composite':
        _enforce_hybrid_relationship_constraints(model)
        if (agg_tables or 'none') == 'auto':
            _generate_aggregation_tables(model)

    return model


def _enforce_hybrid_relationship_constraints(model):
    """Enforce oneDirection cross-filtering for relationships spanning storage modes."""
    table_modes = {}
    for table in model['model']['tables']:
        tname = table.get('name', '')
        partitions = table.get('partitions', [])
        mode = partitions[0].get('mode', 'import') if partitions else 'import'
        table_modes[tname] = mode

    for rel in model['model']['relationships']:
        from_mode = table_modes.get(rel.get('fromTable', ''), 'import')
        to_mode = table_modes.get(rel.get('toTable', ''), 'import')
        if from_mode != to_mode:
            rel['crossFilteringBehavior'] = 'oneDirection'


def _generate_aggregation_tables(model):
    """Generate Import-mode aggregation tables for directQuery fact tables."""
    new_tables = []
    new_rels = []
    for table in model['model']['tables']:
        partitions = table.get('partitions', [])
        if not partitions or partitions[0].get('mode') != 'directQuery':
            continue
        tname = table.get('name', '')
        measures = table.get('measures', [])
        columns = table.get('columns', [])
        if not measures:
            continue

        agg_name = f"Agg_{tname}"
        agg_columns = []
        for col in columns:
            col_type = col.get('dataType', 'string')
            if col_type in ('DateTime', 'int64', 'double', 'decimal'):
                agg_col = {
                    'name': col['name'],
                    'dataType': col_type,
                    'sourceColumn': col.get('sourceColumn', col['name']),
                    'summarizeBy': 'none',
                    'annotations': [{'name': 'alternateOf', 'value': f"'{tname}'[{col['name']}]"}],
                }
                agg_columns.append(agg_col)

        if not agg_columns:
            continue

        # M query for agg table: group-by on dimension keys, summarize measures
        dim_cols = [c['name'] for c in agg_columns if c['dataType'] in ('DateTime', 'int64')]
        m_lines = [f'let\n    Source = {tname},']
        if dim_cols:
            group_cols = ', '.join(f'"{c}"' for c in dim_cols)
            m_lines.append(f'    Grouped = Table.Group(Source, {{{group_cols}}}, {{}})')
        else:
            m_lines.append('    Grouped = Source')
        m_lines.append('in\n    Grouped')
        m_query = '\n'.join(m_lines)

        agg_table = {
            'name': agg_name,
            'columns': agg_columns,
            'partitions': [{
                'name': f"Partition-{agg_name}",
                'mode': 'import',
                'source': {'type': 'm', 'expression': m_query},
            }],
            'measures': [],
            'annotations': [{'name': 'isAggregationTable', 'value': 'true'}],
        }
        new_tables.append(agg_table)

    model['model']['tables'].extend(new_tables)


def _collect_semantic_context(datasources, extra_objects):
    """Phases 1-2c: Collect tables, deduplicate, and build DAX context mappings.

    Returns a dict with: best_tables, m_query_overrides, all_calculations,
    col_metadata_map, main_table_name, dax_context, column_table_map,
    table_datasource_set, ds_main_table, measure_names.
    """
    # Phase 1: Collect all physical tables and deduplicate
    best_tables = {}  # name -> (table_dict, connection_details)
    m_query_overrides = {}  # table_name -> complete M query (from Prep flows)
    all_calculations = []
    all_columns_metadata = []
    all_hierarchies = []
    all_sets = []
    all_groups = []
    all_bins = []

    for ds in datasources:
        ds_connection = ds.get('connection', {})
        connection_map = ds.get('connection_map', {})
        calculations = ds.get('calculations', [])
        all_calculations.extend(calculations)

        # Collect column metadata
        ds_columns = ds.get('columns', [])
        all_columns_metadata.extend(ds_columns)

        # Extract physical columns from datasource-level list (excluding calculations)
        ds_physical_cols = [c for c in ds_columns if not c.get('calculation')]

        tables = ds.get('tables', [])
        for table in tables:
            table_name = table.get('name', 'Table1')

            # Skip tables without a name
            if not table_name or table_name == 'Unknown':
                continue

            # Inherit datasource-level columns into tables that have none
            # (common for Tableau Extracts: single table with columns at DS level)
            if not table.get('columns') and ds_physical_cols and len(tables) == 1:
                # Clean DS-level columns: strip bracket notation and skip special columns
                cleaned_cols = []
                for c in ds_physical_cols:
                    raw = c.get('name', '')
                    if raw.startswith('[:') or not raw:
                        continue  # Skip special Tableau columns (e.g. [:Measure Names])
                    clean = dict(c)
                    clean['name'] = raw.strip('[]')
                    cleaned_cols.append(clean)
                table['columns'] = cleaned_cols

            col_count = len(table.get('columns', []))

            # Resolve per-table connection
            table_conn = table.get('connection_details', {})
            if not table_conn:
                conn_ref = table.get('connection', '')
                table_conn = connection_map.get(conn_ref, ds_connection)

            # Deduplicate: merge columns from all datasources sharing the same table name
            if table_name not in best_tables:
                best_tables[table_name] = (table, table_conn)
            else:
                # Merge columns: add any new columns not already present
                existing_cols = best_tables[table_name][0].get('columns', [])
                existing_names = {c.get('name', '') for c in existing_cols}
                for col in table.get('columns', []):
                    if col.get('name', '') not in existing_names:
                        existing_cols.append(col)
                        existing_names.add(col.get('name', ''))
                # Keep the connection from the table with more columns originally
                if col_count > len(existing_cols) - len(table.get('columns', [])):
                    best_tables[table_name] = (best_tables[table_name][0], table_conn)

        # Collect Prep flow M query overrides
        ds_m_overrides = ds.get('m_query_overrides', {})
        for tname, mq in ds_m_overrides.items():
            m_query_overrides[tname] = mq
        # Single-table override (from prep_flow_parser output)
        single_override = ds.get('m_query_override', '')
        if single_override:
            for table in ds.get('tables', []):
                m_query_overrides[table.get('name', '')] = single_override

    # Phase 2: Identify the main table (the one with the most columns = fact table)
    main_table_name = None
    max_cols = -1
    for tname, (table, conn) in best_tables.items():
        ncols = len(table.get('columns', []))
        if ncols > max_cols:
            max_cols = ncols
            main_table_name = tname

    # Phase 2a: Build column metadata mapping
    col_metadata_map = {}
    for cm in all_columns_metadata:
        raw = cm.get('name', '').replace('[', '').replace(']', '')
        caption = cm.get('caption', raw)
        key = caption if caption else raw
        col_metadata_map[key] = cm
        col_metadata_map[raw] = cm

    # Phase 2b: Build context mappings for DAX conversion
    calc_map = {}
    for calc in all_calculations:
        raw = calc.get('name', '').replace('[', '').replace(']', '')
        caption = calc.get('caption', raw)
        if raw and raw != caption:
            calc_map[raw] = caption

    # param_map: "Parameter X" -> parameter caption
    param_map = {}
    # Source 1: From "Parameters" datasource calculations (old Tableau format)
    for ds in datasources:
        if ds.get('name', '') == 'Parameters':
            for calc in ds.get('calculations', []):
                raw = calc.get('name', '').replace('[', '').replace(']', '')
                caption = calc.get('caption', raw)
                if raw:
                    param_map[raw] = caption
    # Source 2: From extracted parameters (new Tableau format)
    for param in extra_objects.get('parameters', []):
        raw_name = param.get('name', '')
        caption = param.get('caption', '')
        if raw_name and caption:
            match = re.match(r'\[Parameters\]\.\[([^\]]+)\]', raw_name)
            if match:
                param_map[match.group(1)] = caption
            else:
                clean = raw_name.replace('[', '').replace(']', '')
                if clean and clean not in param_map:
                    param_map[clean] = caption

    # column_table_map: column_name -> table_name
    column_table_map = {}
    for tname, (table, conn) in best_tables.items():
        for col in table.get('columns', []):
            cname = col.get('name', '')
            if cname and cname not in column_table_map:
                column_table_map[cname] = tname

    # Supplement with Tableau local-name → table mappings from metadata
    # records.  Connectors like Salesforce have columns (e.g. Id →
    # "Opportunity ID", Probability → "Probability (%)") that exist in
    # <metadata-record> elements but have no <column> element at the
    # datasource level.  Without this, DAX resolution defaults to the
    # current table and produces invalid references.
    for ds in datasources:
        for col_name, parent_table in ds.get('col_local_name_map', {}).items():
            if col_name not in column_table_map and parent_table in best_tables:
                column_table_map[col_name] = parent_table

    # measure_names: set of all measure names (captions).
    # Exclude calculated columns (dimension-role calcs with column refs but no
    # aggregation) so that _resolve_columns qualifies them via column_table_map
    # instead of leaving them as bare [col] measure references.
    measure_names = set()
    _agg_pat_mn = re.compile(
        r'\b(SUM|AVG|AVERAGE|MIN|MAX|COUNT|COUNTD|MEDIAN|STDEV|STDEVP|'
        r'VAR|VARP|PERCENTILE|ATTR|CORR|COVAR|COVARP|COLLECT)\s*\(',
        re.IGNORECASE)
    for calc in all_calculations:
        caption = calc.get('caption', calc.get('name', '').replace('[', '').replace(']', ''))
        if not caption:
            continue
        role = calc.get('role', 'measure')
        formula = calc.get('formula', '').strip()
        has_agg = bool(_agg_pat_mn.search(formula)) if formula else False
        # Tableau role='measure' means the formula is aggregated in view context
        # (implicit SUM/COUNT).  Only dimension-role calcs without aggregation
        # are calculated columns; measure-role calcs are always measures.
        is_calc_col = (role == 'dimension' and not has_agg)
        if not is_calc_col:
            measure_names.add(caption)
    measure_names.update(param_map.values())

    # param_values: {caption: literal_value} for inlining in calculated columns
    param_values = {}
    # Simple Tableau→DAX function replacements applied to inlined literals
    _inline_replacements = [
        (re.compile(r'\bMAKEDATE\s*\(', re.IGNORECASE), 'DATE('),
        (re.compile(r'\bMAKEDATETIME\s*\(', re.IGNORECASE), 'DATE('),
        (re.compile(r'\bMAKETIME\s*\(', re.IGNORECASE), 'TIME('),
    ]
    for calc in all_calculations:
        caption = calc.get('caption', calc.get('name', '').replace('[', '').replace(']', ''))
        formula = calc.get('formula', '').strip()
        if caption and formula and '[' not in formula:
            # Apply basic Tableau→DAX replacements so inlined values
            # don't contain unconverted function names (e.g. MAKEDATE→DATE).
            for pattern, repl in _inline_replacements:
                formula = pattern.sub(repl, formula)
            param_values[caption] = formula
    for param in extra_objects.get('parameters', []):
        caption = param.get('caption', '')
        value = param.get('value', '').strip('"')
        if caption and value and caption not in param_values:
            datatype = param.get('datatype', 'string')
            if datatype == 'string':
                param_values[caption] = f'"{value}"'
            elif datatype in ('date', 'datetime'):
                # Convert Tableau #YYYY-MM-DD# date literal to DAX DATE()
                date_m = re.match(r'#(\d{4})-(\d{2})-(\d{2})#', value)
                if date_m:
                    param_values[caption] = f'DATE({int(date_m.group(1))}, {int(date_m.group(2))}, {int(date_m.group(3))})'
                else:
                    param_values[caption] = value
            else:
                param_values[caption] = value

    # Also add parameter measure names
    for param in extra_objects.get('parameters', []):
        caption = param.get('caption', '')
        if caption:
            measure_names.add(caption)

    # Phase 2c: Build per-datasource column → table map for multi-source routing
    # Maps datasource_name → {column_name → table_name}
    ds_column_table_map = {}
    datasource_table_map = {}  # table_name → datasource_name (last wins for conn)
    table_datasource_set = {}  # table_name → set of ALL datasource names that own it
    for ds in datasources:
        ds_name = ds.get('name', '')
        ds_col_map = {}
        for table in ds.get('tables', []):
            tname = table.get('name', 'Table1')
            if tname in best_tables:
                datasource_table_map[tname] = ds_name
                # Track ALL datasources that own this table (for calculation routing)
                if tname not in table_datasource_set:
                    table_datasource_set[tname] = set()
                table_datasource_set[tname].add(ds_name)
                for col in table.get('columns', []):
                    cname = col.get('name', '')
                    if cname:
                        ds_col_map[cname] = tname
        if ds_name:
            ds_column_table_map[ds_name] = ds_col_map

    dax_context = {
        'calc_map': calc_map,
        'param_map': param_map,
        'column_table_map': column_table_map,
        'measure_names': measure_names,
        'param_values': param_values,
        'ds_column_table_map': ds_column_table_map,
        'datasource_table_map': datasource_table_map,
    }

    # Build compute_using_map from worksheet table_calcs for PARTITIONBY/ORDERBY
    # Maps calc field name → list of compute-using dimension names
    compute_using_map = {}
    for ws in extra_objects.get('worksheets', []):
        for tc in ws.get('table_calcs', []):
            tc_field = tc.get('field', '')
            cu = tc.get('compute_using', [])
            if tc_field and cu:
                compute_using_map[tc_field] = cu
    dax_context['compute_using_map'] = compute_using_map

    # Build ds_main_table: datasource_name → table_name (table with most columns in that DS)
    ds_main_table = {}
    for tname, ds_names in table_datasource_set.items():
        if tname not in best_tables:
            continue
        for ds_name in ds_names:
            if ds_name not in ds_main_table:
                ds_main_table[ds_name] = tname
            else:
                existing = ds_main_table[ds_name]
                existing_cols = len(best_tables.get(existing, ({}, {}))[0].get('columns', []))
                current_cols = len(best_tables.get(tname, ({}, {}))[0].get('columns', []))
                if current_cols > existing_cols:
                    ds_main_table[ds_name] = tname

    # Register dimension-role calculations (calculated columns) in the
    # column_table_map so that cross-table references resolve correctly.
    # Without this, SUMX('OtherTable', IF([CalcCol], ...)) leaves [CalcCol]
    # unqualified, causing "column not found" errors in DAX.
    _agg_pat = re.compile(
        r'\b(SUM|AVG|AVERAGE|MIN|MAX|COUNT|COUNTD|MEDIAN|STDEV|STDEVP|'
        r'VAR|VARP|PERCENTILE|ATTR|CORR|COVAR|COVARP|COLLECT)\s*\(',
        re.IGNORECASE)
    for calc in all_calculations:
        role = calc.get('role', 'measure')
        formula = calc.get('formula', '').strip()
        if not formula:
            continue
        caption = calc.get('caption', calc.get('name', '').replace('[', '').replace(']', ''))
        if not caption or caption in column_table_map:
            continue
        has_agg = bool(_agg_pat.search(formula))
        has_col_refs = bool(re.search(r'\[', formula))
        is_calc_col = (role == 'dimension') or (role == 'measure' and not has_agg and has_col_refs)
        if is_calc_col:
            # Route to the datasource's main table
            dsn = calc.get('datasource_name', '')
            target_table = ds_main_table.get(dsn, main_table_name)
            column_table_map[caption] = target_table

    return {
        'best_tables': best_tables,
        'm_query_overrides': m_query_overrides,
        'all_calculations': all_calculations,
        'col_metadata_map': col_metadata_map,
        'main_table_name': main_table_name,
        'dax_context': dax_context,
        'column_table_map': column_table_map,
        'table_datasource_set': table_datasource_set,
        'ds_main_table': ds_main_table,
        'measure_names': measure_names,
        'datasource_table_map': datasource_table_map,
    }


def _create_semantic_tables(model, ctx, datasources, extra_objects=None):
    """Phase 3: Create model tables with calculation routing."""
    best_tables = ctx['best_tables']
    all_calculations = ctx['all_calculations']
    main_table_name = ctx['main_table_name']
    table_datasource_set = ctx['table_datasource_set']
    ds_main_table = ctx['ds_main_table']
    dax_context = ctx['dax_context']
    col_metadata_map = ctx['col_metadata_map']
    m_query_overrides = ctx['m_query_overrides']
    datasource_table_map = ctx['datasource_table_map']

    # Build hyper table lookup from extracted hyper_files metadata
    hyper_table_data = {}  # table_name_lower -> hyper_reader_tables list
    if extra_objects:
        for hf in extra_objects.get('hyper_files', []):
            hrt = hf.get('hyper_reader_tables', [])
            if hrt:
                for ht in hrt:
                    tname = ht.get('table', '')
                    if tname:
                        hyper_table_data[tname.lower()] = hrt

    for table_name, (table, table_conn) in best_tables.items():
        # Route calculations to their source datasource's main table
        # Use table_datasource_set to handle multiple datasources sharing the same table name
        ds_names_for_table = table_datasource_set.get(table_name, set())
        is_main_for_any_ds = any(
            ds_main_table.get(dsn) == table_name for dsn in ds_names_for_table
        )
        if is_main_for_any_ds:
            # This table is the main table for one or more datasources — collect all their calcs
            owning_ds_names = {
                dsn for dsn in ds_names_for_table
                if ds_main_table.get(dsn) == table_name
            }
            table_calculations = [
                c for c in all_calculations
                if c.get('datasource_name', '') in owning_ds_names
            ]
            # Also add calcs with no datasource_name (legacy) if this is the global main table
            if table_name == main_table_name:
                table_calculations += [
                    c for c in all_calculations
                    if not c.get('datasource_name')
                ]
        elif table_name == main_table_name:
            # Fallback: calcs with no datasource match go to the global main table
            routed_ds_names = set(ds_main_table.values())
            table_calculations = [
                c for c in all_calculations
                if c.get('datasource_name', '') not in datasource_table_map.values()
                or not c.get('datasource_name')
            ]
        else:
            table_calculations = []

        tbl = _build_table(
            table=table,
            connection=table_conn,
            calculations=table_calculations,
            columns_metadata=[],
            dax_context=dax_context,
            col_metadata_map=col_metadata_map,
            extra_objects={},
            m_query_override=m_query_overrides.get(table_name, ''),
            model_mode=model.get('_model_mode', 'import'),
            composite_threshold=model.get('_composite_threshold'),
        )

        # Sprint 109: If this is a hyper/extract table with no Prep override,
        # try to inject inline data from extracted .hyper files
        conn_type = table_conn.get('type', '')
        if conn_type.lower() in ('hyper', 'extract', 'dataengine') \
                and not m_query_overrides.get(table_name):
            hrt = hyper_table_data.get(table_name.lower())
            if hrt:
                hyper_m = generate_m_from_hyper(hrt, table_name=table_name)
                if hyper_m:
                    # Replace the partition's M expression with hyper-inlined data
                    partitions = tbl.get('partitions', [])
                    if partitions:
                        partitions[0]['source']['expression'] = hyper_m
                        logger.debug("Hyper data inlined for table '%s'", table_name)

        model["model"]["tables"].append(tbl)


def _create_and_validate_relationships(model, datasources):
    """Phase 4: Create, deduplicate, validate, and fix type mismatches in relationships."""
    seen_rels = set()
    for ds in datasources:
        relationships = ds.get('relationships', [])
        rels = _build_relationships(relationships)
        for rel in rels:
            key = (rel.get('fromTable'), rel.get('fromColumn'),
                   rel.get('toTable'), rel.get('toColumn'))
            if key not in seen_rels:
                seen_rels.add(key)
                model["model"]["relationships"].append(rel)
            else:
                print(f"  ⚠ Skipped duplicate relationship: {key[0]}.{key[1]} → {key[2]}.{key[3]}")

    # Validate relationships: keep only those pointing to existing tables/columns
    valid_relationships = []
    table_columns = {}
    for table in model["model"]["tables"]:
        tname = table.get("name", "")
        table_columns[tname] = {col.get("name", "") for col in table.get("columns", [])}

    def _resolve_rel_column(col_name, table_name, available_cols):
        """Try to resolve a relationship column name to an existing column.

        Handles Tableau renaming patterns:
        - Suffixed: 'Id' → 'Id (TableName)'
        - CamelCase split: 'CreatedById' → 'Created By ID' or 'Created By Id'
        - Case-insensitive match
        """
        if col_name in available_cols:
            return col_name

        # 1. Try with table suffix: col → 'col (table_name)'
        suffixed = f"{col_name} ({table_name})"
        if suffixed in available_cols:
            return suffixed

        # 2. CamelCase → space-separated: 'CreatedById' → 'Created By Id'
        camel_split = re.sub(r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])',
                             ' ', col_name)
        if camel_split != col_name:
            if camel_split in available_cols:
                return camel_split
            # Also try with uppercase last word: 'Created By Id' → 'Created By ID'
            parts = camel_split.rsplit(' ', 1)
            if len(parts) == 2 and len(parts[1]) <= 3:
                upper_last = f"{parts[0]} {parts[1].upper()}"
                if upper_last in available_cols:
                    return upper_last

        # 3. Case-insensitive match
        col_lower = col_name.lower()
        for ac in available_cols:
            if ac.lower() == col_lower:
                return ac

        # 4. Case-insensitive CamelCase split
        if camel_split != col_name:
            cs_lower = camel_split.lower()
            for ac in available_cols:
                if ac.lower() == cs_lower:
                    return ac

        return None

    for rel in model["model"]["relationships"]:
        from_table = rel.get("fromTable", "")
        to_table = rel.get("toTable", "")
        from_col = rel.get("fromColumn", "")
        to_col = rel.get("toColumn", "")

        if from_table in table_columns and to_table in table_columns and from_table != to_table:
            resolved_from = _resolve_rel_column(from_col, from_table, table_columns[from_table])
            resolved_to = _resolve_rel_column(to_col, to_table, table_columns[to_table])
            if resolved_from and resolved_to:
                if resolved_from != from_col or resolved_to != to_col:
                    print(f"  ✓ Resolved relationship columns: {from_table}.{from_col}→{resolved_from}, {to_table}.{to_col}→{resolved_to}")
                rel["fromColumn"] = resolved_from
                rel["toColumn"] = resolved_to
                valid_relationships.append(rel)
                continue

        reasons = []
        if from_table not in table_columns:
            reasons.append(f"fromTable '{from_table}' not found")
        elif not _resolve_rel_column(from_col, from_table, table_columns.get(from_table, set())):
            reasons.append(f"fromColumn '{from_col}' not in '{from_table}'")
        if to_table not in table_columns:
            reasons.append(f"toTable '{to_table}' not found")
        elif not _resolve_rel_column(to_col, to_table, table_columns.get(to_table, set())):
            reasons.append(f"toColumn '{to_col}' not in '{to_table}'")
        if from_table == to_table:
            reasons.append("self-join")
        print(f"  ⚠ Dropped relationship: {from_table}.{from_col} → {to_table}.{to_col} ({'; '.join(reasons)})")

    model["model"]["relationships"] = valid_relationships

    # Phase 4b: Fix type mismatches in relationship keys
    _fix_relationship_type_mismatches(model)


def _apply_semantic_enrichments(model, extra_objects, main_table_name, column_table_map, datasources):
    """Phases 5-12: Sets, date table, hierarchies, parameters, RLS, cross-table inference, perspectives."""
    # Phase 5: Add sets, groups, bins as calculated columns
    _process_sets_groups_bins(model, extra_objects, main_table_name, column_table_map)

    # Phase 6: Automatic date table if date columns detected
    # Skip if the source already has a date/calendar table (name-based or column-heuristic)
    has_existing_date_table = any(
        _is_date_table(t) for t in model['model']['tables']
    )

    has_date_columns = False
    if not has_existing_date_table:
        for table in model["model"]["tables"]:
            for col in table.get("columns", []):
                if col.get("dataType") == "DateTime" or col.get("dataCategory") == "DateTime":
                    has_date_columns = True
                    break
            if has_date_columns:
                break
    if has_date_columns and not has_existing_date_table:
        _add_date_table(model)

    # Phase 7: Hierarchies from Tableau drill-paths
    _apply_hierarchies(model, extra_objects.get('hierarchies', []), column_table_map)

    # Phase 7b: Auto-generate date hierarchies for DateTime columns without one
    _auto_date_hierarchies(model)

    # Phase 8: Parameter tables (What-If parameters)
    _create_parameter_tables(model, extra_objects.get('parameters', []), main_table_name)

    # Phase 8b: Calculation groups (measure-switching parameters)
    _create_calculation_groups(model, extra_objects.get('parameters', []), main_table_name)

    # Phase 8c: Field parameters (dimension-switching parameters with NAMEOF)
    _create_field_parameters(model, extra_objects.get('parameters', []),
                             main_table_name, column_table_map)

    # Phase 9: RLS roles from Tableau user filters / security
    _create_rls_roles(model, extra_objects.get('user_filters', []),
                      main_table_name, column_table_map)

    # Phase 9b: Auto-generate measures for quick table calculations (% of total, running sum, etc.)
    _create_quick_table_calc_measures(model, extra_objects.get('worksheets', []),
                                      main_table_name, column_table_map)

    # Phase 9c: Auto-generate "Number of Records" COUNTROWS measure when
    # worksheets use COUNT(*) on __tableau_internal_object_id__.
    _create_number_of_records_measure(model, extra_objects.get('_worksheets', []),
                                      main_table_name)

    # Phase 10: Infer missing relationships from cross-table DAX references
    _infer_cross_table_relationships(model)

    # Phase 10b: Detect cardinality (runs AFTER Phase 10 so inferred rels are included)
    _detect_many_to_many(model, datasources)

    # Phase 10c: Replace RELATED() with LOOKUPVALUE() for manyToMany
    _fix_related_for_many_to_many(model)

    # Phase 11: Deactivate relationships that create ambiguous paths
    _deactivate_ambiguous_paths(model)

    # Deduplicate measures globally
    global_measure_names = set()
    for table in model["model"]["tables"]:
        unique_measures = []
        for measure in table.get("measures", []):
            mname = measure.get("name", "")
            if mname not in global_measure_names:
                global_measure_names.add(mname)
                unique_measures.append(measure)
        table["measures"] = unique_measures

    # Phase 12: Auto-generate perspectives from table list
    all_table_names = [t.get('name', '') for t in model["model"]["tables"]]
    model["model"]["perspectives"] = [{
        "name": "Full Model",
        "tables": all_table_names
    }]

    # Phase 12b (Sprint 123): R² measures for trend lines with show_r_squared
    worksheets = extra_objects.get('worksheets', extra_objects.get('_worksheets', []))
    if worksheets:
        _inject_r_squared_measures(model, worksheets, main_table_name, column_table_map)

    # Phase 12c (Sprint 124): Dynamic format string measures
    _inject_dynamic_format_measures(model)


def _inject_r_squared_measures(model, worksheets, main_table_name, column_table_map):
    """Sprint 123: Generate R² DAX measures for trend lines with show_r_squared.

    For each worksheet with a trend line showing R², creates a measure using
    POWER(CORREL(x, y), 2) to compute the coefficient of determination.
    """
    existing = set()
    for t in model['model']['tables']:
        for m in t.get('measures', []):
            existing.add(m.get('name', ''))

    main_table = None
    for t in model['model']['tables']:
        if t.get('name') == main_table_name:
            main_table = t
            break
    if main_table is None and model['model']['tables']:
        main_table = model['model']['tables'][0]
    if main_table is None:
        return

    for ws in worksheets:
        if isinstance(ws, str):
            continue
        trend_lines = ws.get('trend_lines', [])
        if not trend_lines:
            continue
        for tl in trend_lines:
            if not tl.get('show_r_squared'):
                continue
            # Find a numeric measure from the worksheet fields
            ws_name = ws.get('name', ws.get('title', 'Sheet'))
            measure_name = f"R² {ws_name}"
            if measure_name in existing:
                continue
            existing.add(measure_name)

            # Look for measure fields in the worksheet
            fields = ws.get('fields', [])
            measure_field = None
            dim_field = None
            for f in fields:
                fname = f if isinstance(f, str) else f.get('name', f.get('field', ''))
                if not fname:
                    continue
                clean = fname.strip('[]').split('.')[-1].strip('[]')
                # Check if it's a measure
                is_measure = False
                for t in model['model']['tables']:
                    for m in t.get('measures', []):
                        if m.get('name') == clean:
                            is_measure = True
                            break
                    if is_measure:
                        break
                if is_measure and not measure_field:
                    measure_field = clean
                elif not dim_field:
                    dim_field = clean

            if measure_field:
                tbl = column_table_map.get(measure_field, main_table_name)
                r2_expr = (
                    f"VAR _x = RANKX(ALL('{tbl}'), [{measure_field}],,ASC,Dense) "
                    f"VAR _corr = POWER(CORREL(ADDCOLUMNS(ALL('{tbl}'), "
                    f"\"_rank\", RANKX(ALL('{tbl}'), [{measure_field}],,ASC,Dense), "
                    f"\"_val\", [{measure_field}]), [_rank], [_val]), 2) "
                    f"RETURN _corr"
                )
                main_table['measures'].append({
                    'name': measure_name,
                    'expression': f"POWER(CORREL(ADDCOLUMNS(ALL('{tbl}'), \"_idx\", RANKX(ALL('{tbl}'), [{measure_field}],,ASC,Dense)), [_idx], [{measure_field}]), 2)",
                    'formatString': '0.0000',
                    'displayFolder': 'Analytics',
                    'description': f'R² coefficient of determination for {ws_name} trend line',
                    'annotations': [{'name': 'MigrationNote',
                                     'value': f'Auto-generated R² measure for Tableau trend line on {ws_name}'}],
                })


def _inject_dynamic_format_measures(model):
    """Sprint 124: Wrap measures with conditional FORMAT() when format metadata suggests dynamic patterns.

    Detects measures whose format suggests conditional formatting:
    - Currency measures with large values → K/M/B abbreviation wrapper
    - Ratio measures → percentage vs decimal depending on magnitude
    """
    for table in model['model']['tables']:
        for measure in table.get('measures', []):
            fmt = measure.get('formatString', '')
            expr = measure.get('expression', '')
            name = measure.get('name', '')
            if not fmt or not expr:
                continue

            # Skip if already a FORMAT wrapper or a time-intelligence measure
            if 'FORMAT(' in expr or name in ('Year To Date', 'Previous Year', 'Year Over Year %'):
                continue

            # K/M/B abbreviation for large currency/numeric measures
            if fmt.startswith('$') or fmt.startswith('€') or fmt.startswith('£'):
                symbol = fmt[0]
                fmt_name = f"{name} Formatted"
                # Check if a formatted wrapper already exists
                existing_names = {m.get('name', '') for m in table.get('measures', [])}
                if fmt_name in existing_names:
                    continue
                table['measures'].append({
                    'name': fmt_name,
                    'expression': (
                        f'VAR _val = [{name}] '
                        f'RETURN IF(ABS(_val) >= 1E9, FORMAT(_val / 1E9, "#,0.0") & "B", '
                        f'IF(ABS(_val) >= 1E6, FORMAT(_val / 1E6, "#,0.0") & "M", '
                        f'IF(ABS(_val) >= 1E3, FORMAT(_val / 1E3, "#,0.0") & "K", '
                        f'FORMAT(_val, "{fmt}"))))'
                    ),
                    'formatString': '',
                    'displayFolder': 'Formatted',
                    'description': f'Dynamic {symbol} abbreviation for {name} (K/M/B)',
                    'annotations': [{'name': 'MigrationNote',
                                     'value': f'Auto-generated dynamic format wrapper for {name}'}],
                })


def _build_m_transform_steps(columns, col_metadata_map):
    """
    Build M transformation steps from TWB-embedded column metadata.

    Detects:
    - Column renames: caption ≠ raw name → Table.RenameColumns
    - Hidden columns: hidden=true → Table.RemoveColumns (at query level)

    Args:
        columns: list of column dicts from the table
        col_metadata_map: dict {col_name: {caption, hidden, ...}}

    Returns:
        list of (step_name, step_expression) tuples for inject_m_steps()
    """
    steps = []

    # 1. Collect column renames from caption metadata
    renames = {}
    for col in columns:
        col_name = col.get('name', '')
        meta = col_metadata_map.get(col_name, {})
        caption = meta.get('caption', '')
        # Clean bracket notation: [col_name] → col_name
        clean_name = col_name.strip('[]')
        if caption and caption != clean_name and caption != col_name:
            renames[clean_name] = caption

    if renames:
        steps.append(m_transform_rename(renames))

    return steps


def _build_table(table, connection, calculations, columns_metadata, dax_context=None,
                 col_metadata_map=None, extra_objects=None, m_query_override='',
                 model_mode='import', composite_threshold=None):
    """
    Create a semantic model table with columns, partitions and measures.

    Args:
        table: Dict with name, columns
        connection: Dict with type and connection details
        calculations: List of Tableau calculations
        columns_metadata: List of column metadata
        dax_context: Dict with calc_map, param_map, column_table_map, measure_names
        col_metadata_map: Dict {col_name: {hidden, semantic_role, description, ...}}
        extra_objects: Dict with sets, groups, bins, aliases
        model_mode: 'import', 'directquery', or 'composite'

    Returns:
        dict: Complete table definition
    """
    if dax_context is None:
        dax_context = {}
    if col_metadata_map is None:
        col_metadata_map = {}
    if extra_objects is None:
        extra_objects = {}

    table_name = table.get('name', 'Table1')
    columns = table.get('columns', [])

    # Generate M query: use Prep flow override if available, else generate from connection
    if m_query_override:
        m_query = m_query_override
    else:
        m_query = generate_power_query_m(connection, table)

    # Inject TWB-embedded transformation steps from column metadata
    m_steps = _build_m_transform_steps(columns, col_metadata_map)
    if m_steps:
        m_query = inject_m_steps(m_query, m_steps)

    # Wrap Source step with try...otherwise for graceful error handling
    col_names = [c.get('name', '') for c in columns if c.get('name')]
    m_query = wrap_source_with_try_otherwise(m_query, col_names)

    # Determine partition mode based on model_mode
    # For composite: large tables use directQuery, small/lookup use import
    partition_mode = model_mode if model_mode in ('import', 'directQuery') else 'import'
    if model_mode == 'composite':
        threshold = composite_threshold if composite_threshold is not None else 10
        col_count = len(columns)
        if col_count > threshold:
            partition_mode = 'directQuery'
        else:
            partition_mode = 'import'

    result_table = {
        "name": table_name,
        "columns": [],
        "partitions": [
            {
                "name": f"Partition-{table_name}",
                "mode": partition_mode,
                "source": {
                    "type": "m",
                    "expression": m_query
                }
            }
        ],
        "measures": []
    }

    # Track column names (avoid duplicates within the table)
    column_name_counts = {}

    # Add columns
    for col in columns:
        original_col_name = col.get('name', 'Column')

        # Handle duplicate column names by adding a suffix
        if original_col_name in column_name_counts:
            column_name_counts[original_col_name] += 1
            unique_col_name = f"{original_col_name}_{column_name_counts[original_col_name]}"
        else:
            column_name_counts[original_col_name] = 0
            unique_col_name = original_col_name

        bim_column = {
            "name": unique_col_name,
            "dataType": map_tableau_to_powerbi_type(col.get('datatype', 'string')),
            "sourceColumn": col.get('name', 'Column'),
            "summarizeBy": "none"
        }

        # Apply metadata (hidden, semantic_role, description)
        col_meta = col_metadata_map.get(unique_col_name, col_metadata_map.get(col.get('name', ''), {}))
        if col_meta.get('hidden', False):
            bim_column["isHidden"] = True
        if col_meta.get('description', ''):
            bim_column["description"] = col_meta['description']

        # Geographic data categories from semantic-role
        semantic_role = col_meta.get('semantic_role', '')
        geo_category = _map_semantic_role_to_category(semantic_role, unique_col_name)
        if geo_category:
            bim_column["dataCategory"] = geo_category

        # Add the appropriate data type
        if col.get('datatype') == 'date' or col.get('datatype') == 'datetime':
            bim_column["dataCategory"] = "DateTime"
            bim_column["formatString"] = "General Date"
        elif col.get('datatype') in ['integer', 'real']:
            bim_column["summarizeBy"] = "sum"
            if col.get('datatype') == 'real':
                bim_column["formatString"] = "#,0.00"

        # Apply Tableau number format if available (overrides default)
        tableau_fmt = col_meta.get('default_format', '') or col.get('default_format', '')
        if tableau_fmt:
            pbi_fmt = _convert_tableau_format_to_pbi(tableau_fmt)
            if pbi_fmt:
                bim_column["formatString"] = pbi_fmt

        result_table["columns"].append(bim_column)

    # Separate calculations into calculated columns vs measures
    column_table_map = dax_context.get('column_table_map', {})
    calc_map_ctx = dax_context.get('calc_map', {})
    param_values = dax_context.get('param_values', {})
    measure_names_ctx = dax_context.get('measure_names', set())

    # Pre-compiled aggregation pattern (reused in pre-classification and main loop)
    _agg_pattern = re.compile(
        r'\b(SUM|COUNT|COUNTA|COUNTD|COUNTROWS|AVERAGE|AVG|MIN|MAX|MEDIAN|'
        r'STDEV|STDEVP|VAR|VARP|PERCENTILE|DISTINCTCOUNT|CALCULATE|'
        r'TOTALYTD|SAMEPERIODLASTYEAR|RANKX|SUMX|AVERAGEX|MINX|MAXX|COUNTX|'
        r'CORR|COVAR|COVARP|RUNNING_SUM|RUNNING_AVG|RUNNING_COUNT|RUNNING_MAX|RUNNING_MIN|'
        r'WINDOW_SUM|WINDOW_AVG|WINDOW_MAX|WINDOW_MIN|WINDOW_COUNT|'
        r'WINDOW_MEDIAN|WINDOW_STDEV|WINDOW_STDEVP|WINDOW_VAR|WINDOW_VARP|'
        r'WINDOW_CORR|WINDOW_COVAR|WINDOW_COVARP|WINDOW_PERCENTILE|'
        r'RANK|RANK_UNIQUE|RANK_DENSE|RANK_MODIFIED|RANK_PERCENTILE)\s*\(',
        re.IGNORECASE
    )

    # --- Pre-classification pass ---
    # Identify which calculations will be calculated columns so that when
    # a calc references another calc-column, we correctly treat it as a
    # column reference (not a measure reference).  Without this, a
    # dimension-role calc that concatenates other calc-columns (e.g.
    # Filière = Nucléaire_vrai & Réseaux_vrai & NSE_vrai) is incorrectly
    # demoted to a measure because the refs appear in calc_map/measure_names.
    prelim_calc_col_captions = set()
    prelim_calc_col_raws = set()
    for _pc in calculations:
        _pc_name = _pc.get('name', '').replace('[', '').replace(']', '')
        _pc_caption = _pc.get('caption', _pc_name)
        _pc_formula = _pc.get('formula', '').strip()
        _pc_role = _pc.get('role', 'measure')
        _pc_is_literal = _pc_formula and '[' not in _pc_formula
        _pc_has_agg = bool(_agg_pattern.search(_pc_formula))
        # Check for physical column refs (refs not in calc_map/measure_names)
        _pc_refs = re.findall(r'\[([^\]]+)\]', _pc_formula)
        _pc_has_col = False
        for _r in _pc_refs:
            if _r == _pc_caption or _r.startswith('Parameters'):
                continue
            if not (_r in measure_names_ctx or _r in calc_map_ctx.values() or _r in calc_map_ctx):
                _pc_has_col = True
                break
        # Dimension-role calcs without aggregation → pre-classify as calc columns.
        # Measure-role calcs are always measures (Tableau's role='measure'
        # means the formula is aggregated in view context — implicit SUM).
        _pc_is_cc = (not _pc_is_literal) and (
            _pc_role == 'dimension' and not _pc_has_agg
        )
        if _pc_is_cc:
            prelim_calc_col_captions.add(_pc_caption)
            prelim_calc_col_raws.add(_pc_name)

    # --- Pre-classification fixup ---
    # Iteratively remove calcs from the prelim-calc-col sets when they
    # reference ONLY known calcs/measures that are NOT themselves in the
    # prelim set.  This handles chains like:
    #   Base(has_agg→measure) ← (num)(no_agg→dim) ← OOC(no_agg→dim)
    # where (num) and OOC should cascade to measures.
    _fixup_changed = True
    while _fixup_changed:
        _fixup_changed = False
        for _pc in calculations:
            _pc_name = _pc.get('name', '').replace('[', '').replace(']', '')
            _pc_caption = _pc.get('caption', _pc_name)
            if _pc_name not in prelim_calc_col_raws:
                continue
            _pc_formula = _pc.get('formula', '').strip()
            _pc_refs = re.findall(r'\[([^\]]+)\]', _pc_formula)
            _pc_only_measures = True
            _pc_has_refs = False
            for _r in _pc_refs:
                if _r == _pc_caption or _r.startswith('Parameters'):
                    continue
                _pc_has_refs = True
                _r_known = (_r in measure_names_ctx or
                            _r in calc_map_ctx.values() or
                            _r in calc_map_ctx)
                _r_is_cc = (_r in prelim_calc_col_captions or
                            _r in prelim_calc_col_raws)
                if not (_r_known and not _r_is_cc):
                    _pc_only_measures = False
                    break
            if _pc_only_measures and _pc_has_refs:
                prelim_calc_col_captions.discard(_pc_caption)
                prelim_calc_col_raws.discard(_pc_name)
                measure_names_ctx.add(_pc_caption)
                _fixup_changed = True

    m_calc_steps = []  # Accumulated M Table.AddColumn steps (replaces DAX calc cols)
    dax_only_calc_cols = set()  # Names of calc columns that stayed as DAX (not converted to M)

    # Build set of column names belonging to *this* table so that
    # _resolve_columns prefers same-table refs over cross-table RELATED().
    _this_table_columns = {c.get('name', '') for c in columns if c.get('name', '')}
    # Track boolean columns — MAX()/SUM() don't support Boolean type;
    # these need MAX(IF(col, 1, 0)) wrapping instead.
    _bool_table_columns = {c.get('name', '') for c in columns
                           if c.get('name', '')
                           and (c.get('datatype', '') or '').lower() == 'boolean'}

    for calc in calculations:
        calc_name = calc.get('name', '').replace('[', '').replace(']', '')
        caption = calc.get('caption', '') or calc_name
        caption = caption.replace('[', '').replace(']', '')
        formula = calc.get('formula', '').strip()
        role = calc.get('role', 'measure')
        datatype = calc.get('datatype', 'string')

        # Skip calculations with no formula (e.g. categorical-bin groups)
        # to avoid generating measures with empty expressions.
        if not formula:
            continue

        # Skip pure string-literal formulas (e.g. Tableau KPI descriptions
        # like "Count Distinct of IF...").  These are text metadata, not
        # computable DAX expressions, and embedded double-quotes cause
        # TMDL parsing errors.
        _stripped = formula.strip()
        if _stripped.startswith('"') and _stripped.endswith('"') and len(_stripped) > 2:
            continue

        # Determine if it's a simple literal (parameter) -> measure
        is_literal = formula and '[' not in formula

        # Classify: calculated column or measure
        has_aggregation = bool(_agg_pattern.search(formula))
        refs_in_formula = re.findall(r'\[([^\]]+)\]', formula)
        has_column_refs = False
        references_only_measures = True
        for ref in refs_in_formula:
            if ref == caption:
                continue
            if ref.startswith('Parameters'):
                continue
            # A ref is a "measure/calc ref" ONLY if it's a known calc/param
            # AND it was NOT pre-classified as a calculated column.
            is_known_calc = (ref in measure_names_ctx or
                             ref in calc_map_ctx.values() or
                             ref in calc_map_ctx)
            is_calc_col_ref = (ref in prelim_calc_col_captions or
                               ref in prelim_calc_col_raws)
            is_measure_ref = is_known_calc and not is_calc_col_ref
            if not is_measure_ref:
                has_column_refs = True
                references_only_measures = False
                break

        is_calc_col = (not is_literal) and (
            role == 'dimension' and not has_aggregation
        )

        # If a dimension-role calc references ONLY other measures/calcs
        # (no physical columns), it must be a measure — calc columns
        # cannot reference measures in DAX.
        if is_calc_col and not has_column_refs and references_only_measures:
            is_calc_col = False
            # Update prelim sets and measure_names so downstream calcs see
            # correct classification
            prelim_calc_col_captions.discard(caption)
            prelim_calc_col_raws.discard(calc_name)
            measure_names_ctx.add(caption)

        # Security functions must be measures, never calculated columns
        has_security_func = bool(re.search(
            r'\b(USERPRINCIPALNAME|USERNAME|CUSTOMDATA|USERCULTURE)\s*\(',
            dax_context.get('_preview_dax', formula), re.IGNORECASE
        )) or bool(re.search(
            r'\b(USERNAME|FULLNAME|USERDOMAIN|ISMEMBEROF)\s*\(',
            formula, re.IGNORECASE
        ))
        if has_security_func:
            is_calc_col = False

        # Ignore MAKEPOINT (no DAX equivalent)
        if re.search(r'\bMAKEPOINT\b', formula, re.IGNORECASE):
            continue

        dax_formula = convert_tableau_formula_to_dax(
            formula,
            column_name=calc_name,
            table_name=table_name,
            calc_map=dax_context.get('calc_map'),
            param_map=dax_context.get('param_map'),
            column_table_map=column_table_map,
            measure_names=dax_context.get('measure_names'),
            is_calc_column=is_calc_col,
            param_values=param_values,
            calc_datatype=datatype,
            partition_fields=calc.get('table_calc_partitioning'),
            compute_using=dax_context.get('compute_using_map', {}).get(calc_name)
                          or dax_context.get('compute_using_map', {}).get(caption),
            table_columns=_this_table_columns,
            bool_columns=_bool_table_columns
        )

        if is_calc_col:
            # Post-process: inline literal-value measure references
            for ms in result_table.get("measures", []):
                ms_name = ms.get("name", "")
                ms_expr = ms.get("expression", "").strip()
                if ms_expr and re.match(r'^[\d.]+$|^"[^"]*"$|^true$|^false$', ms_expr, re.IGNORECASE):
                    dax_formula = re.sub(
                        r'\[' + re.escape(ms_name) + r'\]',
                        ms_expr,
                        dax_formula
                    )

            # ── Try to push the calculated column into Power Query M ──
            m_expr = _dax_to_m_expression(dax_formula, table_name)
            # Dependency check: if the M expression references a calc column
            # that stayed as DAX (not converted to M), we must fall back to DAX
            if m_expr is not None:
                # Columns available in M: physical source columns + previously created M steps
                m_available_cols = set(_this_table_columns)
                for step_name, _ in m_calc_steps:
                    # Step names are like '#"Added ColName"' — extract the column name
                    sm = re.match(r'#"Added (.+?)"', step_name)
                    if sm:
                        m_available_cols.add(sm.group(1))
                col_refs = re.findall(r'\[#?"?([^\]"]+)"?\]', m_expr)
                for ref in col_refs:
                    if ref in dax_only_calc_cols:
                        m_expr = None
                        break
                    # M queries can only reference physical columns or prior M step columns.
                    # If a ref doesn't exist in M-available columns, it's likely a
                    # measure or DAX calc column — fall back to DAX.
                    if ref not in m_available_cols:
                        m_expr = None
                        break
            if m_expr is not None:
                m_type = _DAX_TO_M_TYPE.get(
                    map_tableau_to_powerbi_type(datatype), 'type text')
                new_step = m_transform_add_column(caption, f'each {m_expr}', m_type)
                # Dedup: replace existing M step for the same column name
                existing_m_idx = None
                for mi, (sn, _) in enumerate(m_calc_steps):
                    sm2 = re.match(r'#"Added (.+?)"', sn)
                    if sm2 and sm2.group(1).lower() == caption.lower():
                        existing_m_idx = mi
                        break
                if existing_m_idx is not None:
                    m_calc_steps[existing_m_idx] = new_step
                else:
                    m_calc_steps.append(new_step)
                bim_calc_col = {
                    "name": caption,
                    "dataType": map_tableau_to_powerbi_type(datatype),
                    "sourceColumn": caption,
                    "summarizeBy": "none",
                }
            else:
                # Fallback: keep as DAX calculated column
                dax_only_calc_cols.add(caption)
                bim_calc_col = {
                    "name": caption,
                    "dataType": map_tableau_to_powerbi_type(datatype),
                    "expression": dax_formula,
                    "summarizeBy": "none",
                    "isCalculated": True,
                }
            if datatype == 'real':
                bim_calc_col["formatString"] = "#,0.00"

            calc_meta = col_metadata_map.get(caption, col_metadata_map.get(calc_name, {}))
            if calc_meta.get('hidden', False):
                bim_calc_col["isHidden"] = True
            if calc_meta.get('description', ''):
                bim_calc_col["description"] = calc_meta['description']
            sr = calc_meta.get('semantic_role', '')
            geo_cat = _map_semantic_role_to_category(sr, caption)
            if geo_cat:
                bim_calc_col["dataCategory"] = geo_cat

            # Dedup: replace existing physical/calc column with same name
            existing_idx = None
            for idx, ec in enumerate(result_table["columns"]):
                if ec.get("name", "").lower() == caption.lower():
                    existing_idx = idx
                    break
            if existing_idx is not None:
                result_table["columns"][existing_idx] = bim_calc_col
            else:
                result_table["columns"].append(bim_calc_col)
            # Track the calc column name so subsequent measures can detect
            # bare column refs at conversion time (Phase 5h).
            _this_table_columns.add(caption)
            if (datatype or '').lower() == 'boolean':
                _bool_table_columns.add(caption)
        else:
            # DAX measures cannot be bare column references — they need an
            # aggregation.  If the converted DAX is just 'Table'[Col] or
            # [Col], wrap it in SUM() so PBI Desktop accepts it.
            # Type-aware: SUM for numeric, MAX for string/date, MAX(IF(col,1,0)) for boolean.
            _bare_col_re = re.compile(
                r"^(?:'[^']*')?\[[^\]]+\]$"
            )
            if _bare_col_re.match(dax_formula.strip()):
                dt_lower = (datatype or '').lower()
                if dt_lower == 'boolean':
                    dax_formula = f"MAX(IF({dax_formula.strip()}, 1, 0))"
                elif dt_lower in ('string', 'date', 'datetime'):
                    dax_formula = f"MAX({dax_formula.strip()})"
                else:
                    dax_formula = f"SUM({dax_formula.strip()})"

            # DAX Measure
            bim_measure = {
                "name": caption,
                "expression": dax_formula,
                "formatString": _get_format_string(datatype),
                "displayFolder": _get_display_folder(datatype, role)
            }
            # Propagate description from Tableau (if extracted)
            calc_desc = calc.get('description', '')
            if calc_desc:
                bim_measure['description'] = calc_desc
            # Store original Tableau formula for auto-description generation
            original_formula = calc.get('formula', '')
            if original_formula:
                bim_measure['_original_formula'] = original_formula
            # Propagate lineage metadata from calculation
            if calc.get('_source_workbooks'):
                bim_measure['_source_workbooks'] = calc['_source_workbooks']
            if calc.get('_merge_action'):
                bim_measure['_merge_action'] = calc['_merge_action']
            # Dedup: skip if measure with same name already exists
            existing_measure = any(
                m.get("name", "").lower() == caption.lower()
                for m in result_table["measures"]
            )
            if not existing_measure:
                result_table["measures"].append(bim_measure)

    # ── Post-processing: fix SUM/AVG/COUNT/MIN/MAX of measure references ──
    # In DAX, SUM([X]) only accepts a column reference.  If [X] resolves to
    # a measure name, the aggregation wrapper must be removed because the
    # measure already aggregates internally.
    _all_measure_names = {m["name"] for m in result_table["measures"]}
    _AGG_OF_MEASURE_RE = re.compile(
        r'\b(SUM|AVERAGE|COUNT|MIN|MAX)\(\s*\[([^\]]+)\]\s*\)',
        re.IGNORECASE,
    )
    for meas in result_table["measures"]:
        expr = meas.get("expression", "")
        if not expr:
            continue
        new_expr = expr
        for m_agg in _AGG_OF_MEASURE_RE.finditer(expr):
            agg_fn = m_agg.group(1)
            ref_name = m_agg.group(2)
            if ref_name in _all_measure_names:
                # Replace SUM([measure]) with just [measure]
                new_expr = new_expr.replace(m_agg.group(0), f'[{ref_name}]')
                logger.debug(
                    "Unwrapped %s([%s]) → [%s] (measure reference, not column)",
                    agg_fn, ref_name, ref_name,
                )
        if new_expr != expr:
            meas["expression"] = new_expr

    # ── Post-processing: wrap bare cross-table column refs in SUM ──
    # A DAX measure cannot reference a column from another table without
    # aggregation.  Pattern: 'Table'[Column] where Column is NOT a measure.
    # Only skip wrapping when the ref is inside an aggregation function
    # (SUM, MAX, etc. — already aggregated) or an iterator function
    # (SUMX, FILTER, etc. — provides row context).  Scalar functions
    # like IF, CONVERT, NOT, SWITCH do NOT provide aggregation or row
    # context, so column refs inside them still need wrapping.
    _XTABLE_COL_RE = re.compile(
        r"'([^']+(?:''[^']*)*)'(\[[^\]]+\])"
    )
    # Functions that provide column context (aggregation, iteration, or
    # column-reference semantics).  Column refs inside these do NOT need
    # SUM wrapping.
    _COLUMN_CONTEXT_FUNCS = frozenset({
        # Aggregation functions (column is their direct input)
        'SUM', 'AVERAGE', 'COUNT', 'COUNTA', 'COUNTBLANK', 'COUNTROWS',
        'MIN', 'MAX', 'DISTINCTCOUNT', 'DISTINCTCOUNTNOBLANK',
        'MEDIAN', 'PERCENTILE',
        # Iterator functions (provide row context in their body)
        'SUMX', 'AVERAGEX', 'COUNTX', 'MINX', 'MAXX', 'PRODUCTX',
        'CONCATENATEX', 'MEDIANX', 'PERCENTILEX',
        'FILTER', 'ADDCOLUMNS', 'SELECTCOLUMNS',
        'GENERATE', 'GENERATEALL', 'RANKX', 'TOPN',
        'SUMMARIZE', 'SUMMARIZECOLUMNS', 'GROUPBY',
        # Lookup / column-reference functions
        'RELATED', 'RELATEDTABLE', 'LOOKUPVALUE', 'TREATAS',
        'VALUES', 'DISTINCT', 'ALL', 'ALLEXCEPT', 'ALLNOBLANKROW',
        'ALLSELECTED', 'REMOVEFILTERS',
        'EARLIER', 'EARLIEST', 'SELECTEDVALUE',
        'HASONEVALUE', 'HASONEFILTER', 'ISINSCOPE',
        'USERELATIONSHIP', 'CROSSFILTER', 'CALCULATETABLE',
    })
    # Build set of boolean columns in the current table — SUM/MAX don't
    # support Boolean type, so these need special wrapping (IF(col,1,0)).
    _bool_cols_for_xtable = {
        c.get('name', '') for c in result_table.get("columns", [])
        if (c.get('dataType', '') or '').lower() == 'boolean'
        and c.get('name')
    }
    # String/DateTime columns should use MAX, not SUM (SUM is invalid for text/dates).
    _text_date_cols_for_xtable = {
        c.get('name', '') for c in result_table.get("columns", [])
        if (c.get('dataType', '') or '').lower() in ('string', 'datetime')
        and c.get('name')
    }
    for meas in result_table["measures"]:
        expr = meas.get("expression", "")
        if not expr:
            continue
        new_expr = expr
        for m_col in reversed(list(_XTABLE_COL_RE.finditer(expr))):
            col_name = m_col.group(2).strip('[]')
            if col_name in _all_measure_names:
                continue  # measure ref — leave as-is
            # Walk expression up to match position tracking whether we
            # are inside an aggregation/iterator function.  Only those
            # functions provide contexts where bare column refs are valid.
            # Scalar functions (IF, CONVERT, NOT, SWITCH …) do NOT
            # provide aggregation or row context.
            agg_depth = 0
            func_stack = []   # True/False per paren level
            text_before = expr[:m_col.start()]
            i = 0
            while i < len(text_before):
                ch = text_before[i]
                if ch == '"':
                    # Skip DAX string literal ("" = escaped double-quote)
                    i += 1
                    while i < len(text_before):
                        if text_before[i] == '"':
                            if (i + 1 < len(text_before)
                                    and text_before[i + 1] == '"'):
                                i += 2  # escaped double-quote
                            else:
                                break
                        i += 1
                    i += 1  # skip closing quote
                elif ch == '(':
                    # Look backwards past spaces to find the function name
                    j = i - 1
                    while j >= 0 and text_before[j] == ' ':
                        j -= 1
                    func_end = j + 1
                    while j >= 0 and (text_before[j].isalnum()
                                      or text_before[j] == '_'):
                        j -= 1
                    func_name = text_before[j + 1:func_end].upper()
                    is_ctx = func_name in _COLUMN_CONTEXT_FUNCS
                    func_stack.append(is_ctx)
                    if is_ctx:
                        agg_depth += 1
                    i += 1
                elif ch == ')':
                    if func_stack:
                        if func_stack.pop():
                            agg_depth -= 1
                    i += 1
                else:
                    i += 1
            if agg_depth > 0:
                continue  # Inside aggregation/iterator — row-level ref
            # Bare column ref not inside any aggregation → wrap.
            # Type-aware: SUM for numeric, MAX for string/date,
            # MAX(IF(col, 1, 0)) for Boolean.
            old_ref = m_col.group(0)
            tbl_name = m_col.group(1).replace("''", "'")
            is_same_table = tbl_name == result_table.get("name", "")
            if is_same_table and col_name in _bool_cols_for_xtable:
                new_ref = f"MAX(IF({old_ref}, 1, 0))"
            elif is_same_table and col_name in _text_date_cols_for_xtable:
                new_ref = f"MAX({old_ref})"
            else:
                new_ref = f"SUM({old_ref})"
            new_expr = new_expr[:m_col.start()] + new_ref + new_expr[m_col.end():]
            logger.debug(
                "Wrapped bare column ref %s → SUM(%s) in measure '%s'",
                old_ref, old_ref, meas.get("name", ""),
            )
        if new_expr != expr:
            meas["expression"] = new_expr

    # Inject accumulated M steps into the partition (replaces DAX calc cols)
    if m_calc_steps:
        _inject_m_steps_into_partition(result_table, m_calc_steps)

    # Propagate lineage metadata from source table (merge pipeline)
    if table.get('_source_workbooks'):
        result_table['_source_workbooks'] = table['_source_workbooks']
    if table.get('_merge_action'):
        result_table['_merge_action'] = table['_merge_action']

    return result_table


def _build_relationships(relationships):
    """
    Create relationships from Tableau joins.

    Args:
        relationships: List of extracted relations with left/right {table, column}

    Returns:
        list: Relationship definitions
    """
    result = []

    for rel in relationships:
        left = rel.get('left', {})
        right = rel.get('right', {})

        from_table = left.get('table', '')
        from_column = left.get('column', '')
        to_table = right.get('table', '')
        to_column = right.get('column', '')

        if not from_table or not to_table or not from_column or not to_column:
            continue

        join_type = rel.get('type', 'left')
        result.append({
            "name": f"Relationship-{len(result)+1}",
            "fromTable": from_table,
            "fromColumn": from_column,
            "toTable": to_table,
            "toColumn": to_column,
            "joinType": join_type,
            "crossFilteringBehavior": "bothDirections" if join_type == 'full' else "oneDirection"
        })

    return result


def _detect_join_graph_issues(relationships):
    """Detect multi-hop chains and diamond joins in the relationship graph.

    Returns a list of warning dicts:
      - {'type': 'diamond', 'tables': [A, B, C, D], 'message': ...}
      - {'type': 'multi_hop', 'chain': [A, B, C], 'message': ...}
    """
    warnings = []
    # Build adjacency list (undirected)
    adj = {}  # table -> set of connected tables
    for rel in relationships:
        ft = rel.get('fromTable', '')
        tt = rel.get('toTable', '')
        if ft and tt:
            adj.setdefault(ft, set()).add(tt)
            adj.setdefault(tt, set()).add(ft)

    # Detect multi-hop chains: A→B→C where A has no direct link to C
    all_tables = list(adj.keys())
    for a in all_tables:
        for b in adj.get(a, set()):
            for c in adj.get(b, set()):
                if c != a and c not in adj.get(a, set()):
                    warnings.append({
                        'type': 'multi_hop',
                        'chain': [a, b, c],
                        'message': (
                            f"Multi-hop join path: '{a}' → '{b}' → '{c}'. "
                            f"PBI may need an intermediate relationship or bridge table."
                        ),
                    })

    # Detect diamond joins: A→B, A→C, B→D, C→D
    for a in all_tables:
        neighbors = list(adj.get(a, set()))
        for i, b in enumerate(neighbors):
            for c in neighbors[i + 1:]:
                shared = adj.get(b, set()) & adj.get(c, set()) - {a}
                for d in shared:
                    warnings.append({
                        'type': 'diamond',
                        'tables': [a, b, c, d],
                        'message': (
                            f"Diamond join: '{a}'→'{b}'→'{d}' and "
                            f"'{a}'→'{c}'→'{d}'. May cause ambiguous paths in PBI."
                        ),
                    })

    # Deduplicate
    seen = set()
    unique = []
    for w in warnings:
        key = (w['type'], tuple(sorted(w.get('chain', w.get('tables', [])))))
        if key not in seen:
            seen.add(key)
            unique.append(w)
    return unique


def _infer_cross_table_relationships(model):
    """
    Infer relationships between tables when DAX expressions reference
    columns from another table but no explicit relationship exists.

    Algorithm:
    1. Scan all DAX expressions (measures, calc columns, RLS roles)
    2. Find 'TableName'[ColumnName] cross-table references
    3. For each unconnected table pair, find the best column-name match
    4. Create a manyToOne relationship (fact->dimension)
    """
    tables = model["model"]["tables"]
    relationships = model["model"]["relationships"]

    # Build existing relationship pairs (bidirectional)
    connected_pairs = set()
    for rel in relationships:
        ft = rel.get("fromTable", "")
        tt = rel.get("toTable", "")
        connected_pairs.add((ft, tt))
        connected_pairs.add((tt, ft))

    # Build table->columns map
    table_columns = {}
    for table in tables:
        tname = table.get("name", "")
        table_columns[tname] = {col.get("name", "") for col in table.get("columns", [])}

    cross_ref_pattern = re.compile(r"'([^']+)'\[([^\]]+)\]")

    # Collect needed table pairs from DAX cross-table references
    needed_pairs = set()

    for table in tables:
        tname = table.get("name", "")
        for measure in table.get("measures", []):
            expr = measure.get("expression", "")
            for match in cross_ref_pattern.finditer(expr):
                ref_table = match.group(1)
                if ref_table != tname and ref_table in table_columns:
                    needed_pairs.add((tname, ref_table))
        for col in table.get("columns", []):
            if col.get("isCalculated"):
                expr = col.get("expression", "")
                for match in cross_ref_pattern.finditer(expr):
                    ref_table = match.group(1)
                    if ref_table != tname and ref_table in table_columns:
                        needed_pairs.add((tname, ref_table))

    # Scan RLS roles
    for role in model["model"].get("roles", []):
        for tp in role.get("tablePermissions", []):
            perm_table = tp.get("name", "")
            expr = tp.get("filterExpression", "")
            for match in cross_ref_pattern.finditer(expr):
                ref_table = match.group(1)
                if ref_table != perm_table and ref_table in table_columns:
                    needed_pairs.add((perm_table, ref_table))

    # For each needed pair, find a matching column for the relationship
    for (source_table, ref_table) in needed_pairs:
        if (source_table, ref_table) in connected_pairs:
            continue

        source_cols = table_columns.get(source_table, set())
        ref_cols = table_columns.get(ref_table, set())

        best_match = None
        best_score = 0

        for sc in source_cols:
            for rc in ref_cols:
                sc_lower = sc.lower()
                rc_lower = rc.lower()
                score = 0

                if sc_lower == rc_lower:
                    score = 100
                elif sc_lower in rc_lower and len(sc_lower) >= 3:
                    score = 50 - (len(rc) - len(sc))
                elif rc_lower in sc_lower and len(rc_lower) >= 3:
                    score = 50 - (len(sc) - len(rc))
                elif len(sc_lower) >= 3 and len(rc_lower) >= 3:
                    common = 0
                    for a, b in zip(sc_lower, rc_lower):
                        if a == b:
                            common += 1
                        else:
                            break
                    if common >= 3:
                        score = common * 5

                if score > best_score:
                    best_score = score
                    best_match = (sc, rc)

        if best_match and best_score >= 15:
            from_col, to_col = best_match

            if len(source_cols) >= len(ref_cols):
                fact_table, dim_table = source_table, ref_table
                fk_col, pk_col = from_col, to_col
            else:
                fact_table, dim_table = ref_table, source_table
                fk_col, pk_col = to_col, from_col

            relationships.append({
                "name": f"inferred_{fact_table}_{dim_table}",
                "fromTable": fact_table,
                "fromColumn": fk_col,
                "toTable": dim_table,
                "toColumn": pk_col,
                "crossFilteringBehavior": "oneDirection"
            })

            connected_pairs.add((source_table, ref_table))
            connected_pairs.add((ref_table, source_table))

    # Pass 2: Proactive key-column matching for unconnected tables
    # Looks for columns with identical names that look like keys (ID, Key, Code, etc.)
    _KEY_SUFFIXES = {'id', 'key', 'code', 'no', 'number', 'num', 'pk', 'fk', 'sk'}
    all_table_names = list(table_columns.keys())

    for i, t1 in enumerate(all_table_names):
        for t2 in all_table_names[i + 1:]:
            if (t1, t2) in connected_pairs:
                continue
            # Skip auto-generated tables (Calendar, parameters)
            if t1 == 'Calendar' or t2 == 'Calendar':
                continue

            t1_cols = table_columns.get(t1, set())
            t2_cols = table_columns.get(t2, set())

            best_col = None
            best_score = 0

            common_cols = t1_cols & t2_cols
            for col in common_cols:
                col_lower = col.lower().rstrip('_')
                # Score: exact ID/key column names get highest priority
                parts = re.split(r'[_\s]', col_lower)
                has_key_suffix = any(p in _KEY_SUFFIXES for p in parts)
                if has_key_suffix:
                    score = 90
                elif col_lower.endswith('name'):
                    score = 40
                else:
                    score = 20  # Any common column
                if score > best_score:
                    best_score = score
                    best_col = col

            if best_col and best_score >= 40:
                # Fact = table with more columns, dim = fewer
                if len(t1_cols) >= len(t2_cols):
                    fact_table, dim_table = t1, t2
                else:
                    fact_table, dim_table = t2, t1

                relationships.append({
                    "name": f"inferred_{fact_table}_{dim_table}",
                    "fromTable": fact_table,
                    "fromColumn": best_col,
                    "toTable": dim_table,
                    "toColumn": best_col,
                    "crossFilteringBehavior": "oneDirection"
                })
                connected_pairs.add((t1, t2))
                connected_pairs.add((t2, t1))


def _detect_many_to_many(model, datasources):
    """
    Determine cardinality for each relationship.

    Strategy — based on Tableau join type + column-count ratio heuristic:
    - Full joins → manyToMany (ambiguous direction)
    - Left/Inner/Right joins:
      - If to-table column count ≥ 70% of from-table → manyToMany (peer/fact tables)
      - If to-table column count < 70% of from-table → manyToOne (lookup table)

    The 70% threshold detects when two tables have similar schemas (both are
    fact tables, e.g. Tableau data blend artifacts) and a manyToOne assumption
    would fail because the 'one' side has duplicates.
    """
    # Build table column count map
    table_col_counts = {}
    for table in model['model'].get('tables', []):
        tname = table.get('name', '')
        table_col_counts[tname] = len(table.get('columns', []))

    for rel in model['model']['relationships']:
        to_table = rel.get('toTable', '')
        to_col = rel.get('toColumn', '')
        from_table = rel.get('fromTable', '')
        join_type = rel.get('joinType', 'left')

        if join_type == 'full':
            rel['fromCardinality'] = 'many'
            rel['toCardinality'] = 'many'
            rel['crossFilteringBehavior'] = 'bothDirections'
            print(f"  ⚠️  Relation → '{to_table}.{to_col}' set to manyToMany (full join).")
        else:
            # Column-count ratio heuristic
            from_cols = table_col_counts.get(from_table, 0)
            to_cols = table_col_counts.get(to_table, 0)

            # Check if this is an inferred relationship (Phase 10) joining on
            # a non-key column — default to manyToMany since we can't verify
            # uniqueness without data.
            rel_name = rel.get('name', '')
            is_inferred = rel_name.startswith('inferred_')
            to_col_lower = to_col.lower()
            _key_indicators = {'id', 'key', 'code', 'pk', 'fk', 'sk', 'no', 'number', 'num'}
            is_key_column = any(kw in to_col_lower.split() or to_col_lower.endswith(kw) or to_col_lower.startswith(kw)
                                for kw in _key_indicators)

            if is_inferred and not is_key_column:
                # Inferred relationship on a non-key column → manyToMany (safe default)
                rel['fromCardinality'] = 'many'
                rel['toCardinality'] = 'many'
                rel['crossFilteringBehavior'] = 'bothDirections'
                print(f"  ⚠️  Relation → '{to_table}.{to_col}' set to manyToMany (inferred, non-key column).")
            elif from_cols > 0 and to_cols >= 0.7 * from_cols:
                # Both tables have similar column counts → peer/fact tables
                rel['fromCardinality'] = 'many'
                rel['toCardinality'] = 'many'
                rel['crossFilteringBehavior'] = 'bothDirections'
                print(f"  ⚠️  Relation → '{to_table}.{to_col}' set to manyToMany (peer table, {to_cols}/{from_cols} cols ≥ 70%).")
            elif to_table == 'Calendar':
                # Calendar.Date is guaranteed unique (generated table)
                rel['fromCardinality'] = 'many'
                rel['toCardinality'] = 'one'
                rel['crossFilteringBehavior'] = 'oneDirection'
                print(f"  ✓  Relation → '{to_table}.{to_col}' set to manyToOne (Calendar table).")
            else:
                # Default to manyToMany — we cannot verify uniqueness without data
                # PBI silently drops manyToOne relationships if the "one" side has duplicates
                rel['fromCardinality'] = 'many'
                rel['toCardinality'] = 'many'
                rel['crossFilteringBehavior'] = 'bothDirections'
                print(f"  ⚠️  Relation → '{to_table}.{to_col}' set to manyToMany (cannot verify uniqueness).")


def _fix_related_for_many_to_many(model):
    """
    Replace RELATED('table'[col]) with LOOKUPVALUE() for manyToMany relationships.
    """
    # Build lookup: (current_table, referenced_table) → (ref_join_col, current_join_col)
    m2m_pairs = {}
    for rel in model['model']['relationships']:
        if rel.get('fromCardinality') == 'many' and rel.get('toCardinality') == 'many':
            to_table = rel.get('toTable', '')
            to_col = rel.get('toColumn', '')
            from_table = rel.get('fromTable', '')
            from_col = rel.get('fromColumn', '')
            # From from_table context, RELATED('to_table'[x]) uses to_col ↔ from_col
            m2m_pairs.setdefault((from_table, to_table), (to_col, from_col))
            # From to_table context, RELATED('from_table'[x]) uses from_col ↔ to_col
            m2m_pairs.setdefault((to_table, from_table), (from_col, to_col))

    if not m2m_pairs:
        return

    for table in model['model']['tables']:
        current_table = table.get('name', '')
        for col in table.get('columns', []):
            expr = col.get('expression', '')
            if expr and 'RELATED(' in expr:
                col['expression'] = _replace_related_with_lookupvalue(
                    expr, m2m_pairs, current_table)
        for measure in table.get('measures', []):
            expr = measure.get('expression', '')
            if expr and 'RELATED(' in expr:
                # First pass: replace RELATED using the measure's own table
                expr = _replace_related_with_lookupvalue(
                    expr, m2m_pairs, current_table)
                # Second pass: replace RELATED inside SUMX/AVERAGEX/etc.
                # where the iteration table is the context, not the measure table
                expr = _replace_related_in_aggx_context(expr, m2m_pairs)
                measure['expression'] = expr


def _replace_related_with_lookupvalue(expr, m2m_pairs, current_table=''):
    """Replace RELATED('table'[col]) with LOOKUPVALUE() for m2m tables."""
    pattern = r"RELATED\(('([^']+)'|([A-Za-z0-9_][A-Za-z0-9_ .-]*))\[([^\]]*(?:\]\][^\]]*)*)\]\)"

    def replacer(match):
        table_name = match.group(2) if match.group(2) else match.group(3)
        col_name = match.group(4)

        pair_key = (current_table, table_name)
        if pair_key not in m2m_pairs:
            return match.group(0)

        ref_join_col, current_join_col = m2m_pairs[pair_key]

        # Escape apostrophes in TMDL table names ('O''Reilly')
        t_esc = table_name.replace("'", "''")
        ct_esc = current_table.replace("'", "''")
        t_ref = f"'{t_esc}'" if not table_name.isidentifier() else table_name
        ct_ref = f"'{ct_esc}'" if not current_table.isidentifier() else current_table

        return f"LOOKUPVALUE({t_ref}[{col_name}], {t_ref}[{ref_join_col}], {ct_ref}[{current_join_col}])"

    return re.sub(pattern, replacer, expr)


def _replace_related_in_aggx_context(expr, m2m_pairs):
    """Replace RELATED() inside SUMX/AVERAGEX/etc. using the iteration table.

    Inside ``SUMX('Opportunities', ...RELATED('Created By'[col])...)``,
    the RELATED navigates from ``Opportunities`` (iteration context) to
    ``Created By``.  The standard ``_replace_related_with_lookupvalue``
    uses the measure's own table, which is wrong for iterator context.
    """
    if 'RELATED(' not in expr:
        return expr

    aggx_pattern = re.compile(
        r'\b(SUMX|AVERAGEX|MINX|MAXX|COUNTX|STDEVX\.S|STDEVX\.P|MEDIANX)\s*\(\s*'
        r"'([^']+)'\s*,\s*",
        re.IGNORECASE)

    result = expr
    for m in aggx_pattern.finditer(expr):
        iter_table = m.group(2)
        body_start = m.end()
        # Find the matching closing paren for the AGGX call
        depth = 1
        pos = body_start
        while pos < len(result) and depth > 0:
            if result[pos] == '(':
                depth += 1
            elif result[pos] == ')':
                depth -= 1
            pos += 1
        if depth != 0:
            continue
        body = result[body_start:pos - 1]
        if 'RELATED(' not in body:
            continue
        new_body = _replace_related_with_lookupvalue(
            body, m2m_pairs, iter_table)
        if new_body != body:
            result = result[:body_start] + new_body + result[pos - 1:]

    return result


def _fix_relationship_type_mismatches(model):
    """
    Fix type mismatches between relationship key columns.
    Aligns the toColumn ('one' side) to the fromColumn ('many' side) type.
    """
    tables = {t.get('name', ''): t for t in model['model']['tables']}

    pbi_to_m = {
        'String': 'type text',
        'string': 'type text',
        'Int64': 'Int64.Type',
        'int64': 'Int64.Type',
        'Double': 'type number',
        'double': 'type number',
        'Boolean': 'type logical',
        'boolean': 'type logical',
        'DateTime': 'type datetime',
        'dateTime': 'type datetime',
    }

    for rel in model['model']['relationships']:
        from_table = tables.get(rel.get('fromTable', ''))
        to_table = tables.get(rel.get('toTable', ''))
        if not from_table or not to_table:
            continue

        from_col_name = rel.get('fromColumn', '')
        to_col_name = rel.get('toColumn', '')

        from_col = next((c for c in from_table.get('columns', []) if c.get('name') == from_col_name), None)
        to_col = next((c for c in to_table.get('columns', []) if c.get('name') == to_col_name), None)
        if not from_col or not to_col:
            continue

        from_type = from_col.get('dataType', 'string')
        to_type = to_col.get('dataType', 'string')

        if from_type == to_type:
            continue

        print(f"  \u26a0\ufe0f  Type mismatch: {rel.get('fromTable')}.{from_col_name} ({from_type}) "
              f"-> {rel.get('toTable')}.{to_col_name} ({to_type}). Aligning to {from_type}.")

        old_type = to_type
        to_col['dataType'] = from_type

        if from_type.lower() == 'string':
            to_col['summarizeBy'] = 'none'
            if 'formatString' in to_col:
                del to_col['formatString']

        old_m_type = pbi_to_m.get(old_type, '')
        new_m_type = pbi_to_m.get(from_type, '')
        if old_m_type and new_m_type:
            for partition in to_table.get('partitions', []):
                source = partition.get('source', {})
                if isinstance(source, dict) and 'expression' in source:
                    expr = source['expression']
                    old_pattern = f'"{to_col_name}", {old_m_type}'
                    new_pattern = f'"{to_col_name}", {new_m_type}'
                    if old_pattern in expr:
                        source['expression'] = expr.replace(old_pattern, new_pattern)
        else:
            print(f"    \u26a0\ufe0f  Cannot map M types for {to_col_name}: {repr(old_type)} / {repr(from_type)}")


def _map_semantic_role_to_category(semantic_role, col_name=''):
    """Map a Tableau semantic-role to a Power BI dataCategory."""
    role_map = {
        '[Country].[Name]': 'Country',
        '[Country].[ISO3166_2]': 'Country',
        '[State].[Name]': 'StateOrProvince',
        '[State].[Abbreviation]': 'StateOrProvince',
        '[County].[Name]': 'County',
        '[City].[Name]': 'City',
        '[ZipCode].[Name]': 'PostalCode',
        '[Latitude]': 'Latitude',
        '[Longitude]': 'Longitude',
        '[Geographical].[Latitude]': 'Latitude',
        '[Geographical].[Longitude]': 'Longitude',
        '[Address]': 'Address',
        '[Continent].[Name]': 'Continent',
    }
    if semantic_role in role_map:
        return role_map[semantic_role]

    if not semantic_role:
        name_lower = col_name.lower()
        if 'latitude' in name_lower or name_lower in ('lat', 'lat_upgrade'):
            return 'Latitude'
        if 'longitude' in name_lower or name_lower in ('lon', 'lng', 'long', 'long_upgrade'):
            return 'Longitude'
        if name_lower in ('city', 'ville', 'commune', 'label') and 'code' not in name_lower:
            return 'City'
        if name_lower in ('country', 'pays') or name_lower.startswith('pays/'):
            return 'Country'
        if any(x in name_lower for x in ['region', '\u00e9tat', 'state', 'province', 'd\u00e9partement']):
            return 'StateOrProvince'
        if 'postal' in name_lower or 'zip' in name_lower or 'code_postal' in name_lower:
            return 'PostalCode'

    return None


def _get_display_folder(datatype, role):
    """Determine the display folder based on type and role."""
    if role == 'dimension':
        return 'Dimensions'
    if datatype in ('real', 'integer', 'number'):
        return 'Measures'
    if datatype in ('date', 'datetime'):
        return 'Time Intelligence'
    if datatype == 'boolean':
        return 'Flags'
    return 'Calculations'


def _process_sets_groups_bins(model, extra_objects, main_table_name, column_table_map):
    """Add sets, groups and bins as Power Query M columns (fallback: DAX calc cols)."""
    if not main_table_name:
        return

    main_table = None
    for table in model["model"]["tables"]:
        if table.get("name") == main_table_name:
            main_table = table
            break
    if not main_table:
        return

    existing_cols = {col.get("name", "") for col in main_table.get("columns", [])}
    m_steps = []  # Accumulated M steps

    # Sets -> boolean column
    for s in extra_objects.get('sets', []):
        set_name = s.get('name', '')
        if not set_name or set_name in existing_cols:
            continue

        members = s.get('members', [])
        formula = s.get('formula', '')

        if formula:
            dax_expr = formula
        elif members:
            escaped = [f'"{m.replace(chr(34), chr(34)+chr(34))}"' for m in members[:50]]
            dax_expr = f"'{main_table_name}'[{set_name}] IN {{{', '.join(escaped)}}}"
        else:
            dax_expr = 'TRUE()'

        m_expr = _dax_to_m_expression(dax_expr, main_table_name)
        if m_expr is not None:
            m_steps.append(m_transform_add_column(set_name, f'each {m_expr}', 'type logical'))
            main_table["columns"].append({
                "name": set_name,
                "dataType": "Boolean",
                "sourceColumn": set_name,
                "summarizeBy": "none",
                "displayFolder": "Sets"
            })
        else:
            main_table["columns"].append({
                "name": set_name,
                "dataType": "Boolean",
                "expression": dax_expr,
                "summarizeBy": "none",
                "isCalculated": True,
                "displayFolder": "Sets"
            })
        existing_cols.add(set_name)

    # Groups -> SWITCH / concatenation column
    for g in extra_objects.get('groups', []):
        group_name = g.get('name', '')
        if not group_name or group_name in existing_cols:
            continue

        group_type = g.get('group_type', 'values')
        members = g.get('members', {})
        source_field = g.get('source_field', '').replace('[', '').replace(']', '')
        source_fields = g.get('source_fields', [])

        if group_type == 'combined' and source_fields:
            calc_map_lookup = {}
            # Also build internal-name → caption mapping from datasource columns
            col_caption_map = {}
            for ds in extra_objects.get('_datasources', []):
                for calc in ds.get('calculations', []):
                    raw = calc.get('name', '').replace('[', '').replace(']', '')
                    cap = (calc.get('caption', '') or raw).replace('[', '').replace(']', '')
                    calc_map_lookup[raw] = cap
                for tbl in ds.get('tables', []):
                    for col_info in tbl.get('columns', []):
                        col_name = col_info.get('name', '').replace('[', '').replace(']', '')
                        col_cap = col_info.get('caption', '')
                        if col_cap and col_name != col_cap:
                            col_caption_map[col_name] = col_cap
            # Also resolve from existing_cols (columns already in the BIM table)
            for table_obj in model.get('model', {}).get('tables', []):
                for col in table_obj.get('columns', []):
                    col_name = col.get('name', '')
                    src_col = col.get('sourceColumn', '')
                    if src_col and src_col != col_name:
                        col_caption_map[src_col] = col_name
            for table_obj in model.get('model', {}).get('tables', []):
                for col in table_obj.get('columns', []):
                    if col.get('isCalculated'):
                        col_name = col.get('name', '')
                        if col_name and col_name not in column_table_map:
                            column_table_map[col_name] = table_obj.get('name', main_table_name)
                for meas in table_obj.get('measures', []):
                    meas_name = meas.get('name', '')
                    if meas_name and meas_name not in column_table_map:
                        column_table_map[meas_name] = table_obj.get('name', main_table_name)

            # Date-part derivation prefix → M date function mapping
            _DATE_PART_M_FUNC = {
                'yr': 'Date.Year', 'tyr': 'Date.Year',
                'mn': 'Date.Month', 'tmn': 'Date.Month',
                'dy': 'Date.Day', 'tdy': 'Date.Day',
                'qr': 'Date.QuarterOfYear', 'tqr': 'Date.QuarterOfYear',
                'wk': 'Date.WeekOfYear', 'twk': 'Date.WeekOfYear',
                'hr': 'Time.Hour', 'mt': 'Time.Minute', 'sc': 'Time.Second',
            }
            # Also map function names from group name (e.g. YEAR, MONTH)
            _FUNC_NAME_M = {
                'YEAR': 'Date.Year', 'MONTH': 'Date.Month', 'DAY': 'Date.Day',
                'QUARTER': 'Date.QuarterOfYear', 'WEEK': 'Date.WeekOfYear',
                'HOUR': 'Time.Hour', 'MINUTE': 'Time.Minute', 'SECOND': 'Time.Second',
            }
            # Parse group name to extract function wrappers per position
            # e.g. "Action (Category,YEAR(Order Date),MONTH(Order Date))"
            #  → [None, 'Date.Year', 'Date.Month']
            name_func_map = []
            _gn_match = re.match(r'^.*?\((.+)\)\s*$', group_name)
            if _gn_match:
                _gn_inner = _gn_match.group(1)
                _gn_parts, _gn_depth, _gn_cur = [], 0, []
                for _ch in _gn_inner:
                    if _ch == '(':
                        _gn_depth += 1
                        _gn_cur.append(_ch)
                    elif _ch == ')':
                        _gn_depth -= 1
                        _gn_cur.append(_ch)
                    elif _ch == ',' and _gn_depth == 0:
                        _gn_parts.append(''.join(_gn_cur).strip())
                        _gn_cur = []
                    else:
                        _gn_cur.append(_ch)
                _gn_parts.append(''.join(_gn_cur).strip())
                for _gp in _gn_parts:
                    _fm = re.match(r'^(YEAR|MONTH|DAY|QUARTER|WEEK|HOUR|MINUTE|SECOND)\(', _gp, re.IGNORECASE)
                    name_func_map.append(_FUNC_NAME_M.get(_fm.group(1).upper()) if _fm else None)

            m_parts = []
            dax_parts = []
            for idx, sf_raw in enumerate(source_fields):
                # 1. Extract derivation prefix before cleaning
                prefix_match = _RE_TMDL_DERIVATION_PREFIX.match(sf_raw)
                date_prefix = prefix_match.group(1) if prefix_match else None
                # 2. Clean and resolve field name
                sf = _clean_tableau_field_ref(sf_raw)
                resolved = calc_map_lookup.get(sf, sf)
                resolved = _clean_tableau_field_ref(resolved)
                # Resolve internal Tableau field name to caption (e.g. "Postal Code" → "Code postal")
                resolved = col_caption_map.get(resolved, resolved)
                # Also check if the resolved name exists in existing columns
                if resolved not in existing_cols and sf in col_caption_map:
                    resolved = col_caption_map[sf]
                # Validate: skip fields that don't exist in any known column set
                if resolved not in existing_cols and resolved not in column_table_map:
                    print(f"  ⚠ Group '{group_name}': skipping unknown source field '{sf_raw}' (resolved='{resolved}')")
                    continue
                # 3. Build M column reference
                escaped_m = resolved.replace('"', '""')
                m_ref = f'[#"{escaped_m}"]'
                # 4. Apply date-part function: first from derivation prefix, then from group name
                m_func = None
                if date_prefix and date_prefix in _DATE_PART_M_FUNC:
                    m_func = _DATE_PART_M_FUNC[date_prefix]
                elif idx < len(name_func_map) and name_func_map[idx]:
                    m_func = name_func_map[idx]
                if m_func:
                    m_ref = f'{m_func}({m_ref})'
                # 5. Wrap in Text.From() for safe text concatenation
                m_ref = f'Text.From({m_ref})'
                m_parts.append(m_ref)
                # Also build DAX parts for fallback
                table_ref = column_table_map.get(resolved, column_table_map.get(sf, main_table_name))
                escaped_col = resolved.replace(']', ']]')
                ref = f"'{table_ref}'[{escaped_col}]"
                if table_ref != main_table_name:
                    ref = f"RELATED({ref})"
                dax_parts.append(ref)

            if not m_parts:
                # All source fields were unknown — skip this group entirely
                print(f"  ⚠ Group '{group_name}': no valid source fields found, skipping")
                continue
            # Build M expression directly (type-safe concatenation)
            if len(m_parts) == 1:
                m_concat_expr = m_parts[0]
            else:
                m_concat_expr = ' & " | " & '.join(m_parts)
            m_steps.append(m_transform_add_column(group_name, f'each {m_concat_expr}', 'type text'))
            main_table["columns"].append({
                "name": group_name,
                "dataType": "String",
                "sourceColumn": group_name,
                "summarizeBy": "none",
                "displayFolder": "Groups"
            })
            existing_cols.add(group_name)
            continue

        elif members and source_field:
            total_values = sum(len(v) for v in members.values())
            # Large groups: use M table-join lookup (avoids M engine complexity limit)
            if total_values > 100:
                escaped_src = source_field.replace('"', '""')
                escaped_grp = group_name.replace('"', '""')
                rows = []
                for label, values in members.items():
                    el = label.replace('"', '""')
                    for val in values:
                        ev = val.replace('"', '""')
                        rows.append(f'{{"{ev}", "{el}"}}')
                map_expr = (
                    f'#table(type table [key = text, grp = text], '
                    f'{{{", ".join(rows)}}})'
                )
                safe_tag = re.sub(r'[^A-Za-z0-9_]', '_', group_name)
                m_steps.append((
                    f'#"Join_{safe_tag}"',
                    f'Table.NestedJoin({{prev}}, {{"{escaped_src}"}}, {map_expr}, {{"key"}}, "_lkp_{safe_tag}", JoinKind.LeftOuter)'
                ))
                m_steps.append((
                    f'#"Expand_{safe_tag}"',
                    f'Table.ExpandTableColumn({{prev}}, "_lkp_{safe_tag}", {{"grp"}}, {{"{escaped_grp}"}})'
                ))
                m_steps.append((
                    f'#"Fill_{safe_tag}"',
                    f'Table.ReplaceValue({{prev}}, null, "Other", Replacer.ReplaceValue, {{"{escaped_grp}"}})'
                ))
                main_table["columns"].append({
                    "name": group_name,
                    "dataType": "String",
                    "sourceColumn": group_name,
                    "summarizeBy": "none",
                    "displayFolder": "Groups"
                })
                existing_cols.add(group_name)
                continue

            table_ref = column_table_map.get(source_field, main_table_name)
            cases = []
            for label, values in members.items():
                escaped_label = label.replace('"', '""')
                for val in values:
                    escaped_val = val.replace('"', '""')
                    cases.append(f'"{escaped_val}", "{escaped_label}"')

            if cases:
                dax_expr = f"SWITCH('{table_ref}'[{source_field}], {', '.join(cases)}, \"Other\")"
            else:
                dax_expr = f"'{table_ref}'[{source_field}]"
        else:
            dax_expr = '""'

        m_expr = _dax_to_m_expression(dax_expr, main_table_name)
        if m_expr is not None:
            m_steps.append(m_transform_add_column(group_name, f'each {m_expr}', 'type text'))
            main_table["columns"].append({
                "name": group_name,
                "dataType": "String",
                "sourceColumn": group_name,
                "summarizeBy": "none",
                "displayFolder": "Groups"
            })
        else:
            main_table["columns"].append({
                "name": group_name,
                "dataType": "String",
                "expression": dax_expr,
                "summarizeBy": "none",
                "isCalculated": True,
                "displayFolder": "Groups"
            })
        existing_cols.add(group_name)

    # Bins -> FLOOR column
    for b in extra_objects.get('bins', []):
        bin_name = b.get('name', '')
        if not bin_name or bin_name in existing_cols:
            continue

        source_field = b.get('source_field', '').replace('[', '').replace(']', '')
        bin_size = b.get('size', '10')

        if source_field:
            table_ref = column_table_map.get(source_field, main_table_name)
            dax_expr = f"FLOOR('{table_ref}'[{source_field}], {bin_size})"
        else:
            dax_expr = '0'

        m_expr = _dax_to_m_expression(dax_expr, main_table_name)
        if m_expr is not None:
            m_steps.append(m_transform_add_column(bin_name, f'each {m_expr}', 'type number'))
            main_table["columns"].append({
                "name": bin_name,
                "dataType": "Double",
                "sourceColumn": bin_name,
                "summarizeBy": "none",
                "displayFolder": "Bins"
            })
        else:
            main_table["columns"].append({
                "name": bin_name,
                "dataType": "Double",
                "expression": dax_expr,
                "summarizeBy": "none",
                "isCalculated": True,
                "displayFolder": "Bins"
            })
        existing_cols.add(bin_name)

    # Inject accumulated M steps into the partition
    if m_steps:
        _inject_m_steps_into_partition(main_table, m_steps)


def _apply_hierarchies(model, hierarchies, column_table_map):
    """Apply Tableau hierarchies (drill-paths) to the model."""
    if not hierarchies:
        return

    for h in hierarchies:
        h_name = h.get('name', '')
        levels = h.get('levels', [])
        if not h_name or not levels:
            continue

        first_level = levels[0]
        target_table_name = column_table_map.get(first_level, '')
        if not target_table_name:
            continue

        for table in model["model"]["tables"]:
            if table.get("name") == target_table_name:
                table_col_names = {col.get("name", "") for col in table.get("columns", [])}
                valid_levels = [l for l in levels if l in table_col_names]

                if valid_levels:
                    if "hierarchies" not in table:
                        table["hierarchies"] = []

                    hierarchy = {
                        "name": h_name,
                        "levels": [
                            {"name": lvl, "ordinal": idx, "column": lvl}
                            for idx, lvl in enumerate(valid_levels)
                        ]
                    }
                    table["hierarchies"].append(hierarchy)
                break


def _auto_date_hierarchies(model):
    """Auto-generate Year > Quarter > Month > Day hierarchies for date columns.

    For every date/dateTime column that does not already belong to a
    user-defined hierarchy, we create Power Query M columns
    (Date.Year, Date.QuarterOfYear, Date.Month, Date.Day)
    and a hierarchy definition on the same table.
    """
    DATE_TYPES = {'dateTime', 'date'}
    # (label, M function, BIM dataType, ordinal)
    PARTS = [
        ('Year', 'Date.Year', 'int64', 0),
        ('Quarter', 'Date.QuarterOfYear', 'int64', 1),
        ('Month', 'Date.Month', 'int64', 2),
        ('Day', 'Date.Day', 'int64', 3),
    ]

    for table in model.get('model', {}).get('tables', []):
        columns = table.get('columns', [])
        existing_hierarchies = table.get('hierarchies', [])

        # Collect columns already used in a hierarchy
        hier_cols = set()
        for h in existing_hierarchies:
            for lvl in h.get('levels', []):
                hier_cols.add(lvl.get('column', ''))

        existing_col_names = {c.get('name', '') for c in columns}

        m_steps = []  # M steps for this table

        for col in list(columns):  # iterate copy — we may append
            col_type = col.get('dataType', '')
            col_name = col.get('name', '')
            if col_type not in DATE_TYPES:
                continue
            if col_name in hier_cols:
                continue  # already in a user-defined hierarchy

            # Build hierarchy name scoped to the column
            hier_name = f"{col_name} Hierarchy"

            # Skip if we already auto-generated this one (idempotency)
            if any(h.get('name') == hier_name for h in existing_hierarchies):
                continue

            # Add M-based columns for the parts (skip if name clashes)
            calc_col_names = []
            for part_label, m_fn, dt, _ in PARTS:
                calc_name = f"{col_name} {part_label}"
                if calc_name in existing_col_names:
                    calc_col_names.append(calc_name)
                    continue  # already exists (e.g. from Tableau extraction)

                col_ref = f'[{col_name}]' if not any(c in _M_SPECIAL_CHARS for c in col_name) else f'[#"{col_name}"]'
                m_steps.append(m_transform_add_column(
                    calc_name,
                    f'each {m_fn}({col_ref})',
                    'Int64.Type'
                ))
                columns.append({
                    'name': calc_name,
                    'dataType': dt,
                    'sourceColumn': calc_name,
                    'isHidden': True,
                })
                existing_col_names.add(calc_name)
                calc_col_names.append(calc_name)

            # Create the hierarchy
            hierarchy = {
                'name': hier_name,
                'levels': [
                    {'name': PARTS[i][0], 'ordinal': i, 'column': calc_col_names[i]}
                    for i in range(len(calc_col_names))
                ],
            }
            if 'hierarchies' not in table:
                table['hierarchies'] = []
            table['hierarchies'].append(hierarchy)

        # Inject accumulated M steps into the table's partition
        if m_steps:
            _inject_m_steps_into_partition(table, m_steps)


def _create_parameter_tables(model, parameters, main_table_name):
    """Create What-If parameter tables for Tableau parameters.

    - Range parameters (integer/real): GENERATESERIES(min, max, step) table
    - List parameters (string/boolean): DATATABLE with domain values
    - Any parameters (no domain): measure with default value on main table
    """
    if not parameters:
        return

    type_map = {
        'integer': ('int64', 'INTEGER'),
        'real': ('double', 'DOUBLE'),
        'date': ('dateTime', 'DATETIME'),
        'datetime': ('dateTime', 'DATETIME'),
        'boolean': ('boolean', 'BOOLEAN'),
        'string': ('string', 'STRING'),
    }

    for param in parameters:
        caption = param.get('caption', '')
        if not caption:
            continue

        datatype = param.get('datatype', 'string')
        default_value = param.get('value', '').strip('"')
        domain_type = param.get('domain_type', 'any')
        allowable_values = param.get('allowable_values', [])

        pbi_type, dax_type = type_map.get(datatype, ('string', 'STRING'))

        if datatype == 'string':
            default_expr = f'"{default_value}"'
        elif datatype == 'boolean':
            default_expr = default_value.upper() if default_value else 'TRUE'
        elif datatype in ('date', 'datetime'):
            # Convert Tableau #YYYY-MM-DD# date literal to DAX DATE()
            date_m = re.match(r'#(\d{4})-(\d{2})-(\d{2})#', default_value)
            if date_m:
                default_expr = f'DATE({int(date_m.group(1))}, {int(date_m.group(2))}, {int(date_m.group(3))})'
            else:
                default_expr = default_value if default_value else 'DATE(2024, 1, 1)'
        else:
            default_expr = default_value if default_value else '0'

        if domain_type == 'database':
            # Dynamic parameter — database-query-driven (Tableau 2024.3+)
            # Generate M table using Value.NativeQuery() for database refresh
            query_sql = param.get('query', '')
            conn_class = param.get('query_connection', '')
            dbname = param.get('query_dbname', '')

            # Build M expression referencing native query
            if query_sql:
                escaped_sql = query_sql.replace('"', '""')
                m_source = f'Value.NativeQuery(#"Source", "{escaped_sql}", null, [EnableFolding=true])'
            else:
                # Fallback — no query available, produce DAX table
                m_source = None

            col_name = "Value"
            param_table = {
                "name": caption,
                "columns": [{
                    "name": col_name,
                    "dataType": pbi_type,
                    "sourceColumn": col_name,
                    "annotations": [
                        {"name": "displayFolder", "value": "Parameters"}
                    ]
                }],
                "measures": [{
                    "name": caption,
                    "expression": f"SELECTEDVALUE('{caption.replace(chr(39), chr(39)*2)}'[{col_name}], {default_expr})",
                    "annotations": [
                        {"name": "displayFolder", "value": "Parameters"},
                        {"name": "MigrationNote",
                         "value": f"Dynamic parameter from Tableau — source query: {query_sql[:200]}"}
                    ]
                }],
                "partitions": [{
                    "name": caption,
                    "mode": "import",
                    "source": {
                        "type": "m",
                        "expression": m_source or f'#table({{"{col_name}"}}, {{{{"{default_value}"}}}})'
                    }
                }],
                "annotations": [
                    {"name": "MigrationNote",
                     "value": "Tableau dynamic parameter — configure Power Query source connection"}
                ]
            }
            if param.get('refresh_on_open'):
                param_table['refreshPolicy'] = {
                    'type': 'automatic'
                }
            model["model"]["tables"].append(param_table)
            continue

        if domain_type == 'any' or not allowable_values:
            # Skip string-literal values only when the inner text contains
            # embedded quotes (which would break DAX/TMDL string syntax).
            # Simple quoted values like "CHAMPIONS" must still produce a
            # measure so that DAX formulas referencing [ParamCaption] work.
            _raw_val = param.get('value', '').strip()
            if (_raw_val.startswith('"') and _raw_val.endswith('"')
                    and len(_raw_val) > 2):
                _inner = _raw_val[1:-1]
                if '"' in _inner:
                    continue
            for table in model["model"]["tables"]:
                if table.get("name") == main_table_name:
                    if "measures" not in table:
                        table["measures"] = []
                    table["measures"].append({
                        "name": caption,
                        "expression": default_expr,
                        "annotations": [
                            {"name": "displayFolder", "value": "Parameters"}
                        ]
                    })
                    break
            continue

        table_expr = None
        col_name = caption
        has_aliases = False

        if domain_type == 'range':
            range_info = next((v for v in allowable_values if v.get('type') == 'range'), None)
            if range_info:
                min_val = range_info.get('min', '0')
                max_val = range_info.get('max', '100')
                step = range_info.get('step', '') or '1'
                table_expr = f"GENERATESERIES({min_val}, {max_val}, {step})"
                col_name = "Value"

        elif domain_type == 'list':
            list_values = [v for v in allowable_values if v.get('type') != 'range']
            if list_values:
                # Check if aliases exist and differ from values (display names)
                has_aliases = any(
                    v.get('alias') and str(v.get('alias')) != str(v.get('value', ''))
                    for v in list_values
                )
                if datatype == 'string':
                    rows = ', '.join(f'{{"{v.get("value", "")}"}}' for v in list_values)
                elif datatype == 'boolean':
                    rows = ', '.join(f'{{{v.get("value", "TRUE").upper()}}}' for v in list_values)
                elif has_aliases:
                    # Numeric list with aliases → include Name column
                    rows = ', '.join(
                        '{{{}, "{}"}}'.format(v.get("value", "0"), v.get("alias", v.get("value", "")).replace('"', '""'))
                        for v in list_values
                    )
                else:
                    rows = ', '.join(f'{{{v.get("value", "0")}}}' for v in list_values)
                col_name = "Value"
                if has_aliases and datatype not in ('string', 'boolean'):
                    table_expr = f'DATATABLE("Value", {dax_type}, "Name", STRING, {{{rows}}})'
                else:
                    table_expr = f'DATATABLE("Value", {dax_type}, {{{rows}}})'

        if not table_expr:
            continue

        # Escape apostrophes in caption for DAX table references
        dax_caption = caption.replace("'", "''")

        param_table = {
            "name": caption,
            "columns": [{
                "name": col_name,
                "dataType": pbi_type,
                "sourceColumn": col_name,
                "annotations": [
                    {"name": "displayFolder", "value": "Parameters"}
                ]
            }],
            "measures": [{
                "name": caption,
                "expression": f"SELECTEDVALUE('{dax_caption}'[{col_name}], {default_expr})",
                "annotations": [
                    {"name": "displayFolder", "value": "Parameters"}
                ]
            }],
            "partitions": [{
                "name": caption,
                "mode": "import",
                "source": {
                    "type": "calculated",
                    "expression": table_expr
                }
            }]
        }

        # Add Name column for numeric list parameters with aliases
        if has_aliases and domain_type == 'list':
            param_table["columns"].append({
                "name": "Name",
                "dataType": "string",
                "sourceColumn": "Name",
                "annotations": [
                    {"name": "displayFolder", "value": "Parameters"}
                ]
            })

        model["model"]["tables"].append(param_table)

    # Deduplicate: remove parameter measures from other tables
    param_table_names = set()
    for param in parameters:
        caption = param.get('caption', '')
        domain_type = param.get('domain_type', 'any')
        if caption and domain_type in ('range', 'list') and param.get('allowable_values'):
            param_table_names.add(caption)

    if param_table_names:
        for table in model["model"]["tables"]:
            table_name = table.get("name", "")
            if table_name in param_table_names:
                continue
            if "measures" in table:
                table["measures"] = [
                    m for m in table["measures"]
                    if m.get("name", "") not in param_table_names
                ]


def _create_calculation_groups(model, parameters, main_table_name):
    """Create calculation group tables from parameters that switch between measures.

    Two detection paths:
    1. **String list parameters** whose allowable values match existing measure
       names → each measure becomes a ``CALCULATE(SELECTEDMEASURE())`` item.
    2. **Numeric list parameters with aliases** where a SWITCH measure maps
       numeric values to aggregation expressions → each alias becomes a
       calculation item with the branch expression.  The SWITCH measure and
       What-If table are kept alongside for backward compatibility.
    """
    if not parameters:
        return

    existing_tables = {t.get('name', '') for t in model['model']['tables']}

    # Collect all measure names across the model
    measure_names = set()
    for table in model['model']['tables']:
        for m in table.get('measures', []):
            measure_names.add(m.get('name', ''))

    for param in parameters:
        caption = param.get('caption', '')
        domain_type = param.get('domain_type', '')
        datatype = param.get('datatype', 'string')
        allowable_values = param.get('allowable_values', [])

        if domain_type != 'list' or not allowable_values:
            continue

        # ── Path 1: String list parameters matching measure names ──
        if datatype == 'string':
            matching_values = [
                v for v in allowable_values
                if v.get('type') != 'range' and v.get('value', '') in measure_names
            ]
            if len(matching_values) < 2:
                continue

            cg_name = f"{caption} CalcGroup"
            if cg_name in existing_tables:
                continue

            calc_items = []
            for idx, val in enumerate(matching_values):
                measure_ref = val.get('value', '')
                calc_items.append({
                    "name": measure_ref,
                    "expression": "CALCULATE(SELECTEDMEASURE())",
                    "ordinal": idx,
                })

            cg_table = {
                "name": cg_name,
                "calculationGroup": {
                    "columns": [{"name": caption, "dataType": "string",
                                 "sourceColumn": "Name"}],
                    "calculationItems": calc_items,
                },
                "columns": [{"name": caption, "dataType": "string",
                             "sourceColumn": "Name"}],
                "partitions": [{
                    "name": cg_name,
                    "mode": "import",
                    "source": {"type": "calculationGroup"},
                }],
                "annotations": [
                    {"name": "displayFolder", "value": "Calculation Groups"},
                ],
            }
            model['model']['tables'].append(cg_table)
            existing_tables.add(cg_name)
            continue

        # ── Path 2: Numeric list parameters with aliases → SWITCH measure ──
        if datatype not in ('real', 'integer'):
            continue

        list_values = [v for v in allowable_values if v.get('type') != 'range']
        if len(list_values) < 2:
            continue
        # All values must have aliases for meaningful item names
        if not all(v.get('alias') for v in list_values):
            continue

        # Build value→alias map (normalise "1.0" → "1")
        val_alias = {}
        for v in list_values:
            raw = v.get('value', '')
            try:
                num = float(raw)
                normalised = str(int(num)) if num == int(num) else str(num)
            except (ValueError, OverflowError):
                normalised = raw
            val_alias[normalised] = v.get('alias', '')

        # Find SWITCH measures that reference this parameter
        switch_pat = re.compile(
            r'^SWITCH\s*\(\s*\[' + re.escape(caption) + r'\]\s*,(.+)\)$',
            re.IGNORECASE | re.DOTALL,
        )

        found_branches = None
        for table in model['model']['tables']:
            for m in table.get('measures', []):
                expr = m.get('expression', '').strip()
                sm = switch_pat.match(expr)
                if not sm:
                    continue
                branches = _parse_switch_branches(sm.group(1).strip())
                if branches and all(bk in val_alias for bk, _ in branches):
                    found_branches = branches
                    break
            if found_branches:
                break

        if not found_branches:
            continue

        cg_name = f"{caption} CalcGroup"
        if cg_name in existing_tables:
            continue

        calc_items = []
        for idx, (bval, bexpr) in enumerate(found_branches):
            item_name = val_alias.get(bval, bval)
            calc_items.append({
                "name": item_name,
                "expression": f"CALCULATE({bexpr})",
                "ordinal": idx,
            })

        cg_table = {
            "name": cg_name,
            "calculationGroup": {
                "columns": [{"name": caption, "dataType": "string",
                             "sourceColumn": "Name"}],
                "calculationItems": calc_items,
            },
            "columns": [{"name": caption, "dataType": "string",
                         "sourceColumn": "Name"}],
            "partitions": [{
                "name": cg_name,
                "mode": "import",
                "source": {"type": "calculationGroup"},
            }],
            "annotations": [
                {"name": "displayFolder", "value": "Calculation Groups"},
            ],
        }
        model['model']['tables'].append(cg_table)
        existing_tables.add(cg_name)


def _parse_switch_branches(args_str):
    """Parse the arguments of a SWITCH() after the switch expression.

    Returns a list of ``(value, expression)`` tuples, or *None* if parsing fails.
    The trailing default value (odd argument) is ignored.
    """
    parts = []
    depth = 0
    current = []
    for ch in args_str:
        if ch in '(':
            depth += 1
            current.append(ch)
        elif ch in ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current).strip())

    branches = []
    i = 0
    while i + 1 < len(parts):
        val = parts[i].strip()
        expr = parts[i + 1].strip()
        try:
            num = float(val)
            val = str(int(num)) if num == int(num) else str(num)
        except (ValueError, OverflowError):
            pass
        branches.append((val, expr))
        i += 2
    return branches if branches else None


def _create_field_parameters(model, parameters, main_table_name, column_table_map):
    """Create field parameter tables from parameters that switch between columns.

    Field parameters in Power BI allow users to dynamically choose which column
    appears on a visual axis or slicer. This converts Tableau parameters whose
    allowable values match existing column names into PBI field parameter tables
    with ``NAMEOF()`` references.
    """
    if not parameters:
        return

    existing_tables = {t.get('name', '') for t in model['model']['tables']}

    # Collect all known column names and measure names
    all_columns = set()
    measure_names = set()
    for table in model['model']['tables']:
        for col in table.get('columns', []):
            all_columns.add(col.get('name', ''))
        for m in table.get('measures', []):
            measure_names.add(m.get('name', ''))

    for param in parameters:
        caption = param.get('caption', '')
        domain_type = param.get('domain_type', '')
        datatype = param.get('datatype', 'string')
        allowable_values = param.get('allowable_values', [])

        # Only string list parameters with column-like values
        if datatype != 'string' or domain_type != 'list' or not allowable_values:
            continue

        matching_cols = [
            v for v in allowable_values
            if v.get('type') != 'range' and v.get('value', '') in all_columns
        ]

        if len(matching_cols) < 2:
            continue
        # Skip if all values are measures (those become calc groups instead)
        if all(v.get('value', '') in measure_names for v in matching_cols):
            continue

        fp_name = f"{caption} FieldParam"
        if fp_name in existing_tables:
            continue

        # Build NAMEOF references for the field parameter DAX expression
        rows = []
        for idx, val in enumerate(matching_cols):
            col_name = val.get('value', '')
            col_table = column_table_map.get(col_name, main_table_name)
            rows.append(
                f"(NAMEOF('{col_table}'[{col_name}]), {idx}, \"{col_name}\")"
            )

        fp_expr = "{\\n" + ",\\n".join(rows) + "\\n}"

        fp_table = {
            "name": fp_name,
            "columns": [
                {"name": caption, "dataType": "string",
                 "sourceColumn": caption,
                 "annotations": [{"name": "displayFolder",
                                  "value": "Field Parameters"}]},
                {"name": f"{caption}_Order", "dataType": "int64",
                 "sourceColumn": f"{caption}_Order", "isHidden": True},
                {"name": f"{caption}_Fields", "dataType": "string",
                 "sourceColumn": f"{caption}_Fields", "isHidden": True},
            ],
            "partitions": [{
                "name": fp_name,
                "mode": "import",
                "source": {
                    "type": "calculated",
                    "expression": fp_expr,
                },
            }],
            "annotations": [
                {"name": "displayFolder", "value": "Field Parameters"},
                {"name": "PBI_NavigationStepName", "value": "Navigation"},
                {"name": "ParameterMetadata",
                 "value": json.dumps({"version": 3, "kind": 2})},
            ],
        }
        model['model']['tables'].append(fp_table)
        existing_tables.add(fp_name)


def _create_rls_roles(model, user_filters, main_table_name, column_table_map):
    """Create Row-Level Security (RLS) roles from Tableau user filters.

    Converts Tableau security patterns to Power BI RLS roles:
    - User filter (explicit user->row mappings) -> RLS role with USERPRINCIPALNAME()
    - Calculated security (USERNAME/FULLNAME formulas) -> RLS role with DAX filter
    - ISMEMBEROF group patterns -> separate RLS role per group
    """
    if not user_filters:
        return

    if not main_table_name:
        tables = model.get('model', {}).get('tables', [])
        if tables:
            main_table_name = tables[0].get('name', 'Table')
        else:
            main_table_name = 'Table'

    roles = []
    role_names = set()

    for uf in user_filters:
        uf_type = uf.get('type', '')

        if uf_type == 'user_filter':
            filter_name = uf.get('name', 'UserFilter')
            column = uf.get('column', '')
            user_mappings = uf.get('user_mappings', [])

            table_name = column_table_map.get(column, main_table_name)

            col_clean = column
            if ':' in col_clean:
                col_clean = col_clean.split(':')[-1]

            if user_mappings:
                user_values = {}
                for mapping in user_mappings:
                    user = mapping.get('user', '')
                    val = mapping.get('value', '')
                    if user and val:
                        user_values.setdefault(user, []).append(val)

                or_clauses = []
                for user_email, values in user_values.items():
                    if len(values) == 1:
                        val_expr = f'[{col_clean}] = "{values[0]}"'
                    else:
                        val_list = ', '.join(f'"{v}"' for v in values)
                        val_expr = f'[{col_clean}] IN {{{val_list}}}'
                    or_clauses.append(
                        f'(USERPRINCIPALNAME() = "{user_email}" && {val_expr})'
                    )

                if or_clauses:
                    filter_dax = ' || '.join(or_clauses)
                else:
                    filter_dax = 'FALSE()'

                role_name = _unique_role_name(filter_name, role_names)
                role_names.add(role_name)

                roles.append({
                    "name": role_name,
                    "modelPermission": "read",
                    "tablePermissions": [
                        {
                            "name": table_name,
                            "filterExpression": filter_dax
                        }
                    ],
                    "_migration_note": (
                        f"Migrated from Tableau user filter '{filter_name}'. "
                        f"Each user is mapped to their allowed {col_clean} values inline. "
                        f"Consider creating a security table for dynamic RLS."
                    ),
                    "_user_mappings": user_mappings
                })

            elif column:
                filter_dax = f"[{col_clean}] = USERPRINCIPALNAME()"
                role_name = _unique_role_name(filter_name, role_names)
                role_names.add(role_name)

                roles.append({
                    "name": role_name,
                    "modelPermission": "read",
                    "tablePermissions": [
                        {
                            "name": table_name,
                            "filterExpression": filter_dax
                        }
                    ]
                })

        elif uf_type == 'calculated_security':
            calc_name = uf.get('name', 'SecurityCalc')
            formula = uf.get('formula', '')
            functions_used = uf.get('functions_used', [])
            ismemberof_groups = uf.get('ismemberof_groups', [])

            if ismemberof_groups:
                for group in ismemberof_groups:
                    role_name = _unique_role_name(group, role_names)
                    role_names.add(role_name)

                    filter_dax = f"TRUE()  /* Members of role '{group}' have access */"

                    roles.append({
                        "name": role_name,
                        "modelPermission": "read",
                        "tablePermissions": [
                            {
                                "name": main_table_name,
                                "filterExpression": filter_dax
                            }
                        ],
                        "_migration_note": (
                            f"Migrated from Tableau ISMEMBEROF(\"{group}\"). "
                            f"Assign Azure AD group members to this RLS role."
                        )
                    })

            elif 'USERNAME' in functions_used or 'FULLNAME' in functions_used:
                dax_filter = convert_tableau_formula_to_dax(
                    formula,
                    table_name=main_table_name,
                    column_table_map=column_table_map
                )

                role_name = _unique_role_name(calc_name, role_names)
                role_names.add(role_name)

                # Determine which table the filter applies to
                cross_ref = re.search(r"'([^']+)'\[", dax_filter)
                perm_table = main_table_name
                if cross_ref:
                    ref_table = cross_ref.group(1)
                    model_table_names = {t.get("name", "") for t in model["model"]["tables"]}
                    if ref_table in model_table_names and ref_table != main_table_name:
                        perm_table = ref_table
                        dax_filter = dax_filter.replace(f"'{ref_table}'[", "[")

                roles.append({
                    "name": role_name,
                    "modelPermission": "read",
                    "tablePermissions": [
                        {
                            "name": perm_table,
                            "filterExpression": dax_filter
                        }
                    ],
                    "_migration_note": (
                        f"Migrated from Tableau calculated security '{calc_name}'. "
                        f"Original formula: {formula}"
                    )
                })

    if roles:
        model["model"]["roles"] = roles
        print(f"    \u2713 {len(roles)} RLS role(s) created")


def _unique_role_name(base_name, existing_names):
    """Generate a unique role name, appending _N if needed."""
    clean = re.sub(r'[^\w\s-]', '', base_name).strip()
    if not clean:
        clean = 'Role'

    if clean not in existing_names:
        return clean

    counter = 2
    while f"{clean}_{counter}" in existing_names:
        counter += 1
    return f"{clean}_{counter}"


def _get_format_string(datatype):
    """Return the Power BI format string for a given type."""
    format_map = {
        'integer': '0',
        'real': '#,0.00',
        'currency': '$#,0.00',
        'percentage': '0.00%',
        'date': 'Short Date',
        'datetime': 'General Date',
        'boolean': 'True/False'
    }
    return format_map.get(datatype.lower(), '0')


def _convert_tableau_format_to_pbi(tableau_format):
    """Convert a Tableau number format string to Power BI format string.

    Tableau formats:  #,##0.00  |  0.0%  |  $#,##0  |  0.000  |  #,##0
    PBI formats:      #,0.00   |  0.0%  |  $#,0    |  0.000  |  #,0

    Args:
        tableau_format: Tableau format string (from default-format attribute)

    Returns:
        str: Power BI format string, or empty string if no conversion needed
    """
    if not tableau_format:
        return ''

    fmt = tableau_format.strip()

    # Already a PBI-compatible format
    if fmt in ('0', '#,0', '#,0.00', '0.00%', '$#,0.00', 'General Date', 'Short Date'):
        return fmt

    # Percentage formats
    if '%' in fmt:
        # Normalize: Tableau uses 0.0% or 0.00% etc.
        return fmt

    # Currency with symbol
    for symbol in ('$', '€', '£', '¥'):
        if symbol in fmt:
            # Convert Tableau ##0 pattern to PBI #,0 pattern
            cleaned = fmt.replace('##0', '#0').replace('###', '#').replace(',,', ',')
            # Ensure at least one digit placeholder
            if '0' not in cleaned:
                cleaned = cleaned + '0'
            return cleaned

    # Numeric formats
    # Tableau uses #,##0.00 → PBI uses #,0.00
    result = fmt
    # Convert Tableau's #,##0 → #,0 pattern
    result = result.replace('#,##0', '#,0')
    result = result.replace('#,###', '#,#')
    # Handle plain 0 patterns
    if result and result[0] == '0':
        return result  # Already numeric

    return result if result != fmt else fmt


def _deactivate_ambiguous_paths(model):
    """
    Detect and deactivate relationships that create ambiguous paths.

    Power BI requires that the graph of active relationships forms a forest
    (tree per connected component) — i.e., no cycles when treated as undirected.
    If a cycle is detected, the least-important relationship is deactivated.

    Priority for deactivation (first deactivated):
      1. Auto-generated Calendar relationships (name starts with 'Calendar_')
      2. Inferred cross-table relationships (name starts with 'inferred_')
      3. Original Tableau-extracted relationships (last resort)
    """
    relationships = model["model"]["relationships"]
    if not relationships:
        return

    # --- Union-Find -------------------------------------------------------
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])  # path compression
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return False          # cycle detected
        parent[ra] = rb
        return True

    # --- Sort relationships so the most important are added first ----------
    def _deactivation_priority(rel):
        """Lower value = more important = added to tree first."""
        name = rel.get('name', '')
        if name.startswith('Calendar_'):
            return 2   # auto-generated → deactivate first
        if name.startswith('inferred_'):
            return 1   # inferred → deactivate second
        return 0       # original Tableau relationships → keep

    sorted_rels = sorted(relationships, key=_deactivation_priority)

    deactivated = []
    for rel in sorted_rels:
        if rel.get('isActive') == False:
            continue  # already inactive, skip
        from_t = rel.get('fromTable', '')
        to_t = rel.get('toTable', '')
        if not from_t or not to_t:
            continue
        if not union(from_t, to_t):
            # This edge creates a cycle → deactivate it
            rel['isActive'] = False
            deactivated.append(f"{from_t}.{rel.get('fromColumn','')} → "
                               f"{to_t}.{rel.get('toColumn','')}")

    for d in deactivated:
        print(f"  ⚠ Deactivated relationship (ambiguous path): {d}")


def _create_number_of_records_measure(model, worksheets, main_table_name):
    """Auto-generate a 'Number of Records' COUNTROWS measure.

    Tableau worksheets that use COUNT(*) on ``__tableau_internal_object_id__``
    are extracted with a synthetic field ``Number of Records`` (aggregation=cnt).
    This function creates the corresponding DAX measure on the main table.
    """
    if not worksheets or not main_table_name:
        return

    # Check if any worksheet field uses "Number of Records"
    needs_measure = False
    for ws in worksheets:
        for f in ws.get('fields', []):
            if f.get('name') == 'Number of Records':
                needs_measure = True
                break
        if needs_measure:
            break

    if not needs_measure:
        return

    # Find the main table and add the measure (if not already present)
    for table in model['model']['tables']:
        if table.get('name') == main_table_name:
            existing = {m.get('name') for m in table.get('measures', [])}
            if 'Number of Records' not in existing:
                table.setdefault('measures', []).append({
                    'name': 'Number of Records',
                    'expression': "COUNTROWS('" + main_table_name.replace("'", "''") + "')",
                    'displayFolder': 'Measures',
                    'annotations': [
                        {'name': 'MigrationNote',
                         'value': 'Auto-generated from Tableau COUNT(*) on internal object ID.'}
                    ]
                })
            break


def _create_quick_table_calc_measures(model, worksheets, main_table_name, column_table_map):
    """Auto-generate DAX measures for Tableau quick table calculations.
    
    Detects fields with table_calc metadata (pcto, pctd, running_sum, rank, etc.)
    and creates corresponding DAX measures:
    - pcto (% of Total): DIVIDE(SUM([Field]), CALCULATE(SUM([Field]), ALL('Table')))
    - pctd (% Difference): DIVIDE(SUM([Field]) - CALCULATE(SUM([Field]), PREVIOUSDAY(...)), ...)
    - running_sum: CALCULATE(SUM([Field]), FILTER(ALL('Calendar'[Date]), ...))
    - running_avg, running_count, running_min, running_max: similar pattern
    - rank / rank_unique / rank_dense: RANKX(ALL('Table'), SUM([Field]))
    """
    if not worksheets:
        return
    
    # Find the main table to add measures to
    target_table = None
    for t in model["model"]["tables"]:
        if t.get("name") == main_table_name:
            target_table = t
            break
    if not target_table:
        return
    
    existing_measures = {m.get("name", "") for m in target_table.get("measures", [])}
    added = 0
    
    _AGG_MAP = {
        'sum': 'SUM', 'avg': 'AVERAGE', 'count': 'COUNT',
        'min': 'MIN', 'max': 'MAX', 'countd': 'DISTINCTCOUNT',
    }
    
    for ws in worksheets:
        for field in ws.get('fields', []):
            tc_type = field.get('table_calc')
            if not tc_type:
                continue
            
            field_name = field.get('name', '')
            tc_agg = field.get('table_calc_agg', 'sum')
            agg_func = _AGG_MAP.get(tc_agg, 'SUM')
            tbl = column_table_map.get(field_name, main_table_name)
            
            if tc_type == 'pcto':
                measure_name = f"% of Total {field_name}"
                if measure_name not in existing_measures:
                    expr = f"DIVIDE({agg_func}('{tbl}'[{field_name}]), CALCULATE({agg_func}('{tbl}'[{field_name}]), ALL('{tbl}')))"
                    target_table.setdefault("measures", []).append({
                        "name": measure_name,
                        "expression": expr,
                        "formatString": "0.00%",
                        "displayFolder": "Table Calculations"
                    })
                    existing_measures.add(measure_name)
                    added += 1
            
            elif tc_type == 'pctd':
                measure_name = f"% Difference {field_name}"
                if measure_name not in existing_measures:
                    base = f"{agg_func}('{tbl}'[{field_name}])"
                    prev = f"CALCULATE({base}, PREVIOUSDAY('Calendar'[Date]))"
                    expr = f"VAR _Current = {base} VAR _Previous = {prev} RETURN DIVIDE(_Current - _Previous, _Previous)"
                    target_table.setdefault("measures", []).append({
                        "name": measure_name,
                        "expression": expr,
                        "formatString": "0.00%",
                        "displayFolder": "Table Calculations"
                    })
                    existing_measures.add(measure_name)
                    added += 1
            
            elif tc_type.startswith('running_'):
                running_agg = tc_type.replace('running_', '')
                running_func = _AGG_MAP.get(running_agg, 'SUM')
                measure_name = f"Running {running_agg.title()} {field_name}"
                if measure_name not in existing_measures:
                    expr = (f"CALCULATE({running_func}('{tbl}'[{field_name}]), "
                            f"FILTER(ALL('Calendar'[Date]), 'Calendar'[Date] <= MAX('Calendar'[Date])))")
                    target_table.setdefault("measures", []).append({
                        "name": measure_name,
                        "expression": expr,
                        "formatString": "#,0.00",
                        "displayFolder": "Table Calculations"
                    })
                    existing_measures.add(measure_name)
                    added += 1
            
            elif tc_type in ('rank', 'rank_unique', 'rank_dense'):
                dense = ", DENSE" if tc_type == 'rank_dense' else ""
                measure_name = f"Rank {field_name}"
                if measure_name not in existing_measures:
                    expr = f"RANKX(ALL('{tbl}'), {agg_func}('{tbl}'[{field_name}]){dense})"
                    target_table.setdefault("measures", []).append({
                        "name": measure_name,
                        "expression": expr,
                        "formatString": "#,0",
                        "displayFolder": "Table Calculations"
                    })
                    existing_measures.add(measure_name)
                    added += 1
            
            elif tc_type == 'diff':
                measure_name = f"Difference {field_name}"
                if measure_name not in existing_measures:
                    base = f"{agg_func}('{tbl}'[{field_name}])"
                    prev = f"CALCULATE({base}, PREVIOUSDAY('Calendar'[Date]))"
                    expr = f"{base} - {prev}"
                    target_table.setdefault("measures", []).append({
                        "name": measure_name,
                        "expression": expr,
                        "formatString": "#,0.00",
                        "displayFolder": "Table Calculations"
                    })
                    existing_measures.add(measure_name)
                    added += 1
    
    if added:
        print(f"  ✓ {added} quick table calc measures generated")


# Well-known date table names (any language)
_DATE_TABLE_NAMES = {
    # English
    'calendar', 'date', 'dimdate', 'dim_date', 'datedimension',
    'date_dimension', 'dim date', 'datetable', 'date_table',
    'time', 'dimtime', 'dim_time', 'dates',
    # French
    'calendrier', 'dimcalendrier', 'dim_calendrier',
    'tabledate', 'table_date', 'temps',
    # German
    'datum', 'kalender', 'dimdatum', 'dim_datum', 'dimkalender',
    'dim_kalender', 'zeit',
    # Spanish
    'fecha', 'calendario', 'dimfecha', 'dim_fecha', 'dimcalendario',
    'dim_calendario',
    # Portuguese
    'data', 'dimdata', 'dim_data',
    # Italian
    'datacalendario',
    # Dutch (datum/kalender already covered above)
    # Romanized
    'datemaster', 'date_master', 'masterdate', 'master_date',
}

# Column-name patterns that are typical date-part columns (any language)
_DATE_PART_PATTERNS = re.compile(
    r'^('
    # Year
    r'year|ann[eé]e|annee|jahr|a[nñ]o|ano|anno|jaar'
    r'|'
    # Month
    r'month|mois|monat|mes|mese|maand|monthname|month.?name|month.?num'
    r'|'
    # Day
    r'day|jour|tag|d[ií]a|dia|giorno|dag|dayname|day.?name|dayofweek|day.?of.?week'
    r'|'
    # Quarter
    r'quarter|trimestre|quartal|kwartaal|quarter.?name|quarter.?num'
    r'|'
    # Week
    r'week|semaine|woche|semana|settimana|weeknum|week.?num|weekday|week.?of.?year'
    r'|'
    # Date (the key column itself)
    r'date|datum|fecha|data|datekey|date.?key|fulldate|full.?date'
    r'|'
    # Calendar-specific
    r'calendar|calendrier|kalender|calendario|fiscal.?year|fiscal.?month|fiscal.?quarter'
    r')$', re.IGNORECASE
)


def _is_date_table(table):
    """Detect whether a table is a date/calendar dimension table.

    Uses two strategies:
    1. Name-based: table name matches a known date table name (any language).
    2. Column-heuristic: table has a DateTime column AND ≥50% of its columns
       have names that match common date-part patterns (Year, Month, Day, etc.).
    """
    name = table.get('name', '').lower().strip()

    # Strategy 1: well-known name
    if name in _DATE_TABLE_NAMES:
        return True

    # Strategy 2: column heuristic
    columns = table.get('columns', [])
    if not columns:
        return False

    has_datetime_col = any(
        c.get('dataType') == 'DateTime' or c.get('dataCategory') == 'DateTime'
        for c in columns
    )
    if not has_datetime_col:
        return False

    date_part_count = sum(
        1 for c in columns
        if _DATE_PART_PATTERNS.match(c.get('name', '').strip())
    )

    # If ≥50% of columns look like date parts, it's a date table
    return date_part_count >= len(columns) * 0.5


def _add_date_table(model):
    """
    Add an automatic date table using Power Query M.

    Uses an M partition (not DAX calculated) to avoid "invalid column ID"
    errors when TMDL relationships reference columns inside
    calculated-table partitions.

    Links Calendar to ALL fact tables that have date columns
    (not just the first one).

    Supports customizable date range via model['_calendar_start'] and
    model['_calendar_end'] (default: 2020–2030).

    Skipped if the model already contains a table named 'Calendar'.
    """
    # Guard: don't add if Calendar already exists (e.g. from source data)
    existing_names = {t.get('name', '') for t in model['model']['tables']}
    if 'Calendar' in existing_names:
        return
    cal_start = model.get('_calendar_start') or 2020
    cal_end = model.get('_calendar_end') or 2030
    cal_culture = model.get('model', {}).get('culture', 'en-US')

    calendar_m = (
        'let\n'
        f'    StartDate = #date({cal_start}, 1, 1),\n'
        f'    EndDate = #date({cal_end}, 12, 31),\n'
        '    DayCount = Duration.Days(EndDate - StartDate) + 1,\n'
        '    DateList = List.Dates(StartDate, DayCount, #duration(1, 0, 0, 0)),\n'
        '    #"Date Table" = Table.FromList(DateList, Splitter.SplitByNothing(), {"Date"}, null, ExtraValues.Error),\n'
        '    #"Changed Type" = Table.TransformColumnTypes(#"Date Table", {{"Date", type date}}),\n'
        '    #"Added Year" = Table.AddColumn(#"Changed Type", "Year", each Date.Year([Date]), Int64.Type),\n'
        '    #"Added Quarter" = Table.AddColumn(#"Added Year", "Quarter", each "Q" & Text.From(Date.QuarterOfYear([Date]))),\n'
        '    #"Added Month" = Table.AddColumn(#"Added Quarter", "Month", each Date.Month([Date]), Int64.Type),\n'
        f'    #"Added MonthName" = Table.AddColumn(#"Added Month", "MonthName", each Date.MonthName([Date], "{cal_culture}")),\n'
        '    #"Added Day" = Table.AddColumn(#"Added MonthName", "Day", each Date.Day([Date]), Int64.Type),\n'
        '    #"Added DayOfWeek" = Table.AddColumn(#"Added Day", "DayOfWeek", each Date.DayOfWeek([Date], Day.Monday) + 1, Int64.Type),\n'
        f'    #"Added DayName" = Table.AddColumn(#"Added DayOfWeek", "DayName", each Date.DayOfWeekName([Date], "{cal_culture}"))\n'
        'in\n'
        '    #"Added DayName"'
    )

    date_table = {
        "name": "Calendar",
        "isHidden": False,
        "columns": [
            {
                "name": "Date",
                "dataType": "DateTime",
                "isKey": True,
                "dataCategory": "DateTime",
                "formatString": "dd/mm/yyyy",
                "sourceColumn": "Date",
                "summarizeBy": "none"
            },
            {
                "name": "Year",
                "dataType": "int64",
                "dataCategory": "Years",
                "sourceColumn": "Year",
                "summarizeBy": "none"
            },
            {
                "name": "Quarter",
                "dataType": "string",
                "sourceColumn": "Quarter",
                "summarizeBy": "none"
            },
            {
                "name": "Month",
                "dataType": "int64",
                "dataCategory": "Months",
                "sourceColumn": "Month",
                "summarizeBy": "none"
            },
            {
                "name": "MonthName",
                "dataType": "string",
                "sourceColumn": "MonthName",
                "sortByColumn": "Month",
                "summarizeBy": "none"
            },
            {
                "name": "Day",
                "dataType": "int64",
                "dataCategory": "Days",
                "sourceColumn": "Day",
                "summarizeBy": "none"
            },
            {
                "name": "DayOfWeek",
                "dataType": "int64",
                "sourceColumn": "DayOfWeek",
                "summarizeBy": "none"
            },
            {
                "name": "DayName",
                "dataType": "string",
                "sourceColumn": "DayName",
                "sortByColumn": "DayOfWeek",
                "summarizeBy": "none"
            }
        ],
        "partitions": [
            {
                "name": "Calendar-Partition",
                "mode": "import",
                "source": {
                    "type": "m",
                    "expression": calendar_m
                }
            }
        ],
        "measures": []
    }

    value_expr = None
    # Find a SUM-based measure in any table for time intelligence
    for t in model["model"]["tables"]:
        if t["name"] == "Calendar":
            continue
        for ms in t.get("measures", []):
            expr = ms.get("expression", "")
            if re.match(r'^SUM\b', expr, re.IGNORECASE):
                value_expr = f'[{ms["name"]}]'
                break
        if value_expr:
            break

    time_intelligence_measures = []
    if value_expr:
        time_intelligence_measures = [
            {
                "name": "Year To Date",
                "expression": f"TOTALYTD({value_expr}, 'Calendar'[Date])",
                "formatString": "#,0.00",
                "displayFolder": "Time Intelligence"
            },
            {
                "name": "Previous Year",
                "expression": f"CALCULATE({value_expr}, SAMEPERIODLASTYEAR('Calendar'[Date]))",
                "formatString": "#,0.00",
                "displayFolder": "Time Intelligence"
            },
            {
                "name": "Year Over Year %",
                "expression": "DIVIDE([Year To Date] - [Previous Year], [Previous Year], 0)",
                "formatString": "0.00%",
                "displayFolder": "Time Intelligence"
            }
        ]

    date_table["measures"].extend(time_intelligence_measures)

    # Add Date hierarchy (Year → Quarter → Month → Day)
    date_table["hierarchies"] = [
        {
            "name": "Date Hierarchy",
            "levels": [
                {"name": "Year", "column": "Year", "ordinal": 0},
                {"name": "Quarter", "column": "Quarter", "ordinal": 1},
                {"name": "Month", "column": "MonthName", "ordinal": 2},
                {"name": "Day", "column": "Day", "ordinal": 3},
            ]
        }
    ]

    model["model"]["tables"].append(date_table)

    # Add relationships: Calendar[Date] -> each table's first date column
    for t in model["model"]["tables"]:
        tname = t.get("name", "")
        if tname == "Calendar":
            continue
        for col in t.get("columns", []):
            if col.get("dataType") == "DateTime" or col.get("dataCategory") == "DateTime":
                date_col_name = col.get("name", "")
                if date_col_name and not col.get("isCalculated", False):
                    model["model"]["relationships"].append({
                        "name": f"Calendar_{tname}_{date_col_name}",
                        "fromTable": tname,
                        "fromColumn": date_col_name,
                        "toTable": "Calendar",
                        "toColumn": "Date",
                        "crossFilteringBehavior": "oneDirection"
                    })
                    break  # one date column per table is enough


# ════════════════════════════════════════════════════════════════════
#  TMDL FILE WRITERS
# ════════════════════════════════════════════════════════════════════

def _quote_name(name):
    """Quote a TMDL name if needed (spaces, special characters).
    Internal apostrophes are escaped by doubling them ('')."""
    if re.search(r'[^a-zA-Z0-9_]', name):
        escaped = name.replace("'", "''")
        return f"'{escaped}'"
    return name


def _tmdl_datatype(bim_type):
    """Convert a type to TMDL type."""
    mapping = {
        'int64': 'int64', 'string': 'string', 'double': 'double',
        'decimal': 'decimal', 'boolean': 'boolean', 'datetime': 'dateTime',
        'binary': 'binary',
    }
    return mapping.get(bim_type.lower() if bim_type else '', 'string')


def _tmdl_summarize(summarize_by):
    """Convert summarizeBy to TMDL."""
    mapping = {
        'sum': 'sum',
        'none': 'none',
        'count': 'count',
        'average': 'average',
        'min': 'min',
        'max': 'max',
    }
    return mapping.get(str(summarize_by).lower(), 'none')


def _safe_filename(name):
    """Create a safe filename for a table."""
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    return safe


# ════════════════════════════════════════════════════════════════════
#  THEME GENERATION
# ════════════════════════════════════════════════════════════════════

# Default Power BI color palette (used when Tableau has no theme)
_DEFAULT_PBI_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2",
    "#59A14F", "#EDC948", "#B07AA1", "#FF9DA7",
    "#9C755F", "#BAB0AC", "#86BCB6", "#8CD17D"
]


def generate_theme_json(theme_data=None):
    """
    Generate a Power BI theme.json from extracted Tableau dashboard theme data.

    Sprint 79: Enhanced with background color, border style, and font mapping.

    Args:
        theme_data: dict with 'colors' (list of hex), 'font_family', 'styles',
                    'background_color', 'border_color', 'border_width'
                    from extract_theme() in extract_tableau_data.py

    Returns:
        dict: Power BI theme definition
    """
    colors = _DEFAULT_PBI_COLORS
    font_family = "Segoe UI"
    background = "#FFFFFF"
    foreground = "#252423"

    # Tableau → web-safe font mapping
    font_map = {
        'Tableau Book': 'Segoe UI',
        'Tableau Light': 'Segoe UI Light',
        'Tableau Medium': 'Segoe UI Semibold',
        'Tableau Bold': 'Segoe UI Bold',
        'Tableau Semibold': 'Segoe UI Semibold',
        'Benton Sans': 'Segoe UI',
        'Benton Sans Book': 'Segoe UI',
    }

    if theme_data:
        t_colors = theme_data.get('colors', [])
        if t_colors:
            # Filter valid hex colors
            valid = [c for c in t_colors if isinstance(c, str) and c.startswith('#')]
            if valid:
                colors = valid[:12]
                # Pad to 12 if fewer
                while len(colors) < 12:
                    colors.append(_DEFAULT_PBI_COLORS[len(colors) % len(_DEFAULT_PBI_COLORS)])
        t_font = theme_data.get('font_family', '')
        if t_font:
            font_family = font_map.get(t_font, t_font)
        # Sprint 79: Background and foreground from styles
        bg = theme_data.get('background_color', '')
        if bg and isinstance(bg, str) and bg.startswith('#'):
            background = bg
        fg = theme_data.get('foreground_color', '')
        if fg and isinstance(fg, str) and fg.startswith('#'):
            foreground = fg

    theme = {
        "name": "Tableau Migration Theme",
        "dataColors": colors,
        "background": background,
        "foreground": foreground,
        "tableAccent": colors[0] if colors else "#4E79A7",
        "textClasses": {
            "callout": {
                "fontSize": 28,
                "fontFace": font_family,
                "color": foreground
            },
            "title": {
                "fontSize": 12,
                "fontFace": font_family,
                "color": foreground
            },
            "header": {
                "fontSize": 12,
                "fontFace": font_family,
                "color": foreground
            },
            "label": {
                "fontSize": 10,
                "fontFace": font_family,
                "color": "#666666"
            }
        },
        "visualStyles": {
            "*": {
                "*": {
                    "*": [{
                        "fontFamily": font_family,
                        "wordWrap": True
                    }]
                }
            }
        }
    }

    # Sprint 79: Border styling
    if theme_data:
        border_color = theme_data.get('border_color', '')
        border_width = theme_data.get('border_width', 0)
        if border_color and isinstance(border_color, str) and border_color.startswith('#'):
            theme["visualStyles"]["*"]["*"]["border"] = [{
                "show": True,
                "color": border_color,
                "width": border_width if border_width else 1,
            }]

    return theme


def _write_tmdl_files(model_data, output_dir):
    """
    Write the complete TMDL file structure from a semantic model.

    Args:
        model_data: dict -- the full model (with 'model' key)
        output_dir: str -- path to the SemanticModel folder

    Returns:
        str -- path to the created definition/ folder
    """
    model = model_data.get('model', model_data)

    def_dir = os.path.join(output_dir, 'definition')
    os.makedirs(def_dir, exist_ok=True)

    tables = model.get('tables', [])
    relationships = model.get('relationships', [])
    roles = model.get('roles', [])
    culture = model.get('culture', 'en-US')

    # Pre-assign stable UUIDs to relationships for consistency between
    # model.tmdl (ref relationship <id>) and relationships.tmdl (relationship <id>)
    for rel in relationships:
        rel_name = rel.get('name', '')
        try:
            uuid.UUID(rel_name)
        except (ValueError, AttributeError):
            rel['name'] = str(uuid.uuid4())

    # 1. database.tmdl
    _write_database_tmdl(def_dir, model)

    # 2. model.tmdl
    _write_model_tmdl(def_dir, model, tables, roles, relationships)

    # 3. relationships.tmdl
    _write_relationships_tmdl(def_dir, relationships)

    # 4. expressions.tmdl (with datasource parameters)
    _write_expressions_tmdl(def_dir, tables, datasources=model_data.get('_datasources'))

    # 5. roles.tmdl
    if roles:
        _write_roles_tmdl(def_dir, roles)

    # 6. tables/*.tmdl
    tables_dir = os.path.join(def_dir, 'tables')
    os.makedirs(tables_dir, exist_ok=True)

    # Clean stale table files from previous runs
    expected_files = set()
    for table in tables:
        tname = table.get('name', 'Table')
        expected_files.add(tname + '.tmdl')
    for existing in os.listdir(tables_dir):
        if existing.endswith('.tmdl') and existing not in expected_files:
            stale_path = os.path.join(tables_dir, existing)
            for _attempt in range(3):
                try:
                    os.remove(stale_path)
                    break
                except PermissionError:
                    time.sleep(0.3 * (2 ** _attempt))
                    logger.debug("Retry removing stale TMDL: %s", stale_path)
                except OSError as exc:
                    logger.debug("Cannot remove stale TMDL %s: %s", stale_path, exc)
                    break
            else:
                logger.warning("Cannot remove stale TMDL %s after retries (locked)", stale_path)

    for table in tables:
        _write_table_tmdl(tables_dir, table)

    # 7. diagramLayout.json (empty — Power BI Desktop fills it on first open)
    diagram_path = os.path.join(def_dir, 'diagramLayout.json')
    with open(diagram_path, 'w', encoding='utf-8') as f:
        json.dump({}, f)

    # 8. perspectives.tmdl (auto-generated from table groupings)
    perspectives = model.get('perspectives', [])
    if not perspectives and len(tables) > 2:
        # Auto-generate a "Full Model" perspective referencing all tables
        perspectives = [{
            "name": "Full Model",
            "tables": [t.get('name', '') for t in tables]
        }]
    if perspectives:
        _write_perspectives_tmdl(def_dir, perspectives)

    # 9. cultures/*.tmdl (model culture)
    linguistic_synonyms = model.get('_linguistic_synonyms', {})
    if culture and culture != 'en-US':
        cultures_dir = os.path.join(def_dir, 'cultures')
        os.makedirs(cultures_dir, exist_ok=True)
        _write_culture_tmdl(cultures_dir, culture, tables, linguistic_synonyms=linguistic_synonyms)
    elif linguistic_synonyms:
        # Even for en-US, write culture with synonyms for Q&A
        cultures_dir = os.path.join(def_dir, 'cultures')
        os.makedirs(cultures_dir, exist_ok=True)
        _write_culture_tmdl(cultures_dir, 'en-US', tables, linguistic_synonyms=linguistic_synonyms)

    # 9b. Additional language cultures (--languages flag)
    extra_languages = model.get('_languages', '')
    if extra_languages:
        _write_multi_language_cultures(def_dir, extra_languages, tables)

    # Release heavy table data after all writing steps (culture/perspectives)
    # are done. Post-write callers only need names and counts.
    for t in tables:
        t['_n_columns'] = len(t.get('columns', []))
        t['_n_measures'] = len(t.get('measures', []))
        t.pop('columns', None)
        t.pop('measures', None)
        t.pop('partitions', None)

    return def_dir


def _write_perspectives_tmdl(def_dir, perspectives):
    """
    Write perspectives.tmdl for multi-audience model views.

    Each perspective lists the tables visible from that viewpoint,
    allowing different user groups to see relevant subsets.

    Args:
        def_dir: Path to the definition/ folder
        perspectives: List of dicts with 'name' and 'tables' keys
    """
    lines = []
    for persp in perspectives:
        p_name = persp.get('name', 'Default')
        lines.append(f"perspective {_quote_name(p_name)}")
        for table_ref in persp.get('tables', []):
            tbl_name = table_ref if isinstance(table_ref, str) else table_ref.get('name', '')
            if tbl_name:
                lines.append(f"\tperspectiveTable {_quote_name(tbl_name)}")
        lines.append("")

    filepath = os.path.join(def_dir, 'perspectives.tmdl')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _write_culture_tmdl(cultures_dir, culture_name, tables, linguistic_synonyms=None):
    """
    Write a culture TMDL file with linguistic metadata and translations.

    Generates translation entries for all table and column names
    in the model for the specified culture/locale.  When the culture
    differs from en-US, also writes ``translatedDisplayFolders`` and
    ``translatedDescriptions`` for measures and columns.

    Args:
        cultures_dir: Path to the cultures/ folder
        culture_name: Locale string (e.g. 'fr-FR')
        tables: List of table definitions (for generating metadata entries)
        linguistic_synonyms: Optional dict of field_name -> list of synonyms
            from Tableau captions/aliases for Q&A support
    """
    lines = [f"culture {_quote_name(culture_name)}"]

    # Linguistic metadata with synonyms
    lines.append("\tlinguisticMetadata =")
    lines.append('\t\t```')
    metadata = {
        "Version": "1.0.0",
        "Language": culture_name,
        "DynamicImprovement": "HighConfidence"
    }
    # Inject synonyms from Tableau field captions
    if linguistic_synonyms:
        entities = {}
        for field_name, syns in linguistic_synonyms.items():
            if syns:
                entities[field_name] = {
                    "State": "Generated",
                    "Terms": [{
                        "Value": s,
                        "State": "Suggested",
                        "Weight": 0.9
                    } for s in syns[:5]]  # Limit to 5 synonyms per field
                }
        if entities:
            metadata["Entities"] = entities
    lines.append(f'\t\t\t{json.dumps(metadata, ensure_ascii=False)}')
    lines.append('\t\t\t```')
    lines.append("")

    # Translation section — translatedDisplayFolders + translatedDescriptions
    folder_translations = _get_display_folder_translations(culture_name)
    if folder_translations and tables:
        for table in tables:
            tbl_name = table.get('name', '')
            if not tbl_name:
                continue
            # Translate display folders for measures
            for measure in table.get('measures', []):
                orig = measure.get('displayFolder', '')
                if not orig:
                    for ann in measure.get('annotations', []):
                        if ann.get('name') == 'displayFolder':
                            orig = ann.get('value', '')
                            break
                translated = folder_translations.get(orig, '')
                if translated and translated != orig:
                    lines.append(
                        f"\ttranslatedDisplayFolder {_quote_name(tbl_name)}"
                        f".{_quote_name(measure.get('name', ''))}"
                        f" = {_quote_name(translated)}"
                    )
            # Translate display folders for columns
            for col in table.get('columns', []):
                orig = col.get('displayFolder', '')
                if not orig:
                    for ann in col.get('annotations', []):
                        if ann.get('name') == 'displayFolder':
                            orig = ann.get('value', '')
                            break
                translated = folder_translations.get(orig, '')
                if translated and translated != orig:
                    lines.append(
                        f"\ttranslatedDisplayFolder {_quote_name(tbl_name)}"
                        f".{_quote_name(col.get('name', ''))}"
                        f" = {_quote_name(translated)}"
                    )
        lines.append("")

    filepath = os.path.join(cultures_dir, f'{culture_name}.tmdl')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _write_multi_language_cultures(def_dir, languages, tables):
    """Write culture TMDL files for multiple languages.

    Args:
        def_dir: Path to the definition/ folder
        languages: Comma-separated locale string (e.g. 'fr-FR,de-DE,es-ES')
        tables: List of table definitions
    """
    if not languages:
        return

    locales = [loc.strip() for loc in languages.split(',') if loc.strip()]
    if not locales:
        return

    cultures_dir = os.path.join(def_dir, 'cultures')
    os.makedirs(cultures_dir, exist_ok=True)

    for locale in locales:
        if locale == 'en-US':
            continue  # Default culture, no need for translation file
        _write_culture_tmdl(cultures_dir, locale, tables)


# ── Display folder translations (built-in) ──────────────────────────────────

_DISPLAY_FOLDER_TRANSLATIONS = {
    'fr-FR': {
        'Dimensions': 'Dimensions',
        'Measures': 'Mesures',
        'Time Intelligence': 'Intelligence Temporelle',
        'Flags': 'Indicateurs',
        'Calculations': 'Calculs',
        'Groups': 'Groupes',
        'Sets': 'Ensembles',
        'Bins': 'Intervalles',
        'Parameters': 'Paramètres',
        'Field Parameters': 'Paramètres de Champ',
        'Calculation Groups': 'Groupes de Calcul',
    },
    'de-DE': {
        'Dimensions': 'Dimensionen',
        'Measures': 'Kennzahlen',
        'Time Intelligence': 'Zeitintelligenz',
        'Flags': 'Kennzeichen',
        'Calculations': 'Berechnungen',
        'Groups': 'Gruppen',
        'Sets': 'Mengen',
        'Bins': 'Intervalle',
        'Parameters': 'Parameter',
        'Field Parameters': 'Feldparameter',
        'Calculation Groups': 'Berechnungsgruppen',
    },
    'es-ES': {
        'Dimensions': 'Dimensiones',
        'Measures': 'Medidas',
        'Time Intelligence': 'Inteligencia Temporal',
        'Flags': 'Indicadores',
        'Calculations': 'Cálculos',
        'Groups': 'Grupos',
        'Sets': 'Conjuntos',
        'Bins': 'Intervalos',
        'Parameters': 'Parámetros',
        'Field Parameters': 'Parámetros de Campo',
        'Calculation Groups': 'Grupos de Cálculo',
    },
    'pt-BR': {
        'Dimensions': 'Dimensões',
        'Measures': 'Medidas',
        'Time Intelligence': 'Inteligência Temporal',
        'Flags': 'Indicadores',
        'Calculations': 'Cálculos',
        'Groups': 'Grupos',
        'Sets': 'Conjuntos',
        'Bins': 'Intervalos',
        'Parameters': 'Parâmetros',
        'Field Parameters': 'Parâmetros de Campo',
        'Calculation Groups': 'Grupos de Cálculo',
    },
    'ja-JP': {
        'Dimensions': 'ディメンション',
        'Measures': 'メジャー',
        'Time Intelligence': 'タイムインテリジェンス',
        'Flags': 'フラグ',
        'Calculations': '計算',
        'Groups': 'グループ',
        'Sets': 'セット',
        'Bins': 'ビン',
        'Parameters': 'パラメーター',
        'Field Parameters': 'フィールドパラメーター',
        'Calculation Groups': '計算グループ',
    },
    'zh-CN': {
        'Dimensions': '维度',
        'Measures': '度量',
        'Time Intelligence': '时间智能',
        'Flags': '标志',
        'Calculations': '计算',
        'Groups': '组',
        'Sets': '集',
        'Bins': '区间',
        'Parameters': '参数',
        'Field Parameters': '字段参数',
        'Calculation Groups': '计算组',
    },
    'ko-KR': {
        'Dimensions': '차원',
        'Measures': '측정값',
        'Time Intelligence': '시간 인텔리전스',
        'Flags': '플래그',
        'Calculations': '계산',
        'Groups': '그룹',
        'Sets': '집합',
        'Bins': '구간',
        'Parameters': '매개변수',
        'Field Parameters': '필드 매개변수',
        'Calculation Groups': '계산 그룹',
    },
    'it-IT': {
        'Dimensions': 'Dimensioni',
        'Measures': 'Misure',
        'Time Intelligence': 'Time Intelligence',
        'Flags': 'Indicatori',
        'Calculations': 'Calcoli',
        'Groups': 'Gruppi',
        'Sets': 'Insiemi',
        'Bins': 'Intervalli',
        'Parameters': 'Parametri',
        'Field Parameters': 'Parametri di Campo',
        'Calculation Groups': 'Gruppi di Calcolo',
    },
    'nl-NL': {
        'Dimensions': 'Dimensies',
        'Measures': 'Metingen',
        'Time Intelligence': 'Tijdintelligentie',
        'Flags': 'Vlaggen',
        'Calculations': 'Berekeningen',
        'Groups': 'Groepen',
        'Sets': 'Sets',
        'Bins': 'Intervallen',
        'Parameters': 'Parameters',
        'Field Parameters': 'Veldparameters',
        'Calculation Groups': 'Berekeningsgroepen',
    },
    # ── v28: Additional culture translations ──
    'sv-SE': {
        'Dimensions': 'Dimensioner',
        'Measures': 'Mått',
        'Time Intelligence': 'Tidsintelligens',
        'Flags': 'Flaggor',
        'Calculations': 'Beräkningar',
        'Groups': 'Grupper',
        'Sets': 'Uppsättningar',
        'Bins': 'Intervall',
        'Parameters': 'Parametrar',
        'Field Parameters': 'Fältparametrar',
        'Calculation Groups': 'Beräkningsgrupper',
    },
    'da-DK': {
        'Dimensions': 'Dimensioner',
        'Measures': 'Målinger',
        'Time Intelligence': 'Tidsintelligens',
        'Flags': 'Flag',
        'Calculations': 'Beregninger',
        'Groups': 'Grupper',
        'Sets': 'Sæt',
        'Bins': 'Intervaller',
        'Parameters': 'Parametre',
        'Field Parameters': 'Feltparametre',
        'Calculation Groups': 'Beregningsgrupper',
    },
    'nb-NO': {
        'Dimensions': 'Dimensjoner',
        'Measures': 'Målinger',
        'Time Intelligence': 'Tidsintelligens',
        'Flags': 'Flagg',
        'Calculations': 'Beregninger',
        'Groups': 'Grupper',
        'Sets': 'Sett',
        'Bins': 'Intervaller',
        'Parameters': 'Parametere',
        'Field Parameters': 'Feltparametere',
        'Calculation Groups': 'Beregningsgrupper',
    },
    'fi-FI': {
        'Dimensions': 'Dimensiot',
        'Measures': 'Mittarit',
        'Time Intelligence': 'Aikaäly',
        'Flags': 'Liput',
        'Calculations': 'Laskelmat',
        'Groups': 'Ryhmät',
        'Sets': 'Joukot',
        'Bins': 'Intervallit',
        'Parameters': 'Parametrit',
        'Field Parameters': 'Kenttäparametrit',
        'Calculation Groups': 'Laskelmaryhmät',
    },
    'pl-PL': {
        'Dimensions': 'Wymiary',
        'Measures': 'Miary',
        'Time Intelligence': 'Analiza Czasowa',
        'Flags': 'Flagi',
        'Calculations': 'Obliczenia',
        'Groups': 'Grupy',
        'Sets': 'Zbiory',
        'Bins': 'Przedziały',
        'Parameters': 'Parametry',
        'Field Parameters': 'Parametry Pola',
        'Calculation Groups': 'Grupy Obliczeń',
    },
    'tr-TR': {
        'Dimensions': 'Boyutlar',
        'Measures': 'Ölçüler',
        'Time Intelligence': 'Zaman Zekası',
        'Flags': 'Bayraklar',
        'Calculations': 'Hesaplamalar',
        'Groups': 'Gruplar',
        'Sets': 'Kümeler',
        'Bins': 'Aralıklar',
        'Parameters': 'Parametreler',
        'Field Parameters': 'Alan Parametreleri',
        'Calculation Groups': 'Hesaplama Grupları',
    },
    'ru-RU': {
        'Dimensions': 'Измерения',
        'Measures': 'Метрики',
        'Time Intelligence': 'Временной анализ',
        'Flags': 'Флаги',
        'Calculations': 'Вычисления',
        'Groups': 'Группы',
        'Sets': 'Наборы',
        'Bins': 'Интервалы',
        'Parameters': 'Параметры',
        'Field Parameters': 'Параметры полей',
        'Calculation Groups': 'Группы вычислений',
    },
    'ar-SA': {
        'Dimensions': 'الأبعاد',
        'Measures': 'المقاييس',
        'Time Intelligence': 'ذكاء الوقت',
        'Flags': 'الأعلام',
        'Calculations': 'الحسابات',
        'Groups': 'المجموعات',
        'Sets': 'المجموعات',
        'Bins': 'الفواصل',
        'Parameters': 'المعلمات',
        'Field Parameters': 'معلمات الحقل',
        'Calculation Groups': 'مجموعات الحساب',
    },
    'hi-IN': {
        'Dimensions': 'आयाम',
        'Measures': 'माप',
        'Time Intelligence': 'समय बुद्धिमत्ता',
        'Flags': 'झंडे',
        'Calculations': 'गणनाएँ',
        'Groups': 'समूह',
        'Sets': 'सेट',
        'Bins': 'अंतराल',
        'Parameters': 'पैरामीटर',
        'Field Parameters': 'फ़ील्ड पैरामीटर',
        'Calculation Groups': 'गणना समूह',
    },
    'th-TH': {
        'Dimensions': 'มิติ',
        'Measures': 'การวัด',
        'Time Intelligence': 'ความฉลาดด้านเวลา',
        'Flags': 'ธง',
        'Calculations': 'การคำนวณ',
        'Groups': 'กลุ่ม',
        'Sets': 'ชุด',
        'Bins': 'ช่วง',
        'Parameters': 'พารามิเตอร์',
        'Field Parameters': 'พารามิเตอร์ฟิลด์',
        'Calculation Groups': 'กลุ่มการคำนวณ',
    },
}


def _get_display_folder_translations(culture_name):
    """Look up display folder translations for a given culture.

    Falls back to translating using the language portion (e.g. 'fr' from 'fr-CA').
    Returns empty dict if no translations are available.
    """
    # Exact match
    if culture_name in _DISPLAY_FOLDER_TRANSLATIONS:
        return _DISPLAY_FOLDER_TRANSLATIONS[culture_name]

    # Try language-only match (e.g. 'fr' from 'fr-CA' → 'fr-FR')
    lang = culture_name.split('-')[0].lower()
    for key, val in _DISPLAY_FOLDER_TRANSLATIONS.items():
        if key.split('-')[0].lower() == lang:
            return val

    return {}


def _write_database_tmdl(def_dir, model):
    """Generate database.tmdl."""
    compat = model.get('compatibilityLevel', 1567)
    if compat < 1600:
        compat = 1600

    content = f"database\n\tcompatibilityLevel: {compat}\n\n"

    filepath = os.path.join(def_dir, 'database.tmdl')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def _write_model_tmdl(def_dir, model, tables, roles=None, relationships=None):
    """Generate model.tmdl."""
    culture = model.get('culture', 'en-US')
    perspectives = model.get('perspectives', [])

    has_calc_groups = any(t.get('calculationGroup') for t in tables)

    lines = []
    lines.append("model Model")
    lines.append(f"\tculture: {culture}")
    lines.append("\tdefaultPowerBIDataSourceVersion: powerBI_V3")
    lines.append("\tsourceQueryCulture: en-US")
    if has_calc_groups:
        lines.append("\tdiscourageImplicitMeasures")
    lines.append("\tdataAccessOptions")
    lines.append("\t\tlegacyRedirects")
    lines.append("\t\treturnErrorValuesAsNull")
    lines.append("")

    # Table order annotation
    table_names = [t.get('name', '') for t in tables]
    table_names_json = '["' + '","'.join(table_names) + '"]'
    lines.append(f"annotation PBI_QueryOrder = {table_names_json}")
    lines.append("")

    # Ref tables
    for table in tables:
        tname = _quote_name(table.get('name', ''))
        lines.append(f"ref table {tname}")

    lines.append("")

    # Ref relationships
    if relationships:
        for rel in relationships:
            rel_id = rel.get('name', str(uuid.uuid4()))
            lines.append(f"ref relationship {rel_id}")
        lines.append("")

    # Ref expression for the DataFolder parameter
    lines.append("ref expression DataFolder")
    lines.append("")

    # Ref roles (RLS)
    if roles:
        for role in roles:
            rname = _quote_name(role.get('name', ''))
            lines.append(f"ref role {rname}")
        lines.append("")

    # Ref perspectives
    if perspectives:
        for persp in perspectives:
            pname = _quote_name(persp.get('name', 'Default'))
            lines.append(f"ref perspective {pname}")
        lines.append("")

    # Ref culture
    if culture and culture != 'en-US':
        lines.append(f"ref culture {_quote_name(culture)}")
        lines.append("")

    content = '\n'.join(lines) + '\n'

    filepath = os.path.join(def_dir, 'model.tmdl')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def _write_expressions_tmdl(def_dir, tables, datasources=None):
    """Generate expressions.tmdl with M parameters.

    Creates parameterized data source expressions:
    - DataFolder: for file-based data sources
    - ServerName: for server-based connections (SQL, Oracle, PostgreSQL, etc.)
    - DatabaseName: for database-based connections

    These M parameters allow easy switching between dev/staging/prod environments.
    """
    file_dirs = []          # directory paths for DataFolder
    has_file_source = False  # whether any file-based DataFolder ref exists
    server_names = set()
    database_names = set()

    for table in tables:
        for partition in table.get('partitions', []):
            source = partition.get('source', {})
            if isinstance(source, dict):
                expr = source.get('expression', '')
            elif isinstance(source, str):
                expr = source
            else:
                continue

            # Detect file-based sources (DataFolder references)
            if re.search(r'DataFolder\s*&\s*"\\', expr):
                has_file_source = True
            if re.search(r'File\.Contents\(', expr):
                has_file_source = True

            # Detect server/database references from M queries
            for m in re.finditer(r'(?:Sql\.Database|PostgreSQL\.Database|Oracle\.Database|Mysql\.Database)\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"', expr):
                server_names.add(m.group(1))
                database_names.add(m.group(2))
            for m in re.finditer(r'(?:Snowflake\.Databases|AmazonRedshift\.Database|GoogleBigQuery\.Database)\s*\(\s*"([^"]+)"', expr):
                server_names.add(m.group(1))

    # Extract directory info from datasource connection metadata
    if datasources:
        for ds in (datasources if isinstance(datasources, list) else [datasources]):
            conn = ds.get('connection', {})
            server = conn.get('server', conn.get('host', ''))
            db = conn.get('dbname', conn.get('database', ''))
            if server:
                server_names.add(server)
            if db:
                database_names.add(db)

            # Extract file directory from connection details (filename / directory)
            for cmap_val in list(ds.get('connection_map', {}).values()) + [conn]:
                details = cmap_val.get('details', cmap_val) if isinstance(cmap_val, dict) else {}
                fn = details.get('filename', '')
                dr = details.get('directory', '')
                if fn:
                    norm = fn.replace('\\', '/').lstrip('/')
                    parent = norm.rsplit('/', 1)[0] if '/' in norm else ''
                    if parent:
                        file_dirs.append(parent)
                        has_file_source = True
                if dr:
                    file_dirs.append(dr.replace('\\', '/').lstrip('/'))
                    has_file_source = True

    default_folder = "C:\\Data"

    if file_dirs:
        unique_dirs = list(dict.fromkeys(file_dirs))  # deduplicate, preserve order

        if len(unique_dirs) == 1:
            common_dir = unique_dirs[0]
        else:
            common = os.path.commonprefix(unique_dirs)
            if '/' in common:
                common_dir = common[:common.rfind('/')]
            else:
                common_dir = common  # all in same directory

        if common_dir:
            default_folder = "C:\\" + common_dir.replace('/', '\\')

    lines = []
    lines.append(f'expression DataFolder = "{default_folder}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]')
    lines.append("")

    # Add server/database M parameters for easy environment switching
    if server_names:
        default_server = sorted(server_names)[0]
        lines.append(f'expression ServerName = "{default_server}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]')
        lines.append("")

    if database_names:
        default_db = sorted(database_names)[0]
        lines.append(f'expression DatabaseName = "{default_db}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]')
        lines.append("")

    content = '\n'.join(lines) + '\n'

    filepath = os.path.join(def_dir, 'expressions.tmdl')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def _write_roles_tmdl(def_dir, roles):
    """Generate roles.tmdl with RLS role definitions."""
    if not roles:
        return

    lines = []

    for role in roles:
        role_name = _quote_name(role.get('name', 'DefaultRole'))
        model_permission = role.get('modelPermission', 'read')

        lines.append(f"role {role_name}")
        lines.append(f"\tmodelPermission: {model_permission}")

        migration_note = role.get('_migration_note', '')
        if migration_note:
            note_escaped = migration_note.replace('"', '\\"')
            lines.append(f'\tannotation MigrationNote = "{note_escaped}"')

        lines.append("")

        for tp in role.get('tablePermissions', []):
            tp_name = tp.get('name', '') or ''
            if not tp_name:
                continue
            table_name = _quote_name(tp_name)
            filter_expr = tp.get('filterExpression', '')

            lines.append(f"\ttablePermission {table_name}")

            if filter_expr:
                filter_clean = filter_expr.replace('\n', ' ').replace('\r', ' ').strip()
                lines.append(f"\t\tfilterExpression = {filter_clean}")

            lines.append("")

    content = '\n'.join(lines) + '\n'

    filepath = os.path.join(def_dir, 'roles.tmdl')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def _write_relationships_tmdl(def_dir, relationships):
    """Generate relationships.tmdl."""
    if not relationships:
        filepath = os.path.join(def_dir, 'relationships.tmdl')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("")
        return

    lines = []

    for rel in relationships:
        rel_id = rel.get('name', str(uuid.uuid4()))
        try:
            uuid.UUID(rel_id)
        except ValueError:
            rel_id = str(uuid.uuid4())

        from_table = _quote_name(rel.get('fromTable', ''))
        from_col = _quote_name(rel.get('fromColumn', ''))
        to_table = _quote_name(rel.get('toTable', ''))
        to_col = _quote_name(rel.get('toColumn', ''))

        lines.append(f"relationship {rel_id}")
        lines.append(f"\tfromColumn: {from_table}.{from_col}")
        lines.append(f"\ttoColumn: {to_table}.{to_col}")

        from_card = rel.get('fromCardinality', '')
        to_card = rel.get('toCardinality', '')
        if from_card == 'many' and to_card == 'many':
            lines.append("\tfromCardinality: many")
            lines.append("\ttoCardinality: many")
        elif from_card == 'many' and to_card == 'one':
            pass

        cfb = rel.get('crossFilteringBehavior', 'oneDirection')
        lines.append(f"\tcrossFilteringBehavior: {cfb}")

        if rel.get('isActive') == False:
            lines.append("\tisActive: false")

        lines.append("")

    content = '\n'.join(lines) + '\n'

    filepath = os.path.join(def_dir, 'relationships.tmdl')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


# --- Description auto-generation for Copilot/Q&A readiness ---

def _generate_table_description(table):
    """Auto-generate a human-readable description for a table.

    Priority: (1) explicit description, (2) caption-based, (3) synthesized
    from table name and column summary.
    """
    existing = table.get('description', '')
    if existing:
        return existing

    table_name = table.get('name', 'Table')
    columns = table.get('columns', [])
    measures = table.get('measures', [])

    col_names = [c.get('name', '') for c in columns[:8] if c.get('name')]
    col_summary = ', '.join(col_names)
    if len(columns) > 8:
        col_summary += f', ... ({len(columns)} columns total)'

    parts = [f"Contains {len(columns)} columns"]
    if measures:
        parts.append(f"{len(measures)} measures")
    parts_str = ' and '.join(parts)

    if col_summary:
        return f"{parts_str}: {col_summary}."
    return f"{parts_str}."


def _generate_column_description(column):
    """Auto-generate a description for a column when none exists.

    Uses data type, semantic role, and data category to create a readable
    description for PBI Copilot/Q&A.
    """
    existing = column.get('description', '')
    if existing:
        return existing

    col_name = column.get('name', 'Column')
    data_type = column.get('dataType', 'string')
    data_category = column.get('dataCategory', '')
    is_calculated = column.get('isCalculated', False)
    expression = column.get('expression', '')

    parts = []
    if is_calculated and expression:
        parts.append(f"Calculated column ({data_type})")
    else:
        parts.append(f"{data_type.capitalize()} column")

    if data_category:
        parts.append(f"categorized as {data_category}")

    if column.get('isKey', False):
        parts.append("(table key)")

    return '. '.join(parts) + '.'


def _generate_measure_description(measure):
    """Auto-generate a description for a measure when none exists.

    Includes the original Tableau formula as documentation when available.
    """
    existing = measure.get('description', '')
    if existing:
        return existing

    measure_name = measure.get('name', 'Measure')
    expression = measure.get('expression', '')
    original_formula = measure.get('_original_formula', '')

    parts = []
    if original_formula:
        parts.append(f"Migrated from Tableau: {original_formula}")
    if expression and expression != '0':
        dax_preview = expression[:200]
        if len(expression) > 200:
            # Ensure truncation doesn't leave unclosed brackets
            # which would cause validator false positives
            open_brackets = dax_preview.count('[') - dax_preview.count(']')
            open_parens = dax_preview.count('(') - dax_preview.count(')')
            suffix = ']' * max(0, open_brackets) + ')' * max(0, open_parens)
            dax_preview += suffix + '...'
        parts.append(f"DAX: {dax_preview}")

    if not parts:
        parts.append(f"Measure: {measure_name}")

    return ' | '.join(parts)


def _write_table_tmdl(tables_dir, table):
    """Generate a {table_name}.tmdl file."""
    table_name = table.get('name', 'Table')
    tname_quoted = _quote_name(table_name)

    lines = []
    lines.append(f"table {tname_quoted}")
    lines.append(f"\tlineageTag: {uuid.uuid4()}")

    # Table description — TMDL does not support 'description:' at the table level.
    # The description is preserved as a Copilot_TableDescription annotation instead.
    table_desc = _generate_table_description(table)

    lines.append("")

    # Calculation group block (must come before columns/measures)
    cg = table.get('calculationGroup')
    if cg:
        lines.append("\tcalculationGroup")
        lines.append(f"\t\tprecedence: {cg.get('precedence', 0)}")
        lines.append("")
        for item in cg.get('calculationItems', []):
            item_name = _quote_name(item.get('name', 'Item'))
            lines.append(f"\t\tcalculationItem {item_name}")
            expr = item.get('expression', 'CALCULATE(SELECTEDMEASURE())')
            if '\n' in expr:
                lines.append(f"\t\t\texpression = ```")
                for el in expr.split('\n'):
                    lines.append(f"\t\t\t\t{el}")
                lines.append("\t\t\t\t```")
            else:
                lines.append(f"\t\t\texpression = {expr}")
            ordinal = item.get('ordinal')
            if ordinal is not None:
                lines.append(f"\t\t\tordinal: {ordinal}")
            lines.append("")
        lines.append("")

    # Measures (before columns, as in PBI Hero reference)
    # Deduplicate by name — first wins
    seen_measure_names = set()
    for measure in table.get('measures', []):
        mn = measure.get('name', '').lower()
        if mn not in seen_measure_names:
            seen_measure_names.add(mn)
            _write_measure(lines, measure)

    # Columns (deduplicate by name — last wins)
    seen_col_names = set()
    deduped_columns = []
    for column in reversed(table.get('columns', [])):
        cn = column.get('name', '').lower()
        if cn not in seen_col_names:
            seen_col_names.add(cn)
            deduped_columns.append(column)
    deduped_columns.reverse()
    for column in deduped_columns:
        _write_column(lines, column)

    # Hierarchies
    for hierarchy in table.get('hierarchies', []):
        _write_hierarchy(lines, hierarchy)

    # Partition
    for partition in table.get('partitions', []):
        _write_partition(lines, table_name, partition)

    # Incremental refresh policy (if configured)
    refresh_policy = table.get('refreshPolicy')
    if refresh_policy:
        _write_refresh_policy(lines, refresh_policy)

    # Annotations
    lines.append("\tannotation PBI_ResultType = Table")

    # Copilot optimization hints
    if table_name == 'Calendar':
        lines.append("\tannotation Copilot_DateTable = true")
    lines.append(f"\tannotation Copilot_TableDescription = {_generate_table_description(table)}")

    # Lineage annotations (from merge)
    source_wbs = table.get('_source_workbooks', [])
    if source_wbs:
        lines.append(f"\tannotation MigrationSource = {json.dumps(source_wbs)}")
    merge_action = table.get('_merge_action', '')
    if merge_action:
        lines.append(f'\tannotation MergeAction = {merge_action}')
    lines.append("")

    content = '\n'.join(lines) + '\n'

    filename = _safe_filename(table_name) + '.tmdl'
    filepath = os.path.join(tables_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def _write_measure(lines, measure):
    """Write a measure in TMDL."""
    mname = _quote_name(measure.get('name', 'Measure'))
    expression = measure.get('expression') or '0'

    if '\n' in expression:
        lines.append(f"\tmeasure {mname} = ```")
        for expr_line in expression.split('\n'):
            lines.append(f"\t\t\t{expr_line}")
        lines.append("\t\t\t```")
    else:
        lines.append(f"\tmeasure {mname} = {expression}")

    fmt = measure.get('formatString', '')
    if fmt and fmt != '0':
        lines.append(f"\t\tformatString: {fmt}")

    folder = measure.get('displayFolder', '')
    if folder:
        lines.append(f"\t\tdisplayFolder: {folder}")

    if measure.get('isHidden', False):
        lines.append("\t\tisHidden")

    lines.append(f"\t\tlineageTag: {uuid.uuid4()}")

    # Description as annotation for Copilot/Q&A readiness
    measure_desc = _generate_measure_description(measure)
    safe_desc = measure_desc.replace('\n', ' ').replace('\r', '').strip()
    if safe_desc:
        lines.append(f"\t\tannotation Copilot_Description = {safe_desc}")

    # Lineage annotations (from merge)
    source_wbs = measure.get('_source_workbooks', [])
    if source_wbs:
        lines.append(f"\t\tannotation MigrationSource = {json.dumps(source_wbs)}")
    merge_action = measure.get('_merge_action', '')
    if merge_action:
        lines.append(f'\t\tannotation MergeAction = {merge_action}')

    lines.append("")


def _write_column_properties(lines, column):
    """Write shared column properties (formatString, lineageTag, summarizeBy, etc.)."""
    fmt = column.get('formatString', '')
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")

    lines.append(f"\t\tlineageTag: {uuid.uuid4()}")

    summarize = _tmdl_summarize(column.get('summarizeBy', 'none'))
    lines.append(f"\t\tsummarizeBy: {summarize}")


def _write_column_flags(lines, column):
    """Write optional column flags (isHidden, isKey, dataCategory, etc.)."""
    if column.get('isHidden', False):
        lines.append("\t\tisHidden")
    if column.get('isKey', False):
        lines.append("\t\tisKey")
    data_category = column.get('dataCategory', '')
    if data_category:
        lines.append(f"\t\tdataCategory: {data_category}")
    display_folder = column.get('displayFolder', '')
    if display_folder:
        lines.append(f"\t\tdisplayFolder: {display_folder}")
    sort_by = column.get('sortByColumn', '')
    if sort_by:
        lines.append(f"\t\tsortByColumn: {_quote_name(sort_by)}")

    # Custom annotations (e.g. alternateOf for agg tables)
    for ann in column.get('annotations', []):
        ann_name = ann.get('name', '')
        ann_value = ann.get('value', '')
        if ann_name and ann_value:
            lines.append(f"\t\tannotation {ann_name} = {ann_value}")

    # Copilot optimization: mark technical columns as hidden from Copilot
    # Match patterns like OrderID, Customer_ID, product_key, etc.
    # but not words like "Valid", "Fluid", "Avid"
    col_name = column.get('name', '')
    _is_technical = bool(re.search(
        r'(?:_id|_key|_sk|_fk|_pk|ID|Key|SK|FK|PK)$',
        col_name
    ))
    if _is_technical:
        lines.append("\t\tannotation Copilot_Hidden = true")

    lines.append("")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    lines.append("")


def _write_column(lines, column):
    """Write a column in TMDL (physical or calculated)."""
    col_name = column.get('name', 'Column')
    cname_quoted = _quote_name(col_name)
    data_type = _tmdl_datatype(column.get('dataType', 'string'))
    expression = column.get('expression', '')
    is_calculated = column.get('isCalculated', False)

    if is_calculated and expression:
        if '\n' in expression:
            lines.append(f"\tcolumn {cname_quoted} = ```")
            for expr_line in expression.split('\n'):
                lines.append(f"\t\t\t{expr_line}")
            lines.append("\t\t\t```")
        else:
            lines.append(f"\tcolumn {cname_quoted} = {expression}")
        lines.append(f"\t\tdataType: {data_type}")
        _write_column_properties(lines, column)
        _write_column_flags(lines, column)
    else:
        lines.append(f"\tcolumn {cname_quoted}")
        lines.append(f"\t\tdataType: {data_type}")
        _write_column_properties(lines, column)

        source_col = column.get('sourceColumn', col_name)
        source_col_quoted = _quote_name(source_col) if re.search(r'[^a-zA-Z0-9_]', source_col) else source_col
        lines.append(f"\t\tsourceColumn: {source_col_quoted}")
        _write_column_flags(lines, column)


def _write_hierarchy(lines, hierarchy):
    """Write a hierarchy in TMDL."""
    h_name = _quote_name(hierarchy.get('name', 'Hierarchy'))
    levels = hierarchy.get('levels', [])

    lines.append(f"\thierarchy {h_name}")
    lines.append(f"\t\tlineageTag: {uuid.uuid4()}")
    lines.append("")

    for level in levels:
        level_name = _quote_name(level.get('name', 'Level'))
        col_name = _quote_name(level.get('column', level.get('name', '')))
        ordinal = level.get('ordinal', 0)

        lines.append(f"\t\tlevel {level_name}")
        lines.append(f"\t\t\tordinal: {ordinal}")
        lines.append(f"\t\t\tcolumn: {col_name}")
        lines.append(f"\t\t\tlineageTag: {uuid.uuid4()}")
        lines.append("")

    lines.append("")


def _write_refresh_policy(lines, policy):
    """Write an incremental refresh policy in TMDL format.

    The policy dict should contain:
      - incrementalGranularity: 'Day' | 'Month' | 'Quarter' | 'Year'
      - incrementalPeriods: int (number of periods to refresh)
      - rollingWindowGranularity: 'Day' | 'Month' | 'Quarter' | 'Year'
      - rollingWindowPeriods: int (total window size)
      - pollingExpression: M expression for the date column (optional)
      - sourceExpression: M source expression (optional)
    """
    lines.append("\trefreshPolicy")
    gran = policy.get('incrementalGranularity', 'Day')
    inc_periods = policy.get('incrementalPeriods', 1)
    rw_gran = policy.get('rollingWindowGranularity', 'Month')
    rw_periods = policy.get('rollingWindowPeriods', 12)

    lines.append(f"\t\tincrementalGranularity: {gran}")
    lines.append(f"\t\tincrementalPeriods: {inc_periods}")
    lines.append(f"\t\trollingWindowGranularity: {rw_gran}")
    lines.append(f"\t\trollingWindowPeriods: {rw_periods}")

    # Polling expression (the date column to filter on)
    polling = policy.get('pollingExpression', '')
    if polling:
        lines.append(f"\t\tpollingExpression =")
        for pl in polling.split('\n'):
            lines.append(f"\t\t\t\t{pl}")

    # Source expression (the M query with RangeStart/RangeEnd parameters)
    source_expr = policy.get('sourceExpression', '')
    if source_expr:
        lines.append(f"\t\tsourceExpression =")
        for sl in source_expr.split('\n'):
            lines.append(f"\t\t\t\t{sl}")

    lines.append("")


def detect_refresh_policy(table, datasources=None):
    """Auto-detect an incremental refresh policy for a table.

    If the table has a DateTime column and comes from a relational data source,
    generate default policy settings. Users should refine these.

    Args:
        table: Table dict with 'columns' list.
        datasources: Optional list of datasource dicts for connection type detection.

    Returns:
        dict with policy settings, or None if not applicable.
    """
    date_cols = []
    for col in table.get('columns', []):
        dt = (col.get('dataType') or col.get('type') or '').lower()
        name = (col.get('name') or '').lower()
        if 'date' in dt or 'datetime' in dt or 'timestamp' in dt:
            date_cols.append(col)
        elif any(kw in name for kw in ('date', 'datetime', 'timestamp', 'created_at', 'updated_at')):
            date_cols.append(col)

    if not date_cols:
        return None

    # Pick the best candidate date column
    best = date_cols[0]
    for c in date_cols:
        cn = (c.get('name') or '').lower()
        if any(kw in cn for kw in ('updated', 'modified', 'last_')):
            best = c
            break

    col_name = best.get('name', 'Date')

    # Build M polling expression
    polling = f'let\n    currentDate = DateTime.LocalNow(),\n    #"MaxDate" = Sql.Database("server", "db"){{[Schema="dbo",Item="{table.get("name", "Table")}"]}}[{col_name}],\n    maxVal = List.Max(#"MaxDate")\nin\n    maxVal'

    return {
        'incrementalGranularity': 'Day',
        'incrementalPeriods': 3,
        'rollingWindowGranularity': 'Month',
        'rollingWindowPeriods': 12,
        'pollingExpression': polling,
        'sourceExpression': '',
        'dateColumn': col_name,
    }


def _fix_m_if_else_balance(m_expr):
    """Ensure every M ``if...then`` has a matching ``else`` clause.

    Power Query M requires ``if cond then val else fallback`` — an ``if``
    without ``else`` is a parse error.  This function counts ``if`` vs
    ``else`` tokens (outside string literals) and appends ``else null`` for
    each missing ``else``.
    """
    if not m_expr or 'if' not in m_expr:
        return m_expr
    stripped = re.sub(r'"([^"]|"")*"', '""', m_expr)
    if_count = len(re.findall(r'\bif\b', stripped))
    else_count = len(re.findall(r'\belse\b', stripped))
    if if_count > else_count:
        deficit = if_count - else_count
        logger.warning("M if/else imbalance (if=%d, else=%d) — auto-appending %d × 'else null'",
                        if_count, else_count, deficit)
        m_expr = m_expr.rstrip() + ' else null' * deficit
    return m_expr


def _write_partition(lines, table_name, partition):
    """Write a partition in TMDL."""
    part_name = f"{table_name}-{uuid.uuid4()}"
    mode = partition.get('mode', 'import')
    source = partition.get('source', {})
    source_type = source.get('type', 'm')
    expression = source.get('expression', '')

    lines.append(f"\tpartition {_quote_name(part_name)} = {source_type}")
    lines.append(f"\t\tmode: {mode}")

    # Calculation group partitions have no source expression
    if source_type == 'calculationGroup':
        lines.append("")
        return

    if expression:
        if source_type == 'calculated':
            expr_clean = expression.replace('\r\n', '\n').replace('\r', '\n')
            if '\n' in expr_clean:
                lines.append("\t\tsource = ```")
                for expr_line in expr_clean.split('\n'):
                    lines.append(f"\t\t\t\t{expr_line}")
                lines.append("\t\t\t\t```")
            else:
                lines.append(f"\t\tsource = {expr_clean}")
        else:
            # Validate M if/else balance before writing
            expression = _fix_m_if_else_balance(expression)
            lines.append(f"\t\tsource =")
            for expr_line in expression.split('\n'):
                lines.append(f"\t\t\t\t{expr_line}")
    else:
        lines.append(f"\t\tsource =")
        lines.append("\t\t\t\tlet")
        lines.append("\t\t\t\t\tSource = #table(type table [], {})")
        lines.append("\t\t\t\t\t// TODO: Configure data source — replace with actual connection")
        lines.append("\t\t\t\tin")
        lines.append("\t\t\t\t\tSource")

    lines.append("")
