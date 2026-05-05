<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">RC</div>
        <div>
          <div class="brand-title">农村承包经营权</div>
          <div class="brand-subtitle">一体化平台 / GIS 协同</div>
        </div>
      </div>

      <nav class="nav nav-tree">
        <section v-for="item in visibleNavItems" :key="item.key" class="nav-tree-group">
          <button
            v-if="item.children?.length"
            type="button"
            class="nav-tree-parent"
            :class="{ 'is-expanded': isExpanded(item.key), 'is-active': isGroupActive(item) }"
            @click="toggleGroup(item.key)"
          >
            <span class="nav-tree-parent-main">{{ item.label }}</span>
            <span class="nav-tree-parent-arrow">{{ isExpanded(item.key) ? "▾" : "▸" }}</span>
          </button>

          <RouterLink
            v-else
            :to="item.to"
            class="nav-link nav-tree-leaf"
            :class="{ 'is-active': isActive(item.to) }"
          >
            <span class="nav-link-text">{{ item.label }}</span>
          </RouterLink>

          <div v-if="item.children?.length && isExpanded(item.key)" class="nav-tree-children">
            <RouterLink
              v-for="child in item.children"
              :key="child.to"
              :to="child.to"
              class="nav-link nav-tree-child"
              :class="{ 'is-active': isActive(child.to) }"
            >
              <span class="nav-link-text">{{ child.label }}</span>
            </RouterLink>
          </div>
        </section>
      </nav>
    </aside>

    <main class="main">
      <header class="header">
        <div class="header-bar">
          <div>
            <div class="page-title">农村承包经营权平台</div>
          </div>

          <div class="user-panel">
            <div class="user-meta">
              <div class="user-name">{{ authStore.displayName }}</div>
              <div class="user-role">{{ authStore.user?.role || "未设置角色" }}</div>
            </div>
            <el-button plain type="primary" @click="handleLogout">退出登录</el-button>
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
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "../stores/auth";

const REQUEST_MODULE_PERMISSIONS = [
  "requests.manage",
  "requests.submit",
  "requests.review.village",
  "requests.review.town",
  "requests.review.county",
];

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const navItems = [
  {
    key: "gis",
    label: "一张图",
    to: "/gis",
    permissions: ["dashboard.view"],
  },
  {
    key: "business",
    label: "业务办理",
    children: [
      { to: "/surveys", label: "串户调查成果", permissions: ["contractors.view"] },
      { to: "/requests", label: "业务申请", permissions: REQUEST_MODULE_PERMISSIONS },
    ],
  },
  {
    key: "data-center",
    label: "数据中心",
    children: [
      { to: "/issuers", label: "发包方管理", permissions: ["issuers.view"] },
      { to: "/contractors", label: "承包方管理", permissions: ["contractors.view"] },
      { to: "/data-imports", label: "数据导入", permissions: ["contractors.view"] },
    ],
  },
  {
    key: "data-viz",
    label: "数据可视化",
    to: "/dashboard",
    permissions: ["dashboard.view"],
  },
  {
    key: "archives",
    label: "档案管理",
    to: "/archives",
    permissions: [...REQUEST_MODULE_PERMISSIONS, "users.view", "roles.view"],
  },
  {
    key: "system",
    label: "系统管理",
    children: [
      { to: "/users", label: "人员权限", permissions: ["users.view", "roles.view"] },
      { to: "/regions", label: "区域管理", permissions: ["regions.view", "regions.manage"] },
      { to: "/workflows", label: "流程设计", permissions: ["roles.manage"] },
      { to: "/layers", label: "图层管理", permissions: ["layers.manage"] },
      { to: "/request-attachment-templates", label: "流程附件", permissions: ["requests.manage"] },
    ],
  },
];

const expandedGroups = ref(["business", "system", "data-center"]);

const visibleNavItems = computed(() =>
  navItems
    .map((item) => {
      if (item.children?.length) {
        const children = item.children.filter((child) => authStore.hasAnyPermission(child.permissions));
        return { ...item, children };
      }
      return item;
    })
    .filter((item) => (item.children?.length ? item.children.length > 0 : authStore.hasAnyPermission(item.permissions))),
);

watch(
  visibleNavItems,
  (items) => {
    const visibleKeys = new Set(items.filter((item) => item.children?.length).map((item) => item.key));
    expandedGroups.value = expandedGroups.value.filter((key) => visibleKeys.has(key));
    const activeGroup = items.find((item) => item.children?.some((child) => isActive(child.to)));
    if (activeGroup && !expandedGroups.value.includes(activeGroup.key)) {
      expandedGroups.value.push(activeGroup.key);
    }
  },
  { immediate: true },
);

function isActive(targetPath) {
  return route.path === targetPath;
}

function isGroupActive(item) {
  return item.children?.some((child) => isActive(child.to));
}

function isExpanded(key) {
  return expandedGroups.value.includes(key);
}

function toggleGroup(key) {
  if (isExpanded(key)) {
    expandedGroups.value = expandedGroups.value.filter((item) => item !== key);
    return;
  }
  expandedGroups.value = [...expandedGroups.value, key];
}

function handleLogout() {
  authStore.logout();
  router.push({ name: "login" });
}
</script>
