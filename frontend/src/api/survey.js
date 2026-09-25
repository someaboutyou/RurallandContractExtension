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

export function finishSurveyBatch(batchId) {
  return http.post(`/surveys/batches/${batchId}/finish`);
}

export function exportSurveyResults(batchId, params) {
  return http.get(`/surveys/batches/${batchId}/export-results.zip`, { params, responseType: "blob" });
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

export function createSurveyIssuer(batchId, payload) {
  return http.post(`/surveys/batches/${batchId}/issuers`, payload);
}

export function fetchSurveyIssuer(batchId, issuerUid) {
  return http.get(`/surveys/batches/${batchId}/issuers/${issuerUid}`);
}

export function updateSurveyIssuer(batchId, issuerUid, payload) {
  return http.put(`/surveys/batches/${batchId}/issuers/${issuerUid}`, payload);
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

export function validateSurveyParcelGeometry(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/parcels/validate-geometry`, payload);
}

export function previewSplitSurveyParcel(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/parcels/preview-split`, payload);
}

export function generateNextSurveyParcelCode(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/parcels/next-code`);
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
