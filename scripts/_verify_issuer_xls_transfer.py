# -*- coding: utf-8 -*-
"""离线验证发包方调查表 Excel 导出/预览链路（只读，不落库）。"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

# ⛔ config.py 的 database_port 默认 5432 是错的（本机可移植 PG 在 15432），
#    必须在 import app 之前注入（与 start-all-dev.ps1 同源口径）。
os.environ.setdefault("DATABASE_PORT", "15432")

import app.main  # noqa: F401,E402  确保全部 ORM 模型注册
from app.db.session import SessionLocal  # noqa: E402
from app.models.survey import SurveyBatch  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.survey import survey_service  # noqa: E402

db = SessionLocal()
try:
    batch = db.query(SurveyBatch).filter(SurveyBatch.status == "active").order_by(SurveyBatch.id.desc()).first()
    if batch is None:
        print("NO_ACTIVE_BATCH")
        sys.exit(0)
    user = db.get(User, 1)
    print(f"batch={batch.id} region={batch.region_code} name={batch.region_name!r}")

    filename, content = survey_service.export_issuers_xls(db, batch.id, user)
    print(f"export ok: {filename} bytes={len(content)}")

    with open(os.path.join(os.path.dirname(__file__), "_issuer_xls_roundtrip.xls"), "wb") as f:
        f.write(content)

    preview = survey_service.preview_issuers_xls_import(db, batch.id, user, content)
    print("preview summary:", preview["summary"])
    print("warnings:", preview["warnings"])
    for row in preview["issuers"][:5]:
        print("  row", row["rowIndex"], row["code"], row["name"], row["action"], row.get("changes"), row["errors"])
    print("ROUNDTRIP_OK")
finally:
    db.close()
