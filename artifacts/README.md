# artifacts — Generated Files

This folder contains all artifacts produced by the migration.

## Structure

```
artifacts/
├── powerbi_projects/       # .pbip projects (main output)
│   └── [ReportName]/       #   Complete project, openable in Power BI Desktop
├── powerbi_reports/        # JSON report definitions
├── powerbi_objects/        # Converted objects (legacy pipeline)
├── conversion_logs/        # Conversion logs
├── migration_reports/      # Migration reports
└── test_results/           # Test results
```

> **Main output**: `powerbi_projects/[ReportName]/[ReportName].pbip`
