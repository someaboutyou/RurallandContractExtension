import http from "./http";

export function fetchSurveyBatches(params) {
  return http.get("/surveys/batches", { params });
}

export function createSurveyBatch(payload) {
  return http.post("/surveys/batches", payload);
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

export function deleteSurveyAttachment(id) {
  return http.delete(`/surveys/attachments/${id}`);
}

export function fetchSurveyParcels(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/parcels`);
}

export function generateSurveyRequest(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/generate-request`, payload);
}

// ── 合同信息 ──────────────────────────────────────────

export function fetchSurveyContract(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/contract`);
}

export function fetchSurveyPlotSketchMap(batchId, contractorUid) {
  return http.get(`/surveys/batches/${batchId}/results/${contractorUid}/plot-sketch-map`);
}

export function printSurveyContract(batchId, contractorUid) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/contract/print`);
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

export function mergeSurveyHousehold(batchId, contractorUid, payload) {
  return http.post(`/surveys/batches/${batchId}/results/${contractorUid}/merge-household`, payload);
}
