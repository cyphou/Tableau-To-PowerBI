# Documentation

<p align="center">
  <img src="images/banner.svg" alt="Tableau to Power BI Migration Tool" width="960"/>
</p>

## Guides

- [POWERBI_PROJECT_GUIDE.md](POWERBI_PROJECT_GUIDE.md) — Understanding and using `.pbip` projects
- [MAPPING_REFERENCE.md](MAPPING_REFERENCE.md) — Tableau ↔ Power BI mappings (118+ visuals, formulas, interactions)
- [TABLEAU_TO_DAX_REFERENCE.md](TABLEAU_TO_DAX_REFERENCE.md) — Complete 180+-function Tableau → DAX mapping
- [TABLEAU_TO_POWERQUERY_REFERENCE.md](TABLEAU_TO_POWERQUERY_REFERENCE.md) — Complete 108-property Tableau → Power Query M mapping (25 connectors)
- [TABLEAU_PREP_TO_POWERQUERY_REFERENCE.md](TABLEAU_PREP_TO_POWERQUERY_REFERENCE.md) — Complete 165-operation Tableau Prep → Power Query M transformation mapping
- [FAQ.md](FAQ.md) — Frequently asked questions

## Quick Reference

### CLI Options

```bash
python migrate.py file.twbx                          # Basic migration
python migrate.py file.twbx --prep flow.tfl           # With Prep flow
python migrate.py file.twbx --output-dir /tmp/output  # Custom output
python migrate.py file.twbx --verbose --log-file m.log # Verbose + log file
python migrate.py --batch dir/ --output-dir /tmp/out   # Batch migration
python migrate.py --skip-conversion                    # Re-generate only
```

### Project Structure

| Module | Purpose |
|--------|---------|
| `migrate.py` | CLI entry point, batch support, logging |
| `tableau_export/` | Tableau XML parsing, DAX conversion, Power Query M generation |
| `powerbi_import/` | .pbip generation, TMDL, visuals, validation, deployment |
| `tests/` | 6,831 tests (141 files), 0 failures |
| `artifacts/` | Generated .pbip projects |
| `.github/workflows/` | CI/CD pipeline (lint, test, validate, deploy) |
