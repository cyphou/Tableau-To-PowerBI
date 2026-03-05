"""
Script de test pour valider la migration Tableau vers Power BI

Ce script teste l'intégrité et la conformité des conversions.
"""

import os
import json
import unittest
from datetime import datetime


class TestTableauMigration(unittest.TestCase):
    """Tests pour la migration Tableau vers Power BI"""
    
    @classmethod
    def setUpClass(cls):
        """Configuration initiale"""
        cls.export_dir = '../tableau_export/'
        cls.converted_dir = 'artifacts/powerbi_objects/'
        cls.results = {
            'timestamp': datetime.now().isoformat(),
            'tests': [],
        }
    
    def load_json(self, directory, filename):
        """Charge un fichier JSON"""
        path = os.path.join(directory, filename)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def test_01_extraction_files_exist(self):
        """Test 1: Vérifier que les fichiers d'extraction existent"""
        expected_files = [
            'worksheets.json',
            'dashboards.json',
            'datasources.json',
            'calculations.json',
            'parameters.json',
            'filters.json',
            'stories.json',
        ]
        
        if not os.path.isdir(self.export_dir):
            self.skipTest("Export directory not found (run extraction first)")
        for filename in expected_files:
            path = os.path.join(self.export_dir, filename)
            self.assertTrue(os.path.exists(path), f"Fichier manquant: {filename}")
        
        print("[OK] Tous les fichiers d'extraction sont presents")
    
    def test_02_conversion_files_exist(self):
        """Test 2: Vérifier que les fichiers de conversion existent"""
        expected_files = [
            'worksheets_powerbi.json',
            'dashboards_powerbi.json',
            'datasources_powerbi.json',
            'calculations_powerbi.json',
            'parameters_powerbi.json',
            'filters_powerbi.json',
            'stories_powerbi.json',
        ]
        
        if not os.path.isdir(self.converted_dir) or not any(
            f.endswith('_powerbi.json') for f in os.listdir(self.converted_dir)
        ):
            self.skipTest("Converted files not found (legacy pipeline not run)")
        for filename in expected_files:
            path = os.path.join(self.converted_dir, filename)
            self.assertTrue(os.path.exists(path), f"Fichier manquant: {filename}")
        
        print("[OK] Tous les fichiers de conversion sont presents")
    
    def test_03_worksheets_conversion(self):
        """Test 3: Valider la conversion des worksheets"""
        tableau_worksheets = self.load_json(self.export_dir, 'worksheets.json')
        powerbi_visuals = self.load_json(self.converted_dir, 'worksheets_powerbi.json')
        
        if tableau_worksheets and powerbi_visuals:
            self.assertEqual(len(tableau_worksheets), len(powerbi_visuals),
                           "Le nombre de worksheets ne correspond pas")
            
            for visual in powerbi_visuals:
                self.assertIn('name', visual, "Visuel sans nom")
                self.assertIn('visualType', visual, "Visuel sans type")
                self.assertIn('dataFields', visual, "Visuel sans champs")
            
            print(f"[OK] {len(powerbi_visuals)} worksheets converties correctement")
    
    def test_04_dashboards_conversion(self):
        """Test 4: Valider la conversion des dashboards"""
        tableau_dashboards = self.load_json(self.export_dir, 'dashboards.json')
        powerbi_reports = self.load_json(self.converted_dir, 'dashboards_powerbi.json')
        
        if tableau_dashboards and powerbi_reports:
            self.assertEqual(len(tableau_dashboards), len(powerbi_reports),
                           "Le nombre de dashboards ne correspond pas")
            
            for report in powerbi_reports:
                self.assertIn('name', report, "Rapport sans nom")
                self.assertIn('pages', report, "Rapport sans pages")
            
            print(f"[OK] {len(powerbi_reports)} dashboards convertis correctement")
    
    def test_05_datasources_conversion(self):
        """Test 5: Valider la conversion des datasources"""
        tableau_datasources = self.load_json(self.export_dir, 'datasources.json')
        powerbi_datasets = self.load_json(self.converted_dir, 'datasources_powerbi.json')
        
        if tableau_datasources and powerbi_datasets:
            self.assertEqual(len(tableau_datasources), len(powerbi_datasets),
                           "Le nombre de datasources ne correspond pas")
            
            for dataset in powerbi_datasets:
                self.assertIn('name', dataset, "Dataset sans nom")
                self.assertIn('tables', dataset, "Dataset sans tables")
            
            print(f"[OK] {len(powerbi_datasets)} datasources converties correctement")
    
    def test_06_calculations_conversion(self):
        """Test 6: Valider la conversion des calculs"""
        tableau_calculations = self.load_json(self.export_dir, 'calculations.json')
        powerbi_measures = self.load_json(self.converted_dir, 'calculations_powerbi.json')
        
        if tableau_calculations and powerbi_measures:
            for measure in powerbi_measures:
                self.assertIn('name', measure, "Mesure sans nom")
                self.assertIn('expression', measure, "Mesure sans expression DAX")
                
                # Vérifier que l'expression n'est pas vide
                self.assertNotEqual(measure['expression'].strip(), '',
                                  f"Expression DAX vide pour {measure.get('name')}")
            
            print(f"[OK] {len(powerbi_measures)} calculs convertis en DAX")
    
    def test_07_parameters_conversion(self):
        """Test 7: Valider la conversion des paramètres"""
        tableau_parameters = self.load_json(self.export_dir, 'parameters.json')
        powerbi_parameters = self.load_json(self.converted_dir, 'parameters_powerbi.json')
        
        if tableau_parameters and powerbi_parameters:
            self.assertEqual(len(tableau_parameters), len(powerbi_parameters),
                           "Le nombre de paramètres ne correspond pas")
            
            for param in powerbi_parameters:
                self.assertIn('name', param, "Paramètre sans nom")
                self.assertIn('dataType', param, "Paramètre sans type")
            
            print(f"[OK] {len(powerbi_parameters)} parametres convertis correctement")
    
    def test_08_filters_conversion(self):
        """Test 8: Valider la conversion des filtres"""
        tableau_filters = self.load_json(self.export_dir, 'filters.json')
        powerbi_filters = self.load_json(self.converted_dir, 'filters_powerbi.json')
        
        if tableau_filters and powerbi_filters:
            for filt in powerbi_filters:
                self.assertIn('field', filt, "Filtre sans champ")
                self.assertIn('filterType', filt, "Filtre sans type")
            
            print(f"[OK] {len(powerbi_filters)} filtres convertis correctement")
    
    def test_09_stories_conversion(self):
        """Test 9: Valider la conversion des stories"""
        tableau_stories = self.load_json(self.export_dir, 'stories.json')
        powerbi_bookmarks = self.load_json(self.converted_dir, 'stories_powerbi.json')
        
        if tableau_stories and powerbi_bookmarks:
            for story in powerbi_bookmarks:
                self.assertIn('name', story, "Story sans nom")
                self.assertIn('bookmarks', story, "Story sans signets")
            
            print(f"[OK] {len(powerbi_bookmarks)} stories converties en signets")
    
    def test_10_data_integrity(self):
        """Test 10: Vérifier l'intégrité des données converties"""
        # Charger tous les fichiers convertis
        worksheets = self.load_json(self.converted_dir, 'worksheets_powerbi.json')
        dashboards = self.load_json(self.converted_dir, 'dashboards_powerbi.json')
        
        if worksheets and dashboards:
            # Vérifier que les références de worksheets dans les dashboards existent
            for dashboard in dashboards:
                for page in dashboard.get('pages', []):
                    for container in page.get('visualContainers', []):
                        visual_ref = container.get('visual', {})
                        if visual_ref.get('type') == 'worksheetReference':
                            worksheet_name = visual_ref.get('worksheetName', '')
                            worksheet_exists = any(
                                ws.get('name') == worksheet_name for ws in worksheets
                            )
                            self.assertTrue(
                                worksheet_exists,
                                f"Worksheet référencée non trouvée: {worksheet_name}"
                            )
            
            print("[OK] Integrite des references validee")
    
    @classmethod
    def tearDownClass(cls):
        """Sauvegarde des résultats"""
        results_dir = 'artifacts/test_results/'
        os.makedirs(results_dir, exist_ok=True)
        
        results_file = os.path.join(
            results_dir,
            f'test_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(cls.results, f, indent=2, ensure_ascii=False)
        
        print(f"\n[STATS] Resultats sauvegardes: {results_file}")


def run_tests():
    """Exécute tous les tests"""
    print("=" * 80)
    print("TESTS DE MIGRATION TABLEAU → POWER BI")
    print("=" * 80)
    print()
    
    # Créer la suite de tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestTableauMigration)
    
    # Exécuter les tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Résumé
    print()
    print("=" * 80)
    print("RÉSUMÉ DES TESTS")
    print("=" * 80)
    print(f"Tests exécutés: {result.testsRun}")
    print(f"Succès: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Échecs: {len(result.failures)}")
    print(f"Erreurs: {len(result.errors)}")
    print()
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
