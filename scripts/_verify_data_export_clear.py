"""验收：数据导出「清除」功能（clear_export）。

验证点：
  1. 迁移：老库缺 is_historical 列时 upgrade_schema 能补上（幂等）；
  2. 清除：产物文件 + 以 id 命名的目录被删，记录保留并 is_historical=True、file_path 置空；
  3. 序列化：DataExportRead 暴露 isHistorical；
  4. 异常：清除不存在的记录抛 KeyError；
  5. 下载闸门：is_historical 的记录 file_path 为 None（下载接口天然 404/400）。

全程使用独立临时库（见 TEST_DB），不碰开发库；产物目录用真实 storage 路径但收尾自清。

跑法（必须用带依赖的解释器，在 backend 目录语义下）：
  runtime/windows/python/python.exe scripts/_verify_data_export_clear.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "runtime" / ".state" / "runtime.env"
TEST_DB = "erlunyanbao_clearverify"

STORAGE_DATA_EXPORTS = ROOT / "backend" / "storage" / "data_exports"


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
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

from sqlalchemy import inspect as sa_inspect  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.bootstrap import bootstrap_database  # noqa: E402
from app.db.migrations import upgrade_schema  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.data_export import DataExport  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.data_export import DataExportRead, serialize_export  # noqa: E402
from app.services.data_export_service import data_export_service  # noqa: E402

checks: list[dict] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def main() -> int:
    # ---- 3. 首次 bootstrap（含 upgrade_schema：新库直接建出 is_historical）----
    bootstrap_database()
    cols = {c["name"] for c in sa_inspect(engine).get_columns("data_exports")}
    check("新库建表含 is_historical", "is_historical" in cols)

    # ---- 4. 模拟老库：删列 → 再跑 upgrade_schema，验证补列幂等 -------------
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE data_exports DROP COLUMN is_historical")
    upgrade_schema(engine)
    cols = {c["name"] for c in sa_inspect(engine).get_columns("data_exports")}
    check("老库升级补回 is_historical", "is_historical" in cols)

    # ---- 5. 造真实产物：backend/storage/data_exports/<id>/xxx.zip ---------
    with SessionLocal() as db:
        admin = db.scalar(select(User).order_by(User.id).limit(1))
        export = DataExport(
            export_no="EXPCLEARVERIFY0001",
            region_code="321324",
            region_name="验收临时区域",
            region_level="county",
            export_type="contractor_roster",
            status="success",
            progress=100,
            file_size=3,
            record_count=1,
            operator_id=admin.id,
            operator_name=getattr(admin, "display_name", None) or admin.real_name or admin.username,
        )
        db.add(export)
        db.commit()
        db.refresh(export)

        target_dir = STORAGE_DATA_EXPORTS / str(export.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        zip_path = target_dir / "数据导出_验收临时.zip"
        zip_path.write_bytes(b"zip")
        export.file_path = f"data_exports/{export.id}/数据导出_验收临时.zip"
        export.file_name = "数据导出_验收临时.zip"
        db.commit()

        export_id = export.id
        check("夹具就绪（记录+产物目录）", zip_path.exists() and target_dir.is_dir(), f"id={export_id}")

        # ---- 6. 清除：目录、文件、字段、标记 -------------------------------
        cleared = data_export_service.clear_export(db, export_id, admin)
        check("产物目录已删除", not target_dir.exists())
        check("is_historical=True", cleared.is_historical is True)
        check("file_path 已置空", cleared.file_path is None)
        check("file_name 保留作台账", cleared.file_name == "数据导出_验收临时.zip")
        check("其余台账字段未动", cleared.export_no == "EXPCLEARVERIFY0001" and cleared.record_count == 1)

        # ---- 7. 序列化契约 -------------------------------------------------
        payload = serialize_export(db.get(DataExport, export_id))
        read = DataExportRead(**payload)
        check("serialize_export 暴露 isHistorical", read.isHistorical is True)

        # ---- 8. 幂等：对已清除记录再清一次不报错 ---------------------------
        data_export_service.clear_export(db, export_id, admin)
        check("重复清除幂等", db.get(DataExport, export_id).is_historical is True)

        # ---- 9. 异常：不存在 → KeyError ------------------------------------
        try:
            data_export_service.clear_export(db, 99999999, admin)
            check("不存在记录抛 KeyError", False)
        except KeyError:
            check("不存在记录抛 KeyError", True)

    result = {"passed": sum(1 for c in checks if c["ok"]), "failed": sum(1 for c in checks if not c["ok"])}
    print(f"\n== {result['passed']} passed, {result['failed']} failed ==")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    code = main()
    # ---- 10. 收尾：临时库丢弃（验收数据都在临时库里） ----------------------
    with psycopg.connect(
        f"host={HOST} port={PORT} user={DB_USER} password={DB_PWD} dbname=postgres",
        autocommit=True,
    ) as conn:
        conn.execute(f'DROP DATABASE "{TEST_DB}" WITH (FORCE)')
    # 保险：万一失败路径留下产物目录，按 id 清掉（仅验收 id 目录）
    if STORAGE_DATA_EXPORTS.exists():
        for d in STORAGE_DATA_EXPORTS.iterdir():
            if d.is_dir() and d.name.isdigit() and not any(d.iterdir()):
                d.rmdir()
    sys.exit(code)
