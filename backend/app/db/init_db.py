import base64
import re
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domain.survey_attachment import (
    DEFAULT_SURVEY_ATTACHMENT_CATEGORY_NAMES,
    SURVEY_ATTACHMENT_STAGE_NAME,
    SURVEY_ATTACHMENT_TEMPLATE_SCOPE,
)
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
    {"name": "查看工作进展大屏", "code": "dashboard.bigscreen", "group_name": "平台首页", "category": "menu", "description": "允许进入二轮延包工作进展大屏（全屏数据看板）。"},
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
    {"name": "管理打印模板", "code": "contract_templates.manage", "group_name": "系统管理", "category": "action", "description": "允许在线编辑打印 HTML 模板。"},
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
        "service_url": "https://t6.tianditu.gov.cn/DataServer?T=img_w&x={x}&y={y}&l={z}&tk=d9d9f17f6979a9b6cc681e5b1589f750",
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

LEGACY_ARCGIS_IMAGE_BASEMAP_URL = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

LEGACY_DEFAULT_MAP_LAYER_KEYS = {
    "contract_land",
    "issuer_boundary",
    "contractor_distribution",
    "workflow_status",
    "issue_review",
}


def seed_initial_data(db: Session) -> None:
    ensure_default_regions(db)
    ensure_tenants(db)
    sync_region_tenants(db)
    ensure_default_roles(db)
    created_permissions = ensure_default_permissions(db)
    ensure_default_role_permissions(db)
    ensure_new_permission_grants(db, created_permissions)
    ensure_default_users(db)
    ensure_default_request_workflow_mappings(db)
    ensure_default_map_layers(db)
    ensure_dictionary_presets(db)
    ensure_default_request_attachment_templates(db)
    ensure_attachment_template_hierarchy(db)
    ensure_survey_attachment_categories(db)
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


# 调查附件类别预设（`/surveys` → 承包方调查录入 → 调查附件 & 转业业务申请）。
# 复用附件组管理页（request_attachment_templates）承载类别清单，作用域与默认项见
# app/domain/survey_attachment.py：
#   - 叶子行的 name 既是页面显示名，也是写入 survey_attachments.category 的类别值（中文）；
#   - 分组（parent_id）只用于页面归类，读取类别时会被排除；
#   - required 在调查附件侧不参与任何校验，一律 False —— 免得页面上挂着兑现不了的"必传"。
def ensure_survey_attachment_categories(db: Session) -> None:
    """幂等：把调查附件类别灌进附件组管理页；已存在就完全不碰（用户在页面上改过的不被覆盖）。"""
    request_type, stage_code = SURVEY_ATTACHMENT_TEMPLATE_SCOPE
    existing = db.scalar(
        select(func.count())
        .select_from(RequestAttachmentTemplate)
        .where(
            RequestAttachmentTemplate.request_type == request_type,
            RequestAttachmentTemplate.stage_code == stage_code,
        )
    )
    if existing:
        return

    for index, name in enumerate(DEFAULT_SURVEY_ATTACHMENT_CATEGORY_NAMES, start=1):
        db.add(
            RequestAttachmentTemplate(
                tenant_code=None,
                parent_id=None,
                request_type=request_type,
                stage_code=stage_code,
                stage_name=SURVEY_ATTACHMENT_STAGE_NAME,
                category=name,
                name=name,
                required=False,
                description="承包方调查附件类别：上传时作为类型选项，名称即写入调查附件的类别值。",
                example_file_name=None,
                sort_order=index,
                enabled=True,
            )
        )
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
    group_rows = db.execute(
        select(Fbf.fbfbm, func.min(Fbf.fbfmc))
        .where(func.length(Fbf.fbfbm) >= 12)
        .group_by(Fbf.fbfbm)
        .order_by(Fbf.fbfbm)
    ).all()
    if not group_rows:
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

    for raw_group_code, raw_group_name in group_rows:
        if not raw_group_code:
            continue
        group_code = raw_group_code[:14] if len(raw_group_code) >= 14 else None
        village_code = raw_group_code[:12]
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
            # 从fbf表获取正确的镇名
            _fbf_town = db.scalar(select(Fbf.fbfmc).where(Fbf.region_code == town_code))
            if _fbf_town:
                _s = re.sub(r'^.*?县', '', _fbf_town)
                _m = re.search(r'^(.*?(?:镇|乡|开发区))', _s)
                town_name = _m.group(1) if _m else f"{town_code} 镇级区域"
            else:
                town_name = f"{town_code} 镇级区域"
            town = Region(
                name=town_name,
                code=town_code,
                level="town",
                full_name=f"{county.full_name} / {town_name}",
                parent_id=county.id,
                tenant_code=county_code,
            )
            db.add(town)
            db.flush()
            created = True

        village = db.scalar(select(Region).where(Region.code == village_code))
        if village is None:
            # 从fbf表获取正确的村名
            _fbf_village = db.scalar(select(Fbf.fbfmc).where(Fbf.region_code == village_code))
            if _fbf_village:
                _s2 = re.sub(r'^.*?(?:镇|乡|开发区)', '', _fbf_village)
                _m2 = re.search(r'^(.*?(?:村|居|社区))', _s2)
                village_name = _m2.group(1) if _m2 else f"{village_code} 村级区域"
            else:
                village_name = f"{village_code} 村级区域"
            village = Region(
                name=village_name,
                code=village_code,
                level="village",
                full_name=f"{town.full_name} / {village_name}",
                parent_id=town.id,
                tenant_code=county_code,
            )
            db.add(village)
            db.flush()
            created = True

        if group_code:
            group = db.scalar(select(Region).where(Region.code == group_code))
            if group is None:
                group_name = raw_group_name or f"{group_code} 组级区域"
                group = Region(
                    name=group_name,
                    code=group_code,
                    level="group",
                    full_name=f"{village.full_name} / {group_name}",
                    parent_id=village.id,
                    tenant_code=county_code,
                )
                db.add(group)
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
        expected_tenant_code = region.code[:6] if region.level in {"county", "town", "village", "group"} else None
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


def ensure_default_permissions(db: Session) -> set[str]:
    """补齐缺失的权限点；已存在的权限点不覆盖。

    旧实现会把已存在权限的 `name / group_name / category / description` 覆写回预设文案，
    运维改过的权限名称会在重启后被改回去。现在只做\"缺则新增\"。

    返回**本次新登记**的权限码集合，供 `ensure_new_permission_grants` 判断
    \"哪些权限是刚加进代码的\"——补授动作只对新权限发生一次。
    """
    created: set[str] = set()
    for item in DEFAULT_PERMISSIONS:
        permission = db.scalar(select(Permission).where(Permission.code == item["code"]))
        if permission is not None:
            continue
        db.add(
            Permission(
                name=item["name"],
                code=item["code"],
                group_name=item["group_name"],
                category=item["category"],
                description=item["description"],
            )
        )
        created.add(item["code"])
    if created:
        db.commit()
    return created


def ensure_default_role_permissions(db: Session) -> None:
    """给**尚未配置权限**的角色种默认权限；角色已有权限则完全跳过。

    旧实现是\"只补缺不删\"，看着安全，实则会把运维从角色上**摘掉**的权限在下次重启时
    再加回来（回灌）。现在改为：角色权限集合为空才灌预设，非空则一行不动。
    """
    permissions = {item.code: item for item in db.scalars(select(Permission)).all()}
    changed = False
    for role_code, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            continue
        if role.permissions:
            continue
        seeded = [permissions[code] for code in permission_codes if code in permissions]
        if seeded:
            role.permissions = seeded
            changed = True
    if changed:
        db.commit()


def ensure_new_permission_grants(db: Session, created_codes: set[str]) -> None:
    """把**本次启动新登记**的权限点补授给平台管理员角色。

    为什么需要单独一步：`ensure_default_role_permissions` 对"已有权限"的角色整体跳过
    （这是刻意的，防止把运维从角色上摘掉的权限在重启后回灌），副作用是
    **代码里新加的权限码不会自动挂到已存在的 platform_admin 上** ——
    新装库能拿到，老库升级后管理员反而看不到新功能。

    折中办法：只在"该权限码是本次启动新建的"前提下补授一次。
    权限码一旦已存在（无论被谁持有、还是被运维摘掉），这里一概不碰，
    因此运维在「角色权限」页调整过的授权不会被重启改回去。

    这也正是 `dashboard.bigscreen` 的落地方式：权限点随代码发布自动
    补授给平台管理员，其他角色要开放时去「角色权限」里手工勾选。
    """
    if not created_codes:
        return
    role = db.scalar(select(Role).where(Role.code == "platform_admin"))
    if role is None:
        return
    owned = {item.code for item in role.permissions}
    missing = sorted(created_codes - owned)
    if not missing:
        return
    available = {
        item.code: item
        for item in db.scalars(select(Permission).where(Permission.code.in_(missing))).all()
    }
    granted = [available[code] for code in missing if code in available]
    if not granted:
        return
    role.permissions = [*role.permissions, *granted]
    db.commit()


def ensure_default_users(db: Session) -> None:
    """按需创建内置演示用户；**已存在的用户一律不修改**。

    旧实现在每次启动时把已存在用户的 `real_name / mobile / status / tenant_code /
    role_id / region_id` 全部覆盖回预设值，并调用 `_ensure_user_region_permissions`
    把区域授权重置为预设集合——运维在「人员权限」页改过的东西会在重启后被悄悄改回去
    （典型表现：改了某用户的数据权限区域，重启后\"自己恢复了\"）。

    现在改为：用户不存在才创建（连默认区域授权一起种）；用户名已存在则整个跳过，
    不碰任何字段、不碰授权行。需要重置请显式走运维手段，不要依赖启动流程。
    """
    password_hash = hash_password("Admin123456")
    preferred_regions = _resolve_demo_regions(db)
    changed = False
    for item in DEFAULT_USERS:
        existing = db.scalar(select(User).where(User.username == item["username"]))
        if existing is not None:
            # 已存在：不覆盖资料、不重置角色/区域、不重灌区域授权。
            continue
        role = db.scalar(select(Role).where(Role.code == item["role_code"]))
        region_code = item.get("region_code") or preferred_regions.get(item["role_code"])
        region = db.scalar(select(Region).where(Region.code == region_code))
        if role is None or region is None:
            continue
        user = User(
            username=item["username"],
            real_name=item["real_name"],
            password_hash=password_hash,
            mobile=item["mobile"],
            status="active",
            tenant_code=region.tenant_code,
            role_id=role.id,
            region_id=region.id,
        )
        db.add(user)
        db.flush()
        permission_codes = item.get("permission_codes") or [region.code]
        _seed_user_region_permissions(db, user, permission_codes)
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


def _seed_user_region_permissions(db: Session, user: User, region_codes: list[str]) -> None:
    """给**新建**用户种默认区域授权。

    只在用户当前没有任何授权行时写入。已有授权则一行都不动：不删、不补、不改。

    旧实现（名为 `_ensure_user_region_permissions`）会先 `db.delete()` 掉所有不在预设集
    合里的授权行、再补齐缺失的，等于每次启动都把用户的授权\"对齐\"回代码预设值。
    这是\"改了数据权限区域、重启后被改回去\"的直接原因，已废弃。

    授权只能由「人员权限」页或显式运维脚本变更，启动流程无权覆盖。
    """
    has_any = db.scalar(
        select(func.count())
        .select_from(UserRegionPermission)
        .where(UserRegionPermission.user_id == user.id)
    )
    if has_any:
        return

    desired_codes = {code for code in (_normalize_region_code(raw_code) for raw_code in region_codes) if code}
    for code in desired_codes:
        db.add(
            UserRegionPermission(
                user_id=user.id,
                tenant_code=code[:6],
                region_code=code,
                level=_level_by_region_code(code),
            )
        )


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
    """补齐缺失的默认图层；**已存在的图层一律不覆盖、不删除**。

    旧实现会：① 删掉 `LEGACY_DEFAULT_MAP_LAYER_KEYS` 里的历史图层行；
    ② 把 survey_dk_result 的 name/group_name、image 的 service_url 覆写回预设值。
    结果是运维在「图层管理」页改过的图层名称、底图地址会在重启后被改回去。
    现在只做缺则新增；历史遗留行的清理不再由启动流程承担（需要时走显式运维 SQL）。
    """
    changed = False
    for item in DEFAULT_MAP_LAYERS:
        if item["key"] in LEGACY_DEFAULT_MAP_LAYER_KEYS:
            continue
        existing = db.scalar(select(MapLayer).where(MapLayer.key == item["key"]))
        if existing is not None:
            continue
        if item["key"] == "survey_dk_result":
            item = {**item, "name": "\u627f\u5305\u5730\u5757", "group_name": "GeoServer\u56fe\u5c42"}
        db.add(
            MapLayer(
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
        )
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
    """仅在**字典表为空**时灌入内置预设；表里已有数据则完全不动。

    旧实现是「表非空就再按 dict_type 同步一次」（`_sync_dictionary_group`）：那个同步会
    覆写已存在字典项的 `dict_name / item_name / sort_order / remark / enabled`，还会
    **删除**所有不在预设清单里的字典项——运维在「字典管理」页改过或补录过的条目会在
    重启后丢失。现在改为：有数据就一行不碰。

    注意取舍：字典表非空时，代码后续版本新增的 dict_type 不会自动灌入，
    需要时请显式执行运维数据脚本。
    """
    existing_count = db.scalar(select(func.count()).select_from(DictionaryItem)) or 0
    if existing_count > 0:
        return

    from app.db.dictionary_presets import NYT2539_APPENDIX_C_DICTIONARY_ITEMS

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


# 原 `_sync_dictionary_group()` 已删除：它会在每次启动时覆写已存在字典项的字段，
# 并删除所有不在预设清单里的项，属于\"用代码预设覆盖运维数据\"。
# 字典预设现在只在字典表为空时灌入一次，见 `ensure_dictionary_presets()`。





