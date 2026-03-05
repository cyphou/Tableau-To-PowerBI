"""
Module de conversion des Sources de Données Tableau vers Power BI Datasets
"""

def convert_datasource_to_dataset(datasource):
    """
    Convertit une source de données Tableau en dataset Power BI
    
    Mapping:
    - Tableau Data Connection -> Power BI Data Source
    - Tableau Custom SQL -> Power Query / Direct Query
    - Tableau Data Extract -> Import Mode
    - Tableau Live Connection -> DirectQuery / LiveConnection
    """
    
    datasource_name = datasource.get('name', 'Unnamed Datasource')
    
    powerbi_dataset = {
        'name': datasource_name,
        'tables': convert_tables(datasource.get('tables', [])),
        'relationships': convert_relationships(datasource.get('relationships', [])),
        'measures': convert_measures(datasource.get('calculated_fields', [])),
        'dataSource': convert_connection(datasource.get('connection', {})),
        'refreshSchedule': convert_refresh_schedule(datasource.get('extract', {})),
    }
    
    return powerbi_dataset


def convert_tables(tableau_tables):
    """Convertit les tables Tableau en tables Power BI"""
    powerbi_tables = []
    
    for table in tableau_tables:
        powerbi_tables.append({
            'name': table.get('name'),
            'columns': convert_columns(table.get('columns', [])),
            'partitions': convert_partitions(table.get('connection', {})),
            'isHidden': table.get('hidden', False),
        })
    
    return powerbi_tables


def convert_columns(tableau_columns):
    """Convertit les colonnes avec leurs métadonnées"""
    powerbi_columns = []
    
    for col in tableau_columns:
        powerbi_columns.append({
            'name': col.get('name'),
            'dataType': convert_column_datatype(col.get('datatype', 'string')),
            'isHidden': col.get('hidden', False),
            'isKey': col.get('is_key', False),
            'description': col.get('description', ''),
            'formatString': convert_format_string(col.get('format', '')),
            'dataCategory': convert_data_category(col.get('role', 'measure')),
        })
    
    return powerbi_columns


def convert_column_datatype(tableau_type):
    """Convertit les types de colonnes"""
    type_mapping = {
        'string': 'string',
        'integer': 'int64',
        'real': 'double',
        'boolean': 'boolean',
        'date': 'dateTime',
        'datetime': 'dateTime',
        'spatial': 'geography',
    }
    return type_mapping.get(tableau_type.lower(), 'string')


def convert_format_string(tableau_format):
    """Convertit les formats d'affichage"""
    if not tableau_format:
        return None
    
    # Conversions courantes
    format_mapping = {
        'n0': '#,##0',
        'n2': '#,##0.00',
        'c': '$#,##0.00',
        'p0': '0%',
        'p2': '0.00%',
        'd': 'dd/MM/yyyy',
    }
    
    return format_mapping.get(tableau_format.lower(), tableau_format)


def convert_data_category(tableau_role):
    """Convertit les rôles de données en catégories Power BI"""
    category_mapping = {
        'dimension': None,
        'measure': None,
        'latitude': 'Latitude',
        'longitude': 'Longitude',
        'country': 'Country',
        'state': 'StateOrProvince',
        'city': 'City',
        'postal': 'PostalCode',
    }
    return category_mapping.get(tableau_role.lower())


def convert_relationships(tableau_relationships):
    """Convertit les relations entre tables"""
    powerbi_relationships = []
    
    for rel in tableau_relationships:
        powerbi_relationships.append({
            'fromTable': rel.get('from_table'),
            'fromColumn': rel.get('from_column'),
            'toTable': rel.get('to_table'),
            'toColumn': rel.get('to_column'),
            'cardinality': convert_cardinality(rel.get('cardinality', 'many-to-one')),
            'crossFilterDirection': convert_filter_direction(rel.get('direction', 'single')),
            'isActive': rel.get('is_active', True),
        })
    
    return powerbi_relationships


def convert_cardinality(tableau_cardinality):
    """Convertit la cardinalité des relations"""
    cardinality_mapping = {
        'one-to-one': 'oneToOne',
        'one-to-many': 'oneToMany',
        'many-to-one': 'manyToOne',
        'many-to-many': 'manyToMany',
    }
    return cardinality_mapping.get(tableau_cardinality.lower(), 'manyToOne')


def convert_filter_direction(tableau_direction):
    """Convertit la direction de filtrage"""
    direction_mapping = {
        'single': 'oneDirection',
        'both': 'bothDirections',
    }
    return direction_mapping.get(tableau_direction.lower(), 'oneDirection')


def convert_measures(calculated_fields):
    """Convertit les champs calculés Tableau en mesures DAX"""
    powerbi_measures = []
    
    for calc_field in calculated_fields:
        if calc_field.get('role', 'measure').lower() == 'measure':
            powerbi_measures.append({
                'name': calc_field.get('name'),
                'expression': convert_calculation_to_dax(calc_field.get('formula', '')),
                'formatString': convert_format_string(calc_field.get('format', '')),
                'description': calc_field.get('description', ''),
                'isHidden': calc_field.get('hidden', False),
            })
    
    return powerbi_measures


def convert_calculation_to_dax(tableau_formula):
    """
    Convertit une formule Tableau en DAX
    
    Mappings courants:
    - SUM([Field]) -> SUM([Field])
    - AVG([Field]) -> AVERAGE([Field])
    - IF condition THEN value1 ELSE value2 END -> IF(condition, value1, value2)
    - [Field1] + [Field2] -> [Field1] + [Field2]
    - DATEADD('month', -1, [Date]) -> DATEADD([Date], -1, MONTH)
    """
    
    if not tableau_formula:
        return ''
    
    # Conversions de base (à étendre)
    dax_formula = tableau_formula
    
    # Remplacement des fonctions courantes
    replacements = {
        'IF ': 'IF(',
        ' THEN ': ', ',
        ' ELSE ': ', ',
        ' END': ')',
        'COUNTD(': 'DISTINCTCOUNT(',
        'ATTR(': 'MIN(',  # ATTR en Tableau -> MIN en DAX (approximation)
        'ZN(': 'IFERROR(',
        'ISNULL(': 'ISBLANK(',
        'LEN(': 'LEN(',
        'LEFT(': 'LEFT(',
        'RIGHT(': 'RIGHT(',
        'UPPER(': 'UPPER(',
        'LOWER(': 'LOWER(',
    }
    
    for tableau_func, dax_func in replacements.items():
        dax_formula = dax_formula.replace(tableau_func, dax_func)
    
    # Note: conversion complète nécessiterait un parseur
    return dax_formula


def convert_connection(tableau_connection):
    """Convertit les informations de connexion"""
    conn_type = tableau_connection.get('class', '').lower()
    
    powerbi_connection = {
        'connectionType': convert_connection_type(conn_type),
        'connectionDetails': {
            'server': tableau_connection.get('server', ''),
            'database': tableau_connection.get('dbname', ''),
        },
    }
    
    # Ajouter les détails spécifiques selon le type
    if conn_type in ['sqlserver', 'postgres', 'mysql', 'oracle']:
        powerbi_connection['connectionMode'] = 'DirectQuery' if tableau_connection.get('live', False) else 'Import'
    
    return powerbi_connection


def convert_connection_type(tableau_conn_type):
    """Convertit les types de connexion"""
    type_mapping = {
        'sqlserver': 'SQL Server',
        'postgres': 'PostgreSQL',
        'mysql': 'MySQL',
        'oracle': 'Oracle',
        'excel': 'Excel',
        'csv': 'Text/CSV',
        'json': 'JSON',
        'web': 'Web',
        'odata': 'OData',
        'sharepoint': 'SharePoint',
        'azure': 'Azure SQL',
        'snowflake': 'Snowflake',
        'bigquery': 'Google BigQuery',
        'redshift': 'Amazon Redshift',
    }
    return type_mapping.get(tableau_conn_type, 'Unknown')


def convert_partitions(connection_info):
    """Convertit les informations de partition (extracts)"""
    return [{
        'name': 'Partition1',
        'source': {
            'type': 'query',
            'query': connection_info.get('query', 'SELECT * FROM Table'),
        }
    }]


def convert_refresh_schedule(extract_info):
    """Convertit les informations d'extract en planification de rafraîchissement"""
    if not extract_info or not extract_info.get('enabled', False):
        return None
    
    return {
        'enabled': True,
        'frequency': extract_info.get('frequency', 'daily'),
        'time': extract_info.get('time', '08:00'),
        'days': extract_info.get('days', ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']),
    }
