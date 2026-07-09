-- Gross revenue ACTUALS from T360_GLOBAL_SALES_ORDERS (real-time hardware sales orders).
-- Alternate revenue source to ADAPTIVE_GL_PL_ACTUALS for periods that haven't closed yet:
-- Adaptive's recognized-P&L table lags the close, but this order-level feed is current
-- within days of ship. HARDWARE ONLY — no subscription revenue (unlike GL_PL) — the
-- dashboard's toggle makes that scope explicit to the user.
--
-- IMPORTANT: SALES is in LOCAL currency (per COMPANY) — NOT USD. Do NOT use SALES_USD;
-- the dashboard FX-converts SALES itself per company/month via meta.fx_rates, exactly like
-- every other revenue/actuals path, so all sources use the same Adaptive FX rate. Using the
-- table's own SALES_USD would introduce a second, inconsistent FX source.
--
-- No SALES_REPORTING_ACCOUNT filter: confirmed ~97% of DTC-channel dollars carry a NULL
-- SALES_REPORTING_ACCOUNT in this table (DTC doesn't get a line-level GL account tag the way
-- Wholesale/Freemotion do), so filtering to the same 4500-series accounts used elsewhere would
-- silently drop nearly all of DTC. Every row here already represents a real sales-order dollar
-- amount by construction — no risk of pulling in non-revenue GL lines the way a raw GL table would.
--
-- CHANNEL values: 'Wholesale','DTC','Freemotion','Other' (plus a few whitespace variants,
-- hence TRIM). No iFIT-Core/iFIT-App breakout — those are subscription-app channels and this
-- table is hardware orders only; they will show no data under this source, which is expected.

SELECT
    COMPANY                          AS company,
    TRIM(CHANNEL)                    AS channel,
    CAST(RR_FISCAL_YEAR  AS INTEGER) AS fy,
    CAST(RR_FISCAL_MONTH AS INTEGER) AS fm,
    SUM(SALES)                       AS amount
FROM ANALYTICS.ANALYTICS_TABLEAU_360_MART.T360_GLOBAL_SALES_ORDERS
WHERE TRIM(CHANNEL) IN ('Wholesale','DTC','Freemotion','Other')
  AND RR_FISCAL_YEAR  BETWEEN {fy_min} AND {fy_max}
  AND RR_FISCAL_MONTH BETWEEN 1 AND 12
GROUP BY 1, 2, 3, 4
;
