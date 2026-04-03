# powerbi_import — Power BI Generation

Generates complete Power BI projects (`.pbip`) from extracted Tableau data.

## Core Modules

### `import_to_powerbi.py`

Main orchestrator. Reads extracted JSON and generates the `.pbip` project.

```bash
python powerbi_import/import_to_powerbi.py
```

### `pbip_generator.py`

Generates the complete `.pbip` file structure:

- `.pbip` file (entry point)
- SemanticModel (TMDL via `tmdl_generator.py`)
- Report (PBIR v4.0: `report.json`, `pages.json`, `visual.json`)
- `.platform` files and metadata

### `tmdl_generator.py`

Converts extracted data into TMDL (Tabular Model Definition Language) files:

- `database.tmdl` — compatibility
- `model.tmdl` — culture, data source version
- `relationships.tmdl` — relationships between tables
- `tables/{Table}.tmdl` — physical columns, calculated columns, measures, M partitions

### `visual_generator.py`

Generates JSON visual definitions for the report. Maps 118+ Tableau visual types to Power BI.

### `m_query_generator.py`

Generates Power Query M queries for the different data source types.

### `validator.py`

Validates `.pbip` projects (JSON, TMDL, report structure) before opening in PBI Desktop.

### `migration_report.py`

Per-item fidelity tracking and migration status reporting.

### `api_server.py`

REST API server (stdlib `http.server`). Endpoints: `POST /migrate`, `GET /status/{id}`, `GET /download/{id}`, `GET /health`, `GET /jobs`.

### `schema_drift.py`

Schema drift detection — compares extraction snapshots. Detects added/removed/changed tables, columns, calculations, worksheets, relationships, parameters, filters.

## Deployment Subpackage (`deploy/`)

Fabric deployment is in the `deploy/` subpackage:

| Module | Responsibility |
|--------|---------------|
| `auth.py` | Azure AD authentication (Service Principal + Managed Identity) |
| `client.py` | Fabric REST API client with retry logic |
| `deployer.py` | Fabric deployment orchestrator |
| `utils.py` | DeploymentReport, ArtifactCache |
| `config/settings.py` | Centralized config via env vars |
| `config/environments.py` | Per-environment configs (dev/staging/production) |

## Output Format

**PBIR v4.0** — compatible with **Power BI Desktop March 2025 (CY25SU03)** and later.
Base theme: `CY25SU03`, report version at import: `5.58`.

| Artifact | Schema | Version |
|----------|--------|--------|
| report.json | `report/2.0.0` | 2.0.0 |
| page.json | `page/2.0.0` | 2.0.0 |
| visual.json | `visualContainer/2.5.0` | 2.5.0 |
| bookmark.json | `bookmark/1.1.0` | 1.1.0 |
| pages.json | `pagesMetadata/1.0.0` | 1.0.0 |
| definition.pbir | `definitionProperties/2.0.0` | PBIR v4.0 |
| .platform | `platformProperties/2.0.0` | 2.0.0 |
| .pbip | `pbipProperties/1.0.0` | 1.0.0 |
