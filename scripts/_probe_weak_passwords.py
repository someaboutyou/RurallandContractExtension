# -*- coding: utf-8 -*-
"""弱口令实测：对库内全部 active 用户试常见弱口令（只读，不改任何数据）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.security import verify_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

WEAK = [
    "Admin123456", "admin123", "12345678", "123456789", "password1",
    "Aa123456", "admin@123", "qwerty123", "1qaz2wsx", "Admin@123",
    "88888888", "66666666", "00000000", "123123123", "abc12345",
]

with SessionLocal() as db:
    users = db.scalars(select(User)).all()
    print(f"total users: {len(users)}")
    weak_hits = []
    for user in users:
        if user.status != "active":
            continue
        hit = [pwd for pwd in WEAK if verify_password(pwd, user.password_hash)]
        if hit:
            weak_hits.append((user.username, user.role.code if user.role else "?", hit))
    if weak_hits:
        print("WEAK PASSWORDS FOUND:")
        for username, role, hit in weak_hits:
            print(f"  {username} ({role}): {hit}")
    else:
        print("no weak passwords found")
