-- Revenue forecast from RPT_FORECAST_DETAIL.
-- SALES_USD is already in USD -- no FX conversion needed.
-- CHANNEL and REGION are native columns (no dept mapping required).

SELECT
    VERSION,
    CAST(FISCAL_YEAR  AS INTEGER) AS fiscal_year,
    CAST(FISCAL_MONTH AS INTEGER) AS fiscal_month,
    CAST(COMPANY AS INTEGER) AS source_company,
    CHANNEL,
    REGION,
    SUM(SALES_USD) AS amount_usd,
    SUM(SALES)     AS amount_local
FROM ANALYTICS.ANALYTICS_GL_ANALYTICS_MART.RPT_FORECAST_DETAIL
WHERE FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 1, 2, 3, 4
;
