-- ============================================================
-- Reset survey change state
--
-- Purpose:
-- 1. Reset change markers in survey result tables back to normal.
-- 2. Clear task-layer change flags/counts.
-- 3. Delete survey change records and field diffs.
--
-- Important:
-- - This script DOES NOT restore physically deleted households,
--   members, parcel relations, or parcels.
-- - This script keeps current result-table data values as-is and only
--   clears "changed" state and change logs.
-- - Back up the database before execution.
-- ============================================================

-- ========== Part A: preview ==========

SELECT 'survey_cbf_result_changed_rows' AS metric, COUNT(*)::BIGINT AS row_count
FROM survey_cbf_result
WHERE result_status <> 'normal' OR is_changed IS TRUE OR change_type <> 'none' OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_cbf_jtcy_result_changed_rows', COUNT(*)::BIGINT
FROM survey_cbf_jtcy_result
WHERE member_result_status <> 'normal' OR is_changed IS TRUE OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_fbf_result_changed_rows', COUNT(*)::BIGINT
FROM survey_fbf_result
WHERE result_status <> 'normal' OR is_changed IS TRUE OR change_type <> 'none' OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_cbdkxx_result_changed_rows', COUNT(*)::BIGINT
FROM survey_cbdkxx_result
WHERE result_status <> 'normal' OR is_changed IS TRUE OR change_type <> 'none' OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_dk_result_changed_rows', COUNT(*)::BIGINT
FROM survey_dk_result
WHERE result_status <> 'normal' OR is_changed IS TRUE OR change_type <> 'none' OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_cbf_base_changed_tasks', COUNT(*)::BIGINT
FROM survey_cbf_base
WHERE has_change IS TRUE OR change_count <> 0
UNION ALL
SELECT 'survey_cbf_jtcy_base_changed_tasks', COUNT(*)::BIGINT
FROM survey_cbf_jtcy_base
WHERE has_change IS TRUE OR change_count <> 0
UNION ALL
SELECT 'survey_fbf_base_changed_tasks', COUNT(*)::BIGINT
FROM survey_fbf_base
WHERE has_change IS TRUE OR change_count <> 0
UNION ALL
SELECT 'survey_cbdkxx_base_changed_tasks', COUNT(*)::BIGINT
FROM survey_cbdkxx_base
WHERE has_change IS TRUE OR change_count <> 0
UNION ALL
SELECT 'survey_dk_base_changed_tasks', COUNT(*)::BIGINT
FROM survey_dk_base
WHERE has_change IS TRUE OR change_count <> 0
UNION ALL
SELECT 'survey_change_records_rows', COUNT(*)::BIGINT
FROM survey_change_records
UNION ALL
SELECT 'survey_change_diffs_rows', COUNT(*)::BIGINT
FROM survey_change_diffs;

-- ========== Part B: reset ==========

BEGIN;

LOCK TABLE survey_cbf_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_cbf_jtcy_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_fbf_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_cbdkxx_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_dk_result IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_cbf_base IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_cbf_jtcy_base IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_fbf_base IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_cbdkxx_base IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_dk_base IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_change_records IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE survey_change_diffs IN SHARE ROW EXCLUSIVE MODE;

UPDATE survey_cbf_result
SET
  result_status = 'normal',
  is_changed = FALSE,
  change_type = 'none',
  change_reason = NULL;

UPDATE survey_cbf_jtcy_result
SET
  member_result_status = 'normal',
  is_changed = FALSE,
  change_reason = NULL;

UPDATE survey_fbf_result
SET
  result_status = 'normal',
  is_changed = FALSE,
  change_type = 'none',
  change_reason = NULL;

UPDATE survey_cbdkxx_result
SET
  result_status = 'normal',
  is_changed = FALSE,
  change_type = 'none',
  change_reason = NULL;

UPDATE survey_dk_result
SET
  result_status = 'normal',
  is_changed = FALSE,
  change_type = 'none',
  change_reason = NULL;

UPDATE survey_cbf_base
SET
  has_change = FALSE,
  change_count = 0;

UPDATE survey_cbf_jtcy_base
SET
  has_change = FALSE,
  change_count = 0;

UPDATE survey_fbf_base
SET
  has_change = FALSE,
  change_count = 0;

UPDATE survey_cbdkxx_base
SET
  has_change = FALSE,
  change_count = 0;

UPDATE survey_dk_base
SET
  has_change = FALSE,
  change_count = 0;

DELETE FROM survey_change_diffs;
DELETE FROM survey_change_records;

COMMIT;

-- ========== Part C: post-check ==========

SELECT 'survey_cbf_result_remaining_changed_rows' AS metric, COUNT(*)::BIGINT AS row_count
FROM survey_cbf_result
WHERE result_status <> 'normal' OR is_changed IS TRUE OR change_type <> 'none' OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_cbf_jtcy_result_remaining_changed_rows', COUNT(*)::BIGINT
FROM survey_cbf_jtcy_result
WHERE member_result_status <> 'normal' OR is_changed IS TRUE OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_fbf_result_remaining_changed_rows', COUNT(*)::BIGINT
FROM survey_fbf_result
WHERE result_status <> 'normal' OR is_changed IS TRUE OR change_type <> 'none' OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_cbdkxx_result_remaining_changed_rows', COUNT(*)::BIGINT
FROM survey_cbdkxx_result
WHERE result_status <> 'normal' OR is_changed IS TRUE OR change_type <> 'none' OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_dk_result_remaining_changed_rows', COUNT(*)::BIGINT
FROM survey_dk_result
WHERE result_status <> 'normal' OR is_changed IS TRUE OR change_type <> 'none' OR change_reason IS NOT NULL
UNION ALL
SELECT 'survey_change_records_remaining_rows', COUNT(*)::BIGINT
FROM survey_change_records
UNION ALL
SELECT 'survey_change_diffs_remaining_rows', COUNT(*)::BIGINT
FROM survey_change_diffs;
