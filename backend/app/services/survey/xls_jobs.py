# -*- coding: utf-8 -*-
"""承包方调查表 Excel 导出 / 导入后台任务。

为什么要后台任务：承包方上千户时，同步导出/导入一个请求要跑几十秒到几分钟，
HTTP 超时、前端白屏等待都不可接受。改为「启动任务 → 前端轮询进度 → 完成后
下载/看结果」三段式。

实现约束：
- 单进程内存注册表（部署就是单 uvicorn 进程）；任务上限自动清理最旧的。
- worker 线程用**独立 DB 会话**（SessionLocal），绝不复用请求的会话。
- job_id 用 uuid4，下载接口虽然不可猜测，仍做权限校验（view/manage）。
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid

logger = logging.getLogger(__name__)

_MAX_JOBS = 40
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _cleanup_locked() -> None:
    """调用方必须已持有 _LOCK。按创建时间保留最新 _MAX_JOBS 个。"""
    if len(_JOBS) <= _MAX_JOBS:
        return
    ordered = sorted(_JOBS.items(), key=lambda kv: kv[1]["createdAt"])
    for key, _ in ordered[:-_MAX_JOBS]:
        _JOBS.pop(key, None)


def create_job(kind: str, batch_id: int, user_id: int) -> dict:
    job = {
        "id": uuid.uuid4().hex,
        "kind": kind,  # export / import
        "batchId": batch_id,
        "userId": user_id,
        "status": "running",  # running / done / error
        "phase": "准备中",
        "done": 0,
        "total": 0,
        "current": "",
        "error": "",
        "createdAt": time.time(),
        # export 专用
        "filename": "",
        "content": b"",
        # import 专用
        "summary": None,
        "results": None,
        "warnings": None,
    }
    with _LOCK:
        _JOBS[job["id"]] = job
        _cleanup_locked()
    return job


def get_job(job_id: str) -> dict | None:
    with _LOCK:
        return _JOBS.get(job_id)


def update_job(job_id: str, **fields) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(fields)


def _progress_cb(job_id: str):
    def cb(done: int, total: int, phase: str, current: str = "") -> None:
        update_job(job_id, done=done, total=total, phase=phase, current=current)

    return cb


def _run_worker(job_id: str, target) -> None:
    def wrapper():
        try:
            target()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Excel 后台任务失败 job=%s", job_id)
            update_job(job_id, status="error", error=str(exc) or exc.__class__.__name__,
                       detail=traceback.format_exc(limit=5))

    thread = threading.Thread(target=wrapper, name=f"xls-job-{job_id[:8]}", daemon=True)
    thread.start()


def start_export_job(batch_id: int, user_id: int) -> dict:
    job = create_job("export", batch_id, user_id)

    def target():
        from app.db.session import SessionLocal
        from app.models.user import User
        from app.services.survey import survey_service

        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            filename, content = survey_service.export_contractors_xls(
                db, batch_id, user, progress_cb=_progress_cb(job["id"])
            )
            update_job(job["id"], status="done", phase="导出完成", done=1, total=1,
                       filename=filename, content=content)
        finally:
            db.close()

    _run_worker(job["id"], target)
    return job


def start_import_job(batch_id: int, user_id: int, content: bytes) -> dict:
    job = create_job("import", batch_id, user_id)

    def target():
        from app.db.session import SessionLocal
        from app.models.user import User
        from app.services.survey import survey_service

        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            result = survey_service.import_contractors_xls(
                db, batch_id, user, content, progress_cb=_progress_cb(job["id"])
            )
            update_job(job["id"], status="done", phase="导入完成", done=1, total=1,
                       summary=result.get("summary"), results=result.get("households"),
                       warnings=result.get("warnings"))
        finally:
            db.close()

    _run_worker(job["id"], target)
    return job


def job_public_view(job: dict | None) -> dict | None:
    """对外暴露的字段（剔除文件字节与内部细节）。"""
    if job is None:
        return None
    view = {
        "jobId": job["id"], "kind": job["kind"], "batchId": job["batchId"],
        "status": job["status"], "phase": job["phase"],
        "done": job["done"], "total": job["total"], "current": job["current"],
        "error": job["error"], "filename": job["filename"],
        "summary": job["summary"], "results": job["results"], "warnings": job["warnings"],
    }
    if job["status"] == "error":
        view["detail"] = job.get("detail", "")
    return view
