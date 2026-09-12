import axios from "axios";

const TOKEN_KEY = "rural_land_token";

const http = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
});

http.interceptors.request.use((config) => {
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
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }

    return Promise.reject(error);
  },
);

export default http;
