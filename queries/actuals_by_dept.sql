-- Actuals from GLOBAL_COMBINED_GL for a single department.
-- Returns one row per FY/FM/source_company/reporting_account.
-- Vendor + customer are kept aggregated separately for drill-through.
--
-- Params (Python str-format style):
--   dept_number    = e.g. 10  (numeric — DEPT_NUMBER is NUMBER)
--   fy_min, fy_max = e.g. 2025, 2026
--
-- Notes:
--   * No GL_TYPE filter (per Devin) — use PL_TOTAL which is already P&L-scoped.
--   * Exclude bad fiscal_month rows (0 or >12) and SUMMARY ENTRY rollups.
--   * REVENUE SIGN-FLIP FIX (2026-05-13): for revenue accounts (4500*),
--     a handful of GL entries have PL_TOTAL stored negative even though
--     the underlying TOTAL is also negative (the system's sign-flip
--     skipped them). Detected by: account starts '4500' AND both TOTAL
--     and PL_TOTAL are negative AND comment is NOT a known reversal
--     pattern (BACK OUT, REVERSAL, ADJUSTMENT, RECLASS, CORRECT, REFUND).
--     Catches Co 14 CS SALES / RPS SALES and Co 11 RPS SALES anomalies
--     while preserving legitimate sales-backout entries.

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
WHERE DEPT_NUMBER  IN ({depts_csv})
  AND FISCAL_YEAR  BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
  AND REPORTING_ACCOUNT IS NOT NULL
  AND REPORTING_ACCOUNT NOT ILIKE '%SUMMARY ENTRY%'
  AND PL_TOTAL IS NOT NULL
  {account_filter_clause}
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
ORDER BY 1, 2, 3, 4, 6
;
