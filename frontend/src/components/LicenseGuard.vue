<template>
  <slot />

  <el-dialog
    v-model="visible"
    title="系统未授权"
    width="520px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    align-center
  >
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #title>
        当前服务器未授权，大部分功能暂不可用。请联系管理员完成授权后再使用。
      </template>
    </el-alert>

    <el-descriptions :column="1" border size="small">
      <el-descriptions-item label="授权状态">
        <el-tag type="danger">{{ statusText }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="机器码">
        <div style="display: flex; align-items: center; gap: 8px">
          <code style="font-size: 13px; word-break: break-all">{{ machineCode }}</code>
          <el-button size="small" @click="copyCode">复制</el-button>
        </div>
      </el-descriptions-item>
    </el-descriptions>

    <p style="margin-top: 12px; font-size: 13px; color: #909399">
      请将机器码和需要授权的区域代码（6位区县 / 9位镇 / 12位村）发送给授权方，获取授权文件后放到
      <code>backend/storage/license.dat</code> 并重启后端服务。
    </p>

    <template #footer>
      <el-button type="primary" @click="refresh">我已完成授权，刷新</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import http from "../api/http";

const visible = ref(false);
const machineCode = ref("");
const statusText = ref("加载中…");

const STATUS_MAP = {
  not_found: "授权文件不存在",
  invalid_format: "授权文件格式错误",
  machine_mismatch: "机器码不匹配",
  expired: "授权已过期",
  tampered: "授权文件被篡改",
};

async function checkLicense() {
  try {
    const { data } = await http.get("/license/status");
    const info = data.data ?? data;
    if (info.is_valid) {
      visible.value = false;
      return;
    }
    statusText.value = STATUS_MAP[info.status] || info.error_message || "未知错误";
    visible.value = true;
  } catch {
    statusText.value = "无法连接授权服务";
    visible.value = true;
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

function copyCode() {
  if (!machineCode.value) return;
  navigator.clipboard.writeText(machineCode.value).then(
    () => ElMessage.success("机器码已复制到剪贴板"),
    () => ElMessage.warning("复制失败，请手动复制"),
  );
}

function refresh() {
  window.location.reload();
}

onMounted(async () => {
  await Promise.all([checkLicense(), fetchMachineCode()]);
});
</script>
