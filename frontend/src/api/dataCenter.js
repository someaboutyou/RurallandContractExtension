import http from "./http";

// ── 数据中心：清单导入导出（无批次，区域/整库）+ 全库数据质检 ──────────────
// 建库中心同能力走 /issuers、/surveys（批次口径）；本模块一律区域口径（空=整库）。

// ── 数据质检 ──

/** 启动数据中心质检（regionCode 空=整库）。 */
export function startDataCenterQualityCheck(payload) {
  return http.post("/data-center/quality-checks", payload, { timeout: 30000 });
}

/** 轮询质检任务进度。 */
export function getDataCenterQualityCheckJob(jobId) {
  return http.get(`/data-center/quality-checks/jobs/${jobId}`);
}

/** 质检历史（batch_id=0 哨兵运行）。 */
export function fetchDataCenterQualityRuns(params) {
  return http.get("/data-center/quality-checks/runs", { params });
}

/** 一次质检运行的问题明细。 */
export function fetchDataCenterQualityRecords(runId, params) {
  return http.get(`/data-center/quality-checks/runs/${runId}/records`, { params });
}

/** 导出一次质检运行的问题明细 Excel。 */
export function exportDataCenterQualityRecords(runId, params) {
  return http.get(`/data-center/quality-checks/runs/${runId}/records/export`, {
    params,
    responseType: "blob",
    timeout: 120000,
  });
}

// ── 承包方清单导出（后台任务）──

/** 启动承包方清单导出（mode: single=整体 xls | group=按发包方分组 zip）。 */
export function startContractorListExportJob(payload) {
  return http.post("/data-center/contractor-list/export-jobs", payload, { timeout: 60000 });
}

export function getContractorListExportJob(jobId) {
  return http.get(`/data-center/contractor-list/export-jobs/${jobId}`);
}

export function downloadContractorListExportJob(jobId) {
  return http.get(`/data-center/contractor-list/export-jobs/${jobId}/download`, {
    responseType: "blob",
    timeout: 600000,
  });
}

// ── 承包方清单导入（后台任务）──

/** 校验承包方清单 Excel（只读预览）。 */
export function previewContractorList(formData) {
  return http.post("/data-center/contractor-list/preview", formData, { timeout: 120000 });
}

/** 启动导入任务（按承包方编号更新主表，不建新户）。 */
export function startContractorListImportJob(formData) {
  return http.post("/data-center/contractor-list/import-jobs", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
}

export function getContractorListImportJob(jobId) {
  return http.get(`/data-center/contractor-list/import-jobs/${jobId}`);
}
