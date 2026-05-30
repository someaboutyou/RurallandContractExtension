<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div class="panel-title">数据导入</div>
      <div class="toolbar-actions">
        <el-input v-model="keyword" clearable placeholder="搜索批次号或名称" style="width: 220px" @keyup.enter="loadBatches" />
        <el-button plain @click="loadBatches">刷新</el-button>
        <el-button v-if="canManage" type="success" @click="openCreateDialog">新建导入批次</el-button>
      </div>
    </div>

    <div class="table-shell">
      <div class="table-scroll">
        <el-table v-loading="loading" :data="rows" border>
          <el-table-column prop="importNo" label="导入批次号" min-width="170" />
          <el-table-column prop="importName" label="导入名称" min-width="180" />
          <el-table-column prop="sourceName" label="最近文件" min-width="180" />
          <el-table-column prop="status" label="状态" min-width="120">
            <template #default="{ row }">
              <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">
                {{ importStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="totalCount" label="总行数" min-width="90" />
          <el-table-column prop="successCount" label="成功" min-width="90" />
          <el-table-column prop="failedCount" label="失败" min-width="90" />
          <el-table-column prop="importedByName" label="导入人" min-width="120" />
          <el-table-column prop="createdAt" label="创建时间" min-width="180" />
          <el-table-column label="操作" fixed="right" min-width="220">
            <template #default="{ row }">
              <div class="table-actions">
                <el-button v-if="canManage" link type="primary" @click="openUploadDialog(row)">上传数据</el-button>
                <el-button link type="primary" @click="openRows(row)">行明细</el-button>
                <el-button link type="warning" @click="handleDownloadFailedRows(row)">失败行</el-button>
                <el-button v-if="canRollback(row)" link type="danger" @click="handleRollback(row)">回滚</el-button>
              </div>
            </template>
          </el-table-column>
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
  </section>

  <el-dialog v-model="createVisible" title="新建导入批次" width="620px">
    <el-form :model="form" label-position="top">
      <el-form-item label="导入名称">
        <el-input v-model="form.importName" placeholder="例如：存量承包方数据导入" />
      </el-form-item>
      <el-form-item label="数据提供单位">
        <el-input v-model="form.sourceOrg" placeholder="请输入数据来源单位" />
      </el-form-item>
      <el-form-item label="区域代码">
        <el-tree-select
          v-model="form.regionId"
          clearable
          filterable
          lazy
          check-strictly
          :data="regionTree"
          :props="regionTreeProps"
          :load="loadRegionNode"
          :filter-method="handleRegionFilter"
          node-key="id"
          placeholder="请选择导入区域"
          @change="handleRegionChange"
        />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createVisible = false">取消</el-button>
      <el-button :loading="submitting" type="success" @click="handleCreate">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="uploadVisible" :title="`上传数据 - ${activeBatch?.importName || ''}`" width="640px">
    <el-form label-position="top">
      <el-alert
        class="upload-tip"
        type="info"
        show-icon
        :closable="false"
        title="请上传包含 FileGDB（.gdb 目录）的 ZIP 压缩包，系统会自动导入 FBF、CBF、CBF_JTCY、CBDKXX、DK 图层。"
      />
      <el-form-item label="GDB ZIP 文件">
        <input type="file" :accept="uploadAccept" :disabled="uploading" @change="handleFileChange" />
      </el-form-item>
      <div v-if="importProgress" class="import-progress">
        <div class="progress-meta">
          <span>{{ progressStatusLabel(importProgress.status) }}</span>
          <span>{{ importProgress.processedRows || 0 }}/{{ importProgress.totalRows || 0 }}</span>
        </div>
        <el-progress :percentage="Number(importProgress.percent || 0)" :status="progressBarStatus" />
        <div class="progress-message">{{ importProgress.message || importProgress.currentLayer || "" }}</div>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="uploadVisible = false">关闭</el-button>
      <el-button v-if="canCancelImport" type="warning" plain @click="handleCancelImport">取消导入</el-button>
      <el-button :loading="uploading" :disabled="uploading" type="success" @click="handleUpload">上传并导入</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="rowsVisible" title="导入行明细" size="70%">
    <div class="toolbar">
      <div class="toolbar-actions">
        <el-select v-model="rowStatusFilter" clearable placeholder="行状态" style="width: 150px" @change="reloadRows">
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button plain @click="reloadRows">刷新</el-button>
      </div>
    </div>
    <el-table v-loading="rowLoading" :data="detailRows" border>
      <el-table-column prop="rowNo" label="行号" width="80" />
      <el-table-column prop="entityType" label="类型" width="110" />
      <el-table-column prop="entityKey" label="业务键" min-width="180" />
      <el-table-column prop="operationType" label="操作" width="100" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : 'danger'">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="errorMessage" label="错误信息" min-width="260" />
    </el-table>
  </el-drawer>
</template>

<script setup>
import { computed, onUnmounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createImportBatch,
  cancelImport,
  downloadFailedImportRows,
  fetchImportBatches,
  fetchImportProgress,
  fetchImportRows,
  rollbackImport,
  uploadImportGdb,
} from "../api/dataImport";
import { fetchRegionChildren, searchRegions } from "../api/region";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));
const loading = ref(false);
const submitting = ref(false);
const uploading = ref(false);
const rowLoading = ref(false);
const rows = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const createVisible = ref(false);
const uploadVisible = ref(false);
const rowsVisible = ref(false);
const activeBatch = ref(null);
const selectedFile = ref(null);
const importProgress = ref(null);
const detailRows = ref([]);
const rowStatusFilter = ref("");
const regionTree = ref([]);
const regionTreeProps = { label: "fullName", children: "children", isLeaf: "leaf" };
const selectedRegionMap = ref(new Map());
const form = reactive({ importName: "", sourceOrg: "", regionId: undefined, regionCode: "", regionName: "", remark: "" });
const uploadAccept = ".zip,application/zip";
const importDoneStatuses = ["success", "partial_success", "failed", "canceled"];
const importActiveBatchStatuses = ["processing"];
let progressTimer = null;
let regionSearchTimer = null;

const progressBarStatus = computed(() => {
  if (!importProgress.value) return undefined;
  if (importProgress.value.status === "failed" || importProgress.value.status === "canceled") return "exception";
  if (importDoneStatuses.includes(importProgress.value.status)) return "success";
  return undefined;
});

const canCancelImport = computed(() => {
  return importProgress.value && !importDoneStatuses.includes(importProgress.value.status) && importProgress.value.status !== "cancel_requested";
});

function importStatusLabel(value) {
  return { uploaded: "已创建", processing: "处理中", canceled: "已取消", rolled_back: "已回滚", success: "成功", partial_success: "部分成功", failed: "失败" }[value] || value;
}

function progressStatusLabel(value) {
  return {
    queued: "等待导入",
    running: "正在导入",
    processing: "处理中",
    cancel_requested: "正在取消",
    canceled: "已取消",
    rolled_back: "已回滚",
    success: "导入成功",
    partial_success: "部分成功",
    failed: "导入失败",
  }[value] || value;
}

function canRollback(row) {
  return canManage.value && ["success", "partial_success", "failed", "canceled"].includes(row.status);
}

function isActiveImportBatch(row) {
  return row && importActiveBatchStatuses.includes(row.status);
}

async function loadBatches() {
  loading.value = true;
  try {
    const { data } = await fetchImportBatches({ page: page.value, page_size: pageSize.value, keyword: keyword.value || undefined });
    rows.value = data.data.items;
    total.value = data.data.total;
  } finally {
    loading.value = false;
  }
}

function openCreateDialog() {
  Object.assign(form, { importName: "", sourceOrg: "", regionId: undefined, regionCode: "", regionName: "", remark: "" });
  createVisible.value = true;
}

async function handleCreate() {
  if (!form.importName.trim()) {
    ElMessage.warning("请输入导入名称");
    return;
  }
  if (!form.regionCode) {
    ElMessage.warning("请选择导入区域");
    return;
  }
  submitting.value = true;
  try {
    await createImportBatch({
      ...form,
      importName: form.importName.trim(),
      sourceType: "gdb",
      regionId: undefined,
    });
    ElMessage.success("导入批次已创建");
    createVisible.value = false;
    await loadBatches();
  } finally {
    submitting.value = false;
  }
}

function flattenRegions(nodes, result = []) {
  for (const item of nodes || []) {
    result.push(item);
    flattenRegions(item.children, result);
  }
  return result;
}

function handleRegionChange(value) {
  const selected = selectedRegionMap.value.get(value) || flattenRegions(regionTree.value).find((item) => item.id === value);
  form.regionCode = selected?.code || "";
  form.regionName = selected?.fullName || "";
}

function rememberRegions(nodes) {
  for (const item of nodes || []) {
    selectedRegionMap.value.set(item.id, item);
    rememberRegions(item.children || []);
  }
}

async function loadRegionRoots() {
  const { data } = await fetchRegionChildren({ includeGroups: true });
  regionTree.value = data.data;
  rememberRegions(regionTree.value);
}

async function loadRegionNode(node, resolve) {
  if (node.level === 0) {
    resolve(regionTree.value);
    return;
  }
  const { data } = await fetchRegionChildren({ parentId: node.data.id, includeGroups: true });
  rememberRegions(data.data);
  resolve(data.data);
}

function handleRegionFilter(keyword) {
  window.clearTimeout(regionSearchTimer);
  regionSearchTimer = window.setTimeout(async () => {
    if (!keyword) {
      await loadRegionRoots();
      return;
    }
    const { data } = await searchRegions({ keyword, includeGroups: true, limit: 80 });
    regionTree.value = data.data;
    rememberRegions(regionTree.value);
  }, 250);
}

function openUploadDialog(row) {
  stopProgressPolling();
  activeBatch.value = row;
  selectedFile.value = null;
  importProgress.value = null;
  uploadVisible.value = true;
  uploading.value = false;
  if (isActiveImportBatch(row)) {
    importProgress.value = buildProgressFromBatch(row);
    uploading.value = true;
    startProgressPolling();
  }
}

function buildProgressFromBatch(row) {
  const totalRows = row.totalCount || 0;
  const processedRows = (row.successCount || 0) + (row.failedCount || 0);
  return {
    batchId: row.id,
    jobId: null,
    status: row.status,
    totalRows,
    processedRows,
    successRows: row.successCount || 0,
    failedRows: row.failedCount || 0,
    percent: totalRows ? Number(((processedRows * 100) / totalRows).toFixed(2)) : 0,
    message: "正在获取导入进度",
  };
}

function handleFileChange(event) {
  selectedFile.value = event.target.files?.[0] || null;
}

async function handleUpload() {
  if (!activeBatch.value || !selectedFile.value) {
    ElMessage.warning("请先选择 GDB ZIP 文件");
    return;
  }
  const formData = new FormData();
  formData.append("file", selectedFile.value);
  uploading.value = true;
  try {
    const { data } = await uploadImportGdb(activeBatch.value.id, formData);
    importProgress.value = {
      batchId: activeBatch.value.id,
      jobId: data.data.jobId,
      status: data.data.status,
      totalRows: 0,
      processedRows: 0,
      percent: 0,
      message: "后台导入任务已提交",
    };
    ElMessage.success("导入任务已提交");
    startProgressPolling();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导入失败");
    uploading.value = false;
  }
}

function startProgressPolling() {
  stopProgressPolling();
  pollImportProgress();
  progressTimer = window.setInterval(pollImportProgress, 1500);
}

function stopProgressPolling() {
  if (progressTimer) {
    window.clearInterval(progressTimer);
    progressTimer = null;
  }
}

async function pollImportProgress() {
  if (!activeBatch.value) return;
  try {
    const { data } = await fetchImportProgress(activeBatch.value.id);
    importProgress.value = data.data;
    if (importDoneStatuses.includes(importProgress.value.status)) {
      stopProgressPolling();
      uploading.value = false;
      await loadBatches();
    }
  } catch (error) {
    stopProgressPolling();
    uploading.value = false;
    ElMessage.error(error.response?.data?.detail || "获取导入进度失败");
  }
}

async function handleCancelImport() {
  if (!activeBatch.value) return;
  try {
    const { data } = await cancelImport(activeBatch.value.id);
    importProgress.value = data.data;
    ElMessage.info("已请求取消导入");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "取消导入失败");
  } finally {
    await loadBatches();
  }
}

async function handleRollback(row) {
  try {
    await ElMessageBox.confirm(`确认回滚导入批次「${row.importName}」吗？`, "回滚导入", {
      type: "warning",
      confirmButtonText: "回滚",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    await rollbackImport(row.id);
    ElMessage.success("批次已回滚");
    await loadBatches();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "回滚失败");
  }
}

async function handleDownloadFailedRows(row) {
  const { data } = await downloadFailedImportRows(row.id);
  downloadBlob(data, `${row.importNo || row.id}_failed_rows.csv`);
}

function downloadBlob(data, filename) {
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function openRows(row) {
  activeBatch.value = row;
  rowStatusFilter.value = "";
  rowsVisible.value = true;
  await reloadRows();
}

async function reloadRows() {
  if (!activeBatch.value) {
    detailRows.value = [];
    return;
  }
  rowLoading.value = true;
  try {
    const { data } = await fetchImportRows(activeBatch.value.id, {
      page: 1,
      page_size: 200,
      status: rowStatusFilter.value || undefined,
    });
    detailRows.value = data.data.items;
  } finally {
    rowLoading.value = false;
  }
}

function handlePageChange(value) {
  page.value = value;
  loadBatches();
}

async function loadRegionTree() {
  await loadRegionRoots();
}

loadRegionTree();
loadBatches();
onUnmounted(() => {
  stopProgressPolling();
  window.clearTimeout(regionSearchTimer);
});
</script>

<style scoped>
.upload-tip {
  margin-bottom: 16px;
}

.import-progress {
  margin-top: 12px;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.progress-message {
  min-height: 20px;
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
