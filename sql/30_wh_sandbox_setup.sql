-- SYNTHETIC DATA · for training only · no OSFI data
-- =====================================================================================
-- 30_wh_sandbox_setup.sql  -  run on the warehouse wh_analyst_sandbox
-- Run by scripts/01-Deploy-FdaEnvironment.ps1 and 02-Reset-FdaDemo.ps1. Idempotent:
-- drops the demo's own objects and recreates them.
-- Click fallback: wh_analyst_sandbox > New SQL query > paste > Run.
-- =====================================================================================

DROP TABLE IF EXISTS dbo.watchlist_2026q3;     -- created live in D3 (sql/21 block E)
DROP TABLE IF EXISTS dbo.analyst_notes;
GO

CREATE TABLE dbo.analyst_notes
(
    note_id          int           NOT NULL,
    institution_code varchar(10)   NOT NULL,
    quarter_key      int           NOT NULL,
    note_text        varchar(400)  NOT NULL,
    author           varchar(100)  NOT NULL,
    created_at       datetime2(0)  NOT NULL
);
GO

-- Fictitious institutions and authors (see dim_institution)
INSERT INTO dbo.analyst_notes (note_id, institution_code, quarter_key, note_text, author, created_at)
VALUES
 (1, 'FI007', 20262, 'Cedarline Bank: CET1 ratio below the internal watch threshold for the first time. Request capital plan update.', 'Fatima Haddad',   '2026-08-20T10:15:00'),
 (2, 'FI003', 20263, 'Stonebridge Bank: LCR fell sharply QoQ. Ask treasury for the drivers (deposit outflows vs HQLA).',             'Sofia Marchetti', '2026-10-28T14:05:00'),
 (3, 'FI011', 20263, 'Driftwood Bank: 2026 Q3 return late. Follow up with the filing contact.',                                       'Amara Okafor',    '2026-10-31T09:30:00'),
 (4, 'FI023', 20263, 'Prairie Crown Life: LICAT total ratio trending down for four quarters.',                                        'Sofia Marchetti', '2026-10-29T11:00:00'),
 (5, 'FI034', 20263, 'Kettle Lake General: MCT below internal watch after catastrophe losses; monitor reinsurance recoveries.',       'Rajiv Mehta',     '2026-10-30T16:45:00');
GO

SELECT COUNT(*) AS analyst_notes_rows FROM dbo.analyst_notes;   -- Expected: 5
GO
