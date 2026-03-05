# tableau_export — Tableau Extraction

Extracts metadata from Tableau `.twb` and `.twbx` files.

## Modules

### `extract_tableau_data.py`

Extraction orchestrator. Parses the Tableau XML, decompresses `.twbx` files, and calls the enhanced extractor.

```bash
python tableau_export/extract_tableau_data.py your_workbook.twbx
```

### `enhanced_datasource_extractor.py`

Main extractor. For each Tableau datasource:

- **Physical tables**: name, columns, data types, per-table connection
- **Calculations**: raw formula, caption, role (dimension/measure), type
- **Relationships**: joins between tables (LEFT, INNER, FULL)
- **Connections**: Excel, CSV, GeoJSON, SQL Server, PostgreSQL
- **Parameters**: names and default values

Also includes the **DAX converter** (`convert_tableau_formula_to_dax()`) which transforms Tableau formulas into valid DAX.

## Output

JSON files in `tableau_export/`:

| File | Content |
|------|---------|
| `datasources.json` | Tables, columns, calculations, relationships, connections (**used by the pipeline**) |
| `worksheets.json` | Sheets and visuals |
| `dashboards.json` | Dashboards |
| `calculations.json` | Calculated fields |
| `parameters.json` | Parameters |
| `filters.json` | Filters |
| `stories.json` | Stories |

> **Note**: only `datasources.json` is used by the `.pbip` generation pipeline. The other JSON files are informational.
