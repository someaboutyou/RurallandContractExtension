import http from "./http";

export function fetchRequests(params) {
  return http.get("/requests", { params });
}

export function fetchRequestDetail(id) {
  return http.get(`/requests/${id}`);
}

export function fetchRequestWorkflowView(id) {
  return http.get(`/requests/${id}/workflow-view`);
}

export function fetchRequestWorkflowOptions() {
  return http.get("/request-workflow-mappings/options");
}

export function uploadRequestAttachment(id, formData) {
  return http.post(`/requests/${id}/attachments`, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
}

export function deleteRequestAttachment(id, attachmentId) {
  return http.delete(`/requests/${id}/attachments/${attachmentId}`);
}

export function downloadRequestAttachment(id, attachmentId) {
  return http.get(`/requests/${id}/attachments/${attachmentId}/download`, {
    responseType: "blob",
  });
}

export function createRequest(payload) {
  return http.post("/requests", payload);
}

export function updateRequest(id, payload) {
  return http.put(`/requests/${id}`, payload);
}

export function submitRequest(id) {
  return http.post(`/requests/${id}/submit`);
}

export function approveRequest(id, payload) {
  return http.post(`/requests/${id}/approve`, payload);
}

export function rejectRequest(id, payload) {
  return http.post(`/requests/${id}/reject`, payload);
}

export function deleteRequest(id) {
  return http.delete(`/requests/${id}`);
}
