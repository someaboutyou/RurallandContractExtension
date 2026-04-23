import http from "./http";

export function fetchRequestAttachmentTemplates(params) {
  return http.get("/request-attachment-templates", { params });
}

export function createRequestAttachmentTemplate(payload) {
  return http.post("/request-attachment-templates", payload);
}

export function updateRequestAttachmentTemplate(id, payload) {
  return http.put(`/request-attachment-templates/${id}`, payload);
}

export function deleteRequestAttachmentTemplate(id) {
  return http.delete(`/request-attachment-templates/${id}`);
}
