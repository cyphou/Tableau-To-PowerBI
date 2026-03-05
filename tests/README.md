# tests — Migration Validation

## Available Tests

### `test_migration.py`

Unit tests for the migration (file integrity, conversions, references).

```bash
python tests/test_migration.py
```

### `test_extraction.py`

Quick test of the Tableau extractor on a sample workbook.

```bash
python tests/test_extraction.py
```

## Manual Validation

After generating the `.pbip`, verify in Power BI Desktop:

1. The project opens without errors
2. Tables and columns are correct
3. DAX measures compute correctly
4. Calculated columns are valid
5. Relationships are functional
6. Visuals display the correct data
