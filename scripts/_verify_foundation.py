"""Throwaway: verify the brand/slug/data-path foundation is consistent."""
import json, re, sys
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
R = Path(__file__).resolve().parent.parent
html = (R / "dashboard" / "index.html").read_text(encoding="utf-8")
print("leftover 'member-care'/'Member Care' in index.html:", len(re.findall(r"member-care|Member Care", html)))
print("references ../data/marketing.json:", "../data/marketing.json" in html)
print("references ../data/member-care.json:", "../data/member-care.json" in html)
man = json.loads((R / "data" / "manifest.json").read_text(encoding="utf-8"))
cfg = json.loads((R / "data" / "_domain_config.json").read_text(encoding="utf-8"))
acc = json.loads((R / "access.json").read_text(encoding="utf-8"))
mk  = json.loads((R / "data" / "marketing.json").read_text(encoding="utf-8"))
slug = man["tabs"][0]["slug"]
print("manifest slug:", slug, "| section_children has key:", slug in cfg["section_children"])
print("section_children regions:", [c["id"] for c in cfg["section_children"][slug]])
print("marketing.json accounts:", len(mk["accounts"]), "| meta.slug:", mk["meta"]["slug"])
print("access users:", list(acc["users"].keys()))
print("ALL JSON VALID + CHECKS DONE")
