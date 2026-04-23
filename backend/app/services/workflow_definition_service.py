from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from SpiffWorkflow.spiff.parser import SpiffBpmnParser

from app.models.user import User
from app.models.workflow_definition_version import WorkflowDefinitionVersion


class WorkflowDefinitionService:
    def __init__(self) -> None:
        self.workflow_dir = Path(__file__).resolve().parent.parent / "workflows"

    def list_definitions(self, db: Session) -> list[dict]:
        version_stats = self._get_version_stats(db)
        items = []
        for file_path in sorted(self.workflow_dir.glob("*.bpmn")):
            definition = self._read_definition(file_path)
            stats = version_stats.get(file_path.stem, {})
            definition["versionCount"] = stats.get("versionCount", 0)
            definition["activeVersionId"] = stats.get("activeVersionId")
            definition["activeVersionNo"] = stats.get("activeVersionNo")
            definition["hasDraft"] = stats.get("hasDraft", True)
            definition["draftUpdatedAt"] = definition["updatedAt"] if definition["hasDraft"] else None
            items.append(definition)
        return items

    def get_definition(self, db: Session, workflow_key: str) -> dict:
        file_path = self._resolve_workflow_file(workflow_key)
        result = self._read_definition(file_path, include_content=True)
        versions = self.list_versions(db, workflow_key)
        result["versions"] = versions
        result["versionCount"] = len(versions)
        stats = self._get_version_stats(db).get(workflow_key, {})
        result["activeVersionId"] = stats.get("activeVersionId")
        result["activeVersionNo"] = stats.get("activeVersionNo")
        result["hasDraft"] = stats.get("hasDraft", True)
        result["draftUpdatedAt"] = result["updatedAt"] if result["hasDraft"] else None
        return result

    def save_definition(self, db: Session, workflow_key: str, payload: dict) -> dict:
        file_path = self.workflow_dir / f"{workflow_key}.bpmn"
        validation = self.validate_definition(payload["content"])
        if not validation["valid"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=validation["message"])

        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        file_path.write_text(payload["content"], encoding="utf-8")
        result = self._read_definition(file_path, include_content=True, fallback_name=payload["name"])
        versions = self.list_versions(db, workflow_key)
        stats = self._get_version_stats(db).get(workflow_key, {})
        result["versions"] = versions
        result["versionCount"] = len(versions)
        result["activeVersionId"] = stats.get("activeVersionId")
        result["activeVersionNo"] = stats.get("activeVersionNo")
        result["hasDraft"] = stats.get("hasDraft", True)
        result["draftUpdatedAt"] = result["updatedAt"] if result["hasDraft"] else None
        return result

    def list_versions(self, db: Session, workflow_key: str) -> list[dict]:
        stmt = (
            select(WorkflowDefinitionVersion)
            .options(joinedload(WorkflowDefinitionVersion.published_by))
            .where(WorkflowDefinitionVersion.workflow_key == workflow_key)
            .order_by(WorkflowDefinitionVersion.version_no.desc())
        )
        return [self._serialize_version(item) for item in db.scalars(stmt).all()]

    def get_version_record(self, db: Session, workflow_key: str, version_id: int | None) -> WorkflowDefinitionVersion | None:
        if version_id is None:
            return None
        stmt = (
            select(WorkflowDefinitionVersion)
            .options(joinedload(WorkflowDefinitionVersion.published_by))
            .where(
                WorkflowDefinitionVersion.id == version_id,
                WorkflowDefinitionVersion.workflow_key == workflow_key,
            )
        )
        return db.scalars(stmt).first()

    def get_active_version_record(self, db: Session, workflow_key: str) -> WorkflowDefinitionVersion | None:
        stmt = (
            select(WorkflowDefinitionVersion)
            .options(joinedload(WorkflowDefinitionVersion.published_by))
            .where(
                WorkflowDefinitionVersion.workflow_key == workflow_key,
                WorkflowDefinitionVersion.is_active.is_(True),
            )
            .order_by(WorkflowDefinitionVersion.version_no.desc())
        )
        return db.scalars(stmt).first()

    def publish_definition(self, db: Session, workflow_key: str, payload: dict, current_user: User) -> dict:
        file_path = self._resolve_workflow_file(workflow_key)
        content = file_path.read_text(encoding="utf-8")
        validation = self.validate_definition(content)
        if not validation["valid"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=validation["message"])

        existing_versions = db.scalars(
            select(WorkflowDefinitionVersion)
            .where(WorkflowDefinitionVersion.workflow_key == workflow_key)
            .order_by(WorkflowDefinitionVersion.version_no.desc())
        ).all()
        duplicate_version = next((item for item in existing_versions if item.content == content), None)
        if duplicate_version is not None:
            if duplicate_version.is_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"当前流程与生效版本 V{duplicate_version.version_no} 一致，无需重复发布",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"当前流程内容与历史版本 V{duplicate_version.version_no} 一致，请直接启用该版本或修改后再发布",
            )

        current_max = db.scalar(
            select(func.max(WorkflowDefinitionVersion.version_no)).where(
                WorkflowDefinitionVersion.workflow_key == workflow_key
            )
        )
        next_version = int(current_max or 0) + 1
        if payload.get("activate", True):
            self._deactivate_versions(db, workflow_key)

        version = WorkflowDefinitionVersion(
            workflow_key=workflow_key,
            version_no=next_version,
            name=validation["name"] or workflow_key,
            process_ids=json.dumps(validation["processIds"], ensure_ascii=False),
            content=content,
            remark=(payload.get("remark") or "").strip() or None,
            is_active=bool(payload.get("activate", True)),
            published_by_id=current_user.id,
        )
        db.add(version)
        db.commit()
        db.refresh(version)
        return self._serialize_version(version)

    def activate_version(self, db: Session, workflow_key: str, version_id: int) -> dict:
        version = db.scalar(
            select(WorkflowDefinitionVersion).where(
                WorkflowDefinitionVersion.id == version_id,
                WorkflowDefinitionVersion.workflow_key == workflow_key,
            )
        )
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="流程版本不存在")

        validation = self.validate_definition(version.content)
        if not validation["valid"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=validation["message"])

        file_path = self.workflow_dir / f"{workflow_key}.bpmn"
        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        file_path.write_text(version.content, encoding="utf-8")

        self._deactivate_versions(db, workflow_key)
        version.is_active = True
        db.commit()
        db.refresh(version)
        return self._serialize_version(version)

    def validate_definition(self, content: str) -> dict:
        try:
            process_ids = self._parse_process_ids(content)
            display_name = self._extract_process_name(content)
            return {
                "valid": True,
                "processIds": process_ids,
                "name": display_name,
                "message": "BPMN 流程定义校验通过",
            }
        except Exception as error:  # noqa: BLE001
            return {
                "valid": False,
                "processIds": [],
                "name": None,
                "message": f"BPMN 校验失败：{error}",
            }

    def _deactivate_versions(self, db: Session, workflow_key: str) -> None:
        versions = db.scalars(
            select(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.workflow_key == workflow_key)
        ).all()
        for item in versions:
            item.is_active = False

    def _get_version_stats(self, db: Session) -> dict[str, dict]:
        versions = db.scalars(select(WorkflowDefinitionVersion).order_by(WorkflowDefinitionVersion.version_no.desc())).all()
        stats: dict[str, dict] = {}
        for item in versions:
            bucket = stats.setdefault(
                item.workflow_key,
                {
                    "versionCount": 0,
                    "activeVersionId": None,
                    "activeVersionNo": None,
                    "activeVersionContent": None,
                    "latestVersionContent": None,
                },
            )
            if bucket["latestVersionContent"] is None:
                bucket["latestVersionContent"] = item.content
            bucket["versionCount"] += 1
            if item.is_active and bucket["activeVersionId"] is None:
                bucket["activeVersionId"] = item.id
                bucket["activeVersionNo"] = item.version_no
                bucket["activeVersionContent"] = item.content

        for file_path in self.workflow_dir.glob("*.bpmn"):
            workflow_key = file_path.stem
            current_content = file_path.read_text(encoding="utf-8")
            bucket = stats.setdefault(
                workflow_key,
                {
                    "versionCount": 0,
                    "activeVersionId": None,
                    "activeVersionNo": None,
                    "activeVersionContent": None,
                    "latestVersionContent": None,
                },
            )
            baseline_content = bucket["activeVersionContent"] or bucket["latestVersionContent"]
            bucket["hasDraft"] = baseline_content is None or current_content != baseline_content

        for bucket in stats.values():
            bucket.pop("activeVersionContent", None)
            bucket.pop("latestVersionContent", None)
        return stats

    def _resolve_workflow_file(self, workflow_key: str) -> Path:
        file_path = self.workflow_dir / f"{workflow_key}.bpmn"
        if not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="流程定义不存在")
        return file_path

    def _read_definition(self, file_path: Path, *, include_content: bool = False, fallback_name: str | None = None) -> dict:
        content = file_path.read_text(encoding="utf-8")
        process_ids = self._parse_process_ids(content)
        name = self._extract_process_name(content) or fallback_name or file_path.stem
        result = {
            "key": file_path.stem,
            "name": name,
            "filename": file_path.name,
            "processIds": process_ids,
            "updatedAt": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
        }
        if include_content:
            result["content"] = content
        return result

    def _serialize_version(self, item: WorkflowDefinitionVersion) -> dict:
        return {
            "id": item.id,
            "workflowKey": item.workflow_key,
            "versionNo": item.version_no,
            "name": item.name,
            "processIds": json.loads(item.process_ids or "[]"),
            "remark": item.remark,
            "isActive": item.is_active,
            "publishedByName": item.published_by.real_name if item.published_by else None,
            "createdAt": item.created_at.isoformat(),
        }

    def _parse_process_ids(self, content: str) -> list[str]:
        parser = SpiffBpmnParser()
        parser.add_bpmn_str(content.encode("utf-8"), "workflow.bpmn")
        specs = parser.find_all_specs()
        process_ids = sorted(specs.keys())
        if not process_ids:
            raise ValueError("未找到流程 process 定义")
        return process_ids

    def _extract_process_name(self, content: str) -> str | None:
        root = ElementTree.fromstring(content)
        namespace = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
        process = root.find("bpmn:process", namespace)
        if process is None:
            return None
        return process.attrib.get("name") or process.attrib.get("id")


workflow_definition_service = WorkflowDefinitionService()
