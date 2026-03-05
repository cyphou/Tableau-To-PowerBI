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
    (r'\bATTR\s*\(', 'SELECTEDVALUE('),

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
    (r'\bDATEADD\s*\(', 'DATEADD('),
    (r'\bTODAY\s*\(\s*\)', 'TODAY()'),
    (r'\bNOW\s*\(\s*\)', 'NOW()'),
    # DATENAME handled by _convert_datename (needs format string arg)
    # DATEPARSE handled by _convert_dateparse (needs value extraction)
    (r'\bMAKEDATE\s*\(', 'DATE('),
    (r'\bMAKEDATETIME\s*\(', 'DATE('),
    (r'\bMAKETIME\s*\(', 'TIME('),

    # Text functions
    (r'\bTRIM\s*\(', 'TRIM('),
    (r'\bLTRIM\s*\(', 'TRIM('),
    (r'\bRTRIM\s*\(', 'TRIM('),
    (r'\bLEN\s*\(', 'LEN('),
    (r'\bLEFT\s*\(', 'LEFT('),
    (r'\bRIGHT\s*\(', 'RIGHT('),
    (r'\bMID\s*\(', 'MID('),
    (r'\bUPPER\s*\(', 'UPPER('),
    (r'\bLOWER\s*\(', 'LOWER('),
    (r'\bREPLACE\s*\(', 'SUBSTITUTE('),
    (r'\bSPACE\s*\(', 'REPT(" ", '),
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

    # Regex approximation
    (r'\bREGEXP_MATCH\s*\(', 'CONTAINSSTRING('),
    (r'\bREGEXP_REPLACE\s*\(', 'SUBSTITUTE('),
    (r'\bREGEXP_EXTRACT_NTH\s*\(', '/* REGEXP_EXTRACT_NTH: no DAX regex — manual conversion needed */ CONTAINSSTRING('),
    (r'\bREGEXP_EXTRACT\s*\(', 'CONTAINSSTRING('),

    # Spatial functions (no DAX equivalent)
    (r'\bMAKEPOINT\s*\(', '/* MAKEPOINT: no DAX spatial equivalent */ BLANK( /*'),
    (r'\bMAKELINE\s*\(', '/* MAKELINE: no DAX spatial equivalent */ BLANK( /*'),
    (r'\bDISTANCE\s*\(', '/* DISTANCE: no DAX spatial equivalent */ 0 + ( /*'),
    (r'\bBUFFER\s*\(', '/* BUFFER: no DAX spatial equivalent */ BLANK( /*'),
    (r'\bAREA\s*\(', '/* AREA: no DAX spatial equivalent */ 0 + ( /*'),
    (r'\bINTERSECTION\s*\(', '/* INTERSECTION: no DAX spatial equivalent */ BLANK( /*'),
    (r'\bHEXBINX\s*\(', '/* HEXBINX: no DAX equivalent */ 0 + ( /*'),
    (r'\bHEXBINY\s*\(', '/* HEXBINY: no DAX equivalent */ 0 + ( /*'),

    # Table calculations — RUNNING_* already wraps an aggregation, so just add CALCULATE
    (r'\bRUNNING_SUM\s*\(', 'CALCULATE('),
    (r'\bRUNNING_AVG\s*\(', 'CALCULATE('),
    (r'\bRUNNING_COUNT\s*\(', 'CALCULATE('),
    (r'\bRUNNING_MAX\s*\(', 'CALCULATE('),
    (r'\bRUNNING_MIN\s*\(', 'CALCULATE('),
    # RANK/RANK_UNIQUE/RANK_DENSE/RANK_MODIFIED/RANK_PERCENTILE handled by _convert_rank_functions
    (r'\bINDEX\s*\(\s*\)', 'RANKX(ALL(), [Value])'),
    (r'\bFIRST\s*\(\s*\)', '0'),
    (r'\bLAST\s*\(\s*\)', '0'),
    (r'\bTOTAL\s*\(', 'CALCULATE('),
    (r'\bPREVIOUS_VALUE\s*\(', '/* PREVIOUS_VALUE: manual conversion needed */ ('),
    (r'\bLOOKUP\s*\(', '/* LOOKUP: use LOOKUPVALUE */ LOOKUPVALUE('),
    (r'\bSIZE\s*\(\s*\)', 'COUNTROWS()'),

    # Additional WINDOW_* table calculations
    (r'\bWINDOW_MEDIAN\s*\(', 'CALCULATE(MEDIAN('),
    (r'\bWINDOW_STDEVP\s*\(', 'CALCULATE(STDEV.P('),
    (r'\bWINDOW_STDEV\s*\(', 'CALCULATE(STDEV.S('),
    (r'\bWINDOW_VARP\s*\(', 'CALCULATE(VAR.P('),
    (r'\bWINDOW_VAR\s*\(', 'CALCULATE(VAR.S('),
    (r'\bWINDOW_CORR\s*\(', '/* WINDOW_CORR: no DAX equivalent */ 0 + ('),
    (r'\bWINDOW_COVAR\s*\(', '/* WINDOW_COVAR: no DAX equivalent */ 0 + ('),
    (r'\bWINDOW_COVARP\s*\(', '/* WINDOW_COVARP: no DAX equivalent */ 0 + ('),
    (r'\bWINDOW_PERCENTILE\s*\(', 'CALCULATE(PERCENTILE.INC('),

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
                                    calc_datatype=None, partition_fields=None):
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
    
    dax = formula.strip()
    
    # === Phase 1: Resolve Tableau references ===
    dax = _resolve_references(dax, calc_map, param_map, is_calc_column, param_values)
    
    # === Phase 2: Convert CASE/WHEN → SWITCH(), IF/THEN → IF() ===
    dax = _convert_case_structure(dax)
    dax = _convert_if_structure(dax)
    
    # === Phase 3: Convert Tableau functions → DAX ===
    
    # 3a. ISMEMBEROF (special — captures group name)
    dax = re.sub(
        r'\bISMEMBEROF\s*\(\s*["\']([^"\']+)["\']\s*\)',
        r'TRUE()  /* ISMEMBEROF("\1"): implement via RLS role */',
        dax, flags=re.IGNORECASE
    )
    
    # 3b-pre. Dedicated converters (functions needing special arg handling)
    dax = _convert_radians_degrees(dax)
    dax = _convert_find(dax)
    dax = _convert_str_to_format(dax)
    dax = _convert_float_to_convert(dax)
    dax = _convert_datename(dax)
    dax = _convert_dateparse(dax)
    dax = _convert_isdate(dax)
    dax = _convert_corr_covar(dax)
    dax = _convert_endswith(dax)
    dax = _convert_startswith(dax)
    dax = _convert_proper(dax)
    dax = _convert_split(dax)
    dax = _convert_atan2(dax)
    dax = _convert_div(dax)
    dax = _convert_square(dax)
    dax = _convert_iif(dax)

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
    dax = _convert_window_functions(dax, table_name, partition_fields)
    
    # 3f. RANK / RANK_UNIQUE / RANK_DENSE → RANKX
    dax = _convert_rank_functions(dax, table_name, partition_fields)
    
    # === Phase 4: Convert operators ===
    dax = dax.replace('!=', '<>')   # != before == to avoid partial match
    dax = dax.replace('==', '=')
    dax = re.sub(r'\bor\b', '||', dax, flags=re.IGNORECASE)
    dax = re.sub(r'\band\b', '&&', dax, flags=re.IGNORECASE)
    
    # === Phase 5: Resolve remaining columns [col] → 'Table'[col] ===
    dax = _resolve_columns(dax, table_name, column_table_map, measure_names,
                           is_calc_column, param_values)

    # === Phase 5a: Fix STARTOF* for calculated columns ===
    if is_calc_column:
        dax = _fix_startof_calc_columns(dax)

    # === Phase 5b: Convert AGG(IF(...)) → AGGX('table', IF(...)) ===
    dax = _convert_agg_if_to_aggx(dax, table_name)
    
    # === Phase 5c: Convert AGG(multi-col expr) → AGGX('table', expr) ===
    # DAX SUM/AVERAGE/MIN/MAX/COUNT only accept a single column.
    # Expressions like SUM('T'[a] * 'T'[b]) must use SUMX('T', 'T'[a] * 'T'[b]).
    dax = _convert_agg_expr_to_aggx(dax, table_name)
    
    # === Phase 6: Final cleanup ===
    dax = _normalize_spaces_outside_identifiers(dax).strip()
    dax = re.sub(r'[\r\n]+\s*', ' ', dax)

    # === Phase 6b: Fix date literals ===
    dax = _fix_date_literals(dax)

    # === Phase 7: String concatenation ===
    if calc_datatype == 'string':
        dax = _convert_string_concat(dax)

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
    dax = re.sub(r'\[Parameters\]\.\[([^\]]+)\]', resolve_param, dax)
    
    # [Calculation_xxx] → [caption]
    def resolve_calc(m):
        ref = m.group(1)
        if ref in calc_map:
            return f'[{calc_map[ref]}]'
        return m.group(0)
    dax = re.sub(r'\[([^\]]+)\]', resolve_calc, dax)
    
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
        text = re.sub(r'\bELSEIF\b', 'ELSE IF', text, flags=re.IGNORECASE)
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


def _convert_zn(dax):
    """ZN(expr) → IF(ISBLANK(expr), 0, expr)"""
    def _zn_repl(m):
        arg = m.group(1)
        return f'IF(ISBLANK({arg}), 0, {arg})'
    return re.sub(r'\bZN\s*\(([^)]+)\)', _zn_repl, dax, flags=re.IGNORECASE)


def _convert_ifnull(dax):
    """IFNULL(a, b) → IF(ISBLANK(a), b, a)"""
    def _ifnull_repl(m):
        parts = m.group(1).split(',', 1)
        if len(parts) == 2:
            return f'IF(ISBLANK({parts[0].strip()}), {parts[1].strip()}, {parts[0].strip()})'
        return m.group(0)
    return re.sub(r'\bIFNULL\s*\(([^)]+)\)', _ifnull_repl, dax, flags=re.IGNORECASE)


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
    dax = re.sub(r'\bFINDNTH\s*\(', 'FIND(', dax, flags=re.IGNORECASE)
    pattern = re.compile(r'\bFIND\s*\(', re.IGNORECASE)
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


def _convert_corr_covar(dax):
    """Convert CORR/COVAR/COVARP to proper DAX using VAR/iterator patterns.

    CORR(x, y) → Pearson correlation using VAR + SUMX pattern
    COVAR(x, y) → sample covariance using VAR + SUMX pattern
    COVARP(x, y) → population covariance using VAR + SUMX pattern
    """
    for tab_func in ['CORR', 'COVARP', 'COVAR']:
        pattern = re.compile(r'\b' + tab_func + r'\s*\(', re.IGNORECASE)
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
                    replacement = _build_corr_covar_dax(tab_func.upper(), x_expr, y_expr)
                else:
                    # Fallback if can't parse args
                    replacement = f'0 /* {tab_func}({inner}): could not parse arguments */'
                dax = dax[:match.start()] + replacement + dax[i:]
                match = pattern.search(dax, match.start() + len(replacement))
            else:
                break
    return dax


def _build_corr_covar_dax(func_name, x_expr, y_expr):
    """Build DAX expression for correlation/covariance using VAR/iterator pattern.

    Uses SUMX over ALL() rows with deviation-from-mean calculations.
    """
    if func_name == 'CORR':
        # Pearson correlation: Σ((x-μx)(y-μy)) / √(Σ(x-μx)² × Σ(y-μy)²)
        return (
            f'VAR _MeanX = AVERAGEX(ALL(\'Table\'), {x_expr}) '
            f'VAR _MeanY = AVERAGEX(ALL(\'Table\'), {y_expr}) '
            f'VAR _Cov = SUMX(ALL(\'Table\'), ({x_expr} - _MeanX) * ({y_expr} - _MeanY)) '
            f'VAR _StdX = SQRT(SUMX(ALL(\'Table\'), ({x_expr} - _MeanX) ^ 2)) '
            f'VAR _StdY = SQRT(SUMX(ALL(\'Table\'), ({y_expr} - _MeanY) ^ 2)) '
            f'RETURN DIVIDE(_Cov, _StdX * _StdY, 0)'
        )
    elif func_name == 'COVARP':
        # Population covariance: Σ((x-μx)(y-μy)) / N
        return (
            f'VAR _MeanX = AVERAGEX(ALL(\'Table\'), {x_expr}) '
            f'VAR _MeanY = AVERAGEX(ALL(\'Table\'), {y_expr}) '
            f'VAR _N = COUNTROWS(ALL(\'Table\')) '
            f'RETURN DIVIDE(SUMX(ALL(\'Table\'), ({x_expr} - _MeanX) * ({y_expr} - _MeanY)), _N, 0)'
        )
    else:  # COVAR — sample covariance
        # Sample covariance: Σ((x-μx)(y-μy)) / (N-1)
        return (
            f'VAR _MeanX = AVERAGEX(ALL(\'Table\'), {x_expr}) '
            f'VAR _MeanY = AVERAGEX(ALL(\'Table\'), {y_expr}) '
            f'VAR _N = COUNTROWS(ALL(\'Table\')) '
            f'RETURN DIVIDE(SUMX(ALL(\'Table\'), ({x_expr} - _MeanX) * ({y_expr} - _MeanY)), _N - 1, 0)'
        )


# ── Generic function-call transformer ─────────────────────────────────────────

def _transform_func_call(dax, func_name, transformer_fn):
    """Generic: find func_name(...), extract balanced args, apply transformer_fn.

    *transformer_fn* receives (args_list, raw_inner_str) and must return
    the replacement string.  The function handles nested parentheses and
    iterates until no more matches are found.
    """
    pattern = re.compile(re.escape(func_name) + r'\s*\(', re.IGNORECASE)
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
    """PROPER(string) → UPPER(LEFT()) & LOWER(MID())."""
    def _xf(args, inner):
        s = inner.strip()
        return f'UPPER(LEFT({s}, 1)) & LOWER(MID({s}, 2, LEN({s})))'
    return _transform_func_call(dax, 'PROPER', _xf)


def _convert_split(dax):
    """SPLIT(string, delimiter, token_number) → placeholder (no direct DAX split)."""
    def _xf(args, inner):
        return f'/* SPLIT({inner}): no direct DAX equivalent — use PATHITEM with SUBSTITUTE or manual parsing */ BLANK()'
    return _transform_func_call(dax, 'SPLIT', _xf)


def _convert_atan2(dax):
    """ATAN2(y, x) → ATAN(y/x) with quadrant handling."""
    def _xf(args, inner):
        if len(args) >= 2:
            return f'ATAN({args[0].strip()} / {args[1].strip()}) /* ATAN2: verify quadrant handling */'
        return f'ATAN2({inner})'
    return _transform_func_call(dax, 'ATAN2', _xf)


def _convert_div(dax):
    """DIV(integer1, integer2) → QUOTIENT(integer1, integer2)"""
    return _transform_func_call(dax, 'DIV', lambda args, inner: f'QUOTIENT({inner})')


def _convert_square(dax):
    """SQUARE(number) → POWER(number, 2)"""
    return _transform_func_call(dax, 'SQUARE', lambda args, inner: f'POWER({inner.strip()}, 2)')


def _convert_dateparse(dax):
    """DATEPARSE(format, string) → DATEVALUE(string) — format ignored in DAX."""
    def _xf(args, inner):
        return f'DATEVALUE({args[1].strip()})' if len(args) >= 2 else f'DATEVALUE({inner})'
    return _transform_func_call(dax, 'DATEPARSE', _xf)


def _convert_isdate(dax):
    """ISDATE(string) → NOT(ISERROR(DATEVALUE(string)))"""
    return _transform_func_call(dax, 'ISDATE', lambda args, inner: f'NOT(ISERROR(DATEVALUE({inner.strip()})))')


def _convert_iif(dax):
    """IIF(test, then, else, [unknown]) → IF(test, then, else)"""
    def _xf(args, inner):
        if len(args) >= 3:
            return f'IF({args[0].strip()}, {args[1].strip()}, {args[2].strip()})'
        if len(args) == 2:
            return f'IF({args[0].strip()}, {args[1].strip()}, BLANK())'
        return f'IIF({inner})'
    return _transform_func_call(dax, 'IIF', _xf)


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
    return re.sub(r'#(\d{4})-(\d{2})-(\d{2})#', _date_repl, dax)


def _convert_string_concat(dax):
    """Convert Tableau + to DAX & for string concatenation.

    Only converts + at parenthesis depth 0 (top-level) so that arithmetic +
    inside function arguments (e.g. FIND(...) + 1) is preserved.
    """
    result = []
    depth = 0
    in_string = False
    i = 0
    while i < len(dax):
        ch = dax[i]
        if in_string:
            result.append(ch)
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == '+' and depth == 0:
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
    return max(counts, key=lambda k: counts[k])


def _convert_lod_expressions(dax, table_name, column_table_map):
    """Convert LOD expressions: {FIXED/INCLUDE/EXCLUDE dims : AGG} → CALCULATE."""
    
    def _resolve_dims(dims_str, default_table):
        dims = [d.strip().strip('[]') for d in dims_str.split(',') if d.strip()]
        refs = []
        for d in dims:
            t = column_table_map.get(d, default_table)
            refs.append(f"'{t}'[{d}]")
        return dims, refs
    
    def _lod_fixed(m):
        dims, dim_refs = _resolve_dims(m.group(1).strip(), table_name)
        agg_expr = m.group(2).strip()
        if dim_refs:
            allexcept_table = column_table_map.get(dims[0], table_name)
            return f"CALCULATE({agg_expr}, ALLEXCEPT('{allexcept_table}', {', '.join(dim_refs)}))"
        return f"CALCULATE({agg_expr}, ALL('{table_name}'))"
    
    def _lod_include(m):
        return f"CALCULATE({m.group(2).strip()})"
    
    def _lod_exclude(m):
        dims, dim_refs = _resolve_dims(m.group(1).strip(), table_name)
        agg_expr = m.group(2).strip()
        if dim_refs:
            return f"CALCULATE({agg_expr}, REMOVEFILTERS({', '.join(dim_refs)}))"
        return f"CALCULATE({agg_expr})"
    
    dax = re.sub(r'\{\s*FIXED\s+(.*?)\s*:\s*(.*?)\s*\}', _lod_fixed,
                 dax, flags=re.IGNORECASE | re.DOTALL)
    dax = re.sub(r'\{\s*INCLUDE\s+(.*?)\s*:\s*(.*?)\s*\}', _lod_include,
                 dax, flags=re.IGNORECASE | re.DOTALL)
    dax = re.sub(r'\{\s*EXCLUDE\s+(.*?)\s*:\s*(.*?)\s*\}', _lod_exclude,
                 dax, flags=re.IGNORECASE | re.DOTALL)
    
    # LOD without dimension — use balanced brace matching (not global replace)
    _lod_no_dim_pattern = re.compile(
        r'\{\s*(SUM|AVG|AVERAGE|MIN|MAX|COUNT|COUNTD|MEDIAN)\s*\(',
        re.IGNORECASE
    )
    match = _lod_no_dim_pattern.search(dax)
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
            match = _lod_no_dim_pattern.search(dax, start + len(replacement))
        else:
            break
    
    return dax


def _convert_window_functions(dax, table_name, partition_fields=None):
    """Convert WINDOW_SUM/AVG/MAX/MIN/COUNT → CALCULATE(..., ALL/ALLEXCEPT).
    
    If partition_fields are provided (from COMPUTE USING addressing),
    uses ALLEXCEPT('table', partition_columns) to maintain partition context
    instead of blanket ALL('table').
    """
    if partition_fields:
        partition_cols = ", ".join(f"'{table_name}'[{f}]" for f in partition_fields)
        filter_expr = f"ALLEXCEPT('{table_name}', {partition_cols})"
    else:
        filter_expr = f"ALL('{table_name}')"
    
    for window_func in ['WINDOW_SUM', 'WINDOW_AVG', 'WINDOW_MAX', 'WINDOW_MIN', 'WINDOW_COUNT']:
        pattern = re.compile(rf'\b{window_func}\s*\(', re.IGNORECASE)
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
            replacement = f"CALCULATE({inner}, {filter_expr})"
            dax = dax[:match.start()] + replacement + dax[i:]
            match = pattern.search(dax)
    return dax


def _convert_rank_functions(dax, table_name, partition_fields=None):
    """Convert RANK(expr), RANK_UNIQUE(expr), RANK_DENSE(expr), RANK_MODIFIED(expr),
    RANK_PERCENTILE(expr) → RANKX(ALL/ALLEXCEPT('table'), expr) variants.
    
    If partition_fields are provided, uses ALLEXCEPT for partitioned ranking.
    """
    if partition_fields:
        partition_cols = ", ".join(f"'{table_name}'[{f}]" for f in partition_fields)
        all_expr = f"ALLEXCEPT('{table_name}', {partition_cols})"
    else:
        all_expr = f"ALL('{table_name}')"
    
    # Process longer names first to avoid partial matches
    for rank_func in ['RANK_PERCENTILE', 'RANK_MODIFIED', 'RANK_DENSE', 'RANK_UNIQUE', 'RANK']:
        pattern = re.compile(r'\b' + rank_func + r'\s*\(', re.IGNORECASE)
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
            if func_upper == 'RANK_DENSE':
                replacement = f"RANKX({all_expr}, {inner},, ASC, DENSE)"
            elif func_upper == 'RANK_MODIFIED':
                replacement = f"RANKX({all_expr}, {inner}) /* RANK_MODIFIED: uses competition ranking, verify */"
            elif func_upper == 'RANK_PERCENTILE':
                replacement = f"DIVIDE(RANKX({all_expr}, {inner}) - 1, COUNTROWS({all_expr}) - 1) /* RANK_PERCENTILE: approximate */"
            else:
                replacement = f"RANKX({all_expr}, {inner})"
            dax = dax[:match.start()] + replacement + dax[i:]
            match = pattern.search(dax, match.start() + len(replacement))
    return dax


# ── Phase 5: Column resolution ───────────────────────────────────────────────

def _resolve_columns(dax, table_name, column_table_map, measure_names,
                     is_calc_column, param_values):
    """Resolve [col] → 'Table'[col] with cross-table RELATED() support."""
    
    def _dax_escape_col(col_name):
        return col_name.replace(']', ']]')
    
    def _resolve_col_name(col):
        reversed_name = _reverse_tableau_bracket_escape(col)
        if reversed_name != col and reversed_name in column_table_map:
            return reversed_name
        return col
    
    def resolve_column(m):
        raw_col = m.group(1)
        col = _resolve_col_name(raw_col)
        if col in measure_names:
            if is_calc_column and col in param_values:
                return param_values[col]
            return f'[{_dax_escape_col(col)}]'
        if col in column_table_map:
            col_table = column_table_map[col]
            if is_calc_column and col_table != table_name:
                return f"RELATED('{col_table}'[{_dax_escape_col(col)}])"
            return f"'{col_table}'[{_dax_escape_col(col)}]"
        return f"'{table_name}'[{_dax_escape_col(col)}]"
    
    return re.sub(r"(?<!')\[([^\]]+)\]", resolve_column, dax)


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
                replacement = f"{aggx}('{iter_table}', {inner})"
                dax_text = dax_text[:start] + replacement + dax_text[pos:]
            m = pattern.search(dax_text, start + len(aggx))
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
            pattern = re.compile(r'\b' + re.escape(agg) + r'\s*\(', re.IGNORECASE)
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
        if text[i] in ("'", "["):
            close = "'" if text[i] == "'" else "]"
            j = text.index(close, i + 1) + 1 if close in text[i + 1:] else len(text)
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
    """Split function arguments respecting nested parentheses."""
    args = []
    depth = 0
    current = []
    for ch in inner:
        if ch == '(':
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
