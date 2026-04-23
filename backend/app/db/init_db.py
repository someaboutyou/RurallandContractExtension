from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.fbf import Fbf
from app.models.permission import Permission
from app.models.region import Region
from app.models.request_workflow_mapping import RequestWorkflowMapping
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User

DEFAULT_ROLES = [
    {"name": "平台管理员", "code": "platform_admin", "data_scope": "all", "description": "系统平台管理员，拥有全局管理权限。"},
    {"name": "村级审核员", "code": "village_auditor", "data_scope": "village", "description": "负责村级业务审核。"},
    {"name": "镇级审核员", "code": "town_auditor", "data_scope": "town", "description": "负责镇级业务审核。"},
    {"name": "县级审核员", "code": "county_auditor", "data_scope": "county", "description": "负责县级业务审核。"},
    {"name": "业务员", "code": "operator", "data_scope": "town", "description": "负责申请受理、补录和流转。"},
]

DEFAULT_REGIONS = [
    {"name": "江苏省", "code": "320000", "level": "province", "full_name": "江苏省", "parent_code": None},
    {"name": "如东县", "code": "320623", "level": "county", "full_name": "江苏省 / 南通市 / 如东县", "parent_code": "320000"},
    {"name": "掘港街道", "code": "320623100", "level": "town", "full_name": "江苏省 / 南通市 / 如东县 / 掘港街道", "parent_code": "320623"},
    {"name": "岔河镇", "code": "320623101", "level": "town", "full_name": "江苏省 / 南通市 / 如东县 / 岔河镇", "parent_code": "320623"},
    {
        "name": "掘港某村",
        "code": "320623100200",
        "level": "village",
        "full_name": "江苏省 / 南通市 / 如东县 / 掘港街道 / 某村",
        "parent_code": "320623100",
    },
    {
        "name": "岔河某村",
        "code": "320623101300",
        "level": "village",
        "full_name": "江苏省 / 南通市 / 如东县 / 岔河镇 / 某村",
        "parent_code": "320623101",
    },
]

DEFAULT_USERS = [
    {"username": "admin", "real_name": "超级管理员", "mobile": "13900000001", "role_code": "platform_admin", "region_code": "320623"},
    {"username": "county_auditor", "real_name": "县级审核员", "mobile": "13900000002", "role_code": "county_auditor", "region_code": "320623"},
    {"username": "town_auditor", "real_name": "镇级审核员", "mobile": "13900000003", "role_code": "town_auditor", "region_code": "320623100"},
    {"username": "village_auditor", "real_name": "村级审核员", "mobile": "13900000004", "role_code": "village_auditor", "region_code": "320623100200"},
    {"username": "town_operator", "real_name": "镇级业务员", "mobile": "13900000005", "role_code": "operator", "region_code": "320623100"},
]

DEFAULT_PERMISSIONS = [
    {"name": "查看工作台", "code": "dashboard.view", "group_name": "平台首页", "category": "menu", "description": "允许进入工作台页面。"},
    {"name": "查看人员权限", "code": "users.view", "group_name": "人员权限", "category": "menu", "description": "允许查看用户管理页面。"},
    {"name": "管理用户", "code": "users.manage", "group_name": "人员权限", "category": "action", "description": "允许新增、编辑、删除和重置用户密码。"},
    {"name": "查看角色权限", "code": "roles.view", "group_name": "人员权限", "category": "menu", "description": "允许查看角色与权限配置。"},
    {"name": "管理角色权限", "code": "roles.manage", "group_name": "人员权限", "category": "action", "description": "允许编辑角色和分配权限。"},
    {"name": "查看发包方", "code": "issuers.view", "group_name": "发包方管理", "category": "menu", "description": "允许查看发包方列表。"},
    {"name": "管理发包方", "code": "issuers.manage", "group_name": "发包方管理", "category": "action", "description": "允许维护发包方信息。"},
    {"name": "查看承包方", "code": "contractors.view", "group_name": "承包方管理", "category": "menu", "description": "允许查看承包方列表。"},
    {"name": "管理承包方", "code": "contractors.manage", "group_name": "承包方管理", "category": "action", "description": "允许维护承包方及家庭成员信息。"},
    {"name": "查看业务申请", "code": "requests.view", "group_name": "业务申请", "category": "menu", "description": "允许查看业务申请页面。"},
    {"name": "管理业务申请", "code": "requests.manage", "group_name": "业务申请", "category": "action", "description": "允许新增、编辑、删除业务申请。"},
    {"name": "提交业务申请", "code": "requests.submit", "group_name": "业务申请", "category": "action", "description": "允许提交业务申请。"},
    {"name": "村级审核", "code": "requests.review.village", "group_name": "业务申请", "category": "action", "description": "允许办理村级审核节点。"},
    {"name": "镇级审核", "code": "requests.review.town", "group_name": "业务申请", "category": "action", "description": "允许办理镇级审核节点。"},
    {"name": "县级审核", "code": "requests.review.county", "group_name": "业务申请", "category": "action", "description": "允许办理县级审核节点。"},
]

DEFAULT_ROLE_PERMISSIONS = {
    "platform_admin": [item["code"] for item in DEFAULT_PERMISSIONS],
    "village_auditor": ["dashboard.view", "issuers.view", "contractors.view", "requests.view", "requests.review.village"],
    "town_auditor": ["dashboard.view", "issuers.view", "contractors.view", "requests.view", "requests.review.town"],
    "county_auditor": ["dashboard.view", "issuers.view", "contractors.view", "requests.view", "requests.review.county"],
    "operator": [
        "dashboard.view",
        "issuers.view",
        "issuers.manage",
        "contractors.view",
        "contractors.manage",
        "requests.view",
        "requests.manage",
        "requests.submit",
        "requests.review.village",
        "requests.review.town",
    ],
}

DEFAULT_REQUEST_TYPES = [
    "首次登记",
    "变更登记",
    "注销登记",
    "证书补发",
]


def seed_initial_data(db: Session) -> None:
    sync_demo_user_passwords(db)
    ensure_default_regions(db)
    sync_regions_from_business_codes(db)
    ensure_tenants(db)
    sync_region_tenants(db)
    ensure_default_roles(db)
    ensure_default_permissions(db)
    ensure_default_role_permissions(db)
    ensure_default_users(db)
    ensure_default_request_workflow_mappings(db)


def ensure_default_regions(db: Session) -> None:
    existing_codes = set(db.scalars(select(Region.code)).all())
    if all(item["code"] in existing_codes for item in DEFAULT_REGIONS):
        return

    created_by_code: dict[str, Region] = {}
    for item in DEFAULT_REGIONS:
        region = db.scalar(select(Region).where(Region.code == item["code"]))
        if region is None:
            parent_id = None
            if item["parent_code"]:
                parent = created_by_code.get(item["parent_code"]) or db.scalar(
                    select(Region).where(Region.code == item["parent_code"])
                )
                parent_id = parent.id if parent else None
            region = Region(
                name=item["name"],
                code=item["code"],
                level=item["level"],
                full_name=item["full_name"],
                parent_id=parent_id,
            )
            db.add(region)
            db.flush()
        created_by_code[item["code"]] = region
    db.commit()


def sync_regions_from_business_codes(db: Session) -> None:
    village_codes = db.scalars(select(func.substring(Fbf.fbfbm, 1, 12)).distinct()).all()
    if not village_codes:
        return

    created = False
    province_code = "auto-province"
    province = db.scalar(select(Region).where(Region.code == province_code))
    if province is None:
        province = Region(
            name="导入数据省级占位",
            code=province_code,
            level="province",
            full_name="导入数据省级占位",
            parent_id=None,
            tenant_code=None,
        )
        db.add(province)
        db.flush()
        created = True

    for village_code in sorted({code for code in village_codes if code}):
        county_code = village_code[:6]
        town_code = village_code[:9]

        county = db.scalar(select(Region).where(Region.code == county_code))
        if county is None:
            county = Region(
                name=f"{county_code} 县域",
                code=county_code,
                level="county",
                full_name=f"导入数据 / {county_code} 县域",
                parent_id=province.id,
                tenant_code=county_code,
            )
            db.add(county)
            db.flush()
            created = True

        town = db.scalar(select(Region).where(Region.code == town_code))
        if town is None:
            town = Region(
                name=f"{town_code} 镇级区域",
                code=town_code,
                level="town",
                full_name=f"{county.full_name} / {town_code} 镇级区域",
                parent_id=county.id,
                tenant_code=county_code,
            )
            db.add(town)
            db.flush()
            created = True

        village = db.scalar(select(Region).where(Region.code == village_code))
        if village is None:
            village = Region(
                name=f"{village_code} 村级区域",
                code=village_code,
                level="village",
                full_name=f"{town.full_name} / {village_code} 村级区域",
                parent_id=town.id,
                tenant_code=county_code,
            )
            db.add(village)
            db.flush()
            created = True

    if created:
        db.commit()


def ensure_tenants(db: Session) -> None:
    county_regions = db.scalars(select(Region).where(Region.level == "county").order_by(Region.code)).all()
    changed = False
    for region in county_regions:
        tenant_code = region.code[:6]
        tenant = db.get(Tenant, tenant_code)
        if tenant is None:
            tenant = Tenant(
                code=tenant_code,
                name=region.name,
                region_code=region.code,
                status="active",
                description=f"按县级行政区 {region.code} 建立的租户",
            )
            db.add(tenant)
            changed = True
            continue
        updated = False
        if tenant.name != region.name:
            tenant.name = region.name
            updated = True
        if tenant.region_code != region.code:
            tenant.region_code = region.code
            updated = True
        if tenant.status != "active":
            tenant.status = "active"
            updated = True
        changed = changed or updated
    if changed:
        db.commit()


def sync_region_tenants(db: Session) -> None:
    changed = False
    regions = db.scalars(select(Region)).all()
    for region in regions:
        expected_tenant_code = region.code[:6] if region.level in {"county", "town", "village"} else None
        if region.tenant_code != expected_tenant_code:
            region.tenant_code = expected_tenant_code
            changed = True
    if changed:
        db.commit()


def ensure_default_roles(db: Session) -> None:
    changed = False
    for item in DEFAULT_ROLES:
        role = db.scalar(select(Role).where(Role.code == item["code"]))
        if role is None:
            role = Role(
                name=item["name"],
                code=item["code"],
                data_scope=item["data_scope"],
                description=item["description"],
            )
            db.add(role)
            changed = True
            continue
        if role.name != item["name"] or role.data_scope != item["data_scope"] or role.description != item["description"]:
            role.name = item["name"]
            role.data_scope = item["data_scope"]
            role.description = item["description"]
            changed = True
    if changed:
        db.commit()


def ensure_default_permissions(db: Session) -> None:
    changed = False
    for item in DEFAULT_PERMISSIONS:
        permission = db.scalar(select(Permission).where(Permission.code == item["code"]))
        if permission is None:
            permission = Permission(
                name=item["name"],
                code=item["code"],
                group_name=item["group_name"],
                category=item["category"],
                description=item["description"],
            )
            db.add(permission)
            changed = True
            continue
        if (
            permission.name != item["name"]
            or permission.group_name != item["group_name"]
            or permission.category != item["category"]
            or permission.description != item["description"]
        ):
            permission.name = item["name"]
            permission.group_name = item["group_name"]
            permission.category = item["category"]
            permission.description = item["description"]
            changed = True
    if changed:
        db.commit()


def ensure_default_role_permissions(db: Session) -> None:
    permissions = {item.code: item for item in db.scalars(select(Permission)).all()}
    changed = False
    for role_code, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            continue
        desired_permissions = [permissions[code] for code in permission_codes if code in permissions]
        current_codes = {item.code for item in role.permissions}
        desired_codes = {item.code for item in desired_permissions}
        if current_codes != desired_codes:
            role.permissions = desired_permissions
            changed = True
    if changed:
        db.commit()


def ensure_default_users(db: Session) -> None:
    password_hash = hash_password("Admin123456")
    preferred_regions = _resolve_demo_regions(db)
    changed = False
    for item in DEFAULT_USERS:
        role = db.scalar(select(Role).where(Role.code == item["role_code"]))
        region_code = preferred_regions.get(item["role_code"], item["region_code"])
        region = db.scalar(select(Region).where(Region.code == region_code))
        if role is None or region is None:
            continue
        tenant_code = region.tenant_code
        user = db.scalar(select(User).where(User.username == item["username"]))
        if user is None:
            user = User(
                username=item["username"],
                real_name=item["real_name"],
                password_hash=password_hash,
                mobile=item["mobile"],
                status="active",
                tenant_code=tenant_code,
                role_id=role.id,
                region_id=region.id,
            )
            db.add(user)
            changed = True
            continue
        updated = False
        if "$" not in user.password_hash:
            user.password_hash = password_hash
            updated = True
        if user.real_name != item["real_name"]:
            user.real_name = item["real_name"]
            updated = True
        if user.mobile != item["mobile"]:
            user.mobile = item["mobile"]
            updated = True
        if user.role_id != role.id:
            user.role_id = role.id
            updated = True
        if user.region_id != region.id:
            user.region_id = region.id
            updated = True
        if user.tenant_code != tenant_code:
            user.tenant_code = tenant_code
            updated = True
        if user.status != "active":
            user.status = "active"
            updated = True
        changed = changed or updated
    if changed:
        db.commit()


def _resolve_demo_regions(db: Session) -> dict[str, str]:
    business_county = db.scalar(select(func.substring(Fbf.fbfbm, 1, 6)).limit(1))
    business_town = db.scalar(select(func.substring(Fbf.fbfbm, 1, 9)).limit(1))
    business_village = db.scalar(select(func.substring(Fbf.fbfbm, 1, 12)).limit(1))
    return {
        "platform_admin": business_county or "320623",
        "county_auditor": business_county or "320623",
        "town_auditor": business_town or "320623100",
        "operator": business_town or "320623100",
        "village_auditor": business_village or "320623100200",
    }


def sync_demo_user_passwords(db: Session) -> None:
    demo_password_hash = hash_password("Admin123456")
    demo_usernames = [item["username"] for item in DEFAULT_USERS]
    users = db.scalars(select(User).where(User.username.in_(demo_usernames))).all()
    updated = False
    for user in users:
        if "$" not in user.password_hash:
            user.password_hash = demo_password_hash
            updated = True
    if updated:
        db.commit()


def ensure_default_request_workflow_mappings(db: Session) -> None:
    changed = False
    for index, request_type in enumerate(DEFAULT_REQUEST_TYPES, start=1):
        mapping = db.scalar(
            select(RequestWorkflowMapping).where(
                RequestWorkflowMapping.tenant_code.is_(None),
                RequestWorkflowMapping.request_type == request_type,
            )
        )
        if mapping is None:
            mapping = RequestWorkflowMapping(
                tenant_code=None,
                request_type=request_type,
                workflow_key="rural_contract",
                enabled=True,
                sort_order=index,
                remark="系统初始化的全局默认流程映射",
            )
            db.add(mapping)
            changed = True
            continue

        updated = False
        if mapping.workflow_key != "rural_contract":
            mapping.workflow_key = "rural_contract"
            updated = True
        if not mapping.enabled:
            mapping.enabled = True
            updated = True
        if mapping.sort_order != index:
            mapping.sort_order = index
            updated = True
        if not mapping.remark:
            mapping.remark = "系统初始化的全局默认流程映射"
            updated = True
        changed = changed or updated

    if changed:
        db.commit()
