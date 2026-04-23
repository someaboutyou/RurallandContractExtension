from sqlalchemy import and_, exists, or_, select

from app.models.request_case import RequestCase
from app.models.request_case_participant import RequestCaseParticipant
from app.models.user import User


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

    def get_region_scope_prefix(self, user: User) -> str | None:
        data_scope = user.role.data_scope
        region_code = getattr(user.region, "code", None)
        if not region_code or data_scope == "all":
            return None
        if data_scope == "county":
            return region_code[:6]
        if data_scope == "town":
            return region_code[:9] if len(region_code) >= 9 else region_code[:6]
        if data_scope in {"village", "self"}:
            return region_code
        return region_code[:6]

    def get_allowed_workflow_steps(self, user: User) -> list[str]:
        user_permissions = {item.code for item in user.role.permissions}
        return [
            step_name
            for step_name, permission_code in self.workflow_step_permissions.items()
            if permission_code in user_permissions
        ]

    def build_code_scope_filters(self, column, user: User) -> list:
        if user.role.data_scope == "all":
            return []
        prefix = self.get_region_scope_prefix(user)
        if not prefix:
            return []
        return [column.like(f"{prefix}%")]

    def ensure_code_in_scope(self, user: User, code: str | None, *, detail: str = "当前数据不在可操作范围内") -> None:
        if user.role.data_scope == "all" or not code:
            return
        prefix = self.get_region_scope_prefix(user)
        if prefix and not str(code).startswith(prefix):
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    def derive_request_scope(
        self,
        *,
        issuer_code: str | None,
        contractor_code: str | None,
        contract_code: str | None,
        fallback_region_code: str | None,
    ) -> tuple[str | None, str | None]:
        scope_code = issuer_code or contractor_code or contract_code or fallback_region_code
        tenant_code = scope_code[:6] if scope_code else None
        region_source = issuer_code or contractor_code or fallback_region_code
        region_code = region_source[:12] if region_source else None
        return tenant_code, region_code

    def build_request_case_filters(self, user: User) -> list:
        if user.role.data_scope == "all":
            return []

        filters = []
        tenant_code = self.get_tenant_code(user)
        if tenant_code:
            filters.append(RequestCase.tenant_code == tenant_code)

        region_prefix = self.get_region_scope_prefix(user)
        if region_prefix:
            filters.append(RequestCase.region_code.like(f"{region_prefix}%"))

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
        tenant_code = self.get_tenant_code(user)
        if tenant_code and record.tenant_code and record.tenant_code != tenant_code:
            return False
        region_prefix = self.get_region_scope_prefix(user)
        if region_prefix and record.region_code and not record.region_code.startswith(region_prefix):
            return False
        if record.created_by_id == user.id:
            return True
        if any(item.user_id == user.id for item in record.participants):
            return True
        return record.status == "审核中" and record.current_step in self.get_allowed_workflow_steps(user)


data_access_service = DataAccessService()
