"""地籍调查表批量导出：后台逐户生成 Word，打包 zip，前端轮询进度。

一个村上千户、每户 20~30KB，同步等在前端会超时且没有任何反馈，因此走
"创建任务 → 后台线程逐户渲染 → 前端轮询进度 → 完成后下载 zip"。
进度状态放进程内存（与 ``raster_publish_service`` 同一套路），任务数上限
``MAX_TASKS``，超出后按创建时间淘汰最旧的。
"""

from __future__ import annotations

import io
import logging
import threading
import uuid
import zipfile
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal, set_current_user
from app.models.user import User
from app.services.cadastral_docx_service import cadastral_docx_service
from app.services.contractor_service import contractor_service

logger = logging.getLogger(__name__)

#: 每次从库里取多少户（同时决定写 zip 的批大小）
PAGE_SIZE = 100
#: 单次导出的户数上限，超过要求先缩小区域
MAX_CONTRACTORS = 500
#: 内存里最多保留多少个任务
MAX_TASKS = 20


class CadastralExportService:
    """按区域批量导出《地籍调查表》Word，打成 zip。"""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    # ── 任务生命周期 ────────────────────────────────────────────────────────
    def create_task(
        self, *, filters: dict, user_id: int, region_label: str
    ) -> str:
        task_id = uuid.uuid4().hex
        with self._lock:
            self._prune_locked()
            self._tasks[task_id] = {
                "id": task_id,
                "status": "pending",
                "done": 0,
                "total": 0,
                "percent": 0,
                "message": "正在准备…",
                "error": None,
                "archive": None,
                "filename": None,
                "regionLabel": region_label,
                "createdAt": datetime.now(),
            }
        thread = threading.Thread(
            target=self._run,
            args=(task_id, filters, user_id, region_label),
            daemon=True,
        )
        thread.start()
        return task_id

    def get_progress(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return {key: value for key, value in task.items() if key != "archive"}

    def get_archive(self, task_id: str) -> tuple[str, bytes] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or not task.get("archive"):
                return None
            return task["filename"] or "地籍调查表.zip", task["archive"]

    def _prune_locked(self) -> None:
        if len(self._tasks) < MAX_TASKS:
            return
        ordered = sorted(self._tasks.items(), key=lambda item: item[1]["createdAt"])
        for task_id, _ in ordered[: len(self._tasks) - MAX_TASKS + 1]:
            self._tasks.pop(task_id, None)

    def _update(self, task_id: str, **fields: Any) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.update(fields)

    # ── 后台线程 ────────────────────────────────────────────────────────────
    def _run(
        self, task_id: str, filters: dict, user_id: int, region_label: str
    ) -> None:
        db: Session = SessionLocal()
        try:
            user = db.get(User, user_id)
            if user is None:
                self._update(task_id, status="failed", error="操作用户不存在，无法导出")
                return
            set_current_user(db, user)

            self._update(task_id, status="running", message="正在统计可导出的承包方…")
            first = contractor_service.list_contractors(
                db, page=1, page_size=PAGE_SIZE, current_user=user, **filters
            )
            total = first["total"]
            if not total:
                self._update(
                    task_id, status="failed", error=f"「{region_label}」下没有可导出的承包方"
                )
                return
            if total > MAX_CONTRACTORS:
                self._update(
                    task_id,
                    status="failed",
                    error=(
                        f"「{region_label}」共 {total} 户，超过单次导出上限 "
                        f"{MAX_CONTRACTORS} 户，请选择更小的区域后再导出"
                    ),
                )
                return

            self._update(
                task_id, total=total, message=f"共 {total} 户，开始生成…", percent=1
            )

            used_names: set[str] = set()
            buffer = io.BytesIO()
            done = 0
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                page = 1
                while True:
                    page_data = first if page == 1 else contractor_service.list_contractors(
                        db, page=page, page_size=PAGE_SIZE, current_user=user, **filters
                    )
                    items = page_data.get("items") or []
                    if not items:
                        break
                    for item in items:
                        code = item.get("code")
                        if not code:
                            continue
                        try:
                            payload, filename = cadastral_docx_service.render_contractor(
                                db, cbfbm=code
                            )
                        except Exception:  # 单户失败不应中断整批
                            logger.exception("导出地籍调查表失败：%s", code)
                            done += 1
                            continue
                        archive.writestr(
                            self._unique_name(used_names, filename), payload
                        )
                        done += 1
                        self._update(
                            task_id,
                            done=done,
                            percent=min(99, max(1, int(done * 100 / total))),
                            message=f"已生成 {done}/{total} 户",
                        )
                    # 读了大批数据后释放 identity map，避免长任务内存膨胀
                    db.expire_all()
                    if page * PAGE_SIZE >= total:
                        break
                    page += 1

            self._update(
                task_id,
                status="completed",
                done=done,
                percent=100,
                message=f"已生成 {done} 户，可以下载了",
                archive=buffer.getvalue(),
                filename=f"{region_label or '区域'}地籍调查表.zip",
            )
        except Exception as exc:  # noqa: BLE001 - 后台任务需要兜住所有异常
            logger.exception("批量导出地籍调查表失败：task=%s", task_id)
            self._update(task_id, status="failed", error=str(exc))
        finally:
            db.close()

    @staticmethod
    def _unique_name(used: set[str], filename: str) -> str:
        if filename not in used:
            used.add(filename)
            return filename
        stem, _, suffix = filename.rpartition(".")
        index = 2
        candidate = f"{stem}({index}).{suffix}"
        while candidate in used:
            index += 1
            candidate = f"{stem}({index}).{suffix}"
        used.add(candidate)
        return candidate


cadastral_export_service = CadastralExportService()
