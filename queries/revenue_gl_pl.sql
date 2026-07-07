-- Gross revenue ACTUALS from ADAPTIVE_GL_PL_ACTUALS (Adaptive recognized P&L actuals).
-- This is the Excel's revenue source: correct channel taxonomy (WHSL/DTC/FM/iFIT-Core/
-- iFIT-App/Corp-Other, i.e. INCLUDES subscription) and already in USD (no FX needed).
-- Used for the Media tab's Gross Revenue (Actual + PY columns) and the % -of-Revenue denominator.
--
-- Gross = SECTION 'Revenue' excluding Sales Deductions (4500500) and Eliminations (4501000).
-- ACTUALS = adjusted/proforma actuals (matches the dashboard's ADJ view).

SELECT
    COMPANY                          AS company,
    CHANNEL                          AS channel,
    CAST(FISCAL_YEAR  AS INTEGER)    AS fy,
    CAST(FISCAL_MONTH AS INTEGER)    AS fm,
    SUM(ACTUALS)                     AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_GL_PL_ACTUALS
WHERE SECTION = 'Revenue'
  AND ACCOUNT_CODE NOT IN ('4500500','4501000')
  AND FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY 1, 2, 3, 4
;
