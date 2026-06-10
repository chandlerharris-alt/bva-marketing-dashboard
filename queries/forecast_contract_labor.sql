-- Contract-labor forecast for a single dept (one row per contractor / month / version).

SELECT
    VERSION_NAME,
    CAST(FISCAL_YEAR  AS INTEGER) AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER) AS fiscal_month,
    LEVEL_CODE,
    DEPARTMENT           AS dept_str,
    GENERAL_LEDGER       AS reporting_account,
    CONTRACTOR_NAME,
    VENDOR,
    PURPOSE,
    PROJECT,
    COUNTRY,
    SUM(AMOUNT)          AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_CONTRACT_LABOR
WHERE DEPARTMENT  IN ({dept_strs_csv})
  AND FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
ORDER BY 1, 2, 3, 4, 5
;
