import http from "./http";

export function fetchTenants() {
  return http.get("/tenants");
}
