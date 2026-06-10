"""Throwaway: diagnose gross-revenue channel/region tagging in the GL for FY26 FM12.
Run: python scripts/_inspect_revenue.py"""
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

print("=== Revenue 4500% FY26 FM12 by raw CHANNEL (PL_TOTAL, $K) ===")
cur.execute(f"""
  SELECT COALESCE(CHANNEL,'(null)') ch, ROUND(SUM(PL_TOTAL)/1000,1) amt, COUNT(*) n
  FROM {GL} WHERE REPORTING_ACCOUNT LIKE '4500%' AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND PL_TOTAL IS NOT NULL
  GROUP BY 1 ORDER BY 2 DESC
""")
for r in cur.fetchall(): print(f"   {str(r[0]):14} {r[1]:>12,.1f}  ({r[2]} rows)")

print("\n=== Revenue 4500% FY26 FM12 by REGION (PL_TOTAL, $K) ===")
cur.execute(f"""
  SELECT COALESCE(REGION,'(null)') rg, ROUND(SUM(PL_TOTAL)/1000,1) amt
  FROM {GL} WHERE REPORTING_ACCOUNT LIKE '4500%' AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND PL_TOTAL IS NOT NULL
  GROUP BY 1 ORDER BY 2 DESC
""")
for r in cur.fetchall(): print(f"   {str(r[0]):12} {r[1]:>12,.1f}")

print("\n=== Compare account scopes, FY26 FM12 total revenue (PL_TOTAL, $K) ===")
for label, where in [("4500000 only","REPORTING_ACCOUNT='4500000'"),
                     ("4500% (all)","REPORTING_ACCOUNT LIKE '4500%'"),
                     ("FIN_STATEMENT Revenue","FIN_STATEMENT ILIKE '%revenue%'"),
                     ("CATEGORY Revenue","CATEGORY ILIKE 'revenue'")]:
    try:
        cur.execute(f"SELECT ROUND(SUM(PL_TOTAL)/1000,1) FROM {GL} WHERE {where} AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND PL_TOTAL IS NOT NULL")
        print(f"   {label:26} {cur.fetchone()[0]}")
    except Exception as e:
        print(f"   {label:26} ERR {e}")

print("\n=== Distinct FIN_STATEMENT values (FY26) ===")
cur.execute(f"SELECT DISTINCT FIN_STATEMENT FROM {GL} WHERE FISCAL_YEAR=2026 ORDER BY 1")
print("   ", [r[0] for r in cur.fetchall()])

print("\n  (Excel Gross Revenue: Americas Actual ~46,564 | ROW pieces sum ~ ; total all-region check)")
cur.close(); conn.close()
