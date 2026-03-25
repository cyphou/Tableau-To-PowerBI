"""Scan all workbooks for title formatting attributes."""
import xml.etree.ElementTree as ET
import os
import glob
import zipfile

for f in sorted(glob.glob("examples/**/*.twb*", recursive=True)):
    try:
        if f.endswith(".twbx"):
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    if n.endswith(".twb"):
                        root = ET.fromstring(z.read(n))
                        break
        else:
            root = ET.parse(f).getroot()
        for ws in root.findall(".//worksheet"):
            title_el = ws.find(".//title")
            if title_el is not None:
                runs = title_el.findall(".//run")
                if runs:
                    for r in runs:
                        attrs = dict(r.attrib)
                        if attrs:
                            wsn = ws.get("name", "")
                            bn = os.path.basename(f)
                            print(f"{bn} | {wsn} | {attrs} | {repr(r.text)}")
    except Exception as e:
        pass
