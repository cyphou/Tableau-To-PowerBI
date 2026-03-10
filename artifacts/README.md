# artifacts — Generated Files

This folder contains all artifacts produced by the migration.

## Structure

```
artifacts/
├── powerbi_projects/
│   ├── assessments/            # Pre-migration assessment JSONs
│   │   └── assessment_*.json/  #   One per workbook
│   ├── migrated/               # .pbip projects (main output)
│   │   └── [ReportName]/       #   Complete project, openable in Power BI Desktop
│   ├── reports/                # Migration fidelity report JSONs
│   │   └── migration_report_*.json
│   └── MIGRATION_ASSESSMENT_REPORT.html  # Consolidated HTML report
└── test_results/               # Test results
```

> **Main output**: `powerbi_projects/migrated/[ReportName]/[ReportName].pbip`
