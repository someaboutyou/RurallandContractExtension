import { defineStore } from "pinia";
import { ref } from "vue";
import http from "../api/http";

const STATUS_TEXT_MAP = {
  not_found: "授权文件不存在",
  invalid_format: "授权文件格式错误",
  machine_mismatch: "机器码不匹配",
  expired: "授权已过期",
  tampered: "授权文件被篡改",
};

export const useLicenseStore = defineStore("license", () => {
  const isValid = ref(true); // 默认 true，避免未检查时误弹窗
  const checked = ref(false);
  const dialogVisible = ref(false);
  const statusText = ref("");
  const machineCode = ref("");

  function showDialog(message) {
    statusText.value = message || "系统未授权";
    dialogVisible.value = true;
  }

  function hideDialog() {
    dialogVisible.value = false;
  }

  /** 被 HTTP 拦截器调用：后端返回 license_required 时触发 */
  function onLicenseDenied(detail) {
    isValid.value = false;
    checked.value = true;
    showDialog(detail || "系统未授权");
    // 异步获取机器码（如果还没有）
    if (!machineCode.value) {
      fetchMachineCode();
    }
  }

  /** 主动检查授权状态 */
  async function checkLicense() {
    try {
      const { data } = await http.get("/license/status");
      const info = data.data ?? data;
      isValid.value = info.is_valid;
      checked.value = true;
      if (!info.is_valid) {
        showDialog(STATUS_TEXT_MAP[info.status] || info.error_message || "未知错误");
      }
    } catch {
      isValid.value = false;
      checked.value = true;
      showDialog("无法连接授权服务");
    }
    // 同时获取机器码
    await fetchMachineCode();
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

  return {
    isValid,
    checked,
    dialogVisible,
    statusText,
    machineCode,
    showDialog,
    hideDialog,
    onLicenseDenied,
    checkLicense,
    fetchMachineCode,
  };
});
