<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    title="数据质检"
    width="860px"
    :close-on-click-modal="false"
    :show-close="jobStatus !== 'running'"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="resetDialog"
  >
    <!-- 运行中：进度 -->
    <div v-if="jobStatus === 'running'" class="qc-running">
      <el-progress :percentage="percentage" :stroke-width="14" striped striped-flow />
      <div class="phase-line">{{ job.phase || "正在启动…" }}</div>
      <div class="count-line">
        <span v-if="job.total">{{ job.done }} / {{ job.total }}</span>
        <span v-if="job.current">　当前：{{ job.current }}</span>
      </div>
      <div class="count-line qc-live-counts">
        <el-tag type="danger" size="small">错误 {{ job.counts?.error || 0 }}</el-tag>
        <el-tag type="warning" size="small">警告 {{ job.counts?.warn || 0 }}</el-tag>
      </div>
      <div class="tip-line">质检在后台执行，关闭弹窗不会中断任务；重新打开可查看历史记录。</div>
    </div>

    <!-- 完成：结果 -->
    <template v-else-if="jobStatus === 'done'">
      <div class="qc-summary">
        <el-result
          :icon="(runCounts.error || 0) > 0 ? 'warning' : 'success'"
          :title="`质检完成：错误 ${runCounts.error || 0} 条，警告 ${runCounts.warn || 0} 条`"
          :sub-title="runDuration"
        />
      </div>
      <div class="qc-result-toolbar">
        <el-radio-group v-model="severityFilter" size="small" @change="reloadRecords">
          <el-radio-button value="">全部（{{ recordTotal }}）</el-radio-button>
          <el-radio-button value="error">错误</el-radio-button>
          <el-radio-button value="warn">警告</el-radio-button>
          <el-radio-button value="info">提示</el-radio-button>
        </el-radio-group>
        <el-select v-model="itemFilter" size="small" clearable placeholder="质检项" style="width: 150px" @change="reloadRecords">
          <el-option v-for="item in checkItems" :key="item.key" :label="item.label" :value="item.key" />
        </el-select>
        <div class="qc-toolbar-spacer" />
        <el-button size="small" type="primary" plain :loading="exporting" @click="exportRecords">导出 Excel</el-button>
        <el-button size="small" plain @click="backToConfig">再查一次</el-button>
      </div>
      <el-table v-loading="recordLoading" :data="records" border stripe size="small" max-height="360">
        <el-table-column label="级别" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="severityTagType(row.severity)" size="small">{{ severityLabel(row.severity) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="checkItemLabel" label="质检项" width="110" show-overflow-tooltip />
        <el-table-column prop="cbfbm" label="承包方编码" width="150" show-overflow-tooltip />
        <el-table-column prop="dkbm" label="地块编码" width="155" show-overflow-tooltip />
        <el-table-column prop="message" label="问题描述" min-width="320" show-overflow-tooltip />
      </el-table>
      <div class="qc-pagination">
        <el-pagination
          v-model:current-page="recordPage"
          :page-size="recordPageSize"
          :total="recordTotal"
          layout="total, prev, pager, next"
          small
          @current-change="loadRecords"
        />
      </div>
    </template>

    <!-- 配置 / 历史 -->
    <template v-else>
      <div class="qc-config">
        <div class="qc-section-title">质检项目（参照原延包工具检查项）</div>
        <el-checkbox-group v-model="enabledItems" class="qc-items">
          <el-checkbox v-for="item in checkItems" :key="item.key" :value="item.key">
            <span class="qc-item-name">{{ item.label }}</span>
            <span class="qc-item-desc">{{ item.description }}</span>
          </el-checkbox>
        </el-checkbox-group>
        <div class="qc-config-actions">
          <el-button type="primary" :disabled="!enabledItems.length || !batch?.id" @click="start">
            开始质检
          </el-button>
        </div>
      </div>

      <div class="qc-history">
        <div class="qc-section-title">历史质检记录</div>
        <el-table v-loading="historyLoading" :data="historyRuns" border stripe size="small" max-height="240"
                  @row-click="openHistoryRun">
          <el-table-column label="检查时间" width="160">
            <template #default="{ row }">{{ formatDateTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="结果" align="center" width="180">
            <template #default="{ row }">
              <el-tag type="danger" size="small">错误 {{ row.counts?.error || 0 }}</el-tag>
              <el-tag type="warning" size="small" class="qc-tag-gap">警告 {{ row.counts?.warn || 0 }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="检查项" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">{{ runItemLabels(row.items) }}</template>
          </el-table-column>
        </el-table>
        <div v-if="!historyLoading && !historyRuns.length" class="tip-line">暂无历史记录，点击「开始质检」生成第一次检查。</div>
      </div>
    </template>

    <template #footer>
      <el-button v-if="jobStatus === 'running'" @click="emit('update:modelValue', false)">后台运行</el-button>
      <el-button v-else @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  exportQualityCheckRecords,
  fetchQualityCheckRecords,
  fetchQualityCheckRuns,
  getQualityCheckJob,
  startQualityCheckJob,
} from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  batch: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue"]);

// 与后端 CHECK_ITEMS 一致
const checkItems = [
  { key: "card_no", label: "证件号码重复", description: "全体家庭成员证件号码查重" },
  { key: "fbf", label: "发包方信息", description: "负责人、调查员、调查日期等完整性" },
  { key: "cbf", label: "承包方信息", description: "编码、证件、联系方式、家庭成员关系" },
  { key: "land", label: "承包地块信息", description: "地块编码、面积、四至、指界人、空间图形" },
  { key: "contract", label: "合同与权证", description: "承包地块与合同台账勾稽" },
];

const jobStatus = ref("idle"); // idle / running / done
const job = ref({});
const enabledItems = ref(checkItems.map((item) => item.key));
const runCounts = ref({});
const runDurationMs = ref(0);

const historyLoading = ref(false);
const historyRuns = ref([]);

const records = ref([]);
const recordLoading = ref(false);
const recordTotal = ref(0);
const recordPage = ref(1);
const recordPageSize = 50;
const severityFilter = ref("");
const itemFilter = ref("");
const activeRunId = ref("");

let pollTimer = null;

const percentage = computed(() => {
  const total = Number(job.value.total || 0);
  const done = Number(job.value.done || 0);
  if (!total) return 4;
  return Math.min(99, Math.round((done / total) * 95) + 4);
});

const runDuration = computed(() => {
  const ms = Number(runDurationMs.value || 0);
  if (!ms) return "";
  return ms >= 1000 ? `耗时 ${(ms / 1000).toFixed(1)} 秒` : `耗时 ${ms} 毫秒`;
});

function formatDateTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 19);
}

function severityTagType(severity) {
  return { error: "danger", warn: "warning", info: "info" }[severity] || "info";
}

function severityLabel(severity) {
  return { error: "错误", warn: "警告", info: "提示" }[severity] || severity;
}

function runItemLabels(items) {
  if (!items || !Object.keys(items).length) return "-";
  return checkItems.filter((item) => items[item.key]).map((item) => item.label).join("、");
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function resetDialog() {
  stopPoll();
  job.value = {};
  jobStatus.value = "idle";
  runCounts.value = {};
  runDurationMs.value = 0;
  records.value = [];
  recordTotal.value = 0;
  activeRunId.value = "";
  severityFilter.value = "";
  itemFilter.value = "";
}

async function loadHistory() {
  if (!props.batch?.id) return;
  historyLoading.value = true;
  try {
    const { data } = await fetchQualityCheckRuns(props.batch.id, { page: 1, pageSize: 10 });
    historyRuns.value = data.data.items || [];
  } catch {
    historyRuns.value = [];
  } finally {
    historyLoading.value = false;
  }
}

async function start() {
  if (!props.batch?.id) return;
  const items = {};
  checkItems.forEach((item) => { items[item.key] = enabledItems.value.includes(item.key); });
  jobStatus.value = "running";
  job.value = { phase: "正在创建质检任务…", counts: {} };
  try {
    const { data } = await startQualityCheckJob(props.batch.id, items);
    poll(data.data.jobId);
  } catch (error) {
    jobStatus.value = "idle";
    ElMessage.error(error.response?.data?.detail || "创建质检任务失败");
  }
}

function poll(jobId) {
  stopPoll();
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getQualityCheckJob(props.batch.id, jobId);
      const view = data.data;
      job.value = view;
      if (view.status === "done") {
        stopPoll();
        runCounts.value = view.counts || {};
        jobStatus.value = "done";
        activeRunId.value = view.runId || "";
        recordPage.value = 1;
        severityFilter.value = "";
        itemFilter.value = "";
        await loadRecords();
        loadHistory();
      } else if (view.status === "error") {
        stopPoll();
        ElMessage.error(view.error || "质检任务失败");
        jobStatus.value = "idle";
        loadHistory();
      }
    } catch (error) {
      stopPoll();
      ElMessage.error(error.response?.data?.detail || "查询质检进度失败");
      jobStatus.value = "idle";
    }
  }, 1000);
}

async function loadRecords() {
  if (!props.batch?.id || !activeRunId.value) return;
  recordLoading.value = true;
  try {
    const params = {
      page: recordPage.value,
      pageSize: recordPageSize,
    };
    if (severityFilter.value) params.severity = severityFilter.value;
    if (itemFilter.value) params.checkItem = itemFilter.value;
    const { data } = await fetchQualityCheckRecords(props.batch.id, activeRunId.value, params);
    records.value = data.data.items || [];
    recordTotal.value = data.data.total || 0;
  } catch {
    records.value = [];
    recordTotal.value = 0;
  } finally {
    recordLoading.value = false;
  }
}

function reloadRecords() {
  recordPage.value = 1;
  loadRecords();
}

const exporting = ref(false);

async function exportRecords() {
  if (!props.batch?.id || !activeRunId.value) return;
  exporting.value = true;
  try {
    const params = {};
    if (severityFilter.value) params.severity = severityFilter.value;
    if (itemFilter.value) params.checkItem = itemFilter.value;
    const { data, headers } = await exportQualityCheckRecords(props.batch.id, activeRunId.value, params);
    // 优先取响应头文件名，取不到用本地兜底名
    let filename = `数据质检记录_${formatDateTime(new Date().toISOString()).replaceAll(":", "").replaceAll("-", "").slice(0, 14)}.xls`;
    const disposition = headers?.["content-disposition"] || "";
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (match) filename = decodeURIComponent(match[1]);
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导出质检记录失败");
  } finally {
    exporting.value = false;
  }
}

function openHistoryRun(row) {
  activeRunId.value = row.runId;
  runCounts.value = row.counts || {};
  runDurationMs.value = row.durationMs || 0;
  recordPage.value = 1;
  severityFilter.value = "";
  itemFilter.value = "";
  jobStatus.value = "done";
}

function backToConfig() {
  jobStatus.value = "idle";
}

watch(() => props.modelValue, (visible) => {
  if (visible) {
    loadHistory();
  } else {
    stopPoll();
  }
});
</script>

<style scoped>
.qc-section-title {
  color: #1e293b;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}
.qc-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.qc-items :deep(.el-checkbox) {
  align-items: flex-start;
  height: auto;
  margin-right: 0;
  padding: 4px 0;
}
.qc-item-name {
  font-weight: 500;
}
.qc-item-desc {
  color: #94a3b8;
  font-size: 12px;
  margin-left: 8px;
}
.qc-config-actions {
  margin-top: 14px;
}
.qc-history {
  border-top: 1px solid #e2e8f0;
  margin-top: 16px;
  padding-top: 14px;
}
.qc-running {
  padding: 8px 4px;
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
.qc-live-counts {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.tip-line {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 12px;
}
.qc-summary :deep(.el-result) {
  padding: 12px 0;
}
.qc-result-toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}
.qc-toolbar-spacer {
  flex: 1;
}
.qc-tag-gap {
  margin-left: 6px;
}
.qc-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}
</style>
