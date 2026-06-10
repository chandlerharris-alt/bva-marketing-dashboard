"""Throwaway: diagnose the 8+4 forecast in ADAPTIVE_PLANNING_GENERAL so we can make
the 8+4 tie to the Excel. Run: python scripts/_inspect_forecast.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from config.snowflake_creds import load_snowflake_creds
load_snowflake_creds()
import os, snowflake.connector
conn = snowflake.connector.connect(
    user=os.environ["SNOWFLAKE_USER"], password=os.environ["SNOWFLAKE_PASSWORD"],
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "REPORTING_WAREHOUSE"), database="ANALYTICS")
cur = conn.cursor()
T = "ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_PLANNING_GENERAL"
ADV = "'6736000','6738000','6740000','6746000','6747000','6750000','6763000','6775000','6790000'"
ACCT = "COALESCE(NULLIF(TRIM(GENERAL_LEDGER),''),EXPENSE_ACCOUNT)"

print("=== COLUMNS ===")
cur.execute(f"DESCRIBE TABLE {T}")
cols=[r[0] for r in cur.fetchall()]; print(cols)
print("region-like:", [c for c in cols if any(k in c.upper() for k in ('REGION','LEVEL','COMPANY','COUNTRY','CHANNEL'))])

print("\n=== VERSION_NAME like %8+4% ===")
cur.execute(f"SELECT DISTINCT VERSION_NAME FROM {T} WHERE VERSION_NAME ILIKE '%8+4%' ORDER BY 1")
vers=[r[0] for r in cur.fetchall()]; print(vers)
VER = next((v for v in vers if 'Final' in v), vers[0] if vers else '8+4')
print("Using version:", VER)

print(f"\n=== 8+4 ADVERTISING (all depts) FY2026 FM12 by LEVEL_CODE, $K ===")
cur.execute(f"""
  SELECT LEVEL_CODE, ROUND(SUM(AMOUNT)/1000,1) amt
  FROM {T}
  WHERE VERSION_NAME='{VER}' AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND {ACCT} IN ({ADV})
  GROUP BY 1 ORDER BY 2 DESC
""")
tot=0
for r in cur.fetchall(): print(f"   LEVEL_CODE={r[0]:>8}  ${r[1]:,.1f}"); tot+=r[1]
print(f"   ADVERTISING 8+4 FM12 TOTAL (all depts): ${tot:,.1f}K   (Excel Am+ROW = ~$4,892.5K)")

print(f"\n=== 8+4 DEPT-75 OPEX (non-adv) FY2026 FM12 total, $K ===")
cur.execute(f"""
  SELECT ROUND(SUM(AMOUNT)/1000,1)
  FROM {T}
  WHERE VERSION_NAME='{VER}' AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12
    AND DEPARTMENT IN ('075') AND {ACCT} NOT IN ({ADV})
""")
print(f"   DEPT-75 OPEX 8+4 FM12 TOTAL: ${cur.fetchone()[0]:,.1f}K   (Excel Am+ROW Total OPEX = ~$3,017.2K)")

print(f"\n=== DISTINCT LEVEL_CODE (8+4, FM12, marketing/adv scope) ===")
cur.execute(f"""
  SELECT DISTINCT LEVEL_CODE FROM {T}
  WHERE VERSION_NAME='{VER}' AND FISCAL_YEAR=2026
    AND (DEPARTMENT IN ('075') OR {ACCT} IN ({ADV})) ORDER BY 1
""")
print([r[0] for r in cur.fetchall()])

print(f"\n=== 8+4 union (dept75 OR adv) FY2026 FM12 — Advertising vs OPEX split, $K ===")
cur.execute(f"""
  SELECT ROUND(SUM(CASE WHEN {ACCT} IN ({ADV}) THEN AMOUNT ELSE 0 END)/1000,1) adv,
         ROUND(SUM(CASE WHEN DEPARTMENT IN ('075') AND {ACCT} NOT IN ({ADV}) THEN AMOUNT ELSE 0 END)/1000,1) opex,
         ROUND(SUM(AMOUNT)/1000,1) total
  FROM {T}
  WHERE VERSION_NAME='{VER}' AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12
    AND (DEPARTMENT IN ('075') OR {ACCT} IN ({ADV}))
""")
r=cur.fetchone()
print(f"   Adv ${r[0]:,.1f}K | OPEX ${r[1]:,.1f}K | TOTAL ${r[2]:,.1f}K   (Excel Total Marketing = ~$7,909.7K)")

cur.close(); conn.close()
