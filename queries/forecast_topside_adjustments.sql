-- Topside adjustments (manual overlays) for a single dept.

SELECT
    VERSION_NAME,
    CAST(FISCAL_YEAR  AS INTEGER) AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER) AS fiscal_month,
    LEVEL_CODE,
    DEPARTMENT           AS dept_str,
    GENERAL_LEDGER       AS reporting_account,
    NOTE,
    VENDOR,
    PROJECT,
    CHANNEL,
    SUM(AMOUNT)          AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_TOPSIDE_ADJUSTMENTS
WHERE DEPARTMENT  IN ({dept_strs_csv})
  AND FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
ORDER BY 1, 2, 3, 4, 5
;
