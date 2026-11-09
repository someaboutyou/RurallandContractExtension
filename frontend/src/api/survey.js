import http from "./http";

export function fetchSurveyBatches(params) {
  return http.get("/surveys/batches", { params });
}

export function createSurveyBatch(payload) {
  return http.post("/surveys/batches", payload);
}

/** 进行中的调查批次（含区域码与创建人），用于新建批次时置灰已初始化的区域。 */
export function fetchActiveSurveyBatches() {
  return http.get("/surveys/active-batches");
}

/** 当前用户「进入任务」记住的批次。 */
export function fetchCurrentSurveyBatch() {
  return http.get("/surveys/current-batch");
}

/** 记录当前批次（下次进入系统时相关页面默认显示该批次）。 */
export function setCurrentSurveyBatch(batchId) {
  return http.put("/surveys/current-batch", { batchId });
}

/** 批次统计：发包方 / 承包方 / 家庭成员 / 承包地块 / 承包合同。 */
export function fetchSurveyBatchStats(batchId) {
  return http.get(`/surveys/batches/${batchId}/stats`);
}

export function finishSurveyBatch(batchId) {
  return http.post(`/surveys/batches/${batchId}/finish`);
}

export function exportSurveyResults(batchId, params) {
  return http.get(`/surveys/batches/${batchId}/export-results.zip`, { params, responseType: "blob" });
}

/** 承包方调查表 Excel 导出（鱼鳞图样式模板，xls）。 */
export function exportContractorSurveyXls(batchId) {
  return http.get(`/surveys/batches/${batchId}/contractors-xls`, { responseType: "blob" });
}

/** 按勾选的承包方批量导出调查表/声明书/测绘申请书。 */
export function exportContractorDocuments(batchId, payload) {
  return http.post(`/surveys/batches/${batchId}/contractors-export`, payload, {
    responseType: "blob",
    timeout: 300000,
  });
}

/** 批量锁定/解锁承包方。 */
export function lockSurveyContractors(batchId, payload) {
  return http.post(`/surveys/batches/${batchId}/contractors-lock`, payload);
}

/** 家庭关系检查。 */
export function checkContractorRelations(batchId) {
  return http.get(`/surveys/batches/${batchId}/contractor-relations/check`, {
    timeout: 120000,
  });
}

/** 家庭关系批量替换。 */
export function replaceContractorRelations(batchId, payload) {
  return http.post(`/surveys/batches/${batchId}/contractor-relations/replace`, payload, {
    timeout: 120000,
  });
}

/** 承包地块导入预览：地块调查表 / 摸底核实表 / 矢量图斑。 */
export function previewParcelImport(batchId, formData) {
  return http.post(`/surveys/batches/${batchId}/parcel-imports/preview`, formData, {
    timeout: 300000,
  });
}

/** 承包地块导入提交。 */
export function importParcels(batchId, formData) {
  return http.post(`/surveys/batches/${batchId}/parcel-imports`, formData, {
    timeout: 600000,
  });
}

/** 按选中发包方批量导出调查表单。 */
export function exportBatchForms(batchId, payload) {
  return http.post(`/surveys/batches/${batchId}/forms-export`, payload, {
    responseType: "blob",
    timeout: 600000,
  });
}

/** 家庭成员关联修复。 */
export function repairContractorMembers(batchId) {
  return http.post(`/surveys/batches/${batchId}/contractor-relations/repair-members`, {}, {
    timeout: 120000,
  });
}

/** 承包方调查表 Excel 导入预览：上传文件，返回逐户校验报告（不落库）。 */
export function previewContractorSurveyXls(batchId, formData) {
  return http.post(`/surveys/batches/${batchId}/contractors-xls/preview`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
}

/** 承包方调查表 Excel 导入：逐户验证、导入（复用页面保存同源逻辑）。 */
export function importContractorSurveyXls(batchId, formData) {
  return http.post(`/surveys/batches/${batchId}/contractors-xls/import`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 600000,
  });
}

// ── 后台任务版导出 / 导入（大数据量：启动任务 → 轮询进度 → 下载/看结果）──

export function startXlsExportJob(batchId) {
  return http.post(`/surveys/batches/${batchId}/contractors-xls/export-jobs`);
}

export function getXlsExportJob(batchId, jobId) {
  return http.get(`/surveys/batches/${batchId}/contractors-xls/export-jobs/${jobId}`);
}

export function downloadXlsExportJob(batchId, jobId) {
  return http.get(`/surveys/batches/${batchId}/contractors-xls/export-jobs/${jobId}/download`, {
    responseType: "blob",
    timeout: 600000, // 大文件 blob 下载走 axios 默认 10s 会被掐断
  });
}

export function startXlsImportJob(batchId, formData) {
  return http.post(`/surveys/batches/${batchId}/contractors-xls/import-jobs`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
}

export function getXlsImportJob(batchId, jobId) {
  return http.get(`/surveys/batches/${batchId}/contractors-xls/import-jobs/${jobId}`);
}

// ── 数据质检（迁移自原延包工具「检查数据库数据」）──────────────────
// 三段式：启动任务 → 轮询进度 → 看结果（结果与历史落 survey_quality_check_records 表）

export function startQualityCheckJob(batchId, items) {
  return http.post(`/surveys/batches/${batchId}/quality-checks`, { items: items || {} }, { timeout: 30000 });
}

export function getQualityCheckJob(batchId, jobId) {
  return http.get(`/surveys/batches/${batchId}/quality-checks/jobs/${jobId}`);
}

export function fetchQualityCheckRuns(batchId, params) {
  return http.get(`/surveys/batches/${batchId}/quality-checks/runs`, { params });
}

export function fetchQualityCheckRecords(batchId, runId, params) {
  return http.get(`/surveys/batches/${batchId}/quality-checks/runs/${runId}/records`, { params });
}

export function exportQualityCheckRecords(batchId, runId, params) {
  return http.get(`/surveys/batches/${batchId}/quality-checks/runs/${runId}/records/export`, {
    params,
    responseType: "blob",
  });
}


export function fetchSurveyTasks(batchId, params) {
  return http.get(`/surveys/batches/${batchId}/tasks`, { params });
}

export function assignSurveyTasks(batchId, payload) {
  return http.put(`/surveys/batches/${batchId}/tasks/assign`, payload);
}

export function fetchAssignableUsers(batchId) {
  return http.get(`/surveys/batches/${batchId}/assignable-users`);
}

/** 可指派为调查员的用户（不绑定批次）。传 regionCode 时顺带返回 coversRegion，供前端置灰。 */
export function fetchSurveyAssignees(params) {
  return http.get("/surveys/assignees", { params });
}

export function fetchMergeCandidates(batchId, contractorUid, params) {
  return http.get(`/surveys/batches/${batchId}/tasks/${contractorUid}/merge-candidates`, { params });
}

export function fetchSwapCandidates(batchId, contractorUid, params) {
  return http.get(`/surveys/batches/${batchId}/tasks/${contractorUid}/swap-candidates`, { params });
}

export function fetchContractorCodes(batchId, params) {
  return http.get(`/surveys/batches/${batchId}/contractor-codes`, { params });
}

export function fetchDeregisteredSurveyContractors(batchId, params) {
  return http.get(`/surveys/batches/${batchId}/deregistered-contractors`, { params });
}

export function createSurveyContractor(batchId, payload) {
  return http.post(`/surveys/batches/${batchId}/tasks`, payload);
}

export function fetchSurveyIssuers(batchId, params) {
  return http.get(`/surveys/batches/${batchId}/issuers`, { params });
}

/** 单个发包方的《发包方调查表》Word。 */
export function exportIssuerSurveyDocx(batchId, issuerUid) {
  return http.get(`/surveys/batches/${batchId}/issuers/${issuerUid}/survey-docx`, {
    responseType: "blob",
    timeout: 120000,
  });
}

/** 选中的发包方批量导出《发包方调查表》Word（单个 docx / 多个 zip）。 */
export function exportIssuerSurveyDocxBulk(batchId, payload) {
  return http.post(`/surveys/batches/${batchId}/issuers/export-docx`, payload, {
    responseType: "blob",
    timeout: 300000,
  });
}

export function createSurveyIssuer(batchId, payload) {
  return http.post(`/surveys/batches/${batchId}/issuers`, payload);
}

export function fetchSurveyIssuer(batchId, issuerUid) {
  return http.get(`/surveys/batches/${batchId}/issuers/${issuerUid}`);
}

export function updateSurveyIssuer(batchId, issuerUid, payload) {
  return http.put(`/surveys/batches/${batchId}/issuers/${issuerUid}`, payload);
}

export function deleteSurveyIssuer(batchId, issuerUid) {
  return http.delete(`/surveys/batches/${batchId}/issuers/${issuerUid}`);
}

export function deleteSurveyContractor(batchId, contractorUid) {
  return http.delete(`/surveys/batches/${batchId}/results/${contractorUid}`);
}

export function mergeSurveyIssuers(batchId, payload) {
  return http.post(`/surveys/batches/${batchId}/issuers/merge`, payload);
}

export function skipSurveyTask(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/tasks/${contractorUid}/skip`, payload);
}

export function fetchSurveyResult(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}`);
}

export function fetchSurveyPhase2(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/phase2`);
}

export function fetchSurveyDiffs(batchId, contractorUid, params) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/diffs`, { params });
}

export function fetchSurveyChanges(batchId, params) {
  return http.get(`/surveys/batches/${batchId}/changes`, { params });
}

export function updateSurveyResult(batchId, contractorUid, payload) {
  return http.put(`/surveys/batches/${batchId}/results/${contractorUid}`, payload);
}

export function confirmSurveyResult(batchId, contractorUid) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/confirm`);
}

export function unconfirmSurveyResult(batchId, contractorUid) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/unconfirm`);
}

export function refreshSurveyTags(batchId, contractorUid) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/tags/refresh`);
}

export function createSurveyTag(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/tags`, payload);
}

export function disableSurveyTag(tagId, payload) {
  return http.post(`/surveys/tags/${tagId}/disable`, payload);
}

export function createSurveyRestructure(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/restructures`, payload);
}

export function updateSurveyRestructure(id, payload) {
  return http.put(`/surveys/restructures/${id}`, payload);
}

export function deleteSurveyRestructure(id) {
  return http.delete(`/surveys/restructures/${id}`);
}

export function createSurveyAuthorization(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/authorizations`, payload);
}

export function updateSurveyAuthorization(id, payload) {
  return http.put(`/surveys/authorizations/${id}`, payload);
}

export function revokeSurveyAuthorization(id, payload) {
  return http.post(`/surveys/authorizations/${id}/revoke`, payload);
}

export function uploadSurveyAuthorizationFile(id, formData) {
  return http.post(`/surveys/authorizations/${id}/file`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export function downloadSurveyAuthorizationTemplate(id) {
  return http.get(`/surveys/authorizations/${id}/template`, { responseType: "blob" });
}

export function downloadSurveyAuthorizationFile(id) {
  return http.get(`/surveys/authorizations/${id}/file`, { responseType: "blob" });
}

export function uploadSurveyAttachment(batchId, contractorUid, formData) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/attachments`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export function downloadSurveyAttachment(id) {
  return http.get(`/surveys/attachments/${id}/download`, { responseType: "blob" });
}

// 预览与下载取的是同一份文件流，差别只在浏览器如何消费：
// 预览在前端 createObjectURL 后交给 img / iframe 渲染，因此放宽超时（大扫描件容忍更久）。
export function previewSurveyAttachment(id) {
  return http.get(`/surveys/attachments/${id}/download`, { responseType: "blob", timeout: 60000 });
}

export function deleteSurveyAttachment(id) {
  return http.delete(`/surveys/attachments/${id}`);
}

// 调查附件上传的类别选项：来源是「附件组管理」页里 request_type=调查附件 的叶子项。
export function fetchSurveyAttachmentCategories() {
  return http.get("/surveys/attachment-categories");
}

export function fetchSurveyParcels(batchId, contractorUid, params) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/parcels`, { params });
}

/** 建库中心 > 承包地块：以承包方为单位的地块汇总清单。 */
export function fetchParcelsOverview(params) {
  return http.get("/surveys/parcels/overview", { params });
}

/** 承包地块数据初始化（对齐 CS 版承包台账-初始数据）。 */
export function initializeParcelAttributes(payload) {
  return http.post("/surveys/parcels/initialize", payload, { timeout: 180000 });
}

/** 承包地块图幅编号初始化（CS 初始数据-图幅编号）。 */
export function initializeParcelImageNumbers(payload) {
  return http.post("/surveys/parcels/initialize-image-number", payload, {
    timeout: 300000,
  });
}

/** 承包地块调查信息初始化（CS 初始数据-调查信息）。 */
export function initializeParcelSurveyInfo(payload) {
  return http.post("/surveys/parcels/initialize-survey-info", payload, {
    timeout: 180000,
  });
}

/** 承包地块编码与四至获取（CS 初始数据-地块编码/获取四至）。 */
export function initializeParcelCodeBoundary(payload) {
  return http.post("/surveys/parcels/initialize-code-boundary", payload, {
    timeout: 300000,
  });
}

/** 面积量算（CS 初始数据-面积量算）。 */
export function calculateParcelAreas(payload) {
  return http.post("/surveys/parcels/calculate-area", payload, {
    timeout: 300000,
  });
}

/** 面积截取（CS 初始数据-面积截取）。 */
export function truncateParcelAreas(payload) {
  return http.post("/surveys/parcels/truncate-area", payload, {
    timeout: 180000,
  });
}

/** 承包地块矢量数据导出（承包地块/界址点/界址线，Shapefile 或 GDB）。 */
export function exportParcelVector(payload) {
  return http.post("/surveys/parcels/export-vector", payload, {
    responseType: "blob",
    timeout: 600000,
  });
}

/** 界址初始化（CS 初始数据-界址数据）：批量生成界址点/界址线。 */
export function initializeParcelBoundary(payload) {
  return http.post("/surveys/parcels/initialize-boundary", payload, {
    timeout: 600000,
  });
}

/** 基本农田分析（CS 初始数据-基本农田）。 */
export function analyzeParcelBasicFarmland(payload) {
  return http.post("/surveys/parcels/analyze-basic-farmland", payload, {
    timeout: 300000,
  });
}

/** 导出选中地块的《承包地块调查表》Word（一个返回 docx，多个返回 zip）。 */
export function exportParcelSurveyDocx(payload) {
  return http.post("/surveys/parcels/export-docx", payload, {
    responseType: "blob",
    timeout: 180000,
  });
}

/** 导出选中地块的《承包地块示意图》PDF（单户返回 pdf，多户返回 zip）。 */
export function exportParcelSketchPdf(payload) {
  return http.post("/surveys/parcels/export-sketch-pdf", payload, {
    responseType: "blob",
    timeout: 300000,
  });
}

export function validateSurveyParcelGeometry(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/parcels/validate-geometry`, payload);
}

export function previewSplitSurveyParcel(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/parcels/preview-split`, payload);
}

export function generateNextSurveyParcelCode(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/parcels/next-code`);
}

// 把**一条**「待保存」的地块操作单独落库（目前仅支持新增地块）。
// 场景：新增地块后要立刻维护界址点 / 界址线，而界址点由库里的地块图形推导，
// 地块不落库就没有宿体；走这个入口不必把整份调查结果提交一遍。
export function persistSurveyPendingOperation(batchId, contractorUid, operation) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/parcels/persist`, operation);
}

// ── 界址点 / 界址线 ───────────────────────────────────

export function fetchParcelBoundary(batchId, contractorUid, dkbm) {
  return http.get(
    `/surveys/batches/${batchId}/results/${contractorUid}/parcels/${encodeURIComponent(dkbm)}/boundary`
  );
}

export function saveParcelBoundary(batchId, contractorUid, dkbm, payload) {
  return http.put(
    `/surveys/batches/${batchId}/results/${contractorUid}/parcels/${encodeURIComponent(dkbm)}/boundary`,
    payload
  );
}

export function generateSurveyRequest(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/generate-request`, payload);
}

// ── 合同信息 ──────────────────────────────────────────

export function fetchSurveyContract(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/contract`);
}

// 该承包方的合同清单（现行延包合同 + 历史合同 + 上次承包合同）
export function fetchSurveyContracts(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/contracts`);
}

// 指定合同的明细与渲染 HTML（历史合同也能查看）
export function fetchSurveyContractDetail(batchId, contractorUid, cbhtbm) {
  return http.get(
    `/surveys/batches/${batchId}/results/${contractorUid}/contracts/${encodeURIComponent(cbhtbm)}`,
    { timeout: 30000 }
  );
}

// 按新的调查信息生成延包合同（生成后上次合同置为历史）
export function generateSurveyContract(batchId, contractorUid, payload) {
  return http.post(
    `/surveys/batches/${batchId}/results/${contractorUid}/contract/generate`,
    payload || {}
  );
}

// 承包合同管理：批次内各承包户的合同关键信息列表（分页）
export function fetchBatchContractOverview(batchId, params) {
  return http.get(`/surveys/batches/${batchId}/contract-overview`, { params });
}

// ── 登记（延包）申请书（集体 / 单户） ─────────────────

// 打印《集体登记申请书》（返回渲染好的 HTML）
export function fetchCollectiveApplication(batchId) {
  return http.get(`/surveys/batches/${batchId}/collective-application`);
}

// 导出《集体登记申请书》Word
export function exportCollectiveApplicationDocx(batchId) {
  return http.post(`/surveys/batches/${batchId}/collective-application/export-docx`, null, {
    responseType: "blob",
  });
}

// 打印《单户登记申请书》（第二轮土地承包到期后再延长三十年登记申请表）
export function fetchHouseholdApplication(batchId, contractorUid) {
  return http.get(
    `/surveys/batches/${batchId}/results/${contractorUid}/household-application`
  );
}

// 导出《单户登记申请书》Word（config 可覆盖 timeout 等，批量下载逐户调用时放宽超时）
export function exportHouseholdApplicationDocx(batchId, contractorUid, config = {}) {
  return http.post(
    `/surveys/batches/${batchId}/results/${contractorUid}/household-application/export-docx`,
    null,
    { responseType: "blob", ...config }
  );
}

export function fetchSurveyPlotSketchMap(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/plot-sketch-map`, {
    // Rendering includes parcel geometry and nearby-parcel lookup, which can
    // legitimately take longer than the shared 10-second request timeout.
    timeout: 30000,
  });
}

export function printSurveyContract(batchId, contractorUid, cbhtbm) {
  return http.post(
    `/surveys/batches/${batchId}/results/${contractorUid}/contract/print`,
    cbhtbm ? { cbhtbm } : {}
  );
}

// 导出现行延包合同 Word（未生成延包合同时后端 404，批量导出据此逐户提示）
export function exportSurveyContractDocx(batchId, contractorUid, config = {}) {
  return http.post(
    `/surveys/batches/${batchId}/results/${contractorUid}/contract/export-docx`,
    null,
    { responseType: "blob", ...config }
  );
}

export function fetchSurveyRegistrationApplication(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/registration-application`);
}

export function fetchCadastralSurvey(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/cadastral-survey`, {
    // 一户一整套（封面 + 发包方 + 承包方 + 每地块两表），地块多时渲染较慢。
    timeout: 60000,
  });
}

// ── 调查操作 ──────────────────────────────────────────

export function changeHouseholdHead(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/change-head`, payload);
}

export function maintainSurveyMembers(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/maintain-members`, payload);
}

export function deregisterContractor(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/deregister`, payload);
}

export function rollbackDeregisteredContractor(batchId, contractorUid) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/rollback-deregister`);
}

export function addSurveyParcel(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/add-parcel`, payload);
}

export function splitSurveyParcel(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/split-parcel`, payload);
}

export function swapSurveyParcels(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/swap-parcels`, payload);
}

export function removeSurveyParcel(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/remove-parcel`, payload);
}

export function splitSurveyHousehold(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/split-household`, payload);
}

export function rollbackSplitSurveyHousehold(batchId, contractorUid) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/split-household/rollback`);
}

export function rollbackMergeSurveyHousehold(batchId, contractorUid) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/merge-household/rollback`);
}

export function mergeSurveyHousehold(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/merge-household`, payload);
}

// ── 两张摸底表（2026-10-09 礼泉试点；2026-10-10 简化）──────────────────
// 摸底数据读写随调查结果（updateSurveyResult / fetchSurveyResult）走：
// familyMembers[*].sheet。这里只保留两个打印入口。

/** 返回打印 HTML 字符串（Response data）。 */
export function printLandChangeSheet(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/land-change-sheet/print`, {
    timeout: 60000,
  });
}

export function printMemberChangeSheet(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/member-change-sheet/print`, {
    timeout: 60000,
  });
}
