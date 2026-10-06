# -*- coding: utf-8 -*-
"""生成「界址点 / 界址线维护」入口闸门的浏览器验收上下文（供 e2e_boundary_gate.mjs 读取）。

只读脚本。挑一个「active 批次 + 未确认 + ≥2 块有图形的地块」的承包户：
地块多，才能在同一个弹窗里同时对照
  · 自己的正常地块 → 按钮必须**可点**（反例对照，证明闸门没把正常路径一起关掉）
  · 互换换入的对方地块（待保存预览行）→ 按钮必须**禁用**并给出原因
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.update({
    "DATABASE_HOST": "127.0.0.1",
    "DATABASE_PORT": "15432",
    "DATABASE_NAME": "erlunyanbao",
    "DATABASE_USER": "RurallandContractExtension",
    "DATABASE_PASSWORD": "dK9venBRbBRewDFAWYHRGdCM",
    "SECRET_KEY": "verify-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import app.main  # noqa: F401,E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.services.auth_service import auth_service  # noqa: E402
from app.services.survey import survey_service  # noqa: E402

OUT = ROOT / "runtime/.state/_e2e_boundary_gate_ctx.json"


def main() -> None:
    db = SessionLocal()
    admin = auth_service.get_current_user(db, 1)
    set_current_user(db, admin)

    batches = db.execute(text(
        "SELECT id, batch_no, region_name, status FROM survey_batches "
        "WHERE status = 'active' ORDER BY id"
    )).all()
    print("active 批次:", [tuple(row) for row in batches])

    picked = None
    for batch in batches:
        rows = db.execute(text(
            """
            SELECT t.contractor_uid, t.cbfbm, t.task_status
            FROM survey_cbf_base t
            WHERE t.batch_id = :bid
            ORDER BY t.id
            LIMIT 200
            """
        ), {"bid": batch.id}).all()
        for row in rows:
            try:
                result = survey_service._get_result(db, batch.id, row.contractor_uid)
            except HTTPException:
                continue
            if result.survey_status == "confirmed" or result.result_status in {"cancelled", "extinct"}:
                continue
            parcels = db.execute(text(
                """
                SELECT r.dkbm, r.result_status, d.geom IS NOT NULL AS has_geom
                FROM survey_cbdkxx_result r
                JOIN survey_dk_result d ON d.dkbm = r.dkbm
                WHERE r.cbfbm = :cbfbm
                  AND r.result_status NOT IN ('removed', 'split_source')
                  AND d.result_status <> 'removed'
                ORDER BY r.dkbm
                """
            ), {"cbfbm": result.cbfbm}).all()
            usable = [p for p in parcels if p.has_geom]
            if len(usable) >= 2:
                picked = {
                    "batchId": batch.id,
                    "batchName": batch.region_name or batch.batch_no,
                    "household": {
                        "cbfbm": result.cbfbm,
                        "contractorUid": row.contractor_uid,
                        "cbfmc": result.cbfmc,
                        "groupRegionCode": result.group_region_code or result.region_code,
                    },
                    "parcels": [{"dkbm": p.dkbm, "resultStatus": p.result_status} for p in usable],
                }
                break
        if picked:
            break

    db.close()
    if not picked:
        raise SystemExit("找不到「active 批次 + 未确认 + ≥2 块有图形地块」的承包户")

    picked["token"] = create_access_token("1")
    picked["userName"] = admin.real_name
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(picked, ensure_ascii=False, indent=2))
    print("写入:", OUT)


if __name__ == "__main__":
    main()
