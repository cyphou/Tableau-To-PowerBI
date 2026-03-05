"""
Import orchestrator for Power BI project generation.

Loads extracted Tableau JSON files and drives the .pbip project
generation pipeline (BIM model + TMDL + PBIR report).
"""

import os
import json
from datetime import datetime
from pbip_generator import PowerBIProjectGenerator


class PowerBIImporter:
    """Power BI object importer"""
    
    def __init__(self, source_dir=None):
        self.source_dir = source_dir or 'tableau_export/'
    
    def import_all(self, generate_pbip=True, report_name=None, output_dir=None,
                   calendar_start=None, calendar_end=None, culture=None):
        """
        Import all extracted objects and generate Power BI project
        
        Args:
            generate_pbip: If True, generates Power BI Projects (.pbip)
            report_name: Override report name (defaults to dashboard name or 'Report')
            output_dir: Custom output directory for .pbip projects
            calendar_start: Start year for Calendar table (default: 2020)
            calendar_end: End year for Calendar table (default: 2030)
            culture: Override culture/locale for semantic model
        """
        
        print("=" * 80)
        print("IMPORT POWER BI")
        print("=" * 80)
        print()
        
        # Load converted objects directly from tableau_export/
        converted_objects = self._load_converted_objects()
        
        if not converted_objects.get('datasources'):
            print(f"  [ERROR] No datasources found in {os.path.join(self.source_dir, 'datasources.json')}")
            print("     Run extraction first: python migrate.py <file>")
            return
        
        # Determine report name
        if not report_name:
            dashboards = converted_objects.get('dashboards', [])
            if dashboards:
                report_name = dashboards[0].get('name', 'Report')
            else:
                report_name = 'Report'
        
        print(f"  Report: {report_name}")
        print(f"  Datasources: {len(converted_objects.get('datasources', []))}")
        print(f"  Worksheets: {len(converted_objects.get('worksheets', []))}")
        print(f"  Calculations: {len(converted_objects.get('calculations', []))}")
        
        # Generate Power BI Project (.pbip) directly from converted objects
        if generate_pbip:
            self.generate_powerbi_project(report_name, converted_objects, output_dir=output_dir,
                                          calendar_start=calendar_start, calendar_end=calendar_end,
                                          culture=culture)
        
        print()
        print("=" * 80)
        print("IMPORT COMPLETE")
        print("=" * 80)
        print()
        if generate_pbip:
            print("[OK] Power BI Projects (.pbip) generated automatically")
            print("   Open the .pbip files in Power BI Desktop")
            print()
    
    def _load_converted_objects(self):
        """Load all extracted JSON files from the source directory."""
        data = {}
        src = self.source_dir
        files_map = {
            'datasources': os.path.join(src, 'datasources.json'),
            'worksheets': os.path.join(src, 'worksheets.json'),
            'dashboards': os.path.join(src, 'dashboards.json'),
            'calculations': os.path.join(src, 'calculations.json'),
            'parameters': os.path.join(src, 'parameters.json'),
            'filters': os.path.join(src, 'filters.json'),
            'stories': os.path.join(src, 'stories.json'),
            'actions': os.path.join(src, 'actions.json'),
            'sets': os.path.join(src, 'sets.json'),
            'groups': os.path.join(src, 'groups.json'),
            'bins': os.path.join(src, 'bins.json'),
            'hierarchies': os.path.join(src, 'hierarchies.json'),
            'sort_orders': os.path.join(src, 'sort_orders.json'),
            'aliases': os.path.join(src, 'aliases.json'),
            'custom_sql': os.path.join(src, 'custom_sql.json'),
            'user_filters': os.path.join(src, 'user_filters.json'),
        }
        
        for key, filepath in files_map.items():
            try:
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data[key] = json.load(f)
                else:
                    data[key] = [] if key != 'aliases' else {}
            except Exception:
                data[key] = [] if key != 'aliases' else {}
        
        return data
    
    def generate_powerbi_project(self, report_name, converted_objects, output_dir=None,
                                 calendar_start=None, calendar_end=None, culture=None):
        """Generate a Power BI Project (.pbip)

        Args:
            report_name: Name of the report
            converted_objects: Dict of extracted Tableau objects
            output_dir: Custom output directory for .pbip project
            calendar_start: Start year for Calendar table
            calendar_end: End year for Calendar table
            culture: Override culture/locale
        """
        
        print(f"\n  Generating Power BI Project (.pbip)...")
        
        try:
            # Determine absolute path to powerbi_projects
            if output_dir:
                projects_dir = os.path.abspath(output_dir)
            else:
                artifacts_dir = os.path.abspath('artifacts')
                projects_dir = os.path.join(artifacts_dir, 'powerbi_projects')
            
            artifacts_dir = os.path.abspath('artifacts')
            generator = PowerBIProjectGenerator(
                output_dir=projects_dir
            )
            
            project_path = generator.generate_project(report_name, converted_objects,
                                                       calendar_start=calendar_start,
                                                       calendar_end=calendar_end,
                                                       culture=culture)
            print(f"  [OK] Power BI Project created: {project_path}")
            
        except Exception as e:
            print(f"  [WARN] Error generating Power BI Project: {str(e)}")


def main():
    """Main entry point"""
    
    import sys
    
    # Option to disable .pbip generation
    generate_pbip = '--no-pbip' not in sys.argv
    
    importer = PowerBIImporter()
    importer.import_all(generate_pbip=generate_pbip)


if __name__ == '__main__':
    main()
