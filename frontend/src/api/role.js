import http from "./http";

export function fetchRoles() {
  return http.get("/roles");
}

export function createRole(payload) {
  return http.post("/roles", payload);
}

export function updateRole(roleId, payload) {
  return http.put(`/roles/${roleId}`, payload);
}

export function deleteRole(roleId) {
  return http.delete(`/roles/${roleId}`);
}
