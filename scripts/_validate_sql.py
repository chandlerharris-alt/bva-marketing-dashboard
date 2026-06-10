"""Offline sanity check: every SQL template formats cleanly with the params
refresh_dept.py builds. No Snowflake connection. Throwaway."""
import glob, os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

p = dict(
    depts_csv="75",
    dept_strs_csv="'075'",
    fy_min=2025,
    fy_max=2026,
    account_filter_clause="",
    ad_accounts_csv="'6736000','6740000'",
)

base = os.path.join(os.path.dirname(__file__), "..", "queries")
for f in sorted(glob.glob(os.path.join(base, "*.sql"))):
    sql = open(f, encoding="utf-8").read()
    name = os.path.basename(f)
    try:
        sql.format(**p)
        print("OK    ", name)
    except KeyError as e:
        print("NEEDS ", name, "-> missing param", e)
    except Exception as e:
        print("ERR   ", name, "->", type(e).__name__, e)
