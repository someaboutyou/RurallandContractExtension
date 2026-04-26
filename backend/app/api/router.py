from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    contractor,
    dashboard,
    gis,
    issuer,
    map_layer,
    permission,
    region,
    request_attachment_template,
    request_case,
    request_workflow_mapping,
    role,
    tenant,
    user,
    workflow_definition,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(contractor.router, prefix="/contractors", tags=["Contractors"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(gis.router, prefix="/gis", tags=["GIS"])
api_router.include_router(region.router, prefix="/regions", tags=["Regions"])
api_router.include_router(permission.router, prefix="/permissions", tags=["Permissions"])
api_router.include_router(map_layer.router, prefix="/map-layers", tags=["MapLayers"])
api_router.include_router(role.router, prefix="/roles", tags=["Roles"])
api_router.include_router(tenant.router, prefix="/tenants", tags=["Tenants"])
api_router.include_router(user.router, prefix="/users", tags=["Users"])
api_router.include_router(issuer.router, prefix="/issuers", tags=["Issuers"])
api_router.include_router(request_attachment_template.router, prefix="/request-attachment-templates", tags=["RequestAttachmentTemplates"])
api_router.include_router(request_case.router, prefix="/requests", tags=["Requests"])
api_router.include_router(request_workflow_mapping.router, prefix="/request-workflow-mappings", tags=["RequestWorkflowMappings"])
api_router.include_router(workflow_definition.router, prefix="/workflow-definitions", tags=["WorkflowDefinitions"])
