<template>
  <section class="panel table-page survey-contractor-page">
    <div v-if="!activeBatch" class="survey-contractor-empty">
      <el-empty description="请先在左侧选择一个调查批次" />
    </div>

    <div v-else class="survey-contractor-body">
      <SurveyBatchPanel v-model="activeBatch" />

      <div class="survey-contractor-main">
        <div class="toolbar">
          <div class="panel-title">承包方管理</div>
          <div class="toolbar-actions">
            <el-input v-model="taskKeyword" :disabled="!activeBatch" clearable placeholder="搜索承包方" style="width: 220px" @keyup.enter="loadTasks" />
            <el-button :disabled="!activeBatch" :icon="Search" plain @click="loadTasks">查询</el-button>
            <el-button v-if="canManage" :disabled="!activeBatch || activeBatch?.status === 'finished'" :icon="Plus" type="primary" @click="openCreateContractor">新增</el-button>
            <el-button :disabled="!activeBatch || !selectedTasks.length" plain @click="exportDialogVisible = true">导出</el-button>
            <el-button v-if="canManage" :disabled="!activeBatch || !selectedTasks.length" plain @click="lockDialogVisible = true">锁定/解锁</el-button>
            <el-button v-if="canManage" :disabled="!activeBatch || activeBatch?.status === 'finished'" plain @click="xlsImportVisible = true">承包户导入</el-button>
            <el-button v-if="canManage" :disabled="!activeBatch" plain @click="relationDialogVisible = true">家庭关系处理</el-button>
          </div>
        </div>

        <el-table
          ref="taskTableRef"
          v-loading="taskLoading"
          :data="tasks"
          border
          stripe
          size="small"
          class="survey-table"
          @selection-change="handleSelectionChange"
        >
        <el-table-column type="selection" width="40" fixed="left" />
        <el-table-column prop="cbfbm" label="泗洪承包方编码" width="160" show-overflow-tooltip />
        <el-table-column prop="cbfmc" label="承包方姓名" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.cbfmc }}</span>
            <el-tag v-if="row.isLocked" class="lock-tag" type="info" size="small" effect="plain">已锁定</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="cbfdz" label="承包方地址" min-width="160" show-overflow-tooltip />
        <el-table-column prop="cbfcysl" label="成员数量" width="80" align="center" />
        <el-table-column prop="lxdh" label="联系电话" width="120" />
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
              <el-tooltip v-if="isResultReadOnly(row)" placement="top" :content="readOnlyReason(row)">
                <el-button link type="warning" @click="openResult(row)">查看详情</el-button>
              </el-tooltip>
              <el-button v-else link type="primary" @click="openResult(row)">编辑</el-button>
              <el-button
                v-if="canManage && row.canWrite !== false && activeBatch?.status !== 'finished'"
                link
                type="danger"
                @click="handleDeleteTask(row)"
              >删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      </div>
    </div>

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
    <ContractorXlsImportDialog v-model="xlsImportVisible" :batch="activeBatch" @imported="loadTasks" />
    <ContractorExportDialog
      v-model="exportDialogVisible"
      :batch="activeBatch"
      :contractor-uids="selectedTasks.map((row) => row.contractorUid)"
    />
    <ContractorLockDialog
      v-model="lockDialogVisible"
      :batch="activeBatch"
      :contractors="selectedTasks"
      @locked="onLocked"
    />
    <ContractorRelationDialog
      v-model="relationDialogVisible"
      :batch="activeBatch"
      @replaced="loadTasks"
      @repaired="loadTasks"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Search } from "@element-plus/icons-vue";

import ContractorResultDialog from "../components/survey/view/ContractorResultDialog.vue";
import ContractorXlsImportDialog from "../components/survey/ContractorXlsImportDialog.vue";
import ContractorExportDialog from "../components/survey/ContractorExportDialog.vue";
import ContractorLockDialog from "../components/survey/ContractorLockDialog.vue";
import ContractorRelationDialog from "../components/survey/ContractorRelationDialog.vue";
import SurveyBatchPanel from "../components/survey/SurveyBatchPanel.vue";

import {
  deleteSurveyContractor,
  fetchCurrentSurveyBatch,
  fetchSurveyTasks,
} from "../api/survey";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));

const activeBatch = ref(null);

const taskLoading = ref(false);
const tasks = ref([]);
const taskKeyword = ref("");
const selectedTasks = ref([]);
const taskTableRef = ref(null);
const resultVisible = ref(false);
const activeTaskCanWrite = ref(true);
const contractorResultDialog = ref(null);
const xlsImportVisible = ref(false);
const exportDialogVisible = ref(false);
const lockDialogVisible = ref(false);
const relationDialogVisible = ref(false);

const activeRegionCode = computed(() => activeBatch.value?.regionCode || "");
const activeRegionLabel = computed(() => activeBatch.value?.regionName || "");

function formatDateTime(value) { if (!value) return "-"; return String(value).replace("T", " ").slice(0, 19); }
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

// 批次切换（左侧面板点选）：重新加载该批次的承包户任务。
watch(activeBatch, () => {
  loadTasks();
});

// 用户在 /surveys「进入任务」记住的批次作为默认选中。
onMounted(async () => {
  try {
    const { data } = await fetchCurrentSurveyBatch();
    if (data.data?.id) {
      activeBatch.value = data.data;
      return; // watch(activeBatch) 会触发首次加载
    }
  } catch { /* 拿不到当前批次就等用户手动选择 */ }
});

async function loadTasks() {
  if (!activeBatch.value) { tasks.value = []; return; }
  taskLoading.value = true;
  try {
    const { data } = await fetchSurveyTasks(activeBatch.value.id, {
      page: 1,
      page_size: 100,
      keyword: taskKeyword.value || undefined,
      ...buildRegionParams(),
    });
    tasks.value = data.data.items || [];
    selectedTasks.value = [];
    taskTableRef.value?.clearSelection();
  } finally { taskLoading.value = false; }
}

function handleSelectionChange(rows) {
  selectedTasks.value = rows || [];
}

function isResultReadOnly(row) {
  return row?.canWrite === false || row?.isLocked || row?.taskStatus === "confirmed";
}

function readOnlyReason(row) {
  if (row?.isLocked) return "该承包方已锁定，请先解锁后再编辑";
  if (row?.taskStatus === "confirmed") return "该承包方调查结果已确认，请先撤回确认后再编辑";
  if (row?.assignedToName) return `已分配给${row.assignedToName}，只能查看详细信息`;
  return "尚未分配调查员，只能查看详细信息";
}

function openResult(row) {
  activeTaskCanWrite.value = row?.canWrite !== false;
  contractorResultDialog.value.openForResult(activeBatch.value, row);
}
function openCreateContractor() { if (!activeBatch.value) return; activeTaskCanWrite.value = true; contractorResultDialog.value.openForCreate(activeBatch.value); }
function onResultSaved() { loadTasks(); }
function onLocked() {
  selectedTasks.value = [];
  taskTableRef.value?.clearSelection();
  loadTasks();
}

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

async function handleDeleteTask(row) {
  if (!activeBatch.value || !row?.contractorUid) return;
  // 与 CS 版一致：删除按钮常显，但已锁定/已确认的承包方点击后拦截。
  if (row.isLocked) {
    ElMessage.warning("承包方已锁定，请先解锁后再删除");
    return;
  }
  if (row.taskStatus === "confirmed") {
    ElMessage.warning("承包方已确认（锁定），请先在编辑中撤回确认后再删除");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `删除承包方「${row.cbfmc || row.cbfbm || ""}」会关联删除成员、地块、合同等信息，确定删除？`,
      "删除承包方",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return; // 用户取消
  }
  try {
    await deleteSurveyContractor(activeBatch.value.id, row.contractorUid);
    ElMessage.success("承包方已删除");
    await loadTasks();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "删除承包方失败");
  }
}
</script>

<style scoped>

/* 左侧调查批次面板 + 承包户任务列表的双栏布局。 */
.survey-contractor-empty {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
}

.survey-contractor-body {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 12px;
  overflow: hidden;
}

.survey-contractor-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

@media (max-width: 960px) {
  .survey-contractor-body {
    grid-template-columns: 1fr;
    overflow: visible;
  }
}

.survey-contractor-page {
  min-height: 0;
}

.lock-tag {
  margin-left: 6px;
}
</style>
