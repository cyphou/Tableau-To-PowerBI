"""
Script de test rapide pour valider les fichiers Tableau d'exemple
"""

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

# Chemin vers les fichiers d'exemple
SAMPLES_DIR = 'examples/tableau_samples'

# Liste des fichiers à tester
TEST_FILES = [
    {
        'name': 'Superstore_Sales.twb',
        'expected': {
            'worksheets': 3,
            'dashboards': 1,
            'calculations': 4,
            'datasources': 1
        }
    },
    {
        'name': 'HR_Analytics.twb',
        'expected': {
            'worksheets': 4,
            'dashboards': 1,
            'calculations': 4,
            'datasources': 1
        }
    },
    {
        'name': 'Financial_Report.twb',
        'expected': {
            'worksheets': 4,
            'dashboards': 1,
            'calculations': 6,
            'datasources': 1,
            'parameters': 2,
            'stories': 1
        }
    }
]


def validate_tableau_file(filepath, expected):
    """Valide un fichier Tableau"""
    
    print(f"\n{'='*60}")
    print(f"Validation: {os.path.basename(filepath)}")
    print(f"{'='*60}")
    
    results = {
        'valid_xml': False,
        'has_datasources': False,
        'has_worksheets': False,
        'has_dashboards': False,
        'has_calculations': False,
        'counts': {}
    }
    
    try:
        # Parser le XML
        tree = ET.parse(filepath)
        root = tree.getroot()
        results['valid_xml'] = True
        print("✓ Fichier XML valide")
        
        # Vérifier les datasources
        datasources = root.findall('.//datasource[@inline="true"]')
        results['counts']['datasources'] = len(datasources)
        results['has_datasources'] = len(datasources) > 0
        if results['has_datasources']:
            print(f"✓ Sources de données: {len(datasources)}")
        
        # Vérifier les worksheets
        worksheets = root.findall('.//worksheet')
        results['counts']['worksheets'] = len(worksheets)
        results['has_worksheets'] = len(worksheets) > 0
        if results['has_worksheets']:
            print(f"✓ Worksheets: {len(worksheets)}")
            for ws in worksheets:
                name = ws.get('name', 'Sans nom')
                print(f"    - {name}")
        
        # Vérifier les dashboards
        dashboards = root.findall('.//dashboard')
        results['counts']['dashboards'] = len(dashboards)
        results['has_dashboards'] = len(dashboards) > 0
        if results['has_dashboards']:
            print(f"✓ Dashboards: {len(dashboards)}")
            for db in dashboards:
                name = db.get('name', 'Sans nom')
                print(f"    - {name}")
        
        # Vérifier les calculs
        calculations = root.findall('.//column[@name][@role="measure"]')
        calc_count = 0
        for calc in calculations:
            if calc.find('calculation') is not None:
                calc_count += 1
        results['counts']['calculations'] = calc_count
        results['has_calculations'] = calc_count > 0
        if results['has_calculations']:
            print(f"✓ Calculs: {calc_count}")
        
        # Vérifier les paramètres (si attendus)
        if 'parameters' in expected:
            parameters = root.findall('.//parameter')
            results['counts']['parameters'] = len(parameters)
            print(f"✓ Paramètres: {len(parameters)}")
            for param in parameters:
                name = param.get('caption', 'Sans nom')
                print(f"    - {name}")
        
        # Vérifier les stories (si attendues)
        if 'stories' in expected:
            stories = root.findall('.//story')
            results['counts']['stories'] = len(stories)
            if len(stories) > 0:
                print(f"✓ Stories: {len(stories)}")
                for story in stories:
                    name = story.get('name', 'Sans nom')
                    points = len(story.findall('.//story-point'))
                    print(f"    - {name} ({points} points)")
        
        # Comparer avec les valeurs attendues
        print(f"\n{'─'*60}")
        print("Validation des comptes attendus:")
        all_match = True
        
        for key, expected_count in expected.items():
            actual_count = results['counts'].get(key, 0)
            match = actual_count == expected_count
            all_match = all_match and match
            
            status = "✓" if match else "✗"
            print(f"{status} {key}: {actual_count} (attendu: {expected_count})")
        
        print(f"{'─'*60}")
        if all_match:
            print("✅ VALIDATION RÉUSSIE - Tous les comptes correspondent")
        else:
            print("⚠️  VALIDATION PARTIELLE - Certains comptes diffèrent")
        
        return all_match
        
    except ET.ParseError as e:
        print(f"✗ Erreur de parsing XML: {str(e)}")
        return False
    
    except Exception as e:
        print(f"✗ Erreur: {str(e)}")
        return False


def main():
    """Test tous les fichiers d'exemple"""
    
    print("="*60)
    print("TEST DES FICHIERS TABLEAU D'EXEMPLE")
    print("="*60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Dossier: {SAMPLES_DIR}")
    
    results = []
    
    for test_file in TEST_FILES:
        filepath = os.path.join(SAMPLES_DIR, test_file['name'])
        
        if not os.path.exists(filepath):
            print(f"\n✗ Fichier non trouvé: {filepath}")
            results.append(False)
            continue
        
        success = validate_tableau_file(filepath, test_file['expected'])
        results.append(success)
    
    # Résumé final
    print("\n" + "="*60)
    print("RÉSUMÉ DES TESTS")
    print("="*60)
    
    for i, test_file in enumerate(TEST_FILES):
        status = "✅ PASS" if results[i] else "❌ FAIL"
        print(f"{status} - {test_file['name']}")
    
    success_count = sum(results)
    total_count = len(results)
    
    print(f"\nRésultat: {success_count}/{total_count} fichiers validés")
    
    if success_count == total_count:
        print("\n🎉 Tous les fichiers Tableau sont valides et prêts pour la migration!")
        print("\n🚀 Commandes de test recommandées:")
        print("   python migrate.py examples/tableau_samples/Superstore_Sales.twb")
        print("   python migrate.py examples/tableau_samples/HR_Analytics.twb")
        print("   python migrate.py examples/tableau_samples/Financial_Report.twb")
        return 0
    else:
        print("\n⚠️  Certains fichiers nécessitent une vérification")
        return 1


if __name__ == '__main__':
    sys.exit(main())
