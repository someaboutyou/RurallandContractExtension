import http from "./http";

/**
 * 部署级系统配置（只读）。
 * map-config 返回 { homeRegionCode, mapCenter: [lng, lat] | null }，
 * 地图页面用它做初始定位（部署初始化时按行政区划码固化，替代历史写死的泗洪坐标）。
 */
export function fetchMapConfig() {
  return http.get("/system/map-config");
}

/**
 * 手机 App 下载地址（外网）。
 * 返回 { url: string | null, configured: boolean }：
 * 地址由字典 app_download（ip / port / path）拼接，ip 未配置时 url 为 null，
 * 前端据此隐藏右上角的下载二维码入口。
 */
export function fetchAppDownloadUrl() {
  return http.get("/system/app-download-url");
}
