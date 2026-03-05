"""
Module de conversion des Dashboards Tableau vers Power BI Reports
"""

def convert_dashboard_to_report(dashboard):
    """
    Convertit un dashboard Tableau en rapport Power BI
    
    Structure:
    - Dashboard Layout -> Report Page Layout
    - Dashboard Objects -> Report Visuals
    - Dashboard Actions -> Report Interactions
    - Dashboard Filters -> Report-level Filters
    """
    
    dashboard_name = dashboard.get('name', 'Unnamed Dashboard')
    
    powerbi_report = {
        'name': dashboard_name,
        'displayName': dashboard.get('title', dashboard_name),
        'pages': convert_dashboard_pages(dashboard),
        'theme': convert_dashboard_theme(dashboard.get('theme', {})),
        'filters': convert_dashboard_filters(dashboard.get('filters', [])),
        'parameters': convert_dashboard_parameters(dashboard.get('parameters', [])),
        'bookmarks': convert_dashboard_bookmarks(dashboard.get('stories', [])),
    }
    
    return powerbi_report


def convert_dashboard_pages(dashboard):
    """Convertit les layouts de dashboard en pages Power BI"""
    pages = []
    
    # Un dashboard Tableau = une page Power BI principale
    main_page = {
        'name': dashboard.get('name', 'Page1'),
        'displayName': dashboard.get('title', dashboard.get('name', 'Page1')),
        'width': dashboard.get('size', {}).get('width', 1280),
        'height': dashboard.get('size', {}).get('height', 720),
        'visualContainers': convert_dashboard_objects(dashboard.get('objects', [])),
    }
    pages.append(main_page)
    
    return pages


def convert_dashboard_objects(objects):
    """Convertit les objets de dashboard (worksheets, images, text, etc.)"""
    visual_containers = []
    
    for obj in objects:
        obj_type = obj.get('type', '').lower()
        
        container = {
            'x': obj.get('position', {}).get('x', 0),
            'y': obj.get('position', {}).get('y', 0),
            'width': obj.get('size', {}).get('width', 300),
            'height': obj.get('size', {}).get('height', 200),
            'z-index': obj.get('z_index', 0),
        }
        
        if obj_type == 'worksheet':
            container['visual'] = {
                'type': 'worksheetReference',
                'worksheetName': obj.get('worksheet', ''),
            }
        elif obj_type == 'text':
            container['visual'] = {
                'type': 'textbox',
                'content': obj.get('text', ''),
                'fontSize': obj.get('font_size', 12),
                'fontColor': obj.get('font_color', '#000000'),
            }
        elif obj_type == 'image':
            container['visual'] = {
                'type': 'image',
                'url': obj.get('image_url', ''),
                'scaling': convert_image_scaling(obj.get('scaling', 'fit')),
            }
        elif obj_type == 'web':
            container['visual'] = {
                'type': 'webContent',
                'url': obj.get('url', ''),
            }
        elif obj_type == 'blank':
            container['visual'] = {
                'type': 'shape',
                'shapeType': 'rectangle',
                'fillColor': obj.get('background_color', '#FFFFFF'),
            }
        
        visual_containers.append(container)
    
    return visual_containers


def convert_image_scaling(tableau_scaling):
    """Convertit les options de mise à l'échelle d'image"""
    scaling_mapping = {
        'fit': 'Fit',
        'fill': 'Fill',
        'normal': 'Normal',
        'stretch': 'Fill',
    }
    return scaling_mapping.get(tableau_scaling.lower(), 'Fit')


def convert_dashboard_theme(tableau_theme):
    """Convertit le thème du dashboard"""
    return {
        'name': tableau_theme.get('name', 'Custom'),
        'dataColors': tableau_theme.get('colors', [
            '#4E79A7', '#F28E2B', '#E15759', '#76B7B2', 
            '#59A14F', '#EDC948', '#B07AA1', '#FF9DA7'
        ]),
        'background': tableau_theme.get('background_color', '#FFFFFF'),
        'foreground': tableau_theme.get('text_color', '#000000'),
        'fontFamily': tableau_theme.get('font_family', 'Segoe UI'),
    }


def convert_dashboard_filters(tableau_filters):
    """Convertit les filtres de niveau dashboard"""
    powerbi_filters = []
    
    for filt in tableau_filters:
        powerbi_filters.append({
            'field': filt.get('field'),
            'displayName': filt.get('caption', filt.get('field')),
            'type': convert_filter_control_type(filt.get('control', 'list')),
            'isRequired': filt.get('required', False),
            'allowMultiple': filt.get('multiple', True),
            'showSelectAll': filt.get('show_all', True),
        })
    
    return powerbi_filters


def convert_filter_control_type(tableau_control):
    """Convertit les types de contrôles de filtre"""
    control_mapping = {
        'list': 'dropdown',
        'dropdown': 'dropdown',
        'slider': 'slider',
        'date': 'relativeDateFilter',
        'wildcard': 'search',
    }
    return control_mapping.get(tableau_control.lower(), 'dropdown')


def convert_dashboard_parameters(tableau_params):
    """Convertit les paramètres Tableau en paramètres Power BI"""
    powerbi_params = []
    
    for param in tableau_params:
        powerbi_params.append({
            'name': param.get('name'),
            'displayName': param.get('caption', param.get('name')),
            'dataType': convert_param_datatype(param.get('datatype', 'string')),
            'defaultValue': param.get('value', param.get('default_value')),
            'allowedValues': param.get('allowable_values', []),
            'controlType': convert_param_control(param.get('control', 'list')),
        })
    
    return powerbi_params


def convert_param_datatype(tableau_type):
    """Convertit les types de paramètres"""
    type_mapping = {
        'string': 'Text',
        'integer': 'Number',
        'real': 'Decimal',
        'boolean': 'Boolean',
        'date': 'Date',
        'datetime': 'DateTime',
    }
    return type_mapping.get(tableau_type.lower(), 'Text')


def convert_param_control(tableau_control):
    """Convertit les types de contrôles de paramètres"""
    control_mapping = {
        'list': 'dropdown',
        'range': 'slider',
        'text': 'textbox',
    }
    return control_mapping.get(tableau_control.lower(), 'dropdown')


def convert_dashboard_bookmarks(tableau_stories):
    """Convertit les Story Points Tableau en signets Power BI"""
    powerbi_bookmarks = []
    
    for story_point in tableau_stories:
        powerbi_bookmarks.append({
            'name': story_point.get('caption', f'Bookmark {len(powerbi_bookmarks) + 1}'),
            'description': story_point.get('description', ''),
            'capturesFilters': True,
            'capturesSlicers': True,
        })
    
    return powerbi_bookmarks
