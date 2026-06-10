-- Marketing UNION-scope forecast OPEX/advertising from ADAPTIVE_PLANNING_GENERAL.
-- Mirrors forecast_planning_general.sql but widens the dept filter to the same union
-- scope as the marketing actuals: ALL accounts for dept(s) {dept_strs_csv} (dept 075)
-- OR ANY advertising account in {ad_accounts_csv} (regardless of department).
--
-- This captures advertising FORECAST that lives in non-marketing depts (DTC, iFIT,
-- Freemotion, intl) so the 8+4 Advertising rollup ties to the Excel. Dept-75 OPEX
-- forecast lines are unchanged. LEVEL_CODE maps to the source company (and carries
-- UK/EMEA/China levels for the regional 8+4 split).

SELECT
    VERSION_NAME,
    CAST(FISCAL_YEAR  AS INTEGER) AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER) AS fiscal_month,
    LEVEL_CODE,
    DEPARTMENT AS dept_str,
    COALESCE(NULLIF(TRIM(GENERAL_LEDGER), ''), EXPENSE_ACCOUNT) AS reporting_account,
    EXPENSE_ACCOUNT,
    DESCRIPTION,
    VENDOR,
    CHANNEL,
    EXPENSE_TYPE,
    PROJECT,
    SUM(AMOUNT)          AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_PLANNING_GENERAL
WHERE ( DEPARTMENT IN ({dept_strs_csv})
        OR COALESCE(NULLIF(TRIM(GENERAL_LEDGER), ''), EXPENSE_ACCOUNT) IN ({ad_accounts_csv}) )
  AND FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY VERSION_NAME, fiscal_year, fiscal_month, LEVEL_CODE, dept_str, reporting_account,
         EXPENSE_ACCOUNT, DESCRIPTION, VENDOR, CHANNEL, EXPENSE_TYPE, PROJECT
ORDER BY 1, 2, 3, 4, 5
;
