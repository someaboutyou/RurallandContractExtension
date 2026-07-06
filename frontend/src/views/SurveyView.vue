<template>
  <div class="survey-page">
    <section class="panel survey-batch-panel">
      <div class="batch-panel-header">
        <div class="panel-title">调查批次</div>
        <div class="batch-panel-actions">
          <el-select v-model="batchSurveyStatus" clearable placeholder="调查状态" class="batch-header-filter">
            <el-option label="未调查" value="not_started" />
            <el-option label="调查中" value="in_progress" />
            <el-option label="已调查" value="surveyed" />
            <el-option label="已确认" value="confirmed" />
            <el-option label="已跳过" value="skipped" />
          </el-select>
          <el-tooltip content="新建调查批次" placement="top">
            <el-button v-if="canManage" :icon="Plus" circle type="success" @click="openCreateBatch" />
          </el-tooltip>
        </div>
      </div>
      <el-input
        v-model="batchKeyword"
        :prefix-icon="Search"
        clearable
        placeholder="搜索批次"
        class="batch-search"
        @keyup.enter="loadBatches"
        @clear="loadBatches"
      />

      <div v-loading="batchLoading" class="batch-card-list">
        <el-empty v-if="!filteredBatches.length && !batchLoading" description="暂无调查批次" :image-size="88" />
        <el-tooltip
          v-for="batch in filteredBatches"
          :key="batch.id"
          placement="right"
          effect="light"
          :show-after="250"
          popper-class="batch-detail-tooltip"
        >
          <template #content>
            <div class="batch-tooltip-content">
              <div><span>批次号</span>{{ batch.batchNo || "-" }}</div>
              <div><span>创建时间</span>{{ formatDateTime(batch.createdAt) }}</div>
              <div><span>调查区域</span>{{ batch.regionName || batch.regionCode || "-" }}</div>
              <div><span>已调查</span>{{ batch.surveyedCount || 0 }} 户</div>
              <div><span>有变化</span>{{ batch.changedCount || 0 }} 户</div>
              <div><span>已确认</span>{{ batch.confirmedCount || 0 }} 户</div>
              <div><span>已跳过</span>{{ batch.skippedCount || 0 }} 户</div>
            </div>
          </template>
          <button
            type="button"
            class="batch-card"
            :class="{ 'is-active': activeBatch?.id === batch.id }"
            @click="handleBatchSelect(batch)"
          >
            <span class="batch-card-title">{{ batch.batchName || batch.batchNo }}</span>
            <span class="batch-card-status-row">
              <el-tag :type="batchStatusType(batch.status)" size="small">{{ batchStatusLabel(batch.status) }}</el-tag>
              <span class="batch-card-progress">{{ batchSurveySummary(batch) }}</span>
            </span>
            <span class="batch-card-metrics">
              <span>
                <b>{{ batch.taskCount || 0 }}</b>
                应调查户数
              </span>
              <span>
                <b>{{ batch.surveyedCount || 0 }}</b>
                已调查
              </span>
            </span>
          </button>
        </el-tooltip>
      </div>
      <div class="batch-footer-actions">
        <el-button :disabled="!activeBatch" :icon="Download" plain type="primary" @click="handleExportResults">导出</el-button>
        <el-button
          v-if="canManage"
          :disabled="!activeBatch || activeBatch.status === 'finished'"
          :icon="CircleCheck"
          plain
          type="warning"
          @click="handleFinishBatch"
        >
          结束
        </el-button>
      </div>
    </section>

    <section class="panel table-page survey-work-panel">
      <el-tabs v-model="surveyPanelTab" class="survey-work-tabs">
        <el-tab-pane label="承包方调查" name="contractor">
          <div class="toolbar">
            <div class="panel-title">{{ taskPanelTitle }}</div>
            <div class="toolbar-actions">
              <el-input v-model="taskKeyword" :disabled="!activeBatch" clearable placeholder="搜索承包方" style="width: 220px" @keyup.enter="loadTasks" />
              <el-select v-model="taskStatus" :disabled="!activeBatch" clearable placeholder="调查状态" style="width: 160px" @change="loadTasks">
                <el-option label="未调查" value="not_started" />
                <el-option label="已调查" value="surveyed" />
                <el-option label="已确认" value="confirmed" />
                <el-option label="已跳过" value="skipped" />
              </el-select>
              <el-button :disabled="!activeBatch" :icon="Search" plain @click="loadTasks">查询</el-button>
              <el-button v-if="canManage" :disabled="!activeBatch || activeBatch?.status === 'finished'" :icon="Plus" type="primary" @click="openCreateContractor">新增</el-button>
            </div>
          </div>

          <el-table v-loading="taskLoading" :data="tasks" border height="100%">
            <el-table-column prop="cbfbm" label="承包方代码" min-width="170" show-overflow-tooltip />
            <el-table-column prop="cbfmc" label="承包方名称" min-width="170" show-overflow-tooltip />
            <el-table-column prop="taskStatus" label="调查状态" width="112">
              <template #default="{ row }">
                <el-tag :type="row.hasChange ? 'warning' : row.taskStatus === 'not_started' ? 'info' : 'success'">
                  {{ taskStatusLabel(row.taskStatus) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="hasChange" label="是否变化" width="92" align="center">
              <template #default="{ row }">{{ row.hasChange ? "是" : "否" }}</template>
            </el-table-column>
            <el-table-column prop="investigatedAt" label="调查时间" min-width="150" show-overflow-tooltip />
            <el-table-column label="操作" fixed="right" width="190" align="center" class-name="survey-action-column">
              <template #default="{ row }">
                <div class="survey-row-actions">
                  <el-button link type="primary" @click="openResult(row)">调查录入</el-button>
                  <el-button
                    v-if="canManage"
                    :disabled="activeBatch?.status === 'finished' || row.taskStatus === 'confirmed'"
                    link
                    type="success"
                    @click="handleConfirmTask(row)"
                  >
                    确认
                  </el-button>
                  <el-button
                    v-if="canManage"
                    :disabled="activeBatch?.status === 'finished' || row.taskStatus === 'confirmed' || row.taskStatus === 'skipped'"
                    link
                    type="warning"
                    @click="handleSkipTask(row)"
                  >
                    跳过
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="发包方调查" name="issuer">
          <div class="toolbar">
            <div class="panel-title">发包方调查</div>
            <div class="toolbar-actions">
              <el-input v-model="issuerKeyword" :disabled="!activeBatch" clearable placeholder="搜索发包方" style="width: 220px" />
              <el-button :disabled="!activeBatch" :icon="Search" plain @click="loadIssuerSurveyRows(true)">查询</el-button>
              <el-button v-if="canManage" :disabled="!activeBatch || activeBatch?.status === 'finished'" :icon="Plus" type="primary" @click="openCreateIssuer">新增</el-button>
            </div>
          </div>

          <el-table v-loading="issuerLoading" :data="filteredIssuerRows" border height="100%">
            <el-table-column prop="code" label="发包方代码" min-width="160" />
            <el-table-column prop="name" label="发包方名称" min-width="180" show-overflow-tooltip />
            <el-table-column prop="responsibleName" label="负责人" min-width="120" />
            <el-table-column prop="surveyStatus" label="调查状态" min-width="120">
              <template #default="{ row }">
                <el-tag :type="surveyStatusTagType(row.surveyStatus)">{{ taskStatusLabel(row.surveyStatus) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="relatedContractorCount" label="关联承包方" min-width="110" />
            <el-table-column prop="surveyDate" label="调查日期" min-width="130" />
            <el-table-column prop="surveyorName" label="调查员" min-width="130" />
            <el-table-column label="操作" fixed="right" min-width="150">
              <template #default="{ row }">
                <el-button link type="primary" @click="openIssuerSurvey(row)">进入调查</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </section>

  <el-dialog v-model="batchDialogVisible" title="新建调查批次" width="640px">
    <el-alert
      title="创建后会把当前正式承包方和家庭成员数据复制为调查前快照，并同步生成可编辑的调查结果。"
      type="info"
      show-icon
      :closable="false"
    />
    <el-form :model="batchForm" label-position="top" class="survey-dialog-form">
      <el-form-item label="批次名称">
        <el-input v-model="batchForm.batchName" placeholder="例如：2026年二轮延包承包方串户调查" />
      </el-form-item>
      <el-form-item label="区域代码">
        <el-tree-select
          v-model="batchForm.regionId"
          clearable
          filterable
          lazy
          check-strictly
          :data="batchRegionTree"
          :props="batchRegionTreeProps"
          :load="loadBatchRegionNode"
          :filter-method="handleBatchRegionFilter"
          node-key="id"
          placeholder="请选择调查区域；为空则按权限范围初始化"
          @change="handleBatchRegionChange"
        />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="batchForm.remark" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="batchDialogVisible = false">取消</el-button>
      <el-button :loading="submittingBatch" type="success" @click="handleCreateBatch">创建并初始化</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="resultVisible" :title="resultDialogTitle" width="92vw" top="3vh" destroy-on-close>
    <!-- 操作工具栏 -->
    <div v-if="!isCreatingContractorResult" class="survey-toolbar">
      <el-button type="danger" plain size="small" @click="handleOpDeregister">注销承包方</el-button>
      <el-button plain size="small" @click="handleOpSplitHousehold">分户</el-button>
      <el-button plain size="small" @click="handleOpMergeHousehold">合户</el-button>
      <span v-if="!canManage || isResultLocked" class="toolbar-lock-hint">（当前为只读模式）</span>
    </div>

    <el-alert
      v-if="pendingOperations.length"
      type="warning"
      :closable="false"
      show-icon
      class="pending-operation-alert"
      :title="`当前有 ${pendingOperations.length} 项操作尚未保存，请点击“保存调查结果”统一提交。`"
    />
    <div v-if="pendingOperations.length" class="pending-operation-list">
      <div
        v-for="(operation, index) in pendingOperations"
        :key="`${operation.type}-${index}`"
        class="pending-operation-item"
      >
        <span class="pending-operation-text">{{ pendingOperationLabelPreview(operation) }}</span>
        <el-button
          v-if="canUndoPendingOperation(operation)"
          link
          type="danger"
          size="small"
          @click="handleUndoPendingOperationPreview(index)"
        >
          撤销
        </el-button>
      </div>
    </div>

    <!-- 4 个信息 Tab -->
    <el-tabs v-model="activeTab">
      <el-tab-pane :label="`承包方及其家庭成员（${resultForm.familyMembers.length}人）`" name="contractor">
        <ContractorMemberPanel
          ref="contractorMemberPanel"
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
          :result="resultForm"
          :changed-fields="computedChangedFields"
          :can-generate-code="resultForm.resultStatus === 'added'"
          @generate-code="generateResultContractorCode"
        />
      </el-tab-pane>

      <el-tab-pane label="地块信息" name="parcels" :disabled="isCreatingContractorResult">
        <ParcelInfoPanel
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
          :parcels="parcels"
          :parcels-loading="parcelsLoading"
          :can-manage="canManage"
          :is-result-locked="isResultLocked"
          :saved-swap-records="savedSwapRecords"
          :saved-split-records="savedSplitRecords"
          :can-rollback-saved-parcel-change="canRollbackSavedParcelChange"
          :rollback-change-loading-id="rollbackingSavedChangeId"
          @swap-parcels="handleOpSwapParcels"
          @add-parcel="handlePendingOperation"
          @split-parcel="handlePendingOperation"
          @remove-parcel="handleOpRemoveParcel"
          @rollback-saved-swap="handleRollbackSavedSwap"
          @rollback-saved-split="handleRollbackSavedSplit"
        />
      </el-tab-pane>

      <el-tab-pane label="承包地块示意图" name="plotSketchMap" :disabled="isCreatingContractorResult">
        <PlotSketchMapPanel
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
          :refresh-key="plotSketchRefreshKey"
        />
      </el-tab-pane>

      <el-tab-pane label="合同信息" name="contract" :disabled="isCreatingContractorResult">
        <ContractInfoPanel
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 辅助功能面板 -->
    <el-collapse v-if="!isCreatingContractorResult" class="survey-aux-panel">
      <el-collapse-item title="调查附件 & 转业务申请" name="aux">
        <!-- 附件上传 -->
        <div v-if="canManage && !isResultLocked" class="phase2-upload">
          <el-select v-model="attachmentCategory" style="width: 160px" size="small">
            <el-option label="身份证" value="id_card" />
            <el-option label="户口簿" value="household_register" />
            <el-option label="死亡证明" value="death_certificate" />
            <el-option label="婚嫁证明" value="marriage_certificate" />
            <el-option label="进城落户证明" value="urban_settlement" />
            <el-option label="政策依据" value="policy_basis" />
            <el-option label="授权委托书" value="authorization" />
            <el-option label="合同扫描件" value="contract" />
          </el-select>
          <el-input v-model="attachmentDescription" placeholder="附件说明" style="width: 200px" size="small" />
          <input type="file" @change="handleAttachmentFileChange" />
          <el-button type="success" size="small" plain @click="handleUploadAttachment">上传</el-button>
        </div>
        <el-table v-loading="phase2Loading" :data="phase2.attachments" border size="small">
          <el-table-column prop="category" label="类型" width="120" />
          <el-table-column prop="originalName" label="文件名" min-width="200" />
          <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
          <el-table-column label="操作" width="130">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="handleDownloadAttachment(row)">下载</el-button>
              <el-button v-if="canManage && !isResultLocked" link type="danger" size="small" @click="handleDeleteAttachment(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-divider />

        <!-- 转业务申请 -->
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="已生成申请">{{ resultForm.generatedRequestNo || "-" }}</el-descriptions-item>
          <el-descriptions-item label="建议业务类型">{{ inferRequestType(resultForm) }}</el-descriptions-item>
        </el-descriptions>
        <el-form v-if="canManage && !resultForm.generatedRequestId" :model="requestForm" class="compact-form" label-position="top" style="margin-top:8px">
          <div class="form-grid">
            <el-form-item label="业务类型">
              <el-select v-model="requestForm.requestType" size="small">
                <el-option label="变更登记" value="变更登记" />
                <el-option label="注销登记" value="注销登记" />
                <el-option label="首次登记" value="首次登记" />
              </el-select>
            </el-form-item>
            <el-form-item label="申请标题"><el-input v-model="requestForm.requestTitle" size="small" /></el-form-item>
            <el-form-item class="form-span-2" label="申请原因"><el-input v-model="requestForm.reason" type="textarea" :rows="2" size="small" /></el-form-item>
          </div>
          <el-button type="success" size="small" @click="handleGenerateRequest">生成业务申请</el-button>
        </el-form>
      </el-collapse-item>
    </el-collapse>

    <template #footer>
      <el-button @click="closeResultDialog">取消</el-button>
      <el-button
        v-if="canManage && !isResultLocked"
        :loading="savingResult || creatingContractor"
        type="success"
        @click="handleSaveResult"
      >
        {{ isCreatingContractorResult ? "新增并保存" : "保存调查结果" }}
      </el-button>
      <el-button
        v-if="canManage && !isCreatingContractorResult && !isResultLocked && resultForm.surveyStatus !== 'not_surveyed'"
        :loading="confirmingResult"
        type="primary"
        @click="handleConfirmCurrent"
      >
        确认调查结果
      </el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="issuerSurveyVisible" :title="issuerSurveyDialogTitle" width="760px">
    <el-form ref="issuerSurveyFormRef" :model="issuerSurveyForm" :rules="issuerSurveyRules" label-position="top" status-icon class="survey-dialog-form">
      <div class="form-grid-3">
        <el-form-item label="发包方编码" prop="code">
          <el-input :model-value="issuerSurveyForm.code" maxlength="14" readonly @input="handleIssuerCodeInput">
            <template v-if="isCreatingIssuerSurvey" #append>
              <el-button @click="generateIssuerCode">生成</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="发包方名称" prop="name">
          <el-input v-model="issuerSurveyForm.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="负责人姓名" prop="responsibleName">
          <el-input v-model="issuerSurveyForm.responsibleName" maxlength="50" />
        </el-form-item>
        <el-form-item label="负责人证件类型" prop="responsibleIdType">
          <el-select v-model="issuerSurveyForm.responsibleIdType">
            <el-option label="居民身份证" value="1" />
            <el-option label="户口簿" value="2" />
            <el-option label="军官证" value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人证件号码" prop="responsibleIdNo">
          <el-input v-model="issuerSurveyForm.responsibleIdNo" maxlength="30" />
        </el-form-item>
        <el-form-item label="联系电话" prop="phone">
          <el-input v-model="issuerSurveyForm.phone" maxlength="15" />
        </el-form-item>
      </div>
      <el-form-item label="发包方地址" prop="address">
        <el-input v-model="issuerSurveyForm.address" maxlength="100" />
      </el-form-item>
      <div class="form-grid-3">
        <el-form-item label="邮政编码" prop="postcode">
          <el-input v-model="issuerSurveyForm.postcode" maxlength="6" />
        </el-form-item>
        <el-form-item label="调查员">
          <el-input v-model="issuerSurveyForm.surveyorName" maxlength="254" />
        </el-form-item>
        <el-form-item label="调查日期">
          <el-date-picker v-model="issuerSurveyForm.surveyDate" value-format="YYYY-MM-DD" type="date" style="width: 100%" />
        </el-form-item>
      </div>
      <el-form-item label="调查记事">
        <el-input v-model="issuerSurveyForm.surveyNote" type="textarea" :rows="2" maxlength="254" show-word-limit />
      </el-form-item>
      <el-form-item label="变化原因">
        <el-input v-model="issuerSurveyForm.changeReason" type="textarea" :rows="2" maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="closeIssuerSurveyDialog">取消</el-button>
      <el-button
        v-if="canManage && activeBatch?.status !== 'finished' && issuerSurveyForm.surveyStatus !== 'confirmed'"
        :loading="savingIssuerSurvey || creatingIssuer"
        type="primary"
        @click="handleSaveIssuerSurvey"
      >
        {{ isCreatingIssuerSurvey ? "新增并保存" : "保存发包方调查" }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 操作对话框 -->
  <DeregisterDialog ref="deregisterDialog" @done="handlePendingOperation" />
  <SwapParcelsDialog ref="swapParcelsDialog" @done="handlePendingOperation" />
  <SplitHouseholdDialog ref="splitHouseholdDialog" @done="handlePendingOperation" />
  <MergeHouseholdDialog ref="mergeHouseholdDialog" @done="handlePendingOperation" />
  <RemoveParcelDialog ref="removeParcelDialog" @done="handlePendingOperation" />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { CircleCheck, Download, Plus, Search } from "@element-plus/icons-vue";

import ContractorMemberPanel from "../components/survey/ContractorMemberPanel.vue";
import ParcelInfoPanel from "../components/survey/ParcelInfoPanel.vue";
import PlotSketchMapPanel from "../components/survey/PlotSketchMapPanel.vue";
import ContractInfoPanel from "../components/survey/ContractInfoPanel.vue";
import DeregisterDialog from "../components/survey/DeregisterDialog.vue";
import SwapParcelsDialog from "../components/survey/SwapParcelsDialog.vue";
import SplitHouseholdDialog from "../components/survey/SplitHouseholdDialog.vue";
import MergeHouseholdDialog from "../components/survey/MergeHouseholdDialog.vue";
import RemoveParcelDialog from "../components/survey/RemoveParcelDialog.vue";

import {
  confirmSurveyResult,
  createSurveyAuthorization,
  createSurveyBatch,
  createSurveyContractor,
  createSurveyIssuer,
  createSurveyRestructure,
  createSurveyTag,
  deleteSurveyAttachment,
  deleteSurveyRestructure,
  disableSurveyTag,
  downloadSurveyAttachment,
  downloadSurveyAuthorizationFile,
  downloadSurveyAuthorizationTemplate,
  exportSurveyResults,
  fetchSurveyBatches,
  fetchSurveyChanges,
  fetchSurveyDiffs,
  fetchSurveyIssuer,
  fetchSurveyIssuers,
  fetchSurveyParcels,
  fetchSurveyPhase2,
  fetchSurveyResult,
  fetchSurveyTasks,
  finishSurveyBatch,
  generateSurveyRequest,
  refreshSurveyTags,
  revokeSurveyAuthorization,
  skipSurveyTask,
  updateSurveyResult,
  updateSurveyIssuer,
  uploadSurveyAttachment,
  uploadSurveyAuthorizationFile,
} from "../api/survey";
import { fetchRegionChildren, fetchRegionTree, searchRegions } from "../api/region";
import { useAuthStore } from "../stores/auth";
import { useDialogMap } from "../composables/useDialogMap";
import { useDictionary } from "../composables/useDictionary";
import { validateChinaId, validateMobile, validatePostcode } from "../utils/validators";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));
const { labelOf: genderLabel } = useDictionary("nyt2539_c17_gender");
const { labelOf: yesNoLabel } = useDictionary("nyt2539_c19_yes_no");
const { labelOf: relationDictionaryLabel } = useDictionary("nyt2539_c20_relation_to_head");
const batchLoading = ref(false);
const taskLoading = ref(false);
const diffLoading = ref(false);
const submittingBatch = ref(false);
const savingResult = ref(false);
const confirmingResult = ref(false);
const batches = ref([]);
const tasks = ref([]);
const issuerRows = ref([]);
const diffRows = ref([]);
const savedSwapChanges = ref([]);
const savedSplitChanges = ref([]);
const phase2Loading = ref(false);
const issuerLoading = ref(false);
const savedParcelChangeLoading = ref(false);
const phase2 = reactive({ tags: [], restructures: [], authorizations: [], attachments: [] });
const activeBatch = ref(null);
const activeTask = ref(null);
const activeRegionId = ref(undefined);
const activeRegionCode = ref("");
const activeRegionLabel = ref("");
const batchKeyword = ref("");
const batchSurveyStatus = ref("");
const taskKeyword = ref("");
const taskStatus = ref("");
const issuerKeyword = ref("");
const batchDialogVisible = ref(false);
const issuerSurveyVisible = ref(false);
const resultVisible = ref(false);
const isCreatingContractorResult = ref(false);
const isCreatingIssuerSurvey = ref(false);
const surveyPanelTab = ref("contractor");
const activeTab = ref("contractor");
const plotSketchRefreshKey = ref(0);
const regionTree = ref([]);
const regionTreeProps = { label: "fullName", children: "children" };
const batchRegionTree = ref([]);
const batchRegionTreeProps = { label: "fullName", children: "children", isLeaf: "leaf" };
const rememberedBatchRegions = new Map();
let batchRegionSearchTimer = null;
const batchForm = reactive({ batchName: "", regionId: undefined, regionCode: "", regionName: "", remark: "" });
const creatingContractor = ref(false);
const creatingIssuer = ref(false);
const savingIssuerSurvey = ref(false);
const resultForm = reactive(createEmptyResult());
const issuerSurveyForm = reactive(createEmptyIssuerSurvey());
const activeIssuer = ref(null);
const tagForm = reactive({ tagCode: "whole_family_urbanized", reason: "", policyBasis: "" });
const restructureForm = reactive(createEmptyRestructure());
const authorizationForm = reactive(createEmptyAuthorization());
const requestForm = reactive({ requestType: "变更登记", requestTitle: "", reason: "", note: "" });
const attachmentCategory = ref("id_card");
const attachmentDescription = ref("");
const selectedAttachmentFile = ref(null);
const authorizationFileInput = ref(null);
const authorizationUploadTarget = ref(null);
const contractorMemberPanel = ref(null);
const issuerSurveyFormRef = ref(null);
const deregisterDialog = ref(null);
const swapParcelsDialog = ref(null);
const splitHouseholdDialog = ref(null);
const mergeHouseholdDialog = ref(null);
const removeParcelDialog = ref(null);
const pendingOperations = ref([]);
const rollbackingSavedChangeId = ref(null);
const isResultLocked = computed(() => activeBatch.value?.status === "finished" || (!isCreatingContractorResult.value && resultForm.surveyStatus === "confirmed"));
const hasPendingOperations = computed(() => pendingOperations.value.length > 0);
const canRollbackSavedParcelChange = computed(() => canManage.value && !isResultLocked.value && !hasPendingOperations.value);

const filteredIssuerRows = computed(() => {
  const keyword = issuerKeyword.value.trim().toLowerCase();
  if (!keyword) {
    return issuerRows.value;
  }
  return issuerRows.value.filter((row) =>
    [row.code, row.name, row.responsibleName, row.surveyorName]
      .some((value) => String(value || "").toLowerCase().includes(keyword)),
  );
});

const filteredBatches = computed(() => {
  if (!batchSurveyStatus.value) {
    return batches.value;
  }
  return batches.value.filter((batch) => batchSurveyStatusValue(batch) === batchSurveyStatus.value);
});

const savedSwapRecords = computed(() =>
  savedSwapChanges.value.map((item) => {
    const beforeSummary = item.beforeSummary || {};
    const afterSummary = item.afterSummary || {};
    const swappedOut = Array.isArray(beforeSummary.swapped_out) ? beforeSummary.swapped_out.filter(Boolean) : [];
    const swappedIn = Array.isArray(afterSummary.swapped_in) ? afterSummary.swapped_in.filter(Boolean) : [];
    return {
      ...item,
      swappedOut,
      swappedIn,
      swappedOutText: swappedOut.length ? swappedOut.join("、") : "-",
      swappedInText: swappedIn.length ? swappedIn.join("、") : "-",
      counterpartyLabel: afterSummary.counterparty || "-",
    };
  }),
);

const savedSplitRecords = computed(() =>
  savedSplitChanges.value.map((item) => {
    const beforeSummary = item.beforeSummary || {};
    const afterSummary = item.afterSummary || {};
    const generatedParcels = Array.isArray(afterSummary.generated_parcels)
      ? afterSummary.generated_parcels.filter((parcel) => parcel?.dkbm)
      : (afterSummary.new_dkbm ? [{ dkbm: afterSummary.new_dkbm, area: afterSummary.new_area }] : []);
    const generatedDkbms = generatedParcels.map((parcel) => String(parcel.dkbm || "").trim()).filter(Boolean);
    return {
      ...item,
      originalDkbm: String(beforeSummary.dkbm || afterSummary.original_dkbm || "").trim(),
      sourceResultStatus: beforeSummary.source_result_status || "normal",
      sourceChangeType: beforeSummary.source_change_type || "none",
      sourceChangeReason: beforeSummary.source_change_reason || "",
      sourceIsChanged: Boolean(beforeSummary.source_is_changed),
      generatedParcels,
      generatedDkbms,
      generatedText: generatedDkbms.length ? generatedDkbms.join("、") : "-",
    };
  }),
);

const resultDialogTitle = computed(() => {
  const name = resultForm.name ? ` - ${resultForm.name}` : "";
  return `${isCreatingContractorResult.value ? "新增承包方调查录入" : "承包方调查录入"}${name}`;
});

const issuerSurveyDialogTitle = computed(() => {
  const name = issuerSurveyForm.name ? ` - ${issuerSurveyForm.name}` : "";
  return `${isCreatingIssuerSurvey.value ? "新增发包方调查录入" : "发包方调查录入"}${name}`;
});

const validateIssuerCodeField = (_rule, value, callback) => {
  const text = String(value || "").trim();
  if (!text) {
    callback(new Error("请输入发包方编码"));
    return;
  }
  if (!/^\d+$/.test(text)) {
    callback(new Error("发包方编码只能输入数字"));
    return;
  }
  if (text.length !== 14) {
    callback(new Error("发包方编码必须为14位"));
    return;
  }
  callback();
};

const validateIssuerIdNoField = (_rule, value, callback) => {
  const text = String(value || "").trim();
  if (!text) {
    callback(new Error("请输入负责人证件号码"));
    return;
  }
  if (issuerSurveyForm.responsibleIdType === "1" && !validateChinaId(text)) {
    callback(new Error("请输入正确的居民身份证号码"));
    return;
  }
  callback();
};

const validateIssuerPhoneField = (_rule, value, callback) => {
  const text = String(value || "").trim();
  if (text && !validateMobile(text)) {
    callback(new Error("请输入正确的联系电话"));
    return;
  }
  callback();
};

const validateIssuerPostcodeField = (_rule, value, callback) => {
  const text = String(value || "").trim();
  if (text && !validatePostcode(text)) {
    callback(new Error("邮政编码必须为6位数字"));
    return;
  }
  callback();
};

const issuerSurveyRules = {
  code: [{ validator: validateIssuerCodeField, trigger: "blur" }],
  name: [{ required: true, message: "请输入发包方名称", trigger: "blur" }],
  responsibleName: [{ required: true, message: "请输入负责人姓名", trigger: "blur" }],
  responsibleIdType: [{ required: true, message: "请选择负责人证件类型", trigger: "change" }],
  responsibleIdNo: [{ validator: validateIssuerIdNoField, trigger: "blur" }],
  phone: [{ validator: validateIssuerPhoneField, trigger: "blur" }],
  address: [{ required: true, message: "请输入发包方地址", trigger: "blur" }],
  postcode: [{ validator: validateIssuerPostcodeField, trigger: "blur" }],
};

// 计算变化字段列表（供 ContractorInfoPanel 高亮用）
const computedChangedFields = computed(() => {
  const fields = [];
  const base = resultForm.baseContractor;
  if (!base) return fields;
  const keyMap = [
    { f: "code", b: "code" }, { f: "name", b: "name" }, { f: "typeCode", b: "typeCode" },
    { f: "idType", b: "idType" }, { f: "idNo", b: "idNo" }, { f: "mobile", b: "mobile" },
    { f: "address", b: "address" }, { f: "postcode", b: "postcode" },
    { f: "memberCount", b: "memberCount" }, { f: "surveyorName", b: "surveyorName" },
    { f: "surveyDate", b: "surveyDate" }, { f: "surveyNote", b: "surveyNote" },
    { f: "publicNoticeNote", b: "publicNoticeNote" }, { f: "publicNoticeRecorder", b: "publicNoticeRecorder" },
    { f: "publicNoticeReviewDate", b: "publicNoticeReviewDate" }, { f: "publicNoticeReviewer", b: "publicNoticeReviewer" },
    { f: "groupRegionCode", b: "groupRegionCode" }, { f: "groupRegionName", b: "groupRegionName" },
  ];
  for (const { f, b } of keyMap) {
    if (String(resultForm[f] ?? "") !== String(base[b] ?? "")) {
      fields.push(f);
    }
  }
  return fields;
});

// ── 操作入口（Phase 3-8 实现） ──────────────────────

function handleOpDeregister() {
  const validCount = (resultForm.familyMembers || []).filter((m) => !m._deleted).length;
  deregisterDialog.value.open(
    activeBatch.value.id,
    activeTask.value.contractorUid,
    resultForm.name,
    resultForm.code,
    validCount,
  );
}
function handleOpSplitHousehold() {
  const validMembers = (resultForm.familyMembers || []).filter((m) => !m._deleted);
  splitHouseholdDialog.value.open(
    activeBatch.value.id,
    activeTask.value.contractorUid,
    validMembers,
    parcels.value,
  );
}
function handleOpMergeHousehold() {
  const validMembers = (resultForm.familyMembers || []).filter((m) => !m._deleted);
  mergeHouseholdDialog.value.open(
    activeBatch.value.id,
    activeTask.value.contractorUid,
    resultForm.name,
    resultForm.code,
    validMembers,
    parcels.value,
    tasks.value,
  );
}
function handleOpSwapParcels() {
  swapParcelsDialog.value.open(
    activeBatch.value.id,
    activeTask.value.contractorUid,
    tasks.value,
    parcels.value,
    resultForm,
  );
}
function handleOpRemoveParcel() {
  removeParcelDialog.value.open(
    activeBatch.value.id,
    activeTask.value.contractorUid,
    parcels.value,
  );
}

function cloneParcel(parcel) {
  return JSON.parse(JSON.stringify(parcel || {}));
}

function markParcelRemoved(dkbm, changeType, reason) {
  const index = parcels.value.findIndex((item) => item.dkbm === dkbm);
  if (index === -1) return;
  parcels.value[index] = {
    ...parcels.value[index],
    resultStatus: "removed",
    isChanged: true,
    changeType,
    changeReason: reason,
    _pending: true,
  };
}

function applyPendingParcelPreview(operation) {
  const payload = operation.payload || {};
  if (operation.type === "add_parcel") {
    parcels.value = [
      ...parcels.value,
      {
        ...payload,
        cbfbm: resultForm.code,
        cbfmc: resultForm.name,
        htmj: payload.htmj ?? payload.scmj,
        resultStatus: "added",
        isChanged: true,
        changeType: "add_parcel",
        changeReason: payload.reason,
        _pending: true,
      },
    ];
    return;
  }
  if (operation.type === "remove_parcel") {
    markParcelRemoved(payload.dkbm, "remove_parcel", payload.reason);
    return;
  }
  if (operation.type === "split_parcel") {
    const index = parcels.value.findIndex((item) => item.dkbm === payload.dkbm);
    if (index === -1) return;
    const source = cloneParcel(parcels.value[index]);
    const updatedSource = {
      ...source,
      resultStatus: "split_source",
      isChanged: true,
      changeType: "split_parcel",
      changeReason: payload.reason,
      _pending: true,
    };
    parcels.value[index] = updatedSource;
    const generatedParcels = Array.isArray(payload.generatedParcels) && payload.generatedParcels.length
      ? payload.generatedParcels
      : [{
        dkbm: payload.newDkbm,
        dkmc: payload.newDkmc,
        scmj: payload.newScmj || payload.estimatedNewScmj || null,
        htmj: payload.newScmj || payload.estimatedNewScmj || null,
        geometry: payload.newGeometry || null,
      }];
    parcels.value = [
      ...parcels.value,
      ...generatedParcels.map((item) => ({
        ...source,
        dkbm: item.dkbm,
        dkmc: item.dkmc,
        scmj: item.scmj ?? null,
        htmj: item.htmj ?? item.scmj ?? null,
        geometry: item.geometry || null,
        resultStatus: "split_generated",
        isChanged: true,
        changeType: "split_parcel",
        changeReason: payload.reason,
        _pending: true,
      })),
    ];
    return;
  }
  if (operation.type === "swap_parcels") {
    for (const dkbm of payload.sourceDkbms || []) {
      markParcelRemoved(dkbm, "swap_parcels", payload.reason);
    }
    const incoming = (payload.targetParcels || []).map((item) => ({
      ...cloneParcel(item),
      cbfbm: resultForm.code,
      cbfmc: resultForm.name,
      isChanged: true,
      changeType: "swap_parcels",
      changeReason: payload.reason,
      _pending: true,
    }));
    if (incoming.length) {
      const existing = new Set(parcels.value.map((item) => item.dkbm));
      parcels.value = [
        ...parcels.value,
        ...incoming.filter((item) => !existing.has(item.dkbm)),
      ];
    }
    return;
  }
  if (operation.type === "rollback_swap_parcels") {
    for (const dkbm of payload.returnDkbms || []) {
      markParcelRemoved(dkbm, "rollback_swap_parcels", payload.reason);
    }
    for (const parcel of payload.restoreParcels || []) {
      const restored = {
        ...cloneParcel(parcel),
        cbfbm: resultForm.code,
        cbfmc: resultForm.name,
        resultStatus: "normal",
        isChanged: true,
        changeType: "rollback_swap_parcels",
        changeReason: payload.reason,
        _pending: true,
      };
      const index = parcels.value.findIndex((item) => item.dkbm === restored.dkbm && item.resultStatus === "removed");
      if (index >= 0) {
        parcels.value[index] = restored;
      } else if (!parcels.value.some((item) => item.dkbm === restored.dkbm && !["removed", "split_source"].includes(item.resultStatus))) {
        parcels.value = [...parcels.value, restored];
      }
    }
    return;
  }
  if (operation.type === "rollback_split_parcel") {
    const sourceIndex = parcels.value.findIndex((item) => item.dkbm === payload.sourceDkbm);
    if (sourceIndex >= 0) {
      const source = cloneParcel(parcels.value[sourceIndex]);
      parcels.value[sourceIndex] = {
        ...source,
        resultStatus: payload.sourceResultStatus || "normal",
        isChanged: Boolean(payload.sourceIsChanged),
        changeType: payload.sourceChangeType || "none",
        changeReason: payload.sourceChangeReason || "",
        _pending: true,
      };
    }
    const generatedSet = new Set(payload.generatedDkbms || []);
    parcels.value = parcels.value.filter((item) => !generatedSet.has(item.dkbm));
  }
}

function handlePendingOperation(operation) {
  if (!operation?.type) return;
  pendingOperations.value.push(operation);
  applyPendingParcelPreview(operation);
  if (operation.type === "deregister") {
    resultForm.resultStatus = "cancelled";
    resultForm.changeType = "deregister";
    resultForm.changeReason = operation.payload?.reason || resultForm.changeReason;
  }
  if (operation.type === "merge_household") {
    resultForm.resultStatus = "cancelled";
    resultForm.changeType = "merge_household";
    resultForm.changeReason = operation.payload?.reason || resultForm.changeReason;
  }
}

const parcelOperationTypes = new Set(["add_parcel", "remove_parcel", "split_parcel", "rollback_split_parcel", "swap_parcels", "rollback_swap_parcels"]);

function canUndoPendingOperation(operation) {
  return parcelOperationTypes.has(operation?.type);
}

function pendingOperationLabelPreview(operation) {
  const payload = operation?.payload || {};
  if (operation?.type === "swap_parcels") {
    const sourceCount = (payload.sourceDkbms || []).length;
    const targetCount = (payload.targetDkbms || []).length;
    return `地块互换：本方 ${sourceCount} 块，对方 ${targetCount} 块`;
  }
  if (operation?.type === "add_parcel") {
    return `新增地块：${payload.dkbm || payload.dkmc || "未命名地块"}`;
  }
  if (operation?.type === "remove_parcel") {
    return `移除地块：${payload.dkbm || "-"}`;
  }
  if (operation?.type === "split_parcel") {
    const generatedCount = Array.isArray(payload.generatedParcels) && payload.generatedParcels.length
      ? payload.generatedParcels.length
      : 1;
    return `切割地块：${payload.dkbm || "-"} -> ${generatedCount} 块`;
  }
  if (operation?.type === "rollback_split_parcel") {
    return `撤回切割：${payload.sourceDkbm || "-"}`;
  }
  return operation?.type || "未命名操作";
}

async function reloadParcelPreviewFromPendingOperations() {
  await loadSurveyParcels();
  for (const operation of pendingOperations.value) {
    applyPendingParcelPreview(operation);
  }
}

async function handleUndoPendingOperationPreview(index) {
  const operation = pendingOperations.value[index];
  if (!canUndoPendingOperation(operation)) {
    return;
  }
  pendingOperations.value.splice(index, 1);
  await reloadParcelPreviewFromPendingOperations();
  ElMessage.success("待保存地块操作已撤销");
}

function pendingOperationLabel(operation) {
  const payload = operation?.payload || {};
  if (operation?.type === "swap_parcels") {
    const sourceCount = (payload.sourceDkbms || []).length;
    const targetCount = (payload.targetDkbms || []).length;
    return `地块互换：本方 ${sourceCount} 块，对方 ${targetCount} 块`;
  }
  if (operation?.type === "rollback_swap_parcels") {
    const returnCount = (payload.returnDkbms || []).length;
    const restoreCount = (payload.restoreDkbms || []).length;
    return `撤回互换：退回 ${returnCount} 块，恢复 ${restoreCount} 块`;
  }
  if (operation?.type === "add_parcel") {
    return `新增地块：${payload.dkbm || payload.dkmc || "未命名地块"}`;
  }
  if (operation?.type === "remove_parcel") {
    return `移除地块：${payload.dkbm || "-"}`;
  }
  if (operation?.type === "split_parcel") {
    const generatedCount = Array.isArray(payload.generatedParcels) && payload.generatedParcels.length
      ? payload.generatedParcels.length
      : 1;
    return `切分地块：${payload.dkbm || "-"} -> ${generatedCount} 块`;
  }
  if (operation?.type === "rollback_split_parcel") {
    return `撤回切割：${payload.sourceDkbm || "-"}`;
  }
  return operation?.type || "未命名操作";
}

async function handleUndoPendingOperation(index) {
  const operation = pendingOperations.value[index];
  if (!canUndoPendingOperation(operation)) {
    return;
  }
  pendingOperations.value.splice(index, 1);
  await reloadParcelPreviewFromPendingOperations();
  if (["rollback_swap_parcels", "rollback_split_parcel"].includes(operation?.type)) {
    await loadSavedParcelChanges();
  }
  ElMessage.success("待保存地块操作已撤销");
}

const taskPanelTitle = computed(() => {
  if (!activeBatch.value) {
    return "调查任务";
  }
  return activeBatch.value.batchName || "调查任务";
});

// ---- 地块信息 tab ----
const parcelTabMapRoot = ref(null);
const parcels = ref([]);
const selectedParcel = ref(null);
const parcelsLoading = ref(false);
const flashDkbm = ref(null);

let flashTimer = null;
function triggerFlash(dkbm) {
  flashDkbm.value = dkbm;
  if (flashTimer) clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    flashDkbm.value = null;
  }, 2800);
}

const {
  mapReady,
  activeBasemap: parcelBasemap,
  basemapOptions,
  selectedParcelDkbm,
  initMap,
  switchBasemap: switchParcelBasemap,
  loadParcels,
  fitToParcels,
  focusParcel: mapFocusParcel,
  clearSelection: mapClearSelection,
  updateMapSize,
  destroyMap,
} = useDialogMap(parcelTabMapRoot);

async function loadSurveyParcels() {
  if (!activeBatch.value || !activeTask.value) {
    parcels.value = [];
    return;
  }
  parcelsLoading.value = true;
  try {
    const { data } = await fetchSurveyParcels(activeBatch.value.id, activeTask.value.contractorUid);
    parcels.value = data.data || [];
  } catch {
    parcels.value = [];
  } finally {
    parcelsLoading.value = false;
  }
}

function selectParcel(parcel) {
  selectedParcel.value = parcel;
  triggerFlash(parcel.dkbm);
  mapFocusParcel(parcel.dkbm);
}

async function initParcelTab() {
  await loadSurveyParcels();
  if (!mapReady.value) {
    await initMap();
  }
  if (parcels.value.length) {
    loadParcels(parcels.value);
    fitToParcels();
  }
}

async function handleParcelTabEnter() {
  if (!mapReady.value) {
    await initMap();
  }
  setTimeout(() => {
    if (parcelTabMapRoot.value) {
      updateMapSize();
      if (parcels.value.length && mapReady.value) {
        loadParcels(parcels.value);
        fitToParcels();
      }
    }
  }, 200);
}

function parcelFieldLabel(key) {
  const labels = {
    dkbm: "地块编码", dkmc: "地块名称", scmj: "实测面积（亩）", htmj: "合同面积（亩）",
    yhtmj: "原合同面积", htmjm: "合同面积（亩）", yhtmjm: "原合同面积（亩）",
    syqxz: "所有权性质", dklb: "地块类别", dldj: "地类等级", tdyt: "土地用途",
    tdlylx: "土地来源类型", sfjbnt: "是否基本农田", dkdz: "地块地址",
    dkxz: "地块形状", dknz: "地块内至", dkbz: "地块备注", dkbzxx: "地块备注信息",
    fbfbm: "发包方编码", fbfmc: "发包方名称", cbjyqqdfs: "取得方式",
    cbhtbm: "承包合同编码", cbjyqzbm: "经营权证编码", lzhtbm: "流转合同编码",
    sfqqqg: "是否确权确股", cbfbm: "承包方编码", cbfmc: "承包方名称",
    cbflx: "承包方类型",
  };
  return labels[key] || key;
}

function parcelFieldValue(parcel, key) {
  const val = parcel[key];
  if (val == null || val === "") return "-";
  if (key === "sfjbnt") return val === "1" ? "是" : val === "0" ? "否" : val;
  if (key === "sfqqqg") return val === "1" ? "是" : val === "0" ? "否" : val;
  if (key === "cbflx") return { "1": "农户", "2": "个人", "3": "单位" }[val] || val;
  return val;
}

const detailFields = [
  "dkbm", "dkmc", "cbfmc", "fbfmc", "scmj", "htmj", "syqxz", "dklb",
  "dldj", "tdyt", "sfjbnt", "tdlylx", "cbjyqqdfs", "cbhtbm", "cbjyqzbm",
  "lzhtbm", "sfqqqg", "dkdz", "dkxz", "dknz", "dkbz",
];

function createEmptyResult() {
  return {
    contractorUid: "",
    code: "",
    typeCode: "1",
    name: "",
    idType: "1",
    idNo: "",
    address: "",
    postcode: "000000",
    mobile: "",
    memberCount: 0,
    groupRegionCode: "",
    groupRegionName: "",
    surveyDate: "",
    surveyorName: "",
    surveyNote: "",
    publicNoticeNote: "",
    publicNoticeRecorder: "",
    publicNoticeReviewDate: "",
    publicNoticeReviewer: "",
    surveyStatus: "surveyed",
    resultStatus: "normal",
    changeType: "none",
    changeReason: "",
    policyBasis: "",
    evidenceSummary: "",
    remark: "",
    baseContractor: null,
    issuer: null,
    baseIssuer: null,
    familyMembers: [],
    generatedRequestId: null,
    generatedRequestNo: "",
  };
}

function createEmptyIssuerSurvey() {
  return {
    issuerUid: "",
    code: "",
    name: "",
    responsibleName: "",
    responsibleIdType: "1",
    responsibleIdNo: "",
    phone: "",
    address: "",
    postcode: "000000",
    surveyorName: "",
    surveyDate: "",
    surveyNote: "",
    surveyStatus: "surveyed",
    resultStatus: "normal",
    changeType: "none",
    changeReason: "",
    remark: "",
    baseIssuer: null,
  };
}

function digitsOnly(value) {
  return String(value || "").replace(/\D/g, "");
}

async function buildNextContractorCode(currentCode = "") {
  const batchPrefix = digitsOnly(activeBatch.value?.regionCode || activeRegionCode.value);
  const currentPrefix = digitsOnly(currentCode);
  const prefix = batchPrefix || currentPrefix.slice(0, Math.min(currentPrefix.length, 14));
  if (!prefix) return "";
  if (prefix.length >= 18) return prefix.slice(0, 18);
  const suffixLength = 18 - prefix.length;
  let existingRows = tasks.value;
  if (activeBatch.value) {
    const { data } = await fetchSurveyTasks(activeBatch.value.id, {
      page: 1,
      page_size: 10000,
      ...buildRegionParams(),
    });
    existingRows = data.data.items || [];
  }
  const existingSuffixes = existingRows
    .map((item) => digitsOnly(item.cbfbm))
    .filter((code) => code.length === 18 && code.startsWith(prefix))
    .map((code) => Number(code.slice(prefix.length)))
    .filter(Number.isFinite);
  const next = (existingSuffixes.length ? Math.max(...existingSuffixes) : 0) + 1;
  return `${prefix}${String(next).padStart(suffixLength, "0")}`.slice(0, 18);
}

async function generateResultContractorCode() {
  const code = await buildNextContractorCode(resultForm.code);
  if (!code) {
    ElMessage.warning("请先选择调查批次或输入区域前缀");
    return;
  }
  resultForm.code = code;
}

function handleIssuerCodeInput(value) {
  issuerSurveyForm.code = digitsOnly(value).slice(0, 14);
}

async function buildNextIssuerCode(currentCode = "") {
  const batchCode = digitsOnly(activeBatch.value?.regionCode || activeRegionCode.value);
  if (batchCode.length >= 14) return batchCode.slice(0, 14);
  const currentPrefix = digitsOnly(currentCode);
  const prefix = batchCode || currentPrefix.slice(0, Math.min(currentPrefix.length, 12));
  if (!prefix) return "";
  if (prefix.length >= 14) return prefix.slice(0, 14);
  const suffixLength = 14 - prefix.length;
  let existingRows = issuerRows.value;
  if (activeBatch.value) {
    const { data } = await fetchSurveyIssuers(activeBatch.value.id, {
      page: 1,
      page_size: 10000,
      ...buildRegionParams(),
    });
    existingRows = data.data.items || [];
  }
  const existingSuffixes = existingRows
    .map((item) => digitsOnly(item.code))
    .filter((code) => code.length === 14 && code.startsWith(prefix))
    .map((code) => Number(code.slice(prefix.length)))
    .filter(Number.isFinite);
  const next = (existingSuffixes.length ? Math.max(...existingSuffixes) : 0) + 1;
  return `${prefix}${String(next).padStart(suffixLength, "0")}`.slice(0, 14);
}

async function generateIssuerCode() {
  const code = await buildNextIssuerCode(issuerSurveyForm.code);
  if (!code) {
    ElMessage.warning("请先选择调查批次或输入区域前缀");
    return;
  }
  issuerSurveyForm.code = code;
}

function createEmptyRestructure() {
  return {
    restructureType: "split",
    sourceContractorUid: "",
    sourceCbfbm: "",
    sourceCbfmc: "",
    targetContractorUid: "",
    targetCbfbm: "",
    targetCbfmc: "",
    newCbfbm: "",
    newCbfmc: "",
    status: "draft",
    reason: "",
    policyBasis: "",
    rightsSummary: "",
    contractDisposition: "",
    certificateDisposition: "",
    remark: "",
    members: [],
  };
}

function createEmptyAuthorization() {
  return {
    principalName: "",
    principalIdNo: "",
    agentName: "",
    agentIdNo: "",
    agentPhone: "",
    authorizedMatters: "代为办理二轮延包承包方调查确认、材料签署及相关事项。",
    validFrom: "",
    validTo: "",
    status: "active",
    remark: "",
  };
}

function taskStatusLabel(value) {
  return {
    not_started: "未调查",
    not_surveyed: "未调查",
    in_progress: "调查中",
    surveyed: "已调查",
    changed: "有变化",
    unchanged: "无变化",
    confirmed: "已确认",
    skipped: "已跳过",
  }[value] || value;
}

function surveyStatusTagType(value) {
  return {
    not_started: "info",
    not_surveyed: "info",
    surveyed: "success",
    confirmed: "primary",
    skipped: "warning",
  }[value] || "info";
}

function batchStatusLabel(value) {
  return { active: "进行中", finished: "已结束", draft: "草稿" }[value] || value || "-";
}

function batchStatusType(value) {
  return { active: "success", finished: "info", draft: "warning" }[value] || "info";
}

function batchSurveySummary(batch) {
  const total = Number(batch.taskCount || 0);
  if (!total) {
    return "暂无任务";
  }
  return `${Number(batch.surveyedCount || 0)}/${total} 已调查`;
}

function batchSurveyStatusValue(batch) {
  const total = Number(batch.taskCount || 0);
  const surveyed = Number(batch.surveyedCount || 0);
  const confirmed = Number(batch.confirmedCount || 0);
  const skipped = Number(batch.skippedCount || 0);
  if (!total || surveyed === 0) {
    return "not_started";
  }
  if (confirmed >= total) {
    return "confirmed";
  }
  if (skipped >= total) {
    return "skipped";
  }
  if (surveyed >= total) {
    return "surveyed";
  }
  return "in_progress";
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  return String(value).replace("T", " ").slice(0, 19);
}

const relationToHeadFallback = {
  "01": "户主",
  "02": "配偶",
  "03": "子",
  "04": "女",
  "05": "孙子、孙女或外孙子、外孙女",
  "06": "父母",
  "07": "祖父母或外祖父母",
  "08": "兄弟姐妹",
  "09": "其他",
};

function relationToHeadLabel(value) {
  return relationDictionaryLabel(value, relationToHeadFallback[value] || value || "-");
}

function normalizeCompareValue(value) {
  if (value == null) return "";
  return String(value).trim();
}

function isChangedValue(before, after) {
  return normalizeCompareValue(before) !== normalizeCompareValue(after);
}

function snapshotFieldClass(field) {
  return {
    "snapshot-changed-value": isChangedValue(resultForm.baseContractor?.[field], resultForm[field]),
  };
}

function findSurveyMember(baseMember) {
  if (!baseMember) return null;
  if (baseMember.memberUid) {
    const byUid = resultForm.familyMembers.find((item) => item.memberUid && item.memberUid === baseMember.memberUid);
    if (byUid) return byUid;
  }
  return resultForm.familyMembers.find((item) => item.idNo && item.idNo === baseMember.idNo) || null;
}

function snapshotMemberFieldClass(baseMember, field) {
  const surveyMember = findSurveyMember(baseMember);
  return {
    "snapshot-changed-value": !surveyMember || isChangedValue(baseMember?.[field], surveyMember?.[field]),
  };
}

async function loadBatches() {
  batchLoading.value = true;
  try {
    const { data } = await fetchSurveyBatches({
      page: 1,
      page_size: 50,
      keyword: batchKeyword.value || undefined,
      regionCode: activeRegionCode.value || undefined,
    });
    batches.value = data.data.items;
    const previousBatchId = activeBatch.value?.id;
    activeBatch.value = filteredBatches.value.find((item) => item.id === previousBatchId) || filteredBatches.value[0] || null;
    if (activeBatch.value) {
      await loadTasks();
      if (surveyPanelTab.value === "issuer") {
        await loadIssuerSurveyRows(true);
      }
    } else {
      tasks.value = [];
      issuerRows.value = [];
    }
  } finally {
    batchLoading.value = false;
  }
}

async function reloadBatchesForRegion() {
  activeBatch.value = null;
  tasks.value = [];
  issuerRows.value = [];
  await loadBatches();
}

function buildRegionParams() {
  const regionCode = activeBatch.value?.regionCode || activeRegionCode.value;
  return regionCode ? { regionCode } : {};
}

async function handleActiveRegionChange(value) {
  const selected = flattenRegions(regionTree.value).find((item) => item.id === value);
  activeRegionCode.value = selected?.code || "";
  activeRegionLabel.value = selected?.fullName || "";
  activeRegionId.value = selected?.id;
  await reloadBatchesForRegion();
}

function applyDefaultRegionFilter() {
  if (activeRegionId.value) {
    return;
  }
  const userRegionCode = authStore.user?.regionCode;
  if (!userRegionCode) {
    return;
  }
  const selected = flattenRegions(regionTree.value).find((item) => item.code === userRegionCode);
  if (selected) {
    activeRegionId.value = selected.id;
    activeRegionCode.value = selected.code;
    activeRegionLabel.value = selected.fullName;
  }
}

async function loadTasks() {
  if (!activeBatch.value) {
    tasks.value = [];
    return;
  }
  taskLoading.value = true;
  try {
    const { data } = await fetchSurveyTasks(activeBatch.value.id, {
      page: 1,
      page_size: 100,
      keyword: taskKeyword.value || undefined,
      taskStatus: taskStatus.value || undefined,
      ...buildRegionParams(),
    });
    tasks.value = data.data.items;
    issuerRows.value = [];
  } finally {
    taskLoading.value = false;
  }
}

async function loadIssuerSurveyRows(force = false) {
  if (!activeBatch.value) {
    issuerRows.value = [];
    return;
  }
  if (!force && issuerRows.value.length) {
    return;
  }
  issuerLoading.value = true;
  try {
    const { data } = await fetchSurveyIssuers(activeBatch.value.id, {
      page: 1,
      page_size: 200,
      keyword: issuerKeyword.value || undefined,
      ...buildRegionParams(),
    });
    issuerRows.value = data.data.items;
  } finally {
    issuerLoading.value = false;
  }
}

function handleBatchSelect(row) {
  activeBatch.value = row;
  issuerRows.value = [];
  loadTasks().then(() => {
    if (surveyPanelTab.value === "issuer") {
      loadIssuerSurveyRows(true);
    }
  });
}

function openCreateBatch() {
  const selectedRegion = [...rememberedBatchRegions.values()].find((item) => item.code === activeRegionCode.value);
  Object.assign(batchForm, {
    batchName: selectedRegion ? (selectedRegion.name || "") + "调查批次" : "",
    regionId: selectedRegion?.id,
    regionCode: selectedRegion?.code || "",
    regionName: selectedRegion?.fullName || "",
    remark: "",
  });
  batchDialogVisible.value = true;
}

async function handleCreateBatch() {
  if (!batchForm.batchName.trim()) {
    ElMessage.warning("请输入批次名称");
    return;
  }
  submittingBatch.value = true;
  try {
    await createSurveyBatch({
      ...batchForm,
      batchName: batchForm.batchName.trim(),
      regionId: undefined,
    });
    ElMessage.success("调查批次已创建并初始化");
    batchDialogVisible.value = false;
    activeBatch.value = null;
    await loadBatches();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "创建调查批次失败");
  } finally {
    submittingBatch.value = false;
  }
}

function openCreateContractor() {
  if (!activeBatch.value) {
    return;
  }
  isCreatingContractorResult.value = true;
  activeTask.value = null;
  selectedParcel.value = null;
  parcels.value = [];
  diffRows.value = [];
  savedSwapChanges.value = [];
  savedSplitChanges.value = [];
  savedParcelChangeLoading.value = false;
  pendingOperations.value = [];
  rollbackingSavedChangeId.value = null;
  Object.assign(resultForm, createEmptyResult(), {
    code: activeBatch.value?.regionCode || activeRegionCode.value || "",
    groupRegionCode: activeBatch.value?.regionCode || activeRegionCode.value || "",
    groupRegionName: activeBatch.value?.regionName || activeRegionLabel.value || "",
    resultStatus: "added",
    changeType: "add_contractor",
    isChanged: false,
  });
  resetPhase2Forms();
  activeTab.value = "contractor";
  resultVisible.value = true;
}

function openCreateIssuer() {
  if (!activeBatch.value) {
    return;
  }
  isCreatingIssuerSurvey.value = true;
  activeIssuer.value = null;
  const regionCode = activeBatch.value?.regionCode || activeRegionCode.value || "";
  Object.assign(issuerSurveyForm, createEmptyIssuerSurvey(), {
    code: regionCode.length >= 14 ? regionCode.slice(0, 14) : regionCode,
  });
  issuerSurveyVisible.value = true;
}

async function openIssuerSurvey(row) {
  if (!activeBatch.value) {
    return;
  }
  isCreatingIssuerSurvey.value = false;
  activeIssuer.value = row;
  const { data } = await fetchSurveyIssuer(activeBatch.value.id, row.issuerUid);
  Object.assign(issuerSurveyForm, createEmptyIssuerSurvey(), data.data);
  issuerSurveyVisible.value = true;
}

function closeIssuerSurveyDialog() {
  issuerSurveyVisible.value = false;
  isCreatingIssuerSurvey.value = false;
}

async function handleSaveIssuerSurvey() {
  if (!activeBatch.value || (!activeIssuer.value && !isCreatingIssuerSurvey.value)) {
    return;
  }
  const valid = await issuerSurveyFormRef.value?.validate().catch(() => false);
  if (!valid) {
    return;
  }
  savingIssuerSurvey.value = true;
  creatingIssuer.value = isCreatingIssuerSurvey.value;
  try {
    const { baseIssuer, id, isChanged, ...payload } = issuerSurveyForm;
    let issuerUid = activeIssuer.value?.issuerUid;
    const cleanPayload = {
      ...payload,
      code: payload.code.trim(),
      name: payload.name.trim(),
      responsibleName: payload.responsibleName.trim(),
      responsibleIdNo: payload.responsibleIdNo.trim(),
      phone: payload.phone?.trim() || null,
      address: payload.address.trim(),
      postcode: payload.postcode.trim(),
    };
    if (isCreatingIssuerSurvey.value) {
      const { data } = await createSurveyIssuer(activeBatch.value.id, cleanPayload);
      issuerUid = data.data.issuerUid;
    }
    await updateSurveyIssuer(activeBatch.value.id, issuerUid, cleanPayload);
    ElMessage.success(isCreatingIssuerSurvey.value ? "发包方调查数据已新增" : "发包方调查已保存");
    closeIssuerSurveyDialog();
    await loadIssuerSurveyRows(true);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || (isCreatingIssuerSurvey.value ? "新增发包方失败" : "保存发包方调查失败"));
  } finally {
    savingIssuerSurvey.value = false;
    creatingIssuer.value = false;
  }
}

function flattenRegions(nodes, result = []) {
  for (const item of nodes || []) {
    result.push(item);
    flattenRegions(item.children, result);
  }
  return result;
}

function rememberBatchRegions(nodes) {
  for (const node of nodes || []) {
    rememberedBatchRegions.set(node.id, node);
    rememberBatchRegions(node.children);
  }
}

async function loadBatchRegionNode(node, resolve) {
  if (node.level === 0) {
    resolve(batchRegionTree.value);
    return;
  }
  const { data } = await fetchRegionChildren({ parentId: node.data.id, includeGroups: true });
  rememberBatchRegions(data.data);
  resolve(data.data);
}

function handleBatchRegionFilter(keyword) {
  window.clearTimeout(batchRegionSearchTimer);
  batchRegionSearchTimer = window.setTimeout(async () => {
    if (!keyword) {
      const { data } = await fetchRegionChildren({ includeGroups: true });
      batchRegionTree.value = data.data;
      rememberBatchRegions(batchRegionTree.value);
      return;
    }
    const { data } = await searchRegions({ keyword, includeGroups: true, limit: 100 });
    batchRegionTree.value = data.data;
    rememberBatchRegions(batchRegionTree.value);
  }, 250);
}

function handleBatchRegionChange(value) {
  const selected = rememberedBatchRegions.get(value);
  batchForm.regionCode = selected?.code || "";
  batchForm.regionName = selected?.fullName || "";
  if (selected) {
    batchForm.batchName = (selected.name || "") + "调查批次";
  }
}

async function loadRegionTree() {
  const { data } = await fetchRegionTree();
  regionTree.value = data.data;
  applyDefaultRegionFilter();
  const { data: batchData } = await fetchRegionChildren({ includeGroups: true });
  batchRegionTree.value = batchData.data;
  rememberBatchRegions(batchRegionTree.value);
}

async function loadInitialData() {
  await loadRegionTree();
  await loadBatches();
}

async function handleFinishBatch() {
  if (!activeBatch.value) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定结束调查批次“${activeBatch.value.batchName}”吗？结束后该批次调查成果将不能继续编辑。`,
      "结束调查批次",
      { type: "warning", confirmButtonText: "结束批次", cancelButtonText: "取消" },
    );
    await finishSurveyBatch(activeBatch.value.id);
    ElMessage.success("调查批次已结束");
    activeBatch.value = null;
    await loadBatches();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "结束批次失败");
    }
  }
}

async function handleExportResults() {
  if (!activeBatch.value) {
    return;
  }
  const { data } = await exportSurveyResults(activeBatch.value.id, buildRegionParams());
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${activeBatch.value.batchNo || activeBatch.value.id}_survey_results.zip`;
  link.click();
  URL.revokeObjectURL(url);
}

async function openResult(row) {
  isCreatingContractorResult.value = false;
  activeTask.value = row;
  selectedParcel.value = null;
  mapClearSelection();
  pendingOperations.value = [];
  savedSwapChanges.value = [];
  savedSplitChanges.value = [];
  savedParcelChangeLoading.value = false;
  rollbackingSavedChangeId.value = null;
  const { data } = await fetchSurveyResult(row.batchId, row.contractorUid);
  Object.assign(resultForm, createEmptyResult(), data.data, {
    familyMembers: (data.data.familyMembers || []).map((item) => ({ ...item })),
  });
  resetPhase2Forms();
  activeTab.value = "contractor";
  resultVisible.value = true;
  await loadDiffs();
  await loadSavedParcelChanges();
  await loadPhase2();
  loadSurveyParcels();
}

function closeResultDialog() {
  resultVisible.value = false;
  isCreatingContractorResult.value = false;
  pendingOperations.value = [];
  savedSwapChanges.value = [];
  savedSplitChanges.value = [];
  savedParcelChangeLoading.value = false;
  rollbackingSavedChangeId.value = null;
}

async function loadDiffs() {
  if (!activeBatch.value || !activeTask.value) {
    diffRows.value = [];
    return;
  }
  diffLoading.value = true;
  try {
    const { data } = await fetchSurveyDiffs(activeBatch.value.id, activeTask.value.contractorUid, { page: 1, page_size: 300 });
    diffRows.value = data.data.items;
  } finally {
    diffLoading.value = false;
  }
}

async function loadSavedParcelChanges() {
  if (!activeBatch.value || !activeTask.value) {
    savedSwapChanges.value = [];
    savedSplitChanges.value = [];
    return;
  }
  savedParcelChangeLoading.value = true;
  try {
    const { data } = await fetchSurveyChanges(activeBatch.value.id, {
      contractorUid: activeTask.value.contractorUid,
      page: 1,
      page_size: 200,
    });
    const items = data.data.items || [];
    savedSwapChanges.value = items.filter(
      (item) => item.changeType === "swap_parcels" && item.changeStatus !== "rolled_back",
    );
    savedSplitChanges.value = items.filter(
      (item) => item.changeType === "split_parcel" && item.changeStatus !== "rolled_back",
    );
  } catch {
    savedSwapChanges.value = [];
    savedSplitChanges.value = [];
  } finally {
    savedParcelChangeLoading.value = false;
  }
}

async function handleRollbackSavedSwapPending(change) {
  return handleRollbackSavedSwap(change);
  if (!activeBatch.value || !activeTask.value || !change?.id) {
    return;
  }
  if (hasPendingOperations.value) {
    ElMessage.warning("请先处理顶部未保存操作，再撤回已保存互换");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定撤回这次已保存的地块互换吗？\n换出：${change.swappedOutText}\n换入：${change.swappedInText}`,
      "撤回已保存互换",
      {
        type: "warning",
        confirmButtonText: "撤回互换",
        cancelButtonText: "取消",
      },
    );
    rollbackingSavedChangeId.value = change.id;
    await handleRollbackSavedSwap(
      activeBatch.value.id,
      activeTask.value.contractorUid,
      change.id,
      {},
    );
    ElMessage.success("已撤回已保存的地块互换");
    await reloadSurveyResult();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "撤回已保存互换失败");
    }
  } finally {
    rollbackingSavedChangeId.value = null;
  }
}

async function handleRollbackSavedSwap(change) {
  if (!activeBatch.value || !activeTask.value || !change?.id) {
    return;
  }
  if (hasPendingOperations.value) {
    ElMessage.warning("请先处理顶部未保存操作，再撤回已保存互换");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定撤回这次已保存的地块互换吗？\n换出：${change.swappedOutText}\n换入：${change.swappedInText}`,
      "撤回已保存互换",
      {
        type: "warning",
        confirmButtonText: "加入待保存",
        cancelButtonText: "取消",
      },
    );
    rollbackingSavedChangeId.value = change.id;
    const counterpartyCode = String(change.counterpartyLabel || "").trim();
    const counterpartyTask = tasks.value.find((item) => item.cbfbm === counterpartyCode);
    if (!counterpartyTask?.contractorUid) {
      ElMessage.warning("鏈壘鍒板鏂规壙鍖呮柟锛岃鍏堝埛鏂版壙鍖呮柟鍒楄〃鍚庡啀璇?");
      return;
    }
    const { data: counterpartyData } = await fetchSurveyParcels(
      activeBatch.value.id,
      counterpartyTask.contractorUid,
    );
    const restoreParcels = (counterpartyData.data || [])
      .filter((item) => (change.swappedOut || []).includes(item.dkbm))
      .map((item) => cloneParcel(item));
    const returnParcels = parcels.value
      .filter((item) => (change.swappedIn || []).includes(item.dkbm) && !["removed", "split_source"].includes(item.resultStatus));
    if (restoreParcels.length !== (change.swappedOut || []).length || returnParcels.length !== (change.swappedIn || []).length) {
      ElMessage.warning("当前页面地块状态已变化，请先重新打开调查录入后再试");
      return;
    }
    handlePendingOperation({
      type: "rollback_swap_parcels",
      payload: {
        changeId: change.id,
        changeNo: change.changeNo,
        returnDkbms: [...(change.swappedIn || [])],
        restoreDkbms: [...(change.swappedOut || [])],
        restoreParcels,
        reason: `撤回互换 ${change.changeNo}`,
      },
    });
    savedSwapChanges.value = savedSwapChanges.value.filter((item) => item.id !== change.id);
    ElMessage.success("已加入待保存，保存调查结果后才会正式落库");
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "撤回已保存互换失败");
    }
  } finally {
    rollbackingSavedChangeId.value = null;
  }
}

async function handleRollbackSavedSplit(change) {
  if (!activeBatch.value || !activeTask.value || !change?.id) {
    return;
  }
  if (hasPendingOperations.value) {
    ElMessage.warning("请先处理顶部未保存操作，再撤回已保存切割");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定撤回这次已保存的地块切割吗？\n源地块：${change.originalDkbm || "-"}\n生成地块：${change.generatedText || "-"}`,
      "撤回已保存切割",
      {
        type: "warning",
        confirmButtonText: "加入待保存",
        cancelButtonText: "取消",
      },
    );
    rollbackingSavedChangeId.value = change.id;
    const sourceParcel = parcels.value.find((item) => item.dkbm === change.originalDkbm && item.resultStatus === "split_source");
    if (!sourceParcel) {
      ElMessage.warning("当前页面地块状态已变化，请重新打开调查录入后再试");
      return;
    }
    const generatedParcels = parcels.value.filter(
      (item) => (change.generatedDkbms || []).includes(item.dkbm) && !["removed", "split_source"].includes(item.resultStatus),
    );
    if (generatedParcels.length !== (change.generatedDkbms || []).length) {
      ElMessage.warning("当前页面地块状态已变化，请重新打开调查录入后再试");
      return;
    }
    handlePendingOperation({
      type: "rollback_split_parcel",
      payload: {
        changeId: change.id,
        changeNo: change.changeNo,
        sourceDkbm: change.originalDkbm,
        sourceResultStatus: change.sourceResultStatus,
        sourceChangeType: change.sourceChangeType,
        sourceChangeReason: change.sourceChangeReason,
        sourceIsChanged: change.sourceIsChanged,
        generatedDkbms: [...(change.generatedDkbms || [])],
        reason: `撤回切割 ${change.changeNo}`,
      },
    });
    savedSplitChanges.value = savedSplitChanges.value.filter((item) => item.id !== change.id);
    ElMessage.success("已加入待保存，保存调查结果后才会正式落库");
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "撤回已保存切割失败");
    }
  } finally {
    rollbackingSavedChangeId.value = null;
  }
}

async function loadPhase2() {
  if (!activeBatch.value || !activeTask.value) {
    Object.assign(phase2, { tags: [], restructures: [], authorizations: [], attachments: [] });
    return;
  }
  phase2Loading.value = true;
  try {
    const { data } = await fetchSurveyPhase2(activeBatch.value.id, activeTask.value.contractorUid);
    Object.assign(phase2, {
      tags: data.data.tags || [],
      restructures: data.data.restructures || [],
      authorizations: data.data.authorizations || [],
      attachments: data.data.attachments || [],
    });
  } finally {
    phase2Loading.value = false;
  }
}

function resetPhase2Forms() {
  Object.assign(tagForm, { tagCode: "whole_family_urbanized", reason: "", policyBasis: "" });
  Object.assign(restructureForm, createEmptyRestructure());
  Object.assign(authorizationForm, createEmptyAuthorization(), {
    principalName: resultForm.name || "",
    principalIdNo: resultForm.idNo || "",
  });
  Object.assign(requestForm, {
    requestType: inferRequestType(resultForm),
    requestTitle: `${inferRequestType(resultForm)}-${resultForm.name || ""}-调查转办`,
    reason: resultForm.changeReason || "",
    note: resultForm.evidenceSummary || "",
  });
  selectedAttachmentFile.value = null;
  authorizationUploadTarget.value = null;
}

function inferRequestType(row) {
  return row.changeType === "extinct" || ["extinct", "cancelled"].includes(row.resultStatus) ? "注销登记" : "变更登记";
}

function tagNameByCode(code) {
  return {
    whole_family_urbanized: "全家进城落户户",
    household_extinct: "整户消亡户",
    five_guarantees: "五保户",
    little_or_no_land: "无地少地户",
  }[code] || code;
}

async function handleRefreshTags() {
  await refreshSurveyTags(activeBatch.value.id, activeTask.value.contractorUid);
  await loadPhase2();
}

async function handleCreateTag() {
  await createSurveyTag(activeBatch.value.id, activeTask.value.contractorUid, {
    ...tagForm,
    tagName: tagNameByCode(tagForm.tagCode),
  });
  ElMessage.success("人工标签已新增");
  Object.assign(tagForm, { tagCode: "whole_family_urbanized", reason: "", policyBasis: "" });
  await loadPhase2();
}

async function handleDisableTag(row) {
  const { value } = await ElMessageBox.prompt("请输入停用原因", "停用标签", {
    inputType: "textarea",
    inputValidator: (text) => Boolean(text?.trim()) || "请输入停用原因",
  });
  await disableSurveyTag(row.id, { disabledReason: value.trim() });
  await loadPhase2();
}

function fillRestructureMembers() {
  restructureForm.sourceCbfbm = resultForm.code;
  restructureForm.sourceCbfmc = resultForm.name;
  restructureForm.members = resultForm.familyMembers.map((item) => ({
    memberUid: item.memberUid,
    memberName: item.name,
    memberIdNo: item.idNo,
    fromCbfbm: resultForm.code,
    toCbfbm: restructureForm.targetCbfbm || restructureForm.newCbfbm,
    actionType: "move",
    rightsDisposition: item.rightsDisposition || "",
    remark: "",
  }));
}

async function handleSaveRestructure() {
  if (!restructureForm.reason?.trim()) {
    ElMessage.warning("请输入分合户原因");
    return;
  }
  await createSurveyRestructure(activeBatch.value.id, activeTask.value.contractorUid, {
    ...restructureForm,
    sourceCbfbm: restructureForm.sourceCbfbm || resultForm.code,
    sourceCbfmc: restructureForm.sourceCbfmc || resultForm.name,
  });
  ElMessage.success("分合户专项已保存");
  Object.assign(restructureForm, createEmptyRestructure());
  await loadPhase2();
}

async function handleDeleteRestructure(row) {
  await ElMessageBox.confirm(`确定删除专项 ${row.restructureNo} 吗？`, "删除分合户专项", { type: "warning" });
  await deleteSurveyRestructure(row.id);
  await loadPhase2();
}

async function handleSaveAuthorization() {
  if (!authorizationForm.principalName || !authorizationForm.agentName || !authorizationForm.authorizedMatters) {
    ElMessage.warning("请填写委托人、受托人和委托事项");
    return;
  }
  await createSurveyAuthorization(activeBatch.value.id, activeTask.value.contractorUid, authorizationForm);
  ElMessage.success("授权委托已保存");
  Object.assign(authorizationForm, createEmptyAuthorization(), {
    principalName: resultForm.name || "",
    principalIdNo: resultForm.idNo || "",
  });
  await loadPhase2();
}

function openAuthorizationFile(row) {
  authorizationUploadTarget.value = row;
  authorizationFileInput.value?.click();
}

async function handleAuthorizationFileChange(event) {
  const file = event.target.files?.[0];
  if (!file || !authorizationUploadTarget.value) {
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  await uploadSurveyAuthorizationFile(authorizationUploadTarget.value.id, formData);
  event.target.value = "";
  authorizationUploadTarget.value = null;
  await loadPhase2();
}

async function handleDownloadAuthorizationTemplate(row) {
  const { data } = await downloadSurveyAuthorizationTemplate(row.id);
  downloadBlob(data, `${row.authorizationNo}_授权委托书.txt`);
}

async function handleDownloadAuthorizationFile(row) {
  const { data } = await downloadSurveyAuthorizationFile(row.id);
  downloadBlob(data, row.originalName || `${row.authorizationNo}_file`);
}

async function handleRevokeAuthorization(row) {
  const { value } = await ElMessageBox.prompt("请输入作废原因", "作废授权委托", {
    inputType: "textarea",
    inputValidator: (text) => Boolean(text?.trim()) || "请输入作废原因",
  });
  await revokeSurveyAuthorization(row.id, { revokeReason: value.trim() });
  await loadPhase2();
}

function handleAttachmentFileChange(event) {
  selectedAttachmentFile.value = event.target.files?.[0] || null;
}

async function handleUploadAttachment() {
  if (!selectedAttachmentFile.value) {
    ElMessage.warning("请选择附件文件");
    return;
  }
  const formData = new FormData();
  formData.append("category", attachmentCategory.value);
  formData.append("description", attachmentDescription.value || "");
  formData.append("file", selectedAttachmentFile.value);
  await uploadSurveyAttachment(activeBatch.value.id, activeTask.value.contractorUid, formData);
  selectedAttachmentFile.value = null;
  attachmentDescription.value = "";
  await loadPhase2();
}

async function handleDownloadAttachment(row) {
  const { data } = await downloadSurveyAttachment(row.id);
  downloadBlob(data, row.originalName);
}

async function handleDeleteAttachment(row) {
  await ElMessageBox.confirm(`确定删除附件 ${row.originalName} 吗？`, "删除调查附件", { type: "warning" });
  await deleteSurveyAttachment(row.id);
  await loadPhase2();
}

async function handleGenerateRequest() {
  if (!requestForm.requestType) {
    ElMessage.warning("请选择业务类型");
    return;
  }
  const { data } = await generateSurveyRequest(activeBatch.value.id, activeTask.value.contractorUid, requestForm);
  ElMessage.success(`已生成业务申请 ${data.data.serialNo}`);
  const result = await fetchSurveyResult(activeBatch.value.id, activeTask.value.contractorUid);
  Object.assign(resultForm, result.data.data, {
    familyMembers: (result.data.data.familyMembers || []).map((item) => ({ ...item })),
  });
}

function downloadBlob(data, filename) {
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function handleSaveResult() {
  if (!activeBatch.value || (!activeTask.value && !isCreatingContractorResult.value)) {
    return;
  }
  resultForm.code = digitsOnly(resultForm.code).slice(0, 18);
  if (resultForm.code.length !== 18) {
    ElMessage.warning("承包方编码必须为18位数字");
    return;
  }
  if (!resultForm.name?.trim() || !resultForm.idNo?.trim() || !resultForm.address?.trim()) {
    ElMessage.warning("请填写承包方名称、证件号码和地址");
    return;
  }
  savingResult.value = true;
  creatingContractor.value = isCreatingContractorResult.value;
  try {
    const allMembers = resultForm.familyMembers || [];
    const validMembers = allMembers.filter((m) => !m._deleted);
    const cleanMembers = validMembers.map(({ _deleted, _isNew, ...rest }) => rest);
    const deletedMembers = allMembers
      .filter((m) => m._deleted && m.memberUid)
      .map((m) => ({
        memberUid: m.memberUid,
        changeReason: m.changeReason || resultForm.changeReason || "去世",
      }));
    const { issuer, baseIssuer, ...contractorPayload } = resultForm;
    let contractorUid = activeTask.value?.contractorUid;
    if (isCreatingContractorResult.value) {
      const { data } = await createSurveyContractor(activeBatch.value.id, {
        code: contractorPayload.code.trim(),
        typeCode: contractorPayload.typeCode,
        name: contractorPayload.name.trim(),
        idType: contractorPayload.idType,
        idNo: contractorPayload.idNo.trim(),
        address: contractorPayload.address.trim(),
        postcode: contractorPayload.postcode?.trim() || "000000",
        mobile: contractorPayload.mobile?.trim() || null,
        groupRegionCode: contractorPayload.groupRegionCode || activeBatch.value.regionCode || activeRegionCode.value || "",
        groupRegionName: contractorPayload.groupRegionName || activeBatch.value.regionName || activeRegionLabel.value || "",
        surveyDate: contractorPayload.surveyDate,
        surveyorName: contractorPayload.surveyorName,
        remark: contractorPayload.remark,
      });
      contractorUid = data.data.contractorUid;
    }
    await updateSurveyResult(activeBatch.value.id, contractorUid, {
      ...contractorPayload,
      contractorUid,
      familyMembers: cleanMembers,
      deletedMembers,
      pendingOperations: pendingOperations.value,
    });
    ElMessage.success(isCreatingContractorResult.value ? "承包方调查数据已新增" : "调查结果已保存");
    pendingOperations.value = [];
    closeResultDialog();
    await loadTasks();
    await loadBatches();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || (isCreatingContractorResult.value ? "新增承包方失败" : "保存调查结果失败"));
  } finally {
    savingResult.value = false;
    creatingContractor.value = false;
  }
}

async function handleConfirmTask(row) {
  try {
    await confirmSurveyResult(row.batchId, row.contractorUid);
    ElMessage.success("调查结果已确认");
    await loadTasks();
    await loadBatches();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "确认失败");
  }
}

async function handleSkipTask(row) {
  try {
    const { value } = await ElMessageBox.prompt("请输入跳过原因", "跳过调查任务", {
      inputType: "textarea",
      inputPlaceholder: "例如：本轮调查无需处理、非本区域调查对象等",
      inputValidator: (text) => Boolean(text?.trim()) || "请输入跳过原因",
      confirmButtonText: "跳过",
      cancelButtonText: "取消",
      type: "warning",
    });
    await skipSurveyTask(row.batchId, row.contractorUid, { skipReason: value.trim() });
    ElMessage.success("调查任务已跳过");
    await loadTasks();
    await loadBatches();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "跳过失败");
    }
  }
}

async function handleConfirmCurrent() {
  if (!activeBatch.value || !activeTask.value) {
    return;
  }
  confirmingResult.value = true;
  try {
    await confirmSurveyResult(activeBatch.value.id, activeTask.value.contractorUid);
    ElMessage.success("调查结果已确认");
    resultVisible.value = false;
    await loadTasks();
    await loadBatches();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "确认失败");
  } finally {
    confirmingResult.value = false;
  }
}

async function reloadSurveyResult() {
  if (!activeBatch.value || !activeTask.value) return;
  try {
    const { data } = await fetchSurveyResult(activeBatch.value.id, activeTask.value.contractorUid);
    Object.assign(resultForm, createEmptyResult(), data.data, {
      familyMembers: (data.data.familyMembers || []).map((item) => ({ ...item })),
    });
    await loadDiffs();
    await loadSavedParcelChanges();
    await loadTasks();
    await loadBatches();
    await loadSurveyParcels();
    plotSketchRefreshKey.value += 1;
  } catch (e) {
    // silently ignore reload errors
  }
}

async function handleDeregisterDone() {
  resultVisible.value = false;
  await loadTasks();
  await loadBatches();
}

async function handleMergeDone() {
  resultVisible.value = false;
  await loadTasks();
  await loadBatches();
}

watch(activeTab, (tab) => {
  if (tab === "parcels") {
    handleParcelTabEnter();
  }
});

watch(surveyPanelTab, (tab) => {
  if (tab === "issuer") {
    loadIssuerSurveyRows();
  }
});

watch(parcels, (list) => {
  if (activeTab.value === "parcels" && mapReady.value && list.length) {
    loadParcels(list);
    if (!selectedParcelDkbm.value) {
      fitToParcels();
    }
  }
});

watch(resultVisible, (visible) => {
  if (!visible) {
    destroyMap();
    selectedParcel.value = null;
    mapClearSelection();
  }
});

loadInitialData();
</script>

<style scoped>
.survey-page {
  display: flex;
  gap: 16px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.survey-batch-panel {
  display: flex;
  flex: 0 0 calc(20% - 8px);
  flex-direction: column;
  min-width: 220px;
  max-width: 300px;
  min-height: 0;
  padding: 14px;
}

.survey-work-panel {
  display: flex;
  flex: 1 1 auto;
  margin-top: 0;
  min-width: 0;
  min-height: 0;
}

.survey-work-tabs {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}

.survey-work-tabs :deep(.el-tabs__content) {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
}

.survey-work-tabs :deep(.el-tab-pane) {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.survey-work-panel :deep(.el-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.survey-work-panel :deep(.survey-action-column .cell) {
  white-space: nowrap;
}

.survey-row-actions {
  align-items: center;
  display: inline-flex;
  flex-wrap: nowrap;
  gap: 10px;
  justify-content: center;
  white-space: nowrap;
}

.survey-row-actions :deep(.el-button) {
  margin-left: 0;
}

.batch-panel-header,
.batch-footer-actions {
  align-items: center;
  display: flex;
}

.batch-panel-header {
  justify-content: space-between;
  gap: 10px;
}

.batch-footer-actions {
  gap: 8px;
}

.batch-panel-actions {
  align-items: center;
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 116px) auto;
}

.batch-header-filter {
  width: 116px;
}

.batch-search {
  margin-top: 12px;
}

.batch-card-list {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.batch-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  color: #0f172a;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  text-align: left;
  transition: background 0.2s, border-color 0.2s, box-shadow 0.2s;
  width: 100%;
}

.batch-card:hover,
.batch-card.is-active {
  background: #f8fafc;
  border-color: #2563eb;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
}

.batch-card-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.batch-card-status-row,
.batch-card-metrics {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
}

.batch-card-progress {
  color: #475569;
  font-size: 12px;
  white-space: nowrap;
}

.batch-card-metrics {
  border-top: 1px solid #e2e8f0;
  padding-top: 8px;
}

.batch-card-metrics span {
  color: #64748b;
  display: flex;
  flex-direction: column;
  font-size: 12px;
  gap: 2px;
}

.batch-card-metrics b {
  color: #0f172a;
  font-size: 18px;
  line-height: 1;
}

.batch-footer-actions {
  border-top: 1px solid #e2e8f0;
  flex-shrink: 0;
  margin-top: 12px;
  padding-top: 12px;
}

.batch-tooltip-content {
  display: grid;
  gap: 6px;
  min-width: 220px;
}

.batch-tooltip-content div {
  color: #0f172a;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.batch-tooltip-content span {
  color: #64748b;
  flex: 0 0 70px;
}

@media (max-width: 1080px) {
  .survey-page {
    flex-direction: column;
  }

  .survey-batch-panel {
    flex-basis: auto;
    max-width: none;
    min-height: 240px;
  }
}

.survey-dialog-form {
  margin-top: 16px;
}

.snapshot-member-title {
  color: #334155;
  font-size: 14px;
  font-weight: 700;
  margin: 16px 0 10px;
}

.snapshot-changed-value {
  background: #fef3c7;
  border: 1px solid #f59e0b;
  border-radius: 4px;
  color: #92400e;
  display: inline-block;
  font-weight: 600;
  line-height: 1.5;
  padding: 0 6px;
}

.phase2-actions,
.phase2-upload {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.phase2-form {
  margin: 14px 0;
}

.phase2-submit {
  margin-top: 12px;
}

/* ---- 地块信息 tab ---- */
.parcel-tab-shell {
  display: flex;
  gap: 12px;
  height: 520px;
  align-items: stretch;
}

.parcel-map-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.parcel-map-toolbar {
  align-items: center;
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.parcel-map-toolbar-label {
  color: #475569;
  font-size: 13px;
  font-weight: 600;
}

.parcel-map-container {
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  flex: 1;
  min-height: 0;
}

.parcel-list-panel {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  width: 230px;
  flex-shrink: 0;
  overflow: hidden;
}

.parcel-list-header {
  align-items: center;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  flex-shrink: 0;
  justify-content: space-between;
  padding: 8px 10px;
}

.parcel-list-title {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.parcel-list-body {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.parcel-list-item {
  align-items: center;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  gap: 6px;
  margin-bottom: 4px;
  padding: 5px 8px;
  transition: background 0.15s, border-color 0.15s;
  width: 100%;
}

.parcel-list-item:hover {
  background: #f8fafc;
  border-color: #94a3b8;
}

.parcel-list-item.is-selected {
  background: #eff6ff;
  border-color: #3b82f6;
}

.parcel-list-item.is-flash {
  animation: parcel-flash 0.9s ease-in-out 3;
}

@keyframes parcel-flash {
  0%, 100% {
    background: #eff6ff;
    border-color: #3b82f6;
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4);
  }
  50% {
    background: #fef08a;
    border-color: #eab308;
    box-shadow: 0 0 8px 2px rgba(234, 179, 8, 0.6);
  }
}

.parcel-list-index {
  background: #e2e8f0;
  border-radius: 50%;
  color: #475569;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  height: 18px;
  width: 18px;
}

.is-selected .parcel-list-index {
  background: #3b82f6;
  color: #fff;
}

.parcel-list-code {
  color: #1e293b;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.parcel-list-name {
  color: #64748b;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.parcel-detail-panel {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  width: 290px;
  flex-shrink: 0;
  overflow: hidden;
}

.parcel-detail-title {
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  color: #334155;
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 12px;
}

.parcel-detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.parcel-detail-row {
  display: flex;
  padding: 3px 12px;
}

.parcel-detail-row.is-highlight {
  background: #eff6ff;
}

.parcel-detail-label {
  color: #64748b;
  flex-shrink: 0;
  font-size: 12px;
  width: 105px;
}

.parcel-detail-label::after {
  content: "：";
}

.parcel-detail-value {
  color: #1e293b;
  font-size: 12px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.parcel-detail-empty {
  align-items: center;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  display: flex;
  justify-content: center;
  width: 290px;
  flex-shrink: 0;
}

.pending-operation-alert {
  margin-bottom: 12px;
}

.pending-operation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: -4px 0 12px;
}

.pending-operation-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  border: 1px solid #f3d19e;
  border-radius: 8px;
  background: #fdf6ec;
}

.pending-operation-text {
  color: #8a5a12;
  font-size: 13px;
}
</style>
