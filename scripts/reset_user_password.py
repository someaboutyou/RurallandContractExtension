# -*- coding: utf-8 -*-
"""运维工具：重置指定用户的登录密码（弱口令轮换用，2026-10-09 审计跟进）。

用法（在项目根目录）：
    runtime\\windows\\python\\python.exe scripts\\reset_user_password.py <用户名> <新密码>

- 数据库连接自动读取 runtime/.state/runtime.env（无需手动 export）。
- 新密码走与后端一致的强度校验（≥8 位、字母+数字、拒绝常见弱口令）。
- 只改密码，不动角色 / 区域 / 状态。
- 可用 `--list` 列出所有用户及其密码是否命中常见弱口令（只读）。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ⛔ 先注入环境变量再 import app（config.py 在 import 时读 .env / 环境变量）。
_runtime_env = PROJECT_ROOT / "runtime" / ".state" / "runtime.env"
if _runtime_env.exists():
    for line in _runtime_env.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

# ⛔ 布局自适应：源码布局 app 在 backend/，编译布局（生产部署）在 backend/dist/app。
# 源码存在时优先源码，否则落到编译版。
_backend_root = PROJECT_ROOT / "backend"
for _candidate in (_backend_root / "dist", _backend_root):
    if (_candidate / "app").exists():
        sys.path.insert(0, str(_candidate))
if not any((p / "app").exists() for p in (_backend_root, _backend_root / "dist")):
    print(f"找不到 app 包：{_backend_root} 与 {_backend_root / 'dist'} 下均无 app/，请确认部署布局")
    sys.exit(3)

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password, verify_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.user_service import user_service  # noqa: E402

_WEAK = [
    "Admin123456", "admin123", "12345678", "123456789", "password1",
    "Aa123456", "admin@123", "qwerty123", "1qaz2wsx", "Admin@123",
    "88888888", "66666666", "00000000", "123123123", "abc12345",
]


def list_users() -> int:
    with SessionLocal() as db:
        users = db.scalars(select(User)).all()
        print(f"{'id':>4}  {'用户名':<20} {'角色':<18} 状态    弱口令命中")
        for user in users:
            hits = [pwd for pwd in _WEAK if verify_password(pwd, user.password_hash)]
            flag = ",".join(hits) if hits else "-"
            print(f"{user.id:>4}  {user.username:<20} {user.role.code if user.role else '?':<18} {user.status:<6}  {flag}")
    return 0


def reset(username: str, password: str) -> int:
    try:
        user_service._validate_password(password)
    except Exception as exc:
        print(f"新密码不合规：{exc}")
        return 2
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            print(f"用户不存在：{username}")
            return 1
        user.password_hash = hash_password(password)
        db.commit()
        print(f"已重置 {username}（id={user.id}）的密码。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="重置用户登录密码 / 巡检弱口令")
    parser.add_argument("username", nargs="?", help="用户名（留空配合 --list 巡检）")
    parser.add_argument("password", nargs="?", help="新密码")
    parser.add_argument("--list", action="store_true", help="只读巡检：列出全部用户与弱口令命中")
    args = parser.parse_args()
    if args.list:
        return list_users()
    if not args.username or not args.password:
        parser.error("需要 <用户名> <新密码>，或使用 --list 巡检")
    return reset(args.username, args.password)


if __name__ == "__main__":
    sys.exit(main())
