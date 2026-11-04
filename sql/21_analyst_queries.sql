-- SYNTHETIC DATA · for training only · no OSFI data
-- =====================================================================================
-- 21_analyst_queries.sql  -  LIVE in D3 (SQL analytics endpoint)
-- Highlight ONE block and select Run (only the highlighted text runs).
--   Blocks A-D and F1: lh_supervisory > SQL analytics endpoint > New SQL query
--   Blocks E and F2:   wh_analyst_sandbox > New SQL query
-- Expected results assume D2 has run (late filings landed) and thresholds are v1.
-- Values before landing are given in brackets [ ].
-- Watch thresholds are internal watch thresholds (illustrative), NOT OSFI regulatory minimums.
-- =====================================================================================


-- ===== BLOCK A · what is in the lakehouse? (row counts) ==============================
SELECT 'dim_institution' AS table_name, COUNT_BIG(*) AS row_count FROM dbo.dim_institution
UNION ALL SELECT 'dim_quarter',                  COUNT_BIG(*) FROM dbo.dim_quarter
UNION ALL SELECT 'dim_province',                 COUNT_BIG(*) FROM dbo.dim_province
UNION ALL SELECT 'fact_capital',                 COUNT_BIG(*) FROM dbo.fact_capital
UNION ALL SELECT 'fact_liquidity',               COUNT_BIG(*) FROM dbo.fact_liquidity
UNION ALL SELECT 'fact_insurance_capital',       COUNT_BIG(*) FROM dbo.fact_insurance_capital
UNION ALL SELECT 'fact_mortgage_exposure',       COUNT_BIG(*) FROM dbo.fact_mortgage_exposure
UNION ALL SELECT 'supervisory_watch_thresholds', COUNT_BIG(*) FROM dbo.supervisory_watch_thresholds
ORDER BY table_name;
-- Expected: dim_institution 40 · dim_province 13 · dim_quarter 31 · fact_capital 682 [677]
--           fact_insurance_capital 558 [553] · fact_liquidity 682 [677]
--           fact_mortgage_exposure 1,218,393 [1,211,265] · supervisory_watch_thresholds 14


-- ===== BLOCK B · CET1 ratio by institution type, current quarter ======================
-- Store components, not ratios: SUM(capital) / SUM(RWA) is the right aggregate.
-- The naive AVG of institution ratios is shown only to make the point.
SELECT
    i.institution_type,
    COUNT(*)                                                   AS institutions,
    CAST(SUM(c.cet1_capital) / SUM(c.rwa) AS decimal(9, 4))    AS cet1_ratio,            -- correct
    CAST(AVG(c.cet1_capital / c.rwa)      AS decimal(9, 4))    AS avg_of_ratios_wrong    -- misleading
FROM dbo.fact_capital AS c
JOIN dbo.dim_institution AS i ON i.institution_id = c.institution_id
JOIN dbo.dim_quarter     AS q ON q.quarter_key   = c.quarter_key
WHERE q.is_current = 1
GROUP BY i.institution_type
ORDER BY cet1_ratio;
-- Expected (2026 Q3): D-SIB 6 0.1309 (avg 0.1318) · Other bank 10 0.1398 (avg 0.1382)
--                     Trust and loan 6 0.1496 (avg 0.1487)
--           [before landing: D-SIB 5 0.1299 · Other bank 8 0.1416 · Trust and loan 4 0.1506]


-- ===== BLOCK C · quarter-over-quarter change (LAG) and rank in peer group (RANK) ======
WITH qoq AS (
    SELECT
        institution_name,
        institution_type,
        peer_group,
        quarter_key,
        quarter_label,
        cet1_ratio,
        (cet1_ratio - LAG(cet1_ratio) OVER (PARTITION BY institution_id ORDER BY quarter_key)) * 100 AS cet1_qoq_pp
    FROM dbo.vw_capital_ratios_quarterly
)
SELECT
    peer_group,
    RANK() OVER (PARTITION BY peer_group ORDER BY cet1_qoq_pp) AS drop_rank_in_peer_group,
    institution_name,
    quarter_label,
    cet1_ratio,
    CAST(cet1_qoq_pp AS decimal(6, 2)) AS cet1_qoq_pp
FROM qoq
WHERE quarter_key = 20263
ORDER BY peer_group, drop_rank_in_peer_group;
-- Expected rank 1 per peer group: D-SIB Stonebridge Bank -0.64 · Mid-size bank Driftwood Bank -1.41
--   · Small bank Ashgrove Bank -0.17 · Trust and loan Riverbend Trust and Loan -0.58
--   [before landing Driftwood Bank has no 2026 Q3 row; Mid-size bank rank 1 = Larchmont Bank -0.17]


-- ===== BLOCK D · late filers: who has not filed 2026 Q3? ==============================
SELECT
    i.institution_code,
    i.institution_name,
    i.institution_type,
    i.supervisory_lead,
    i.is_late_filer_2026q3,
    CASE WHEN c.institution_id IS NULL AND ic.institution_id IS NULL THEN 'Missing' ELSE 'Filed' END AS status_2026q3
FROM dbo.dim_institution AS i
LEFT JOIN dbo.fact_capital           AS c  ON c.institution_id  = i.institution_id AND c.quarter_key  = 20263
LEFT JOIN dbo.fact_insurance_capital AS ic ON ic.institution_id = i.institution_id AND ic.quarter_key = 20263
WHERE i.is_late_filer_2026q3 = 1
ORDER BY status_2026q3 DESC, i.institution_code;
-- Expected: 10 rows (FI002, FI011, FI013, FI018, FI022, FI027, FI029, FI033, FI038, FI040),
--           all 'Filed' after D2 [all 'Missing' before landing].


-- ===== BLOCK E · run on wh_analyst_sandbox: cross-database query + CTAS ===============
-- Three-part names reach the lakehouse SQL analytics endpoint in the same workspace. No copy job.
SELECT TOP 5 institution_name, quarter_label, cet1_ratio
FROM lh_supervisory.dbo.vw_capital_ratios_quarterly
WHERE quarter_key = 20263
ORDER BY cet1_ratio;
-- Expected (rounded to 4 dp): Driftwood Bank 0.1121 · Cedarline Bank 0.1138 · Ashgrove Bank 0.1178 · Larchmont Bank 0.1191 · Silverpine Bank 0.1270

DROP TABLE IF EXISTS dbo.watchlist_2026q3;
CREATE TABLE dbo.watchlist_2026q3
AS
SELECT
    v.institution_code,
    v.institution_name,
    v.institution_type,
    v.supervisory_lead,
    v.quarter_key,
    v.cet1_ratio,
    CAST(t.watch_threshold AS decimal(9, 4)) AS cet1_watch_threshold,
    t.source_file,
    CAST(SYSUTCDATETIME() AS datetime2(0))   AS created_at_utc
FROM lh_supervisory.dbo.vw_capital_ratios_quarterly AS v
JOIN lh_supervisory.dbo.supervisory_watch_thresholds AS t
  ON t.institution_type = v.institution_type
 AND t.metric = 'CET1 ratio'
WHERE v.quarter_key = 20263
  AND v.cet1_ratio < t.watch_threshold;

SELECT * FROM dbo.watchlist_2026q3 ORDER BY cet1_ratio;
-- Expected: 2 rows: Driftwood Bank 0.1121 and Cedarline Bank 0.1138 vs 0.1150 (v1)
--           [1 row before landing: Cedarline Bank] [4 rows after D5 v2: + Ashgrove Bank, Larchmont Bank vs 0.1200]


-- ===== BLOCK F1 · run on the lh_supervisory SQL analytics endpoint: it is READ-ONLY ===
INSERT INTO dbo.dim_province (province_code, province_name, province_name_fr, region)
VALUES ('ZZ', 'Test', 'Test', 'Test');
-- Expected: ERROR. DML (INSERT/UPDATE/DELETE) is not supported on the SQL analytics endpoint of a lakehouse;
-- the wording varies by release (VERIFY on the day). Data is written by Spark, Dataflow Gen2 or pipelines;
-- the endpoint is for reading, views and security.


-- ===== BLOCK F2 · run on wh_analyst_sandbox: the warehouse is WRITABLE =================
INSERT INTO dbo.analyst_notes (note_id, institution_code, quarter_key, note_text, author, created_at)
VALUES (6, 'FI011', 20263, 'Driftwood Bank: Q3 return received; CET1 11.21% below internal watch. Escalate.', 'Live demo', SYSUTCDATETIME());

SELECT note_id, institution_code, quarter_key, note_text, author FROM dbo.analyst_notes ORDER BY note_id;
-- Expected: (1 row affected), then 6 rows. Reset: 02-Reset-FdaDemo.ps1 reruns sql/30_wh_sandbox_setup.sql.


-- ===== Connection string (SSMS, Azure Data Studio, Excel, Power BI Desktop) ===========
-- lh_supervisory > SQL analytics endpoint > Settings (gear) > SQL endpoint > copy "SQL connection string"
--   Server: <xxxx>.datawarehouse.fabric.microsoft.com   Database: lh_supervisory
--   Authentication: Microsoft Entra ID (MFA). Read-only for lakehouse tables; your workspace role/permissions apply.
