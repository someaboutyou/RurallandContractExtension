<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div class="panel-title">承包地块管理</div>
      <div class="toolbar-actions">
        <el-input
          v-model="keyword"
          clearable
          placeholder="搜索发包方/承包方名称或编码"
          style="width: 250px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button plain @click="handleSearch">查询</el-button>
        <el-button plain @click="load">刷新</el-button>
        <el-button v-if="canManage" plain :disabled="!batchId" @click="importVisible = true">导入</el-button>
        <el-button v-if="canManage" plain :disabled="!batchId" @click="handleAdd">添加</el-button>
        <el-button
          v-if="canManage"
          plain
          type="danger"
          :disabled="!selectedRows.length || !batchId"
          @click="handleDelete"
        >
          删除{{ selectedRows.length ? `(${selectedRows.length})` : "" }}
        </el-button>
        <el-dropdown
          trigger="click"
          :disabled="!selectedRows.length || exporting"
          @command="handleExportCommand"
        >
          <el-button
            type="primary"
            :disabled="!selectedRows.length || exporting"
            :loading="exporting"
          >
            导出{{ selectedRows.length ? `(${selectedRows.length})` : "" }}
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="survey">地块调查表</el-dropdown-item>
              <el-dropdown-item command="sketch">地块示意图</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <div class="table-shell">
      <div class="table-scroll">
        <el-table
          v-loading="loading"
          :data="treeRows"
          row-key="rowKey"
          :tree-props="{ children: 'children' }"
          default-expand-all
          border
          :row-class-name="rowClassName"
          @selection-change="handleSelectionChange"
          @row-click="handleRowClick"
          @row-dblclick="handleRowDblClick"
        >
          <el-table-column type="selection" width="44" :selectable="isSelectableRow" />
          <el-table-column label="地块名称" min-width="240">
            <template #default="{ row }">
              <span :class="{ 'parcel-group-label': row.isGroup }">{{ row.dkmc || "-" }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="dkbm" label="地块编码" min-width="190" show-overflow-tooltip />
          <el-table-column label="二轮合同面积(亩)" min-width="140" align="right">
            <template #default="{ row }">{{ formatAreaValue(row.twoRoundArea) }}</template>
          </el-table-column>
          <el-table-column label="实测面积(亩)" min-width="120" align="right">
            <template #default="{ row }">{{ formatAreaValue(row.actualArea) }}</template>
          </el-table-column>
          <el-table-column label="延包面积(亩)" min-width="120" align="right">
            <template #default="{ row }">{{ formatAreaValue(row.delayArea) }}</template>
          </el-table-column>
          <el-table-column label="确权面积(亩)" min-width="120" align="right">
            <template #default="{ row }">{{ formatAreaValue(row.confirmedArea) }}</template>
          </el-table-column>
          <el-table-column prop="landUseLabel" label="土地利用类型" min-width="120" />
          <el-table-column prop="parcelCategoryLabel" label="地块类别" min-width="110" />
          <el-table-column prop="basicFarmlandLabel" label="基本农田" min-width="90" align="center" />
          <el-table-column prop="stockParcelLabel" label="是否确股地块" min-width="110" align="center" />
          <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
        </el-table>
      </div>
    </div>

    <div class="pagination-wrap">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        background
        layout="total, prev, pager, next"
        @current-change="handlePageChange"
      />
    </div>

    <AddParcelDialog
      ref="addParcelDialog"
      :batch-id="batchId"
      :contractor-uid="addTarget?.contractorUid || ''"
      :existing-parcel-codes="addExistingCodes"
      :require-geometry="false"
      @done="handleAddDone"
    />

    <ContractorResultDialog
      ref="contractorDialog"
      v-model="contractorDialogVisible"
      :active-batch="selectedBatch"
      :can-manage="canManage"
      :can-write="true"
      :tasks="[]"
      :active-region-code="selectedBatch?.regionCode || ''"
      :active-region-label="selectedBatch?.regionName || ''"
      @saved="load"
    />

    <ParcelImportDialog
      v-model="importVisible"
      :batch="selectedBatch"
      @imported="load"
    />
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import AddParcelDialog from "../components/survey/AddParcelDialog.vue";
import ParcelImportDialog from "../components/survey/ParcelImportDialog.vue";
import ContractorResultDialog from "../components/survey/view/ContractorResultDialog.vue";
import {
  exportParcelSketchPdf,
  exportParcelSurveyDocx,
  fetchCurrentSurveyBatch,
  fetchParcelsOverview,
  fetchSurveyBatches,
  persistSurveyPendingOperation,
  removeSurveyParcel,
} from "../api/survey";
import { useDictionary } from "../composables/useDictionary";
import { useAuthStore } from "../stores/auth";
import { sqmToMu } from "../utils/areaUnits";

const { labelOf: landUseLabel } = useDictionary("nyt2539_c09_land_use");
const { labelOf: parcelCategoryLabel } = useDictionary("nyt2539_c07_parcel_category");
const { labelOf: yesNoLabel } = useDictionary("nyt2539_c19_yes_no");

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));

const loading = ref(false);
const exporting = ref(false);
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const selectedRows = ref([]);
const currentRow = ref(null);

const batches = ref([]);
const batchId = ref(null);
const importVisible = ref(false);
const selectedBatch = computed(
  () => batches.value.find((batch) => batch.id === batchId.value) || null
);

const addParcelDialog = ref(null);
const addTarget = ref(null);
const addExistingCodes = ref([]);
const contractorDialog = ref(null);
const contractorDialogVisible = ref(false);

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

/** 二轮合同面积（亩）：优先 NY/T 原合同面积（亩），否则由平方米换算。 */
function twoRoundAreaMu(parcel) {
  const mu = toNumber(parcel.yhtmjm);
  if (mu !== null) return mu;
  const sqm = toNumber(parcel.htmj);
  return sqm !== null ? sqmToMu(sqm) : 0;
}

/** 实测面积（亩）：库内为平方米。 */
function actualAreaMu(parcel) {
  const sqm = toNumber(parcel.scmj);
  return sqm !== null ? sqmToMu(sqm) : 0;
}

/** 确权面积（亩）：优先 NY/T 确权（合同）面积（亩），否则退回实测面积。 */
function confirmedAreaMu(parcel) {
  const mu = toNumber(parcel.htmjm);
  if (mu !== null) return mu;
  return actualAreaMu(parcel);
}

/** 延包面积：CS 版对应 ZD_CBD.YBMJ，当前 Web 结果表尚未落该字段，固定 0.00。 */
function delayAreaMu() {
  return 0;
}

function formatAreaValue(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "";
  return num.toFixed(2);
}

function sumBy(rows, key) {
  return rows.reduce((acc, row) => acc + (Number(row[key]) || 0), 0);
}

function toParcelRow(parcel, group) {
  return {
    rowKey: `parcel-${parcel.cbfbm}-${parcel.dkbm}`,
    isGroup: false,
    cbfbm: parcel.cbfbm,
    cbfmc: group?.cbfmc || parcel.cbfmc || "",
    contractorUid: group?.contractorUid || "",
    dkmc: parcel.dkmc,
    dkbm: parcel.dkbm,
    twoRoundArea: twoRoundAreaMu(parcel),
    actualArea: actualAreaMu(parcel),
    delayArea: delayAreaMu(parcel),
    confirmedArea: confirmedAreaMu(parcel),
    landUseLabel: landUseLabel(parcel.tdlylx) || parcel.tdlylx || "",
    parcelCategoryLabel: parcelCategoryLabel(parcel.dklb) || parcel.dklb || "",
    basicFarmlandLabel: yesNoLabel(parcel.sfjbnt) || (parcel.sfjbnt === "1" ? "是" : "否"),
    stockParcelLabel: yesNoLabel(parcel.sfqqqg) || (parcel.sfqqqg === "1" ? "是" : "否"),
    remark: parcel.dkbzxx || "",
  };
}

function buildGroup(group) {
  const parcels = (group.parcels || []).map((parcel) => toParcelRow(parcel, group));
  const name = group.cbfmc || group.cbfbm || "";
  return {
    rowKey: `group-${group.cbfbm}`,
    isGroup: true,
    cbfbm: group.cbfbm,
    cbfmc: group.cbfmc,
    contractorUid: group.contractorUid,
    dkmc: `${name}(地块数:${group.parcelCount ?? parcels.length})(户号:${group.householdNo})`,
    dkbm: "",
    twoRoundArea: sumBy(parcels, "twoRoundArea"),
    actualArea: sumBy(parcels, "actualArea"),
    delayArea: sumBy(parcels, "delayArea"),
    confirmedArea: sumBy(parcels, "confirmedArea"),
    landUseLabel: "",
    parcelCategoryLabel: "",
    basicFarmlandLabel: "",
    stockParcelLabel: "",
    remark: "",
    children: parcels,
  };
}

const treeRows = computed(() => items.value.map(buildGroup));

function isSelectableRow(row) {
  return !row.isGroup;
}

function handleSelectionChange(rows) {
  selectedRows.value = rows || [];
}

function handleRowClick(row) {
  currentRow.value = row;
}

function resolveTargetGroup() {
  const row = currentRow.value || selectedRows.value[0];
  if (!row?.cbfbm) return null;
  return items.value.find((group) => group.cbfbm === row.cbfbm) || null;
}

async function handleAdd() {
  if (!batchId.value) {
    ElMessage.warning("请先选择调查批次");
    return;
  }
  const group = resolveTargetGroup();
  if (!group) {
    ElMessage.warning("请先点击选择承包方或地块，再新增地块");
    return;
  }
  addTarget.value = group;
  addExistingCodes.value = (group.parcels || []).map((parcel) => parcel.dkbm).filter(Boolean);
  await nextTick();
  addParcelDialog.value?.open();
}

async function handleAddDone(operation) {
  if (!batchId.value || !addTarget.value) return;
  try {
    await persistSurveyPendingOperation(batchId.value, addTarget.value.contractorUid, operation);
    ElMessage.success("承包地块已添加");
    await load();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "添加承包地块失败");
  }
}

async function handleDelete() {
  if (!batchId.value) {
    ElMessage.warning("请先选择调查批次");
    return;
  }
  const rows = selectedRows.value.filter((row) => !row.isGroup && row.dkbm);
  if (!rows.length) {
    ElMessage.warning("请先勾选要删除的承包地块");
    return;
  }
  let reason = "";
  try {
    const { value } = await ElMessageBox.prompt("请输入删除原因", "删除承包地块", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      inputType: "textarea",
      type: "warning",
      inputValidator: (text) => Boolean(text?.trim()) || "请输入删除原因",
    });
    reason = value;
  } catch {
    return;
  }

  const groups = new Map();
  for (const row of rows) {
    const list = groups.get(row.contractorUid) || [];
    list.push(row.dkbm);
    groups.set(row.contractorUid, list);
  }

  let failed = 0;
  for (const [contractorUid, dkbms] of groups) {
    for (const dkbm of dkbms) {
      try {
        await removeSurveyParcel(batchId.value, contractorUid, { dkbm, reason });
      } catch {
        failed += 1;
      }
    }
  }
  if (failed) {
    ElMessage.warning(`已删除 ${rows.length - failed} 个地块，${failed} 个失败`);
  } else {
    ElMessage.success(`已删除 ${rows.length} 个承包地块`);
  }
  await load();
}

function handleRowDblClick(row) {
  if (row.isGroup) return;
  if (!batchId.value || !selectedBatch.value) {
    ElMessage.warning("请先选择调查批次");
    return;
  }
  if (!row.contractorUid) {
    ElMessage.warning("缺少承包方标识，无法进入编辑");
    return;
  }
  contractorDialog.value?.openForResult(
    selectedBatch.value,
    {
      batchId: selectedBatch.value.id,
      contractorUid: row.contractorUid,
      cbfbm: row.cbfbm,
      cbfmc: row.cbfmc,
    },
    { panel: "parcels" }
  );
}

function parseFilename(disposition, fallback) {
  if (!disposition) return fallback;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (utf8) return decodeURIComponent(utf8[1]);
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain ? decodeURIComponent(plain[1]) : fallback;
}

function downloadBlob(data, filename) {
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function selectedExportItems() {
  return selectedRows.value
    .filter((row) => !row.isGroup && row.dkbm)
    .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm }));
}

async function handleExportCommand(command) {
  const itemsToExport = selectedExportItems();
  if (!itemsToExport.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  exporting.value = true;
  try {
    if (command === "sketch") {
      const response = await exportParcelSketchPdf({ items: itemsToExport });
      const isZip = String(response.data?.type || "").includes("zip");
      const fallback = isZip ? "承包地块示意图.zip" : "承包地块示意图.pdf";
      const filename = parseFilename(response.headers?.["content-disposition"], fallback);
      downloadBlob(response.data, filename);
      ElMessage.success(`已导出 ${itemsToExport.length} 个地块示意图`);
    } else {
      const response = await exportParcelSurveyDocx({ items: itemsToExport });
      const isZip = String(response.data?.type || "").includes("zip");
      const fallback = isZip ? "承包地块调查表.zip" : "承包地块调查表.docx";
      const filename = parseFilename(response.headers?.["content-disposition"], fallback);
      downloadBlob(response.data, filename);
      ElMessage.success(`已导出 ${itemsToExport.length} 个地块调查表`);
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导出失败");
  } finally {
    exporting.value = false;
  }
}

async function loadBatches() {
  try {
    const { data } = await fetchSurveyBatches({ page: 1, page_size: 100 });
    batches.value = data.data.items || [];
    try {
      const current = await fetchCurrentSurveyBatch();
      if (current.data.data?.id) {
        batchId.value = current.data.data.id;
        return;
      }
    } catch {
      // 忽略：回退到进行中/第一个批次
    }
    const active = batches.value.find((batch) => batch.status === "active");
    batchId.value = (active || batches.value[0])?.id ?? null;
  } catch {
    batches.value = [];
    batchId.value = null;
  }
}

async function load() {
  loading.value = true;
  try {
    const { data } = await fetchParcelsOverview({
      page: page.value,
      pageSize: pageSize.value,
      keyword: keyword.value.trim() || undefined,
    });
    items.value = data.data.items || [];
    total.value = data.data.total || 0;
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "加载承包地块失败");
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  load();
}

function handlePageChange(value) {
  page.value = value;
  load();
}

onMounted(async () => {
  await loadBatches();
  await load();
});
</script>

<style scoped>
.parcel-group-row {
  background: #dfe9f5;
}

.parcel-group-row :deep(td) {
  background: #dfe9f5 !important;
  font-weight: 600;
}

.parcel-group-label {
  font-weight: 600;
}

.parcel-child-row :deep(td) {
  background: #fff;
}
</style>
