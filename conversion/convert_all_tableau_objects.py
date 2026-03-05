"""
Script principal de conversion de tous les objets Tableau vers Power BI

Ce script orchestre la conversion complète d'un workbook Tableau vers un rapport Power BI,
incluant tous les types d'objets : worksheets, dashboards, datasources, calculs, paramètres, filtres et stories.
"""

import os
import json
import sys
from datetime import datetime

# Import des modules de conversion
from worksheet_converter import convert_worksheet_to_visual
from dashboard_converter import convert_dashboard_to_report
from datasource_converter import convert_datasource_to_dataset
from calculation_converter import convert_calculation_to_measure
from parameter_converter import convert_parameter_to_powerbi, generate_whatif_parameter
from filter_converter import convert_filter_to_powerbi
from story_converter import convert_story_to_bookmarks, generate_story_navigation_page

# Configuration des dossiers
TABLEAU_EXPORT_DIR = 'tableau_export/'
POWERBI_OUTPUT_DIR = 'artifacts/powerbi_objects/'
CONVERSION_LOGS_DIR = 'artifacts/conversion_logs/'

# Types d'objets Tableau à convertir
CONVERSION_MODULES = {
    'worksheets': convert_worksheet_to_visual,
    'dashboards': convert_dashboard_to_report,
    'datasources': convert_datasource_to_dataset,
    'calculations': convert_calculation_to_measure,
    'parameters': convert_parameter_to_powerbi,
    'filters': convert_filter_to_powerbi,
    'stories': convert_story_to_bookmarks,
}


class TableauToPowerBIConverter:
    """Classe principale de conversion"""
    
    def __init__(self, export_dir=TABLEAU_EXPORT_DIR, output_dir=POWERBI_OUTPUT_DIR):
        self.export_dir = export_dir
        self.output_dir = output_dir
        self.logs_dir = CONVERSION_LOGS_DIR
        self.conversion_stats = {
            'start_time': datetime.now(),
            'objects_converted': {},
            'errors': [],
            'warnings': [],
        }
        
        # Créer les dossiers nécessaires
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
    
    def convert_all(self):
        """Convertit tous les objets Tableau"""
        
        print("=" * 80)
        print("CONVERSION TABLEAU → POWER BI")
        print("=" * 80)
        print(f"Début: {self.conversion_stats['start_time']}")
        print()
        
        # Convertir chaque type d'objet
        for obj_type, converter_func in CONVERSION_MODULES.items():
            self.convert_object_type(obj_type, converter_func)
        
        # Générer le rapport de conversion
        self.generate_conversion_report()
        
        # Sauvegarder les statistiques
        self.save_conversion_stats()
        
        print()
        print("=" * 80)
        print("CONVERSION TERMINÉE")
        print("=" * 80)
        print(f"Durée: {datetime.now() - self.conversion_stats['start_time']}")
        print(f"Objets convertis: {sum(self.conversion_stats['objects_converted'].values())}")
        print(f"Erreurs: {len(self.conversion_stats['errors'])}")
        print(f"Avertissements: {len(self.conversion_stats['warnings'])}")
        print()
    
    def convert_object_type(self, obj_type, converter_func):
        """Convertit un type spécifique d'objets"""
        
        input_path = os.path.join(self.export_dir, f'{obj_type}.json')
        output_path = os.path.join(self.output_dir, f'{obj_type}_powerbi.json')
        
        print(f"Conversion: {obj_type}...")
        
        if not os.path.exists(input_path):
            warning = f'Fichier non trouvé : {input_path}'
            print(f"  ⚠️  {warning}")
            self.conversion_stats['warnings'].append(warning)
            self.conversion_stats['objects_converted'][obj_type] = 0
            return
        
        try:
            # Charger les objets Tableau
            with open(input_path, 'r', encoding='utf-8') as infile:
                tableau_objects = json.load(infile)
            
            if not isinstance(tableau_objects, list):
                tableau_objects = [tableau_objects]
            
            # Convertir chaque objet
            powerbi_objects = []
            for obj in tableau_objects:
                try:
                    converted = converter_func(obj)
                    powerbi_objects.append(converted)
                except Exception as e:
                    error = f'Erreur lors de la conversion de {obj.get("name", "objet sans nom")} ({obj_type}): {str(e)}'
                    print(f"  ❌ {error}")
                    self.conversion_stats['errors'].append(error)
            
            # Sauvegarder les objets convertis
            with open(output_path, 'w', encoding='utf-8') as outfile:
                json.dump(powerbi_objects, outfile, indent=2, ensure_ascii=False)
            
            count = len(powerbi_objects)
            self.conversion_stats['objects_converted'][obj_type] = count
            print(f"  ✓ {count} {obj_type} converti(s) -> {output_path}")
            
        except Exception as e:
            error = f'Erreur lors du traitement de {obj_type}: {str(e)}'
            print(f"  ❌ {error}")
            self.conversion_stats['errors'].append(error)
            self.conversion_stats['objects_converted'][obj_type] = 0
    
    def generate_conversion_report(self):
        """Génère un rapport de conversion complet"""
        
        report_path = os.path.join(self.logs_dir, f'conversion_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        
        report = {
            'metadata': {
                'conversion_date': self.conversion_stats['start_time'].isoformat(),
                'duration': str(datetime.now() - self.conversion_stats['start_time']),
            },
            'summary': {
                'total_objects': sum(self.conversion_stats['objects_converted'].values()),
                'objects_by_type': self.conversion_stats['objects_converted'],
                'error_count': len(self.conversion_stats['errors']),
                'warning_count': len(self.conversion_stats['warnings']),
            },
            'errors': self.conversion_stats['errors'],
            'warnings': self.conversion_stats['warnings'],
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print()
        print(f"Rapport de conversion sauvegardé: {report_path}")
    
    def save_conversion_stats(self):
        """Sauvegarde les statistiques de conversion"""
        
        stats_path = os.path.join(self.output_dir, 'conversion_stats.json')
        
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump({
                'date': self.conversion_stats['start_time'].isoformat(),
                'objects_converted': self.conversion_stats['objects_converted'],
                'total': sum(self.conversion_stats['objects_converted'].values()),
            }, f, indent=2, ensure_ascii=False)


def main():
    """Point d'entrée principal"""
    
    # Vérifier les arguments
    if len(sys.argv) > 1:
        export_dir = sys.argv[1]
    else:
        export_dir = TABLEAU_EXPORT_DIR
    
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    else:
        output_dir = POWERBI_OUTPUT_DIR
    
    # Lancer la conversion
    converter = TableauToPowerBIConverter(export_dir, output_dir)
    converter.convert_all()


if __name__ == '__main__':
    main()
