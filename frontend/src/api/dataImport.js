import http from "./http";

export function fetchImportBatches(params) {
  return http.get("/data-imports", { params });
}

export function createImportBatch(payload) {
  return http.post("/data-imports", payload);
}

export function downloadImportTemplate(fileType) {
  return http.get(`/data-imports/templates/${fileType}`, { responseType: "blob" });
}

export function downloadImportFieldNotes(fileType) {
  return http.get(`/data-imports/templates/${fileType}/field-notes`, { responseType: "blob" });
}

export function uploadImportFile(batchId, fileType, formData) {
  return http.post(`/data-imports/${batchId}/files`, formData, {
    params: { fileType },
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 60000,
  });
}

export function uploadImportArchive(batchId, formData) {
  return http.post(`/data-imports/${batchId}/archive`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 60000,
  });
}

export function uploadImportGdb(batchId, formData) {
  return http.post(`/data-imports/${batchId}/gdb`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 300000,
  });
}

export function fetchImportProgress(batchId) {
  return http.get(`/data-imports/${batchId}/progress`);
}

export function cancelImport(batchId) {
  return http.post(`/data-imports/${batchId}/cancel`);
}

export function rollbackImport(batchId) {
  return http.post(`/data-imports/${batchId}/rollback`);
}

export function fetchImportRows(batchId, params) {
  return http.get(`/data-imports/${batchId}/rows`, { params });
}

export function downloadFailedImportRows(batchId) {
  return http.get(`/data-imports/${batchId}/failed-rows.csv`, { responseType: "blob" });
}
