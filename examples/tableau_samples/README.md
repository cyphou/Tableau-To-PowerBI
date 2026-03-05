# Sample Tableau Files for Migration Testing

This folder contains sample Tableau workbooks to test the Power BI migration tool.

## 📁 Available Files

### 1. Superstore_Sales.twb
**Type:** Tableau Workbook (XML)  
**Data Source:** Excel  
**Complexity:** Simple to Medium  
**Content:**
- ✅ 1 data source with 21 columns
- ✅ 4 custom calculations (Total Sales, Total Profit, Profit Ratio, Number of Orders)
- ✅ 3 worksheets: Sales by Region (bubble), Profit by Category (bar), Sales Trend (line)
- ✅ 1 dashboard (Sales Overview)
- ✅ Aggregations: SUM, COUNTD

**Use case:** Basic conversions, simple visuals, dashboard layout

---

### 2. HR_Analytics.twb
**Type:** Tableau Workbook (XML)  
**Data Source:** SQL Server  
**Complexity:** Medium  
**Content:**
- ✅ 1 data source with 11 columns
- ✅ 4 advanced calculations (Average Salary, Employee Count, Tenure Category, Total Compensation)
- ✅ 4 worksheets: Headcount (pie), Salary (bar), Hiring Trend (area), Performance Matrix (treemap)
- ✅ 1 dashboard (HR Executive Dashboard) with 4 zones
- ✅ IF/ELSEIF/ELSE conditions

**Use case:** Conditional formulas, varied chart types (pie, bar, area, matrix)

---

### 3. Financial_Report.twb
**Type:** Tableau Workbook (XML)  
**Data Source:** PostgreSQL  
**Complexity:** Advanced  
**Content:**
- ✅ 1 data source with 8 columns
- ✅ 6 advanced calculations: Revenue, Expenses (SUM(IF) → SUMX), Net Income, Profit Margin %, YTD Revenue (LOD FIXED), Budget Variance (WINDOW_AVG)
- ✅ 2 parameters: Fiscal Year (integer range), Business Unit Filter (string dropdown)
- ✅ 4 worksheets: Revenue vs Expenses (dual-axis), Category Breakdown (bar), Business Unit (scatter), Top 10 (bar)
- ✅ 1 dashboard with parameter controls
- ✅ 1 story with 2 story points → PBI bookmarks
- ✅ Advanced filters: categorical, topN, date range

**Use case:** Parameters, LOD expressions, window functions, SUMX conversion, stories, complex filters

---

### 4. BigQuery_Analytics.twb
**Type:** Tableau Workbook (XML)  
**Data Source:** Google BigQuery  
**Complexity:** Medium-Advanced  
**Content:**
- ✅ 2 data sources (sessions, users) with relationships
- ✅ 1 relationship: `sessions.user_id → users.user_id` (Left join → **manyToOne**)
- ✅ Custom calculations with cross-table references (RELATED)
- ✅ Multiple worksheets with aggregations

**Use case:** Multi-table models, relationships, cross-table DAX references (RELATED), BigQuery connector

---

### 5. Security_Test.twb
**Type:** Tableau Workbook (XML)  
**Data Source:** SQL Server  
**Complexity:** Advanced (Security)  
**Content:**
- ✅ 2 tables (Orders, Regions)
- ✅ User filters with explicit user→region mappings → RLS roles
- ✅ USERNAME(), FULLNAME(), ISMEMBEROF() security calculations
- ✅ 5 RLS roles generated (territory, current user, group-based)

**Use case:** Row-Level Security migration, user filters → Power BI RLS roles

---

### 6. Enterprise_Sales.twb
**Type:** Tableau Workbook (XML)  
**Data Source:** Snowflake (multi-table join)  
**Complexity:** Advanced — all features combined  
**Content:**
- ✅ 2 joined data sources (Orders + Customers) → manyToOne relationship
- ✅ 22 advanced calculations:
  - LOD expressions: `{FIXED}`, `{FIXED multi-dim}`, `{EXCLUDE}` → `CALCULATE` + `ALLEXCEPT` / `REMOVEFILTERS`
  - Iterator functions: `SUM(IF)` → `SUMX`, `AVG(IF)` → `AVERAGEX`
  - Window functions: `WINDOW_AVG`, `RUNNING_SUM`, `RANK`
  - YTD calculation: `{FIXED : SUM(IF YEAR() = YEAR(TODAY()) ...)}` → nested `CALCULATE` + `SUMX`
  - Nested IF/ELSEIF (4 levels) → nested `IF()`
  - Null handling: `ISNULL` + `ZN` → `ISBLANK` + `IF(ISBLANK())`
  - String operations: `UPPER` + concatenation (`+` → `&`)
  - Date: `DATEDIFF("day", ...)` → `DATEDIFF(..., DAY)`
  - Stats: `STDEV` → `STDEV.S`
  - Aggregations: `COUNTD` → `DISTINCTCOUNT`, `AVG` → `AVERAGE`
  - Security: `USERNAME()` → `USERPRINCIPALNAME()`
- ✅ 3 parameters: Target Margin (real range), Date Range Start (date), Top N (integer range)
- ✅ 5 worksheets: KPIs, stacked bar, dual-axis line, scatter/bubble, geographic map
- ✅ 1 dashboard with 5 zones (title + 4 charts)
- ✅ 1 story with 3 story points → PBI bookmarks
- ✅ 3 actions (filter, highlight, URL)
- ✅ User filter (territory-based) → RLS role
- ✅ USERNAME() security calculation → RLS role
- ✅ Geographic columns: City, State, Country, PostalCode, Latitude, Longitude → `dataCategory`
- ✅ Cross-table references: Customers columns accessed from Orders context

**Use case:** Full migration stress test — every supported feature in a single workbook

---

### 7. Manufacturing_IoT.twb
**Type:** Tableau Workbook (XML)  
**Data Source:** Oracle (multi-table with full outer join)  
**Complexity:** Advanced — math/trig/stats/table calcs  
**Content:**
- ✅ 3 tables (Sensors, Machines, Maintenance) with inner join + full outer join → **manyToMany**
- ✅ 25 advanced calculations:
  - Math: `ABS`, `CEILING`, `FLOOR`, `ROUND`, `POWER`, `SQRT`, `LOG`, `LN`, `EXP`
  - Trigonometry: `SIN`, `COS`, `RADIANS` (vibration X/Y decomposition)
  - Type conversions: `INT`, `FLOAT` → `CONVERT`, `STR` → `FORMAT`
  - Statistics: `MEDIAN`, `PERCENTILE` → `PERCENTILE.INC`, `VAR` → `VAR.S`, `VARP` → `VAR.P`
  - LOD INCLUDE: `{INCLUDE [sensor_type],[machine_id] : AVG([value])}` → `CALCULATE(AVERAGE)`
  - Date: `DATETRUNC(month/quarter)` → `STARTOFMONTH/STARTOFQUARTER`, `DATEPART(hour/weekday)` → `HOUR/WEEKDAY`
  - Table calcs: `RUNNING_AVG`, `RUNNING_COUNT`, `RUNNING_MAX`, `RUNNING_MIN`
  - Ranking: `RANK_DENSE` → `RANKX(ALL(), ..., DENSE)`, `RANK_UNIQUE` → `RANKX(ALL())`
  - Window: `WINDOW_SUM` → `CALCULATE(SUM, ALL)`
- ✅ 2 parameters: Alert Threshold (real range), Time Granularity (string enum)
- ✅ 6 worksheets: Sensor Overview, Temperature Heatmap, Vibration Analysis, Anomaly Detection, Maintenance Timeline, Energy Dashboard
- ✅ 2 dashboards (Operations Overview + Analytics Deep Dive)
- ✅ 1 story with 3 story points → PBI bookmarks
- ✅ 3 actions (filter, highlight, URL)
- ✅ Custom SQL query (Machine Alerts)

**Use case:** Oracle connector, full outer join (manyToMany + LOOKUPVALUE), math/trig functions, statistical aggregations, all RUNNING_* variants, RANK_DENSE/RANK_UNIQUE, WINDOW_SUM, custom SQL

---

### 8. Marketing_Campaign.twb
**Type:** Tableau Workbook (XML)  
**Data Source:** MySQL  
**Complexity:** Advanced — string functions, REGEXP, stats  
**Content:**
- ✅ 2 tables (Campaigns, Leads) with left join → **manyToOne** + RELATED()
- ✅ 25 advanced calculations:
  - String: `MID` (email domain), `LEFT` (first name), `MID` (last name), `LEN`, `FIND`, `REPLACE` → `SUBSTITUTE`, `TRIM`, `RIGHT`, `SPACE` → `REPT`, `UPPER`, `CONTAINS` → `CONTAINSSTRING`
  - REGEXP: `REGEXP_MATCH` → `CONTAINSSTRING`, `REGEXP_REPLACE` → `SUBSTITUTE`
  - Date: `DATETRUNC(year)` → `STARTOFYEAR`, `DATEPART(month)` → `MONTH`, `DATENAME(month)` → `FORMAT`, `DATEDIFF`
  - Statistics: `CORR` → `CORREL`, `COVAR` → `COVARIANCE.S`
  - Aggregations: `COUNTA`, `COUNTD` → `DISTINCTCOUNT`, `SUM(IF)` → `SUMX`
  - LOD INCLUDE: `{INCLUDE [channel] : AVG([deal_value])}` → `CALCULATE(AVERAGE)`
  - Window: `WINDOW_MAX`, `WINDOW_MIN` → `CALCULATE(MAX/MIN, ALL)`
  - Table calc: `RUNNING_COUNT` → `CALCULATE(COUNT)`
  - Type: `INT`, `STR` → `FORMAT`
- ✅ Column aliases (Email → Email Marketing, SEM → Search Engine Marketing, etc.)
- ✅ Sort orders (lead_status manual funnel sort, channel ascending)
- ✅ 2 parameters: Min Budget (real range), Target Channel (string enum)
- ✅ 5 worksheets: Campaign Performance, Lead Funnel, Channel ROI, Engagement Analysis, Budget vs Results
- ✅ 1 dashboard (Marketing Executive Dashboard)
- ✅ 1 story with 2 story points → PBI bookmarks
- ✅ 3 actions (filter, highlight, URL)

**Use case:** MySQL connector, string manipulation functions, REGEXP, CORR/COVAR stats, COUNTA, aliases, sort orders, WINDOW_MAX/MIN

---

## 🧪 Running Migrations

```bash
cd TableauToPowerBI
python migrate.py examples/tableau_samples/Superstore_Sales.twb
python migrate.py examples/tableau_samples/HR_Analytics.twb
python migrate.py examples/tableau_samples/Financial_Report.twb
python migrate.py examples/tableau_samples/BigQuery_Analytics.twb
python migrate.py examples/tableau_samples/Security_Test.twb
python migrate.py examples/tableau_samples/Enterprise_Sales.twb
python migrate.py examples/tableau_samples/Manufacturing_IoT.twb
python migrate.py examples/tableau_samples/Marketing_Campaign.twb
```

Output is generated in `artifacts/powerbi_projects/<name>/`.

---

## 📊 Feature Coverage Matrix

| Feature | Superstore | HR | Financial | BigQuery | Security | Enterprise | Mfg IoT | Marketing |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Data Sources** | | | | | | | | |
| Excel | ✅ | | | | | | | |
| SQL Server | | ✅ | | | ✅ | | | |
| PostgreSQL | | | ✅ | | | | | |
| BigQuery | | | | ✅ | | | | |
| Snowflake | | | | | | ✅ | | |
| Oracle | | | | | | | ✅ | |
| MySQL | | | | | | | | ✅ |
| **Multi-table joins** | | | | ✅ | | ✅ | ✅ | ✅ |
| **Full outer join (manyToMany)** | | | | | | | ✅ | |
| **Visuals** | | | | | | | | |
| Bar chart | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Line chart | ✅ | | ✅ | ✅ | | ✅ | ✅ | ✅ |
| Pie chart | | ✅ | | | | | | |
| Area chart | | ✅ | | | | | | |
| Scatter/Bubble | ✅ | | ✅ | | | ✅ | ✅ | ✅ |
| Treemap/Matrix | | ✅ | | | | | ✅ | |
| Slicer | | | ✅ | | | | | |
| Map (geographic) | | | | | | ✅ | | |
| KPI / Text | | | | | | ✅ | | |
| **Calculations** | | | | | | | | |
| SUM, AVG, COUNT | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| COUNTD → DISTINCTCOUNT | ✅ | | | | | ✅ | | ✅ |
| COUNTA | | | | | | | | ✅ |
| IF Conditions | | ✅ | ✅ | | | ✅ | | |
| Nested IF/ELSEIF (4+ levels) | | | | | | ✅ | | |
| SUM(IF) → SUMX | | | ✅ | | | ✅ | | ✅ |
| AVG(IF) → AVERAGEX | | | | | | ✅ | | |
| LOD FIXED (single dim) | | | ✅ | | | ✅ | | |
| LOD FIXED (multi dim) | | | | | | ✅ | | |
| LOD EXCLUDE | | | | | | ✅ | | |
| LOD INCLUDE | | | | | | | ✅ | ✅ |
| LOD FIXED (grand total) | | | ✅ | | | ✅ | | |
| WINDOW_AVG | | | ✅ | | | ✅ | | |
| WINDOW_SUM | | | | | | | ✅ | |
| WINDOW_MAX / WINDOW_MIN | | | | | | | | ✅ |
| RUNNING_SUM | | | | | | ✅ | | |
| RUNNING_AVG / COUNT / MAX / MIN | | | | | | | ✅ | ✅ |
| RANK | | | | | | ✅ | | |
| RANK_DENSE / RANK_UNIQUE | | | | | | | ✅ | |
| DATEDIFF with reorder | | | | | | ✅ | | ✅ |
| DATETRUNC (month/quarter) | | | | | | | ✅ | |
| DATETRUNC (year) | | | | | | | | ✅ |
| DATEPART / DATENAME | | | | | | | ✅ | ✅ |
| ZN, ISNULL, IFNULL | | | | | | ✅ | | |
| String concat (+ → &) | | | | | | ✅ | | |
| UPPER, CONTAINS | | | | | | ✅ | | ✅ |
| LEFT, RIGHT, MID, LEN, FIND | | | | | | | | ✅ |
| REPLACE → SUBSTITUTE, TRIM | | | | | | | | ✅ |
| SPACE → REPT | | | | | | | | ✅ |
| REGEXP_MATCH / REGEXP_REPLACE | | | | | | | | ✅ |
| ABS, CEILING, FLOOR, ROUND | | | | | | | ✅ | |
| POWER, SQRT, LOG, LN, EXP | | | | | | | ✅ | |
| SIN, COS, RADIANS (trig) | | | | | | | ✅ | |
| INT, FLOAT/CONVERT, STR/FORMAT | | | | | | | ✅ | ✅ |
| MEDIAN, PERCENTILE, VAR, VARP | | | | | | | ✅ | |
| CORR → CORREL, COVAR → COVARIANCE.S | | | | | | | | ✅ |
| STDEV → STDEV.S | | | | | | ✅ | | |
| **Model Features** | | | | | | | | |
| Relationships | | | | ✅ | | ✅ | ✅ | ✅ |
| manyToOne (optimized) | | | | ✅ | | ✅ | | ✅ |
| manyToMany (full join) | | | | | | | ✅ | |
| RELATED() | | | | ✅ | | ✅ | | ✅ |
| LOOKUPVALUE() | | | | | | | ✅ | |
| Calculated columns | | ✅ | | | | ✅ | ✅ | ✅ |
| Parameters (What-If) | | | ✅ | | | ✅ | ✅ | ✅ |
| Date table (auto) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Geographic dataCategory | | | | | | ✅ | | ✅ |
| Column aliases | | | | | | | | ✅ |
| Sort orders | | | | | | | | ✅ |
| Custom SQL | | | | | | | ✅ | |
| **Security** | | | | | | | | |
| User filters → RLS | | | | | ✅ | ✅ | | |
| USERNAME() → RLS | | | | | ✅ | ✅ | | |
| FULLNAME() → RLS | | | | | ✅ | | | |
| ISMEMBEROF() → RLS | | | | | ✅ | | | |
| **Advanced** | | | | | | | | |
| Filters (3 levels) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Stories → Bookmarks | | | ✅ | | | ✅ | ✅ | ✅ |
| Actions (filter/highlight) | | | | | | ✅ | ✅ | ✅ |
| Dashboard layout | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Multiple dashboards | | | | | | | ✅ | |

---

## 🔗 Relationship Cardinality Detection

The migration tool uses **smart cardinality detection** based on raw column count ratios:

| Join Type | Default Cardinality | Rationale |
|---|---|---|
| `left` / `inner` | **manyToOne** | Standard fact→dimension pattern. The right (to) table is a lookup. |
| `full` | **manyToMany** | Ambiguous direction — both sides could have duplicates. |

**Column ratio heuristic** (for left/inner joins):
- If the to-table has **< 70%** of the from-table's raw columns → **manyToOne** (simple lookup)
- If the to-table has **≥ 70%** of the from-table's raw columns → **manyToMany** (peer/detail table)

**Impact on DAX:**
- `manyToOne` → `RELATED()` for cross-table references, `oneDirection` filter propagation
- `manyToMany` → `LOOKUPVALUE()` for cross-table references, `bothDirections` filter propagation

---

## 📐 DAX Conversion Highlights

### Iterator Functions (SUM(IF) → SUMX)
Tableau allows `SUM(IF([col]="A", [val], 0))` but DAX's `SUM()` only accepts column references.  
The tool converts these to iterator functions:

| Tableau | DAX |
|---|---|
| `SUM(IF(...))` | `SUMX('table', IF(...))` |
| `AVG(IF(...))` | `AVERAGEX('table', IF(...))` |
| `MIN(IF(...))` | `MINX('table', IF(...))` |
| `MAX(IF(...))` | `MAXX('table', IF(...))` |
| `COUNT(IF(...))` | `COUNTX('table', IF(...))` |

### Measure vs Calculated Column Classification
The tool uses 3-factor analysis to determine if a calculation is a measure or calculated column:

| Factor | Measure | Calc Column |
|---|---|---|
| Has aggregation (SUM, COUNT...) | ✅ | ❌ |
| References physical columns | Optional | ✅ (needs row context) |
| Tableau role | `measure` | `dimension` |

Rule: If no aggregation AND has column references → **calculated column** (regardless of Tableau role).

### Parameter Value Inlining
When a calculated column references a literal-value measure (e.g., a Tableau parameter converted to a measure like `900`), the tool inlines the value directly into the formula since calculated columns can't reference measures in DAX.

---

## 🔍 Validation

After migration, verify:

1. **Generated files:** `artifacts/powerbi_projects/<name>/`
2. **Open the .pbip** in Power BI Desktop (December 2025+)
3. **Check relationships** in Model view — verify cardinality
4. **Test DAX measures** — check for syntax errors in the formula bar
5. **Compare visuals** with the original Tableau workbook

---

## 📝 Notes

- `.twb` files do not contain data — configure data sources in Power Query after import
- `.twbx` files are packaged but the extracted data is referenced via Power Query M expressions
- The tool supports 80+ Tableau-to-DAX formula conversions
- Date tables are auto-generated when date columns are detected
- Geographic columns get `dataCategory` annotations (City, Latitude, Longitude, etc.)

---

## ✅ Migration Output Summary

| Workbook | Tables | Columns | Measures | Relationships | RLS Roles | Visuals |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Superstore_Sales | 2 | 29 | 7 | 0 | 0 | 3 |
| HR_Analytics | 2 | 20 | 6 | 0 | 0 | 4 |
| Financial_Report | 2 | 16 | 9 | 0 | 0 | 4 |
| BigQuery_Analytics | 3 | 27 | 10 | 1 | 0 | 4 |
| Security_Test | 3 | 16 | 4 | 0 | 5 | 2 |
| Enterprise_Sales | 5 | 41 | 21 | 2 | 2 | 5 |
| **Manufacturing_IoT** | **5** | **50** | **14** | **1** | **0** | **6** |
| **Marketing_Campaign** | **4** | **52** | **13** | **2** | **0** | **5** |
