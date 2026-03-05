"""
Module de conversion des Calculs Tableau vers DAX Power BI
"""

import re

def convert_calculation_to_measure(calculation):
    """
    Convertit un champ calculé Tableau en mesure DAX Power BI
    """
    
    calc_name = calculation.get('name', 'Unnamed Calculation')
    tableau_formula = calculation.get('formula', '')
    
    powerbi_measure = {
        'name': calc_name,
        'expression': convert_tableau_formula_to_dax(tableau_formula),
        'formatString': convert_format(calculation.get('format', '')),
        'description': calculation.get('comment', ''),
        'folder': calculation.get('folder', 'Calculations'),
    }
    
    return powerbi_measure


def convert_tableau_formula_to_dax(formula):
    """
    Convertit une formule Tableau complète en DAX
    
    Principales conversions:
    - Fonctions d'agrégation
    - Fonctions logiques
    - Fonctions de texte
    - Fonctions de date
    - Fonctions mathématiques
    - Table calculations (LOD expressions)
    """
    
    if not formula:
        return ''
    
    dax_formula = formula
    
    # Agrégations
    dax_formula = convert_aggregations(dax_formula)
    
    # Logique conditionnelle
    dax_formula = convert_logic(dax_formula)
    
    # Fonctions de texte
    dax_formula = convert_text_functions(dax_formula)
    
    # Fonctions de date
    dax_formula = convert_date_functions(dax_formula)
    
    # Fonctions mathématiques
    dax_formula = convert_math_functions(dax_formula)
    
    # LOD Expressions
    dax_formula = convert_lod_expressions(dax_formula)
    
    # Nettoyage final
    dax_formula = clean_formula(dax_formula)
    
    return dax_formula


def convert_aggregations(formula):
    """Convertit les fonctions d'agrégation"""
    
    conversions = {
        r'\bSUM\(': 'SUM(',
        r'\bAVG\(': 'AVERAGE(',
        r'\bMIN\(': 'MIN(',
        r'\bMAX\(': 'MAX(',
        r'\bCOUNT\(': 'COUNT(',
        r'\bCOUNTD\(': 'DISTINCTCOUNT(',
        r'\bMEDIAN\(': 'MEDIAN(',
        r'\bSTDEV\(': 'STDEV.P(',
        r'\bSTDEVP\(': 'STDEV.P(',
        r'\bVAR\(': 'VAR.P(',
        r'\bVARP\(': 'VAR.P(',
        r'\bATTR\(': 'VALUES(',  # ATTR -> VALUES (approximation)
    }
    
    for tableau_func, dax_func in conversions.items():
        formula = re.sub(tableau_func, dax_func, formula, flags=re.IGNORECASE)
    
    return formula


def convert_logic(formula):
    """Convertit les expressions logiques"""
    
    # IF THEN ELSE END -> IF()
    formula = re.sub(
        r'\bIF\b\s+(.+?)\s+\bTHEN\b\s+(.+?)\s+\bELSE\b\s+(.+?)\s+\bEND\b',
        r'IF(\1, \2, \3)',
        formula,
        flags=re.IGNORECASE | re.DOTALL
    )
    
    # CASE WHEN -> SWITCH
    formula = convert_case_when(formula)
    
    # Opérateurs logiques
    conversions = {
        r'\bAND\b': '&&',
        r'\bOR\b': '||',
        r'\bNOT\b': 'NOT',
        r'\bISNULL\(': 'ISBLANK(',
        r'\bIFNULL\(': 'IF(ISBLANK(',
        r'\bZN\(': 'IF(ISBLANK(',  # ZN -> Zero if Null
    }
    
    for tableau_op, dax_op in conversions.items():
        formula = re.sub(tableau_op, dax_op, formula, flags=re.IGNORECASE)
    
    return formula


def convert_case_when(formula):
    """Convertit CASE WHEN en SWITCH/IF imbriqués"""
    
    # Pattern CASE WHEN
    case_pattern = r'\bCASE\b\s+(.+?)\s+\bEND\b'
    
    def replace_case(match):
        case_content = match.group(1)
        
        # Extraire les clauses WHEN
        when_pattern = r'\bWHEN\b\s+(.+?)\s+\bTHEN\b\s+(.+?)(?=\s+\bWHEN\b|\s+\bELSE\b|\s+\bEND\b|$)'
        whens = re.findall(when_pattern, case_content, flags=re.IGNORECASE | re.DOTALL)
        
        # Extraire ELSE
        else_pattern = r'\bELSE\b\s+(.+?)$'
        else_match = re.search(else_pattern, case_content, flags=re.IGNORECASE | re.DOTALL)
        else_value = else_match.group(1).strip() if else_match else 'BLANK()'
        
        # Construire IF imbriqués
        result = else_value
        for condition, value in reversed(whens):
            result = f'IF({condition.strip()}, {value.strip()}, {result})'
        
        return result
    
    formula = re.sub(case_pattern, replace_case, formula, flags=re.IGNORECASE | re.DOTALL)
    
    return formula


def convert_text_functions(formula):
    """Convertit les fonctions de texte"""
    
    conversions = {
        r'\bLEN\(': 'LEN(',
        r'\bLEFT\(': 'LEFT(',
        r'\bRIGHT\(': 'RIGHT(',
        r'\bMID\(': 'MID(',
        r'\bUPPER\(': 'UPPER(',
        r'\bLOWER\(': 'LOWER(',
        r'\bTRIM\(': 'TRIM(',
        r'\bLTRIM\(': 'TRIM(',
        r'\bRTRIM\(': 'TRIM(',
        r'\bREPLACE\(': 'SUBSTITUTE(',
        r'\bCONTAINS\(': 'SEARCH(',
        r'\bSTARTSWITH\(': 'LEFT(',  # Approx
        r'\bENDSWITH\(': 'RIGHT(',  # Approx
        r'\bSPLIT\(': 'SPLIT(',  # Si disponible
        r'\b\+\b': ' & ',  # Concaténation string
    }
    
    for tableau_func, dax_func in conversions.items():
        formula = re.sub(tableau_func, dax_func, formula, flags=re.IGNORECASE)
    
    return formula


def convert_date_functions(formula):
    """Convertit les fonctions de date"""
    
    conversions = {
        r'\bYEAR\(': 'YEAR(',
        r'\bMONTH\(': 'MONTH(',
        r'\bDAY\(': 'DAY(',
        r'\bQUARTER\(': 'QUARTER(',
        r'\bWEEK\(': 'WEEKNUM(',
        r'\bWEEKDAY\(': 'WEEKDAY(',
        r'\bHOUR\(': 'HOUR(',
        r'\bMINUTE\(': 'MINUTE(',
        r'\bSECOND\(': 'SECOND(',
        r'\bNOW\(\)': 'NOW()',
        r'\bTODAY\(\)': 'TODAY()',
        r'\bDATEADD\(': 'DATEADD(',  # Syntaxe différente
        r'\bDATEDIFF\(': 'DATEDIFF(',  # Syntaxe différente
        r'\bDATETRUNC\(': 'STARTOFYEAR(',  # Approx
        r'\bMAKEDATE\(': 'DATE(',
        r'\bMAKEDATETIME\(': 'DATETIME(',
    }
    
    for tableau_func, dax_func in conversions.items():
        formula = re.sub(tableau_func, dax_func, formula, flags=re.IGNORECASE)
    
    # DATEADD syntax: DATEADD('month', interval, date) -> DATEADD(date, interval, MONTH)
    formula = re.sub(
        r"DATEADD\(\s*['\"](\w+)['\"]\s*,\s*(.+?)\s*,\s*(.+?)\s*\)",
        r'DATEADD(\3, \2, \1)',
        formula,
        flags=re.IGNORECASE
    )
    
    return formula


def convert_math_functions(formula):
    """Convertit les fonctions mathématiques"""
    
    conversions = {
        r'\bABS\(': 'ABS(',
        r'\bROUND\(': 'ROUND(',
        r'\bCEILING\(': 'ROUNDUP(',
        r'\bFLOOR\(': 'ROUNDDOWN(',
        r'\bSQRT\(': 'SQRT(',
        r'\bPOWER\(': 'POWER(',
        r'\bEXP\(': 'EXP(',
        r'\bLN\(': 'LN(',
        r'\bLOG\(': 'LOG(',
        r'\bSQUARE\(': 'POWER(',  # SQUARE(x) -> POWER(x, 2)
    }
    
    for tableau_func, dax_func in conversions.items():
        formula = re.sub(tableau_func, dax_func, formula, flags=re.IGNORECASE)
    
    return formula


def convert_lod_expressions(formula):
    """
    Convertit les LOD (Level of Detail) expressions Tableau en DAX
    
    { FIXED [Dim] : AGG([Measure]) } -> CALCULATE(AGG([Measure]), ALL(Table[Dim]))
    { INCLUDE [Dim] : AGG([Measure]) } -> CALCULATE(AGG([Measure]))
    { EXCLUDE [Dim] : AGG([Measure]) } -> CALCULATE(AGG([Measure]), ALL(Table[Dim]))
    """
    
    # FIXED pattern
    fixed_pattern = r'\{\s*FIXED\s+(.+?)\s*:\s*(.+?)\s*\}'
    
    def replace_fixed(match):
        dimensions = match.group(1).strip()
        aggregation = match.group(2).strip()
        
        # Extraire les dimensions
        dims = [d.strip() for d in dimensions.split(',')]
        all_clauses = ', '.join([f'ALL({d})' for d in dims])
        
        return f'CALCULATE({aggregation}, {all_clauses})'
    
    formula = re.sub(fixed_pattern, replace_fixed, formula, flags=re.IGNORECASE | re.DOTALL)
    
    # INCLUDE pattern (moins de transformation nécessaire)
    include_pattern = r'\{\s*INCLUDE\s+(.+?)\s*:\s*(.+?)\s*\}'
    formula = re.sub(include_pattern, r'CALCULATE(\2)', formula, flags=re.IGNORECASE | re.DOTALL)
    
    # EXCLUDE pattern
    exclude_pattern = r'\{\s*EXCLUDE\s+(.+?)\s*:\s*(.+?)\s*\}'
    
    def replace_exclude(match):
        dimensions = match.group(1).strip()
        aggregation = match.group(2).strip()
        
        dims = [d.strip() for d in dimensions.split(',')]
        all_clauses = ', '.join([f'ALLEXCEPT(Table, {", ".join(dims)})' for dims in [dims]])
        
        return f'CALCULATE({aggregation}, {all_clauses})'
    
    formula = re.sub(exclude_pattern, replace_exclude, formula, flags=re.IGNORECASE | re.DOTALL)
    
    return formula


def clean_formula(formula):
    """Nettoyage et formatage final"""
    
    # Supprimer les espaces multiples
    formula = re.sub(r'\s+', ' ', formula)
    
    # Gérer les parenthèses non fermées de ZN/IFNULL
    formula = re.sub(r'IF\(ISBLANK\((.+?)\)\)', r'IF(ISBLANK(\1), 0, \1)', formula)
    
    return formula.strip()


def convert_format(tableau_format):
    """Convertit le format d'affichage"""
    
    if not tableau_format:
        return None
    
    format_mapping = {
        'n0': '#,##0',
        'n1': '#,##0.0',
        'n2': '#,##0.00',
        'c0': '$#,##0',
        'c2': '$#,##0.00',
        'p0': '0%',
        'p1': '0.0%',
        'p2': '0.00%',
        'd': 'dd/MM/yyyy',
        'D': 'dddd, MMMM dd, yyyy',
        't': 'HH:mm',
        'T': 'HH:mm:ss',
    }
    
    return format_mapping.get(tableau_format.lower(), tableau_format)
