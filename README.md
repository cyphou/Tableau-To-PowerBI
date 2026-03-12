# Tableau to Power BI Migration

Automated migration tool for Tableau workbooks (`.twb`, `.twbx`) and Tableau Prep flows (`.tfl`, `.tflx`) to Power BI projects (`.pbip`) that can be opened directly in Power BI Desktop.

**v7.0.0** — 2,057 tests across 40 test files — Python 3.9+ — zero external dependencies for core migration.

## Features

### Migration Engine
- **Full extraction** of 16 object types: datasources, tables, columns, calculations, relationships, parameters, worksheets, dashboards, filters, stories, actions, sets, groups, bins, hierarchies, sort orders, aliases, custom SQL, user filters
- **`.pbip` project generation** in PBIR v4.0 format with TMDL semantic model
- **172+ DAX conversions** of Tableau formulas (LOD, table calcs, IF/THEN/END, ISNULL, CONTAINS, security, stats, etc.)
- **60+ visual type mappings**: Tableau marks → Power BI visuals (bar, line, pie, scatter, map, gauge, KPI, waterfall, box plot, funnel, word cloud, combo, matrix, treemap, etc.)
- **Custom visual GUIDs**: Sankey → `sankeyDiagram`, Chord → `chordChart`, Network → `networkNavigator`, Gantt → `ganttChart` (AppSource custom visuals)
- **26 connector types** in Power Query M (Excel, CSV, SQL Server, PostgreSQL, BigQuery, Oracle, MySQL, Snowflake, Teradata, SAP HANA, SAP BW, Redshift, Databricks, Spark, Azure SQL/Synapse, Google Sheets, SharePoint, JSON, XML, PDF, Salesforce, Web, etc.)
- **40+ Power Query M transformation generators**: rename, filter, aggregate, pivot/unpivot, join, union, sort, conditional columns — chainable via `inject_m_steps()`
- **165 Tableau Prep → Power Query M** operation mappings ([reference doc](docs/TABLEAU_PREP_TO_POWERQUERY_REFERENCE.md))
- **Tableau Prep flow parser** (`.tfl`/`.tflx`): converts Prep steps (Clean, Join, Aggregate, Union, Pivot) into chained Power Query M queries via `--prep` CLI flag
- **M-based calculated columns**: calculated columns use Power Query M `Table.AddColumn` steps (DAX-to-M converter) with DAX fallback for cross-table references — avoids DAX calculated column limitations
- **Calculated columns** vs measures: automatic 3-factor classification based on aggregation, column references, and Tableau role
- **Cross-table references**: automatic `RELATED()` (manyToOne) or `LOOKUPVALUE()` (manyToMany)
- **Relationship extraction**: handles both `[Table].[Column]` and bare `[Column]` join clause formats with table inference
- **Smart cardinality detection**: raw column count ratio determines manyToOne vs manyToMany; cross-table inference creates relationships by scanning unconnected tables for matching column names
- **Row-Level Security (RLS)**: user filters, USERNAME(), FULLNAME(), ISMEMBEROF() → Power BI RLS roles with `USERPRINCIPALNAME()`
- **Parameters**: range (integer/real), list (string/boolean), and any-domain → What-If parameter tables with `GENERATESERIES` or `DATATABLE` + `SELECTEDVALUE` measures
- **Nested LOD cleanup**: `AGG(CALCULATE(...))` redundancy removal for LOD-inside-aggregation patterns
- **Multi-datasource routing**: calculations tagged with source datasource and routed to the correct table by column reference density
- **Visuals** automatically positioned based on Tableau worksheets and dashboard layouts

### Tableau Server / Cloud Integration
- **Direct download**: download workbooks from Tableau Server/Cloud via REST API
- **Authentication**: Personal Access Token (PAT) or username/password
- **Single workbook**: `--server URL --workbook "Name"` downloads and migrates one workbook
- **Batch by project**: `--server-batch PROJECT` downloads all workbooks from a Tableau Server project
- **Datasource listing**: enumerate published datasources on the server
- **Regex search**: find workbooks by name pattern

### Visual Generator (PBIR-native)
- **PBIR config templates** for 60+ visual types with data role definitions and query state builders
- **Slicer sync groups**: cross-page slicer synchronization
- **Slicer modes**: dropdown, list, between, relative date
- **Cross-filtering disable**: opt-out visuals from cross-filtering
- **Action button navigation**: page navigation and URL link buttons
- **TopN visual filters**: visual-level TopN and categorical filters
- **Sort state migration**: ascending/descending sort definitions
- **Reference lines**: constant lines and dynamic lines (average, median, percentile, min, max) on value axis
- **Conditional formatting**: color-by-measure gradients with stepped thresholds (`LessThanOrEqual`/`GreaterThan` operators)
- **Textbox & Image objects**: dashboard text → textbox visual, image → image visual
- **Custom theme**: Tableau dashboard colors → PBI theme JSON (`RegisteredResources/TableauMigrationTheme.json`)
- **Tooltip pages**: worksheets with `viz_in_tooltip` → PBI Tooltip pages (480×320)
- **Drill-through pages**: drill-through filter fields → PBI Drillthrough pages with target filters

### Semantic Model Intelligence
- **Auto Calendar table**: detects date columns, generates a Power Query M-based Calendar table with Year/Quarter/Month/Day columns and auto-relationship to fact table
- **Auto date hierarchies**: Year → Quarter → Month → Day hierarchies for every date/dateTime column not already in a hierarchy
- **Calculation groups**: Tableau parameters that switch between measures → PBI Calculation Group tables with `CALCULATE(SELECTEDMEASURE())`
- **Field parameters**: Tableau parameters that switch between dimension columns → PBI Field Parameter tables with `NAMEOF()` references
- **Number format conversion**: Tableau `###,###` / `$#,##0` / `0.0%` patterns → Power BI `formatString`
- **Context filter promotion**: worksheet context filters automatically promoted to page-level filters
- **Pages shelf slicer**: Tableau Pages shelf → Power BI slicer for animation playback
- **dataCategory mapping**: Tableau semantic roles → City, Latitude, Longitude, StateOrProvince, PostalCode, Country, County
- **isHidden**: columns hidden in Tableau → hidden in Power BI
- **displayFolder**: measures/columns organized into Dimensions, Measures, Time Intelligence, Flags, Calculations, Groups, Sets, Bins
- **sortByColumn**: Calendar MonthName→Month, DayName→DayOfWeek (prevents alphabetical month sorting) with cross-validation in validator
- **Hierarchies**: Tableau drill-paths → BIM hierarchies with levels
- **Sets**: → M-based boolean calculated columns (IN expression), with DAX fallback for cross-table refs
- **Groups**: → M-based SWITCH calculated columns (values→groups mapping), with DAX fallback
- **Bins**: → M-based FLOOR calculated columns (source, size), with DAX fallback
- **Perspectives**: auto-generated "Full Model" perspective referencing all tables
- **Cultures**: culture TMDL file with linguistic metadata for non-en-US locales

### Pre-Migration Assessment
- **`--assess` mode**: run readiness analysis before migration — checks 8 categories: datasource, calculation, visual, filter, data model, interactivity, extract, scope
- **Scoring**: overall readiness score (0–100) with per-category severity (pass / info / warning / fail)
- **Strategy advisor**: recommends Import, DirectQuery, or Composite connection mode based on 7 signal types (connectors, table/column count, custom SQL, LOD complexity, Prep flows, etc.)
- **JSON report**: assessment results saved as structured JSON for CI/CD and audit trails

### Deployment
- **Power BI Service** (`--deploy WORKSPACE_ID`): package `.pbip` → `.pbix`, upload via REST API, poll import status, optional dataset refresh (`--deploy-refresh`)
  - Azure AD auth: Service Principal, Managed Identity, or environment token
  - Post-deploy validation: checks dataset existence and refresh history
- **Microsoft Fabric**: deploy semantic models and reports to Fabric workspaces via REST API
  - Service Principal or Managed Identity auth via `azure-identity`
  - Incremental deployment with artifact caching
  - Environment-specific configs (development / staging / production)
- **Gateway config generation**: `GatewayConfigGenerator` produces gateway binding JSON for on-premises data sources

### Infrastructure
- **Batch migration**: `--batch DIR` to migrate all workbooks in a directory
- **Batch config file**: `--batch-config FILE` for per-workbook overrides (prep, culture, calendar, mode)
- **Custom output**: `--output-dir DIR` for output location
- **Output format selection**: `--output-format pbip|tmdl|pbir` for full project, semantic model only, or report only
- **Structured logging**: `--verbose`, `--quiet`, and `--log-file` flags
- **Artifact validation**: validate generated `.pbip` projects (JSON, TMDL, report structure, sortByColumn cross-refs)
- **Dry-run mode**: `--dry-run` to preview migration without writing files
- **Incremental merge**: `--incremental DIR` to merge changes into an existing `.pbip`, preserving manual edits
- **Rollback**: `--rollback` to backup existing projects before overwriting
- **Calendar customization**: `--calendar-start YEAR` and `--calendar-end YEAR` to set date table range
- **Culture/locale**: `--culture LOCALE` for non-en-US linguistic metadata (e.g., `fr-FR`)
- **Semantic model mode**: `--mode import|directquery|composite`
- **Interactive wizard**: `--wizard` for guided step-by-step migration prompts
- **Paginated reports**: `--paginated` to generate paginated report layout alongside interactive report
- **JSON config file**: `--config FILE` to load settings from a JSON file (CLI args override)
- **Structured exit codes**: distinct codes for extraction, generation, and validation failures
- **Migration metadata**: enriched `migration_metadata.json` with TMDL stats (measures, columns, relationships), visual type mappings, approximations, theme status
- **Per-item fidelity tracking**: `MigrationReport` scores each object (exact / approximate / unsupported) and generates migration reports
- **CI/CD pipeline**: GitHub Actions with 5-stage pipeline (lint+ruff, test, strict validate+twbx, staging deploy, production deploy)
- **2,057 tests** across 40 test files + conftest.py shared fixtures

## Quick Start

### Prerequisites

- Python 3.9+
- Power BI Desktop (December 2025 or later recommended)
- No external dependencies for core migration (Python standard library only)
- Optional: `azure-identity` + `requests` for deployment, `pydantic-settings` for typed config

### One-command migration

```bash
python migrate.py your_workbook.twbx
```

### With Tableau Prep flow

```bash
python migrate.py your_workbook.twbx --prep your_flow.tflx
```

The `--prep` flag parses the Prep flow, converts all steps to Power Query M, and merges the resulting queries into the workbook's datasources before generating the Power BI project.

### From Tableau Server

```bash
# Single workbook
python migrate.py --server https://tableau.company.com --workbook "Sales Dashboard" \
    --token-name my-pat --token-secret secret123

# All workbooks in a project
python migrate.py --server https://tableau.company.com --server-batch "Marketing" \
    --token-name my-pat --token-secret secret123 --output-dir /tmp/batch
```

### Batch migration

```bash
python migrate.py --batch examples/tableau_samples/ --output-dir /tmp/output
```

### Deploy to Power BI Service

```bash
python migrate.py your_workbook.twbx --deploy WORKSPACE_ID --deploy-refresh
```

### Pre-migration assessment

```bash
python migrate.py your_workbook.twbx --assess
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--prep FILE` | Tableau Prep flow (.tfl/.tflx) to merge |
| `--output-dir DIR` | Custom output directory (default: `artifacts/powerbi_projects/`) |
| `--output-format FORMAT` | Output format: `pbip` (default), `tmdl`, or `pbir` |
| `--verbose` / `-v` | Enable verbose (DEBUG) console logging |
| `--quiet` / `-q` | Suppress all output except errors |
| `--log-file FILE` | Write logs to a file |
| `--batch DIR` | Batch-migrate all .twb/.twbx files in a directory |
| `--batch-config FILE` | JSON batch config with per-workbook overrides |
| `--skip-extraction` | Skip extraction, re-use existing datasources.json |
| `--skip-conversion` | Skip DAX/M conversion, re-use existing JSON files |
| `--dry-run` | Preview migration without writing files |
| `--calendar-start YEAR` | Calendar table start year (default: 2020) |
| `--calendar-end YEAR` | Calendar table end year (default: 2030) |
| `--culture LOCALE` | Culture/locale for linguistic metadata (e.g., `fr-FR`) |
| `--mode MODE` | Semantic model mode: `import`, `directquery`, or `composite` |
| `--assess` | Run pre-migration assessment and strategy analysis (no generation) |
| `--deploy WORKSPACE_ID` | Deploy to Power BI Service workspace after generation |
| `--deploy-refresh` | Trigger dataset refresh after deploy (requires `--deploy`) |
| `--rollback` | Backup existing .pbip project before overwriting |
| `--incremental DIR` | Merge changes into existing .pbip, preserving manual edits |
| `--wizard` | Launch interactive migration wizard |
| `--paginated` | Generate paginated report layout |
| `--config FILE` | Load settings from a JSON configuration file |
| `--telemetry` | Enable anonymous usage telemetry (opt-in) |
| `--compare` | Generate comparison report (HTML) after migration |
| `--dashboard` | Generate telemetry dashboard after migration |
| `--server URL` | Tableau Server/Cloud URL for remote extraction |
| `--site SITE_ID` | Tableau site content URL (empty for default site) |
| `--workbook NAME` | Workbook name/LUID to download from server |
| `--token-name NAME` | PAT name for Tableau Server auth |
| `--token-secret SECRET` | PAT secret for Tableau Server auth |
| `--server-batch PROJECT` | Download all workbooks from a server project |

### Output

A complete project in `artifacts/powerbi_projects/[ReportName]/`:

```
[ReportName]/
├── [ReportName].pbip                          # Double-click to open
├── migration_metadata.json                    # Migration stats, fidelity, TMDL stats
├── [ReportName].SemanticModel/
│   ├── definition.pbism
│   ├── .platform
│   └── definition/
│       ├── database.tmdl
│       ├── model.tmdl
│       ├── relationships.tmdl
│       ├── expressions.tmdl                   # Power Query M partitions
│       ├── perspectives.tmdl                  # "Full Model" perspective
│       ├── roles.tmdl                         # RLS roles (if user filters exist)
│       ├── diagramLayout.json                 # Auto-filled by PBI Desktop
│       ├── cultures/
│       │   └── {locale}.tmdl                  # Linguistic metadata (--culture)
│       └── tables/
│           ├── Table1.tmdl                    # Columns + DAX measures
│           ├── Calendar.tmdl                  # Auto-generated date table
│           └── ...
└── [ReportName].Report/
    ├── definition.pbir
    ├── .platform
    └── definition/
        ├── report.json
        ├── version.json
        ├── RegisteredResources/
        │   └── TableauMigrationTheme.json     # Custom color theme
        └── pages/
            ├── pages.json
            └── ReportSection/
                ├── page.json
                └── visuals/
                    └── [id]/visual.json
```

### Step-by-step migration

```bash
# 1. Extraction only
python tableau_export/extract_tableau_data.py your_workbook.twbx

# 2. Power BI project generation
python powerbi_import/import_to_powerbi.py
```

## Architecture

```
TableauToPowerBI/
├── migrate.py                                 # CLI entry point (30+ flags)
├── tableau_export/                            # Tableau extraction
│   ├── extract_tableau_data.py                #   TWB/TWBX parser (16 object types)
│   ├── datasource_extractor.py                #   Connection/table/calc extractor
│   ├── dax_converter.py                       #   172+ DAX formula conversions
│   ├── m_query_builder.py                     #   26 connector types + 40+ transform generators
│   ├── prep_flow_parser.py                    #   Tableau Prep flow parser (.tfl/.tflx)
│   └── server_client.py                       #   Tableau Server REST API client
├── powerbi_import/                            # Power BI generation
│   ├── import_to_powerbi.py                   #   Orchestrator (supports --output-dir)
│   ├── pbip_generator.py                      #   .pbip project + visuals + filters + bookmarks
│   ├── visual_generator.py                    #   60+ visual types, PBIR-native configs
│   ├── tmdl_generator.py                      #   Semantic model → TMDL
│   ├── m_query_generator.py                   #   Sample data M query generator
│   ├── gateway_config.py                      #   Gateway binding config generator
│   ├── assessment.py                          #   Pre-migration readiness assessment
│   ├── strategy_advisor.py                    #   Import/DirectQuery/Composite advisor
│   ├── validator.py                           #   Artifact validation (JSON, TMDL, .pbip)
│   ├── migration_report.py                    #   Per-item fidelity tracking
│   └── deploy/                                #   Deployment subpackage
│       ├── auth.py                            #     Azure AD auth (SP / MI)
│       ├── client.py                          #     Fabric REST API client (retry + fallback)
│       ├── deployer.py                        #     Fabric deployment orchestrator
│       ├── pbi_client.py                      #     PBI Service REST API client
│       ├── pbix_packager.py                   #     .pbip → .pbix ZIP packager
│       ├── pbi_deployer.py                    #     PBI Service deployment orchestrator
│       ├── utils.py                           #     DeploymentReport, ArtifactCache
│       └── config/                            #     Configuration
│           ├── settings.py                    #       Env-var based settings
│           └── environments.py                #       Dev/staging/production configs
├── tests/                                     # 2,057 tests (40 test files + conftest.py)
├── docs/                                      # Documentation
├── examples/                                  # Sample Tableau files (22 workbooks)
├── .github/workflows/ci.yml                   # CI/CD pipeline
└── artifacts/                                 # Generated output
    └── powerbi_projects/                      #   .pbip projects
```

## Pipeline

```
.twbx/.twb --> extract_tableau_data.py --> 16 JSON files --+
.tfl/.tflx --> prep_flow_parser.py --> M query overrides --+--> pbip_generator.py + tmdl_generator.py --> .pbip
                                                           +-- (merge)
```

```
              +-------------------------------+
              |           INPUT               |
              |  .twb / .twbx  (workbook)     |
              |  .tfl / .tflx  (Prep, opt.)   |
              |  Tableau Server (opt.)        |
              +---------------+---------------+
                              |
                              v
              +-------------------------------+
              |    STEP 1 - EXTRACTION        |
              |                               |
              |  extract_tableau_data.py       |
              |    +-- datasource_extractor.py |
              |    +-- dax_converter.py        |
              |    +-- m_query_builder.py      |
              |    +-- prep_flow_parser.py     |
              |    +-- server_client.py (opt.) |
              +---------------+---------------+
                              |
                              v
              +-------------------------------+
              |      16 INTERMEDIATE JSON     |
              |                               |
              |  worksheets    calculations   |
              |  dashboards    parameters     |
              |  datasources   filters        |
              |  stories       actions        |
              |  sets/groups   bins           |
              |  hierarchies   sort_orders    |
              |  aliases       custom_sql     |
              |  user_filters  ds_filters     |
              +---------------+---------------+
                              |
                              v
              +-------------------------------+
              |    STEP 2 - GENERATION        |
              |                               |
              |  import_to_powerbi.py         |
              |    +-- pbip_generator.py      |
              |    +-- tmdl_generator.py      |
              |    +-- visual_generator.py    |
              |    +-- validator.py           |
              +---------------+---------------+
                              |
                              v
              +-------------------------------+
              |    STEP 3 - DEPLOY (opt.)     |
              |                               |
              |  pbi_deployer.py (PBI Service)|
              |  deployer.py (Fabric)         |
              +---------------+---------------+
                              |
                              v
              +-------------------------------+
              |           OUTPUT              |
              |                               |
              |  .pbip project                |
              |  PBIR v4.0 report             |
              |  TMDL semantic model          |
              |  migration_metadata.json      |
              +-------------------------------+
```

## DAX Conversions (172+ functions)

> **Full reference:** [docs/TABLEAU_TO_DAX_REFERENCE.md](docs/TABLEAU_TO_DAX_REFERENCE.md)

| Category | Tableau | DAX |
|----------|---------|-----|
| Logic | `IF cond THEN val ELSE val2 END` | `IF(cond, val, val2)` |
| Logic | `IF ... ELSEIF ... END` | `IF(..., ..., IF(...))` |
| Null | `ISNULL([col])` | `ISBLANK([col])` |
| Null | `ZN([col])`, `IFNULL([col], 0)` | `IF(ISBLANK([col]), 0, [col])` |
| Text | `CONTAINS([col], "text")` | `CONTAINSSTRING([col], "text")` |
| Text | `ASCII`, `LEN`, `LEFT`, `RIGHT`, `MID` | `UNICODE`, `LEN`, `LEFT`, `RIGHT`, `MID` |
| Text | `UPPER`, `LOWER`, `REPLACE`, `TRIM` | `UPPER`, `LOWER`, `SUBSTITUTE`, `TRIM` |
| Agg | `COUNTD([col])` | `DISTINCTCOUNT([col])` |
| Agg | `AVG([col])` | `AVERAGE([col])` |
| Date | `DATETRUNC`, `DATEPART`, `DATEDIFF` | `STARTOF*`, `YEAR/MONTH/DAY/etc`, `DATEDIFF` |
| Date | `DATEADD`, `TODAY`, `NOW` | `DATEADD`, `TODAY`, `NOW` |
| Math | `ABS`, `CEILING`, `FLOOR`, `ROUND` | Identical or mapped |
| Stats | `MEDIAN`, `STDEV`, `STDEVP` | `MEDIAN`, `STDEV.S`, `STDEV.P` |
| Stats | `VAR`, `VARP`, `PERCENTILE`, `CORR` | `VAR.S`, `VAR.P`, `PERCENTILE.INC`, `CORREL` |
| Conversion | `INT`, `FLOAT`, `STR`, `DATE` | `INT`, `CONVERT`, `FORMAT`, `DATE` |
| Syntax | `==` | `=` |
| Syntax | `or` / `and` | `\|\|` / `&&` |
| Syntax | `+` (strings) | `&` |
| LOD | `{FIXED [dim] : AGG}` | `CALCULATE(AGG, ALLEXCEPT)` |
| LOD | `{INCLUDE [dim] : AGG}` | `CALCULATE(AGG)` |
| LOD | `{EXCLUDE [dim] : AGG}` | `CALCULATE(AGG, REMOVEFILTERS)` |
| Table Calc | `RUNNING_SUM / AVG / COUNT` | `CALCULATE(SUM/AVERAGE/COUNT)` |
| Table Calc | `RANK`, `RANK_UNIQUE`, `RANK_DENSE` | `RANKX(ALL())` |
| Table Calc | `WINDOW_SUM / AVG / MAX / MIN` | `CALCULATE()` |
| Iterator | `SUM(IF(...))` | `SUMX('table', IF(...))` |
| Iterator | `AVG(IF(...))` / `COUNT(IF(...))` | `AVERAGEX(...)` / `COUNTX(...)` |
| Cross-table | `[col]` other table (manyToOne) | `RELATED('Table'[col])` |
| Cross-table | `[col]` other table (manyToMany) | `LOOKUPVALUE(...)` |
| Security | `USERNAME()` | `USERPRINCIPALNAME()` |
| Security | `FULLNAME()` | `USERPRINCIPALNAME()` |
| Security | `ISMEMBEROF("group")` | `TRUE()` + RLS role per group |

## Visual Type Mapping (60+)

| Tableau Mark | Power BI visualType | Notes |
|-------------|-------------------|-------|
| Bar | `clusteredBarChart` | Standard bar |
| Stacked Bar | `stackedBarChart` | |
| Line | `lineChart` | With markers |
| Area | `areaChart` | |
| Pie | `pieChart` | |
| SemiCircle / Donut / Ring | `donutChart` | |
| Circle / Shape / Dot Plot | `scatterChart` | |
| Square / Hex / Treemap | `treemap` | |
| Text | `tableEx` | Table with text |
| Automatic | `table` | Default table |
| Map / Density | `map` | |
| Polygon / Multipolygon | `filledMap` | Choropleth |
| Gantt Bar | `ganttChart` | Custom visual |
| Histogram | `clusteredColumnChart` | |
| Box Plot | `boxAndWhisker` | |
| Waterfall | `waterfallChart` | |
| Funnel | `funnel` | |
| Bullet / Radial / Gauge | `gauge` | |
| Heat Map / Highlight Table | `matrix` | Conditional formatting |
| Packed Bubble / Strip Plot | `scatterChart` | Bubble variant |
| Word Cloud | `wordCloud` | |
| Dual Axis / Combo / Pareto | `lineClusteredColumnComboChart` | |
| Sankey | `sankeyDiagram` | Custom visual GUID |
| Chord | `chordChart` | Custom visual GUID |
| Network | `networkNavigator` | Custom visual GUID |
| KPI | `card` | |
| Image | `image` | |
| 100% Stacked Area | `hundredPercentStackedAreaChart` | |
| Sunburst | `sunburst` | |
| Decomposition Tree | `decompositionTree` | |
| Shape Map | `shapeMap` | |

## Complex Transformation Examples

### LOD Expressions → CALCULATE

| Tableau LOD | Generated DAX |
|-------------|---------------|
| `{FIXED [customer_id] : SUM([qty] * [price])}` | `CALCULATE(SUM('Orders'[qty] * 'Orders'[price]), ALLEXCEPT('Orders', 'Orders'[customer_id]))` |
| `{FIXED [region], [channel] : SUM(...)}` | `CALCULATE(SUM(...), ALLEXCEPT('Orders', 'Orders'[region], 'Orders'[channel]))` |
| `{EXCLUDE [channel] : SUM(...)}` | `CALCULATE(SUM(...), REMOVEFILTERS('Orders'[channel]))` |
| `{FIXED : SUM(IF YEAR([date]) = YEAR(TODAY()) THEN [amount] ELSE 0 END)}` | `CALCULATE(SUMX('Table', IF(YEAR(...) = YEAR(TODAY()), ...)), ALL('Table'))` |

### SUM(IF) → SUMX Iterator Conversion

```
Tableau:  SUM(IF [order_status] != "Cancelled" THEN [quantity] * [unit_price] * (1 - [discount]) ELSE 0 END)
DAX:      SUMX('Orders', IF('Orders'[order_status] != "Cancelled", 'Orders'[quantity] * 'Orders'[unit_price] * (1 - 'Orders'[discount]), 0))
```

Also: `AVG(IF)` → `AVERAGEX`, `MIN(IF)` → `MINX`, `MAX(IF)` → `MAXX`, `COUNT(IF)` → `COUNTX`.

### Nested IF/ELSEIF → Nested IF()

```
Tableau:  IF [Revenue] > 10000 THEN "Platinum"
          ELSEIF [Revenue] > 5000 THEN "Gold"
          ELSEIF [Revenue] > 1000 THEN "Silver"
          ELSE "Bronze" END

DAX:      IF([Revenue] > 10000, "Platinum", IF([Revenue] > 5000, "Gold", IF([Revenue] > 1000, "Silver", "Bronze")))
```

### Window & Table Calculations

| Tableau | Generated DAX |
|---------|---------------|
| `WINDOW_AVG(SUM([revenue]))` | `CALCULATE(SUM('Table'[revenue]), ALL('Table'))` |
| `RUNNING_SUM(SUM([quantity]))` | `CALCULATE(SUM(SUM('Table'[quantity])))` |
| `RANK(SUM([revenue]))` | `RANKX(ALL(SUM('Table'[revenue])))` |

### Cross-Table References (RELATED)

```
Tableau calc column:    [segment]      → where segment lives in Customers table
DAX calculated column:  RELATED('Customers'[segment])     (manyToOne relationship)
DAX calculated column:  LOOKUPVALUE('Customers'[segment], 'Customers'[id], [customer_id])   (manyToMany)
```

### Row-Level Security (RLS) Migration

| Tableau Security | Generated Power BI RLS |
|------------------|----------------------|
| `<user-filter>` with user→value mappings | Role with `USERPRINCIPALNAME() = "user@co.com" && [Col] IN {"val1", "val2"}` |
| `[Email] = USERNAME()` | Role with `[Email] = USERPRINCIPALNAME()` |
| `ISMEMBEROF("Managers")` | Separate RLS role `Managers` (assign Azure AD group) |
| `[Manager] = FULLNAME()` | Role with `[Manager] = USERPRINCIPALNAME()` |

### Parameters → What-If Tables

| Tableau Parameter | Generated Power BI |
|-------------------|-------------------|
| Integer range (min=2020, max=2030) | `GENERATESERIES(2020, 2030, 1)` table + `SELECTEDVALUE` measure |
| String list ("All", "Europe", ...) | `DATATABLE("Value", STRING, {{"All"}, {"Europe"}, ...})` table + `SELECTEDVALUE` measure |
| Real range (min=0, max=0.5, step=0.01) | `GENERATESERIES(0, 0.5, 0.01)` table + `SELECTEDVALUE` measure |

### Geographic Data Categories

| Tableau semantic-role | Power BI dataCategory |
|-----------------------|----------------------|
| `[City].[Name]` | `City` |
| `[State].[Name]` | `StateOrProvince` |
| `[Country].[Name]` | `Country` |
| `[ZipCode].[Name]` | `PostalCode` |
| `[Geographical].[Latitude]` | `Latitude` |
| `[Geographical].[Longitude]` | `Longitude` |

## Complex Example: Enterprise Sales

```bash
python migrate.py examples/tableau_samples/Enterprise_Sales.twb
```

**Input:** 2 joined tables (Orders + Customers) from Snowflake, 22 calculations, 3 parameters, 5 worksheets, RLS rules, stories

**Generated output:**

| Component | Count | Details |
|-----------|-------|---------|
| Tables | 5 | Orders, Customers, Calendar (auto), Target Margin, Top N |
| Columns | 41 | Physical + calculated columns |
| DAX Measures | 21 | Including SUMX, CALCULATE, LOD, window functions |
| Relationships | 2 | Orders→Customers (manyToOne), Orders→Calendar |
| RLS Roles | 2 | Territory Access (user mapping), Is My Account (USERNAME) |
| Visuals | 5 | KPIs, stacked bar, line, scatter, map |
| Bookmarks | 3 | From story points |

## Validation

Validate generated projects before opening in Power BI Desktop:

```python
from powerbi_import.validator import ArtifactValidator

# Validate a single project
result = ArtifactValidator.validate_project("artifacts/powerbi_projects/MyReport")
print(result)  # {"valid": True, "files_checked": 15, "errors": []}

# Validate all projects in a directory
results = ArtifactValidator.validate_directory("artifacts/powerbi_projects/")
```

The validator checks:
- `.pbip` file exists and is valid JSON
- Report directory contains `report.json`, `definition.pbir`, page and visual JSONs
- SemanticModel directory contains `model.tmdl` (starts with `model Model`), table TMDLs
- `sortByColumn` targets reference columns that actually exist

## Deployment

### Power BI Service

```bash
# Set environment variables
export PBI_TENANT_ID="your-tenant-guid"
export PBI_CLIENT_ID="your-app-client-id"
export PBI_CLIENT_SECRET="your-app-secret"

# Migrate and deploy in one command
python migrate.py your_workbook.twbx --deploy WORKSPACE_ID --deploy-refresh
```

Or via Python API:

```python
from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer

deployer = PBIWorkspaceDeployer(workspace_id="your-workspace-guid")
result = deployer.deploy("artifacts/powerbi_projects/MyReport", refresh=True)
print(result)  # DeploymentResult(success=True, dataset_id="...", report_id="...")
```

### Microsoft Fabric

```bash
# Set environment variables
export FABRIC_WORKSPACE_ID="your-workspace-guid"
export FABRIC_TENANT_ID="your-tenant-guid"
export FABRIC_CLIENT_ID="your-app-client-id"
export FABRIC_CLIENT_SECRET="your-app-secret"

# Deploy via Python
python -c "
from powerbi_import.deploy.deployer import FabricDeployer
deployer = FabricDeployer(workspace_id='your-workspace-guid')
deployer.deploy_artifacts_batch('artifacts/powerbi_projects/')
"
```

### Dependencies for deployment

```bash
pip install azure-identity requests  # Optional, only for deployment
```

The client falls back to `urllib` (stdlib) if `requests` is not installed.

### Environment configurations

| Environment | Log Level | Retry | Validate | Approval |
|-------------|-----------|-------|----------|----------|
| development | DEBUG | 3 | No | No |
| staging | INFO | 3 | Yes | No |
| production | WARNING | 5 | Yes | Yes |

## CI/CD

The project includes a GitHub Actions pipeline (`.github/workflows/ci.yml`) with 5 stages:

1. **Lint**: `flake8` (errors only) + `ruff` (style checks)
2. **Test**: Python 3.9–3.12 matrix, 2,057 tests
3. **Strict Validate**: Run sample .twbx migrations + artifact validation with strict mode
4. **Staging Deploy**: Automated deployment to staging Fabric workspace
5. **Production Deploy**: Manual approval + deployment to production Fabric workspace

## Testing

```bash
# Run all 2,057 tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_dax_converter.py -v
python -m pytest tests/test_visual_generator.py -v
python -m pytest tests/test_non_regression.py -v
```

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_dax_converter.py` | 86 | DAX formula conversions, operators, LOD, table calcs |
| `test_dax_coverage.py` | 168 | Edge cases across all DAX conversion categories |
| `test_generation_coverage.py` | 145 | TMDL/PBIR generation edge cases |
| `test_m_query_builder.py` | 102 | Power Query M generation, 40+ transforms, connectors |
| `test_tmdl_generator.py` | 92 | TMDL model building, Calendar table, file writers |
| `test_sprint_features.py` | 78 | Sprint feature tests (multi-DS, inference, metadata) |
| `test_error_paths.py` | 78 | Error handling, edge cases, graceful degradation |
| `test_new_features.py` | 74 | Calc groups, field params, DAX-to-M, M-based columns |
| `test_v5_features.py` | 72 | v5.x feature tests |
| `test_visual_generator.py` | 65 | 60+ visual types, sync groups, action buttons, filters |
| `test_non_regression.py` | 63 | End-to-end migration of all sample workbooks |
| `test_prep_flow_parser.py` | 58 | Prep flow parsing, DAG traversal, step conversion |
| `test_assessment.py` | 55 | Pre-migration assessment (8 categories + scoring) |
| `test_phase_l_dax_coverage.py` | 55 | Window stats, date edge cases, pattern coverage |
| `test_sprint_13.py` | 53 | Custom visuals, stepped colors, dynamic ref lines |
| `test_v51_features.py` | 52 | v5.1 feature tests |
| `test_gap_implementations.py` | 50 | DAX fixes, validation, slicer modes, drill-through |
| `test_phase_c_dax_m_hardening.py` | 47 | DAX-to-M converter hardening |
| `test_pbip_generator.py` | 46 | Project generation, visual objects, slicers |
| `test_phase_d_e_coverage.py` | 46 | Visual config templates, coverage gaps |
| `test_feature_gaps.py` | 44 | Reference lines, axes, legend, sort, formatting |
| `test_migration_report.py` | 39 | Fidelity scoring, migration status reporting |
| `test_backlog.py` | 36 | Backlog feature tests |
| `test_infrastructure.py` | 36 | Validator, deployment utils, config, auth, client |
| `test_pbi_desktop_validation.py` | 34 | PBI Desktop-compatible output validation |
| `test_pbi_service.py` | 33 | PBI Service client, packager, deploy orchestrator |
| `test_extraction.py` | 29 | Tableau XML extraction |
| `test_fabric_integration.py` | 27 | Fabric deployment integration tests |
| `test_strategy_advisor.py` | 26 | Import/DirectQuery/Composite recommendations |
| `test_server_client.py` | 26 | Tableau Server client, auth, batch download |
| `test_migration_validation.py` | 14 | Migration validation end-to-end |
| `test_property_based.py` | 12 | Property-based testing for converters |
| `test_mutation.py` | 12 | Mutation testing |
| `test_snapshot.py` | 12 | Snapshot-based regression tests |
| `test_integration.py` | 11 | Full pipeline integration tests |
| `test_migration.py` | 10 | Migration pipeline tests |
| `test_performance.py` | 9 | Performance benchmarks |
| `conftest.py` | — | Shared fixtures: sample datasources, worksheets, model |

## Documentation

- [.pbip project guide](docs/POWERBI_PROJECT_GUIDE.md)
- [Tableau → Power BI mapping reference](docs/MAPPING_REFERENCE.md)
- [172 Tableau → DAX function reference](docs/TABLEAU_TO_DAX_REFERENCE.md)
- [108 Tableau → Power Query M property reference](docs/TABLEAU_TO_POWERQUERY_REFERENCE.md)
- [165 Tableau Prep → Power Query M transformation reference](docs/TABLEAU_PREP_TO_POWERQUERY_REFERENCE.md)
- [Architecture overview](docs/ARCHITECTURE.md)
- [Comprehensive gap analysis](docs/GAP_ANALYSIS.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Migration checklist](docs/MIGRATION_CHECKLIST.md)
- [Deployment guide](docs/DEPLOYMENT_GUIDE.md)
- [Tableau version compatibility](docs/TABLEAU_VERSION_COMPATIBILITY.md)
- [FAQ](docs/FAQ.md)
- [Contributing guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Known Limitations

- `MAKEPOINT()` (Tableau spatial) has no DAX equivalent — ignored
- `PREVIOUS_VALUE()` / `LOOKUP()` converted via OFFSET-based DAX pattern — may need manual adjustment for complex seed logic
- Data source paths must be reconfigured in Power Query after migration
- Some table calculations (`INDEX()`, `SIZE()`) are approximated
- Deployment requires `azure-identity` and a registered Azure AD application
- `.hyper` file data is not read (only XML metadata)
- Nested LOD expressions (LOD inside LOD) handled for common patterns, edge cases may remain
- Tableau 2024.3+ features (dynamic zone visibility, dynamic parameters) are not extracted
- See [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) for the full list

## License

MIT
