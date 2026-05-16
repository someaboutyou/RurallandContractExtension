<template>
  <div class="shell" :class="{ 'is-map-page': isMapPage }" :style="themeStyle">
    <header class="app-topbar">
      <div class="app-topbar-inner">
        <RouterLink to="/gis" class="brand">
          <div>
            <div class="brand-title">农村承包经营权</div>
            <div class="brand-subtitle">一体化平台</div>
          </div>
        </RouterLink>

        <nav class="primary-nav" aria-label="一级菜单">
          <template v-for="item in visibleNavItems" :key="item.key">
            <RouterLink
              v-if="!item.children?.length"
              :to="item.to"
              class="primary-nav-item"
              :class="{ 'is-active': isActive(item.to) }"
            >
              {{ item.label }}
            </RouterLink>
            <RouterLink
              v-else
              :to="firstChildPath(item)"
              class="primary-nav-item"
              :class="{ 'is-active': isGroupActive(item) }"
            >
              {{ item.label }}
            </RouterLink>
          </template>
        </nav>

        <div class="user-panel">
          <el-dropdown trigger="click" popper-class="topbar-dropdown" @command="handleSettingsCommand">
            <button type="button" class="topbar-icon-button" aria-label="系统设置">
              <el-icon aria-hidden="true"><Setting /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="item in systemNavItems"
                  :key="item.to"
                  :command="item.to"
                  :class="{ 'is-current': isActive(item.to) }"
                >
                  {{ item.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-dropdown trigger="click" popper-class="profile-dropdown" @command="handleUserCommand">
            <button type="button" class="avatar-button" aria-label="用户信息">
              <span class="avatar-button-text">{{ userInitial }}</span>
            </button>
            <template #dropdown>
              <div class="profile-card">
                <div class="profile-card-avatar">{{ userInitial }}</div>
                <div class="profile-card-main">
                  <div class="profile-card-name">{{ authStore.displayName }}</div>
                  <div class="profile-card-role">{{ authStore.user?.role || "未设置角色" }}</div>
                </div>
              </div>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div class="secondary-nav-row" :class="{ 'is-empty': !secondaryNavItems.length }">
        <nav v-if="secondaryNavItems.length" class="secondary-nav" aria-label="二级菜单">
          <RouterLink
            v-for="child in secondaryNavItems"
            :key="child.to"
            :to="child.to"
            class="secondary-nav-item"
            :class="{ 'is-active': isActive(child.to) }"
          >
            {{ child.label }}
          </RouterLink>
        </nav>
      </div>
    </header>

    <main class="main">
      <section class="content">
        <RouterView />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Setting } from "@element-plus/icons-vue";
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
const contentTheme = ref(null);

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
      { to: "/dictionaries", label: "字典管理", permissions: ["dictionaries.view"] },
      { to: "/regions", label: "区域管理", permissions: ["regions.view", "regions.manage"] },
      { to: "/workflows", label: "流程设计", permissions: ["roles.manage"] },
      { to: "/layers", label: "图层管理", permissions: ["layers.manage"] },
      { to: "/request-attachment-templates", label: "流程附件", permissions: ["requests.manage"] },
    ],
  },
];

const visibleNavItems = computed(() =>
  navItems
    .map((item) => {
      if (item.children?.length) {
        const children = item.children.filter((child) => authStore.hasAnyPermission(child.permissions));
        return { ...item, children };
      }
      return item;
    })
    .filter((item) => item.key !== "system")
    .filter((item) => (item.children?.length ? item.children.length > 0 : authStore.hasAnyPermission(item.permissions))),
);

const systemNavItems = computed(() => {
  const systemItem = navItems.find((item) => item.key === "system");
  return (systemItem?.children || []).filter((child) => authStore.hasAnyPermission(child.permissions));
});

const routeThemeMap = {
  gis: { topbarBg: "rgba(232, 238, 225, 0.96)", topbarAccent: "#5f7f44", topbarText: "#243325" },
  business: { topbarBg: "rgba(229, 238, 246, 0.96)", topbarAccent: "#2f70a2", topbarText: "#213447" },
  "data-center": { topbarBg: "rgba(225, 239, 238, 0.96)", topbarAccent: "#2a6f68", topbarText: "#203b3a" },
  "data-viz": { topbarBg: "rgba(228, 235, 247, 0.96)", topbarAccent: "#355f9f", topbarText: "#22314b" },
  archives: { topbarBg: "rgba(240, 234, 222, 0.96)", topbarAccent: "#7b643f", topbarText: "#3f3528" },
  system: { topbarBg: "rgba(232, 236, 242, 0.96)", topbarAccent: "#4a5c77", topbarText: "#273242" },
};

const activeTopItem = computed(() =>
  visibleNavItems.value.find((item) => (item.children?.length ? isGroupActive(item) : isActive(item.to))) ||
  visibleNavItems.value[0] ||
  null,
);

const secondaryNavItems = computed(() => activeTopItem.value?.children || []);
const isMapPage = computed(() => route.path === "/gis");
const userInitial = computed(() => (authStore.displayName || "用").trim().slice(0, 1).toUpperCase());

const themeStyle = computed(() => {
  const theme = contentTheme.value || routeThemeMap[activeTopItem.value?.key] || routeThemeMap.system;
  return {
    "--topbar-bg": theme.topbarBg,
    "--topbar-accent": theme.topbarAccent,
    "--topbar-text": theme.topbarText,
  };
});

watch(
  () => route.path,
  () => {
    contentTheme.value = null;
  },
);

function isActive(targetPath) {
  return route.path === targetPath;
}

function isGroupActive(item) {
  return item.children?.some((child) => isActive(child.to));
}

function firstChildPath(item) {
  return item.children?.[0]?.to || item.to || "/";
}

function handleThemeChange(event) {
  if (route.path !== "/gis") return;
  contentTheme.value = event.detail || null;
}

function handleSettingsCommand(path) {
  if (path) {
    router.push(path);
  }
}

function handleUserCommand(command) {
  if (command === "logout") {
    handleLogout();
  }
}

onMounted(() => {
  window.addEventListener("app-theme-change", handleThemeChange);
});

onBeforeUnmount(() => {
  window.removeEventListener("app-theme-change", handleThemeChange);
});

function handleLogout() {
  authStore.logout();
  router.push({ name: "login" });
}
</script>
