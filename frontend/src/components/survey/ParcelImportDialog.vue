<template>
  <el-dialog
    :model-value="modelValue"
    title="导入承包地块数据"
    width="820px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="resetDialog"
  >
    <el-alert
      class="import-tip"
      type="info"
      :closable="false"
      show-icon
      :title="`导入范围：当前调查批次「${batch?.batchName || batch?.batchNo || ''}」，按承包方编码 / 地块编码匹配现有数据。`"
    />

    <el-radio-group v-model="importType" class="type-group" @change="resetPreview">
      <el-radio-button value="parcel_survey">地块调查表</el-radio-button>
      <el-radio-button value="baseline_survey">摸底核实表</el-radio-button>
      <el-radio-button value="vector">矢量图斑</el-radio-button>
    </el-radio-group>

    <div class="import-row">
      <input
        ref="fileInput"
        type="file"
        class="file-input"
        :accept="acceptTypes"
        @change="handleFileChange"
      />
      <el-button plain :icon="FolderOpened" @click="fileInput?.click()">选择文件</el-button>
      <span class="file-name">{{ fileName || fileHint }}</span>
      <el-button type="primary" :disabled="!file" :loading="previewing" @click="handlePreview">
        校验预览
      </el-button>
    </div>

    <el-form v-if="importType === 'baseline_survey'" label-width="120px" class="mode-form">
      <el-form-item label="覆盖方式">
        <el-select v-model="mode" style="width: 300px" @change="resetPreview">
          <el-option label="覆盖属性，保留图形数据" value="merge" />
          <el-option label="覆盖全部数据（按户替换）" value="replace" />
          <el-option label="只覆盖承包方数据" value="contractor_only" />
        </el-select>
      </el-form-item>
    </el-form>

    <template v-if="preview">
      <div class="summary-row">
        <el-tag type="primary">共 {{ preview.total || 0 }} 行</el-tag>
        <el-tag type="success">匹配 {{ preview.matched || 0 }}</el-tag>
        <el-tag v-if="preview.updatedContractors" type="warning">承包方 {{ preview.updatedContractors }}</el-tag>
        <el-tag v-if="preview.updatedMembers" type="warning">成员 {{ preview.updatedMembers }}</el-tag>
        <el-tag v-if="preview.updatedParcels" type="warning">地块 {{ preview.updatedParcels }}</el-tag>
        <el-tag v-if="preview.skipped" type="info">跳过 {{ preview.skipped }}</el-tag>
        <el-tag :type="preview.error ? 'danger' : 'info'">问题 {{ preview.error || 0 }}</el-tag>
      </div>

      <el-table
        v-if="preview.issues?.length"
        :data="preview.issues"
        border
        stripe
        size="small"
        max-height="260"
      >
        <el-table-column prop="row" label="行/序号" width="90" />
        <el-table-column prop="message" label="问题说明" min-width="400" show-overflow-tooltip />
      </el-table>
      <el-alert
        v-else
        type="success"
        :closable="false"
        show-icon
        title="校验通过，可以导入。"
      />
    </template>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!preview" :loading="importing" @click="handleImport">
        开始导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { FolderOpened } from "@element-plus/icons-vue";

import { importParcels, previewParcelImport } from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  batch: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue", "imported"]);

const fileInput = ref(null);
const file = ref(null);
const fileName = ref("");
const importType = ref("parcel_survey");
const mode = ref("merge");
const preview = ref(null);
const previewing = ref(false);
const importing = ref(false);

const acceptTypes = computed(() =>
  importType.value === "vector" ? ".zip" : ".xls,.xlt",
);
const fileHint = computed(() =>
  importType.value === "vector" ? "选择包含 .shp 的 ZIP 压缩包" : "选择 .xls / .xlt 文件",
);

function resetPreview() {
  preview.value = null;
  file.value = null;
  fileName.value = "";
  if (fileInput.value) fileInput.value.value = "";
}

function resetDialog() {
  importType.value = "parcel_survey";
  mode.value = "merge";
  resetPreview();
  previewing.value = false;
  importing.value = false;
}

function handleFileChange(event) {
  const selected = event.target.files?.[0];
  if (!selected) return;
  file.value = selected;
  fileName.value = selected.name;
  preview.value = null;
}

function buildFormData() {
  const formData = new FormData();
  formData.append("file", file.value);
  formData.append("importType", importType.value);
  formData.append("mode", mode.value);
  return formData;
}

async function handlePreview() {
  if (!props.batch?.id || !file.value) return;
  previewing.value = true;
  try {
    const { data } = await previewParcelImport(props.batch.id, buildFormData());
    preview.value = data.data;
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "校验失败，请检查文件格式");
  } finally {
    previewing.value = false;
  }
}

async function handleImport() {
  if (!props.batch?.id || !file.value || !preview.value) return;
  importing.value = true;
  try {
    const { data } = await importParcels(props.batch.id, buildFormData());
    const result = data.data || {};
    const parcelCount = result.updatedParcels
      ?? ((result.created || 0) + (result.updated || 0));
    ElMessage.success(
      `导入完成：更新承包方 ${result.updatedContractors || 0} 户、成员 ${result.updatedMembers || 0} 人、地块 ${parcelCount} 块`,
    );
    emit("imported", result);
    emit("update:modelValue", false);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导入失败，请检查文件和数据");
  } finally {
    importing.value = false;
  }
}
</script>

<style scoped>
.import-tip {
  margin-bottom: 12px;
}

.type-group {
  margin-bottom: 12px;
}

.import-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.file-input {
  display: none;
}

.file-name {
  flex: 1 1 auto;
  overflow: hidden;
  color: var(--muted);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mode-form {
  margin-bottom: 4px;
}

.summary-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0 10px;
}
</style>
