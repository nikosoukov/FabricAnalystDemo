-- SYNTHETIC DATA · for training only · no OSFI data
-- =====================================================================================
-- 20_lh_views.sql  -  run on the lh_supervisory SQL analytics endpoint (database lh_supervisory)
-- Run by scripts/01-Deploy-FdaEnvironment.ps1 (Invoke-Sqlcmd -AccessToken). Idempotent.
-- Click fallback: lh_supervisory > SQL analytics endpoint > New SQL query > paste > Run.
--
-- Views are the analyst-friendly layer: ratios are computed here from stored COMPONENTS
-- (SUM/SUM at any grain), never stored. Views on the SQL analytics endpoint are read-only,
-- usable from SSMS, Excel, Power BI (DirectQuery) and cross-database queries.
-- =====================================================================================

-- Institution x quarter: capital and liquidity ratios (deposit-taking institutions only)
CREATE OR ALTER VIEW dbo.vw_capital_ratios_quarterly
AS
SELECT
    i.institution_id,
    i.institution_code,
    i.institution_name,
    i.institution_type,
    i.peer_group,
    i.supervisory_lead,
    q.quarter_key,
    q.quarter_label,
    q.quarter_index,
    c.cet1_capital,
    c.rwa,
    CAST(c.cet1_capital  / NULLIF(c.rwa, 0)               AS decimal(9, 6)) AS cet1_ratio,
    CAST(c.tier1_capital / NULLIF(c.rwa, 0)               AS decimal(9, 6)) AS tier1_ratio,
    CAST(c.total_capital / NULLIF(c.rwa, 0)               AS decimal(9, 6)) AS total_capital_ratio,
    CAST(c.tier1_capital / NULLIF(c.leverage_exposure, 0) AS decimal(9, 6)) AS leverage_ratio,
    CAST(l.hqla / NULLIF(l.net_cash_outflows_30d, 0)                     AS decimal(9, 6)) AS lcr,
    CAST(l.available_stable_funding / NULLIF(l.required_stable_funding, 0) AS decimal(9, 6)) AS nsfr
FROM dbo.fact_capital AS c
JOIN dbo.dim_institution AS i ON i.institution_id = c.institution_id
JOIN dbo.dim_quarter     AS q ON q.quarter_key   = c.quarter_key
LEFT JOIN dbo.fact_liquidity AS l
       ON l.institution_id = c.institution_id
      AND l.quarter_key    = c.quarter_key;
GO

-- Quarter x province: mortgage balance, insured share and 90-day arrears rate
CREATE OR ALTER VIEW dbo.vw_mortgage_by_province
AS
SELECT
    q.quarter_key,
    q.quarter_label,
    p.province_code,
    p.province_name,
    p.region,
    SUM(m.balance)                                                     AS balance_cad_m,
    SUM(m.loan_count)                                                  AS loan_count,
    SUM(CASE WHEN m.insured_flag = 1 THEN m.balance ELSE 0 END) / NULLIF(SUM(m.balance), 0) AS insured_share,
    SUM(m.arrears_90d_balance) / NULLIF(SUM(m.balance), 0)             AS arrears_90d_rate
FROM dbo.fact_mortgage_exposure AS m
JOIN dbo.dim_quarter  AS q ON q.quarter_key   = m.quarter_key
JOIN dbo.dim_province AS p ON p.province_code = m.province_code
GROUP BY q.quarter_key, q.quarter_label, p.province_code, p.province_name, p.region;
GO

-- Check (expected initial: 677 institution-quarters, 2026 Q3 has 17 deposit-taking institutions)
SELECT COUNT(*) AS capital_rows,
       SUM(CASE WHEN quarter_key = 20263 THEN 1 ELSE 0 END) AS rows_2026q3
FROM dbo.vw_capital_ratios_quarterly;
GO
