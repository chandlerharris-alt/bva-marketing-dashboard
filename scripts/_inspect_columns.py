"""Throwaway: inspect GLOBAL_COMBINED_GL columns + key dimensions to diagnose the
region-attribution + OPEX tie-out gaps. Run directly: python scripts/_inspect_columns.py"""
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
    warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "REPORTING_WAREHOUSE"), database="ANALYTICS",
)
cur = conn.cursor()

print("=== COLUMNS of ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL ===")
cur.execute("DESCRIBE TABLE ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL")
cols = [r[0] for r in cur.fetchall()]
for c in cols:
    print("  ", c)

# Any region / company / country style columns?
region_like = [c for c in cols if any(k in c.upper() for k in ("REGION","COMPANY","COUNTRY","ENTITY","CHANNEL"))]
print("\nRegion/company/country/channel-like columns:", region_like)

# Distinct CHANNEL values
print("\n=== DISTINCT CHANNEL ===")
cur.execute("SELECT DISTINCT CHANNEL FROM ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL WHERE FISCAL_YEAR=2026 ORDER BY 1")
print([r[0] for r in cur.fetchall()])

# For advertising account 6736000 in FY2026 FM12: rows by SOURCE_COMPANY vs REPORTING_COMPANY (if present)
have_rc = any(c.upper()=="REPORTING_COMPANY" for c in cols)
have_sc = any(c.upper()=="SOURCE_COMPANY" for c in cols)
print(f"\nHAS REPORTING_COMPANY={have_rc}  HAS SOURCE_COMPANY={have_sc}")
if have_rc and have_sc:
    cur.execute("""
        SELECT SOURCE_COMPANY, REPORTING_COMPANY, ROUND(SUM(PL_TOTAL),0) amt
        FROM ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL
        WHERE REPORTING_ACCOUNT='6736000' AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12
        GROUP BY 1,2 ORDER BY 3 DESC
    """)
    print("\n6736000 FY26 FM12 — SOURCE_COMPANY | REPORTING_COMPANY | $:")
    for r in cur.fetchall():
        print(f"   src={r[0]}  rpt={r[1]}  ${r[2]:,.0f}")

# Dept-75 OPEX May actual by category (to diagnose OPEX gap) — GL only
print("\n=== Dept-75 FY26 FM12 PL_TOTAL by CATEGORY (GL actual) ===")
cur.execute("""
    SELECT CATEGORY, ROUND(SUM(PL_TOTAL),0) amt, COUNT(*) n
    FROM ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL
    WHERE DEPT_NUMBER=75 AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND PL_TOTAL IS NOT NULL
    GROUP BY 1 ORDER BY 2 DESC
""")
for r in cur.fetchall():
    print(f"   {str(r[0]):28} ${r[1]:>14,.0f}  ({r[2]} rows)")

cur.close(); conn.close()
