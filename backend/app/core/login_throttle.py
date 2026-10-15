# -*- coding: utf-8 -*-
"""登录失败锁定（审计 M4）。

按「用户名 + 来源 IP」做失败计数：连续失败达阈值后锁定一段时间，
锁定期内即使密码正确也拒绝（防在线爆破拖库/撞库）。

实现说明：
- 进程内存态即可：本项目单进程 uvicorn 部署，无需跨进程共享；
  重启后清零（攻击者收益有限——锁定窗口远小于重启成本）。
- 成功登录即清零该 key 的计数。
- 字典做简单容量控制，防止恶意刷大量用户名撑爆内存。
"""

from __future__ import annotations

import threading
import time

#: 连续失败多少次后锁定
MAX_FAILURES = 5
#: 锁定时长（秒）
LOCK_SECONDS = 10 * 60
#: 记录条数上限（超出时清理已过期条目）
MAX_KEYS = 10_000

_lock = threading.Lock()
# key -> [失败次数, 锁定截止时间戳（0 表示未锁定）]
_records: dict[str, list[float]] = {}


def _make_key(username: str, ip: str) -> str:
    return f"{(username or '').strip().lower()}|{ip or 'unknown'}"


def _now() -> float:
    return time.monotonic()


def _evict_expired_locked(now: float) -> None:
    if len(_records) < MAX_KEYS:
        return
    # 优先清理「未锁定且无计数」的死条目
    dead = [key for key, (count, until) in _records.items() if count == 0 and until <= now]
    for key in dead:
        _records.pop(key, None)
    # 仍超限时按最早锁定截止时间淘汰（极端情况兜底）
    if len(_records) >= MAX_KEYS:
        for key, _ in sorted(_records.items(), key=lambda item: item[1][1])[: len(_records) - MAX_KEYS + 1]:
            _records.pop(key, None)


def check_locked(username: str, ip: str) -> int:
    """若该 key 正处于锁定期，返回剩余秒数；否则返回 0。"""
    key = _make_key(username, ip)
    now = _now()
    with _lock:
        record = _records.get(key)
        if record is None:
            return 0
        _count, until = record
        if until > now:
            return int(until - now) + 1
        # 仅当「锁定期刚结束」（until 曾被设置且已过期）才清零计数重新计；
        # until == 0 表示从未锁定，不能动失败计数。
        if until and _count:
            record[0] = 0
        return 0


def record_failure(username: str, ip: str) -> int:
    """记一次失败，返回剩余可尝试次数（达到 0 即进入锁定）。

    ⛔ 固定锁定窗口：已处于锁定期时不再延长 until——否则攻击者持续尝试
    就能把受害账号永久锁死（变成拒绝服务）。
    """
    key = _make_key(username, ip)
    now = _now()
    with _lock:
        _evict_expired_locked(now)
        record = _records.setdefault(key, [0, 0.0])
        if record[1] > now:
            # 已锁定：不计数、不续期
            return 0
        record[0] += 1
        if record[0] >= MAX_FAILURES:
            record[1] = now + LOCK_SECONDS
            return 0
        return MAX_FAILURES - record[0]


def reset(username: str, ip: str) -> None:
    """登录成功后清除计数。"""
    key = _make_key(username, ip)
    with _lock:
        _records.pop(key, None)
