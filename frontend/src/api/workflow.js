import http from "./http";

export function fetchWorkflowDefinitions() {
  return http.get("/workflow-definitions");
}

export function fetchWorkflowDefinition(key) {
  return http.get(`/workflow-definitions/${key}`);
}

export function validateWorkflowDefinition(content) {
  return http.post("/workflow-definitions/validate", { content });
}

export function saveWorkflowDefinition(key, payload) {
  return http.put(`/workflow-definitions/${key}`, payload);
}

export function fetchWorkflowVersions(key) {
  return http.get(`/workflow-definitions/${key}/versions`);
}

export function publishWorkflowDefinition(key, payload) {
  return http.post(`/workflow-definitions/${key}/publish`, payload);
}

export function activateWorkflowDefinition(key, versionId) {
  return http.post(`/workflow-definitions/${key}/activate`, { versionId });
}
