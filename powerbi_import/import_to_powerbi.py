"""
Import orchestrator for Power BI project generation.

Loads extracted Tableau JSON files and drives the .pbip project
generation pipeline (BIM model + TMDL + PBIR report).
"""

import os
import json
import uuid
from datetime import datetime
from pbip_generator import PowerBIProjectGenerator


def _write_json_file(path, data):
    """Write a JSON file with consistent formatting."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class PowerBIImporter:
    """Power BI object importer"""
    
    def __init__(self, source_dir=None):
        self.source_dir = source_dir or 'tableau_export/'
    
    def import_all(self, generate_pbip=True, report_name=None, output_dir=None,
                   calendar_start=None, calendar_end=None, culture=None,
                   model_mode='import', output_format='pbip', languages=None):
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
                                          culture=culture, model_mode=model_mode,
                                          output_format=output_format, languages=languages)
        
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
                                 calendar_start=None, calendar_end=None, culture=None,
                                 model_mode='import', output_format='pbip', paginated=False,
                                 languages=None):
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
                projects_dir = os.path.join(artifacts_dir, 'powerbi_projects', 'migrated')
            
            artifacts_dir = os.path.abspath('artifacts')
            generator = PowerBIProjectGenerator(
                output_dir=projects_dir
            )
            
            project_path = generator.generate_project(report_name, converted_objects,
                                                       calendar_start=calendar_start,
                                                       calendar_end=calendar_end,
                                                       culture=culture,
                                                       model_mode=model_mode,
                                                       output_format=output_format,
                                                       paginated=paginated,
                                                       languages=languages)
            print(f"  [OK] Power BI Project created: {project_path}")
            
        except Exception as e:
            print(f"  [WARN] Error generating Power BI Project: {str(e)}")

    def import_shared_model(self, model_name, all_converted_objects,
                            workbook_names, output_dir=None,
                            calendar_start=None, calendar_end=None,
                            culture=None, model_mode='import',
                            languages=None, force_merge=False,
                            merge_config_path=None, save_config=False):
        """Generate a shared semantic model + thin reports.

        Args:
            model_name: Name for the shared semantic model.
            all_converted_objects: List of converted_objects dicts (one per workbook).
            workbook_names: List of workbook names (parallel with all_converted_objects).
            output_dir: Custom output directory.
            calendar_start: Start year for Calendar table.
            calendar_end: End year for Calendar table.
            culture: Override culture/locale.
            model_mode: Semantic model mode (import/directquery/composite).
            languages: Additional locale strings.
            force_merge: Force merge even with low score.
            merge_config_path: Path to merge config JSON (load saved decisions).
            save_config: Save merge decisions to config file.

        Returns:
            dict with 'assessment', 'model_path', 'report_paths', plus new fields.
        """
        from powerbi_import.shared_model import (
            assess_merge, merge_semantic_models, build_field_mapping,
            validate_thin_report_fields, build_column_lineage,
            generate_lineage_annotations, analyze_measure_risk,
            consolidate_rls_roles, merge_rls_roles,
            build_cross_report_navigation,
        )
        from powerbi_import.merge_assessment import generate_merge_report, print_merge_summary
        from powerbi_import.thin_report_generator import ThinReportGenerator

        print("=" * 64)
        print("  SHARED SEMANTIC MODEL MIGRATION")
        print("=" * 64)

        # 1. Assess merge feasibility
        print("\n  Step 1: Analyzing merge candidates...")
        assessment = assess_merge(all_converted_objects, workbook_names)

        # 1b. Load merge config if provided
        if merge_config_path:
            from powerbi_import.merge_config import load_merge_config, apply_merge_config
            print(f"  Loading merge config: {merge_config_path}")
            config = load_merge_config(merge_config_path)
            assessment = apply_merge_config(assessment, config)

        print_merge_summary(assessment)

        if assessment.recommendation == 'separate' and not force_merge:
            print("  Merge not recommended (score too low). Use --force-merge to override.")
            return {'assessment': assessment, 'model_path': None, 'report_paths': []}

        # 1c. Report isolated tables (excluded from shared model)
        if assessment.isolated_tables:
            total_isolated = sum(len(v) for v in assessment.isolated_tables.values())
            print(f"\n  Step 1c: {total_isolated} isolated table(s) excluded from shared model")
            for wb, tables in assessment.isolated_tables.items():
                for t in tables:
                    print(f"    [skip] {t} — no link to other workbooks (stays in {wb} report only)")

        # 1d. Analyze measure risks
        risk_analysis = []
        if assessment.measure_conflicts:
            print("\n  Step 1d: Analyzing measure conflict risks...")
            risk_analysis = analyze_measure_risk(assessment.measure_conflicts)
            for ra in risk_analysis:
                icon = {"low": "✓", "medium": "⚠", "high": "✗"}.get(ra.risk_level, "?")
                print(f"    [{icon}] {ra.measure_name}: {ra.risk_level} — {ra.reason}")

        # 1e. Consolidate RLS roles
        rls_consolidations = consolidate_rls_roles(all_converted_objects, workbook_names)
        if rls_consolidations:
            print(f"\n  Step 1e: RLS role consolidation ({len(rls_consolidations)} roles)...")
            for cons in rls_consolidations:
                print(f"    [{cons.action}] {cons.role_name} from {', '.join(cons.source_workbooks)}")

        # 2. Merge into unified dataset
        print("\n  Step 2: Merging semantic models...")
        merged = merge_semantic_models(all_converted_objects, assessment, model_name)

        # 2b. Apply RLS consolidation
        merged_rls = merge_rls_roles(all_converted_objects, workbook_names)
        if merged_rls:
            merged['user_filters'] = merged_rls

        # 2c. Build column lineage
        lineage = build_column_lineage(all_converted_objects, workbook_names, assessment)
        lineage_annotations = generate_lineage_annotations(lineage)

        # Store lineage annotations in merged data for TMDL generator
        if lineage_annotations:
            merged['_lineage_annotations'] = lineage_annotations

        # 3. Determine output directory
        if output_dir:
            projects_dir = os.path.abspath(output_dir)
        else:
            projects_dir = os.path.abspath(
                os.path.join('artifacts', 'powerbi_projects', 'shared')
            )
        os.makedirs(projects_dir, exist_ok=True)

        # 4. Generate the shared semantic model
        print(f"\n  Step 3: Generating shared semantic model '{model_name}'...")
        generator = PowerBIProjectGenerator(output_dir=projects_dir)

        # Store generation options
        generator._calendar_start = calendar_start
        generator._calendar_end = calendar_end
        generator._culture = culture
        generator._model_mode = model_mode or 'import'
        generator._languages = languages

        # Create the project directory
        project_dir = os.path.join(projects_dir, model_name)
        os.makedirs(project_dir, exist_ok=True)

        # Generate SemanticModel
        sm_dir = generator.create_semantic_model_structure(
            project_dir, model_name, merged
        )
        print(f"  [OK] Shared SemanticModel created: {sm_dir}")

        # Create a model-explorer report so the model can be opened in PBI Desktop
        self._create_model_explorer_report(project_dir, model_name)

        # 5. Generate thin reports for each workbook
        print(f"\n  Step 4: Generating {len(workbook_names)} thin reports...")
        report_paths = []
        validation_issues = []

        thin_gen = ThinReportGenerator(model_name, project_dir)

        # Build cross-report navigation
        nav_configs = build_cross_report_navigation(workbook_names, model_name)

        for wb_name, wb_data in zip(workbook_names, all_converted_objects):
            field_mapping = build_field_mapping(assessment, wb_name)

            # Validate fields before generating
            issues = validate_thin_report_fields(wb_data, merged, field_mapping)
            if issues:
                validation_issues.extend(issues)
                for issue in issues[:3]:
                    print(f"    [WARN] {wb_name}: orphaned field '{issue['field']}' in {issue['location']}")

            report_path = thin_gen.generate_thin_report(
                wb_name, wb_data, field_mapping=field_mapping
            )
            report_paths.append(report_path)
            print(f"    [OK] Thin report: {wb_name}")

        # 6. Save artifacts (assessment, config, lineage, HTML report)
        self._save_shared_model_artifacts(
            project_dir, assessment, lineage, save_config,
            workbook_names, all_converted_objects, merged, model_name,
        )

        print(f"\n  Shared Semantic Model migration complete!")
        print(f"  Output: {project_dir}")

        return {
            'assessment': assessment,
            'model_path': sm_dir,
            'report_paths': report_paths,
            'validation_issues': validation_issues,
            'risk_analysis': risk_analysis,
            'rls_consolidations': rls_consolidations,
            'lineage': lineage,
            'navigation': nav_configs,
        }

    def _create_model_explorer_report(self, project_dir, model_name):
        """Create a model-explorer report so the model can be opened in PBI Desktop.

        PBI Desktop requires a .Report artifact to open a .pbip file.
        """
        model_report_name = f"{model_name}_Model"
        model_report_dir = os.path.join(project_dir, f"{model_report_name}.Report")
        os.makedirs(os.path.join(model_report_dir, 'definition'), exist_ok=True)

        # .platform
        _write_json_file(os.path.join(model_report_dir, '.platform'), {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Report", "displayName": model_report_name},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
        })

        # definition.pbir -> byPath to the shared model
        _write_json_file(os.path.join(model_report_dir, 'definition.pbir'), {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {
                "byPath": {"path": f"../{model_name}.SemanticModel"},
            },
        })

        # Minimal report.json (empty report -- user opens Model view)
        _write_json_file(os.path.join(model_report_dir, 'definition', 'report.json'), {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.1.0/schema.json",
            "name": model_report_name,
            "description": f"Model explorer for shared semantic model '{model_name}'. Open this to view and edit the data model.",
        })

        # version.json
        _write_json_file(os.path.join(model_report_dir, 'definition', 'version.json'), {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
            "dataFormatVersion": "2.0",
        })

        # .pbip pointing to the model-explorer report
        _write_json_file(os.path.join(project_dir, f"{model_name}.pbip"), {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": f"{model_report_name}.Report"}}],
            "settings": {"enableAutoRecovery": True},
        })
        print(f"  [OK] Model explorer .pbip: {model_name}.pbip → {model_report_name}.Report")

    def _save_shared_model_artifacts(self, project_dir, assessment, lineage,
                                      save_config, workbook_names,
                                      all_converted_objects, merged, model_name):
        """Save merge assessment, config, lineage, and HTML report artifacts."""
        from powerbi_import.merge_assessment import generate_merge_report

        # Write merge assessment report
        assess_path = os.path.join(project_dir, 'merge_assessment.json')
        generate_merge_report(assessment, output_path=assess_path)
        print(f"\n  [OK] Merge assessment saved: {assess_path}")

        # Save merge config if requested
        if save_config:
            from powerbi_import.merge_config import save_merge_config
            config_path = os.path.join(project_dir, 'merge_config.json')
            save_merge_config(assessment, workbook_names, config_path, merged)
            print(f"  [OK] Merge config saved: {config_path}")

        # Save lineage report
        if lineage:
            lineage_path = os.path.join(project_dir, 'column_lineage.json')
            with open(lineage_path, 'w', encoding='utf-8') as f:
                json.dump(lineage, f, indent=2, ensure_ascii=False)
            print(f"  [OK] Column lineage saved: {lineage_path}")

        # Generate HTML merge report
        try:
            from powerbi_import.merge_report_html import generate_merge_html_report
        except ImportError:
            from merge_report_html import generate_merge_html_report

        html_path = os.path.join(project_dir, 'MERGE_REPORT.html')
        generate_merge_html_report(
            assessment=assessment,
            all_extracted=all_converted_objects,
            workbook_names=workbook_names,
            merged=merged,
            model_name=model_name,
            output_path=html_path,
        )
        print(f"  [OK] HTML merge report: {html_path}")


def main():
    """Main entry point"""
    
    import sys
    
    # Option to disable .pbip generation
    generate_pbip = '--no-pbip' not in sys.argv
    
    importer = PowerBIImporter()
    importer.import_all(generate_pbip=generate_pbip)


if __name__ == '__main__':
    main()
