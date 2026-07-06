-- ============================================================
-- Migration: base/result 关系反转 + task 表合并到 base
-- 执行前请备份数据库，停服执行
-- ============================================================

BEGIN;

-- ========== Part A: base 表加 result_id ==========

ALTER TABLE survey_cbf_base ADD COLUMN IF NOT EXISTS result_id INTEGER;
ALTER TABLE survey_cbf_jtcy_base ADD COLUMN IF NOT EXISTS result_id INTEGER;
ALTER TABLE survey_fbf_base ADD COLUMN IF NOT EXISTS result_id INTEGER;
ALTER TABLE survey_cbdkxx_base ADD COLUMN IF NOT EXISTS result_id INTEGER;
ALTER TABLE survey_dk_base ADD COLUMN IF NOT EXISTS result_id INTEGER;

-- 从 result.base_id 反向填充 base.result_id
UPDATE survey_cbf_base b SET result_id = r.id
  FROM survey_cbf_result r WHERE r.base_id = b.id;
UPDATE survey_cbf_jtcy_base b SET result_id = r.id
  FROM survey_cbf_jtcy_result r WHERE r.base_id = b.id;
UPDATE survey_fbf_base b SET result_id = r.id
  FROM survey_fbf_result r WHERE r.base_id = b.id;
UPDATE survey_cbdkxx_base b SET result_id = r.id
  FROM survey_cbdkxx_result r WHERE r.base_id = b.id;
UPDATE survey_dk_base b SET result_id = r.id
  FROM survey_dk_result r WHERE r.base_id = b.id;

-- 添加 NOT NULL 约束（jtcy 除外）
ALTER TABLE survey_cbf_base ALTER COLUMN result_id SET NOT NULL;
ALTER TABLE survey_fbf_base ALTER COLUMN result_id SET NOT NULL;
ALTER TABLE survey_cbdkxx_base ALTER COLUMN result_id SET NOT NULL;
ALTER TABLE survey_dk_base ALTER COLUMN result_id SET NOT NULL;

-- ========== Part B: task 数据迁入 base ==========

ALTER TABLE survey_cbf_base ADD COLUMN IF NOT EXISTS task_status VARCHAR(32) NOT NULL DEFAULT 'not_started';
ALTER TABLE survey_cbf_base ADD COLUMN IF NOT EXISTS has_change BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE survey_cbf_base ADD COLUMN IF NOT EXISTS change_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE survey_cbf_base ADD COLUMN IF NOT EXISTS assigned_to INTEGER;
ALTER TABLE survey_cbf_base ADD COLUMN IF NOT EXISTS assigned_to_name VARCHAR(50);
ALTER TABLE survey_cbf_base ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ;
ALTER TABLE survey_cbf_base ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE survey_cbf_base ADD COLUMN IF NOT EXISTS skip_reason TEXT;

UPDATE survey_cbf_base b SET
  task_status    = t.task_status,
  has_change     = t.has_change,
  change_count   = t.change_count,
  assigned_to    = t.assigned_to,
  assigned_to_name = t.assigned_to_name,
  assigned_at    = t.assigned_at,
  reviewed_at    = t.reviewed_at,
  skip_reason    = t.skip_reason
FROM survey_contractor_tasks t
WHERE t.batch_id = b.batch_id AND t.contractor_uid = b.contractor_uid;

-- ========== Part C: 删 result 旧字段 ==========

ALTER TABLE survey_cbf_result DROP COLUMN IF EXISTS base_id;
ALTER TABLE survey_cbf_result DROP COLUMN IF EXISTS initialized_from_base_id;
ALTER TABLE survey_cbf_jtcy_result DROP COLUMN IF EXISTS base_id;
ALTER TABLE survey_cbf_jtcy_result DROP COLUMN IF EXISTS initialized_from_base_id;
ALTER TABLE survey_fbf_result DROP COLUMN IF EXISTS base_id;
ALTER TABLE survey_fbf_result DROP COLUMN IF EXISTS initialized_from_base_id;
ALTER TABLE survey_cbdkxx_result DROP COLUMN IF EXISTS base_id;
ALTER TABLE survey_cbdkxx_result DROP COLUMN IF EXISTS initialized_from_base_id;
ALTER TABLE survey_dk_result DROP COLUMN IF EXISTS base_id;
ALTER TABLE survey_dk_result DROP COLUMN IF EXISTS initialized_from_base_id;

-- ========== Part D: 删 task 表 ==========

DROP TABLE IF EXISTS survey_contractor_tasks;

COMMIT;
