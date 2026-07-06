-- ============================================================
-- Cleanup: remove legacy parcel history rows from survey result
-- tables after switching to "result keeps final state only".
--
-- Execute after backing up the database and stopping write traffic.
-- Recommended order:
-- 1. Run the preview section and review counts.
-- 2. If counts are expected, run the whole script.
-- ============================================================

-- ========== Part A: preview ==========

SELECT 'removed_relation_rows' AS metric, COUNT(*)::BIGINT AS row_count
FROM survey_cbdkxx_result
WHERE result_status = 'removed'
UNION ALL
SELECT 'removed_parcel_rows', COUNT(*)::BIGINT
FROM survey_dk_result
WHERE result_status = 'removed'
UNION ALL
SELECT 'orphan_active_parcel_rows', COUNT(*)::BIGINT
FROM survey_dk_result AS dk
WHERE dk.result_status <> 'removed'
  AND NOT EXISTS (
    SELECT 1
    FROM survey_cbdkxx_result AS rel
    WHERE rel.dkbm = dk.dkbm
      AND rel.result_status <> 'removed'
  );

-- ========== Part B: cleanup ==========

BEGIN;

LOCK TABLE survey_cbdkxx_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_dk_result IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE tmp_removed_survey_cbdkxx_result_ids AS
SELECT id
FROM survey_cbdkxx_result
WHERE result_status = 'removed';

CREATE TEMP TABLE tmp_removed_survey_dk_result_ids AS
SELECT id
FROM survey_dk_result
WHERE result_status = 'removed';

CREATE TEMP TABLE tmp_orphan_survey_dk_result_ids AS
SELECT dk.id
FROM survey_dk_result AS dk
WHERE dk.result_status <> 'removed'
  AND NOT EXISTS (
    SELECT 1
    FROM survey_cbdkxx_result AS rel
    WHERE rel.dkbm = dk.dkbm
      AND rel.result_status <> 'removed'
  );

DELETE FROM survey_cbdkxx_result
WHERE id IN (SELECT id FROM tmp_removed_survey_cbdkxx_result_ids);

DELETE FROM survey_dk_result
WHERE id IN (
    SELECT id FROM tmp_removed_survey_dk_result_ids
    UNION
    SELECT id FROM tmp_orphan_survey_dk_result_ids
);

SELECT 'deleted_relation_rows' AS metric, COUNT(*)::BIGINT AS row_count
FROM tmp_removed_survey_cbdkxx_result_ids
UNION ALL
SELECT 'deleted_removed_parcel_rows', COUNT(*)::BIGINT
FROM tmp_removed_survey_dk_result_ids
UNION ALL
SELECT 'deleted_orphan_parcel_rows', COUNT(*)::BIGINT
FROM tmp_orphan_survey_dk_result_ids;

COMMIT;

-- ========== Part C: post-check ==========

SELECT 'remaining_removed_relation_rows' AS metric, COUNT(*)::BIGINT AS row_count
FROM survey_cbdkxx_result
WHERE result_status = 'removed'
UNION ALL
SELECT 'remaining_removed_parcel_rows', COUNT(*)::BIGINT
FROM survey_dk_result
WHERE result_status = 'removed'
UNION ALL
SELECT 'remaining_orphan_active_parcel_rows', COUNT(*)::BIGINT
FROM survey_dk_result AS dk
WHERE dk.result_status <> 'removed'
  AND NOT EXISTS (
    SELECT 1
    FROM survey_cbdkxx_result AS rel
    WHERE rel.dkbm = dk.dkbm
      AND rel.result_status <> 'removed'
  );
