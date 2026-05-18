import http from "./http";

export function fetchContractTemplate() {
  return http.get("/contract-templates/contract");
}

export function updateContractTemplate(payload) {
  return http.put("/contract-templates/contract", payload);
}

export function previewContractTemplate(payload) {
  return http.post("/contract-templates/contract/preview", payload);
}
