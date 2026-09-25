import http from "./http";

export function fetchContractors(params) {
  return http.get("/contractors", { params });
}

export function fetchContractorDetail(code) {
  return http.get(`/contractors/${code}`);
}

/**
 * 批量打印地籍调查表：按筛选条件分页取承包方，服务端逐户渲染整套表。
 * 返回 `{ page, pageSize, total, contractorCount, hasMore, renderedHtml }`；
 * 一个村可达上千户，调用方需按页取数、自行拼接到同一个打印窗口。
 */
export function printCadastralSurveys(params) {
  return http.get("/contractors/cadastral-survey", {
    params,
    // 一页 50 户的整套表格渲染可能耗时数十秒。
    timeout: 300000,
  });
}

/**
 * 批量导出《地籍调查表》Word：创建后台导出任务，立即返回 `{ taskId }`。
 * 之后用 `fetchCadastralExportProgress` 轮询进度，完成后用
 * `fetchCadastralExportArchive` 取 zip。
 */
export function startCadastralExport(payload) {
  return http.post("/contractors/cadastral-survey/export", payload);
}

export function fetchCadastralExportProgress(taskId) {
  return http.get(`/contractors/cadastral-survey/export/${taskId}`);
}

export function fetchCadastralExportArchive(taskId) {
  return http.get(`/contractors/cadastral-survey/export/${taskId}/download`, {
    responseType: "blob",
    timeout: 300000,
  });
}

/** 单户《地籍调查表》Word 下载，返回 blob 响应。 */
export function fetchCadastralSurveyDocx(code, params) {
  return http.get(`/contractors/${code}/cadastral-survey.docx`, {
    params,
    responseType: "blob",
    timeout: 300000,
  });
}

export function createContractor(payload) {
  return http.post("/contractors", payload);
}

export function updateContractor(code, payload) {
  return http.put(`/contractors/${code}`, payload);
}

export function deleteContractor(code) {
  return http.delete(`/contractors/${code}`);
}
