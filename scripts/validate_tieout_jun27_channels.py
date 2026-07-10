"""
Full region x channel tie-out check for June FY27 (FM1) against
data/_tieout_jun27.json (extracted from the Excel 'Account by Region
Summary' sheet).

Unlike validate_tieout.py (region rollups only, "Total" channel), this
checks every (region, channel) intersection at both:
  (a) individual GL account level (1:1 with Excel account rows)
  (b) category-subtotal level (Gross Revenue, Advertising, Salaries & Wages,
      Freight, Contract Labor, Rent & Leases, Software & Technology,
      Travel & Entertainment, Supplies, Repair and Maintenance, Tradeshows,
      Telecom, Other Expense, Total OPEX, Total Marketing)

marketing.json is in DOLLARS; the Excel is in THOUSANDS -> json values /1000.

Usage:  python scripts/validate_tieout_jun27_channels.py
"""
import json, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = json.load(open(ROOT / "data" / "marketing.json", encoding="utf-8"))
TIE  = json.load(open(ROOT / "data" / "_tieout_jun27.json", encoding="utf-8"))

FY, MI = "2027", 0   # FY2027, fiscal month 1 (June)
ADV = {"6736000","6738000","6740000","6746000","6747000","6750000","6763000","6775000","6790000"}

REGION_COS = {
    "Americas":  {11,14,74,86,16,13,1711,5533,2920,3032, 20,70, 33,168},
    "Australia": {30,32},
    "UK":        {40},
    "EMEA":      {41},
    "China":     {65},
}
REGION_COS["ROW"] = set().union(REGION_COS["Australia"], REGION_COS["UK"], REGION_COS["EMEA"], REGION_COS["China"])

DISPLAY_CHANNELS = ["Wholesale","DTC","Freemotion","iFIT - Core","iFIT - App","Corp/Other"]
def norm_channel(raw):
    u = str(raw or "").strip().upper()
    if u in ("WHSL","WHOLESALE"): return "Wholesale"
    if u == "DTC": return "DTC"
    if u in ("FM","FREEMOTION","COMMERCIAL (FM)"): return "Freemotion"
    if u in ("IFIT - CORE","IFIT-CORE","IFIT CORE"): return "iFIT - Core"
    if u in ("IFIT - APP","IFIT-APP","IFIT APP"): return "iFIT - App"
    return "Corp/Other"

accts = DATA["accounts"]
FX = DATA.get("meta", {}).get("fx_rates", {})

def fx_rate(co, fy, fm):
    """Matches client-side fxRate(): rate for company/fy/fiscal-month(1-based)."""
    arr = FX.get(str(co), {}).get(str(fy))
    return arr[fm-1] if arr and len(arr) >= fm else None

# Excel item label -> json category name (where they differ)
CATEGORY_LABEL_MAP = {
    "Salaries & Wages": "Salaries & Wages",
    "Freight": "Freight",
    "Contract Labor": "Contract Labor",
    "Rent & Leases": "Rent & Leases",
    "Software & Technology": "Software",
    "Travel & Entertainment": "Travel",
    "Supplies": "Supplies",
    "Repair and Maintenance": "Repair & Maintenance",
    "Tradeshows": "Tradeshows",
    "Telecom": "Telecom",
    "Other Expense": "Other Expenses",
}

def account_june_by_channel_region(a, region, channel_disp):
    """June FY27 actual $ for account `a`, restricted to companies in `region`
    and raw channels normalizing to `channel_disp` (or unrestricted if None)."""
    cbc = (a.get("actuals_by_channel_company") or {}).get(FY) or {}
    cos = REGION_COS[region]
    total = 0.0
    for raw_ch, bycompany in cbc.items():
        if channel_disp is not None and norm_channel(raw_ch) != channel_disp:
            continue
        for co, v in bycompany.items():
            if int(co) in cos and len(v) > MI:
                # Matches client-side rendering: actuals_by_channel_company is stored in LOCAL
                # currency; the app converts to USD as v / fxRate(co, fy, month) at display time
                # (see index.html channelActualsMonthly etc.). Reconciling raw, unconverted values
                # here would falsely look like a region-wide FX-driven mismatch that doesn't
                # actually exist on screen.
                r = fx_rate(co, FY, MI + 1)
                total += (v[MI] / r) if r else v[MI]
    return total

REV_GL_PL = DATA.get("meta", {}).get("rev_gl_pl", {})

def gross_revenue_by_channel_region(region, channel_disp):
    """June FY27 Gross Revenue $ — from meta.rev_gl_pl (the app's actual Media-tab revenue
    source, a separate Snowflake pull from the OPEX/Advertising actuals), NOT from summing
    Revenue-category GL accounts out of actuals_by_channel_company. rev_gl_pl's channel keys
    are already display buckets (Wholesale/DTC/...), not raw codes needing norm_channel."""
    cos = REGION_COS[region]
    disp_channels = [channel_disp] if channel_disp is not None else DISPLAY_CHANNELS
    total = 0.0
    for ch in disp_channels:
        for co, byfy in (REV_GL_PL.get(ch) or {}).items():
            if not str(co).isdigit() or int(co) not in cos:
                continue
            arr = byfy.get(FY)
            if not arr or len(arr) <= MI:
                continue
            r = fx_rate(co, FY, MI + 1)
            total += (arr[MI] / r) if r else arr[MI]
    return total

GROSS_REV_ACCTS = {"4500000", "4500777", "4500774", "4500123"}

def rollup_by_channel_region(region, channel_disp, revenue_source="gross_rev_accts"):
    """(gross_revenue, advertising, opex, total_marketing, {excel_category_label: $}) in $K.
    revenue_source: 'gl_actuals' sums the Revenue-category GL accounts out of
    actuals_by_channel_company (the same dept-75/advertising/revenue-union pull that feeds
    everything else here) -- 'rev_gl_pl' uses the Media tab's separate ADAPTIVE_GL_PL_ACTUALS
    pull, which has narrower company coverage (only a handful of companies loaded) and is NOT
    expected to match a full region rollup."""
    rev = adv = opex = 0.0
    cat_totals = {}
    for a in accts:
        ra, cat = a["reporting_account"], a["category"]
        v = account_june_by_channel_region(a, region, channel_disp) / 1000.0
        if cat == "Revenue":
            if revenue_source == "gl_actuals":
                rev += v
            elif revenue_source == "gross_rev_accts" and ra in GROSS_REV_ACCTS:
                rev += v
            continue
        if ra in ADV:
            adv += v
        else:
            opex += v
        cat_totals[cat] = cat_totals.get(cat, 0.0) + v
    if revenue_source == "rev_gl_pl":
        rev = gross_revenue_by_channel_region(region, channel_disp) / 1000.0
    return rev, adv, opex, adv + opex, cat_totals

def excel_val(region, item, channel):
    return (TIE["matrix"].get(region, {}).get("Actuals", {}).get(channel, {}) or {}).get(item)

def diffline(label, region, channel, j, x, tol=0.5):
    if j is None and x is None:
        return None
    j = j or 0.0
    x = 0.0 if x is None else x
    d = j - x
    if abs(d) <= tol:
        return None
    pct = f"{(d/x*100):+.1f}%" if abs(x) > 0.01 else "n/a"
    return f"{region:10} | {channel:12} | {label:32} | json {j:12,.1f} vs excel {x:12,.1f} | diff {d:+10,.1f}  ({pct})"

print("="*140)
print("JUNE FY27 (FM1) FULL REGION x CHANNEL TIE-OUT — json (marketing.json) vs Excel 'Account by Region Summary' Actuals")
print("Values in $K. Flagging diffs > $0.5K.")
print("="*140)

mismatches = []
for region in ["Americas","Australia","UK","EMEA","China","ROW"]:
    for channel in DISPLAY_CHANNELS + ["Total"]:
        ch_arg = None if channel == "Total" else channel
        rev, adv, opex, total_mkt, cats = rollup_by_channel_region(region, ch_arg)

        l = diffline("Gross Revenue", region, channel, rev, excel_val(region, "Gross Revenue", channel))
        if l: mismatches.append(l)
        l = diffline("Advertising", region, channel, adv, excel_val(region, "Advertising", channel))
        if l: mismatches.append(l)
        l = diffline("Total OPEX", region, channel, opex, excel_val(region, "Total OPEX", channel))
        if l: mismatches.append(l)
        l = diffline("Total Marketing", region, channel, total_mkt, excel_val(region, "Total Marketing", channel))
        if l: mismatches.append(l)
        for excel_label, json_cat in CATEGORY_LABEL_MAP.items():
            l = diffline(excel_label, region, channel, cats.get(json_cat, 0.0), excel_val(region, excel_label, channel))
            if l: mismatches.append(l)

        # Individual GL accounts explicitly listed in the Excel
        for a in accts:
            ra, name = a["reporting_account"], a.get("account_name") or ""
            label = f"{ra} - {name}"
            xv = excel_val(region, label, channel)
            if xv is None:
                continue
            jv = account_june_by_channel_region(a, region, ch_arg) / 1000.0
            l = diffline(label, region, channel, jv, xv)
            if l: mismatches.append(l)

print(f"\n{len(mismatches)} mismatches found (>$0.5K):\n")
for m in mismatches:
    print(m)
