"""验证 `users.region_id`（所属区域）是否随授权码提交顺序漂移。

只读：不写库。用库里 multi_scope_user 的两条真实授权，按两种顺序各算一次"所属区域"。
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        continue
    key, value = text.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.domain.region_code import normalize_region_codes  # noqa: E402
from app.models.region import Region  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_region_permission import UserRegionPermission  # noqa: E402
from app.services.user_service import user_service  # noqa: E402

TOWN = "321324100"
VILLAGE = "321324101203"

db = SessionLocal()
try:
    user = db.get(User, 6)
    print(f"用户: {user.username}  当前 region_id={user.region_id} ({user.region.full_name})")
    print()

    parent_map = user_service._region_parent_map(db)
    for label, order in (("青阳镇在前", [TOWN, VILLAGE]), ("草湾村在前", [VILLAGE, TOWN])):
        normalized = normalize_region_codes(order, parent_map)
        permissions = []
        for code in normalized:
            permissions.append(
                UserRegionPermission(tenant_code=code[:6], region_code=code, level=user_service._level_by_code(code))
            )
        home = user_service._get_home_region_from_permissions(db, permissions)
        print(f"{label:12s} 提交顺序={order}")
        print(f"{'':12s} 归一化后={normalized}")
        print(f"{'':12s} ⇒ 所属区域 = id={home.id} code={home.code} ({home.full_name})")
        print()

    print("=== 现在直接查库，看落库顺序 ===")
    rows = db.scalars(
        select(UserRegionPermission)
        .where(UserRegionPermission.user_id == 6)
        .order_by(UserRegionPermission.id)
    ).all()
    for row in rows:
        print(f"  id={row.id} region_code={row.region_code} level={row.level}")
finally:
    db.close()
