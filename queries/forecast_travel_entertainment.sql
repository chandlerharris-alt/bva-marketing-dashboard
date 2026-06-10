-- Travel & Entertainment forecast for a single dept.

SELECT
    VERSION_NAME,
    CAST(FISCAL_YEAR  AS INTEGER) AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER) AS fiscal_month,
    LEVEL_CODE,
    DEPARTMENT            AS dept_str,
    ACCOUNT_CODE          AS reporting_account,
    ACCOUNT_NAME,
    SUM(AMOUNT)           AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_TRAVEL_ENTERTAINMENT
WHERE DEPARTMENT  IN ({dept_strs_csv})
  AND FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY 1, 2, 3, 4, 5
;
