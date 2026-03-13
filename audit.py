#!/usr/bin/env python3
"""Comprehensive audit of the migration output."""
import json, os, glob

base = r"C:\Users\pidoudet\OneDrive - Microsoft\Boulot\EDF\EDF SA\TableauToPowerBI\output\SIMPLE\Hypermarché\Hypermarché"
report = os.path.join(base, "Hypermarché.Report")
model = os.path.join(base, "Hypermarché.SemanticModel")

print("=" * 70)
print("1. REPORT STRUCTURE AUDIT")
print("=" * 70)

# Count pages and visuals
pages = []
visuals_total = 0
visual_types = {}
empty_visuals = []
visuals_no_query = []
duplicate_pages = {}

for root_dir, dirs, files in os.walk(report):
    if "page.json" in files:
        pg = json.load(open(os.path.join(root_dir, "page.json"), encoding="utf-8"))
        pname = pg.get("displayName", "?")
        pages.append(pname)
        duplicate_pages[pname] = duplicate_pages.get(pname, 0) + 1
        
        vis_dir = os.path.join(root_dir, "visuals")
        if not os.path.isdir(vis_dir):
            continue
        for vd in os.listdir(vis_dir):
            vf = os.path.join(vis_dir, vd, "visual.json")
            if not os.path.isfile(vf):
                continue
            v = json.load(open(vf, encoding="utf-8"))
            vis = v.get("visual", {})
            vtype = vis.get("visualType", "?")
            visuals_total += 1
            visual_types[vtype] = visual_types.get(vtype, 0) + 1
            
            qs = vis.get("query", {}).get("queryState", {})
            if not qs and vtype not in ("pageNavigator", "textbox", "image", "actionButton"):
                visuals_no_query.append(f"  {pname} / {vtype}")
            
            # Check for empty role bindings
            for role, rdata in qs.items():
                projs = rdata.get("projections", [])
                if not projs:
                    empty_visuals.append(f"  {pname} / {vtype} / role={role} (empty projections)")

print(f"\nTotal pages: {len(pages)}")
print(f"Total visuals: {visuals_total}")
print(f"\nVisual types: {json.dumps(visual_types, indent=2)}")

# Check for duplicate page names
dupes = {k: v for k, v in duplicate_pages.items() if v > 1}
if dupes:
    print(f"\n⚠ DUPLICATE PAGE NAMES: {dupes}")

if visuals_no_query:
    print(f"\n⚠ Visuals WITHOUT query ({len(visuals_no_query)}):")
    for v in visuals_no_query:
        print(v)

if empty_visuals:
    print(f"\n⚠ Visuals with EMPTY role projections ({len(empty_visuals)}):")
    for v in empty_visuals:
        print(v)

print("\n" + "=" * 70)
print("2. VISUAL FIELD BINDING AUDIT")
print("=" * 70)

issues = []
for root_dir, dirs, files in os.walk(report):
    if "page.json" in files:
        pg = json.load(open(os.path.join(root_dir, "page.json"), encoding="utf-8"))
        pname = pg.get("displayName", "?")
        vis_dir = os.path.join(root_dir, "visuals")
        if not os.path.isdir(vis_dir):
            continue
        for vd in os.listdir(vis_dir):
            vf = os.path.join(vis_dir, vd, "visual.json")
            if not os.path.isfile(vf):
                continue
            v = json.load(open(vf, encoding="utf-8"))
            vis = v.get("visual", {})
            vtype = vis.get("visualType", "?")
            qs = vis.get("query", {}).get("queryState", {})
            roles = list(qs.keys())
            
            # Check bar/column/line/area charts have both Category and Y
            if vtype in ("clusteredBarChart", "stackedBarChart", "clusteredColumnChart",
                         "stackedColumnChart", "lineChart", "areaChart"):
                if "Category" not in roles:
                    issues.append(f"  {pname} / {vtype}: MISSING Category role")
                if "Y" not in roles:
                    issues.append(f"  {pname} / {vtype}: MISSING Y role")
            
            # Check map visuals have Category
            if vtype in ("map", "filledMap"):
                if "Category" not in roles:
                    issues.append(f"  {pname} / {vtype}: MISSING Category (Location)")
            
            # Check scatter charts
            if vtype == "scatterChart":
                if "Y" not in roles and "X" not in roles:
                    issues.append(f"  {pname} / {vtype}: MISSING both X and Y")
            
            # Check treemap has Group
            if vtype == "treemap":
                if "Group" not in roles:
                    issues.append(f"  {pname} / {vtype}: MISSING Group role")
            
            # Check for unknown/internal field refs
            for role, rdata in qs.items():
                for p in rdata.get("projections", []):
                    f = p.get("field", {})
                    prop = None
                    if "Column" in f:
                        prop = f["Column"].get("Property", "")
                    elif "Measure" in f:
                        prop = f["Measure"].get("Property", "")
                    if prop and ("__tableau" in prop or "Calculation_" in prop):
                        issues.append(f"  {pname} / {vtype} / {role}: RAW FIELD '{prop}' (not resolved)")

if issues:
    print(f"\n⚠ VISUAL BINDING ISSUES ({len(issues)}):")
    for i in issues:
        print(i)
else:
    print("\n✓ No visual binding issues found")

print("\n" + "=" * 70)
print("3. SEMANTIC MODEL AUDIT (TMDL)")
print("=" * 70)

# Check TMDL files
tmdl_dir = os.path.join(model, "definition")
if os.path.isdir(tmdl_dir):
    tmdl_files = []
    for root_dir, dirs, files in os.walk(tmdl_dir):
        for f in files:
            tmdl_files.append(os.path.join(root_dir, f))
    
    print(f"\nTMDL files: {len(tmdl_files)}")
    
    # Check model.tmdl
    model_tmdl = os.path.join(tmdl_dir, "model.tmdl")
    if os.path.isfile(model_tmdl):
        content = open(model_tmdl, encoding="utf-8").read()
        tables_count = content.count("ref table")
        rels_count = content.count("ref relationship")
        roles_count = content.count("ref role")
        print(f"  Tables: {tables_count}")
        print(f"  Relationships: {rels_count}")
        print(f"  RLS Roles: {roles_count}")
    
    # Check tables
    tables_dir = os.path.join(tmdl_dir, "tables")
    if os.path.isdir(tables_dir):
        for tf in sorted(os.listdir(tables_dir)):
            if tf.endswith(".tmdl"):
                tpath = os.path.join(tables_dir, tf)
                tc = open(tpath, encoding="utf-8").read()
                cols = tc.count("\n\tcolumn ")
                measures = tc.count("\n\tmeasure ")
                partitions = tc.count("\n\tpartition ")
                hidden_cols = tc.count("isHidden")
                print(f"\n  Table: {tf}")
                print(f"    Columns: {cols}, Measures: {measures}, Partitions: {partitions}, Hidden: {hidden_cols}")
                
                # Check for empty DAX
                import re
                empty_dax = re.findall(r'measure .+? =\s*$', tc, re.MULTILINE)
                if empty_dax:
                    for ed in empty_dax:
                        print(f"    ⚠ EMPTY DAX: {ed.strip()}")
                
                # Check for unresolved Tableau references
                if "[Parameters]" in tc or "__tableau" in tc:
                    print(f"    ⚠ UNRESOLVED TABLEAU REFS in TMDL")

# Check relationships
rels_dir = os.path.join(tmdl_dir, "relationships")
if os.path.isdir(rels_dir):
    print(f"\n  Relationships dir: {len(os.listdir(rels_dir))} files")
    for rf in sorted(os.listdir(rels_dir)):
        if rf.endswith(".tmdl"):
            rc = open(os.path.join(rels_dir, rf), encoding="utf-8").read()
            print(f"    {rf}: {rc.strip()[:100]}...")

print("\n" + "=" * 70)
print("4. FILTER AUDIT")
print("=" * 70)

filter_count = 0
filter_issues = []
for root_dir, dirs, files in os.walk(report):
    if "page.json" in files:
        pg = json.load(open(os.path.join(root_dir, "page.json"), encoding="utf-8"))
        pname = pg.get("displayName", "?")
        vis_dir = os.path.join(root_dir, "visuals")
        if not os.path.isdir(vis_dir):
            continue
        for vd in os.listdir(vis_dir):
            vf = os.path.join(vis_dir, vd, "visual.json")
            if not os.path.isfile(vf):
                continue
            v = json.load(open(vf, encoding="utf-8"))
            vis = v.get("visual", {})
            vtype = vis.get("visualType", "?")
            for filt in vis.get("filters", []):
                filter_count += 1
                ft = filt.get("type", "?")
                fc = filt.get("field", {}).get("Column", {}).get("Property", "?")
                if ft == "Advanced":
                    filter_issues.append(f"  {pname} / {vtype}: Advanced filter on '{fc}'")
                    
# Check report-level filters
report_json = os.path.join(report, "report.json")
if os.path.isfile(report_json):
    rj = json.load(open(report_json, encoding="utf-8"))
    rf = rj.get("filters", [])
    filter_count += len(rf)
    for filt in rf:
        ft = filt.get("type", "?")
        fc = filt.get("field", {}).get("Column", {}).get("Property", "?")
        if ft == "Advanced":
            filter_issues.append(f"  REPORT-LEVEL: Advanced filter on '{fc}'")

print(f"\nTotal filters: {filter_count}")
if filter_issues:
    print(f"\n⚠ FILTER ISSUES ({len(filter_issues)}):")
    for fi in filter_issues:
        print(fi)
else:
    print("✓ No filter issues")

print("\n" + "=" * 70)
print("5. PAGE NAVIGATION & STRUCTURE AUDIT")
print("=" * 70)

for root_dir, dirs, files in os.walk(report):
    if "page.json" in files:
        pg = json.load(open(os.path.join(root_dir, "page.json"), encoding="utf-8"))
        pname = pg.get("displayName", "?")
        ptype = pg.get("pageType", "")
        vis_dir = os.path.join(root_dir, "visuals")
        vis_count = 0
        vis_types = []
        if os.path.isdir(vis_dir):
            for vd in os.listdir(vis_dir):
                vf = os.path.join(vis_dir, vd, "visual.json")
                if os.path.isfile(vf):
                    v = json.load(open(vf, encoding="utf-8"))
                    vt = v.get("visual", {}).get("visualType", "?")
                    vis_count += 1
                    vis_types.append(vt)
        ptype_str = f" [{ptype}]" if ptype else ""
        print(f"  {pname}{ptype_str}: {vis_count} visuals → {vis_types}")

print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)
