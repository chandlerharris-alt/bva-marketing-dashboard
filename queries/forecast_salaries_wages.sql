-- Salaries & Wages forecast for a single dept (the missing payroll feed).
-- Schema is leaner than PLANNING_GENERAL: ACCOUNT_CODE is the join key (no GL).

SELECT
    VERSION_NAME,
    CAST(FISCAL_YEAR  AS INTEGER) AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER) AS fiscal_month,
    LEVEL_CODE,
    DEPARTMENT            AS dept_str,
    ACCOUNT_CODE          AS reporting_account,
    ACCOUNT_NAME,
    SUM(AMOUNT)           AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_SALARIES_WAGES
WHERE DEPARTMENT  IN ({dept_strs_csv})
  AND FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY 1, 2, 3, 4, 5
;
