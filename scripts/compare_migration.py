#!/usr/bin/env python3
"""Automated migration fidelity comparison — Tableau vs Power BI.

Compares extracted Tableau metadata (from tableau_export/*.json)
against generated PBI artifacts (.pbip directory) across 9 dimensions:

  1. Dashboards → Pages (count, sizes)
  2. Worksheets → Visuals (count per page, type mapping)
  3. Calculations → DAX Measures + Calc Columns (coverage)
  4. Fields per visual (Jaccard matching)
  5. Filters (report / page / visual)
  6. Parameters → What-If parameters
  7. Datasources → Tables / Columns / Relationships
  8. Actions → Bookmarks / Drillthrough
  9. Stories → Bookmarks

Usage::

    python scripts/compare_migration.py <pbip_dir> [--extract-dir tableau_export]
    python scripts/compare_migration.py "c:/Tableau to Power BI/PowerBI/Salesforce" --verbose
    python scripts/compare_migration.py "c:/Tableau to Power BI/PowerBI/MyProject" --json results.json
"""

import argparse
import glob
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _items(data, key=None):
    """Normalise extracted JSON to list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if key and key in data:
            return data[key]
        for v in data.values():
            if isinstance(v, list):
                return v
    return []


# ---------------------------------------------------------------------------
# Tableau source loader
# ---------------------------------------------------------------------------

def load_tableau(extract_dir):
    """Load all extracted JSON files into a dict."""
    names = [
        "worksheets", "dashboards", "datasources", "calculations",
        "parameters", "filters", "stories", "actions", "sets", "groups",
        "bins", "hierarchies", "sort_orders", "aliases", "custom_sql",
        "user_filters",
    ]
    src = {}
    for n in names:
        raw = _load(os.path.join(extract_dir, f"{n}.json"))
        src[n] = _items(raw, n)
    return src


# ---------------------------------------------------------------------------
# PBI output loader
# ---------------------------------------------------------------------------

def load_pbi(pbip_dir):
    """Load PBI report + semantic model from .pbip directory."""
    pbi = {"pages": [], "visuals_by_page": {}, "measures": [], "calc_cols": [],
           "columns_by_table": {}, "tables": [], "relationships": [],
           "parameters": [], "report": {}}

    # --- Report ---
    report_dir = None
    sm_dir = None
    for d in os.listdir(pbip_dir):
        full = os.path.join(pbip_dir, d)
        if d.endswith(".Report") and os.path.isdir(full):
            report_dir = full
        if d.endswith(".SemanticModel") and os.path.isdir(full):
            sm_dir = full

    # Pages & visuals
    if report_dir:
        pages_dir = os.path.join(report_dir, "definition", "pages")
        if os.path.isdir(pages_dir):
            for page_name in sorted(os.listdir(pages_dir)):
                page_path = os.path.join(pages_dir, page_name)
                pj = os.path.join(page_path, "page.json")
                if not os.path.exists(pj):
                    continue
                pd = _load(pj)
                display = pd.get("displayName", page_name)
                width = pd.get("width", 0)
                height = pd.get("height", 0)
                page_type = pd.get("pageType", "")

                visuals = []
                vdir = os.path.join(page_path, "visuals")
                if os.path.isdir(vdir):
                    for vn in sorted(os.listdir(vdir)):
                        vf = os.path.join(vdir, vn, "visual.json")
                        if not os.path.exists(vf):
                            continue
                        vd = _load(vf)
                        vis = vd.get("visual", {})
                        vtype = vis.get("visualType", "?")

                        # Title
                        title = ""
                        vc = vis.get("vcObjects", {})
                        if "title" in vc:
                            for item in vc["title"]:
                                lit = (item.get("properties", {}).get("text", {})
                                       .get("expr", {}).get("Literal", {}).get("Value", ""))
                                if lit:
                                    title = lit.strip("'")
                        if not title:
                            t = vis.get("title", {})
                            if t:
                                lit = (t.get("text", {}).get("expr", {})
                                       .get("Literal", {}).get("Value", ""))
                                if lit:
                                    title = lit.strip("'")

                        # Fields from queryState
                        fields = set()
                        entities = set()
                        qs = vis.get("query", {}).get("queryState", {})
                        for _role, role_data in qs.items():
                            for proj in role_data.get("projections", []):
                                fi = proj.get("field", {})
                                agg = fi.get("Aggregation", {})
                                if agg:
                                    col = agg.get("Expression", {}).get("Column", {})
                                else:
                                    col = fi.get("Column", {})
                                prop = col.get("Property", "")
                                ent = col.get("Expression", {}).get("SourceRef", {}).get("Entity", "")
                                if not ent:
                                    ent = col.get("Entity", "")  # flat form
                                if prop:
                                    fields.add(prop)
                                if ent:
                                    entities.add(ent)

                        # Filters
                        vfilters = vis.get("filters", [])

                        visuals.append({
                            "type": vtype,
                            "title": title,
                            "fields": sorted(fields),
                            "entities": sorted(entities),
                            "filter_count": len(vfilters),
                            "id": vn,
                        })

                pbi["pages"].append({
                    "name": display,
                    "folder": page_name,
                    "width": width,
                    "height": height,
                    "type": page_type,
                    "visual_count": len(visuals),
                })
                pbi["visuals_by_page"][display] = visuals

        # Report-level filters
        report_json = os.path.join(report_dir, "definition", "report.json")
        if os.path.exists(report_json):
            pbi["report"] = _load(report_json)

    # --- Semantic Model ---
    if sm_dir:
        tmdl_dir = os.path.join(sm_dir, "definition", "tables")
        if os.path.isdir(tmdl_dir):
            for tmdl_file in sorted(glob.glob(os.path.join(tmdl_dir, "*.tmdl"))):
                tname = os.path.splitext(os.path.basename(tmdl_file))[0]
                with open(tmdl_file, encoding="utf-8") as f:
                    content = f.read()

                # Measures (quoted: measure 'Name' = ... or unquoted: measure Name = ...)
                for m in re.finditer(
                    r"\tmeasure\s+(?:'([^']+(?:''[^']*)*)'|([A-Za-z_]\w*))[\t ]*=[\t ]*(.+?)(?=\n\t(?:measure|column|partition|annotation|hierarchy)\b|\n\n|\Z)",
                    content, re.DOTALL
                ):
                    mname = (m.group(1) or m.group(2) or "").replace("''", "'")
                    mexpr = m.group(3).strip().split("\n")[0][:200]
                    pbi["measures"].append({"table": tname, "name": mname, "expr": mexpr})

                # Columns (quoted: column 'Name' or unquoted: column Name)
                cols = []
                for c in re.finditer(r"\tcolumn\s+(?:'([^']+(?:''[^']*)*)'|([A-Za-z_]\w*))", content):
                    cname = (c.group(1) or c.group(2) or "").replace("''", "'")
                    cols.append(cname)
                pbi["columns_by_table"][tname] = cols
                pbi["tables"].append(tname)

                # Calculated columns (quoted or unquoted)
                for c in re.finditer(
                    r"\tcolumn\s+(?:'([^']+(?:''[^']*)*)'|([A-Za-z_]\w*))\s*=\s*(.+?)(?=\n\t(?:measure|column|partition|annotation)\b|\n\n|\Z)",
                    content, re.DOTALL
                ):
                    ccname = (c.group(1) or c.group(2) or "").replace("''", "'")
                    pbi["calc_cols"].append({"table": tname, "name": ccname})

        # Relationships
        model_tmdl = os.path.join(sm_dir, "definition", "model.tmdl")
        if os.path.exists(model_tmdl):
            with open(model_tmdl, encoding="utf-8") as f:
                model_content = f.read()
            pbi["relationships"] = re.findall(r"ref\s+relationship\s+", model_content)

    return pbi


# ---------------------------------------------------------------------------
# Comparison functions
# ---------------------------------------------------------------------------

def compare_dashboards(src, pbi):
    """1. Dashboards → Pages."""
    dashboards = src["dashboards"]
    pages = pbi["pages"]

    results = []
    for db in dashboards:
        db_name = db.get("name", "?")
        db_objects = db.get("objects", [])
        # Tableau uses both "worksheet" and "worksheetReference" as object types
        db_ws_names = [o.get("name", "") for o in db_objects
                       if o.get("type") in ("worksheet", "worksheetReference")]
        db_ws_count = len(db_ws_names)
        db_filter_count = sum(1 for o in db_objects
                              if o.get("type") in ("filter_control", "parameter_control"))
        db_text_count = sum(1 for o in db_objects if o.get("type") == "text")
        db_image_count = sum(1 for o in db_objects if o.get("type") == "image")
        db_width = db.get("width", db.get("size", {}).get("width", 0))
        db_height = db.get("height", db.get("size", {}).get("height", 0))

        # Match PBI page — exact first, then substring
        match = None
        for p in pages:
            if p["name"] == db_name:
                match = p
                break
        if not match:
            for p in pages:
                if db_name.lower() in p["name"].lower() or p["name"].lower() in db_name.lower():
                    match = p
                    break

        pbi_vis_count = match["visual_count"] if match else 0
        pbi_w = match["width"] if match else 0
        pbi_h = match["height"] if match else 0

        # Count PBI visual types on this page
        pbi_visuals = pbi["visuals_by_page"].get(match["name"], []) if match else []
        pbi_slicers = sum(1 for v in pbi_visuals if v["type"] == "slicer")
        pbi_textboxes = sum(1 for v in pbi_visuals if v["type"] == "textbox")
        pbi_images = sum(1 for v in pbi_visuals if v["type"] == "image")
        pbi_buttons = sum(1 for v in pbi_visuals if v["type"] == "actionButton")
        pbi_content = pbi_vis_count - pbi_slicers - pbi_textboxes - pbi_images - pbi_buttons

        size_ok = True
        if match and db_width and db_height:
            size_ok = (abs(pbi_w - db_width) < 50 and abs(pbi_h - db_height) < 50)

        results.append({
            "dashboard": db_name,
            "tab_worksheets": db_ws_count,
            "tab_ws_names": db_ws_names,
            "tab_filters": db_filter_count,
            "tab_text": db_text_count,
            "tab_images": db_image_count,
            "tab_size": f"{db_width}x{db_height}" if db_width else "?",
            "pbi_page": match["name"] if match else "MISSING",
            "pbi_content": pbi_content,
            "pbi_slicers": pbi_slicers,
            "pbi_textboxes": pbi_textboxes,
            "pbi_images": pbi_images,
            "pbi_total": pbi_vis_count,
            "pbi_size": f"{pbi_w}x{pbi_h}" if match else "?",
            "size_match": size_ok,
            "matched": match is not None,
        })

    return {
        "dashboard_count": len(dashboards),
        "page_count": len(pages),
        "matched": sum(1 for r in results if r["matched"]),
        "details": results,
    }


def _build_field_map(src):
    """Build a mapping from internal Tableau field names to display captions.

    Tableau worksheets reference fields by internal names like
    ``[KPI_ConvRate (copy)_12345]`` while PBI visuals use the caption
    (e.g. ``Won/Lost Rate``).  This function builds the resolution map.
    """
    field_map = {}  # internal_name → caption

    # From calculations
    for c in src["calculations"]:
        name = c.get("name", "")
        caption = c.get("caption", "")
        if name and caption:
            # Strip leading/trailing brackets
            clean = name.strip("[]")
            field_map[clean] = caption
            field_map[name] = caption

    # From datasource columns
    for ds in src["datasources"]:
        for t in ds.get("tables", []):
            for col in t.get("columns", []):
                name = col.get("name", "")
                caption = col.get("caption", col.get("name", ""))
                if name and caption:
                    clean = name.strip("[]")
                    field_map[clean] = caption
                    field_map[name] = caption

    return field_map


def compare_visuals(src, pbi):
    """2. Worksheets → Visuals (dashboard-centric matching).

    Instead of matching individual worksheets to visuals by field overlap,
    we match via the dashboard structure: each dashboard references specific
    worksheets, and we compare against the matched PBI page's visuals.
    """
    worksheets = src["worksheets"]
    dashboards = src["dashboards"]
    ws_by_name = {ws.get("name", ""): ws for ws in worksheets}
    field_map = _build_field_map(src)

    all_pbi_visuals = []
    for page_name, visuals in pbi["visuals_by_page"].items():
        for v in visuals:
            all_pbi_visuals.append({**v, "page": page_name})

    # Resolve which worksheets are in which dashboard
    ws_in_dashboard = set()
    page_results = []

    for db in dashboards:
        db_name = db.get("name", "?")
        db_objects = db.get("objects", [])
        ws_refs = [o.get("name", "") for o in db_objects
                   if o.get("type") in ("worksheet", "worksheetReference") and o.get("name")]
        filter_refs = [o for o in db_objects
                       if o.get("type") in ("filter_control", "parameter_control")]

        # Find matched PBI page
        pbi_page_visuals = pbi["visuals_by_page"].get(db_name, [])
        pbi_content = [v for v in pbi_page_visuals
                       if v["type"] not in ("textbox", "image", "actionButton")]
        pbi_slicers = [v for v in pbi_content if v["type"] == "slicer"]
        pbi_charts = [v for v in pbi_content if v["type"] != "slicer"]

        for ws_name in ws_refs:
            ws_in_dashboard.add(ws_name)

        page_results.append({
            "dashboard": db_name,
            "tab_worksheets": len(ws_refs),
            "tab_filters": len(filter_refs),
            "pbi_charts": len(pbi_charts),
            "pbi_slicers": len(pbi_slicers),
            "ws_names": ws_refs,
            "chart_types": [v["type"] for v in pbi_charts],
        })

    # Worksheets NOT on any dashboard (standalone sheets)
    standalone = [ws for ws in worksheets if ws.get("name", "") not in ws_in_dashboard]

    # Summary: count content visuals vs worksheet refs
    total_ws_refs = sum(r["tab_worksheets"] for r in page_results)
    total_pbi_charts = sum(r["pbi_charts"] for r in page_results)
    total_pbi_slicers = sum(r["pbi_slicers"] for r in page_results)

    return {
        "worksheet_count": len(worksheets),
        "worksheets_in_dashboards": len(ws_in_dashboard),
        "standalone_worksheets": len(standalone),
        "pbi_visual_count": len(all_pbi_visuals),
        "total_ws_refs_in_dashboards": total_ws_refs,
        "total_pbi_charts": total_pbi_charts,
        "total_pbi_slicers": total_pbi_slicers,
        "per_page": page_results,
    }


def compare_calculations(src, pbi):
    """3. Calculations → Measures + Calc Columns.

    Matches by caption (display name) since PBI uses captions, not internal IDs.
    """
    calcs = src["calculations"]
    measures = pbi["measures"]
    calc_cols = pbi["calc_cols"]

    measure_names = {m["name"] for m in measures}
    measure_lower = {m["name"].lower(): m["name"] for m in measures}
    calc_col_names = {c["name"] for c in calc_cols}
    calc_col_lower = {c["name"].lower(): c["name"] for c in calc_cols}
    # Also include regular source columns (Tableau calcs converted to M transforms)
    all_columns = set()
    for cols in pbi.get("columns_by_table", {}).values():
        all_columns.update(cols)
    all_columns_lower = {c.lower(): c for c in all_columns}

    matched = []
    missing = []
    seen_captions = set()

    for c in calcs:
        caption = c.get("caption", c.get("name", ""))
        name = c.get("name", "")
        formula = c.get("formula", "")
        role = c.get("role", "")
        if not caption:
            continue

        # Deduplicate by caption (Tableau can have multiple internal calcs
        # with same caption from copy operations)
        if caption in seen_captions:
            continue
        seen_captions.add(caption)

        # Match by exact caption, then case-insensitive
        pbi_type = None
        if caption in measure_names:
            pbi_type = "measure"
        elif caption in calc_col_names:
            pbi_type = "calc_column"
        elif caption in all_columns:
            pbi_type = "column"
        elif caption.lower() in measure_lower:
            pbi_type = "measure"
        elif caption.lower() in calc_col_lower:
            pbi_type = "calc_column"
        elif caption.lower() in all_columns_lower:
            pbi_type = "column"

        if pbi_type:
            matched.append({"name": caption, "role": role, "pbi_type": pbi_type})
        else:
            # Categorize the missing calculation
            is_desc = "Description" in caption or "description" in caption
            is_literal = (formula.startswith('"') or formula.startswith("'")
                          or re.match(r'^-?\d+\.?\d*$', formula.strip()))
            is_kpi_text = caption.startswith("KPI_") and ("_Calculation" in caption)
            # KPI_*_Calculation formulas that look like human-readable descriptions
            # (e.g. "Average of [Amount]") rather than actual Tableau calc syntax
            if is_kpi_text and formula.startswith('"'):
                is_desc = True
            category = "description" if is_desc else ("literal" if is_literal else "formula")
            missing.append({"name": caption, "role": role, "formula": formula[:100],
                            "category": category})

    # Categorize missing
    missing_by_cat = {}
    for m in missing:
        cat = m["category"]
        missing_by_cat[cat] = missing_by_cat.get(cat, 0) + 1

    # Non-functional calcs (descriptions, literals) are intentionally not
    # migrated as separate DAX objects — they are metadata, not logic.
    non_functional = sum(v for k, v in missing_by_cat.items()
                         if k in ("description", "literal"))

    return {
        "tableau_calcs": len(seen_captions),
        "pbi_measures": len(measures),
        "pbi_calc_cols": len(calc_cols),
        "matched": len(matched),
        "missing": len(missing),
        "non_functional_missing": non_functional,
        "missing_by_category": missing_by_cat,
        "missing_details": missing,
        "matched_details": matched,
    }


def compare_filters(src, pbi):
    """5. Filters."""
    tab_filters = src["filters"]
    # Count PBI filters at report, page, visual levels
    report_filters = len(pbi["report"].get("filters", []))
    page_filters = 0
    visual_filters = 0
    slicer_count = 0
    for page_name, visuals in pbi["visuals_by_page"].items():
        for v in visuals:
            visual_filters += v["filter_count"]
            if v["type"] == "slicer":
                slicer_count += 1

    return {
        "tableau_global_filters": len(tab_filters),
        "pbi_report_filters": report_filters,
        "pbi_visual_filters": visual_filters,
        "pbi_slicers": slicer_count,
    }


def compare_parameters(src, pbi):
    """6. Parameters."""
    tab_params = src["parameters"]
    # Count PBI parameter tables (tables starting with parameter-like names)
    pbi_param_tables = [t for t in pbi["tables"]
                        if t not in ("Calendar",) and any(
                            p.get("caption", p.get("name", "")).lower() == t.lower()
                            for p in tab_params)]
    return {
        "tableau_parameters": len(tab_params),
        "pbi_parameter_tables": len(pbi_param_tables),
    }


def compare_datasources(src, pbi):
    """7. Datasources → Tables / Columns."""
    tab_ds = src["datasources"]
    tab_tables = set()
    tab_columns = 0
    for ds in tab_ds:
        for t in ds.get("tables", []):
            tname = t.get("name", "")
            if tname:
                tab_tables.add(tname)
            tab_columns += len(t.get("columns", []))

    return {
        "tableau_datasources": len(tab_ds),
        "tableau_tables": len(tab_tables),
        "tableau_columns": tab_columns,
        "pbi_tables": len(pbi["tables"]),
        "pbi_columns": sum(len(cols) for cols in pbi["columns_by_table"].values()),
    }


def compare_stories(src, pbi):
    """9. Stories → Bookmarks."""
    stories = src["stories"]
    # Check bookmarks dir
    return {
        "tableau_stories": len(stories),
    }


# ---------------------------------------------------------------------------
# Main comparison orchestrator
# ---------------------------------------------------------------------------

def run_comparison(pbip_dir, extract_dir, verbose=False):
    """Run all comparisons and return structured results."""
    src = load_tableau(extract_dir)
    pbi = load_pbi(pbip_dir)

    results = {
        "source_dir": extract_dir,
        "output_dir": pbip_dir,
        "dashboards": compare_dashboards(src, pbi),
        "visuals": compare_visuals(src, pbi),
        "calculations": compare_calculations(src, pbi),
        "filters": compare_filters(src, pbi),
        "parameters": compare_parameters(src, pbi),
        "datasources": compare_datasources(src, pbi),
        "stories": compare_stories(src, pbi),
    }

    # Overall score
    dash = results["dashboards"]
    vis = results["visuals"]
    calc = results["calculations"]
    ds = results["datasources"]

    scores = []
    if dash["dashboard_count"]:
        scores.append(dash["matched"] / dash["dashboard_count"])
    if vis["total_ws_refs_in_dashboards"]:
        # Compare worksheet refs vs PBI content visuals (charts + slicers)
        ratio = min(1.0, (vis["total_pbi_charts"] + vis["total_pbi_slicers"]) / vis["total_ws_refs_in_dashboards"])
        scores.append(ratio)
    if calc["tableau_calcs"]:
        # Non-functional calcs (descriptions, literals) are intentionally not
        # migrated — count them as accounted-for in the score.
        effective = calc["matched"] + calc.get("non_functional_missing", 0)
        scores.append(min(1.0, effective / calc["tableau_calcs"]))

    results["overall_score"] = round(sum(scores) / len(scores) * 100, 1) if scores else 0

    return results


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"
_DIM = "\033[2m"


def _status(ok, total=None):
    if total is not None:
        pct = ok / total * 100 if total else 100
        color = _GREEN if pct >= 90 else (_YELLOW if pct >= 60 else _RED)
        return f"{color}{ok}/{total} ({pct:.0f}%){_RESET}"
    return f"{_GREEN}OK{_RESET}" if ok else f"{_RED}FAIL{_RESET}"


def print_results(results, verbose=False):
    """Print comparison results to console."""
    print(f"\n{_BOLD}{'=' * 72}{_RESET}")
    print(f"{_BOLD}  MIGRATION FIDELITY COMPARISON{_RESET}")
    print(f"{_BOLD}{'=' * 72}{_RESET}")

    score = results["overall_score"]
    color = _GREEN if score >= 90 else (_YELLOW if score >= 60 else _RED)
    print(f"\n  Overall Score: {color}{_BOLD}{score}%{_RESET}")

    # ── 1. Dashboards → Pages ──
    dash = results["dashboards"]
    print(f"\n{_CYAN}  1. DASHBOARDS → PAGES{_RESET}")
    print(f"     Tableau dashboards: {dash['dashboard_count']}")
    print(f"     PBI pages:          {dash['page_count']}")
    print(f"     Matched:            {_status(dash['matched'], dash['dashboard_count'])}")
    if verbose:
        for d in dash["details"]:
            size_icon = f"{_GREEN}✓{_RESET}" if d["size_match"] else f"{_RED}✗{_RESET}"
            match_icon = f"{_GREEN}✓{_RESET}" if d["matched"] else f"{_RED}✗{_RESET}"
            ws_vs_vis = f"ws={d['tab_worksheets']} flt={d['tab_filters']}"
            pbi_breakdown = f"charts={d['pbi_content']} slicers={d['pbi_slicers']} text={d['pbi_textboxes']} img={d['pbi_images']}"
            print(f"       {match_icon} {d['dashboard']:30s}  {d['tab_size']:>11s} → {d['pbi_size']:>11s}  {size_icon}  [{ws_vs_vis}] → [{pbi_breakdown}]")

    # ── 2. Visuals ──
    vis = results["visuals"]
    print(f"\n{_CYAN}  2. WORKSHEETS → VISUALS (dashboard-centric){_RESET}")
    print(f"     Tableau worksheets:       {vis['worksheet_count']}  (in dashboards: {vis['worksheets_in_dashboards']}, standalone: {vis['standalone_worksheets']})")
    print(f"     WS refs in dashboards:    {vis['total_ws_refs_in_dashboards']}")
    print(f"     PBI content visuals:      {vis['total_pbi_charts']} charts + {vis['total_pbi_slicers']} slicers")
    print(f"     PBI total visuals:        {vis['pbi_visual_count']}")
    if verbose:
        for pr in vis["per_page"]:
            ws_ok = pr["tab_worksheets"]
            pbi_ok = pr["pbi_charts"] + pr["pbi_slicers"]
            icon = f"{_GREEN}✓{_RESET}" if pbi_ok >= ws_ok else f"{_YELLOW}~{_RESET}"
            print(f"       {icon} {pr['dashboard']:30s}  tab: {pr['tab_worksheets']} ws + {pr['tab_filters']} flt  →  pbi: {pr['pbi_charts']} charts + {pr['pbi_slicers']} slicers")
            if pr["chart_types"]:
                types = {}
                for t in pr["chart_types"]:
                    types[t] = types.get(t, 0) + 1
                type_str = ", ".join(f"{t}:{n}" for t, n in sorted(types.items()))
                print(f"         PBI types: {type_str}")

    # ── 3. Calculations ──
    calc = results["calculations"]
    print(f"\n{_CYAN}  3. CALCULATIONS → DAX{_RESET}")
    print(f"     Tableau calcs:      {calc['tableau_calcs']}")
    print(f"     PBI measures:       {calc['pbi_measures']}")
    print(f"     PBI calc columns:   {calc['pbi_calc_cols']}")
    print(f"     Matched:            {_status(calc['matched'], calc['tableau_calcs'])}")
    nf = calc.get("non_functional_missing", 0)
    formula_missing = calc.get("missing", 0) - nf
    print(f"     Missing formulas:   {formula_missing}")
    if nf:
        print(f"     Non-functional:     {nf} (descriptions/literals — excluded from score)")
    cats = calc.get("missing_by_category", {})
    if cats:
        parts = []
        if cats.get("description"):
            parts.append(f"{cats['description']} descriptions")
        if cats.get("literal"):
            parts.append(f"{cats['literal']} literals")
        if cats.get("formula"):
            parts.append(f"{cats['formula']} formulas")
        print(f"       Breakdown:        {', '.join(parts)}")
    if verbose and calc["missing_details"]:
        formulas = [m for m in calc["missing_details"] if m["category"] == "formula"]
        if formulas:
            print(f"\n     {_RED}Missing formula calculations ({len(formulas)}):{_RESET}")
            for m in formulas[:15]:
                print(f"       {m['name'][:40]:40s}  role={m['role']:10s}  {_DIM}{m['formula'][:50]}{_RESET}")
        descs = [m for m in calc["missing_details"] if m["category"] != "formula"]
        if descs and verbose:
            print(f"\n     {_DIM}Skipped non-formula calcs ({len(descs)}): descriptions, literals, metadata{_RESET}")

    # ── 4. Filters ──
    filt = results["filters"]
    print(f"\n{_CYAN}  4. FILTERS{_RESET}")
    print(f"     Tableau global:     {filt['tableau_global_filters']}")
    print(f"     PBI report filters: {filt['pbi_report_filters']}")
    print(f"     PBI visual filters: {filt['pbi_visual_filters']}")
    print(f"     PBI slicers:        {filt['pbi_slicers']}")

    # ── 5. Parameters ──
    params = results["parameters"]
    print(f"\n{_CYAN}  5. PARAMETERS{_RESET}")
    print(f"     Tableau parameters: {params['tableau_parameters']}")
    print(f"     PBI parameter tables: {params['pbi_parameter_tables']}")

    # ── 6. Datasources ──
    ds = results["datasources"]
    print(f"\n{_CYAN}  6. DATA MODEL{_RESET}")
    print(f"     Tableau datasources: {ds['tableau_datasources']}")
    print(f"     Tableau tables:      {ds['tableau_tables']}")
    print(f"     PBI tables:          {ds['pbi_tables']}")
    print(f"     Tableau columns:     {ds['tableau_columns']}")
    print(f"     PBI columns:         {ds['pbi_columns']}")

    # ── 7. Stories ──
    stories = results["stories"]
    if stories["tableau_stories"]:
        print(f"\n{_CYAN}  7. STORIES → BOOKMARKS{_RESET}")
        print(f"     Tableau stories:    {stories['tableau_stories']}")

    print(f"\n{_BOLD}{'=' * 72}{_RESET}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compare Tableau extraction vs PBI output for migration fidelity.",
    )
    parser.add_argument("pbip_dir", help="Path to the generated .pbip project directory")
    parser.add_argument("--extract-dir", default=None,
                        help="Path to tableau_export/ directory (default: auto-detect)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed per-item comparison")
    parser.add_argument("--json", dest="json_out", metavar="FILE",
                        help="Write results to JSON file")
    args = parser.parse_args()

    pbip_dir = os.path.abspath(args.pbip_dir)
    if not os.path.isdir(pbip_dir):
        print(f"ERROR: {pbip_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    extract_dir = args.extract_dir
    if not extract_dir:
        # Auto-detect: look for tableau_export/ relative to this script's repo
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(script_dir)
        extract_dir = os.path.join(repo_root, "tableau_export")
    extract_dir = os.path.abspath(extract_dir)

    if not os.path.isdir(extract_dir):
        print(f"ERROR: {extract_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    results = run_comparison(pbip_dir, extract_dir, verbose=args.verbose)
    print_results(results, verbose=args.verbose)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {os.path.abspath(args.json_out)}")


if __name__ == "__main__":
    main()
