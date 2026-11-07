import http from "./http";

export function fetchIssuers(params) {
  return http.get("/issuers", { params });
}

export function fetchIssuerContractors(code) {
  return http.get(`/issuers/${code}/contractors`);
}

export function fetchIssuerParcels(code) {
  return http.get(`/issuers/${code}/parcels`);
}

export function createIssuer(payload) {
  return http.post("/issuers", payload);
}

export function updateIssuer(id, payload) {
  return http.put(`/issuers/${id}`, payload);
}

export function deleteIssuer(id) {
  return http.delete(`/issuers/${id}`);
}

export function mergeIssuers(payload) {
  return http.post("/issuers/merge", payload);
}

/** 导出发包方清单 Excel（口径与页面查询一致）。 */
export function exportIssuerXls(params) {
  return http.get("/issuers/xls", {
    params,
    responseType: "blob",
    timeout: 120000,
  });
}

/** 校验发包方调查表 Excel。 */
export function previewIssuerXls(formData) {
  return http.post("/issuers/xls/preview", formData, { timeout: 120000 });
}

/** 导入发包方调查表 Excel。 */
export function importIssuerXls(formData) {
  return http.post("/issuers/xls/import", formData, { timeout: 300000 });
}

/** 单个发包方的《发包方调查表》Word。 */
export function exportIssuerSurveyDocx(code) {
  return http.get(`/issuers/${code}/survey-docx`, {
    responseType: "blob",
    timeout: 120000,
  });
}

/** 选中的发包方批量导出《发包方调查表》Word（单个 docx / 多个 zip）。 */
export function exportIssuerSurveyDocxBulk(payload) {
  return http.post("/issuers/export-docx", payload, {
    responseType: "blob",
    timeout: 300000,
  });
}

/** 按发包方（村组）导出《调查信息公示签字表》Excel（一个发包方一个 sheet）。 */
export function exportPublicityXls(payload) {
  return http.post("/issuers/publicity-xls", payload, {
    responseType: "blob",
    timeout: 300000,
  });
}

// ── 批量导出后台任务：创建 → 轮询进度 → 下载（kind: survey | publicity）──

/** 创建批量导出任务，立即返回 `{ taskId }`。 */
export function startIssuerExportJob(payload) {
  return http.post("/issuers/export-jobs", payload, { timeout: 60000 });
}

/** 轮询批量导出任务进度。 */
export function getIssuerExportJob(taskId) {
  return http.get(`/issuers/export-jobs/${taskId}`);
}

/** 下载批量导出任务产物（单个 docx/xls，多个 zip）。 */
export function downloadIssuerExportJob(taskId) {
  return http.get(`/issuers/export-jobs/${taskId}/download`, {
    responseType: "blob",
    timeout: 300000,
  });
}
