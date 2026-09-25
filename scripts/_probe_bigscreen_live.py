"""探针：对**运行中的 8000 实例**验证大屏权限链路与接口可用性（只读）。

与 `_verify_bigscreen_dashboard.py` 的区别：那个用进程内 TestClient 验新代码逻辑，
这个打真实监听端口，用来回答"用户现在能不能打开大屏"。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_probe_bigscreen_live.py

检查四项：
  A 权限点 `dashboard.bigscreen` 是否入库
  B 它挂在哪些角色上（期望：只有 platform_admin）
  C 管理员 /auth/me 返回的 permissions 是否包含它（前端菜单与路由守卫就靠这个字段）
  D 管理员调 /dashboard/bigscreen 是否 200
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
PERM = "dashboard.bigscreen"


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


for _key, _value in load_env().items():
    os.environ.setdefault(_key, _value)
os.environ.setdefault("SECRET_KEY", "verify-only")

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from sqlalchemy import text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.session import engine  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    ok = ok and passed
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}" + (f"  -- {detail}" if detail else ""))


def call(path: str, token: str | None = None) -> tuple[int, object]:
    req = urllib.request.Request(BASE + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> None:
    print("== A 权限点是否入库 ==")
    with engine.connect() as conn:
        perm_row = conn.execute(
            text("SELECT id, name, code, category, group_name FROM permissions WHERE code = :c"),
            {"c": PERM},
        ).mappings().first()
    check(f"permissions 存在 {PERM}", perm_row is not None, str(dict(perm_row)) if perm_row else "未入库")
    if perm_row is None:
        return

    print("== B 权限挂在哪些角色 ==")
    with engine.connect() as conn:
        roles = conn.execute(
            text(
                "SELECT r.id, r.code, r.name FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id WHERE rp.permission_id = :pid ORDER BY r.code"
            ),
            {"pid": perm_row["id"]},
        ).mappings().all()
    role_codes = [r["code"] for r in roles]
    check("只授予 platform_admin", role_codes == ["platform_admin"], f"实际 = {role_codes}")

    print("== C/D 以管理员身份打真实端口 ==")
    with engine.connect() as conn:
        admin = conn.execute(
            text(
                "SELECT u.id, u.username FROM users u JOIN roles r ON r.id = u.role_id "
                "WHERE r.code = 'platform_admin' ORDER BY u.id LIMIT 1"
            )
        ).mappings().first()
    if admin is None:
        check("找到 platform_admin 用户", False, "库里没有该角色用户")
        return
    token = create_access_token(str(admin["id"]))
    print(f"  (以 {admin['username']} / user_id={admin['id']} 身份请求)")

    status, me = call("/auth/me", token)
    if status != 200 or not isinstance(me, dict):
        check("/auth/me 返回 200", False, f"status={status} body={str(me)[:200]}")
        return
    # ⛔ 接口统一包一层 {"data": ...}：不剥壳会把 permissions 读成空列表 ⇒ 误报"权限没生效"
    if isinstance(me.get("data"), dict):
        me = me["data"]
    print("  /auth/me 顶层字段: " + str(sorted(me.keys())))
    perms = me.get("permissions")
    if not perms:
        print("  /auth/me 原始返回: " + json.dumps(me, ensure_ascii=False)[:900])
    perms = perms or []
    check("/auth/me 200 且返回权限列表", isinstance(perms, list) and len(perms) > 0, f"{len(perms)} 项")
    check(
        f"/auth/me 的 permissions 含 {PERM}（决定菜单与路由守卫）",
        PERM in perms,
        "" if PERM in perms else f"未包含；样例 = {perms[:6]}",
    )

    status, data = call("/dashboard/bigscreen", token)
    check("/dashboard/bigscreen 返回 200", status == 200, f"status={status} body={str(data)[:300]}")
    if status == 200 and isinstance(data, dict):
        payload = data.get("data") if "data" in data else data
        keys = sorted(payload.keys()) if isinstance(payload, dict) else []
        print(f"  返回顶层字段: {keys}")
        ov = (payload or {}).get("overview") or {}
        if ov:
            print("  概览原始: " + json.dumps(ov, ensure_ascii=False)[:600])
        ts = (payload or {}).get("taskStatus")
        if ts:
            print("  任务状态: " + json.dumps(ts, ensure_ascii=False)[:300])

    print()
    print("结论：" + ("全部通过，admin 可正常打开大屏" if ok else "存在失败项，见上"))


if __name__ == "__main__":
    main()
