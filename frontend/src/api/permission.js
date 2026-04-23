import http from "./http";

export function fetchPermissions() {
  return http.get("/permissions");
}
