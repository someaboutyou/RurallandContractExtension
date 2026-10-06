<template>
  <div class="m-shell">
    <van-nav-bar
      :title="title"
      :left-arrow="canGoBack"
      fixed
      placeholder
      safe-area-inset-top
      @click-left="onBack"
    />

    <div class="m-body">
      <!--
        keep-alive 只缓存「列表型」页面：返回/切 tab 时不重新挂载、不重复拉数据。
        ⛔ 详情/地块/附件页（MobileTaskDetailView / MobileParcelView /
        MobileAttachmentView）按路由参数取数，**绝不能进缓存**，否则换一户进来
        会展示上一户的旧数据 —— 它们不在 include 名单里即被排除。
        include 匹配的是 SFC 文件名推断出的组件名（Vue 3.2.34+），改名时同步这里。
      -->
      <router-view v-slot="{ Component }">
        <keep-alive :include="['MobileTaskListView', 'MobileProfileView']">
          <component :is="Component" />
        </keep-alive>
      </router-view>
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
  /* 导航栏默认 z-index 只有 1，压不住页面里 z-index:10 的吸顶头部（详情页 hero），
     抬到 20 保证层级：导航栏 > 吸顶头 > 内容（弹层/Toast 仍在 2000+ 之上） */
  --van-nav-bar-z-index: 20;
}

.m-body {
  min-height: calc(100vh - 46px);
}
</style>
