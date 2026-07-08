# -*- coding: utf-8 -*-
# Parse the FY27 AOP "Global Revenue by Region & Channel" workbook into
# data/rev_aop_fy27.json — the Plan/AOP revenue the Media tab shows in its Plan column.
# Grid: channel x region x 12 fiscal months (FM1=Jun'26 .. FM12=May'27), USD.
import sys, json, openpyxl
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

X = r"G:\Shared drives\FP&A\Budgets & Forecasts\FY2027\AOP\Sales\Global Revenue by Region & Channel_FY27 AOP.xlsx"
ROOT = Path(__file__).resolve().parent.parent
CHANNELS = {'Wholesale','DTC','Freemotion','iFIT - Core','iFIT - App','Corp/Other'}

wb = openpyxl.load_workbook(X, data_only=True, read_only=True)
ws = wb['Sheet1']
byCR = {}
for row in ws.iter_rows(min_row=3, values_only=True):
    ch = row[1].strip() if isinstance(row[1], str) else None
    rg = row[2].strip() if isinstance(row[2], str) else None
    if not ch or not rg or ch not in CHANNELS:
        continue
    months = []
    for i in range(4, 16):   # cols 5..16 = FM1..FM12 (Jun'26..May'27)
        v = row[i] if i < len(row) else None
        months.append(round(float(v), 2) if isinstance(v, (int, float)) else 0.0)
    byCR.setdefault(ch, {})[rg] = months

out = {
    "_comment": "FY27 AOP revenue by channel x region, 12 fiscal months (FM1=Jun'26 .. FM12=May'27), USD. "
                "Source: Global Revenue by Region & Channel_FY27 AOP.xlsx. Used as the Plan/AOP revenue on the Media tab.",
    "fy": 2027,
    "byChannelRegion": byCR,
}
(ROOT / "data" / "rev_aop_fy27.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

# Summary
grand = 0.0
print("FY27 AOP revenue ($M) by channel:")
for ch in sorted(byCR):
    ct = sum(sum(m) for m in byCR[ch].values())
    grand += ct
    print(f"   {ch:14} {ct/1e6:>8,.1f}   regions: {sorted(byCR[ch].keys())}")
print(f"   {'TOTAL':14} {grand/1e6:>8,.1f}M")
