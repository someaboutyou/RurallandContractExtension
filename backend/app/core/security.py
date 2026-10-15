from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings

# ⛔ 弱口令黑名单（实测本系统曾有 5 个账号用 Admin123456，见 2026-10-09 审计）。
# 校验时统一小写比较。命中即拒绝——新增/重置密码都走 validate_password_strength。
_WEAK_PASSWORDS = frozenset({
    "admin123", "admin1234", "admin12345", "admin123456", "admin@123",
    "12345678", "123456789", "1234567890", "123123123", "11223344",
    "88888888", "66666666", "00000000", "11111111", "99999999",
    "password1", "password8", "passw0rd", "qwerty123", "1qaz2wsx",
    "aa123456", "abc12345", "abcd1234", "a1234567", "p@ssw0rd",
    "zxcvbnm1", "asdfghj1", "qwe12345", "test1234", "root1234",
})


def validate_password_strength(password: str) -> None:
    """新密码强度闸门：≥8 位 + 同时含字母和数字 + 不在弱口令黑名单。

    违规时抛 ValueError（service 层转 400）。种子数据不走此校验
    （hash_password 直接调用），避免初始化流程被策略卡死。
    """
    if not password or len(password) < 8:
        raise ValueError("密码长度至少 8 位")
    if len(password) > 100:
        raise ValueError("密码长度不能超过 100 位")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("密码必须同时包含字母和数字")
    if password.strip().lower() in _WEAK_PASSWORDS:
        raise ValueError("密码过于简单（常见弱口令），请更换")
    # 纯顺序/重复字符的简易识别（如 aaaaa123 / abcdefg1 的变体）
    if len(set(password)) <= 3:
        raise ValueError("密码过于简单（有效字符种类过少），请更换")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, digest_hex = password_hash.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return hmac.compare_digest(actual, expected)


def create_access_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
