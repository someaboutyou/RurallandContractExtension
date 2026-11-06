<template>
  <div class="survey-page">
    <section class="panel survey-batch-panel">
      <div class="batch-panel-header">
        <div class="panel-title">调查批次管理</div>
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
          <!-- 卡片用 div 而非 button：选中批次的卡片内要放「承包户导出/导入」入口，button 不能嵌 button -->
          <div
            class="batch-card"
            :class="{ 'is-active': activeBatch?.id === batch.id }"
            role="button"
            tabindex="0"
            @click="handleBatchSelect(batch)"
            @keydown.enter.prevent="handleBatchSelect(batch)"
          >
            <span class="batch-card-title">{{ batch.batchName || batch.batchNo }}</span>
            <span class="batch-card-status-row">
              <el-tag :type="batchStatusType(batch.status)" size="small">{{ batchStatusLabel(batch.status) }}</el-tag>
              <span class="batch-card-progress">{{ batchSurveySummary(batch) }}</span>
            </span>
            <span class="batch-card-meta-row">
              <span v-if="batch.createdByMe || batch.assignedToMe" class="batch-card-badges">
                <el-tag v-if="batch.createdByMe" size="small" type="success" effect="plain">我创建</el-tag>
                <el-tag v-if="batch.assignedToMe" size="small" type="primary" effect="plain">分给我 {{ batch.myTaskCount }} 户</el-tag>
              </span>
              <span class="batch-card-assignee" :class="{ 'is-empty': !batch.assigneeCount }">
                调查员：{{ assigneeSummary(batch) }}
              </span>
            </span>
            <span v-if="batch.unassignedCount" class="batch-card-unassigned">
              还有 {{ batch.unassignedCount }} 户待分配，请及时改派
            </span>
          </div>
        </el-tooltip>
      </div>
    </section>

    <section v-if="activeBatch" class="panel table-page survey-batch-detail">
      <div class="batch-detail-header">
        <div>
          <div class="panel-title">{{ activeBatch.batchName || activeBatch.batchNo }}</div>
          <div class="batch-detail-meta">
            {{ activeBatch.batchNo }} · {{ activeBatch.regionName || activeBatch.regionCode || "-" }} ·
            {{ batchStatusLabel(activeBatch.status) }}
          </div>
        </div>
        <div class="batch-detail-actions">
          <el-button type="primary" :loading="enteringTask" @click="handleEnterTask">进入任务</el-button>
          <el-button plain :icon="Download" @click="handleExportResults">导出成果</el-button>
          <el-button plain type="warning" @click="qualityCheckVisible = true">数据质检</el-button>
          <el-button
            v-if="canFinishBatch"
            plain
            type="warning"
            :disabled="activeBatch.status === 'finished'"
            :icon="CircleCheck"
            @click="handleFinishBatch"
          >
            结束批次
          </el-button>
        </div>
      </div>

      <div class="batch-stats">
        <div class="batch-stat-card">
          <span class="batch-stat-label">发包方</span>
          <strong class="batch-stat-value">{{ batchStats.issuerCount }}</strong>
          <span class="batch-stat-unit">个</span>
        </div>
        <div class="batch-stat-card">
          <span class="batch-stat-label">承包方</span>
          <strong class="batch-stat-value">{{ batchStats.contractorCount }}</strong>
          <span class="batch-stat-unit">个</span>
        </div>
        <div class="batch-stat-card">
          <span class="batch-stat-label">家庭成员</span>
          <strong class="batch-stat-value">{{ batchStats.memberCount }}</strong>
          <span class="batch-stat-unit">人</span>
        </div>
        <div class="batch-stat-card">
          <span class="batch-stat-label">承包地块</span>
          <strong class="batch-stat-value">{{ batchStats.parcelCount }}</strong>
          <span class="batch-stat-unit">块</span>
        </div>
        <div class="batch-stat-card">
          <span class="batch-stat-label">承包合同</span>
          <strong class="batch-stat-value">{{ batchStats.contractCount }}</strong>
          <span class="batch-stat-unit">份</span>
        </div>
      </div>

      <div class="batch-issuer-panel">
        <div class="toolbar">
          <div class="panel-title">本批次发包方清单</div>
          <div class="toolbar-actions">
            <el-input v-model="issuerKeyword" clearable placeholder="搜索发包方" style="width: 220px" @keyup.enter="loadIssuerRows" @clear="loadIssuerRows" />
            <el-button :icon="Search" plain @click="loadIssuerRows">查询</el-button>
            <template v-if="canManage">
              <el-button
                :disabled="activeBatch?.status === 'finished' || selectedIssuerRows.length < 2"
                type="warning"
                plain
                @click="openMergeIssuer"
              >合并</el-button>
              <el-button :disabled="activeBatch?.status === 'finished'" :icon="Plus" type="primary" @click="openCreateIssuer">新增</el-button>
            </template>
            <span class="batch-selected-hint">已选 {{ selectedIssuerRows.length }} 个发包方</span>
          </div>
        </div>
        <el-table
          ref="issuerTableRef"
          v-loading="issuerLoading"
          :data="issuerRows"
          row-key="issuerUid"
          border
          stripe
          size="small"
          class="survey-table"
          @selection-change="handleIssuerSelectionChange"
        >
          <el-table-column type="selection" width="44" />
          <el-table-column prop="code" label="发包方编码" width="150" show-overflow-tooltip />
          <el-table-column prop="name" label="发包方名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="responsibleName" label="负责人" width="110" />
          <el-table-column prop="phone" label="联系电话" width="130" />
          <el-table-column prop="address" label="地址" min-width="200" show-overflow-tooltip />
        </el-table>

        <div class="batch-forms-export">
          <div class="batch-forms-head">
            <span class="batch-forms-title">导出调查表单</span>
            <span class="batch-selected-hint">已选 {{ selectedIssuerRows.length }} 个发包方</span>
          </div>
          <div class="batch-forms-checks">
            <el-checkbox
              v-for="form in FORM_OPTIONS"
              :key="form.value"
              v-model="formChecks[form.value]"
            >
              {{ form.label }}
            </el-checkbox>
          </div>
          <div class="batch-forms-actions">
            <el-button
              type="primary"
              :loading="batchExporting"
              :disabled="!selectedIssuerRows.length || !hasCheckedForm"
              @click="handleBatchFormExport"
            >
              导出
            </el-button>
          </div>
        </div>
      </div>
    </section>
    <section v-else class="panel table-page">
      <el-empty description="请先在上方选择一个调查批次" />
    </section>

    <BatchCreateDialog ref="batchCreateDialog" v-model="batchDialogVisible" @created="onBatchCreated" />
    <IssuerSurveyDialog ref="issuerSurveyDialog" v-model="issuerSurveyVisible" :active-batch="activeBatch" :can-manage="canManage" @saved="onIssuerSaved" />
    <MergeIssuerDialog ref="mergeIssuerDialog" v-model="mergeIssuerVisible" :active-batch="activeBatch" :rows="selectedIssuerRows" @merged="onIssuersMerged" />
    <QualityCheckDialog v-model="qualityCheckVisible" :batch="activeBatch" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { CircleCheck, Download, Plus, Search } from "@element-plus/icons-vue";

import BatchCreateDialog from "../components/survey/view/BatchCreateDialog.vue";
import IssuerSurveyDialog from "../components/survey/view/IssuerSurveyDialog.vue";
import MergeIssuerDialog from "../components/survey/view/MergeIssuerDialog.vue";
import QualityCheckDialog from "../components/survey/QualityCheckDialog.vue";

import {
  exportBatchForms,
  exportSurveyResults,
  fetchSurveyAssignees,
  fetchSurveyBatchStats,
  fetchSurveyBatches,
  fetchSurveyIssuers,
  finishSurveyBatch,
  setCurrentSurveyBatch,
} from "../api/survey";
import { fetchRegionTree } from "../api/region";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));

// ---- Batch list state ----
const batchLoading = ref(false);
const batches = ref([]);
const batchKeyword = ref("");
const batchSurveyStatus = ref("");
const isAdmin = computed(() => authStore.user?.dataScope === "all");
const batchAssigneeId = ref(null);
const assigneeOptions = ref([]);
const assigneeLoading = ref(false);
const showAssigneeFilter = computed(() => isAdmin.value);
const mineOnlyBatches = ref(false);
const showMineBatchFilter = computed(() => !isAdmin.value);
const activeBatch = ref(null);
const batchDialogVisible = ref(false);

const filteredBatches = computed(() => {
  if (!batchSurveyStatus.value) return batches.value;
  return batches.value.filter((batch) => batchSurveyStatusValue(batch) === batchSurveyStatus.value);
});

// ---- Batch detail state ----
const batchStats = reactive({
  issuerCount: 0,
  contractorCount: 0,
  memberCount: 0,
  parcelCount: 0,
  contractCount: 0,
});
const issuerLoading = ref(false);
const issuerRows = ref([]);
const issuerKeyword = ref("");
const selectedIssuerRows = ref([]);
const enteringTask = ref(false);

const FORM_OPTIONS = [
  { value: "issuer_excel", label: "发包方调查表（Excel）" },
  { value: "contractor_excel", label: "承包方调查表（Excel）" },
  { value: "parcel_excel", label: "承包地块调查表（Excel）" },
  { value: "notice_excel", label: "延包调查公示表（Excel）" },
  { value: "baseline_excel", label: "摸底调查核实表（Excel）" },
  { value: "baseline_print_excel", label: "摸底调查核实表（打印版）" },
  { value: "issuer_word", label: "发包方调查表（Word）" },
  { value: "contractor_word", label: "承包方调查表（Word）" },
  { value: "parcel_word", label: "承包地块调查表（Word）" },
  { value: "public_notice_word", label: "公示结果归户表（Word）" },
];
const formChecks = reactive(
  Object.fromEntries(FORM_OPTIONS.map((item) => [item.value, false])),
);
const hasCheckedForm = computed(() => Object.values(formChecks).some(Boolean));
const batchExporting = ref(false);

// ---- 发包方维护（新增 / 编辑 / 合并 / 删除）----
const issuerTableRef = ref(null);
const issuerSurveyDialog = ref(null);
const issuerSurveyVisible = ref(false);
const mergeIssuerDialog = ref(null);
const mergeIssuerVisible = ref(false);
// ---- 数据质检 ----
const qualityCheckVisible = ref(false);

// ---- Region state ----
const regionTree = ref([]);
const regionTreeProps = { label: "fullName", children: "children" };
const activeRegionId = ref(undefined);
const activeRegionCode = ref("");
const activeRegionLabel = ref("");

const batchCreateDialog = ref(null);

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
function assigneeSummary(batch) {
  const names = (batch?.assigneeNames || []).filter(Boolean);
  if (!names.length) return "未分配";
  const shown = names.slice(0, 3).join("、");
  return names.length > 3 ? `${shown} 等 ${names.length} 人` : shown;
}

const canFinishBatch = computed(
  () => canManage.value && (isAdmin.value || activeBatch.value?.createdByMe === true),
);

async function loadAssigneeOptions() {
  if (!showAssigneeFilter.value) { assigneeOptions.value = []; return; }
  assigneeLoading.value = true;
  try {
    const { data } = await fetchSurveyAssignees({ regionCode: activeRegionCode.value || undefined });
    assigneeOptions.value = data.data || [];
  } catch { assigneeOptions.value = []; } finally { assigneeLoading.value = false; }
}

// ---- Region tree ----
function flattenRegions(nodes, result = []) { for (const item of nodes || []) { result.push(item); flattenRegions(item.children, result); } return result; }

async function handleActiveRegionChange(value) {
  const selected = flattenRegions(regionTree.value).find((item) => item.id === value);
  activeRegionCode.value = selected?.code || "";
  activeRegionLabel.value = selected?.fullName || "";
  activeRegionId.value = selected?.id;
  activeBatch.value = null;
  batchAssigneeId.value = null;
  await loadAssigneeOptions();
  await loadBatches();
}

function applyDefaultRegionFilter() {
  if (activeRegionId.value) return;
  const userRegionCode = authStore.user?.regionCode;
  if (!userRegionCode) return;
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
    const regionCode = mineOnlyBatches.value ? undefined : activeRegionCode.value || undefined;
    const { data } = await fetchSurveyBatches({ page: 1, page_size: 50, keyword: batchKeyword.value || undefined, regionCode, assigneeId: batchAssigneeId.value || undefined, mineOnly: mineOnlyBatches.value ? 1 : undefined });
    batches.value = data.data.items;
    const previousBatchId = activeBatch.value?.id;
    activeBatch.value = filteredBatches.value.find((item) => item.id === previousBatchId) || filteredBatches.value[0] || null;
    selectedIssuerRows.value = [];
    await loadBatchDetail();
  } finally { batchLoading.value = false; }
}

function handleBatchSelect(row) {
  activeBatch.value = row;
  selectedIssuerRows.value = [];
  issuerKeyword.value = "";
  loadBatchDetail();
}

async function loadBatchDetail() {
  if (!activeBatch.value) {
    Object.assign(batchStats, { issuerCount: 0, contractorCount: 0, memberCount: 0, parcelCount: 0, contractCount: 0 });
    issuerRows.value = [];
    return;
  }
  await Promise.all([loadBatchStats(), loadIssuerRows()]);
}

async function loadBatchStats() {
  if (!activeBatch.value) return;
  try {
    const { data } = await fetchSurveyBatchStats(activeBatch.value.id);
    Object.assign(batchStats, data.data || {});
  } catch {
    Object.assign(batchStats, { issuerCount: 0, contractorCount: 0, memberCount: 0, parcelCount: 0, contractCount: 0 });
  }
}

async function loadIssuerRows() {
  if (!activeBatch.value) { issuerRows.value = []; return; }
  issuerLoading.value = true;
  try {
    const { data } = await fetchSurveyIssuers(activeBatch.value.id, { page: 1, page_size: 200, keyword: issuerKeyword.value || undefined });
    issuerRows.value = data.data.items || [];
  } catch { issuerRows.value = []; } finally { issuerLoading.value = false; }
}

function handleIssuerSelectionChange(rows) { selectedIssuerRows.value = rows || []; }

// ---- Issuer operations ----
function openCreateIssuer() {
  if (!activeBatch.value || activeBatch.value?.status === "finished") return;
  issuerSurveyDialog.value.openForCreate(activeBatch.value, activeBatch.value?.regionCode || activeRegionCode.value);
}
function onIssuerSaved() { loadBatchDetail(); }

function openMergeIssuer() {
  if (!activeBatch.value || selectedIssuerRows.value.length < 2) return;
  mergeIssuerDialog.value.open();
}
function onIssuersMerged() {
  // 合并后被合并方已删除，清掉勾选再整表重查
  selectedIssuerRows.value = [];
  issuerTableRef.value?.clearSelection();
  loadBatchDetail();
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

function filenameFromDisposition(disposition) {
  const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition || "");
  return match ? decodeURIComponent(match[1]) : "";
}

async function handleBatchFormExport() {
  if (!activeBatch.value || !selectedIssuerRows.value.length) {
    ElMessage.warning("请先勾选发包方");
    return;
  }
  const forms = FORM_OPTIONS.filter((item) => formChecks[item.value]).map((item) => item.value);
  if (!forms.length) {
    ElMessage.warning("请至少勾选一种调查表单");
    return;
  }
  batchExporting.value = true;
  try {
    const { data, headers } = await exportBatchForms(activeBatch.value.id, {
      issuerUids: selectedIssuerRows.value.map((row) => row.issuerUid),
      forms,
    });
    const filename =
      filenameFromDisposition(headers?.["content-disposition"]) ||
      (String(headers?.["content-type"] || "").includes("zip") ? "调查表单.zip" : "调查表单.xls");
    downloadBlob(data, filename);
    ElMessage.success("调查表单已导出");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导出调查表单失败");
  } finally {
    batchExporting.value = false;
  }
}

async function handleEnterTask() {
  if (!activeBatch.value) return;
  enteringTask.value = true;
  try {
    await setCurrentSurveyBatch(activeBatch.value.id);
    ElMessage.success(`已进入「${activeBatch.value.batchName || activeBatch.value.batchNo}」`);
    router.push({ name: "survey-contractors" });
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "进入任务失败");
  } finally { enteringTask.value = false; }
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
  const { data } = await exportSurveyResults(activeBatch.value.id, activeBatch.value.regionCode ? { regionCode: activeBatch.value.regionCode } : {});
  const url = URL.createObjectURL(data);
  const link = document.createElement("a"); link.href = url; link.download = `${activeBatch.value.batchNo || activeBatch.value.id}_survey_results.zip`; link.click(); URL.revokeObjectURL(url);
}

onMounted(async () => {
  await loadRegionTree();
  await loadAssigneeOptions();
  await loadBatches();
});
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
  flex-wrap: wrap;
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

.batch-card-meta-row {
  align-items: center;
  column-gap: 8px;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  row-gap: 2px;
}

.batch-card-badges {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.batch-card-badges:empty {
  display: none;
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

.batch-card-status-row {
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

.batch-card-actions {
  border-top: 1px dashed #e2e8f0;
  display: flex;
  gap: 4px;
  justify-content: flex-end;
  padding-top: 8px;
}

.batch-card-actions :deep(.el-button) {
  margin-left: 0;
  padding: 0 6px;
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

/* ---- 批次详情：统计 + 发包方清单 + 批量导出 ---- */
.survey-batch-detail {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
}

.batch-detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.batch-detail-meta {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.batch-detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.batch-stats {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.batch-stat-card {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}

.batch-stat-label {
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.batch-stat-value {
  color: var(--el-color-primary);
  font-size: 24px;
  line-height: 1;
}

.batch-stat-unit {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.batch-issuer-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.batch-selected-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.batch-forms-export {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}

.batch-forms-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.batch-forms-title {
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 600;
}

.batch-forms-checks {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 2px 14px;
}

.batch-forms-checks :deep(.el-checkbox) {
  height: 24px;
  margin-right: 0;
}

.batch-forms-actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1280px) {
  .batch-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
