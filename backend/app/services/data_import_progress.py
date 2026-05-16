import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

try:
    import redis
except ImportError:
    redis = None


logger = logging.getLogger(__name__)


class DataImportProgressService:
    ttl_seconds = 60 * 60 * 24

    def __init__(self) -> None:
        self._memory_progress: dict[int, dict[str, Any]] = {}
        self._memory_cancel: set[int] = set()
        host = os.getenv("REDIS_HOST", "127.0.0.1")
        port = int(os.getenv("REDIS_PORT", "16379"))
        db = int(os.getenv("REDIS_DB", "0"))
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True) if redis else None
        if self.client is None:
            logger.warning("Redis package is not installed; data import progress falls back to in-memory state")

    def progress_key(self, batch_id: int) -> str:
        return f"data_import:progress:{batch_id}"

    def cancel_key(self, batch_id: int) -> str:
        return f"data_import:cancel:{batch_id}"

    def init(self, batch_id: int, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        progress = {
            "batchId": batch_id,
            "jobId": job_id,
            "status": "queued",
            "currentLayer": None,
            "totalRows": 0,
            "processedRows": 0,
            "successRows": 0,
            "failedRows": 0,
            "percent": 0,
            "message": "等待导入",
            "cancelRequested": False,
            "startedAt": now,
            "updatedAt": now,
            **payload,
        }
        self._write_progress(batch_id, progress)
        self._delete_cancel(batch_id)
        return progress

    def update(self, batch_id: int, **values: Any) -> dict[str, Any]:
        progress = self.get(batch_id) or {"batchId": batch_id}
        progress.update(values)
        total = int(progress.get("totalRows") or 0)
        processed = int(progress.get("processedRows") or 0)
        progress["percent"] = round(processed * 100 / total, 2) if total else 0
        progress["cancelRequested"] = self.is_cancel_requested(batch_id)
        progress["updatedAt"] = datetime.now(timezone.utc).isoformat()
        self._write_progress(batch_id, progress)
        return progress

    def get(self, batch_id: int) -> dict[str, Any] | None:
        if self.client is None:
            return self._memory_progress.get(batch_id)
        try:
            value = self.client.get(self.progress_key(batch_id))
            return json.loads(value) if value else None
        except Exception:
            logger.exception("Failed to read import progress from Redis; using in-memory fallback")
            return self._memory_progress.get(batch_id)

    def request_cancel(self, batch_id: int) -> dict[str, Any]:
        self._write_cancel(batch_id)
        return self.update(batch_id, status="cancel_requested", cancelRequested=True, message="正在取消导入")

    def is_cancel_requested(self, batch_id: int) -> bool:
        if self.client is None:
            return batch_id in self._memory_cancel
        try:
            return self.client.get(self.cancel_key(batch_id)) == "1"
        except Exception:
            logger.exception("Failed to read import cancel flag from Redis; using in-memory fallback")
            return batch_id in self._memory_cancel

    def _write_progress(self, batch_id: int, progress: dict[str, Any]) -> None:
        self._memory_progress[batch_id] = progress.copy()
        if self.client is None:
            return
        try:
            self.client.setex(self.progress_key(batch_id), self.ttl_seconds, json.dumps(progress, ensure_ascii=False))
        except Exception:
            logger.exception("Failed to write import progress to Redis; using in-memory fallback")

    def _write_cancel(self, batch_id: int) -> None:
        self._memory_cancel.add(batch_id)
        if self.client is None:
            return
        try:
            self.client.setex(self.cancel_key(batch_id), self.ttl_seconds, "1")
        except Exception:
            logger.exception("Failed to write import cancel flag to Redis; using in-memory fallback")

    def _delete_cancel(self, batch_id: int) -> None:
        self._memory_cancel.discard(batch_id)
        if self.client is None:
            return
        try:
            self.client.delete(self.cancel_key(batch_id))
        except Exception:
            logger.exception("Failed to delete import cancel flag from Redis; using in-memory fallback")


data_import_progress = DataImportProgressService()
