<template>
  <van-popup
    :show="show"
    position="bottom"
    round
    :close-on-click-overlay="true"
    @update:show="emit('update:show', $event)"
  >
    <div class="m-server">
      <h3 class="m-server__title">服务器设置</h3>

      <p class="m-server__desc">
        填后端服务的地址（含端口），例如 <code>192.168.1.10:8000</code> 或
        <code>https://survey.example.cn</code>。不需要带 <code>/api/v1</code>，程序会自动补。
      </p>

      <van-cell-group inset>
        <van-field
          v-model="input"
          label="服务器"
          placeholder="192.168.1.10:8000"
          clearable
          autocomplete="off"
          :error-message="inputError"
        />
      </van-cell-group>

      <div class="m-server__preview">
        <p class="m-server__preview-label">保存后接口地址</p>
        <code class="m-server__preview-value">{{ previewApiBase }}</code>
      </div>

      <div class="m-server__actions">
        <van-button block round type="primary" :loading="saving" @click="onSave">
          保存并检测连接
        </van-button>
        <van-button block round plain :disabled="saving" @click="onReset">
          恢复默认（清除本机设置）
        </van-button>
      </div>

      <p class="m-server__hint">
        本设置只影响这台设备，改完无需重新安装 App。换服务器时在这里改一次即可。
      </p>
    </div>
  </van-popup>
</template>

<script setup>
/**
 * 服务器地址设置弹层（移动端）。
 *
 * 存在的理由：Capacitor「内置资源模式」下页面的 origin 是 `http://localhost`，
 * 相对路径打不到后端；而构建期注入的地址一旦写进 APK 就固化，
 * 换服务器得让所有调查员重装。所以把地址做成运行时可改（存 localStorage）。
 *
 * 「保存并检测连接」会真的打一次 `GET {apiBase}/license/status`：
 * - 该接口在后端授权白名单里放行（不需要登录），拿它探活最轻；
 * - 用原生 fetch 而不是 axios 实例，才能检测"尚未保存的"地址；
 * - 这一步同时能暴露后端 CORS 白名单没放行 `http://localhost` 的情况
 *   （表现为 fetch 直接被拦，而不是返回 HTTP 错误码）。
 */
import { computed, ref, watch } from "vue";
import { getServerBase, resolveApiBase, setServerBase, validateServerBase } from "../../api/serverConfig";
import { VanButton, VanCellGroup, VanField, VanPopup, showToast } from "../ui.js";

const props = defineProps({
  show: { type: Boolean, default: false },
});
const emit = defineEmits(["update:show", "saved"]);

const input = ref("");
const inputError = ref("");
const saving = ref(false);

// 每次打开时用已保存的值回填，避免上次输入的半成品残留
watch(
  () => props.show,
  (visible) => {
    if (visible) {
      input.value = getServerBase();
      inputError.value = "";
    }
  },
);

/** 实时预览：让用户看到"自己输入的这串"最终会变成什么 */
const previewApiBase = computed(() => {
  const raw = input.value.trim();
  if (!raw) return resolveApiBase() || "/api/v1";
  const error = validateServerBase(raw);
  if (error) return "（地址不合法）";

  const normalized = raw.replace(/\/+$/, "").replace(/\/api\/v1$/i, "");
  const withScheme = /^https?:\/\//i.test(normalized) ? normalized : `http://${normalized}`;
  return `${withScheme.replace(/\/+$/, "")}/api/v1`;
});

/** 探测目标服务是否可达（不依赖 axios 实例，所以能测未保存的地址） */
async function probe(apiBase) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${apiBase}/license/status`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    // 能拿到 HTTP 状态码就说明网络通、后端在、CORS 也放行了
    return { reachable: true, status: response.status };
  } catch (error) {
    return { reachable: false, reason: error?.name === "AbortError" ? "超时" : "网络不通或被跨域拦截" };
  } finally {
    window.clearTimeout(timer);
  }
}

async function onSave() {
  const error = validateServerBase(input.value);
  inputError.value = error;
  if (error) return;

  const before = getServerBase();
  const after = setServerBase(input.value);

  if (!after) {
    showToast("已清除设置，回到默认地址");
    emit("saved", after);
    emit("update:show", false);
    return;
  }

  saving.value = true;
  const result = await probe(`${after}/api/v1`);
  saving.value = false;

  if (result.reachable) {
    showToast(`连接正常（HTTP ${result.status}）`);
    emit("saved", after);
    emit("update:show", false);
  } else {
    // 地址仍然保存 —— 可能是外业现场暂时没网，不该逼用户重填。
    // 但必须明确告诉他是"连不上"，避免误以为是授权问题。
    showToast({
      message: `地址已保存，但连接失败：${result.reason}`,
      duration: 4000,
    });
    emit("saved", after);
  }

  // 地址真的变了才刷新：让 license / 用户信息按新地址重新拉一次
  if (after !== before) {
    window.setTimeout(() => window.location.reload(), 1200);
  }
}

function onReset() {
  setServerBase("");
  input.value = "";
  inputError.value = "";
  showToast("已恢复默认地址");
  emit("saved", "");
  emit("update:show", false);
}
</script>

<style scoped>
.m-server {
  padding: 20px 0 24px;
}

.m-server__title {
  margin: 0 0 12px;
  padding: 0 20px;
  font-size: 16px;
  font-weight: 500;
  color: #1f2d3d;
}

.m-server__desc {
  margin: 0 0 16px;
  padding: 0 20px;
  font-size: 12px;
  line-height: 1.7;
  color: #8a94a6;
}

.m-server__desc code,
.m-server__preview-value {
  padding: 1px 4px;
  border-radius: 3px;
  background: #f2f3f5;
  color: #387ac4;
  font-size: 12px;
  word-break: break-all;
}

.m-server__preview {
  margin: 14px 20px 0;
}

.m-server__preview-label {
  margin: 0 0 4px;
  font-size: 12px;
  color: #a6adbb;
}

.m-server__actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px 16px 0;
}

.m-server__hint {
  margin: 16px 20px 0;
  font-size: 12px;
  line-height: 1.7;
  color: #a6adbb;
}
</style>
