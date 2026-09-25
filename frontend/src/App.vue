<template>
  <RouterView />
  <!-- 授权提醒：PC 与移动端用不同实现 ——
       PC 是 Element Plus 的 el-dialog；移动端换成 vant 的 Dialog
       （在手机上弹 PC 风格的对话框会布局错位）。
       移动端组件必须异步加载，否则 vant 会进 PC 端的入口 chunk。 -->
  <LicenseDialog v-if="!isMobileRoute" />
  <component :is="MobileLicenseNotice" v-else />
</template>

<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted } from "vue";
import { useRoute } from "vue-router";
import LicenseDialog from "./components/LicenseDialog.vue";
import { AUTO_CHECK_INTERVAL, useLicenseStore } from "./stores/license";

const route = useRoute();
const store = useLicenseStore();

const isMobileRoute = computed(() => route.path.startsWith("/m"));

/**
 * ⛔ 必须是 defineAsyncComponent：改成静态 import 会把 vant 的 JS 也并进入口 chunk，
 * 让 PC 端白下载一整套移动端组件库。它只在移动端路由下才真正加载。
 */
const MobileLicenseNotice = defineAsyncComponent(() =>
  import("./mobile/components/MobileLicenseNotice.vue"),
);

onMounted(() => {
  // 1. 程序启动即检查一次授权状态
  store.checkLicense();
  // 2. 之后每 10 分钟自动检查一次
  store.startAutoCheck(AUTO_CHECK_INTERVAL);
});

onBeforeUnmount(() => {
  store.stopAutoCheck();
});
</script>
