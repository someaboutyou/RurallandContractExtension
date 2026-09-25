import http from "./http";

export function fetchDashboardSummary() {
  return http.get("/dashboard/summary");
}

/**
 * 二轮延包工作进展大屏（全屏看板）。
 *
 * 权限独立于 `/summary`：需要 `dashboard.bigscreen`，目前只授予平台管理员。
 * 参数：batchId（不传=最新进行中批次）、trendDays（7-90）、topN（3-20）、regionLevel（town|village）。
 */
export function fetchBigscreen(params = {}) {
  return http.get("/dashboard/bigscreen", { params });
}
