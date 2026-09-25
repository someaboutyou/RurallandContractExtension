"""验证：程序初始化（seed）不再冲掉运维改过的数据。

做两件事：
  A. 空库首次 bootstrap —— 必须能完整初始化；
  B. 模拟运维改动后再 bootstrap（等价于"重启程序"）—— 改动必须全部保留。

全程使用独立的临时库（见 TEST_DB），**不碰开发库 erlunyanbao**。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_verify_seed_idempotent.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "runtime" / ".state" / "runtime.env"
TEST_DB = "erlunyanbao_seedverify"
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_seed_result.json"

CHANGED_LAYER_URL = "https://example.com/operator-changed/{z}/{x}/{y}.png"
CHANGED_GROUP_CODES = ("32132410000102", "32132410000103")


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    # 源码/配置文件带 BOM，必须用 utf-8-sig
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


env = load_env()
HOST = env["DATABASE_HOST"]
PORT = int(env["DATABASE_PORT"])
DB_USER = env["DATABASE_USER"]
DB_PWD = env["DATABASE_PASSWORD"]

import psycopg  # noqa: E402

# ---- 1. 重建临时库 ---------------------------------------------------------
with psycopg.connect(
    f"host={HOST} port={PORT} user={DB_USER} password={DB_PWD} dbname=postgres",
    autocommit=True,
) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,))
        if cur.fetchone():
            cur.execute(f'DROP DATABASE "{TEST_DB}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{TEST_DB}"')

# ---- 2. 让 app 连到临时库（必须在 import app 之前注入） --------------------
os.environ["DATABASE_HOST"] = HOST
os.environ["DATABASE_PORT"] = str(PORT)
os.environ["DATABASE_USER"] = DB_USER
os.environ["DATABASE_PASSWORD"] = DB_PWD
os.environ["DATABASE_NAME"] = TEST_DB

sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import delete, func, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.bootstrap import bootstrap_database  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.dictionary import DictionaryItem  # noqa: E402
from app.models.map_layer import MapLayer  # noqa: E402
from app.models.permission import Permission  # noqa: E402
from app.models.region import Region  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_region_permission import UserRegionPermission  # noqa: E402

checks: list[dict] = []
notes: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def perms_of(db, username: str) -> set[str]:
    user = db.scalar(select(User).where(User.username == username))
    rows = db.scalars(
        select(UserRegionPermission).where(UserRegionPermission.user_id == user.id)
    ).all()
    return {row.region_code for row in rows}


def write_result(exit_code: int) -> None:
    payload = {
        "testDatabase": TEST_DB,
        "actualDatabaseInUse": settings.database_name,
        "passed": sum(1 for item in checks if item["ok"]),
        "failed": sum(1 for item in checks if not item["ok"]),
        "checks": checks,
        "notes": notes,
    }
    RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if settings.database_name != TEST_DB:
    check("临时库已生效（settings.database_name）", False, f"{settings.database_name} != {TEST_DB}")
    write_result(2)
    raise SystemExit(2)

# ==== A. 空库首次 bootstrap =================================================
bootstrap_database()
with SessionLocal() as db:
    check(
        "空库初始化：表与基础数据已建",
        count(db, Region) > 0 and count(db, Role) > 0 and count(db, Permission) > 0,
        f"regions={count(db, Region)} roles={count(db, Role)} perms={count(db, Permission)}",
    )
    check("空库初始化：图层已创建", count(db, MapLayer) > 0, count(db, MapLayer))
    check("空库初始化：字典已创建", count(db, DictionaryItem) > 0, count(db, DictionaryItem))

# 真实部署里 regions 由 fbf 业务数据同步而来（省/市/县/镇/村/组）。
# 空库没有业务数据，DEFAULT_USERS 里镇/村级的用户会因目标区域不存在被跳过 —— 这是既有行为，
# 与本次改造无关。这里补两条区域再跑一次 bootstrap，等价于"业务数据到位后重启程序"。
with SessionLocal() as db:
    county = db.scalar(select(Region).where(Region.code == "321324"))
    town = Region(
        name="青阳镇",
        code="321324100",
        level="town",
        full_name="导入数据 / 泗洪县 / 青阳镇",
        parent_id=county.id,
        tenant_code="321324",
    )
    db.add(town)
    db.flush()
    db.add(
        Region(
            name="城东居",
            code="321324100001",
            level="village",
            full_name="导入数据 / 泗洪县 / 青阳镇 / 城东居",
            parent_id=town.id,
            tenant_code="321324",
        )
    )
    db.commit()

bootstrap_database()
with SessionLocal() as db:
    check("区域补齐后 bootstrap：默认用户全部创建", count(db, User) >= 7, count(db, User))
    check(
        "区域补齐后 bootstrap：group_scope_user 拿到预设授权",
        perms_of(db, "group_scope_user") == {"32132410000101"},
        sorted(perms_of(db, "group_scope_user")),
    )

# ==== B. 模拟运维改动 =======================================================
with SessionLocal() as db:
    group_user = db.scalar(select(User).where(User.username == "group_scope_user"))
    # ① 改数据权限区域：整组换掉（正是用户报告的场景）
    db.execute(delete(UserRegionPermission).where(UserRegionPermission.user_id == group_user.id))
    for code in CHANGED_GROUP_CODES:
        db.add(
            UserRegionPermission(
                user_id=group_user.id,
                tenant_code=code[:6],
                region_code=code,
                level="group",
            )
        )
    # ② 改用户资料
    group_user.real_name = "组级测试员（已改名）"
    group_user.mobile = "13900009999"

    # ③ 把另一个用户的授权全部清空（旧实现会在重启时凭 users.region_id 重建）
    village_user = db.scalar(select(User).where(User.username == "village_auditor"))
    db.execute(delete(UserRegionPermission).where(UserRegionPermission.user_id == village_user.id))

    # ④ 改管理员姓名
    admin = db.scalar(select(User).where(User.username == "admin"))
    admin.real_name = "超级管理员（已改名）"

    # ⑤ 改底图地址
    layer = db.scalar(select(MapLayer).where(MapLayer.key == "image"))
    layer.service_url = CHANGED_LAYER_URL

    # ⑥ 改权限点文案
    perm = db.scalar(select(Permission).where(Permission.code == "dashboard.view"))
    perm.name = "查看工作台（已改名）"

    # ⑦ 运维手工补录字典项
    db.add(
        DictionaryItem(
            dict_type="op_custom_test",
            dict_name="运维自建字典",
            item_value="x1",
            item_name="自定义项",
            sort_order=1,
            enabled=True,
            remark="手工补录，不该被初始化冲掉",
            tenant_code=None,
        )
    )

    # ⑧ 从角色上摘掉一个权限
    role = db.scalar(select(Role).where(Role.code == "town_auditor"))
    role.permissions = [item for item in role.permissions if item.code != "issuers.view"]

    db.commit()

with SessionLocal() as db:
    notes.append(f"改动后 group_scope_user 授权 = {sorted(perms_of(db, 'group_scope_user'))}")
    notes.append(f"改动后 village_auditor 授权 = {sorted(perms_of(db, 'village_auditor'))}")

# ==== C. 再跑一次 bootstrap（等价于重启程序） ==============================
bootstrap_database()

with SessionLocal() as db:
    check(
        "重启后：改过的数据权限区域保留（未回滚成预设）",
        perms_of(db, "group_scope_user") == set(CHANGED_GROUP_CODES),
        sorted(perms_of(db, "group_scope_user")),
    )
    group_user = db.scalar(select(User).where(User.username == "group_scope_user"))
    check("重启后：用户姓名未被覆盖", group_user.real_name == "组级测试员（已改名）", group_user.real_name)
    check("重启后：用户手机号未被覆盖", group_user.mobile == "13900009999", group_user.mobile)

    admin = db.scalar(select(User).where(User.username == "admin"))
    check("重启后：管理员姓名未被覆盖", admin.real_name == "超级管理员（已改名）", admin.real_name)

    check(
        "重启后：被清空的授权未被兜底重建",
        perms_of(db, "village_auditor") == set(),
        sorted(perms_of(db, "village_auditor")),
    )

    layer = db.scalar(select(MapLayer).where(MapLayer.key == "image"))
    check("重启后：底图地址未被覆盖", layer.service_url == CHANGED_LAYER_URL, layer.service_url)

    perm = db.scalar(select(Permission).where(Permission.code == "dashboard.view"))
    check("重启后：权限点文案未被覆盖", perm.name == "查看工作台（已改名）", perm.name)

    custom = db.scalar(
        select(DictionaryItem).where(DictionaryItem.dict_type == "op_custom_test")
    )
    check("重启后：运维补录的字典项仍在", custom is not None, custom.item_name if custom else None)

    role = db.scalar(select(Role).where(Role.code == "town_auditor"))
    codes = {item.code for item in role.permissions}
    check("重启后：从角色摘掉的权限未被回灌", "issuers.view" not in codes, len(codes))

failed = [item for item in checks if not item["ok"]]
write_result(0 if not failed else 1)

# ---- 3. 清理临时库（仅全部通过时） ----------------------------------------
if not failed:
    with psycopg.connect(
        f"host={HOST} port={PORT} user={DB_USER} password={DB_PWD} dbname=postgres",
        autocommit=True,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE "{TEST_DB}" WITH (FORCE)')
    print(f"[cleanup] dropped {TEST_DB}")
else:
    print(f"[keep] 验证未全通过，保留临时库 {TEST_DB} 供复查")

raise SystemExit(1 if failed else 0)
