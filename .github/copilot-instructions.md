<!-- Copilot instructions for the Tableau to Power BI migration project -->

# Project: Tableau to Power BI Migration

Automated migration of Tableau workbooks (.twb/.twbx) to Power BI projects (.pbip) in PBIR v4.0 format with TMDL semantic model.

## Architecture — 2-Step Pipeline

```
.twbx --> [Extraction] --> 16 JSON files --> [Generation] --> .pbip (PBIR + TMDL)
```

1. **Extraction** (`tableau_export/`): Parses Tableau XML, extracts worksheets/dashboards/datasources/calculations/parameters/filters/stories/actions/sets/groups/bins/hierarchies/sort_orders/aliases/custom_sql
2. **Generation** (`powerbi_import/`): Produces the complete .pbip project (BIM → TMDL, PBIR v4.0 report, Power Query M, visuals, filters, bookmarks)

## Project Structure

- **tableau_export/**: Tableau XML extraction and parsing + DAX formula conversion
  - `extract_tableau_data.py`: Main orchestrator, parses TWB/TWBX, extracts 16 object types
  - `datasource_extractor.py`: Datasource extraction (connections, tables, columns, calculations, relationships)
  - `dax_converter.py`: 172 Tableau → DAX formula conversions (LOD, table calcs, security, etc.)
  - `m_query_builder.py`: Power Query M generator (26 connector types + 40+ transformation generators: rename, filter, aggregate, pivot/unpivot, join, union, sort, conditional columns — chainable via `inject_m_steps()`)
  - `prep_flow_parser.py`: Tableau Prep flow parser (.tfl/.tflx → Power Query M) — DAG traversal, Clean/Join/Aggregate/Union/Pivot steps, expression converter, merge with TWB datasources
- **powerbi_import/**: Power BI project generation
  - `pbip_generator.py`: .pbip generator (PBIR v4.0, visuals, filters, bookmarks, slicers, textbox, image)
  - `tmdl_generator.py`: Unified semantic model generator — direct Tableau → TMDL (tables, columns, measures, relationships, hierarchies, sets/groups/bins, parameters, RLS, dataCategory, isHidden)
  - `visual_generator.py`: Visual container generator — 60+ visual type mappings, PBIR-native config templates, data role definitions, query state builder, slicer sync groups, cross-filtering disable, action button navigation, TopN filters, sort state, reference lines, conditional formatting
  - `import_to_powerbi.py`: Generation pipeline orchestrator (supports `--output-dir`)
  - `m_query_generator.py`: Sample data M query generator
  - `validator.py`: Artifact validator — validates .pbip projects (JSON, TMDL, report structure) before opening in PBI Desktop
  - `migration_report.py`: Per-item fidelity tracking and migration status reporting
  - `deploy/`: Fabric deployment subpackage
    - `auth.py`: Azure AD authentication — Service Principal + Managed Identity (optional `azure-identity`)
    - `client.py`: Fabric REST API client — auto-detects `requests` with retry, falls back to `urllib`
    - `deployer.py`: Fabric deployment orchestrator — deploy datasets, reports, batch directories
    - `utils.py`: `DeploymentReport` (pass/fail tracking), `ArtifactCache` (incremental deployment metadata)
    - `config/settings.py`: Centralized config via env vars (FABRIC_WORKSPACE_ID, FABRIC_TENANT_ID, etc.)
    - `config/environments.py`: Per-environment configs (development/staging/production)
- **tests/**: Unit and integration tests (725 tests)
- **docs/**: FAQ, PBI project guide, mapping reference
- **.github/workflows/ci.yml**: CI/CD pipeline (lint → test → validate → deploy)
- **artifacts/**: Migration output (generated .pbip projects)

## Technologies

- Python 3.8+ (standard library only — no external dependencies for core migration)
- Optional dependencies: `azure-identity` (Fabric auth), `requests` (HTTP client with retry), `pydantic-settings` (typed config)
- Modules: xml.etree, json, os, uuid, re, zipfile, argparse, datetime, copy, logging, glob
- Power BI Desktop (December 2025+)
- Output format: PBIR v4.0 + TMDL

## Main Command

```bash
python migrate.py path/to/workbook.twbx
python migrate.py path/to/workbook.twbx --prep path/to/flow.tfl
python migrate.py path/to/workbook.twbx --output-dir /tmp/pbi_output --verbose
python migrate.py --batch examples/tableau_samples/ --output-dir /tmp/batch_output
python migrate.py path/to/workbook.twbx --dry-run
python migrate.py path/to/workbook.twbx --calendar-start 2018 --calendar-end 2028
python migrate.py path/to/workbook.twbx --culture fr-FR
```

## Extracted Objects (16 types)

| Type | JSON File | Description |
|------|-----------|-------------|
| worksheets | worksheets.json | Sheets with fields, filters, formatting, mark_encoding, axes |
| dashboards | dashboards.json | Dashboards with objects (worksheet, text, image, filter_control) |
| datasources | datasources.json | Sources with tables, columns, relationships, connection_map |
| calculations | calculations.json | Tableau calculations (formulas, role, type) |
| parameters | parameters.json | Parameters with values, domain_type, and allowable_values (both XML formats) |
| filters | filters.json | Global filters with fields and values |
| stories | stories.json | Story points → converted to PBI bookmarks |
| actions | actions.json | Actions (filter/highlight/url/navigate/param/set) |
| sets | sets.json | Sets → boolean calculated columns |
| groups | groups.json | Manual groups → SWITCH columns |
| bins | bins.json | Intervals → FLOOR columns |
| hierarchies | hierarchies.json | Drill-paths → PBI hierarchies |
| sort_orders | sort_orders.json | Sort orders |
| aliases | aliases.json | Column aliases |
| custom_sql | custom_sql.json | Custom SQL queries |
| user_filters | user_filters.json | User filters, security rules → PBI RLS roles |

## Key Model Files

The DAX context is managed in `tmdl_generator.py` via dictionaries:
- `calc_map`: calculation ID → DAX formula
- `param_map`: parameter name → value
- `column_table_map`: column name → table name
- `measure_names`: set of measure names
- `param_values`: parameter → inline value
- `col_metadata_map`: column name → {hidden, semantic_role, description}

## Supported DAX Conversions (80+)

| Category | Tableau | DAX |
|----------|---------|-----|
| Null/Logic | ISNULL, ZN, IFNULL | ISBLANK, IF(ISBLANK) |
| Text | CONTAINS, ASCII, LEN, LEFT, RIGHT, MID, UPPER, LOWER, REPLACE, TRIM | CONTAINSSTRING, UNICODE, LEN, LEFT, RIGHT, MID, UPPER, LOWER, SUBSTITUTE, TRIM |
| Date | DATETRUNC, DATEPART, DATEDIFF, DATEADD, TODAY, NOW | STARTOF*, YEAR/MONTH/DAY/etc, DATEDIFF, DATEADD, TODAY, NOW |
| Math | ABS, CEILING, FLOOR, ROUND, POWER, SQRT, LOG, LN, EXP, SIN, COS, TAN | identical or mapped |
| Stats | MEDIAN, STDEV, STDEVP, VAR, VARP, PERCENTILE, CORR, COVAR | MEDIAN, STDEV.S, STDEV.P, VAR.S, VAR.P, PERCENTILE.INC, CORREL, COVARIANCE.S |
| Conversion | INT, FLOAT, STR, DATE, DATETIME | INT, CONVERT, FORMAT, DATE, DATE |
| LOD | {FIXED dims : AGG} | CALCULATE(AGG, ALLEXCEPT) |
| LOD | {INCLUDE dims : AGG} | CALCULATE(AGG) |
| LOD | {EXCLUDE dims : AGG} | CALCULATE(AGG, REMOVEFILTERS) |
| Table Calc | RUNNING_SUM/AVG/COUNT | CALCULATE(SUM/AVERAGE/COUNT) |
| Table Calc | RANK, RANK_UNIQUE, RANK_DENSE | RANKX(ALL()) |
| Table Calc | WINDOW_SUM/AVG/MAX/MIN | CALCULATE() |
| Syntax | ==, or/and, ELSEIF, + (strings), multi-line IF | =, \|\|/&&, ,, &, condensed IF |
| Cross-table | Column refs from other tables | RELATED() (manyToOne) or LOOKUPVALUE() (manyToMany) |
| Iterator | SUM(IF(...)), AVG(IF(...)) | SUMX('table', IF(...)), AVERAGEX('table', IF(...)) |
| Aggregation | COUNTD | DISTINCTCOUNT |
| Security | USERNAME() | USERPRINCIPALNAME() |
| Security | FULLNAME() | USERPRINCIPALNAME() |
| Security | USERDOMAIN() | "" (no DAX equivalent — use RLS roles) |
| Security | ISMEMBEROF("group") | TRUE() + RLS role per group |

## Power Query M Transformation Generators (40+)

All transform functions return `(step_name, step_expression)` tuples with `{prev}` placeholder, chained via `inject_m_steps()`.

| Category | Functions | Power Query M |
|----------|-----------|---------------|
| Column | rename, remove, select, duplicate, reorder, split, merge | Table.RenameColumns, RemoveColumns, SelectColumns, DuplicateColumn, ReorderColumns, SplitColumn, CombineColumns |
| Value | replace, replace_nulls, trim, clean, upper, lower, proper, fill_down, fill_up | Table.ReplaceValue, TransformColumns, FillDown, FillUp |
| Filter | filter_values, exclude, range, nulls, contains, distinct, top_n | Table.SelectRows, Table.Distinct, Table.FirstN |
| Aggregate | group by (sum/avg/count/countd/min/max/median/stdev) | Table.Group |
| Pivot | unpivot, unpivot_other, pivot | Table.Unpivot, UnpivotOtherColumns, Pivot |
| Join | inner, left, right, full, leftanti, rightanti | Table.NestedJoin + ExpandTableColumn |
| Union | append, wildcard_union | Table.Combine, Folder.Files |
| Reshape | sort, transpose, add_index, skip_rows, remove_last, remove_errors, promote/demote headers | Table.Sort, Transpose, AddIndexColumn, Skip, RemoveLastN |
| Calculated | add_column, conditional_column | Table.AddColumn |

TWB-embedded transforms (column renames from captions) are auto-detected and injected into M queries.

## PBIR Report Features

- **Visuals**: worksheetReference → visual.json with query, title, labels, legend, axes
- **Textbox**: dashboard text objects → visualType "textbox"
- **Image**: image objects → visualType "image"
- **Slicers**: filter_control --> visualType "slicer" (dropdown, list, between, relative date modes)
- **Filters**: 3 levels (report, page, visual) with categorical and range conditions
- **Bookmarks**: Tableau stories --> PBI bookmarks
- **Formatting**: labels on/off, label color, legend, axes, background
- **Layout**: positions and sizes calculated with scale factor
- **Custom theme**: Tableau dashboard colors --> PBI theme JSON (RegisteredResources/TableauMigrationTheme.json) with dataColors, textClasses, visualStyles
- **Conditional formatting**: quantitative color encoding --> PBI dataPoint gradient (min/max rules)
- **Reference lines**: Tableau reference lines --> PBI constant lines on valueAxis (dashed, labeled)
- **Tooltip pages**: worksheets with viz_in_tooltip --> PBI Tooltip pages (480x320, pageType: "Tooltip")
- **Drill-through pages**: drill-through filter fields --> PBI Drillthrough pages with target filters
- **Number formats**: Tableau number format patterns --> PBI formatString on measures/columns
- **Datasource filters**: Extract-level filters --> PBI report-level filter objects

## Visual Type Mapping (60+ Tableau mark types)

| Tableau Mark | Power BI visualType | Notes |
|-------------|-------------------|-------|
| Bar | clusteredBarChart | Standard bar |
| Stacked Bar | stackedBarChart | |
| Line | lineChart | With markers |
| Area | areaChart | |
| Pie | pieChart | |
| SemiCircle / Donut / Ring | donutChart | |
| Circle / Shape / Dot Plot | scatterChart | |
| Square / Hex / Treemap | treemap | |
| Text | tableEx | Table with text |
| Automatic | table | Default table |
| Map / Density | map | |
| Polygon / Multipolygon | filledMap | Choropleth |
| Gantt Bar / Lollipop | clusteredBarChart | Approximation |
| Histogram | clusteredColumnChart | |
| Box Plot | boxAndWhisker | |
| Waterfall | waterfallChart | |
| Funnel | funnel | |
| Bullet / Radial / Gauge | gauge | |
| Heat Map / Highlight Table / Calendar | matrix | Conditional formatting |
| Packed Bubble / Strip Plot | scatterChart | Bubble variant |
| Word Cloud | wordCloud | |
| Dual Axis / Combo / Pareto | lineClusteredColumnComboChart | |
| Bump Chart / Slope Chart / Timeline / Sparkline | lineChart | |
| Butterfly Chart / Waffle | hundredPercentStackedBarChart | |
| Sankey / Chord / Network | decompositionTree | |
| KPI | card | |
| Image | image | |

## Semantic Model Features

- **dataCategory**: Tableau semantic-role mapping → City, Latitude, Longitude, StateOrProvince, PostalCode, Country, County
- **isHidden**: columns hidden in Tableau → hidden in PBI
- **displayFolder**: Dimensions, Measures, Time Intelligence, Flags, Calculations, Groups, Sets, Bins
- **sortByColumn**: Calendar MonthName→Month, DayName→DayOfWeek (prevents alphabetical month sorting)
- **isKey**: Calendar Date column marked as table key
- **Hierarchies**: Tableau drill-paths → BIM hierarchies with levels
- **Sets**: → boolean calculated columns (IN expression)
- **Groups**: → SWITCH calculated columns (values→groups mapping)
- **Bins**: → FLOOR calculated columns (source, size)
- **Perspectives**: auto-generated "Full Model" perspective referencing all tables (`perspectives.tmdl`)
- **Cultures**: culture TMDL file with linguistic metadata for non-en-US locales (`cultures/{locale}.tmdl`)
- **diagramLayout.json**: empty layout file — Power BI Desktop auto-fills on first open
- **Parameters**: Tableau parameters → PBI What-If parameter tables:
  - Range parameters (integer/real) → `GENERATESERIES(min, max, step)` table + `SELECTEDVALUE` measure
  - List parameters (string/boolean) → `DATATABLE` table + `SELECTEDVALUE` measure
  - Any-domain parameters (no values) → simple measure on main table with default value
  - Both XML formats supported: `<column[@param-domain-type]>` (classic) and `<parameters><parameter>` (modern)
  - Deduplication: old-format parameters that appear both as calculations and parameter tables are deduplicated
- **Date table**: auto-detection and generation if date columns are present
  - Uses a **Power Query M partition** (not DAX calculated) to generate the Calendar table — avoids "invalid column ID" errors when TMDL relationships reference columns inside calculated-table partitions
  - M expression: `List.Dates` + `Table.AddColumn` for Year, Month, Quarter, etc.
  - Auto-creates relationship: Calendar[Date] → fact_table[first_DateTime_column], `crossFilteringBehavior: oneDirection`
- **Relationships**: Smart cardinality detection using raw column count ratio:
  - Extraction handles both `[Table].[Column]` and bare `[Column]` join clause formats (infers table from child relation elements)
  - LEFT/INNER join + to-table < 70% of from-table columns → **manyToOne** (lookup)
  - LEFT/INNER join + to-table ≥ 70% of from-table columns → **manyToMany** (peer table)
  - FULL join → **manyToMany** (ambiguous direction)
  - manyToOne uses `RELATED()`, manyToMany uses `LOOKUPVALUE()`
  - **Cross-table inference** (Phase 10): when DAX measures, calc columns, or RLS roles reference `'TableName'[Column]` from another table but no relationship exists, the generator infers one by matching column names (exact, substring, prefix) and creates a manyToOne relationship
- **RLS Roles**: Tableau user filters → Power BI Row-Level Security:
  - `<user-filter>` elements → RLS role with `USERPRINCIPALNAME()` + inline OR-based DAX from actual user mappings
  - USERNAME()/FULLNAME() calculations → RLS role with converted DAX filter expression
    - If DAX references `'OtherTable'[Col]`, the `tablePermission` is placed on that table (not the main fact table) so RLS propagates via the relationship
  - ISMEMBEROF("group") → separate RLS role per group (assign Azure AD members)
  - USERDOMAIN() → empty string with comment (no DAX equivalent)
  - Output: `roles` array in BIM model, `roles.tmdl` file, `ref role` in `model.tmdl`
  - Migration notes preserved as `MigrationNote` annotations on each role

## Output Formats — PBIR Schemas

- report: `https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.1.0/schema.json`
- page: `https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json`
- visualContainer: `https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json`

## Development Rules

1. **No external dependencies** — everything uses Python standard library
2. **Deduplication** — tables are deduplicated in the extractor (`type="table"` filtering)
3. **Calculated columns vs measures** — 3-factor classification:
   - Has aggregation (SUM, COUNT...) → measure
   - No aggregation + has column references (needs row context) → calculated column
   - No aggregation + no column refs → measure (formula-only)
   - Literal-value measure references in calc columns are inlined
4. **RELATED()** — used for cross-table refs in manyToOne relationships only
5. **LOOKUPVALUE()** — used for cross-table refs in manyToMany relationships
6. **SUM(IF(...))** — converted to SUMX('table', IF(...)) (also AVG→AVERAGEX, etc.)
7. **MAKEPOINT** — ignored (no DAX equivalent)
8. **SemanticModel** — Power BI naming convention (not "Dataset")
9. **Apostrophes** — escaped in TMDL names (`'name'` → `''name''`)
10. **Single-line DAX formulas** — multi-line formulas are condensed
11. **Parameters** — two XML formats handled:
    - Old: `<column[@param-domain-type]>` (Tableau Desktop classic)
    - New: `<parameters><parameter>` (Tableau Desktop modern, e.g., Financial_Report)
    - `param_map` populated from both sources for DAX reference resolution
    - `[Parameters].[X]` → `[Caption]` (measure) or inlined literal (calc column)

## Best Practices

- Open the .pbip in Power BI Desktop to validate
- Check relationships in the Model view
- Compare Tableau visuals vs Power BI
- Refer to `docs/FAQ.md` for frequently asked questions
