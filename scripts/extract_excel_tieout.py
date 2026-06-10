"""
One-off: extract May FY26 tie-out targets from the Marketing Excel Summary sheet,
and cross-check against the transaction-level Detail sheet to confirm the period.

Writes data/_tieout_may26.json (the authoritative tie-out reference used later by
validate_tieout.py to compare against the refreshed marketing.json).

Usage:  python scripts/extract_excel_tieout.py
"""
import json, openpyxl, sys
from pathlib import Path
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

XLSX = r"G:\Shared drives\FP&A\Monthly Reporting\FY26\12 - May\Marketing\Total Marketing Spend Review_May26_V2.xlsx"
OUT  = Path(__file__).resolve().parent.parent / "data" / "_tieout_may26.json"

wb = openpyxl.load_workbook(XLSX, data_only=True, read_only=True)

# ---------- 1) Map Summary columns -> (region, version, channel) ----------
ws = wb["Summary"]
rows = list(ws.iter_rows(values_only=True))
def cell(r, c):
    return rows[r-1][c] if r-1 < len(rows) and c < len(rows[r-1]) else None

ncols = max(len(r) for r in rows)
# Row 2 = region (merged), Row 3 = version (merged), Row 4 = channel (per col)
region_row, version_row, channel_row = 2, 3, 4
col_map = {}   # col_idx -> (region, version, channel)
cur_region = cur_version = None
for c in range(ncols):
    rg = cell(region_row, c);   rg = str(rg).strip() if rg is not None else None
    vr = cell(version_row, c);  vr = str(vr).strip() if vr is not None else None
    ch = cell(channel_row, c);  ch = str(ch).strip() if ch is not None else None
    if rg: cur_region = rg
    if vr: cur_version = vr
    if ch:  # a real data column has a channel header
        col_map[c] = (cur_region, cur_version, ch)

regions  = sorted({v[0] for v in col_map.values() if v[0]})
versions = sorted({v[1] for v in col_map.values() if v[1]})
channels = [c for c in dict.fromkeys(v[2] for v in col_map.values())]  # preserve order
print("Regions :", regions)
print("Versions:", versions)
print("Channels:", channels)

# ---------- 2) Extract line-item values ----------
# Line-item label = col D (index 3); detail label = col A (index 0)
LABEL_COL, FULL_COL = 3, 0
matrix = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))  # region->version->channel->{item:val}
items_order = []
for r in range(5, len(rows) + 1):
    label = cell(r, LABEL_COL)
    full  = cell(r, FULL_COL)
    name = (str(label).strip() if label is not None else "") or (str(full).strip() if full is not None else "")
    if not name:
        continue
    if name not in items_order:
        items_order.append(name)
    for c, (rg, vr, ch) in col_map.items():
        val = cell(r, c)
        if isinstance(val, (int, float)):
            matrix[rg][vr][ch][name] = round(float(val), 4)

# ---------- 3) Cross-check period via Detail sheet ----------
wd = wb["Detail"]
dheaders = None
fm_totals = defaultdict(float)        # fiscal_month -> sum(TOTAL)
fm_rowcount = defaultdict(int)
adv_accts = {"6736000","6738000","6739000","6740000","6744000","6746000","6747000",
             "6750000","6763000","6775000","6790000"}
for i, row in enumerate(wd.iter_rows(values_only=True), 1):
    if i == 1:
        dheaders = [str(c).strip() if c else "" for c in row]
        idx = {h: j for j, h in enumerate(dheaders)}
        continue
    fm = row[idx["FISCAL_MONTH"]]
    tot = row[idx["TOTAL"]]
    if fm is None or tot is None:
        continue
    fm = int(fm);
    fm_totals[fm] += float(tot)
    fm_rowcount[fm] += 1

print("\nDetail sheet rows by FISCAL_MONTH (sum of TOTAL, $):")
for fm in sorted(fm_totals):
    print(f"  FM{fm:>2}: rows={fm_rowcount[fm]:>5}  sum={fm_totals[fm]:,.2f}")

# ---------- 4) Print Americas May tie-out (8+4 vs Actuals, Total channel) ----------
def block(region):
    print(f"\n=== {region} — line items (Total channel) ===")
    print(f"{'Line item':45} | {'8+4 Final':>15} | {'Actuals':>15}")
    fc_ver  = next((v for v in versions if "8+4" in v), None)
    act_ver = next((v for v in versions if v.lower()=="actuals"), None)
    for it in items_order:
        fc  = matrix[region].get(fc_ver,{}).get("Total",{}).get(it)
        act = matrix[region].get(act_ver,{}).get("Total",{}).get(it)
        if fc is None and act is None:
            continue
        print(f"{it[:45]:45} | {('' if fc is None else f'{fc:,.2f}'):>15} | {('' if act is None else f'{act:,.2f}'):>15}")

for rg in regions:
    block(rg)

# ---------- 5) Save reference ----------
out = {
    "_source": XLSX,
    "_note": "May FY26 (FM12) tie-out targets extracted from Summary sheet. $ in thousands as stored in workbook.",
    "regions": regions, "versions": versions, "channels": channels,
    "items_order": items_order,
    "detail_fm_totals": {str(k): round(v,2) for k,v in fm_totals.items()},
    "matrix": matrix,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=lambda o: dict(o)))
print(f"\nSaved tie-out reference -> {OUT}")
wb.close()
