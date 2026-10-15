<template>
  <section class="panel data-export-page">
    <div class="export-layout">
      <!-- 左栏：区域树 -->
      <aside class="region-panel">
        <div class="region-panel-head">
          <div>
            <div class="region-panel-title">区域选择</div>
            <div class="region-panel-subtitle">在县 / 镇 / 村 / 组上点击「导出」生成数据包</div>
          </div>
        </div>
        <div class="format-row">
          <span class="format-label">导出格式</span>
          <el-select v-model="exportFormat" size="small" class="format-select">
            <el-option label="清册 CSV（Excel 打开）" value="contractor_roster" />
            <el-option label="GDB 数据库（NY/T 2539）" value="nyt2539_gdb" />
            <el-option label="SQLite DB（NY/T 2539）" value="nyt2539_db" />
            <el-option label="MDB + SHP（NY/T 2539）" value="nyt2539_mdb_shp" />
          </el-select>
        </div>
        <div class="format-tip">标准格式只导出有效数据（排除注销 / 消亡 / 历史合同 / 移除成员）；数据量大时生成需要数十秒到几分钟。</div>
        <el-input
          v-model="regionKeyword"
          class="region-filter-search"
          clearable
          placeholder="按区域名称搜索"
          @keyup.enter="handleRegionFilter"
          @clear="handleRegionFilter"
        />
        <el-tree
          ref="treeRef"
          class="region-tree"
          node-key="id"
          :data="regionTree"
          :props="regionTreeProps"
          :load="loadRegionNode"
          lazy
          :expand-on-click-node="false"
          :filter-node-method="filterRegionNode"
        >
          <template #default="{ node, data }">
            <div class="region-tree-node">
              <!-- 短名展示（层级已由树结构表达），fullName 放 tooltip -->
              <span class="region-tree-label" :title="node.label">{{ data.name || node.label }}</span>
              <el-button
                v-if="data.level && data.level !== 'province'"
                size="small"
                type="primary"
                link
                :loading="exportingId === data.id"
                @click.stop="handleExport(data)"
              >
                导出
              </el-button>
            </div>
          </template>
        </el-tree>
      </aside>

      <!-- 右栏：导出记录列表 -->
      <div class="record-panel">
        <div class="toolbar">
          <div class="panel-title">导出记录</div>
          <div class="toolbar-actions">
            <el-input v-model="keyword" clearable placeholder="搜索区域 / 编号" style="width: 220px" @keyup.enter="loadRecords" />
            <el-button plain @click="loadRecords">刷新</el-button>
          </div>
        </div>

        <div class="table-shell">
          <div class="table-scroll">
            <el-table v-loading="loading" :data="rows" border>
              <el-table-column prop="exportNo" label="导出编号" min-width="170" />
              <el-table-column label="区域" min-width="220">
                <template #default="{ row }">
                  <div>{{ row.regionName || "—" }}</div>
                  <div class="cell-sub">{{ row.regionCode || "" }}（{{ levelLabel(row.regionLevel) }}）</div>
                </template>
              </el-table-column>
              <el-table-column label="格式" min-width="130">
                <template #default="{ row }">{{ exportTypeLabel(row.exportType) }}</template>
              </el-table-column>
              <el-table-column prop="recordCount" label="记录数" min-width="90" />
              <el-table-column label="状态" min-width="160">
                <template #default="{ row }">
                  <el-tag v-if="row.isHistorical" type="info">历史</el-tag>
                  <el-tag v-else-if="row.status !== 'processing'" :type="row.status === 'success' ? 'success' : 'danger'">
                    {{ statusLabel(row.status) }}
                  </el-tag>
                  <template v-else>
                    <el-progress
                      class="export-progress"
                      :percentage="row.progress || 0"
                      :stroke-width="8"
                    />
                    <div class="progress-msg">{{ row.progressMessage || "正在生成…" }}</div>
                  </template>
                </template>
              </el-table-column>
              <el-table-column prop="operatorName" label="操作人" min-width="120" />
              <el-table-column label="创建时间" min-width="160">
                <template #default="{ row }">{{ formatDateTime(row.createdAt) }}</template>
              </el-table-column>
              <el-table-column label="操作" fixed="right" min-width="180">
                <template #default="{ row }">
                  <div class="table-actions">
                    <el-button
                      link
                      type="primary"
                      :disabled="row.isHistorical || row.status !== 'success'"
                      @click="handleDownload(row)"
                    >
                      下载
                    </el-button>
                    <el-button
                      v-if="!row.isHistorical"
                      link
                      type="warning"
                      :disabled="row.status === 'processing'"
                      @click="handleClear(row)"
                    >
                      清除
                    </el-button>
                    <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
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
      </div>
    </div>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { fetchRegionChildren, searchRegions } from "../api/region";
import {
  clearDataExport,
  createDataExport,
  deleteDataExport,
  downloadDataExport,
  fetchDataExports,
} from "../api/dataExport";

const regionTreeProps = { label: "fullName", children: "children", isLeaf: "leaf" };

const treeRef = ref(null);
const regionTree = ref([]);
const regionKeyword = ref("");
const exportingId = ref(null);

const loading = ref(false);
const rows = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");

let regionSearchTimer = null;

const LEVEL_LABELS = { county: "县级", town: "镇级", village: "村级", group: "组级" };
const STATUS_LABELS = { processing: "生成中", success: "成功", failed: "失败" };
const EXPORT_TYPE_LABELS = {
  contractor_roster: "清册 CSV",
  nyt2539_gdb: "GDB 数据库",
  nyt2539_db: "SQLite DB",
  nyt2539_mdb_shp: "MDB + SHP",
};

const exportFormat = ref("contractor_roster");

function exportTypeLabel(value) {
  return EXPORT_TYPE_LABELS[value] || value || "—";
}

function levelLabel(value) {
  return LEVEL_LABELS[value] || value || "—";
}
function statusLabel(value) {
  return STATUS_LABELS[value] || value;
}

function formatDateTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

async function loadRegionRoots() {
  const { data } = await fetchRegionChildren({ includeGroups: true });
  regionTree.value = data.data || [];
}

async function loadRegionNode(node, resolve) {
  if (node.level === 0) {
    resolve(regionTree.value);
    return;
  }
  try {
    const { data } = await fetchRegionChildren({ parentId: node.data.id, includeGroups: true });
    const children = (data.data || []).map((item) => ({
      ...item,
      leaf: item.level === "group",
    }));
    resolve(children);
  } catch (error) {
    resolve([]);
    ElMessage.error(error?.response?.data?.detail || "加载子区域失败");
  }
}

function filterRegionNode(value, data) {
  if (!value) return true;
  const keyword = String(value);
  return (
    String(data.fullName || data.name || "").includes(keyword) ||
    String(data.code || "").includes(keyword)
  );
}

function handleRegionFilter() {
  window.clearTimeout(regionSearchTimer);
  regionSearchTimer = window.setTimeout(async () => {
    const keyword = regionKeyword.value.trim();
    if (!keyword) {
      await loadRegionRoots();
      return;
    }
    try {
      const { data } = await searchRegions({ keyword, includeGroups: true, limit: 80 });
      regionTree.value = data.data || [];
    } catch (error) {
      ElMessage.error(error?.response?.data?.detail || "搜索区域失败");
    }
  }, 250);
}

async function handleExport(data) {
  exportingId.value = data.id;
  // ⛔ 后端 create_export 是同步生成：先落一条 processing 记录再打包，
  // POST 直到打包结束才返回（几十秒~几分钟）。因此不能等响应回来才刷表——
  // 先跳回第 1 页静默刷新，让「生成中」行立刻出现（进度条由 schedulePoll 每 2s 接力），
  // 再继续等最终结果弹成功/失败提示。
  page.value = 1;
  const creating = createDataExport({
    regionCode: data.code,
    regionName: data.fullName || data.name,
    regionLevel: data.level,
    exportType: exportFormat.value,
  });
  window.setTimeout(() => loadRecords(true), 500);
  try {
    const { data: resp } = await creating;
    const record = resp.data;
    if (record.status === "failed") {
      ElMessage.error(`导出失败：${record.errorMessage || "未知错误"}`);
    } else {
      ElMessage.success(`已生成「${data.fullName || data.name}」的数据导出包`);
    }
    await loadRecords();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "导出失败");
  } finally {
    exportingId.value = null;
  }
}

async function loadRecords(silent = false) {
  if (!silent) loading.value = true;
  try {
    const { data } = await fetchDataExports({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    });
    rows.value = data.data.items;
    total.value = data.data.total;
  } catch (error) {
    // 轮询失败保持安静，不打断用户；手动刷新仍弹错
    if (!silent) ElMessage.error(error?.response?.data?.detail || "加载导出记录失败");
  } finally {
    if (!silent) loading.value = false;
  }
  schedulePoll();
}

// 有「生成中」记录时每 2 秒静默轮询，刷新进度条；全部终态后自动停
let pollTimer = null;

function schedulePoll() {
  const hasProcessing = rows.value.some((row) => row.status === "processing");
  if (hasProcessing && !pollTimer) {
    pollTimer = window.setTimeout(async () => {
      pollTimer = null;
      await loadRecords(true);
    }, 2000);
  } else if (!hasProcessing && pollTimer) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function handlePageChange(value) {
  page.value = value;
  loadRecords();
}

async function handleDownload(row) {
  try {
    const { data } = await downloadDataExport(row.id);
    downloadBlob(data, row.fileName || `${row.exportNo}.zip`);
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "下载失败");
  }
}

async function handleClear(row) {
  try {
    await ElMessageBox.confirm(
      `确认清除导出「${row.exportNo}」吗？将删除服务器上的导出文件及产物目录，记录保留为历史（不可再下载）。`,
      "清除导出",
      {
        type: "warning",
        confirmButtonText: "清除",
        cancelButtonText: "取消",
      },
    );
  } catch {
    return;
  }
  try {
    await clearDataExport(row.id);
    ElMessage.success("已清除，记录置为历史");
    await loadRecords();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "清除失败");
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除导出记录「${row.exportNo}」吗？`, "删除导出", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    await deleteDataExport(row.id);
    ElMessage.success("已删除");
    await loadRecords();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "删除失败");
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

onMounted(() => {
  loadRegionRoots();
  loadRecords();
});

onBeforeUnmount(() => {
  if (pollTimer) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
});
</script>

<style scoped>
.data-export-page {
  height: 100%;
}

.export-layout {
  display: flex;
  gap: 16px;
  height: 100%;
  min-height: 0;
}

.region-panel {
  width: 320px;
  flex: 0 0 320px;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px;
  min-height: 0;
}

.region-panel-head {
  margin-bottom: 10px;
}

.region-panel-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.region-panel-subtitle {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.region-filter-search {
  margin-bottom: 10px;
}

.format-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.format-label {
  flex: 0 0 auto;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.format-select {
  flex: 1 1 auto;
  min-width: 0;
}

.format-tip {
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
}

.region-tree {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 8px;
}

.region-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  /* ⛔ 覆盖全局 styles.css 的 .region-tree-node { min-width: 280px }（承包方筛选树专用），
     否则节点被撑到 280px + 树缩进超出 320px 左栏，「导出」按钮被顶出可视区 */
  min-width: 0;
  gap: 8px;
}

.region-tree-label {
  flex: 1 1 auto;
  min-width: 0; /* ⛔ 缺了它 flex 子项不收缩，长 fullName 会把「导出」按钮挤出可视区 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.record-panel {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px;
  min-height: 0;
}

.cell-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.export-progress {
  width: 130px;
  margin-bottom: 2px;
}

.export-progress :deep(.el-progress__text) {
  font-size: 11px !important;
}

.progress-msg {
  font-size: 11px;
  line-height: 1.4;
  color: var(--el-text-color-secondary);
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-actions {
  display: flex;
  gap: 4px;
}
</style>
