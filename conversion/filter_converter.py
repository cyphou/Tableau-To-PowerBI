"""
Module de conversion des Filtres Tableau vers Power BI Filters
"""

def convert_filter_to_powerbi(filter_obj):
    """
    Convertit un filtre Tableau en filtre Power BI
    
    Types de filtres:
    - Categorical Filter -> Basic Filter / Advanced Filter
    - Quantitative Filter -> Advanced Filter
    - Date Filter -> Relative Date Filter / Advanced Filter
    - Top N Filter -> Top N Filter
    - Context Filter -> Page/Report Level Filter
    """
    
    filter_name = filter_obj.get('field', 'Unnamed Filter')
    filter_type = filter_obj.get('type', 'categorical')
    
    powerbi_filter = {
        'field': filter_name,
        'displayName': filter_obj.get('caption', filter_name),
        'filterType': convert_filter_type(filter_type),
        'operator': convert_filter_operator(filter_obj.get('operator', 'in')),
        'values': filter_obj.get('values', []),
        'level': convert_filter_level(filter_obj.get('scope', 'worksheet')),
        'isRequired': filter_obj.get('required', False),
        'allowMultiple': filter_obj.get('allow_multiple', True),
    }
    
    # Configuration spécifique selon le type
    if filter_type.lower() == 'date':
        powerbi_filter['dateFilterConfig'] = convert_date_filter(filter_obj)
    elif filter_type.lower() == 'top':
        powerbi_filter['topNConfig'] = convert_topn_filter(filter_obj)
    elif filter_type.lower() == 'quantitative':
        powerbi_filter['rangeConfig'] = convert_range_filter(filter_obj)
    
    return powerbi_filter


def convert_filter_type(tableau_type):
    """Convertit le type de filtre"""
    type_mapping = {
        'categorical': 'basic',
        'quantitative': 'advanced',
        'date': 'relative',
        'top': 'topN',
        'wildcard': 'advanced',
        'context': 'advanced',
    }
    return type_mapping.get(tableau_type.lower(), 'basic')


def convert_filter_operator(tableau_operator):
    """Convertit l'opérateur de filtre"""
    operator_mapping = {
        'in': 'In',
        'not in': 'NotIn',
        'equals': 'Is',
        '=': 'Is',
        'not equals': 'IsNot',
        '!=': 'IsNot',
        '<>': 'IsNot',
        'greater than': 'GreaterThan',
        '>': 'GreaterThan',
        'greater than or equal': 'GreaterThanOrEqual',
        '>=': 'GreaterThanOrEqual',
        'less than': 'LessThan',
        '<': 'LessThan',
        'less than or equal': 'LessThanOrEqual',
        '<=': 'LessThanOrEqual',
        'between': 'Between',
        'contains': 'Contains',
        'does not contain': 'DoesNotContain',
        'starts with': 'StartsWith',
        'ends with': 'EndsWith',
        'is null': 'IsBlank',
        'is not null': 'IsNotBlank',
    }
    return operator_mapping.get(tableau_operator.lower(), 'In')


def convert_filter_level(tableau_scope):
    """Convertit le niveau/scope du filtre"""
    level_mapping = {
        'worksheet': 'visual',
        'dashboard': 'page',
        'workbook': 'report',
        'context': 'report',
        'datasource': 'dataset',
    }
    return level_mapping.get(tableau_scope.lower(), 'visual')


def convert_date_filter(filter_obj):
    """
    Convertit un filtre de date Tableau en filtre de date Power BI
    
    Types de filtres de date:
    - Relative Date (last 7 days, this month, etc.)
    - Date Range (between dates)
    - Date Parts (years, quarters, months)
    """
    
    date_type = filter_obj.get('date_filter_type', 'range').lower()
    
    config = {
        'filterType': date_type,
    }
    
    if date_type == 'relative':
        # Filtres relatifs: Last N days, This month, etc.
        config['relativeConfig'] = {
            'period': convert_date_period(filter_obj.get('period', 'day')),
            'anchor': filter_obj.get('anchor', 'today'),
            'offset': filter_obj.get('offset', 0),
            'includeThisPeriod': filter_obj.get('include_current', True),
        }
    elif date_type == 'range':
        # Plage de dates
        config['rangeConfig'] = {
            'startDate': filter_obj.get('start_date'),
            'endDate': filter_obj.get('end_date'),
        }
    elif date_type == 'datepart':
        # Parties de date (années, mois, etc.)
        config['datePartConfig'] = {
            'datePart': convert_date_part(filter_obj.get('date_part', 'month')),
            'values': filter_obj.get('values', []),
        }
    
    return config


def convert_date_period(tableau_period):
    """Convertit les périodes de date"""
    period_mapping = {
        'day': 'Day',
        'week': 'Week',
        'month': 'Month',
        'quarter': 'Quarter',
        'year': 'Year',
    }
    return period_mapping.get(tableau_period.lower(), 'Day')


def convert_date_part(tableau_part):
    """Convertit les parties de date"""
    part_mapping = {
        'year': 'Year',
        'quarter': 'Quarter',
        'month': 'Month',
        'week': 'Week',
        'day': 'Day',
        'weekday': 'DayOfWeek',
        'hour': 'Hour',
    }
    return part_mapping.get(tableau_part.lower(), 'Month')


def convert_topn_filter(filter_obj):
    """
    Convertit un filtre Top N Tableau en filtre Top N Power BI
    
    Top 10 Products by Sales -> Top N filter
    """
    
    config = {
        'count': filter_obj.get('top_n', 10),
        'direction': convert_topn_direction(filter_obj.get('direction', 'top')),
        'byField': filter_obj.get('by_field', ''),
        'showOthers': filter_obj.get('show_others', False),
    }
    
    return config


def convert_topn_direction(tableau_direction):
    """Convertit la direction Top/Bottom"""
    direction_mapping = {
        'top': 'Top',
        'bottom': 'Bottom',
    }
    return direction_mapping.get(tableau_direction.lower(), 'Top')


def convert_range_filter(filter_obj):
    """Convertit un filtre de plage (quantitatif)"""
    
    config = {
        'minValue': filter_obj.get('min_value'),
        'maxValue': filter_obj.get('max_value'),
        'includeMin': filter_obj.get('include_min', True),
        'includeMax': filter_obj.get('include_max', True),
    }
    
    return config


def generate_filter_dax(filter_obj):
    """
    Génère l'expression DAX pour un filtre
    
    Utilisé pour les filtres dans CALCULATE ou pour les mesures filtrées
    """
    
    field = filter_obj.get('field', '')
    operator = filter_obj.get('operator', 'in').lower()
    values = filter_obj.get('values', [])
    
    if operator == 'in':
        # [Field] IN {value1, value2, ...}
        values_str = ', '.join([f'"{v}"' if isinstance(v, str) else str(v) for v in values])
        return f'{field} IN {{{values_str}}}'
    elif operator == 'equals':
        # [Field] = value
        value = values[0] if values else ''
        value_str = f'"{value}"' if isinstance(value, str) else str(value)
        return f'{field} = {value_str}'
    elif operator == 'greater than':
        value = values[0] if values else 0
        return f'{field} > {value}'
    elif operator == 'less than':
        value = values[0] if values else 0
        return f'{field} < {value}'
    elif operator == 'between':
        min_val = values[0] if len(values) > 0 else 0
        max_val = values[1] if len(values) > 1 else 100
        return f'{field} >= {min_val} && {field} <= {max_val}'
    elif operator == 'contains':
        value = values[0] if values else ''
        return f'SEARCH("{value}", {field}, 1, 0) > 0'
    
    return f'{field} = BLANK()'


def convert_filter_action(action):
    """
    Convertit une action de filtre Tableau en interaction Power BI
    
    Dashboard Actions -> Report Interactions
    """
    
    powerbi_action = {
        'type': 'filter',
        'sourceVisual': action.get('source_sheet', ''),
        'targetVisuals': action.get('target_sheets', []),
        'filterFields': action.get('fields', []),
        'clearable': action.get('clearable', True),
    }
    
    return powerbi_action
