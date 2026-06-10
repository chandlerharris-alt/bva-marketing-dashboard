"""Throwaway: diagnose the dept-75 OPEX gap. Tests (1) PL_TOTAL vs TOTAL and
(2) whether 'Marketing' spans more than GL dept 75. Run: python scripts/_inspect_opex.py"""
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
GL = "ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL"
ADV = "'6736000','6738000','6740000','6746000','6747000','6750000','6763000','6775000','6790000'"

print("=== (1) Dept 75 FY26 FM12: PL_TOTAL vs TOTAL, $K ===")
cur.execute(f"""
  SELECT ROUND(SUM(PL_TOTAL)/1000,1) pl, ROUND(SUM(TOTAL)/1000,1) tot,
         ROUND(SUM(CASE WHEN REPORTING_ACCOUNT NOT IN ({ADV}) THEN PL_TOTAL END)/1000,1) opex_pl,
         ROUND(SUM(CASE WHEN REPORTING_ACCOUNT NOT IN ({ADV}) THEN TOTAL END)/1000,1) opex_tot
  FROM {GL} WHERE DEPT_NUMBER=75 AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND PL_TOTAL IS NOT NULL
""")
r=cur.fetchone()
print(f"   ALL d75:  PL_TOTAL ${r[0]:,.1f}K | TOTAL ${r[1]:,.1f}K")
print(f"   OPEX d75: PL_TOTAL ${r[2]:,.1f}K | TOTAL ${r[3]:,.1f}K   (Excel Americas Total OPEX ~$2,544K)")

print("\n=== (2) FY26 FM12 depts with 'market' in the name (PL_TOTAL, $K) ===")
cur.execute(f"""
  SELECT DEPT_NUMBER, DEPT_NAME, ROUND(SUM(PL_TOTAL)/1000,1) pl
  FROM {GL} WHERE FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND PL_TOTAL IS NOT NULL
    AND DEPT_NAME ILIKE '%market%'
  GROUP BY 1,2 ORDER BY 3 DESC
""")
rows=cur.fetchall()
for x in rows: print(f"   dept {str(x[0]):>5}  {str(x[1])[:34]:34}  ${x[2]:,.1f}K")
print(f"   ({len(rows)} marketing-named depts)")

print("\n=== (2b) Dept 75 — DEPT_NAME values present (sanity) ===")
cur.execute(f"SELECT DISTINCT DEPT_NAME FROM {GL} WHERE DEPT_NUMBER=75 AND FISCAL_YEAR=2026")
print("   ", [r[0] for r in cur.fetchall()])

print("\n=== (3) Dept 75 OPEX (non-adv) FY26 FM12 by REPORTING_ACCOUNT — PL vs TOTAL top 20, $K ===")
cur.execute(f"""
  SELECT REPORTING_ACCOUNT, ANY_VALUE(ACCOUNT_NAME) nm,
         ROUND(SUM(PL_TOTAL)/1000,1) pl, ROUND(SUM(TOTAL)/1000,1) tot
  FROM {GL} WHERE DEPT_NUMBER=75 AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12
    AND REPORTING_ACCOUNT NOT IN ({ADV}) AND PL_TOTAL IS NOT NULL
  GROUP BY 1 ORDER BY ABS(SUM(PL_TOTAL)) DESC LIMIT 20
""")
print(f"   {'acct':9} {'name':28} {'PL_TOTAL':>10} {'TOTAL':>10}")
for x in cur.fetchall():
    print(f"   {str(x[0]):9} {str(x[1])[:28]:28} {x[2]:10,.1f} {x[3]:10,.1f}")

cur.close(); conn.close()
