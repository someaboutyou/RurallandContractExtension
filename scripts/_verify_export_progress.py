"""验收：导出进度 + 假死清扫（2026-10-04）。

覆盖：
1. upgrade_schema 给 data_exports 补 progress/progress_message/worker_pid 三列（幂等）；
2. sweep_stale_processing：死 PID → failed；当前进程 PID → 不动；
   无 PID 旧记录 + 心跳超时（updated_at 回拨 31 分钟）→ failed；
3. 真实导出（nyt2539_gdb，小区域）全程跑通，终态 success + progress=100，
   过程中 reporter 写库可见（用子线程在生成期间轮询验证 progress 有中间值）。

运行：runtime/windows/python/python.exe scripts/_verify_export_progress.py
"""

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    t = line.strip()
    if t and not t.startswith("#") and "=" in t:
        k, v = t.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, str(ROOT / "backend"))

import app.main  # noqa: F401,E402 — 注册全部 mapper
from sqlalchemy import inspect as sa_inspect, select, text  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.data_export import DataExport  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.data_export_service import data_export_service  # noqa: E402
from app.services.export_progress import ExportProgressReporter, pid_alive  # noqa: E402

_results = []


def check(name, ok, detail=""):
    _results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} | {name}" + (f" | {detail}" if detail else ""))


def main():
    # ---- 1. 迁移加列（直接调 upgrade_schema，幂等）
    from app.db.migrations import upgrade_schema

    upgrade_schema(engine)
    cols = {c["name"] for c in sa_inspect(engine).get_columns("data_exports")}
    check("迁移后 data_exports 含 progress 列", "progress" in cols)
    check("迁移后 data_exports 含 progress_message 列", "progress_message" in cols)
    check("迁移后 data_exports 含 worker_pid 列", "worker_pid" in cols)

    # 再跑一次证明幂等
    upgrade_schema(engine)
    check("upgrade_schema 幂等（重复执行不报错）", True)

    # ---- 2. 清扫判活
    db = SessionLocal()
    try:
        # pid_alive 基础行为
        check("pid_alive(当前进程)=True", pid_alive(os.getpid()))
        check("pid_alive(0)=False", not pid_alive(0))
        check("pid_alive(99999999)=False", not pid_alive(99999999))

        # 造三条 processing 夹具
        fixtures = []
        for tag, pid in [("dead_pid", 99999999), ("alive_pid", os.getpid())]:
            row = DataExport(
                export_no=f"EXPVERIFY{tag}{int(time.time())}",
                region_code="321324", region_name="进度验收", region_level="county",
                export_type="contractor_roster", status="processing",
                worker_pid=pid, operator_id=1, operator_name="verify",
            )
            db.add(row)
            fixtures.append(row)
        legacy = DataExport(
            export_no=f"EXPVERIFYlegacy{int(time.time())}",
            region_code="321324", region_name="进度验收", region_level="county",
            export_type="contractor_roster", status="processing",
            worker_pid=None, operator_id=1, operator_name="verify",
        )
        db.add(legacy)
        db.commit()
        fixtures.append(legacy)
        ids = [r.id for r in fixtures]

        # 无 PID 旧记录回拨 updated_at 31 分钟（模拟心跳超时）
        db.execute(
            text("UPDATE data_exports SET updated_at = NOW() - INTERVAL '31 minutes' WHERE id = :i"),
            {"i": legacy.id},
        )
        db.commit()

        swept = data_export_service.sweep_stale_processing(db)
        db.expire_all()
        dead = db.get(DataExport, ids[0])
        alive = db.get(DataExport, ids[1])
        legacy2 = db.get(DataExport, ids[2])
        check("死 PID 记录被清成 failed", dead.status == "failed" and "99999999" in (dead.error_message or ""))
        check("活 PID 记录保持 processing", alive.status == "processing")
        check("无 PID + 心跳超时记录被清成 failed", legacy2.status == "failed" and "心跳" in (legacy2.error_message or ""))
        check("清扫返回条数 ≥ 2（夹具 2 条 + 库中真实假死记录）", swept >= 2, f"swept={swept}")

        # ---- 3. 真实导出：nyt2539_gdb 小区域，子线程轮询中间进度
        user = db.get(User, 1)
        region = "321324100001"
        progress_samples = []
        stop = threading.Event()

        created = {}

        def poll_by_no():
            poll_db = SessionLocal()
            try:
                while not stop.is_set():
                    # create_export 内部才生成 export_no，这里按区域抓 processing 记录取中间进度
                    rows = poll_db.scalars(
                        select(DataExport).where(
                            DataExport.region_code == region,
                            DataExport.export_type == "nyt2539_gdb",
                            DataExport.status == "processing",
                        )
                    ).all()
                    for row in rows:
                        progress_samples.append((row.progress, row.progress_message))
                    stop.wait(0.1)
            finally:
                poll_db.close()

        watcher = threading.Thread(target=poll_by_no, daemon=True)
        watcher.start()
        rec = data_export_service.create_export(db, {
            "regionCode": region, "regionName": "进度验收村", "regionLevel": "village",
            "exportType": "nyt2539_gdb",
        }, user)
        created["no"] = rec.exportNo
        time.sleep(0.2)
        stop.set()
        watcher.join(timeout=2)

        check("真实导出终态 success", rec.status == "success", f"rows={rec.recordCount}")
        row = db.scalars(select(DataExport).where(DataExport.export_no == rec.exportNo)).first()
        check("终态 progress=100", row.progress == 100, f"progress={row.progress}")
        check("终态 progress_message=完成", row.progress_message == "完成", str(row.progress_message))
        mid = [p for p, _ in progress_samples if 0 < p < 100]
        check("生成过程中观察到中间进度", len(mid) > 0, f"samples={sorted(set(mid))[:8]} msg={progress_samples[0][1] if progress_samples else '—'}")

        # 清理验收夹具与产物
        for rid in ids + [row.id]:
            r = db.get(DataExport, rid)
            if r:
                try:
                    data_export_service.delete_export(db, rid, user)
                except Exception as e:  # noqa: BLE001
                    print(f"cleanup warn id={rid}: {e}")
        print("cleanup done")
    finally:
        db.close()

    failed = [n for n, ok, _ in _results if not ok]
    print(f"\n===== {len(_results) - len(failed)}/{len(_results)} PASS =====")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
