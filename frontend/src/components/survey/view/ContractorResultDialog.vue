<template>
  <el-dialog :model-value="modelValue" :title="resultDialogTitle" width="92vw" top="3vh" destroy-on-close @update:model-value="$emit('update:modelValue', $event)">
    <div v-if="!isCreatingContractorResult" class="survey-toolbar">
      <el-button type="danger" plain size="small" :disabled="dataReadOnly" @click="handleOpDeregister">注销承包方</el-button>
      <el-button plain size="small" :disabled="dataReadOnly" @click="handleOpSplitHousehold">分户</el-button>
      <el-button v-if="canRollbackSplitHousehold" type="warning" plain size="small" :loading="rollbackingSplitHousehold" @click="handleRollbackSplitHousehold">撤回分户</el-button>
      <el-button plain size="small" :disabled="dataReadOnly" @click="handleOpMergeHousehold">合并户</el-button>
      <el-button v-if="canRollbackMergeHousehold" type="warning" plain size="small" :loading="rollbackingMergeHousehold" @click="handleRollbackMergeHousehold">撤回合户</el-button>
      <span class="toolbar-print">
        <el-button type="primary" plain size="small" :loading="printingCadastral" :disabled="isCreatingContractorResult" @click="handlePrintCadastral">打印地籍调查表</el-button>
      </span>
      <span v-if="dataReadOnly" class="toolbar-lock-hint">（当前为只读模式，只能查看详细信息）</span>
    </div>
    <el-alert v-if="pendingOperations.length" type="warning" :closable="false" show-icon class="pending-operation-alert" :title="`当前有 ${pendingOperations.length} 项操作尚未保存，请点击保存调查结果统一提交。`" />
    <div v-if="pendingOperations.length" class="pending-operation-list">
      <div v-for="(operation, index) in pendingOperations" :key="`${operation.type}-${index}`" class="pending-operation-item">
        <span class="pending-operation-text">{{ pendingOperationLabelPreview(operation) }}</span>
        <el-button v-if="canUndoPendingOperation(operation)" link type="danger" size="small" @click="handleUndoPendingOperationPreview(index)">撤销</el-button>
      </div>
    </div>
    <el-collapse v-model="openPanels" class="survey-collapse" @change="handlePanelsChange">
      <el-collapse-item name="contractor" :title="`承包方及其家庭成员（${resultForm.familyMembers.length}人）`">
        <ContractorMemberPanel ref="contractorMemberPanel" :batch-id="activeBatch?.id" :contractor-uid="resultForm.contractorUid" :result="resultForm" :changed-fields="computedChangedFields" :readonly="dataReadOnly" :can-generate-code="!dataReadOnly && resultForm.resultStatus === 'added'" @generate-code="generateResultContractorCode" />
      </el-collapse-item>
      <el-collapse-item title="地块信息" name="parcels" :disabled="isCreatingContractorResult">
        <ParcelInfoPanel v-if="isPanelMounted('parcels')" :batch-id="activeBatch?.id" :contractor-uid="resultForm.contractorUid" :parcels="parcels" :parcels-loading="parcelsLoading" :can-manage="canManage && canWrite" :is-result-locked="dataReadOnly" :saved-swap-records="savedSwapRecords" :saved-split-records="savedSplitRecords" :saved-remove-records="savedRemoveRecords" :can-rollback-saved-parcel-change="canRollbackSavedParcelChange" :rollback-change-loading-id="rollbackingSavedChangeId" @swap-parcels="handleOpSwapParcels" @add-parcel="handlePendingOperation" @split-parcel="handlePendingOperation" @remove-parcel="handleOpRemoveParcel" @rollback-saved-swap="handleRollbackSavedSwap" @rollback-saved-split="handleRollbackSavedSplit" @rollback-saved-remove="handleRollbackSavedRemove" @undo-pending-remove="handleUndoPendingRemoveFromPanel" />
      </el-collapse-item>
      <el-collapse-item title="承包地块示意图" name="plotSketchMap" :disabled="isCreatingContractorResult">
        <PlotSketchMapPanel v-if="isPanelMounted('plotSketchMap')" :batch-id="activeBatch?.id" :contractor-uid="resultForm.contractorUid" :refresh-key="plotSketchRefreshKey" />
      </el-collapse-item>
      <el-collapse-item title="合同信息" name="contract" :disabled="isCreatingContractorResult">
        <ContractInfoPanel
          v-if="isPanelMounted('contract')"
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
          :can-manage="canManage && canWrite"
          :batch-status="activeBatch?.status || 'active'"
        />
      </el-collapse-item>
    </el-collapse>
    <el-collapse v-if="!isCreatingContractorResult" v-model="openAuxPanels" class="survey-collapse survey-collapse--aux">
      <el-collapse-item title="调查附件 & 转业业务申请" name="aux">
        <div v-if="canManage && canWrite && !dataReadOnly" class="phase2-upload">
          <el-select v-model="attachmentCategory" style="width: 160px" size="small">
            <el-option v-for="item in attachmentCategoryOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-input v-model="attachmentDescription" placeholder="附件说明" style="width: 200px" size="small" />
          <input type="file" @change="handleAttachmentFileChange" />
          <el-button type="success" size="small" plain @click="handleUploadAttachment">上传</el-button>
        </div>
        <el-table v-loading="phase2Loading" :data="phase2.attachments" border size="small">
          <el-table-column label="类型" width="140">
            <template #default="{ row }">{{ surveyAttachmentCategoryLabel(row.category, attachmentCategoryOptions) }}</template>
          </el-table-column>
          <el-table-column prop="originalName" label="文件名" min-width="200" />
          <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
          <el-table-column label="操作" width="170">
            <template #default="{ row }">
              <el-button link type="success" size="small" @click="handlePreviewAttachment(row)">预览</el-button>
              <el-button link type="primary" size="small" @click="handleDownloadAttachment(row)">下载</el-button>
              <el-button v-if="canManage && canWrite && !isResultLocked" link type="danger" size="small" @click="handleDeleteAttachment(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-divider />
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="已生成申请">{{ resultForm.generatedRequestNo || "-" }}</el-descriptions-item>
          <el-descriptions-item label="建议业务类型">{{ inferRequestType(resultForm) }}</el-descriptions-item>
        </el-descriptions>
        <el-form v-if="canManage && canWrite && !resultForm.generatedRequestId" :model="requestForm" class="compact-form" label-position="top" style="margin-top:8px">
          <div class="form-grid">
            <el-form-item label="业务类型"><el-select v-model="requestForm.requestType" size="small"><el-option label="变更登记" value="变更登记" /><el-option label="注销登记" value="注销登记" /><el-option label="首次登记" value="首次登记" /></el-select></el-form-item>
            <el-form-item label="申请标题"><el-input v-model="requestForm.requestTitle" size="small" /></el-form-item>
            <el-form-item class="form-span-2" label="申请原因"><el-input v-model="requestForm.reason" type="textarea" :rows="2" size="small" /></el-form-item>
          </div>
          <el-button type="success" size="small" @click="handleGenerateRequest">生成业务申请</el-button>
        </el-form>
      </el-collapse-item>
    </el-collapse>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button v-if="canManage && canWrite && !isResultLocked && (!savedTerminated || terminalPendingOperation)" :loading="savingResult || creatingContractor" type="success" @click="handleSaveResult">{{ isCreatingContractorResult ? "新增并保存" : "保存调查结果" }}</el-button>
      <el-button v-if="canManage && canWrite && !isCreatingContractorResult && !dataReadOnly && resultForm.surveyStatus !== 'not_surveyed'" :loading="confirmingResult" type="primary" @click="handleConfirmCurrent">确认调查结果</el-button>
    </template>
  </el-dialog>
  <DeregisterDialog ref="deregisterDialog" @done="handlePendingOperation" />
  <SwapParcelsDialog ref="swapParcelsDialog" @done="handlePendingOperation" />
  <SplitHouseholdDialog ref="splitHouseholdDialog" @done="handlePendingOperation" />
  <MergeHouseholdDialog ref="mergeHouseholdDialog" @done="handlePendingOperation" />
  <RemoveParcelDialog ref="removeParcelDialog" @done="handlePendingOperation" />
  <AttachmentPreviewDialog
    v-model="previewAttachmentVisible"
    :source="previewAttachment"
    :loader="loadAttachmentPreviewBlob"
    :navigation="attachmentPreviewNavigation"
    @download="handleDownloadAttachment"
    @prev="stepAttachmentPreview(-1)"
    @next="stepAttachmentPreview(1)"
  />
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import ContractorMemberPanel from "../ContractorMemberPanel.vue";
import ParcelInfoPanel from "../ParcelInfoPanel.vue";
import PlotSketchMapPanel from "../PlotSketchMapPanel.vue";
import ContractInfoPanel from "../ContractInfoPanel.vue";
import DeregisterDialog from "../DeregisterDialog.vue";
import SwapParcelsDialog from "../SwapParcelsDialog.vue";
import SplitHouseholdDialog from "../SplitHouseholdDialog.vue";
import MergeHouseholdDialog from "../MergeHouseholdDialog.vue";
import RemoveParcelDialog from "../RemoveParcelDialog.vue";
import AttachmentPreviewDialog from "../../requests/AttachmentPreviewDialog.vue";

import {
  confirmSurveyResult, createSurveyAuthorization, createSurveyContractor,
  createSurveyRestructure, createSurveyTag, deleteSurveyAttachment,
  deleteSurveyRestructure, disableSurveyTag, downloadSurveyAttachment,
  downloadSurveyAuthorizationFile, downloadSurveyAuthorizationTemplate,
  fetchSurveyChanges, fetchSurveyDiffs, fetchSurveyParcels, fetchSurveyPhase2,
  fetchSurveyAttachmentCategories,
  fetchSurveyResult, generateSurveyRequest, refreshSurveyTags,
  fetchContractorCodes, fetchCadastralSurvey,
  previewSurveyAttachment,
  revokeSurveyAuthorization, updateSurveyResult, uploadSurveyAttachment,
  uploadSurveyAuthorizationFile, rollbackSplitSurveyHousehold, rollbackMergeSurveyHousehold,
} from "../../../api/survey";
import { collectContractorCodes, fetchAllBatchTasks } from "../../../utils/surveyCandidates";
import { FALLBACK_SURVEY_ATTACHMENT_CATEGORIES, surveyAttachmentCategoryLabel } from "../../../config/surveyAttachmentCategories";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  activeBatch: { type: Object, default: null },
  canManage: { type: Boolean, default: false },
  // 任务归属：这一户是否分给当前用户（后端 SurveyTaskRead.canWrite）。
  // false ⇒ 界面上一切照旧但全部只读：能看详细信息，不能录入。
  // 默认 true 是为了不破坏「新增承包方」这类还没有归属行可判的入口。
  canWrite: { type: Boolean, default: true },
  tasks: { type: Array, default: () => [] },
  activeRegionCode: { type: String, default: "" },
  activeRegionLabel: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue", "saved", "confirmed"]);


// ---- State ----
const savingResult = ref(false);
const creatingContractor = ref(false);
const confirmingResult = ref(false);
const printingCadastral = ref(false);
const activeTask = ref(null);
const isCreatingContractorResult = ref(false);
// 折叠面板：openPanels = 当前展开的面板；openedPanels = 展开过一次的面板。
// el-collapse-item 的内容是常挂载（v-show），而地块/示意图/合同三个面板在 mount 时
// 就会立刻拉数据，所以用 v-if 卡住首次展开 —— 不展开就不挂载，维持原 lazy tab 的请求数。
const openPanels = ref(["contractor"]);
const openAuxPanels = ref([]);
const openedPanels = ref(["contractor"]);
function isPanelMounted(name) { return openedPanels.value.includes(name); }
async function handlePanelsChange(names) {
  const list = Array.isArray(names) ? names : [names];
  for (const name of list) if (!openedPanels.value.includes(name)) openedPanels.value = [...openedPanels.value, name];
  if (list.includes("parcels")) {
    // 地图容器需要先完成挂载，再初始化 OpenLayers。
    await nextTick();
    if (!parcelsLoaded.value && !parcelsLoading.value) {
      await Promise.all([loadSurveyParcels(), loadSavedParcelChanges()]);
    }
  }
}
const plotSketchRefreshKey = ref(0);
const contractorMemberPanel = ref(null);
const deregisterDialog = ref(null);
const swapParcelsDialog = ref(null);
const splitHouseholdDialog = ref(null);
const mergeHouseholdDialog = ref(null);
const removeParcelDialog = ref(null);

const parcels = ref([]);
const parcelsLoaded = ref(false);
const selectedParcel = ref(null);
const parcelsLoading = ref(false);
const flashDkbm = ref(null);
let flashTimer = null;

const diffRows = ref([]);
const diffLoading = ref(false);
const savedSwapChanges = ref([]);
const savedSplitChanges = ref([]);
const savedRemoveChanges = ref([]);
const savedParcelChangeLoading = ref(false);
const pendingOperations = ref([]);
const rollbackingSavedChangeId = ref(null);
const rollbackingSplitHousehold = ref(false);
const rollbackingMergeHousehold = ref(false);

const phase2Loading = ref(false);
const phase2 = reactive({ tags: [], restructures: [], authorizations: [], attachments: [] });

const tagForm = reactive({ tagCode: "whole_family_urbanized", reason: "", policyBasis: "" });
const restructureForm = reactive(createEmptyRestructure());
const authorizationForm = reactive(createEmptyAuthorization());
const requestForm = reactive({ requestType: "变更登记", requestTitle: "", reason: "", note: "" });
const attachmentCategory = ref(FALLBACK_SURVEY_ATTACHMENT_CATEGORIES[0].value);
// 上传类别来自「附件组管理」页，加载成功就替换掉这份兜底。
const attachmentCategoryOptions = ref([...FALLBACK_SURVEY_ATTACHMENT_CATEGORIES]);
const attachmentDescription = ref("");
const selectedAttachmentFile = ref(null);
const previewAttachment = ref(null);
const previewAttachmentVisible = ref(false);
// 预览翻页的位置，按附件列表当前顺序（与表格同序，`phase2.attachments`）。
const attachmentPreviewIndex = ref(-1);
const attachmentPreviewNavigation = computed(() => {
  const total = phase2.attachments.length;
  if (!previewAttachmentVisible.value || attachmentPreviewIndex.value < 0 || total === 0) return null;
  return { index: attachmentPreviewIndex.value, total };
});
const authorizationFileInput = ref(null);
const authorizationUploadTarget = ref(null);

const resultForm = reactive(createEmptyResult());

// ---- Computed ----
const isResultLocked = computed(() => props.activeBatch?.status === "finished" || (!isCreatingContractorResult.value && resultForm.surveyStatus === "confirmed"));
const terminalPendingOperation = computed(() => pendingOperations.value.find(op => ["deregister", "split_household", "merge_household"].includes(op?.type)) || null);
// 这一户是否已被终结（注销 / 被合户并走 / 被分户拆走）——**只消费后端给的 isTerminal**，
// 不自己拿 changeType 算：分户/合户**新生成**的户 changeType 与原户同值（merge_household /
// split_household），自算会把新户一起判成"已注销"，整个表单变只读（2026-09-25 用户报
// 「合户之后刘乃高不能修改」的界面侧根因）。与后端 `update_result` 的 400 闸门同源。
const savedTerminated = computed(() => !isCreatingContractorResult.value && Boolean(resultForm.isTerminal));
// 只读的四种来源：没有管理权限 / 批次已结束或成果已确认（isResultLocked）/
// 还有未保存的终结操作 / **这一户没分给我**（!canWrite）。
// 最后一条（2026-09-23 加）就是「未分配或已分给他人的户只能看详细信息」：
// 界面照旧，但不给编辑、不给功能按钮。
const dataReadOnly = computed(() => !props.canManage || !props.canWrite || isResultLocked.value || Boolean(terminalPendingOperation.value) || savedTerminated.value);
const hasPendingOperations = computed(() => pendingOperations.value.length > 0);
const canRollbackSavedParcelChange = computed(() => props.canManage && props.canWrite && !isResultLocked.value && !hasPendingOperations.value);
const canRollbackSplitHousehold = computed(() => props.canManage && props.canWrite && props.activeBatch?.status !== "finished" && resultForm.resultStatus === "cancelled" && resultForm.changeType === "split_household" && !hasPendingOperations.value);
const canRollbackMergeHousehold = computed(() => props.canManage && props.canWrite && props.activeBatch?.status !== "finished" && resultForm.resultStatus === "cancelled" && resultForm.changeType === "merge_household" && !hasPendingOperations.value);

const resultDialogTitle = computed(() => {
  const name = resultForm.name ? ` - ${resultForm.name}` : "";
  if (isCreatingContractorResult.value) return `新增承包方调查录入${name}`;
  return `${dataReadOnly.value ? "承包方调查详情（只读）" : "承包方调查录入"}${name}`;
});

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
    if (String(resultForm[f] ?? "") !== String(base[b] ?? "")) fields.push(f);
  }
  return fields;
});

const savedSwapRecords = computed(() =>
  savedSwapChanges.value.map((item) => {
    const bs = item.beforeSummary || {};
    const as = item.afterSummary || {};
    const swappedOut = Array.isArray(bs.swapped_out) ? bs.swapped_out.filter(Boolean) : [];
    const swappedIn = Array.isArray(as.swapped_in) ? as.swapped_in.filter(Boolean) : [];
    return { ...item, swappedOut, swappedIn, swappedOutText: swappedOut.length ? swappedOut.join("、") : "-", swappedInText: swappedIn.length ? swappedIn.join("、") : "-", counterpartyLabel: as.counterparty || "-" };
  }),
);

const savedSplitRecords = computed(() =>
  savedSplitChanges.value.map((item) => {
    const bs = item.beforeSummary || {};
    const as = item.afterSummary || {};
    const generatedParcels = Array.isArray(as.generated_parcels) ? as.generated_parcels.filter((p) => p?.dkbm) : (as.new_dkbm ? [{ dkbm: as.new_dkbm, area: as.new_area }] : []);
    const generatedDkbms = generatedParcels.map((p) => String(p.dkbm || "").trim()).filter(Boolean);
    return { ...item, originalDkbm: String(bs.dkbm || as.original_dkbm || "").trim(), sourceResultStatus: bs.source_result_status || "normal", sourceChangeType: bs.source_change_type || "none", sourceChangeReason: bs.source_change_reason || "", sourceIsChanged: Boolean(bs.source_is_changed), generatedParcels, generatedDkbms, generatedText: generatedDkbms.length ? generatedDkbms.join("、") : "-" };
  }),
);

const savedRemoveRecords = computed(() =>
  savedRemoveChanges.value.map((item) => {
    const bs = item.beforeSummary || {};
    const as = item.afterSummary || {};
    const removedDkbm = String(as.dkbm || "").trim();
    return {
      ...item,
      removedDkbm,
      sourceResultStatus: bs.source_result_status || "normal",
      sourceChangeType: bs.source_change_type || "none",
      sourceChangeReason: bs.source_change_reason || "",
      sourceIsChanged: Boolean(bs.source_is_changed),
      label: removedDkbm || "-",
    };
  }),
);

// ---- Factories ----
function createEmptyResult() {
  return { contractorUid: "", code: "", typeCode: "1", name: "", idType: "1", idNo: "", address: "", postcode: "000000", mobile: "", memberCount: 0, groupRegionCode: "", groupRegionName: "", surveyDate: "", surveyorName: "", surveyNote: "", publicNoticeNote: "", publicNoticeRecorder: "", publicNoticeReviewDate: "", publicNoticeReviewer: "", surveyStatus: "surveyed", resultStatus: "normal", changeType: "none", changeReason: "", policyBasis: "", evidenceSummary: "", remark: "", isTerminal: false, baseContractor: null, issuer: null, baseIssuer: null, familyMembers: [], generatedRequestId: null, generatedRequestNo: "" };
}
function createEmptyRestructure() {
  return { restructureType: "split", sourceContractorUid: "", sourceCbfbm: "", sourceCbfmc: "", targetContractorUid: "", targetCbfbm: "", targetCbfmc: "", newCbfbm: "", newCbfmc: "", status: "draft", reason: "", policyBasis: "", rightsSummary: "", contractDisposition: "", certificateDisposition: "", remark: "", members: [] };
}
function createEmptyAuthorization() {
  return { principalName: "", principalIdNo: "", agentName: "", agentIdNo: "", agentPhone: "", authorizedMatters: "代为办理二轮延包承包方调查确认、材料签署及相关事项。", validFrom: "", validTo: "", status: "active", remark: "" };
}

// ---- Helpers ----
function digitsOnly(value) { return String(value || "").replace(/\D/g, ""); }
function cloneParcel(parcel) { return JSON.parse(JSON.stringify(parcel || {})); }
function inferRequestType(row) { return row.changeType === "extinct" || ["extinct", "cancelled"].includes(row.resultStatus) ? "注销登记" : "变更登记"; }
function tagNameByCode(code) { return { whole_family_urbanized: "全家进城落户户", household_extinct: "整户消亡户", five_guarantees: "五保户", little_or_no_land: "无地少地户" }[code] || code; }
function downloadBlob(data, filename) { const url = URL.createObjectURL(data); const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url); }
function hasPendingSwapOperation() { return pendingOperations.value.some((op) => ["swap_parcels", "rollback_swap_parcels"].includes(op?.type)); }
function hasSavedSwapOperation() { return savedSwapChanges.value.length > 0; }

// ---- Code generation ----
async function buildNextContractorCode(currentCode = "") {
  const batchPrefix = digitsOnly(props.activeBatch?.regionCode || props.activeRegionCode);
  const currentPrefix = digitsOnly(currentCode);
  const prefix = batchPrefix || currentPrefix.slice(0, Math.min(currentPrefix.length, 14));
  if (!prefix) return "";
  if (prefix.length >= 18) return prefix.slice(0, 18);
  const suffixLength = 18 - prefix.length;
  // 编码唯一性按「该前缀下全部承包方」判断。原实现用 page_size=10000 拉任务列表，
  // 超出后端上限（200）会直接 422；改为专用接口，失败再退回循环分页。
  let codes = [];
  if (props.activeBatch) {
    try {
      const { data } = await fetchContractorCodes(props.activeBatch.id, { prefix });
      codes = collectContractorCodes(data.data);
    } catch {
      codes = collectContractorCodes(await fetchAllBatchTasks(props.activeBatch.id));
    }
  } else {
    codes = collectContractorCodes(props.tasks);
  }
  const existingSuffixes = codes.filter((c) => c.length === 18 && c.startsWith(prefix)).map((c) => Number(c.slice(prefix.length))).filter(Number.isFinite);
  const next = (existingSuffixes.length ? Math.max(...existingSuffixes) : 0) + 1;
  return `${prefix}${String(next).padStart(suffixLength, "0")}`.slice(0, 18);
}
async function generateResultContractorCode() {
  const code = await buildNextContractorCode(resultForm.code);
  if (!code) { ElMessage.warning("请先选择调查批次或输入区域前缀"); return; }
  resultForm.code = code;
}

// ---- Operation handlers ----
function handleOpDeregister() {
  if (hasPendingSwapOperation() || hasSavedSwapOperation()) { ElMessage.warning("该承包方存在未撤回的地块互换，不能注销"); return; }
  const validCount = (resultForm.familyMembers || []).filter((m) => !m._deleted).length;
  deregisterDialog.value.open(props.activeBatch.id, activeTask.value.contractorUid, resultForm.name, resultForm.code, validCount);
}
function handleOpSplitHousehold() {
  const validMembers = (resultForm.familyMembers || []).filter((m) => !m._deleted);
  const validParcels = (parcels.value || []).filter((item) => !["removed", "split_source"].includes(item.resultStatus));
  if (validMembers.length < 2) { ElMessage.warning("当前承包户只有一名家庭成员，没有可继续分配的成员，不能分户"); return; }
  if (validParcels.length < 2) { ElMessage.warning("当前承包户只有一块有效地块，没有可继续分配的地块，不能分户"); return; }
  splitHouseholdDialog.value.open(props.activeBatch.id, activeTask.value.contractorUid, validMembers, validParcels, resultForm.code, props.tasks);
}
function handleOpMergeHousehold() {
  const validMembers = (resultForm.familyMembers || []).filter((m) => !m._deleted);
  mergeHouseholdDialog.value.open(props.activeBatch.id, activeTask.value.contractorUid, resultForm.name, resultForm.code, validMembers, parcels.value, props.tasks, resultForm.address);
}
function handleOpSwapParcels() {
  swapParcelsDialog.value.open(props.activeBatch.id, activeTask.value.contractorUid, props.tasks, parcels.value, resultForm);
}
function handleOpRemoveParcel(dkbm) {
  removeParcelDialog.value.open(props.activeBatch.id, activeTask.value.contractorUid, parcels.value, dkbm);
}

// ---- Pending operations ----
function markParcelRemoved(dkbm, changeType, reason) {
  const index = parcels.value.findIndex((item) => item.dkbm === dkbm);
  if (index === -1) return;
  parcels.value[index] = { ...parcels.value[index], resultStatus: "removed", isChanged: true, changeType, changeReason: reason, _pending: true };
}

function applyPendingParcelPreview(operation) {
  const payload = operation.payload || {};
  if (operation.type === "deregister") {
    parcels.value = parcels.value.map((item) => ({ ...item, isChanged: true, changeType: "deregister", changeReason: payload.reason, _pending: true }));
    return;
  }
  if (operation.type === "add_parcel") {
    parcels.value = [...parcels.value, { ...payload, cbfbm: resultForm.code, cbfmc: resultForm.name, htmj: payload.htmj ?? payload.scmj, resultStatus: "added", isChanged: true, changeType: "add_parcel", changeReason: payload.reason, _pending: true }];
    return;
  }
  if (operation.type === "remove_parcel") { markParcelRemoved(payload.dkbm, "remove_parcel", payload.reason); return; }
  if (operation.type === "split_parcel") {
    const index = parcels.value.findIndex((item) => item.dkbm === payload.dkbm);
    if (index === -1) return;
    const source = cloneParcel(parcels.value[index]);
    parcels.value[index] = { ...source, resultStatus: "split_source", isChanged: true, changeType: "split_parcel", changeReason: payload.reason, _pending: true };
    const gen = Array.isArray(payload.generatedParcels) && payload.generatedParcels.length ? payload.generatedParcels : [{ dkbm: payload.newDkbm, dkmc: payload.newDkmc, scmj: payload.newScmj || payload.estimatedNewScmj || null, htmj: payload.newScmj || payload.estimatedNewScmj || null, geometry: payload.newGeometry || null }];
    parcels.value = [...parcels.value, ...gen.map((item) => ({ ...source, dkbm: item.dkbm, dkmc: item.dkmc, scmj: item.scmj ?? null, htmj: item.htmj ?? item.scmj ?? null, geometry: item.geometry || null, resultStatus: "split_generated", isChanged: true, changeType: "split_parcel", changeReason: payload.reason, _pending: true }))];
    return;
  }
  if (operation.type === "swap_parcels") {
    for (const dkbm of payload.sourceDkbms || []) markParcelRemoved(dkbm, "swap_parcels", payload.reason);
    const incoming = (payload.targetParcels || []).map((item) => ({ ...cloneParcel(item), cbfbm: resultForm.code, cbfmc: resultForm.name, isChanged: true, changeType: "swap_parcels", changeReason: payload.reason, _pending: true }));
    if (incoming.length) { const existing = new Set(parcels.value.map((item) => item.dkbm)); parcels.value = [...parcels.value, ...incoming.filter((item) => !existing.has(item.dkbm))]; }
    return;
  }
  if (operation.type === "rollback_swap_parcels") {
    for (const dkbm of payload.returnDkbms || []) markParcelRemoved(dkbm, "rollback_swap_parcels", payload.reason);
    for (const parcel of payload.restoreParcels || []) {
      const restored = { ...cloneParcel(parcel), cbfbm: resultForm.code, cbfmc: resultForm.name, resultStatus: "normal", isChanged: true, changeType: "rollback_swap_parcels", changeReason: payload.reason, _pending: true };
      const index = parcels.value.findIndex((item) => item.dkbm === restored.dkbm && item.resultStatus === "removed");
      if (index >= 0) { parcels.value[index] = restored; } else if (!parcels.value.some((item) => item.dkbm === restored.dkbm && !["removed", "split_source"].includes(item.resultStatus))) { parcels.value = [...parcels.value, restored]; }
    }
    return;
  }
  if (operation.type === "rollback_split_parcel") {
    const sourceIndex = parcels.value.findIndex((item) => item.dkbm === payload.sourceDkbm);
    if (sourceIndex >= 0) {
      const source = cloneParcel(parcels.value[sourceIndex]);
      parcels.value[sourceIndex] = { ...source, resultStatus: payload.sourceResultStatus || "normal", isChanged: Boolean(payload.sourceIsChanged), changeType: payload.sourceChangeType || "none", changeReason: payload.sourceChangeReason || "", _pending: true };
    }
    const generatedSet = new Set(payload.generatedDkbms || []);
    parcels.value = parcels.value.filter((item) => !generatedSet.has(item.dkbm));
  }
  if (operation.type === "rollback_remove_parcel") {
    const index = parcels.value.findIndex((item) => item.dkbm === payload.dkbm && isRemovedParcel(item));
    if (index >= 0) {
      parcels.value[index] = {
        ...parcels.value[index],
        resultStatus: payload.sourceResultStatus || "normal",
        isChanged: Boolean(payload.sourceIsChanged),
        changeType: payload.sourceChangeType || "none",
        changeReason: payload.sourceChangeReason || "",
        _pending: true,
      };
    }
  }
}
async function handleRollbackSplitHousehold() {
  try {
    await ElMessageBox.confirm("确定撤回本次分户吗？原承包户、成员和地块将恢复，分户生成的新承包户将删除。", "撤回分户", { type: "warning", confirmButtonText: "确认撤回", cancelButtonText: "取消" });
    rollbackingSplitHousehold.value = true;
    await rollbackSplitSurveyHousehold(props.activeBatch.id, resultForm.contractorUid);
    ElMessage.success("分户已撤回");
    emit("saved");
    close();
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error(error.response?.data?.detail || "撤回分户失败");
  } finally { rollbackingSplitHousehold.value = false; }
}

async function handleRollbackMergeHousehold() {
  try {
    await ElMessageBox.confirm("确定撤回本次合户吗？合户生成的新承包方将删除，所有原承包方、家庭成员和地块将恢复到合户前状态。", "撤回合户", { type: "warning", confirmButtonText: "确认撤回", cancelButtonText: "取消" });
    rollbackingMergeHousehold.value = true;
    await rollbackMergeSurveyHousehold(props.activeBatch.id, resultForm.contractorUid);
    ElMessage.success("合户已撤回");
    emit("saved");
    close();
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error(error.response?.data?.detail || "撤回合户失败");
  } finally { rollbackingMergeHousehold.value = false; }
}

// 打印当前承包方的整套地籍调查表：封面 + 发包方调查表 + 承包方调查表
// + 每地块一套（承包地块调查表 + 界址点坐标成果表）。
async function handlePrintCadastral() {
  const batchId = props.activeBatch?.id;
  const contractorUid = resultForm.contractorUid;
  if (!batchId || !contractorUid) {
    ElMessage.warning("缺少批次或承包方信息，无法打印地籍调查表");
    return;
  }
  printingCadastral.value = true;
  try {
    const { data } = await fetchCadastralSurvey(batchId, contractorUid);
    const html = data.data?.renderedHtml || "";
    if (!html) {
      ElMessage.warning("无可用数据");
      return;
    }
    const w = window.open("", "_blank", "width=1200,height=900");
    if (!w) {
      ElMessage.warning("浏览器拦截了打印窗口，请允许本站弹出窗口后重试");
      return;
    }
    w.document.write(html);
    w.document.close();
    // 等浏览器完成排版再唤起打印对话框（多地块时 HTML 较大）。
    setTimeout(() => w.print(), 800);
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "打印地籍调查表失败");
  } finally {
    printingCadastral.value = false;
  }
}

function handlePendingOperation(operation) {
  if (!operation?.type) return;
  pendingOperations.value.push(operation);
  applyPendingParcelPreview(operation);
  if (operation.type === "deregister") { resultForm.resultStatus = "cancelled"; resultForm.changeType = "deregister"; resultForm.changeReason = operation.payload?.reason || resultForm.changeReason; }
  if (operation.type === "merge_household") { resultForm.resultStatus = "cancelled"; resultForm.changeType = "merge_household"; resultForm.changeReason = operation.payload?.reason || resultForm.changeReason; }
  if (operation.type === "split_household") { resultForm.resultStatus = "cancelled"; resultForm.changeType = "split_household"; resultForm.changeReason = operation.payload?.reason || resultForm.changeReason; }
}

const undoableOperationTypes = new Set(["add_parcel", "remove_parcel", "split_parcel", "rollback_split_parcel", "swap_parcels", "rollback_swap_parcels", "rollback_remove_parcel", "deregister", "split_household", "merge_household"]);
function canUndoPendingOperation(operation) { return undoableOperationTypes.has(operation?.type); }

function pendingOperationLabelPreview(operation) {
  const p = operation?.payload || {};
  if (operation?.type === "deregister") return `注销承包方：${resultForm.name || resultForm.code || "-"}`;
  if (operation?.type === "swap_parcels") return `地块互换：本方 ${(p.sourceDkbms || []).length} 块，对方 ${(p.targetDkbms || []).length} 块`;
  if (operation?.type === "add_parcel") return `新增地块：${p.dkbm || p.dkmc || "未命名地块"}`;
  if (operation?.type === "remove_parcel") return `移除地块：${p.dkbm || "-"}`;
  if (operation?.type === "split_parcel") { const cnt = Array.isArray(p.generatedParcels) && p.generatedParcels.length ? p.generatedParcels.length : 1; return `切割地块：${p.dkbm || "-"} -> ${cnt} 块`; }
  if (operation?.type === "rollback_split_parcel") return `撤销切割：${p.sourceDkbm || "-"}`;
  if (operation?.type === "split_household") return `分户：原户注销，新增 ${(p.newHouseholds || []).length} 户`;
  if (operation?.type === "merge_household") return `合户：注销 ${(p.sourceContractorUids || []).length} 个原户，新增 ${p.newCbfmc || p.newCbfbm || "新户"}`;
  return operation?.type || "未命名操作";
}

async function reloadParcelPreviewFromPendingOperations() {
  await loadSurveyParcels();
  for (const op of pendingOperations.value) applyPendingParcelPreview(op);
}
async function handleUndoPendingOperationPreview(index) {
  const op = pendingOperations.value[index];
  if (!canUndoPendingOperation(op)) return;
  pendingOperations.value.splice(index, 1);
  if (["deregister", "split_household", "merge_household"].includes(op?.type)) {
    await reloadSurveyResult();
    ElMessage.success("待保存操作已撤销，承包户信息已恢复编辑");
    return;
  }
  await reloadParcelPreviewFromPendingOperations();
  ElMessage.success("待保存地块操作已撤销");
}
async function handleUndoPendingOperation(index) {
  const op = pendingOperations.value[index];
  if (!canUndoPendingOperation(op)) return;
  pendingOperations.value.splice(index, 1);
  await reloadParcelPreviewFromPendingOperations();
  if (["rollback_swap_parcels", "rollback_split_parcel", "rollback_remove_parcel"].includes(op?.type)) await loadSavedParcelChanges();
  ElMessage.success("待保存地块操作已撤销");
}
async function handleUndoPendingRemoveFromPanel(dkbm) {
  const index = pendingOperations.value.findIndex((op) => op.type === "remove_parcel" && op.payload?.dkbm === dkbm);
  if (index === -1) return;
  pendingOperations.value.splice(index, 1);
  await reloadParcelPreviewFromPendingOperations();
  ElMessage.success("待保存移除操作已撤销");
}

// ---- Parcel tab (map) ----
async function loadSurveyParcels() {
  if (!props.activeBatch || !activeTask.value) { parcels.value = []; parcelsLoaded.value = false; return; }
  parcelsLoading.value = true;
  try { const { data } = await fetchSurveyParcels(props.activeBatch.id, activeTask.value.contractorUid); parcels.value = data.data || []; parcelsLoaded.value = true; } catch { parcels.value = []; parcelsLoaded.value = false; } finally { parcelsLoading.value = false; }
}

function triggerFlash(dkbm) { flashDkbm.value = dkbm; if (flashTimer) clearTimeout(flashTimer); flashTimer = setTimeout(() => { flashDkbm.value = null; }, 2800); }

// ---- Diff / Change loading ----
async function loadDiffs() {
  if (!props.activeBatch || !activeTask.value) { diffRows.value = []; return; }
  diffLoading.value = true;
  try { const { data } = await fetchSurveyDiffs(props.activeBatch.id, activeTask.value.contractorUid, { page: 1, page_size: 300 }); diffRows.value = data.data.items; } finally { diffLoading.value = false; }
}

async function loadSavedParcelChanges() {
  if (!props.activeBatch || !activeTask.value) { savedSwapChanges.value = []; savedSplitChanges.value = []; return; }
  savedParcelChangeLoading.value = true;
  try {
    const { data } = await fetchSurveyChanges(props.activeBatch.id, { contractorUid: activeTask.value.contractorUid, page: 1, page_size: 200 });
    const items = data.data.items || [];
    savedSwapChanges.value = items.filter((i) => i.changeType === "swap_parcels" && i.changeStatus !== "rolled_back");
    savedSplitChanges.value = items.filter((i) => i.changeType === "split_parcel" && i.changeStatus !== "rolled_back");
    savedRemoveChanges.value = items.filter((i) => i.changeType === "remove_parcel" && i.changeStatus !== "rolled_back");
  } catch { savedSwapChanges.value = []; savedSplitChanges.value = []; savedRemoveChanges.value = []; } finally { savedParcelChangeLoading.value = false; }
}

async function handleRollbackSavedSwap(change) {
  if (!props.activeBatch || !activeTask.value || !change?.id) return;
  if (hasPendingOperations.value) { ElMessage.warning("请先处理顶部未保存操作，再撤回已保存互换"); return; }
  try {
    await ElMessageBox.confirm(`确定撤回这次已保存的地块互换吗？\n换出：${change.swappedOutText}\n换入：${change.swappedInText}`, "撤回已保存互换", { type: "warning", confirmButtonText: "加入待保存", cancelButtonText: "取消" });
    rollbackingSavedChangeId.value = change.id;
    const counterpartyCode = String(change.counterpartyLabel || "").trim();
    const counterpartyTask = props.tasks.find((i) => i.cbfbm === counterpartyCode);
    if (!counterpartyTask?.contractorUid) { ElMessage.warning("未找到对应承包方，请确认对方承包方编码是否正确。"); return; }
    const { data: cpData } = await fetchSurveyParcels(props.activeBatch.id, counterpartyTask.contractorUid);
    const restoreParcels = (cpData.data || []).filter((i) => (change.swappedOut || []).includes(i.dkbm)).map((i) => cloneParcel(i));
    const returnParcels = parcels.value.filter((i) => (change.swappedIn || []).includes(i.dkbm) && !["removed", "split_source"].includes(i.resultStatus));
    if (restoreParcels.length !== (change.swappedOut || []).length || returnParcels.length !== (change.swappedIn || []).length) { ElMessage.warning("当前页面地块状态已变化，请先重新打开调查录入后再试。"); return; }
    handlePendingOperation({ type: "rollback_swap_parcels", payload: { changeId: change.id, changeNo: change.changeNo, returnDkbms: [...(change.swappedIn || [])], restoreDkbms: [...(change.swappedOut || [])], restoreParcels, reason: `撤回互换 ${change.changeNo}` } });
    savedSwapChanges.value = savedSwapChanges.value.filter((i) => i.id !== change.id);
    ElMessage.success("已加入待保存，保存调查结果后才会正式落库");
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(error.response?.data?.detail || "撤回已保存互换失败"); } finally { rollbackingSavedChangeId.value = null; }
}

async function handleRollbackSavedSplit(change) {
  if (!props.activeBatch || !activeTask.value || !change?.id) return;
  if (hasPendingOperations.value) { ElMessage.warning("请先处理顶部未保存操作，再撤回已保存切割"); return; }
  try {
    await ElMessageBox.confirm(`确定撤回这次已保存的地块切割吗？\n源地块：${change.originalDkbm || "-"}\n生成地块：${change.generatedText || "-"}`, "撤回已保存切割", { type: "warning", confirmButtonText: "加入待保存", cancelButtonText: "取消" });
    rollbackingSavedChangeId.value = change.id;
    const sourceParcel = parcels.value.find((i) => i.dkbm === change.originalDkbm && i.resultStatus === "split_source");
    if (!sourceParcel) { ElMessage.warning("当前页面地块状态已变化，请先重新打开调查录入后再试。"); return; }
    const generatedParcels = parcels.value.filter((i) => (change.generatedDkbms || []).includes(i.dkbm) && !["removed", "split_source"].includes(i.resultStatus));
    if (generatedParcels.length !== (change.generatedDkbms || []).length) { ElMessage.warning("当前页面地块状态已变化，请先重新打开调查录入后再试。"); return; }
    handlePendingOperation({ type: "rollback_split_parcel", payload: { changeId: change.id, changeNo: change.changeNo, sourceDkbm: change.originalDkbm, sourceResultStatus: change.sourceResultStatus, sourceChangeType: change.sourceChangeType, sourceChangeReason: change.sourceChangeReason, sourceIsChanged: change.sourceIsChanged, generatedDkbms: [...(change.generatedDkbms || [])], reason: `撤回切割 ${change.changeNo}` } });
    savedSplitChanges.value = savedSplitChanges.value.filter((i) => i.id !== change.id);
    ElMessage.success("已加入待保存，保存调查结果后才会正式落库");
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(error.response?.data?.detail || "撤回已保存切割失败"); } finally { rollbackingSavedChangeId.value = null; }
}

async function handleRollbackSavedRemove(change) {
  if (!props.activeBatch || !activeTask.value || !change?.id) return;
  if (hasPendingOperations.value) { ElMessage.warning("请先处理顶部未保存操作，再撤回已保存移除"); return; }
  try {
    await ElMessageBox.confirm(`确定撤回这次已保存的地块移除吗？\n地块编码：${change.removedDkbm || "-"}`, "撤回已保存移除", { type: "warning", confirmButtonText: "加入待保存", cancelButtonText: "取消" });
    rollbackingSavedChangeId.value = change.id;
    const removedParcel = parcels.value.find((item) => item.dkbm === change.removedDkbm && item.resultStatus === "removed" && !item._pending);
    if (!removedParcel) { ElMessage.warning("当前页面地块状态已变化，请先重新打开调查录入后再试。"); return; }
    handlePendingOperation({
      type: "rollback_remove_parcel",
      payload: {
        changeId: change.id,
        changeNo: change.changeNo,
        dkbm: change.removedDkbm,
        cbfbm: removedParcel.cbfbm || change.cbfbm || resultForm.code,
        sourceResultStatus: change.sourceResultStatus || "normal",
        sourceChangeType: change.sourceChangeType || "none",
        sourceChangeReason: change.sourceChangeReason || "",
        sourceIsChanged: Boolean(change.sourceIsChanged),
        reason: `撤回移除 ${change.changeNo}`,
      },
    });
    savedRemoveChanges.value = savedRemoveChanges.value.filter((i) => i.id !== change.id);
    ElMessage.success("已加入待保存，保存调查结果后才会正式落库");
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(error.response?.data?.detail || "撤回已保存移除失败"); } finally { rollbackingSavedChangeId.value = null; }
}

// ---- Phase 2 ----
async function loadPhase2() {
  if (!props.activeBatch || !activeTask.value) { Object.assign(phase2, { tags: [], restructures: [], authorizations: [], attachments: [] }); return; }
  phase2Loading.value = true;
  try { const { data } = await fetchSurveyPhase2(props.activeBatch.id, activeTask.value.contractorUid); Object.assign(phase2, { tags: data.data.tags || [], restructures: data.data.restructures || [], authorizations: data.data.authorizations || [], attachments: data.data.attachments || [] }); } finally { phase2Loading.value = false; }
}

function resetPhase2Forms() {
  Object.assign(tagForm, { tagCode: "whole_family_urbanized", reason: "", policyBasis: "" });
  Object.assign(restructureForm, createEmptyRestructure());
  Object.assign(authorizationForm, createEmptyAuthorization(), { principalName: resultForm.name || "", principalIdNo: resultForm.idNo || "" });
  Object.assign(requestForm, { requestType: inferRequestType(resultForm), requestTitle: `${inferRequestType(resultForm)}-${resultForm.name || ""}-调查转办`, reason: resultForm.changeReason || "", note: resultForm.evidenceSummary || "" });
  selectedAttachmentFile.value = null;
  authorizationUploadTarget.value = null;
}

async function handleRefreshTags() { await refreshSurveyTags(props.activeBatch.id, activeTask.value.contractorUid); await loadPhase2(); }
async function handleCreateTag() {
  await createSurveyTag(props.activeBatch.id, activeTask.value.contractorUid, { ...tagForm, tagName: tagNameByCode(tagForm.tagCode) });
  ElMessage.success("人工标签已新增"); Object.assign(tagForm, { tagCode: "whole_family_urbanized", reason: "", policyBasis: "" }); await loadPhase2();
}
async function handleDisableTag(row) {
  const { value } = await ElMessageBox.prompt("请输入停用原因", "停用标签", { inputType: "textarea", inputValidator: (text) => Boolean(text?.trim()) || "请输入停用原因" });
  await disableSurveyTag(row.id, { disabledReason: value.trim() }); await loadPhase2();
}
function fillRestructureMembers() {
  restructureForm.sourceCbfbm = resultForm.code; restructureForm.sourceCbfmc = resultForm.name;
  restructureForm.members = resultForm.familyMembers.map((item) => ({ memberUid: item.memberUid, memberName: item.name, memberIdNo: item.idNo, fromCbfbm: resultForm.code, toCbfbm: restructureForm.targetCbfbm || restructureForm.newCbfbm, actionType: "move", rightsDisposition: item.rightsDisposition || "", remark: "" }));
}
async function handleSaveRestructure() {
  if (!restructureForm.reason?.trim()) { ElMessage.warning("请输入分合户原因"); return; }
  await createSurveyRestructure(props.activeBatch.id, activeTask.value.contractorUid, { ...restructureForm, sourceCbfbm: restructureForm.sourceCbfbm || resultForm.code, sourceCbfmc: restructureForm.sourceCbfmc || resultForm.name });
  ElMessage.success("分合户专项已保存"); Object.assign(restructureForm, createEmptyRestructure()); await loadPhase2();
}
async function handleDeleteRestructure(row) { await ElMessageBox.confirm(`确定删除专项 ${row.restructureNo} 吗？`, "删除分合户专项", { type: "warning" }); await deleteSurveyRestructure(row.id); await loadPhase2(); }
async function handleSaveAuthorization() {
  if (!authorizationForm.principalName || !authorizationForm.agentName || !authorizationForm.authorizedMatters) { ElMessage.warning("请填写委托人、受托人和委托事项"); return; }
  await createSurveyAuthorization(props.activeBatch.id, activeTask.value.contractorUid, authorizationForm);
  ElMessage.success("授权委托已保存"); Object.assign(authorizationForm, createEmptyAuthorization(), { principalName: resultForm.name || "", principalIdNo: resultForm.idNo || "" }); await loadPhase2();
}
function openAuthorizationFile(row) { authorizationUploadTarget.value = row; authorizationFileInput.value?.click(); }
async function handleAuthorizationFileChange(event) {
  const file = event.target.files?.[0]; if (!file || !authorizationUploadTarget.value) return;
  const formData = new FormData(); formData.append("file", file);
  await uploadSurveyAuthorizationFile(authorizationUploadTarget.value.id, formData);
  event.target.value = ""; authorizationUploadTarget.value = null; await loadPhase2();
}
async function handleDownloadAuthorizationTemplate(row) { const { data } = await downloadSurveyAuthorizationTemplate(row.id); downloadBlob(data, `${row.authorizationNo}_授权委托书.txt`); }
async function handleDownloadAuthorizationFile(row) { const { data } = await downloadSurveyAuthorizationFile(row.id); downloadBlob(data, row.originalName || `${row.authorizationNo}_file`); }
async function handleRevokeAuthorization(row) {
  const { value } = await ElMessageBox.prompt("请输入作废原因", "作废授权委托", { inputType: "textarea", inputValidator: (text) => Boolean(text?.trim()) || "请输入作废原因" });
  await revokeSurveyAuthorization(row.id, { revokeReason: value.trim() }); await loadPhase2();
}
function handleAttachmentFileChange(event) { selectedAttachmentFile.value = event.target.files?.[0] || null; }
// 类别选项来自「附件组管理」页；拿不到就退回本地兜底，别让上传功能跟着挂掉。
async function loadAttachmentCategories() {
  try {
    const { data } = await fetchSurveyAttachmentCategories();
    const items = (data.data || []).filter((item) => item.value);
    if (items.length) attachmentCategoryOptions.value = items;
  } catch { /* 保持兜底选项 */ }
  if (!attachmentCategoryOptions.value.some((item) => item.value === attachmentCategory.value)) {
    attachmentCategory.value = attachmentCategoryOptions.value[0]?.value || "";
  }
}
async function handleUploadAttachment() {
  if (!attachmentCategory.value) { ElMessage.warning("请先选择附件类型（可在「附件组管理」中配置）"); return; }
  if (!selectedAttachmentFile.value) { ElMessage.warning("请选择附件文件"); return; }
  const formData = new FormData(); formData.append("category", attachmentCategory.value); formData.append("description", attachmentDescription.value || ""); formData.append("file", selectedAttachmentFile.value);
  await uploadSurveyAttachment(props.activeBatch.id, activeTask.value.contractorUid, formData);
  selectedAttachmentFile.value = null; attachmentDescription.value = ""; await loadPhase2();
}
async function handleDownloadAttachment(row) { const { data } = await downloadSurveyAttachment(row.id); downloadBlob(data, row.originalName); }

// 附件预览：图片 / PDF 直接在弹窗内渲染；其余类型弹窗给出提示并提供下载入口。
// 与「业务申请附件」共用同一个预览弹窗，只是把取数换成调查附件的下载接口。
function handlePreviewAttachment(row) {
  const items = phase2.attachments;
  const index = items.findIndex((item) => item.id === row.id);
  attachmentPreviewIndex.value = index >= 0 ? index : 0;
  previewAttachment.value = index >= 0 ? items[index] : row;
  previewAttachmentVisible.value = true;
}
// 上一页 / 下一页：只换 source，弹窗内自行按新 source 重新取数。
function stepAttachmentPreview(offset) {
  const items = phase2.attachments;
  const next = attachmentPreviewIndex.value + offset;
  if (next < 0 || next >= items.length) return;
  attachmentPreviewIndex.value = next;
  previewAttachment.value = items[next];
}
function loadAttachmentPreviewBlob(item) {
  return previewSurveyAttachment(item.id);
}
async function handleDeleteAttachment(row) { await ElMessageBox.confirm(`确定删除附件 ${row.originalName} 吗？`, "删除调查附件", { type: "warning" }); await deleteSurveyAttachment(row.id); await loadPhase2(); }
async function handleGenerateRequest() {
  if (!requestForm.requestType) { ElMessage.warning("请选择业务类型"); return; }
  const { data } = await generateSurveyRequest(props.activeBatch.id, activeTask.value.contractorUid, requestForm);
  ElMessage.success(`已生成业务申请 ${data.data.serialNo}`);
  const result = await fetchSurveyResult(props.activeBatch.id, activeTask.value.contractorUid);
  Object.assign(resultForm, result.data.data, { familyMembers: (result.data.data.familyMembers || []).map((item) => ({ ...item })) });
}

// ---- Save / Confirm ----
async function handleSaveResult() {
  if (!props.activeBatch || (!activeTask.value && !isCreatingContractorResult.value)) return;
  resultForm.code = digitsOnly(resultForm.code).slice(0, 18);
  if (resultForm.code.length !== 18) { ElMessage.warning("承包方编码必须为18位数字"); return; }
  if (!resultForm.name?.trim() || !resultForm.address?.trim()) { ElMessage.warning("请填写承包方名称和地址"); return; }
  // 证件号码（承包方 + 全部有效家庭成员）由录入面板统一校验，口径见 ContractorMemberPanel。
  // `??` 兜底：万一面板 ref 尚未就绪，至少保证承包方证件号码非空。
  const idNoProblem = contractorMemberPanel.value?.validateIdNos?.()
    ?? (resultForm.idNo?.trim() ? "" : "承包方证件号码：请输入证件号码");
  if (idNoProblem) { ElMessage.warning(idNoProblem.split("\n").join("；")); return; }
  savingResult.value = true;
  creatingContractor.value = isCreatingContractorResult.value;
  try {
    const allMembers = resultForm.familyMembers || [];
    const validMembers = allMembers.filter((m) => !m._deleted);
    const cleanMembers = validMembers.map(({ _deleted, _isNew, ...rest }) => rest);
    const deletedMembers = allMembers.filter((m) => m._deleted && m.memberUid).map((m) => ({ memberUid: m.memberUid, changeReason: m.changeReason || resultForm.changeReason || "去世" }));
    const { issuer, baseIssuer, ...contractorPayload } = resultForm;
    let contractorUid = activeTask.value?.contractorUid;
    if (isCreatingContractorResult.value) {
      const { data } = await createSurveyContractor(props.activeBatch.id, {
        code: contractorPayload.code.trim(), typeCode: contractorPayload.typeCode, name: contractorPayload.name.trim(),
        idType: contractorPayload.idType, idNo: contractorPayload.idNo.trim(), address: contractorPayload.address.trim(),
        postcode: contractorPayload.postcode?.trim() || "000000", mobile: contractorPayload.mobile?.trim() || null,
        groupRegionCode: contractorPayload.groupRegionCode || props.activeBatch.regionCode || props.activeRegionCode || "",
        groupRegionName: contractorPayload.groupRegionName || props.activeBatch.regionName || props.activeRegionLabel || "",
        surveyDate: contractorPayload.surveyDate, surveyorName: contractorPayload.surveyorName, remark: contractorPayload.remark,
      });
      contractorUid = data.data.contractorUid;
    }
    await updateSurveyResult(props.activeBatch.id, contractorUid, { ...contractorPayload, contractorUid, familyMembers: cleanMembers, deletedMembers, pendingOperations: pendingOperations.value });
    ElMessage.success(isCreatingContractorResult.value ? "承包方调查数据已新增" : "调查结果已保存");
    pendingOperations.value = [];
    close();
    emit("saved");
  } catch (error) { ElMessage.error(error.response?.data?.detail || (isCreatingContractorResult.value ? "新增承包方失败" : "保存调查结果失败")); } finally { savingResult.value = false; creatingContractor.value = false; }
}

async function handleConfirmCurrent() {
  if (!props.activeBatch || !activeTask.value) return;
  confirmingResult.value = true;
  try { await confirmSurveyResult(props.activeBatch.id, activeTask.value.contractorUid); ElMessage.success("调查结果已确认"); close(); emit("confirmed"); } catch (error) { ElMessage.error(error.response?.data?.detail || "确认失败"); } finally { confirmingResult.value = false; }
}

async function reloadSurveyResult() {
  if (!props.activeBatch || !activeTask.value) return;
  try {
    const { data } = await fetchSurveyResult(props.activeBatch.id, activeTask.value.contractorUid);
    Object.assign(resultForm, createEmptyResult(), data.data, { familyMembers: (data.data.familyMembers || []).map((item) => ({ ...item })) });
    await loadDiffs();
    if (parcelsLoaded.value || isPanelMounted("parcels")) {
      await loadSavedParcelChanges();
      await loadSurveyParcels();
    }
    plotSketchRefreshKey.value += 1;
  } catch { /* silently ignore */ }
}

// ---- Open / Close ----
async function openForResult(batch, row) {
  isCreatingContractorResult.value = false; activeTask.value = row; selectedParcel.value = null; parcels.value = []; parcelsLoaded.value = false;
  previewAttachmentVisible.value = false; previewAttachment.value = null; attachmentPreviewIndex.value = -1;
  pendingOperations.value = []; savedSwapChanges.value = []; savedSplitChanges.value = []; savedRemoveChanges.value = []; savedParcelChangeLoading.value = false; rollbackingSavedChangeId.value = null;
  const { data } = await fetchSurveyResult(row.batchId, row.contractorUid);
  Object.assign(resultForm, createEmptyResult(), data.data, { familyMembers: (data.data.familyMembers || []).map((item) => ({ ...item })) });
  resetPhase2Forms(); openPanels.value = ["contractor"]; openedPanels.value = ["contractor"]; openAuxPanels.value = []; emit("update:modelValue", true);
  await loadDiffs(); await loadPhase2();
}

function openForCreate(batch) {
  isCreatingContractorResult.value = true; activeTask.value = null; selectedParcel.value = null; parcels.value = [];
  diffRows.value = []; savedSwapChanges.value = []; savedSplitChanges.value = []; savedRemoveChanges.value = []; savedParcelChangeLoading.value = false;
  pendingOperations.value = []; rollbackingSavedChangeId.value = null;
  Object.assign(resultForm, createEmptyResult(), { code: batch?.regionCode || props.activeRegionCode || "", groupRegionCode: batch?.regionCode || props.activeRegionCode || "", groupRegionName: batch?.regionName || props.activeRegionLabel || "", resultStatus: "added", changeType: "add_contractor", isChanged: false });
  resetPhase2Forms(); openPanels.value = ["contractor"]; openedPanels.value = ["contractor"]; openAuxPanels.value = []; emit("update:modelValue", true);
}

function close() {
  emit("update:modelValue", false); isCreatingContractorResult.value = false;
  previewAttachmentVisible.value = false; previewAttachment.value = null; attachmentPreviewIndex.value = -1;
  pendingOperations.value = []; savedSwapChanges.value = []; savedSplitChanges.value = []; savedRemoveChanges.value = []; savedParcelChangeLoading.value = false; rollbackingSavedChangeId.value = null;
}

// ---- Watchers ----
watch(() => props.modelValue, (visible) => {
  if (visible) { void loadAttachmentCategories(); return; }
  selectedParcel.value = null;
});

defineExpose({ openForResult, openForCreate });
</script>

<style scoped>
.survey-toolbar { display: flex; align-items: center; flex-wrap: wrap; row-gap: 8px; margin-bottom: 12px; }
.toolbar-print { margin-left: auto; }
.survey-dialog-form { margin-top: 16px; }
.snapshot-member-title { color: #334155; font-size: 14px; font-weight: 700; margin: 16px 0 10px; }
.snapshot-changed-value { background: #fef3c7; border: 1px solid #f59e0b; border-radius: 4px; color: #92400e; display: inline-block; font-weight: 600; line-height: 1.5; padding: 0 6px; }
.phase2-actions, .phase2-upload { align-items: center; display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.phase2-form { margin: 14px 0; }
.phase2-submit { margin-top: 12px; }
.pending-operation-alert { margin-bottom: 12px; }
.pending-operation-list { display: flex; flex-direction: column; gap: 8px; margin: -4px 0 12px; }
.pending-operation-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border: 1px solid #f3d19e; border-radius: 8px; background: #fdf6ec; }
.pending-operation-text { color: #8a5a12; font-size: 13px; }

/* ---- 折叠面板：主数据区与「调查附件」区共用同一套样式，卡片式、与正文明确分区 ---- */
.survey-collapse {
  border: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 12px;
}

.survey-collapse :deep(.el-collapse-item) {
  overflow: hidden;
  background: #fff;
  border: 1px solid rgba(56, 122, 196, 0.28);
  border-radius: var(--radius-xl);
  box-shadow: 0 1px 4px rgba(25, 74, 128, 0.07);
}

.survey-collapse :deep(.el-collapse-item:last-child) { margin-bottom: 0; }

.survey-collapse :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 46px;
  padding: 10px 16px;
  border-bottom: 1px solid transparent;
  border-left: 4px solid var(--accent);
  background: #eef4fb;
  color: var(--text);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.5;
}

.survey-collapse :deep(.el-collapse-item__header:hover) { background: #e2effc; }

.survey-collapse :deep(.el-collapse-item__header.is-active) {
  border-bottom-color: rgba(56, 122, 196, 0.28);
  background: #d7e8fa;
}

.survey-collapse :deep(.el-collapse-item__arrow) { color: var(--accent); font-weight: 700; }

.survey-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
  background: transparent;
}

.survey-collapse :deep(.el-collapse-item__content) {
  padding: 16px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.6;
}

.survey-collapse :deep(.el-collapse-item__title) { color: inherit; font-size: inherit; font-weight: inherit; }

.survey-collapse :deep(.el-collapse-item.is-disabled .el-collapse-item__header) {
  border-left-color: #c3cfdd;
  background: #eef1f5;
}

.survey-collapse :deep(.el-collapse-item.is-disabled .el-collapse-item__title) { color: var(--muted); }

/* 附属区与主数据区同一套样式，只在间距上留一道分隔；不另设配色，保持两处观感一致。 */
.survey-collapse--aux { margin-top: 6px; }
</style>


