import http from "./http";

/**
 * 数据中心 → 数据导出
 * 与 dataImport.js 同约定：具名函数封装 http 调用，调用方读 .data。
 */

export function createDataExport(payload) {
  // 县级可达十几万户，生成 ZIP 可能要几十秒；http 实例默认 10s 会被掐断
  return http.post("/data-exports", payload, { timeout: 5 * 60 * 1000 });
}

export function fetchDataExports(params = {}) {
  return http.get("/data-exports", { params });
}

export function downloadDataExport(id) {
  return http.get(`/data-exports/${id}/download`, { responseType: "blob" });
}

export function deleteDataExport(id) {
  return http.delete(`/data-exports/${id}`);
}
