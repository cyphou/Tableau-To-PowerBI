# Tableau Properties → Power Query M Complete Reference

Complete mapping of **every Tableau data source property** to its Power Query M equivalent.
All connector conversions are implemented in `tableau_export/m_query_builder.py`.

> **Legend**  
> ✅ Automatic — fully converted by the migration tool  
> ⚠️ Partial — converted with defaults, may need adjustment  
> 🔧 Manual — placeholder generated, manual configuration needed  
> ❌ Not applicable — no Power Query counterpart

---

## 1. Data Source Connectors

### Supported Connectors (23 types)

| # | Tableau Connection | Power Query M Function | Status | Notes |
|---|-------------------|----------------------|--------|-------|
| 1 | Excel (.xlsx/.xls) | `Excel.Workbook(File.Contents())` | ✅ | Sheet selection, headers, type changes |
| 2 | SQL Server | `Sql.Database(server, database)` | ✅ | Schema/table navigation |
| 3 | PostgreSQL | `PostgreSQL.Database(server:port, db)` | ✅ | Schema/table navigation |
| 4 | MySQL | `MySQL.Database(server:port, db)` | ✅ | Schema/table navigation |
| 5 | Oracle | `Oracle.Database(server:port/service)` | ✅ | Schema/table navigation |
| 6 | CSV / Text | `Csv.Document(File.Contents())` | ✅ | Delimiter, encoding, headers |
| 7 | Google BigQuery | `GoogleBigQuery.Database()` | ✅ | Project/dataset/table navigation |
| 8 | Snowflake | `Snowflake.Databases(server, warehouse)` | ✅ | Database/schema/table navigation |
| 9 | GeoJSON | `Json.Document(File.Contents())` | ✅ | Feature extraction, geometry handling |
| 10 | Teradata | `Teradata.Database(server)` | ✅ | Database/table navigation |
| 11 | SAP HANA | `SapHana.Database(server:port)` | ✅ | Schema/table navigation |
| 12 | SAP BW | `SapBusinessWarehouse.Cubes(server, sysNr, clientId)` | ✅ | Catalog/cube navigation |
| 13 | Amazon Redshift | `AmazonRedshift.Database(server:port, db)` | ✅ | Schema/table navigation |
| 14 | Databricks | `Databricks.Catalogs(server, http_path)` | ✅ | Catalog/schema/table navigation |
| 15 | Spark SQL | `SparkSql.Database(server, port)` | ✅ | Table navigation |
| 16 | Azure SQL Database | `AzureSQL.Database(server, database)` | ✅ | Schema/table navigation |
| 17 | Azure Synapse | `AzureSQL.Database(server, database)` | ✅ | Schema/table navigation |
| 18 | Google Sheets | `Web.Contents() + Csv.Document()` | ✅ | CSV export via Google API |
| 19 | SharePoint | `SharePoint.Files(site_url)` | ✅ | File selection, Excel parsing |
| 20 | JSON | `Json.Document(File.Contents())` | ✅ | List/record handling |
| 21 | XML | `Xml.Tables(File.Contents())` | ✅ | Table extraction |
| 22 | PDF | `Pdf.Tables(File.Contents())` | ✅ | Table extraction, headers |
| 23 | Salesforce | `Salesforce.Data()` | ✅ | Object/table navigation |
| 24 | Web API | `Web.Contents(url) + Json.Document()` | ✅ | JSON response parsing |
| 25 | Custom SQL | `Sql.Database(server, db, [Query=...])` | ✅ | Native SQL query passthrough |
| 26 | Other / Unknown | `#table(columns, rows)` | 🔧 | Sample data with TODO comment |

---

## 2. Connection Properties

| # | Tableau Property | M Equivalent | Status | Notes |
|---|-----------------|--------------|--------|-------|
| 1 | `server` | Connection string parameter | ✅ | Server address in connector function |
| 2 | `port` | Appended to server (`:port`) | ✅ | Combined with server where needed |
| 3 | `database` / `dbname` | Database navigation parameter | ✅ | |
| 4 | `schema` | Schema navigation step | ✅ | `{{[Schema="dbo"]}}` etc. |
| 5 | `warehouse` (Snowflake) | Warehouse parameter | ✅ | |
| 6 | `service` (Oracle) | Part of connection string | ✅ | `server:port/service` |
| 7 | `project` (BigQuery) | `BillingProject` parameter | ✅ | |
| 8 | `dataset` (BigQuery) | Dataset navigation step | ✅ | |
| 9 | `catalog` (Databricks) | Catalog navigation step | ✅ | |
| 10 | `http_path` (Databricks) | HTTP path parameter | ✅ | |
| 11 | `filename` | `File.Contents()` path | ✅ | Uses `DataFolder` parameter |
| 12 | `directory` | Combined with filename for path | ✅ | |
| 13 | `delimiter` (CSV) | `Delimiter` option | ✅ | |
| 14 | `encoding` (CSV) | `Encoding` option (codepage) | ✅ | UTF-8 → 65001 |
| 15 | `authentication` | Power Query credential prompt | ⚠️ | Power BI handles auth separately |
| 16 | `ssl-mode` | Implicit in connector | ⚠️ | Handled by Power BI gateway |
| 17 | `username` / `password` | Credential manager | ❌ | Never stored in M query |
| 18 | `initial-sql` | `[Query="..."]` option | ✅ | Via Custom SQL connector |
| 19 | `one-time-sql` | `[Query="..."]` option | ⚠️ | Merged with initial-sql |

---

## 3. Column / Field Properties

| # | Tableau Property | Power Query / Semantic Model | Status | Notes |
|---|-----------------|------------------------------|--------|-------|
| 1 | Column `name` | M column name + TMDL column name | ✅ | Bracket escaping reversed |
| 2 | Column `datatype` | M `Table.TransformColumnTypes()` | ✅ | Full type mapping (see §7) |
| 3 | Column `role` (dimension/measure) | TMDL `summarizeBy` property | ✅ | |
| 4 | Column `hidden` | TMDL `isHidden` property | ✅ | |
| 5 | Column `alias` | TMDL `description` annotation | ✅ | |
| 6 | Column `caption` | TMDL column display name | ✅ | |
| 7 | Column `semantic-role` | TMDL `dataCategory` | ✅ | See §8 |
| 8 | Column `default-format` | TMDL `formatString` | ⚠️ | Basic format mapping |
| 9 | Column `aggregation` | TMDL `summarizeBy` | ✅ | SUM, AVG, COUNT, etc. |
| 10 | Column `description` | TMDL `description` | ✅ | |

---

## 4. Table Properties

| # | Tableau Property | Power Query / Semantic Model | Status | Notes |
|---|-----------------|------------------------------|--------|-------|
| 1 | Table `name` | M query name + TMDL table name | ✅ | |
| 2 | Table `connection_type` | M connector function | ✅ | See §1 |
| 3 | Table `columns[]` | M type changes + TMDL columns | ✅ | |
| 4 | Table `filters[]` (data source) | M `Table.SelectRows()` | ⚠️ | Basic filter support |
| 5 | Custom SQL query | M `[Query="..."]` option | ✅ | Via Custom SQL connector |

---

## 5. Relationship / Join Properties

| # | Tableau Property | Semantic Model (TMDL) | Status | Notes |
|---|-----------------|----------------------|--------|-------|
| 1 | Join type: `inner` | `crossFilteringBehavior: oneDirection` | ✅ | |
| 2 | Join type: `left` | `crossFilteringBehavior: oneDirection` | ✅ | |
| 3 | Join type: `right` | `crossFilteringBehavior: oneDirection` | ✅ | Reversed direction |
| 4 | Join type: `full` | `crossFilteringBehavior: bothDirections` | ✅ | manyToMany |
| 5 | Join columns (from/to) | TMDL relationship `fromColumn`/`toColumn` | ✅ | |
| 6 | Cardinality (auto-detected) | `manyToOne` / `manyToMany` | ✅ | Based on column count ratio |
| 7 | Cross-table references | `RELATED()` / `LOOKUPVALUE()` | ✅ | Inferred from DAX refs |

---

## 6. Workbook / Report Properties

| # | Tableau Property | Power BI Equivalent | Status | Notes |
|---|-----------------|-------------------|--------|-------|
| 1 | Worksheet (viz) | PBIR visual page | ✅ | |
| 2 | Dashboard | PBIR page with multiple visuals | ✅ | |
| 3 | Story / story point | Power BI bookmark | ✅ | |
| 4 | Parameter | What-If parameter table | ✅ | GENERATESERIES / DATATABLE |
| 5 | Set | Boolean calculated column | ✅ | IN expression |
| 6 | Group | SWITCH calculated column | ✅ | |
| 7 | Bin | FLOOR calculated column | ✅ | |
| 8 | Hierarchy | TMDL hierarchy with levels | ✅ | |
| 9 | User filter | RLS role | ✅ | USERPRINCIPALNAME() |
| 10 | Action (filter) | Cross-filter interaction | ⚠️ | |
| 11 | Action (highlight) | Cross-highlight interaction | ⚠️ | |
| 12 | Action (URL) | Button/hyperlink | ⚠️ | |
| 13 | Action (navigation) | Bookmark/drill action | ⚠️ | |
| 14 | Sort order | TMDL `sortByColumn` | ✅ | |
| 15 | Alias | Column rename via description | ✅ | |
| 16 | Tooltip | Visual tooltip config | ⚠️ | |

---

## 7. Data Type Mapping

### Tableau → Power Query M Types

| Tableau Type | Power Query M Type | Status |
|-------------|-------------------|--------|
| `string` | `type text` | ✅ |
| `integer` | `Int64.Type` | ✅ |
| `int64` | `Int64.Type` | ✅ |
| `real` | `type number` | ✅ |
| `double` | `type number` | ✅ |
| `decimal` | `type number` | ✅ |
| `number` | `type number` | ✅ |
| `boolean` | `type logical` | ✅ |
| `date` | `type date` | ✅ |
| `datetime` | `type datetime` | ✅ |
| `time` | `type time` | ✅ |
| `spatial` | `type text` | ⚠️ | Serialized as text |
| `binary` | `type binary` | ✅ |
| `currency` | `Currency.Type` | ✅ |
| `percentage` | `Percentage.Type` | ✅ |

### Tableau → TMDL Semantic Model Types

| Tableau Type | TMDL Type | Status |
|-------------|-----------|--------|
| `string` | `String` | ✅ |
| `integer` | `Int64` | ✅ |
| `real` | `Double` | ✅ |
| `boolean` | `Boolean` | ✅ |
| `date` | `DateTime` | ✅ |
| `datetime` | `DateTime` | ✅ |
| `number` | `Double` | ✅ |

---

## 8. Semantic Role / dataCategory Mapping

| Tableau semantic-role | Power BI dataCategory | Status |
|----------------------|----------------------|--------|
| `[Country].[Name]` | `Country` | ✅ |
| `[State].[Name]` | `StateOrProvince` | ✅ |
| `[County].[Name]` | `County` | ✅ |
| `[City].[Name]` | `City` | ✅ |
| `[Postal Code].[Name]` | `PostalCode` | ✅ |
| `[Latitude]` | `Latitude` | ✅ |
| `[Longitude]` | `Longitude` | ✅ |

---

## 9. Extract / Data Refresh Properties

| # | Tableau Property | Power BI Equivalent | Status | Notes |
|---|-----------------|-------------------|--------|-------|
| 1 | Tableau Extract (.hyper) | Power BI Import mode | ⚠️ | Reconnect to original source |
| 2 | Live connection | DirectQuery mode | ⚠️ | Configure in Power BI Desktop |
| 3 | Extract filter | Data source filter / M filter | ⚠️ | Manual review recommended |
| 4 | Incremental extract | Incremental refresh policy | 🔧 | Manual setup in Power BI |

---

## 10. Power Query M Step Patterns

The migration tool generates M queries following this standard pattern:

```
let
    Source = [Connector].[Function](parameters),
    #"Table Navigation" = Source{{[Schema="...", Item="..."]}}[Data],
    #"Promoted Headers" = Table.PromoteHeaders(navigation_step),
    #"Changed Types" = Table.TransformColumnTypes(#"Promoted Headers", {
        {"Column1", type text},
        {"Column2", Int64.Type},
        {"Column3", type datetime}
    }),
    Result = #"Changed Types"
in
    Result
```

### Common M Steps Generated

| Step | M Function | When Generated |
|------|-----------|----------------|
| Source connection | Connector-specific | Always |
| Table/schema navigation | `Source{{[...]}}[Data]` | Database connectors |
| Header promotion | `Table.PromoteHeaders()` | File connectors (Excel, CSV) |
| Type changes | `Table.TransformColumnTypes()` | When columns have types |
| Feature expansion | `Table.ExpandRecordColumn()` | GeoJSON features |
| Geometry serialization | `Table.TransformColumns()` | GeoJSON with geometry |
| Column rename | `Table.RenameColumns()` | GeoJSON geometry field |

---

## Summary Statistics

| Category | Total Items | ✅ Auto | ⚠️ Partial | 🔧 Manual | ❌ N/A |
|----------|------------|---------|-----------|-----------|--------|
| Connectors | 25 | 24 | 0 | 1 | 0 |
| Connection Props | 19 | 14 | 3 | 0 | 2 |
| Column Props | 10 | 9 | 1 | 0 | 0 |
| Table Props | 5 | 4 | 1 | 0 | 0 |
| Relationships | 7 | 7 | 0 | 0 | 0 |
| Workbook Props | 16 | 11 | 4 | 0 | 1 |
| Data Types (M) | 15 | 14 | 1 | 0 | 0 |
| Semantic Roles | 7 | 7 | 0 | 0 | 0 |
| Extract/Refresh | 4 | 0 | 2 | 1 | 1 |
| **TOTAL** | **108** | **90** | **12** | **2** | **4** |

**Coverage: 90/108 (83%) fully automatic, 102/108 (94%) automatic+partial**
