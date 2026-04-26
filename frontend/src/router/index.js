import { createRouter, createWebHistory } from "vue-router";

import AppLayout from "../layout/AppLayout.vue";
import pinia from "../stores";
import { useAuthStore } from "../stores/auth";

const LoginView = () => import("../views/LoginView.vue");
const DashboardView = () => import("../views/DashboardView.vue");
const DataCenterView = () => import("../views/DataCenterView.vue");
const ArchiveView = () => import("../views/ArchiveView.vue");
const LayerManagementView = () => import("../views/LayerManagementView.vue");
const UserView = () => import("../views/UserView.vue");
const IssuerView = () => import("../views/IssuerView.vue");
const ContractorView = () => import("../views/ContractorView.vue");
const GisView = () => import("../views/GisView.vue");
const RequestView = () => import("../views/RequestView.vue");
const RequestAttachmentTemplateView = () => import("../views/RequestAttachmentTemplateView.vue");
const WorkflowDesignerView = () => import("../views/WorkflowDesignerView.vue");

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
  { path: "requests", name: "requests", component: RequestView, meta: { requiresAuth: true, permissions: REQUEST_MODULE_PERMISSIONS } },
  {
    path: "data-center",
    name: "data-center",
    component: DataCenterView,
    meta: { requiresAuth: true, permissions: ["issuers.view", "contractors.view", ...REQUEST_MODULE_PERMISSIONS] },
  },
  { path: "dashboard", name: "dashboard", component: DashboardView, meta: { requiresAuth: true, permissions: ["dashboard.view"] } },
  {
    path: "archives",
    name: "archives",
    component: ArchiveView,
    meta: { requiresAuth: true, permissions: [...REQUEST_MODULE_PERMISSIONS, "users.view", "roles.view"] },
  },
  { path: "users", name: "users", component: UserView, meta: { requiresAuth: true, permissions: ["users.view", "roles.view"] } },
  { path: "workflows", name: "workflows", component: WorkflowDesignerView, meta: { requiresAuth: true, permissions: ["roles.manage"] } },
  { path: "layers", name: "layers", component: LayerManagementView, meta: { requiresAuth: true, permissions: ["layers.manage"] } },
  {
    path: "request-attachment-templates",
    name: "request-attachment-templates",
    component: RequestAttachmentTemplateView,
    meta: { requiresAuth: true, permissions: ["requests.manage"] },
  },
];

const routes = [
  {
    path: "/login",
    name: "login",
    component: LoginView,
    meta: { requiresAuth: false },
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

function getFirstAllowedRoute(authStore) {
  const match = appChildren.find((item) => !item.meta?.permissions || authStore.hasAnyPermission(item.meta.permissions));
  return match?.name || "login";
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia);
  await authStore.bootstrap();

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }

  if (to.name === "login" && authStore.isAuthenticated) {
    return { name: getFirstAllowedRoute(authStore) };
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
