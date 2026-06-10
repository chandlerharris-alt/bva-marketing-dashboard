-- Outbound freight forecast from ADAPTIVE_OUTBOUND_FREIGHT_SUMMARY.
-- ACCOUNT_CODE has an "OBF_SUM.Fi" prefix; the GL account number sits in
-- ACCOUNT_NAME (e.g. "6755000 - Delivery Expense"). We extract it via SPLIT_PART.

SELECT
    VERSION_NAME,
    CAST(FISCAL_YEAR  AS INTEGER) AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER) AS fiscal_month,
    LEVEL_CODE,
    DEPARTMENT            AS dept_str,
    CHANNEL,
    SPLIT_PART(ACCOUNT_NAME, ' - ', 1)  AS reporting_account,
    ACCOUNT_NAME,
    SUM(AMOUNT)           AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_OUTBOUND_FREIGHT_SUMMARY
WHERE DEPARTMENT  IN ({dept_strs_csv})
  AND FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
ORDER BY 1, 2, 3, 4, 5
;
