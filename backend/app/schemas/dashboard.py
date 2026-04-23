from pydantic import BaseModel


class DashboardSummary(BaseModel):
    userCount: int
    issuerCount: int
    requestCount: int
    todoCount: int
    workflowEnabled: bool
    gisEnabled: bool
