<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">RL</div>
        <div>
          <div class="brand-title">农村承包经营权</div>
          <div class="brand-subtitle">一体化平台</div>
        </div>
      </div>

      <nav class="nav">
        <RouterLink v-for="item in visibleNavItems" :key="item.to" class="nav-link" :to="item.to">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>

    <main class="main">
      <header class="header">
        <div class="header-bar">
          <div>
            <div class="page-title">农村承包经营权平台</div>
            <div class="page-subtitle">已接入权限、审批流、标准业务表和 GIS 预留扩展</div>
          </div>

          <div class="user-panel">
            <div class="user-meta">
              <div class="user-name">{{ authStore.displayName }}</div>
              <div class="user-role">{{ authStore.user?.role || "未设置角色" }}</div>
            </div>
            <el-button plain type="success" @click="handleLogout">退出登录</el-button>
          </div>
        </div>
      </header>

      <section class="content">
        <RouterView />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "../stores/auth";

const router = useRouter();
const authStore = useAuthStore();

const navItems = [
  { to: "/dashboard", label: "工作台", permissions: ["dashboard.view"] },
  { to: "/users", label: "人员权限", permissions: ["users.view", "roles.view"] },
  { to: "/issuers", label: "发包方管理", permissions: ["issuers.view"] },
  { to: "/contractors", label: "承包方管理", permissions: ["contractors.view"] },
  { to: "/requests", label: "业务申请", permissions: ["requests.view"] },
  { to: "/request-attachment-templates", label: "材料模板", permissions: ["requests.manage"] },
  { to: "/workflows", label: "流程设计", permissions: ["roles.manage"] },
];

const visibleNavItems = computed(() => navItems.filter((item) => authStore.hasAnyPermission(item.permissions)));

function handleLogout() {
  authStore.logout();
  router.push({ name: "login" });
}
</script>
