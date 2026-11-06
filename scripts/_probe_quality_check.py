# -*- coding: utf-8 -*-
"""质检服务端到端试跑：对真实批次跑一遍质检，打印计数与样例记录。"""
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
env_file = PROJECT / "runtime" / ".state" / "runtime.env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(PROJECT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models.survey import SurveyBatch, SurveyQualityCheckRecord  # noqa: E402
from app.services.survey import quality_check as qc  # noqa: E402

db = SessionLocal()
# 新表还没经历后端启动（bootstrap create_all），探针里先补建
SurveyQualityCheckRecord.__table__.create(db.bind, checkfirst=True)
# 清掉上次探针试跑的记录，避免累加
db.query(SurveyQualityCheckRecord).filter(SurveyQualityCheckRecord.run_id == "probe-run-0001").delete()
db.commit()
batch = db.query(SurveyBatch).order_by(SurveyBatch.id.desc()).first()
if batch is None:
    print("NO BATCH")
    sys.exit(0)
print(f"batch: id={batch.id} no={batch.batch_no} name={batch.batch_name} region={batch.region_code} tenant={batch.tenant_code}")

ctx = qc._load_run_context(db, batch)
print(f"households={len(ctx['bases'])} members={len(ctx['members'])} fbf={len(ctx['fbf_pairs'])} "
      f"dk={len(ctx['dk_pairs'])} cbdk={len(ctx['cbdk_pairs'])} contracts={len(ctx['contract_numbers'])} "
      f"relationCodes={len(ctx['relation_codes'])} geomMissing={len(ctx['geom_missing_ids'])}")

writer = qc._RecordWriter(db, "probe-run-0001", batch, 1)


def tick():
    pass


qc._check_card_no(ctx, writer, tick)
qc._check_fbf(ctx, writer, tick)
qc._check_cbf(ctx, writer, tick)
qc._check_land(ctx, writer, tick)
qc._check_contract(ctx, writer, tick)
writer.flush()

print("counts:", writer.counts)
print("perItem:", writer.per_item)
rows = (db.query(SurveyQualityCheckRecord)
        .filter(SurveyQualityCheckRecord.run_id == "probe-run-0001")
        .order_by(SurveyQualityCheckRecord.id.asc()).all())
from collections import Counter
print("message categories:")
for (item, sev), n in Counter((r.check_item, r.severity) for r in rows).most_common():
    print(f"  [{sev}] {item}: {n}")
for item in ("cbf", "land"):
    sample = [r.message for r in rows if r.check_item == item][:6]
    print(f"sample {item}:")
    for msg in sample:
        print("   ", msg)
# 探井记录不留在库里（正式质检由接口触发，run_id 是 uuid）
db.query(SurveyQualityCheckRecord).filter(SurveyQualityCheckRecord.run_id == "probe-run-0001").delete()
db.commit()
db.close()
db.rollback()
db.close()
print("PROBE OK")
