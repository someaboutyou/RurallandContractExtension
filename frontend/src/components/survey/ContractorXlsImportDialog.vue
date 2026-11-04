<template>
  <el-dialog
    :model-value="modelValue"
    title="导入承包方调查表（Excel）"
    width="920px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="resetDialog"
  >
    <el-alert
      class="import-tip"
      type="info"
      :closable="false"
      show-icon
      :title="`批次「${batch?.batchName || batch?.batchNo || ''}」区域码：${batch?.regionCode || '未配置'}`"
      description="请使用本系统「承包户导出」生成的 Excel 修改后导入：逐户校验承包方编号（须以批次区域码开头），成员按证件号码对比修改 / 新增；删除成员＝将该成员行的「姓名」单元格填充底色或加删除线；删除整户＝将该户「承包方姓名」单元格填充底色或加删除线（整户注销，底档保留可在注销列表撤回）；其余库内成员原样保留。导入后各户调查状态置为已调查；已确认的户自动跳过。"
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
        <el-tag type="primary">共 {{ preview.totalHouseholds }} 户</el-tag>
        <el-tag type="success">新增 {{ preview.summary.create || 0 }}</el-tag>
        <el-tag type="warning">更新 {{ preview.summary.update || 0 }}</el-tag>
        <el-tag type="info">无变化 {{ preview.summary.no_change || 0 }}</el-tag>
        <el-tag type="info">跳过 {{ preview.summary.skipped || 0 }}</el-tag>
        <el-tag :type="preview.summary.error ? 'danger' : 'info'">错误 {{ preview.summary.error || 0 }}</el-tag>
        <el-tag v-if="preview.summary.deregister" type="danger">注销整户 {{ preview.summary.deregister }}</el-tag>
        <el-tag v-if="previewDeleteCount" type="danger">删除成员 {{ previewDeleteCount }} 名</el-tag>
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
      <el-table :data="preview.households" border stripe size="small" max-height="380" class="report-table">
        <el-table-column prop="rowIndex" label="行号" width="70" />
        <el-table-column prop="cbfbm" label="承包方编号" width="160" show-overflow-tooltip />
        <el-table-column prop="cbfmc" label="承包方姓名" width="110" show-overflow-tooltip />
        <el-table-column label="动作" width="90">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" size="small">{{ actionLabel(row.action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="变化明细" min-width="240">
          <template #default="{ row }">
            <span v-if="row.action === 'skipped'">{{ row.message }}</span>
            <span v-else-if="row.action === 'deregister'" class="delete-line">整户注销</span>
            <template v-else>
              <div v-if="row.contractorChanges?.length" class="change-line">承包方：{{ row.contractorChanges.join("、") }}</div>
              <div v-if="row.memberSummary?.added?.length" class="change-line">新增成员：{{ row.memberSummary.added.join("、") }}</div>
              <div v-if="row.memberSummary?.updated?.length" class="change-line">修改成员：{{ row.memberSummary.updated.join("；") }}</div>
              <div v-if="row.memberSummary?.deleted?.length" class="delete-line">删除成员：{{ row.memberSummary.deleted.join("、") }}</div>
              <span v-if="!row.contractorChanges?.length && !row.memberSummary?.added?.length && !row.memberSummary?.updated?.length && !row.memberSummary?.deleted?.length">—</span>
            </template>
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

    <!-- 第三步：导入进度（后台任务轮询） -->
    <template v-else-if="step === 'progress'">
      <el-progress :percentage="percentage" :stroke-width="14" striped striped-flow />
      <div class="phase-line">{{ job.phase || "正在启动…" }}</div>
      <div v-if="job.total" class="count-line">
        {{ job.done }} / {{ job.total }} 户<span v-if="job.current">　当前：{{ job.current }}</span>
      </div>
      <div class="tip-line">导入逐户执行、逐户保存：单户失败不影响其他户。请保持弹窗开启直至完成。</div>
    </template>

    <!-- 第四步：导入结果 -->
    <template v-else-if="step === 'result' && result">
      <div class="summary-row">
        <el-tag type="success">新增 {{ result.summary.created || 0 }}</el-tag>
        <el-tag type="warning">更新 {{ result.summary.updated || 0 }}</el-tag>
        <el-tag type="info">无变化 {{ result.summary.no_change || 0 }}</el-tag>
        <el-tag type="info">跳过 {{ result.summary.skipped || 0 }}</el-tag>
        <el-tag :type="result.summary.failed ? 'danger' : 'info'">失败 {{ result.summary.failed || 0 }}</el-tag>
        <el-tag v-if="result.summary.deregistered" type="danger">注销整户 {{ result.summary.deregistered }}</el-tag>
      </div>
      <el-table :data="result.households" border stripe size="small" max-height="380" class="report-table">
        <el-table-column prop="rowIndex" label="行号" width="70" />
        <el-table-column prop="cbfbm" label="承包方编号" width="160" show-overflow-tooltip />
        <el-table-column prop="cbfmc" label="承包方姓名" width="110" show-overflow-tooltip />
        <el-table-column label="结果" width="80">
          <template #default="{ row }">
            <el-tag :type="resultTagType(row.status)" size="small">{{ resultLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="说明" min-width="280" show-overflow-tooltip />
      </el-table>
    </template>

    <template #footer>
      <template v-if="step === 'progress'">
        <el-button disabled>导入中…</el-button>
      </template>
      <template v-else-if="step === 'preview'">
        <el-button @click="backToUpload">重新选择文件</el-button>
        <el-button
          type="primary"
          :disabled="batch?.status === 'finished'"
          @click="doImport"
        >
          {{ preview.summary.error ? `仍要导入（${preview.summary.error} 户错误将被跳过）` : '确认导入' }}
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
import { computed, onBeforeUnmount, ref } from "vue";
import { ElMessage } from "element-plus";
import { FolderOpened } from "@element-plus/icons-vue";
import { getXlsImportJob, previewContractorSurveyXls, startXlsImportJob } from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  batch: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue", "imported"]);

const fileInput = ref(null);
const file = ref(null);
const fileName = ref("");
const step = ref("upload");
const previewLoading = ref(false);
const preview = ref(null);
const result = ref(null);
const job = ref({});
let pollTimer = null;

const percentage = computed(() => {
  const total = Number(job.value.total || 0);
  if (!total) return 5;
  return Math.min(99, Math.round((Number(job.value.done || 0) / total) * 95) + 4);
});

const previewDeleteCount = computed(() =>
  (preview.value?.households || []).reduce((sum, h) => sum + (h.memberSummary?.deleted?.length || 0), 0),
);

function resetDialog() {
  stopPoll();
  file.value = null;
  fileName.value = "";
  step.value = "upload";
  preview.value = null;
  result.value = null;
  job.value = {};
  if (fileInput.value) fileInput.value.value = "";
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

onBeforeUnmount(stopPoll);

function handleFileChange(event) {
  const selected = event.target.files?.[0];
  if (!selected) return;
  if (!/\.xls$/i.test(selected.name)) {
    ElMessage.warning("请选择 .xls 文件（承包户导出生成的即为此格式）");
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
    // ⛔ 接口统一包 {"data": …} 信封：这里必须取 data.data，否则预览页全是 undefined
    const { data } = await previewContractorSurveyXls(props.batch.id, buildFormData());
    preview.value = data.data;
    step.value = "preview";
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "校验失败，请检查文件格式");
  } finally {
    previewLoading.value = false;
  }
}

async function doImport() {
  step.value = "progress";
  job.value = { phase: "正在上传并创建导入任务…" };
  try {
    const { data } = await startXlsImportJob(props.batch.id, buildFormData());
    pollImport(data.data.jobId);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "创建导入任务失败");
    step.value = "preview";
  }
}

function pollImport(jobId) {
  stopPoll();
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getXlsImportJob(props.batch.id, jobId);
      const view = data.data;
      job.value = view;
      if (view.status === "done") {
        stopPoll();
        result.value = { summary: view.summary || {}, households: view.results || [], warnings: view.warnings || [] };
        step.value = "result";
        emit("imported");
      } else if (view.status === "error") {
        stopPoll();
        ElMessage.error(view.error || "导入失败");
        step.value = "preview";
      }
    } catch (error) {
      stopPoll();
      ElMessage.error(error.response?.data?.detail || "查询导入进度失败");
      step.value = "preview";
    }
  }, 1000);
}

function finish() {
  emit("update:modelValue", false);
}

const ACTION_LABELS = { create: "新增户", update: "更新", no_change: "无变化", skipped: "跳过", error: "错误", deregister: "注销" };
const ACTION_TAG_TYPES = { create: "success", update: "warning", no_change: "info", skipped: "info", error: "danger", deregister: "danger" };
const RESULT_LABELS = { created: "新增", updated: "更新", no_change: "无变化", skipped: "跳过", failed: "失败", deregistered: "注销" };
const RESULT_TAG_TYPES = { created: "success", updated: "warning", no_change: "info", skipped: "info", failed: "danger", deregistered: "danger" };

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
.phase-line {
  color: #1e293b;
  font-size: 14px;
  margin-top: 14px;
}
.count-line {
  color: #64748b;
  font-size: 13px;
  margin-top: 4px;
}
.tip-line {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 12px;
}
.change-line,
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
