from datetime import datetime

from pydantic import BaseModel, Field


class SurveyBatchCreate(BaseModel):
    batchName: str | None = Field(default=None, max_length=120)
    regionCode: str | None = Field(default=None, max_length=32)
    regionName: str | None = Field(default=None, max_length=120)
    remark: str | None = None
    # 指派调查员。**必填与否取决于是不是管理员**，所以这里不能写 min_length=1：
    # - 管理员：必填（至少 1 人），可指派他人；
    # - 其他人：前端不显示选择器、也不传这个字段，服务端强制派给自己。
    # Pydantic 拿不到 current_user，做不了「按角色必填」；若在此写 min_length=1，
    # 非管理员的正常请求会被 422 拦死。必填校验统一放
    # services/survey/assignment.py::resolve_batch_create_assignees 按角色判。
    assigneeIds: list[int] | None = Field(default=None, max_length=50)


class SurveyBatchRead(BaseModel):
    id: int
    batchNo: str
    batchName: str
    regionCode: str | None = None
    regionName: str | None = None
    surveyType: str
    status: str
    taskCount: int = 0
    notStartedCount: int = 0
    surveyedCount: int = 0
    changedCount: int = 0
    confirmedCount: int = 0
    skippedCount: int = 0
    createdAt: datetime
    remark: str | None = None
    # 批次调查员：聚合自该批次任务的归属人（survey_cbf_base.assigned_to），
    # 按名下户数降序去重。批次本身不存调查员字段，避免与任务归属两处真相。
    assigneeNames: list[str] = Field(default_factory=list)
    assigneeCount: int = 0
    unassignedCount: int = 0
    # 「与我相关」的标记：调查员登录后，自己创建的批次与（别人创建但）分给自己的批次
    # 都要在列表里显示出来，卡片上据此打标签。
    createdByMe: bool = False
    assignedToMe: bool = False
    myTaskCount: int = 0


class SurveyTaskRead(BaseModel):
    id: int
    batchId: int
    contractorUid: str
    cbfbm: str
    cbfmc: str
    cbfdz: str | None = None
    cbfcysl: int = 0
    lxdh: str | None = None
    regionCode: str | None = None
    groupRegionCode: str | None = None
    groupRegionName: str | None = None
    taskStatus: str
    hasChange: bool
    changeCount: int
    investigatedAt: datetime | None = None
    remark: str | None = None
    # 任务归属（survey_cbf_base.assigned_to）：只有归属人能录入，其余人只能查看。
    assignedTo: int | None = None
    assignedToName: str | None = None
    assignedAt: datetime | None = None
    # 实际调查人（区别于归属人）：来自 survey_cbf_result.investigator_name。
    investigatorName: str | None = None
    # 当前用户能否录入这一户（后端算，与 ensure_task_write_permission 同口径）。
    # 前端据此把「调查录入」降级成「查看详情」并把对话框切只读；
    # 默认 False 是安全方向：调用方忘传时就当只读，而不是当可写。
    canWrite: bool = False


class SurveyDeregisteredContractorRead(BaseModel):
    id: int
    batchId: int
    contractorUid: str
    cbfbm: str
    cbfmc: str
    cbfdz: str | None = None
    cbfcysl: int = 0
    lxdh: str | None = None
    groupRegionCode: str | None = None
    groupRegionName: str | None = None
    deregisterReason: str | None = None
    deregisteredAt: datetime | None = None
    changeNo: str | None = None
    #: 让该户离开待办的终态操作类型：deregister / merge_household / split_household。
    #: 前端据此把「撤回」按钮分流到对应的撤回接口（不再一律打 rollback-deregister）。
    changeType: str | None = None
    canRollback: bool = True


class SurveyIssuerRowRead(BaseModel):
    id: int
    batchId: int
    issuerUid: str
    code: str
    name: str
    responsibleName: str
    surveyStatus: str
    relatedContractorCount: int = 0
    surveyDate: str | None = None
    surveyorName: str | None = None
    sourceTask: SurveyTaskRead | None = None


class SurveyContractorCreate(BaseModel):
    code: str = Field(min_length=1, max_length=18)
    typeCode: str = Field(default="1", min_length=1, max_length=1)
    name: str = Field(min_length=1, max_length=50)
    idType: str = Field(default="1", min_length=1, max_length=1)
    idNo: str = Field(min_length=1, max_length=20)
    address: str = Field(min_length=1, max_length=100)
    postcode: str = Field(default="000000", min_length=1, max_length=6)
    mobile: str | None = Field(default=None, max_length=20)
    groupRegionCode: str | None = Field(default=None, max_length=32)
    groupRegionName: str | None = Field(default=None, max_length=120)
    surveyorName: str | None = Field(default=None, max_length=50)
    surveyDate: str | None = None
    remark: str | None = None


class SurveyIssuerCreate(BaseModel):
    code: str = Field(min_length=1, max_length=14)
    name: str = Field(min_length=1, max_length=50)
    responsibleName: str = Field(min_length=1, max_length=50)
    responsibleIdType: str = Field(default="1", min_length=1, max_length=1)
    responsibleIdNo: str = Field(min_length=1, max_length=30)
    phone: str | None = Field(default=None, max_length=15)
    address: str = Field(min_length=1, max_length=100)
    postcode: str = Field(default="000000", min_length=1, max_length=6)
    surveyorName: str | None = Field(default=None, max_length=254)
    surveyDate: str | None = None
    surveyNote: str | None = Field(default=None, max_length=254)
    remark: str | None = None


class SurveyChangeRecordRead(BaseModel):
    id: int
    changeNo: str
    batchId: int
    contractorUid: str
    cbfbm: str
    changeType: str
    changeLevel: str
    changeStatus: str
    changeReason: str | None = None
    policyBasis: str | None = None
    generatedRequestId: int | None = None
    generatedRequestNo: str | None = None
    investigatorName: str | None = None
    investigatedAt: datetime | None = None
    beforeSummary: dict | None = None
    afterSummary: dict | None = None
    createdAt: datetime


class SurveyChangeDiffRead(BaseModel):
    id: int
    batchId: int
    contractorUid: str
    changeId: int | None = None
    entityType: str
    entityUid: str
    entityName: str | None = None
    fieldName: str
    fieldLabel: str
    beforeValue: str | None = None
    afterValue: str | None = None
    changeReason: str | None = None
    createdAt: datetime


class SurveyTagCreate(BaseModel):
    tagCode: str = Field(min_length=1, max_length=64)
    tagName: str = Field(min_length=1, max_length=80)
    reason: str | None = None
    policyBasis: str | None = None


class SurveyTagDisable(BaseModel):
    disabledReason: str = Field(min_length=1, max_length=500)


class SurveyRestructureMemberUpdate(BaseModel):
    memberUid: str | None = None
    memberName: str = Field(min_length=1, max_length=50)
    memberIdNo: str | None = Field(default=None, max_length=20)
    fromCbfbm: str | None = Field(default=None, max_length=18)
    toCbfbm: str | None = Field(default=None, max_length=18)
    actionType: str = Field(default="move", max_length=32)
    rightsDisposition: str | None = Field(default=None, max_length=64)
    remark: str | None = None


class SurveyRestructureCreate(BaseModel):
    restructureType: str = Field(min_length=1, max_length=32)
    sourceContractorUid: str | None = Field(default=None, max_length=36)
    sourceCbfbm: str | None = Field(default=None, max_length=18)
    sourceCbfmc: str | None = Field(default=None, max_length=50)
    targetContractorUid: str | None = Field(default=None, max_length=36)
    targetCbfbm: str | None = Field(default=None, max_length=18)
    targetCbfmc: str | None = Field(default=None, max_length=50)
    newCbfbm: str | None = Field(default=None, max_length=18)
    newCbfmc: str | None = Field(default=None, max_length=50)
    status: str = Field(default="draft", max_length=32)
    reason: str | None = None
    policyBasis: str | None = None
    rightsSummary: str | None = None
    contractDisposition: str | None = Field(default=None, max_length=64)
    certificateDisposition: str | None = Field(default=None, max_length=64)
    remark: str | None = None
    members: list[SurveyRestructureMemberUpdate] = []


class SurveyAuthorizationCreate(BaseModel):
    principalName: str = Field(min_length=1, max_length=50)
    principalIdNo: str | None = Field(default=None, max_length=32)
    agentName: str = Field(min_length=1, max_length=50)
    agentIdNo: str | None = Field(default=None, max_length=32)
    agentPhone: str | None = Field(default=None, max_length=32)
    authorizedMatters: str = Field(min_length=1)
    validFrom: str | None = None
    validTo: str | None = None
    status: str = Field(default="active", max_length=32)
    remark: str | None = None


class SurveyAuthorizationRevoke(BaseModel):
    revokeReason: str = Field(min_length=1, max_length=500)


# ── 合同信息 ──────────────────────────────────────────

class SurveyContractRead(BaseModel):
    cbhtbm: str
    ycbhtbm: str | None = None
    fbfbm: str | None = None
    fbfmc: str | None = None
    cbfbm: str | None = None
    cbfs: str | None = None
    cbqxq: str | None = None
    cbqxz: str | None = None
    htzmj: float | None = None
    htzmjm: float | None = None
    cbdkzs: int | None = None
    qdsj: str | None = None
    renderedHtml: str | None = None
    # 延包业务：合同版本（现行 / 历史）与来源（上次承包合同 / 平台生成的延包合同）
    contractStatus: str | None = None
    contractStatusText: str | None = None
    contractSource: str | None = None
    isCurrent: bool | None = None
    isOriginal: bool | None = None
    generatedAt: str | None = None
    generatedBy: str | None = None


class SurveyContractGenerate(BaseModel):
    """生成延包合同。

    全部字段都可缺省：承包期限起默认取**上次合同到期时间**（没有上次合同则为空），
    承包期限止默认 = 起 + ``years`` 年 − 1 天（``years`` 默认 30）。
    """

    cbqxq: str | None = None
    cbqxz: str | None = None
    years: int | None = Field(default=None, ge=1, le=100)
    qdsj: str | None = None
    cbfs: str | None = Field(default=None, max_length=3)


class SurveyContractPrint(BaseModel):
    cbhtbm: str | None = None



class SurveyPlotSketchMapRead(BaseModel):
    cbfbm: str | None = None
    cbfmc: str | None = None
    plotCount: int = 0
    totalArea: str | None = None
    renderedHtml: str | None = None


# ── 调查操作请求 ──────────────────────────────────────

class SurveyChangeHeadRequest(BaseModel):
    newHeadMemberUid: str = Field(min_length=1, max_length=36)
    reason: str | None = Field(default=None, max_length=500)


class SurveyDeregisterRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class SurveyAddParcelRequest(BaseModel):
    dkbm: str = Field(min_length=1, max_length=19)
    dkmc: str = Field(min_length=1, max_length=50)
    scmj: float = Field(gt=0)
    dklb: str = Field(min_length=1, max_length=2)
    tdyt: str = Field(min_length=1, max_length=1)
    sfjbnt: str = Field(min_length=1, max_length=1)
    dldj: str = Field(min_length=1, max_length=2)
    syqxz: str | None = Field(default=None, max_length=2)
    tdlylx: str | None = Field(default=None, max_length=3)
    dkdz: str | None = Field(default=None, max_length=50)
    dkxz: str | None = Field(default=None, max_length=50)
    dknz: str | None = Field(default=None, max_length=50)
    dkbz: str | None = Field(default=None, max_length=50)
    dkbzxx: str | None = Field(default=None, max_length=300)
    cbjyqqdfs: str = Field(default="001", max_length=3)
    cbhtbm: str | None = Field(default=None, max_length=19)
    lzhtbm: str | None = Field(default=None, max_length=20)
    cbjyqzbm: str | None = Field(default=None, max_length=19)
    htmj: float | None = None
    yhtmj: float | None = None
    htmjm: float | None = None
    yhtmjm: float | None = None
    sfqqqg: str | None = Field(default=None, max_length=1)
    geometry: dict | None = None
    geometrySourceSrid: int = Field(default=4326, ge=1, le=999999)
    reason: str | None = Field(default=None, max_length=500)


class SurveyParcelGeometryLocalParcel(BaseModel):
    dkbm: str | None = Field(default=None, max_length=19)
    dkmc: str | None = Field(default=None, max_length=50)
    cbfbm: str | None = Field(default=None, max_length=18)
    cbfmc: str | None = Field(default=None, max_length=50)
    resultStatus: str | None = Field(default=None, max_length=32)
    geometry: dict | None = None


class SurveyParcelGeometryValidateRequest(BaseModel):
    geometry: dict
    geometrySourceSrid: int = Field(default=4326, ge=1, le=999999)
    localParcels: list[SurveyParcelGeometryLocalParcel] = []


class SurveyParcelGeometryOverlapRead(BaseModel):
    source: str = Field(default="database", max_length=32)
    dkbm: str | None = None
    dkmc: str | None = None
    cbfbm: str | None = None
    cbfmc: str | None = None
    overlapAreaMu: float | None = None


class SurveyParcelGeometryValidateRead(BaseModel):
    valid: bool = True
    areaMu: float | None = None
    overlaps: list[SurveyParcelGeometryOverlapRead] = []


class SurveySplitParcelRequest(BaseModel):
    dkbm: str = Field(min_length=1, max_length=19)
    newDkbm: str | None = Field(default=None, max_length=19)
    newDkmc: str | None = Field(default=None, max_length=50)
    splitMode: str | None = Field(default="area", max_length=32)
    newScmj: float | None = Field(default=None, gt=0)
    splitDirection: str | None = Field(default=None, max_length=16)
    splitGeometry: dict | None = None
    geometrySourceSrid: int = Field(default=4326, ge=1, le=999999)
    reason: str | None = Field(default=None, max_length=500)
    generatedParcels: list["SurveySplitGeneratedParcel"] = []


class SurveySplitGeneratedParcel(BaseModel):
    dkbm: str = Field(min_length=1, max_length=19)
    dkmc: str = Field(min_length=1, max_length=50)
    scmj: float | None = Field(default=None, gt=0)
    htmj: float | None = Field(default=None, gt=0)
    geometry: dict | None = None


class SurveySplitParcelPreviewRead(BaseModel):
    sourceDkbm: str
    splitMode: str
    generatedParcels: list[SurveySplitGeneratedParcel] = []


class SurveyRemoveParcelRequest(BaseModel):
    dkbm: str = Field(min_length=1, max_length=19)
    reason: str | None = Field(default=None, max_length=500)


class SurveySwapParcelsRequest(BaseModel):
    targetContractorUid: str = Field(min_length=1, max_length=36)
    sourceDkbms: list[str] = Field(min_length=1)
    targetDkbms: list[str] = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=500)


class SurveyRollbackSwapParcelsRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# ── 界址点 / 界址线维护 ──────────────────────────────────────────────────────
# 结构（点位、边）由地块图形决定，请求体只提交属性，并按显示序号 seq 对齐。


class SurveyBoundaryPointUpdate(BaseModel):
    """界址点属性更新项。``seq`` 与界面上 ``J1..Jn`` 的显示序号一致。"""

    seq: int = Field(ge=1)
    jzdh: str | None = Field(default=None, max_length=32)
    jblx: str | None = Field(default=None, max_length=2)
    bz: str | None = Field(default=None, max_length=200)


class SurveyBoundaryLineUpdate(BaseModel):
    """界址线属性更新项。

    ``seq`` 表示"从第 seq 个界址点出发的那条界址线"，与调查表逐行对应。
    """

    seq: int = Field(ge=1)
    fromCode: str | None = Field(default=None, max_length=16)
    toCode: str | None = Field(default=None, max_length=16)
    jzxlb: str | None = Field(default=None, max_length=2)
    jzxwz: str | None = Field(default=None, max_length=2)
    jzxsm: str | None = Field(default=None, max_length=200)


class SurveyParcelBoundaryUpdate(BaseModel):
    points: list[SurveyBoundaryPointUpdate] = []
    lines: list[SurveyBoundaryLineUpdate] = []


class SurveyBoundaryOptionRead(BaseModel):
    value: str
    label: str


class SurveyBoundaryOptionsRead(BaseModel):
    markTypes: list[SurveyBoundaryOptionRead] = []
    lineCategories: list[SurveyBoundaryOptionRead] = []
    linePositions: list[SurveyBoundaryOptionRead] = []


class SurveyBoundaryPointRead(BaseModel):
    seq: int
    code: str
    jzdh: str | None = None
    x: str
    y: str
    jblx: str | None = None
    bz: str | None = None
    edge: str | None = None
    registered: bool = False


class SurveyBoundaryLineRead(BaseModel):
    seq: int
    fromCode: str
    toCode: str
    fromJzdh: str | None = None
    toJzdh: str | None = None
    jzxlb: str | None = None
    jzxwz: str | None = None
    jzxsm: str | None = None
    registered: bool = False


class SurveyParcelBoundaryRead(BaseModel):
    dkbm: str
    dkmc: str | None = None
    contractorUid: str
    cbfbm: str
    mappingUnit: str
    cordSystem: str
    editable: bool
    options: SurveyBoundaryOptionsRead
    points: list[SurveyBoundaryPointRead] = []
    lines: list[SurveyBoundaryLineRead] = []


class SurveySplitHouseholdTarget(BaseModel):
    newCbfbm: str = Field(min_length=1, max_length=18)
    newCbfmc: str = Field(min_length=1, max_length=50)
    memberUids: list[str] = Field(min_length=1)
    parcelDkbms: list[str] = Field(min_length=1)
    householdHeadMemberUid: str = Field(min_length=1, max_length=36)


class SurveySplitHouseholdRequest(BaseModel):
    newHouseholds: list[SurveySplitHouseholdTarget] = Field(min_length=2)
    reason: str | None = Field(default=None, max_length=500)


class SurveyMergeHouseholdRequest(BaseModel):
    sourceContractorUids: list[str] = Field(min_length=2)
    newCbfbm: str = Field(min_length=18, max_length=18)
    newCbfmc: str = Field(min_length=1, max_length=50)
    householdHeadMemberUid: str = Field(min_length=1, max_length=36)
    newAddress: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500)


class SurveyMemberEntry(BaseModel):
    memberUid: str | None = None
    name: str = Field(min_length=1, max_length=50)
    gender: str = Field(min_length=1, max_length=1)
    idType: str = Field(min_length=1, max_length=1)
    idNo: str = Field(min_length=1, max_length=20)
    relationToHead: str = Field(min_length=1, max_length=2)
    noteCode: str | None = Field(default=None, max_length=1)
    isCoOwner: str | None = Field(default=None, max_length=1)
    note: str | None = Field(default=None, max_length=254)
    isHouseholdHead: bool = False
    changeReason: str | None = Field(default=None, max_length=500)


class SurveyMemberDeleteEntry(BaseModel):
    memberUid: str = Field(min_length=1, max_length=36)
    changeReason: str | None = Field(default=None, max_length=500)


class SurveyMaintainMembersRequest(BaseModel):
    membersToAdd: list[SurveyMemberEntry] = []
    membersToUpdate: list[SurveyMemberEntry] = []
    membersToDelete: list[str | SurveyMemberDeleteEntry] = []  # keep string UID compatibility
    reason: str | None = Field(default=None, max_length=500)


class SurveyGenerateRequest(BaseModel):
    requestType: str | None = Field(default=None, max_length=32)
    requestTitle: str | None = Field(default=None, max_length=120)
    reason: str | None = None
    note: str | None = None


class SurveyTaskSkip(BaseModel):
    skipReason: str = Field(min_length=1, max_length=500)


class SurveyTaskAssignRequest(BaseModel):
    """批量分配/改派承包方调查任务。assigneeId 为 None 表示收回分配。"""

    contractorUids: list[str] = Field(min_length=1, max_length=500)
    assigneeId: int | None = None


class SurveyMemberUpdate(BaseModel):
    memberUid: str | None = None
    name: str = Field(min_length=1, max_length=50)
    gender: str = Field(min_length=1, max_length=1)
    idType: str = Field(min_length=1, max_length=1)
    idNo: str = Field(min_length=1, max_length=20)
    relationToHead: str = Field(min_length=1, max_length=2)
    noteCode: str | None = Field(default=None, max_length=1)
    isCoOwner: str | None = Field(default=None, max_length=1)
    note: str | None = Field(default=None, max_length=254)
    memberResultStatus: str = "normal"
    surveyStatus: str = "surveyed"
    isHouseholdHead: bool = False
    isUrbanSettled: bool = False
    urbanSettledDate: str | None = None
    urbanSettledPlace: str | None = None
    isMarriedOutWoman: bool = False
    marriedOutDate: str | None = None
    marriedOutPlace: str | None = None
    isDeceased: bool = False
    deceasedDate: str | None = None
    isFiveGuarantees: bool = False
    currentResidenceAddress: str | None = None
    householdRegisterAddress: str | None = None
    phone: str | None = None
    changeReason: str | None = None
    policyBasis: str | None = None
    rightsDisposition: str | None = None
    remark: str | None = None


class SurveyIssuerUpdate(BaseModel):
    issuerUid: str | None = None
    code: str = Field(min_length=1, max_length=14)
    name: str = Field(min_length=1, max_length=50)
    responsibleName: str = Field(min_length=1, max_length=50)
    responsibleIdType: str = Field(min_length=1, max_length=1)
    responsibleIdNo: str = Field(min_length=1, max_length=30)
    phone: str | None = Field(default=None, max_length=15)
    address: str = Field(min_length=1, max_length=100)
    postcode: str = Field(min_length=1, max_length=6)
    surveyorName: str | None = Field(default=None, max_length=254)
    surveyDate: str | None = None
    surveyNote: str | None = Field(default=None, max_length=254)
    surveyStatus: str = "surveyed"
    resultStatus: str = "normal"
    changeType: str = "none"
    changeReason: str | None = None
    policyBasis: str | None = None
    remark: str | None = None


class SurveyPendingOperation(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    payload: dict = {}


class SurveyContractorUpdate(BaseModel):
    code: str = Field(min_length=1, max_length=18)
    typeCode: str = Field(min_length=1, max_length=1)
    name: str = Field(min_length=1, max_length=50)
    idType: str = Field(min_length=1, max_length=1)
    idNo: str = Field(min_length=1, max_length=20)
    address: str = Field(min_length=1, max_length=100)
    postcode: str = Field(min_length=1, max_length=6)
    mobile: str | None = None
    surveyDate: str | None = None
    surveyorName: str | None = None
    surveyNote: str | None = None
    publicNoticeNote: str | None = None
    publicNoticeRecorder: str | None = None
    publicNoticeReviewDate: str | None = None
    publicNoticeReviewer: str | None = None
    groupRegionCode: str | None = Field(default=None, max_length=32)
    groupRegionName: str | None = Field(default=None, max_length=120)
    surveyStatus: str = "surveyed"
    resultStatus: str = "normal"
    changeType: str = "none"
    changeReason: str | None = None
    policyBasis: str | None = None
    evidenceSummary: str | None = None
    remark: str | None = None
    issuer: SurveyIssuerUpdate | None = None
    familyMembers: list[SurveyMemberUpdate] = []
    deletedMembers: list[SurveyMemberDeleteEntry] = []
    pendingOperations: list[SurveyPendingOperation] = []


class SurveyMemberRead(SurveyMemberUpdate):
    memberUid: str
    baseId: int | None = None
    isChanged: bool = False


class SurveyBaseMemberRead(BaseModel):
    memberUid: str
    name: str
    gender: str
    idType: str
    idNo: str
    relationToHead: str
    noteCode: str | None = None
    isCoOwner: str | None = None
    note: str | None = None


class SurveyBaseContractorRead(BaseModel):
    code: str
    typeCode: str
    name: str
    idType: str
    idNo: str
    address: str
    postcode: str
    mobile: str | None = None
    memberCount: int
    surveyDate: str | None = None
    surveyorName: str | None = None
    surveyNote: str | None = None
    publicNoticeNote: str | None = None
    publicNoticeRecorder: str | None = None
    publicNoticeReviewDate: str | None = None
    publicNoticeReviewer: str | None = None
    groupRegionCode: str | None = None
    groupRegionName: str | None = None
    familyMembers: list[SurveyBaseMemberRead] = []


class SurveyIssuerRead(SurveyIssuerUpdate):
    id: int
    baseId: int | None = None
    isChanged: bool = False


class SurveyBaseIssuerRead(BaseModel):
    code: str
    name: str
    responsibleName: str
    responsibleIdType: str
    responsibleIdNo: str
    phone: str | None = None
    address: str
    postcode: str
    surveyorName: str | None = None
    surveyDate: str | None = None
    surveyNote: str | None = None


class SurveyContractorRead(BaseModel):
    id: int
    batchId: int
    contractorUid: str
    baseId: int | None = None
    code: str
    typeCode: str
    name: str
    idType: str
    idNo: str
    address: str
    postcode: str
    mobile: str | None = None
    memberCount: int
    surveyDate: str | None = None
    surveyorName: str | None = None
    surveyNote: str | None = None
    publicNoticeNote: str | None = None
    publicNoticeRecorder: str | None = None
    publicNoticeReviewDate: str | None = None
    publicNoticeReviewer: str | None = None
    groupRegionCode: str | None = None
    groupRegionName: str | None = None
    surveyStatus: str
    resultStatus: str
    isChanged: bool
    changeType: str
    changeReason: str | None = None
    # 已被终结（注销 / 被合户并走 / 被分户拆走）。⚠️ 必须在这里声明：模型外字段会被
    # pydantic **静默丢掉**，前端就拿不到（`/auth/me` 漏 `regionPermissions` 的同类坑）。
    isTerminal: bool = False
    policyBasis: str | None = None
    evidenceSummary: str | None = None
    remark: str | None = None
    baseContractor: SurveyBaseContractorRead | None = None
    issuer: SurveyIssuerRead | None = None
    baseIssuer: SurveyBaseIssuerRead | None = None
    familyMembers: list[SurveyMemberRead]
    generatedRequestId: int | None = None
    generatedRequestNo: str | None = None
