<template>
  <section class="panel license-page">
    <div class="toolbar">
      <div class="panel-title">授权管理</div>
      <div class="toolbar-actions">
        <el-button plain :loading="loading" @click="load">刷新</el-button>
        <el-button plain :loading="reloading" @click="handleReload">重新加载授权</el-button>
      </div>
    </div>

    <el-empty v-if="!isPlatformAdmin" description="仅平台管理员可管理授权。" />

    <template v-else>
      <div class="license-grid">
        <el-card shadow="never" class="license-card">
          <template #header>
            <div class="license-card-head">
              <span>当前授权</span>
              <el-tag :type="status?.is_valid ? 'success' : 'danger'" effect="plain">
                {{ status?.is_valid ? "有效" : "无效" }}
              </el-tag>
            </div>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="授权区域">
              {{ status?.region_name || "-" }}
              <span v-if="status?.region_code" class="license-region-code">（{{ status.region_code }}）</span>
            </el-descriptions-item>
            <el-descriptions-item label="区域级别">{{ regionLevelText }}</el-descriptions-item>
            <el-descriptions-item label="签发时间">{{ formatDateTime(status?.issued_at) }}</el-descriptions-item>
            <el-descriptions-item label="到期时间">{{ status?.expires_at ? formatDateTime(status.expires_at) : "长期有效" }}</el-descriptions-item>
            <el-descriptions-item label="授权状态">
              <span :class="status?.is_valid ? 'license-ok' : 'license-error'">
                {{ status?.error_message || (status?.is_valid ? "授权文件校验通过" : "授权文件无效") }}
              </span>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card shadow="never" class="license-card">
          <template #header>
            <div class="license-card-head">
              <span>机器码</span>
              <el-button link type="primary" @click="copyMachineCode">复制</el-button>
            </div>
          </template>
          <div class="machine-code">{{ machineCode || "-" }}</div>
          <p class="license-hint">
            更换服务器或重装系统后机器码可能变化。申请授权时请把机器码和需要授权的区域编码（6 位区县 / 9 位镇 / 12 位村）一起提供给授权方。
          </p>
        </el-card>
      </div>

      <el-card shadow="never" class="license-upload-card">
        <template #header>
          <div class="license-card-head">
            <span>更新 / 替换授权文件</span>
            <el-tag type="warning" effect="plain" size="small">立即生效</el-tag>
          </div>
        </template>
        <div class="license-upload-row">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :show-file-list="false"
            :limit="1"
            accept=".dat"
            :on-change="handleFileSelected"
          >
            <el-button type="primary" :loading="uploading">选择授权文件并上传</el-button>
          </el-upload>
          <span class="license-hint">支持授权方提供的 `.dat` 授权文件；替换前系统会自动备份旧授权。</span>
        </div>

        <el-alert
          v-if="uploadResult"
          class="license-result"
          :type="uploadResult.is_valid ? 'success' : 'error'"
          :closable="false"
          show-icon
          :title="uploadResult.is_valid ? '授权文件已替换并生效' : '授权文件无效，请更换后重试'"
          :description="uploadResult.error_message || (uploadResult.is_valid ? `授权区域：${uploadResult.region_name || uploadResult.region_code || '-'}` : '')"
        />
        <el-alert
          v-else
          class="license-result"
          type="info"
          :closable="false"
          show-icon
          title="替换授权会立即生效，无需重启后端。请确认授权区域与当前业务区域一致。"
        />
      </el-card>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import {
  fetchLicenseMachineCode,
  fetchLicenseStatus,
  reloadLicense,
  uploadLicenseFile,
} from "../api/license";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const isPlatformAdmin = computed(() => authStore.user?.roleCode === "platform_admin");

const loading = ref(false);
const reloading = ref(false);
const uploading = ref(false);
const status = ref(null);
const machineCode = ref("");
const uploadResult = ref(null);
const uploadRef = ref(null);

const regionLevelText = computed(() => {
  const level = status.value?.region_level || "";
  return {
    province: "省级",
    city: "市级",
    county: "区县级",
    town: "乡镇级",
    village: "村级",
    group: "组级",
  }[level] || level || "-";
});

function formatDateTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 19);
}

async function load() {
  if (!isPlatformAdmin.value) return;
  loading.value = true;
  try {
    const [statusRes, machineRes] = await Promise.all([
      fetchLicenseStatus(),
      fetchLicenseMachineCode(),
    ]);
    status.value = statusRes.data?.data || null;
    machineCode.value = machineRes.data?.data?.machine_code || "";
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "授权状态读取失败");
  } finally {
    loading.value = false;
  }
}

async function handleReload() {
  reloading.value = true;
  try {
    const { data } = await reloadLicense();
    const info = data?.data || {};
    if (info.is_valid) {
      ElMessage.success("授权已重新加载");
    } else {
      ElMessage.error(info.error_message || "授权文件无效");
    }
    await load();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "重新加载授权失败");
  } finally {
    reloading.value = false;
  }
}

async function handleFileSelected(uploadFile) {
  if (!uploadFile?.raw) return;
  uploading.value = true;
  uploadResult.value = null;
  try {
    const formData = new FormData();
    formData.append("file", uploadFile.raw);
    const { data } = await uploadLicenseFile(formData);
    const info = data?.data || {};
    uploadResult.value = info;
    if (info.is_valid) {
      ElMessage.success("授权文件已替换并生效");
      await load();
    } else {
      ElMessage.error(info.error_message || "授权文件无效");
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "授权文件上传失败");
  } finally {
    uploading.value = false;
    uploadRef.value?.clearFiles();
  }
}

function copyMachineCode() {
  if (!machineCode.value) return;
  navigator.clipboard.writeText(machineCode.value).then(
    () => ElMessage.success("机器码已复制"),
    () => ElMessage.warning("复制失败，请手动复制"),
  );
}

onMounted(load);
</script>

<style scoped>
.license-page {
  height: 100%;
  overflow: auto;
}

.license-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}

.license-card,
.license-upload-card {
  border: 1px solid var(--line);
}

.license-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
}

.license-region-code {
  color: var(--muted);
}

.license-ok {
  color: var(--success);
}

.license-error {
  color: var(--danger);
}

.machine-code {
  padding: 10px 12px;
  overflow-wrap: anywhere;
  border: 1px dashed var(--line);
  border-radius: var(--radius-md);
  background: var(--bg-2);
  color: var(--text);
  font-family: Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
}

.license-hint {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}

.license-upload-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.license-result {
  margin-top: 12px;
}

@media (max-width: 900px) {
  .license-grid {
    grid-template-columns: 1fr;
  }
}
</style>
