import axios from "axios";

import { resolveApiBase } from "./serverConfig";

const TOKEN_KEY = "rural_land_token";

/**
 * 当前页面是否运行在 Capacitor 原生壳（Android App）里。
 *
 * 判据与 router/index.js 的 isNativeShell() 保持同源，但不直接 import：
 * router → stores/auth → api/auth → api/http 是一条环，http.js 反向引 router
 * 会造成循环依赖，所以这里复制同一套判据（改口径必须两边同步改）。
 *
 * ⛔ 401 兜底跳转必须用它而不是只看 `location.pathname.startsWith("/m")`：
 * 冷启动时 WebView 落在 `/`，路由守卫 bootstrap() 会带旧 token 打 /auth/me，
 * token 过期 ⇒ 401 在 pathname 还是 `/`（未进入 /m/*）时到达 ⇒ 旧逻辑把手机
 * 硬跳到 PC 版 /login（用户实测"手机有时跳出电脑端登录界面"的根因）。
 */
function isNativeShellPage() {
  if (window.Capacitor?.isNativePlatform?.()) return true;
  const { origin } = window.location;
  return (
    origin === "http://localhost" ||
    origin === "https://localhost" ||
    origin === "capacitor://localhost"
  );
}

// baseURL 的来源与优先级见 `serverConfig.js`，简言之：
// - PC 端 / Capacitor「在线模式」（server.url 指向后端）→ 同源相对路径 `/api/v1`，天然免 CORS；
// - Capacitor「内置资源模式」→ 页面 origin 是 http://localhost，必须给绝对地址。
//   除了构建期注入 `VITE_API_BASE_URL`，用户在 App 内「服务器设置」里改的地址
//   （localStorage）优先级更高，改完立刻生效。
const http = axios.create({
  baseURL: resolveApiBase(),
  timeout: 10000,
});

http.interceptors.request.use((config) => {
  // 每次请求都重新解析，而不是只在模块加载时算一次：
  // 这样在「服务器设置」里改完地址后，无需重启 App 或重新登录即可生效。
  config.baseURL = resolveApiBase();

  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const body = error.response?.data;

    // 授权拦截：后端返回 403 + license_required
    if (status === 403 && body?.error === "license_required") {
      // 动态导入避免循环依赖
      import("../stores/license").then(({ useLicenseStore }) => {
        const store = useLicenseStore();
        store.onLicenseDenied(body.message || body.detail);
      });
      return Promise.reject(error);
    }

    // 未授权 / token 过期
    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem("rural_land_user");
      // 移动端（/m/*）必须回移动端登录页：跳到 PC 版 /login 在手机上是错位的布局，
      // 而且会把用户甩出套壳页面的预期路径。
      // ⛔ 判据不能只看 location.pathname：冷启动守卫 bootstrap() 的 /auth/me 401
      // 到达时 pathname 还是 `/`（导航尚未提交），按 pathname 判会误跳 PC 登录页。
      // 原生壳内一律回 /m/login；PC 浏览器再按 pathname 分流。
      const loginPath =
        isNativeShellPage() || window.location.pathname.startsWith("/m")
          ? "/m/login"
          : "/login";
      if (window.location.pathname !== loginPath) {
        window.location.href = loginPath;
      }
    }

    return Promise.reject(error);
  },
);

export default http;
