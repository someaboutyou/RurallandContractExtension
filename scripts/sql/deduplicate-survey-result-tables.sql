-- ============================================================
-- Deduplicate survey result tables
--
-- Purpose:
-- 1. Remove duplicate rows from survey result tables.
-- 2. Keep only the latest row (largest id) for each business key.
-- 3. Help distinguish "exact duplicate rows" from "business conflicts".
--
-- Business keys used in this cleanup:
-- - survey_cbf_result: cbfbm
-- - survey_cbf_jtcy_result: cbfbm + cyzjhm
-- - survey_fbf_result: fbfbm
-- - survey_cbdkxx_result: dkbm + cbfbm
-- - survey_dk_result: dkbm
--
-- Important:
-- - Back up the database before execution.
-- - Stop write traffic before execution.
-- - This script only cleans exact duplicate business-key rows.
-- - If one dkbm exists under multiple cbfbm values, that is a separate
--   business conflict and should be investigated separately.
-- ============================================================

-- ========== Part A: preview ==========

SELECT 'survey_cbf_result_duplicate_rows' AS metric, COALESCE(SUM(group_size - 1), 0)::BIGINT AS row_count
FROM (
    SELECT cbfbm, COUNT(*) AS group_size
    FROM survey_cbf_result
    GROUP BY cbfbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_cbf_result_duplicate_groups', COUNT(*)::BIGINT
FROM (
    SELECT cbfbm
    FROM survey_cbf_result
    GROUP BY cbfbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_cbf_jtcy_result_duplicate_rows', COALESCE(SUM(group_size - 1), 0)::BIGINT
FROM (
    SELECT cbfbm, cyzjhm, COUNT(*) AS group_size
    FROM survey_cbf_jtcy_result
    GROUP BY cbfbm, cyzjhm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_cbf_jtcy_result_duplicate_groups', COUNT(*)::BIGINT
FROM (
    SELECT cbfbm, cyzjhm
    FROM survey_cbf_jtcy_result
    GROUP BY cbfbm, cyzjhm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_fbf_result_duplicate_rows', COALESCE(SUM(group_size - 1), 0)::BIGINT
FROM (
    SELECT fbfbm, COUNT(*) AS group_size
    FROM survey_fbf_result
    GROUP BY fbfbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_fbf_result_duplicate_groups', COUNT(*)::BIGINT
FROM (
    SELECT fbfbm
    FROM survey_fbf_result
    GROUP BY fbfbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_cbdkxx_result_duplicate_rows', COALESCE(SUM(group_size - 1), 0)::BIGINT
FROM (
    SELECT dkbm, cbfbm, COUNT(*) AS group_size
    FROM survey_cbdkxx_result
    GROUP BY dkbm, cbfbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_cbdkxx_result_duplicate_groups', COUNT(*)::BIGINT
FROM (
    SELECT dkbm, cbfbm
    FROM survey_cbdkxx_result
    GROUP BY dkbm, cbfbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_dk_result_duplicate_rows', COALESCE(SUM(group_size - 1), 0)::BIGINT
FROM (
    SELECT dkbm, COUNT(*) AS group_size
    FROM survey_dk_result
    GROUP BY dkbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_dk_result_duplicate_groups', COUNT(*)::BIGINT
FROM (
    SELECT dkbm
    FROM survey_dk_result
    GROUP BY dkbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_cbdkxx_result_cross_owner_dkbm_conflicts', COUNT(*)::BIGINT
FROM (
    SELECT dkbm
    FROM survey_cbdkxx_result
    GROUP BY dkbm
    HAVING COUNT(DISTINCT cbfbm) > 1
) AS t;

-- Optional detail preview: uncomment as needed.
-- SELECT cbfbm, COUNT(*) AS row_count, ARRAY_AGG(id ORDER BY id DESC) AS ids
-- FROM survey_cbf_result
-- GROUP BY cbfbm
-- HAVING COUNT(*) > 1
-- ORDER BY row_count DESC, cbfbm
-- LIMIT 100;
--
-- SELECT cbfbm, cyzjhm, COUNT(*) AS row_count, ARRAY_AGG(id ORDER BY id DESC) AS ids
-- FROM survey_cbf_jtcy_result
-- GROUP BY cbfbm, cyzjhm
-- HAVING COUNT(*) > 1
-- ORDER BY row_count DESC, cbfbm, cyzjhm
-- LIMIT 100;
--
-- SELECT fbfbm, COUNT(*) AS row_count, ARRAY_AGG(id ORDER BY id DESC) AS ids
-- FROM survey_fbf_result
-- GROUP BY fbfbm
-- HAVING COUNT(*) > 1
-- ORDER BY row_count DESC, fbfbm
-- LIMIT 100;
--
-- SELECT dkbm, cbfbm, COUNT(*) AS row_count, ARRAY_AGG(id ORDER BY id DESC) AS ids
-- FROM survey_cbdkxx_result
-- GROUP BY dkbm, cbfbm
-- HAVING COUNT(*) > 1
-- ORDER BY row_count DESC, dkbm, cbfbm
-- LIMIT 100;
--
-- SELECT dkbm, COUNT(*) AS row_count, ARRAY_AGG(id ORDER BY id DESC) AS ids
-- FROM survey_dk_result
-- GROUP BY dkbm
-- HAVING COUNT(*) > 1
-- ORDER BY row_count DESC, dkbm
-- LIMIT 100;

-- ========== Part B: cleanup ==========

BEGIN;

LOCK TABLE survey_cbf_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_cbf_jtcy_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_fbf_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_cbdkxx_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_dk_result IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE tmp_delete_survey_cbf_result_ids AS
SELECT id
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (PARTITION BY cbfbm ORDER BY id DESC) AS rn
    FROM survey_cbf_result
) AS ranked
WHERE rn > 1;

CREATE TEMP TABLE tmp_delete_survey_cbf_jtcy_result_ids AS
SELECT id
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (PARTITION BY cbfbm, cyzjhm ORDER BY id DESC) AS rn
    FROM survey_cbf_jtcy_result
) AS ranked
WHERE rn > 1;

CREATE TEMP TABLE tmp_delete_survey_fbf_result_ids AS
SELECT id
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (PARTITION BY fbfbm ORDER BY id DESC) AS rn
    FROM survey_fbf_result
) AS ranked
WHERE rn > 1;

CREATE TEMP TABLE tmp_delete_survey_cbdkxx_result_ids AS
SELECT id
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (PARTITION BY dkbm, cbfbm ORDER BY id DESC) AS rn
    FROM survey_cbdkxx_result
) AS ranked
WHERE rn > 1;

CREATE TEMP TABLE tmp_delete_survey_dk_result_ids AS
SELECT id
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (PARTITION BY dkbm ORDER BY id DESC) AS rn
    FROM survey_dk_result
) AS ranked
WHERE rn > 1;

DELETE FROM survey_cbf_result
WHERE id IN (SELECT id FROM tmp_delete_survey_cbf_result_ids);

DELETE FROM survey_cbf_jtcy_result
WHERE id IN (SELECT id FROM tmp_delete_survey_cbf_jtcy_result_ids);

DELETE FROM survey_fbf_result
WHERE id IN (SELECT id FROM tmp_delete_survey_fbf_result_ids);

DELETE FROM survey_cbdkxx_result
WHERE id IN (SELECT id FROM tmp_delete_survey_cbdkxx_result_ids);

DELETE FROM survey_dk_result
WHERE id IN (SELECT id FROM tmp_delete_survey_dk_result_ids);

SELECT 'deleted_survey_cbf_result_rows' AS metric, COUNT(*)::BIGINT AS row_count
FROM tmp_delete_survey_cbf_result_ids
UNION ALL
SELECT 'deleted_survey_cbf_jtcy_result_rows', COUNT(*)::BIGINT
FROM tmp_delete_survey_cbf_jtcy_result_ids
UNION ALL
SELECT 'deleted_survey_fbf_result_rows', COUNT(*)::BIGINT
FROM tmp_delete_survey_fbf_result_ids
UNION ALL
SELECT 'deleted_survey_cbdkxx_result_rows', COUNT(*)::BIGINT
FROM tmp_delete_survey_cbdkxx_result_ids
UNION ALL
SELECT 'deleted_survey_dk_result_rows', COUNT(*)::BIGINT
FROM tmp_delete_survey_dk_result_ids;

COMMIT;

-- ========== Part C: post-check ==========

SELECT 'survey_cbf_result_remaining_duplicate_rows' AS metric, COALESCE(SUM(group_size - 1), 0)::BIGINT AS row_count
FROM (
    SELECT cbfbm, COUNT(*) AS group_size
    FROM survey_cbf_result
    GROUP BY cbfbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_cbf_jtcy_result_remaining_duplicate_rows', COALESCE(SUM(group_size - 1), 0)::BIGINT
FROM (
    SELECT cbfbm, cyzjhm, COUNT(*) AS group_size
    FROM survey_cbf_jtcy_result
    GROUP BY cbfbm, cyzjhm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_fbf_result_remaining_duplicate_rows', COALESCE(SUM(group_size - 1), 0)::BIGINT
FROM (
    SELECT fbfbm, COUNT(*) AS group_size
    FROM survey_fbf_result
    GROUP BY fbfbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_cbdkxx_result_remaining_duplicate_rows', COALESCE(SUM(group_size - 1), 0)::BIGINT
FROM (
    SELECT dkbm, cbfbm, COUNT(*) AS group_size
    FROM survey_cbdkxx_result
    GROUP BY dkbm, cbfbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_dk_result_remaining_duplicate_rows', COALESCE(SUM(group_size - 1), 0)::BIGINT
FROM (
    SELECT dkbm, COUNT(*) AS group_size
    FROM survey_dk_result
    GROUP BY dkbm
    HAVING COUNT(*) > 1
) AS t
UNION ALL
SELECT 'survey_cbdkxx_result_remaining_cross_owner_dkbm_conflicts', COUNT(*)::BIGINT
FROM (
    SELECT dkbm
    FROM survey_cbdkxx_result
    GROUP BY dkbm
    HAVING COUNT(DISTINCT cbfbm) > 1
) AS t;
