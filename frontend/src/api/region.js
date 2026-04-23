import http from "./http";

export function fetchRegions(level) {
  return http.get("/regions", {
    params: level ? { level } : undefined,
  });
}
