<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div class="panel-title">业务申请</div>
      <div class="toolbar-actions toolbar-wrap">
        <el-input
          v-model="keyword"
          clearable
          placeholder="搜索流水号、标题、承包方、身份证号"
          style="width: 280px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-select
          v-model="statusFilter"
          clearable
          placeholder="状态筛选"
          style="width: 150px"
          @change="handleSearch"
        >
          <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-button plain @click="handleSearch">查询</el-button>
        <el-button plain @click="resetFilters">重置</el-button>
        <el-button v-if="canManageRequests" type="success" @click="openCreateDialog">新增申请</el-button>
      </div>
    </div>

    <div class="table-shell">
      <div class="table-scroll">
        <el-table v-loading="loading" :data="rows" border>
          <el-table-column prop="serialNo" label="受理流水号" min-width="220" />
          <el-table-column prop="requestTitle" label="申请标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="requestType" label="业务类型" min-width="120" />
          <el-table-column prop="issuerName" label="发包方" min-width="180" show-overflow-tooltip />
          <el-table-column prop="contractorName" label="承包方" min-width="160" show-overflow-tooltip />
          <el-table-column prop="currentStep" label="当前环节" min-width="120" />
          <el-table-column label="状态" min-width="110">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" effect="light">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="submittedAt" label="提交时间" min-width="170">
            <template #default="{ row }">{{ formatDateTime(row.submittedAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" min-width="380">
            <template #default="{ row }">
              <div class="table-actions">
                <el-button link type="info" @click="openDetail(row)">详情</el-button>
                <el-button v-if="hasAction(row, 'edit')" link type="primary" @click="openEditDialog(row)">编辑</el-button>
                <el-button v-if="hasAction(row, 'submit')" link type="success" @click="handleSubmit(row)">提交</el-button>
                <el-button v-if="hasAction(row, 'approve')" link type="success" @click="handleApprove(row)">通过</el-button>
                <el-button v-if="hasAction(row, 'reject')" link type="warning" @click="handleReject(row)">退回</el-button>
                <el-button v-if="hasAction(row, 'delete')" link type="danger" @click="handleDelete(row)">删除</el-button>
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
  </section>

  <RequestEditDialog
    ref="editDialogRef"
    v-model="dialogVisible"
    :editing-id="editingId"
    :request-workflow-mappings="requestWorkflowMappings"
    :workflow-options="workflowOptions"
    @saved="handleDialogSaved"
    @refresh-detail="refreshDetailIfOpen"
    @preview-attachment="handleDialogPreviewAttachment"
  />

  <RequestDetailDrawer
    ref="detailDrawerRef"
    v-model="detailVisible"
    :can-upload="canUploadAttachmentsForDetail"
  />

  <AttachmentPreviewDialog
    v-model="attachmentPreviewVisible"
    :source="attachmentPreviewSource"
    @download="handleAttachmentDownload"
  />
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { approveRequest, deleteRequest, downloadRequestAttachment, fetchRequestDetail, fetchRequests, fetchRequestWorkflowOptions, rejectRequest, submitRequest } from "../api/request";
import { useAuthStore } from "../stores/auth";
import RequestEditDialog from "../components/requests/RequestEditDialog.vue";
import RequestDetailDrawer from "../components/requests/RequestDetailDrawer.vue";
import AttachmentPreviewDialog from "../components/requests/AttachmentPreviewDialog.vue";
import { statusTagType, formatDateTime } from "../utils/attachmentHelpers";

const authStore = useAuthStore();
const canManageRequests = computed(() => authStore.hasPermission("requests.manage"));
const canUploadAttachmentsForDetail = computed(() => {
  if (!detailRecord.value) return false;
  return ["edit", "approve", "reject"].some((action) => hasAction(detailRecord.value, action));
});

const editDialogRef = ref(null);
const detailDrawerRef = ref(null);
const loading = ref(false);
const dialogVisible = ref(false);
const detailVisible = ref(false);
const editingId = ref(0);
const rows = ref([]);
const detailRecord = ref(null);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const statusFilter = ref("");
const requestWorkflowMappings = ref([]);
const workflowOptions = ref([]);
const attachmentPreviewVisible = ref(false);
const attachmentPreviewSource = ref(null);

const statusOptions = [
  { label: "待提交", value: "待提交" },
  { label: "审核中", value: "审核中" },
  { label: "已办结", value: "已办结" },
  { label: "已退回", value: "已退回" },
];

function hasAction(row, action) {
  return Array.isArray(row.availableActions) && row.availableActions.includes(action);
}

async function loadData() {
  loading.value = true;
  try {
    const { data } = await fetchRequests({ page: page.value, page_size: pageSize.value, keyword: keyword.value || undefined, status: statusFilter.value || undefined });
    rows.value = data.data.items;
    total.value = data.data.total;
  } finally { loading.value = false; }
}

async function loadWorkflowOptions() {
  try {
    const { data } = await fetchRequestWorkflowOptions();
    requestWorkflowMappings.value = data.data.mappings || [];
    workflowOptions.value = data.data.workflows || [];
  } catch (error) { ElMessage.error(error.response?.data?.detail || "加载业务流程映射失败"); }
}

async function refreshDetailIfOpen(id) {
  if (detailVisible.value && detailRecord.value?.id === id && detailDrawerRef.value) {
    detailRecord.value = await detailDrawerRef.value.loadDetail(id);
  }
}

function handleSearch() { page.value = 1; loadData(); }
function resetFilters() { keyword.value = ""; statusFilter.value = ""; page.value = 1; loadData(); }
function handlePageChange(value) { page.value = value; loadData(); }
function handlePageSizeChange(value) { pageSize.value = value; page.value = 1; loadData(); }

function openCreateDialog() { editingId.value = 0; editDialogRef.value?.openForCreate(); }
async function openEditDialog(row) { editingId.value = row.id; await editDialogRef.value?.openForEdit(row); }
function handleDialogSaved(record) { editingId.value = record.id; loadData(); }
async function openDetail(row) { detailVisible.value = true; detailRecord.value = await detailDrawerRef.value?.loadDetail(row.id); }

function handleDialogPreviewAttachment({ item, caseId }) {
  attachmentPreviewSource.value = { ...item, __caseId: caseId };
  attachmentPreviewVisible.value = true;
}

async function handleAttachmentDownload(item) {
  const caseId = item?.__caseId || detailRecord.value?.id;
  if (!caseId) return;
  try {
    const response = await downloadRequestAttachment(caseId, item.id);
    const blob = new Blob([response.data], { type: item.contentType || response.headers["content-type"] || "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = item.originalName || "attachment-" + item.id;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) { ElMessage.error(error.response?.data?.detail || "附件下载失败"); }
}

async function handleSubmit(row) {
  try {
    await ElMessageBox.confirm(
      `确定提交业务申请“${row.requestTitle || row.serialNo}”吗？提交后将进入下一审核节点。`,
      "提交确认",
      {
        type: "warning",
        confirmButtonText: "提交",
        cancelButtonText: "取消",
      },
    );
    await submitRequest(row.id);
    ElMessage.success("业务申请已提交");
    await Promise.all([loadData(), refreshDetailIfOpen(row.id)]);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "提交失败");
    }
  }
}

async function handleApprove(row) {
  try {
    const detail = row.taskConfig ? row : await loadDetail(row.id);
    const requireComment = Boolean(detail?.taskConfig?.requireComment);
    const { value } = await ElMessageBox.prompt(
      `请输入“${row.currentStep}”的审核意见。${requireComment ? "当前节点要求必须填写意见。" : "意见可留空。"} `,
      "审核通过",
      {
        confirmButtonText: "通过",
        cancelButtonText: "取消",
        inputPlaceholder: requireComment ? "请填写审核意见" : "可选填写审核意见",
        inputValidator: (inputValue) => {
          if (requireComment && !inputValue?.trim()) {
            return "当前节点要求必须填写审核意见";
          }
          return true;
        },
      },
    );
    await approveRequest(row.id, { comment: value?.trim() || null });
    ElMessage.success("审核已通过");
    await Promise.all([loadData(), refreshDetailIfOpen(row.id)]);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "审核通过失败");
    }
  }
}

async function handleReject(row) {
  try {
    const { value } = await ElMessageBox.prompt(`请输入“${row.currentStep}”的退回原因。`, "退回申请", {
      confirmButtonText: "退回",
      cancelButtonText: "取消",
      inputPlaceholder: "请输入退回原因",
      inputValidator: (inputValue) => {
        if (!inputValue?.trim()) {
          return "退回原因不能为空";
        }
        return true;
      },
    });
    await rejectRequest(row.id, { comment: value.trim() });
    ElMessage.success("业务申请已退回");
    await Promise.all([loadData(), refreshDetailIfOpen(row.id)]);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "退回失败");
    }
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除业务申请“${row.requestTitle || row.serialNo}”吗？该操作不可恢复。`,
      "删除确认",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
      },
    );
    await deleteRequest(row.id);
    ElMessage.success("业务申请已删除");
    if (detailVisible.value && detailRecord.value?.id === row.id) {
      detailVisible.value = false;
      detailRecord.value = null;
    }
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


onMounted(async () => {
  if (canManageRequests.value) { await Promise.all([loadWorkflowOptions(), loadData()]); return; }
  await loadData();
});

watch(dialogVisible, (value) => { if (!value) editingId.value = 0; });
watch(detailVisible, (value) => { if (value) return; detailRecord.value = null; });

</script>