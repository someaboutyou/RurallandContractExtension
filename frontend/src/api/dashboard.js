import http from "./http";

export function fetchDashboardSummary() {
  return http.get("/dashboard/summary");
}
