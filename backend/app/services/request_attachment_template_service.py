from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.request_attachment_template import RequestAttachmentTemplate


class RequestAttachmentTemplateService:
    def list_templates(
        self,
        db: Session,
        tenant_code: str | None = None,
        *,
        request_type: str | None = None,
        stage_code: str | None = None,
        source: str | None = None,
        parent_id: int | None = None,
        apply_parent_filter: bool = False,
    ) -> list[dict]:
        stmt = select(RequestAttachmentTemplate).order_by(
            RequestAttachmentTemplate.request_type.asc(),
            RequestAttachmentTemplate.stage_code.asc(),
            RequestAttachmentTemplate.parent_id.asc().nulls_first(),
            RequestAttachmentTemplate.sort_order.asc(),
            RequestAttachmentTemplate.id.asc(),
        )
        if tenant_code is not None:
            stmt = stmt.where(or_(RequestAttachmentTemplate.tenant_code == tenant_code, RequestAttachmentTemplate.tenant_code.is_(None)))
        if request_type:
            stmt = stmt.where(RequestAttachmentTemplate.request_type == request_type)
        if stage_code:
            stmt = stmt.where(RequestAttachmentTemplate.stage_code == stage_code)
        if source == "global":
            stmt = stmt.where(RequestAttachmentTemplate.tenant_code.is_(None))
        elif source == "tenant":
            stmt = stmt.where(RequestAttachmentTemplate.tenant_code.is_not(None))
        if apply_parent_filter:
            if parent_id is None:
                stmt = stmt.where(RequestAttachmentTemplate.parent_id.is_(None))
            else:
                stmt = stmt.where(RequestAttachmentTemplate.parent_id == parent_id)
        rows = db.scalars(stmt).all()
        child_counts = self._load_child_counts(db, [item.id for item in rows])
        return [self._serialize(item, has_children=child_counts.get(item.id, 0) > 0) for item in rows]

    def create_template(self, db: Session, payload: dict) -> dict:
        self._validate_parent(db, None, payload)
        template = RequestAttachmentTemplate(
            tenant_code=payload.get("tenantCode"),
            parent_id=payload.get("parentId"),
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
        self._validate_parent(db, template_id, payload)
        template.tenant_code = payload.get("tenantCode")
        template.parent_id = payload.get("parentId")
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
        tenant_rows = [item for item in rows if item.tenant_code == tenant_code]
        if tenant_rows:
            return [self._serialize(item) for item in tenant_rows]
        return [self._serialize(item) for item in rows if item.tenant_code is None]

    def _serialize(self, item: RequestAttachmentTemplate, *, has_children: bool = False) -> dict:
        return {
            "id": item.id,
            "tenantCode": item.tenant_code,
            "parentId": item.parent_id,
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
            "hasChildren": has_children,
        }

    def _load_child_counts(self, db: Session, parent_ids: list[int]) -> dict[int, int]:
        if not parent_ids:
            return {}
        stmt = (
            select(RequestAttachmentTemplate.parent_id, func.count(RequestAttachmentTemplate.id))
            .where(RequestAttachmentTemplate.parent_id.in_(parent_ids))
            .group_by(RequestAttachmentTemplate.parent_id)
        )
        return {parent_id: count for parent_id, count in db.execute(stmt).all() if parent_id is not None}

    def _validate_parent(self, db: Session, template_id: int | None, payload: dict) -> None:
        parent_id = payload.get("parentId")
        if not parent_id:
            return
        if template_id and template_id == parent_id:
            raise ValueError("template parent cannot be itself")
        parent = db.get(RequestAttachmentTemplate, parent_id)
        if parent is None:
            raise ValueError("parent template not found")
        if parent.request_type != payload["requestType"] or parent.stage_code != payload["stageCode"]:
            raise ValueError("parent template must belong to the same request type and stage")
        if (parent.tenant_code or None) != (payload.get("tenantCode") or None):
            raise ValueError("parent template must belong to the same tenant scope")
        if template_id:
            cursor = parent
            while cursor is not None:
                if cursor.id == template_id:
                    raise ValueError("template parent cannot be a descendant")
                cursor = cursor.parent


request_attachment_template_service = RequestAttachmentTemplateService()
