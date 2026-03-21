# FAQ — Tableau to Power BI Migration

## General

### Which Tableau files are supported?

`.twb` (XML workbooks) and `.twbx` (packaged workbooks with data). `.tds`/`.tdsx` (datasources) are also supported by the extractor.

### What is a `.pbip` file?

It is a **Power BI Project** — a text-based file format (JSON + TMDL) that represents a complete Power BI report. It opens directly in Power BI Desktop by double-clicking.

### Do I need to install Python dependencies?

No. The core migration uses only the Python standard library (xml, json, os, uuid, re, etc.).

Optional dependencies for advanced features:
- `azure-identity` + `requests` — for Fabric workspace deployment
- `pydantic-settings` — for typed configuration (falls back to env vars)

## Migration

### How do I run a migration?

```bash
python migrate.py your_workbook.twbx
```

Or with additional options:

```bash
# Custom output directory
python migrate.py your_workbook.twbx --output-dir /tmp/output

# Verbose logging
python migrate.py your_workbook.twbx --verbose

# Batch migrate all workbooks in a directory
python migrate.py --batch examples/tableau_samples/ --output-dir /tmp/batch_output

# With Tableau Prep flow
python migrate.py your_workbook.twbx --prep flow.tfl

# Log to file
python migrate.py your_workbook.twbx --log-file migration.log
```

Or step by step:

```bash
python tableau_export/extract_tableau_data.py your_workbook.twbx
python powerbi_import/import_to_powerbi.py
```

### Where is the output?

In `artifacts/powerbi_projects/[ReportName]/[ReportName].pbip`. Double-click to open in Power BI Desktop.

### Why do some formulas not work?

Some Tableau functions have no direct DAX equivalent:

- `MAKEPOINT()` — no DAX equivalent; use lat/lon columns in a map visual
- `PREVIOUS_VALUE()` — automatically converted to OFFSET-based DAX pattern (may need manual adjustment for complex seed logic)
- `LOOKUP()` — automatically converted to OFFSET-based DAX pattern
- Table functions (`SIZE()` → `COUNTROWS(ALLSELECTED())`, `INDEX()` → `RANKX()`) — approximated, may need adjustment

Most complex patterns **are** handled automatically:
- LOD expressions (`{ FIXED ... }`) → `CALCULATE` + `ALLEXCEPT` / `REMOVEFILTERS` / `ALL`
- `SUM(IF ...)` → `SUMX('table', IF(...))` iterator conversion
- Nested `IF/ELSEIF/ELSE/END` → nested `IF()` calls
- Window functions (`WINDOW_AVG`, `WINDOW_SUM`) → `CALCULATE(..., ALL('table'))`
- Table calculations (`RUNNING_SUM`, `RANK`) → `CALCULATE(SUM(...))`, `RANKX(ALL(...))`

### How are LOD expressions converted?

LOD (Level of Detail) expressions are one of the most complex Tableau features. The tool converts them automatically:

```
{FIXED [Region] : SUM([Sales])}
→ CALCULATE(SUM('Table'[Sales]), ALLEXCEPT('Table', 'Table'[Region]))

{FIXED [Region], [Category] : SUM([Sales])}
→ CALCULATE(SUM(...), ALLEXCEPT('Table', 'Table'[Region], 'Table'[Category]))

{EXCLUDE [Category] : SUM([Sales])}
→ CALCULATE(SUM(...), REMOVEFILTERS('Table'[Category]))

{FIXED : SUM(IF YEAR([Date]) = YEAR(TODAY()) THEN [Amount] ELSE 0 END)}
→ CALCULATE(SUMX('Table', IF(YEAR(...) = YEAR(TODAY()), ...)), ALL('Table'))
```

### How does the SUM(IF) → SUMX conversion work?

In Tableau, `SUM(IF condition THEN value ELSE 0 END)` is common. DAX's `SUM()` only accepts a single column, so the tool converts to iterator functions:

```
Tableau: SUM(IF [type] = "Revenue" THEN [amount] ELSE 0 END)
DAX:     SUMX('transactions', IF('transactions'[type] = "Revenue", 'transactions'[amount], 0))
```

This applies to all aggregate+condition patterns:
- `SUM(IF ...)` → `SUMX`
- `AVG(IF ...)` → `AVERAGEX`
- `MIN(IF ...)` → `MINX`
- `MAX(IF ...)` → `MAXX`
- `COUNT(IF ...)` → `COUNTX`

### How is Row-Level Security (RLS) migrated?

Tableau has multiple security mechanisms, all converted to Power BI RLS roles:

1. **User filters** (`<user-filter>` with user→value mappings):
   ```tmdl
   role 'Region Access'
       tablePermission Orders
           filterExpression = (USERPRINCIPALNAME() = "alice@co.com" && [Region] IN {"East", "West"}) || ...
   ```

2. **USERNAME() / FULLNAME() calculations**:
   ```tmdl
   role 'Is Current User'
       tablePermission Orders
           filterExpression = 'Orders'[Email] = USERPRINCIPALNAME()
   ```

3. **ISMEMBEROF("group")** — creates a separate role per group:
   ```tmdl
   role Managers
       tablePermission Orders
           filterExpression = TRUE()  /* Assign Azure AD group members to this role */
   ```

### What about parameters?

Tableau parameters are converted to Power BI What-If parameter tables:

- **Integer/real range** → `GENERATESERIES(min, max, step)` table + `SELECTEDVALUE` measure
- **String list** → `DATATABLE("Value", STRING, {{"val1"}, {"val2"}})` table + `SELECTEDVALUE` measure
- **Date parameters** → static measure with default value

When a calculated column references a parameter, the value is **inlined** (since calc columns can't reference measures in DAX).

### How do I generate Fabric-native output?

Use `--output-format fabric` to generate Lakehouse, Dataflow Gen2, PySpark Notebook, DirectLake Semantic Model, and Data Pipeline artifacts instead of a .pbip project:

```bash
python migrate.py workbook.twbx --output-format fabric --output-dir /tmp/fabric_output
```

### How do I optimize the generated DAX formulas?

Use `--optimize-dax` to run an AST-based DAX optimizer pass after conversion. This rewrites verbose formulas for readability and performance:

```bash
python migrate.py workbook.twbx --optimize-dax --time-intelligence auto
```

The optimizer applies: nested IF→SWITCH, IF(ISBLANK)→COALESCE, redundant CALCULATE collapse, constant folding, SUMX simplification, and optional Time Intelligence auto-injection (YTD, PY, YoY%).

### How do I reconfigure the data sources?

1. Open the `.pbip` in Power BI Desktop
2. Go to Power Query Editor (Transform Data)
3. Edit the source parameters in each query
4. Close and Apply

## Technical

### What is the difference between a measure and a calculated column?

- **Measure**: computed at aggregation time (e.g., `SUM`, `AVERAGE`). Adapts to the filter context.
- **Calculated column**: computed row by row, stored in the model. Like an added column.

The tool classifies automatically:
- Tableau `role=measure` → DAX measure
- Tableau `role=dimension` → calculated column

### Why does `RELATED()` appear in some formulas?

In calculated columns, to access a column from another related table, DAX requires `RELATED('OtherTable'[column])`. The tool adds `RELATED()` automatically when the column belongs to a different table.

### What is the TMDL format?

**Tabular Model Definition Language** — a text format for describing Power BI semantic models. It is the successor to the `model.bim` JSON, used in `.pbip` projects.

### How do relationships work?

Tableau relationships (joins) are converted to Power BI relationships:
- `LEFT JOIN` → `toColumn` with `crossFilteringBehavior: oneDirection`
- `FULL OUTER JOIN` → `crossFilteringBehavior: bothDirections`
- Join columns become the relationship keys

## Validation & Deployment

### How do I validate generated projects?

Use the built-in `ArtifactValidator` to check project integrity before opening in Power BI Desktop:

```python
from powerbi_import.validator import ArtifactValidator

result = ArtifactValidator.validate_project("artifacts/powerbi_projects/MyReport")
print(result)  # {"valid": True, "files_checked": 15, "errors": []}

# Batch validate all projects
results = ArtifactValidator.validate_directory("artifacts/powerbi_projects/")
```

The validator checks: `.pbip` JSON, Report directory (report.json, pages, visuals), SemanticModel directory (model.tmdl starts with `model Model`, table TMDLs).

### How do I deploy to Microsoft Fabric?

1. Install optional dependencies: `pip install azure-identity requests`
2. Set environment variables:
   ```bash
   export FABRIC_WORKSPACE_ID="your-workspace-guid"
   export FABRIC_TENANT_ID="your-tenant-guid"
   export FABRIC_CLIENT_ID="your-app-client-id"
   export FABRIC_CLIENT_SECRET="your-app-secret"
   ```
3. Deploy:
   ```python
   from powerbi_import.deployer import FabricDeployer
   deployer = FabricDeployer(workspace_id='your-workspace-guid')
   deployer.deploy_artifacts_batch('artifacts/powerbi_projects/')
   ```

Service Principal and Managed Identity authentication are both supported.

### How do I batch-migrate multiple workbooks?

```bash
python migrate.py --batch /path/to/tableau/files/ --output-dir /tmp/output
```

This processes all `.twb` and `.twbx` files in the directory and generates separate .pbip projects for each.

### How do I merge multiple workbooks into a shared semantic model?

Use `--shared-model` to merge workbooks that share the same data sources into one Power BI semantic model with thin reports:

```bash
# Pre-assessment (see merge score before generating)
python migrate.py --shared-model wb1.twbx wb2.twbx --assess-merge

# Generate shared model + thin reports
python migrate.py --shared-model wb1.twbx wb2.twbx --model-name "Sales Model"

# Batch all workbooks in a directory
python migrate.py --batch /path/to/workbooks/ --shared-model

# Force merge even with low overlap score
python migrate.py --shared-model wb1.twbx wb2.twbx --force-merge
```

The merge engine uses fingerprint-based table matching — tables are matched by `connection_type|server|database|table_name`, so workbooks connecting to the same physical database tables are automatically detected as merge candidates.

**Merge scores:**
- **≥60** — MERGE RECOMMENDED: high table overlap, few conflicts
- **30–59** — PARTIAL: some overlap but significant differences
- **<30** — KEEP SEPARATE: different data sources, use `--force-merge` to override

### What is a thin report?

A thin report is a Power BI report (`.pbip`) that doesn’t contain its own semantic model. Instead, it references a shared semantic model via a `byPath` pointer in `definition.pbir`:

```json
{
  "datasetReference": {
    "byPath": {
      "path": "../SharedModel.SemanticModel"
    }
  }
}
```

This allows multiple reports to share one data model — changes to the model (tables, measures, relationships) are reflected in all thin reports automatically.

### How are measure conflicts resolved during merge?

- **Identical measures** (same name + same DAX formula) → deduplicated (kept once)
- **Conflicting measures** (same name, different formula) → namespaced as `MeasureName (WorkbookName)` in the shared model
- **Unique measures** (name only in one workbook) → kept as-is

The `merge_assessment.json` file lists all conflicts detected.

### How do I run the tests?

```bash
python -m pytest tests/ -v
```

The project includes **6,192 tests across 128 test files** covering DAX conversion, Power Query M generation, TMDL model building, visual generation, project structure, artifact validation, deployment utilities, Fabric-native generation, DAX optimization, cross-platform equivalence testing, and end-to-end non-regression migration of all 16 real-world workbooks.
