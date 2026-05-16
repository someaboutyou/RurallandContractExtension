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

export function fetchGeoserverLayers(params) {
  return http.get("/map-layers/geoserver-layers", { params });
}

export function recalculateMapLayerBbox(id) {
  return http.post(`/map-layers/${id}/geoserver/recalculate-bbox`);
}

export function recalculateAllMapLayerBboxes() {
  return http.post("/map-layers/geoserver/recalculate-bbox");
}

export function seedMapLayerCache(id, payload) {
  return http.post(`/map-layers/${id}/geoserver/seed-cache`, payload);
}

export function seedMapLayerServiceCache(payload) {
  return http.post("/map-layers/geoserver/seed-cache", payload);
}
