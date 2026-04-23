from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.role import Role
from app.repositories.permission_repository import permission_repository
from app.repositories.role_repository import role_repository

SYSTEM_ROLE_CODES = {
    "platform_admin",
    "village_auditor",
    "town_auditor",
    "county_auditor",
    "operator",
}

VALID_DATA_SCOPES = {"all", "county", "town", "village", "self"}


class RoleService:
    def list_roles(self, db: Session) -> list[dict]:
        records = role_repository.list_roles(db)
        return [
            {
                "id": role.id,
                "name": role.name,
                "code": role.code,
                "dataScope": role.data_scope,
                "description": role.description,
                "userCount": user_count,
                "isSystem": role.code in SYSTEM_ROLE_CODES,
                "permissionCodes": sorted(item.code for item in role.permissions),
            }
            for role, user_count in records
        ]

    def create_role(self, db: Session, payload: dict) -> dict:
        self._validate_data_scope(payload["dataScope"])
        self._ensure_code_unique(db, payload["code"])
        permissions = self._resolve_permissions(db, payload.get("permissionCodes", []))
        role = Role(
            name=payload["name"].strip(),
            code=payload["code"].strip(),
            data_scope=payload["dataScope"],
            description=self._normalize_optional(payload.get("description")),
        )
        role.permissions = permissions
        role = role_repository.add_role(db, role)
        return self.serialize_role(db, role)

    def update_role(self, db: Session, role_id: int, payload: dict) -> dict:
        role = self._get_role_or_404(db, role_id)
        self._validate_data_scope(payload["dataScope"])
        new_code = payload["code"].strip()
        if role.code in SYSTEM_ROLE_CODES and new_code != role.code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="系统内置角色编码不允许修改")
        self._ensure_code_unique(db, new_code, exclude_id=role.id)
        role.permissions = self._resolve_permissions(db, payload.get("permissionCodes", []))
        role.name = payload["name"].strip()
        role.code = new_code
        role.data_scope = payload["dataScope"]
        role.description = self._normalize_optional(payload.get("description"))
        role = role_repository.update_role(db, role)
        return self.serialize_role(db, role)

    def delete_role(self, db: Session, role_id: int) -> None:
        role = self._get_role_or_404(db, role_id)
        if role.code in SYSTEM_ROLE_CODES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="系统内置角色不允许删除")
        if role_repository.count_users(db, role.id) > 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色下仍有用户，不能删除")
        role_repository.delete_role(db, role)

    def serialize_role(self, db: Session, role: Role) -> dict:
        return {
            "id": role.id,
            "name": role.name,
            "code": role.code,
            "dataScope": role.data_scope,
            "description": role.description,
            "userCount": role_repository.count_users(db, role.id),
            "isSystem": role.code in SYSTEM_ROLE_CODES,
            "permissionCodes": sorted(item.code for item in role.permissions),
        }

    def _get_role_or_404(self, db: Session, role_id: int) -> Role:
        role = role_repository.get_role(db, role_id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
        return role

    def _ensure_code_unique(self, db: Session, code: str, *, exclude_id: int | None = None) -> None:
        existed = role_repository.get_role_by_code(db, code.strip())
        if existed and existed.id != exclude_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色编码已存在")

    def _validate_data_scope(self, value: str) -> None:
        if value not in VALID_DATA_SCOPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据权限范围不合法")

    def _resolve_permissions(self, db: Session, codes: list[str]) -> list:
        normalized_codes = sorted({code.strip() for code in codes if code and code.strip()})
        permissions = permission_repository.list_by_codes(db, normalized_codes)
        if len(permissions) != len(normalized_codes):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="存在无效的权限编码")
        by_code = {item.code: item for item in permissions}
        return [by_code[code] for code in normalized_codes]

    def _normalize_optional(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


role_service = RoleService()
