import http from "./http";

export function fetchRequestWorkflowMappings() {
  return http.get("/request-workflow-mappings");
}

export function createRequestWorkflowMapping(payload) {
  return http.post("/request-workflow-mappings", payload);
}

export function updateRequestWorkflowMapping(id, payload) {
  return http.put(`/request-workflow-mappings/${id}`, payload);
}

export function deleteRequestWorkflowMapping(id) {
  return http.delete(`/request-workflow-mappings/${id}`);
}
