-- Gross revenue ACTUALS from ADAPTIVE_GL_PL_ACTUALS (Adaptive recognized P&L actuals).
-- This is the Excel's revenue source: correct channel taxonomy (WHSL/DTC/FM/iFIT-Core/
-- iFIT-App/Corp-Other, i.e. INCLUDES subscription).
--
-- IMPORTANT: ACTUALS is in LOCAL currency (per COMPANY) — NOT USD. The dashboard
-- FX-converts it per company/month via meta.fx_rates (USD = local / rate), exactly
-- like the GL actuals path. Do NOT treat these numbers as USD.
--
-- Gross revenue = 4500-series accounts (equipment 4500000, subscription 4500777/774,
-- app 4500123, plus freight/service/install/DR sales) EXCLUDING Sales Deductions
-- (4500500) and Sales Eliminations (4501000). Verified May FY26: local 70,740.8K ->
-- USD 57,955.6K, ties to the Excel Global Summary gross (57,606.9K) within 0.6%.
-- Restricting to 4500% (vs all SECTION='Revenue') drops returns/discounts/financing-fee
-- contra accounts, matching the Excel's "Gross Revenue" (before returns) definition.
-- ACTUALS = adjusted/proforma actuals (matches the dashboard's ADJ view).

SELECT
    COMPANY                          AS company,
    CHANNEL                          AS channel,
    CAST(FISCAL_YEAR  AS INTEGER)    AS fy,
    CAST(FISCAL_MONTH AS INTEGER)    AS fm,
    SUM(ACTUALS)                     AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.ADAPTIVE_GL_PL_ACTUALS
WHERE SECTION = 'Revenue'
  AND ACCOUNT_CODE LIKE '4500%'
  AND ACCOUNT_CODE NOT IN ('4500500','4501000')
  AND FISCAL_YEAR BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY 1, 2, 3, 4
;
