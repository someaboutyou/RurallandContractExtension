<template>
  <div class="m-shell">
    <van-nav-bar
      :title="title"
      :left-arrow="canGoBack"
      fixed
      placeholder
      @click-left="onBack"
    />

    <div class="m-body">
      <router-view />
    </div>

    <van-tabbar v-if="showTabbar" route fixed placeholder>
      <van-tabbar-item to="/m/tasks" icon="todo-list-o">待调查</van-tabbar-item>
      <van-tabbar-item to="/m/profile" icon="user-o">我的</van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup>
/**
 * 移动端外壳：顶部标题栏 + 内容区 + 底部导航。
 *
 * 与 PC 端 `layout/AppLayout.vue` 并列，互不影响 —— 移动端路由都挂在 `/m/*` 下。
 * 因此 PC 端页面完全不会加载 vant 的样式与组件。
 */
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { VanNavBar, VanTabbar, VanTabbarItem } from "../ui.js";
// 样式统一走 ../styles.js（内部是动态 import），登录页与本文件共用同一份，不会重复打包。
// ⛔ 不要改回模块顶层的静态 `import "vant/lib/index.css"`：本文件有可能被 Rollup
// 内联进入口 chunk，届时 vant 全量样式（约 199KB）会被并进入口 CSS，
// **每个 PC 页面都会白下载一份移动端样式**（2026-09-22 实测：入口 CSS 一度涨到 260.9KB）。
import "../styles.js";

const route = useRoute();
const router = useRouter();

const title = computed(() => route.meta?.mobileTitle || "延包调查");
const showTabbar = computed(() => route.meta?.mobileTabbar !== false);
const canGoBack = computed(() => route.meta?.mobileBack !== false);

function onBack() {
  if (window.history.length > 1) {
    router.back();
  } else {
    router.replace({ name: "mobile-tasks" });
  }
}
</script>

<style scoped>
.m-shell {
  min-height: 100vh;
  background: #f7f8fa;
}

.m-body {
  min-height: calc(100vh - 46px);
}
</style>
