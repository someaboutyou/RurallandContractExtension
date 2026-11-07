<template>
  <el-dialog
    :model-value="modelValue"
    title="导入发包方清单（Excel）"
    width="860px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="resetDialog"
  >
    <el-alert
      class="import-tip"
      type="info"
      :closable="false"
      show-icon
      title="请使用「发包方管理 → 导出发包方清单」生成的 Excel 修改后导入"
      description="逐行校验发包方编码与数据权限，按编码匹配——库内存在则对比更新，不存在则新增；删除发包方＝将该行「发包方名称」单元格填充底色或加删除线（名下仍有承包方的不允许删除，该行报错拦截）。"
    />

    <!-- 第一步：选择文件 -->
    <div v-if="step === 'upload'" class="upload-area">
      <input ref="fileInput" type="file" accept=".xls" class="file-input" @change="handleFileChange" />
      <el-button type="primary" plain :icon="FolderOpened" @click="fileInput?.click()">选择 .xls 文件</el-button>
      <span v-if="fileName" class="file-name">{{ fileName }}</span>
      <div class="upload-actions">
        <el-button type="primary" :disabled="!file" :loading="previewLoading" @click="doPreview">校验并预览</el-button>
      </div>
    </div>

    <!-- 第二步：预览报告 -->
    <template v-else-if="step === 'preview' && preview">
      <div class="summary-row">
        <el-tag type="primary">共 {{ preview.totalRows }} 行</el-tag>
        <el-tag type="success">新增 {{ preview.summary.create || 0 }}</el-tag>
        <el-tag type="warning">更新 {{ preview.summary.update || 0 }}</el-tag>
        <el-tag type="info">无变化 {{ preview.summary.no_change || 0 }}</el-tag>
        <el-tag v-if="preview.summary.delete" type="danger">删除 {{ preview.summary.delete }}</el-tag>
        <el-tag :type="preview.summary.error ? 'danger' : 'info'">错误 {{ preview.summary.error || 0 }}</el-tag>
      </div>
      <el-alert
        v-for="(warning, index) in preview.warnings"
        :key="`w${index}`"
        class="global-warning"
        type="warning"
        :closable="false"
        show-icon
        :title="warning"
      />
      <el-table :data="preview.issuers" border stripe size="small" max-height="380" class="report-table">
        <el-table-column prop="rowIndex" label="行号" width="70" />
        <el-table-column prop="code" label="发包方编码" width="150" show-overflow-tooltip />
        <el-table-column prop="name" label="发包方名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="动作" width="90">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" size="small">{{ actionLabel(row.action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="变化明细" min-width="220">
          <template #default="{ row }">
            <span v-if="row.action === 'delete'" class="delete-line">删除该发包方</span>
            <span v-else-if="row.changes?.length">{{ row.changes.join("、") }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="问题" min-width="200">
          <template #default="{ row }">
            <div v-for="(error, i) in row.errors" :key="`e${i}`" class="error-line">{{ error }}</div>
            <div v-for="(warning, i) in row.warnings" :key="`w${i}`" class="warning-line">{{ warning }}</div>
            <span v-if="!row.errors?.length && !row.warnings?.length">—</span>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 第三步：导入结果 -->
    <template v-else-if="step === 'result' && result">
      <div class="summary-row">
        <el-tag type="success">新增 {{ result.summary.created || 0 }}</el-tag>
        <el-tag type="warning">更新 {{ result.summary.updated || 0 }}</el-tag>
        <el-tag type="info">无变化 {{ result.summary.no_change || 0 }}</el-tag>
        <el-tag v-if="result.summary.deleted" type="danger">删除 {{ result.summary.deleted }}</el-tag>
        <el-tag :type="result.summary.failed ? 'danger' : 'info'">失败 {{ result.summary.failed || 0 }}</el-tag>
      </div>
      <el-table :data="result.issuers" border stripe size="small" max-height="380" class="report-table">
        <el-table-column prop="rowIndex" label="行号" width="70" />
        <el-table-column prop="code" label="发包方编码" width="150" show-overflow-tooltip />
        <el-table-column prop="name" label="发包方名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag :type="resultTagType(row.status)" size="small">{{ resultLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="说明" min-width="260" show-overflow-tooltip />
      </el-table>
    </template>

    <template #footer>
      <template v-if="step === 'preview'">
        <el-button @click="backToUpload">重新选择文件</el-button>
        <el-button type="primary" :loading="importing" @click="doImport">
          {{ preview.summary.error ? `仍要导入（${preview.summary.error} 行错误将被跳过）` : "确认导入" }}
        </el-button>
      </template>
      <template v-else-if="step === 'result'">
        <el-button type="primary" @click="finish">完成</el-button>
      </template>
      <template v-else>
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { FolderOpened } from "@element-plus/icons-vue";
import { importIssuerXls, previewIssuerXls } from "../../api/issuer";

defineProps({
  modelValue: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue", "imported"]);

const fileInput = ref(null);
const file = ref(null);
const fileName = ref("");
const step = ref("upload");
const previewLoading = ref(false);
const importing = ref(false);
const preview = ref(null);
const result = ref(null);

function resetDialog() {
  file.value = null;
  fileName.value = "";
  step.value = "upload";
  preview.value = null;
  result.value = null;
  importing.value = false;
  if (fileInput.value) fileInput.value.value = "";
}

function handleFileChange(event) {
  const selected = event.target.files?.[0];
  if (!selected) return;
  if (!/\.xls$/i.test(selected.name)) {
    ElMessage.warning("请选择 .xls 文件（发包方导出的即为此格式）");
    event.target.value = "";
    return;
  }
  file.value = selected;
  fileName.value = selected.name;
}

function backToUpload() {
  step.value = "upload";
  preview.value = null;
}

function buildFormData() {
  const formData = new FormData();
  formData.append("file", file.value);
  return formData;
}

async function doPreview() {
  previewLoading.value = true;
  try {
    // 接口统一包 {"data": …} 信封：这里必须取 data.data
    const { data } = await previewIssuerXls(buildFormData());
    preview.value = data.data;
    step.value = "preview";
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "校验失败，请检查文件格式");
  } finally {
    previewLoading.value = false;
  }
}

async function doImport() {
  importing.value = true;
  try {
    const { data } = await importIssuerXls(buildFormData());
    result.value = data.data;
    step.value = "result";
    emit("imported");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导入失败，请检查文件后重试");
  } finally {
    importing.value = false;
  }
}

function finish() {
  emit("update:modelValue", false);
}

const ACTION_LABELS = { create: "新增", update: "更新", no_change: "无变化", error: "错误", delete: "删除" };
const ACTION_TAG_TYPES = { create: "success", update: "warning", no_change: "info", error: "danger", delete: "danger" };
const RESULT_LABELS = { created: "新增", updated: "更新", no_change: "无变化", failed: "失败", deleted: "删除" };
const RESULT_TAG_TYPES = { created: "success", updated: "warning", no_change: "info", failed: "danger", deleted: "danger" };

function actionLabel(value) { return ACTION_LABELS[value] || value; }
function actionTagType(value) { return ACTION_TAG_TYPES[value] || "info"; }
function resultLabel(value) { return RESULT_LABELS[value] || value; }
function resultTagType(value) { return RESULT_TAG_TYPES[value] || "info"; }
</script>

<style scoped>
.import-tip {
  margin-bottom: 12px;
}
.upload-area {
  align-items: center;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 28px 0 12px;
}
.file-input {
  display: none;
}
.file-name {
  color: #475569;
  font-size: 13px;
}
.upload-actions {
  margin-top: 4px;
}
.summary-row {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.global-warning {
  margin-bottom: 8px;
}
.report-table {
  width: 100%;
}
.warning-line {
  color: #b45309;
  font-size: 12px;
  line-height: 1.6;
}
.delete-line {
  color: #dc2626;
  font-size: 12px;
  line-height: 1.6;
}
.error-line {
  color: #dc2626;
  font-size: 12px;
  line-height: 1.6;
}
</style>
