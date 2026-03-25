"""Temporary inspection script for NBA visuals."""
import json, os, glob

base = "c:/temp/nba_fix3/nba_player_stats/nba_player_stats.Report/definition/pages"
for page_dir in sorted(glob.glob(os.path.join(base, "*"))):
    vis_base = os.path.join(page_dir, "visuals")
    if not os.path.isdir(vis_base):
        continue
    for vd in sorted(os.listdir(vis_base)):
        vf = os.path.join(vis_base, vd, "visual.json")
        if not os.path.exists(vf):
            continue
        v = json.load(open(vf, encoding="utf-8"))
        vtype = v.get("visual", {}).get("visualType", "")
        vco = v.get("visual", {}).get("visualContainerObjects", {})
        tp = vco.get("title", [{}])[0].get("properties", {})
        title_val = tp.get("text", {})
        if isinstance(title_val, dict):
            title_val = title_val.get("expr", {}).get("Literal", {}).get("Value", "")
        print(f"\n  {vd} type={vtype: <25} title={title_val}")
        
        # Show query projections and data roles
        q = v.get("visual", {}).get("query", {})
        if q:
            cmds = q.get("Commands", [])
            for cmd in cmds:
                qs = cmd.get("SemanticQueryDataShapeCommand", {}).get("Query", {})
                sels = qs.get("Select", [])
                for s in sels:
                    sname = s.get("Name", "")
                    print(f"    sel: {sname}")
            # Show queryState roles
            binding = q.get("queryState", {})
            for role, val in binding.items():
                projs = val.get("projections", [])
                proj_names = [p.get("queryRef", "") for p in projs]
                print(f"    role[{role}]: {proj_names}")
