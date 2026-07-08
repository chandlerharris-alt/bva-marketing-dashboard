# Marketing BvA Dashboard — Build State (living handoff)

**Purpose:** durable state so a context reset doesn't backpedal. Update after each meaningful change.

## Where things live
- **Local repo:** `C:\Users\chandler.harris\BvA Build\bva-marketing-dashboard`
- **GitHub:** `chandlerharris-alt/bva-marketing-dashboard` (private, branch `main`)
- **Live:** https://bva-marketing-dashboard.pages.dev (Cloudflare **Pages** project; Functions active)
- **Excel source of truth:** `G:\Shared drives\FP&A\Monthly Reporting\FY26\12 - May\Marketing\Total Marketing Spend Review_May26_V2.xlsx`
- **Snowflake creds:** OS keyring service `ifit-snowflake`, keys `SNOWFLAKE_USER/PASSWORD/ACCOUNT/WAREHOUSE` (user CHANDLER_HARRIS, wh REPORTING_WAREHOUSE, db ANALYTICS). connect() in scripts/refresh_dept.py.
- **Run refresh:** `python scripts/refresh_all.py` (writes data/marketing.json, ~11MB). `_jscheck.py` validates index.html JS before every push.

## Architecture
Snowflake → `scripts/refresh_all.py`→`refresh_dept.py` → `data/marketing.json` → git push → Cloudflare Pages build → dashboard (`dashboard/index.html`, single-file SPA). Comments/categories saved via `functions/api/*.js` (need Cloudflare Access to authenticate — NOT set up yet).

## Data scope (Option 1 — union)
- **Dept 75 (all accounts) UNION advertising accounts (any dept)** — `queries/actuals_marketing.sql` + `actuals_drill_marketing.sql` (knobs `--actuals-sql/--drill-sql/--advertising-accounts` in refresh_dept.py). Also pulls `4500%` revenue.
- Advertising accounts: 6736000,6738000,6740000,6746000,6747000,6750000,6763000,6775000,6790000.
- Forecast: `forecast_planning_general_marketing.sql` (union) via `--planning-sql`; `RPT_FORECAST_DETAIL` revenue via `--load-revenue-forecast`.

## Tabs (manifest.json + refresh_all.py MANIFEST_TABS)
- **Overview** (rollup tiles).
- **OPEX** — slug `marketing`; BvA grid (`buildTable`, GL categories). Top-level = rollup of all regions; region sub-sections (US/Canada/Mexico/Australia/UK/EMEA/China) filter by company. Advertising EXCLUDED (scopeAccountsForTab).
- **Paid / Non-Paid Media** — slug `media`, **virtual tab** (`virtual:true, dataSlug:'marketing'` → reuses marketing.json). BvA-style grid `buildMediaGrid()`: Gross Revenue → Paid Media (6736+6740) → Paid % of Rev → Non-Paid Media (rest) → Non-Paid % of Rev → Total Advertising → Total Adv % of Rev. % rows show variances in **bps**. Channel+Region **button bars** on grid (region buttons only on rollup); filterbar Channel/Company dropdowns hidden on media. scopeAccountsForTab keeps advertising+revenue only.

## Column order (BvA grids): **PY · AOP · 8+4 · Actuals** + $Variance + %Variance (all PY/AOP/8+4). Set in buildTable header + catRow/acctRow/totalRow + buildMediaGrid.

## Key implementation notes (index.html)
- `isRevenueAccount` → `GROSS_REV_ACCTS = {4500000, 4500777, 4500774, 4500123}` (equipment + subscription; GL sign-flip makes subs positive).
- `effectiveSeries` applies `channelFactor` so AOP/8+4 forecast responds to the channel filter (like actuals).
- `scopeAccountsForTab(accts)` in initTab: media = advertising+revenue; marketing(OPEX) = exclude advertising.
- Dispatch in `render()`: media+OPEX → `renderTable()`→`buildTable()` (buildTable branches to `buildMediaGrid()` for media). Only freight/warehouse use the matrix. `renderMarketingSummary` (old channel matrix) is now UNUSED/dead.
- Account drill: `buildMediaGrid`/`buildTable` account rows expand (renderTable wiring); drill panel (~line 3600s) shows **By Category** groupings by default + collapsed **"Expand Transactions (N untagged)"** bar (`toggleReconLines`).
- Contacts/Calendar MC tabs removed; Adj/Unadj toggle hidden; adj forced ADJ.

## Validated tie-outs (May FY26 / FM12, vs Excel)
- Advertising (global) ties ~93–96%. OPEX categories tie (Excel "Total OPEX" was double-counting — resolved). Data/tie-out reference: `data/_tieout_may26.json`, checker `scripts/validate_tieout.py`.
- **Media Gross Revenue ACTUAL + PY (DONE):** sourced from `ADAPTIVE_GL_PL_ACTUALS` → `meta.rev_gl_pl`. FY26 May global by channel (USD, gross): Wholesale $23.7M, DTC $20.3M, iFIT-Core $15.2M, Freemotion $8.9M, Corp/Other $0.5M, iFIT-App $0. Americas subset ties to Excel within unclosed-May tolerance.

## OPEN ITEMS
1. **Subscription-forecast gap (remaining piece of the revenue work):** Media Gross Revenue **Actual + PY** now correct (from `meta.rev_gl_pl`, USD, incl subscription — see refresh_dept.py `--load-gl-pl-revenue`, `queries/revenue_gl_pl.sql`, and the `glplRev()` block in `buildMediaGrid`). BUT the **AOP/8+4 forecast** revenue columns still come from `RPT_FORECAST_DETAIL`, which is **hardware-only** — so forecast revenue understates actuals by the subscription amount and the Gross-Revenue 8+4/AOP variances read artificially negative. Need a subscription FORECAST source (RPT is hardware-only; ADAPTIVE_GL_PL_ACTUALS is actuals-only). Flag to Chandler; candidate = an Adaptive planning version cube for revenue by channel.
2. **Cloudflare Access login gate NOT set up** → `/api/*` returns 401 → "Save Categories authentication failing" (categories are browser-local only, won't persist for others). Zero Trust → Access → self-hosted app on the pages.dev host, policy: emails ending @ifit.com. This is the last infra step + makes sharing safe.
3. Marketing dept-head name/email still placeholder ("Marketing") in access.json/manifest/_domain_config.

## Automation — daily refresh (DONE, 2026-07-07)
Full chain runs itself: **Snowflake → refresh_all.py → git commit+push → Cloudflare rebuild**.
- **Wrapper:** `scripts/daily_refresh.ps1` — runs refresh_all.py, stages **only `data/`**, commits `Automated daily data refresh <date>`, pushes, logs to `logs/refresh_*.log` (30-day prune). Exit 0 = ok.
- **Registrar:** `scripts/register_daily_task.ps1` (params `-Time -Cadence -TaskName`) creates Windows Scheduled Task **"iFIT Marketing BvA - Daily Refresh"**: Mon–Fri 06:30, `StartWhenAvailable` (catch-up on missed), runs on battery, principal = Chandler.Harris **Interactive** (so Credential Manager vault w/ Snowflake pwd + GitHub token is unlocked). Re-run to change time.
- **Verified:** direct run AND scheduler-triggered run both exit 0 and pushed (`bffdbc9`, `3d8e25c`).
- Caveat: needs PC on + logged in at some point on/after 06:30; if off it catches up at next logon. `logs/` + `scripts/_*.py` are gitignored.
- Known minor: consecutive refreshes produce large non-deterministic JSON diffs (~17k lines) — Snowflake row order isn't stable (no ORDER BY on some pulls). Cosmetic churn only; future cleanup = sort keys / add ORDER BY for deterministic output.
- Change schedule: `powershell -ExecutionPolicy Bypass -File scripts\register_daily_task.ps1 -Time 05:00 -Cadence Daily`. Check health: Task Scheduler → last run result, or newest `logs/refresh_*.log`.

## Git: latest commit `b9a7481` (daily auto-refresh automation). Push after each change; Cloudflare auto-rebuilds ~1-2 min.
