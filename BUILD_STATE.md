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

## Versions available vs. allowlisted (2026-07-08)
`ALLOWED_VERSIONS` (refresh_dept.py) is a curated allowlist — the ONLY way a version reaches the dashboard (the admin panel can only HIDE what's pulled, not add). Full scan of Adaptive tables: `scripts/_scan_versions.py`. Adaptive carries ~40 versions incl. many drafts/deprecated/`FX Virtual`/`Board`/`Cerberus`/`MPF` cuts. Added **`FY27: AOP Final`** (was missing — only the `FY27 AOP v5.5.26` draft was allowlisted). Because the RPT revenue normaliser also emits `FY27: AOP Final`, OPEX + hardware revenue now combine under that one key. NOT added (available on request): `FY27: Board AOP`, `FY26: Board AOP`, `FY26: Cerberus AOP`, interim/deprecated drafts. FY25 RPT AOP still skipped (normalises to `FY25: AOP Final`, which isn't allowlisted; FY25 OPEX uses `FY25 AOP`).

## Access model v2 + auth plan (2026-07-08)
**Access schema (access.json):** each user = `{ admin?, tabs, versions }`. `admin:true` = full + manage-access. `tabs` maps slug→`{view,tag,comment,forecast}` (`'*'` = default for all tabs; no entry = tab hidden). `versions` = `'*'` or array of base version names the user may compare. Old `{role,slugs}` auto-migrates on read (`normalizeEntry` in me.js + `normalizeAccessEntry` in index.html — keep them in sync).
- **Client helpers** (index.html): `authIsAdmin()`, `authCan(slug,cap)`, `authCanSee(slug)`, `authVersionAllowed(base)`. Enforcement wired into: tag save (`saveCategoriesToServer`/`updateCategoriesSaveButton`→'tag'), comment save (`saveVarianceComments`→'comment'), forecast editor+save (`buildFcLineItemEditor`/`updateSaveButton`/`saveForecastToServer`→'forecast'), tab visibility (`filterSidebarByAccess`/`authCanSee`), admin visibility, and the Compare version pickers (`setupComparisonPickers` filters by `VERSION_HIDDEN` ∩ `authVersionAllowed`).
- **Admin > User Access** = per-user cards: Admin toggle + per-tab View/Tag/Comment/Forecast + per-user version chips (`adminUserCardHtml`/`wireAdminCard`/`adminSave`, new schema). Plus the global "Forecast Versions" hide card.
- **CRITICAL — not enforced yet:** there is NO auth identity source (no `functions/_middleware.js`, no login gate), so `/api/me` 401s and the client **falls back to full local admin for everyone** (`initAuth` FALLBACK). Nothing restricts users and no `/api/*` write persists until auth is wired.
- **Chosen auth (per Chandler): Google sign-in ("Sign in with Google" restricted to @ifit.com), NOT Cloudflare Access** (Access limits seats). TODO to activate: (1) get the Google OAuth **Client ID** (`…apps.googleusercontent.com`) from the employee who set up Google auth for other iFIT apps; add `https://bva-marketing-dashboard.pages.dev` to that client's Authorized JavaScript origins. (2) Add Google Identity Services sign-in to index.html → sets AUTH_STATE.email. (3) Write `functions/_middleware.js` to verify the Google ID token (RS256 vs Google JWKS, check hd/email domain) and set `context.data.user={email}` — then all `/api/*` + permissions enforce.

## OPEX UX changes (Chandler request, 2026-07-08)
DONE (commit c8df62c): "BvA"→**"Financial Performance"** app-wide (viewMode button + `#bva-card` header + page title); **collapsible Top Variances** (`toggleTopVariances`/`applyTopVarCollapse`, localStorage `bva_topvar_collapsed`) with a vs-Plan/vs-PY summary banner (`#bva-var-summary`); **trend chart** = Actuals / Plan(cmpA) / Prior Year (dropped the cmpB series).
REMAINING (deferred — coupled refactor): OPEX filterbar → keep View/FY/As-of-Month/Currency, rename Compare A label to **"Plan"**, remove **Compare B + Prior Period** selectors (PY fixed = same month prior FY, set cmpPY automatically), **remove Channel** on OPEX (keep on media), and replace the **Source Companies dropdown with an on-grid multi-button selector** above the grid (region tabs show only that region's companies — mirror media's region buttons). This forces the OPEX grid columns from PY/AOP/8+4/Actuals to **PY | Plan | Actuals** — but `catRow`/`acctRow`/`totalRow`/`deltaCells`/header/drill-KPIs/top-variance table are SHARED with the 4-column media grid, so it needs a column-config threaded through (or an OPEX-only branch). Do as one focused change; verify media grid still renders 4 cols.

## Google sign-in — LIVE (2026-07-08)
Server-side OAuth (auth-code flow), per the employee's "one project, many clients" standard — NOT Cloudflare Access (seat limits).
- **Google Cloud:** own project `iFIT-FPA-Dashboards` under org `iconfitness.com`; consent screen **Internal**; OAuth client `bva-marketing-dashboard`. Client ID `541431881403-t5k9f1t79nu6n0rb5g0hions7nnp95n5.apps.googleusercontent.com`. Redirect URIs: `https://bva-marketing-dashboard.pages.dev/auth/callback` + `http://localhost:8788/auth/callback`.
- **Code:** `functions/_authlib.js` (signed-session + OAuth helpers, Web Crypto HMAC), `functions/_middleware.js` (site gate — **fails open if GOOGLE_CLIENT_ID/SESSION_SECRET unset**, else verifies session cookie → sets `context.data.user`, redirects unauth → `/auth/login`, 401s `/api/*`), `functions/auth/{login,callback,logout}.js`. 12h signed session cookie. Domain lock via `ALLOWED_DOMAIN` = `ifit.com,iconfitness.com`. `initAuth` fallback (`_local` admin) only when `/api/me` 401s (local dev / gate off). "Sign out" link in the user badge.
- **Cloudflare env vars (Production):** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (enc), `SESSION_SECRET` (enc), `ALLOWED_DOMAIN`. Env-var changes need a fresh deploy to bind (a "Retry" may not rebind — push a commit). VERIFIED live: `/dashboard/` 302→/auth/login; /auth/login 302→accounts.google.com with correct params.
- Access model v2 now ENFORCES (per-tab caps + per-user versions) since `/api/me` returns the real user.
- **REMAINING for saves to persist:** the GitHub-commit Functions (`/api/access`, `/api/categories`, `/api/comments`, `/api/version-config`, `/api/save-forecast`) need env vars **`GITHUB_TOKEN` (PAT, repo scope), `GITHUB_OWNER`=chandlerharris-alt, `GITHUB_REPO`=bva-marketing-dashboard** (+ optional `GITHUB_BRANCH`=main). Without them, admin "Save" → 500 server_misconfigured (auth works, but changes don't persist to the shared file). Set these next to make Save Users/Categories/Comments/Versions write through for everyone.

## API auth aligned to access v2 (2026-07-08)
All `/api/*` write Functions had bespoke checks against the OLD `role`/`slugs` fields → admins got 403 on the migrated `{admin,tabs,versions}` schema. Added shared **`functions/_access.js`** (`getAccess`/`isAdmin`/`can(slug,cap)`/`canSee` + old→new migration, mirrors me.js) and rewired every function: access.js/version-config.js/overrides/approve → `isAdmin`; categories → `can 'tag'`; comments → `can 'comment'`; save-forecast/overrides → `can 'forecast'`; audit → `isAdmin`/`canSee`. Per-tab capability model now enforced server-side too. GitHub-commit env vars (`GITHUB_TOKEN`/`GITHUB_OWNER`=chandlerharris-alt/`GITHUB_REPO`=bva-marketing-dashboard) are set → saves persist.

## Git: latest commit `2cbd803` (API auth → v2 schema). Push after each change; Cloudflare auto-rebuilds ~1-2 min.
