-- Vendor / description / line-level drill-through for a single dept.
-- Used to power the "expand row" tooltip and Salesforce-style line matching
-- (so software accounts can show which vendor each $ went to).

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
    SUM(PL_TOTAL) AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL
WHERE DEPT_NUMBER  IN ({depts_csv})
  AND FISCAL_YEAR  BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
  AND REPORTING_ACCOUNT IS NOT NULL
  AND REPORTING_ACCOUNT NOT ILIKE '%SUMMARY ENTRY%'
  AND PL_TOTAL IS NOT NULL
  {account_filter_clause}
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9
ORDER BY 1, 2, 3, 4, ABS(SUM(PL_TOTAL)) DESC
;
