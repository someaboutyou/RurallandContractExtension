from fastapi import HTTPException, status
from sqlalchemy import and_, any_, bindparam, create_engine, event, false
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import String
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria

from app.core.config import settings
from app.db import base as _base  # noqa: F401  Ensures all ORM models are registered.
from app.models.base import TenantScopedMixin
from app.services.data_access_service import data_access_service

engine = create_engine(settings.sqlalchemy_database_uri, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def set_current_user(session: Session, user) -> None:
    data_scope = user.role.data_scope
    tenant_code = data_access_service.get_tenant_code(user)
    region_permissions = tuple(
        (item.tenant_code, item.region_code, item.level)
        for item in data_access_service.get_region_permissions(user)
    )
    session.info["current_user"] = user
    session.info["current_user_data_scope"] = data_scope
    session.info["current_user_tenant_code"] = tenant_code
    session.info["current_user_region_permissions"] = region_permissions


@event.listens_for(Session, "do_orm_execute")
def _add_tenant_scope(execute_state):
    if not execute_state.is_select or execute_state.execution_options.get("skip_tenant_scope"):
        return
    data_scope = execute_state.session.info.get("current_user_data_scope")
    if data_scope is None:
        return
    if data_scope == "all":
        return
    tenant_code = execute_state.session.info.get("current_user_tenant_code")
    permissions = execute_state.session.info.get("current_user_region_permissions") or ()
    if not tenant_code or not permissions:
        criteria = lambda cls: false()
    else:
        tenant_param = bindparam("tenant_scope_code", value=tenant_code)
        region_patterns_param = bindparam(
            "region_scope_patterns",
            value=[permission[1] + "%" for permission in permissions],
            type_=ARRAY(String),
        )
        criteria = lambda cls: and_(cls.tenant_code == tenant_param, cls.region_code.like(any_(region_patterns_param)))
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantScopedMixin,
            criteria,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _fill_tenant_scope(session, _flush_context, _instances):
    data_scope = session.info.get("current_user_data_scope")
    tenant_scope = session.info.get("current_user_tenant_code")
    permissions = session.info.get("current_user_region_permissions") or ()
    current_user = session.info.get("current_user")
    for item in session.new.union(session.dirty):
        if not isinstance(item, TenantScopedMixin):
            continue
        region_code = getattr(item, "region_code", None)
        if not region_code:
            region_code = _derive_region_code(item)
        if not region_code and current_user is not None:
            region_code = getattr(getattr(current_user, "region", None), "code", None)
        region_code = data_access_service.normalize_region_code(region_code)
        if region_code:
            item.region_code = region_code
        tenant_code = getattr(item, "tenant_code", None) or data_access_service.derive_tenant_code(region_code)
        if tenant_code:
            item.tenant_code = tenant_code
        if data_scope is not None:
            _validate_scope(data_scope, tenant_scope, permissions, item)


def _derive_region_code(item) -> str | None:
    for attr in (
        "fbfbm",
        "source_fbfbm",
        "dkbm",
        "source_dkbm",
        "cbfbm",
        "cbhtbm",
        "issuer_code",
        "contractor_code",
        "contract_code",
        "source_cbfbm",
        "target_cbfbm",
        "new_cbfbm",
        "from_cbfbm",
        "to_cbfbm",
    ):
        value = getattr(item, attr, None)
        if value:
            return str(value)
    request_case = getattr(item, "request_case", None)
    if request_case is not None:
        return getattr(request_case, "region_code", None)
    return None


def _validate_scope(data_scope: str, tenant_scope: str | None, permissions: tuple, item) -> None:
    if data_scope == "all":
        return
    if not tenant_scope or item.tenant_code != tenant_scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前数据不属于当前租户",
        )
    if not any(str(item.region_code).startswith(permission[1]) for permission in permissions):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前区域不在可操作范围内",
        )
