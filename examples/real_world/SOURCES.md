# Real-World Tableau Example Files — Sources & Licenses

These files were downloaded from public GitHub repositories for testing purposes.

## Tableau Workbook Files (.twb)

| File | Source Repository | License | Description |
|------|-------------------|---------|-------------|
| `sample-superstore.twb` | [tableau/document-api-python](https://github.com/tableau/document-api-python) | MIT | Official Tableau Superstore sample workbook with SQL Server connection, 24 fields, 1 worksheet |
| `datasource_test.twb` | [tableau/document-api-python](https://github.com/tableau/document-api-python) | MIT | Test workbook for datasource API validation |
| `multiple_connections.twb` | [tableau/document-api-python](https://github.com/tableau/document-api-python) | MIT | Test workbook demonstrating multiple data connections |
| `TABLEAU_10_TWB.twb` | [tableau/document-api-python](https://github.com/tableau/document-api-python) | MIT | Tableau 10 format compatibility test workbook |
| `filtering.twb` | [tableau/document-api-python](https://github.com/tableau/document-api-python) | MIT | Complex filtering workbook with multiple worksheets and filter configurations (112 KB) |
| `shapes_test.twb` | [tableau/document-api-python](https://github.com/tableau/document-api-python) | MIT | Complex shapes/visuals workbook with numerous shape definitions (227 KB) |
| `ephemeral_field.twb` | [tableau/document-api-python](https://github.com/tableau/document-api-python) | MIT | Workbook with calculated/ephemeral fields |
| `global_superstores_db.twb` | [bijenmanandhar/tableau](https://github.com/bijenmanandhar/tableau) | Public | Global Superstores dashboard with multiple worksheets, calculations, and data blending (592 KB) |
| `RESTAPISample.twb` | [tableau/server-client-python](https://github.com/tableau/server-client-python) | MIT | REST API sample workbook with multiple views (241 KB) |

## Tableau Packaged Workbook Files (.twbx)

| File | Source Repository | License | Description |
|------|-------------------|---------|-------------|
| `TABLEAU_10_TWBX.twbx` | [tableau/document-api-python](https://github.com/tableau/document-api-python) | MIT | Tableau 10 packaged workbook format |
| `Cache.twbx` | [tableau/document-api-python](https://github.com/tableau/document-api-python) | MIT | Packaged workbook with cached data extract |
| `superstore_sales_dashboard.twbx` | [Nishit-soni-01/Superstore-Sales-Performance-Dashboard-with-Tableau](https://github.com/Nishit-soni-01/Superstore-Sales-Performance-Dashboard-with-Tableau) | Public | Multi-page Superstore sales dashboard with calculated fields, KPIs across sales, products, customers, shipping, and returns (333 KB) |
| `nba_player_stats.twbx` | [bijenmanandhar/tableau](https://github.com/bijenmanandhar/tableau) | Public | NBA Player Stats analysis dashboard with sports data visualizations (651 KB) |
| `SampleWB.twbx` | [tableau/server-client-python](https://github.com/tableau/server-client-python) | MIT | Sample packaged workbook for server API testing (171 KB) |

## Tableau Prep Flow Files (.tfl)

| File | Source Repository | License | Description |
|------|-------------------|---------|-------------|
| `tableau_prep_book.tfl` | [aloth/tableau-book-resources](https://github.com/aloth/tableau-book-resources) | CC-BY-4.0 | Prep flow from "Visual Analytics with Tableau" by Alexander Loth (Wiley). Contains 10 nodes: CSV inputs, Excel input, SuperUnion, SuperJoin, WriteToHyper output |
| `SampleFlow.tfl` | [tableau/server-client-python](https://github.com/tableau/server-client-python) | MIT | Sample Prep flow for server API testing |

## Tableau Data Source Files (.tds)

| File | Source Repository | License | Description |
|------|-------------------|---------|-------------|
| `SampleDS.tds` | [tableau/server-client-python](https://github.com/tableau/server-client-python) | MIT | Sample Tableau data source definition |

## Attribution

- **tableau/document-api-python**: Copyright © Tableau Software. Licensed under the [MIT License](https://github.com/tableau/document-api-python/blob/master/LICENSE).
- **tableau/server-client-python**: Copyright © Tableau Software. Licensed under the [MIT License](https://github.com/tableau/server-client-python/blob/master/LICENSE).
- **aloth/tableau-book-resources**: Copyright © Alexander Loth. Licensed under [Creative Commons Attribution 4.0 International (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/). Citation: Loth, A. (2019). *Visual Analytics with Tableau*. Wiley.
- **bijenmanandhar/tableau**: Public repository. No explicit license. Files used for testing purposes only.
- **Nishit-soni-01/Superstore-Sales-Performance-Dashboard-with-Tableau**: Public repository. No explicit license. Files used for testing purposes only.

## Migration Test Results

| File | Fidelity | Worksheets | Tables | Notes |
|------|----------|------------|--------|-------|
| `global_superstores_db.twb` | 100.0% | 20 | 2 | 4 calcs, 4 groups, 1 bin |
| `superstore_sales_dashboard.twbx` | 100.0% | 4 | 3 | 1 group |
| `RESTAPISample.twb` | 100.0% | — | — | Multiple views |
| `nba_player_stats.twbx` | 100.0% | 5 | 2 | 3 calcs, 1 param |
| `sample-superstore.twb` + `tableau_prep_book.tfl` | 100.0% | 1 | 1 | Prep flow merged |
| `filtering.twb` | 80.0% | — | — | 1 set-ref calc skipped |
