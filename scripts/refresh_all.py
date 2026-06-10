"""
Run refresh for the Marketing domain.

Scope (Option 1, per Chandler) — a single combined dataset:
  * Dept 75 (Marketing): ALL accounts (salaries, software, T&E, freight, leases,
    contract labor, advertising, ...).
  * Advertising accounts in ANY department: 6736000, 6738000, 6740000, 6746000,
    6747000, 6750000, 6763000, 6775000, 6790000 — matches the "Advertising" rollup
    in the Total Marketing Spend Review Excel.

The union is expressed by queries/actuals_marketing.sql (and the drill variant),
selected via the --actuals-sql / --drill-sql / --advertising-accounts knobs.

The dashboard slices this by channel (Wholesale / DTC / Freemotion / iFIT-Core /
iFIT-App / Corp-Other) and region (Americas / ROW, drilling to US / Canada / Mexico /
Australia / UK / EMEA / China). breakdown=company populates the company rollup that
backs the region sub-sections.

Usage:
    python scripts/refresh_all.py
"""
import os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Advertising accounts treated as "advertising in any department" (matches the Excel rollup).
ADVERTISING_ACCOUNTS = "6736000,6738000,6740000,6746000,6747000,6750000,6763000,6775000,6790000"

# Data-pull tabs — each triggers a refresh_dept run that writes data/<slug>.json.
TABS = [
    {
        "slug": "marketing", "name": "OPEX", "owner": "Marketing",
        "depts": "75", "breakdown": "company",
        "actuals_sql": "actuals_marketing.sql",
        "drill_sql": "actuals_drill_marketing.sql",
        "planning_sql": "forecast_planning_general_marketing.sql",
        "advertising_accounts": ADVERTISING_ACCOUNTS,
        "load_revenue_forecast": True,
    },
]

# Sidebar tabs (manifest). 'media' is a VIRTUAL tab that reuses marketing.json
# (dataSlug) — it shows the Sales + Advertising view; 'marketing' shows OPEX.
MANIFEST_TABS = [
    {"slug": "marketing", "name": "OPEX", "owner": "Marketing", "depts": "75", "breakdown": "company"},
    {"slug": "media", "name": "Paid / Non-Paid Media", "owner": "Marketing", "depts": "75",
     "breakdown": "company", "virtual": True, "dataSlug": "marketing"},
]


def write_manifest():
    import json
    (ROOT / "data" / "manifest.json").write_text(json.dumps({"tabs": MANIFEST_TABS}, indent=2))


def run():
    for t in TABS:
        cmd = [sys.executable, str(ROOT / "scripts" / "refresh_dept.py"),
               "--slug", t["slug"], "--dept-name", t["name"], "--owner", t["owner"], "--depts", t["depts"]]
        if t.get("breakdown"):             cmd += ["--breakdown", t["breakdown"]]
        if t.get("actuals_sql"):           cmd += ["--actuals-sql", t["actuals_sql"]]
        if t.get("drill_sql"):             cmd += ["--drill-sql", t["drill_sql"]]
        if t.get("planning_sql"):          cmd += ["--planning-sql", t["planning_sql"]]
        if t.get("advertising_accounts"):  cmd += ["--advertising-accounts", t["advertising_accounts"]]
        if t.get("load_revenue_forecast"): cmd += ["--load-revenue-forecast"]
        print("\n>", " ".join(cmd))
        # Ensure the project root is importable in the child (so `from config...` works
        # regardless of where the script's own dir lands on sys.path).
        child_env = dict(os.environ)
        child_env["PYTHONPATH"] = str(ROOT) + (os.pathsep + child_env["PYTHONPATH"] if child_env.get("PYTHONPATH") else "")
        r = subprocess.run(cmd, cwd=str(ROOT), env=child_env)
        if r.returncode != 0:
            print(f"!! {t['slug']} failed (rc={r.returncode}); continuing")
    write_manifest()
    print("\nDone. Manifest written to data/manifest.json")


if __name__ == "__main__":
    run()
