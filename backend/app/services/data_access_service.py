from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, false, or_, select

from app.models.request_case import RequestCase
from app.models.request_case_participant import RequestCaseParticipant
from app.models.user import User


LEVEL_BY_LENGTH = {6: "county", 9: "town", 12: "village", 14: "group"}


@dataclass(frozen=True)
class RegionPermission:
    tenant_code: str
    region_code: str
    level: str


class DataAccessService:
    workflow_step_permissions = {
        "村级审核": "requests.review.village",
        "镇级审核": "requests.review.town",
        "县级审核": "requests.review.county",
    }

    def get_tenant_code(self, user: User) -> str | None:
        if getattr(user, "tenant_code", None):
            return user.tenant_code
        region_code = getattr(user.region, "code", None)
        return region_code[:6] if region_code else None

    def normalize_region_code(self, code: str | None) -> str | None:
        if not code:
            return None
        text = str(code).strip()
        if len(text) >= 14:
            return text[:14]
        if len(text) >= 12:
            return text[:12]
        if len(text) >= 9:
            return text[:9]
        return text[:6] if len(text) >= 6 else text

    def derive_tenant_code(self, code: str | None) -> str | None:
        normalized = self.normalize_region_code(code)
        return normalized[:6] if normalized and len(normalized) >= 6 else None

    def derive_level(self, code: str | None) -> str:
        normalized = self.normalize_region_code(code)
        return LEVEL_BY_LENGTH.get(len(normalized or ""), "custom")

    def get_region_permissions(self, user: User) -> list[RegionPermission]:
        if user.role.data_scope == "all":
            return []
        tenant_code = self.get_tenant_code(user)
        items = [
            RegionPermission(
                tenant_code=tenant_code or item.tenant_code,
                region_code=item.region_code,
                level=item.level,
            )
            for item in getattr(user, "region_permissions", [])
            if item.region_code and (tenant_code is None or item.tenant_code == tenant_code)
        ]
        if items:
            return items
        fallback_code = getattr(user.region, "code", None)
        if fallback_code and tenant_code:
            normalized = self.normalize_region_code(fallback_code)
            return [RegionPermission(tenant_code=tenant_code, region_code=normalized, level=self.derive_level(normalized))]
        return []

    def build_tenant_filter(self, model, user: User):
        if user.role.data_scope == "all":
            return None
        tenant_code = self.get_tenant_code(user)
        if not tenant_code:
            return false()
        return getattr(model, "tenant_code") == tenant_code

    def build_region_filter(self, model, user: User):
        if user.role.data_scope == "all":
            return None
        permissions = self.get_region_permissions(user)
        if not permissions:
            return false()
        region_column = getattr(model, "region_code")
        return or_(
            *[
                region_column.like(f"{permission.region_code}%")
                for permission in permissions
            ]
        )

    def build_scoped_filter(self, model, user: User):
        if user.role.data_scope == "all":
            return None
        tenant_filter = self.build_tenant_filter(model, user)
        if hasattr(model, "region_code"):
            region_filter = self.build_region_filter(model, user)
            return and_(tenant_filter, region_filter)
        return tenant_filter

    def get_data_permission_sql(
        self,
        user: User,
        *,
        table_alias: str,
        tenant_column: str = "tenant_code",
        region_column: str = "region_code",
    ) -> str:
        if user.role.data_scope == "all":
            return "1=1"
        tenant_code = self.get_tenant_code(user)
        if not tenant_code:
            return "1=0"
        permissions = self.get_region_permissions(user)
        if not permissions:
            return "1=0"
        clauses = [
            f"{table_alias}.{region_column} LIKE '{item.region_code}%'"
            for item in permissions
        ]
        return f"({table_alias}.{tenant_column} = '{tenant_code}' AND (" + " OR ".join(clauses) + "))"

    def ensure_code_in_scope(self, user: User, code: str | None, *, detail: str = "当前数据不在可操作范围内") -> None:
        if user.role.data_scope == "all" or not code:
            return
        normalized = self.normalize_region_code(code)
        tenant_code = self.derive_tenant_code(normalized)
        if tenant_code != self.get_tenant_code(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        for permission in self.get_region_permissions(user):
            if normalized.startswith(permission.region_code):
                return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    def ensure_region_in_scope(self, user: User, region_code: str | None, *, detail: str = "当前区域不在可操作范围内") -> None:
        self.ensure_code_in_scope(user, region_code, detail=detail)

    def derive_request_scope(
        self,
        *,
        issuer_code: str | None,
        contractor_code: str | None,
        contract_code: str | None,
        fallback_region_code: str | None,
    ) -> tuple[str | None, str | None]:
        scope_code = issuer_code or contractor_code or contract_code or fallback_region_code
        region_code = self.normalize_region_code(scope_code)
        tenant_code = self.derive_tenant_code(region_code)
        return tenant_code, region_code

    def build_code_scope_filters(self, column, user: User) -> list:
        if user.role.data_scope == "all":
            return []
        permissions = self.get_region_permissions(user)
        if not permissions:
            return [false()]
        return [or_(*[column.like(f"{item.region_code}%") for item in permissions])]

    def get_allowed_workflow_steps(self, user: User) -> list[str]:
        user_permissions = {item.code for item in user.role.permissions}
        return [
            step_name
            for step_name, permission_code in self.workflow_step_permissions.items()
            if permission_code in user_permissions
        ]

    def build_request_case_filters(self, user: User) -> list:
        if user.role.data_scope == "all":
            return []

        filters = []
        scope_filter = self.build_scoped_filter(RequestCase, user)
        if scope_filter is not None:
            filters.append(scope_filter)

        allowed_steps = self.get_allowed_workflow_steps(user)
        visibility_conditions = [
            RequestCase.created_by_id == user.id,
            exists(
                select(RequestCaseParticipant.id).where(
                    and_(
                        RequestCaseParticipant.case_id == RequestCase.id,
                        RequestCaseParticipant.user_id == user.id,
                    )
                )
            ),
        ]
        if allowed_steps:
            visibility_conditions.append(
                and_(
                    RequestCase.status == "审核中",
                    RequestCase.current_step.in_(allowed_steps),
                )
            )
        filters.append(or_(*visibility_conditions))
        return filters

    def can_access_request_case(self, user: User, record: RequestCase) -> bool:
        if user.role.data_scope == "all":
            return True
        tenant_code = self.derive_tenant_code(record.region_code or record.tenant_code)
        region_code = self.normalize_region_code(record.region_code)
        if not region_code:
            return False
        if not any(
            tenant_code == permission.tenant_code and region_code.startswith(permission.region_code)
            for permission in self.get_region_permissions(user)
        ):
            return False
        if record.created_by_id == user.id:
            return True
        if any(item.user_id == user.id for item in record.participants):
            return True
        return record.status == "审核中" and record.current_step in self.get_allowed_workflow_steps(user)


data_access_service = DataAccessService()
