import http from "./http";

export function fetchLicenseStatus() {
  return http.get("/license/status", { timeout: 10000 });
}

export function fetchLicenseMachineCode() {
  return http.get("/license/machine-code", { timeout: 10000 });
}

export function reloadLicense() {
  return http.post("/license/reload", null, { timeout: 30000 });
}

export function uploadLicenseFile(formData) {
  return http.post("/license/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 60000,
  });
}
