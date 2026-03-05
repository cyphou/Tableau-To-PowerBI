"""
Module de conversion des Paramètres Tableau vers Power BI Parameters
"""

def convert_parameter_to_powerbi(parameter):
    """
    Convertit un paramètre Tableau en paramètre Power BI
    
    Tableau Parameters -> Power BI Parameters (What-If Parameters, Query Parameters)
    """
    
    param_name = parameter.get('name', 'Unnamed Parameter')
    param_type = parameter.get('datatype', 'string')
    
    powerbi_parameter = {
        'name': param_name,
        'displayName': parameter.get('caption', param_name),
        'description': parameter.get('description', ''),
        'dataType': convert_param_type(param_type),
        'currentValue': parameter.get('value', parameter.get('default_value')),
        'parameterType': determine_parameter_type(parameter),
        'config': convert_parameter_config(parameter),
    }
    
    return powerbi_parameter


def convert_param_type(tableau_type):
    """Convertit les types de paramètres"""
    type_mapping = {
        'string': 'text',
        'integer': 'number',
        'real': 'decimal',
        'boolean': 'logical',
        'date': 'date',
        'datetime': 'datetime',
    }
    return type_mapping.get(tableau_type.lower(), 'text')


def determine_parameter_type(parameter):
    """
    Détermine le type de paramètre Power BI:
    - Query Parameter: pour filtrer les données à la source
    - What-If Parameter: pour l'analyse de scénarios
    - Report Parameter: pour les filtres de rapport
    """
    
    # Si le paramètre a une plage de valeurs numériques -> What-If
    if parameter.get('datatype', '').lower() in ['integer', 'real']:
        if parameter.get('allowable_values_type') == 'range':
            return 'what-if'
    
    # Si utilisé dans les requêtes -> Query Parameter
    if parameter.get('used_in_query', False):
        return 'query'
    
    # Par défaut -> Report Parameter
    return 'report'


def convert_parameter_config(parameter):
    """Convertit la configuration spécifique du paramètre"""
    
    config = {
        'allowMultipleValues': parameter.get('allowable_values_type') == 'list' and parameter.get('allow_multiple', False),
        'showInFilterPane': True,
    }
    
    # Configuration pour les valeurs autorisées
    allowable_type = parameter.get('allowable_values_type', 'all')
    
    if allowable_type == 'list':
        config['allowedValues'] = {
            'type': 'list',
            'values': parameter.get('allowable_values', []),
        }
    elif allowable_type == 'range':
        config['allowedValues'] = {
            'type': 'range',
            'min': parameter.get('range_min', 0),
            'max': parameter.get('range_max', 100),
            'step': parameter.get('range_step', 1),
        }
    else:
        config['allowedValues'] = {
            'type': 'any',
        }
    
    # Configuration du contrôle UI
    control_type = parameter.get('control', 'list')
    config['controlType'] = convert_control_type(control_type)
    
    return config


def convert_control_type(tableau_control):
    """Convertit le type de contrôle UI"""
    control_mapping = {
        'list': 'dropdown',
        'dropdown': 'dropdown',
        'range': 'slider',
        'text': 'textbox',
    }
    return control_mapping.get(tableau_control.lower(), 'dropdown')


def generate_whatif_parameter(parameter):
    """
    Génère un What-If Parameter Power BI
    
    Un What-If Parameter nécessite:
    - Une table de paramètre
    - Une colonne de valeurs
    - Une mesure de paramètre
    """
    
    param_name = parameter.get('name')
    min_value = parameter.get('range_min', 0)
    max_value = parameter.get('range_max', 100)
    step = parameter.get('range_step', 1)
    
    whatif = {
        'tableName': f'{param_name} Parameter',
        'columnName': f'{param_name} Value',
        'measureName': f'{param_name}',
        'minValue': min_value,
        'maxValue': max_value,
        'increment': step,
        'defaultValue': parameter.get('value', min_value),
        'formatString': parameter.get('format', '0'),
    }
    
    return whatif


def generate_dax_parameter_usage(parameter, calculation):
    """
    Génère l'utilisation DAX d'un paramètre dans un calcul
    
    Tableau: [Parameter Name]
    Power BI: SELECTEDVALUE('Parameter Table'[Parameter Value], DefaultValue)
    """
    
    param_name = parameter.get('name')
    default_value = parameter.get('value', parameter.get('default_value', 0))
    
    # Format pour référencer le paramètre dans DAX
    if parameter.get('parameterType') == 'what-if':
        dax_reference = f"SELECTEDVALUE('{param_name} Parameter'[{param_name} Value], {default_value})"
    else:
        dax_reference = f"SELECTEDVALUE('Parameters'[{param_name}], {default_value})"
    
    return dax_reference
