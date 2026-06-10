-- Marketing UNION-scope actuals from GLOBAL_COMBINED_GL.
-- Scope = ALL accounts for the marketing dept(s) in {depts_csv}  (i.e. dept 75)
--         UNION
--         ANY advertising account in {ad_accounts_csv}  (regardless of department).
--
-- This is the one purpose-built query for the Marketing dashboard (Option 1):
-- it expresses the "dept 75 (all accounts) OR advertising account (any dept)"
-- union that the generic dept-scoped template cannot. It deliberately mirrors
-- actuals_by_dept.sql column-for-column so refresh_dept.py consumes it identically.
--
-- Params (Python str-format):
--   depts_csv       = e.g. 75
--   ad_accounts_csv = quoted CSV of advertising REPORTING_ACCOUNTs, e.g. '6736000','6740000',...
--                     (refresh_dept passes '__none__' when no advertising list is set, which
--                      degenerates this query to dept-only scope.)
--   fy_min, fy_max  = e.g. 2025, 2026
--
-- Notes mirror actuals_by_dept.sql: no GL_TYPE filter (PL_TOTAL is P&L-scoped),
-- exclude bad fiscal_month + SUMMARY ENTRY rollups, and apply the 4500* revenue
-- sign-flip fix (harmless here since marketing scope carries no 4500 revenue).

SELECT
    CAST(FISCAL_YEAR  AS INTEGER)   AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER)   AS fiscal_month,
    CAST(SOURCE_COMPANY AS INTEGER) AS source_company,
    CAST(DEPT_NUMBER   AS INTEGER)  AS dept_number,
    DEPT_NAME,
    REPORTING_ACCOUNT,
    ACCOUNT_NAME,
    CATEGORY,
    GL_TYPE,
    CHANNEL,
    SUM(
      CASE
        WHEN REPORTING_ACCOUNT LIKE '4500%'
             AND TOTAL < 0 AND PL_TOTAL < 0
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%BACK%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%REVERSAL%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%ADJUSTMENT%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%CORRECT%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%RECLASS%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%REFUND%'
          THEN ABS(PL_TOTAL)
        ELSE PL_TOTAL
      END
    )                                AS amount,
    COUNT(*)                         AS row_count
FROM ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL
WHERE ( DEPT_NUMBER IN ({depts_csv})
        OR REPORTING_ACCOUNT IN ({ad_accounts_csv}) )
  AND FISCAL_YEAR  BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
  AND REPORTING_ACCOUNT IS NOT NULL
  AND REPORTING_ACCOUNT NOT ILIKE '%SUMMARY ENTRY%'
  AND PL_TOTAL IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
ORDER BY 1, 2, 3, 4, 6
;
