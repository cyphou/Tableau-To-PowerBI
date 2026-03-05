# powerbi_import — Power BI Generation

Generates complete Power BI projects (`.pbip`) from extracted Tableau data.

## Modules

### `import_to_powerbi.py`

Main orchestrator. Reads `tableau_export/datasources.json` and generates the `.pbip` project.

```bash
python powerbi_import/import_to_powerbi.py
```

### `enhanced_bim_generator.py`

Builds the BIM (Business Intelligence Model) JSON:

- **Physical tables**: columns with types, M partitions
- **Calculated columns**: DAX formulas for `role=dimension` calculations
- **Measures**: DAX formulas for `role=measure` calculations and parameters
- **Relationships**: foreign keys between tables
- **DAX context**: `calc_map`, `param_map`, `column_table_map`, `measure_names`, `param_values`

### `pbip_generator.py`

Generates the complete `.pbip` file structure:

- `.pbip` file (entry point)
- SemanticModel (TMDL via `tmdl_generator.py`)
- Report (PBIR v4.0: `report.json`, `pages.json`, `visual.json`)
- `.platform` files and metadata

### `tmdl_generator.py`

Converts BIM JSON into TMDL (Tabular Model Definition Language) files:

- `database.tmdl` — compatibility
- `model.tmdl` — culture, data source version
- `relationships.tmdl` — relationships between tables
- `tables/{Table}.tmdl` — physical columns, calculated columns, measures, M partitions

### `visual_generator.py`

Generates JSON visual definitions for the report. Maps Tableau visual types to Power BI (bar chart, line chart, table, map, etc.).

### `m_query_generator.py`

Generates Power Query M queries for the different data source types.

## Format de sortie

**PBIR v4.0** avec schemas :
- `report/3.1.0`
- `page/2.0.0`
- `visualContainer/2.5.0`
- `pbipProperties/1.0.0`
- `definitionProperties/2.0.0`
