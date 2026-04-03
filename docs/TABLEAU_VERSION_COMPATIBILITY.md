# Tableau Version Compatibility

This document describes which Tableau Desktop versions and features are supported by the migration tool.

---

## Supported File Formats

| Format | Extension | Support |
|--------|-----------|---------|
| Tableau Workbook | `.twb` | ✅ Full |
| Tableau Packaged Workbook | `.twbx` | ✅ Full |
| Tableau Data Source | `.tds` | ✅ Full |
| Tableau Packaged Data Source | `.tdsx` | ✅ Full |
| Tableau Prep Flow | `.tfl` | ✅ Full |
| Tableau Packaged Prep Flow | `.tflx` | ✅ Full |
| Hyper Extract | `.hyper` | ⚠️ Metadata only (data not read) |

## Tableau Desktop Version Matrix

| Tableau Version | XML Format | Support Level | Notes |
|----------------|------------|---------------|-------|
| **2018.x** | Classic XML with `<column[@param-domain-type]>` | ✅ Full | Basic parameter format |
| **2019.x** | Added `<parameters><parameter>` XML format | ✅ Full | Both parameter formats handled |
| **2020.x** | Extended mark types (Histogram, Box Plot, etc.) | ✅ Full | 50+ mark types mapped |
| **2021.x** | Enhanced relationship model, federated connections | ✅ Full | Both old/new join clause formats |
| **2022.x** | Object Model relationships, viz-in-tooltip | ✅ Full | Tooltip pages generated |
| **2023.x** | Set actions, parameter actions | ✅ Full | Actions extracted and mapped |
| **2024.1–2024.2** | Story point enhancements | ✅ Full | Stories → PBI bookmarks |
| **2024.3+** | Dynamic zone visibility, database-query parameters | ❌ Not supported | New features ignored |

## Feature Compatibility by Tableau Version

### Parameters

| Feature | Introduced | Support |
|---------|-----------|---------|
| Basic parameters (string, int, float) | 2018.x | ✅ |
| Range parameters (min/max/step) | 2018.x | ✅ → GENERATESERIES table |
| List parameters | 2018.x | ✅ → DATATABLE table |
| `<column[@param-domain-type]>` format | 2018.x (classic) | ✅ |
| `<parameters><parameter>` format | 2019.x (modern) | ✅ |
| Parameter actions | 2023.x | ✅ Extracted |
| Database-query parameters | 2024.3+ | ❌ |

### Calculations & LOD

| Feature | Introduced | Support |
|---------|-----------|---------|
| Basic calculated fields | All | ✅ |
| FIXED LOD expressions | 2015.x | ✅ → CALCULATE(AGG, ALLEXCEPT) |
| INCLUDE LOD expressions | 2015.x | ✅ → CALCULATE(AGG) |
| EXCLUDE LOD expressions | 2015.x | ✅ → CALCULATE(AGG, REMOVEFILTERS) |
| Nested LOD | All | ⚠️ Approximated |
| Table calculations (RUNNING, RANK, WINDOW) | All | ⚠️ Approximated |

### Data Sources

| Feature | Introduced | Support |
|---------|-----------|---------|
| File-based (Excel, CSV) | All | ✅ |
| Database (SQL Server, PostgreSQL, MySQL, Oracle) | All | ✅ |
| Cloud (BigQuery, Snowflake, Databricks) | Various | ✅ |
| SAP (HANA, BW) | Various | ⚠️ Basic M query |
| GeoJSON, JSON, XML, PDF | Various | ✅ |
| Custom SQL | All | ✅ |
| Federated connections | 2020.x | ✅ |
| Relationships (Object Model) | 2020.x | ✅ |
| OAuth connections | All | ❌ Credentials stripped |

### Dashboard Features

| Feature | Introduced | Support |
|---------|-----------|---------|
| Worksheets, text, images | All | ✅ |
| Filter controls (quick filters) | All | ✅ → PBI slicers |
| Dashboard actions (filter, highlight, URL) | All | ✅ |
| Sheet-navigate actions | 2019.x | ✅ → PageNavigation buttons |
| Set actions | 2023.x | ✅ Extracted |
| Device layouts (phone) | 2018.x | ✅ → Mobile pages |
| Floating layout | All | ✅ |
| Tiled layout | All | ✅ |
| Viz-in-tooltip | 2019.x | ✅ → Tooltip pages |
| Layout containers | All | ✅ (shallow nesting) |
| Dynamic zone visibility | 2024.3+ | ❌ |

### Security

| Feature | Introduced | Support |
|---------|-----------|---------|
| User filters | All | ✅ → PBI RLS roles |
| USERNAME() / FULLNAME() | All | ✅ → USERPRINCIPALNAME() |
| ISMEMBEROF() | All | ✅ → Per-group RLS roles |
| USERDOMAIN() | All | ⚠️ Returns empty string |
| Row-level security | All | ✅ |

## Tableau Prep Version Matrix

| Tableau Prep Version | Support | Notes |
|---------------------|---------|-------|
| 2019.x–2024.x | ✅ Full | DAG traversal, Clean/Join/Aggregate/Union/Pivot |
| LoadHyper steps | ⚠️ | Emits empty `#table` — Hyper data not read |
| Wildcard union | ✅ | `Folder.Files` M pattern |
| Expression functions | ✅ | Converted via dax_converter |

## Power BI Desktop Requirements

- **Minimum version**: March 2025 (for PBIR v4.0 format support)
- **Recommended**: Latest Power BI Desktop release
- **PBIR format**: Must be enabled (default in recent versions)
- **TMDL format**: Must be supported (default in Power BI Desktop)
