<template>
  <div class="survey-page">
    <section class="panel survey-batch-panel">
      <div class="batch-panel-header">
        <div class="panel-title">调查批次</div>
        <div class="batch-panel-actions">
          <el-select v-model="batchSurveyStatus" clearable placeholder="调查状态" class="batch-header-filter">
            <el-option label="未调查" value="not_started" />
            <el-option label="调查中" value="in_progress" />
            <el-option label="已调查" value="surveyed" />
            <el-option label="已确认" value="confirmed" />
            <el-option label="已跳过" value="skipped" />
          </el-select>
          <el-tooltip content="新建调查批次" placement="top">
            <el-button v-if="canManage" :icon="Plus" circle type="success" @click="openCreateBatch" />
          </el-tooltip>
        </div>
      </div>
      <!-- 「按调查员筛选批次」只有管理员有：这是「看别人负责的批次」的入口，
           非管理员应聚焦与自己相关的批次（后端仍会按区域授权 ∪ 与我相关给出数据）。 -->
      <el-select
        v-if="showAssigneeFilter"
        v-model="batchAssigneeId"
        clearable
        filterable
        :loading="assigneeLoading"
        class="batch-assignee-filter"
        placeholder="按调查员筛选批次"
        @change="loadBatches"
        @clear="loadBatches"
      >
        <el-option v-for="user in assigneeOptions" :key="user.id" :value="user.id" :label="user.realName" />
      </el-select>
      <el-input v-model="batchKeyword" :prefix-icon="Search" clearable placeholder="搜索批次" class="batch-search" @keyup.enter="loadBatches" @clear="loadBatches" />
      <!-- 调查员视角：只看与我相关的批次（我创建的 / 有户分给我的）。
           勾上后不再叠加区域筛选——批次可能落在我的授权范围内、却不以我所属区域码开头。 -->
      <el-checkbox
        v-if="showMineBatchFilter"
        v-model="mineOnlyBatches"
        class="batch-mine-filter"
        @change="loadBatches"
      >
        只看与我相关的批次
      </el-checkbox>
      <div v-loading="batchLoading" class="batch-card-list">
        <el-empty v-if="!filteredBatches.length && !batchLoading" description="暂无调查批次" :image-size="88" />
        <el-tooltip v-for="batch in filteredBatches" :key="batch.id" placement="right" effect="light" :show-after="250" popper-class="batch-detail-tooltip">
          <template #content>
            <div class="batch-tooltip-content">
              <div><span>批次号</span>{{ batch.batchNo || "-" }}</div>
              <div><span>创建时间</span>{{ formatDateTime(batch.createdAt) }}</div>
              <div><span>调查区域</span>{{ batch.regionName || batch.regionCode || "-" }}</div>
              <div><span>调查员</span>{{ assigneeSummary(batch) }}</div>
              <div><span>待分配</span>{{ batch.unassignedCount || 0 }} 户</div>
              <div><span>已调查</span>{{ batch.surveyedCount || 0 }} 户</div>
              <div><span>有变化</span>{{ batch.changedCount || 0 }} 户</div>
              <div><span>已确认</span>{{ batch.confirmedCount || 0 }} 户</div>
              <div><span>已跳过</span>{{ batch.skippedCount || 0 }} 户</div>
            </div>
          </template>
          <button type="button" class="batch-card" :class="{ 'is-active': activeBatch?.id === batch.id }" @click="handleBatchSelect(batch)">
            <span class="batch-card-title">{{ batch.batchName || batch.batchNo }}</span>
            <span class="batch-card-status-row">
              <el-tag :type="batchStatusType(batch.status)" size="small">{{ batchStatusLabel(batch.status) }}</el-tag>
              <span class="batch-card-progress">{{ batchSurveySummary(batch) }}</span>
            </span>
            <span v-if="batch.createdByMe || batch.assignedToMe" class="batch-card-badges">
              <el-tag v-if="batch.createdByMe" size="small" type="success" effect="plain">我创建</el-tag>
              <el-tag v-if="batch.assignedToMe" size="small" type="primary" effect="plain">分给我 {{ batch.myTaskCount }} 户</el-tag>
            </span>
            <span class="batch-card-assignee" :class="{ 'is-empty': !batch.assigneeCount }">
              调查员：{{ assigneeSummary(batch) }}
            </span>
            <span v-if="batch.unassignedCount" class="batch-card-unassigned">
              还有 {{ batch.unassignedCount }} 户待分配，请及时改派
            </span>
            <span class="batch-card-metrics">
              <span><b>{{ batch.taskCount || 0 }}</b> 应调查户数</span>
              <span><b>{{ batch.surveyedCount || 0 }}</b> 已调查</span>
            </span>
          </button>
        </el-tooltip>
      </div>
      <div class="batch-footer-actions">
        <el-button :disabled="!activeBatch" :icon="Download" plain type="primary" @click="handleExportResults">导出</el-button>
        <el-button v-if="canFinishBatch" :disabled="!activeBatch || activeBatch.status === 'finished'" :icon="CircleCheck" plain type="warning" @click="handleFinishBatch">结束</el-button>
      </div>
    </section>

    <section class="panel table-page survey-work-panel">
      <el-tabs v-model="surveyPanelTab" class="survey-work-tabs">
        <el-tab-pane label="承包方调查" name="contractor">
          <div class="toolbar">
            <div class="panel-title">{{ taskPanelTitle }}</div>
            <div class="toolbar-actions">
              <el-input v-model="taskKeyword" :disabled="!activeBatch" clearable placeholder="搜索承包方" style="width: 220px" @keyup.enter="loadTasks" />
              <el-select v-model="taskStatus" :disabled="!activeBatch" clearable placeholder="调查状态" style="width: 160px" @change="loadTasks">
                <el-option label="未调查" value="not_started" /><el-option label="已调查" value="surveyed" /><el-option label="已确认" value="confirmed" /><el-option label="已跳过" value="skipped" />
              </el-select>
              <el-checkbox v-model="onlyMine" :disabled="!activeBatch" @change="handleOnlyMineChange">只看我的</el-checkbox>
              <el-button :disabled="!activeBatch" :icon="Search" plain @click="loadTasks">查询</el-button>
              <el-button v-if="canManage" :disabled="!activeBatch || activeBatch?.status === 'finished'" :icon="Plus" type="primary" @click="openCreateContractor">新增</el-button>
              <el-tooltip placement="top" content="先在上表勾选承包方，再点此分配调查员" :disabled="Boolean(selectedTasks.length)">
                <el-button v-if="canManage" :disabled="assignDisabled" :icon="UserFilled" plain type="warning" @click="openAssign">
                  分配任务<template v-if="selectedTasks.length">（{{ selectedTasks.length }}）</template>
                </el-button>
              </el-tooltip>
              <el-button :disabled="!activeBatch" plain @click="openDeregisteredDialog">已注销的承包方</el-button>
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
                <!-- 未分配归属人但已有人录入时，把实际录入人放进 tooltip：
                     否则「已经调查过的户仍然写未分配」很容易被误判成显示逻辑出错。 -->
                <el-tooltip v-else-if="row.investigatorName" placement="top" :content="`尚未分配归属人　实际录入：${row.investigatorName}`">
                  <el-tag size="small" type="info" effect="plain">未分配</el-tag>
                </el-tooltip>
                <el-tag v-else size="small" type="info" effect="plain">未分配</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="260" fixed="right" class-name="survey-action-column">
              <template #default="{ row }">
                <div class="survey-row-actions">
                  <!-- 未分配 / 已分给别人的户：入口保留但只读查看（后端 Save 也会 403 兜底）。 -->
                  <el-tooltip v-if="row.canWrite === false" placement="top" :content="row.assignedToName ? `已分配给${row.assignedToName}，只能查看详细信息` : '尚未分配调查员，只能查看详细信息；请先分配调查员后再录入'">
                    <el-button link type="warning" @click="openResult(row)">查看详情</el-button>
                  </el-tooltip>
                  <el-button v-else link type="primary" @click="openResult(row)">调查录入</el-button>
                  <el-button v-if="canManage && row.taskStatus === 'surveyed'" link type="success" @click="handleConfirmTask(row)">确认</el-button>
                  <el-button v-if="canManage && row.canWrite !== false && activeBatch?.status !== 'finished' && row.taskStatus !== 'confirmed' && row.taskStatus !== 'skipped'" link type="warning" @click="handleSkipTask(row)">跳过</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="发包方调查" name="issuer">
          <div class="toolbar">
            <div class="panel-title">发包方调查</div>
            <div class="toolbar-actions">
              <el-input v-model="issuerKeyword" :disabled="!activeBatch" clearable placeholder="搜索发包方" style="width: 220px" />
              <el-button :disabled="!activeBatch" :icon="Search" plain @click="loadIssuerSurveyRows(true)">查询</el-button>
              <el-button v-if="canManage" :disabled="!activeBatch || activeBatch?.status === 'finished'" :icon="Plus" type="primary" @click="openCreateIssuer">新增</el-button>
            </div>
          </div>
          <el-table v-loading="issuerLoading" :data="filteredIssuerRows" border stripe size="small" class="survey-table">
            <el-table-column prop="code" label="发包方编码" width="150" show-overflow-tooltip />
            <el-table-column prop="name" label="发包方名称" min-width="160" show-overflow-tooltip />
            <el-table-column prop="responsibleName" label="负责人" width="100" />
            <el-table-column prop="phone" label="联系电话" width="120" />
            <el-table-column label="操作" width="120" fixed="right" class-name="survey-action-column">
              <template #default="{ row }">
                <div class="survey-row-actions">
                  <el-button link type="primary" @click="openIssuerSurvey(row)">进入调查</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </section>

    <BatchCreateDialog ref="batchCreateDialog" v-model="batchDialogVisible" @created="onBatchCreated" />
    <ContractorResultDialog ref="contractorResultDialog" v-model="resultVisible" :active-batch="activeBatch" :can-manage="canManage" :can-write="activeTaskCanWrite" :tasks="tasks" :active-region-code="activeRegionCode" :active-region-label="activeRegionLabel" @saved="onResultSaved" @confirmed="onResultSaved" />
    <IssuerSurveyDialog ref="issuerSurveyDialog" v-model="issuerSurveyVisible" :active-batch="activeBatch" :can-manage="canManage" @saved="onIssuerSurveySaved" />
    <DeregisteredContractorsDialog ref="deregisteredDialog" :active-batch="activeBatch" :can-manage="canManage" @restored="onResultSaved" />
    <TaskAssignDialog ref="taskAssignDialog" :active-batch="activeBatch" @assigned="onTasksAssigned" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { CircleCheck, Download, Plus, Search, UserFilled } from "@element-plus/icons-vue";

import BatchCreateDialog from "../components/survey/view/BatchCreateDialog.vue";
import ContractorResultDialog from "../components/survey/view/ContractorResultDialog.vue";
import DeregisteredContractorsDialog from "../components/survey/view/DeregisteredContractorsDialog.vue";
import IssuerSurveyDialog from "../components/survey/view/IssuerSurveyDialog.vue";
import TaskAssignDialog from "../components/survey/view/TaskAssignDialog.vue";

import { fetchSurveyBatches, fetchSurveyAssignees, fetchSurveyTasks, fetchSurveyIssuers, finishSurveyBatch, exportSurveyResults, confirmSurveyResult, skipSurveyTask } from "../api/survey";
import { fetchRegionTree } from "../api/region";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));

// ---- Batch state ----
const batchLoading = ref(false);
const batches = ref([]);
const batchKeyword = ref("");
const batchSurveyStatus = ref("");
// 管理员判据（data_scope=all）：多处共用，统一在这里定义，别再各写一遍字符串比较。
const isAdmin = computed(() => authStore.user?.dataScope === "all");
// 管理员才有的「按调查员筛选批次」下拉。⛔ 判据是**管理员**（data_scope=all），
// 不是 contractors.manage 权限：镇级业务员也有 manage 权限，但不该看到别人负责的批次。
const batchAssigneeId = ref(null);
const assigneeOptions = ref([]);
const assigneeLoading = ref(false);
const showAssigneeFilter = computed(() => isAdmin.value);
// 「只看与我相关的批次」：管理员（data_scope=all）本来就看得见全部，不显示这个开关。
const mineOnlyBatches = ref(false);
const showMineBatchFilter = computed(() => !isAdmin.value);
const activeBatch = ref(null);
const batchDialogVisible = ref(false);

const filteredBatches = computed(() => {
  if (!batchSurveyStatus.value) return batches.value;
  return batches.value.filter((batch) => batchSurveyStatusValue(batch) === batchSurveyStatus.value);
});

const taskPanelTitle = computed(() => {
  if (!activeBatch.value) return "调查任务";
  return activeBatch.value.batchName || "调查任务";
});

// ---- Task state ----
const taskLoading = ref(false);
const tasks = ref([]);
const taskKeyword = ref("");
const taskStatus = ref("");
const onlyMine = ref(false);
const selectedTasks = ref([]);
const taskTableRef = ref(null);

const assignDisabled = computed(
  () => !activeBatch.value || activeBatch.value.status === "finished" || !selectedTasks.value.length,
);

// 「结束批次」判据与后端 `_ensure_batch_manager` 同源：管理员 / 本批次创建人。
// ⛔ 不能沿用 canManage（contractors.manage）——镇级业务员也有该权限，
// 会变成"按钮点得动、点下去 403"，正是「分配任务」上一版踩过的坑。
// （分配任务不在此列：后端 `_ensure_batch_assigner` 已放宽到"数据权限覆盖本批次区域"。）
const canFinishBatch = computed(
  () => canManage.value && (isAdmin.value || activeBatch.value?.createdByMe === true),
);

// ---- Issuer state ----
const issuerLoading = ref(false);
const issuerRows = ref([]);
const issuerKeyword = ref("");
const issuerSurveyVisible = ref(false);

const filteredIssuerRows = computed(() => {
  const keyword = issuerKeyword.value.trim().toLowerCase();
  if (!keyword) return issuerRows.value;
  return issuerRows.value.filter((row) =>
    [row.code, row.name, row.responsibleName, row.surveyorName].some((v) => String(v || "").toLowerCase().includes(keyword)),
  );
});

// ---- Region state ----
const regionTree = ref([]);
const regionTreeProps = { label: "fullName", children: "children" };
const activeRegionId = ref(undefined);
const activeRegionCode = ref("");
const activeRegionLabel = ref("");

// ---- Panel state ----
const surveyPanelTab = ref("contractor");
const resultVisible = ref(false);

// ---- Component refs ----
const batchCreateDialog = ref(null);
const contractorResultDialog = ref(null);
const deregisteredDialog = ref(null);
const issuerSurveyDialog = ref(null);
const taskAssignDialog = ref(null);

// ---- Helpers ----
function formatDateTime(value) { if (!value) return "-"; return String(value).replace("T", " ").slice(0, 19); }
function batchStatusLabel(value) { return { active: "进行中", finished: "已结束", draft: "草稿" }[value] || value || "-"; }
function batchStatusType(value) { return { active: "success", finished: "info", draft: "warning" }[value] || "info"; }
function batchSurveySummary(batch) { const total = Number(batch.taskCount || 0); if (!total) return "暂无任务"; return `${Number(batch.surveyedCount || 0)}/${total} 已调查`; }
function batchSurveyStatusValue(batch) {
  const total = Number(batch.taskCount || 0); const surveyed = Number(batch.surveyedCount || 0);
  const confirmed = Number(batch.confirmedCount || 0); const skipped = Number(batch.skippedCount || 0);
  if (!total || surveyed === 0) return "not_started";
  if (confirmed >= total) return "confirmed";
  if (skipped >= total) return "skipped";
  if (surveyed >= total) return "surveyed";
  return "in_progress";
}
function taskStatusLabel(value) { return { not_started: "未调查", not_surveyed: "未调查", in_progress: "调查中", surveyed: "已调查", changed: "有变化", unchanged: "无变化", confirmed: "已确认", skipped: "已跳过", deregistered: "已注销" }[value] || value; }
function surveyStatusTagType(value) { return { not_started: "info", not_surveyed: "info", surveyed: "success", confirmed: "primary", skipped: "warning", deregistered: "danger" }[value] || "info"; }
function buildRegionParams() { const regionCode = activeBatch.value?.regionCode || activeRegionCode.value; return regionCode ? { regionCode } : {}; }

// 已确认/已注销的户不再参与改派，避免把定案成果挪给别人。
function isTaskSelectable(row) { return !["confirmed", "deregistered"].includes(row?.taskStatus); }

function assigneeTooltip(row) {
  const parts = [];
  if (row?.assignedAt) parts.push(`分配时间：${formatDateTime(row.assignedAt)}`);
  if (row?.investigatorName && row.investigatorName !== row.assignedToName) parts.push(`实际录入：${row.investigatorName}`);
  return parts.join("　") || "已分配";
}

// 批次卡片上的调查员：按名下户数降序，最多列 3 人，其余收成「等 N 人」。
function assigneeSummary(batch) {
  const names = (batch?.assigneeNames || []).filter(Boolean);
  if (!names.length) return "未分配";
  const shown = names.slice(0, 3).join("、");
  return names.length > 3 ? `${shown} 等 ${names.length} 人` : shown;
}

async function loadAssigneeOptions() {
  // 与下拉的显示条件同源：非管理员没有这个筛选入口，不必（也不该）拉名单。
  if (!showAssigneeFilter.value) { assigneeOptions.value = []; return; }
  assigneeLoading.value = true;
  try {
    const { data } = await fetchSurveyAssignees({ regionCode: activeRegionCode.value || undefined });
    assigneeOptions.value = data.data || [];
  } catch (error) {
    // 拿不到名单不拦人：筛选框留空即可，分配动作后端仍会兜底校验。
    assigneeOptions.value = [];
  } finally { assigneeLoading.value = false; }
}

// ---- Task assignment ----
function handleSelectionChange(rows) { selectedTasks.value = rows || []; }
function handleOnlyMineChange() { loadTasks(); }
function openAssign() { if (!activeBatch.value || !selectedTasks.value.length) return; taskAssignDialog.value.open(selectedTasks.value); }
function onTasksAssigned() { selectedTasks.value = []; taskTableRef.value?.clearSelection(); loadTasks(); }

// ---- Region tree ----
function flattenRegions(nodes, result = []) { for (const item of nodes || []) { result.push(item); flattenRegions(item.children, result); } return result; }

async function handleActiveRegionChange(value) {
  const selected = flattenRegions(regionTree.value).find((item) => item.id === value);
  activeRegionCode.value = selected?.code || "";
  activeRegionLabel.value = selected?.fullName || "";
  activeRegionId.value = selected?.id;
  activeBatch.value = null; tasks.value = []; issuerRows.value = [];
  // 换了区域，可筛选的调查员名单也要跟着换（管辖范围变了）。
  batchAssigneeId.value = null;
  await loadAssigneeOptions();
  await loadBatches();
}

function applyDefaultRegionFilter() {
  if (activeRegionId.value) return;
  const userRegionCode = authStore.user?.regionCode;
  if (!userRegionCode) return;
  // 只有「单一区域授权」的用户才拿所属区域当默认筛选。
  // 多区域授权（例如「一个镇 + 另一个镇的某个村」）时，所属区域只是其中之一，
  // 硬按它的前缀去筛会把其余授权区域的数据全部挡在列表外 —— 曾表现为
  // multi_scope_user（青阳镇 + 双沟镇/草湾村）登录后「调查批次」一片空白，
  // 其实它的权限一行都没少（详见 user_service._get_home_region_from_permissions 的说明）。
  // 不设默认筛选时后端仍会按 build_scoped_filter 兜底，看到的绝不会超出自己的授权范围。
  if ((authStore.user?.regionPermissions || []).length > 1) return;
  const selected = flattenRegions(regionTree.value).find((item) => item.code === userRegionCode);
  if (selected) { activeRegionId.value = selected.id; activeRegionCode.value = selected.code; activeRegionLabel.value = selected.fullName; }
}

async function loadRegionTree() {
  const { data } = await fetchRegionTree();
  regionTree.value = data.data;
  applyDefaultRegionFilter();
}

// ---- Batch operations ----
async function loadBatches() {
  batchLoading.value = true;
  try {
    // 勾了「只看与我相关」就不叠加区域筛选：这类批次由后端按「我创建 / 有户分给我」给出，
    // 再按我所属区域前缀去卡，反而会把分给我的批次挡掉。
    const regionCode = mineOnlyBatches.value ? undefined : activeRegionCode.value || undefined;
    const { data } = await fetchSurveyBatches({ page: 1, page_size: 50, keyword: batchKeyword.value || undefined, regionCode, assigneeId: batchAssigneeId.value || undefined, mineOnly: mineOnlyBatches.value ? 1 : undefined });
    batches.value = data.data.items;
    const previousBatchId = activeBatch.value?.id;
    activeBatch.value = filteredBatches.value.find((item) => item.id === previousBatchId) || filteredBatches.value[0] || null;
    if (activeBatch.value) { await loadTasks(); if (surveyPanelTab.value === "issuer") await loadIssuerSurveyRows(true); }
    else { tasks.value = []; issuerRows.value = []; }
  } finally { batchLoading.value = false; }
}

function handleBatchSelect(row) {
  activeBatch.value = row;
  issuerRows.value = [];
  selectedTasks.value = [];
  onlyMine.value = false;
  taskTableRef.value?.clearSelection();
  loadTasks().then(() => { if (surveyPanelTab.value === "issuer") loadIssuerSurveyRows(true); });
}

function openCreateBatch() { batchCreateDialog.value.open(activeRegionCode.value, activeRegionLabel.value); }
function onBatchCreated() { activeBatch.value = null; loadBatches(); }

async function handleFinishBatch() {
  if (!activeBatch.value) return;
  try {
    await ElMessageBox.confirm(`确定结束调查批次「${activeBatch.value.batchName}」吗？结束后该批次调查成果将不能继续编辑。`, "结束调查批次", { type: "warning", confirmButtonText: "结束批次", cancelButtonText: "取消" });
    await finishSurveyBatch(activeBatch.value.id);
    ElMessage.success("调查批次已结束");
    activeBatch.value = null;
    await loadBatches();
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(error.response?.data?.detail || "结束批次失败"); }
}

async function handleExportResults() {
  if (!activeBatch.value) return;
  const { data } = await exportSurveyResults(activeBatch.value.id, buildRegionParams());
  const url = URL.createObjectURL(data);
  const link = document.createElement("a"); link.href = url; link.download = `${activeBatch.value.batchNo || activeBatch.value.id}_survey_results.zip`; link.click(); URL.revokeObjectURL(url);
}

// ---- Task operations ----
async function loadTasks() {
  if (!activeBatch.value) { tasks.value = []; return; }
  taskLoading.value = true;
  try {
    const { data } = await fetchSurveyTasks(activeBatch.value.id, { page: 1, page_size: 100, keyword: taskKeyword.value || undefined, taskStatus: taskStatus.value || undefined, mine: onlyMine.value ? 1 : undefined, ...buildRegionParams() });
    tasks.value = data.data.items;
    issuerRows.value = [];
  } finally { taskLoading.value = false; }
}

// 打开录入界面前先记下这一户是否可写：对话框据此切只读
// （未分配 / 分给别人的户，只能看详细信息）。
const activeTaskCanWrite = ref(true);
function openResult(row) {
  activeTaskCanWrite.value = row?.canWrite !== false;
  contractorResultDialog.value.openForResult(activeBatch.value, row);
}
function openCreateContractor() { if (!activeBatch.value) return; activeTaskCanWrite.value = true; contractorResultDialog.value.openForCreate(activeBatch.value); }
function openDeregisteredDialog() { if (!activeBatch.value) return; deregisteredDialog.value.open(); }
function onResultSaved() { loadTasks(); loadBatches(); }

async function handleConfirmTask(row) {
  try { await confirmSurveyResult(row.batchId, row.contractorUid); ElMessage.success("调查结果已确认"); await loadTasks(); await loadBatches(); } catch (error) { ElMessage.error(error.response?.data?.detail || "确认失败"); }
}

async function handleSkipTask(row) {
  try {
    const { value } = await ElMessageBox.prompt("请输入跳过原因", "跳过调查任务", { inputType: "textarea", inputPlaceholder: "例如：本轮调查无需处理、非本区域调查对象等", inputValidator: (text) => Boolean(text?.trim()) || "请输入跳过原因", confirmButtonText: "跳过", cancelButtonText: "取消", type: "warning" });
    await skipSurveyTask(row.batchId, row.contractorUid, { skipReason: value.trim() });
    ElMessage.success("调查任务已跳过"); await loadTasks(); await loadBatches();
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(error.response?.data?.detail || "跳过失败"); }
}

// ---- Issuer operations ----
async function loadIssuerSurveyRows(force = false) {
  if (!activeBatch.value) { issuerRows.value = []; return; }
  if (!force && issuerRows.value.length) return;
  issuerLoading.value = true;
  try {
    const { data } = await fetchSurveyIssuers(activeBatch.value.id, { page: 1, page_size: 200, keyword: issuerKeyword.value || undefined, ...buildRegionParams() });
    issuerRows.value = data.data.items;
  } finally { issuerLoading.value = false; }
}

function openCreateIssuer() { if (!activeBatch.value) return; issuerSurveyDialog.value.openForCreate(activeBatch.value, activeBatch.value?.regionCode || activeRegionCode.value); }
function openIssuerSurvey(row) { if (!activeBatch.value) return; issuerSurveyDialog.value.openForEdit(activeBatch.value, row); }
function onIssuerSurveySaved() { loadIssuerSurveyRows(true); }

// ---- Watchers ----
watch(surveyPanelTab, (tab) => { if (tab === "issuer") loadIssuerSurveyRows(); });

// ---- Init ----
async function loadInitialData() { await loadRegionTree(); await loadAssigneeOptions(); await loadBatches(); }
loadInitialData();
</script>

<style scoped>
.survey-page {
  display: flex;
  gap: 16px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.survey-batch-panel {
  display: flex;
  flex: 0 0 calc(20% - 8px);
  flex-direction: column;
  min-width: 220px;
  max-width: 300px;
  min-height: 0;
  padding: 14px;
}

.survey-work-panel {
  display: flex;
  flex: 1 1 auto;
  margin-top: 0;
  min-width: 0;
  min-height: 0;
}

.survey-work-tabs {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}

.survey-work-tabs :deep(.el-tabs__content) {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
}

.survey-work-tabs :deep(.el-tab-pane) {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.survey-work-panel :deep(.el-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.survey-work-panel :deep(.survey-action-column .cell) {
  white-space: nowrap;
}

.survey-row-actions {
  align-items: center;
  display: inline-flex;
  flex-wrap: nowrap;
  gap: 10px;
  justify-content: center;
  white-space: nowrap;
}

.survey-row-actions :deep(.el-button) {
  margin-left: 0;
}

.survey-assignee {
  color: var(--el-color-primary);
  cursor: default;
}

.batch-panel-header,
.batch-footer-actions {
  align-items: center;
  display: flex;
}

.batch-panel-header {
  justify-content: space-between;
  gap: 10px;
}

.batch-footer-actions {
  gap: 8px;
}

.batch-panel-actions {
  align-items: center;
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 116px) auto;
}

.batch-header-filter {
  width: 116px;
}

.batch-search {
  margin-top: 12px;
}

.batch-assignee-filter {
  margin-top: 12px;
  width: 100%;
}

.batch-mine-filter {
  margin-top: 10px;
}

.batch-card-badges {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.batch-card-badges :deep(.el-tag) {
  margin: 0;
}

.batch-card-unassigned {
  color: var(--el-color-warning);
  font-size: 12px;
  line-height: 1.4;
}

.batch-card-assignee {
  color: #2563eb;
  font-size: 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.batch-card-assignee.is-empty {
  color: #94a3b8;
}

.batch-card-list {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.batch-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  color: #0f172a;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  text-align: left;
  transition: background 0.2s, border-color 0.2s, box-shadow 0.2s;
  width: 100%;
}

.batch-card:hover,
.batch-card.is-active {
  background: #f8fafc;
  border-color: #2563eb;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
}

.batch-card-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.batch-card-status-row,
.batch-card-metrics {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
}

.batch-card-progress {
  color: #475569;
  font-size: 12px;
  white-space: nowrap;
}

.batch-card-metrics {
  border-top: 1px solid #e2e8f0;
  padding-top: 8px;
}

.batch-card-metrics span {
  color: #64748b;
  display: flex;
  flex-direction: column;
  font-size: 12px;
  gap: 2px;
}

.batch-card-metrics b {
  color: #0f172a;
  font-size: 18px;
  line-height: 1;
}

.batch-footer-actions {
  border-top: 1px solid #e2e8f0;
  flex-shrink: 0;
  margin-top: 12px;
  padding-top: 12px;
}

.batch-tooltip-content {
  display: grid;
  gap: 6px;
  min-width: 220px;
}

.batch-tooltip-content div {
  color: #0f172a;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.batch-tooltip-content span {
  color: #64748b;
  flex: 0 0 70px;
}

@media (max-width: 1080px) {
  .survey-page {
    flex-direction: column;
  }

  .survey-batch-panel {
    flex-basis: auto;
    max-width: none;
    min-height: 240px;
  }
}
</style>
