"""把 `users.region_id`（所属区域）按确定性口径重算并归位。

背景：`user_service._get_home_region_from_permissions` 旧实现取“授权列表第一条”，
而该列表顺序由前端提交顺序决定 ⇒ 一次「取消再勾回」就能让所属区域漂移。
修复后口径为「授权码里层级最高（码最短）的那条」。

本脚本是**幂等**运维脚本：先扫描差异、备份原值、再更新、最后回读确认。
只动 `users.region_id`，不碰授权行、不碰 tenant_code。
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        continue
    key, value = text.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select, update  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.region_repository import region_repository  # noqa: E402
from app.services.user_service import user_service  # noqa: E402

DRY_RUN = "--apply" not in sys.argv

db = SessionLocal()
try:
    plan = []
    for user in db.scalars(select(User).order_by(User.id)).all():
        code = user_service._home_region_code(list(user.region_permissions))
        if not code:
            continue
        lookup = code[:12] if len(code) >= 12 else code
        target = region_repository.get_region_by_code(db, lookup)
        if target is None or target.id == user.region_id:
            continue
        plan.append(
            {
                "userId": user.id,
                "username": user.username,
                "fromRegionId": user.region_id,
                "fromRegion": user.region.full_name if user.region else None,
                "toRegionId": target.id,
                "toRegion": target.full_name,
                "regionCodes": sorted(item.region_code for item in user.region_permissions),
            }
        )

    print(f"扫描完成：{len(plan)} 个用户所属区域需要归位")
    for item in plan:
        print(
            f"  {item['username']}(id={item['userId']}): "
            f"{item['fromRegion']} -> {item['toRegion']}  [授权 {item['regionCodes']}]"
        )

    if not plan:
        print("无需修改。")
    elif DRY_RUN:
        print("\n当前为预览模式（未改库）。加 --apply 执行。")
    else:
        backup_path = ROOT / "runtime" / ".state" / f"_home_region_fix_{datetime.now():%Y%m%d%H%M%S}.json"
        backup_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n原值已备份到: {backup_path}")
        for item in plan:
            db.execute(update(User).where(User.id == item["userId"]).values(region_id=item["toRegionId"]))
        db.commit()
        print("已提交。回读确认：")
        for item in plan:
            fresh = db.get(User, item["userId"])
            db.refresh(fresh)
            flag = "OK" if fresh.region_id == item["toRegionId"] else "FAILED"
            print(f"  {fresh.username}: region_id={fresh.region_id} ({fresh.region.full_name}) {flag}")
finally:
    db.close()
