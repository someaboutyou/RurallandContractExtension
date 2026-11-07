# -*- coding: utf-8 -*-
"""数据中心（无批次）清单导出 / 导入后台任务。

与 ``survey/xls_jobs.py`` 同款实现（单进程内存注册表 + 独立 DB 会话的
worker 线程），差异只在作用域：这里没有批次，scope 用区域码表达
（空 = 整库）。数据量可能覆盖全库，仍走「启动任务 → 轮询 → 下载/看结果」。
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


def create_job(kind: str, user_id: int, region_code: str = "") -> dict:
    job = {
        "id": uuid.uuid4().hex,
        "kind": kind,  # export / import
        "userId": user_id,
        "regionCode": region_code or "",
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
            logger.exception("数据中心后台任务失败 job=%s", job_id)
            update_job(job_id, status="error", error=str(exc) or exc.__class__.__name__,
                       detail=traceback.format_exc(limit=5))

    thread = threading.Thread(target=wrapper, name=f"dc-job-{job_id[:8]}", daemon=True)
    thread.start()


def job_public_view(job: dict | None) -> dict | None:
    """对外暴露的字段（剔除文件字节与内部细节）。"""
    if job is None:
        return None
    view = {
        "jobId": job["id"], "kind": job["kind"], "regionCode": job["regionCode"],
        "status": job["status"], "phase": job["phase"],
        "done": job["done"], "total": job["total"], "current": job["current"],
        "error": job["error"], "filename": job["filename"],
        "summary": job["summary"], "results": job["results"], "warnings": job["warnings"],
    }
    if job["status"] == "error":
        view["detail"] = job.get("detail", "")
    return view
