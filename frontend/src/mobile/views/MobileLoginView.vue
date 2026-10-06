<template>
  <div class="m-login">
    <div class="m-login__hero">
      <h1 class="m-login__title">延包调查</h1>
      <p class="m-login__subtitle">农村土地承包合同延包 · 外业采集端</p>
    </div>

    <van-form @submit="onSubmit">
      <van-cell-group inset>
        <van-field
          v-model="form.username"
          name="username"
          label="账号"
          placeholder="请输入账号"
          autocomplete="username"
          :rules="[{ required: true, message: '请输入账号' }]"
        />
        <van-field
          v-model="form.password"
          type="password"
          name="password"
          label="密码"
          placeholder="请输入密码"
          autocomplete="current-password"
          :rules="[{ required: true, message: '请输入密码' }]"
        />
      </van-cell-group>

      <div class="m-login__actions">
        <van-checkbox v-model="remember" shape="square" class="m-login__remember">
          记住账号密码
        </van-checkbox>
        <van-button round block type="primary" native-type="submit" :loading="loading">
          登录
        </van-button>
      </div>
    </van-form>

    <div class="m-login__env">
      <p>运行环境：{{ runtimeLabel }}</p>
      <p class="m-login__server" @click="serverSettingVisible = true">
        后端地址：{{ apiBaseLabel }}
        <span class="m-login__server-edit">修改</span>
      </p>
      <p v-if="!apiConfigured" class="m-login__warn">
        尚未设置后端地址，登录会失败 —— 请先点上方「修改」填写服务器地址。
      </p>
    </div>

    <ServerSettingPopup v-model:show="serverSettingVisible" />
  </div>
</template>

<script setup>
/**
 * 移动端登录。复用 PC 端同一套 auth store / token 存储，
 * 因此登录态在两端互通（同一浏览器/同一 WebView 下）。
 *
 * 底部「运行环境 + 后端地址」不是装饰，而是外业排障的抓手：
 * - 运行环境 → 区分 App 壳还是浏览器
 * - 后端地址 → 内置资源模式下页面 origin 是 http://localhost，
 *   必须显式配置后端地址才能连通；这一行让"配没配、配的是什么"一目了然，
 *   点它即可就地修改（详见 ServerSettingPopup.vue）。
 */
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../../stores/auth";
import { isApiBaseConfigured, resolveApiBase } from "../../api/serverConfig";
import { CREDENTIALS_KEY, clearManualLogout, isManualLogoutPending } from "../session.js";
import ServerSettingPopup from "../components/ServerSettingPopup.vue";
// ⚠️ 登录页不在 MobileLayout 下（`/m/login` 是独立路由），必须自己引入 vant 样式，
// 否则登录表单是"能点但没样式"的裸奔状态。
import "../styles.js";
import { isNativePlatform } from "../native/location.js";
import { VanButton, VanCellGroup, VanCheckbox, VanField, VanForm, showToast } from "../ui.js";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const form = reactive({ username: "", password: "" });
const loading = ref(false);
const serverSettingVisible = ref(false);
const remember = ref(false);

const runtimeLabel = computed(() => (isNativePlatform() ? "Android App" : "浏览器 / H5"));
const apiBaseLabel = computed(() => resolveApiBase());
const apiConfigured = computed(() => isApiBaseConfigured());

async function onSubmit() {
  if (!apiConfigured.value) {
    showToast("请先设置后端服务器地址");
    serverSettingVisible.value = true;
    return;
  }

  loading.value = true;
  try {
    await authStore.login({
      username: form.username.trim(),
      password: form.password,
    });
    if (remember.value) {
      localStorage.setItem(
        CREDENTIALS_KEY,
        JSON.stringify({ username: form.username.trim(), password: form.password }),
      );
    } else {
      localStorage.removeItem(CREDENTIALS_KEY);
    }
    // 手动登录成功 = 用户明确表达了登录意愿，清除「主动退出」标记，
    // 恢复本会话内的自动登录语义。
    clearManualLogout();
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "";
    await router.replace(redirect || { name: "mobile-tasks" });
    // 登录成功 = 后端地址已验证可用，此时补一次热更检查（非阻塞，不拦截进首页）。
    // 背景：冷启动的自动检查发生在登录页，清存储后地址还没配，检查必然失败；
    // 若节流时间戳在失败时也被写下（旧版 bug），手机会被锁在「不再检查」里。
    void import("../updater.js")
      .then((m) => m.checkForUpdates())
      .catch(() => {});
  } catch (error) {
    // 连不上后端时 axios 报的是网络错误（没有 response），
    // 这种情况必须提示"检查服务器地址"，而不是笼统的"账号密码错误"。
    if (!error?.response) {
      showToast("无法连接服务器，请检查后端地址");
      serverSettingVisible.value = true;
      return;
    }
    const detail = error.response.data?.detail || error.response.data?.message;
    showToast(typeof detail === "string" ? detail : "登录失败，请检查账号与密码");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  try {
    const saved = localStorage.getItem(CREDENTIALS_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (parsed.username) {
        form.username = parsed.username;
      }
      if (parsed.password) {
        form.password = parsed.password;
      }
      remember.value = true;
      // ⛔ 主动退出后**只预填、不自动登录**：否则退出 → 跳登录页 → 自动重登 →
      // 跳回「我的待调查」，退出形同虚设（2026-10-04 事故，详见 session.js）。
      // sessionStorage 标记在杀掉 App 重开后自动消失，冷启动自动登录不受影响。
      if (apiConfigured.value && !isManualLogoutPending()) {
        onSubmit();
      }
    }
  } catch {
    // 存储损坏时忽略，走正常手动登录
  }
});
</script>

<style scoped>
.m-login {
  min-height: 100vh;
  padding-top: calc(14vh + env(safe-area-inset-top));
  background: #f7f8fa;
}

.m-login__hero {
  padding: 0 24px 28px;
  text-align: center;
}

.m-login__title {
  margin: 0;
  font-size: 26px;
  font-weight: 500;
  color: #1f2d3d;
  letter-spacing: 2px;
}

.m-login__subtitle {
  margin: 10px 0 0;
  font-size: 13px;
  color: #8a94a6;
}

.m-login__actions {
  padding: 20px 16px 0;
}

.m-login__remember {
  margin-bottom: 14px;
  font-size: 13px;
  color: #646566;
}

.m-login__env {
  padding: 32px 24px 0;
  font-size: 12px;
  line-height: 1.8;
  color: #a6adbb;
  text-align: center;
}

.m-login__env p {
  margin: 0;
}

.m-login__server {
  word-break: break-all;
}

.m-login__server-edit {
  margin-left: 4px;
  color: #387ac4;
  text-decoration: underline;
}

.m-login__warn {
  margin-top: 8px !important;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fff7e6;
  color: #d48806;
  line-height: 1.6;
  text-align: left;
}
</style>
