from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.request_workflow_mapping import RequestWorkflowMapping
from app.models.user import User
from app.models.workflow_definition_version import WorkflowDefinitionVersion
from app.services.workflow_definition_service import workflow_definition_service


class RequestWorkflowMappingService:
    def list_mappings(self, db: Session) -> list[dict]:
        stmt = (
            select(RequestWorkflowMapping)
            .options(
                joinedload(RequestWorkflowMapping.tenant),
                joinedload(RequestWorkflowMapping.workflow_version),
            )
            .order_by(RequestWorkflowMapping.tenant_code.asc().nullsfirst(), RequestWorkflowMapping.sort_order.asc())
        )
        return [self._serialize(item) for item in db.scalars(stmt).all()]

    def list_workflow_options(self, db: Session, current_user: User) -> dict:
        definitions = workflow_definition_service.list_definitions(db)
        definition_map = {item["key"]: item for item in definitions}

        stmt = (
            select(RequestWorkflowMapping)
            .options(
                joinedload(RequestWorkflowMapping.tenant),
                joinedload(RequestWorkflowMapping.workflow_version),
            )
            .where(
                RequestWorkflowMapping.enabled.is_(True),
                or_(RequestWorkflowMapping.tenant_code == current_user.tenant_code, RequestWorkflowMapping.tenant_code.is_(None)),
            )
            .order_by(RequestWorkflowMapping.request_type.asc(), RequestWorkflowMapping.tenant_code.desc().nullslast())
        )
        rows = db.scalars(stmt).all()

        resolved: dict[str, RequestWorkflowMapping] = {}
        for item in rows:
            current = resolved.get(item.request_type)
            if current is None:
                resolved[item.request_type] = item
                continue
            if current.tenant_code is None and item.tenant_code == current_user.tenant_code:
                resolved[item.request_type] = item

        options = []
        for request_type, item in sorted(resolved.items(), key=lambda pair: pair[1].sort_order):
            workflow_meta = definition_map.get(item.workflow_key, {})
            options.append(
                {
                    "requestType": request_type,
                    "workflowKey": item.workflow_key,
                    "workflowName": workflow_meta.get("name") or item.workflow_key,
                    "workflowVersionId": item.workflow_version_id,
                    "workflowVersionNo": item.workflow_version_no,
                    "tenantCode": item.tenant_code,
                    "source": "tenant" if item.tenant_code else "global",
                }
            )

        workflows = [
            {
                "key": item["key"],
                "name": item["name"],
                "activeVersionId": item.get("activeVersionId"),
                "activeVersionNo": item.get("activeVersionNo"),
            }
            for item in definitions
        ]
        return {"mappings": options, "workflows": workflows}

    def create_mapping(self, db: Session, payload: dict) -> dict:
        workflow_version = self._validate_workflow_binding(db, payload["workflowKey"], payload.get("workflowVersionId"))
        self._ensure_unique_request_type(db, payload["tenantCode"], payload["requestType"])

        record = RequestWorkflowMapping(
            tenant_code=payload["tenantCode"],
            request_type=payload["requestType"],
            workflow_key=payload["workflowKey"],
            workflow_version_id=workflow_version.id if workflow_version else None,
            workflow_version_no=workflow_version.version_no if workflow_version else None,
            enabled=payload["enabled"],
            sort_order=payload["sortOrder"],
            remark=(payload.get("remark") or "").strip() or None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return self._serialize(self._reload(db, record.id))

    def update_mapping(self, db: Session, mapping_id: int, payload: dict) -> dict:
        record = self._get_mapping(db, mapping_id)
        workflow_version = self._validate_workflow_binding(db, payload["workflowKey"], payload.get("workflowVersionId"))
        self._ensure_unique_request_type(db, payload["tenantCode"], payload["requestType"], exclude_id=mapping_id)

        record.tenant_code = payload["tenantCode"]
        record.request_type = payload["requestType"]
        record.workflow_key = payload["workflowKey"]
        record.workflow_version_id = workflow_version.id if workflow_version else None
        record.workflow_version_no = workflow_version.version_no if workflow_version else None
        record.enabled = payload["enabled"]
        record.sort_order = payload["sortOrder"]
        record.remark = (payload.get("remark") or "").strip() or None
        db.commit()
        return self._serialize(self._reload(db, mapping_id))

    def delete_mapping(self, db: Session, mapping_id: int) -> None:
        record = self._get_mapping(db, mapping_id)
        db.delete(record)
        db.commit()

    def resolve_workflow_binding(
        self,
        db: Session,
        *,
        request_type: str,
        tenant_code: str | None,
        explicit_workflow_code: str | None = None,
        explicit_workflow_version_id: int | None = None,
    ) -> dict:
        explicit_code = (explicit_workflow_code or "").strip() or None
        if explicit_code:
            workflow_version = self._validate_workflow_binding(db, explicit_code, explicit_workflow_version_id)
            if workflow_version is None:
                workflow_version = workflow_definition_service.get_active_version_record(db, explicit_code)
            return self._build_binding_result(explicit_code, workflow_version)

        stmt = (
            select(RequestWorkflowMapping)
            .options(joinedload(RequestWorkflowMapping.workflow_version))
            .where(
                RequestWorkflowMapping.request_type == request_type,
                RequestWorkflowMapping.enabled.is_(True),
                or_(RequestWorkflowMapping.tenant_code == tenant_code, RequestWorkflowMapping.tenant_code.is_(None)),
            )
            .order_by(RequestWorkflowMapping.tenant_code.desc().nullslast(), RequestWorkflowMapping.sort_order.asc())
        )
        record = db.scalars(stmt).first()
        if record is not None:
            workflow_version = record.workflow_version
            if workflow_version is None:
                workflow_version = workflow_definition_service.get_active_version_record(db, record.workflow_key)
            return self._build_binding_result(record.workflow_key, workflow_version)

        fallback = workflow_definition_service.list_definitions(db)
        if fallback:
            workflow_key = fallback[0]["key"]
            return self._build_binding_result(workflow_key, workflow_definition_service.get_active_version_record(db, workflow_key))
        return {"workflowCode": "rural_contract", "workflowVersionId": None, "workflowVersionNo": None, "workflowContent": None}

    def _build_binding_result(self, workflow_key: str, workflow_version: WorkflowDefinitionVersion | None) -> dict:
        return {
            "workflowCode": workflow_key,
            "workflowVersionId": workflow_version.id if workflow_version else None,
            "workflowVersionNo": workflow_version.version_no if workflow_version else None,
            "workflowContent": workflow_version.content if workflow_version else None,
        }

    def _validate_workflow_binding(
        self,
        db: Session,
        workflow_key: str,
        workflow_version_id: int | None,
    ) -> WorkflowDefinitionVersion | None:
        self._validate_workflow_key(db, workflow_key)
        if workflow_version_id is None:
            return None
        workflow_version = workflow_definition_service.get_version_record(db, workflow_key, workflow_version_id)
        if workflow_version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定的流程版本不存在或不属于当前流程")
        return workflow_version

    def _validate_workflow_key(self, db: Session, workflow_key: str) -> None:
        definitions = workflow_definition_service.list_definitions(db)
        if not any(item["key"] == workflow_key for item in definitions):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定的流程定义不存在")

    def _ensure_unique_request_type(
        self,
        db: Session,
        tenant_code: str | None,
        request_type: str,
        *,
        exclude_id: int | None = None,
    ) -> None:
        stmt = select(RequestWorkflowMapping).where(
            RequestWorkflowMapping.request_type == request_type,
            RequestWorkflowMapping.tenant_code == tenant_code,
        )
        if exclude_id is not None:
            stmt = stmt.where(RequestWorkflowMapping.id != exclude_id)
        existing = db.scalars(stmt).first()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前租户下该业务类型已配置流程映射")

    def _get_mapping(self, db: Session, mapping_id: int) -> RequestWorkflowMapping:
        record = self._reload(db, mapping_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="业务流程映射不存在")
        return record

    def _reload(self, db: Session, mapping_id: int) -> RequestWorkflowMapping | None:
        stmt = (
            select(RequestWorkflowMapping)
            .options(
                joinedload(RequestWorkflowMapping.tenant),
                joinedload(RequestWorkflowMapping.workflow_version),
            )
            .where(RequestWorkflowMapping.id == mapping_id)
        )
        return db.scalars(stmt).first()

    def _serialize(self, item: RequestWorkflowMapping) -> dict:
        definition = workflow_definition_service._read_definition(  # noqa: SLF001
            workflow_definition_service._resolve_workflow_file(item.workflow_key)
        )
        return {
            "id": item.id,
            "tenantCode": item.tenant_code,
            "tenantName": item.tenant.name if item.tenant else "全局默认",
            "requestType": item.request_type,
            "workflowKey": item.workflow_key,
            "workflowName": definition["name"],
            "workflowVersionId": item.workflow_version_id,
            "workflowVersionNo": item.workflow_version_no,
            "workflowVersionLabel": f"V{item.workflow_version_no}" if item.workflow_version_no else "跟随当前生效版本",
            "enabled": item.enabled,
            "sortOrder": item.sort_order,
            "remark": item.remark,
            "source": "tenant" if item.tenant_code else "global",
            "createdAt": item.created_at.isoformat(),
            "updatedAt": item.updated_at.isoformat(),
        }


request_workflow_mapping_service = RequestWorkflowMappingService()
