<template>
  <el-dialog
    :model-value="modelValue"
    title="发包方导出（Excel）"
    width="480px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="resetDialog"
  >
    <div class="export-body">
      <template v-if="status === 'loading'">
        <el-progress :percentage="80" :stroke-width="14" striped striped-flow />
        <div class="tip-line">正在生成本批次的发包方调查表 Excel…</div>
      </template>

      <template v-else-if="status === 'done'">
        <el-result icon="success" title="导出完成" :sub-title="filename">
          <template #extra>
            <el-button v-if="!autoDownloaded" type="primary" @click="download">下载</el-button>
            <el-button v-else type="primary" @click="emit('update:modelValue', false)">关闭</el-button>
          </template>
        </el-result>
      </template>

      <template v-else-if="status === 'error'">
        <el-result icon="error" title="导出失败" :sub-title="errorMessage" />
      </template>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { exportIssuerSurveyXls } from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  batch: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue"]);

const status = ref("idle"); // idle / loading / done / error
const filename = ref("");
const errorMessage = ref("");
const content = ref(null);
const autoDownloaded = ref(false);

function resetDialog() {
  status.value = "idle";
  filename.value = "";
  errorMessage.value = "";
  content.value = null;
  autoDownloaded.value = false;
}

function download() {
  if (!content.value) return;
  const url = URL.createObjectURL(content.value);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.value || "发包方调查表.xls";
  link.click();
  URL.revokeObjectURL(url);
  autoDownloaded.value = true;
}

async function start() {
  if (!props.batch?.id) return;
  status.value = "loading";
  try {
    const { data, headers } = await exportIssuerSurveyXls(props.batch.id);
    content.value = data;
    // 优先从 Content-Disposition 解析后端文件名（filename*=UTF-8''…）
    const disposition = headers?.["content-disposition"] || "";
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
    filename.value = match ? decodeURIComponent(match[1]) : "发包方调查表.xls";
    status.value = "done";
    download();
  } catch (error) {
    status.value = "error";
    errorMessage.value = error.response?.data?.detail || "导出失败，请稍后重试";
  }
}

watch(() => props.modelValue, (visible) => { if (visible) start(); });
</script>

<style scoped>
.export-body {
  padding: 8px 4px;
}
.tip-line {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 12px;
}
</style>
