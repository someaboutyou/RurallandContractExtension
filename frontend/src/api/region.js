import http from "./http";

export function fetchRegions(level) {
  return http.get("/regions", {
    params: level ? { level } : undefined,
  });
}

export function fetchRegionTree(level, options = {}) {
  const params = {};
  if (level) {
    params.level = level;
  }
  if (options.includeGroups) {
    params.include_groups = true;
  }
  return http.get("/regions/tree", {
    params: Object.keys(params).length ? params : undefined,
  });
}

export function createRegion(payload) {
  return http.post("/regions", payload);
}

export function updateRegion(id, payload) {
  return http.put(`/regions/${id}`, payload);
}

export function deleteRegion(id) {
  return http.delete(`/regions/${id}`);
}
