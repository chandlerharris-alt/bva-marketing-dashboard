import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from config.snowflake_creds import load_snowflake_creds
load_snowflake_creds()
import os, snowflake.connector
c = snowflake.connector.connect(user=os.environ["SNOWFLAKE_USER"], password=os.environ["SNOWFLAKE_PASSWORD"],
    account=os.environ["SNOWFLAKE_ACCOUNT"], warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE","REPORTING_WAREHOUSE"), database="ANALYTICS").cursor()
GL = "ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL"

print("=== 4500% iFIT-Core channel FY26 FM12 by ACCOUNT ($K) ===")
c.execute("SELECT REPORTING_ACCOUNT, ANY_VALUE(ACCOUNT_NAME), ROUND(SUM(PL_TOTAL)/1000,1), COUNT(*) FROM "+GL+
          " WHERE REPORTING_ACCOUNT LIKE '4500%' AND CHANNEL='iFIT - Core' AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND PL_TOTAL IS NOT NULL GROUP BY 1 ORDER BY 3")
for r in c.fetchall(): print(f"   {r[0]:9} {str(r[1])[:32]:32} {r[2]:>12,.1f} ({r[3]} rows)")

print("\n=== Top 4500% accounts overall FY26 FM12 ($K) ===")
c.execute("SELECT REPORTING_ACCOUNT, ANY_VALUE(ACCOUNT_NAME), ROUND(SUM(PL_TOTAL)/1000,1) FROM "+GL+
          " WHERE REPORTING_ACCOUNT LIKE '4500%' AND FISCAL_YEAR=2026 AND FISCAL_MONTH=12 AND PL_TOTAL IS NOT NULL GROUP BY 1 ORDER BY ABS(SUM(PL_TOTAL)) DESC LIMIT 14")
for r in c.fetchall(): print(f"   {r[0]:9} {str(r[1])[:32]:32} {r[2]:>12,.1f}")
