"""Investigate LOOKUPVALUE type mismatch for Opportunity Close Date."""
import json

# Check which tables have Close Date
ds = json.load(open('tableau_export/datasources.json'))
for d in ds:
    for t in d.get('tables', []):
        for col in t.get('columns', []):
            if 'Close Date' in col.get('name', '') or 'Close Date' in col.get('caption', ''):
                print(f"Table: {t['name']}, Col: {col['name']}, Caption: {col.get('caption','')}, Type: {col.get('datatype','')}")

print("\n--- Relationships ---")
for d in ds:
    for r in d.get('relationships', []):
        tables = [r.get('from_table',''), r.get('to_table','')]
        if any('Created By' in str(t) or 'Opportunit' in str(t) for t in tables):
            print(json.dumps(r, indent=2))
