<script setup>
/**
 * 移动端授权 / 连接提示。
 *
 * ## 为什么不能用 PC 端的 LicenseDialog
 *
 * PC 端 `App.vue` 全局挂的是 `components/LicenseDialog.vue`（Element Plus 的 el-dialog），
 * 而移动端跑的是 vant —— 在手机上弹一个 PC 风格的对话框，布局是错位的。
 * 这里换成 vant 的 Dialog，只保留移动端真正需要的两个动作：重新检查 / 知道了。
 *
 * ## 为什么必须异步加载（`defineAsyncComponent` / 动态 import）
 *
 * 本文件 import 了 vant，若被 `App.vue` 静态引入，vant 的代码会进入口 chunk，
 * PC 端也会白下载。所以在 `App.vue` 里用动态引入，只在移动端路由下才加载。
 *
 * ## 关于「系统未授权」这个文案的来历（2026-09-22 实测确认）
 *
 * Capacitor 内置资源模式下，页面 origin 是 `http://localhost`，相对路径 `/api/v1/...`
 * 会被 WebView 本地服务器接管，而它对**不含扩展名**的路径一律回落 `index.html`
 * （`WebViewLocalServer.handleLocalRequest`），返回 **HTTP 200 + HTML**。
 * 于是授权检查"以为请求成功了"，把一段 HTML 当授权信息解析，`is_valid` 取到 undefined
 * ⇒ 弹窗落到「系统未授权」。**这其实是"没配后端地址"的误报**，不是真的授权问题。
 * 所以这里的文案必须把用户导向"检查服务器地址"，而不是"去申请授权"。
 */
import { watch } from "vue";
import { useLicenseStore } from "../../stores/license";
import { showDialog } from "../ui.js";
import "../styles.js";

const store = useLicenseStore();

/** 防止重入：store.dialogVisible 反复置 true 时只弹一个对话框 */
let busy = false;

watch(
  () => store.dialogVisible,
  (visible) => {
    if (visible) {
      open();
    }
  },
  { immediate: true },
);

async function open() {
  if (busy) return;
  busy = true;

  const { connectionError } = store;

  // 先把 store 的标志清掉：这样用户点「重新检查」若仍失败，
  // store 会把 dialogVisible 从 false 再置 true，watch 才能再次触发、重新提示。
  store.hideDialog();

  try {
    await showDialog({
      title: connectionError ? "无法连接服务器" : "系统未授权",
      message: connectionError
        ? `取不到后端数据（${store.statusText || "服务不可达"}）。\n\n请在登录页底部点击「后端地址」，确认服务器地址填写正确、后端服务已启动。`
        : `后端返回：${store.statusText || "未授权"}。\n\n请联系管理员完成授权后再使用。`,
      messageAlign: "left",
      confirmButtonText: "重新检查",
      cancelButtonText: "知道了",
      showCancelButton: true,
    });
    // 点「重新检查」：成功则 store 内部会 hideDialog，失败则会再次触发本组件
    store.checkLicense();
  } catch {
    // 点「知道了」：不再打扰；后续任意接口返回 403 时仍会重新弹出
  } finally {
    busy = false;
  }
}
</script>

<template>
  <!-- 纯逻辑组件，界面由函数式 Dialog 呈现 -->
  <span />
</template>
