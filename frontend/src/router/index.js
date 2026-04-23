import { createRouter, createWebHistory } from "vue-router";

import AppLayout from "../layout/AppLayout.vue";
import pinia from "../stores";
import { useAuthStore } from "../stores/auth";

const LoginView = () => import("../views/LoginView.vue");
const DashboardView = () => import("../views/DashboardView.vue");
const UserView = () => import("../views/UserView.vue");
const IssuerView = () => import("../views/IssuerView.vue");
const ContractorView = () => import("../views/ContractorView.vue");
const RequestView = () => import("../views/RequestView.vue");
const RequestAttachmentTemplateView = () => import("../views/RequestAttachmentTemplateView.vue");
const WorkflowDesignerView = () => import("../views/WorkflowDesignerView.vue");

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
    redirect: "/dashboard",
    meta: { requiresAuth: true },
    children: [
      { path: "dashboard", name: "dashboard", component: DashboardView, meta: { requiresAuth: true, permissions: ["dashboard.view"] } },
      { path: "users", name: "users", component: UserView, meta: { requiresAuth: true, permissions: ["users.view", "roles.view"] } },
      { path: "issuers", name: "issuers", component: IssuerView, meta: { requiresAuth: true, permissions: ["issuers.view"] } },
      { path: "contractors", name: "contractors", component: ContractorView, meta: { requiresAuth: true, permissions: ["contractors.view"] } },
      { path: "requests", name: "requests", component: RequestView, meta: { requiresAuth: true, permissions: ["requests.view"] } },
      { path: "request-attachment-templates", name: "request-attachment-templates", component: RequestAttachmentTemplateView, meta: { requiresAuth: true, permissions: ["requests.manage"] } },
      { path: "workflows", name: "workflows", component: WorkflowDesignerView, meta: { requiresAuth: true, permissions: ["roles.manage"] } },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

function getFirstAllowedRoute(authStore) {
  const candidates = routes[1].children || [];
  const match = candidates.find((item) => !item.meta?.permissions || authStore.hasAnyPermission(item.meta.permissions));
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
