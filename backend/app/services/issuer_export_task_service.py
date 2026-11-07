"""发包方（村组）批量导出后台任务：进度轮询 + 完成下载。

与 ``cadastral_export_service`` 同一套路：批量导出耗时随选中村组数线性增长，
同步等在前端既超时又没有反馈，因此走「创建任务 → 后台线程逐个村组渲染 →
前端轮询进度 → 完成后从下载接口取文件」。

支持两种导出类型（kind）：

- ``survey``：发包方调查表 Word——单个 docx，多个打包 zip；
- ``publicity``：村组公示表 xls——所有选中村组合并为**一个** xls
  （一个发包方一个 sheet，与同步端点口径一致），进度按 sheet 汇报。

进度状态放进程内存，任务数上限 ``MAX_TASKS``，超出按创建时间淘汰最旧的。
权限与 ``cadastral_export_service`` 相同：任务进度/产物只允许创建人（或
``data_scope=all`` 平台管理员）访问；数据范围（ensure_code_in_scope）在
创建任务的端点里先行校验，后台线程只渲染已通过校验的编码清单。
"""

from __future__ import annotations

import io
import logging
import threading
import uuid
import zipfile
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.session import SessionLocal, set_current_user
from app.models.user import User
from app.services.issuer_survey_docx_service import issuer_survey_docx_service
from app.services.village_publicity_export_service import village_publicity_export_service

logger = logging.getLogger(__name__)

#: 内存里最多保留多少个任务
MAX_TASKS = 20

#: 支持的导出类型 → 展示名（用于进度文案与默认文件名）
KIND_LABELS: dict[str, str] = {
    "survey": "发包方调查表",
    "publicity": "村组公示表",
}


class IssuerExportTaskService:
    """按选中发包方（村组）批量导出调查表 / 公示表，带进度。"""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    # ── 任务生命周期 ────────────────────────────────────────────────────────
    def create_task(self, *, kind: str, codes: list[str], user_id: int) -> str:
        if kind not in KIND_LABELS:
            raise ValueError(f"不支持的导出类型：{kind}")
        # 编码去重，保持顺序（与同步端点同口径）
        unique: list[str] = []
        seen: set[str] = set()
        for code in codes:
            code = str(code or "").strip()
            if code and code not in seen:
                seen.add(code)
                unique.append(code)
        if not unique:
            raise ValueError("未指定发包方")

        task_id = uuid.uuid4().hex
        with self._lock:
            self._prune_locked()
            self._tasks[task_id] = {
                "id": task_id,
                "kind": kind,
                # ⛔ 归属绑定：进度/产物只允许创建人（或 data_scope=all）访问
                "user_id": user_id,
                "status": "pending",
                "done": 0,
                "total": len(unique),
                "percent": 0,
                "message": "正在准备…",
                "error": None,
                "archive": None,
                "filename": None,
                "createdAt": datetime.now(),
            }
        thread = threading.Thread(
            target=self._run,
            args=(task_id, kind, unique, user_id),
            daemon=True,
        )
        thread.start()
        return task_id

    @staticmethod
    def _ensure_owner(task: dict, current_user) -> None:
        """越权访问导出任务时抛 PermissionError（端点层转 403）。"""
        user_id = getattr(current_user, "id", None)
        if user_id is not None and task.get("user_id") == user_id:
            return
        if getattr(current_user.role, "data_scope", None) == "all":
            return
        raise PermissionError("无权访问该导出任务")

    def get_progress(self, task_id: str, current_user=None) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if current_user is not None:
                self._ensure_owner(task, current_user)
            return {key: value for key, value in task.items() if key != "archive"}

    def get_archive(self, task_id: str, current_user=None) -> tuple[str, bytes] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if current_user is not None:
                # ⛔ 先鉴权再判产物：避免通过 403/404 差异探测他人任务是否存在
                self._ensure_owner(task, current_user)
            if not task.get("archive"):
                return None
            label = KIND_LABELS.get(task.get("kind", ""), "导出文件")
            return task["filename"] or f"{label}.zip", task["archive"]

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
    def _run(self, task_id: str, kind: str, codes: list[str], user_id: int) -> None:
        db: Session = SessionLocal()
        try:
            user = db.get(User, user_id)
            if user is None:
                self._update(task_id, status="failed", error="操作用户不存在，无法导出")
                return
            set_current_user(db, user)

            total = len(codes)
            label = KIND_LABELS[kind]
            self._update(task_id, status="running", total=total, message=f"共 {total} 个村组，开始生成…")

            if kind == "survey":
                filename, payload = self._run_survey(db, task_id, codes, total, label)
            else:
                filename, payload = self._run_publicity(db, task_id, codes, total, label)

            self._update(
                task_id,
                status="completed",
                done=total,
                percent=100,
                message=f"已生成 {total} 个村组的{label}，可以下载了",
                archive=payload,
                filename=filename,
            )
        except Exception as exc:  # noqa: BLE001 - 后台任务需要兜住所有异常
            logger.exception("发包方批量导出失败：task=%s kind=%s", task_id, kind)
            self._update(task_id, status="failed", error=str(exc))
        finally:
            db.close()

    def _run_survey(
        self, db: Session, task_id: str, codes: list[str], total: int, label: str
    ) -> tuple[str, bytes]:
        """发包方调查表：逐个渲染 docx，单个直接返回，多个打包 zip。"""
        files: list[tuple[str, bytes]] = []
        for index, code in enumerate(codes, start=1):
            content, filename = issuer_survey_docx_service.render(db, fbfbm=code)
            files.append((filename, content))
            self._update(
                task_id,
                done=index,
                percent=min(99, max(1, int(index * 100 / total))),
                message=f"已生成 {index}/{total} 个村组的{label}",
            )

        if len(files) == 1:
            return files[0]

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for filename, content in files:
                archive.writestr(filename, content)
        return f"{label}.zip", buffer.getvalue()

    def _run_publicity(
        self, db: Session, task_id: str, codes: list[str], total: int, label: str
    ) -> tuple[str, bytes]:
        """村组公示表：一个发包方一个 sheet，全部合并为一个 xls（同步端点同口径）。"""

        def on_sheet_done(done: int, sheet_total: int) -> None:
            self._update(
                task_id,
                done=done,
                total=sheet_total,
                percent=min(99, max(1, int(done * 100 / max(1, sheet_total)))),
                message=f"已生成 {done}/{sheet_total} 个村组的{label}",
            )

        content, filename = village_publicity_export_service.export(
            db, codes, progress_callback=on_sheet_done
        )
        return filename, content


#: 供端点层做参数校验时复用的回调类型标注（无运行时作用）
ProgressCallback = Callable[[int, int], None]

issuer_export_task_service = IssuerExportTaskService()
