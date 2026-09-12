<template>
  <el-dialog
    v-model="store.dialogVisible"
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
        <el-tag type="danger">{{ store.statusText }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="机器码">
        <div style="display: flex; align-items: center; gap: 8px">
          <code style="font-size: 13px; word-break: break-all">{{ store.machineCode }}</code>
          <el-button size="small" @click="copyCode">复制</el-button>
        </div>
      </el-descriptions-item>
    </el-descriptions>

    <p style="margin-top: 12px; font-size: 13px; color: #909399">
      请将机器码和需要授权的区域代码（6位区县 / 9位镇 / 12位村）发送给授权方，获取授权文件后在下方上传。
    </p>

    <template #footer>
      <el-upload
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
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { useLicenseStore } from "../stores/license";
import http from "../api/http";

const store = useLicenseStore();
const uploading = ref(false);
const uploadRef = ref();

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

onMounted(() => {
  store.checkLicense();
});
</script>
