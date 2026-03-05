"""
Module de conversion des Stories Tableau vers Power BI Bookmarks et Buttons
"""

def convert_story_to_bookmarks(story):
    """
    Convertit une Story Tableau en signets Power BI
    
    Tableau Story -> Power BI Bookmarks + Navigation Buttons
    """
    
    story_name = story.get('name', 'Unnamed Story')
    
    powerbi_story = {
        'name': story_name,
        'displayName': story.get('title', story_name),
        'description': story.get('description', ''),
        'bookmarks': convert_story_points(story.get('story_points', [])),
        'navigationButtons': generate_navigation_buttons(story.get('story_points', [])),
    }
    
    return powerbi_story


def convert_story_points(story_points):
    """
    Convertit les Story Points Tableau en signets Power BI
    
    Chaque Story Point capture:
    - L'état des visuels
    - Les filtres appliqués
    - Les sélections
    """
    
    powerbi_bookmarks = []
    
    for idx, point in enumerate(story_points):
        bookmark = {
            'name': point.get('caption', f'Story Point {idx + 1}'),
            'displayName': point.get('caption', f'Story Point {idx + 1}'),
            'description': point.get('description', ''),
            'order': idx,
            'captureSettings': {
                'captureAllFilters': True,
                'captureSlicers': True,
                'captureSelectedVisuals': True,
                'captureCurrentPage': True,
            },
            'snapshot': convert_story_point_snapshot(point),
        }
        
        powerbi_bookmarks.append(bookmark)
    
    return powerbi_bookmarks


def convert_story_point_snapshot(point):
    """
    Convertit le snapshot d'un Story Point
    """
    
    snapshot = {
        'visualStates': [],
        'filterStates': [],
        'pageState': {},
    }
    
    # États des visuels
    for visual in point.get('visuals', []):
        snapshot['visualStates'].append({
            'visualName': visual.get('worksheet', ''),
            'isVisible': visual.get('visible', True),
            'isHighlighted': visual.get('highlighted', False),
        })
    
    # États des filtres
    for filter_state in point.get('filters', []):
        snapshot['filterStates'].append({
            'field': filter_state.get('field', ''),
            'values': filter_state.get('values', []),
        })
    
    # État de la page
    snapshot['pageState'] = {
        'zoom': point.get('zoom', 100),
        'scroll': point.get('scroll_position', {'x': 0, 'y': 0}),
    }
    
    return snapshot


def generate_navigation_buttons(story_points):
    """
    Génère les boutons de navigation pour naviguer entre les Story Points
    
    Crée:
    - Bouton Previous
    - Bouton Next
    - Boutons individuels pour chaque point
    """
    
    buttons = []
    
    # Bouton Previous
    buttons.append({
        'type': 'button',
        'name': 'Previous',
        'text': '← Previous',
        'action': {
            'type': 'bookmark',
            'destination': 'previous',
        },
        'position': {'x': 10, 'y': 10},
        'size': {'width': 100, 'height': 40},
    })
    
    # Bouton Next
    buttons.append({
        'type': 'button',
        'name': 'Next',
        'text': 'Next →',
        'action': {
            'type': 'bookmark',
            'destination': 'next',
        },
        'position': {'x': 120, 'y': 10},
        'size': {'width': 100, 'height': 40},
    })
    
    # Boutons pour chaque Story Point
    x_position = 230
    for idx, point in enumerate(story_points):
        buttons.append({
            'type': 'button',
            'name': f'StoryPoint_{idx + 1}',
            'text': str(idx + 1),
            'tooltip': point.get('caption', f'Story Point {idx + 1}'),
            'action': {
                'type': 'bookmark',
                'bookmarkName': point.get('caption', f'Story Point {idx + 1}'),
            },
            'position': {'x': x_position, 'y': 10},
            'size': {'width': 40, 'height': 40},
            'style': {
                'backgroundColor': '#4E79A7',
                'textColor': '#FFFFFF',
                'borderRadius': 5,
            },
        })
        x_position += 50
    
    return buttons


def generate_story_navigation_page(story):
    """
    Génère une page de navigation pour la Story
    
    Page principale avec:
    - Titre de la Story
    - Miniatures des Story Points
    - Boutons de navigation
    """
    
    navigation_page = {
        'name': f'{story.get("name", "Story")}_Navigation',
        'displayName': story.get('title', 'Story Navigation'),
        'elements': [],
    }
    
    # Titre
    navigation_page['elements'].append({
        'type': 'textbox',
        'text': story.get('title', 'Story Navigation'),
        'position': {'x': 50, 'y': 50},
        'size': {'width': 1180, 'height': 80},
        'style': {
            'fontSize': 32,
            'fontWeight': 'bold',
            'alignment': 'center',
        },
    })
    
    # Description
    if story.get('description'):
        navigation_page['elements'].append({
            'type': 'textbox',
            'text': story.get('description', ''),
            'position': {'x': 50, 'y': 140},
            'size': {'width': 1180, 'height': 60},
            'style': {
                'fontSize': 14,
                'alignment': 'center',
            },
        })
    
    # Miniatures des Story Points (grid layout)
    story_points = story.get('story_points', [])
    cols = 3
    x_start = 50
    y_start = 220
    width = 360
    height = 240
    margin = 30
    
    for idx, point in enumerate(story_points):
        row = idx // cols
        col = idx % cols
        
        x = x_start + col * (width + margin)
        y = y_start + row * (height + margin)
        
        # Carte de Story Point
        navigation_page['elements'].append({
            'type': 'button',
            'text': point.get('caption', f'Story Point {idx + 1}'),
            'position': {'x': x, 'y': y},
            'size': {'width': width, 'height': height},
            'action': {
                'type': 'bookmark',
                'bookmarkName': point.get('caption', f'Story Point {idx + 1}'),
            },
            'style': {
                'backgroundColor': '#F5F5F5',
                'borderColor': '#CCCCCC',
                'borderWidth': 1,
            },
        })
    
    return navigation_page


def convert_story_annotations(point):
    """
    Convertit les annotations d'un Story Point
    
    Les annotations Tableau peuvent devenir:
    - Zones de texte Power BI
    - Formes avec texte
    """
    
    annotations = []
    
    for annotation in point.get('annotations', []):
        annotations.append({
            'type': 'textbox',
            'text': annotation.get('text', ''),
            'position': {
                'x': annotation.get('position', {}).get('x', 0),
                'y': annotation.get('position', {}).get('y', 0),
            },
            'size': {
                'width': annotation.get('size', {}).get('width', 200),
                'height': annotation.get('size', {}).get('height', 100),
            },
            'style': {
                'fontSize': annotation.get('font_size', 12),
                'fontColor': annotation.get('font_color', '#000000'),
                'backgroundColor': annotation.get('background_color', '#FFFFCC'),
                'borderColor': annotation.get('border_color', '#000000'),
                'borderWidth': 1,
            },
        })
    
    return annotations
