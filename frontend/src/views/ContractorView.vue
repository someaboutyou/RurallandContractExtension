<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div>
        <div class="panel-title">承包方管理</div>
      </div>
      <div class="toolbar-actions toolbar-wrap">
        <el-input
          v-model="filters.name"
          clearable
          placeholder="承包方名称"
          style="width: 160px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filters.memberName"
          clearable
          placeholder="家庭成员名称"
          style="width: 160px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filters.idNo"
          clearable
          placeholder="证件号码"
          style="width: 180px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filters.address"
          clearable
          placeholder="承包方地址"
          style="width: 180px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button plain @click="handleSearch">查询</el-button>
        <el-button plain @click="resetFilters">重置</el-button>
        <el-button plain @click="loadData">刷新</el-button>
        <el-button v-if="canManage" type="success" @click="openCreateDialog">新增承包方</el-button>
      </div>
    </div>

    <div class="contractor-workspace">
      <div class="contractor-table-area">
        <div class="table-shell">
          <div class="table-scroll">
            <el-table v-loading="loading" :data="rows" border>
              <el-table-column prop="code" label="承包方代码" min-width="180" />
              <el-table-column prop="name" label="承包方名称" min-width="180" />
              <el-table-column prop="typeCode" label="承包方类型" min-width="120">
                <template #default="{ row }">{{ contractorTypeLabel(row.typeCode) }}</template>
              </el-table-column>
              <el-table-column prop="mobile" label="联系电话" min-width="140" />
              <el-table-column prop="groupRegionName" label="所属组" min-width="180" show-overflow-tooltip />
              <el-table-column prop="address" label="承包方地址" min-width="260" />
              <el-table-column prop="memberCount" label="家庭成员数" min-width="110" />
              <el-table-column prop="surveyorName" label="调查员" min-width="120" />
              <el-table-column prop="surveyDate" label="调查日期" min-width="120" />
              <el-table-column label="操作" fixed="right" min-width="200">
                <template #default="{ row }">
                  <div class="table-actions">
                    <el-button v-if="canManage" link type="primary" @click="openEditDialog(row)">编辑</el-button>
                    <el-button v-if="canManage" link type="danger" @click="handleDelete(row)">删除</el-button>
                    <el-dropdown trigger="click" @command="(command) => handleRowAction(command, row)">
                      <el-button link type="primary" class="row-more-btn" @click.stop>更多</el-button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="downloadCadastral">下载地籍调查表</el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
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
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            background
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </div>

      <RegionFilterPanel
        :region-tree="filterRegionTree"
        :active-region-code="activeRegionCode"
        :active-region-label="activeRegionLabel"
        @select="handleRegionNodeClick"
        @clear="clearRegionFilter"
        @action="handleRegionAction"
      />
    </div>
  </section>

  <ContractorDialog
    ref="contractorDialogRef"
    v-model="dialogVisible"
    :editing-code="editingCode"
    :region-tree="regionTree"
    :can-manage="canManage"
    @saved="handleDialogSaved"
  />
</template>

<script setup>
import { reactive, ref, computed } from "vue";
import { ElLoading, ElMessage, ElMessageBox } from "element-plus";

import {
  deleteContractor,
  fetchCadastralExportArchive,
  fetchCadastralExportProgress,
  fetchCadastralSurveyDocx,
  fetchContractors,
  printCadastralSurveys,
  startCadastralExport,
} from "../api/contractor";
import { fetchRegionTree } from "../api/region";
import { useDictionary } from "../composables/useDictionary";
import { useAuthStore } from "../stores/auth";
import ContractorDialog from "../components/contractors/ContractorDialog.vue";
import RegionFilterPanel from "../components/contractors/RegionFilterPanel.vue";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));
const { labelOf: contractorTypeLabel } = useDictionary("nyt2539_c16_contractor_type");

const loading = ref(false);
const dialogVisible = ref(false);
const editingCode = ref("");
const contractorDialogRef = ref(null);
const rows = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const filters = reactive({
  name: "",
  memberName: "",
  idNo: "",
  address: "",
});
const regionTree = ref([]);
const filterRegionTree = ref([]);
const activeRegionCode = ref("");
const activeRegionLabel = ref("");

function normalizeRegionTree(nodes = []) {
  return nodes.map((item) => ({
    ...item,
    value: item.code,
    label: item.name,
    children: normalizeRegionTree(item.children || []),
  }));
}

async function loadRegionTree() {
  const [{ data: groupTree }, { data: villageTree }] = await Promise.all([
    fetchRegionTree(undefined, { includeGroups: true }),
    fetchRegionTree("village"),
  ]);
  regionTree.value = normalizeRegionTree(groupTree.data || []);
  filterRegionTree.value = normalizeRegionTree(villageTree.data || []);
}

async function loadData() {
  loading.value = true;
  try {
    const { data } = await fetchContractors({
      page: page.value,
      page_size: pageSize.value,
      name: filters.name.trim() || undefined,
      memberName: filters.memberName.trim() || undefined,
      idNo: filters.idNo.trim() || undefined,
      address: filters.address.trim() || undefined,
      regionCode: activeRegionCode.value || undefined,
    });
    rows.value = data.data.items;
    total.value = data.data.total;
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  loadData();
}

function resetFilters() {
  filters.name = "";
  filters.memberName = "";
  filters.idNo = "";
  filters.address = "";
  handleSearch();
}

function handleRegionNodeClick(data) {
  activeRegionCode.value = data.value;
  activeRegionLabel.value = data.label;
  handleSearch();
}

function clearRegionFilter() {
  activeRegionCode.value = "";
  activeRegionLabel.value = "";
  handleSearch();
}

function handleRegionAction({ command, data }) {
  if (command === "printSurveyForms") {
    // 「批量打印调查表」只在组级提供：整村一次上千户，整批渲染会拖垮浏览器。
    if (data?.level !== "group") {
      ElMessage.warning("批量打印调查表仅支持组级区域，请展开村后选择组");
      return;
    }
    printSurveyFormsForRegion(data);
    return;
  }
  if (command === "exportSurveyForms") {
    exportSurveyFormsForRegion(data);
    return;
  }
  if (command === "printRoster") {
    ElMessage.info(`${data?.label || ""}：打印承包方清册功能已预留`);
    return;
  }
  ElMessage.info("该功能尚未实现");
}

function handleRowAction(command, row) {
  if (command === "downloadCadastral") {
    downloadCadastralSurveyDocx(row);
  }
}

// ── 导出《地籍调查表》Word（后台任务 + 进度轮询 + zip 下载） ────────────────

const EXPORT_POLL_INTERVAL = 800;
const EXPORT_TIMEOUT = 30 * 60 * 1000;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "导出文件";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function resolveAttachmentName(headers, fallback) {
  const disposition = headers?.["content-disposition"] || headers?.["Content-Disposition"] || "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      // 编码异常时退回兜底文件名
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain ? plain[1] : fallback;
}

async function readBlobError(error) {
  const payload = error?.response?.data;
  if (!payload) return "";
  if (typeof payload === "string") return payload;
  if (payload instanceof Blob) {
    try {
      const parsed = JSON.parse(await payload.text());
      return parsed.detail || parsed.message || "";
    } catch {
      return "";
    }
  }
  return payload.detail || payload.message || "";
}

async function pollCadastralExport(taskId, onTick) {
  const deadline = Date.now() + EXPORT_TIMEOUT;
  for (;;) {
    const { data } = await fetchCadastralExportProgress(taskId);
    const progress = data?.data || {};
    onTick?.(progress);
    if (progress.status === "completed" || progress.status === "failed") {
      return progress;
    }
    if (Date.now() > deadline) {
      return { ...progress, status: "failed", error: "导出超时，请缩小区域后重试" };
    }
    await delay(EXPORT_POLL_INTERVAL);
  }
}

async function exportSurveyFormsForRegion(node) {
  const regionCode = node?.value || "";
  if (!regionCode) {
    ElMessage.warning("请先在区域树中选择一个区域");
    return;
  }
  const regionLabel = node?.label || node?.name || regionCode;

  let taskId = "";
  const preparing = ElLoading.service({ lock: true, text: `正在统计「${regionLabel}」的承包方…` });
  try {
    const { data } = await startCadastralExport({
      regionCode,
      regionLabel,
      name: filters.name.trim() || undefined,
      memberName: filters.memberName.trim() || undefined,
      idNo: filters.idNo.trim() || undefined,
      address: filters.address.trim() || undefined,
    });
    taskId = data?.data?.taskId || "";
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "创建导出任务失败");
    return;
  } finally {
    preparing.close();
  }
  if (!taskId) {
    ElMessage.warning("未能创建导出任务");
    return;
  }

  const loading = ElLoading.service({ lock: true, text: `正在生成「${regionLabel}」的地籍调查表…` });
  try {
    const progress = await pollCadastralExport(taskId, (item) => {
      const percent = item.percent ? `${item.percent}%` : "";
      loading.setText(`正在生成地籍调查表 ${percent}　${item.message || ""}`.trim());
    });
    if (progress.status !== "completed") {
      ElMessage.error(progress.error || "导出失败");
      return;
    }
    const response = await fetchCadastralExportArchive(taskId);
    const filename = resolveAttachmentName(
      response.headers,
      progress.filename || `${regionLabel}地籍调查表.zip`
    );
    saveBlob(response.data, filename);
    ElMessage.success(`已生成 ${progress.done || 0} 户地籍调查表，请查看下载的文件`);
  } catch (error) {
    ElMessage.error((await readBlobError(error)) || "导出地籍调查表失败");
  } finally {
    loading.close();
  }
}

async function downloadCadastralSurveyDocx(row) {
  const loading = ElLoading.service({ lock: true, text: `正在生成「${row.name}」的地籍调查表…` });
  try {
    const response = await fetchCadastralSurveyDocx(row.code);
    const filename = resolveAttachmentName(
      response.headers,
      `${row.code}${row.name || ""}地籍调查表.docx`
    );
    saveBlob(response.data, filename);
    ElMessage.success("地籍调查表已下载");
  } catch (error) {
    ElMessage.error((await readBlobError(error)) || "下载地籍调查表失败");
  } finally {
    loading.close();
  }
}

// 单页（批）户数。一个村可有上千户，整村一次渲染既慢又撑爆浏览器，
// 因此分页取数、拼到同一个打印窗口里。
const CADASTRAL_PAGE_SIZE = 50;
// 单次打印的户数上限，超过则要求先选更小的区域。
const CADASTRAL_MAX_CONTRACTORS = 300;

function extractBodyHtml(html) {
  return String(html || "")
    .replace(/^[\s\S]*?<body[^>]*>/i, "")
    .replace(/<\/body>[\s\S]*$/i, "")
    // 每份文档都带一个悬浮"打印"按钮，打印时隐藏，但拼接后会重叠，直接去掉。
    .replace(/<button class="print-btn"[\s\S]*?<\/button>/gi, "");
}

async function printSurveyFormsForRegion(node) {
  const regionCode = node?.value || "";
  if (!regionCode) {
    ElMessage.warning("请先在区域树中选择一个区域");
    return;
  }
  const regionLabel = node?.label || node?.name || regionCode;
  // 先同步开窗：此时仍在点击手势里，不会被弹窗拦截；渲染要等多次请求。
  const w = window.open("", "_blank", "width=1200,height=900");
  if (!w) {
    ElMessage.warning("浏览器拦截了打印窗口，请允许本站弹出窗口后重试");
    return;
  }
  w.document.write(
    '<!DOCTYPE html><html><head><meta charset="utf-8"><title>地籍调查表</title></head>'
    + '<body style="font-family:sans-serif;padding:24px">正在生成地籍调查表，请稍候…</body></html>'
  );
  w.document.close();

  const loading = ElLoading.service({
    lock: true,
    text: `正在生成「${regionLabel}」的地籍调查表，请稍候…`,
  });
  try {
    const first = await printCadastralSurveys({ regionCode, page: 1, pageSize: CADASTRAL_PAGE_SIZE });
    const firstData = first.data?.data || {};
    const total = firstData.total || 0;
    if (!total) {
      w.close();
      ElMessage.warning(`「${regionLabel}」下没有可打印的承包方`);
      return;
    }
    if (total > CADASTRAL_MAX_CONTRACTORS) {
      w.close();
      ElMessage.warning(
        `「${regionLabel}」共 ${total} 户，超过单次打印上限 ${CADASTRAL_MAX_CONTRACTORS} 户，请选择更小的区域后再打印`
      );
      return;
    }
    const pageCount = Math.ceil(total / CADASTRAL_PAGE_SIZE);
    if (pageCount > 1) {
      try {
        await ElMessageBox.confirm(
          `「${regionLabel}」共 ${total} 户，将分 ${pageCount} 批生成（每批 ${CADASTRAL_PAGE_SIZE} 户），期间请勿关闭窗口。是否继续？`,
          "批量打印地籍调查表",
          { type: "warning", confirmButtonText: "开始生成", cancelButtonText: "取消" }
        );
      } catch {
        w.close();
        return;
      }
    }

    let headHtml = "";
    const bodyParts = [];
    let done = 0;
    for (let current = 1; current <= pageCount; current += 1) {
      const response = current === 1
        ? first
        : await printCadastralSurveys({ regionCode, page: current, pageSize: CADASTRAL_PAGE_SIZE });
      const payload = response.data?.data || {};
      const html = payload.renderedHtml || "";
      if (!html) continue;
      if (!headHtml) {
        // 只取第一份文档的 head，样式全部在这份里。
        headHtml = html.replace(/<\/head>[\s\S]*$/i, "").replace(/^[\s\S]*?<head[^>]*>/i, "");
      }
      bodyParts.push(extractBodyHtml(html));
      done += payload.contractorCount || 0;
    }

    if (!bodyParts.length) {
      w.close();
      ElMessage.warning("未生成任何可打印内容");
      return;
    }
    w.document.open();
    w.document.write(
      `<!DOCTYPE html><html><head><meta charset="utf-8">${headHtml}</head>`
      + `<body>${bodyParts.join("")}</body></html>`
    );
    w.document.close();
    ElMessage.success(`已生成 ${done} 户的地籍调查表（共 ${pageCount} 批）`);
    // 等浏览器完成排版再唤起打印对话框（页数多时耗时更久）。
    setTimeout(() => w.print(), 1200);
  } catch (error) {
    w.close();
    ElMessage.error(error?.response?.data?.detail || "批量打印调查表失败");
  } finally {
    loading.close();
  }
}

function handlePageChange(value) {
  page.value = value;
  loadData();
}

function handlePageSizeChange(value) {
  pageSize.value = value;
  page.value = 1;
  loadData();
}

function openCreateDialog() {
  editingCode.value = "";
  contractorDialogRef.value?.openForCreate();
}

async function openEditDialog(row) {
  editingCode.value = row.code;
  await contractorDialogRef.value?.openForEdit(row.code);
}

function handleDialogSaved() {
  editingCode.value = "";
  loadData();
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除承包方"${row.name}"吗？该操作不可恢复。`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteContractor(row.code);
    ElMessage.success("承包方已删除");
    if (rows.value.length === 1 && page.value > 1) {
      page.value -= 1;
    }
    await loadData();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "删除失败");
    }
  }
}

loadRegionTree();
loadData();
</script>
