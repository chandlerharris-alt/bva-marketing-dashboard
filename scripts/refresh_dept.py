"""
Refresh BvA data for a single Logistics department.

Pulls actuals from GLOBAL_COMBINED_GL and forecasts from the four Adaptive tables,
shapes them into one nested JSON the dashboard consumes.

Usage:
    python scripts/refresh_dept.py --dept 10 --slug inbound-freight \
        --dept-name "Inbound Freight" --owner "Jeff Simper"

Output:
    data/{slug}.json
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sys as _sys; _sys.path.insert(0, r"C:\Users\devin.lindsay\Documents\Claude\Projects\AI Implementation\Automation")  # noqa: E702
from config.snowflake_creds import load_snowflake_creds
import snowflake.connector

ROOT = Path(__file__).resolve().parent.parent
QUERIES = ROOT / "queries"
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

load_snowflake_creds()

# Source-company → display name map (numeric per GL_COMBINED_GL).
SOURCE_COMPANY_MAP = {
    11: "US (11)", 14: "US – FM (14)", 71: "LATAM (71)", 74: "US – DTC (74)",
    86: "US (86)", 13: "iFIT Holdings (13)", 16: "iFIT Inc (16)",
    20: "Canada (20)", 70: "Canada DTC (70)",
    30: "Australia (30)", 32: "Australia (32)",
    33: "Mexico (33)", 168: "Mexico DTC (168)",
    40: "UK (40)", 41: "Europe (41)", 65: "China (65)",
    1711: "US – SAP (1711)", 2920: "US – SAP (2920)", 3032: "US – SAP (3032)", 5533: "US – SAP (5533)",
}

# Version allowlist — keeps only the "real" versions Devin actually compares to.
# Drops Board/Cerberus/MPF-Presentation/deprecated/intermediate cuts.
ALLOWED_VERSIONS = {
    # FY26 cuts
    "FY26: AOP Final",
    "FY26: 2+10",
    "FY26: 5+7",
    "FY26: 8+4 Final",
    # FY25 cuts (only present in SALARIES_WAGES and TRAVEL_ENTERTAINMENT)
    "FY25 AOP",
    "FY25: 2+10",
    "FY25: 4+8",
    "FY25: 7+5",
    "FY25: 10+2",
    # FY27
    "FY27 AOP v5.5.26",
    "Working Forecast",
    # EBITDA addbacks-only:
    "Proforma Adjustments",
    "Actuals",
    "Unadjusted Actuals",
    "Trial Balance Actuals",
}

# Category → reporting_account map (mirrors the Excel tabs' rollup).
# Pulled from `ifit-account-map` skill. Account codes are the **5-digit** stems
# stripped of the `C` suffix; we match on prefix.
CATEGORY_RULES = [
    ("Salaries & Wages",       lambda a: a.startswith(("8010", "7845", "8050", "7875", "8030", "8040", "9010", "8020"))),
    ("Commissions",            lambda a: a.startswith(("8081", "8082", "8083"))),
    ("Advertising",            lambda a: a.startswith(("6082", "671", "672", "6736", "6737", "6739", "674"))),
    ("Contract Labor",         lambda a: a.startswith(("7800", "7871", "7889", "7890", "8925"))),
    ("Freight",                lambda a: a.startswith(("6603", "6712", "6752", "6755"))),
    ("Content",                lambda a: a.startswith(("795", "796"))),
    ("Rent & Leases",          lambda a: a.startswith(("8930", "8931", "8932", "8933", "8934", "8935", "8937", "8938"))),
    ("Software",               lambda a: a.startswith("7865")),
    ("Travel",                 lambda a: a.startswith(("7895", "8500", "8955"))),
    ("Payment Processing Fees",lambda a: a.startswith("8920")),
    ("Warehousing",            lambda a: a.startswith(("8970", "8104", "8107", "6104", "6105", "6106", "9655", "9675"))),
    ("Professional Services",  lambda a: a.startswith(("7800", "7871", "7889", "7890"))),
    ("Utilities",              lambda a: a.startswith("8965")),
    ("Supplies",               lambda a: a.startswith("8950")),
    ("Repair & Maintenance",   lambda a: a.startswith(("6715", "8940"))),
    ("Tradeshows",             lambda a: a.startswith("7920")),
    ("Telecom",                lambda a: a.startswith(("8915", "8965"))),
    ("Depreciation & Amort",   lambda a: a.startswith(("7751", "7754", "7757", "7830", "7831"))),
    ("Bad Debt",               lambda a: a.startswith("7860")),
    ("Insurance",              lambda a: a.startswith(("7876", "7877", "7878"))),
    ("Warranty (OPEX)",        lambda a: a.startswith(("5715", "5536", "5678"))),
    ("COGS",                   lambda a: a.startswith(("5051", "5071", "5500", "5535", "5540", "5542", "5543", "5544", "5545", "5546", "5560", "5996", "5999"))),
    ("Revenue",                lambda a: a.startswith(("4500", "4600", "4700"))),
    ("Other Expenses",         lambda a: a.startswith(("7905", "7906", "8941", "8953"))),
]

# Standardized P&L category order for the BvA grid.
# Matches the Total Ops Financials_Mar26.xlsx Accounts tab OPEX hierarchy
# (R1217-1648). All rows render even when zero — they're the canonical P&L
# line items, not data-driven.
# Applies to every section EXCEPT Outbound Freight (which keeps its custom layout).
STANDARD_CATEGORY_ORDER = [
    "Salaries & Wages",
    "Commissions",
    "Advertising",
    "Freight",
    "Contract Labor",
    "Content",
    "Rent & Leases",
    "Professional Services",
    "Software",
    "Travel",
    "Payment Processing Fees",
    "Warehousing",
    "Utilities",
    "Supplies",
    "Repair & Maintenance",
    "Tradeshows",
    "Telecom",
    "Warranty (OPEX)",
    "Depreciation & Amort",
    "Bad Debt",
    "Other Expenses",
]

# Authoritative account-to-category map built from Total Ops Financials_Mar26.xlsx
# "Accounts" tab. 855 leaf accounts. Loaded once at module import time. Falls back
# to prefix-rule categorization for accounts not in the map (e.g., legacy / unmapped).
_ACCT_CAT_MAP: dict[str, str] = {}
_ACCT_NAMES: dict[str, str] = {}
try:
    import json as _json
    _map_path = Path(__file__).resolve().parent / "account_category_map.json"
    if _map_path.exists():
        _data = _json.loads(_map_path.read_text(encoding="utf-8"))
        _ACCT_CAT_MAP = _data.get("category_map") or {}
        _ACCT_NAMES = _data.get("account_names") or {}
        print(f"[init] loaded {len(_ACCT_CAT_MAP):,} accounts from account_category_map.json")
except Exception as _e:
    print(f"[init] account_category_map.json load failed: {_e}")

def categorize_account(reporting_account: str | None) -> str:
    if not reporting_account:
        return "Other Expenses"
    a = reporting_account.strip().upper().lstrip("0")
    a_num = "".join(ch for ch in a if ch.isdigit())
    # 1) Authoritative map (Excel Accounts tab)
    if a_num in _ACCT_CAT_MAP:
        return _ACCT_CAT_MAP[a_num]
    # 2) Prefix-rule fallback for accounts not in the map (older accounts, etc.)
    for name, fn in CATEGORY_RULES:
        if fn(a_num):
            return name
    return "Other Expenses"

def load_sql(name: str) -> str:
    return (QUERIES / name).read_text()

def connect():
    return snowflake.connector.connect(
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "REPORTING_WAREHOUSE"),
        database="ANALYTICS",
    )

def fetch(cur, sql: str, label: str) -> list[dict]:
    from decimal import Decimal
    print(f"  {label} ... ", end="", flush=True)
    cur.execute(sql)
    cols = [c[0].lower() for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    # Normalize Decimals → float (do NOT touch strings)
    for r in rows:
        for k, v in r.items():
            if isinstance(v, Decimal):
                r[k] = float(v)
    print(f"{len(rows):,} rows")
    return rows

def pick_version(table_versions: list[str], prefs: list[str]) -> str | None:
    for p in prefs:
        if p in table_versions:
            return p
    return None

def build_company_totals(accounts: dict, breakdown: str) -> list[dict]:
    """Aggregate actuals_by_company across all accounts into per-company totals.

    Only populated when breakdown == 'company'.  Forecasts are left empty because
    Adaptive forecast rows carry a LEVEL_CODE (entity) that is not reliably
    present in all forecast tables; the standard account-level BvA table above
    still shows correct total forecasts.
    """
    if breakdown != "company":
        return []

    # {co_int: {fy: [12]}}
    co_actuals: dict[int, dict[int, list[float]]] = {}
    for rec in accounts.values():
        for fy_str, co_map in rec["actuals_by_company"].items():
            fy = int(fy_str)
            for co, arr in co_map.items():
                co_int = int(co)
                co_actuals.setdefault(co_int, {}).setdefault(fy, [0.0]*12)
                for i in range(12):
                    co_actuals[co_int][fy][i] += arr[i] if i < len(arr) else 0.0

    result = []
    for co_int, fy_map in sorted(co_actuals.items()):
        name = SOURCE_COMPANY_MAP.get(co_int, f"Co {co_int}")
        result.append({
            "company": co_int,
            "name": name,
            "actuals": {str(fy): arr for fy, arr in fy_map.items()},
            "forecasts": {},   # intentionally blank — see docstring
        })
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depts", required=True,
                    help="Comma-separated dept numbers (e.g. '10' for inbound, '9,26,55' for OBF+Reverse)")
    ap.add_argument("--slug", required=True, help="File slug, e.g. inbound-freight")
    ap.add_argument("--dept-name", required=True)
    ap.add_argument("--owner", required=True)
    ap.add_argument("--fy-min", type=int, default=2024)
    ap.add_argument("--fy-max", type=int, default=2027)
    ap.add_argument("--account-prefix", default="",
                    help="Comma-separated REPORTING_ACCOUNT prefixes (LIKE) to filter actuals to. e.g. '6755' for outbound freight only.")
    ap.add_argument("--exclude-accounts", default="",
                    help="Comma-separated exact REPORTING_ACCOUNT values to exclude (e.g. revenue freight/subscription carve-outs).")
    ap.add_argument("--drill-prefix", default="",
                    help="Override account prefix for the drill query (narrower than --account-prefix). "
                         "Useful when --account-prefix is broad (e.g. '6755,4500') but drill only needed for freight ('6755').")
    ap.add_argument("--load-outbound-freight-summary", action="store_true",
                    help="Also load ADAPTIVE_OUTBOUND_FREIGHT_SUMMARY forecast (channel-aware).")
    ap.add_argument("--load-revenue-forecast", action="store_true",
                    help="Also load RPT_FORECAST_DETAIL revenue forecast (channel + region aware).")
    ap.add_argument("--breakdown", default="dept",
                    help="Rollup card type: 'dept' (default) or 'company'.")
    ap.add_argument("--actuals-sql", default="actuals_by_dept.sql",
                    help="SQL template for actuals. Default 'actuals_by_dept.sql'. "
                         "Marketing uses 'actuals_marketing.sql' for the dept-75-OR-advertising union scope.")
    ap.add_argument("--drill-sql", default="actuals_drill_by_dept.sql",
                    help="SQL template for the vendor/invoice drill. Default 'actuals_drill_by_dept.sql'. "
                         "Marketing uses 'actuals_drill_marketing.sql'.")
    ap.add_argument("--advertising-accounts", default="",
                    help="Comma-separated exact REPORTING_ACCOUNTs treated as 'advertising in any dept' for the "
                         "union-scope marketing queries (e.g. '6736000,6740000,...'). Empty = dept-only scope.")
    ap.add_argument("--planning-sql", default="forecast_planning_general.sql",
                    help="SQL template for the ADAPTIVE_PLANNING_GENERAL forecast. Default "
                         "'forecast_planning_general.sql'. Marketing uses 'forecast_planning_general_marketing.sql' "
                         "so advertising FORECAST from any dept is captured (matches the 8+4 in the Excel).")
    args = ap.parse_args()

    dept_nums = [int(d.strip()) for d in args.depts.split(",") if d.strip()]
    dept_strs = [f"{d:03d}" for d in dept_nums]
    depts_csv = ",".join(str(d) for d in dept_nums)
    dept_strs_csv = ",".join(f"'{s}'" for s in dept_strs)

    print(f"\n=== Refresh '{args.slug}' ({args.dept_name}) — depts {dept_strs} ===")

    conn = connect()
    cur = conn.cursor()

    # Build optional account-prefix WHERE clause + Python-side filter
    prefixes = [p.strip() for p in args.account_prefix.split(",") if p.strip()] if args.account_prefix else []
    excludes = [e.strip() for e in args.exclude_accounts.split(",") if e.strip()] if args.exclude_accounts else []
    if prefixes:
        likes = " OR ".join([f"REPORTING_ACCOUNT LIKE '{px}%'" for px in prefixes])
        account_filter_clause = f"AND ({likes})"
    else:
        account_filter_clause = ""
    if excludes:
        excl_csv = ",".join(f"'{e}'" for e in excludes)
        account_filter_clause += f" AND REPORTING_ACCOUNT NOT IN ({excl_csv})"

    def matches_prefix(ra: str) -> bool:
        if not prefixes: return True
        if not ra: return False
        if ra in excludes: return False
        return any(ra.startswith(px) for px in prefixes)

    # Drill query may use a narrower account filter to avoid huge result sets
    # (e.g., when account_prefix includes 4500* for revenue, drill only needs 6755*).
    drill_prefixes = [p.strip() for p in args.drill_prefix.split(",") if p.strip()] if args.drill_prefix else prefixes
    if drill_prefixes:
        drill_likes = " OR ".join([f"REPORTING_ACCOUNT LIKE '{px}%'" for px in drill_prefixes])
        drill_account_filter_clause = f"AND ({drill_likes})"
        if excludes:
            drill_account_filter_clause += f" AND REPORTING_ACCOUNT NOT IN ({excl_csv})"
    else:
        drill_account_filter_clause = account_filter_clause

    # Advertising-account union list (Option 1). Quoted CSV for the {ad_accounts_csv}
    # placeholder used by actuals_marketing.sql / actuals_drill_marketing.sql.
    # '__none__' is a safe sentinel that matches no REPORTING_ACCOUNT, so the union
    # query degenerates to dept-only scope when no advertising list is supplied.
    ad_accts = [a.strip() for a in args.advertising_accounts.split(",") if a.strip()]
    ad_accounts_csv = ",".join(f"'{a}'" for a in ad_accts) if ad_accts else "'__none__'"
    if ad_accts:
        print(f"  advertising union accounts: {ad_accts}")

    p = dict(depts_csv=depts_csv, dept_strs_csv=dept_strs_csv,
             fy_min=args.fy_min, fy_max=args.fy_max,
             account_filter_clause=account_filter_clause,
             ad_accounts_csv=ad_accounts_csv)
    p_drill = dict(p, account_filter_clause=drill_account_filter_clause)

    # FX rates — pull once, applies to every tab
    print("  fx_rates ... ", end="", flush=True)
    cur.execute("""
        SELECT CAST(COMPANY AS INTEGER) AS company,
               CAST(FISCAL_YEAR AS INTEGER) AS fy,
               CAST(FISCAL_MONTH AS INTEGER) AS fm,
               CAST(RATE AS FLOAT) AS rate
        FROM ANALYTICS.ANALYTICS_GL_ANALYTICS_MART.ADAPTIVE_EXCHANGE_RATES
    """)
    fx_raw = cur.fetchall()
    print(f"{len(fx_raw):,} rows")
    fx_rates: dict[str, dict[str, list]] = {}
    for co, fy, fm, rate in fx_raw:
        if co is None or fy is None or fm is None:
            continue
        fx_rates.setdefault(str(co), {}).setdefault(str(fy), [1.0]*12)[fm-1] = float(rate or 1.0)

    actuals = fetch(cur, load_sql(args.actuals_sql).format(**p), "actuals (GL)")
    drill   = fetch(cur, load_sql(args.drill_sql).format(**p_drill), "actuals drill")
    pg      = fetch(cur, load_sql(args.planning_sql).format(**p), "PLANNING_GENERAL")
    cl      = fetch(cur, load_sql("forecast_contract_labor.sql").format(**p), "CONTRACT_LABOR")
    ts      = fetch(cur, load_sql("forecast_topside_adjustments.sql").format(**p), "TOPSIDE_ADJUSTMENTS")
    eb      = fetch(cur, load_sql("forecast_ebitda_addbacks.sql").format(**p), "EBITDA_ADDBACKS")
    sw      = fetch(cur, load_sql("forecast_salaries_wages.sql").format(**p), "SALARIES_WAGES")
    te      = fetch(cur, load_sql("forecast_travel_entertainment.sql").format(**p), "TRAVEL_ENTERTAINMENT")
    ofs     = fetch(cur, load_sql("forecast_outbound_freight_summary.sql").format(**p), "OUTBOUND_FREIGHT_SUMMARY") if args.load_outbound_freight_summary else []

    # RPT_FORECAST_DETAIL revenue forecast — scoped only to fiscal years in range
    rft_rows: list[dict] = []
    if args.load_revenue_forecast:
        rft_sql = load_sql("forecast_revenue_rpt.sql").format(fy_min=args.fy_min, fy_max=args.fy_max)
        rft_rows = fetch(cur, rft_sql, "RPT_FORECAST_DETAIL (revenue)")
        # Print discovered versions so caller can review mapping
        rft_versions = sorted({r["version"] for r in rft_rows if r.get("version")})
        print(f"  RPT versions discovered: {rft_versions}")

    cur.close()
    conn.close()

    # ---------- Index actuals into nested structure ----------
    accounts: dict[tuple[str, str], dict] = {}
    # Dept-level rollup: {dept_str: {"name": ..., "actuals": {fy: [12]}, "forecasts": {version_key: [12]}}}
    dept_totals: dict[str, dict] = {}

    def empty_monthly():
        return [0.0] * 12

    def pad_dept(ds):
        """Normalize dept value to zero-padded 3-char string, or None if unparseable."""
        if ds is None: return None
        s = str(ds).strip()
        if not s: return None
        try:
            return f"{int(float(s)):03d}"
        except (ValueError, TypeError):
            return s if s else None

    def update_acct_forecast(rec, v_key, fm, amt, ds, lc=None):
        """Update rec.forecasts, rec.forecasts_by_dept, and rec.forecasts_by_company
        for a single forecast row. `lc` is the LEVEL_CODE (string) → company code.
        Both dept and company breakdowns are needed for sub-section FX conversion."""
        rec["forecasts"].setdefault(v_key, empty_monthly())[fm - 1] += amt
        if ds:
            rec.setdefault("forecasts_by_dept", {}).setdefault(v_key, {}).setdefault(ds, empty_monthly())[fm - 1] += amt
        if lc:
            # LEVEL_CODE → company. Normalise to int-string (handles "11", "20", "11.0", etc.)
            try:
                co_str = str(int(float(str(lc).strip())))
            except (ValueError, TypeError):
                co_str = str(lc).strip()
            if co_str:
                rec.setdefault("forecasts_by_company", {}).setdefault(v_key, {}).setdefault(co_str, empty_monthly())[fm - 1] += amt

    def dept_rec(dept_str, dept_name=None):
        rec = dept_totals.setdefault(dept_str, {
            "dept_str": dept_str, "name": dept_name or dept_str,
            "actuals": {}, "actuals_by_company": {},
            "actuals_by_channel": {},   # {fy: {channel: [12]}}
            "forecasts": {},
            "forecasts_by_company": {}, # {v_key: {co_int: [12]}} — LEVEL_CODE → company
        })
        if dept_name and rec["name"] == dept_str:
            rec["name"] = dept_name
        return rec

    for r in actuals:
        ra = (r.get("reporting_account") or "").strip()
        an = (r.get("account_name") or "").strip()
        if not ra:
            continue
        # Use RA as the dedup key. ACCOUNT_NAME varies across GL rows for the same
        # account; collapse them into a single record. Keep the first non-empty name.
        existing = next((k for k in accounts if k[0] == ra), None)
        key = existing or (ra, an or ra)
        rec = accounts.setdefault(key, {
            "reporting_account": ra,
            "account_name": an,
            "category": categorize_account(ra),
            "gl_type": r.get("gl_type"),
            "actuals": {},
            "actuals_by_company": {},
            "actuals_by_channel": {},        # {fy: {channel: [12]}}
            "actuals_by_channel_company": {}, # {fy: {channel: {co: [12]}}}
            "actuals_by_dept": {},           # {fy: {dept_str: [12]}}
            "forecasts": {},
            "forecast_lines": [],
        })
        # Promote a non-empty name if we previously stored an empty one
        if an and not rec["account_name"]:
            rec["account_name"] = an
        fy = int(r["fiscal_year"])
        fm = int(r["fiscal_month"])
        sc = r.get("source_company")
        amt = r.get("amount") or 0.0
        rec["actuals"].setdefault(fy, empty_monthly())[fm - 1] += amt
        co_map = rec["actuals_by_company"].setdefault(fy, {})
        co_arr = co_map.setdefault(int(sc) if sc is not None else 0, empty_monthly())
        co_arr[fm - 1] += amt

        # Channel — keep raw value (DTC, WHSL, FM, Corp/Other, etc.)
        ch = (r.get("channel") or "Unknown").strip() or "Unknown"
        ch_map = rec["actuals_by_channel"].setdefault(fy, {})
        ch_arr = ch_map.setdefault(ch, empty_monthly())
        ch_arr[fm - 1] += amt
        # Joint: channel × company (for the channel-region matrix)
        co_int = int(sc) if sc is not None else 0
        chc_map = rec["actuals_by_channel_company"].setdefault(fy, {}).setdefault(ch, {})
        chc_arr = chc_map.setdefault(co_int, empty_monthly())
        chc_arr[fm - 1] += amt

        # Dept-level rollup
        dn = r.get("dept_number")
        if dn is not None:
            dstr = f"{int(dn):03d}"
            d = dept_rec(dstr, r.get("dept_name"))
            d["actuals"].setdefault(fy, empty_monthly())[fm - 1] += amt
            co_int = int(sc) if sc is not None else 0
            d["actuals_by_company"].setdefault(fy, {}).setdefault(co_int, empty_monthly())[fm - 1] += amt
            d["actuals_by_channel"].setdefault(fy, {}).setdefault(ch, empty_monthly())[fm - 1] += amt
            # Also stash dept breakdown on the account record for sub-section filtering
            rec["actuals_by_dept"].setdefault(fy, {}).setdefault(dstr, empty_monthly())[fm - 1] += amt

    # ---------- Forecasts (Planning General) ----------
    def attach_dept_forecast(r, source_label):
        ds = (r.get("dept_str") or "").strip() or None
        if not ds: return
        # If an account-prefix filter is in effect, skip forecast lines that don't
        # match any of the configured prefixes — keeps dept rollup scoped correctly.
        if prefixes:
            ra = (r.get("reporting_account") or "").strip()
            if not matches_prefix(ra): return
        d = dept_rec(ds)
        fy = int(r["fiscal_year"]); fm = int(r["fiscal_month"])
        ver = r["version_name"]; amt = r.get("amount") or 0.0
        v_key = f"{ver} | FY{fy}"
        d["forecasts"].setdefault(v_key, empty_monthly())[fm - 1] += amt
        # LEVEL_CODE → company. Adaptive stores entity as the company code string.
        lc = (r.get("level_code") or "").strip()
        try:
            co_int = int(float(lc)) if lc else 0
        except (ValueError, TypeError):
            co_int = 0
        d["forecasts_by_company"].setdefault(v_key, {}).setdefault(co_int, empty_monthly())[fm - 1] += amt

    for r in [x for x in pg if x.get("version_name") in ALLOWED_VERSIONS and (x.get("reporting_account") or "").strip() not in excludes]:
        ra = (r.get("reporting_account") or "").strip()
        an = ""  # not in PG; key on RA only and we'll match on existing entry's name
        # Try to find the matching account by RA alone — first match wins
        match_key = None
        for k in accounts:
            if k[0] == ra:
                match_key = k; break
        if not match_key:
            match_key = (ra, ra)
            accounts[match_key] = {
                "reporting_account": ra, "account_name": ra,
                "category": categorize_account(ra), "gl_type": None,
                "actuals": {}, "actuals_by_company": {},
                "forecasts": {}, "forecast_lines": [],
            }
        rec = accounts[match_key]
        fy = int(r["fiscal_year"]); fm = int(r["fiscal_month"])
        ver = r["version_name"]; amt = r.get("amount") or 0.0
        v_key = f"{ver} | FY{fy}"
        ds = pad_dept(r.get("dept_str"))
        update_acct_forecast(rec, v_key, fm, amt, ds, r.get('level_code'))
        # capture line items for vendor/description match
        rec["forecast_lines"].append({
            "version": ver, "fy": fy, "fm": fm, "level_code": r.get("level_code"),
            "dept_str": ds,
            "description": r.get("description"), "vendor": r.get("vendor"),
            "channel": r.get("channel"), "expense_type": r.get("expense_type"),
            "amount": amt, "source": "PLANNING_GENERAL",
        })
        attach_dept_forecast(r, "PG")

    # Contract labor — same approach but tag source
    for r in [x for x in cl if x.get("version_name") in ALLOWED_VERSIONS and (x.get("reporting_account") or "").strip() not in excludes]:
        ra = (r.get("reporting_account") or "").strip()
        match_key = next((k for k in accounts if k[0] == ra), None) or (ra, ra)
        if match_key not in accounts:
            accounts[match_key] = {
                "reporting_account": ra, "account_name": ra,
                "category": "Contract Labor", "gl_type": None,
                "actuals": {}, "actuals_by_company": {},
                "forecasts": {}, "forecast_lines": [],
            }
        rec = accounts[match_key]
        fy = int(r["fiscal_year"]); fm = int(r["fiscal_month"])
        ver = r["version_name"]; amt = r.get("amount") or 0.0
        v_key = f"{ver} | FY{fy}"
        ds = pad_dept(r.get("dept_str"))
        update_acct_forecast(rec, v_key, fm, amt, ds, r.get('level_code'))
        rec["forecast_lines"].append({
            "version": ver, "fy": fy, "fm": fm, "level_code": r.get("level_code"),
            "dept_str": ds,
            "description": r.get("contractor_name") or r.get("purpose"),
            "vendor": r.get("vendor"), "amount": amt, "source": "CONTRACT_LABOR",
        })
        attach_dept_forecast(r, "CL")

    # Salaries & Wages — feeds the missing payroll forecast
    for r in [x for x in sw if x.get("version_name") in ALLOWED_VERSIONS and (x.get("reporting_account") or "").strip() not in excludes]:
        ra = (r.get("reporting_account") or "").strip()
        an = (r.get("account_name") or "").strip()
        match_key = next((k for k in accounts if k[0] == ra), None) or (ra, an or ra)
        if match_key not in accounts:
            accounts[match_key] = {
                "reporting_account": ra, "account_name": an or ra,
                "category": categorize_account(ra), "gl_type": None,
                "actuals": {}, "actuals_by_company": {},
                "forecasts": {}, "forecast_lines": [],
            }
        rec = accounts[match_key]
        fy = int(r["fiscal_year"]); fm = int(r["fiscal_month"])
        ver = r["version_name"]; amt = r.get("amount") or 0.0
        v_key = f"{ver} | FY{fy}"
        ds = pad_dept(r.get("dept_str"))
        update_acct_forecast(rec, v_key, fm, amt, ds, r.get('level_code'))
        rec["forecast_lines"].append({
            "version": ver, "fy": fy, "fm": fm, "level_code": r.get("level_code"),
            "dept_str": ds,
            "description": an or ra, "vendor": None, "amount": amt, "source": "SALARIES_WAGES",
        })
        attach_dept_forecast(r, "SW")

    # Travel & Entertainment forecast
    for r in [x for x in te if x.get("version_name") in ALLOWED_VERSIONS and (x.get("reporting_account") or "").strip() not in excludes]:
        ra = (r.get("reporting_account") or "").strip()
        an = (r.get("account_name") or "").strip()
        match_key = next((k for k in accounts if k[0] == ra), None) or (ra, an or ra)
        if match_key not in accounts:
            accounts[match_key] = {
                "reporting_account": ra, "account_name": an or ra,
                "category": categorize_account(ra), "gl_type": None,
                "actuals": {}, "actuals_by_company": {},
                "forecasts": {}, "forecast_lines": [],
            }
        rec = accounts[match_key]
        fy = int(r["fiscal_year"]); fm = int(r["fiscal_month"])
        ver = r["version_name"]; amt = r.get("amount") or 0.0
        v_key = f"{ver} | FY{fy}"
        ds = pad_dept(r.get("dept_str"))
        update_acct_forecast(rec, v_key, fm, amt, ds, r.get('level_code'))
        rec["forecast_lines"].append({
            "version": ver, "fy": fy, "fm": fm, "level_code": r.get("level_code"),
            "dept_str": ds,
            "description": an or ra, "vendor": None, "amount": amt, "source": "TRAVEL_ENT",
        })
        attach_dept_forecast(r, "TE")

    # Outbound Freight Summary — channel-aware forecast for the freight tab
    for r in [x for x in ofs if x.get("version_name") in ALLOWED_VERSIONS and (x.get("reporting_account") or "").strip() not in excludes]:
        ra = (r.get("reporting_account") or "").strip()
        an = (r.get("account_name") or "").strip()
        match_key = next((k for k in accounts if k[0] == ra), None) or (ra, an or ra)
        if match_key not in accounts:
            accounts[match_key] = {
                "reporting_account": ra, "account_name": an or ra,
                "category": categorize_account(ra), "gl_type": None,
                "actuals": {}, "actuals_by_company": {},
                "actuals_by_channel": {}, "actuals_by_channel_company": {},
                "forecasts": {}, "forecast_lines": [],
            }
        rec = accounts[match_key]
        fy = int(r["fiscal_year"]); fm = int(r["fiscal_month"])
        ver = r["version_name"]; amt = r.get("amount") or 0.0
        v_key = f"{ver} | FY{fy}"
        ds = pad_dept(r.get("dept_str"))
        update_acct_forecast(rec, v_key, fm, amt, ds, r.get('level_code'))
        rec["forecast_lines"].append({
            "version": ver, "fy": fy, "fm": fm, "level_code": r.get("level_code"),
            "dept_str": ds, "channel": r.get("channel"),
            "description": an or ra, "vendor": None, "amount": amt, "source": "OUTBOUND_FREIGHT_SUMMARY",
        })
        attach_dept_forecast(r, "OFS")

    # ---------- RPT_FORECAST_DETAIL revenue forecast ----------
    # RPT VERSION strings use shorthand: 'AOP', '8+4', '5+7', '2+10', '4+8', '7+5'.
    # We normalise them to ALLOWED_VERSIONS by adding 'FY{fy_short}: ' prefix and
    # expanding 'AOP' → 'AOP Final' and 'N+M' → 'N+M Final' where ALLOWED_VERSIONS
    # uses the '... Final' form.
    RPT_VERSION_NORM = {
        "AOP":   "AOP Final",
        "8+4":   "8+4 Final",
        "5+7":   "5+7",
        "2+10":  "2+10",
        "4+8":   "4+8",
        "7+5":   "7+5",
    }
    # RPT CHANNEL → dashboard channel key
    RPT_CHANNEL_NORM = {
        "DTC":          "DTC",
        "Wholesale":    "WHSL",
        "WHOLESALE":    "WHSL",
        "Freemotion":   "FM",
        "FREEMOTION":   "FM",
        "Commercial":   "FM",
        "COMMERCIAL":   "FM",
    }
    # RPT REGION → dashboard region key (REGION_ORDER values)
    RPT_REGION_NORM = {
        "USA":           "US",
        "US/CANADA":     "US",    # combined bucket — assign to US
        "US":            "US",
        "Canada":        "Canada",
        "CANADA":        "Canada",
        "Australia":     "Australia",
        "AUSTRALIA":     "Australia",
        "Latin America": "LATAM",
        "LATAM":         "LATAM",
        "Mexico":        "Mexico",
        "MEXICO":        "Mexico",
        "UK":            "UK",
        "France":        "Europe",
        "FRANCE":        "Europe",
        "Europe":        "Europe",
        "EUROPE":        "Europe",
        "China":         "China",
        "CHINA":         "China",
        "DIRECT SHIP":   "US",    # DTC forward-stock US
        "Dealer":        "US",    # US dealer channel
        "OTF":           "US",    # over-the-forecast — treat as US
        "GLOBAL":        "US",    # global allocation → default US
    }

    REV_ACCOUNT = "4500000"
    rpt_skipped_versions: set[str] = set()
    for r in rft_rows:
        raw_ver = (r.get("version") or "").strip()
        fy = int(r["fiscal_year"])
        fy_short = fy - 2000
        # Normalise version
        normalised = RPT_VERSION_NORM.get(raw_ver)
        if not normalised:
            rpt_skipped_versions.add(raw_ver)
            continue
        ver = f"FY{fy_short}: {normalised}"
        if ver not in ALLOWED_VERSIONS:
            # e.g. FY25: 4+8 — valid normalisation but not in allowed set yet
            rpt_skipped_versions.add(f"{raw_ver} ({ver})")
            continue
        fm = int(r["fiscal_month"])
        amt = float(r.get("amount_usd") or 0.0)
        raw_ch = (r.get("channel") or "").strip()
        raw_reg = (r.get("region") or "").strip()
        channel = RPT_CHANNEL_NORM.get(raw_ch, raw_ch)
        region = RPT_REGION_NORM.get(raw_reg, raw_reg)
        co = int(r.get("source_company") or 0)

        # Find or create the 4500000 account record
        match_key = next((k for k in accounts if k[0] == REV_ACCOUNT), None) or (REV_ACCOUNT, REV_ACCOUNT)
        if match_key not in accounts:
            accounts[match_key] = {
                "reporting_account": REV_ACCOUNT,
                "account_name": "Equipment Gross Sales",
                "category": "Revenue", "gl_type": None,
                "actuals": {}, "actuals_by_company": {},
                "actuals_by_channel": {}, "actuals_by_channel_company": {},
                "forecasts": {}, "forecast_lines": [],
            }
        rec = accounts[match_key]
        v_key = f"{ver} | FY{fy}"
        rec["forecasts"].setdefault(v_key, empty_monthly())[fm - 1] += amt
        rec["forecast_lines"].append({
            "version": ver, "fy": fy, "fm": fm,
            "channel": channel, "source_company": co, "region": region,
            "description": "RPT_FORECAST_DETAIL", "source": "RPT_FORECAST_DETAIL",
            "amount": amt,
        })
    if rpt_skipped_versions:
        print(f"  RPT versions skipped (not in ALLOWED_VERSIONS): {sorted(rpt_skipped_versions)}")

    # Topside adjustments
    for r in [x for x in ts if x.get("version_name") in ALLOWED_VERSIONS and (x.get("reporting_account") or "").strip() not in excludes]:
        ra = (r.get("reporting_account") or "").strip()
        match_key = next((k for k in accounts if k[0] == ra), None) or (ra, ra)
        if match_key not in accounts:
            accounts[match_key] = {
                "reporting_account": ra, "account_name": ra,
                "category": categorize_account(ra), "gl_type": None,
                "actuals": {}, "actuals_by_company": {},
                "forecasts": {}, "forecast_lines": [],
            }
        rec = accounts[match_key]
        fy = int(r["fiscal_year"]); fm = int(r["fiscal_month"])
        ver = r["version_name"]; amt = r.get("amount") or 0.0
        v_key = f"{ver} | FY{fy}"
        ds = pad_dept(r.get("dept_str"))
        update_acct_forecast(rec, v_key, fm, amt, ds, r.get('level_code'))
        rec["forecast_lines"].append({
            "version": ver, "fy": fy, "fm": fm, "level_code": r.get("level_code"),
            "dept_str": ds,
            "description": r.get("note"), "vendor": r.get("vendor"),
            "amount": amt, "source": "TOPSIDE_ADJUSTMENTS",
        })
        attach_dept_forecast(r, "TS")

    # EBITDA addbacks — kept SEPARATE (not added into accounts forecasts).
    # They drive the adj/unadj actuals toggle.
    addbacks_by_version_fy: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(empty_monthly))
    # Per-account/dept/company breakdown so addback can land on the right BvA row
    # and respect sub-section filters.
    # Shape: {version: {reporting_account: {fy: {"total":[12], "by_dept":{ds:[12]}, "by_company":{co:[12]}}}}}
    addbacks_by_account: dict = {}
    addback_lines = []
    for r in [x for x in eb if x.get("version_name") in ALLOWED_VERSIONS and (x.get("reporting_account") or "").strip() not in excludes]:
        fy = int(r["fiscal_year"]); fm = int(r["fiscal_month"])
        ver = r["version_name"]; amt = r.get("amount") or 0.0
        ra = (r.get("reporting_account") or "").strip()
        ds = pad_dept(r.get("dept_str"))
        lc = (r.get("level_code") or "").strip()
        try:
            co_int = int(float(lc)) if lc else 0
        except (ValueError, TypeError):
            co_int = 0
        addbacks_by_version_fy[ver][fy][fm - 1] += amt
        if ra:
            slot = addbacks_by_account.setdefault(ver, {}).setdefault(ra, {}).setdefault(fy, {
                "total": [0.0]*12, "by_dept": {}, "by_company": {},
            })
            slot["total"][fm - 1] += amt
            if ds:
                slot["by_dept"].setdefault(ds, [0.0]*12)[fm - 1] += amt
            if co_int:
                slot["by_company"].setdefault(co_int, [0.0]*12)[fm - 1] += amt
        addback_lines.append({
            "version": ver, "fy": fy, "fm": fm, "level_code": r.get("level_code"),
            "reporting_account": ra, "dept_str": ds,
            "note": r.get("note"), "vendor": r.get("vendor"),
            "cerberus": r.get("cerberus_addbacks"),
            "amount": amt,
        })

    # ---------- Drill detail (vendor/customer) ----------
    drill_by_account = defaultdict(list)
    for r in drill:
        ra = (r.get("reporting_account") or "").strip()
        drill_by_account[ra].append({
            "fy": int(r["fiscal_year"]), "fm": int(r["fiscal_month"]),
            "source_company": int(r["source_company"]) if r.get("source_company") is not None else None,
            "vendor": r.get("vendor_name"), "customer": r.get("customer_name"),
            "invoice": r.get("invoice_number"), "comments": r.get("gl_comments"),
            "amount": r.get("amount") or 0.0,
        })

    # Attach drill list to its account record (first 200 lines per RA — keep file size sane)
    for (ra, _an), rec in accounts.items():
        rec["drill"] = drill_by_account.get(ra, [])[:300]

    # ---------- Discover available versions across all forecast tables ----------
    all_versions: set[str] = set()
    for rec in accounts.values():
        for v_key in rec["forecasts"].keys():
            all_versions.add(v_key)
    available_versions = sorted(all_versions)

    # When account-prefix is set (e.g., outbound freight tab), drop forecast-only accounts
    # that don't match the prefix.
    if prefixes:
        accounts = {k: v for k, v in accounts.items() if matches_prefix(v["reporting_account"])}

    # Dedup safety: collapse any entries that share the same reporting_account
    # (can happen if GL returns variant account_names for the same RA).
    seen_ra: dict[str, tuple] = {}
    dupes: list[tuple] = []
    for k, v in accounts.items():
        ra = v["reporting_account"]
        if ra in seen_ra:
            dupes.append((k, seen_ra[ra]))
        else:
            seen_ra[ra] = k
    for dup_key, primary_key in dupes:
        dup = accounts.pop(dup_key)
        pri = accounts[primary_key]
        for fy, arr in dup.get("actuals", {}).items():
            pri["actuals"].setdefault(fy, empty_monthly())
            for i in range(12):
                pri["actuals"][fy][i] += arr[i] if i < len(arr) else 0.0
        for fy, co_map in dup.get("actuals_by_company", {}).items():
            pri["actuals_by_company"].setdefault(fy, {})
            for co, arr in co_map.items():
                pri["actuals_by_company"][fy].setdefault(co, empty_monthly())
                for i in range(12):
                    pri["actuals_by_company"][fy][co][i] += arr[i] if i < len(arr) else 0.0
        for vk, arr in dup.get("forecasts", {}).items():
            pri["forecasts"].setdefault(vk, empty_monthly())
            for i in range(12):
                pri["forecasts"][vk][i] += arr[i] if i < len(arr) else 0.0
        pri.setdefault("forecast_lines", []).extend(dup.get("forecast_lines", []))
        pri.setdefault("drill", []).extend(dup.get("drill", []))
        print(f"  [dedup] merged duplicate RA '{dup['reporting_account']}' into primary")

    # ---------- Output ----------
    fy_in_actuals = sorted({fy for rec in accounts.values() for fy in rec["actuals"].keys()})
    out = {
        "meta": {
            "slug": args.slug,
            "dept_numbers": dept_strs,
            "dept_name": args.dept_name,
            "owner": args.owner,
            "refreshed_at": datetime.now().isoformat(timespec="seconds"),
            "fy_range": [args.fy_min, args.fy_max],
            "fy_in_actuals": fy_in_actuals,
            "available_versions": available_versions,
            "allowed_versions": sorted(ALLOWED_VERSIONS),
            "standard_category_order": STANDARD_CATEGORY_ORDER,
            "fx_rates": fx_rates,
            "fx_local_currency_by_company": {
                # Used by the dashboard to label Local-mode chips with the right ticker
                "11":"USD","14":"USD","71":"USD","74":"USD","86":"USD","13":"USD","16":"USD",
                "20":"CAD","70":"CAD",
                "32":"AUD","30":"AUD",
                "33":"MXN","168":"MXN",
                "40":"GBP","41":"EUR","65":"CNY",
                "1711":"USD","2920":"USD","3032":"USD","5533":"USD",
            },
            "source_company_map": SOURCE_COMPANY_MAP,
        },
        "accounts": [
            {
                "reporting_account": rec["reporting_account"],
                "account_name": rec["account_name"],
                "category": rec["category"],
                "gl_type": rec["gl_type"],
                "actuals": {str(fy): arr for fy, arr in rec["actuals"].items()},
                "actuals_by_company": {
                    str(fy): {str(co): arr for co, arr in cm.items()}
                    for fy, cm in rec["actuals_by_company"].items()
                },
                "actuals_by_channel": {
                    str(fy): {ch: arr for ch, arr in cm.items()}
                    for fy, cm in rec.get("actuals_by_channel", {}).items()
                },
                "actuals_by_channel_company": {
                    str(fy): {ch: {str(co): arr for co, arr in cm.items()}
                              for ch, cm in chm.items()}
                    for fy, chm in rec.get("actuals_by_channel_company", {}).items()
                },
                "actuals_by_dept": {
                    str(fy): {dstr: arr for dstr, arr in dm.items()}
                    for fy, dm in rec.get("actuals_by_dept", {}).items()
                },
                "forecasts": rec["forecasts"],
                "forecasts_by_dept": rec.get("forecasts_by_dept", {}),
                "forecasts_by_company": rec.get("forecasts_by_company", {}),
                "forecast_lines": rec["forecast_lines"][:5000],  # cap (per-account)
                "drill": rec["drill"],
            }
            for rec in sorted(accounts.values(), key=lambda r: (r["category"], r["reporting_account"]))
        ],
        "company_totals": build_company_totals(accounts, args.breakdown),
        "ebitda_addbacks": {
            ver: {str(fy): arr for fy, arr in fy_map.items()}
            for ver, fy_map in addbacks_by_version_fy.items()
        },
        "ebitda_addbacks_by_account": {
            ver: {
                ra: {
                    str(fy): {
                        "total": slot["total"],
                        "by_dept": dict(slot["by_dept"]),
                        "by_company": {str(co): arr for co, arr in slot["by_company"].items()},
                    }
                    for fy, slot in fy_map.items()
                }
                for ra, fy_map in ra_map.items()
            }
            for ver, ra_map in addbacks_by_account.items()
        },
        "dept_totals": [
            {
                "dept_str": d["dept_str"],
                "name": d["name"],
                "actuals": {str(fy): arr for fy, arr in d["actuals"].items()},
                "actuals_by_company": {
                    str(fy): {str(co): arr for co, arr in cm.items()}
                    for fy, cm in d["actuals_by_company"].items()
                },
                "actuals_by_channel": {
                    str(fy): {ch: arr for ch, arr in cm.items()}
                    for fy, cm in d.get("actuals_by_channel", {}).items()
                },
                "forecasts": d["forecasts"],
                "forecasts_by_company": {
                    v_key: {str(co): arr for co, arr in cm.items()}
                    for v_key, cm in d.get("forecasts_by_company", {}).items()
                },
            }
            for d in sorted(dept_totals.values(), key=lambda x: x["dept_str"])
        ],
        "ebitda_addback_lines": addback_lines[:500],
    }

    out_path = DATA / f"{args.slug}.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    size_kb = out_path.stat().st_size / 1024
    print(f"\nWrote {out_path}  ({size_kb:,.0f} KB, {len(out['accounts'])} accounts, "
          f"{len(available_versions)} version-FYs)")

if __name__ == "__main__":
    main()
