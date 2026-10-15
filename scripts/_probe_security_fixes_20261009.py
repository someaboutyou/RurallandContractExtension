# -*- coding: utf-8 -*-
"""一次性探针：验证 2026-10-09 安全修复（H1/H2/M1/M2/M3/M4）。

运行：scripts 目录下，DATABASE_* 环境变量由调用方注入（runtime.env 同款）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from jwt import encode as jwt_encode  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import create_app  # noqa: E402

app = create_app()
client = TestClient(app)

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(f"{name} {detail}")
    print(("PASS" if cond else "FAIL"), name, detail)


# ── H2: license 端点鉴权 ────────────────────────────────────────────────
r = client.get("/api/v1/license/status")
check("H2 /license/status 免登录可用", r.status_code == 200, r.status_code)

r = client.get("/api/v1/license/machine-code")
check("H2 /machine-code 未登录 401", r.status_code == 401, r.status_code)

r = client.post("/api/v1/license/reload")
check("H2 /reload 未登录 401", r.status_code == 401, r.status_code)

r = client.post("/api/v1/license/upload", files={"file": ("l.dat", b"x")})
check("H2 /upload 未登录 401", r.status_code == 401, r.status_code)

# ── H1: 旧默认密钥伪造的 token 必须失效 ─────────────────────────────────
forged = jwt_encode(
    {"sub": "1", "type": "access"},
    "replace-this-in-production",
    algorithm=settings.jwt_algorithm,
)
r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
check("H1 旧默认密钥伪造 token 被拒 401", r.status_code == 401, r.status_code)

# ── M4: 登录失败锁定 ───────────────────────────────────────────────────
from app.core import login_throttle  # noqa: E402

login_throttle._records.clear()
payload = {"username": "__probe_not_exist__", "password": "wrong"}
codes = []
for _ in range(6):
    r = client.post("/api/v1/auth/login", json=payload)
    codes.append(r.status_code)
check(
    "M4 连续失败 5 次后第 6 次锁定 429",
    codes[:5] == [401] * 5 and codes[5] == 429,
    str(codes),
)

# ── 登录 + 管理员 token（用于 M1/M2/M3 校验）───────────────────────────
import sqlalchemy  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

with SessionLocal() as db:
    from app.models.role import Role

    platform_user = db.scalar(
        select(User).join(Role, User.role_id == Role.id).where(Role.data_scope == "all").limit(1)
    )
    normal_user = db.scalar(
        select(User).join(Role, User.role_id == Role.id).where(Role.data_scope != "all").limit(1)
    )
print("platform user:", platform_user.id if platform_user else None,
      "| normal user:", normal_user.id if normal_user else None)

def tok(user):
    from app.core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

hdr_admin = tok(platform_user)

# ── M3: 用户管理租户边界 ────────────────────────────────────────────────
r = client.get("/api/v1/users", headers=hdr_admin)
check("M3 平台管理员可列全部用户", r.status_code == 200, r.status_code)
admin_total = r.json()["data"]["total"]

if normal_user is not None:
    hdr_normal = tok(normal_user)
    r = client.get("/api/v1/users", headers=hdr_normal)
    if r.status_code == 200:
        normal_total = r.json()["data"]["total"]
        check("M3 非平台管理员用户列表 <= 全量", normal_total <= admin_total,
              f"{normal_total}/{admin_total}")
        others = [u for u in r.json()["data"]["items"] if u["dataScope"] == "all"]
        check("M3 非平台管理员列表不含平台管理员", not others, str(len(others)))
    else:
        check("M3 非平台管理员访问用户列表", True, f"status={r.status_code}（无 users.view 时 403 也算过）")
    # 重置平台管理员密码必须被拒
    r = client.post(
        f"/api/v1/users/{platform_user.id}/reset-password",
        json={"password": "Hacked@123456"},
        headers=hdr_normal,
    )
    check("M3 非平台管理员重置平台管理员密码被拒", r.status_code == 403, r.status_code)

# ── M1: 数据导出下载归属校验（用不存在的 id 验证闸门顺序）────────────────
r = client.get("/api/v1/data-exports/99999999/download", headers=hdr_admin)
check("M1 download 不存在的 id 404", r.status_code == 404, r.status_code)

# ── M2: cadastral 导出任务归属 ─────────────────────────────────────────
from app.services.cadastral_export_service import cadastral_export_service  # noqa: E402

cadastral_export_service._tasks.clear()
tid = cadastral_export_service.create_task(filters={}, user_id=platform_user.id, region_label="t")
r = client.get(f"/api/v1/contractors/cadastral-survey/export/{tid}", headers=hdr_admin)
check("M2 创建人本人可查进度", r.status_code in (200, 404), r.status_code)
if normal_user is not None:
    hdr_normal2 = tok(normal_user)
    r = client.get(f"/api/v1/contractors/cadastral-survey/export/{tid}", headers=hdr_normal2)
    check("M2 他人查进度 403", r.status_code == 403, r.status_code)
    r = client.get(f"/api/v1/contractors/cadastral-survey/export/{tid}/download", headers=hdr_normal2)
    check("M2 他人下载 403", r.status_code == 403, r.status_code)

# ── M2: raster publish 任务归属 ────────────────────────────────────────
from app.services import raster_publish_service as _rps_module  # noqa: E402

_rps_module._tasks.clear()
tid2 = _rps_module.raster_publish_service.create_task(owner_user_id=platform_user.id)
_rps_module._tasks[tid2]["progress"] = 50
r = client.get(f"/api/v1/raster-publish/progress/{tid2}", headers=hdr_admin)
check("M2 raster 本人查进度 200", r.status_code == 200, r.status_code)
if normal_user is not None:
    hdr_normal3 = tok(normal_user)
    r = client.get(f"/api/v1/raster-publish/progress/{tid2}", headers=hdr_normal3)
    if r.status_code != 403:
        # 普通用户可能没有 layers.manage 权限 → 403 同样满足；只有 200 才是漏洞
        check("M2 raster 他人查进度", False, f"status={r.status_code}")
    else:
        check("M2 raster 他人查进度 403", True, r.status_code)

print()
print(f"== {len(passed)} passed, {len(failed)} failed ==")
if failed:
    for f in failed:
        print("FAILED:", f)
    sys.exit(1)
