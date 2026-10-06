<template>
  <div class="m-profile">
    <div class="m-profile__card">
      <div class="m-profile__avatar">{{ avatarText }}</div>
      <div class="m-profile__identity">
        <p class="m-profile__name">{{ authStore.displayName }}</p>
        <p class="m-profile__account">{{ authStore.user?.username || "—" }}</p>
      </div>
    </div>

    <van-cell-group inset title="运行环境">
      <van-cell title="载体" :value="runtimeLabel" />
      <van-cell title="页面来源" :value="originLabel" />
      <van-cell
        title="后端地址"
        :value="apiBaseLabel"
        :label="apiConfigured ? '' : '尚未设置，点此填写'"
        is-link
        @click="serverSettingVisible = true"
      />
      <van-cell title="定位能力" :value="locationLabel" />
    </van-cell-group>

    <van-cell-group inset title="账号">
      <van-cell title="权限项" :value="`${authStore.permissions.length} 项`" />
      <van-cell title="数据权限" :value="dataScopeLabel" />
    </van-cell-group>

    <van-cell-group inset title="版本">
      <van-cell title="Web 包版本" :value="bundleVersionLabel" />
      <van-cell title="App 版本" :value="nativeVersionLabel" />
      <van-cell
        title="检查更新"
        :value="updateHint"
        is-link
        @click="onCheckUpdate"
      />
    </van-cell-group>

    <van-cell-group inset title="诊断">
      <van-cell title="重新检测授权" is-link @click="onRecheckLicense" />
    </van-cell-group>

    <div class="m-profile__actions">
      <van-button round block plain type="danger" @click="onLogout">退出登录</van-button>
    </div>

    <p class="m-profile__hint">
      定位仅用于辅助查找地块，精度约 3~10 米；正式界址点坐标请在 PC 端维护。
    </p>

    <ServerSettingPopup v-model:show="serverSettingVisible" />
  </div>
</template>

<script setup>
/**
 * 「我的」页：账号信息、运行环境自检、退出登录。
 *
 * 「运行环境」几行是外业排障的抓手：
 * - 载体 / 页面来源 → 确认跑在 App 壳里还是浏览器里，页面是从 APK 还是服务器来的
 * - 后端地址 → **这是真正决定"能不能连上后端"的那一项**，点它可就地修改。
 *   注意别和「页面来源」混了：内置资源模式下页面来源恒为 http://localhost，
 *   与本机地址无关。
 * - 定位能力 → 提前暴露"浏览器打开且非 HTTPS"这类当场不可用的情况
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../../stores/auth";
import { isApiBaseConfigured, resolveApiBase } from "../../api/serverConfig";
import { markManualLogout } from "../session.js";
import { useLicenseStore } from "../../stores/license";
import ServerSettingPopup from "../components/ServerSettingPopup.vue";
import { isNativePlatform } from "../native/location.js";
import { getBundleVersion, checkForUpdates } from "../updater.js";
import {
  VanButton,
  VanCell,
  VanCellGroup,
  closeToast,
  showConfirmDialog,
  showLoadingToast,
  showToast,
} from "../ui.js";

const router = useRouter();
const authStore = useAuthStore();
const licenseStore = useLicenseStore();

const serverSettingVisible = ref(false);

const avatarText = computed(() => {
  const name = authStore.displayName || "";
  return name ? name.slice(-2) : "—";
});

const runtimeLabel = computed(() => (isNativePlatform() ? "Android App" : "浏览器 / H5"));
/** 页面自身的来源。内置资源模式下恒为 http://localhost —— 不是后端地址 */
const originLabel = computed(() => window.location.origin);
const apiBaseLabel = computed(() => resolveApiBase());
const apiConfigured = computed(() => isApiBaseConfigured());
const locationLabel = computed(() => {
  if (isNativePlatform()) return "原生定位（可用）";
  return window.isSecureContext ? "浏览器定位（可用）" : "不可用（需 HTTPS）";
});

const dataScopeLabel = computed(() => {
  const scope = authStore.user?.dataScope;
  if (scope === "all") return "全部数据";
  const regionName = authStore.user?.regionName;
  return regionName ? `限 ${regionName}` : "按分配范围";
});

async function onRecheckLicense() {
  await licenseStore.checkLicense();
  if (licenseStore.connectionError) {
    showToast("仍无法连接后端，请检查上方「后端地址」");
    return;
  }
  showToast(licenseStore.isValid ? "授权状态正常" : licenseStore.statusText || "未授权");
}

/* ---- 版本 / 热更 ---- */

/** Web 包版本 = 热更版本号；重启 App 后如果这个值变了，说明热更已生效 */
const bundleVersionLabel = computed(() => getBundleVersion());
const nativeVersionLabel = ref("—");
const checkingUpdate = ref(false);
const updateHint = computed(() => (checkingUpdate.value ? "检查中…" : "点击检查"));

onMounted(async () => {
  if (!isNativePlatform()) {
    nativeVersionLabel.value = "浏览器环境";
    return;
  }
  try {
    const { App } = await import("@capacitor/app");
    const info = await App.getInfo();
    nativeVersionLabel.value = `${info.version}（${info.build}）`;
  } catch {
    nativeVersionLabel.value = "—";
  }
});

/**
 * 手动检查更新：跳过 6h 节流，下载完成后**立即切换**新包（WebView 重载一次）。
 * 这是热更排障的抓手：如果这里提示"已是最新版本"而列表行为仍旧，那问题不在更新。
 */
async function onCheckUpdate() {
  if (!isNativePlatform()) {
    showToast("热更仅在 App 内生效，浏览器请直接刷新页面");
    return;
  }
  checkingUpdate.value = true;
  showLoadingToast({ message: "正在检查更新…", duration: 0, forbidClick: true });
  try {
    const result = await checkForUpdates({ force: true, activateNow: true });
    closeToast();
    switch (result?.status) {
      case "up-to-date":
        showToast("已是最新版本");
        break;
      case "unreachable":
        showToast("无法连接后端，请检查「后端地址」");
        break;
      case "native-too-old":
        showToast("新版本需要升级 App 客户端");
        break;
      case "error":
        showToast("更新失败，请稍后重试");
        break;
      default:
        // updated + activateNow → WebView 正在重载，无需提示
        break;
    }
  } catch {
    closeToast();
    showToast("更新失败，请稍后重试");
  } finally {
    checkingUpdate.value = false;
  }
}

async function onLogout() {
  try {
    await showConfirmDialog({ title: "退出登录", message: "确认退出当前账号？" });
  } catch {
    return;
  }
  authStore.logout();
  // ⛔ 必须在跳登录页**之前**打标记：登录页 onMounted 发现已保存凭据会自动重登，
  // 不打标记的话「退出 → 自动登回列表」等于退出无效（2026-10-04 事故，详见 session.js）。
  markManualLogout();
  router.replace({ name: "mobile-login" });
}
</script>

<style scoped>
.m-profile {
  padding-bottom: 24px;
}

.m-profile__card {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 12px 16px 20px;
  padding: 20px 18px;
  border-radius: 12px;
  background: #fff;
}

.m-profile__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: #e8f0fb;
  color: #387ac4;
  font-size: 17px;
  font-weight: 500;
}

.m-profile__identity {
  min-width: 0;
}

.m-profile__name {
  margin: 0;
  font-size: 17px;
  font-weight: 500;
  color: #1f2d3d;
}

.m-profile__account {
  margin: 4px 0 0;
  font-size: 12px;
  color: #8a94a6;
}

.m-profile__actions {
  padding: 24px 16px 0;
}

.m-profile__hint {
  margin: 18px 24px 0;
  font-size: 12px;
  line-height: 1.7;
  color: #a6adbb;
  text-align: center;
}
</style>
