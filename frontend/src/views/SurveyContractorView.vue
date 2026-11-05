<template>
  <section class="panel table-page survey-contractor-page">
    <el-empty v-if="!activeBatch && !batchLoading" description="请先在「调查批次管理」中进入任务" />

    <template v-else>
      <div class="toolbar">
        <div class="panel-title">承包方管理</div>
        <div class="toolbar-actions">
          <el-input v-model="taskKeyword" :disabled="!activeBatch" clearable placeholder="搜索承包方" style="width: 220px" @keyup.enter="loadTasks" />
          <el-select v-model="taskStatus" :disabled="!activeBatch" clearable placeholder="调查状态" style="width: 160px" @change="loadTasks">
            <el-option label="未调查" value="not_started" />
            <el-option label="已调查" value="surveyed" />
            <el-option label="已确认" value="confirmed" />
            <el-option label="已跳过" value="skipped" />
          </el-select>
          <el-checkbox v-model="onlyMine" :disabled="!activeBatch" @change="loadTasks">只看我的</el-checkbox>
          <el-button :disabled="!activeBatch" :icon="Search" plain @click="loadTasks">查询</el-button>
          <el-button v-if="canManage" :disabled="!activeBatch || activeBatch?.status === 'finished'" :icon="Plus" type="primary" @click="openCreateContractor">新增</el-button>
          <el-tooltip placement="top" content="先在上表勾选承包方，再点此分配调查员" :disabled="Boolean(selectedTasks.length)">
            <el-button v-if="canManage" :disabled="assignDisabled" :icon="UserFilled" plain type="warning" @click="openAssign">
              分配任务<template v-if="selectedTasks.length">（{{ selectedTasks.length }}）</template>
            </el-button>
          </el-tooltip>
          <el-button :disabled="!activeBatch" plain @click="openDeregisteredDialog">已注销的承包方</el-button>
          <el-button :disabled="!activeBatch" plain @click="xlsExportVisible = true">承包户导出</el-button>
          <el-button v-if="canManage" :disabled="!activeBatch || activeBatch?.status === 'finished'" plain @click="xlsImportVisible = true">承包户导入</el-button>
        </div>
      </div>

      <el-table ref="taskTableRef" v-loading="taskLoading" :data="tasks" border stripe size="small" class="survey-table" @selection-change="handleSelectionChange">
        <el-table-column v-if="canManage" type="selection" width="44" fixed="left" :selectable="isTaskSelectable" />
        <el-table-column prop="cbfbm" label="泗洪承包方编码" width="160" show-overflow-tooltip />
        <el-table-column prop="cbfmc" label="承包方姓名" min-width="120" show-overflow-tooltip />
        <el-table-column prop="cbfdz" label="承包方地址" min-width="160" show-overflow-tooltip />
        <el-table-column prop="cbfcysl" label="成员数量" width="80" align="center" />
        <el-table-column prop="lxdh" label="联系电话" width="120" />
        <el-table-column label="调查状态" width="100">
          <template #default="{ row }"><el-tag :type="surveyStatusTagType(row.taskStatus)" size="small">{{ taskStatusLabel(row.taskStatus) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="调查员" width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tooltip v-if="row.assignedToName" placement="top" :content="assigneeTooltip(row)">
              <span class="survey-assignee">{{ row.assignedToName }}</span>
            </el-tooltip>
            <el-tooltip v-else-if="row.investigatorName" placement="top" :content="`尚未分配归属人　实际录入：${row.investigatorName}`">
              <el-tag size="small" type="info" effect="plain">未分配</el-tag>
            </el-tooltip>
            <el-tag v-else size="small" type="info" effect="plain">未分配</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right" class-name="survey-action-column">
          <template #default="{ row }">
            <div class="survey-row-actions">
              <el-tooltip v-if="row.canWrite === false" placement="top" :content="row.assignedToName ? `已分配给${row.assignedToName}，只能查看详细信息` : '尚未分配调查员，只能查看详细信息；请先分配调查员后再录入'">
                <el-button link type="warning" @click="openResult(row)">查看详情</el-button>
              </el-tooltip>
              <el-button v-else link type="primary" @click="openResult(row)">调查录入</el-button>
              <el-button v-if="canManage && CONFIRMABLE_SURVEY_STATUSES.includes(row.taskStatus)" link type="success" @click="handleConfirmTask(row)">确认</el-button>
              <el-button v-if="canManage && row.canWrite !== false && activeBatch?.status !== 'finished' && !TERMINAL_SURVEY_STATUSES.includes(row.taskStatus)" link type="warning" @click="handleSkipTask(row)">跳过</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <ContractorResultDialog
      ref="contractorResultDialog"
      v-model="resultVisible"
      :active-batch="activeBatch"
      :can-manage="canManage"
      :can-write="activeTaskCanWrite"
      :tasks="tasks"
      :active-region-code="activeRegionCode"
      :active-region-label="activeRegionLabel"
      @saved="onResultSaved"
      @confirmed="onResultSaved"
      @open-contractor="onOpenCreatedContractor"
    />
    <DeregisteredContractorsDialog ref="deregisteredDialog" :active-batch="activeBatch" :can-manage="canManage" @restored="onResultSaved" />
    <TaskAssignDialog ref="taskAssignDialog" :active-batch="activeBatch" @assigned="onTasksAssigned" />
    <ContractorXlsImportDialog v-model="xlsImportVisible" :batch="activeBatch" @imported="loadTasks" />
    <ContractorXlsExportDialog v-model="xlsExportVisible" :batch="activeBatch" />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Search, UserFilled } from "@element-plus/icons-vue";

import ContractorResultDialog from "../components/survey/view/ContractorResultDialog.vue";
import DeregisteredContractorsDialog from "../components/survey/view/DeregisteredContractorsDialog.vue";
import TaskAssignDialog from "../components/survey/view/TaskAssignDialog.vue";
import ContractorXlsImportDialog from "../components/survey/ContractorXlsImportDialog.vue";
import ContractorXlsExportDialog from "../components/survey/ContractorXlsExportDialog.vue";

import {
  confirmSurveyResult,
  fetchCurrentSurveyBatch,
  fetchSurveyBatches,
  fetchSurveyTasks,
  skipSurveyTask,
} from "../api/survey";
import { CONFIRMABLE_SURVEY_STATUSES, TERMINAL_SURVEY_STATUSES } from "../config/surveyStatus";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));

const batchLoading = ref(false);
const batches = ref([]);
const activeBatch = ref(null);

const taskLoading = ref(false);
const tasks = ref([]);
const taskKeyword = ref("");
const taskStatus = ref("");
const onlyMine = ref(false);
const selectedTasks = ref([]);
const taskTableRef = ref(null);

const resultVisible = ref(false);
const activeTaskCanWrite = ref(true);
const contractorResultDialog = ref(null);
const deregisteredDialog = ref(null);
const taskAssignDialog = ref(null);
const xlsImportVisible = ref(false);
const xlsExportVisible = ref(false);

const activeRegionCode = computed(() => activeBatch.value?.regionCode || "");
const activeRegionLabel = computed(() => activeBatch.value?.regionName || "");
const assignDisabled = computed(
  () => !activeBatch.value || activeBatch.value.status === "finished" || !selectedTasks.value.length,
);

function formatDateTime(value) { if (!value) return "-"; return String(value).replace("T", " ").slice(0, 19); }
function taskStatusLabel(value) { return { not_started: "未调查", not_surveyed: "未调查", in_progress: "调查中", surveyed: "已调查", changed: "有变化", unchanged: "无变化", confirmed: "已确认", skipped: "已跳过", deregistered: "已注销" }[value] || value; }
function surveyStatusTagType(value) { return { not_started: "info", not_surveyed: "info", surveyed: "success", confirmed: "primary", skipped: "warning", deregistered: "danger" }[value] || "info"; }
function isTaskSelectable(row) { return !["confirmed", "deregistered"].includes(row?.taskStatus); }
function assigneeTooltip(row) {
  const parts = [];
  if (row?.assignedAt) parts.push(`分配时间：${formatDateTime(row.assignedAt)}`);
  if (row?.investigatorName && row.investigatorName !== row.assignedToName) parts.push(`实际录入：${row.investigatorName}`);
  return parts.join("　") || "已分配";
}

function buildRegionParams() {
  const regionCode = activeBatch.value?.regionCode;
  return regionCode ? { regionCode } : {};
}

async function loadBatches() {
  batchLoading.value = true;
  try {
    const { data } = await fetchSurveyBatches({ page: 1, page_size: 100 });
    batches.value = data.data.items || [];
    if (!activeBatch.value) {
      try {
        const current = await fetchCurrentSurveyBatch();
        if (current.data.data) {
          activeBatch.value = current.data.data;
        }
      } catch { /* 忽略：回退到第一个批次 */ }
    }
    if (!activeBatch.value && batches.value.length) {
      activeBatch.value = batches.value[0];
    }
    await loadTasks();
  } finally { batchLoading.value = false; }
}

async function loadTasks() {
  if (!activeBatch.value) { tasks.value = []; return; }
  taskLoading.value = true;
  try {
    const { data } = await fetchSurveyTasks(activeBatch.value.id, {
      page: 1,
      page_size: 100,
      keyword: taskKeyword.value || undefined,
      taskStatus: taskStatus.value || undefined,
      mine: onlyMine.value ? 1 : undefined,
      ...buildRegionParams(),
    });
    tasks.value = data.data.items || [];
  } finally { taskLoading.value = false; }
}

function handleSelectionChange(rows) { selectedTasks.value = rows || []; }
function openAssign() { if (!activeBatch.value || !selectedTasks.value.length) return; taskAssignDialog.value.open(selectedTasks.value); }
function onTasksAssigned() { selectedTasks.value = []; taskTableRef.value?.clearSelection(); loadTasks(); }

function openResult(row) {
  activeTaskCanWrite.value = row?.canWrite !== false;
  contractorResultDialog.value.openForResult(activeBatch.value, row);
}
function openCreateContractor() { if (!activeBatch.value) return; activeTaskCanWrite.value = true; contractorResultDialog.value.openForCreate(activeBatch.value); }
function openDeregisteredDialog() { if (!activeBatch.value) return; deregisteredDialog.value.open(); }
function onResultSaved() { loadTasks(); }

async function onOpenCreatedContractor(target) {
  if (!activeBatch.value || !target) return;
  await loadTasks();
  let row = tasks.value.find((t) => target.contractorUid && t.contractorUid === target.contractorUid)
    || tasks.value.find((t) => target.cbfbm && t.cbfbm === target.cbfbm);
  if (!row) {
    try {
      const { data } = await fetchSurveyTasks(activeBatch.value.id, { page: 1, page_size: 20, keyword: target.cbfbm || undefined, ...buildRegionParams() });
      const items = data.data.items || [];
      row = items.find((t) => t.contractorUid === target.contractorUid) || items[0];
    } catch { /* 查询失败就落到下面那句提示 */ }
  }
  if (row) { openResult(row); return; }
  ElMessage.warning(`新承包方「${target.cbfmc || target.cbfbm || ""}」已生成，但不在当前任务列表筛选结果中，请按编码 ${target.cbfbm || ""} 搜索。`);
}

async function handleConfirmTask(row) {
  try { await confirmSurveyResult(row.batchId, row.contractorUid); ElMessage.success("调查结果已确认"); await loadTasks(); } catch (error) { ElMessage.error(error.response?.data?.detail || "确认失败"); }
}

async function handleSkipTask(row) {
  try {
    const { value } = await ElMessageBox.prompt("请输入跳过原因", "跳过调查任务", { inputType: "textarea", inputPlaceholder: "例如：本轮调查无需处理、非本区域调查对象等", inputValidator: (text) => Boolean(text?.trim()) || "请输入跳过原因", confirmButtonText: "跳过", cancelButtonText: "取消", type: "warning" });
    await skipSurveyTask(row.batchId, row.contractorUid, { skipReason: value.trim() });
    ElMessage.success("调查任务已跳过"); await loadTasks();
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(error.response?.data?.detail || "跳过失败"); }
}

onMounted(loadBatches);
</script>

<style scoped>
.survey-contractor-page {
  min-height: 0;
}
</style>
