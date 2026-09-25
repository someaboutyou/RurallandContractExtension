"""业务编号序列（batch_no / change_no / restructure_no / authorization_no / import_no）。

为什么不再用 ``max(id) + 1``
--------------------------------------------------------------------------
这几列都带唯一约束，旧实现（``survey/base.py``、``contractor_service.py``、
``data_import/helpers.py`` 三份几乎相同的 ``_next_no``）都是
``SELECT max(id) + 1`` 拼编号，必然踩两个坑：

1. **删行后号段回退**：把最大 id 的那行删掉，``max(id)`` 就退回去了，下一个新建会
   **拿到已经用过的编号**（验收里"建批次 → 删 → 再建"连续三次都是
   ``SUR202609230042``）。批次表眼下没做软删，但"删掉重开"是运维常规动作。
2. **并发撞号**：两个请求同时读到同一个 ``max(id)``，算出同一个编号，提交时撞唯一
   约束（偶发 500，且事后难以复现）。

改用 PostgreSQL 序列：``nextval()`` 原子递增、不随删行回退、并发安全。
序列由程序初始化流程 ``bootstrap_database()`` → ``create_database_schema()`` →
``ensure_business_sequences()`` 建好，并且会把游标**顶到库里已有编号之后**，
所以升级部署到已有数据时不会和历史编号撞号（也只前进、绝不回退）。
``next_serial()`` 里还有一层自愈兜底：进程内没跑过初始化（离线脚本、临时库、
手工 ``create_all``）时补建一次。
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class BusinessSequence:
    """一个业务编号列对应的 PostgreSQL 序列。"""

    prefix: str
    table: str
    column: str

    @property
    def name(self) -> str:
        return f"{self.table}_{self.column}_seq"


# 编号格式统一是 ``<prefix><yyyymmdd><4 位以上流水>``，流水号全局递增、不按天重置
# （旧实现用 max(id) 也从不按天重置，保持行为一致，避免同一天内新旧编号混排错乱）。
BUSINESS_SEQUENCES: tuple[BusinessSequence, ...] = (
    BusinessSequence("SUR", "survey_batches", "batch_no"),
    BusinessSequence("CHG", "survey_change_records", "change_no"),
    BusinessSequence("RST", "survey_household_restructures", "restructure_no"),
    BusinessSequence("AUT", "survey_authorizations", "authorization_no"),
    BusinessSequence("IMP", "data_import_batches", "import_no"),
)

_BY_PREFIX = {spec.prefix: spec for spec in BUSINESS_SEQUENCES}

_SERIAL_PATTERN = re.compile(r"^(?P<prefix>[A-Z]+)(?P<day>\d{8})(?P<serial>\d+)$")

_ensure_lock = threading.Lock()
_ensured = False


def _default_engine() -> Engine:
    # 延迟导入：app.db.session 会反向引用本模块的调用方，顶层导入会绕成环。
    from app.db.session import engine

    return engine


def parse_serial(prefix: str, value: str | None) -> int | None:
    """从已有编号里取出流水号；不符合本前缀格式（如 ``SURLEGACYCBF``）返回 None。"""
    match = _SERIAL_PATTERN.match(str(value or "").strip().upper())
    if match is None or match.group("prefix") != prefix:
        return None
    return int(match.group("serial"))


def ensure_business_sequences(bind: Engine | None = None) -> list[str]:
    """建序列（幂等）并把游标顶到库里已有编号之后。返回本次处理的序列名。

    程序初始化（``bootstrap_database``）会调用它；重复调用安全：已存在的序列不会被
    重建，游标不会被改小。
    """
    global _ensured
    target = bind if bind is not None else _default_engine()
    names: list[str] = []
    with _ensure_lock:
        with target.begin() as connection:
            for spec in BUSINESS_SEQUENCES:
                connection.exec_driver_sql(f"CREATE SEQUENCE IF NOT EXISTS {spec.name}")
                _advance_to_existing(connection, spec)
                names.append(spec.name)
        _ensured = True
    return names


def _existing_floor(connection: Connection, spec: BusinessSequence) -> int:
    """库里已有编号的"已占用下界"：取 ``max(id)`` 与已有编号最大流水号的较大者。

    两个都要取：历史数据的编号流水号 ≈ 建号当时的 max(id)，两者可能不等
    （例如 id=40 的批次编号是 ``...0002``，因为它建号时 max(id) 还是 1）。
    """
    if connection.exec_driver_sql(f"SELECT to_regclass('{spec.table}')").scalar() is None:
        return 0
    floor = int(
        connection.exec_driver_sql(f"SELECT coalesce(max(id), 0) FROM {spec.table}").scalar() or 0
    )
    existing = connection.execute(
        text(f"SELECT {spec.column} FROM {spec.table} WHERE {spec.column} LIKE :pattern"),
        {"pattern": f"{spec.prefix}%"},
    ).scalars().all()
    for value in existing:
        serial = parse_serial(spec.prefix, value)
        if serial is not None and serial > floor:
            floor = serial
    return floor


def _advance_to_existing(connection: Connection, spec: BusinessSequence) -> int:
    """只前进、不回退地设置游标；返回设置后"已占用"的位置。"""
    floor = _existing_floor(connection, spec)
    row = connection.exec_driver_sql(f"SELECT last_value, is_called FROM {spec.name}").first()
    last_value = int(row[0]) if row else 0
    is_called = bool(row[1]) if row else False
    # is_called=False 表示刚建出来还没 nextval 过，此刻 last_value 尚未被占用。
    consumed = last_value if is_called else last_value - 1
    if floor > consumed:
        connection.exec_driver_sql(f"SELECT setval('{spec.name}', {floor}, true)")
        return floor
    return consumed


def next_serial(db: Session, prefix: str) -> int:
    """取下一个流水号（原子、不重复）。"""
    spec = _BY_PREFIX.get(prefix)
    if spec is None:
        raise KeyError(f"未登记的业务编号前缀：{prefix}；请在 app.db.sequences 里补一条")
    if not _ensured:
        ensure_business_sequences()
    return int(db.execute(text(f"SELECT nextval('{spec.name}')")).scalar())


def format_no(prefix: str, serial: int, when: datetime | None = None) -> str:
    day = (when or datetime.now()).strftime("%Y%m%d")
    return f"{prefix}{day}{serial:04d}"


def next_no(db: Session, prefix: str, id_column=None) -> str:
    """统一的业务编号入口。

    ``id_column`` 只为兼容旧调用签名保留，已不参与计算（旧实现靠它取 max(id)）。
    """
    return format_no(prefix, next_serial(db, prefix))
