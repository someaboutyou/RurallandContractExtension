/**
 * 定位封装：优先走 Capacitor 原生定位，浏览器打开时兜底 navigator.geolocation。
 *
 * ⚠️ 坐标系（最容易踩的坑）
 * 项目地图与地块数据用的是 **EPSG:4326 / EPSG:3857（WGS84 系）**，
 * Capacitor Geolocation 返回的正是 WGS84 经纬度 ⇒ **可直接使用，无需转换**。
 *
 * 反过来要注意：如果哪天改成在微信里跑（JSSDK `wx.getLocation`），它默认返回的是
 * **GCJ-02（火星坐标）**，与 WGS84 在中国大陆相差 50~700 米 —— 那时必须显式传
 * `type: "wgs84"`，否则调查员点一下会定位到隔壁村。
 *
 * ⚠️ 浏览器兜底路径要求「安全上下文」：`http://` 的非 localhost 源会被浏览器
 * 直接禁用定位 API（`window.isSecureContext === false`）。原生 App 不受此限制，
 * 这也是套壳相比纯 H5 的一个实打实的优势。
 */

import { Capacitor } from "@capacitor/core";

/** 当前是否跑在 Capacitor 原生壳里（Android/iOS），而不是普通浏览器。 */
export function isNativePlatform() {
  return Capacitor.isNativePlatform();
}

function describeGeoError(error) {
  switch (error?.code) {
    case 1:
      return "定位权限被拒绝，请在系统设置中允许本应用获取位置信息";
    case 2:
      return "无法获取位置信息（卫星信号弱或定位服务不可用）";
    case 3:
      return "定位超时，请到开阔处重试";
    default:
      return error?.message || "定位失败";
  }
}

/**
 * 取当前位置。
 * @param {{ enableHighAccuracy?: boolean, timeout?: number, maximumAge?: number }} options
 * @returns {Promise<{ longitude: number, latitude: number, accuracy: number, timestamp: number, source: "native"|"web" }>}
 */
export async function getCurrentPosition(options = {}) {
  const {
    enableHighAccuracy = true,
    timeout = 15000,
    maximumAge = 0,
  } = options;

  if (isNativePlatform()) {
    const { Geolocation } = await import("@capacitor/geolocation");

    const current = await Geolocation.checkPermissions();
    if (current.location !== "granted") {
      const requested = await Geolocation.requestPermissions();
      if (requested.location !== "granted") {
        throw new Error("定位权限被拒绝，请在系统设置中允许本应用获取位置信息");
      }
    }

    const position = await Geolocation.getCurrentPosition({
      enableHighAccuracy,
      timeout,
      maximumAge,
    });

    return {
      longitude: position.coords.longitude,
      latitude: position.coords.latitude,
      accuracy: position.coords.accuracy,
      timestamp: position.timestamp,
      source: "native",
    };
  }

  // ── 浏览器 / H5 兜底 ────────────────────────────────
  if (!("geolocation" in navigator)) {
    throw new Error("当前环境不支持定位");
  }
  if (!window.isSecureContext) {
    throw new Error(
      "当前页面不是安全上下文（需要 HTTPS），浏览器已禁用定位能力。请改用 Android App，或为站点配置 HTTPS。",
    );
  }

  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          longitude: position.coords.longitude,
          latitude: position.coords.latitude,
          accuracy: position.coords.accuracy,
          timestamp: position.timestamp,
          source: "web",
        }),
      (error) => reject(new Error(describeGeoError(error))),
      { enableHighAccuracy, timeout, maximumAge },
    );
  });
}

/**
 * 连续监听位置变化，返回取消函数。用于"边走边显示当前位置"这类场景。
 * @param {(position: { longitude: number, latitude: number, accuracy: number }) => void} onUpdate
 * @param {{ enableHighAccuracy?: boolean, timeout?: number }} [options]
 * @returns {Promise<() => void>} 调用返回的函数即可停止监听
 */
export async function watchPosition(onUpdate, options = {}) {
  const { enableHighAccuracy = true, timeout = 15000 } = options;

  if (isNativePlatform()) {
    const { Geolocation } = await import("@capacitor/geolocation");
    const handle = await Geolocation.watchPosition(
      { enableHighAccuracy, timeout },
      (position, error) => {
        if (error || !position) return;
        onUpdate({
          longitude: position.coords.longitude,
          latitude: position.coords.latitude,
          accuracy: position.coords.accuracy,
        });
      },
    );
    return () => Geolocation.clearWatch({ id: handle });
  }

  if (!("geolocation" in navigator) || !window.isSecureContext) {
    throw new Error("当前环境不支持连续定位（需要 HTTPS 安全上下文）");
  }

  const watchId = navigator.geolocation.watchPosition(
    (position) =>
      onUpdate({
        longitude: position.coords.longitude,
        latitude: position.coords.latitude,
        accuracy: position.coords.accuracy,
      }),
    () => {},
    { enableHighAccuracy, timeout },
  );
  return () => navigator.geolocation.clearWatch(watchId);
}

/**
 * 精度提示文案。手机 GPS 精度通常 3~10 米，**不能用于采集正式界址点坐标**
 * （确权要求厘米级，PC 端用 RTK/GNSS）。这里只做"找到地块/图上快速定位"的辅助。
 * @param {number} accuracy 米
 */
export function describeAccuracy(accuracy) {
  if (!Number.isFinite(accuracy)) return "精度未知";
  if (accuracy <= 10) return `定位精度约 ${accuracy.toFixed(0)} 米（较好）`;
  if (accuracy <= 30) return `定位精度约 ${accuracy.toFixed(0)} 米（一般）`;
  return `定位精度约 ${accuracy.toFixed(0)} 米（偏差较大，仅供参考）`;
}
