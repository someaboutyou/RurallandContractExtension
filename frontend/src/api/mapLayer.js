import http from "./http";

export function fetchMapLayers(params) {
  return http.get("/map-layers", { params });
}

export function createMapLayer(payload) {
  return http.post("/map-layers", payload);
}

export function updateMapLayer(id, payload) {
  return http.put(`/map-layers/${id}`, payload);
}

export function deleteMapLayer(id) {
  return http.delete(`/map-layers/${id}`);
}

export function validateMapLayerService(params) {
  return http.get("/map-layers/validate", { params });
}
