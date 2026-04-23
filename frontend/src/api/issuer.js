import http from "./http";

export function fetchIssuers(params) {
  return http.get("/issuers", { params });
}

export function createIssuer(payload) {
  return http.post("/issuers", payload);
}

export function updateIssuer(id, payload) {
  return http.put(`/issuers/${id}`, payload);
}

export function deleteIssuer(id) {
  return http.delete(`/issuers/${id}`);
}
