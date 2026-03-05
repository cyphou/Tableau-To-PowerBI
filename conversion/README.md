# conversion — Per-Object-Type Converters

Individual conversion modules for each Tableau object type to Power BI.

> **Note**: these converters are used by the legacy 4-step pipeline (`migrate.py` → `convert_all_tableau_objects.py`). The main pipeline directly uses `enhanced_datasource_extractor.py` + `enhanced_bim_generator.py`.

## Modules

| Module | Conversion |
|--------|-----------|
| `calculation_converter.py` | Tableau formulas → DAX measures |
| `worksheet_converter.py` | Worksheets → Power BI visuals |
| `dashboard_converter.py` | Dashboards → report pages |
| `datasource_converter.py` | Datasources → datasets |
| `filter_converter.py` | Filters → Power BI filters |
| `parameter_converter.py` | Parameters → Power BI parameters |
| `story_converter.py` | Stories → bookmarks |
| `convert_all_tableau_objects.py` | Orchestrator for all converters |
