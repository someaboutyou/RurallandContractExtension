import http from "./http";

export function fetchUsers(params) {
  return http.get("/users", { params });
}

export function createUser(payload) {
  return http.post("/users", payload);
}

export function updateUser(userId, payload) {
  return http.put(`/users/${userId}`, payload);
}

export function resetUserPassword(userId, payload) {
  return http.post(`/users/${userId}/reset-password`, payload);
}

export function deleteUser(userId) {
  return http.delete(`/users/${userId}`);
}
