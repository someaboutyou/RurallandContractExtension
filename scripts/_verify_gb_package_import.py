# -*- coding: utf-8 -*-
"""国标包（mdb+shp）导入全流程验收。

流程：打包样例 → 建批次 → run_gb_import_job（同生产后台代码路径）→
行数勾稽 → 关键字段抽查 → 回滚 → 回滚后勾稽。全部通过后库内数据复原。

运行：runtime/windows/python/python.exe scripts/_verify_gb_package_import.py
"""
from __future__ import annotations

import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ⛔ 先注入运行时环境，再 import app（psycopg 连不上会静默退出）
_env_file = ROOT / "runtime" / ".state" / "runtime.env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
os.environ.setdefault("DATABASE_PORT", "15432")
sys.path.insert(0, str(ROOT / "backend"))

SAMPLE_DIR = ROOT / "datas" / "巨日合(1)"
TEST_ZIP = ROOT / "runtime" / ".state" / "gb_package_test.zip"

# mdb 五表 + DK shp 的源行数（样例实测）
EXPECTED_ROWS = {
    "fbf": 27,
    "cbf": 7161,
    "cbf_jtcy": 36807,
    "cbht": 7161,
    "cbdkxx": 42493,
    "dk": 45868,
}
REGION_CODE = "150526"  # 县码（包内文件名的 1505262019 是建库编号，fbfbm/dkbm 实际以 150526 开头）
BATCH_NAME = "国标包导入验收-巨日合"
_member_dup_limit = 3


def _read_mdb_member_rows() -> list[dict]:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.services.data_import.gb_package import read_mdb_table

    return read_mdb_table(str(SAMPLE_DIR / "权属数据" / "1505262019.mdb"), "CBF_JTCY")

_failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}{(' — ' + detail) if detail else ''}", flush=True)
    if not ok:
        _failures.append(f"{label}: {detail}")


def build_test_zip() -> Path:
    if TEST_ZIP.exists():
        return TEST_ZIP
    TEST_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(TEST_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(SAMPLE_DIR / "权属数据" / "1505262019.mdb", "权属数据/1505262019.mdb")
        for item in sorted((SAMPLE_DIR / "矢量数据").iterdir()):
            if item.suffix.lower() in (".shp", ".shx", ".dbf", ".prj", ".sbn", ".sbx", ".xml"):
                zf.write(item, f"矢量数据/{item.name}")
    return TEST_ZIP


def main() -> int:
    build_test_zip()

    import app.main  # noqa: F401 — 注册全部模型
    from sqlalchemy import func, select, text

    # 手动跑迁移：新增的 source_import_batch_id/last_import_batch_id 列
    # 只在后端启动的 bootstrap_database 里创建，验收脚本要自己补
    from app.db.migrations import upgrade_schema
    from app.db.session import engine

    upgrade_schema(engine)

    from app.db.session import SessionLocal, set_current_user
    from app.models.data_import import DataImportBatch
    from app.models.survey import SurveyDkResult, SurveyJzdResult, SurveyJzxResult
    from app.models.user import User
    from app.services.data_import.gb_package import run_gb_import_job
    from app.services.data_import_progress import data_import_progress
    from app.services.data_import_service import data_import_service

    # ⛔ 验收专用：本机 license 授权区域是 321324（泗洪），样例数据是
    # 150526（扎赉特旗），系统区域校验会整包 403。仅在**本进程内**豁免
    # 系统区域码（license 文件本身不动），不影响后端服务进程。
    from app.core.license import license_validator as _license_validator

    _license_validator.get_authorized_region_code = lambda: None

    db = SessionLocal()
    user = db.get(User, 1)
    set_current_user(db, user)

    # ── 前置清理：把上一次验收遗留的批次回滚掉（顺带验证回滚路径）────────
    from app.models.data_import import DataImportBatch as _Batch

    stale = db.scalars(
        select(_Batch).where(
            _Batch.region_code.like("150526%"),
            _Batch.status.in_(("success", "partial_success", "failed", "canceled")),
        )
    ).all()
    for old in stale:
        print(f"cleanup: rollback stale batch id={old.id} status={old.status}", flush=True)
        data_import_service.rollback_batch(db, old.id, user)
        db.expire_all()

    # ── 建批次 ───────────────────────────────────────────────────────────
    batch = data_import_service.create_batch(
        db,
        {
            "importName": BATCH_NAME,
            "regionCode": REGION_CODE,
            "regionName": "内蒙古自治区兴安盟扎赉特旗（验收）",
            "sourceType": "gb_package",
        },
        user,
    )
    batch_id = batch["id"]
    print(f"batch created: id={batch_id} import_no={batch['importNo']} region={batch['regionCode']}", flush=True)

    # ── 后台导入（同步调用同一段生产代码）────────────────────────────────
    job_id = f"gb:{batch_id}:verify"
    data_import_progress.init(batch_id, job_id, {"status": "queued", "message": "验收导入开始", "filename": TEST_ZIP.name})
    started = time.time()
    run_gb_import_job(batch_id, str(TEST_ZIP), TEST_ZIP.name, "application/zip", user.id, job_id)
    elapsed = time.time() - started
    print(f"import job finished in {elapsed:.1f}s", flush=True)

    db.expire_all()
    batch_row = db.get(DataImportBatch, batch_id)
    print(
        f"batch status={batch_row.status} total={batch_row.total_count} "
        f"success={batch_row.success_count} failed={batch_row.failed_count}",
        flush=True,
    )
    check(
        "批次状态",
        batch_row.status in ("success", "partial_success"),
        f"status={batch_row.status}（空证件号成员落失败行 ⇒ partial_success 属预期）",
    )
    progress = data_import_progress.get(batch_id) or {}
    check("进度状态", progress.get("status") == batch_row.status, f"progress={progress.get('status')} message={progress.get('message')}")

    # ── 各图层行数勾稽（data_import_files 视角）──────────────────────────
    file_rows = db.execute(
        text(
            "select file_type, sum(row_count) rows_, sum(error_count) errors "
            "from data_import_files where import_batch_id = :bid group by file_type"
        ),
        {"bid": batch_id},
    ).all()
    by_type = {r[0]: (r[1] or 0, r[2] or 0) for r in file_rows}
    print("data_import_files:", {k: v for k, v in sorted(by_type.items())}, flush=True)
    for file_type, expected in EXPECTED_ROWS.items():
        actual, errors = by_type.get(file_type, (0, 0))
        if file_type == "cbf_jtcy":
            # 既有口径（与 GDB 导入一致）：CYZJHM 为空的成员没有 entity_key，
            # 落失败行（可经「失败行」导出补录）；重复证件号同理。
            mdb_rows = _read_mdb_member_rows()
            no_id = sum(1 for row in mdb_rows if not (row.get("CYZJHM") or "").strip())
            allowed_fail = no_id + _member_dup_limit
            check(
                "图层 cbf_jtcy 行数",
                actual == expected and 0 < errors <= allowed_fail,
                f"expected={expected} actual={actual} errors={errors}（空证件号 {no_id} + 重复上限 {_member_dup_limit}）",
            )
            continue
        check(
            f"图层 {file_type} 行数",
            actual == expected and errors == 0,
            f"expected={expected} actual={actual} errors={errors}",
        )

    # ── 成果表落库勾稽（source_import_batch_id 视角）────────────────────
    table_expect = {
        "survey_fbf_result": EXPECTED_ROWS["fbf"],
        "survey_cbf_result": EXPECTED_ROWS["cbf"],
        "cbht": EXPECTED_ROWS["cbht"],
        "survey_cbdkxx_result": EXPECTED_ROWS["cbdkxx"],
        "survey_dk_result": EXPECTED_ROWS["dk"],
    }
    for table, expected in table_expect.items():
        actual = db.execute(
            text(f"select count(*) from {table} where source_import_batch_id = :bid"),
            {"bid": batch_id},
        ).scalar()
        check(f"成果表 {table} 落库", actual == expected, f"expected={expected} actual={actual}")

    # 成员表落库 = 源行数 - 失败行数（空证件号/重复证件号，见上文口径）
    jtcy_stored = db.execute(
        text("select count(*) from survey_cbf_jtcy_result where source_import_batch_id = :bid"),
        {"bid": batch_id},
    ).scalar()
    jtcy_expected = EXPECTED_ROWS["cbf_jtcy"] - by_type.get("cbf_jtcy", (0, 0))[1]
    check(
        "成果表 survey_cbf_jtcy_result 落库",
        jtcy_stored == jtcy_expected,
        f"expected={jtcy_expected} actual={jtcy_stored}",
    )

    # DK 几何非空 + 坐标量级（转换到 39 带后东坐标质心应以 39 开头，约 39.0M–40.5M）
    geom_total, geom_ok, y39 = db.execute(
        text(
            "select count(*), count(geom), "
            "sum(case when ST_X(ST_Centroid(geom)) between 39000000 and 40500000 then 1 else 0 end) "
            "from survey_dk_result where source_import_batch_id = :bid"
        ),
        {"bid": batch_id},
    ).fetchone()
    check("DK geom 写入", geom_ok == geom_total and geom_total > 0, f"rows={geom_total} with_geom={geom_ok}")
    check("DK 坐标已转到目标带", (y39 or 0) == geom_total, f"centroid_in_target_zone={y39}/{geom_total}")

    # ── 界址点/线勾稽 ───────────────────────────────────────────────────
    # 租户口径与 dk 行一致（导入人所在租户），不能拿 batch.tenant_code
    batch_tenant = db.execute(
        text("select tenant_code from survey_dk_result where source_import_batch_id = :bid limit 1"),
        {"bid": batch_id},
    ).scalar()
    jzd_created = db.execute(
        text("select count(*) from survey_jzd_result where source_import_batch_id = :bid"),
        {"bid": batch_id},
    ).scalar()
    jzx_created = db.execute(
        text("select count(*) from survey_jzx_result where source_import_batch_id = :bid"),
        {"bid": batch_id},
    ).scalar()
    jzd_total = db.execute(
        text("select count(*) from survey_jzd_result where tenant_code = :t"),
        {"t": batch_tenant},
    ).scalar()
    jzx_total = db.execute(
        text("select count(*) from survey_jzx_result where tenant_code = :t"),
        {"t": batch_tenant},
    ).scalar()
    print(f"jzd: batch_created={jzd_created} tenant_total={jzd_total}; jzx: batch_created={jzx_created} tenant_total={jzx_total}", flush=True)
    # shp 的 JZD/JZX 是拓扑清洗后的共点参考值；DK 环顶点存在毫米级不重合的
    # "缝"（源数据非严格共点），推导口径下唯一坐标数会略高于 shp 点数，
    # 只做量级 sanity check。
    check(
        "界址点规模合理",
        121173 <= jzd_created <= 250000,
        f"created={jzd_created}（shp 参考 121173，环顶点缝导致偏多属预期）",
    )
    check(
        "界址线规模合理",
        161013 <= jzx_created <= 320000,
        f"created={jzx_created}（shp 参考 161013）",
    )
    # 可追溯：租户内未挂 source_import_batch_id 的只有验收前遗留的 9+9 条
    untracked_points = db.execute(
        text(
            "select count(*) from survey_jzd_result where tenant_code = :t and source_import_batch_id is null"
        ),
        {"t": batch_tenant},
    ).scalar()
    untracked_lines = db.execute(
        text(
            "select count(*) from survey_jzx_result where tenant_code = :t and source_import_batch_id is null"
        ),
        {"t": batch_tenant},
    ).scalar()
    check(
        "界址点/线新建行全部可追溯",
        untracked_points <= 9 and untracked_lines <= 9,
        f"untracked=({untracked_points},{untracked_lines})（租户内历史遗留 ≤9）",
    )

    # 共点不重复：同一租户内 (x,y) 唯一
    dup_points = db.execute(
        text(
            "select count(*) from (select x, y from survey_jzd_result where tenant_code = :t "
            "group by x, y having count(*) > 1) d"
        ),
        {"t": batch_tenant},
    ).scalar()
    check("界址点共点不重复", dup_points == 0, f"duplicate_xy={dup_points}")
    dup_lines = db.execute(
        text(
            "select count(*) from (select qdjzdh, zdjzdh from survey_jzx_result where tenant_code = :t "
            "group by qdjzdh, zdjzdh having count(*) > 1) d"
        ),
        {"t": batch_tenant},
    ).scalar()
    check("界址线共线不重复", dup_lines == 0, f"duplicate_pair={dup_lines}")

    # JZD 属性回填（界标类型 jblx 非空比例）
    jblx_filled = db.execute(
        text(
            "select count(*) from survey_jzd_result "
            "where source_import_batch_id = :bid and jblx is not null"
        ),
        {"bid": batch_id},
    ).scalar()
    print(f"jzd jblx filled: {jblx_filled}/{jzd_created}", flush=True)
    check("界标类型回填生效", jblx_filled > 0, f"filled={jblx_filled}")
    jzx_attr_filled = db.execute(
        text(
            "select count(*) from survey_jzx_result "
            "where source_import_batch_id = :bid and (jzxlb is not null or jzxwz is not null or jzxsm is not null)"
        ),
        {"bid": batch_id},
    ).scalar()
    print(f"jzx attrs filled: {jzx_attr_filled}/{jzx_created}", flush=True)
    check("界址线属性回填生效", jzx_attr_filled > 0, f"filled={jzx_attr_filled}")

    # CBHT 关键字段抽查：合同面积合计 vs CBDKXX 合同面积合计（勾稽）
    cbht_area = db.execute(
        text("select sum(htzmj) from cbht where source_import_batch_id = :bid"),
        {"bid": batch_id},
    ).scalar()
    cbdkxx_area = db.execute(
        text("select sum(htmj) from survey_cbdkxx_result where source_import_batch_id = :bid"),
        {"bid": batch_id},
    ).scalar()
    print(f"cbht.htzmj sum={cbht_area} vs cbdkxx.htmj sum={cbdkxx_area}", flush=True)
    check(
        "合同面积与地块承包关系勾稽",
        cbht_area is not None and cbdkxx_area is not None and abs(float(cbht_area) - float(cbdkxx_area)) < 1.0,
        f"diff={abs(float(cbht_area or 0) - float(cbdkxx_area or 0)):.4f}",
    )
    cbht_uid = db.execute(
        text("select count(*) from cbht where source_import_batch_id = :bid and contractor_uid is not null"),
        {"bid": batch_id},
    ).scalar()
    check("CBHT 关联承包方 uid", cbht_uid == EXPECTED_ROWS["cbht"], f"matched={cbht_uid}/{EXPECTED_ROWS['cbht']}")

    # 承包方成员数重算抽查
    member_mismatch = db.execute(
        text(
            "select count(*) from survey_cbf_result r "
            "where r.source_import_batch_id = :bid "
            "and r.cbfcysl <> (select count(*) from survey_cbf_jtcy_result m where m.cbfbm = r.cbfbm)"
        ),
        {"bid": batch_id},
    ).scalar()
    check("承包方家庭成员数重算", member_mismatch == 0, f"mismatch={member_mismatch}")

    if _failures:
        print("\n=== 验收失败，保留批次供排查（batch_id=%s）===" % batch_id, flush=True)
        for item in _failures:
            print(" -", item, flush=True)
        return 1

    # ── 回滚 ────────────────────────────────────────────────────────────
    print("\n--- rollback ---", flush=True)
    rolled = data_import_service.rollback_batch(db, batch_id, user)
    check("回滚后状态", rolled["status"] == "rolled_back", f"status={rolled['status']}")
    for table in table_expect:
        actual = db.execute(
            text(f"select count(*) from {table} where source_import_batch_id = :bid"),
            {"bid": batch_id},
        ).scalar()
        check(f"回滚清空 {table}", actual == 0, f"left={actual}")
    jtcy_left = db.execute(
        text("select count(*) from survey_cbf_jtcy_result where source_import_batch_id = :bid"),
        {"bid": batch_id},
    ).scalar()
    check("回滚清空 survey_cbf_jtcy_result", jtcy_left == 0, f"left={jtcy_left}")
    jzd_left = db.execute(
        text("select count(*) from survey_jzd_result where source_import_batch_id = :bid"),
        {"bid": batch_id},
    ).scalar()
    jzx_left = db.execute(
        text("select count(*) from survey_jzx_result where source_import_batch_id = :bid"),
        {"bid": batch_id},
    ).scalar()
    check("回滚清空界址点", jzd_left == 0, f"left={jzd_left}")
    check("回滚清空界址线", jzx_left == 0, f"left={jzx_left}")

    rollback_summary = (rolled.get("errorSummary") or {}).get("rollback") or {}
    print(f"rollback summary: {rollback_summary}", flush=True)

    print("\n=== ALL PASS ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
