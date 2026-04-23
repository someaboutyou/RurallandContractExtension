import http from "./http";

export function fetchContractors(params) {
  return http.get("/contractors", { params });
}

export function fetchContractorDetail(code) {
  return http.get(`/contractors/${code}`);
}

export function createContractor(payload) {
  return http.post("/contractors", payload);
}

export function updateContractor(code, payload) {
  return http.put(`/contractors/${code}`, payload);
}

export function deleteContractor(code) {
  return http.delete(`/contractors/${code}`);
}
