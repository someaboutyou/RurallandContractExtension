from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.request_attachment_template import RequestAttachmentTemplate


class RequestAttachmentTemplateService:
    def list_templates(self, db: Session, tenant_code: str | None = None) -> list[dict]:
        stmt = select(RequestAttachmentTemplate).order_by(
            RequestAttachmentTemplate.request_type.asc(),
            RequestAttachmentTemplate.stage_code.asc(),
            RequestAttachmentTemplate.sort_order.asc(),
            RequestAttachmentTemplate.id.asc(),
        )
        if tenant_code is not None:
            stmt = stmt.where(or_(RequestAttachmentTemplate.tenant_code == tenant_code, RequestAttachmentTemplate.tenant_code.is_(None)))
        return [self._serialize(item) for item in db.scalars(stmt).all()]

    def create_template(self, db: Session, payload: dict) -> dict:
        template = RequestAttachmentTemplate(
            tenant_code=payload.get("tenantCode"),
            request_type=payload["requestType"],
            stage_code=payload["stageCode"],
            stage_name=payload.get("stageName"),
            category=payload["category"],
            name=payload["name"],
            required=payload.get("required", True),
            description=payload.get("description"),
            example_file_name=payload.get("exampleFileName"),
            sort_order=payload.get("sortOrder", 0),
            enabled=payload.get("enabled", True),
        )
        db.add(template)
        db.commit()
        db.refresh(template)
        return self._serialize(template)

    def update_template(self, db: Session, template_id: int, payload: dict) -> dict:
        template = db.get(RequestAttachmentTemplate, template_id)
        if template is None:
            raise ValueError("template not found")
        template.tenant_code = payload.get("tenantCode")
        template.request_type = payload["requestType"]
        template.stage_code = payload["stageCode"]
        template.stage_name = payload.get("stageName")
        template.category = payload["category"]
        template.name = payload["name"]
        template.required = payload.get("required", True)
        template.description = payload.get("description")
        template.example_file_name = payload.get("exampleFileName")
        template.sort_order = payload.get("sortOrder", 0)
        template.enabled = payload.get("enabled", True)
        db.commit()
        db.refresh(template)
        return self._serialize(template)

    def delete_template(self, db: Session, template_id: int) -> None:
        template = db.get(RequestAttachmentTemplate, template_id)
        if template is None:
            raise ValueError("template not found")
        db.delete(template)
        db.commit()

    def resolve_templates(
        self,
        db: Session,
        *,
        request_type: str,
        stage_code: str,
        tenant_code: str | None,
    ) -> list[dict]:
        stmt = (
            select(RequestAttachmentTemplate)
            .where(
                and_(
                    RequestAttachmentTemplate.request_type == request_type,
                    RequestAttachmentTemplate.stage_code == stage_code,
                    RequestAttachmentTemplate.enabled.is_(True),
                    or_(RequestAttachmentTemplate.tenant_code == tenant_code, RequestAttachmentTemplate.tenant_code.is_(None)),
                )
            )
            .order_by(
                RequestAttachmentTemplate.tenant_code.desc().nulls_last(),
                RequestAttachmentTemplate.sort_order.asc(),
                RequestAttachmentTemplate.id.asc(),
            )
        )
        rows = db.scalars(stmt).all()
        merged: dict[tuple[str | None, str], RequestAttachmentTemplate] = {}
        for item in rows:
            key = (item.tenant_code, item.category)
            merged.setdefault(key, item)
        tenant_rows = [item for item in merged.values() if item.tenant_code == tenant_code]
        if tenant_rows:
            return [self._serialize(item) for item in tenant_rows]
        return [self._serialize(item) for item in merged.values() if item.tenant_code is None]

    def _serialize(self, item: RequestAttachmentTemplate) -> dict:
        return {
            "id": item.id,
            "tenantCode": item.tenant_code,
            "requestType": item.request_type,
            "stageCode": item.stage_code,
            "stageName": item.stage_name,
            "category": item.category,
            "name": item.name,
            "required": item.required,
            "description": item.description,
            "exampleFileName": item.example_file_name,
            "sortOrder": item.sort_order,
            "enabled": item.enabled,
        }


request_attachment_template_service = RequestAttachmentTemplateService()
