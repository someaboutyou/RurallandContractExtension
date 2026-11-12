<template>
  <el-dialog
    :model-value="modelValue"
    title="导出承包方资料"
    width="640px"
    top="8vh"
    class="contractor-export-dialog"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="exporting = false"
  >
    <div class="export-head">
      <div class="export-count">
        <template v-if="contractorUids.length">已选 <strong>{{ contractorUids.length }}</strong> 个承包方</template>
        <template v-else>未勾选承包方，将导出本批次<strong>全部 {{ totalCount || "" }}</strong>{{ totalCount ? " 户" : "承包方" }}</template>
      </div>
      <div class="export-tools">
        <span class="export-selected">已选 {{ selectedDocuments.length }}/{{ options.length }} 项</span>
        <el-checkbox
          v-model="allSelected"
          :indeterminate="isIndeterminate"
        >全选</el-checkbox>
      </div>
    </div>

    <div class="export-options">
      <el-checkbox v-model="groupByIssuer">按发包方分组</el-checkbox>
      <span class="export-option-tip">压缩包内按文件类型分文件夹；勾选后先按发包方、再按文件类型分层</span>
    </div>

    <el-checkbox-group v-model="selectedDocuments" class="doc-grid">
      <el-checkbox
        v-for="option in options"
        :key="option.value"
        :label="option.value"
        class="doc-item"
      >
        <span class="doc-label">{{ option.label }}</span>
        <span class="doc-format" :class="option.format === 'Excel' ? 'is-excel' : 'is-word'">
          {{ option.format }}
        </span>
      </el-checkbox>
    </el-checkbox-group>

    <div class="export-tip">
      承包方信息表（Excel）为批量清单；摸底调查核实表按户各生成一份；Word 按户生成。多户或多类型时自动打包为 ZIP，ZIP 内按导出文件类型分文件夹。未勾选承包方时默认导出本批次全部承包方。
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        :loading="exporting"
        :disabled="!selectedDocuments.length || !batch"
        @click="handleExport"
      >
        导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { exportContractorDocuments } from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  batch: { type: Object, default: null },
  contractorUids: { type: Array, default: () => [] },
  totalCount: { type: Number, default: 0 },
});
const emit = defineEmits(["update:modelValue"]);

const options = [
  { value: "contractor_excel", label: "承包方信息表", format: "Excel" },
  { value: "baseline_verify_excel", label: "摸底调查核实表（单户）", format: "Excel" },
  { value: "contractor_word", label: "承包方调查表", format: "Word" },
  { value: "householder_declaration", label: "户主声明书", format: "Word" },
  { value: "authorization_declaration", label: "委托声明书", format: "Word" },
  { value: "no_objection_declaration", label: "无异议声明书", format: "Word" },
  { value: "survey_application", label: "测绘申请书", format: "Word" },
];

const selectedDocuments = ref(options.map((item) => item.value));
const groupByIssuer = ref(false);
const exporting = ref(false);

const allSelected = computed({
  get: () => selectedDocuments.value.length === options.length,
  set: (checked) => {
    selectedDocuments.value = checked ? options.map((item) => item.value) : [];
  },
});
const isIndeterminate = computed(
  () => selectedDocuments.value.length > 0 && selectedDocuments.value.length < options.length,
);

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      selectedDocuments.value = options.map((item) => item.value);
      groupByIssuer.value = false;
      exporting.value = false;
    }
  },
);

function filenameFromDisposition(disposition) {
  const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition || "");
  return match ? decodeURIComponent(match[1]) : "";
}

function downloadBlob(data, filename) {
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function handleExport() {
  if (!props.batch?.id || !selectedDocuments.value.length) {
    ElMessage.warning("请先选择导出内容");
    return;
  }
  exporting.value = true;
  try {
    const { data, headers } = await exportContractorDocuments(props.batch.id, {
      contractorUids: props.contractorUids,
      documents: selectedDocuments.value,
      groupByIssuer: groupByIssuer.value,
    });
    const contentType = String(headers?.["content-type"] || data?.type || "");
    let fallback = "承包方资料";
    if (contentType.includes("zip")) fallback += ".zip";
    else if (contentType.includes("excel")) fallback += ".xls";
    else fallback += ".docx";
    downloadBlob(data, filenameFromDisposition(headers?.["content-disposition"]) || fallback);
    ElMessage.success("导出完成");
    emit("update:modelValue", false);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导出失败，请稍后重试");
  } finally {
    exporting.value = false;
  }
}
</script>

<style scoped>
.export-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}

.export-count {
  color: var(--muted);
  font-size: 13px;
}

.export-count strong {
  color: var(--text);
  font-size: 15px;
}

.export-tools {
  display: flex;
  align-items: center;
  gap: 12px;
}

.export-options {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.export-option-tip {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
}

.export-selected {
  color: var(--muted);
  font-size: 12px;
}

.doc-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.doc-item {
  height: auto;
  margin-right: 0;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--panel-strong);
  transition: border-color 0.15s, background 0.15s;
}

.doc-item:hover {
  border-color: var(--accent);
}

.doc-item.is-checked {
  border-color: var(--accent);
  background: rgba(47, 143, 255, 0.06);
}

.doc-item :deep(.el-checkbox__label) {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  padding-left: 8px;
}

.doc-label {
  overflow: hidden;
  color: var(--text);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-format {
  flex: 0 0 auto;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 18px;
}

.doc-format.is-excel {
  color: #1f7a4d;
  background: rgba(55, 178, 108, 0.12);
}

.doc-format.is-word {
  color: #1e5fa8;
  background: rgba(47, 143, 255, 0.12);
}

.export-tip {
  margin-top: 10px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}
</style>
