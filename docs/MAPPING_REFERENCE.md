# Tableau → Power BI Mapping Reference

This document details all mappings between Tableau and Power BI objects to facilitate migration.

> **See also:**  
> - [TABLEAU_TO_DAX_REFERENCE.md](TABLEAU_TO_DAX_REFERENCE.md) — Complete 172-function Tableau→DAX mapping  
> - [TABLEAU_TO_POWERQUERY_REFERENCE.md](TABLEAU_TO_POWERQUERY_REFERENCE.md) — Complete 108-property Tableau→Power Query M mapping

## 📊 Visual Types (60+ mappings)

### Bar & Column Charts

| Tableau Mark/Type | Power BI visualType | Notes |
|-------------------|-------------------|-------|
| Bar | clusteredBarChart | Standard horizontal bar |
| Stacked Bar | stackedBarChart | |
| 100% Stacked Bar | hundredPercentStackedBarChart | Percentages |
| Bar (Vertical) / Column | clusteredColumnChart | Vertical orientation |
| Stacked Column | stackedColumnChart | |
| 100% Stacked Column | hundredPercentStackedColumnChart | |
| Histogram | clusteredColumnChart | Binned data |
| Gantt Bar / Lollipop | clusteredBarChart | Approximation |
| Butterfly Chart / Waffle | hundredPercentStackedBarChart | |

### Line & Area Charts

| Tableau Mark/Type | Power BI visualType | Notes |
|-------------------|-------------------|-------|
| Line | lineChart | With markers |
| Area | areaChart | |
| Stacked Area | stackedAreaChart | |
| Bump Chart / Slope Chart | lineChart | |
| Timeline / Sparkline | lineChart | |
| Ribbon | ribbonChart | |

### Pie, Donut & Funnel

| Tableau Mark/Type | Power BI visualType | Notes |
|-------------------|-------------------|-------|
| Pie | pieChart | |
| Donut / Ring / Rose / SemiCircle | donutChart | Empty center |
| Funnel | funnel | |

### Combo & Dual Axis

| Tableau Mark/Type | Power BI visualType | Notes |
|-------------------|-------------------|-------|
| Dual Axis | lineClusteredColumnComboChart | Two Y axes |
| Combo / Pareto | lineClusteredColumnComboChart | |
| Line + Stacked Column | lineStackedColumnComboChart | |

### Scatter & Bubble

| Tableau Mark/Type | Power BI visualType | Notes |
|-------------------|-------------------|-------|
| Circle / Shape / Dot Plot | scatterChart | |
| Packed Bubble / Strip Plot | scatterChart | Bubble variant |

### Maps & Geography

| Tableau Mark/Type | Power BI visualType | Notes |
|-------------------|-------------------|-------|
| Map / Symbol Map / Density | map | Points on map |
| Filled Map / Polygon / Multipolygon / Choropleth | filledMap | Colored areas |

### Tables & Matrices

| Tableau Mark/Type | Power BI visualType | Notes |
|-------------------|-------------------|-------|
| Text Table | tableEx | Table with text |
| Automatic | table | Default table |
| Crosstab | matrix | Rows and columns |
| Heat Map / Highlight Table / Calendar | matrix | With conditional formatting |

### Tree, Hierarchy & Flow

| Tableau Mark/Type | Power BI visualType | Notes |
|-------------------|-------------------|-------|
| Square / Hex / Treemap | treemap | |
| Sankey / Chord / Network | sankeyDiagram / chordChart / networkNavigator | Custom visual GUIDs (AppSource) |

### Specialized Charts

| Tableau Mark/Type | Power BI visualType | Notes |
|-------------------|-------------------|-------|
| Waterfall | waterfallChart | |
| Box Plot / Box and Whisker | boxAndWhisker | Native PBI visual |
| Bullet / Radial / Gauge / Speedometer | gauge | |
| Word Cloud | wordCloud | |
| KPI | card | Single-value display |
| Multi-row KPI | multiRowCard | Multiple values |
| Image | image | |

## 🔢 Calculation Functions

### Basic Aggregations

| Tableau | DAX | Example |
|---------|-----|---------|
| `SUM([Sales])` | `SUM([Sales])` | Total sales |
| `AVG([Price])` | `AVERAGE([Price])` | Average price |
| `MIN([Date])` | `MIN([Date])` | Minimum date |
| `MAX([Quantity])` | `MAX([Quantity])` | Maximum quantity |
| `COUNT([Orders])` | `COUNT([Orders])` | Number of orders |
| `COUNTD([Customer ID])` | `DISTINCTCOUNT([Customer ID])` | Unique customers |
| `MEDIAN([Value])` | `MEDIAN([Value])` | Median |
| `STDEV([Amount])` | `STDEV.S([Amount])` | Standard deviation |
| `VAR([Sales])` | `VAR.S([Sales])` | Variance |

### Logical Functions

| Tableau | DAX | Notes |
|---------|-----|-------|
| `IF condition THEN value1 ELSE value2 END` | `IF(condition, value1, value2)` | |
| `IIF(condition, value1, value2)` | `IF(condition, value1, value2)` | |
| `CASE WHEN ... THEN ... END` | `SWITCH(TRUE(), ...)` | Nested |
| `AND` | `&&` | Operator |
| `OR` | `\|\|` | Operator |
| `NOT` | `NOT()` | Function |
| `ISNULL([Field])` | `ISBLANK([Field])` | NULL test |
| `IFNULL([Field], 0)` | `IF(ISBLANK([Field]), 0, [Field])` | Replace NULL |
| `ZN([Field])` | `IF(ISBLANK([Field]), 0, [Field])` | Zero if Null |

### Text Functions

| Tableau | DAX | Notes |
|---------|-----|-------|
| `LEFT([Text], 5)` | `LEFT([Text], 5)` | |
| `RIGHT([Text], 3)` | `RIGHT([Text], 3)` | |
| `MID([Text], 2, 4)` | `MID([Text], 2, 4)` | |
| `UPPER([Text])` | `UPPER([Text])` | |
| `LOWER([Text])` | `LOWER([Text])` | |
| `LEN([Text])` | `LEN([Text])` | |
| `TRIM([Text])` | `TRIM([Text])` | |
| `REPLACE([Text], 'old', 'new')` | `SUBSTITUTE([Text], 'old', 'new')` | |
| `CONTAINS([Text], 'sub')` | `CONTAINSSTRING([Text], 'sub')` | Boolean |
| `[Text1] + [Text2]` | `[Text1] & [Text2]` | Concatenation |

### Date Functions

| Tableau | DAX | Notes |
|---------|-----|-------|
| `YEAR([Date])` | `YEAR([Date])` | |
| `MONTH([Date])` | `MONTH([Date])` | |
| `DAY([Date])` | `DAY([Date])` | |
| `QUARTER([Date])` | `QUARTER([Date])` | |
| `WEEK([Date])` | `WEEKNUM([Date])` | |
| `DATEADD('month', -1, [Date])` | `DATEADD([Date], -1, MONTH)` | Different syntax |
| `DATEDIFF('day', [Start], [End])` | `DATEDIFF([Start], [End], DAY)` | Different syntax |
| `TODAY()` | `TODAY()` | |
| `NOW()` | `NOW()` | |
| `MAKEDATE(2024, 1, 15)` | `DATE(2024, 1, 15)` | |

### Math Functions

| Tableau | DAX | Notes |
|---------|-----|-------|
| `ABS([Value])` | `ABS([Value])` | |
| `ROUND([Value], 2)` | `ROUND([Value], 2)` | |
| `CEILING([Value])` | `ROUNDUP([Value], 0)` | |
| `FLOOR([Value])` | `ROUNDDOWN([Value], 0)` | |
| `SQRT([Value])` | `SQRT([Value])` | |
| `POWER([Base], [Exp])` | `POWER([Base], [Exp])` | |
| `EXP([Value])` | `EXP([Value])` | |
| `LOG([Value])` | `LOG([Value])` | |

## 📐 Level of Detail (LOD) Expressions

### FIXED

| Tableau | DAX | Usage |
|---------|-----|-------|
| `{ FIXED : SUM([Sales]) }` | `CALCULATE(SUM([Sales]), ALL(Table))` | Grand total |
| `{ FIXED [Region] : SUM([Sales]) }` | `CALCULATE(SUM([Sales]), ALLEXCEPT('Table', 'Table'[Region]))` | By region only |
| `{ FIXED [Region], [Category] : SUM([Sales]) }` | `CALCULATE(SUM([Sales]), ALLEXCEPT('Table', 'Table'[Region], 'Table'[Category]))` | Multi-dimension |

### INCLUDE

| Tableau | DAX | Usage |
|---------|-----|-------|
| `{ INCLUDE [Region] : SUM([Sales]) }` | `CALCULATE(SUM([Sales]))` | Add dimension |

### EXCLUDE

| Tableau | DAX | Usage |
|---------|-----|-------|
| `{ EXCLUDE [Category] : SUM([Sales]) }` | `CALCULATE(SUM([Sales]), ALLEXCEPT(Table, [Region]))` | Exclude dimension |

## 🎛️ Parameters

### Parameter Types

| Tableau | Power BI | Usage |
|---------|----------|-------|
| Numeric Range Parameter | What-If Parameter | Numeric slider |
| List Parameter | Query Parameter | List selection |
| Date Parameter | Query Parameter | Date selection |
| String Parameter | Query Parameter | Free text |

### Usage in Calculations

| Tableau | DAX |
|---------|-----|
| `[ParameterName]` | `SELECTEDVALUE('Parameter Table'[Parameter Value], DefaultValue)` |

## 🔍 Filters

### Filter Types

| Tableau | Power BI | Notes |
|---------|----------|-------|
| Categorical Filter | Basic Filter | List of values |
| Quantitative Filter | Advanced Filter | Numeric ranges |
| Date Filter (Relative) | Relative Date Filter | Last month, etc. |
| Date Filter (Range) | Date Filter | Between two dates |
| Top N Filter | Top N Filter | Top 10 |
| Wildcard Filter | Search Filter | Contains... |
| Context Filter | Report-Level Filter | Applied globally |

### Filter Scope

| Tableau | Power BI |
|---------|----------|
| Worksheet Filter | Visual-Level Filter |
| Dashboard Filter | Page-Level Filter |
| Context Filter | Report-Level Filter |
| Data Source Filter | Dataset Filter |

## 🎬 Actions and Interactions

### Action Types

| Tableau | Power BI | Notes |
|---------|----------|-------|
| Filter Action | Cross-Filtering | Click filters other visuals |
| Highlight Action | Cross-Highlighting | Click highlights |
| URL Action | URL Action | Opens URL |
| Go to Sheet | Page Navigation | Navigation buttons |

## 📖 Stories

### Components

| Tableau | Power BI | Notes |
|---------|----------|-------|
| Story | Bookmark Collection | Narrative sequence |
| Story Point | Bookmark | Captured state |
| Story Navigation | Navigation Buttons | Previous/Next |
| Caption | Bookmark Title | Descriptive text |

## 🗂️ Data Sources

### Connection Types

| Tableau | Power BI | Notes |
|---------|----------|-------|
| Live Connection | DirectQuery | Real-time |
| Extract | Import | Local cache |
| Published Data Source | Shared Dataset | Reusable |

### Connectors (25 types)

> **Full reference:** [TABLEAU_TO_POWERQUERY_REFERENCE.md](TABLEAU_TO_POWERQUERY_REFERENCE.md)

| Tableau | Power BI | Availability |
|---------|----------|---------------|
| SQL Server | SQL Server | ✅ |
| PostgreSQL | PostgreSQL | ✅ |
| MySQL | MySQL | ✅ |
| Oracle | Oracle | ✅ |
| Excel | Excel | ✅ |
| CSV | Text/CSV | ✅ |
| JSON | JSON | ✅ |
| XML | XML | ✅ |
| PDF | PDF | ✅ |
| Web Data Connector | Web | ✅ |
| Snowflake | Snowflake | ✅ |
| BigQuery | BigQuery | ✅ |
| Redshift | Redshift | ✅ |
| Databricks | Databricks | ✅ |
| Spark | Spark | ✅ |
| Teradata | Teradata | ✅ |
| SAP HANA | SAP HANA | ✅ |
| Azure SQL | Azure SQL | ✅ |
| Azure Synapse | Azure Synapse | ✅ |
| Google Sheets | Google Sheets | ✅ |
| SharePoint | SharePoint | ✅ |
| GeoJSON | GeoJSON | ✅ |
| Salesforce | Salesforce | ✅ |

## 🎨 Formatting

### Number Formats

| Tableau | Power BI | Example |
|---------|----------|---------|
| `n0` | `#,##0` | 1,234 |
| `n2` | `#,##0.00` | 1,234.56 |
| `c0` | `$#,##0` | $1,234 |
| `c2` | `$#,##0.00` | $1,234.56 |
| `p0` | `0%` | 50% |
| `p2` | `0.00%` | 50.25% |

### Date Formats

| Tableau | Power BI | Example |
|---------|----------|---------|
| `d` (short) | `dd/MM/yyyy` | 15/02/2024 |
| `D` (long) | `dddd, MMMM dd, yyyy` | Thursday, February 15, 2024 |
| `t` (time) | `HH:mm` | 14:30 |
| `T` (long time) | `HH:mm:ss` | 14:30:45 |

## ⚙️ Page/Report Settings

### Dashboard Options

| Tableau | Power BI | Notes |
|---------|----------|-------|
| Dashboard Size | Page Size | Fixed or responsive dimensions |
| Show Title | Show Title | Page option |
| Background Color | Background Color | Page formatting |
| Show Filters | Filter Pane | Show/hide |

---

## 🔬 Complex Transformation Examples

This section shows real-world Tableau formulas and their automatically generated DAX equivalents.

### Example 1: Multi-condition Revenue with SUM(IF) → SUMX

**Tableau:**
```
SUM(IF [order_status] != "Cancelled" THEN [quantity] * [unit_price] * (1 - [discount]) ELSE 0 END)
```

**Generated DAX:**
```dax
SUMX('Orders', IF('Orders'[order_status] != "Cancelled", 'Orders'[quantity] * 'Orders'[unit_price] * (1 - 'Orders'[discount]), 0))
```

**What happens:**
1. `IF/THEN/ELSE/END` → `IF(condition, value, else)`
2. `SUM(IF(...))` → `SUMX('Orders', IF(...))` — iterator needed because DAX `SUM()` only takes a column
3. Bare `[column]` references → `'Orders'[column]` with table qualification

### Example 2: LOD FIXED with Nested Conditions (YTD Revenue)

**Tableau:**
```
{FIXED : SUM(IF YEAR([transaction_date]) = YEAR(TODAY()) THEN [amount] ELSE 0 END)}
```

**Generated DAX:**
```dax
CALCULATE(
    SUMX('transactions', IF(YEAR('transactions'[transaction_date]) = YEAR(TODAY()), 'transactions'[amount], 0)),
    ALL('transactions')
)
```

**What happens:**
1. `{FIXED : ...}` with no dimensions → `CALCULATE(..., ALL('table'))` (grand total across all rows)
2. Inner `SUM(IF ...)` → `SUMX('table', IF(...))`
3. `YEAR()` and `TODAY()` map directly
4. The result is a YTD calculation that ignores all filters

### Example 3: Multi-Dimension LOD FIXED

**Tableau:**
```
{FIXED [region], [channel] : SUM([quantity] * [unit_price])}
```

**Generated DAX:**
```dax
CALCULATE(SUM('Orders'[quantity] * 'Orders'[unit_price]), ALLEXCEPT('Orders', 'Orders'[region], 'Orders'[channel]))
```

**What happens:**
1. `{FIXED dim1, dim2 : AGG}` → `CALCULATE(AGG, ALLEXCEPT('table', 'table'[dim1], 'table'[dim2]))`
2. `ALLEXCEPT` removes all filters except the specified dimensions

### Example 4: LOD EXCLUDE

**Tableau:**
```
{EXCLUDE [channel] : SUM([quantity] * [unit_price])}
```

**Generated DAX:**
```dax
CALCULATE(SUM('Orders'[quantity] * 'Orders'[unit_price]), REMOVEFILTERS('Orders'[channel]))
```

### Example 5: Nested IF/ELSEIF (Customer Tier)

**Tableau:**
```
IF [Revenue per Customer] > 10000 THEN "Platinum"
ELSEIF [Revenue per Customer] > 5000 THEN "Gold"
ELSEIF [Revenue per Customer] > 1000 THEN "Silver"
ELSE "Bronze" END
```

**Generated DAX:**
```dax
IF([Revenue per Customer] > 10000, "Platinum", IF([Revenue per Customer] > 5000, "Gold", IF([Revenue per Customer] > 1000, "Silver", "Bronze")))
```

**What happens:**
1. Each `ELSEIF` becomes a nested `IF()` in the ELSE branch
2. The final `ELSE` becomes the innermost default value

### Example 6: Null Handling (ISNULL + ZN)

**Tableau:**
```
IF ISNULL([discount]) THEN 0 ELSE ZN([discount]) END
```

**Generated DAX:**
```dax
IF(ISBLANK('Orders'[discount]), 0, IF(ISBLANK('Orders'[discount]), 0, 'Orders'[discount]))
```

**What happens:**
1. `ISNULL(x)` → `ISBLANK(x)`
2. `ZN(x)` → `IF(ISBLANK(x), 0, x)` (Zero if Null)

### Example 7: String Concatenation with Type Detection

**Tableau:**
```
UPPER([city]) + ", " + [state] + " (" + [country] + ")"
```

**Generated DAX:**
```dax
UPPER('Customers'[city]) & ", " & 'Customers'[state] & " (" & 'Customers'[country] & ")"
```

**What happens:**
1. When the calculation datatype is `string`, `+` → `&`
2. `UPPER()` maps directly
3. Column references are table-qualified

### Example 8: Date Argument Reordering (DATEDIFF)

**Tableau:**
```
DATEDIFF("day", [first_purchase_date], TODAY())
```

**Generated DAX:**
```dax
DATEDIFF('Customers'[first_purchase_date], TODAY(), DAY)
```

**What happens:**
1. Tableau: `DATEDIFF(interval, start, end)` → DAX: `DATEDIFF(start, end, INTERVAL)`
2. The interval string `"day"` moves from first arg to last arg and becomes the keyword `DAY`

### Example 9: Window Function (Budget Variance)

**Tableau:**
```
SUM([amount]) - WINDOW_AVG(SUM([amount]))
```

**Generated DAX:**
```dax
SUM('transactions'[amount]) - CALCULATE(SUM('transactions'[amount]), ALL('transactions'))
```

### Example 10: Cross-Table Reference in Calculated Column

**Tableau** (calculated column on Orders table referencing Customers):
```
"Segment: " + [segment]
```

**Generated DAX** (when relationship is manyToOne):
```dax
"Segment: " & RELATED('Customers'[segment])
```

**Generated DAX** (when relationship is manyToMany):
```dax
"Segment: " & LOOKUPVALUE('Customers'[segment], 'Customers'[customer_id], 'Orders'[customer_id])
```

### Example 11: Security USERNAME() → RLS Role

**Tableau:**
```xml
<calculation formula='[CustomerEmail] = USERNAME()' />
```

**Generated TMDL:**
```tmdl
role 'Is Current User'
    modelPermission: read
    tablePermission Orders
        filterExpression = 'Orders'[CustomerEmail] = USERPRINCIPALNAME()
```

### Example 12: User Filter → RLS Role with Inline Mappings

**Tableau:**
```xml
<user-filter column='[territory]'>
    <member user='john@acme.com' value='North' />
    <member user='john@acme.com' value='South' />
    <member user='jane@acme.com' value='East' />
</user-filter>
```

**Generated TMDL:**
```tmdl
role 'Territory Access'
    modelPermission: read
    tablePermission Orders
        filterExpression = (USERPRINCIPALNAME() = "john@acme.com" && [territory] IN {"North", "South"})
            || (USERPRINCIPALNAME() = "jane@acme.com" && [territory] = "East")
```

---

**Note**: This reference covers the most common mappings. Some specific or advanced features may require adjustments or custom solutions in Power BI.
