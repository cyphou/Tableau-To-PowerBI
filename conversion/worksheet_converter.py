"""
Module de conversion des Worksheets Tableau vers Power BI Visuals
"""

def convert_worksheet_to_visual(worksheet):
    """
    Convertit une feuille Tableau en objet visuel Power BI
    
    Mapping des types de visualisation:
    - Bar Chart -> Clustered Bar Chart / Stacked Bar Chart
    - Line Chart -> Line Chart / Area Chart
    - Pie Chart -> Pie Chart / Donut Chart
    - Map -> Map / Filled Map
    - Text Table -> Table / Matrix
    - Scatter Plot -> Scatter Chart
    - Tree Map -> Treemap
    - Heat Map -> Matrix with conditional formatting
    """
    
    chart_type_mapping = {
        # ── Standard types ────────────────────────────
        'bar': 'clusteredBarChart',
        'stacked bar': 'stackedBarChart',
        'line': 'lineChart',
        'area': 'areaChart',
        'pie': 'pieChart',
        'donut': 'donutChart',
        'map': 'map',
        'filled map': 'filledMap',
        'text': 'table',
        'scatter': 'scatterChart',
        'treemap': 'treemap',
        'heatmap': 'matrix',
        'heat map': 'matrix',
        'highlight table': 'matrix',
        'histogram': 'clusteredColumnChart',
        'gantt': 'clusteredBarChart',
        'gantt bar': 'clusteredBarChart',
        'bullet': 'gauge',
        'waterfall': 'waterfallChart',
        'box': 'boxAndWhisker',
        'box plot': 'boxAndWhisker',
        'funnel': 'funnel',
        'packed bubble': 'scatterChart',
        'packed bubbles': 'scatterChart',
        'word cloud': 'wordCloud',
        'dual axis': 'lineClusteredColumnComboChart',
        'combo': 'lineClusteredColumnComboChart',
        'kpi': 'card',
        'card': 'card',
        'gauge': 'gauge',
        'circle': 'scatterChart',
        'shape': 'scatterChart',
        'polygon': 'filledMap',
        'density': 'map',
        'dot plot': 'scatterChart',
        'lollipop': 'clusteredBarChart',
        'bump chart': 'lineChart',
        'slope chart': 'lineChart',
        'pareto': 'lineClusteredColumnComboChart',
        'sparkline': 'lineChart',
        'ring': 'donutChart',
        'image': 'image',
        'radial': 'gauge',
    }
    
    worksheet_name = worksheet.get('name', 'Unnamed Worksheet')
    tableau_chart_type = worksheet.get('chart_type', 'bar').lower()
    
    powerbi_visual = {
        'name': worksheet_name,
        'visualType': chart_type_mapping.get(tableau_chart_type, 'table'),
        'title': worksheet.get('title', worksheet_name),
        'dataFields': convert_data_fields(worksheet.get('fields', [])),
        'filters': convert_filters(worksheet.get('filters', [])),
        'tooltips': convert_tooltips(worksheet.get('tooltips', [])),
        'formatting': convert_formatting(worksheet.get('formatting', {})),
        'interactions': convert_interactions(worksheet.get('actions', [])),
    }
    
    return powerbi_visual


def convert_data_fields(tableau_fields):
    """
    Convertit les champs de données Tableau vers Power BI
    
    Mapping des rôles:
    - Rows -> Axis / Category
    - Columns -> Legend / Series
    - Measures -> Values
    - Color -> Legend
    - Size -> Size
    - Detail -> Details
    """
    
    role_mapping = {
        'rows': 'axis',
        'columns': 'legend',
        'measure': 'values',
        'color': 'legend',
        'size': 'size',
        'detail': 'details',
        'tooltip': 'tooltips',
        'pages': 'filters',
    }
    
    powerbi_fields = []
    for field in tableau_fields:
        powerbi_fields.append({
            'name': field.get('name'),
            'role': role_mapping.get(field.get('shelf', 'measure').lower(), 'values'),
            'aggregation': convert_aggregation(field.get('aggregation', 'sum')),
            'dataType': convert_data_type(field.get('datatype', 'string')),
        })
    
    return powerbi_fields


def convert_aggregation(tableau_agg):
    """Convertit les fonctions d'agrégation"""
    agg_mapping = {
        'sum': 'Sum',
        'avg': 'Average',
        'min': 'Min',
        'max': 'Max',
        'count': 'Count',
        'countd': 'DistinctCount',
        'median': 'Median',
        'stdev': 'StandardDeviation',
        'var': 'Variance',
    }
    return agg_mapping.get(tableau_agg.lower(), 'Sum')


def convert_data_type(tableau_type):
    """Convertit les types de données"""
    type_mapping = {
        'string': 'Text',
        'integer': 'Whole Number',
        'real': 'Decimal Number',
        'boolean': 'True/False',
        'date': 'Date',
        'datetime': 'Date/Time',
        'spatial': 'Geography',
    }
    return type_mapping.get(tableau_type.lower(), 'Text')


def convert_filters(tableau_filters):
    """Convertit les filtres Tableau en filtres Power BI"""
    powerbi_filters = []
    for filt in tableau_filters:
        powerbi_filters.append({
            'field': filt.get('field'),
            'filterType': convert_filter_type(filt.get('type', 'categorical')),
            'operator': convert_filter_operator(filt.get('operator', 'in')),
            'values': filt.get('values', []),
            'isRequired': filt.get('required', False),
        })
    return powerbi_filters


def convert_filter_type(tableau_type):
    """Convertit les types de filtres"""
    type_mapping = {
        'categorical': 'basic',
        'quantitative': 'advanced',
        'date': 'relative',
        'top': 'topN',
        'wildcard': 'basic',
    }
    return type_mapping.get(tableau_type.lower(), 'basic')


def convert_filter_operator(tableau_op):
    """Convertit les opérateurs de filtre"""
    op_mapping = {
        'in': 'In',
        'not in': 'NotIn',
        'equals': 'Is',
        'not equals': 'IsNot',
        'greater than': 'GreaterThan',
        'less than': 'LessThan',
        'between': 'Between',
        'contains': 'Contains',
        'starts with': 'StartsWith',
        'ends with': 'EndsWith',
    }
    return op_mapping.get(tableau_op.lower(), 'In')


def convert_tooltips(tableau_tooltips):
    """Convertit les info-bulles"""
    powerbi_tooltips = []
    for tooltip in tableau_tooltips:
        powerbi_tooltips.append({
            'field': tooltip.get('field'),
            'displayName': tooltip.get('display_name', tooltip.get('field')),
        })
    return powerbi_tooltips


def convert_formatting(tableau_formatting):
    """Convertit les options de formatage"""
    return {
        'fontFamily': tableau_formatting.get('font_family', 'Segoe UI'),
        'fontSize': tableau_formatting.get('font_size', 11),
        'fontColor': convert_color(tableau_formatting.get('font_color', '#000000')),
        'backgroundColor': convert_color(tableau_formatting.get('background_color', '#FFFFFF')),
        'borderColor': convert_color(tableau_formatting.get('border_color', '#E0E0E0')),
        'numberFormat': convert_number_format(tableau_formatting.get('number_format', '#,##0')),
    }


def convert_color(tableau_color):
    """Convertit les couleurs (hex)"""
    if isinstance(tableau_color, str) and tableau_color.startswith('#'):
        return tableau_color
    return '#000000'


def convert_number_format(tableau_format):
    """Convertit les formats de nombre"""
    # Tableau et Power BI utilisent des formats similaires
    return tableau_format or '#,##0'


def convert_interactions(tableau_actions):
    """Convertit les actions Tableau en interactions Power BI"""
    powerbi_interactions = []
    for action in tableau_actions:
        action_type = action.get('type', '').lower()
        if action_type == 'filter':
            powerbi_interactions.append({
                'type': 'crossFilter',
                'targetVisuals': action.get('target_sheets', []),
            })
        elif action_type == 'highlight':
            powerbi_interactions.append({
                'type': 'crossHighlight',
                'targetVisuals': action.get('target_sheets', []),
            })
        elif action_type == 'url':
            powerbi_interactions.append({
                'type': 'webURL',
                'url': action.get('url', ''),
            })
    return powerbi_interactions
