"""
Extract June FY27 (FM1) tie-out targets from the Marketing Excel's
'Account by Region Summary' sheet, with full region x channel breakdown
(not just region rollups like the May FY26 tie-out did).

Writes data/_tieout_jun27.json — same schema as data/_tieout_may26.json,
consumed by scripts/validate_tieout_jun27_channels.py.

Usage:  python scripts/extract_excel_tieout_jun27.py
"""
import json, openpyxl, sys
from pathlib import Path
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

XLSX = r"G:\Shared drives\FP&A\Monthly Reporting\FY27\01 - June\Marketing\Total Marketing Spend Review_Jun26.xlsx"
OUT  = Path(__file__).resolve().parent.parent / "data" / "_tieout_jun27.json"

wb = openpyxl.load_workbook(XLSX, data_only=True, read_only=True)

ws = wb["Account by Region Summary"]
rows = list(ws.iter_rows(values_only=True))
def cell(r, c):
    return rows[r-1][c] if r-1 < len(rows) and c < len(rows[r-1]) else None

ncols = max(len(r) for r in rows)
region_row, version_row, channel_row = 2, 3, 4
col_map = {}
cur_region = cur_version = None
for c in range(ncols):
    rg = cell(region_row, c);  rg = str(rg).strip() if rg is not None else None
    vr = cell(version_row, c); vr = str(vr).strip() if vr is not None else None
    ch = cell(channel_row, c); ch = str(ch).strip() if ch is not None else None
    if rg: cur_region = rg
    if vr: cur_version = vr
    if ch:
        col_map[c] = (cur_region, cur_version, ch)

regions  = sorted({v[0] for v in col_map.values() if v[0]})
versions = sorted({v[1] for v in col_map.values() if v[1]})
channels = [c for c in dict.fromkeys(v[2] for v in col_map.values())]
print("Regions :", regions)
print("Versions:", versions)
print("Channels:", channels)

LABEL_COL, FULL_COL = 3, 0
matrix = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
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

out = {
    "_source": XLSX,
    "_note": "June FY27 (FM1) tie-out targets extracted from 'Account by Region Summary', full region x channel breakdown. $ in thousands as stored in workbook. NOTE: the sheet's version header for non-Americas regions reads 'FY26: 8+4 Final' but the underlying columns are positionally the Plan-vs-Actual-vs-Delta triad for this June FY27 report (label appears to be a stale carryover, not a different fiscal year of data) -- verify with Chandler if Plan-column comparisons look off.",
    "regions": regions, "versions": versions, "channels": channels,
    "items_order": items_order,
    "matrix": matrix,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=lambda o: dict(o)), encoding="utf-8")
print(f"\nSaved tie-out reference -> {OUT}")
wb.close()
