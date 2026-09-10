<template>
  <el-dialog
    :model-value="modelValue"
    :title="editingId ? '编辑业务申请' : '新增业务申请'"
    width="1080px"
    destroy-on-close
    class="request-form-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" class="compact-form" label-position="top" status-icon>
      <div class="form-grid">
        <el-form-item label="业务类型" prop="requestType">
          <el-select v-model="form.requestType" placeholder="请选择业务类型">
            <el-option v-for="item in requestTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="申请标题" prop="requestTitle">
          <el-input v-model="form.requestTitle" placeholder="可不填，保存时自动生成" />
        </el-form-item>
        <el-form-item label="发包方代码" prop="issuerCode">
          <el-input v-model="form.issuerCode" placeholder="请输入标准表 FBF 的发包方代码" />
        </el-form-item>
        <el-form-item label="发包方名称" prop="issuerName">
          <el-input v-model="form.issuerName" placeholder="可不填，保存时根据代码自动带出" />
        </el-form-item>
        <el-form-item label="承包方代码" prop="contractorCode">
          <el-input v-model="form.contractorCode" placeholder="请输入标准表 CBF 的承包方代码" />
        </el-form-item>
        <el-form-item label="承包方名称" prop="contractorName">
          <el-input v-model="form.contractorName" placeholder="可不填，保存时根据代码自动带出" />
        </el-form-item>
        <el-form-item label="证件类型" prop="contractorIdType">
          <el-select v-model="form.contractorIdType" clearable placeholder="可不填，保存时自动带出">
            <el-option label="居民身份证" value="1" />
            <el-option label="军官证" value="2" />
            <el-option label="护照" value="3" />
            <el-option label="户口簿" value="4" />
            <el-option label="其他" value="9" />
          </el-select>
        </el-form-item>
        <el-form-item label="证件号码" prop="contractorIdNo">
          <el-input v-model="form.contractorIdNo" placeholder="可不填，保存时自动带出" />
        </el-form-item>
        <el-form-item label="合同代码" prop="contractCode">
          <el-input v-model="form.contractCode" placeholder="可选，输入标准表 CBHT 的合同代码" />
        </el-form-item>
        <el-form-item label="工作流编码" prop="workflowCode">
          <el-select
            v-model="form.workflowCode"
            filterable
            :disabled="lockWorkflowBinding"
            placeholder="按业务类型自动匹配，也可手动改选"
          >
            <el-option v-for="item in workflowOptions" :key="item.key" :label="item.name" :value="item.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="流程版本" prop="workflowVersionId">
          <el-select
            v-model="form.workflowVersionId"
            clearable
            :disabled="lockWorkflowBinding || !form.workflowCode"
            placeholder="不选则跟随当前生效版本"
          >
            <el-option label="跟随当前生效版本" :value="null" />
            <el-option
              v-for="item in workflowVersionOptions"
              :key="item.id"
              :label="`V${item.versionNo} · ${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="联系电话" prop="mobile">
          <el-input v-model="form.mobile" placeholder="可不填，保存时根据承包方自动带出" />
        </el-form-item>
        <el-form-item class="form-span-2">
          <el-alert
            v-if="lockWorkflowBinding"
            title="该申请已经提交过流程，当前只允许修改业务数据，不能再切换流程定义或版本。"
            type="warning"
            :closable="false"
            show-icon
          />
        </el-form-item>
        <el-form-item class="form-span-2" label="联系地址" prop="address">
          <el-input v-model="form.address" placeholder="可不填，保存时根据承包方自动带出" />
        </el-form-item>
        <el-form-item class="form-span-2" label="申请原因" prop="reason">
          <el-input v-model="form.reason" type="textarea" :rows="3" placeholder="请输入申请原因" />
        </el-form-item>
        <el-form-item class="form-span-2" label="备注" prop="note">
          <el-input v-model="form.note" type="textarea" :rows="3" placeholder="请输入备注说明" />
        </el-form-item>
      </div>
    </el-form>

    <div class="request-form-attachments">
      <input
        ref="dialogAttachmentInputRef"
        type="file"
        class="request-attachment-input"
        @change="handleDialogAttachmentInputChange"
      />
      <div class="workflow-handler-head">
        <div>
          <div class="workflow-handler-title">附件材料</div>
          <div class="role-hint">保存表单后，可直接在当前弹窗补充申请材料和审核附件。</div>
        </div>
        <div v-if="editingRequestRecord" class="attachment-toolbar">
          <el-select
            v-model="dialogAttachmentCategory"
            clearable
            filterable
            allow-create
            default-first-option
            placeholder="请选择或输入附件分类"
            style="width: 240px"
          >
            <el-option
              v-for="item in dialogAttachmentTypeOptions"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
          <el-button :loading="uploadingAttachment" plain type="success" @click="openDialogAttachmentPicker">
            上传附件
          </el-button>
        </div>
      </div>

      <template v-if="editingRequestRecord">
        <div class="request-form-attachment-stats">
          <div class="attachment-stat-card">
            <div class="attachment-stat-label">当前附件</div>
            <div class="attachment-stat-value">{{ editingRequestRecord.attachments.length }}</div>
          </div>
          <div class="attachment-stat-card">
            <div class="attachment-stat-label">建议分类</div>
            <div class="attachment-stat-value">{{ dialogAttachmentTypeOptions.length || 0 }}</div>
          </div>
          <div class="attachment-stat-card">
            <div class="attachment-stat-label">待补分类</div>
            <div class="attachment-stat-value">{{ dialogAttachmentMissingCategories.length }}</div>
          </div>
        </div>

        <div v-if="dialogAttachmentMissingCategories.length" class="request-form-missing-tags">
          <el-tag
            v-for="item in dialogAttachmentMissingCategories"
            :key="item"
            size="small"
            type="danger"
            effect="plain"
          >
            {{ item }}
          </el-tag>
        </div>

        <div v-if="editingRequestRecord.attachments.length" class="request-form-attachment-list">
          <div
            v-for="item in editingRequestRecord.attachments"
            :key="item.id"
            class="attachment-card is-compact"
          >
            <div class="attachment-card-main">
              <div class="attachment-card-name">{{ item.originalName }}</div>
              <div class="attachment-card-meta">
                {{ formatFileSize(item.fileSize) }}
                <span class="request-detail-dot">•</span>
                {{ item.category || "-" }}
                <span class="request-detail-dot">•</span>
                {{ item.stageCode || "-" }}
                <span class="request-detail-dot">•</span>
                {{ formatDateTime(item.createdAt) }}
              </div>
            </div>
            <div class="attachment-card-actions">
              <el-button v-if="isPreviewableAttachment(item)" link type="success" @click="handleDialogAttachmentPreview(item)">
                预览
              </el-button>
              <el-button link type="primary" @click="handleDialogAttachmentDownload(item)">下载</el-button>
              <el-button link type="danger" @click="handleDialogAttachmentDelete(item)">删除</el-button>
            </div>
          </div>
        </div>
        <el-empty v-else description="当前申请还没有上传附件" />
      </template>
      <el-alert
        v-else
        title="请先保存表单，再继续上传附件。首次保存后会自动保留在当前窗口，方便继续补材料。"
        type="info"
        :closable="false"
        show-icon
      />
    </div>

    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
      <el-button :loading="submitting" type="success" @click="handleSubmitForm">保存表单</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createRequest,
  deleteRequestAttachment,
  fetchRequestDetail,
  uploadRequestAttachment,
  updateRequest,
} from "../../api/request";
import { fetchWorkflowDefinition } from "../../api/workflow";
import { validateChinaId, validateMobile } from "../../utils/validators";
import { isPreviewableAttachment, formatFileSize, formatDateTime } from "../../utils/attachmentHelpers";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  editingId: { type: Number, default: 0 },
  requestWorkflowMappings: { type: Array, default: () => [] },
  workflowOptions: { type: Array, default: () => [] },
});

const emit = defineEmits([
  "update:modelValue",
  "saved",
  "refresh-detail",
  "preview-attachment",
]);

const submitting = ref(false);
const uploadingAttachment = ref(false);
const editingRequestRecord = ref(null);
const workflowVersionOptions = ref([]);
const lockWorkflowBinding = ref(false);
const formRef = ref();
const dialogAttachmentInputRef = ref(null);
const dialogAttachmentCategory = ref("");

const requestTypeOptions = [
  { label: "首次登记", value: "首次登记" },
  { label: "变更登记", value: "变更登记" },
  { label: "注销登记", value: "注销登记" },
  { label: "证书补发", value: "证书补发" },
];

const createEmptyForm = () => ({
  requestType: "首次登记",
  requestTitle: "",
  issuerCode: "",
  issuerName: "",
  contractorCode: "",
  contractorName: "",
  contractorIdType: "",
  contractorIdNo: "",
  contractCode: "",
  mobile: "",
  address: "",
  reason: "",
  note: "",
  workflowCode: "",
  workflowVersionId: null,
});

const form = reactive(createEmptyForm());

const validateRequestMobile = (_rule, value, callback) => {
  if (!value) { callback(); return; }
  if (!validateMobile(value)) { callback(new Error("请输入正确的手机号")); return; }
  callback();
};

const validateContractorIdNo = (_rule, value, callback) => {
  if (!value) { callback(); return; }
  if ((!form.contractorIdType || form.contractorIdType === "1") && !validateChinaId(value)) {
    callback(new Error("请输入正确的身份证号"));
    return;
  }
  callback();
};

const rules = {
  requestType: [{ required: true, message: "请选择业务类型", trigger: "change" }],
  issuerCode: [{ required: true, message: "请输入发包方代码", trigger: "blur" }],
  contractorIdNo: [{ validator: validateContractorIdNo, trigger: "blur" }],
  mobile: [{ validator: validateRequestMobile, trigger: "blur" }],
  workflowCode: [{ required: true, message: "请选择流程定义", trigger: "change" }],
};

const dialogAttachmentTypeOptions = computed(() => {
  const categories = new Set(editingRequestRecord.value?.taskConfig?.attachmentTypes || []);
  for (const item of editingRequestRecord.value?.attachmentTemplates || []) {
    categories.add(item.name || item.category);
  }
  return Array.from(categories);
});

const dialogAttachmentMissingCategories = computed(() =>
  dialogAttachmentTypeOptions.value.filter(
    (category) => !(editingRequestRecord.value?.attachments || []).some((item) => item.category === category),
  ),
);

function resetForm() {
  Object.assign(form, createEmptyForm());
  workflowVersionOptions.value = [];
  lockWorkflowBinding.value = false;
  editingRequestRecord.value = null;
  dialogAttachmentCategory.value = "";
  formRef.value?.clearValidate();
}

function handleClose() {
  emit("update:modelValue", false);
  resetForm();
}

function findWorkflowMapping(requestType) {
  return props.requestWorkflowMappings.find((item) => item.requestType === requestType) || null;
}

function applyWorkflowMapping(requestType, { force = false } = {}) {
  const mapping = findWorkflowMapping(requestType);
  if (!mapping) {
    if (force) { form.workflowCode = ""; form.workflowVersionId = null; }
    return;
  }
  if (force || !form.workflowCode) {
    form.workflowCode = mapping.workflowKey;
    form.workflowVersionId = mapping.workflowVersionId ?? null;
  }
}

async function loadWorkflowVersions(workflowKey, preferredVersionId = null) {
  if (!workflowKey) {
    workflowVersionOptions.value = [];
    form.workflowVersionId = null;
    return;
  }
  try {
    const { data } = await fetchWorkflowDefinition(workflowKey);
    workflowVersionOptions.value = data.data.versions || [];
    if (preferredVersionId && workflowVersionOptions.value.some((item) => item.id === preferredVersionId)) {
      form.workflowVersionId = preferredVersionId;
      return;
    }
    if (form.workflowVersionId && !workflowVersionOptions.value.some((item) => item.id === form.workflowVersionId)) {
      form.workflowVersionId = null;
    }
  } catch (error) {
    workflowVersionOptions.value = [];
    form.workflowVersionId = null;
    ElMessage.error(error.response?.data?.detail || "加载流程版本列表失败");
  }
}

function buildPayload() {
  return {
    requestType: form.requestType,
    requestTitle: form.requestTitle.trim() || null,
    issuerCode: form.issuerCode.trim(),
    issuerName: form.issuerName.trim() || null,
    contractorCode: form.contractorCode.trim() || null,
    contractorName: form.contractorName.trim() || null,
    contractorIdType: form.contractorIdType || null,
    contractorIdNo: form.contractorIdNo.trim() || null,
    contractCode: form.contractCode.trim() || null,
    mobile: form.mobile.trim() || null,
    address: form.address.trim() || null,
    reason: form.reason.trim() || null,
    note: form.note.trim() || null,
    workflowCode: form.workflowCode.trim() || null,
    workflowVersionId: form.workflowVersionId || null,
  };
}

async function handleSubmitForm() {
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    ElMessage.warning("请先修正表单中的校验问题");
    return;
  }
  submitting.value = true;
  try {
    const payload = buildPayload();
    if (props.editingId) {
      await updateRequest(props.editingId, payload);
      const { data } = await fetchRequestDetail(props.editingId);
      editingRequestRecord.value = data.data;
      ElMessage.success("业务申请已更新");
      emit("refresh-detail", props.editingId);
    } else {
      const response = await createRequest(payload);
      editingRequestRecord.value = response.data.data;
      lockWorkflowBinding.value = Boolean(response.data.data.submittedAt);
      ElMessage.success("业务申请已创建，请继续上传附件");
      emit("saved", response.data.data);
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存失败");
  } finally {
    submitting.value = false;
  }
}

/* ---- Attachment management within the dialog ---- */

function openDialogAttachmentPicker() {
  if (!editingRequestRecord.value) {
    ElMessage.info("请先保存表单，再上传附件");
    return;
  }
  if (dialogAttachmentTypeOptions.value.length && !dialogAttachmentCategory.value?.trim()) {
    ElMessage.warning("请先选择附件分类");
    return;
  }
  dialogAttachmentInputRef.value?.click();
}

async function handleDialogAttachmentInputChange(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file || !editingRequestRecord.value) return;
  const formData = new FormData();
  formData.append("file", file);
  if (dialogAttachmentCategory.value?.trim()) {
    formData.append("category", dialogAttachmentCategory.value.trim());
  }
  uploadingAttachment.value = true;
  try {
    await uploadRequestAttachment(editingRequestRecord.value.id, formData);
    dialogAttachmentCategory.value = "";
    const { data } = await fetchRequestDetail(editingRequestRecord.value.id);
    editingRequestRecord.value = data.data;
    ElMessage.success("附件上传成功");
    emit("refresh-detail", editingRequestRecord.value.id);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "附件上传失败");
  } finally {
    uploadingAttachment.value = false;
  }
}

async function handleDialogAttachmentDelete(item) {
  if (!editingRequestRecord.value) return;
  try {
    await ElMessageBox.confirm(`确定删除附件"${item.originalName}"吗？`, "删除附件", {
      type: "warning", confirmButtonText: "删除", cancelButtonText: "取消",
    });
    await deleteRequestAttachment(editingRequestRecord.value.id, item.id);
    const { data } = await fetchRequestDetail(editingRequestRecord.value.id);
    editingRequestRecord.value = data.data;
    ElMessage.success("附件已删除");
    emit("refresh-detail", editingRequestRecord.value.id);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "附件删除失败");
    }
  }
}

async function handleDialogAttachmentPreview(item) {
  if (!editingRequestRecord.value) return;
  emit("preview-attachment", { item, caseId: editingRequestRecord.value.id });
}

async function handleDialogAttachmentDownload(item) {
  if (!editingRequestRecord.value) return;
  try {
    const response = await (await import("../../api/request")).downloadRequestAttachment(editingRequestRecord.value.id, item.id);
    const blob = new Blob([response.data], {
      type: item.contentType || response.headers["content-type"] || "application/octet-stream",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = item.originalName || `attachment-${item.id}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "附件下载失败");
  }
}

/* ---- Public methods exposed via defineExpose ---- */

async function openForCreate(workflowMappings) {
  resetForm();
  applyWorkflowMapping(form.requestType, { force: true });
  loadWorkflowVersions(form.workflowCode, form.workflowVersionId);
  emit("update:modelValue", true);
}

async function openForEdit(row) {
  try {
    const { data } = await fetchRequestDetail(row.id);
    editingRequestRecord.value = data.data;
    Object.assign(form, {
      requestType: data.data.requestType,
      requestTitle: data.data.requestTitle || "",
      issuerCode: data.data.issuerCode || "",
      issuerName: data.data.issuerName || "",
      contractorCode: data.data.contractorCode || "",
      contractorName: data.data.contractorName || "",
      contractorIdType: data.data.contractorIdType || "",
      contractorIdNo: data.data.contractorIdNo || "",
      contractCode: data.data.contractCode || "",
      mobile: data.data.mobile || "",
      address: data.data.address || "",
      reason: data.data.reason || "",
      note: data.data.note || "",
      workflowCode: data.data.workflowCode || "",
      workflowVersionId: data.data.workflowVersionId || null,
    });
    lockWorkflowBinding.value = Boolean(data.data.submittedAt);
    if (dialogAttachmentCategory.value && !((data.data.taskConfig?.attachmentTypes || []).includes(dialogAttachmentCategory.value))) {
      dialogAttachmentCategory.value = "";
    }
    applyWorkflowMapping(form.requestType, { force: !form.workflowCode });
    await loadWorkflowVersions(form.workflowCode, data.data.workflowVersionId || null);
    formRef.value?.clearValidate();
    emit("update:modelValue", true);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "加载业务申请详情失败");
  }
}

watch(() => props.modelValue, (value) => {
  if (!value) resetForm();
});

watch(() => form.requestType, (value) => {
  if (lockWorkflowBinding.value) return;
  applyWorkflowMapping(value);
});

watch(() => form.workflowCode, async (value, oldValue) => {
  if (!value || value === oldValue) return;
  if (!lockWorkflowBinding.value) {
    const mapping = findWorkflowMapping(form.requestType);
    form.workflowVersionId = mapping?.workflowKey === value ? (mapping.workflowVersionId ?? null) : null;
  }
  await loadWorkflowVersions(value, form.workflowVersionId);
});

defineExpose({ openForCreate, openForEdit });
</script>
