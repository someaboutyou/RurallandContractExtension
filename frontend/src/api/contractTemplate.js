import http from "./http";

export function fetchContractTemplate(templateKey = "contract") {
  return http.get(`/contract-templates/${templateKey}`);
}

export function updateContractTemplate(templateKey = "contract", payload) {
  return http.put(`/contract-templates/${templateKey}`, payload);
}

export function previewContractTemplate(templateKey = "contract", payload) {
  return http.post(`/contract-templates/${templateKey}/preview`, payload);
}
