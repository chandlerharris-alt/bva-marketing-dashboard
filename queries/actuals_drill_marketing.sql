-- Marketing UNION-scope vendor/invoice drill-through.
-- Mirrors actuals_drill_by_dept.sql but uses the same union scope as
-- actuals_marketing.sql: ALL accounts for dept(s) {depts_csv} (dept 75) OR ANY
-- advertising account in {ad_accounts_csv} (any dept). Powers the "expand row"
-- vendor tooltip + line matching for marketing + advertising accounts.

SELECT
    CAST(FISCAL_YEAR  AS INTEGER)   AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER)   AS fiscal_month,
    CAST(SOURCE_COMPANY AS INTEGER) AS source_company,
    REPORTING_ACCOUNT,
    ACCOUNT_NAME,
    VENDOR_NAME,
    CUSTOMER_NAME,
    INVOICE_NUMBER,
    GL_COMMENTS,
    CHANNEL,
    SUM(PL_TOTAL) AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL
WHERE ( DEPT_NUMBER IN ({depts_csv})
        OR REPORTING_ACCOUNT IN ({ad_accounts_csv}) )
  AND FISCAL_YEAR  BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
  AND REPORTING_ACCOUNT IS NOT NULL
  AND REPORTING_ACCOUNT NOT ILIKE '%SUMMARY ENTRY%'
  AND PL_TOTAL IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
ORDER BY 1, 2, 3, 4, ABS(SUM(PL_TOTAL)) DESC
;
