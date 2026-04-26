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

  <el-dialog
    v-model="dialogVisible"
    :title="editingId ? '编辑业务申请' : '新增业务申请'"
    width="1080px"
    destroy-on-close
    class="request-form-dialog"
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
      <el-button @click="handleCloseDialog">关闭</el-button>
      <el-button :loading="submitting" type="success" @click="handleSubmitForm">保存表单</el-button>
    </template>
  </el-dialog>

  <el-drawer
    v-model="detailVisible"
    title="业务申请详情"
    size="100%"
    destroy-on-close
    class="request-detail-drawer"
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

  <el-dialog
    v-model="attachmentPreviewVisible"
    :title="attachmentPreviewName || '附件预览'"
    width="960px"
    destroy-on-close
    class="attachment-preview-dialog"
    @closed="handleAttachmentPreviewClosed"
  >
    <div v-loading="attachmentPreviewLoading" class="attachment-preview-shell">
      <template v-if="attachmentPreviewUrl">
        <img
          v-if="attachmentPreviewType === 'image'"
          :src="attachmentPreviewUrl"
          :alt="attachmentPreviewName || '附件预览'"
          class="attachment-preview-image"
        />
        <iframe
          v-else-if="attachmentPreviewType === 'pdf'"
          :src="attachmentPreviewUrl"
          class="attachment-preview-pdf"
          title="附件预览"
        ></iframe>
      </template>
      <el-empty v-else description="当前附件暂不支持在线预览" />
    </div>

    <template #footer>
      <el-button @click="attachmentPreviewVisible = false">关闭</el-button>
      <el-button
        v-if="attachmentPreviewSource"
        plain
        type="primary"
        @click="handleAttachmentDownload(attachmentPreviewSource)"
      >
        下载原件
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";

import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  approveRequest,
  createRequest,
  deleteRequest,
  deleteRequestAttachment,
  downloadRequestAttachment,
  downloadRequestAttachmentsBundle,
  fetchRequestDetail,
  fetchRequests,
  fetchRequestWorkflowOptions,
  fetchRequestWorkflowView,
  rejectRequest,
  submitRequest,
  uploadRequestAttachment,
  updateRequest,
} from "../api/request";
import { fetchWorkflowDefinition } from "../api/workflow";
import { useAuthStore } from "../stores/auth";
import { validateChinaId, validateMobile } from "../utils/validators";

const authStore = useAuthStore();

const canManageRequests = computed(() => authStore.hasPermission("requests.manage"));
const canUploadAttachmentsForDetail = computed(() => {
  if (!detailRecord.value) {
    return false;
  }
  return ["edit", "approve", "reject"].some((action) => hasAction(detailRecord.value, action));
});
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

const loading = ref(false);
const submitting = ref(false);
const detailLoading = ref(false);
const uploadingAttachment = ref(false);
const dialogVisible = ref(false);
const detailVisible = ref(false);
const editingId = ref(0);
const rows = ref([]);
const detailRecord = ref(null);
const editingRequestRecord = ref(null);
const detailWorkflowView = ref(null);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const statusFilter = ref("");
const formRef = ref();
const attachmentInputRef = ref(null);
const dialogAttachmentInputRef = ref(null);
const workflowCanvasRef = ref(null);
const requestWorkflowMappings = ref([]);
const workflowOptions = ref([]);
const workflowVersionOptions = ref([]);
const lockWorkflowBinding = ref(false);
const detailTab = ref("overview");
const activeWorkflowStepCode = ref("");
const attachmentCategory = ref("");
const dialogAttachmentCategory = ref("");
const attachmentFilterCategory = ref("");
const attachmentFilterType = ref("");
const attachmentSearchKeyword = ref("");
const selectedDetailAttachmentId = ref(0);
const inlineAttachmentPreviewLoading = ref(false);
const inlineAttachmentPreviewUrl = ref("");
const inlineAttachmentPreviewName = ref("");
const inlineAttachmentPreviewType = ref("");
const attachmentPreviewVisible = ref(false);
const attachmentPreviewLoading = ref(false);
const attachmentPreviewUrl = ref("");
const attachmentPreviewName = ref("");
const attachmentPreviewType = ref("");
const attachmentPreviewSource = ref(null);
const attachmentThumbUrls = ref({});

const selectedDetailAttachment = computed(() =>
  filteredAttachments.value.find((item) => item.id === selectedDetailAttachmentId.value) || filteredAttachments.value[0] || null,
);

const statusOptions = [
  { label: "待提交", value: "待提交" },
  { label: "审核中", value: "审核中" },
  { label: "已办结", value: "已办结" },
  { label: "已退回", value: "已退回" },
];

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
  if (!value) {
    callback();
    return;
  }
  if (!validateMobile(value)) {
    callback(new Error("请输入正确的手机号"));
    return;
  }
  callback();
};

const validateContractorIdNo = (_rule, value, callback) => {
  if (!value) {
    callback();
    return;
  }
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

let workflowViewer = null;

function resetForm() {
  Object.assign(form, createEmptyForm());
  workflowVersionOptions.value = [];
  lockWorkflowBinding.value = false;
  editingRequestRecord.value = null;
  dialogAttachmentCategory.value = "";
  formRef.value?.clearValidate();
}

function handleCloseDialog() {
  dialogVisible.value = false;
  resetForm();
}

function findWorkflowMapping(requestType) {
  return requestWorkflowMappings.value.find((item) => item.requestType === requestType) || null;
}

function applyWorkflowMapping(requestType, { force = false } = {}) {
  const mapping = findWorkflowMapping(requestType);
  if (!mapping) {
    if (force) {
      form.workflowCode = "";
      form.workflowVersionId = null;
    }
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
    if (
      preferredVersionId &&
      workflowVersionOptions.value.some((item) => item.id === preferredVersionId)
    ) {
      form.workflowVersionId = preferredVersionId;
      return;
    }
    if (
      form.workflowVersionId &&
      !workflowVersionOptions.value.some((item) => item.id === form.workflowVersionId)
    ) {
      form.workflowVersionId = null;
    }
  } catch (error) {
    workflowVersionOptions.value = [];
    form.workflowVersionId = null;
    ElMessage.error(error.response?.data?.detail || "加载流程版本列表失败");
  }
}

function statusTagType(status) {
  return (
    {
      待提交: "info",
      审核中: "warning",
      已办结: "success",
      已退回: "danger",
    }[status] || "info"
  );
}

function workflowTagType(status) {
  return (
    {
      completed: "success",
      current: "warning",
      pending: "info",
      rejected: "danger",
    }[status] || "info"
  );
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  return String(value).replace("T", " ").slice(0, 19);
}

function formatDataScope(value) {
  return (
    {
      all: "全部数据",
      county: "县级范围",
      town: "镇级范围",
      village: "村级范围",
      self: "仅本人相关",
      "": "沿用账号范围",
      null: "沿用账号范围",
      undefined: "沿用账号范围",
    }[value] || value || "沿用账号范围"
  );
}

function formatCandidateMode(value) {
  return (
    {
      permission_scope: "按权限编码匹配",
      role_scope: "按候选角色匹配",
      manual_assign: "人工指定办理人",
      "": "按权限与数据范围自动匹配",
      null: "按权限与数据范围自动匹配",
      undefined: "按权限与数据范围自动匹配",
    }[value] || value || "按权限与数据范围自动匹配"
  );
}

function formatFileSize(value) {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatReportText(value) {
  if (!value) {
    return "-";
  }
  return escapeHtml(String(value)).replaceAll("\n", "<br />");
}

function buildWorkflowStepHtml(steps) {
  return (steps || [])
    .map(
      (item) => `
        <div class="report-step report-step--${escapeHtml(item.status)}">
          <div class="report-step-name">${escapeHtml(item.name)}</div>
          <div class="report-step-meta">${escapeHtml(item.code)} · ${escapeHtml(item.label)}</div>
        </div>`,
    )
    .join("");
}

function buildCandidateHtml(candidates) {
  if (!candidates?.length) {
    return '<div class="report-empty">当前环节暂无候选办理人。</div>';
  }
  return candidates
    .map(
      (item) => `
        <div class="report-card">
          <div class="report-card-title">${escapeHtml(item.userName || item.username || "-")}</div>
          <div class="report-card-meta">${escapeHtml(item.roleName || "-")} · ${escapeHtml(item.regionName || item.regionCode || "-")}</div>
        </div>`,
    )
    .join("");
}

function buildParticipantHtml(participants) {
  if (!participants?.length) {
    return '<div class="report-empty">当前申请还没有办理轨迹。</div>';
  }
  return participants
    .map(
      (item) => `
        <div class="report-timeline-item">
          <div class="report-timeline-head">
            <div class="report-card-title">${escapeHtml(item.actionLabel || item.action)}</div>
            <div class="report-card-meta">${escapeHtml(formatDateTime(item.createdAt))}</div>
          </div>
          <div class="report-card-meta">${escapeHtml(item.userName || item.username || "-")}${item.roleName ? ` · ${escapeHtml(item.roleName)}` : ""}${item.stepName ? ` · ${escapeHtml(item.stepName)}` : ""}</div>
          ${item.comment ? `<div class="report-comment">${formatReportText(item.comment)}</div>` : ""}
        </div>`,
    )
    .join("");
}

function buildAttachmentHtml(attachments) {
  if (!attachments?.length) {
    return '<div class="report-empty">当前申请还没有上传附件。</div>';
  }
  return attachments
    .map(
      (item) => `
        <div class="report-card">
          <div class="report-card-title">${escapeHtml(item.originalName || "-")}</div>
          <div class="report-card-meta">
            ${escapeHtml(formatFileSize(item.fileSize))}
            ${item.category ? ` 路 ${escapeHtml(item.category)}` : ""}
            ${item.stageCode ? ` 路 ${escapeHtml(item.stageCode)}` : ""}
          </div>
          <div class="report-card-meta">
            ${escapeHtml(item.uploadedByName || "-")} 路 ${escapeHtml(formatDateTime(item.createdAt))}
          </div>
        </div>`,
    )
    .join("");
}

function buildTaskConfigHtml(taskConfig) {
  if (!taskConfig) {
    return '<div class="report-empty">当前节点没有额外业务配置。</div>';
  }
  const candidateRoles = taskConfig.candidateRoleCodes?.length
    ? taskConfig.candidateRoleCodes.map((item) => `<span class="report-pill">${escapeHtml(item)}</span>`).join("")
    : '<span class="report-empty-inline">未单独限定</span>';
  const attachmentTypes = taskConfig.attachmentTypes?.length
    ? taskConfig.attachmentTypes.map((item) => `<span class="report-pill">${escapeHtml(item)}</span>`).join("")
    : '<span class="report-empty-inline">未配置具体分类</span>';
  return `
    <div class="report-grid report-grid--two">
      <div class="report-field"><span class="report-field-label">权限编码</span><span class="report-field-value">${escapeHtml(taskConfig.permissionCode || "-")}</span></div>
      <div class="report-field"><span class="report-field-label">数据范围</span><span class="report-field-value">${escapeHtml(formatDataScope(taskConfig.dataScope))}</span></div>
      <div class="report-field"><span class="report-field-label">候选模式</span><span class="report-field-value">${escapeHtml(formatCandidateMode(taskConfig.candidateUserMode))}</span></div>
      <div class="report-field"><span class="report-field-label">审核意见</span><span class="report-field-value">${taskConfig.requireComment ? "必须填写" : "可选填写"}</span></div>
      <div class="report-field report-field--full"><span class="report-field-label">候选角色</span><span class="report-field-value report-pill-wrap">${candidateRoles}</span></div>
    </div>`;
}

function hasAction(row, action) {
  return Array.isArray(row.availableActions) && row.availableActions.includes(action);
}

async function loadData() {
  loading.value = true;
  try {
    const { data } = await fetchRequests({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      status: statusFilter.value || undefined,
    });
    rows.value = data.data.items;
    total.value = data.data.total;
  } finally {
    loading.value = false;
  }
}

async function loadWorkflowOptions() {
  try {
    const { data } = await fetchRequestWorkflowOptions();
    requestWorkflowMappings.value = data.data.mappings || [];
    workflowOptions.value = data.data.workflows || [];
    applyWorkflowMapping(form.requestType, { force: !form.workflowCode });
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "加载业务流程映射失败");
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

function buildDetailReportHtml(svgMarkup = "") {
  if (!detailRecord.value) {
    return "";
  }
  const detail = detailRecord.value;
  const workflow = detailWorkflowView.value;
  const workflowSection = svgMarkup
    ? `<div class="report-diagram">${svgMarkup}</div>`
    : '<div class="report-empty">当前流程图未生成图形快照，已保留流程步骤摘要。</div>';
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>${escapeHtml(detail.requestTitle || detail.serialNo)} - 审批留痕</title>
  <style>
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 32px; color: #2f3b24; background: #f6f4eb; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
    .report-shell { max-width: 1120px; margin: 0 auto; background: #fffdfa; border: 1px solid #e7e1cf; border-radius: 24px; padding: 30px; box-shadow: 0 16px 40px rgba(69, 80, 44, 0.08); }
    .report-header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; padding-bottom: 20px; border-bottom: 1px solid #ebe5d5; }
    .report-title { margin: 0; font-size: 30px; font-weight: 800; letter-spacing: 0.02em; }
    .report-subtitle { margin-top: 10px; color: #6d745d; font-size: 14px; }
    .report-status { display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 999px; background: #eef5df; color: #55712f; font-weight: 700; }
    .report-section { margin-top: 24px; }
    .report-section-title { margin: 0 0 14px; font-size: 18px; font-weight: 800; }
    .report-grid { display: grid; gap: 12px; }
    .report-grid--summary { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .report-grid--two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .report-field, .report-card, .report-step, .report-timeline-item { padding: 14px 16px; border: 1px solid #e8e1d0; border-radius: 16px; background: #fff; }
    .report-field--full { grid-column: 1 / -1; }
    .report-field-label { display: block; color: #7b806d; font-size: 13px; }
    .report-field-value { display: block; margin-top: 8px; font-size: 15px; font-weight: 700; line-height: 1.7; word-break: break-word; }
    .report-step { background: #fbfaf5; }
    .report-step--completed { background: #f0f9eb; border-color: #d7ebc6; }
    .report-step--current { background: #fdf6ec; border-color: #f3ddbb; }
    .report-step--rejected { background: #fef0f0; border-color: #f6c7c7; }
    .report-step-name, .report-card-title { font-size: 15px; font-weight: 800; }
    .report-step-meta, .report-card-meta { margin-top: 8px; color: #747b66; font-size: 13px; line-height: 1.6; }
    .report-pill-wrap { display: flex; flex-wrap: wrap; gap: 8px; }
    .report-pill { display: inline-flex; align-items: center; padding: 5px 10px; border-radius: 999px; background: #eef5df; color: #55712f; font-size: 12px; font-weight: 700; }
    .report-empty, .report-empty-inline { color: #8b907f; font-size: 13px; }
    .report-comment { margin-top: 10px; padding: 10px 12px; border-radius: 12px; background: #f6f8ef; line-height: 1.7; }
    .report-timeline { display: grid; gap: 12px; }
    .report-timeline-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
    .report-diagram { border: 1px solid #e8e1d0; border-radius: 18px; background: #fafcf7; padding: 16px; overflow: hidden; }
    .report-diagram svg { width: 100%; height: auto; }
    @media print {
      body { background: #fff; padding: 0; }
      .report-shell { border: 0; border-radius: 0; box-shadow: none; max-width: none; }
      .report-section, .report-field, .report-card, .report-step, .report-timeline-item { break-inside: avoid; }
    }
  </style>
</head>
<body>
  <div class="report-shell">
    <div class="report-header">
      <div>
        <h1 class="report-title">${escapeHtml(detail.requestTitle || detail.serialNo)}</h1>
        <div class="report-subtitle">${escapeHtml(detail.serialNo)} · ${escapeHtml(detail.requestType || "-")} · ${escapeHtml(detail.workflowVersionLabel || "跟随当前生效版本")}</div>
      </div>
      <div class="report-status">${escapeHtml(detail.status || "-")} · ${escapeHtml(detail.currentStep || "-")}</div>
    </div>

    <section class="report-section">
      <h2 class="report-section-title">摘要信息</h2>
      <div class="report-grid report-grid--summary">
        <div class="report-field"><span class="report-field-label">创建人</span><span class="report-field-value">${escapeHtml(detail.createdByName || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">租户编码</span><span class="report-field-value">${escapeHtml(detail.tenantCode || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">区域编码</span><span class="report-field-value">${escapeHtml(detail.regionCode || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">更新时间</span><span class="report-field-value">${escapeHtml(formatDateTime(detail.updatedAt))}</span></div>
      </div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">基础信息</h2>
      <div class="report-grid report-grid--two">
        <div class="report-field"><span class="report-field-label">发包方</span><span class="report-field-value">${escapeHtml(detail.issuerName || "-")} (${escapeHtml(detail.issuerCode || "-")})</span></div>
        <div class="report-field"><span class="report-field-label">承包方</span><span class="report-field-value">${escapeHtml(detail.contractorName || "-")} (${escapeHtml(detail.contractorCode || "-")})</span></div>
        <div class="report-field"><span class="report-field-label">证件类型</span><span class="report-field-value">${escapeHtml(detail.contractorIdType || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">证件号码</span><span class="report-field-value">${escapeHtml(detail.contractorIdNo || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">联系电话</span><span class="report-field-value">${escapeHtml(detail.mobile || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">合同代码</span><span class="report-field-value">${escapeHtml(detail.contractCode || "-")}</span></div>
        <div class="report-field report-field--full"><span class="report-field-label">联系地址</span><span class="report-field-value">${formatReportText(detail.address)}</span></div>
        <div class="report-field report-field--full"><span class="report-field-label">申请原因</span><span class="report-field-value">${formatReportText(detail.reason)}</span></div>
        <div class="report-field report-field--full"><span class="report-field-label">备注</span><span class="report-field-value">${formatReportText(detail.note)}</span></div>
      </div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">当前节点配置</h2>
      ${buildTaskConfigHtml(detail.taskConfig)}
    </section>

    <section class="report-section">
      <h2 class="report-section-title">流程步骤</h2>
      <div class="report-grid">${buildWorkflowStepHtml(detail.workflowSteps)}</div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">当前流程图</h2>
      <div class="report-card-meta">${escapeHtml(workflow?.workflowName || detail.workflowCode || "-")} · ${escapeHtml(workflow?.workflowVersionLabel || detail.workflowVersionLabel || "跟随当前生效版本")}</div>
      ${workflowSection}
    </section>

    <section class="report-section">
      <h2 class="report-section-title">候选办理人</h2>
      <div class="report-grid">${buildCandidateHtml(detail.candidateHandlers)}</div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">附件清单</h2>
      <div class="report-grid">${buildAttachmentHtml(detail.attachments)}</div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">审批留痕</h2>
      <div class="report-timeline">${buildParticipantHtml(detail.participants)}</div>
    </section>
  </div>
  <script>
    window.addEventListener("load", function () {
      if (window.location.search.includes("autoprint=1")) {
        setTimeout(function () { window.print(); }, 240);
      }
    });
  <\/script>
</body>
</html>`;
}

function downloadTextFile(filename, content) {
  const blob = new Blob([content], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function buildReportFilename() {
  const serialNo = detailRecord.value?.serialNo || "request";
  return `${serialNo}-approval-report.html`.replace(/[\\/:*?"<>|]/g, "_");
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

function getAttachmentPreviewKind(item) {
  const contentType = (item?.contentType || "").toLowerCase();
  const fileName = (item?.originalName || "").toLowerCase();
  if (contentType.startsWith("image/") || /\.(png|jpe?g|gif|bmp|webp|svg)$/i.test(fileName)) {
    return "image";
  }
  if (contentType.includes("pdf") || /\.pdf$/i.test(fileName)) {
    return "pdf";
  }
  return "";
}

function isPreviewableAttachment(item) {
  return Boolean(getAttachmentPreviewKind(item));
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

function getAttachmentKindLabel(item) {
  const previewType = getAttachmentPreviewKind(item);
  if (previewType === "image") {
    return "图片";
  }
  if (previewType === "pdf") {
    return "PDF";
  }
  const fileName = item?.originalName || "";
  const extension = fileName.includes(".") ? fileName.split(".").pop() : "";
  return (extension || "文件").toUpperCase();
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
  if (!detailVisible.value || detailTab.value !== "attachments") {
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

async function handleDialogAttachmentInputChange(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file || !editingRequestRecord.value) {
    return;
  }
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
    await refreshDetailIfOpen(editingRequestRecord.value.id);
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

async function handleDialogAttachmentDelete(item) {
  if (!editingRequestRecord.value) {
    return;
  }
  try {
    await ElMessageBox.confirm(`确定删除附件“${item.originalName}”吗？`, "删除附件", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteRequestAttachment(editingRequestRecord.value.id, item.id);
    const { data } = await fetchRequestDetail(editingRequestRecord.value.id);
    editingRequestRecord.value = data.data;
    ElMessage.success("附件已删除");
    await refreshDetailIfOpen(editingRequestRecord.value.id);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "附件删除失败");
    }
  }
}

async function handleAttachmentPreview(item) {
  await selectDetailAttachment(item);
}

async function handleDialogAttachmentPreview(item) {
  if (!editingRequestRecord.value) {
    return;
  }
  const previewType = getAttachmentPreviewKind(item);
  if (!previewType) {
    ElMessage.warning("当前附件暂不支持在线预览");
    return;
  }

  attachmentPreviewVisible.value = true;
  attachmentPreviewLoading.value = true;
  attachmentPreviewName.value = item.originalName || "附件预览";
  attachmentPreviewType.value = previewType;
  attachmentPreviewSource.value = { ...item, __caseId: editingRequestRecord.value.id };
  revokeAttachmentPreviewUrl();

  try {
    const response = await downloadRequestAttachment(editingRequestRecord.value.id, item.id);
    const blob = new Blob([response.data], {
      type: item.contentType || response.headers["content-type"] || "application/octet-stream",
    });
    attachmentPreviewUrl.value = URL.createObjectURL(blob);
  } catch (error) {
    attachmentPreviewVisible.value = false;
    ElMessage.error(error.response?.data?.detail || "附件预览失败");
  } finally {
    attachmentPreviewLoading.value = false;
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

async function handleDialogAttachmentDownload(item) {
  await handleAttachmentDownload({ ...item, __caseId: editingRequestRecord.value?.id });
}

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

async function refreshDetailIfOpen(id) {
  if (detailVisible.value && detailRecord.value?.id === id) {
    await loadDetail(id);
  }
}

function handleSearch() {
  page.value = 1;
  loadData();
}

function resetFilters() {
  keyword.value = "";
  statusFilter.value = "";
  page.value = 1;
  loadData();
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
  editingId.value = 0;
  resetForm();
  applyWorkflowMapping(form.requestType, { force: true });
  loadWorkflowVersions(form.workflowCode, form.workflowVersionId);
  dialogVisible.value = true;
}

async function openEditDialog(row) {
  editingId.value = row.id;
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
    if (
      dialogAttachmentCategory.value &&
      !((data.data.taskConfig?.attachmentTypes || []).includes(dialogAttachmentCategory.value))
    ) {
      dialogAttachmentCategory.value = "";
    }
    applyWorkflowMapping(form.requestType, { force: !form.workflowCode });
    await loadWorkflowVersions(form.workflowCode, data.data.workflowVersionId || null);
    formRef.value?.clearValidate();
    dialogVisible.value = true;
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "加载业务申请详情失败");
  }
}

async function openDetail(row) {
  detailTab.value = "overview";
  detailVisible.value = true;
  await loadDetail(row.id);
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
    if (editingId.value) {
      await updateRequest(editingId.value, payload);
      const { data } = await fetchRequestDetail(editingId.value);
      editingRequestRecord.value = data.data;
      ElMessage.success("业务申请已更新");
      await refreshDetailIfOpen(editingId.value);
    } else {
      const response = await createRequest(payload);
      editingId.value = response.data.data.id;
      editingRequestRecord.value = response.data.data;
      lockWorkflowBinding.value = Boolean(response.data.data.submittedAt);
      ElMessage.success("业务申请已创建，请继续上传附件");
    }
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存失败");
  } finally {
    submitting.value = false;
  }
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

watch(
  () => form.requestType,
  (value) => {
    if (lockWorkflowBinding.value) {
      return;
    }
    applyWorkflowMapping(value);
  },
);

watch(
  () => form.workflowCode,
  async (value, oldValue) => {
    if (!value || value === oldValue) {
      return;
    }
    if (!lockWorkflowBinding.value) {
      const mapping = findWorkflowMapping(form.requestType);
      form.workflowVersionId = mapping?.workflowKey === value ? (mapping.workflowVersionId ?? null) : null;
    }
    await loadWorkflowVersions(value, form.workflowVersionId);
  },
);

watch(detailTab, async (value) => {
  if (value === "diagram" && detailVisible.value && detailWorkflowView.value) {
    await nextTick();
    await renderWorkflowDiagram();
    return;
  }
  if (value === "attachments" && detailVisible.value) {
    await preloadAttachmentThumbnails(filteredAttachments.value);
    await syncSelectedDetailAttachment();
  }
});

watch(attachmentFilterCategory, async () => {
  if (detailVisible.value && detailTab.value === "attachments") {
    await preloadAttachmentThumbnails(filteredAttachments.value);
    await syncSelectedDetailAttachment();
  }
});

watch(attachmentFilterType, async () => {
  if (detailVisible.value && detailTab.value === "attachments") {
    await preloadAttachmentThumbnails(filteredAttachments.value);
    await syncSelectedDetailAttachment();
  }
});

watch(attachmentSearchKeyword, async () => {
  if (detailVisible.value && detailTab.value === "attachments") {
    await preloadAttachmentThumbnails(filteredAttachments.value);
    await syncSelectedDetailAttachment();
  }
});

watch(dialogVisible, (value) => {
  if (!value) {
    resetForm();
  }
});

watch(detailVisible, (value) => {
  if (value) {
    return;
  }
  resetInlineAttachmentPreview();
  attachmentPreviewVisible.value = false;
  handleAttachmentPreviewClosed();
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
  if (workflowViewer) {
    workflowViewer.destroy();
    workflowViewer = null;
  }
});

onMounted(async () => {
  if (canManageRequests.value) {
    await Promise.all([loadWorkflowOptions(), loadData()]);
    return;
  }
  await loadData();
});

onBeforeUnmount(() => {
  handleAttachmentPreviewClosed();
  revokeAttachmentThumbUrls();
  if (workflowViewer) {
    workflowViewer.destroy();
    workflowViewer = null;
  }
});
</script>
