# Power BI Projects Guide (.pbip)

This guide explains how to use Power BI Projects generated automatically during Tableau migration.

## 🎯 What is a Power BI Project?

A Power BI Project (.pbip) is a new file format introduced by Microsoft that allows you to:
- 📁 Work with Git and version control
- 💻 Edit in VS Code with extensions
- 👥 Collaborate more easily as a team
- 🔄 Track changes in reports

## 📦 Structure of a Power BI Project

```
MyReport.pbip                      # Main file to open
MyReport.SemanticModel/            # Semantic model folder (TMDL)
├── definition.pbism
├── .platform
└── definition/
    ├── tables/                    # Tables
    │   ├── Sales.tmdl
    │   ├── Customers.tmdl
    │   └── Products.tmdl
    ├── relationships.tmdl         # Relationships
    └── model.tmdl                 # Model configuration

MyReport.Report/                   # Report folder (visuals)
├── report.json
└── definition/
    ├── pages/                     # Report pages
    │   ├── Page1.json
    │   └── Page2.json
    └── report.tmdl

migration_metadata.json            # Migration metadata
```

## 🚀 Opening a Power BI Project

### Method 1: From Power BI Desktop

1. Open Power BI Desktop
2. **File** → **Open** → **Browse reports**
3. Navigate to `artifacts/powerbi_projects/[ReportName]/`
4. Select the file `[ReportName].pbip`
5. Click **Open**

### Method 2: Double-click

1. Navigate to `artifacts/powerbi_projects/[ReportName]/`
2. Double-click on `[ReportName].pbip`
3. Power BI Desktop opens automatically

### Method 3: Command line

```bash
# Windows
start "C:\path\to\project\MyReport.pbip"

# Or with Power BI Desktop directly
"C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe" "C:\path\to\project\MyReport.pbip"
```

## ⚙️ Initial Setup

### Step 1: Configure Data Sources

After opening the project:

1. **Home** → **Transform data**
2. In Power Query Editor:
   - Click on each query
   - Replace `Source = null` with your actual connection
   - Examples:
   
   **SQL Server**
   ```m
   Source = Sql.Database("server.database.windows.net", "DatabaseName")
   ```
   
   **Excel**
   ```m
   Source = Excel.Workbook(File.Contents("C:\Data\file.xlsx"), null, true)
   ```
   
   **CSV**
   ```m
   Source = Csv.Document(File.Contents("C:\Data\file.csv"), [Delimiter=",", Encoding=65001])
   ```

3. **Close & Apply**

### Step 2: Verify the Data Model

1. Go to the **Model** tab
2. Check the **relationships** between tables
3. Validate column **data types**
4. Check **DAX measures** in the Data pane

### Step 3: Create Visuals

1. Go to the **Report** tab
2. Use the definitions in `MyReport.Report/definition/pages/`
3. For each page:
   - Read the page's JSON file
   - Create visuals according to the specifications
   - Position them using x, y, width, height coordinates

### Step 4: Save

1. **File** → **Save**
2. Changes are saved within the project structure
3. Compatible with Git for versioning

## 📝 TMDL Format (Tabular Model Definition Language)

`.tmdl` files use a declarative language to define the model.

### Example: Table

```tmdl
table 'Sales'
    lineageTag: 12345678-1234-1234-1234-123456789abc

    column 'SaleDate'
        dataType: dateTime
        lineageTag: 12345678-1234-1234-1234-123456789abc
        summarizeBy: none
        sourceColumn: SaleDate

    column 'Amount'
        dataType: double
        lineageTag: 12345678-1234-1234-1234-123456789abc
        summarizeBy: sum
        sourceColumn: Amount

    partition 'Sales' = m
        mode: import
        source =
            let
                Source = Sql.Database("server", "database"),
                Sales = Source{[Schema="dbo",Item="Sales"]}[Data]
            in
                Sales
```

### Example: Measure

```tmdl
measure 'Total Sales' =
    SUM([Amount])
    lineageTag: 12345678-1234-1234-1234-123456789abc
    formatString: $#,##0.00
```

### Example: Relationship

```tmdl
relationship 12345678-1234-1234-1234-123456789abc = {
    fromTable: 'Sales'
    fromColumn: 'CustomerID'
    toTable: 'Customers'
    toColumn: 'ID'
    cardinality: manyToOne
    crossFilteringBehavior: oneDirection
    isActive: true
}
```

## 🔧 Common Modifications

### Adding a New Table

1. Create a file in `MyReport.Dataset/definition/tables/`
2. Name it: `NewTable.tmdl`
3. Define the structure:

```tmdl
table 'NewTable'
    lineageTag: [generate a GUID]

    column 'ID'
        dataType: int64
        lineageTag: [generate a GUID]
        summarizeBy: none
        sourceColumn: ID

    partition 'NewTable' = m
        mode: import
        source =
            let
                Source = ...
            in
                Source
```

### Adding a Measure

1. Open `MyReport.Dataset/definition/measures.tmdl`
2. Add:

```tmdl
measure 'New Measure' =
    CALCULATE(SUM([Amount]), FILTER(...))
    lineageTag: [generate a GUID]
    formatString: #,##0
```

### Adding a Relationship

1. Open `MyReport.Dataset/definition/relationships.tmdl`
2. Add:

```tmdl
relationship [GUID] = {
    fromTable: 'Table1'
    fromColumn: 'ID'
    toTable: 'Table2'
    toColumn: 'ForeignKey'
    cardinality: manyToOne
    crossFilteringBehavior: oneDirection
    isActive: true
}
```

## 🔄 Git Workflow

### Initialize Git

```bash
cd artifacts/powerbi_projects/MyReport
git init
git add .
git commit -m "Initial commit - Tableau migration"
```

### Create a Branch for Changes

```bash
git checkout -b feature/new-measure
# Make changes in Power BI Desktop
git add .
git commit -m "Add new sales measure"
git push origin feature/new-measure
```

### Compare Versions

```bash
# View differences
git diff main feature/new-measure

# View history
git log --oneline --graph
```

### Merge Changes

```bash
git checkout main
git merge feature/new-measure
```

## 🎨 Editing in VS Code

### Install Extensions

1. **TMDL Extension** for Power BI
2. **Power BI Project Extension**

### Open the Project

```bash
code artifacts/powerbi_projects/MyReport
```

### Benefits

- ✅ IntelliSense for DAX
- ✅ Syntax validation
- ✅ Search across all files
- ✅ Easier refactoring
- ✅ Native Git integration

## ⚡ Best Practices

### File Organization

```
powerbi_projects/
├── SalesReport/
│   ├── SalesReport.pbip
│   ├── SalesReport.Dataset/
│   └── SalesReport.Report/
├── MarketingReport/
│   ├── MarketingReport.pbip
│   ├── MarketingReport.Dataset/
│   └── MarketingReport.Report/
└── README.md
```

### Naming Conventions

- **Tables**: PascalCase (e.g., `CustomerOrders`)
- **Columns**: PascalCase (e.g., `OrderDate`)
- **Measures**: Spaces allowed (e.g., `Total Sales YTD`)
- **TMDL files**: Same name as the object (e.g., `Sales.tmdl`)

### Comments

```tmdl
/// This is a comment
/// Use triple slash for documentation

measure 'Complex Calculation' =
    // This measure calculates...
    VAR CurrentYear = YEAR(TODAY())
    RETURN
        CALCULATE(
            SUM([Amount]),
            YEAR([Date]) = CurrentYear
        )
```

### Indentation

- Use **tabs** for indentation
- Align properties vertically
- Separate objects with blank lines

## 🐛 Troubleshooting

### Error: "Cannot open .pbip file"

**Cause**: Power BI Desktop version is too old

**Solution**: Update to the latest version of Power BI Desktop

### Error: "Source not found"

**Cause**: Data connections are not configured

**Solution**:
1. Open Power Query Editor
2. Configure each data source
3. Replace `null` values with actual connections

### Error: "Invalid TMDL syntax"

**Cause**: Syntax error in a .tmdl file

**Solution**:
1. Check braces and parentheses
2. Check indentation
3. Validate GUIDs (format: 12345678-1234-1234-1234-123456789abc)

### Visuals Are Not Displaying

**Cause**: Missing or invalid page files

**Solution**:
1. Check `MyReport.Report/definition/pages/`
2. Recreate visuals manually if necessary
3. Use the JSON definitions as a guide

## 📚 Resources

- [Power BI Projects Documentation](https://learn.microsoft.com/power-bi/developer/projects/projects-overview)
- [TMDL Format](https://learn.microsoft.com/analysis-services/tmdl/tmdl-overview)
- [Git with Power BI](https://learn.microsoft.com/power-bi/developer/projects/projects-git)
- [VS Code Extensions](https://marketplace.visualstudio.com/search?term=power%20bi&target=VSCode)

## 🎓 Complete Example

See the example project in:
```
artifacts/powerbi_projects/ExampleReport/
```

Contains:
- ✅ Complete data source configuration
- ✅ Model with relationships
- ✅ Documented DAX measures
- ✅ Report pages with visuals
- ✅ README with instructions

---

**Note**: Power BI Projects are generated automatically during migration. You can modify them directly in Power BI Desktop or in VS Code.
