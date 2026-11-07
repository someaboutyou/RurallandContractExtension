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
          <el-popover
            v-if="downloadUrl"
            placement="bottom-end"
            trigger="click"
            :width="232"
            popper-class="app-download-popover"
            @show="refreshDownloadUrl"
          >
            <template #reference>
              <button type="button" class="topbar-icon-button" aria-label="下载手机App">
                <el-icon aria-hidden="true"><Iphone /></el-icon>
              </button>
            </template>
            <div class="app-download-panel">
              <img v-if="downloadQrUrl" :src="downloadQrUrl" alt="下载App二维码" class="app-download-qr" />
              <div class="app-download-url" :title="downloadUrl">{{ downloadUrl }}</div>
              <div class="app-download-tip">手机扫码下载 App</div>
            </div>
          </el-popover>

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
                  :class="{ 'is-current': isActive(item.to) || isRoutePrefixActive(item.activePrefix) }"
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
import { Iphone, Setting } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";
import qrcode from "qrcode-generator";

import { fetchAppDownloadUrl } from "../api/system";
import { useAuthStore } from "../stores/auth";

const REQUEST_MODULE_PERMISSIONS = [
  "requests.manage",
  "requests.submit",
  "requests.review.village",
  "requests.review.town",
  "requests.review.county",
];

const PRINT_TEMPLATE_NAV_ITEM = {
  key: "print-templates",
  label: "打印模板管理",
  to: "/print-templates",
  activePrefix: "/print-templates",
  permissions: ["contract_templates.manage"],
};

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const contentTheme = ref(null);

// 右上角「下载App」二维码：地址来自字典 app_download（外网 ip/port/path）。
// ip 未配置时 url 为 null，整个入口隐藏（v-if），不占顶栏位置。
const downloadUrl = ref(null);
const downloadQrUrl = ref("");

function buildDownloadQr(url) {
  // qrcode-generator：typeNumber 0 = 按内容长度自动选版本；"M" 容错 15%，
  // 车间/野外打印或屏幕反光场景下仍可扫出。
  const qr = qrcode(0, "M");
  qr.addData(url);
  qr.make();
  downloadQrUrl.value = qr.createDataURL(8, 4);
}

async function refreshDownloadUrl() {
  try {
    const { data } = await fetchAppDownloadUrl();
    const url = data?.data?.url || null;
    if (url && url !== downloadUrl.value) {
      buildDownloadQr(url);
    }
    downloadUrl.value = url;
  } catch {
    // 接口失败不打断页面，入口保持当前状态（首次失败 = 隐藏）
  }
}

const navItems = [
  {
    key: "gis",
    label: "一张图",
    to: "/gis",
    permissions: ["dashboard.view"],
  },
  {
    key: "business",
    label: "建库中心",
    children: [
      { to: "/surveys", label: "调查批次管理", permissions: ["contractors.view"] },
      { to: "/issuers", label: "发包方管理", permissions: ["issuers.view"] },
      { to: "/survey-contractors", label: "承包方管理", permissions: ["contractors.view"] },
      { to: "/parcels", label: "承包地块管理", permissions: ["contractors.view"] },
      { to: "/survey-templates", label: "空白模板下载", permissions: ["contractors.view"] },
      { to: "/requests", label: "业务申请", permissions: REQUEST_MODULE_PERMISSIONS },
    ],
  },
  {
    key: "data-center",
    label: "数据中心",
    children: [
      { to: "/dc/issuers", label: "发包方管理", permissions: ["issuers.view"] },
      { to: "/dc/contractors", label: "承包方管理", permissions: ["contractors.view"] },
      { to: "/data-imports", label: "数据导入", permissions: ["contractors.view"] },
      { to: "/data-exports", label: "数据导出", permissions: ["contractors.view"] },
    ],
  },
  {
    key: "data-viz",
    label: "工作进展大屏",
    to: "/dashboard",
    // 与路由 meta 同源：入口可见性必须和接口/路由的准入判据一致，
    // 否则界面能点进去、进去却被踢回首页（体验事故）。
    permissions: ["dashboard.bigscreen"],
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
      PRINT_TEMPLATE_NAV_ITEM,
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

const secondaryNavItems = computed(() => {
  // 打印模板管理是单页（模板清单在页面左侧面板内），不显示任何二级菜单。
  if (isRoutePrefixActive(PRINT_TEMPLATE_NAV_ITEM.activePrefix)) {
    return [];
  }
  return activeTopItem.value?.children || [];
});
const isMapPage = computed(() => route.path === "/gis");
const userInitial = computed(() => (authStore.displayName || "用户").trim().slice(0, 1).toUpperCase());

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

function isRoutePrefixActive(prefix) {
  return Boolean(prefix) && (route.path === prefix || route.path.startsWith(`${prefix}/`));
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
  refreshDownloadUrl();
});

onBeforeUnmount(() => {
  window.removeEventListener("app-theme-change", handleThemeChange);
});

function handleLogout() {
  authStore.logout();
  router.push({ name: "login" });
}
</script>
