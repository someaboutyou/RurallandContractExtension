import http from "./http";

export function fetchIssuers(params) {
  return http.get("/issuers", { params });
}

export function fetchIssuerContractors(code) {
  return http.get(`/issuers/${code}/contractors`);
}

export function fetchIssuerParcels(code) {
  return http.get(`/issuers/${code}/parcels`);
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
