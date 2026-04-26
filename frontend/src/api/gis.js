import http from "./http";

export function searchGisBusiness(params) {
  return http.get("/gis/search", { params });
}

export function validateMapLayerService(params) {
  return http.get("/map-layers/validate", { params });
}
