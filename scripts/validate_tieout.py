"""
Tie-out check: compare the refreshed marketing.json against the Excel
'Total Marketing Spend Review' May FY26 targets (data/_tieout_may26.json).

Focus: May FY26 = FY2026, fiscal month 12 (index 11).
Compares (a) GLOBAL totals (all companies) and (b) per-region splits, for both
the 8+4 Final forecast and Actuals, at the account level and the rollup level
(Advertising / Total OPEX / Total Marketing).

marketing.json is in DOLLARS; the Excel is in THOUSANDS -> json values /1000.

Usage:  python scripts/validate_tieout.py
"""
import json, re, sys
from pathlib import Path
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = json.load(open(ROOT / "data" / "marketing.json", encoding="utf-8"))
TIE  = json.load(open(ROOT / "data" / "_tieout_may26.json", encoding="utf-8"))

FY, MI = "2026", 11           # FY2026, fiscal month 12 (May) -> index 11
FC_KEY = "FY26: 8+4 Final | FY2026"
ADV = {"6736000","6738000","6740000","6746000","6747000","6750000","6763000","6775000","6790000"}

# source_company -> region (matches the Excel's region taxonomy; ROW = Aus+UK+EMEA+China)
REGION_COS = {
    "Americas":  {11,14,74,86,16,13,1711,5533,2920,3032, 20,70, 33,168},
    "Australia": {30,32},
    "UK":        {40},
    "EMEA":      {41},
    "China":     {65},
}
REGION_COS["ROW"] = set().union(REGION_COS["Australia"], REGION_COS["UK"], REGION_COS["EMEA"], REGION_COS["China"])
GLOBAL_COS = set().union(*REGION_COS.values()) | {71}   # include LATAM in global (Excel omits it)

accts = DATA["accounts"]

def arr(d, *keys):
    for k in keys:
        d = (d or {}).get(k)
        if d is None: return None
    return d

def actual_may(a, cos):
    """May actual (dollars) for account a summed over companies in `cos`."""
    byco = arr(a, "actuals_by_company", FY) or {}
    return sum((v[MI] if len(v) > MI else 0) for c, v in byco.items() if int(c) in cos)

def fc_may(a, cos):
    """May 8+4 forecast (dollars) for account a summed over companies in `cos`."""
    byco = arr(a, "forecasts_by_company", FC_KEY) or {}
    if byco:
        return sum((v[MI] if len(v) > MI else 0) for c, v in byco.items() if int(c) in cos)
    return None  # no per-company forecast available

def global_actual(a):
    v = arr(a, "actuals", FY) or []
    return v[MI] if len(v) > MI else 0

def global_fc(a):
    v = arr(a, "forecasts", FC_KEY) or []
    return v[MI] if len(v) > MI else 0

# ---------- Build json rollups (in thousands) ----------
def rollups(cos, use_global=False):
    adv = opex = 0.0
    adv_fc = opex_fc = 0.0
    per_acct = {}
    for a in accts:
        ra = a["reporting_account"]
        act = (global_actual(a) if use_global else actual_may(a, cos)) / 1000.0
        fcm = global_fc(a) if use_global else fc_may(a, cos)
        fcm = (fcm / 1000.0) if fcm is not None else None
        per_acct[ra] = (act, fcm)
        cat = a["category"]
        if ra in ADV:
            adv += act; adv_fc += (fcm or 0)
        elif cat not in ("Revenue",):
            opex += act; opex_fc += (fcm or 0)
    return dict(adv=adv, opex=opex, total=adv+opex,
                adv_fc=adv_fc, opex_fc=opex_fc, total_fc=adv_fc+opex_fc,
                per_acct=per_acct)

def excel_val(region, version, item):
    return arr(TIE["matrix"], region, version, "Total", item)

def line(label, j_act, x_act, j_fc, x_fc):
    def d(j, x):
        if j is None or x is None: return ""
        dd = j - x
        flag = "  <-- DIFF" if abs(dd) > 1.0 else ""   # >$1K
        return f"{dd:+9.1f}{flag}"
    ja = "" if j_act is None else f"{j_act:11.1f}"
    xa = "" if x_act is None else f"{x_act:11.1f}"
    jf = "" if j_fc  is None else f"{j_fc:11.1f}"
    xf = "" if x_fc  is None else f"{x_fc:11.1f}"
    print(f"{label:34} | A:{ja} vs {xa} {d(j_act,x_act):>14} | 8+4:{jf} vs {xf} {d(j_fc,x_fc):>14}")

print("="*150)
print("MARKETING TIE-OUT — May FY26 (FM12).  Values in $K.  'A'=Actuals, '8+4'=FY26 8+4 Final.  json (left) vs Excel (right).")
print("="*150)

# ---- GLOBAL (all companies) vs Excel Americas+ROW ----
g = rollups(GLOBAL_COS, use_global=True)
xa_adv = (excel_val("Americas","Actuals","Advertising") or 0) + (excel_val("ROW","Actuals","Advertising") or 0)
xf_adv = (excel_val("Americas","FY26: 8+4 Final","Advertising") or 0) + (excel_val("ROW","FY26: 8+4 Final","Advertising") or 0)
xa_tot = (excel_val("Americas","Actuals","Total Marketing") or 0) + (excel_val("ROW","Actuals","Total Marketing") or 0)
xf_tot = (excel_val("Americas","FY26: 8+4 Final","Total Marketing") or 0) + (excel_val("ROW","FY26: 8+4 Final","Total Marketing") or 0)
xa_op  = (excel_val("Americas","Actuals","Total OPEX") or 0) + (excel_val("ROW","Actuals","Total OPEX") or 0)
xf_op  = (excel_val("Americas","FY26: 8+4 Final","Total OPEX") or 0) + (excel_val("ROW","FY26: 8+4 Final","Total OPEX") or 0)
print("\n### GLOBAL (json all companies incl. LATAM)  vs  Excel (Americas + ROW) ###")
line("Advertising",     g["adv"],   xa_adv, g["adv_fc"],   xf_adv)
line("Total OPEX",      g["opex"],  xa_op,  g["opex_fc"],  xf_op)
line("Total Marketing", g["total"], xa_tot, g["total_fc"], xf_tot)
print("\n  Advertising by account (global):")
for ra in sorted(ADV):
    ja, jf = g["per_acct"].get(ra, (None,None))
    line("  "+ra, ja, None, jf, None)

# ---- Per region ----
for region in ["Americas","Australia","UK","EMEA","China","ROW"]:
    r = rollups(REGION_COS[region])
    print(f"\n### {region}  (json source-company mapping)  vs  Excel {region} ###")
    line("Advertising",     r["adv"],   excel_val(region,"Actuals","Advertising"),     r["adv_fc"],   excel_val(region,"FY26: 8+4 Final","Advertising"))
    line("Total OPEX",      r["opex"],  excel_val(region,"Actuals","Total OPEX"),      r["opex_fc"],  excel_val(region,"FY26: 8+4 Final","Total OPEX"))
    line("Total Marketing", r["total"], excel_val(region,"Actuals","Total Marketing"), r["total_fc"], excel_val(region,"FY26: 8+4 Final","Total Marketing"))
