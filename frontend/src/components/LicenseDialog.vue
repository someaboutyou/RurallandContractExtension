<template>
  <el-dialog
    v-model="store.dialogVisible"
    :title="dialogTitle"
    width="520px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    align-center
  >
    <el-alert
      :type="store.connectionError ? 'error' : 'warning'"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #title>
        {{ alertText }}
      </template>
    </el-alert>

    <!-- 连不上后端：与授权无关，不要引导用户去重新申请授权 -->
    <template v-if="store.connectionError">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="异常状态">
          <el-tag type="danger">{{ store.statusText }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="上次检查">
          {{ lastCheckedText }}
        </el-descriptions-item>
      </el-descriptions>

      <p class="license-hint">
        后端服务未在运行或正在重启（本机 8000 端口无响应），页面取不到数据，与授权无关。
        请确认后端已启动（<code>scripts\start-backend.ps1</code>），然后点击「立即重新检查」。
      </p>
    </template>

    <template v-else>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="授权状态">
          <el-tag type="danger">{{ store.statusText }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="机器码">
          <div style="display: flex; align-items: center; gap: 8px">
            <code style="font-size: 13px; word-break: break-all">{{ store.machineCode }}</code>
            <el-button size="small" @click="copyCode">复制</el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="授权到期">
          {{ store.expiresText }}
        </el-descriptions-item>
      </el-descriptions>

      <p class="license-hint">
        请将机器码和需要授权的区域代码（6位区县 / 9位镇 / 12位村）发送给授权方，获取授权文件后在下方上传。
      </p>
    </template>

    <template #footer>
      <div class="license-footer">
        <span class="license-footer__meta">
          每 10 分钟自动检查一次 · {{ lastCheckedText }}
        </span>
        <div class="license-footer__actions">
          <el-button :loading="store.checking" @click="store.checkLicense()">
            立即重新检查
          </el-button>
          <el-upload
            v-if="!store.connectionError"
            ref="uploadRef"
            :auto-upload="false"
            :show-file-list="false"
            :limit="1"
            accept=".dat"
            :on-change="handleFileSelected"
          >
            <el-button type="primary" :loading="uploading">
              上传授权文件
            </el-button>
          </el-upload>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { useLicenseStore } from "../stores/license";
import http from "../api/http";

const store = useLicenseStore();
const uploading = ref(false);
const uploadRef = ref();

const dialogTitle = computed(() =>
  store.connectionError ? "无法连接服务器" : "系统未授权",
);

const alertText = computed(() =>
  store.connectionError
    ? "当前无法连接后端服务，页面功能暂不可用。请检查后端服务是否已启动，稍后重试。"
    : "当前服务器未授权，大部分功能暂不可用。请联系管理员完成授权后再使用。",
);

const lastCheckedText = computed(() => {
  const at = store.lastCheckedAt;
  if (!at) return "尚未检查";
  return `上次检查：${at.toLocaleTimeString("zh-CN", { hour12: false })}`;
});

function copyCode() {
  if (!store.machineCode) return;
  navigator.clipboard.writeText(store.machineCode).then(
    () => ElMessage.success("机器码已复制到剪贴板"),
    () => ElMessage.warning("复制失败，请手动复制"),
  );
}

async function handleFileSelected(uploadFile) {
  if (!uploadFile?.raw) return;

  uploading.value = true;
  try {
    const formData = new FormData();
    formData.append("file", uploadFile.raw);

    const { data } = await http.post("/license/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });

    const info = data.data ?? data;
    if (info.is_valid) {
      ElMessage.success("授权验证成功，正在刷新…");
      setTimeout(() => window.location.reload(), 600);
    } else {
      ElMessage.error("授权文件无效：" + (info.error_message || "未知错误"));
    }
  } catch (err) {
    const msg = err.response?.data?.detail || err.message || "上传失败";
    ElMessage.error("上传失败：" + msg);
  } finally {
    uploading.value = false;
    // 清除已选文件，允许再次选择
    if (uploadRef.value) uploadRef.value.clearFiles();
  }
}
</script>

<style scoped>
.license-hint {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: #909399;
}

.license-hint code {
  padding: 0 4px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
  font-size: 12px;
}

.license-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.license-footer__meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  text-align: left;
}

.license-footer__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
</style>
