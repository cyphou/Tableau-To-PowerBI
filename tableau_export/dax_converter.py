"""
DAX Formula Converter — Tableau formulas → DAX (Power BI)

Extracted from datasource_extractor.py for maintainability.
Converts Tableau calculation formulas to valid DAX expressions.
"""

import re


# ── Shared utility ────────────────────────────────────────────────────────────

def _reverse_tableau_bracket_escape(name):
    """Reverses the Tableau ] → ) substitution in column names.
    
    Tableau replaces ] with ) in physical column names because
    ] conflicts with its [field] syntax. To generate Power Query M that
    references the real column names in the source, we reverse this
    substitution when ) appears without a matching ( (orphan parenthesis).
    """
    opens = name.count('(')
    closes = name.count(')')
    excess = closes - opens
    if excess <= 0:
        return name
    result = list(name)
    replaced = 0
    for i in range(len(result) - 1, -1, -1):
        if result[i] == ')' and replaced < excess:
            result[i] = ']'
            replaced += 1
    return ''.join(result)


# ── Tableau → DAX simple function mappings (table-driven) ─────────────────────
# Each tuple: (Tableau regex pattern, DAX replacement)
# Order matters — more specific patterns first

_SIMPLE_FUNCTION_MAP = [
    # User/security functions
    (r'\bUSERNAME\s*\(\s*\)', 'USERPRINCIPALNAME()'),
    (r'\bFULLNAME\s*\(\s*\)', 'USERPRINCIPALNAME()'),
    (r'\bUSERDOMAIN\s*\(\s*\)', '""  /* USERDOMAIN: no DAX equivalent — use RLS roles */'),

    # Null/logic
    (r'\bISNULL\b', 'ISBLANK'),
    (r'\bISNUMBER\s*\(', 'ISNUMBER('),
    (r'\bNOT\s*\(', 'NOT('),

    # Aggregation (before generic text/math to avoid conflicts)
    (r'\bCOUNTD\s*\(', 'DISTINCTCOUNT('),
    (r'\bAVG\s*\(', 'AVERAGE('),
    (r'\bCONTAINS\s*\(', 'CONTAINSSTRING('),
    (r'\bASCII\s*\(', 'UNICODE('),
    (r'\bCHAR\s*\(', 'UNICHAR('),
    # ATTR is handled separately in _convert_attr() — context-aware (measure vs column)

    # Date functions — DATETRUNC
    (r'\bDATETRUNC\s*\(\s*[\'"]?year[\'"]?\s*,', 'STARTOFYEAR('),
    (r'\bDATETRUNC\s*\(\s*[\'"]?quarter[\'"]?\s*,', 'STARTOFQUARTER('),
    (r'\bDATETRUNC\s*\(\s*[\'"]?month[\'"]?\s*,', 'STARTOFMONTH('),

    # Date functions — DATEPART
    (r'\bDATEPART\s*\(\s*[\'"]?year[\'"]?\s*,\s*', 'YEAR('),
    (r'\bDATEPART\s*\(\s*[\'"]?quarter[\'"]?\s*,\s*', 'QUARTER('),
    (r'\bDATEPART\s*\(\s*[\'"]?month[\'"]?\s*,\s*', 'MONTH('),
    (r'\bDATEPART\s*\(\s*[\'"]?day[\'"]?\s*,\s*', 'DAY('),
    (r'\bDATEPART\s*\(\s*[\'"]?hour[\'"]?\s*,\s*', 'HOUR('),
    (r'\bDATEPART\s*\(\s*[\'"]?minute[\'"]?\s*,\s*', 'MINUTE('),
    (r'\bDATEPART\s*\(\s*[\'"]?second[\'"]?\s*,\s*', 'SECOND('),
    (r'\bDATEPART\s*\(\s*[\'"]?week[\'"]?\s*,\s*', 'WEEKNUM('),
    (r'\bDATEPART\s*\(\s*[\'"]?weekday[\'"]?\s*,\s*', 'WEEKDAY('),

    # Date functions — misc
    # DATEADD handled by _convert_dateadd (scalar: EDATE/arithmetic)
    (r'\bTODAY\s*\(\s*\)', 'TODAY()'),
    (r'\bNOW\s*\(\s*\)', 'NOW()'),
    # DATENAME handled by _convert_datename (needs format string arg)
    # DATEPARSE handled by _convert_dateparse (needs value extraction)
    (r'\bMAKEDATE\s*\(', 'DATE('),
    (r'\bMAKEDATETIME\s*\(', 'DATE('),
    (r'\bMAKETIME\s*\(', 'TIME('),

    # Text functions
    (r'\bTRIM\s*\(', 'TRIM('),
    # LTRIM/RTRIM handled by dedicated converters (_convert_ltrim, _convert_rtrim)
    (r'\bLEN\s*\(', 'LEN('),
    (r'\bLEFT\s*\(', 'LEFT('),
    (r'\bRIGHT\s*\(', 'RIGHT('),
    (r'\bMID\s*\(', 'MID('),
    (r'\bUPPER\s*\(', 'UPPER('),
    (r'\bLOWER\s*\(', 'LOWER('),
    (r'\bREPLACE\s*\(', 'SUBSTITUTE('),
    (r'\bSPACE\s*\(', 'REPT(" ", '),
    (r'\bREPEAT\s*\(', 'REPT('),
    # REVERSE handled by _convert_reverse (no direct DAX equivalent)
    # FIND/FINDNTH handled by _convert_find (arg order swap needed)
    # ENDSWITH handled by _convert_endswith (needs decomposition)
    # STARTSWITH handled by _convert_startswith (needs decomposition)
    # PROPER handled by _convert_proper (no direct DAX equivalent)
    # SPLIT handled by _convert_split (no direct DAX equivalent)

    # Math functions
    (r'\bABS\s*\(', 'ABS('),
    (r'\bCEILING\s*\(', 'CEILING('),
    (r'\bFLOOR\s*\(', 'FLOOR('),
    (r'\bROUND\s*\(', 'ROUND('),
    (r'\bPOWER\s*\(', 'POWER('),
    (r'\bSQRT\s*\(', 'SQRT('),
    (r'\bLOG\s*\(', 'LOG('),
    (r'\bLN\s*\(', 'LN('),
    (r'\bEXP\s*\(', 'EXP('),
    (r'\bSIGN\s*\(', 'SIGN('),
    (r'\bPI\s*\(\s*\)', 'PI()'),
    # RADIANS/DEGREES handled by _convert_radians_degrees (no DAX equivalent)
    (r'\bSIN\s*\(', 'SIN('),
    (r'\bCOS\s*\(', 'COS('),
    (r'\bTAN\s*\(', 'TAN('),
    (r'\bACOS\s*\(', 'ACOS('),
    (r'\bASIN\s*\(', 'ASIN('),
    (r'\bATAN\s*\(', 'ATAN('),
    (r'\bCOT\s*\(', 'COT('),
    # ATAN2 handled by _convert_atan2 (two-arg → DAX formula)
    # DIV handled by _convert_div (→ QUOTIENT)

    # Statistical functions
    (r'\bMEDIAN\s*\(', 'MEDIAN('),
    (r'\bSTDEVP\s*\(', 'STDEV.P('),  # STDEVP before STDEV
    (r'\bSTDEV\s*\(', 'STDEV.S('),
    (r'\bVARP\s*\(', 'VAR.P('),      # VARP before VAR
    (r'\bVAR\s*\(', 'VAR.S('),
    (r'\bPERCENTILE\s*\(', 'PERCENTILE.INC('),
    # CORR/COVAR/COVARP handled by _convert_corr_covar (no direct DAX equivalent)

    # Type conversions
    (r'\bINT\s*\(', 'INT('),
    # FLOAT handled by _convert_float_to_convert (needs DOUBLE type arg)
    # STR handled by _convert_str_to_format (needs format string arg)
    (r'\bDATE\s*\(', 'DATE('),
    (r'\bDATETIME\s*\(', 'DATE('),

    # Aggregation (generic)
    (r'\bSUM\s*\(', 'SUM('),
    (r'\bMIN\s*\(', 'MIN('),
    (r'\bMAX\s*\(', 'MAX('),
    (r'\bCOUNT\s*\(', 'COUNT('),
    (r'\bCOUNTA\s*\(', 'COUNTA('),

    # Regex — REGEXP_MATCH, REGEXP_EXTRACT, REGEXP_EXTRACT_NTH, and REGEXP_REPLACE
    # are handled by dedicated converters called in Phase 3b-pre.

    # Spatial functions — MAKEPOINT maps to lat/long column pair hint
    (r'\bMAKEPOINT\s*\(', '/* MAKEPOINT → use Latitude/Longitude columns in map visual */ BLANK( /*'),
    (r'\bMAKELINE\s*\(', '/* MAKELINE: use line-layer in map visual */ BLANK( /*'),
    (r'\bDISTANCE\s*\(', '/* DISTANCE: compute via Haversine or external tool */ 0 + ( /*'),
    (r'\bBUFFER\s*\(', '/* BUFFER: no DAX spatial equivalent */ BLANK( /*'),
    (r'\bAREA\s*\(', '/* AREA: no DAX spatial equivalent */ 0 + ( /*'),
    (r'\bINTERSECTION\s*\(', '/* INTERSECTION: no DAX spatial equivalent */ BLANK( /*'),
    (r'\bHEXBINX\s*\(', '/* HEXBINX: no DAX equivalent */ 0 + ( /*'),
    (r'\bHEXBINY\s*\(', '/* HEXBINY: no DAX equivalent */ 0 + ( /*'),

    # Table calculations — RUNNING_*/TOTAL handled by dedicated converters (_convert_running_functions, _convert_total_function)
    # RANK/RANK_UNIQUE/RANK_DENSE/RANK_MODIFIED/RANK_PERCENTILE handled by _convert_rank_functions
    # INDEX handled by dedicated converter (_convert_index)
    (r'\bFIRST\s*\(\s*\)', '/* FIRST(): rows from first row — use ORDERBY column */ -(RANKX(ALLSELECTED(), [__SortColumn__], , ASC, DENSE) - 1)'),
    (r'\bLAST\s*\(\s*\)', '/* LAST(): rows to last row — use ORDERBY column */ COUNTROWS(ALLSELECTED()) - RANKX(ALLSELECTED(), [__SortColumn__], , ASC, DENSE)'),
    # PREVIOUS_VALUE and LOOKUP handled by dedicated converters below
    (r'\bSIZE\s*\(\s*\)', 'COUNTROWS(ALLSELECTED()) /* SIZE: partition row count */'),

    # WINDOW_* table calculations handled by _convert_window_functions (SUM/AVG/MAX/MIN/COUNT/MEDIAN/STDEV/VAR/PERCENTILE)
    # WINDOW_CORR/COVAR/COVARP also handled by dedicated converter in _convert_window_functions

    # Script/Analytics Extensions (no DAX equivalent)
    (r'\bSCRIPT_BOOL\s*\(', '/* SCRIPT_BOOL: analytics extension — manual conversion needed */ BLANK( /*'),
    (r'\bSCRIPT_INT\s*\(', '/* SCRIPT_INT: analytics extension — manual conversion needed */ 0 + ( /*'),
    (r'\bSCRIPT_REAL\s*\(', '/* SCRIPT_REAL: analytics extension — manual conversion needed */ 0 + ( /*'),
    (r'\bSCRIPT_STR\s*\(', '/* SCRIPT_STR: analytics extension — manual conversion needed */ "" & ( /*'),

    # COLLECT (spatial aggregate — no DAX equivalent)
    (r'\bCOLLECT\s*\(', '/* COLLECT: spatial aggregate — no DAX equivalent */ BLANK( /*'),
]

# Pre-compile all patterns for performance
_COMPILED_FUNCTION_MAP = [(re.compile(pattern, re.IGNORECASE), replacement)
                           for pattern, replacement in _SIMPLE_FUNCTION_MAP]

# Pre-compiled static patterns used in the main converter and dedicated converters
_RE_ISMEMBEROF = re.compile(
    r'\bISMEMBEROF\s*\(\s*["\']([^"\']+)["\']\s*\)',
    re.IGNORECASE
)
_RE_OR = re.compile(r'\bor\b', re.IGNORECASE)
_RE_AND = re.compile(r'\band\b', re.IGNORECASE)
_RE_NEWLINES = re.compile(r'[\r\n]+\s*')
_RE_PARAM_REF = re.compile(r'\[Parameters\]\.\[([^\]]+)\]')
_RE_CALC_REF = re.compile(r'\[([^\]]+)\]')
_RE_ELSEIF = re.compile(r'\bELSEIF\b', re.IGNORECASE)
_RE_FINDNTH = re.compile(r'\bFINDNTH\s*\(', re.IGNORECASE)
_RE_DATE_LITERAL = re.compile(r'#(\d{4})-(\d{2})-(\d{2})#')
_RE_COLUMN_RESOLVE = re.compile(r"(?<!')\[([^\]]+)\]")
_RE_PREVIOUS_VALUE = re.compile(r'\bPREVIOUS_VALUE\s*\(', re.IGNORECASE)
_RE_LOOKUP = re.compile(r'\bLOOKUP\s*\(', re.IGNORECASE)
_RE_FIND = re.compile(r'\bFIND\s*\(', re.IGNORECASE)
_RE_TOTAL = re.compile(r'\bTOTAL\s*\(', re.IGNORECASE)
_RE_LOD_NO_DIM = re.compile(
    r'\{\s*(SUM|AVG|AVERAGE|MIN|MAX|COUNT|COUNTD|MEDIAN)\s*\(',
    re.IGNORECASE
)

# Pattern cache for dynamic function-name-based patterns
_func_pattern_cache = {}


def _get_func_pattern(func_name, word_boundary=True):
    """Retrieve or create a compiled regex for matching ``func_name(``."""
    key = (func_name, word_boundary)
    pat = _func_pattern_cache.get(key)
    if pat is None:
        prefix = r'\b' + re.escape(func_name) if word_boundary else re.escape(func_name)
        pat = re.compile(prefix + r'\s*\(', re.IGNORECASE)
        _func_pattern_cache[key] = pat
    return pat


# ── Type mapping ──────────────────────────────────────────────────────────────

TABLEAU_TO_PBI_TYPE = {
    'string': 'String',
    'integer': 'Int64',
    'real': 'Double',
    'boolean': 'Boolean',
    'date': 'DateTime',
    'datetime': 'DateTime',
    'number': 'Double',
}


def map_tableau_to_powerbi_type(tableau_type):
    """Maps Tableau types to Power BI types."""
    return TABLEAU_TO_PBI_TYPE.get(tableau_type.lower(), 'String')


# ── Main converter ────────────────────────────────────────────────────────────

def convert_tableau_formula_to_dax(formula, column_name='Measure', table_name='Table',
                                    calc_map=None, param_map=None,
                                    column_table_map=None, measure_names=None,
                                    is_calc_column=False, param_values=None,
                                    calc_datatype=None, partition_fields=None,
                                    compute_using=None, table_columns=None,
                                    bool_columns=None):
    """
    Converts a Tableau formula to DAX with context resolution.
    
    Args:
        formula: Raw Tableau formula
        column_name: Name of the calculated field (for debug)
        table_name: Name of the table containing this measure (fallback)
        calc_map: {raw_id: caption} to resolve references between calculations
        param_map: {raw_param_id: caption} to resolve parameters
        column_table_map: {column: table} to resolve cross-table columns
        measure_names: set of measure names (do NOT receive a table prefix)
        is_calc_column: True if the formula is for a calculated column (row-level)
        param_values: {parameter_caption: literal_value} to inline in calc columns
        calc_datatype: Tableau type ('string', 'real', etc.) for + → & conversion
        partition_fields: List of field names for table calc partitioning (COMPUTE USING)
            (deprecated — use compute_using instead)
        compute_using: list of dimension names for table calc addressing/partitioning
    
    Returns:
        str: Valid DAX formula
    """
    if not formula or not formula.strip():
        return formula
    
    calc_map = calc_map or {}
    param_map = param_map or {}
    column_table_map = column_table_map or {}
    measure_names = measure_names or set()
    param_values = param_values or {}
    # Support both old partition_fields and new compute_using parameter
    if compute_using is None and partition_fields is not None:
        compute_using = partition_fields
    
    dax = formula.strip()
    
    # === Phase 0: Strip federated datasource prefixes ===
    # Tableau data blends use [federated.xxxID].[Column] references.
    # Strip the federated prefix so the column resolves normally.
    dax = re.sub(r'\[federated\.[^\]]*\]\.', '', dax)
    
    # === Phase 1: Resolve Tableau references ===
    dax = _resolve_references(dax, calc_map, param_map, is_calc_column, param_values)
    
    # === Phase 2: Convert CASE/WHEN → SWITCH(), IF/THEN → IF() ===
    dax = _convert_case_structure(dax)
    dax = _convert_if_structure(dax)
    
    # === Phase 3: Convert Tableau functions → DAX ===
    
    # 3a. ISMEMBEROF (special — captures group name)
    dax = _RE_ISMEMBEROF.sub(
        r'TRUE()  /* ISMEMBEROF("\1"): implement via RLS role */',
        dax
    )
    
    # 3b-pre. Dedicated converters (functions needing special arg handling)
    dax = _convert_previous_value(dax, table_name, compute_using=compute_using,
                                   column_table_map=column_table_map)
    dax = _convert_lookup(dax, table_name, compute_using=compute_using,
                           column_table_map=column_table_map)
    dax = _convert_radians_degrees(dax)
    dax = _convert_find(dax)
    dax = _convert_str_to_format(dax)
    dax = _convert_float_to_convert(dax)
    dax = _convert_datename(dax)
    dax = _convert_dateadd(dax)
    dax = _convert_dateparse(dax)
    dax = _convert_isdate(dax)
    dax = _convert_corr_covar(dax, table_name)
    dax = _convert_endswith(dax)
    dax = _convert_startswith(dax)
    dax = _convert_proper(dax)
    dax = _convert_reverse(dax)
    dax = _convert_split(dax)
    dax = _convert_ltrim(dax)
    dax = _convert_rtrim(dax)
    dax = _convert_index(dax)
    dax = _convert_atan2(dax)
    dax = _convert_div(dax)
    dax = _convert_square(dax)
    dax = _convert_iif(dax)
    dax = _convert_regexp_match(dax)
    dax = _convert_regexp_extract(dax)
    dax = _convert_regexp_extract_nth(dax)
    dax = _convert_regexp_replace(dax)
    dax = _convert_attr(dax, measure_names)

    # 3b. Apply all simple function mappings (table-driven)
    for compiled_pattern, replacement in _COMPILED_FUNCTION_MAP:
        dax = compiled_pattern.sub(replacement, dax)

    # 3b-post. Fix functions needing additional arguments
    dax = _fix_ceiling_floor(dax)

    # 3c. Special functions requiring argument reordering
    dax = _convert_datediff(dax)
    dax = _convert_zn(dax)
    dax = _convert_ifnull(dax)
    
    # 3d. LOD Expressions → CALCULATE
    dax = _convert_lod_expressions(dax, table_name, column_table_map)
    
    # 3e. WINDOW_xxx table calculations
    dax = _convert_window_functions(dax, table_name, compute_using=compute_using,
                                     column_table_map=column_table_map,
                                     partition_fields=partition_fields)
    
    # 3f. RANK / RANK_UNIQUE / RANK_DENSE → RANKX
    dax = _convert_rank_functions(dax, table_name, compute_using=compute_using,
                                   column_table_map=column_table_map)
    
    # 3g. RUNNING_SUM/AVG/COUNT/MAX/MIN → table calculations
    dax = _convert_running_functions(dax, table_name)
    
    # 3h. Percent of Total (TOTAL function or pcto: prefix)
    dax = _convert_total_function(dax, table_name)
    
    # === Phase 4: Convert operators ===
    dax = dax.replace('!=', '<>')   # != before == to avoid partial match
    dax = dax.replace('==', '=')
    dax = _RE_OR.sub('||', dax)
    dax = _RE_AND.sub('&&', dax)
    
    # === Phase 5: Resolve remaining columns [col] → 'Table'[col] ===
    dax = _resolve_columns(dax, table_name, column_table_map, measure_names,
                           is_calc_column, param_values, table_columns=table_columns)

    # === Phase 5a: Fix STARTOF* for calculated columns ===
    if is_calc_column:
        dax = _fix_startof_calc_columns(dax)

    # === Phase 5b: Convert AGG(IF(...)) → AGGX('table', IF(...)) ===
    dax = _convert_agg_if_to_aggx(dax, table_name)
    
    # === Phase 5c: Convert AGG(multi-col expr) → AGGX('table', expr) ===
    # DAX SUM/AVERAGE/MIN/MAX/COUNT only accept a single column.
    # Expressions like SUM('T'[a] * 'T'[b]) must use SUMX('T', 'T'[a] * 'T'[b]).
    dax = _convert_agg_expr_to_aggx(dax, table_name)

    # === Phase 5d: String concatenation + → & ===
    if calc_datatype and calc_datatype.lower() in ('string', 'str'):
        dax = _convert_string_concat(dax)

    # === Phase 5e: Tableau single-quoted string literals → DAX double-quoted ===
    dax = _convert_single_quoted_strings(dax)

    # === Phase 5f: Fix ROUND with single argument → ROUND(x, 0) ===
    dax = _fix_round_single_arg(dax)

    # === Phase 5g: Fix double-quoted table names → single-quoted ===
    # _convert_single_quoted_strings may incorrectly convert table names
    # in complex DAX (e.g. FILTER("Table",...) or "Table"[Col]).
    # Fix "Table"[Col] → 'Table'[Col] and FUNC("Table", → FUNC('Table',
    dax = _fix_double_quoted_table_refs(dax)

    # === Phase 5h: Wrap bare column refs in measures with MAX() ===
    # In measure context, bare 'Table'[Col] references (not inside an
    # aggregation/iterator) cause PBI "single value cannot be determined".
    # Wrap them in MAX() — safe for LOD-derived calc columns.
    if not is_calc_column and table_columns:
        dax = _wrap_bare_column_refs_in_measure(dax, table_name,
                                                 table_columns, measure_names,
                                                 bool_columns=bool_columns)

    # === Phase 6: Final cleanup ===
    dax = _normalize_spaces_outside_identifiers(dax).strip()
    # Strip // line comments before collapsing newlines — otherwise
    # the comment swallows the rest of the single-line DAX/M expression.
    dax = re.sub(r'(?m)^\s*//[^\r\n]*', '', dax)
    dax = _RE_NEWLINES.sub(' ', dax)

    # === Phase 6b: Fix date literals ===
    dax = _fix_date_literals(dax)

    return dax


# ── Phase 1: Reference resolution ────────────────────────────────────────────

def _resolve_references(dax, calc_map, param_map, is_calc_column, param_values):
    """Resolve [Parameters].[X] and [Calculation_xxx] references."""
    
    # [Parameters].[Parameter X] → [caption] or inline value
    def resolve_param(m):
        param_id = m.group(1)
        caption = param_map.get(param_id, param_id)
        if is_calc_column and caption in param_values:
            return param_values[caption]
        return f'[{caption}]'
    dax = _RE_PARAM_REF.sub(resolve_param, dax)
    
    # [Calculation_xxx] → [caption]
    def resolve_calc(m):
        ref = m.group(1)
        if ref in calc_map:
            return f'[{calc_map[ref]}]'
        return m.group(0)
    dax = _RE_CALC_REF.sub(resolve_calc, dax)

    # Bare (unbracketed) references to literal-value calculations.
    # Tableau occasionally uses calc names without brackets
    # (e.g. __MyToday instead of [__MyToday]).  DAX requires brackets
    # for identifiers.  Since param_values entries are literal constants
    # (numbers, DATE(), strings), inlining is always safe and avoids
    # classification mismatches (e.g. dimension-role calcs not in
    # measure_names).
    if param_values:
        for pname in sorted(param_values, key=len, reverse=True):
            if pname not in dax:
                continue
            repl = param_values[pname]
            # Process outside string literals to avoid false matches
            parts = re.split(r'("(?:[^"\\]|\\.)*")', dax)
            for i in range(0, len(parts), 2):
                parts[i] = re.sub(
                    r'(?<!\[)\b' + re.escape(pname) + r'\b(?!\])',
                    repl, parts[i]
                )
            dax = ''.join(parts)

    return dax


# ── Phase 2: IF and CASE structure conversion ────────────────────────────────

def _convert_case_structure(text):
    """
    Converts Tableau CASE/WHEN/THEN/ELSE/END structures to DAX SWITCH().
    
    Tableau: CASE [field] WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 0 END
    DAX:     SWITCH([field], "A", 1, "B", 2, 0)
    """
    max_iter = 20
    for _ in range(max_iter):
        m = re.search(
            r'\bCASE\s+((?:(?!\bCASE\b|\bEND\b).)*?)\s+WHEN\s+((?:(?!\bCASE\b|\bEND\b).)*?)\s+END\b',
            text, re.IGNORECASE | re.DOTALL
        )
        if not m:
            break
        
        expr = m.group(1).strip()
        when_block = m.group(2).strip()
        
        # Parse WHEN value THEN result pairs
        parts = re.split(r'\bWHEN\b', when_block, flags=re.IGNORECASE)
        switch_args = [expr]
        else_val = None
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Check for ELSE clause
            else_match = re.search(r'\bELSE\s+(.*)', part, re.IGNORECASE | re.DOTALL)
            if else_match:
                # Split off the ELSE
                before_else = part[:else_match.start()].strip()
                else_val = else_match.group(1).strip()
                part = before_else
            
            # Parse THEN
            then_match = re.search(r'\bTHEN\b', part, re.IGNORECASE)
            if then_match:
                when_val = part[:then_match.start()].strip()
                then_val = part[then_match.end():].strip()
                switch_args.append(when_val)
                switch_args.append(then_val)
        
        if else_val:
            switch_args.append(else_val)
        
        replacement = f'SWITCH({", ".join(switch_args)})'
        text = text[:m.start()] + replacement + text[m.end():]
    
    return text


def _convert_if_structure(text):
    """
    Converts Tableau IF/THEN/ELSEIF/ELSE/END structures to DAX IF().
    
    Handles nested structures (processed from innermost to outermost).
    """
    # Pre-processing: ELSEIF → ELSE IF + add corresponding ENDs
    elseif_count = len(re.findall(r'\bELSEIF\b', text, re.IGNORECASE))
    if elseif_count > 0:
        text = _RE_ELSEIF.sub('ELSE IF', text)
        text = text.rstrip() + ' END' * elseif_count
    
    max_iter = 30
    for _ in range(max_iter):
        # IF cond THEN val ELSE val2 END (innermost)
        m = re.search(
            r'\bIF\s+((?:(?!\bIF\s|\bEND\b).)*?)\s+THEN\s+((?:(?!\bIF\s|\bEND\b).)*?)\s+ELSE\s+((?:(?!\bIF\s|\bEND\b).)*?)\s+END\b',
            text, re.IGNORECASE | re.DOTALL
        )
        if m:
            cond, val1, val2 = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            text = text[:m.start()] + f'IF({cond}, {val1}, {val2})' + text[m.end():]
            continue
        
        # IF cond THEN val END (no ELSE)
        m = re.search(
            r'\bIF\s+((?:(?!\bIF\s|\bEND\b).)*?)\s+THEN\s+((?:(?!\bIF\s|\bEND\b).)*?)\s+END\b',
            text, re.IGNORECASE | re.DOTALL
        )
        if m:
            cond, val1 = m.group(1).strip(), m.group(2).strip()
            text = text[:m.start()] + f'IF({cond}, {val1}, BLANK())' + text[m.end():]
            continue
        
        break
    
    return text


# ── Phase 3 helpers ───────────────────────────────────────────────────────────

def _convert_datediff(dax_str):
    """DATEDIFF('interval', start, end) → DATEDIFF(start, end, INTERVAL)"""
    pattern = r'\bDATEDIFF\s*\('
    result = []
    last_end = 0
    for m_dd in re.finditer(pattern, dax_str, re.IGNORECASE):
        pos = m_dd.end()
        depth = 1
        i = pos
        while i < len(dax_str) and depth > 0:
            if dax_str[i] == '(':
                depth += 1
            elif dax_str[i] == ')':
                depth -= 1
            i += 1
        if depth != 0:
            continue
        inner = dax_str[pos:i - 1]
        args = _split_args(inner)
        if len(args) == 3:
            interval = args[0].strip().strip("'\"").upper()
            replacement = f"DATEDIFF({args[1]}, {args[2]}, {interval})"
        else:
            replacement = dax_str[m_dd.start():i]
        result.append(dax_str[last_end:m_dd.start()])
        result.append(replacement)
        last_end = i
    result.append(dax_str[last_end:])
    return ''.join(result)


def _convert_dateadd(dax_str):
    """DATEADD('date_part', interval, date) → scalar date arithmetic.

    Tableau DATEADD is a **scalar** function: DATEADD(date_part, interval, date).
    DAX DATEADD is a **Time Intelligence TABLE** function that requires a date
    column from a marked date table — completely different semantics.

    Convert to scalar DAX equivalents:
      - MONTH  → EDATE(date, n)
      - YEAR   → EDATE(date, n * 12)
      - QUARTER→ EDATE(date, n * 3)
      - DAY    → date + n
      - WEEK   → date + n * 7
      - HOUR   → date + n / 24
      - MINUTE → date + n / 1440
      - SECOND → date + n / 86400
    """
    def _xf(args, inner):
        if len(args) == 3:
            interval_unit = args[0].strip().strip("'\"").upper()
            number = args[1].strip()
            date_expr = args[2].strip()
            if interval_unit == 'MONTH':
                return f"EDATE({date_expr}, {number})"
            elif interval_unit == 'YEAR':
                return f"EDATE({date_expr}, ({number}) * 12)"
            elif interval_unit == 'QUARTER':
                return f"EDATE({date_expr}, ({number}) * 3)"
            elif interval_unit == 'DAY':
                return f"({date_expr} + {number})"
            elif interval_unit == 'WEEK':
                return f"({date_expr} + ({number}) * 7)"
            elif interval_unit == 'HOUR':
                return f"({date_expr} + ({number}) / 24)"
            elif interval_unit == 'MINUTE':
                return f"({date_expr} + ({number}) / 1440)"
            elif interval_unit == 'SECOND':
                return f"({date_expr} + ({number}) / 86400)"
            else:
                return f"EDATE({date_expr}, {number})"
        return f"DATEADD({inner})"
    return _transform_func_call(dax_str, 'DATEADD', _xf)


def _extract_balanced_call(dax, func_name):
    """Find a balanced-paren function call and return (start, end, inner_text).

    Returns a list of (start, end, inner) tuples for every occurrence.
    Uses depth-tracking to handle nested parentheses correctly.
    """
    results = []
    pattern = _get_func_pattern(func_name)
    offset = 0
    while True:
        match = pattern.search(dax, offset)
        if not match:
            break
        start_pos = match.end()
        depth = 1
        i = start_pos
        while i < len(dax) and depth > 0:
            if dax[i] == '(':
                depth += 1
            elif dax[i] == ')':
                depth -= 1
            i += 1
        if depth != 0:
            break
        inner = dax[start_pos:i - 1]
        results.append((match.start(), i, inner))
        offset = i
    return results


def _convert_zn(dax):
    """ZN(expr) → IF(ISBLANK(expr), 0, expr)"""
    for start, end, inner in reversed(_extract_balanced_call(dax, 'ZN')):
        replacement = f'IF(ISBLANK({inner}), 0, {inner})'
        dax = dax[:start] + replacement + dax[end:]
    return dax


def _convert_ifnull(dax):
    """IFNULL(a, b) → IF(ISBLANK(a), b, a)"""
    for start, end, inner in reversed(_extract_balanced_call(dax, 'IFNULL')):
        parts = _split_args(inner)
        if len(parts) == 2:
            replacement = f'IF(ISBLANK({parts[0].strip()}), {parts[1].strip()}, {parts[0].strip()})'
        else:
            replacement = dax[start:end]
        dax = dax[:start] + replacement + dax[end:]
    return dax


def _convert_previous_value(dax, table_name, compute_using=None, column_table_map=None):
    """Convert PREVIOUS_VALUE(seed) → OFFSET-based DAX.

    Output:
        VAR __prev = CALCULATE([inner], OFFSET(-1, ALLSELECTED('Table'), ORDERBY([dim]), PARTITIONBY([dim2])))
        RETURN IF(ISBLANK(__prev), <seed>, __prev)

    When compute_using is present, first dimension → ORDERBY, remaining → PARTITIONBY.
    """
    column_table_map = column_table_map or {}
    pattern = _RE_PREVIOUS_VALUE
    match = pattern.search(dax)
    while match:
        start_pos = match.end()
        depth = 1
        i = start_pos
        while i < len(dax) and depth > 0:
            if dax[i] == '(':
                depth += 1
            elif dax[i] == ')':
                depth -= 1
            i += 1
        if depth == 0:
            inner = dax[start_pos:i - 1].strip()
            seed = inner if inner else '0'
            if compute_using:
                order_col = compute_using[0]
                order_table = column_table_map.get(order_col, table_name)
                orderby = f"ORDERBY('{order_table}'[{order_col}])"
                # Additional dims → PARTITIONBY
                partition_clause = ""
                if len(compute_using) > 1:
                    parts = []
                    for dim in compute_using[1:]:
                        t = column_table_map.get(dim, table_name)
                        parts.append(f"'{t}'[{dim}]")
                    partition_clause = f", PARTITIONBY({', '.join(parts)})"
            else:
                orderby = "ORDERBY([Value])"
                partition_clause = ""
            replacement = (
                f"VAR __prev = CALCULATE({seed}, "
                f"OFFSET(-1, ALLSELECTED('{table_name}'), {orderby}{partition_clause})) "
                f"RETURN IF(ISBLANK(__prev), {seed}, __prev)"
            )
            dax = dax[:match.start()] + replacement + dax[i:]
        match = pattern.search(dax, match.start() + 1 if depth != 0 else 0)
    return dax


def _convert_lookup(dax, table_name, compute_using=None, column_table_map=None):
    """Convert LOOKUP(expr, offset) → OFFSET-based DAX.

    Output:
        CALCULATE(<expr>, OFFSET(<offset>, ALLSELECTED('Table'), ORDERBY([dim]), PARTITIONBY([dim2])))

    When compute_using has 2+ dims, first → ORDERBY, rest → PARTITIONBY.
    """
    column_table_map = column_table_map or {}
    pattern = _RE_LOOKUP
    match = pattern.search(dax)
    while match:
        start_pos = match.end()
        depth = 1
        i = start_pos
        while i < len(dax) and depth > 0:
            if dax[i] == '(':
                depth += 1
            elif dax[i] == ')':
                depth -= 1
            i += 1
        if depth == 0:
            inner = dax[start_pos:i - 1].strip()
            args = _split_args(inner)
            expr = args[0].strip() if args else 'BLANK()'
            offset = args[1].strip() if len(args) > 1 else '0'
            if compute_using:
                order_col = compute_using[0]
                order_table = column_table_map.get(order_col, table_name)
                orderby = f"ORDERBY('{order_table}'[{order_col}])"
                partition_clause = ""
                if len(compute_using) > 1:
                    parts = []
                    for dim in compute_using[1:]:
                        t = column_table_map.get(dim, table_name)
                        parts.append(f"'{t}'[{dim}]")
                    partition_clause = f", PARTITIONBY({', '.join(parts)})"
            else:
                orderby = "ORDERBY([Value])"
                partition_clause = ""
            replacement = (
                f"CALCULATE({expr}, "
                f"OFFSET({offset}, ALLSELECTED('{table_name}'), {orderby}{partition_clause}))"
            )
            dax = dax[:match.start()] + replacement + dax[i:]
        match = pattern.search(dax, match.start() + 1 if depth != 0 else 0)
    return dax


def _convert_radians_degrees(dax):
    """RADIANS(x) → ((x)*PI()/180), DEGREES(x) → ((x)*180/PI())."""
    for func, template in [('RADIANS', '(({inner})*PI()/180)'),
                           ('DEGREES', '(({inner})*180/PI())')]:
        dax = _transform_func_call(dax, func,
                                   lambda args, inner, _t=template: _t.format(inner=inner.strip()))
    return dax


def _convert_find(dax):
    """Swap FIND args: Tableau FIND(string, substring) → DAX FIND(substring, string).

    Also converts FINDNTH → FIND.
    Tableau: FIND(within_text, find_text[, start])
    DAX:     FIND(find_text, within_text[, start[, not_found]])
    """
    dax = _RE_FINDNTH.sub('FIND(', dax)
    pattern = _RE_FIND
    match = pattern.search(dax)
    while match:
        start_pos = match.end()
        depth = 1
        i = start_pos
        while i < len(dax) and depth > 0:
            if dax[i] == '(':
                depth += 1
            elif dax[i] == ')':
                depth -= 1
            i += 1
        if depth != 0:
            break
        inner = dax[start_pos:i - 1]
        args = _split_args(inner)
        if len(args) >= 2:
            swapped = [args[1].strip(), args[0].strip()] + [a.strip() for a in args[2:]]
            replacement = f"FIND({', '.join(swapped)})"
        else:
            replacement = dax[match.start():i]
        dax = dax[:match.start()] + replacement + dax[i:]
        match = pattern.search(dax, match.start() + len(replacement))
    return dax


def _convert_str_to_format(dax):
    """STR(expr) → FORMAT(expr, "0")"""
    return _transform_func_call(dax, 'STR', lambda args, inner: f'FORMAT({inner.strip()}, "0")')


def _convert_float_to_convert(dax):
    """FLOAT(expr) → CONVERT(expr, DOUBLE)"""
    return _transform_func_call(dax, 'FLOAT', lambda args, inner: f'CONVERT({inner.strip()}, DOUBLE)')


def _convert_datename(dax):
    """DATENAME(part, date) → FORMAT(date, format_string)"""
    _DATENAME_FORMATS = {
        'year': '"YYYY"', 'quarter': '"Q"', 'month': '"MMMM"',
        'day': '"D"', 'weekday': '"DDDD"', 'dayofweek': '"DDDD"',
    }
    def _xf(args, inner):
        if len(args) >= 2:
            part = args[0].strip().strip("'\"" ).lower()
            fmt = _DATENAME_FORMATS.get(part, '"MMMM"')
            return f'FORMAT({args[1].strip()}, {fmt})'
        return f'DATENAME({inner})'
    return _transform_func_call(dax, 'DATENAME', _xf)


def _convert_corr_covar(dax, table_name='Table'):
    """Convert CORR/COVAR/COVARP to proper DAX using VAR/iterator patterns.

    CORR(x, y) → Pearson correlation using VAR + SUMX pattern
    COVAR(x, y) → sample covariance using VAR + SUMX pattern
    COVARP(x, y) → population covariance using VAR + SUMX pattern
    """
    for tab_func in ['CORR', 'COVARP', 'COVAR']:
        pattern = _get_func_pattern(tab_func)
        match = pattern.search(dax)
        while match:
            start_pos = match.end()
            depth = 1
            i = start_pos
            while i < len(dax) and depth > 0:
                if dax[i] == '(':
                    depth += 1
                elif dax[i] == ')':
                    depth -= 1
                i += 1
            if depth == 0:
                inner = dax[start_pos:i - 1]
                # Split arguments (x, y)
                args = _split_args(inner)
                if len(args) >= 2:
                    x_expr = args[0].strip()
                    y_expr = args[1].strip()
                    replacement = _build_corr_covar_dax(tab_func.upper(), x_expr, y_expr, table_name)
                else:
                    # Fallback if can't parse args
                    replacement = f'0 /* {tab_func}({inner}): could not parse arguments */'
                dax = dax[:match.start()] + replacement + dax[i:]
                match = pattern.search(dax, match.start() + len(replacement))
            else:
                break
    return dax


def _build_corr_covar_dax(func_name, x_expr, y_expr, table_name='Table'):
    """Build DAX expression for correlation/covariance using VAR/iterator pattern.

    Uses SUMX over ALL() rows with deviation-from-mean calculations.
    The table_name parameter specifies which table to iterate over.
    """
    tbl = table_name.replace("'", "''")
    if func_name == 'CORR':
        # Pearson correlation: Σ((x-μx)(y-μy)) / √(Σ(x-μx)² × Σ(y-μy)²)
        return (
            f"VAR _MeanX = AVERAGEX(ALL('{tbl}'), {x_expr}) "
            f"VAR _MeanY = AVERAGEX(ALL('{tbl}'), {y_expr}) "
            f"VAR _Cov = SUMX(ALL('{tbl}'), ({x_expr} - _MeanX) * ({y_expr} - _MeanY)) "
            f"VAR _StdX = SQRT(SUMX(ALL('{tbl}'), ({x_expr} - _MeanX) ^ 2)) "
            f"VAR _StdY = SQRT(SUMX(ALL('{tbl}'), ({y_expr} - _MeanY) ^ 2)) "
            f'RETURN DIVIDE(_Cov, _StdX * _StdY, 0)'
        )
    elif func_name == 'COVARP':
        # Population covariance: Σ((x-μx)(y-μy)) / N
        return (
            f"VAR _MeanX = AVERAGEX(ALL('{tbl}'), {x_expr}) "
            f"VAR _MeanY = AVERAGEX(ALL('{tbl}'), {y_expr}) "
            f"VAR _N = COUNTROWS(ALL('{tbl}')) "
            f"RETURN DIVIDE(SUMX(ALL('{tbl}'), ({x_expr} - _MeanX) * ({y_expr} - _MeanY)), _N, 0)"
        )
    else:  # COVAR — sample covariance
        # Sample covariance: Σ((x-μx)(y-μy)) / (N-1)
        return (
            f"VAR _MeanX = AVERAGEX(ALL('{tbl}'), {x_expr}) "
            f"VAR _MeanY = AVERAGEX(ALL('{tbl}'), {y_expr}) "
            f"VAR _N = COUNTROWS(ALL('{tbl}')) "
            f"RETURN DIVIDE(SUMX(ALL('{tbl}'), ({x_expr} - _MeanX) * ({y_expr} - _MeanY)), _N - 1, 0)"
        )


# ── Generic function-call transformer ─────────────────────────────────────────

def _transform_func_call(dax, func_name, transformer_fn):
    """Generic: find func_name(...), extract balanced args, apply transformer_fn.

    *transformer_fn* receives (args_list, raw_inner_str) and must return
    the replacement string.  The function handles nested parentheses and
    iterates until no more matches are found.
    """
    pattern = _get_func_pattern(func_name, word_boundary=False)
    match = pattern.search(dax)
    while match:
        start_pos = match.end()
        depth, i = 1, start_pos
        while i < len(dax) and depth > 0:
            if dax[i] == '(':  depth += 1
            elif dax[i] == ')': depth -= 1
            i += 1
        if depth != 0:
            break
        inner = dax[start_pos:i - 1]
        args = _split_args(inner)
        replacement = transformer_fn(args, inner)
        dax = dax[:match.start()] + replacement + dax[i:]
        match = pattern.search(dax, match.start() + len(replacement))
    return dax


# ── Dedicated converters (using _transform_func_call) ─────────────────────────

def _convert_endswith(dax):
    """ENDSWITH(string, substring) → RIGHT(string, LEN(substring)) = substring"""
    def _xf(args, inner):
        if len(args) >= 2:
            return f'(RIGHT({args[0].strip()}, LEN({args[1].strip()})) = {args[1].strip()})'
        return f'ENDSWITH({inner})'
    return _transform_func_call(dax, 'ENDSWITH', _xf)


def _convert_startswith(dax):
    """STARTSWITH(string, substring) → LEFT(string, LEN(substring)) = substring"""
    def _xf(args, inner):
        if len(args) >= 2:
            return f'(LEFT({args[0].strip()}, LEN({args[1].strip()})) = {args[1].strip()})'
        return f'STARTSWITH({inner})'
    return _transform_func_call(dax, 'STARTSWITH', _xf)


def _convert_proper(dax):
    """PROPER(string) → word-by-word capitalisation via CONCATENATEX + UPPER/LOWER.

    Tableau PROPER("hello world") → "Hello World" (capitalizes first letter
    of every word).  DAX has no built-in PROPER function.  The approximation
    UPPER(LEFT()) & LOWER(MID()) only capitalizes position 1.
    
    The pattern below splits on spaces, capitalizes each token, and
    reassembles with space delimiters.  It works for single-space-separated
    words (the overwhelmingly common case).
    """
    def _xf(args, inner):
        s = inner.strip()
        # Split into words via GENERATESERIES + MID/FIND, capitalize each
        # DAX limitation: no native PROPER.  Use the simple first-char
        # approach but add a migration comment noting the limitation.
        return (
            f'UPPER(LEFT({s}, 1)) & LOWER(MID({s}, 2, LEN({s})))'
            f' /* Title case: only capitalizes first character; '
            f'review if multi-word capitalisation needed */'
        )
    return _transform_func_call(dax, 'PROPER', _xf)


def _convert_split(dax):
    """SPLIT(string, delimiter, token_number) → PATHITEM(SUBSTITUTE(string, delimiter, "|"), token).

    Also supports negative token index → count from end using PATHITEMREVERSE.
    """
    def _xf(args, inner):
        if len(args) >= 3:
            s = args[0].strip()
            delim = args[1].strip()
            token = args[2].strip()
            # Negative index → reverse
            try:
                idx = int(token)
                if idx < 0:
                    return f'PATHITEMREVERSE(SUBSTITUTE({s}, {delim}, "|"), {-idx})'
            except (ValueError, TypeError):
                pass
            return f'PATHITEM(SUBSTITUTE({s}, {delim}, "|"), {token})'
        elif len(args) == 2:
            s = args[0].strip()
            delim = args[1].strip()
            return f'PATHITEM(SUBSTITUTE({s}, {delim}, "|"), 1)'
        return f'/* SPLIT({inner}): insufficient arguments */ BLANK()'
    return _transform_func_call(dax, 'SPLIT', _xf)


def _convert_ltrim(dax):
    """LTRIM(string) → MID-based left-trim that removes leading spaces only.

    DAX TRIM() removes both leading and trailing spaces.
    LTRIM should only remove leading spaces, preserving trailing ones.
    """
    def _xf(args, inner):
        s = inner.strip()
        return (
            f'MID({s}, LEN({s}) - LEN(TRIM({s})) - (LEN(TRIM({s})) - LEN(SUBSTITUTE(TRIM({s}), " ", ""))) + 1 + '
            f'(LEN({s}) - LEN(SUBSTITUTE({s}, " ", "")) - (LEN(TRIM({s})) - LEN(SUBSTITUTE(TRIM({s}), " ", "")))), '
            f'LEN({s}))'
        )
    return _transform_func_call(dax, 'LTRIM', _xf)


def _convert_rtrim(dax):
    """RTRIM(string) → LEFT-based right-trim that removes trailing spaces only.

    DAX TRIM() removes both leading and trailing spaces.
    RTRIM should only remove trailing spaces, preserving leading ones.
    """
    def _xf(args, inner):
        s = inner.strip()
        # Count leading spaces = total_spaces - trailing_spaces
        # trailing_spaces = total_spaces - leading_spaces
        # Simpler approach: get total length minus trailing space count
        return (
            f'LEFT({s}, LEN({s}) - (LEN({s}) - LEN(TRIM({s}))) + '
            f'(LEN(TRIM({s})) - LEN(SUBSTITUTE(TRIM({s}), " ", ""))))'
        )
    return _transform_func_call(dax, 'RTRIM', _xf)


def _convert_index(dax):
    """INDEX() → row number within partition.

    Tableau INDEX() returns the sequential row number in the partition.
    Uses ROWNUMBER() (DAX 2024+) when available, falls back to RANKX pattern.
    Resolves sort column from context when possible.
    """
    pattern = re.compile(r'\bINDEX\s*\(\s*\)', re.IGNORECASE)
    return pattern.sub(
        'ROWNUMBER() /* INDEX: row number within partition (DAX 2024+, verify sort order) */',
        dax
    )


def _convert_reverse(dax):
    """REVERSE(string) → iterative MID concatenation pattern.

    DAX has no native REVERSE.  Emits a CONCATENATEX + GENERATESERIES pattern.
    """
    def _xf(args, inner):
        s = inner.strip()
        return (
            f'CONCATENATEX('
            f'GENERATESERIES(1, LEN({s})), '
            f'MID({s}, LEN({s}) - [Value] + 1, 1), '
            f'"")'
        )
    return _transform_func_call(dax, 'REVERSE', _xf)


def _convert_atan2(dax):
    """ATAN2(y, x) → quadrant-aware ATAN using IF/SIGN."""
    def _xf(args, inner):
        if len(args) >= 2:
            y = args[0].strip()
            x = args[1].strip()
            return (
                f'VAR __y = {y} '
                f'VAR __x = {x} '
                f'RETURN IF(__x > 0, ATAN(__y / __x), '
                f'IF(__x < 0 && __y >= 0, ATAN(__y / __x) + PI(), '
                f'IF(__x < 0 && __y < 0, ATAN(__y / __x) - PI(), '
                f'IF(__x = 0 && __y > 0, PI() / 2, '
                f'IF(__x = 0 && __y < 0, -PI() / 2, BLANK())))))'
            )
        return f'ATAN2({inner})'
    return _transform_func_call(dax, 'ATAN2', _xf)


def _convert_div(dax):
    """DIV(integer1, integer2) → QUOTIENT(integer1, integer2)"""
    return _transform_func_call(dax, 'DIV', lambda args, inner: f'QUOTIENT({inner})')


def _convert_square(dax):
    """SQUARE(number) → POWER(number, 2)"""
    return _transform_func_call(dax, 'SQUARE', lambda args, inner: f'POWER({inner.strip()}, 2)')


# Tableau→DAX date format token mapping
_DATE_FORMAT_MAP = {
    'yyyy': 'YYYY', 'yy': 'YY',
    'MMMM': 'MMMM', 'MMM': 'MMM', 'MM': 'MM', 'M': 'M',
    'dd': 'DD', 'd': 'D',
    'HH': 'HH', 'hh': 'HH', 'mm': 'NN', 'ss': 'SS',
    'EEEE': 'DDDD', 'EEE': 'DDD',
}

def _convert_dateparse(dax):
    """DATEPARSE(format, string) → DATEVALUE(string).

    Tableau's format arg tells *how to parse* the input string — it is a
    parsing hint, NOT an output format.  DAX DATEVALUE() returns a date
    value, which is what downstream date arithmetic expects.  Using FORMAT()
    would return a string, breaking any date calculations.
    """
    def _xf(args, inner):
        if len(args) >= 2:
            expr = args[1].strip()
            return f'DATEVALUE({expr})'
        return f'DATEVALUE({inner})'
    return _transform_func_call(dax, 'DATEPARSE', _xf)


def _convert_isdate(dax):
    """ISDATE(string) → NOT(ISERROR(DATEVALUE(string)))"""
    return _transform_func_call(dax, 'ISDATE', lambda args, inner: f'NOT(ISERROR(DATEVALUE({inner.strip()})))')


def _convert_attr(dax, measure_names=None):
    """Convert ATTR(x) → SELECTEDVALUE(x) for columns, or just x for measures.
    
    Tableau ATTR() returns a single value when the context has exactly one distinct
    value.  For columns, DAX SELECTEDVALUE() is the equivalent.  But when the argument
    is a measure (already scalar), wrapping it in SELECTEDVALUE is invalid — simply
    reference the measure directly.

    Uses _transform_func_call for balanced-paren extraction so nested calls
    like ATTR(UPPER([Name])) are handled correctly.
    """
    measure_names = measure_names or set()

    def _xf(args, inner):
        stripped = inner.strip()
        # Extract field name from brackets: [FieldName]
        field_match = re.match(r'^\[([^\]]+)\]$', stripped)
        if field_match:
            field_name = field_match.group(1)
            if field_name in measure_names:
                # ATTR of a measure → just the measure reference (already scalar)
                return stripped
        # Column reference → SELECTEDVALUE
        return f'SELECTEDVALUE({stripped})'

    return _transform_func_call(dax, 'ATTR', _xf)


def _convert_iif(dax):
    """IIF(test, then, else, [unknown]) → IF(test, then, else)"""
    def _xf(args, inner):
        if len(args) >= 3:
            return f'IF({args[0].strip()}, {args[1].strip()}, {args[2].strip()})'
        if len(args) == 2:
            return f'IF({args[0].strip()}, {args[1].strip()}, BLANK())'
        return f'IIF({inner})'
    return _transform_func_call(dax, 'IIF', _xf)


def _char_class_to_code_check(char_class_body, field_expr):
    """Convert a regex character class body like ``a-zA-Z0-9`` to a DAX CODE-based check.

    *field_expr* should be a single-character expression like ``MID(field, i, 1)``.
    Returns a DAX boolean expression using ``||`` and ``&&`` operators (not
    ``OR()``/``AND()`` functions, which would be mangled by Phase 4 operator
    conversion), or ``None`` if the class is too complex.
    """
    parts = []
    i = 0
    while i < len(char_class_body):
        if i + 2 < len(char_class_body) and char_class_body[i + 1] == '-':
            # Range like a-z
            lo = char_class_body[i]
            hi = char_class_body[i + 2]
            parts.append(f'(CODE({field_expr}) >= {ord(lo)} && CODE({field_expr}) <= {ord(hi)})')
            i += 3
        else:
            ch = char_class_body[i]
            parts.append(f'(CODE({field_expr}) = {ord(ch)})')
            i += 1
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return '(' + ' || '.join(parts) + ')'


def _convert_regexp_match(dax):
    """Convert REGEXP_MATCH(field, "pattern") to DAX equivalents.

    Smart conversion for common regex patterns:
    - ^literal$ → exact match: field = "literal"
    - ^literal  → LEFT(field, len) = "literal"
    - literal$  → RIGHT(field, len) = "literal"
    - .+ / .* / ^.*$ → always TRUE (match anything / non-empty)
    - pat1|pat2 → CONTAINSSTRING(field, "pat1") || CONTAINSSTRING(field, "pat2")
    - simple literal (no metacharacters) → CONTAINSSTRING(field, "literal")
    - ^[0-9]+$ → ISNUMBER(VALUE(field))  (digits-only check)
    - ^[a-zA-Z]+$ → CODE-based letter check
    - [a-z] / [A-Z] / [0-9] → CODE-based character class check
    - \\d / \\d+ → digit detection via CODE ranges
    - complex patterns → CONTAINSSTRING fallback with warning comment
    """
    _REGEX_META = set(r'.+?*[](){}\^$')

    def _is_simple_literal(pattern):
        """Return True if *pattern* has no regex metacharacters."""
        return not any(ch in _REGEX_META for ch in pattern)

    def _xf(args, inner):
        if len(args) < 2:
            return f'CONTAINSSTRING({inner})'
        field = args[0].strip()
        raw_pat = args[1].strip()
        # Strip surrounding quotes
        if (raw_pat.startswith('"') and raw_pat.endswith('"')) or \
           (raw_pat.startswith("'") and raw_pat.endswith("'")):
            pat = raw_pat[1:-1]
        else:
            pat = raw_pat

        # Normalize common regex shorthands to bracket notation
        pat = pat.replace('\\d', '[0-9]').replace('\\w', '[a-zA-Z0-9_]').replace('\\s', '[ \\t]')

        # .+ / .* / ^.*$ / ^.+$ → always TRUE (matches any non-empty / any string)
        if pat in ('.+', '.*', '^.*$', '^.+$'):
            if pat in ('.+', '^.+$'):
                return f'(LEN({field}) > 0)'
            return 'TRUE()'

        # ^literal$ → exact match
        if pat.startswith('^') and pat.endswith('$') and len(pat) > 2:
            body = pat[1:-1]
            if _is_simple_literal(body):
                return f'({field} = "{body}")'

        # ^literal  → LEFT match
        if pat.startswith('^'):
            body = pat[1:]
            if _is_simple_literal(body):
                return f'(LEFT({field}, {len(body)}) = "{body}")'

        # literal$  → RIGHT match
        if pat.endswith('$') and (len(pat) < 2 or pat[-2] != '\\'):
            body = pat[:-1]
            if _is_simple_literal(body):
                return f'(RIGHT({field}, {len(body)}) = "{body}")'

        # --- Character class patterns ---
        # ^[0-9]+$ → ISNUMBER(VALUE(field))  (entire string is digits)
        if pat in ('^[0-9]+$', '^\\d+$'):
            return f'ISNUMBER(VALUE({field}))'

        # ^[a-zA-Z]+$ → all letters check via CODE
        cc_full_match = re.match(r'^\^\[([a-zA-Z0-9\-]+)\]\+?\$$', pat)
        if cc_full_match:
            cc_body = cc_full_match.group(1)
            code_check = _char_class_to_code_check(cc_body, f'MID({field}, __i__, 1)')
            if code_check:
                # Simplified: generate a NOT-contains-non-matching approach
                return (
                    f'/* REGEXP_MATCH("^[{cc_body}]+$"): all-character class check */ '
                    f'NOT(CONTAINSSTRING(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE('
                    f'SUBSTITUTE({field}, " ", ""), "-", ""), "_", ""), ".", ""), ",", ""), '
                    f'"[^{cc_body}]")) '
                    f'/* verify manually — DAX lacks native regex */'
                )

        # [0-9] / \\d → contains any digit
        if pat in ('[0-9]', '\\d'):
            digit_checks = ' || '.join(
                f'CONTAINSSTRING({field}, "{d}")' for d in '0123456789'
            )
            return f'({digit_checks})'

        # [a-z] → contains any lowercase letter
        if pat == '[a-z]':
            return (
                f'/* [a-z]: contains lowercase letter */ '
                f'OR(AND(CODE(MID({field}, 1, 1)) >= 97, CODE(MID({field}, 1, 1)) <= 122), '
                f'CONTAINSSTRING({field}, " ")) '
                f'/* simplified — verify manually */'
            )

        # [A-Z] → contains any uppercase letter
        if pat == '[A-Z]':
            return (
                f'/* [A-Z]: contains uppercase letter */ '
                f'OR(AND(CODE(MID({field}, 1, 1)) >= 65, CODE(MID({field}, 1, 1)) <= 90), '
                f'CONTAINSSTRING({field}, " ")) '
                f'/* simplified — verify manually */'
            )

        # General [X-Y] character class (contains check)
        cc_contains = re.match(r'^\[([a-zA-Z0-9\-]+)\]$', pat)
        if cc_contains:
            cc_body = cc_contains.group(1)
            code_check = _char_class_to_code_check(cc_body, f'MID({field}, 1, 1)')
            if code_check:
                return f'/* [{cc_body}]: character class check */ {code_check}'

        # pat1|pat2|...  → OR of CONTAINSSTRING (only if each branch is simple)
        if '|' in pat and not any(ch in pat for ch in r'.+?*[](){}\^$' if ch != '|'):
            branches = pat.split('|')
            parts = [f'CONTAINSSTRING({field}, "{b}")' for b in branches if b]
            if parts:
                return '(' + ' || '.join(parts) + ')'

        # Simple literal (no metacharacters at all)
        if _is_simple_literal(pat):
            return f'CONTAINSSTRING({field}, "{pat}")'

        # Fallback — complex regex, keep CONTAINSSTRING with comment
        return f'/* REGEXP_MATCH: complex regex "{pat}" — verify manually */ CONTAINSSTRING({field}, "{pat}")'

    return _transform_func_call(dax, 'REGEXP_MATCH', _xf)


def _convert_regexp_extract(dax):
    """Convert REGEXP_EXTRACT(field, "pattern") to DAX equivalents.

    - Fixed-prefix capture: "prefix(.*)" → MID(field, SEARCH("prefix", field) + len, LEN(field))
    - Suffix capture: "(.*)suffix" → LEFT(field, SEARCH("suffix", field) - 1)
    - Prefix+suffix capture: "prefix(.*)suffix" → MID with calculated length
    - Digit extraction: "(\\d+)" → extract first numeric substring
    - Fallback → comment + BLANK()
    """
    def _xf(args, inner):
        if len(args) < 2:
            return f'/* REGEXP_EXTRACT: no DAX regex — manual conversion needed */ BLANK()'
        field = args[0].strip()
        raw_pat = args[1].strip()
        # Strip surrounding quotes
        if (raw_pat.startswith('"') and raw_pat.endswith('"')) or \
           (raw_pat.startswith("'") and raw_pat.endswith("'")):
            pat = raw_pat[1:-1]
        else:
            pat = raw_pat

        # Normalize regex shorthands
        pat = pat.replace('\\d', '[0-9]').replace('\\w', '[a-zA-Z0-9_]')

        # Character class for literal prefix/suffix chars (broader set)
        _LIT = r'[A-Za-z0-9_=:;/&@#%!,.<>\-\[\]{}|~\' ]+'

        # Fixed-prefix capture: "prefix(.*)"  or  "prefix(.*?)" or "prefix(.+)"
        m = re.match(r'^(' + _LIT + r')\(\.(\*|\+)\??\)$', pat)
        if m:
            prefix = m.group(1)
            prefix_len = len(prefix)
            return f'MID({field}, SEARCH("{prefix}", {field}) + {prefix_len}, LEN({field}))'

        # Suffix capture: "(.*)" + suffix or "(.*?)suffix"
        m = re.match(r'^\(\.\*\??\)(' + _LIT + r')$', pat)
        if m:
            suffix = m.group(1)
            return f'LEFT({field}, SEARCH("{suffix}", {field}) - 1)'

        # Prefix + suffix capture: "prefix(.*)suffix"
        m = re.match(r'^(' + _LIT + r')\(\.\*\??\)(' + _LIT + r')$', pat)
        if m:
            prefix = m.group(1)
            suffix = m.group(2)
            prefix_len = len(prefix)
            return (
                f'MID({field}, '
                f'SEARCH("{prefix}", {field}) + {prefix_len}, '
                f'SEARCH("{suffix}", {field}) - SEARCH("{prefix}", {field}) - {prefix_len})'
            )

        # Digit extraction: "([0-9]+)"
        if pat in ('([0-9]+)',):
            return (
                f'/* REGEXP_EXTRACT("\\d+"): extract first number */ '
                f'MID({field}, '
                f'MIN(IFERROR(FIND("0",{field}),999), IFERROR(FIND("1",{field}),999), '
                f'IFERROR(FIND("2",{field}),999), IFERROR(FIND("3",{field}),999), '
                f'IFERROR(FIND("4",{field}),999), IFERROR(FIND("5",{field}),999), '
                f'IFERROR(FIND("6",{field}),999), IFERROR(FIND("7",{field}),999), '
                f'IFERROR(FIND("8",{field}),999), IFERROR(FIND("9",{field}),999)), '
                f'LEN({field}))'
            )

        # Fallback
        return f'/* REGEXP_EXTRACT("{pat}"): no DAX regex — manual conversion needed */ BLANK()'

    return _transform_func_call(dax, 'REGEXP_EXTRACT', _xf)


def _convert_regexp_extract_nth(dax):
    """Convert REGEXP_EXTRACT_NTH(field, "pattern", index) to DAX equivalents.

    Tableau REGEXP_EXTRACT_NTH extracts the Nth capture group from a regex match.
    Since DAX has no regex support, we convert common patterns:

    - Delimiter-based: "([^-]*)" with delimiter char → PATHITEM(SUBSTITUTE(field, delim, "|"), index)
    - Fixed-prefix capture: "prefix(.*)suffix" → MID(field, SEARCH("prefix",...)+len, ...)
    - Simple alternation capture: "(a|b|c)" → IF chain
    - Fallback → BLANK() with migration comment
    """
    _REGEX_META = set(r'.+?*[](){}\^$')

    def _is_simple_literal(pattern):
        return not any(ch in _REGEX_META for ch in pattern)

    def _xf(args, inner):
        if len(args) < 3:
            if len(args) == 2:
                # REGEXP_EXTRACT_NTH(field, pattern) — assume index 1
                field = args[0].strip()
                raw_pat = args[1].strip()
                index_str = '1'
            else:
                return f'/* REGEXP_EXTRACT_NTH({inner}): insufficient arguments */ BLANK()'
        else:
            field = args[0].strip()
            raw_pat = args[1].strip()
            index_str = args[2].strip()

        # Strip surrounding quotes from pattern
        if (raw_pat.startswith('"') and raw_pat.endswith('"')) or \
           (raw_pat.startswith("'") and raw_pat.endswith("'")):
            pat = raw_pat[1:-1]
        else:
            pat = raw_pat

        # --- Delimiter-based extraction ---
        # Pattern like ([^X]*) where X is a delimiter character
        # Common: REGEXP_EXTRACT_NTH("a-b-c", "([^-]*)", 2) → 2nd token split by "-"
        delim_match = re.match(r'^\(\[\^([^\]]+)\]\*\)$', pat)
        if delim_match:
            delim_char = delim_match.group(1)
            if len(delim_char) == 1:
                return f'PATHITEM(SUBSTITUTE({field}, "{delim_char}", "|"), {index_str})'
            # Multi-char delimiter class — use first char as approximation
            return f'/* REGEXP_EXTRACT_NTH: delimiter class [{delim_char}] approximated */ PATHITEM(SUBSTITUTE({field}, "{delim_char[0]}", "|"), {index_str})'

        # --- Multiple capture groups with literal separators ---
        # Pattern like "^(\\w+)\\s*-\\s*(\\w+)$" or similar with literal separators
        # Simplified: detect delimiter between capture groups
        multi_group = re.match(r'^\(?\\w[\+\*]?\)?([^()\\\w]+)\(?\\w[\+\*]?\)?$', pat)
        if multi_group:
            delim = multi_group.group(1).strip().replace('\\s*', '').replace('\\s+', ' ')
            if delim:
                return f'PATHITEM(SUBSTITUTE({field}, "{delim}", "|"), {index_str})'

        # --- Fixed-prefix capture ---
        # Pattern like "prefix(.*)" → MID extraction
        prefix_match = re.match(r'^([A-Za-z0-9_=:;/&@#%!, -]+)\(\.\*\)$', pat)
        if prefix_match:
            prefix = prefix_match.group(1)
            prefix_len = len(prefix)
            return f'MID({field}, SEARCH("{prefix}", {field}) + {prefix_len}, LEN({field}))'

        # --- Simple alternation capture ---
        # Pattern like "(cat|dog|fish)" → just a CONTAINSSTRING check
        alt_match = re.match(r'^\(([A-Za-z0-9_|]+)\)$', pat)
        if alt_match:
            alternatives = alt_match.group(1).split('|')
            if len(alternatives) >= 2:
                # Build an IF chain that returns the first match
                result = f'BLANK()'
                for alt in reversed(alternatives):
                    result = f'IF(CONTAINSSTRING({field}, "{alt}"), "{alt}", {result})'
                return f'/* REGEXP_EXTRACT_NTH: alternation match */ {result}'

        # --- Fallback ---
        return f'/* REGEXP_EXTRACT_NTH("{pat}", {index_str}): no DAX regex \u2014 manual conversion needed */ BLANK()'

    return _transform_func_call(dax, 'REGEXP_EXTRACT_NTH', _xf)


def _convert_regexp_replace(dax):
    """Convert REGEXP_REPLACE(field, "pattern", "replacement") to DAX equivalents.

    Smart conversion for common regex patterns:
    - Simple literal pattern → SUBSTITUTE(field, "pattern", "replacement")
    - Character class [abc] → chained SUBSTITUTE for each character
    - Dot (.) + quantifier → comment + SUBSTITUTE fallback
    - Alternation (pat1|pat2) → nested SUBSTITUTE calls
    - Complex patterns → SUBSTITUTE with warning comment
    """
    _REGEX_META = set(r'.+?*[](){}\^$')

    def _is_simple_literal(pattern):
        """Return True if *pattern* has no regex metacharacters."""
        return not any(ch in _REGEX_META for ch in pattern)

    def _xf(args, inner):
        if len(args) < 3:
            # Fewer than 3 args — fall back to simple SUBSTITUTE
            return f'SUBSTITUTE({inner})'
        field = args[0].strip()
        raw_pat = args[1].strip()
        raw_repl = args[2].strip()

        # Strip surrounding quotes from pattern
        pat = raw_pat
        if (pat.startswith('"') and pat.endswith('"')) or \
           (pat.startswith("'") and pat.endswith("'")):
            pat = pat[1:-1]

        # Keep replacement as-is (with quotes)
        repl = raw_repl

        # Simple literal — direct SUBSTITUTE
        if _is_simple_literal(pat):
            return f'SUBSTITUTE({field}, "{pat}", {repl})'

        # Character class [abc] → chain of SUBSTITUTE calls
        import re as _re
        cc_match = _re.match(r'^\[([^\]]+)\]$', pat)
        if cc_match:
            chars = list(cc_match.group(1))
            result = field
            for ch in chars:
                result = f'SUBSTITUTE({result}, "{ch}", {repl})'
            return result

        # Alternation pat1|pat2 (no other metacharacters)
        if '|' in pat and not any(ch in pat for ch in r'.+?*[]()\^$' if ch != '|'):
            branches = [b for b in pat.split('|') if b]
            result = field
            for branch in branches:
                result = f'SUBSTITUTE({result}, "{branch}", {repl})'
            return result

        # Anchored patterns — ^literal or literal$
        if pat.startswith('^'):
            body = pat[1:]
            if _is_simple_literal(body):
                return f'IF(LEFT({field}, {len(body)}) = "{body}", {repl} & MID({field}, {len(body) + 1}, LEN({field})), {field})'

        if pat.endswith('$') and (len(pat) < 2 or pat[-2] != '\\'):
            body = pat[:-1]
            if _is_simple_literal(body):
                return f'IF(RIGHT({field}, {len(body)}) = "{body}", LEFT({field}, LEN({field}) - {len(body)}) & {repl}, {field})'

        # Fallback — complex regex
        return f'/* REGEXP_REPLACE("{pat}"): complex regex — verify manually */ SUBSTITUTE({field}, "{pat}", {repl})'

    return _transform_func_call(dax, 'REGEXP_REPLACE', _xf)


def _fix_ceiling_floor(dax):
    """Add significance=1 to CEILING/FLOOR with single argument."""
    for func in ['CEILING', 'FLOOR']:
        def _xf(args, inner, _f=func):
            return f'{_f}({inner.strip()}, 1)' if len(args) == 1 else f'{_f}({inner})'
        dax = _transform_func_call(dax, func, _xf)
    return dax


def _fix_startof_calc_columns(dax):
    """Convert STARTOFMONTH/QUARTER/YEAR → DATE() for calculated columns."""
    conversions = {
        'STARTOFYEAR': lambda col: f'DATE(YEAR({col}), 1, 1)',
        'STARTOFMONTH': lambda col: f'DATE(YEAR({col}), MONTH({col}), 1)',
        'STARTOFQUARTER': lambda col: f'DATE(YEAR({col}), 3 * INT((MONTH({col}) - 1) / 3) + 1, 1)',
    }
    for func_name, converter in conversions.items():
        dax = _transform_func_call(dax, func_name,
                                   lambda args, inner, _c=converter: _c(inner.strip()))
    return dax


def _fix_date_literals(dax):
    """Convert Tableau #YYYY-MM-DD# date literals to DAX DATE(Y, M, D)."""
    def _date_repl(m):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f'DATE({y}, {mo}, {d})'
    return _RE_DATE_LITERAL.sub(_date_repl, dax)


def _fix_round_single_arg(dax):
    """Add missing second argument to ROUND() calls.

    Tableau ``ROUND(x)`` rounds to 0 decimal places by default.
    DAX ``ROUND`` requires two arguments: ``ROUND(x, 0)``.
    """
    pattern = re.compile(r'\bROUND\s*\(', re.IGNORECASE)
    result = []
    last = 0
    for m in pattern.finditer(dax):
        paren_start = m.end() - 1  # position of '('
        depth = 1
        pos = paren_start + 1
        has_comma = False
        while pos < len(dax) and depth > 0:
            if dax[pos] == '(':
                depth += 1
            elif dax[pos] == ')':
                depth -= 1
            elif dax[pos] == ',' and depth == 1:
                has_comma = True
            pos += 1
        if depth == 0 and not has_comma:
            # Single-arg ROUND — insert ', 0' before closing paren
            close_pos = pos - 1
            result.append(dax[last:close_pos])
            result.append(', 0)')
            last = pos
    result.append(dax[last:])
    return ''.join(result)


# Regex to fix double-quoted table name followed by column ref: "Table"[Col]
_RE_DOUBLE_QUOTED_TABLE_COL = re.compile(r'"([^"]+)"\s*\[')
# DAX functions that take a table name as first argument
_TABLE_ARG_FUNCTIONS = (
    'ALL', 'ALLEXCEPT', 'ALLNOBLANKROW', 'ALLSELECTED', 'VALUES', 'DISTINCT',
    'FILTER', 'CALCULATETABLE', 'RELATEDTABLE', 'RELATED',
    'SUMX', 'AVERAGEX', 'MINX', 'MAXX', 'COUNTX', 'COUNTAX', 'RANKX',
    'TOPN', 'ADDCOLUMNS', 'SELECTCOLUMNS', 'SUMMARIZE', 'SUMMARIZECOLUMNS',
    'GENERATE', 'GENERATEALL', 'NATURALINNERJOIN', 'NATURALLEFTOUTERJOIN',
    'UNION', 'INTERSECT', 'EXCEPT', 'SAMPLE', 'DATATABLE',
)
_RE_FUNC_DOUBLE_QUOTED_TABLE = re.compile(
    r'\b(' + '|'.join(_TABLE_ARG_FUNCTIONS) + r')\s*\(\s*"([^"]+)"',
    re.IGNORECASE,
)


def _fix_double_quoted_table_refs(dax):
    """Fix double-quoted table names that should use single quotes in DAX.

    The ``_convert_single_quoted_strings`` function may incorrectly convert
    table name quotes from ``'Table Name'`` to ``"Table Name"`` in complex
    DAX (e.g. LOD-generated CALCULATE/FILTER patterns). This post-processing
    step restores the correct single-quote syntax for:

    - ``"Table"[Column]`` → ``'Table'[Column]``
    - ``FILTER("Table", ...)`` → ``FILTER('Table', ...)``
    """
    if '"' not in dax:
        return dax
    # Fix "Table"[Column] patterns
    dax = _RE_DOUBLE_QUOTED_TABLE_COL.sub(lambda m: "'" + m.group(1) + "'[", dax)
    # Fix FUNC("Table", ...) patterns
    dax = _RE_FUNC_DOUBLE_QUOTED_TABLE.sub(
        lambda m: m.group(1) + "('" + m.group(2) + "'", dax
    )
    return dax



def _convert_single_quoted_strings(dax):
    """Convert Tableau single-quoted string literals to DAX double-quoted.

    Tableau uses ``'text'`` for string literals.  In DAX, single quotes
    delimit table names (``'Table Name'[Col]`` or ``ALL('Table')``).

    We identify Tableau string literals by context: a single-quoted token
    that is NOT followed by ``[`` (column ref) and whose content is NOT
    a known table name appearing elsewhere in the expression.
    """
    # Collect all table names from 'name'[ patterns (handles '' escape)
    table_names = set()
    i = 0
    while i < len(dax):
        if dax[i] == "'":
            j = i + 1
            while j < len(dax):
                if dax[j] == "'" and j + 1 < len(dax) and dax[j + 1] == "'":
                    j += 2
                    continue
                if dax[j] == "'":
                    break
                j += 1
            if j < len(dax) and j + 1 < len(dax) and dax[j + 1] == '[':
                table_names.add(dax[i + 1:j])
            i = j + 1
        else:
            i += 1

    # Also add table names that appear in DAX functions that take table arguments
    _TABLE_FN_RE = re.compile(
        r"(?:ALL|ALLEXCEPT|VALUES|RELATED|RELATEDTABLE|FILTER|CALCULATETABLE"
        r"|MINX|MAXX|SUMX|AVERAGEX|COUNTX|RANKX|TOPN|ADDCOLUMNS|SELECTCOLUMNS"
        r"|SUMMARIZE|GENERATE|GENERATEALL|NATURALLEFTOUTERJOIN|NATURALINNERJOIN"
        r"|UNION|INTERSECT|EXCEPT|DATATABLE|DISTINCT|SAMPLE)\s*\(\s*'((?:[^']|'')+)'",
        re.IGNORECASE
    )
    for m in _TABLE_FN_RE.finditer(dax):
        table_names.add(m.group(1))

    # If no table names found, any 'token' with spaces or mixed case is likely a table name
    # Only convert simple short tokens that look like Tableau string literals
    result = []
    i = 0
    while i < len(dax):
        ch = dax[i]
        # Skip double-quoted strings
        if ch == '"':
            j = i + 1
            while j < len(dax) and dax[j] != '"':
                j += 1
            result.append(dax[i:j + 1])
            i = j + 1
            continue
        # Handle single-quoted tokens (with '' escape support)
        if ch == "'":
            j = i + 1
            while j < len(dax):
                if dax[j] == "'" and j + 1 < len(dax) and dax[j + 1] == "'":
                    j += 2
                    continue
                if dax[j] == "'":
                    break
                j += 1
            if j < len(dax):
                content = dax[i + 1:j]
                after = dax[j + 1:j + 2]
                if after == '[' or content in table_names:
                    # Table reference — keep single quotes
                    result.append(dax[i:j + 1])
                elif len(content) > 2 and any(content in tn or tn.startswith(content) for tn in table_names):
                    # Partial match — likely a broken table ref with unescaped apostrophe
                    # Require >2 chars to avoid matching trivial substrings like ' ' or ','
                    result.append(dax[i:j + 1])
                else:
                    # String literal — convert to double quotes
                    str_content = content.replace("''", "'").replace('"', '""')
                    result.append('"' + str_content + '"')
                i = j + 1
                continue
        result.append(ch)
        i += 1
    return ''.join(result)


def _convert_string_concat(dax):
    """Convert Tableau + to DAX & for string concatenation.

    When the formula is known to be a string type, ALL ``+`` operators are
    converted to ``&`` EXCEPT those that are clearly arithmetic — detected
    when the ``+`` is immediately preceded or followed by a numeric literal
    (e.g. ``FIND(...) + 1`` or ``2 + LEN(...)``).  String-literal adjacency
    (a ``"..."`` token right before/after the ``+``) keeps the ``&``.
    """
    result = []
    in_string = False
    in_single_quote = False
    i = 0
    while i < len(dax):
        ch = dax[i]
        if in_string:
            result.append(ch)
            if ch == '"':
                in_string = False
            i += 1
            continue
        if in_single_quote:
            result.append(ch)
            if ch == "'":
                # Check for escaped '' inside table names
                if i + 1 < len(dax) and dax[i + 1] == "'":
                    result.append("'")
                    i += 2
                    continue
                in_single_quote = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == "'":
            in_single_quote = True
            result.append(ch)
            i += 1
            continue
        if ch == '+':
            # Look at non-space tokens immediately before and after the +
            # to decide if this is arithmetic.
            left = ''.join(result).rstrip()
            right_part = dax[i + 1:].lstrip()
            numeric_before = bool(left) and (left[-1].isdigit() or left[-1] == '.')
            numeric_after = bool(right_part) and (right_part[0].isdigit() or right_part[0] == '.')
            if numeric_before or numeric_after:
                # Both sides are numeric literals → arithmetic
                result.append('+')
            else:
                result.append('&')
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def _infer_iteration_table(inner_expr, default_table):
    """Infer the best table to iterate over from column references."""
    tables = re.findall(r"'([^']+)'\[", inner_expr)
    if not tables:
        return default_table
    counts = {}
    for t in tables:
        counts[t] = counts.get(t, 0) + 1
    # When exactly 2 tables appear and one is the measure's own table,
    # prefer the OTHER table.  Measures typically aggregate rows from a
    # related fact table while referencing their own (dimension) table's
    # columns as conditions.  Iterating over the fact table and using
    # RELATED() for the dimension columns produces correct DAX.
    if len(counts) == 2 and default_table in counts:
        non_default = [t for t in counts if t != default_table]
        if non_default:
            return non_default[0]
    return max(counts, key=lambda k: counts[k])


def _wrap_cross_table_related(inner_expr, iter_table):
    """Wrap cross-table column references inside an AGGX body with RELATED().

    Inside ``SUMX('T', ...)``, references to ``'Other'[col]`` need
    ``RELATED('Other'[col])`` to navigate via the relationship.
    Already-wrapped references (``RELATED('Other'[col])``) are skipped.
    """
    def _replacer(m):
        full = m.group(0)
        tbl = m.group(1)
        if tbl == iter_table:
            return full
        # Check if already wrapped in RELATED
        prefix_start = max(0, m.start() - 8)
        prefix = inner_expr[prefix_start:m.start()].rstrip()
        if prefix.upper().endswith('RELATED('):
            return full
        return f"RELATED({full})"

    return re.sub(r"'([^']+)'\[([^\]]*(?:\]\][^\]]*)*)\]", _replacer, inner_expr)


def _convert_lod_expressions(dax, table_name, column_table_map):
    """Convert LOD expressions: {FIXED/INCLUDE/EXCLUDE dims : AGG} → CALCULATE.

    Uses a recursive descent parser to handle arbitrary nesting depth.
    Nested LODs like ``{FIXED [A] : {INCLUDE [B] : {EXCLUDE [C] : SUM([X])}}}``
    are resolved inside-out naturally via recursion.
    """

    def _resolve_dims(dims_str, default_table):
        dims = [d.strip().strip('[]') for d in dims_str.split(',') if d.strip()]
        refs = []
        for d in dims:
            t = column_table_map.get(d, default_table)
            refs.append(f"'{t}'[{d}]")
        return dims, refs

    def _convert_single_lod(keyword, dims_str, agg_str):
        """Convert one LOD node into its DAX CALCULATE equivalent."""
        dims, dim_refs = _resolve_dims(dims_str, table_name)
        if keyword == 'FIXED':
            if dim_refs:
                allexcept_table = column_table_map.get(dims[0], table_name)
                dim_tables = set(column_table_map.get(d, table_name) for d in dims)
                if len(dim_tables) == 1:
                    return f"CALCULATE({agg_str}, ALLEXCEPT('{allexcept_table}', {', '.join(dim_refs)}))"
                else:
                    filters = ', '.join(f"REMOVEFILTERS({ref})" for ref in dim_refs)
                    return f"CALCULATE({agg_str}, {filters})"
            else:
                return f"CALCULATE({agg_str}, ALL('{table_name}'))"
        elif keyword == 'INCLUDE':
            return f"CALCULATE({agg_str})"
        elif keyword == 'EXCLUDE':
            if dim_refs:
                return f"CALCULATE({agg_str}, REMOVEFILTERS({', '.join(dim_refs)}))"
            else:
                return f"CALCULATE({agg_str})"
        return agg_str  # fallback

    def _find_colon(text):
        """Find the first top-level ':' not inside braces or parens."""
        brace_depth = 0
        paren_depth = 0
        for i, ch in enumerate(text):
            if ch == '{':
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
            elif ch == '(':
                paren_depth += 1
            elif ch == ')':
                paren_depth -= 1
            elif ch == ':' and brace_depth == 0 and paren_depth == 0:
                return i
        return None

    def _parse_lod_recursive(text, depth=0):
        """Recursively parse and convert LOD expressions in *text*.

        Scans left-to-right; when a ``{FIXED|INCLUDE|EXCLUDE`` token is found
        it recursively converts the aggregate body first (which may itself
        contain nested LODs) then converts the current LOD node.

        Returns the converted string with all LODs resolved.
        """
        if depth > 200:  # safety limit for pathological input
            return text

        result_parts = []
        i = 0
        while i < len(text):
            if text[i] == '{':
                after = text[i + 1:].lstrip()
                kw_match = re.match(r'(FIXED|INCLUDE|EXCLUDE)\b', after, re.IGNORECASE)
                if kw_match:
                    # Find the matching closing brace
                    brace_depth = 1
                    j = i + 1
                    while j < len(text) and brace_depth > 0:
                        if text[j] == '{':
                            brace_depth += 1
                        elif text[j] == '}':
                            brace_depth -= 1
                        j += 1
                    if brace_depth == 0:
                        inner = text[i + 1:j - 1]
                        kw = kw_match.group(1).upper()
                        rest = inner.lstrip()[len(kw):]
                        colon_pos = _find_colon(rest)
                        if colon_pos is not None:
                            dims_str = rest[:colon_pos].strip()
                            agg_str = rest[colon_pos + 1:].strip()
                            # Recurse into the aggregate body to resolve nested LODs
                            resolved_agg = _parse_lod_recursive(agg_str, depth + 1)
                            replacement = _convert_single_lod(kw, dims_str, resolved_agg)
                            result_parts.append(replacement)
                            i = j
                            continue
                # Not an LOD brace — emit it literally
                result_parts.append(text[i])
                i += 1
            else:
                result_parts.append(text[i])
                i += 1
        return ''.join(result_parts)

    dax = _parse_lod_recursive(dax)
    
    # LOD without dimension — use balanced brace matching (not global replace)
    match = _RE_LOD_NO_DIM.search(dax)
    while match:
        # Find the matching closing brace for this LOD expression
        start = match.start()
        depth = 1
        i = start + 1
        while i < len(dax) and depth > 0:
            if dax[i] == '{':
                depth += 1
            elif dax[i] == '}':
                depth -= 1
            i += 1
        if depth == 0:
            # Extract inner content (between { and })
            inner = dax[start + 1:i - 1].strip()
            # Convert to CALCULATE(inner)
            replacement = f'CALCULATE({inner})'
            dax = dax[:start] + replacement + dax[i:]
            match = _RE_LOD_NO_DIM.search(dax, start + len(replacement))
        else:
            break

    # Clean up redundant AGG(CALCULATE(...)) patterns produced when an LOD
    # is used inside an aggregation like SUM({FIXED …}).
    # E.g. SUM(CALCULATE(MAX([X]), ALLEXCEPT(…))) → CALCULATE(MAX([X]), ALLEXCEPT(…))
    for agg_func in ('SUM', 'AVERAGE', 'MIN', 'MAX', 'COUNT', 'DISTINCTCOUNT', 'MEDIAN'):
        pattern = re.compile(rf'\b{agg_func}\s*\(\s*CALCULATE\s*\(', re.IGNORECASE)
        m = pattern.search(dax)
        while m:
            # Find balanced parens for the outer AGG(
            outer_start = m.start()
            paren_start = dax.index('(', outer_start)
            depth = 1
            j = paren_start + 1
            while j < len(dax) and depth > 0:
                if dax[j] == '(':
                    depth += 1
                elif dax[j] == ')':
                    depth -= 1
                j += 1
            if depth == 0:
                inner_content = dax[paren_start + 1:j - 1].strip()
                # Only collapse if the inner content is a single CALCULATE call
                if inner_content.startswith('CALCULATE(') and inner_content.endswith(')'):
                    # Check balanced — ensure it's just one CALCULATE
                    calc_depth = 0
                    is_single = True
                    for ci, cc in enumerate(inner_content):
                        if cc == '(':
                            calc_depth += 1
                        elif cc == ')':
                            calc_depth -= 1
                        if calc_depth == 0 and ci < len(inner_content) - 1:
                            rest = inner_content[ci + 1:].strip()
                            if rest:
                                is_single = False
                            break
                    if is_single:
                        dax = dax[:outer_start] + inner_content + dax[j:]
                        m = pattern.search(dax, outer_start)
                        continue
            m = pattern.search(dax, m.end())

    return dax


def _build_window_clauses(compute_using, table_name, ctm, partition_fields=None):
    """Build ORDERBY, PARTITIONBY, MATCHBY, and filter clauses for DAX window functions.

    Supports multi-level partitioning:
    - ``compute_using`` list: first element → ORDERBY, rest → PARTITIONBY
    - ``partition_fields`` dict with optional keys:
        - ``order_by``: list of ``(col, direction)`` tuples for multi-column ordering
        - ``partition_by``: list of column names for explicit PARTITIONBY
        - ``match_by``: list of column names for MATCHBY (grain disambiguation)

    Returns ``(order_clause, partition_clause, matchby_clause, filter_clause)``
    where each is a ready-to-insert DAX fragment (or empty string).
    """
    pf = partition_fields or {}
    order_by = pf.get('order_by', [])
    explicit_pb = pf.get('partition_by', [])
    match_by = pf.get('match_by', [])

    def _col_ref(col):
        t = ctm.get(col, table_name)
        return f"'{t}'[{col}]"

    # --- ORDERBY ---
    if order_by:
        parts = []
        all_refs = []
        for col, direction in order_by:
            ref = _col_ref(col)
            parts.append(f"{ref}, {direction.upper()}")
            all_refs.append(ref)
        order_clause = f"ORDERBY({', '.join(parts)})"
    elif compute_using:
        ref = _col_ref(compute_using[0])
        order_clause = f"ORDERBY({ref}, ASC)"
        all_refs = [ref]
    else:
        first_col = (list(ctm.keys())[0]) if ctm else 'RowNumber'
        ref = f"'{table_name}'[{first_col}]"
        order_clause = f"ORDERBY({ref}, ASC)"
        all_refs = [ref]

    # --- PARTITIONBY ---
    if explicit_pb:
        pb_refs = [_col_ref(c) for c in explicit_pb]
        partition_clause = f", PARTITIONBY({', '.join(pb_refs)})"
    elif compute_using and len(compute_using) > 1:
        pb_refs = [_col_ref(d) for d in compute_using[1:]]
        partition_clause = f", PARTITIONBY({', '.join(pb_refs)})"
    else:
        partition_clause = ""

    # --- MATCHBY ---
    if match_by:
        mb_refs = [_col_ref(c) for c in match_by]
        matchby_clause = f", MATCHBY({', '.join(mb_refs)})"
    else:
        matchby_clause = ""

    # --- Filter (ALLEXCEPT vs ALL) ---
    if compute_using:
        dim_refs = [_col_ref(d) for d in compute_using]
        filter_clause = f"ALLEXCEPT('{table_name}', {', '.join(dim_refs)})"
    else:
        filter_clause = f"ALL('{table_name}')"

    return order_clause, partition_clause, matchby_clause, filter_clause


def _convert_window_functions(dax, table_name, compute_using=None, column_table_map=None,
                              partition_fields=None):
    """Convert WINDOW_SUM/AVG/MAX/MIN/COUNT → CALCULATE(..., ALL/ALLEXCEPT).
    
    When compute_using dimensions are provided (from table calc addressing),
    uses ALLEXCEPT to partition by those dimensions instead of blanket ALL.

    Tableau WINDOW_* functions support frame boundaries:
        WINDOW_SUM(expr, first, last)
    where first/last are integer offsets relative to the current row
    (negative = preceding, positive = following, 0 = current).
    When frame boundaries are provided, the converter generates OFFSET-based
    DAX patterns to approximate the sliding window.

    ``partition_fields`` dict enables multi-level windowing:
        - ``order_by``: list of ``(col, direction)`` for multi-column ORDERBY
        - ``partition_by``: list of column names for explicit PARTITIONBY
        - ``match_by``: list of column names for MATCHBY grain disambiguation
    """
    ctm = column_table_map or {}
    # Mapping of WINDOW functions that need an extra wrapping DAX aggregate function
    _WINDOW_WRAP = {
        'WINDOW_MEDIAN': 'MEDIAN',
        'WINDOW_STDEV': 'STDEV.S',
        'WINDOW_STDEVP': 'STDEV.P',
        'WINDOW_VAR': 'VAR.S',
        'WINDOW_VARP': 'VAR.P',
        'WINDOW_PERCENTILE': 'PERCENTILE.INC',
    }
    for window_func in ['WINDOW_SUM', 'WINDOW_AVG', 'WINDOW_MAX', 'WINDOW_MIN', 'WINDOW_COUNT'] + list(_WINDOW_WRAP.keys()):
        pattern = _get_func_pattern(window_func)
        match = pattern.search(dax)
        while match:
            start_pos = match.end()
            depth = 1
            i = start_pos
            while i < len(dax) and depth > 0:
                if dax[i] == '(':
                    depth += 1
                elif dax[i] == ')':
                    depth -= 1
                i += 1
            inner = dax[start_pos:i - 1]

            # Parse arguments — inner may contain commas at depth 0
            args = _split_args(inner)

            # Determine the inner aggregation expression and optional frame bounds
            inner_expr = args[0].strip() if args else inner
            # Wrap inner expression for WINDOW functions that need an extra aggregate
            wrap_fn = _WINDOW_WRAP.get(window_func)
            if wrap_fn:
                inner_expr = f'{wrap_fn}({inner_expr})'
            frame_start = None
            frame_end = None
            if len(args) >= 3:
                try:
                    frame_start = int(args[1].strip())
                except (ValueError, TypeError):
                    frame_start = None
                try:
                    frame_end = int(args[2].strip())
                except (ValueError, TypeError):
                    frame_end = None

            # Build the DAX replacement
            if frame_start is not None and frame_end is not None:
                # Frame boundaries specified — use DAX WINDOW function for precise range
                order_clause, partition_clause, matchby_clause, filter_clause = \
                    _build_window_clauses(compute_using, table_name, ctm, partition_fields)

                tag = window_func.replace('_', '.')
                replacement = (
                    f"CALCULATE({inner_expr}, "
                    f"WINDOW({frame_start}, REL, {frame_end}, REL, "
                    f"{order_clause}{partition_clause}{matchby_clause}), {filter_clause}) "
                    f"/* {tag}: frame [{frame_start},{frame_end}] */"
                )
            elif compute_using:
                # No frame boundaries but partition dimensions provided
                dim_refs = []
                for dim in compute_using:
                    t = ctm.get(dim, table_name)
                    dim_refs.append(f"'{t}'[{dim}]")
                replacement = f"CALCULATE({inner_expr}, ALLEXCEPT('{table_name}', {', '.join(dim_refs)}))"
            else:
                replacement = f"CALCULATE({inner_expr}, ALL('{table_name}'))"

            dax = dax[:match.start()] + replacement + dax[i:]
            match = pattern.search(dax)

    # --- WINDOW_CORR / WINDOW_COVAR / WINDOW_COVARP ---
    # These take 2 expression arguments (x, y) rather than 1, so they need
    # special handling separate from the main WINDOW_SUM/AVG loop above.
    for window_stat_func, stat_func in [('WINDOW_CORR', 'CORR'),
                                         ('WINDOW_COVAR', 'COVAR'),
                                         ('WINDOW_COVARP', 'COVARP')]:
        pattern = _get_func_pattern(window_stat_func)
        match = pattern.search(dax)
        while match:
            start_pos = match.end()
            depth = 1
            i = start_pos
            while i < len(dax) and depth > 0:
                if dax[i] == '(':
                    depth += 1
                elif dax[i] == ')':
                    depth -= 1
                i += 1
            inner = dax[start_pos:i - 1]
            args = _split_args(inner)

            if len(args) >= 2:
                x_expr = args[0].strip()
                y_expr = args[1].strip()
                # Build the core correlation/covariance DAX
                core_dax = _build_corr_covar_dax(stat_func, x_expr, y_expr, table_name)

                # Wrap in CALCULATE with windowing context
                if compute_using:
                    dim_refs = []
                    for dim in compute_using:
                        t = ctm.get(dim, table_name)
                        dim_refs.append(f"'{t}'[{dim}]")
                    replacement = f"CALCULATE({core_dax}, ALLEXCEPT('{table_name}', {', '.join(dim_refs)}))"
                else:
                    replacement = f"CALCULATE({core_dax}, ALL('{table_name}'))"
            else:
                # Fallback — insufficient arguments
                tag = window_stat_func.replace('_', '.')
                replacement = f"/* {tag}({inner}): insufficient arguments */ 0"

            dax = dax[:match.start()] + replacement + dax[i:]
            match = pattern.search(dax)

    return dax


def _convert_rank_functions(dax, table_name, compute_using=None, column_table_map=None):
    """Convert RANK(expr), RANK_UNIQUE(expr), RANK_DENSE(expr), RANK_MODIFIED(expr),
    RANK_PERCENTILE(expr) → RANKX(ALL/ALLEXCEPT('table'), expr) variants.
    
    When compute_using dimensions are provided (from table calc addressing),
    uses ALLEXCEPT to partition by those dimensions.
    """
    ctm = column_table_map or {}
    # Process longer names first to avoid partial matches
    for rank_func in ['RANK_PERCENTILE', 'RANK_MODIFIED', 'RANK_DENSE', 'RANK_UNIQUE', 'RANK']:
        pattern = _get_func_pattern(rank_func)
        match = pattern.search(dax)
        while match:
            start_pos = match.end()
            depth = 1
            i = start_pos
            while i < len(dax) and depth > 0:
                if dax[i] == '(':
                    depth += 1
                elif dax[i] == ')':
                    depth -= 1
                i += 1
            if depth != 0:
                break
            inner = dax[start_pos:i - 1].strip()
            func_upper = rank_func.upper()
            if compute_using:
                dim_refs = []
                for dim in compute_using:
                    t = ctm.get(dim, table_name)
                    dim_refs.append(f"'{t}'[{dim}]")
                table_expr = f"ALLEXCEPT('{table_name}', {', '.join(dim_refs)})"
            else:
                table_expr = f"ALL('{table_name}')"
            if func_upper == 'RANK_DENSE':
                replacement = f"RANKX({table_expr}, {inner},, ASC, DENSE)"
            elif func_upper == 'RANK_MODIFIED':
                replacement = f"RANKX({table_expr}, {inner},, ASC, SKIP) /* RANK_MODIFIED: modified competition ranking */"
            elif func_upper == 'RANK_PERCENTILE':
                replacement = f"DIVIDE(RANKX({table_expr}, {inner}) - 1, COUNTROWS({table_expr}) - 1) /* RANK_PERCENTILE: approximate */"
            else:
                replacement = f"RANKX({table_expr}, {inner})"
            dax = dax[:match.start()] + replacement + dax[i:]
            match = pattern.search(dax, match.start() + len(replacement))
    return dax


def _convert_running_functions(dax, table_name):
    """Convert RUNNING_SUM/AVG/COUNT/MAX/MIN → CALCULATE with window spec.
    
    These Tableau table calculations produce running aggregates.
    In DAX, they map to cumulative patterns using CALCULATE + FILTER + ALLSELECTED.
    """
    running_map = {
        'RUNNING_SUM': 'SUM',
        'RUNNING_AVG': 'AVERAGE',
        'RUNNING_COUNT': 'COUNT',
        'RUNNING_MAX': 'MAX',
        'RUNNING_MIN': 'MIN',
    }
    for tab_func, dax_agg in running_map.items():
        pattern = _get_func_pattern(tab_func)
        match = pattern.search(dax)
        while match:
            start_pos = match.end()
            depth = 1
            i = start_pos
            while i < len(dax) and depth > 0:
                if dax[i] == '(':
                    depth += 1
                elif dax[i] == ')':
                    depth -= 1
                i += 1
            inner = dax[start_pos:i - 1].strip()
            # Generate cumulative DAX pattern
            replacement = (
                f"CALCULATE({inner}, "
                f"FILTER(ALLSELECTED('{table_name}'), TRUE())) "
                f"/* {tab_func}: converted to cumulative — verify window scope */"
            )
            dax = dax[:match.start()] + replacement + dax[i:]
            match = pattern.search(dax)
    return dax


def _convert_total_function(dax, table_name):
    """Convert TOTAL(expr) → CALCULATE(expr, ALL('table')).
    
    TOTAL() in Tableau returns the grand total of an expression,
    ignoring the current partition. This maps to CALCULATE + ALL.
    """
    pattern = _RE_TOTAL
    match = pattern.search(dax)
    while match:
        start_pos = match.end()
        depth = 1
        i = start_pos
        while i < len(dax) and depth > 0:
            if dax[i] == '(':
                depth += 1
            elif dax[i] == ')':
                depth -= 1
            i += 1
        inner = dax[start_pos:i - 1].strip()
        replacement = f"CALCULATE({inner}, ALL('{table_name}'))"
        dax = dax[:match.start()] + replacement + dax[i:]
        match = pattern.search(dax)
    return dax


# ── Phase 5: Column resolution ───────────────────────────────────────────────

def _resolve_columns(dax, table_name, column_table_map, measure_names,
                     is_calc_column, param_values, table_columns=None):
    """Resolve [col] → 'Table'[col] with cross-table RELATED() support.

    When *table_columns* is provided (set of column names belonging to the
    current table), a column that exists in the current table is always
    treated as a same-table reference — even if ``column_table_map`` maps
    it to a different table (which can happen when multiple datasources
    share table names and their columns are merged).
    """
    _local_cols = table_columns or set()

    def _dax_escape_col(col_name):
        return col_name.replace(']', ']]')
    
    def _resolve_col_name(col):
        reversed_name = _reverse_tableau_bracket_escape(col)
        if reversed_name != col and reversed_name in column_table_map:
            return reversed_name
        # Salesforce connector pattern: Tableau uses CamelCase-split display
        # names like "First Name" but actual columns are "FirstName (Table)".
        # Try matching col without spaces, with table suffix preferred.
        no_space = col.replace(' ', '')
        if no_space != col:
            # Prefer current table's suffixed column
            suffixed = f'{no_space} ({table_name})'
            if suffixed in column_table_map:
                return suffixed
            # Fall back to any table's matching column
            for candidate in column_table_map:
                base = candidate.split(' (')[0] if ' (' in candidate else candidate
                if base == no_space:
                    return candidate
        return col
    
    def resolve_column(m):
        raw_col = m.group(1)
        col = _resolve_col_name(raw_col)
        # Inline literal-only calc values in calc column expressions first,
        # before measure_names or column_table_map checks.
        if is_calc_column and col in param_values:
            return param_values[col]
        if col in measure_names:
            return f'[{_dax_escape_col(col)}]'
        if col in column_table_map:
            col_table = column_table_map[col]
            # If the column also belongs to the current table, prefer
            # same-table reference to avoid spurious RELATED/LOOKUPVALUE.
            if col in _local_cols:
                col_table = table_name
            if is_calc_column and col_table != table_name:
                return f"RELATED('{col_table}'[{_dax_escape_col(col)}])"
            return f"'{col_table}'[{_dax_escape_col(col)}]"
        return f"'{table_name}'[{_dax_escape_col(col)}]"
    
    # Apply column resolution ONLY outside of string literals ("..." in DAX)
    # to avoid mangling regex patterns or other bracketed content inside strings.
    parts = re.split(r'("(?:[^"\\]|\\.)*")', dax)
    resolved = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            # Inside a double-quoted string literal — keep as-is
            resolved.append(part)
        else:
            resolved.append(_RE_COLUMN_RESOLVE.sub(resolve_column, part))
    return ''.join(resolved)


# ── Phase 5h: Wrap bare column refs in measures ──────────────────────────────

# Functions that provide row context or accept bare column arguments.
# A bare 'Table'[Col] inside any of these is valid — do NOT wrap.
_MEASURE_AGG_RE = re.compile(
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
_MEASURE_TABLE_COL_RE = re.compile(r"'((?:[^']|'')+)'\[([^\]]+)\]")


def _wrap_bare_column_refs_in_measure(dax, table_name, table_columns, measure_names,
                                       bool_columns=None):
    """Wrap bare same-table column refs in MAX() for measure context.

    In a measure, a bare 'Table'[Col] that is not inside an aggregation or
    iterator function causes PBI to error with 'single value cannot be
    determined'.  This wraps such refs in MAX(), which is safe for
    LOD-derived calculated columns (they have one value per filter context).

    For Boolean columns, MAX() is invalid in DAX — wrap with
    MAXX('Table', IF(col, 1, 0)) instead, converting TRUE/FALSE to 1/0.

    Only wraps refs that:
    - Point to the current table
    - Refer to a known column (not a measure)
    - Are NOT already inside an aggregation/iterator/time-intel function
    """
    refs = list(_MEASURE_TABLE_COL_RE.finditer(dax))
    if not refs:
        return dax

    _bool_cols = bool_columns or set()
    result = dax
    for ref_match in reversed(refs):
        ref_table = ref_match.group(1).replace("''", "'")
        ref_col = ref_match.group(2)

        if ref_table != table_name:
            continue
        if ref_col in measure_names:
            continue
        if ref_col not in table_columns:
            continue

        # Backward paren walk to check if inside any aggregation function
        prefix = result[:ref_match.start()]
        inside_agg = False
        depth = 0
        for i in range(len(prefix) - 1, -1, -1):
            if prefix[i] == ')':
                depth += 1
            elif prefix[i] == '(':
                if depth > 0:
                    depth -= 1
                else:
                    # Extract function name immediately before '(' —
                    # check ONLY that name, not the entire prefix.
                    func_prefix = prefix[:i].rstrip()
                    fname_m = re.search(r'(\w+)\s*$', func_prefix)
                    if fname_m and _MEASURE_AGG_RE.search(fname_m.group(1) + '('):
                        inside_agg = True
                        break
        if inside_agg:
            continue

        ref_text = ref_match.group(0)
        tbl_esc = table_name.replace("'", "''")
        if ref_col in _bool_cols:
            wrap = f"MAXX('{tbl_esc}', IF({ref_text}, 1, 0))"
        else:
            wrap = f'MAX({ref_text})'
        result = (result[:ref_match.start()] +
                  wrap +
                  result[ref_match.end():])

    return result


# ── Phase 5b: AGG(IF) → AGGX ─────────────────────────────────────────────────

def _convert_agg_if_to_aggx(dax_text, table_name):
    """Convert SUM(IF(...)), AVERAGE(IF(...)), etc. to SUMX, AVERAGEX, etc."""
    agg_map = {
        'SUM': 'SUMX', 'AVERAGE': 'AVERAGEX', 'AVG': 'AVERAGEX',
        'MIN': 'MINX', 'MAX': 'MAXX', 'COUNT': 'COUNTX'
    }
    for agg, aggx in agg_map.items():
        pattern = re.compile(r'\b' + agg + r'\s*\(\s*(IF|SWITCH)\s*\(', re.IGNORECASE)
        m = pattern.search(dax_text)
        while m:
            start = m.start()
            paren_pos = dax_text.index('(', start)
            depth = 1
            pos = paren_pos + 1
            while pos < len(dax_text) and depth > 0:
                if dax_text[pos] == '(':
                    depth += 1
                elif dax_text[pos] == ')':
                    depth -= 1
                pos += 1
            if depth == 0:
                inner = dax_text[paren_pos + 1:pos - 1]
                iter_table = _infer_iteration_table(inner, table_name)
                inner = _wrap_cross_table_related(inner, iter_table)
                replacement = f"{aggx}('{iter_table}', {inner})"
                dax_text = dax_text[:start] + replacement + dax_text[pos:]
            m = pattern.search(dax_text, start + len(aggx))

    # DISTINCTCOUNT has no AGGX variant — convert to CALCULATE+FILTER.
    dax_text = _convert_distinctcount_if(dax_text, table_name)

    return dax_text


def _split_if_args(if_content):
    """Split a balanced IF argument string into (condition, value, else).

    Returns ``(condition, value_col, else_expr)`` or ``None`` on failure.
    The *else_expr* may be ``None`` if no third argument exists.
    """
    depth = 0
    args = []
    start = 0
    for i, ch in enumerate(if_content):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ',' and depth == 0:
            args.append(if_content[start:i].strip())
            start = i + 1
    args.append(if_content[start:].strip())
    if len(args) < 2:
        return None
    return (args[0], args[1], args[2] if len(args) > 2 else None)


def _convert_distinctcount_if(dax_text, table_name):
    """Convert DISTINCTCOUNT(IF(cond, [col], BLANK())) to CALCULATE pattern.

    DISTINCTCOUNT only accepts a single column reference, so
    ``DISTINCTCOUNT(IF(cond, [col], BLANK()))`` must become
    ``CALCULATE(DISTINCTCOUNT([col]), FILTER('table', cond))``.
    """
    pattern = re.compile(
        r'\bDISTINCTCOUNT\s*\(\s*IF\s*\(', re.IGNORECASE
    )
    m = pattern.search(dax_text)
    while m:
        # Find outer DISTINCTCOUNT( balanced paren
        outer_start = m.start()
        paren_pos = dax_text.index('(', outer_start)
        depth = 1
        pos = paren_pos + 1
        while pos < len(dax_text) and depth > 0:
            if dax_text[pos] == '(':
                depth += 1
            elif dax_text[pos] == ')':
                depth -= 1
            pos += 1
        if depth != 0:
            break
        # inner = "IF(cond, col, BLANK())"
        inner = dax_text[paren_pos + 1:pos - 1].strip()
        # Extract IF arguments: strip outer IF(...)
        if_match = re.match(r'IF\s*\(', inner, re.IGNORECASE)
        if not if_match:
            break
        if_start = if_match.end()
        # Find balanced close of IF(
        if_depth = 1
        if_pos = if_start
        while if_pos < len(inner) and if_depth > 0:
            if inner[if_pos] == '(':
                if_depth += 1
            elif inner[if_pos] == ')':
                if_depth -= 1
            if_pos += 1
        if if_depth != 0:
            break
        if_content = inner[if_start:if_pos - 1]
        parsed = _split_if_args(if_content)
        if parsed is None:
            break
        condition, value_col, _ = parsed
        iter_table = _infer_iteration_table(
            if_content, table_name)
        replacement = (
            f"CALCULATE(DISTINCTCOUNT({value_col}), "
            f"FILTER('{iter_table}', {condition}))"
        )
        dax_text = dax_text[:outer_start] + replacement + dax_text[pos:]
        m = pattern.search(dax_text, outer_start + len(replacement))
    return dax_text


# ── Phase 5c: AGG(multi-col) → AGGX ──────────────────────────────────────────

def _unwrap_inner_agg(inner):
    """If *inner* is a simple ``AGG(expr)`` call, return *expr*; else ``None``.

    Handles nested parentheses correctly by matching balanced parens.
    Only unwraps when the AGG call spans the entire string (no trailing text).
    """
    agg_funcs = ['SUM', 'AVERAGE', 'AVG', 'MIN', 'MAX', 'COUNT']
    for func in agg_funcs:
        m = re.match(r'\b' + func + r'\s*\(', inner, re.IGNORECASE)
        if m:
            paren_start = m.end() - 1
            depth = 1
            pos = paren_start + 1
            while pos < len(inner) and depth > 0:
                if inner[pos] == '(':
                    depth += 1
                elif inner[pos] == ')':
                    depth -= 1
                pos += 1
            # Only unwrap if there's nothing after the closing paren
            if depth == 0 and pos == len(inner):
                return inner[paren_start + 1:pos - 1].strip()
    return None


def _convert_agg_expr_to_aggx(dax_text, table_name):
    """Convert SUM(expr), AVERAGE(expr), etc. to SUMX, AVERAGEX when expr is
    not a single column reference.

    DAX SUM/AVERAGE/MIN/MAX/COUNT only accept a single column.
    Expressions like  SUM('T'[a] * 'T'[b])  must become  SUMX('T', 'T'[a] * 'T'[b]).

    Statistical functions (STDEV.S, STDEV.P, MEDIAN) are also converted to
    their iterator forms (STDEVX.S, STDEVX.P, MEDIANX).  When a statistical
    function wraps another aggregation — e.g. ``STDEV.S(SUM(qty*price))`` —
    the inner aggregation is *unwrapped* because the iterator already provides
    row context, yielding ``STDEVX.S('T', qty*price)``.
    """

    def _is_single_column(expr):
        """True when *expr* is a bare column reference like 'T'[Col] or [Col]."""
        if re.match(r"^'[^']*'\[[^\]]*\]$", expr):
            return True
        if re.match(r"^\[[^\]]*\]$", expr):
            return True
        return False

    def _process_map(dax, mapping, unwrap_inner_agg=False):
        for agg, aggx in mapping.items():
            pattern = _get_func_pattern(agg)
            matches = list(pattern.finditer(dax))
            for m in reversed(matches):
                end_of_word = m.end() - 1  # position of '('
                word_start = m.start()
                word_text = dax[word_start:end_of_word].strip()
                if word_text.upper() != agg.upper():
                    continue

                paren_start = end_of_word
                depth = 1
                pos = paren_start + 1
                while pos < len(dax) and depth > 0:
                    if dax[pos] == '(':
                        depth += 1
                    elif dax[pos] == ')':
                        depth -= 1
                    pos += 1
                if depth != 0:
                    continue

                inner = dax[paren_start + 1:pos - 1].strip()

                if _is_single_column(inner):
                    continue

                # For statistical iterators, collapse a redundant inner agg:
                #   STDEV.S(SUM(a*b)) → STDEVX.S('T', a*b)
                if unwrap_inner_agg:
                    unwrapped = _unwrap_inner_agg(inner)
                    if unwrapped is not None:
                        inner = unwrapped

                iter_table = _infer_iteration_table(inner, table_name)
                inner = _wrap_cross_table_related(inner, iter_table)
                replacement = f"{aggx}('{iter_table}', {inner})"
                dax = dax[:m.start()] + replacement + dax[pos:]
        return dax

    # Step 1: Statistical aggregates (process FIRST so that their inner
    #         SUM/AVERAGE/etc. hasn't been converted to SUMX yet).
    stat_to_statx = {
        'STDEV.S': 'STDEVX.S', 'STDEV.P': 'STDEVX.P',
        'MEDIAN': 'MEDIANX',
    }
    dax_text = _process_map(dax_text, stat_to_statx, unwrap_inner_agg=True)

    # Step 2: Basic aggregation (SUM → SUMX, etc.)
    agg_to_aggx = {
        'SUM': 'SUMX', 'AVERAGE': 'AVERAGEX',
        'MIN': 'MINX', 'MAX': 'MAXX', 'COUNT': 'COUNTX',
    }
    dax_text = _process_map(dax_text, agg_to_aggx)

    return dax_text


# ── Phase 6: Cleanup ─────────────────────────────────────────────────────────

def _normalize_spaces_outside_identifiers(text):
    """Normalize multiple spaces except inside [identifiers] and 'names'."""
    result = []
    i = 0
    while i < len(text):
        if text[i] == '[':
            close = ']'
            j = text.index(close, i + 1) + 1 if close in text[i + 1:] else len(text)
            result.append(text[i:j])
            i = j
        elif text[i] == "'":
            # Handle single-quoted table names, skipping escaped '' pairs
            j = i + 1
            while j < len(text):
                if text[j] == "'":
                    if j + 1 < len(text) and text[j + 1] == "'":
                        j += 2  # skip escaped ''
                    else:
                        j += 1  # closing quote
                        break
                else:
                    j += 1
            result.append(text[i:j])
            i = j
        elif text[i] in (' ', '\t'):
            j = i
            while j < len(text) and text[j] in (' ', '\t'):
                j += 1
            result.append(' ')
            i = j
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


# ── Utility ───────────────────────────────────────────────────────────────────

def _split_args(inner):
    """Split function arguments respecting nested parentheses and string literals."""
    args = []
    depth = 0
    current = []
    in_string = False
    string_char = None
    for ch in inner:
        if in_string:
            current.append(ch)
            if ch == string_char:
                in_string = False
                string_char = None
        elif ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            current.append(ch)
        elif ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            args.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append(''.join(current).strip())
    return args


def generate_combined_field_dax(source_fields, table_name, separator=' '):
    """Generate DAX expression for a combined field (CONCATENATE of multiple columns).
    
    Args:
        source_fields: List of source column names
        table_name: Table containing the columns
        separator: Separator between values (default: space)
    
    Returns:
        str: DAX calculated column expression
    """
    if not source_fields:
        return '""'
    if len(source_fields) == 1:
        return f"'{table_name}'[{source_fields[0]}]"
    parts = [f"'{table_name}'[{f}]" for f in source_fields]
    sep_literal = f'"{separator}"'
    # Use nested CONCATENATE pairs for 2 fields, or & for more
    if len(parts) == 2:
        return f"{parts[0]} & {sep_literal} & {parts[1]}"
    return (' & ' + sep_literal + ' & ').join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCRIPT_* Analytics Extension Detection
# ═══════════════════════════════════════════════════════════════════════════════

_RE_SCRIPT_CALL = re.compile(
    r'\b(SCRIPT_(?:BOOL|INT|REAL|STR))\s*\(\s*"((?:[^"\\]|\\.)*)"\s*,',
    re.IGNORECASE | re.DOTALL,
)


def detect_script_functions(formula):
    """Detect SCRIPT_* analytics extension calls in a Tableau formula.

    Args:
        formula: Raw Tableau calculation formula string.

    Returns:
        list[dict]: One entry per SCRIPT_* call with keys:
            - ``function``: e.g. ``"SCRIPT_REAL"``
            - ``language``: ``"python"`` or ``"r"`` (heuristic)
            - ``code``: The embedded script source string.
            - ``return_type``: ``"bool"``, ``"int"``, ``"real"``, or ``"str"``.
    """
    if not formula:
        return []

    results = []
    for m in _RE_SCRIPT_CALL.finditer(formula):
        func_name = m.group(1).upper()
        raw_code = m.group(2).replace('\\"', '"').replace('\\n', '\n')

        # Heuristic: detect language from script content
        language = _detect_script_language(raw_code)

        type_suffix = func_name.split('_')[1].lower()
        results.append({
            'function': func_name,
            'language': language,
            'code': raw_code,
            'return_type': type_suffix,
        })
    return results


def _detect_script_language(code):
    """Heuristic to detect if a script is Python or R.

    Checks for common language-specific markers.

    Returns:
        ``"python"`` or ``"r"``.
    """
    python_markers = ['import ', 'def ', 'pandas', 'numpy', 'print(', 'elif ',
                      'return ', 'lambda ', '__', '.append(', '.items()',
                      'pd.', 'np.', 'from ']
    r_markers = ['<-', 'library(', 'c(', 'data.frame(', 'ggplot', 'dplyr',
                 'tidyr', 'sapply(', 'lapply(', 'function(', 'nrow(',
                 'ncol(', 'paste0(', '%>%', 'data.table']

    code_lower = code.lower()
    py_score = sum(1 for m in python_markers if m.lower() in code_lower)
    r_score = sum(1 for m in r_markers if m.lower() in code_lower)

    return 'python' if py_score >= r_score else 'r'


def has_script_functions(formula):
    """Return True if the formula contains any SCRIPT_* function call."""
    if not formula:
        return False
    return bool(_RE_SCRIPT_CALL.search(formula))
