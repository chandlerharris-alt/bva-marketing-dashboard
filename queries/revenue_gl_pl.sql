-- Gross revenue ACTUALS from GLOBAL_COMBINED_GL (the same combined-GL mart the rest of
-- the dashboard's actuals come from), scoped to the explicit revenue account list below.
-- This REPLACES the earlier ADAPTIVE_GL_PL_ACTUALS source. Key: aggregate on
-- REPORTING_COMPANY, not SOURCE_COMPANY. SOURCE_COMPANY is the SAP source ledger
-- (1711/5533/3032/2920 shared entities that carry revenue for MANY regions), so summing
-- it by the dashboard's US company set wrongly pulls Mexico/Australia/UK DTC into "US".
-- REPORTING_COMPANY is the reporting rollup that matches the dashboard's company/region/FX
-- map (74=US DTC, 33=Mexico, 32=Australia, 65=China, ...). Verified US-DTC (co74, DTC):
-- FY25 $165.0M, FY26 $172.2M.
--
-- IMPORTANT: PL_TOTAL is in LOCAL currency (per COMPANY) — NOT USD. The dashboard
-- FX-converts rev_gl_pl per company/month via meta.fx_rates (USD = local / rate),
-- exactly like the OPEX actuals path. Do NOT treat these numbers as USD.
--
-- Revenue account universe (per Chandler, 2026-08-10): equipment/sales + freight +
-- service + commission + subscription + eliminations. Sign convention mirrors
-- actuals_marketing.sql: 4500-series revenue can post as a negative credit in PL_TOTAL
-- (with a positive TOTAL); flip those to positive unless the row is a backout/reversal/
-- reclass/etc. Non-4500 accounts (4501000 elim, 4508000 commission) pass through PL_TOTAL.
--
-- Output columns are unchanged from the prior query (company, channel, fy, fm, amount)
-- so refresh_dept.py consumes it identically.

SELECT
    CAST(REPORTING_COMPANY AS INTEGER) AS company,   -- reporting entity (74=US DTC, 33=MX, ...),
                                                     -- NOT the SAP SOURCE_COMPANY (1711/5533/...)
    CHANNEL                          AS channel,
    CAST(FISCAL_YEAR  AS INTEGER)    AS fy,
    CAST(FISCAL_MONTH AS INTEGER)    AS fm,
    SUM(
      CASE
        WHEN REPORTING_ACCOUNT LIKE '4500%'
             AND TOTAL < 0 AND PL_TOTAL < 0
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%BACK%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%REVERSAL%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%ADJUSTMENT%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%CORRECT%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%RECLASS%'
             AND COALESCE(GL_COMMENTS,'') NOT ILIKE '%REFUND%'
          THEN ABS(PL_TOTAL)
        ELSE PL_TOTAL
      END
    )                                AS amount
FROM ANALYTICS.ANALYTICS_ADAPTIVE.GLOBAL_COMBINED_GL
WHERE REPORTING_ACCOUNT IN (
        '4500000','4500004','4500055','4500056','4500057','4500065',
        '4500070','4500100','4500110','4501000','4508000','4500777'
      )
  AND FISCAL_YEAR  BETWEEN {fy_min} AND {fy_max}
  AND FISCAL_MONTH BETWEEN 1 AND 12
  AND REPORTING_ACCOUNT NOT ILIKE '%SUMMARY ENTRY%'
  AND PL_TOTAL IS NOT NULL
GROUP BY 1, 2, 3, 4
;
