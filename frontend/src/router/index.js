import { createRouter, createWebHistory } from "vue-router";

import AppLayout from "../layout/AppLayout.vue";
import { mobileRoutes } from "../mobile/router";
import pinia from "../stores";
import { useAuthStore } from "../stores/auth";

const LoginView = () => import("../views/LoginView.vue");
const DashboardView = () => import("../views/DashboardView.vue");
const DataCenterView = () => import("../views/DataCenterView.vue");
const ArchiveView = () => import("../views/ArchiveView.vue");
const LayerManagementView = () => import("../views/LayerManagementView.vue");
const RegionManagementView = () => import("../views/RegionManagementView.vue");
const DictionaryManagementView = () => import("../views/DictionaryManagementView.vue");
const UserView = () => import("../views/UserView.vue");
const IssuerView = () => import("../views/IssuerView.vue");
const ContractorView = () => import("../views/ContractorView.vue");
const DataImportView = () => import("../views/DataImportView.vue");
const SurveyView = () => import("../views/SurveyView.vue");
const GisView = () => import("../views/GisView.vue");
const RequestView = () => import("../views/RequestView.vue");
const RequestAttachmentTemplateView = () => import("../views/RequestAttachmentTemplateView.vue");
const WorkflowDesignerView = () => import("../views/WorkflowDesignerView.vue");
const ContractTemplateManagementView = () => import("../views/ContractTemplateManagementView.vue");

const REQUEST_MODULE_PERMISSIONS = [
  "requests.manage",
  "requests.submit",
  "requests.review.village",
  "requests.review.town",
  "requests.review.county",
];

const appChildren = [
  { path: "gis", name: "gis", component: GisView, meta: { requiresAuth: true, permissions: ["dashboard.view"] } },
  { path: "issuers", name: "issuers", component: IssuerView, meta: { requiresAuth: true, permissions: ["issuers.view"] } },
  { path: "contractors", name: "contractors", component: ContractorView, meta: { requiresAuth: true, permissions: ["contractors.view"] } },
  { path: "data-imports", name: "data-imports", component: DataImportView, meta: { requiresAuth: true, permissions: ["contractors.view"] } },
  { path: "surveys", name: "surveys", component: SurveyView, meta: { requiresAuth: true, permissions: ["contractors.view"] } },
  { path: "requests", name: "requests", component: RequestView, meta: { requiresAuth: true, permissions: REQUEST_MODULE_PERMISSIONS } },
  {
    path: "data-center",
    name: "data-center",
    component: DataCenterView,
    meta: { requiresAuth: true, permissions: ["issuers.view", "contractors.view", ...REQUEST_MODULE_PERMISSIONS] },
  },
  {
    path: "archives",
    name: "archives",
    component: ArchiveView,
    meta: { requiresAuth: true, permissions: [...REQUEST_MODULE_PERMISSIONS, "users.view", "roles.view"] },
  },
  { path: "users", name: "users", component: UserView, meta: { requiresAuth: true, permissions: ["users.view", "roles.view"] } },
  {
    path: "dictionaries",
    name: "dictionaries",
    component: DictionaryManagementView,
    meta: { requiresAuth: true, permissions: ["dictionaries.view"] },
  },
  { path: "regions", name: "regions", component: RegionManagementView, meta: { requiresAuth: true, permissions: ["regions.view", "regions.manage"] } },
  { path: "workflows", name: "workflows", component: WorkflowDesignerView, meta: { requiresAuth: true, permissions: ["roles.manage"] } },
  { path: "layers", name: "layers", component: LayerManagementView, meta: { requiresAuth: true, permissions: ["layers.manage"] } },
  {
    path: "request-attachment-templates",
    name: "request-attachment-templates",
    component: RequestAttachmentTemplateView,
    meta: { requiresAuth: true, permissions: ["requests.manage"] },
  },
  {
    path: "contract-templates",
    name: "contract-templates",
    redirect: { name: "print-template-contract" },
    meta: { requiresAuth: true, permissions: ["contract_templates.manage"] },
  },
  {
    path: "print-templates",
    name: "print-templates",
    redirect: { name: "print-template-contract" },
    meta: { requiresAuth: true, permissions: ["contract_templates.manage"] },
  },
  {
    path: "print-templates/contract",
    name: "print-template-contract",
    component: ContractTemplateManagementView,
    meta: { requiresAuth: true, permissions: ["contract_templates.manage"], templateKey: "contract" },
  },
  {
    path: "print-templates/plot-sketch-map",
    name: "print-template-plot-sketch-map",
    component: ContractTemplateManagementView,
    meta: { requiresAuth: true, permissions: ["contract_templates.manage"], templateKey: "plot-sketch-map" },
  },
  {
    path: "print-templates/registration-application",
    name: "print-template-registration-application",
    component: ContractTemplateManagementView,
    meta: { requiresAuth: true, permissions: ["contract_templates.manage"], templateKey: "registration-application" },
  },
  {
    path: "print-templates/cadastral-survey",
    name: "print-template-cadastral-survey",
    component: ContractTemplateManagementView,
    meta: { requiresAuth: true, permissions: ["contract_templates.manage"], templateKey: "cadastral-survey" },
  },
  {
    path: "print-templates/issuer-survey",
    name: "print-template-issuer-survey",
    component: ContractTemplateManagementView,
    meta: { requiresAuth: true, permissions: ["contract_templates.manage"], templateKey: "issuer-survey" },
  },
];

const routes = [
  {
    path: "/login",
    name: "login",
    component: LoginView,
    meta: { requiresAuth: false },
  },
  // 移动端（/m/*，Capacitor 套壳入口）与 PC 端（/ 下 AppLayout 的 17 个页面）并存，
  // 各用各的布局；移动端路由表见 src/mobile/router.js。
  ...mobileRoutes,
  // 工作进展大屏是**独立全屏页**：刻意放在 AppLayout 之外，进入后不渲染平台导航，
  // 适合投屏和值班室长时间挂着。要回到平台用大屏右上角的「返回平台」。
  // 权限独立于 dashboard.view（dashboard.bigscreen）——目前只授予平台管理员，
  // 后续开放给其他角色只需在「角色权限」里勾选，不必改代码。
  {
    path: "/dashboard",
    name: "dashboard",
    component: DashboardView,
    meta: { requiresAuth: true, permissions: ["dashboard.bigscreen"] },
  },
  {
    path: "/",
    component: AppLayout,
    redirect: "/gis",
    meta: { requiresAuth: true },
    children: appChildren,
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

/**
 * 当前是否运行在 Capacitor 原生壳（Android APK）里。
 *
 * ① 首选 Capacitor 注入的全局对象：原生 WebView 里一定有 `window.Capacitor`，
 *    浏览器里没有（可选链短路 ⇒ undefined ⇒ false）。
 * ② 兜底看 origin：内置资源模式下页面 origin 是 `http://localhost`
 *    （`capacitor.config.json` 里 `androidScheme: "http"`），而 Vite dev server 是
 *    `http://localhost:5173`、PC 单端口部署是 `http://host:8000` —— 都带端口，不会误判。
 */
function isNativeShell() {
  if (window.Capacitor?.isNativePlatform?.()) return true;
  const { origin } = window.location;
  return (
    origin === "http://localhost" ||
    origin === "https://localhost" ||
    origin === "capacitor://localhost"
  );
}

function getFirstAllowedRoute(authStore) {
  const match = appChildren.find((item) => !item.meta?.permissions || authStore.hasAnyPermission(item.meta.permissions));
  return match?.name || "login";
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia);
  await authStore.bootstrap();

  // 移动端一律在 `/m/*` 下。
  const isMobileRoute = to.path.startsWith("/m");

  // ★ 原生壳入口分流（2026-09-22 补，用户实测发现）。
  //
  // APK 启动时 WebView 落在 `/`，会被下面的 PC 路由接走（`/` → `/gis` → 未登录 → `/login`），
  // 于是手机屏幕上出现的是 **PC 版登录页**：布局不适配，而且**找不到移动端才有的
  // 「后端地址」入口**（外业人员第一件事就是配服务器地址，这样等于功能不可见）。
  //
  // ⚠️ `/` 在路由表里配了 `redirect: "/gis"`，重定向先于守卫解析完成，
  // 所以守卫收到的 `to.path` 是 `/gis`，判据必须同时看 `to.redirectedFrom`。
  //
  // ⛔ 但**必须排除「已经在移动端区域」的目标**，否则会无限重定向：
  //    重定向链上的每一跳都会再进守卫一次，而 `redirectedFrom` 会**一直保留最初的 `/`**
  //    —— 我们 return `mobile-login` 后，那次 `/m/login` 的 `to.redirectedFrom` 仍是 `/`，
  //    条件再次成立 ⇒ 死循环（vue-router 以 `Infinite redirect in navigation guard` 中止，页面白屏）。
  //    已用 `runtime/.state/router_probe.mjs` 实测复现并验证修复。
  //
  // 只在**入口路径**上分流：PC 浏览器打开 `/` 行为不变；进入 `/m/*` 之后的普通导航不受影响。
  if (isNativeShell() && !isMobileRoute && (to.path === "/" || to.redirectedFrom?.path === "/")) {
    return { name: authStore.isAuthenticated ? "mobile-tasks" : "mobile-login" };
  }

  // 移动端未登录时跳移动端登录页，
  // 否则手机上会落到 PC 版登录页（布局不适配移动端）。

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return {
      name: isMobileRoute ? "mobile-login" : "login",
      query: { redirect: to.fullPath },
    };
  }

  if (to.name === "login" && authStore.isAuthenticated) {
    return { name: getFirstAllowedRoute(authStore) };
  }

  if (to.name === "mobile-login" && authStore.isAuthenticated) {
    return { name: "mobile-tasks" };
  }

  if (to.meta.permissions && !authStore.hasAnyPermission(to.meta.permissions)) {
    const fallbackName = getFirstAllowedRoute(authStore);
    if (fallbackName === "login") {
      authStore.logout();
      return { name: "login" };
    }
    return { name: fallbackName };
  }

  return true;
});

export default router;
