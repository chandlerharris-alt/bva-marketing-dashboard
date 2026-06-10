-- Forecast/budget OPEX from ADAPTIVE_PLANNING_GENERAL for a single dept.
-- Returns one row per (version × FY × FM × level/source-company × account × line description).
-- DESCRIPTION + VENDOR drive the line-item match against GL drill (e.g., "Salesforce").
--
-- LEVEL_CODE in Adaptive maps to the source company.

SELECT
    VERSION_NAME,
    CAST(FISCAL_YEAR  AS INTEGER) AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER) AS fiscal_month,
    LEVEL_CODE,
    DEPARTMENT AS dept_str,
    -- COALESCE: phone stipends and a few other items live in EXPENSE_ACCOUNT
    -- without a GL. Falling back ensures those line up with actuals.
    COALESCE(NULLIF(TRIM(GENERAL_LEDGER), ''), EXPENSE_ACCOUNT) AS reporting_account,
    EXPENSE_ACCOUNT,
    DESCRIPTION,
    VENDOR,
    CHANNEL,
    EXPENSE_TYPE,
    PROJECT,
    SUM(AMOUNT)          AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_PLANNING_GENERAL
WHERE DEPARTMENT  IN ({dept_strs_csv})
  AND FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY VERSION_NAME, fiscal_year, fiscal_month, LEVEL_CODE, dept_str, reporting_account,
         EXPENSE_ACCOUNT, DESCRIPTION, VENDOR, CHANNEL, EXPENSE_TYPE, PROJECT
ORDER BY 1, 2, 3, 4, 5
;
