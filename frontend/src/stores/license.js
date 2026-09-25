import { defineStore } from "pinia";
import { computed, ref } from "vue";
import http from "../api/http";

const STATUS_TEXT_MAP = {
  not_found: "授权文件不存在",
  invalid_format: "授权文件格式错误",
  machine_mismatch: "机器码不匹配",
  expired: "授权已过期",
  tampered: "授权文件被篡改",
};

/** 自动检查间隔：10 分钟 */
export const AUTO_CHECK_INTERVAL = 10 * 60 * 1000;

/** 连不上后端时的快速重试间隔（后端重启通常几十秒内恢复） */
const RETRY_DELAY = 15 * 1000;
/** 连续失败达到该次数才判定为「服务不可用」，避免后端重启时误报 */
const RETRY_TIMES = 3;

export const useLicenseStore = defineStore("license", () => {
  const isValid = ref(true); // 默认 true，避免未检查时误弹窗
  const checked = ref(false);
  const dialogVisible = ref(false);
  const statusText = ref("");
  const machineCode = ref("");
  const licenseInfo = ref(null);
  const lastCheckedAt = ref(null);
  const checking = ref(false);
  /**
   * true 表示「连不上后端服务」，与「后端明确返回未授权」是两回事。
   * 必须分开，否则后端没启动时会把人误导向重新申请授权。
   */
  const connectionError = ref(false);

  // 定时器句柄（非响应式）
  let timer = null;
  let retryTimer = null;
  let retryCount = 0;

  /** 授权到期时间文案 */
  const expiresText = computed(() => {
    const expiresAt = licenseInfo.value?.expires_at;
    if (!expiresAt) return "永久有效";
    const date = new Date(expiresAt);
    if (Number.isNaN(date.getTime())) return "-";
    const days = Math.ceil((date.getTime() - Date.now()) / 86400000);
    const text = date.toLocaleString("zh-CN", { hour12: false });
    return days >= 0 ? `${text}（剩余 ${days} 天）` : `${text}（已过期）`;
  });

  function showDialog(message) {
    statusText.value = message || "系统未授权";
    dialogVisible.value = true;
  }

  function hideDialog() {
    dialogVisible.value = false;
  }

  /** 被 HTTP 拦截器调用：后端返回 403 license_required 时触发 */
  function onLicenseDenied(detail) {
    isValid.value = false;
    checked.value = true;
    connectionError.value = false;
    showDialog(detail || "系统未授权");
    // 异步获取机器码（如果还没有）
    if (!machineCode.value) {
      fetchMachineCode();
    }
  }

  function clearRetry() {
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer);
      retryTimer = null;
    }
  }

  /** 连接失败后的快速重试（不弹窗，静默重试） */
  function scheduleRetry() {
    clearRetry();
    retryTimer = window.setTimeout(() => {
      retryTimer = null;
      checkLicense();
    }, RETRY_DELAY);
  }

  /**
   * 主动检查授权状态
   *
   * 后端 /license/status 每次都按授权文件的当前状态返回，并禁用缓存，
   * 因此这里拿到的始终是最新结果。
   */
  async function checkLicense() {
    if (checking.value) return;
    checking.value = true;
    try {
      const { data } = await http.get("/license/status", {
        params: { _t: Date.now() },
      });
      const info = data.data ?? data;
      isValid.value = !!info.is_valid;
      licenseInfo.value = info;
      checked.value = true;
      connectionError.value = false;
      retryCount = 0;
      clearRetry();
      if (isValid.value) {
        hideDialog();
      } else {
        showDialog(STATUS_TEXT_MAP[info.status] || info.error_message || "未知错误");
        if (!machineCode.value) {
          fetchMachineCode();
        }
      }
    } catch {
      // 请求本身失败（后端未启动、正在重启、网关 502 等）。
      // 先静默快速重试；连续失败 RETRY_TIMES 次才提示，且提示口径是
      // 「连不上服务」而非「未授权」——两者的处理方式完全不同。
      connectionError.value = true;
      checked.value = true;
      licenseInfo.value = null;
      retryCount += 1;
      if (retryCount < RETRY_TIMES) {
        scheduleRetry();
      } else {
        showDialog("无法连接后端服务");
        if (!machineCode.value) {
          fetchMachineCode();
        }
      }
    } finally {
      lastCheckedAt.value = new Date();
      checking.value = false;
    }
  }

  async function fetchMachineCode() {
    try {
      const { data } = await http.get("/license/machine-code");
      const info = data.data ?? data;
      machineCode.value = info.machine_code || "";
    } catch {
      machineCode.value = "获取失败";
    }
  }

  /** 启动定时检查（默认每 10 分钟） */
  function startAutoCheck(intervalMs = AUTO_CHECK_INTERVAL) {
    stopAutoCheck();
    timer = window.setInterval(() => {
      checkLicense();
    }, intervalMs);
    return timer;
  }

  /** 停止定时检查 */
  function stopAutoCheck() {
    if (timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
    clearRetry();
  }

  return {
    isValid,
    checked,
    dialogVisible,
    statusText,
    machineCode,
    licenseInfo,
    lastCheckedAt,
    checking,
    connectionError,
    expiresText,
    showDialog,
    hideDialog,
    onLicenseDenied,
    checkLicense,
    fetchMachineCode,
    startAutoCheck,
    stopAutoCheck,
  };
});
