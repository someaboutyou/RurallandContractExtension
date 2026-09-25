from datetime import datetime

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    userCount: int
    issuerCount: int
    requestCount: int
    todoCount: int
    workflowEnabled: bool
    gisEnabled: bool


class BigscreenBatchOption(BaseModel):
    """大屏顶部批次下拉的一项。"""

    id: int
    batchNo: str
    batchName: str
    status: str
    regionCode: str | None = None
    regionName: str | None = None
    startedAt: datetime | None = None


class BigscreenOverview(BaseModel):
    """核心总量与三个关键完成率（分配 / 调查 / 确认）。"""

    contractorTotal: int
    parcelTotal: int
    issuerTotal: int
    memberTotal: int
    contractAreaMu: float
    assignedCount: int
    assignedRate: float
    surveyedCount: int
    surveyedRate: float
    confirmedCount: int
    confirmedRate: float
    changedCount: int
    changeRecordCount: int
    requestGeneratedCount: int
    attachmentCount: int


class BigscreenFunnelStep(BaseModel):
    """办理漏斗一步：基线 → 已分配 → 已调查 → 已确认 → 已生成申请。"""

    key: str
    label: str
    count: int
    rate: float


class BigscreenStatusItem(BaseModel):
    key: str
    label: str
    count: int
    tone: str


class BigscreenAssignee(BaseModel):
    userId: int
    name: str
    total: int
    surveyed: int
    confirmed: int
    surveyedRate: float
    rank: int


class BigscreenRegionRow(BaseModel):
    code: str
    name: str
    total: int
    assigned: int
    surveyed: int
    confirmed: int
    assignedRate: float
    surveyedRate: float
    confirmedRate: float


class BigscreenRegionBoard(BaseModel):
    level: str
    levelLabel: str
    leading: list[BigscreenRegionRow]
    lagging: list[BigscreenRegionRow]


class BigscreenChangeType(BaseModel):
    key: str
    label: str
    count: int


class BigscreenTrendPoint(BaseModel):
    date: str
    assigned: int
    investigated: int
    confirmed: int


class BigscreenAlert(BaseModel):
    level: str
    title: str
    detail: str
    count: int
    actionKey: str


class DashboardBigscreen(BaseModel):
    generatedAt: datetime
    batch: BigscreenBatchOption | None
    batches: list[BigscreenBatchOption]
    overview: BigscreenOverview
    funnel: list[BigscreenFunnelStep]
    taskStatus: list[BigscreenStatusItem]
    assignees: list[BigscreenAssignee]
    regionBoard: BigscreenRegionBoard
    changeTypes: list[BigscreenChangeType]
    trend: list[BigscreenTrendPoint]
    alerts: list[BigscreenAlert]
