<template>
  <section class="panel table-page contract-manage-page">
    <div v-if="!activeBatch" class="contract-manage-empty">
      <el-empty description="请先在左侧选择一个调查批次" />
    </div>

    <div v-else class="contract-manage-body" :class="{ 'is-batch-collapsed': batchPanelCollapsed }">
      <SurveyBatchPanel v-model="activeBatch" v-model:collapsed="batchPanelCollapsed" />

      <div class="contract-manage-main">
        <div class="toolbar">
          <div class="panel-title">承包合同管理</div>
          <div class="toolbar-actions">
            <el-input v-model="taskKeyword" :disabled="!activeBatch" clearable placeholder="搜索承包方" style="width: 220px" @keyup.enter="loadRows" />
            <el-button :disabled="!activeBatch" :icon="Search" plain @click="loadRows">查询</el-button>
            <el-button
              v-if="canManage"
              type="primary"
              :disabled="!activeBatch || activeBatch?.status === 'finished' || !rows.length"
              :loading="collecting"
              @click="handleBatchSign"
            >批量签订</el-button>
            <el-dropdown trigger="click" :disabled="!activeBatch" @command="(cmd) => handleCollectiveApplication(cmd)">
              <el-button :disabled="!activeBatch" :loading="applicationLoading" plain>
                集体申请书<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="print">打印</el-dropdown-item>
                  <el-dropdown-item command="docx">导出 Word</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <el-table
          ref="rowTableRef"
          v-loading="rowLoading"
          :data="rows"
          border
          stripe
          size="small"
          class="contract-table"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="40" fixed="left" />
          <el-table-column prop="cbfbm" label="承包方编码" width="160" show-overflow-tooltip />
          <el-table-column prop="cbfmc" label="承包方姓名" min-width="110" show-overflow-tooltip />
          <el-table-column prop="contractCode" label="合同编码" width="190" show-overflow-tooltip>
            <template #default="{ row }">{{ row.contractCode || "-" }}</template>
          </el-table-column>
          <el-table-column label="合同状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.signed" type="success" size="small">已签订</el-tag>
              <el-tag v-else type="info" size="small" effect="plain">未签订</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="合同类型" width="110" show-overflow-tooltip>
            <template #default="{ row }">{{ row.contractSourceText || "-" }}</template>
          </el-table-column>
          <el-table-column label="承包期限起" width="110" align="center">
            <template #default="{ row }">{{ row.cbqxq || "-" }}</template>
          </el-table-column>
          <el-table-column label="承包期限止" width="110" align="center">
            <template #default="{ row }">{{ row.cbqxz || "-" }}</template>
          </el-table-column>
          <el-table-column label="签订日期" width="110" align="center">
            <template #default="{ row }">{{ row.qdsj || "-" }}</template>
          </el-table-column>
          <el-table-column label="地块总数" width="80" align="center">
            <template #default="{ row }">{{ row.cbdkzs ?? "-" }}</template>
          </el-table-column>
          <el-table-column label="合同面积(亩)" width="100" align="right">
            <template #default="{ row }">{{ row.htzmjm != null ? Number(row.htzmjm).toFixed(2) : "-" }}</template>
          </el-table-column>
          <el-table-column label="生成人" width="100" show-overflow-tooltip>
            <template #default="{ row }">{{ row.generatedBy || "-" }}</template>
          </el-table-column>
          <el-table-column label="生成时间" width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ formatDateTime(row.generatedAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right" class-name="contract-action-column">
            <template #default="{ row }">
              <div class="contract-row-actions">
                <el-button
                  v-if="canManage"
                  link
                  :type="row.signed ? 'warning' : 'primary'"
                  :disabled="!row.canSign"
                  @click="signSingle(row)"
                >{{ row.signed ? "重新签订" : "签订合同" }}</el-button>
                <el-button
                  v-if="row.signed"
                  link
                  type="primary"
                  @click="viewContract(row)"
                >查看合同</el-button>
                <el-dropdown trigger="click" @command="(cmd) => handleHouseholdApplication(row, cmd)">
                  <el-button link type="primary">单户申请书<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="print">打印</el-dropdown-item>
                      <el-dropdown-item command="docx">导出 Word</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 生成延包合同：与承包方调查录入「合同生成」共用同一对话框（含批量进度条） -->
    <SurveyContractGenerateDialog
      ref="generateDialog"
      :batch-id="activeBatch?.id || null"
      :batch-status="activeBatch?.status || 'active'"
      @completed="onSignCompleted"
    />

    <!-- 查看合同：复用承包方调查录入「合同信息」面板（版本切换/打印/生成/附件同一套） -->
    <el-dialog
      v-model="contractInfoVisible"
      :title="contractInfoTitle"
      width="1040px"
      top="4vh"
      append-to-body
      destroy-on-close
      @closed="onContractInfoClosed"
    >
      <ContractInfoPanel
        v-if="contractInfoVisible && contractInfoTarget && activeBatch"
        :batch-id="activeBatch.id"
        :contractor-uid="contractInfoTarget.contractorUid"
        :can-manage="canManage"
        :batch-status="activeBatch?.status || 'active'"
      />
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, Search } from "@element-plus/icons-vue";

import SurveyBatchPanel from "../components/survey/SurveyBatchPanel.vue";
import SurveyContractGenerateDialog from "../components/survey/SurveyContractGenerateDialog.vue";
import ContractInfoPanel from "../components/survey/ContractInfoPanel.vue";

import {
  exportCollectiveApplicationDocx,
  exportHouseholdApplicationDocx,
  fetchBatchContractOverview,
  fetchCollectiveApplication,
  fetchCurrentSurveyBatch,
  fetchHouseholdApplication,
} from "../api/survey";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));

const activeBatch = ref(null);
const batchPanelCollapsed = ref(false);

const rowLoading = ref(false);
const collecting = ref(false);
const rows = ref([]);
const rowTotal = ref(0);
const taskKeyword = ref("");
const selectedRows = ref([]);
const rowTableRef = ref(null);
const generateDialog = ref(null);
// 查看合同对话框（复用 ContractInfoPanel）
const contractInfoVisible = ref(false);
const contractInfoTarget = ref(null);
const contractInfoTitle = computed(() => {
  const target = contractInfoTarget.value;
  const name = target?.cbfmc || target?.cbfbm || "";
  return name ? `合同信息 —— ${name}` : "合同信息";
});

function formatDateTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 19);
}

function buildRegionParams() {
  const regionCode = activeBatch.value?.regionCode;
  return regionCode ? { regionCode } : {};
}

// 批次切换（左侧面板点选）：重新加载该批次的合同关键信息列表。
watch(activeBatch, () => {
  loadRows();
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

async function loadRows() {
  if (!activeBatch.value) { rows.value = []; rowTotal.value = 0; return; }
  rowLoading.value = true;
  try {
    const { data } = await fetchBatchContractOverview(activeBatch.value.id, {
      page: 1,
      page_size: 100,
      keyword: taskKeyword.value || undefined,
      ...buildRegionParams(),
    });
    rows.value = data.data?.items || [];
    rowTotal.value = data.data?.total || 0;
    selectedRows.value = [];
    rowTableRef.value?.clearSelection();
  } finally {
    rowLoading.value = false;
  }
}

function handleSelectionChange(rows_) {
  selectedRows.value = rows_ || [];
}

// 操作列：单户签订（与调查录入「合同生成」同一个对话框，单户模式）
function signSingle(row) {
  if (!row?.canSign) {
    ElMessage.warning("调查批次已结束，不能生成合同");
    return;
  }
  generateDialog.value?.open({
    contractors: [{ contractorUid: row.contractorUid, cbfmc: row.cbfmc }],
  });
}

// 操作列：查看合同（已签订户；复用调查录入「合同信息」面板，含历史版本/打印/附件）
function viewContract(row) {
  if (!row?.contractorUid) return;
  contractInfoTarget.value = row;
  contractInfoVisible.value = true;
}

// 在查看弹窗里可能重新生成了合同；关闭时刷新列表，保证「现行合同」列不失真
function onContractInfoClosed() {
  contractInfoTarget.value = null;
  loadRows();
}

// ── 登记（延包）申请书（集体 / 单户）：打印与导出 Word ──

const applicationLoading = ref(false);

function printHtml(html) {
  const win = window.open("", "_blank", "width=900,height=700");
  if (!win) {
    ElMessage.warning("浏览器拦截了打印窗口，请允许弹出窗口后重试");
    return;
  }
  win.document.write(html);
  win.document.close();
  setTimeout(() => win.print(), 500);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function batchRegionTail() {
  const parts = (activeBatch.value?.regionName || "").split("/").map((p) => p.trim()).filter(Boolean);
  return parts.slice(-3).join("") || "集体登记申请书";
}

async function handleCollectiveApplication(command) {
  if (!activeBatch.value) return;
  applicationLoading.value = true;
  try {
    if (command === "print") {
      const { data } = await fetchCollectiveApplication(activeBatch.value.id);
      printHtml(typeof data === "string" ? data : String(data));
    } else {
      const { data } = await exportCollectiveApplicationDocx(activeBatch.value.id);
      downloadBlob(data, `${batchRegionTail()}农村土地承包经营权集体登记申请书.docx`);
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "集体申请书处理失败");
  } finally {
    applicationLoading.value = false;
  }
}

async function handleHouseholdApplication(row, command) {
  if (!row?.contractorUid || !activeBatch.value) return;
  applicationLoading.value = true;
  try {
    if (command === "print") {
      const { data } = await fetchHouseholdApplication(activeBatch.value.id, row.contractorUid);
      printHtml(typeof data === "string" ? data : String(data));
    } else {
      const { data } = await exportHouseholdApplicationDocx(activeBatch.value.id, row.contractorUid);
      const name = row.cbfmc || row.cbfbm || "承包户";
      downloadBlob(data, `${name}农村土地承包经营权单户登记申请书.docx`);
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "单户申请书处理失败");
  } finally {
    applicationLoading.value = false;
  }
}

// 工具栏批量签订：
// - 勾选了承包户 → 对勾选的户逐户签订；
// - 未勾选 → 确认后对当前批次**全部未签订**的承包户批量签订（已签订的跳过，避免重复出新版本）。
async function handleBatchSign() {
  if (!activeBatch.value) return;
  if (activeBatch.value?.status === "finished") {
    ElMessage.warning("调查批次已结束，不能生成合同");
    return;
  }
  if (selectedRows.value.length) {
    generateDialog.value?.open({
      contractors: selectedRows.value.map((row) => ({ contractorUid: row.contractorUid, cbfmc: row.cbfmc })),
    });
    return;
  }
  // 未勾选：拉全批次列表（翻页收集）筛出未签订户
  collecting.value = true;
  let all = [];
  try {
    all = await collectAllRows();
  } catch {
    ElMessage.error("获取批次承包户列表失败");
    return;
  } finally {
    collecting.value = false;
  }
  const pending = all.filter((row) => !row.signed && row.canSign);
  if (!pending.length) {
    ElMessage.info(all.length ? "当前批次所有承包户均已签订合同" : "当前批次暂无承包户");
    return;
  }
  const skipCount = all.length - pending.length;
  try {
    await ElMessageBox.confirm(
      `未勾选承包户，将对当前批次全部未签订的承包户签订合同：共 ${pending.length} 户${skipCount ? `（${skipCount} 户已签订，自动跳过）` : ""}。是否继续？`,
      "批量签订",
      { type: "warning", confirmButtonText: "继续", cancelButtonText: "取消" },
    );
  } catch {
    return; // 用户取消
  }
  generateDialog.value?.open({
    contractors: pending.map((row) => ({ contractorUid: row.contractorUid, cbfmc: row.cbfmc })),
  });
}

// 翻页收集当前批次（带当前筛选条件）的全部承包户行
async function collectAllRows() {
  const all = [];
  let page = 1;
  while (true) {
    const { data } = await fetchBatchContractOverview(activeBatch.value.id, {
      page,
      page_size: 200,
      keyword: taskKeyword.value || undefined,
      ...buildRegionParams(),
    });
    const items = data.data?.items || [];
    all.push(...items);
    const total = data.data?.total || 0;
    if (!items.length || all.length >= total) break;
    page += 1;
  }
  return all;
}

function onSignCompleted({ successCount }) {
  if (successCount > 0) loadRows();
}
</script>

<style scoped>
/* 左侧调查批次面板 + 承包户合同关键信息列表的双栏布局（与承包方管理页同构）。 */
.contract-manage-empty {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
}

.contract-manage-body {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 12px;
  overflow: hidden;
}

.contract-manage-body.is-batch-collapsed {
  grid-template-columns: 42px minmax(0, 1fr);
}

.contract-manage-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

@media (max-width: 960px) {
  .contract-manage-body {
    grid-template-columns: 1fr;
    overflow: visible;
  }
}

.contract-manage-page {
  min-height: 0;
}

.contract-row-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0 4px;
}
</style>
