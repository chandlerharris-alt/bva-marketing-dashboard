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
- **Media Gross Revenue ACTUAL (DONE — ties 99.6%):** `ADAPTIVE_GL_PL_ACTUALS` → `meta.rev_gl_pl`. **KEY FINDING: that table's ACTUALS is LOCAL currency, not USD** (Chandler's catch). The dashboard now FX-converts per company/month in `glplRev` (USD = local/rate, `meta.fx_rates`), same as the actuals path. Verified May FY26 global rollup = **$57.40M USD** vs Excel Global Summary gross **$57.61M** (99.6%). Mexico co33 ÷17.4, China co65 ÷6.8, etc. — the un-converted pull was the entire ~$10M over-read. SQL tightened to `ACCOUNT_CODE LIKE '4500%'` (gross, drops returns/discounts contra). Also fixed `rebuildCompanyOptions` to union revenue-bearing companies (China 65 / Canada 70 / LATAM 71) into the company universe, else their revenue drops from the rollup and their region buttons show nothing.

## OPEN ITEMS
1. **PY + forecast revenue columns on Media (secondary gaps):** `ADAPTIVE_GL_PL_ACTUALS` only carries FY26+ (no FY25), so the **PY** Gross-Revenue column can't come from it — `glplRev` falls back to the old RPT/GL-account source for any year it lacks (currently PY shows same as Actual only because the PY selector defaults to `ACTUALS_FY2026`; pick a real FY25 comparison and it uses the fallback). The **AOP/8+4 forecast** revenue still comes from `RPT_FORECAST_DETAIL` = hardware-only, so forecast revenue understates actuals by subscription and Gross-Revenue AOP/8+4 variances read low/blank. Need a subscription+PY revenue source (candidate: an Adaptive planning revenue cube, or extend the SALES/OTHER_HW/subscription Snowflake tables). ACTUAL column is correct and ties — this only affects the PY/forecast comparison columns.
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

## Design system (iFIT 2.0 — applied 2026-07-07)
Source pkg: `Downloads/iFIT Design System.zip` (Shark #272930 dominant, Electric Lime #78F264 accent, deep teal #12313B, Geist/Geist Mono, 24px card / 999px pill radii, sentence-case, no emoji). Chosen scope: **dark Shark chrome + LIGHT data tables** (legibility), **teal-forward, green used sparingly**.
- All tokens live in `index.html` `:root` as `--ifit-*` vars; dashboard's `--navy/--sidebar-bg/etc.` remapped onto them. Change the whole look from there.
- Chrome (`.sidebar`, `.topbar`) = Shark `#272930`; active tab keyline = lime `--ifit-green`; primary/interactive = teal `--ifit-teal-900`; favorable text `#0E9E6E`, unfavorable `#E23A2E` (readable on white).
- Buttons/chips/segmented controls/`.pill-group` + JS inline channel/region toggles (`bOn/bOff`, `aOn/aOff`) = 999px pills. Cards/KPIs = 12px radius + `--ifit-shadow-sm`. Selects/inputs = 10px.
- Fonts via Google Fonts CDN (line 13): Geist 100–900 + Geist Mono. Wordmark already inline SVG in `.sb-brand`.
- LEFT as-is (already on-brand teal/fog, low benefit to change): Chart.js dataset palettes + OPEX monthly-matrix header colors (`#01323C/#015047/#BEB8A2`), `#E8E6DE` accent-val on dark tiles. Full DS pkg (imagery/ui_kits/fonts TTF) NOT copied into repo — only tokens applied.

## Fixes + admin version control (2026-07-08)
- **Blank-on-tab-switch + broken charts (FIXED):** `dashboard/vendor/{chart.umd.min.js,pptxgen.bundle.js}` were **never committed** → `<script>` 404 → `Chart` undefined → `render()` threw at `renderCharts()` → the throw propagated out of `initTab()` into `loadTab()`'s fetch `.catch`, which **overwrote the freshly-built grid** with "Failed: …". Toggling FY re-rendered outside the catch, which is why that "fixed" it. Fix: restored the vendored files (Chart.js v4.4.1 UMD, pptxgenjs 3.12); guarded `renderCharts()` to no-op if `Chart` is absent; moved `initTab()` out of the fetch `.catch` (render errors can't blank the grid anymore).
- **FY27 AOP not shown (FIXED):** data was fine (`FY27 AOP v5.5.26 | FY2027` in `available_versions`); the AOP compare column defaulted to `/AOP Final/` which matched FY26's, not FY27's (whose name lacks "Final"). `setupComparisonPickers` now prefers the SELECTED FY's own AOP (label starts with `FY{yy}`), falling back to any AOP Final / AOP.
- **Admin > Forecast Versions (NEW):** per-version checkboxes control which forecast versions appear in the AOP/8+4/prior-period pickers on every tab. Stored as a HIDDEN base-name list (new cuts default visible) in `data/version_visibility.json` (global, no-auth read) + per-browser `localStorage('bva_hidden_versions')` for instant effect. `functions/api/version-config.js` commits it to GitHub (admin-gated, mirrors `/api/access`) — global save works once the Cloudflare Access gate is on. Dashboard globals: `VERSION_HIDDEN`, `baseVersion()`, `loadVersionVisibility()` (in bootstrap); filter in `setupComparisonPickers`.
- KNOWN refinement (part of the forecast-revenue gap): RPT revenue for FY27 AOP normalizes to `FY27: AOP Final` (skipped, not in ALLOWED_VERSIONS) while OPEX uses `FY27 AOP v5.5.26` — different v_keys, so picking FY27 AOP shows OPEX but not that version's hardware-revenue forecast. Align the RPT normalizer to the OPEX version name if wiring FY27 revenue forecast.

## Git: latest commit `6e49251` (admin forecast-version control). Push after each change; Cloudflare auto-rebuilds ~1-2 min.
