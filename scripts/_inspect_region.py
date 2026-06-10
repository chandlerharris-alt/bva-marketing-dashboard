"""Throwaway: test whether the native REGION column reproduces the Excel region split
for May FY26 (FM12). Run: python scripts/_inspect_region.py"""
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

print("=== DISTINCT REGION (FY26) ===")
cur.execute("SELECT DISTINCT REGION FROM ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL WHERE FISCAL_YEAR=2026 ORDER BY 1")
print([r[0] for r in cur.fetchall()])

ADV = "'6736000','6738000','6740000','6746000','6747000','6750000','6763000','6775000','6790000'"

print("\n=== May FY26 (FM12) by REGION — union scope (dept 75 OR advertising any dept), $K ===")
cur.execute(f"""
  SELECT REGION,
         ROUND(SUM(CASE WHEN REPORTING_ACCOUNT IN ({ADV}) THEN PL_TOTAL ELSE 0 END)/1000,1) AS advertising,
         ROUND(SUM(CASE WHEN DEPT_NUMBER=75 AND REPORTING_ACCOUNT NOT IN ({ADV}) THEN PL_TOTAL ELSE 0 END)/1000,1) AS opex_dept75,
         ROUND(SUM(PL_TOTAL)/1000,1) AS total
  FROM ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL
  WHERE (DEPT_NUMBER=75 OR REPORTING_ACCOUNT IN ({ADV}))
    AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND PL_TOTAL IS NOT NULL
  GROUP BY REGION ORDER BY total DESC
""")
print(f"{'REGION':16} | {'Advertising':>12} | {'OPEX(d75)':>12} | {'Total':>12}")
for r in cur.fetchall():
    print(f"{str(r[0]):16} | {r[1]:12,.1f} | {r[2]:12,.1f} | {r[3]:12,.1f}")

print("\n--- Excel targets (Actuals, $K) for comparison ---")
print("Americas : Adv 3850.3 | OPEX 2543.6 | Total 6394.0")
print("UK       : Adv  267.2 | OPEX  119.3 | Total  386.5")
print("EMEA     : Adv  240.5 | OPEX  167.8 | Total  408.3")
print("Australia: Adv  298.9 | OPEX   26.7 | Total  325.6")
print("China    : Adv   45.8 | OPEX   68.3 | Total  114.1")
print("ROW(sum) : Adv  852.4 | OPEX  382.2 | Total 1234.6")

cur.close(); conn.close()
