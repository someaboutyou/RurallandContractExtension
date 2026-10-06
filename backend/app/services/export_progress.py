"""数据导出进度汇报与进程存活判定。

设计要点：
- 生成过程运行在请求线程里、占用主 DB 会话（流式游标不能中途 commit），
  因此进度用**独立短会话**写 ``data_exports.progress / progress_message`` 并立即提交。
- ORM update 会触发 ``updated_at`` 的 onupdate=now() —— 该字段同时充当**存活心跳**，
  供 ``data_export_service`` 的 stale 清扫判定「进程还在不在干活」。
- 汇报失败绝不打断导出本身：只记 warning。
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

# 心跳兜底阈值：正常汇报间隔 ≤1s，单条大查询（圈定范围/打包压缩）之间
# 也远小于该值；超过它基本可判定生成线程已死（且 pid 校验无法覆盖的旧记录靠它兜底）。
STALE_HEARTBEAT_SECONDS = 30 * 60


class ExportProgressReporter:
    """把导出进度写进 data_exports 记录（节流，默认最快 1 秒一次）。"""

    def __init__(self, export_id: int, min_interval: float = 1.0):
        self._export_id = export_id
        self._min_interval = min_interval
        self._last_ts = 0.0
        self._last_percent = -1

    def report(self, percent: int, message: str = "", force: bool = False) -> None:
        percent = max(0, min(100, int(percent)))
        now = time.monotonic()
        if not force and now - self._last_ts < self._min_interval:
            return
        self._last_ts = now
        self._last_percent = percent
        try:
            from app.db.session import SessionLocal  # noqa: PLC0415 — 避免 import 环
            from app.models.data_export import DataExport  # noqa: PLC0415

            session = SessionLocal()
            try:
                row = session.get(DataExport, self._export_id)
                # 记录已被清扫成 failed（心跳误判等极端情况）就不再覆写进度
                if row is None or row.status != "processing":
                    return
                row.progress = percent
                row.progress_message = (message or "")[:200]
                session.commit()  # onupdate 顺带刷新 updated_at（心跳）
            finally:
                session.close()
        except Exception:  # noqa: BLE001
            logger.warning("导出进度更新失败 export_id=%s", self._export_id, exc_info=True)


class NullProgressReporter:
    """不汇报任何进度的占位实现（离线脚本等场景用）。"""

    def report(self, percent: int, message: str = "", force: bool = False) -> None:
        return


def pid_alive(pid: int) -> bool:
    """判断本机进程是否存活（Windows 用 OpenProcess，POSIX 用 kill 0）。"""
    if not pid or int(pid) <= 0:
        return False
    pid = int(pid)
    try:
        if os.name == "nt":
            import ctypes  # noqa: PLC0415

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        os.kill(pid, 0)
        return True
    except Exception:  # noqa: BLE001
        return False
