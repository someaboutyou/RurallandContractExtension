import base64
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.dictionary import DictionaryItem
from app.models.fbf import Fbf
from app.models.map_layer import MapLayer
from app.models.permission import Permission, role_permissions
from app.models.region import Region
from app.models.request_attachment_template import RequestAttachmentTemplate
from app.models.request_case import RequestCase
from app.models.request_case_attachment import RequestCaseAttachment
from app.models.request_workflow_mapping import RequestWorkflowMapping
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_region_permission import UserRegionPermission

ATTACHMENT_ROOT = Path(__file__).resolve().parents[1] / "storage" / "request_attachments"

DEFAULT_ROLES = [
    {"name": "平台管理员", "code": "platform_admin", "data_scope": "all", "description": "系统平台管理员，拥有全局管理权限。"},
    {"name": "村级审核员", "code": "village_auditor", "data_scope": "village", "description": "负责村级业务审核。"},
    {"name": "镇级审核员", "code": "town_auditor", "data_scope": "town", "description": "负责镇级业务审核。"},
    {"name": "县级审核员", "code": "county_auditor", "data_scope": "county", "description": "负责县级业务审核。"},
    {"name": "业务员", "code": "operator", "data_scope": "town", "description": "负责申请受理、补录和流转。"},
]

DEFAULT_REGIONS = [
    {"name": "江苏省", "code": "320000", "level": "province", "full_name": "江苏省", "parent_code": None},
    {"name": "泗洪县", "code": "321324", "level": "county", "full_name": "江苏省 / 宿迁市 / 泗洪县", "parent_code": "320000"},
]

DEFAULT_USERS = [
    {"username": "admin", "real_name": "超级管理员", "mobile": "13900000001", "role_code": "platform_admin", "region_code": "321324", "permission_codes": ["321324"]},
    {"username": "county_auditor", "real_name": "县级审核员", "mobile": "13900000002", "role_code": "county_auditor", "region_code": "321324", "permission_codes": ["321324"]},
    {"username": "town_auditor", "real_name": "镇级审核员", "mobile": "13900000003", "role_code": "town_auditor", "region_code": "321324100", "permission_codes": ["321324100"]},
    {"username": "village_auditor", "real_name": "村级审核员", "mobile": "13900000004", "role_code": "village_auditor", "region_code": "321324100001", "permission_codes": ["321324100001"]},
    {"username": "town_operator", "real_name": "镇级业务员", "mobile": "13900000005", "role_code": "operator", "region_code": "321324100", "permission_codes": ["321324100"]},
    {"username": "multi_scope_user", "real_name": "多区域测试员", "mobile": "13900000006", "role_code": "operator", "region_code": "321324100", "permission_codes": ["321324100", "321324101203"]},
    {"username": "group_scope_user", "real_name": "组级测试员", "mobile": "13900000007", "role_code": "operator", "region_code": "321324100001", "permission_codes": ["32132410000101"]},
]

DEFAULT_PERMISSIONS = [
    {"name": "查看工作台", "code": "dashboard.view", "group_name": "平台首页", "category": "menu", "description": "允许进入工作台页面。"},
    {"name": "查看人员权限", "code": "users.view", "group_name": "人员权限", "category": "menu", "description": "允许查看用户管理页面。"},
    {"name": "管理用户", "code": "users.manage", "group_name": "人员权限", "category": "action", "description": "允许新增、编辑、删除和重置用户密码。"},
    {"name": "查看角色权限", "code": "roles.view", "group_name": "人员权限", "category": "menu", "description": "允许查看角色与权限配置。"},
    {"name": "管理角色权限", "code": "roles.manage", "group_name": "人员权限", "category": "action", "description": "允许编辑角色和分配权限。"},
    {"name": "查看区域管理", "code": "regions.view", "group_name": "系统管理", "category": "menu", "description": "允许查看区域主数据。"},
    {"name": "管理区域", "code": "regions.manage", "group_name": "系统管理", "category": "action", "description": "允许维护行政区域及区域代码。"},
    {"name": "查看字典管理", "code": "dictionaries.view", "group_name": "系统管理", "category": "menu", "description": "允许查看字典管理页面。"},
    {"name": "管理字典", "code": "dictionaries.manage", "group_name": "系统管理", "category": "action", "description": "允许维护系统字典项。"},
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
    {"name": "查看图层管理", "code": "layers.view", "group_name": "系统管理", "category": "menu", "description": "允许查看图层管理页面。"},
    {"name": "管理图层配置", "code": "layers.manage", "group_name": "系统管理", "category": "action", "description": "允许维护矢量图层与底图配置。"},
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


DEFAULT_MAP_LAYERS = [
    {
        "name": "遥感底图",
        "key": "image",
        "layer_type": "XYZ",
        "category": "basemap",
        "group_name": "基础底图",
        "service_url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "projection": "EPSG:3857",
        "default_visible": True,
        "is_default": True,
        "sort_order": 10,
        "enabled": True,
    },
    {
        "name": "电子地图",
        "key": "vector",
        "layer_type": "OSM",
        "category": "basemap",
        "group_name": "基础底图",
        "service_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "projection": "EPSG:3857",
        "default_visible": False,
        "is_default": False,
        "sort_order": 20,
        "enabled": True,
    },
    {
        "name": "地形图",
        "key": "terrain",
        "layer_type": "XYZ",
        "category": "basemap",
        "group_name": "基础底图",
        "service_url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        "projection": "EPSG:3857",
        "default_visible": False,
        "is_default": False,
        "sort_order": 30,
        "enabled": True,
    },
    {
        "name": "承包地块",
        "key": "contract_land",
        "layer_type": "GeoJSON",
        "category": "vector",
        "group_name": "业务专题",
        "service_url": "/mock/contract-land.geojson",
        "projection": "EPSG:4326",
        "default_visible": True,
        "is_default": False,
        "sort_order": 10,
        "enabled": True,
    },
    {
        "name": "发包方范围",
        "key": "issuer_boundary",
        "layer_type": "GeoJSON",
        "category": "vector",
        "group_name": "业务专题",
        "service_url": "/mock/issuer-boundary.geojson",
        "projection": "EPSG:4326",
        "default_visible": True,
        "is_default": False,
        "sort_order": 20,
        "enabled": True,
    },
    {
        "name": "承包方分布",
        "key": "contractor_distribution",
        "layer_type": "GeoJSON",
        "category": "vector",
        "group_name": "业务专题",
        "service_url": "/mock/contractor-distribution.geojson",
        "projection": "EPSG:4326",
        "default_visible": False,
        "is_default": False,
        "sort_order": 30,
        "enabled": True,
    },
    {
        "name": "流程状态",
        "key": "workflow_status",
        "layer_type": "GeoJSON",
        "category": "vector",
        "group_name": "业务专题",
        "service_url": "/mock/workflow-status.geojson",
        "projection": "EPSG:4326",
        "default_visible": True,
        "is_default": False,
        "sort_order": 40,
        "enabled": True,
    },
    {
        "name": "问题核查",
        "key": "issue_review",
        "layer_type": "GeoJSON",
        "category": "vector",
        "group_name": "业务专题",
        "service_url": "/mock/issue-review.geojson",
        "projection": "EPSG:4326",
        "default_visible": False,
        "is_default": False,
        "sort_order": 50,
        "enabled": True,
    },
    {
        "name": "调查地块结果",
        "key": "survey_dk_result",
        "layer_type": "WMTS",
        "category": "vector",
        "group_name": "GeoServer图层",
        "service_url": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:survey_dk_result&styles=survey_dk_result&format=image/png&transparent=true",
        "projection": "EPSG:4326",
        "service_config": [
            {
                "serviceType": "WMTS",
                "serviceUrl": "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:survey_dk_result&style=survey_dk_result&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png",
                "projection": "EPSG:4326",
                "minZoom": 0,
                "maxZoom": 15,
                "enabled": True,
            },
            {
                "serviceType": "WMS",
                "serviceUrl": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:survey_dk_result&styles=survey_dk_result&format=image/png&transparent=true",
                "projection": "EPSG:4326",
                "minZoom": 16,
                "maxZoom": 24,
                "enabled": True,
            },
        ],
        "default_visible": True,
        "is_default": False,
        "sort_order": 5,
        "enabled": True,
    },
    {
        "name": "村庄开发边界",
        "key": "czkfbj",
        "layer_type": "WMTS",
        "category": "vector",
        "group_name": "国土空间规划",
        "service_url": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:czkfbj&styles=czkfbj&format=image/png&transparent=true",
        "projection": "EPSG:4326",
        "service_config": [
            {
                "serviceType": "WMTS",
                "serviceUrl": "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:czkfbj&style=czkfbj&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png",
                "projection": "EPSG:4326",
                "minZoom": 0,
                "maxZoom": 15,
                "enabled": True,
            },
            {
                "serviceType": "WMS",
                "serviceUrl": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:czkfbj&styles=czkfbj&format=image/png&transparent=true",
                "projection": "EPSG:4326",
                "minZoom": 16,
                "maxZoom": 24,
                "enabled": True,
            },
        ],
        "default_visible": False,
        "is_default": False,
        "sort_order": 20,
        "enabled": True,
    },
    {
        "name": "地类图斑",
        "key": "dltb",
        "layer_type": "WMTS",
        "category": "vector",
        "group_name": "国土空间规划",
        "service_url": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:dltb&styles=dltb&format=image/png&transparent=true",
        "projection": "EPSG:4326",
        "service_config": [
            {
                "serviceType": "WMTS",
                "serviceUrl": "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:dltb&style=dltb&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png",
                "projection": "EPSG:4326",
                "minZoom": 0,
                "maxZoom": 15,
                "enabled": True,
            },
            {
                "serviceType": "WMS",
                "serviceUrl": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:dltb&styles=dltb&format=image/png&transparent=true",
                "projection": "EPSG:4326",
                "minZoom": 16,
                "maxZoom": 24,
                "enabled": True,
            },
        ],
        "default_visible": False,
        "is_default": False,
        "sort_order": 30,
        "enabled": True,
    },
    {
        "name": "耕地保护目标",
        "key": "gdbhmb",
        "layer_type": "WMTS",
        "category": "vector",
        "group_name": "国土空间规划",
        "service_url": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:gdbhmb&styles=gdbhmb&format=image/png&transparent=true",
        "projection": "EPSG:4326",
        "service_config": [
            {
                "serviceType": "WMTS",
                "serviceUrl": "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:gdbhmb&style=gdbhmb&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png",
                "projection": "EPSG:4326",
                "minZoom": 0,
                "maxZoom": 15,
                "enabled": True,
            },
            {
                "serviceType": "WMS",
                "serviceUrl": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:gdbhmb&styles=gdbhmb&format=image/png&transparent=true",
                "projection": "EPSG:4326",
                "minZoom": 16,
                "maxZoom": 24,
                "enabled": True,
            },
        ],
        "default_visible": False,
        "is_default": False,
        "sort_order": 40,
        "enabled": True,
    },
    {
        "name": "生态保护红线",
        "key": "stbhhx",
        "layer_type": "WMTS",
        "category": "vector",
        "group_name": "国土空间规划",
        "service_url": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:stbhhx&styles=stbhhx&format=image/png&transparent=true",
        "projection": "EPSG:4326",
        "service_config": [
            {
                "serviceType": "WMTS",
                "serviceUrl": "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:stbhhx&style=stbhhx&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png",
                "projection": "EPSG:4326",
                "minZoom": 0,
                "maxZoom": 15,
                "enabled": True,
            },
            {
                "serviceType": "WMS",
                "serviceUrl": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:stbhhx&styles=stbhhx&format=image/png&transparent=true",
                "projection": "EPSG:4326",
                "minZoom": 16,
                "maxZoom": 24,
                "enabled": True,
            },
        ],
        "default_visible": False,
        "is_default": False,
        "sort_order": 50,
        "enabled": True,
    },
    {
        "name": "行政区",
        "key": "xzq",
        "layer_type": "WMTS",
        "category": "vector",
        "group_name": "行政区划",
        "service_url": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:xzq&styles=xzq&format=image/png&transparent=true",
        "projection": "EPSG:4326",
        "service_config": [
            {
                "serviceType": "WMTS",
                "serviceUrl": "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:xzq&style=xzq&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png",
                "projection": "EPSG:4326",
                "minZoom": 0,
                "maxZoom": 15,
                "enabled": True,
            },
            {
                "serviceType": "WMS",
                "serviceUrl": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:xzq&styles=xzq&format=image/png&transparent=true",
                "projection": "EPSG:4326",
                "minZoom": 16,
                "maxZoom": 24,
                "enabled": True,
            },
        ],
        "default_visible": False,
        "is_default": False,
        "sort_order": 60,
        "enabled": True,
    },
    {
        "name": "行政区界线",
        "key": "xzqjx",
        "layer_type": "WMTS",
        "category": "vector",
        "group_name": "行政区划",
        "service_url": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:xzqjx&styles=xzqjx&format=image/png&transparent=true",
        "projection": "EPSG:4326",
        "service_config": [
            {
                "serviceType": "WMTS",
                "serviceUrl": "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:xzqjx&style=xzqjx&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png",
                "projection": "EPSG:4326",
                "minZoom": 0,
                "maxZoom": 15,
                "enabled": True,
            },
            {
                "serviceType": "WMS",
                "serviceUrl": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:xzqjx&styles=xzqjx&format=image/png&transparent=true",
                "projection": "EPSG:4326",
                "minZoom": 16,
                "maxZoom": 24,
                "enabled": True,
            },
        ],
        "default_visible": False,
        "is_default": False,
        "sort_order": 70,
        "enabled": True,
    },
    {
        "name": "永久基本农田",
        "key": "yjjbntbhtb",
        "layer_type": "WMTS",
        "category": "vector",
        "group_name": "国土空间规划",
        "service_url": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:yjjbntbhtb&styles=yjjbntbhtb&format=image/png&transparent=true",
        "projection": "EPSG:4326",
        "service_config": [
            {
                "serviceType": "WMTS",
                "serviceUrl": "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:yjjbntbhtb&style=yjjbntbhtb&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png",
                "projection": "EPSG:4326",
                "minZoom": 0,
                "maxZoom": 15,
                "enabled": True,
            },
            {
                "serviceType": "WMS",
                "serviceUrl": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:yjjbntbhtb&styles=yjjbntbhtb&format=image/png&transparent=true",
                "projection": "EPSG:4326",
                "minZoom": 16,
                "maxZoom": 24,
                "enabled": True,
            },
        ],
        "default_visible": False,
        "is_default": False,
        "sort_order": 80,
        "enabled": True,
    },
    {
        "name": "调查地块图层组",
        "key": "rural_land_layers",
        "layer_type": "WMS",
        "category": "vector",
        "group_name": "GeoServer图层",
        "service_url": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:rural_land_layers&format=image/png&transparent=true",
        "projection": "EPSG:4326",
        "service_config": [
            {
                "serviceType": "WMS",
                "serviceUrl": "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:rural_land_layers&format=image/png&transparent=true",
                "projection": "EPSG:4326",
                "minZoom": 0,
                "maxZoom": 24,
                "enabled": True,
            },
        ],
        "default_visible": False,
        "is_default": False,
        "sort_order": 100,
        "enabled": True,
    },
]

LEGACY_DEFAULT_MAP_LAYER_KEYS = {
    "contract_land",
    "issuer_boundary",
    "contractor_distribution",
    "workflow_status",
    "issue_review",
}


def seed_initial_data(db: Session) -> None:
    ensure_default_regions(db)
    sync_regions_from_business_codes(db)
    ensure_tenants(db)
    sync_region_tenants(db)
    ensure_default_roles(db)
    ensure_default_permissions(db)
    ensure_default_role_permissions(db)
    ensure_default_users(db)
    ensure_default_request_workflow_mappings(db)
    ensure_default_map_layers(db)
    ensure_dictionary_presets(db)
    ensure_default_request_attachment_templates(db)
    ensure_attachment_template_hierarchy(db)
    ensure_demo_request_attachments(db)


def ensure_default_request_attachment_templates(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(RequestAttachmentTemplate)) > 0:
        return

    presets = {
        "首次登记": {
            "apply": [
                {
                    "name": "申请材料",
                    "required": True,
                    "children": [
                        {"name": "申请书", "required": True, "example": "首次登记申请书.docx", "description": "申请人提交的正式申请材料。"},
                        {"name": "调查表", "required": True, "example": "权属调查表.xlsx", "description": "权属和四至调查记录。"},
                    ],
                },
                {
                    "name": "身份信息组",
                    "required": True,
                    "children": [
                        {"name": "身份证附件", "required": True, "example": "身份证.pdf", "description": "承包方身份证明材料。"},
                        {"name": "户口簿附件", "required": False, "example": "户口簿.pdf", "description": "户籍信息辅助材料。"},
                    ],
                },
                {
                    "name": "合同材料",
                    "required": True,
                    "children": [
                        {"name": "承包合同附件", "required": True, "example": "承包合同.pdf", "description": "现有承包合同或台账。"},
                        {"name": "补充协议附件", "required": False, "example": "补充协议.pdf", "description": "补充协议或补充说明。"},
                    ],
                },
            ],
            "village_review": [
                {
                    "name": "村级审核材料",
                    "required": True,
                    "children": [
                        {"name": "村级审核意见", "required": True, "example": "村级审核意见.pdf", "description": "村级审核意见和签章页。"},
                        {"name": "公示照片", "required": False, "example": "公示照片.jpg", "description": "公示留痕照片。"},
                    ],
                }
            ],
            "town_review": [
                {
                    "name": "镇级审核材料",
                    "required": True,
                    "children": [
                        {"name": "镇级审核意见", "required": True, "example": "镇级审核意见.pdf", "description": "镇级审核意见和核查说明。"},
                    ],
                }
            ],
            "county_review": [
                {
                    "name": "县级审核材料",
                    "required": True,
                    "children": [
                        {"name": "县级审批意见", "required": True, "example": "县级审批意见.pdf", "description": "县级审批结论材料。"},
                        {"name": "归档清单", "required": False, "example": "归档清单.xlsx", "description": "最终归档和目录清单。"},
                    ],
                }
            ],
        },
        "变更登记": {
            "apply": [
                {
                    "name": "申请材料",
                    "required": True,
                    "children": [
                        {"name": "变更申请书", "required": True, "example": "变更登记申请书.docx", "description": "变更事项说明和申请。"},
                        {"name": "变更依据附件", "required": True, "example": "变更依据.pdf", "description": "继承、分户、流转等依据材料。"},
                    ],
                },
                {
                    "name": "身份信息组",
                    "required": True,
                    "children": [
                        {"name": "相关人员身份证", "required": True, "example": "相关人员身份证.pdf", "description": "变更涉及人员身份证明。"},
                    ],
                },
            ],
            "county_review": [
                {
                    "name": "县级审核材料",
                    "required": True,
                    "children": [
                        {"name": "县级变更审批意见", "required": True, "example": "县级变更审批意见.pdf", "description": "县级审批结论。"},
                    ],
                }
            ],
        },
    }

    def add_group(request_type: str, stage_code: str, stage_name: str, row: dict, sort_order: int, parent_id: int | None = None):
        item = RequestAttachmentTemplate(
            tenant_code=None,
            parent_id=parent_id,
            request_type=request_type,
            stage_code=stage_code,
            stage_name=stage_name,
            category=row["name"],
            name=row["name"],
            required=row.get("required", True),
            description=row.get("description"),
            example_file_name=row.get("example"),
            sort_order=sort_order,
            enabled=True,
        )
        db.add(item)
        db.flush()
        for child_index, child in enumerate(row.get("children", []), start=1):
            add_group(request_type, stage_code, stage_name, child, child_index, item.id)

    for request_type, stage_map in presets.items():
        for stage_code, rows in stage_map.items():
            for index, row in enumerate(rows, start=1):
                add_group(request_type, stage_code, stage_code, row, index)
    db.commit()


def ensure_attachment_template_hierarchy(db: Session) -> None:
    rows = db.scalars(select(RequestAttachmentTemplate).order_by(RequestAttachmentTemplate.id.asc())).all()
    if not rows:
        return

    parent_map: dict[tuple[str | None, str, str, str], RequestAttachmentTemplate] = {}
    created = False
    for row in rows:
        if row.parent_id is not None or not row.category or row.name == row.category:
            continue
        scope_key = (row.tenant_code, row.request_type, row.stage_code, row.category)
        parent = parent_map.get(scope_key)
        if parent is None:
            parent = db.scalars(
                select(RequestAttachmentTemplate).where(
                    RequestAttachmentTemplate.tenant_code.is_(row.tenant_code) if row.tenant_code is None else RequestAttachmentTemplate.tenant_code == row.tenant_code,
                    RequestAttachmentTemplate.request_type == row.request_type,
                    RequestAttachmentTemplate.stage_code == row.stage_code,
                    RequestAttachmentTemplate.parent_id.is_(None),
                    RequestAttachmentTemplate.name == row.category,
                )
            ).first()
            if parent is None:
                parent = RequestAttachmentTemplate(
                    tenant_code=row.tenant_code,
                    parent_id=None,
                    request_type=row.request_type,
                    stage_code=row.stage_code,
                    stage_name=row.stage_name,
                    category=row.category,
                    name=row.category,
                    required=row.required,
                    description=f"{row.category}分组",
                    example_file_name=None,
                    sort_order=max((row.sort_order or 0) - 1, 0),
                    enabled=row.enabled,
                )
                db.add(parent)
                db.flush()
                created = True
            parent_map[scope_key] = parent
        row.parent_id = parent.id

    if created or any(row.parent_id is not None for row in rows):
        db.commit()


def ensure_demo_request_attachments(db: Session) -> None:
    existing_count = db.scalar(select(func.count()).select_from(RequestCaseAttachment)) or 0
    if existing_count >= 3:
        return

    case = db.scalars(select(RequestCase).order_by(RequestCase.id.asc())).first()
    if case is None:
        return

    uploader = db.scalars(select(User).where(User.username == "admin")).first()
    storage_dir = ATTACHMENT_ROOT / str(case.id)
    storage_dir.mkdir(parents=True, exist_ok=True)

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAASwAAADICAIAAADdvUsCAAADQ0lEQVR4nO3UwQ3AIBDAsNL9dz6WIEJC9gR5ZM18A6ft2wG8MynA"
        "JAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKT"
        "CEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwi"
        "MInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInA"
        "JAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKT"
        "CEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwi"
        "MInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInA"
        "JAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJAKTCEwiMInAJP4B4mcE6ynhP58AAAAASUVORK5CYII="
    )
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 160]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 59>>stream\nBT /F1 16 Tf 32 96 Td (Rural land contract demo file) Tj ET\nendstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n0000000110 00000 n \n"
        b"0000000236 00000 n \n0000000345 00000 n \ntrailer<</Root 1 0 R/Size 6>>\nstartxref\n414\n%%EOF"
    )
    doc_bytes = "演示附件：这是用于查看页面效果的申请说明材料。".encode("utf-8")

    demo_files = [
        {
            "stored_name": "demo-plot-photo.png",
            "original_name": "宗地图示意.png",
            "content_type": "image/png",
            "category": "图件材料",
            "stage_code": "apply",
            "content": png_bytes,
        },
        {
            "stored_name": "demo-review-opinion.pdf",
            "original_name": "村级审核意见.pdf",
            "content_type": "application/pdf",
            "category": "审核材料",
            "stage_code": "village_review",
            "content": pdf_bytes,
        },
        {
            "stored_name": "demo-apply-note.txt",
            "original_name": "申请说明.txt",
            "content_type": "text/plain",
            "category": "申请材料",
            "stage_code": "apply",
            "content": doc_bytes,
        },
    ]

    created = False
    for item in demo_files:
        existing = db.scalars(
            select(RequestCaseAttachment).where(
                RequestCaseAttachment.case_id == case.id,
                RequestCaseAttachment.original_name == item["original_name"],
            )
        ).first()
        if existing is not None:
            continue

        target_path = storage_dir / item["stored_name"]
        if not target_path.exists():
            target_path.write_bytes(item["content"])

        db.add(
            RequestCaseAttachment(
                case_id=case.id,
                tenant_code=case.tenant_code,
                category=item["category"],
                stage_code=item["stage_code"],
                original_name=item["original_name"],
                stored_name=item["stored_name"],
                content_type=item["content_type"],
                file_size=target_path.stat().st_size,
                storage_path=str(target_path),
                uploaded_by_id=uploader.id if uploader else None,
            )
        )
        created = True

    if created:
        db.commit()


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
            db.add(
                Tenant(
                    code=tenant_code,
                    name=region.name,
                    region_code=region.code,
                    status="active",
                    description=f"按县级行政区 {region.code} 建立的租户",
                )
            )
            changed = True
    if changed:
        db.commit()


def sync_region_tenants(db: Session) -> None:
    changed = False
    regions = db.scalars(select(Region)).all()
    for region in regions:
        expected_tenant_code = region.code[:6] if region.level in {"county", "town", "village"} else None
        if region.tenant_code is None and expected_tenant_code is not None:
            region.tenant_code = expected_tenant_code
            changed = True
    if changed:
        db.commit()


def ensure_default_roles(db: Session) -> None:
    changed = False
    for item in DEFAULT_ROLES:
        role = db.scalar(select(Role).where(Role.code == item["code"]))
        if role is None:
            db.add(
                Role(
                    name=item["name"],
                    code=item["code"],
                    data_scope=item["data_scope"],
                    description=item["description"],
                )
            )
            changed = True
    if changed:
        db.commit()


def ensure_default_permissions(db: Session) -> None:
    changed = False
    for item in DEFAULT_PERMISSIONS:
        permission = db.scalar(select(Permission).where(Permission.code == item["code"]))
        if permission is None:
            db.add(
                Permission(
                    name=item["name"],
                    code=item["code"],
                    group_name=item["group_name"],
                    category=item["category"],
                    description=item["description"],
                )
            )
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
        current_codes = {item.code for item in role.permissions}
        missing_permissions = [
            permissions[code]
            for code in permission_codes
            if code in permissions and code not in current_codes
        ]
        if missing_permissions:
            role.permissions = [*role.permissions, *missing_permissions]
            changed = True
    if changed:
        db.commit()


def ensure_default_users(db: Session) -> None:
    password_hash = hash_password("Admin123456")
    preferred_regions = _resolve_demo_regions(db)
    changed = False
    for item in DEFAULT_USERS:
        role = db.scalar(select(Role).where(Role.code == item["role_code"]))
        region_code = item.get("region_code") or preferred_regions.get(item["role_code"])
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
            db.flush()
            changed = True
        else:
            user.real_name = item["real_name"]
            user.mobile = item["mobile"]
            user.status = "active"
            user.tenant_code = tenant_code
            user.role_id = role.id
            user.region_id = region.id
            changed = True
        permission_codes = item.get("permission_codes") or [region.code]
        if _ensure_user_region_permissions(db, user, permission_codes):
            changed = True
    if changed:
        db.commit()


def _resolve_demo_regions(db: Session) -> dict[str, str]:
    business_county = db.scalar(select(func.min(func.substring(Fbf.fbfbm, 1, 6))))
    business_town = db.scalar(select(func.min(func.substring(Fbf.fbfbm, 1, 9))))
    business_village = db.scalar(select(func.min(func.substring(Fbf.fbfbm, 1, 12))))
    return {
        "platform_admin": business_county or "321324",
        "county_auditor": business_county or "321324",
        "town_auditor": business_town or "321324100",
        "operator": business_town or "321324100",
        "village_auditor": business_village or "321324100001",
    }


def _ensure_user_region_permissions(db: Session, user: User, region_codes: list[str]) -> bool:
    changed = False
    desired_codes = {code for code in (_normalize_region_code(raw_code) for raw_code in region_codes) if code}
    existing_rows = db.scalars(select(UserRegionPermission).where(UserRegionPermission.user_id == user.id)).all()
    for row in existing_rows:
        if row.region_code not in desired_codes:
            db.delete(row)
            changed = True
    existing = {
        row.region_code
        for row in existing_rows
        if row.region_code in desired_codes
    }
    for code in desired_codes:
        if code in existing:
            continue
        db.add(
            UserRegionPermission(
                user_id=user.id,
                tenant_code=code[:6],
                region_code=code,
                level=_level_by_region_code(code),
            )
        )
        changed = True
    return changed


def _normalize_region_code(code: str | None) -> str | None:
    if not code:
        return None
    if len(code) >= 14:
        return code[:14]
    if len(code) >= 12:
        return code[:12]
    if len(code) >= 9:
        return code[:9]
    return code[:6] if len(code) >= 6 else code


def _level_by_region_code(code: str) -> str:
    return {6: "county", 9: "town", 12: "village", 14: "group"}.get(len(code), "custom")


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


def ensure_default_map_layers(db: Session) -> None:
    changed = False
    for item in DEFAULT_MAP_LAYERS:
        row = db.scalar(select(MapLayer).where(MapLayer.key == item["key"]))
        if item["key"] == "survey_dk_result":
            item = {**item, "name": "\u627f\u5305\u5730\u5757", "group_name": "GeoServer\u56fe\u5c42"}
        if item["key"] in LEGACY_DEFAULT_MAP_LAYER_KEYS:
            if row is not None:
                db.delete(row)
                changed = True
            continue
        if row is None:
            row = MapLayer(
                name=item["name"],
                key=item["key"],
                layer_type=item["layer_type"],
                category=item["category"],
                group_name=item.get("group_name"),
                service_config=json.dumps(item.get("service_config"), ensure_ascii=False) if item.get("service_config") else None,
                service_url=item["service_url"],
                projection=item.get("projection"),
                default_visible=item.get("default_visible", False),
                is_default=item.get("is_default", False),
                sort_order=item.get("sort_order", 0),
                enabled=item.get("enabled", True),
            )
            db.add(row)
            changed = True
        elif item["key"] == "survey_dk_result" and (row.name != item["name"] or row.group_name != item["group_name"]):
            row.name = item["name"]
            row.group_name = item["group_name"]
            changed = True

    if changed:
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
            db.add(
                RequestWorkflowMapping(
                    tenant_code=None,
                    request_type=request_type,
                    workflow_key="rural_contract",
                    enabled=True,
                    sort_order=index,
                    remark="系统初始化的全局默认流程映射",
                )
            )
            changed = True

    if changed:
        db.commit()


def ensure_dictionary_presets(db: Session) -> None:
    from app.db.dictionary_presets import NYT2539_APPENDIX_C_DICTIONARY_ITEMS

    existing_count = db.scalar(select(func.count()).select_from(DictionaryItem)) or 0
    if existing_count > 0:
        _sync_dictionary_group(db, NYT2539_APPENDIX_C_DICTIONARY_ITEMS, "nyt2539_c20_relation_to_head")
        return

    for dict_type, dict_name, item_value, item_name, sort_order, remark in NYT2539_APPENDIX_C_DICTIONARY_ITEMS:
        db.add(
            DictionaryItem(
                dict_type=dict_type,
                dict_name=dict_name,
                item_value=item_value,
                item_name=item_name,
                sort_order=sort_order,
                enabled=True,
                remark=remark,
                tenant_code=None,
            )
        )
    db.commit()


def _sync_dictionary_group(db: Session, preset_items: list[tuple[str, str, str, str, int, str | None]], dict_type: str) -> None:
    group_items = [item for item in preset_items if item[0] == dict_type]
    if not group_items:
        return

    existing_items = db.scalars(
        select(DictionaryItem).where(
            DictionaryItem.dict_type == dict_type,
            DictionaryItem.tenant_code.is_(None),
        )
    ).all()
    existing_by_value = {item.item_value: item for item in existing_items}
    expected_values = {item_value for _, _, item_value, _, _, _ in group_items}
    changed = False

    for dict_type, dict_name, item_value, item_name, sort_order, remark in group_items:
        existing = existing_by_value.get(item_value)
        if existing is None:
            db.add(
                DictionaryItem(
                    dict_type=dict_type,
                    dict_name=dict_name,
                    item_value=item_value,
                    item_name=item_name,
                    sort_order=sort_order,
                    enabled=True,
                    remark=remark,
                    tenant_code=None,
                )
            )
            changed = True
            continue

        if (
            existing.dict_name != dict_name
            or existing.item_name != item_name
            or existing.sort_order != sort_order
            or existing.remark != remark
            or not existing.enabled
        ):
            existing.dict_name = dict_name
            existing.item_name = item_name
            existing.sort_order = sort_order
            existing.remark = remark
            existing.enabled = True
            changed = True

    for existing in existing_items:
        if existing.item_value not in expected_values:
            db.delete(existing)
            changed = True

    if changed:
        db.commit()
