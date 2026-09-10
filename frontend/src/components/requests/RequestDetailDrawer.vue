<template>
  <el-drawer
    :model-value="modelValue"
    title="业务申请详情"
    size="100%"
    destroy-on-close
    class="request-detail-drawer"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="detailLoading" class="request-detail">
      <template v-if="detailRecord">
        <div class="request-detail-head">
          <div>
            <div class="request-detail-title">{{ detailRecord.requestTitle || detailRecord.serialNo }}</div>
            <div class="request-detail-subtitle">{{ detailRecord.serialNo }}</div>
          </div>
          <div class="request-detail-side">
            <div class="request-detail-actions">
              <el-tag :type="statusTagType(detailRecord.status)" effect="light">{{ detailRecord.status }}</el-tag>
              <el-button plain @click="handleExportDetailHtml">导出 HTML</el-button>
              <el-button plain type="success" @click="handlePrintDetail">打印留痕</el-button>
            </div>
          </div>
        </div>

        <el-tabs v-model="detailTab" class="compact-dialog-tabs">
          <el-tab-pane label="流程概览" name="overview">
            <div class="workflow-overview">
              <div class="workflow-current-card">
                <div class="workflow-current-label">当前任务</div>
                <div class="workflow-current-name">{{ detailRecord.currentTaskName || detailRecord.currentStep }}</div>
                <div class="workflow-current-meta">{{ detailRecord.currentTaskCode || "-" }}</div>
                <div class="workflow-current-meta">
                  办理权限：{{ detailRecord.requiredPermission || "当前环节无需审核权限" }}
                </div>
                <div class="workflow-current-actions">
                  <el-button
                    v-if="detailRecord.currentTaskCode"
                    plain
                    size="small"
                    type="success"
                    @click="focusWorkflowStep(detailRecord.currentTaskCode)"
                  >
                    定位到流程图
                  </el-button>
                </div>
              </div>

              <div v-if="detailRecord.taskConfig" class="workflow-config-card">
                <div class="workflow-config-title">当前节点业务配置</div>
                <div class="workflow-config-grid">
                  <div class="workflow-config-item">
                    <span class="workflow-config-label">权限编码</span>
                    <span class="workflow-config-value">{{ detailRecord.taskConfig.permissionCode || "-" }}</span>
                  </div>
                  <div class="workflow-config-item">
                    <span class="workflow-config-label">节点数据范围</span>
                    <span class="workflow-config-value">{{ formatDataScope(detailRecord.taskConfig.dataScope) }}</span>
                  </div>
                  <div class="workflow-config-item">
                    <span class="workflow-config-label">办理人选择方式</span>
                    <span class="workflow-config-value">{{ formatCandidateMode(detailRecord.taskConfig.candidateUserMode) }}</span>
                  </div>
                  <div class="workflow-config-item">
                    <span class="workflow-config-label">是否必须意见</span>
                    <span class="workflow-config-value">
                      <el-tag size="small" :type="detailRecord.taskConfig.requireComment ? 'warning' : 'info'" effect="light">
                        {{ detailRecord.taskConfig.requireComment ? "必须填写" : "可选填写" }}
                      </el-tag>
                    </span>
                  </div>
                  <div class="workflow-config-item workflow-config-item--full">
                    <span class="workflow-config-label">候选角色</span>
                    <div v-if="detailRecord.taskConfig.candidateRoleCodes.length" class="workflow-config-tags">
                      <el-tag
                        v-for="item in detailRecord.taskConfig.candidateRoleCodes"
                        :key="item"
                        size="small"
                        effect="plain"
                      >
                        {{ item }}
                      </el-tag>
                    </div>
                    <span v-else class="workflow-config-value">未单独限定</span>
                  </div>
                  <div v-if="attachmentMissingCategories.length" class="workflow-config-item workflow-config-item--full">
                    <span class="workflow-config-label">待补充分类</span>
                    <div class="workflow-config-tags">
                      <el-tag
                        v-for="item in attachmentMissingCategories"
                        :key="item"
                        size="small"
                        type="danger"
                        effect="plain"
                      >
                        {{ item }}
                      </el-tag>
                    </div>
                  </div>
                </div>
              </div>

              <div class="workflow-step-list">
                <div
                  v-for="item in detailRecord.workflowSteps"
                  :key="item.code"
                  class="workflow-step-card"
                  :class="[{ 'is-active': activeWorkflowStepCode === item.code }, `is-${item.status}`]"
                  role="button"
                  tabindex="0"
                  @click="focusWorkflowStep(item.code)"
                  @keyup.enter="focusWorkflowStep(item.code)"
                >
                  <div class="workflow-step-head">
                    <div class="workflow-step-name">{{ item.name }}</div>
                    <el-tag size="small" :type="workflowTagType(item.status)" effect="light">{{ item.label }}</el-tag>
                  </div>
                  <div class="workflow-step-code">{{ item.code }}</div>
                </div>
              </div>

              <div class="workflow-handler-card">
                <div class="workflow-handler-head">
                  <div class="workflow-handler-title">当前候选办理人</div>
                  <el-tag size="small" effect="plain">{{ detailRecord.candidateHandlers.length }} 人</el-tag>
                </div>
                <div v-if="detailRecord.candidateHandlers.length" class="workflow-handler-list">
                  <div
                    v-for="item in detailRecord.candidateHandlers"
                    :key="item.userId"
                    class="workflow-handler-item"
                  >
                    <div class="workflow-handler-name">{{ item.userName }}</div>
                    <div class="workflow-handler-meta">
                      {{ item.roleName || item.username }}
                      <span class="request-detail-dot">•</span>
                      {{ item.regionName || item.regionCode || "-" }}
                    </div>
                  </div>
                </div>
                <el-empty v-else description="当前环节暂未匹配到可办理人员" />
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="流程图" name="diagram">
            <div class="request-workflow-diagram-card">
              <div class="request-workflow-diagram-head">
                <div>
                  <div class="workflow-handler-title">{{ detailWorkflowView?.workflowName || detailRecord.workflowCode }}</div>
                  <div class="workflow-handler-meta">
                    {{ detailWorkflowView?.workflowVersionLabel || detailRecord.workflowVersionLabel || "跟随当前生效版本" }}
                  </div>
                </div>
                <div class="request-workflow-legend">
                  <span class="request-workflow-legend-item is-current">当前节点</span>
                  <span class="request-workflow-legend-item is-completed">已完成</span>
                  <span class="request-workflow-legend-item is-rejected">退回节点</span>
                </div>
              </div>
              <div ref="workflowCanvasRef" class="request-workflow-viewer"></div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="基础信息" name="basic">
            <el-descriptions :column="2" border class="request-descriptions">
              <el-descriptions-item label="发包方代码">{{ detailRecord.issuerCode || "-" }}</el-descriptions-item>
              <el-descriptions-item label="发包方名称">{{ detailRecord.issuerName || "-" }}</el-descriptions-item>
              <el-descriptions-item label="承包方代码">{{ detailRecord.contractorCode || "-" }}</el-descriptions-item>
              <el-descriptions-item label="承包方名称">{{ detailRecord.contractorName || "-" }}</el-descriptions-item>
              <el-descriptions-item label="证件类型">{{ detailRecord.contractorIdType || "-" }}</el-descriptions-item>
              <el-descriptions-item label="证件号码">{{ detailRecord.contractorIdNo || "-" }}</el-descriptions-item>
              <el-descriptions-item label="合同代码">{{ detailRecord.contractCode || "-" }}</el-descriptions-item>
              <el-descriptions-item label="联系电话">{{ detailRecord.mobile || "-" }}</el-descriptions-item>
              <el-descriptions-item label="工作流编码">{{ detailRecord.workflowCode || "-" }}</el-descriptions-item>
              <el-descriptions-item label="流程版本">{{ detailRecord.workflowVersionLabel || "跟随当前生效版本" }}</el-descriptions-item>
              <el-descriptions-item label="当前任务编码">{{ detailRecord.currentTaskCode || "-" }}</el-descriptions-item>
              <el-descriptions-item :span="2" label="联系地址">{{ detailRecord.address || "-" }}</el-descriptions-item>
              <el-descriptions-item :span="2" label="申请原因">{{ detailRecord.reason || "-" }}</el-descriptions-item>
              <el-descriptions-item :span="2" label="备注">{{ detailRecord.note || "-" }}</el-descriptions-item>
              <el-descriptions-item label="提交时间">{{ formatDateTime(detailRecord.submittedAt) }}</el-descriptions-item>
              <el-descriptions-item label="办结时间">{{ formatDateTime(detailRecord.completedAt) }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>

          <el-tab-pane :label="`办理轨迹（${detailRecord.participants.length}）`" name="timeline">
            <div v-if="detailRecord.participants.length" class="request-timeline">
              <el-timeline>
                <el-timeline-item
                  v-for="item in detailRecord.participants"
                  :key="item.id"
                  :timestamp="formatDateTime(item.createdAt)"
                  placement="top"
                >
                  <div class="timeline-card">
                    <div class="timeline-card-head">
                      <div class="timeline-card-title">{{ item.actionLabel }}</div>
                      <el-tag size="small" effect="plain">{{ item.stepName || "申请环节" }}</el-tag>
                    </div>
                    <div class="timeline-card-meta">
                      {{ item.userName }}
                      <span v-if="item.roleName" class="request-detail-dot">•</span>
                      <span v-if="item.roleName">{{ item.roleName }}</span>
                    </div>
                    <div v-if="item.comment" class="timeline-card-comment">{{ item.comment }}</div>
                  </div>
                </el-timeline-item>
              </el-timeline>
            </div>
            <el-empty v-else description="当前申请还没有办理轨迹" />
          </el-tab-pane>
          <el-tab-pane :label="`附件（${detailRecord.attachments.length}）`" name="attachments">
            <div class="request-attachments request-attachments--workspace">
              <input
                ref="attachmentInputRef"
                type="file"
                class="request-attachment-input"
                @change="handleAttachmentInputChange"
              />
              <div class="attachment-workspace">
                <aside class="attachment-sidebar">
                  <div class="workflow-handler-card attachment-requirement-card">
                    <div class="workflow-handler-head">
                      <div class="workflow-handler-title">节点附件要求</div>
                      <div v-if="canUploadAttachmentsForDetail" class="attachment-toolbar">
                        <el-select
                          v-model="attachmentCategory"
                          clearable
                          filterable
                          allow-create
                          default-first-option
                          placeholder="请选择或输入附件分组"
                          style="width: 220px"
                        >
                          <el-option
                            v-for="item in attachmentTypeOptions"
                            :key="item"
                            :label="item"
                            :value="item"
                          />
                        </el-select>
                        <el-button :loading="uploadingAttachment" plain type="success" @click="openAttachmentPicker">
                          上传附件
                        </el-button>
                        <el-button v-if="detailRecord.attachments.length" plain @click="handleDownloadAllAttachments">
                          打包下载
                        </el-button>
                      </div>
                    </div>
                    <div class="attachment-requirement-summary">
                      <el-tag
                        size="small"
                        :type="detailRecord.taskConfig?.requireAttachment ? 'warning' : 'info'"
                        effect="light"
                      >
                        {{ detailRecord.taskConfig?.requireAttachment ? "当前节点要求上传" : "当前节点未强制要求" }}
                      </el-tag>
                      <span class="attachment-list-summary">
                        共 {{ detailRecord.attachments.length }} 个附件，已覆盖 {{ attachmentStats.requiredUploaded }}/{{ requiredAttachmentGroupCount || 0 }} 个必传分组
                      </span>
                    </div>
                    <div v-if="attachmentTypeOptions.length" class="workflow-config-tags">
                      <el-tag
                        v-for="item in attachmentTypeOptions"
                        :key="item"
                        size="small"
                        effect="plain"
                      >
                        {{ item }}
                      </el-tag>
                    </div>
                    <div v-if="attachmentMissingCategories.length" class="workflow-config-tags">
                      <el-tag
                        v-for="item in attachmentMissingCategories"
                        :key="item"
                        size="small"
                        type="danger"
                        effect="plain"
                      >
                        待补：{{ item }}
                      </el-tag>
                    </div>
                  </div>

                  <div class="attachment-list-panel">
                    <div class="attachment-list-toolbar">
                      <el-input
                        v-model="attachmentSearchKeyword"
                        clearable
                        placeholder="搜索附件名、分组、节点、上传人"
                        style="width: 100%"
                      />
                      <el-select
                        v-model="attachmentFilterCategory"
                        clearable
                        placeholder="按附件分组筛选"
                        style="width: 180px"
                      >
                        <el-option
                          v-for="item in attachmentFilterOptions"
                          :key="item"
                          :label="item"
                          :value="item"
                        />
                      </el-select>
                      <el-select
                        v-model="attachmentFilterType"
                        clearable
                        placeholder="按文件类型筛选"
                        style="width: 160px"
                      >
                        <el-option label="图片" value="image" />
                        <el-option label="PDF" value="pdf" />
                        <el-option label="其他" value="other" />
                      </el-select>
                    </div>
                    <div v-if="attachmentTreeData.length" class="attachment-tree-shell">
                      <el-tree
                        :data="attachmentTreeData"
                        node-key="key"
                        default-expand-all
                        highlight-current
                        :expand-on-click-node="false"
                        :props="{ children: 'children', label: 'label' }"
                        @node-click="handleAttachmentTreeNodeClick"
                      >
                        <template #default="{ data }">
                          <div
                            class="attachment-tree-node"
                            :class="{
                              'is-group': data.nodeType === 'group',
                              'is-attachment': data.nodeType === 'attachment',
                              'is-required': data.required,
                              'is-selected': data.nodeType === 'attachment' && selectedDetailAttachment?.id === data.attachment?.id,
                            }"
                          >
                            <template v-if="data.nodeType === 'group'">
                              <span class="attachment-tree-group-name">
                                {{ data.label }}<span v-if="data.required" class="attachment-tree-required">*</span>
                              </span>
                              <span v-if="data.required && !data.satisfied" class="attachment-tree-missing">未上传</span>
                              <span class="attachment-tree-count">{{ data.attachmentCount || 0 }}</span>
                            </template>
                            <template v-else>
                              <span class="attachment-tree-file-name">{{ data.label }}</span>
                              <span class="attachment-tree-file-meta">
                                {{ formatFileSize(data.attachment.fileSize) }} · {{ data.attachment.uploadedByName || "-" }}
                              </span>
                            </template>
                          </div>
                        </template>
                      </el-tree>
                    </div>
                    <el-empty v-else description="当前申请还没有上传附件" />
                  </div>
                </aside>

                <section class="attachment-preview-panel">
                  <div class="attachment-preview-panel-head">
                    <div>
                      <div class="workflow-handler-title">附件预览</div>
                      <div v-if="selectedDetailAttachment" class="attachment-list-summary">
                        {{ inlineAttachmentPreviewName || selectedDetailAttachment.originalName }}
                      </div>
                    </div>
                    <div v-if="selectedDetailAttachment" class="attachment-card-actions">
                      <el-button link type="primary" @click="handleAttachmentDownload(selectedDetailAttachment)">下载</el-button>
                    </div>
                  </div>

                  <template v-if="selectedDetailAttachment">
                    <div class="attachment-preview-meta">
                      <span>{{ selectedDetailAttachment.category || "-" }}</span>
                      <span class="request-detail-dot">•</span>
                      <span>{{ selectedDetailAttachment.stageCode || "-" }}</span>
                      <span class="request-detail-dot">•</span>
                      <span>{{ formatDateTime(selectedDetailAttachment.createdAt) }}</span>
                    </div>
                    <div v-loading="inlineAttachmentPreviewLoading" class="attachment-preview-shell attachment-preview-shell--inline">
                      <template v-if="inlineAttachmentPreviewUrl && inlineAttachmentPreviewType === 'image'">
                        <img
                          :src="inlineAttachmentPreviewUrl"
                          :alt="inlineAttachmentPreviewName || selectedDetailAttachment.originalName"
                          class="attachment-preview-image"
                        />
                      </template>
                      <template v-else-if="inlineAttachmentPreviewUrl && inlineAttachmentPreviewType === 'pdf'">
                        <iframe
                          :src="inlineAttachmentPreviewUrl"
                          class="attachment-preview-pdf"
                          title="附件预览"
                        ></iframe>
                      </template>
                      <div v-else class="attachment-inline-empty">
                        <div class="attachment-card-thumb attachment-card-thumb--large">
                          <span class="attachment-card-thumb-text">{{ getAttachmentKindLabel(selectedDetailAttachment) }}</span>
                        </div>
                        <div class="attachment-inline-empty-text">当前文件类型不支持直接预览，请使用下载查看原件。</div>
                      </div>
                    </div>
                  </template>
                  <el-empty v-else description="请选择左侧附件查看" />
                </section>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { deleteRequestAttachment, downloadRequestAttachment, downloadRequestAttachmentsBundle, fetchRequestDetail, fetchRequestWorkflowView, uploadRequestAttachment } from "../../api/request";
import { getAttachmentPreviewKind, getAttachmentKindLabel, formatFileSize, formatDateTime, statusTagType, workflowTagType } from "../../utils/attachmentHelpers";
import { buildDetailReportHtml, downloadTextFile, buildReportFilename, formatDataScope, formatCandidateMode } from "../../utils/requestReportBuilder";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  canUpload: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue"]);

const loading = ref(false);
const submitting = ref(false);
const detailLoading = ref(false);
const uploadingAttachment = ref(false);
const detailRecord = ref(null);
const detailWorkflowView = ref(null);
const detailTab = ref("overview");
const activeWorkflowStepCode = ref("");
const attachmentCategory = ref("");
const attachmentFilterCategory = ref("");
const attachmentFilterType = ref("");
const attachmentSearchKeyword = ref("");
const selectedDetailAttachmentId = ref(0);
const inlineAttachmentPreviewLoading = ref(false);
const inlineAttachmentPreviewUrl = ref("");
const inlineAttachmentPreviewName = ref("");
const inlineAttachmentPreviewType = ref("");
const attachmentThumbUrls = ref({});
const workflowCanvasRef = ref(null);
const attachmentInputRef = ref(null);
let workflowViewer = null;

const attachmentTemplateGroups = computed(() => detailRecord.value?.attachmentTemplates || []);
const requiredAttachmentGroupCount = computed(() =>
  attachmentTemplateGroups.value.filter((item) => item.required).length,
);
const attachmentTypeOptions = computed(() => {
  const categories = new Set(detailRecord.value?.taskConfig?.attachmentTypes || []);
  for (const item of attachmentTemplateGroups.value) {
    categories.add(item.name || item.category);
  }
  for (const item of detailRecord.value?.attachments || []) {
    if (item.category) {
      categories.add(item.category);
    }
  }
  return Array.from(categories);
});
const dialogAttachmentTypeOptions = computed(() => {
  const categories = new Set(editingRequestRecord.value?.taskConfig?.attachmentTypes || []);
  for (const item of editingRequestRecord.value?.attachmentTemplates || []) {
    categories.add(item.name || item.category);
  }
  return Array.from(categories);
});
const attachmentStats = computed(() => {
  const items = detailRecord.value?.attachments || [];
  return {
    total: items.length,
    imageCount: items.filter((item) => getAttachmentPreviewKind(item) === "image").length,
    pdfCount: items.filter((item) => getAttachmentPreviewKind(item) === "pdf").length,
    otherCount: items.filter((item) => !["image", "pdf"].includes(getAttachmentPreviewKind(item))).length,
    requiredUploaded: attachmentTemplateGroups.value.filter((item) => item.required && item.satisfied).length,
  };
});
const attachmentTemplateStats = computed(() => {
  const templates = attachmentTemplateGroups.value;
  return {
    total: templates.length,
    satisfied: templates.filter((item) => item.satisfied).length,
    pending: templates.filter((item) => !item.satisfied).length,
  };
});
const attachmentMissingCategories = computed(() =>
  attachmentTemplateGroups.value.filter((item) => item.required && !item.satisfied).map((item) => item.name || item.category),
);
const dialogAttachmentMissingCategories = computed(() =>
  dialogAttachmentTypeOptions.value.filter(
    (category) => !(editingRequestRecord.value?.attachments || []).some((item) => item.category === category),
  ),
);
const attachmentFilterOptions = computed(() => {
  const categories = new Set();
  for (const item of detailRecord.value?.attachments || []) {
    if (item.category) {
      categories.add(item.category);
    }
  }
  return Array.from(categories);
});
const filteredAttachments = computed(() => {
  const items = detailRecord.value?.attachments || [];
  return items.filter((item) => {
    if (attachmentFilterCategory.value && (item.category || "") !== attachmentFilterCategory.value) {
      return false;
    }
    if (attachmentFilterType.value) {
      const fileType = getAttachmentPreviewKind(item) || "other";
      if (fileType !== attachmentFilterType.value) {
        return false;
      }
    }
    if (attachmentSearchKeyword.value) {
      const keyword = attachmentSearchKeyword.value.trim().toLowerCase();
      const haystack = [item.originalName, item.category, item.stageCode, item.uploadedByName]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(keyword)) {
        return false;
      }
    }
    return true;
  });
});
const attachmentTreeData = computed(() => {
  const groupRows = attachmentTemplateGroups.value;
  const nodeMap = new Map();
  const roots = [];

  for (const item of groupRows) {
    nodeMap.set(item.key, {
      key: `group-${item.key}`,
      nodeType: "group",
      label: item.name || item.category,
      name: item.name || item.category,
      required: item.required,
      satisfied: item.satisfied,
      attachmentCount: item.uploadedCount || 0,
      children: [],
      templateKey: item.key,
      parentId: item.parentId,
    });
  }

  const templateIdKeyMap = new Map(
    groupRows
      .filter((item) => item.key && String(item.key).split(":").length > 1)
      .map((item) => [String(item.key).split(":")[1], item.key]),
  );

  for (const item of groupRows) {
    const current = nodeMap.get(item.key);
    const parentKey = item.parentId ? templateIdKeyMap.get(String(item.parentId)) : null;
    if (current && parentKey && nodeMap.has(parentKey)) {
      nodeMap.get(parentKey).children.push(current);
    } else if (current) {
      roots.push(current);
    }
  }

  let ungroupedNode = null;
  for (const item of filteredAttachments.value) {
    const target = Array.from(nodeMap.values()).find((node) => node.name === (item.category || "")) || (() => {
      if (!ungroupedNode) {
        ungroupedNode = {
          key: "group-ungrouped",
          nodeType: "group",
          label: "未分组",
          name: "未分组",
          required: false,
          satisfied: true,
          attachmentCount: 0,
          children: [],
        };
        roots.push(ungroupedNode);
      }
      return ungroupedNode;
    })();
    target.children.push({
      key: `attachment-${item.id}`,
      nodeType: "attachment",
      label: item.originalName,
      attachment: item,
      children: [],
    });
  }

  const sortNodes = (nodes) => {
    nodes.sort((a, b) => {
      if (a.nodeType !== b.nodeType) {
        return a.nodeType === "group" ? -1 : 1;
      }
      return String(a.label).localeCompare(String(b.label), "zh-Hans-CN");
    });
    nodes.forEach((node) => {
      if (node.children?.length) {
        sortNodes(node.children);
      }
    });
  };

  sortNodes(roots);
  return roots;
});


async function loadDetail(id) {
  detailLoading.value = true;
  try {
    const { data } = await fetchRequestDetail(id);
    revokeAttachmentThumbUrls();
    resetInlineAttachmentPreview();
    detailRecord.value = data.data;
    attachmentFilterCategory.value = "";
    attachmentFilterType.value = "";
    attachmentSearchKeyword.value = "";
    selectedDetailAttachmentId.value = data.data.attachments?.[0]?.id || 0;
    if (
      attachmentCategory.value &&
      !((data.data.taskConfig?.attachmentTypes || []).includes(attachmentCategory.value))
    ) {
      attachmentCategory.value = "";
    }
    activeWorkflowStepCode.value =
      data.data.currentTaskCode || data.data.workflowSteps?.find((item) => item.status === "current")?.code || "";
    const workflowResponse = await fetchRequestWorkflowView(id);
    detailWorkflowView.value = workflowResponse.data.data;
    await preloadAttachmentThumbnails(data.data.attachments || []);
    await syncSelectedDetailAttachment();
    await nextTick();
    if (detailTab.value === "diagram") {
      await renderWorkflowDiagram();
    }
    return data.data;
  } finally {
    detailLoading.value = false;
  }
}


async function ensureWorkflowViewer() {
  if (!workflowCanvasRef.value) {
    return null;
  }
  if (workflowViewer) {
    workflowViewer.destroy();
    workflowViewer = null;
  }
  const module = await import("bpmn-js/lib/NavigatedViewer");
  workflowViewer = new module.default({
    container: workflowCanvasRef.value,
  });
  return workflowViewer;
}

async function renderWorkflowDiagram() {
  if (!detailWorkflowView.value || !workflowCanvasRef.value) {
    return;
  }
  const viewer = await ensureWorkflowViewer();
  if (!viewer) {
    return;
  }
  await viewer.importXML(detailWorkflowView.value.content);
  viewer.get("canvas").zoom("fit-viewport", "auto");
  const canvas = viewer.get("canvas");
  const elementRegistry = viewer.get("elementRegistry");
  for (const item of detailWorkflowView.value.workflowSteps || []) {
    if (!elementRegistry.get(item.code)) {
      continue;
    }
    if (item.status === "current") {
      canvas.addMarker(item.code, "request-workflow-current");
    } else if (item.status === "completed") {
      canvas.addMarker(item.code, "request-workflow-completed");
    } else if (item.status === "rejected") {
      canvas.addMarker(item.code, "request-workflow-rejected");
    }
  }
  if (activeWorkflowStepCode.value && elementRegistry.get(activeWorkflowStepCode.value)) {
    canvas.addMarker(activeWorkflowStepCode.value, "request-workflow-focused");
  }
}

async function focusWorkflowStep(stepCode) {
  if (!stepCode) {
    return;
  }
  activeWorkflowStepCode.value = stepCode;
  if (detailTab.value !== "diagram") {
    detailTab.value = "diagram";
    await nextTick();
  }
  await renderWorkflowDiagram();
  if (!workflowViewer) {
    return;
  }
  const canvas = workflowViewer.get("canvas");
  const elementRegistry = workflowViewer.get("elementRegistry");
  const element = elementRegistry.get(stepCode);
  if (!element) {
    return;
  }
  canvas.zoom(1, element);
  canvas.scrollToElement(element, {
    top: 120,
    right: 120,
    bottom: 120,
    left: 120,
  });
}

async function getWorkflowSvgMarkup() {
  if (!detailWorkflowView.value?.content) {
    return "";
  }
  await nextTick();
  await renderWorkflowDiagram();
  if (!workflowViewer || typeof workflowViewer.saveSVG !== "function") {
    return "";
  }
  try {
    const result = await workflowViewer.saveSVG();
    return result?.svg || "";
  } catch {
    return "";
  }
}


async function handleExportDetailHtml() {
  if (!detailRecord.value) {
    return;
  }
  const svgMarkup = await getWorkflowSvgMarkup();
  const html = buildDetailReportHtml(svgMarkup);
  downloadTextFile(buildReportFilename(), html);
  ElMessage.success("审批留痕已导出为 HTML");
}

async function handlePrintDetail() {
  if (!detailRecord.value) {
    return;
  }
  const svgMarkup = await getWorkflowSvgMarkup();
  const html = buildDetailReportHtml(svgMarkup).replace(
    'window.location.search.includes("autoprint=1")',
    "true",
  );
  const printWindow = window.open("", "_blank", "width=1200,height=900");
  if (!printWindow) {
    ElMessage.warning("浏览器拦截了打印窗口，请允许弹窗后重试");
    return;
  }
  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
}


function openAttachmentPicker() {
  if (attachmentTypeOptions.value.length && !attachmentCategory.value) {
    ElMessage.warning("当前节点要求先选择附件分类");
    return;
  }
  attachmentInputRef.value?.click();
}


function revokeAttachmentPreviewUrl() {
  if (attachmentPreviewUrl.value) {
    URL.revokeObjectURL(attachmentPreviewUrl.value);
    attachmentPreviewUrl.value = "";
  }
}

function revokeInlineAttachmentPreviewUrl() {
  if (inlineAttachmentPreviewUrl.value) {
    URL.revokeObjectURL(inlineAttachmentPreviewUrl.value);
    inlineAttachmentPreviewUrl.value = "";
  }
}

function handleAttachmentPreviewClosed() {
  revokeAttachmentPreviewUrl();
  attachmentPreviewLoading.value = false;
  attachmentPreviewName.value = "";
  attachmentPreviewType.value = "";
  attachmentPreviewSource.value = null;
}

function resetInlineAttachmentPreview() {
  revokeInlineAttachmentPreviewUrl();
  inlineAttachmentPreviewLoading.value = false;
  inlineAttachmentPreviewName.value = "";
  inlineAttachmentPreviewType.value = "";
}

function revokeAttachmentThumbUrls() {
  for (const url of Object.values(attachmentThumbUrls.value)) {
    if (url) {
      URL.revokeObjectURL(url);
    }
  }
  attachmentThumbUrls.value = {};
}

function getAttachmentThumbnail(item) {
  return attachmentThumbUrls.value[item?.id] || "";
}


async function loadAttachmentThumbnail(item) {
  if (!detailRecord.value || getAttachmentPreviewKind(item) !== "image" || attachmentThumbUrls.value[item.id]) {
    return;
  }
  try {
    const response = await downloadRequestAttachment(detailRecord.value.id, item.id);
    const blob = new Blob([response.data], {
      type: item.contentType || response.headers["content-type"] || "application/octet-stream",
    });
    attachmentThumbUrls.value = {
      ...attachmentThumbUrls.value,
      [item.id]: URL.createObjectURL(blob),
    };
  } catch {
    // Ignore thumbnail failures and keep the file card usable.
  }
}

async function preloadAttachmentThumbnails(items = detailRecord.value?.attachments || []) {
  const targets = items.filter((item) => getAttachmentPreviewKind(item) === "image").slice(0, 12);
  await Promise.all(targets.map((item) => loadAttachmentThumbnail(item)));
}

function findFirstAttachmentNode(node) {
  if (!node) {
    return null;
  }
  if (node.nodeType === "attachment" && node.attachment) {
    return node.attachment;
  }
  for (const child of node.children || []) {
    const target = findFirstAttachmentNode(child);
    if (target) {
      return target;
    }
  }
  return null;
}

async function handleAttachmentTreeNodeClick(node) {
  if (!node) {
    return;
  }
  if (node.nodeType === "attachment" && node.attachment) {
    await handleAttachmentPreview(node.attachment);
    return;
  }
  const target = findFirstAttachmentNode(node);
  if (target) {
    await handleAttachmentPreview(target);
  }
}


async function selectDetailAttachment(item) {

  selectedDetailAttachmentId.value = item?.id || 0;
  resetInlineAttachmentPreview();
  if (!detailRecord.value || !item) {
    return;
  }
  const previewType = getAttachmentPreviewKind(item);
  inlineAttachmentPreviewName.value = item.originalName || "附件预览";
  inlineAttachmentPreviewType.value = previewType;
  if (!previewType) {
    return;
  }

  inlineAttachmentPreviewLoading.value = true;
  try {
    const response = await downloadRequestAttachment(detailRecord.value.id, item.id);
    const blob = new Blob([response.data], {
      type: item.contentType || response.headers["content-type"] || "application/octet-stream",
    });
    inlineAttachmentPreviewUrl.value = URL.createObjectURL(blob);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "附件预览失败");
  } finally {
    inlineAttachmentPreviewLoading.value = false;
  }
}

async function syncSelectedDetailAttachment() {
  if (!props.modelValue || detailTab.value !== "attachments") {
    return;
  }
  const target = selectedDetailAttachment.value;
  if (!target) {
    selectedDetailAttachmentId.value = 0;
    resetInlineAttachmentPreview();
    return;
  }
  if (target.id !== selectedDetailAttachmentId.value || !inlineAttachmentPreviewName.value) {
    await selectDetailAttachment(target);
  }
}


async function handleAttachmentInputChange(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file || !detailRecord.value) {
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  if (attachmentCategory.value?.trim()) {
    formData.append("category", attachmentCategory.value.trim());
  }
  uploadingAttachment.value = true;
  try {
    await uploadRequestAttachment(detailRecord.value.id, formData);
    attachmentCategory.value = "";
    ElMessage.success("附件上传成功");
    await loadDetail(detailRecord.value.id);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "附件上传失败");
  } finally {
    uploadingAttachment.value = false;
  }
}


async function handleAttachmentDelete(item) {
  if (!detailRecord.value) {
    return;
  }
  try {
    await ElMessageBox.confirm(`确定删除附件“${item.originalName}”吗？`, "删除附件", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteRequestAttachment(detailRecord.value.id, item.id);
    ElMessage.success("附件已删除");
    await loadDetail(detailRecord.value.id);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "附件删除失败");
    }
  }
}


async function handleDownloadAllAttachments() {
  if (!detailRecord.value) {
    return;
  }
  try {
    const response = await downloadRequestAttachmentsBundle(detailRecord.value.id);
    const blob = new Blob([response.data], {
      type: response.headers["content-type"] || "application/zip",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${detailRecord.value.serialNo || "request"}-attachments.zip`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "附件打包下载失败");
  }
}

async function handleAttachmentDownload(item) {
  const caseId = item?.__caseId || detailRecord.value?.id;
  if (!caseId) {
    return;
  }
  try {
    const response = await downloadRequestAttachment(caseId, item.id);
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


watch(detailTab, async (value) => {
  if (value === "diagram" && props.modelValue && detailWorkflowView.value) { await nextTick(); await renderWorkflowDiagram(); return; }
  if (value === "attachments" && props.modelValue) { await preloadAttachmentThumbnails(filteredAttachments.value); await syncSelectedDetailAttachment(); }
});
watch(attachmentFilterCategory, async () => { if (props.modelValue && detailTab.value === "attachments") { await preloadAttachmentThumbnails(filteredAttachments.value); await syncSelectedDetailAttachment(); } });
watch(attachmentFilterType, async () => { if (props.modelValue && detailTab.value === "attachments") { await preloadAttachmentThumbnails(filteredAttachments.value); await syncSelectedDetailAttachment(); } });
watch(attachmentSearchKeyword, async () => { if (props.modelValue && detailTab.value === "attachments") { await preloadAttachmentThumbnails(filteredAttachments.value); await syncSelectedDetailAttachment(); } });

watch(() => props.modelValue, (value) => {
  if (value) return;
  resetInlineAttachmentPreview();
  revokeAttachmentThumbUrls();
  detailRecord.value = null;
  detailWorkflowView.value = null;
  detailTab.value = "overview";
  activeWorkflowStepCode.value = "";
  selectedDetailAttachmentId.value = 0;
  attachmentCategory.value = "";
  attachmentFilterCategory.value = "";
  attachmentFilterType.value = "";
  attachmentSearchKeyword.value = "";
  if (workflowViewer) { workflowViewer.destroy(); workflowViewer = null; }
});

onBeforeUnmount(() => {
  revokeAttachmentThumbUrls();
  if (workflowViewer) { workflowViewer.destroy(); workflowViewer = null; }
});

defineExpose({ loadDetail });
</script>
