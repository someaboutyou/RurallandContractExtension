<template>
  <el-dialog :model-value="modelValue" :title="resultDialogTitle" width="96vw" top="2vh" class="contractor-result-dialog" append-to-body destroy-on-close @update:model-value="$emit('update:modelValue', $event)">
    <div v-if="!isCreatingContractorResult" class="survey-toolbar">
      <el-button type="danger" plain size="small" :disabled="dataReadOnly" @click="handleOpDeregister">注销承包方</el-button>
      <el-button plain size="small" :disabled="dataReadOnly" @click="handleOpSplitHousehold">分户</el-button>
      <el-button v-if="canRollbackSplitHousehold" type="warning" plain size="small" :loading="rollbackingSplitHousehold" @click="handleRollbackSplitHousehold">撤回分户</el-button>
      <el-button plain size="small" :disabled="dataReadOnly" @click="handleOpMergeHousehold">合并户</el-button>
      <el-button v-if="canRollbackMergeHousehold" type="warning" plain size="small" :loading="rollbackingMergeHousehold" @click="handleRollbackMergeHousehold">撤回合户</el-button>
      <span class="toolbar-print">
        <el-button type="primary" plain size="small" :loading="printingCadastral" :disabled="isCreatingContractorResult" @click="handlePrintCadastral">打印地籍调查表</el-button>
        <el-button type="primary" plain size="small" :loading="printingLandSheet" :disabled="isCreatingContractorResult" @click="handlePrintLandSheet">生成承包地变化摸底表</el-button>
        <el-button type="primary" plain size="small" :loading="printingMemberSheet" :disabled="isCreatingContractorResult" @click="handlePrintMemberSheet">生成成员变化摸底表</el-button>
      </span>
      <span v-if="dataReadOnly" class="toolbar-lock-hint">（{{ readOnlyHint }}）</span>
    </div>
    <el-alert v-if="pendingOperations.length" type="warning" :closable="false" show-icon class="pending-operation-alert" :title="`当前有 ${pendingOperations.length} 项操作尚未保存，请点击保存调查结果统一提交。`" />
    <div v-if="pendingOperations.length" class="pending-operation-list">
      <div v-for="(operation, index) in pendingOperations" :key="`${operation.type}-${index}`" class="pending-operation-item">
        <span class="pending-operation-text">{{ pendingOperationLabelPreview(operation) }}</span>
        <el-button v-if="canUndoPendingOperation(operation)" link type="danger" size="small" @click="handleUndoPendingOperationPreview(index)">撤销</el-button>
      </div>
    </div>
    <div class="survey-panel-switch">
      <el-button
        v-for="panel in panelButtons"
        :key="panel.name"
        size="small"
        class="panel-tab"
        :class="{ 'is-active': activePanel === panel.name }"
        :title="panel.label"
        :disabled="panel.disabled"
        @click="switchPanel(panel.name)"
      >
        {{ panel.label }}
      </el-button>
    </div>

    <div class="survey-panel-body">
      <section v-show="activePanel === 'contractor'" class="survey-panel-section">
        <ContractorMemberPanel ref="contractorMemberPanel" :batch-id="activeBatch?.id" :contractor-uid="resultForm.contractorUid" :result="resultForm" :changed-fields="computedChangedFields" :readonly="dataReadOnly" :can-generate-code="!dataReadOnly && resultForm.resultStatus === 'added'" @generate-code="generateResultContractorCode" />
      </section>

      <section v-show="activePanel === 'parcels'" class="survey-panel-section">
        <ParcelInfoPanel v-if="isPanelMounted('parcels')" :batch-id="activeBatch?.id" :contractor-uid="resultForm.contractorUid" :parcels="parcelsForPanel" :highlight-dkbm="focusParcelDkbm" :persisted-dkbms="persistedParcelDkbms" :parcels-loading="parcelsLoading" :can-manage="canManage && canWrite" :is-result-locked="dataReadOnly" :saved-swap-records="savedSwapRecords" :saved-split-records="savedSplitRecords" :saved-remove-records="savedRemoveRecords" :can-rollback-saved-parcel-change="canRollbackSavedParcelChange" :rollback-change-loading-id="rollbackingSavedChangeId" :persisting-dkbm="persistingParcelDkbm" @swap-parcels="handleOpSwapParcels" @add-parcel="handlePendingOperation" @split-parcel="handlePendingOperation" @remove-parcel="handleOpRemoveParcel" @rollback-saved-swap="handleRollbackSavedSwap" @rollback-saved-split="handleRollbackSavedSplit" @rollback-saved-remove="handleRollbackSavedRemove" @undo-pending-remove="handleUndoPendingRemoveFromPanel" @persist-parcel="handlePersistPendingParcel" />
      </section>

      <section v-show="activePanel === 'plotSketchMap'" class="survey-panel-section">
        <PlotSketchMapPanel v-if="isPanelMounted('plotSketchMap')" :batch-id="activeBatch?.id" :contractor-uid="resultForm.contractorUid" :refresh-key="plotSketchRefreshKey" />
      </section>

      <section v-show="activePanel === 'contract'" class="survey-panel-section">
        <ContractInfoPanel
          v-if="isPanelMounted('contract')"
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
          :can-manage="canManage && canWrite"
          :batch-status="activeBatch?.status || 'active'"
        />
      </section>

      <section v-show="activePanel === 'aux'" class="survey-panel-section">
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
            <el-form-item label="业务类型" required><el-select v-model="requestForm.requestType" size="small"><el-option label="变更登记" value="变更登记" /><el-option label="注销登记" value="注销登记" /><el-option label="首次登记" value="首次登记" /></el-select></el-form-item>
            <el-form-item label="申请标题"><el-input v-model="requestForm.requestTitle" size="small" /></el-form-item>
            <el-form-item class="form-span-2" label="申请原因"><el-input v-model="requestForm.reason" type="textarea" :rows="2" size="small" /></el-form-item>
          </div>
          <el-button type="success" size="small" @click="handleGenerateRequest">生成业务申请</el-button>
        </el-form>
      </section>
    </div>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button v-if="canManage && canWrite && !isResultLocked && (!savedTerminated || terminalPendingOperation)" :loading="savingResult || creatingContractor" type="success" @click="handleSaveResult">{{ isCreatingContractorResult ? "新增并保存" : "保存调查结果" }}</el-button>
      <!-- ⛔ 有待保存操作时不给点「确认调查结果」（2026-09-27 用户报 bug 后补）：
           确认接口 confirmSurveyResult(batchId, contractorUid) 根本不接收 pendingOperations，
           点下去 = 待保存的互换/撤回互换被静默丢弃 + 本户立刻被锁成 confirmed（不可逆）。
           用户实测：撤销互换（待保存）→ 点「确认调查结果」⇒ 互换没撤掉、户还被确认。
           口径与同一批「撤回已保存…」按钮的 !hasPendingOperations 保持一致。 -->
      <el-button v-if="canManage && canWrite && !isCreatingContractorResult && !dataReadOnly && !hasPendingOperations && CONFIRMABLE_SURVEY_STATUSES.includes(resultForm.surveyStatus)" :loading="confirmingResult" type="primary" @click="handleConfirmCurrent">确认调查结果</el-button>
      <!-- 撤回确认：仅当前用户拥有 survey_result.unconfirm 权限、且本户已确认为 visible。
           不依赖 !dataReadOnly（confirmed 时 dataReadOnly 恒为 true），否则按钮永远出不来。 -->
      <el-button v-if="canUnconfirm && resultForm.surveyStatus === 'confirmed'" :loading="unconfirmingResult" type="warning" @click="handleUnconfirmCurrent">撤回确认</el-button>
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
import { validateMemberSheetFlow } from "../../../config/surveySheets";
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
  confirmSurveyResult, unconfirmSurveyResult, createSurveyAuthorization, createSurveyContractor,
  createSurveyRestructure, createSurveyTag, deleteSurveyAttachment,
  deleteSurveyRestructure, disableSurveyTag, downloadSurveyAttachment,
  downloadSurveyAuthorizationFile, downloadSurveyAuthorizationTemplate,
  fetchSurveyChanges, fetchSurveyDiffs, fetchSurveyParcels, fetchSurveyPhase2,
  fetchSurveyAttachmentCategories,
  fetchSurveyResult, generateSurveyRequest, refreshSurveyTags,
  fetchContractorCodes, fetchCadastralSurvey,
  previewSurveyAttachment,
  revokeSurveyAuthorization, updateSurveyResult, uploadSurveyAttachment,
  persistSurveyPendingOperation,
  uploadSurveyAuthorizationFile, rollbackSplitSurveyHousehold, rollbackMergeSurveyHousehold,
  printLandChangeSheet, printMemberChangeSheet,
} from "../../../api/survey";
import { collectContractorCodes, fetchAllBatchTasks } from "../../../utils/surveyCandidates";
import { FALLBACK_SURVEY_ATTACHMENT_CATEGORIES, surveyAttachmentCategoryLabel } from "../../../config/surveyAttachmentCategories";
import { CONFIRMABLE_SURVEY_STATUSES } from "../../../config/surveyStatus";
import { useAuthStore } from "../../../stores/auth";
import { applySurveyActorDefaults } from "../../../utils/surveyActorDefaults";

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
const emit = defineEmits(["update:modelValue", "saved", "confirmed", "openContractor"]);

const authStore = useAuthStore();


// ---- State ----
const savingResult = ref(false);
const creatingContractor = ref(false);
const confirmingResult = ref(false);
const unconfirmingResult = ref(false);
const printingCadastral = ref(false);
const activeTask = ref(null);
const isCreatingContractorResult = ref(false);
// 按钮切换面板：activePanel = 当前显示的面板；openedPanels = 打开过一次的面板。
// 地块/示意图/合同三个面板在 mount 时就会立刻拉数据，所以用 v-if 卡住首次打开 ——
// 没点过就不挂载，维持 lazy 加载、避免一次拉全部数据。
const activePanel = ref("contractor");
const openedPanels = ref(["contractor"]);
function isPanelMounted(name) { return openedPanels.value.includes(name); }
const panelButtons = computed(() => {
  const buttons = [
    { name: "contractor", label: `承包方及家庭成员（${resultForm.familyMembers.length}人）`, disabled: false },
    { name: "parcels", label: "地块信息", disabled: isCreatingContractorResult.value },
    { name: "plotSketchMap", label: "承包地块示意图", disabled: isCreatingContractorResult.value },
    { name: "contract", label: "合同信息", disabled: isCreatingContractorResult.value },
  ];
  if (!isCreatingContractorResult.value) {
    buttons.push({ name: "aux", label: "调查附件&转业业务申请", disabled: false });
  }
  return buttons;
});
async function switchPanel(name) {
  activePanel.value = name;
  if (!openedPanels.value.includes(name)) openedPanels.value = [...openedPanels.value, name];
  if (name === "parcels") {
    // 地图容器需要先完成挂载，再初始化 OpenLayers；同时补拉地块数据。
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
// 从「承包地块管理」双击进入时带过来的地块编码：地块清单里加重显示，地图定位到该地块。
const focusParcelDkbm = ref("");
const parcelsLoading = ref(false);
const flashDkbm = ref(null);
let flashTimer = null;

const diffRows = ref([]);
const diffLoading = ref(false);
const savedSwapChanges = ref([]);
const savedSplitChanges = ref([]);
const savedRemoveChanges = ref([]);
const savedParcelChangeLoading = ref(false);
// 服务端**已经落库**的地块编码集合，每次 loadSurveyParcels 重算。
// 用途：`parcels` 里混着两类行 —— 服务端返回的现势行，和前端"待保存预览"行
// （新增地块 / 切割生成 / 互换换入）。后者在库里根本还没有对应记录，
// 界址点 / 界址线维护（后端从 survey_dk_result.geom 解析图形）必然 404，
// 所以 ParcelInfoPanel 要靠这个集合判断"这块地到底存没存过"。
const persistedParcelDkbms = ref([]);
// 操作列「保存」按钮正在落库的地块编码（同一时刻只可能有一个）。
const persistingParcelDkbm = ref("");
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
const isResultLocked = computed(() => props.activeBatch?.status === "finished" || (!isCreatingContractorResult.value && (resultForm.surveyStatus === "confirmed" || resultForm.isLocked)));
// 撤回确认权限：当前用户是否持有 survey_result.unconfirm（默认仅平台管理员）。
// 与后端端点 require_permission("survey_result.unconfirm") 同源。
const canUnconfirm = computed(() => authStore.hasPermission("survey_result.unconfirm"));
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

const readOnlyHint = computed(() => {
  if (!props.canManage) return "当前账号无编辑权限，只能查看详细信息";
  if (props.activeBatch?.status === "finished") return "调查批次已结束，只能查看详细信息";
  if (props.canWrite === false) return "该承包方未分配给你，只能查看详细信息";
  if (resultForm.isLocked) return "承包方已锁定，只能查看详细信息";
  if (resultForm.surveyStatus === "confirmed") return "调查结果已确认，只能查看详细信息";
  if (savedTerminated.value) return "该承包方已注销或已分户/合户，只能查看详细信息";
  if (terminalPendingOperation.value) return "存在未保存的终结操作，只能查看详细信息";
  return "当前为只读模式，只能查看详细信息";
});
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
    // 互换前的地块变更态（后端快照，按 dkbm 存）。撤回互换要把地块还原成互换前的样子，
    // 所以预览也要按这里的原值回填，不能一律写 isChanged/rollback_swap_parcels。
    const sourceStates = bs.source_relation_states && typeof bs.source_relation_states === "object" ? bs.source_relation_states : {};
    return { ...item, swappedOut, swappedIn, sourceStates, swappedOutText: swappedOut.length ? swappedOut.join("、") : "-", swappedInText: swappedIn.length ? swappedIn.join("、") : "-", counterpartyLabel: as.counterparty || "-" };
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
    // remove_parcel 的快照（parcel/relation 列名快照 + geometry），
    // 用于合成「已移除」展示行与撤回时的待保存预览行。
    const parcelSnapshot = bs.parcel && typeof bs.parcel === "object" ? bs.parcel : {};
    const relationSnapshot = bs.relation && typeof bs.relation === "object" ? bs.relation : {};
    return {
      ...item,
      removedDkbm,
      removedDkmc: String(parcelSnapshot.dkmc || "").trim(),
      removedScmj: parcelSnapshot.scmj ?? null,
      removedGeometry: bs.geometry || null,
      relationCbfbm: String(relationSnapshot.cbfbm || "").trim(),
      sourceResultStatus: bs.source_result_status || "normal",
      sourceChangeType: bs.source_change_type || "none",
      sourceChangeReason: bs.source_change_reason || "",
      sourceIsChanged: Boolean(bs.source_is_changed),
      label: removedDkbm || "-",
    };
  }),
);

// ---- 已保存移除的展示行 ----
// 后端 /parcels 刻意过滤 result_status='removed'（"移除本批次新增地块"= 净零变化，
// 不能把已移除地块重新暴露给前端），所以「撤回移除」按钮没有可挂的行。
// 这里按变更记录快照**合成**已移除行：仅用于列表展示与撤回入口，
// 不带图形（不画到地图）、不参与任何"现势地块"判定（resultStatus='removed' 天然被排除）。
const removedSyntheticParcels = computed(() =>
  savedRemoveRecords.value
    .filter((item) => item.removedDkbm)
    .map((item) => ({
      dkbm: item.removedDkbm,
      dkmc: item.removedDkmc || "",
      scmj: item.removedScmj,
      cbfbm: item.relationCbfbm || resultForm.code,
      cbfmc: resultForm.name,
      resultStatus: "removed",
      isChanged: true,
      changeType: "remove_parcel",
      changeReason: item.reason || "",
      _syntheticRemoved: true,
    }))
    .filter((row, index, list) => list.findIndex((i) => i.dkbm === row.dkbm) === index)
);

const parcelsForPanel = computed(() => {
  const existing = new Set(parcels.value.map((item) => item?.dkbm).filter(Boolean));
  const extra = removedSyntheticParcels.value.filter((row) => !existing.has(row.dkbm));
  return extra.length ? [...parcels.value, ...extra] : parcels.value;
});

// ---- Factories ----
function createEmptyResult() {
  return { contractorUid: "", code: "", typeCode: "1", name: "", idType: "1", idNo: "", address: "", postcode: "000000", mobile: "", memberCount: 0, groupRegionCode: "", groupRegionName: "", surveyDate: "", surveyorName: "", surveyNote: "", publicNoticeNote: "", publicNoticeRecorder: "", publicNoticeReviewDate: "", publicNoticeReviewer: "", surveyStatus: "surveyed", resultStatus: "normal", isLocked: false, changeType: "none", changeReason: "", policyBasis: "", evidenceSummary: "", remark: "", isTerminal: false, baseContractor: null, issuer: null, baseIssuer: null, familyMembers: [], generatedRequestId: null, generatedRequestNo: "" };
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

// ---- 「本次调查」的默认调查员 / 调查日期 ----
// 调查员 / 调查日期默认取「本次」：口径在 utils/surveyActorDefaults.js（发包方侧共用同一份）。
// 这里只管把本组件的入参喂给它：快照取 baseContractor，只读判定取 dataReadOnly。
function applyCurrentSurveyDefaults() {
  const task = activeTask.value;
  applySurveyActorDefaults(resultForm, {
    base: resultForm.baseContractor,
    readonly: dataReadOnly.value,
    displayName: authStore.displayName,
    // 已有调查成果的户（导入/保存过）保留库里的调查员与日期，不再改写成当前用户/今天。
    alreadySurveyed: Boolean(task?.taskStatus && task.taskStatus !== "not_started"),
  });
}

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
      // 撤回互换 = 把地块还原成互换前的样子，变更态也要按互换前的原值回填；
      // 一律写 isChanged=true / rollback_swap_parcels 会让净未变的地块显示成「变更」。
      const state = (payload.restoreStates || {})[parcel?.dkbm] || {};
      const restored = { ...cloneParcel(parcel), cbfbm: resultForm.code, cbfmc: resultForm.name, resultStatus: "normal", isChanged: Boolean(state.is_changed), changeType: state.change_type || "none", changeReason: state.change_reason || "", _pending: true };
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
      return;
    }
    // 已保存移除的行不在 parcels 里（/parcels 过滤 removed），凭撤回载荷里的快照
    // 合成待保存预览行，让"已撤回、还没保存"的中间态在列表里可见。
    const restored = payload.restoreParcel || {};
    if (restored.dkbm) {
      parcels.value = [...parcels.value, {
        ...restored,
        cbfmc: restored.cbfmc || resultForm.name,
        resultStatus: payload.sourceResultStatus || "normal",
        isChanged: Boolean(payload.sourceIsChanged),
        changeType: payload.sourceChangeType || "none",
        changeReason: payload.sourceChangeReason || "",
        _pending: true,
      }];
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

// ── 两张摸底表：生成（打印窗口） ──────────────────────────────────────────
const printingLandSheet = ref(false);
const printingMemberSheet = ref(false);

async function printSurveySheet(loader, loadingRef, label) {
  const batchId = props.activeBatch?.id;
  const contractorUid = resultForm.contractorUid;
  if (!batchId || !contractorUid) {
    ElMessage.warning(`缺少批次或承包方信息，无法生成${label}`);
    return;
  }
  loadingRef.value = true;
  try {
    const response = await loader(batchId, contractorUid);
    // print 接口直接返回 HTML 文本
    const html = typeof response.data === "string" ? response.data : response.data?.data?.renderedHtml || "";
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
    setTimeout(() => w.print(), 800);
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || `生成${label}失败`);
  } finally {
    loadingRef.value = false;
  }
}

function handlePrintLandSheet() {
  printSurveySheet(printLandChangeSheet, printingLandSheet, "承包地变化摸底表");
}

function handlePrintMemberSheet() {
  printSurveySheet(printMemberChangeSheet, printingMemberSheet, "成员变化摸底表");
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
  if (operation?.type === "rollback_remove_parcel") return `撤回移除：${p.dkbm || "-"}`;
  if (operation?.type === "rollback_swap_parcels") return `撤回互换：还原 ${((p.restoreDkbms) || []).length} 块，退回 ${((p.returnDkbms) || []).length} 块`;
  if (operation?.type === "split_household") return `分户：原户注销，新增 ${(p.newHouseholds || []).length} 户`;
  if (operation?.type === "merge_household") return `合户：注销 ${(p.sourceContractorUids || []).length} 个原户，新增 ${p.newCbfmc || p.newCbfbm || "新户"}`;
  return operation?.type || "未命名操作";
}

async function reloadParcelPreviewFromPendingOperations() {
  await loadSurveyParcels();
  for (const op of pendingOperations.value) applyPendingParcelPreview(op);
}

// 地块列表操作列上的「保存」：把**这一行**待保存的新增地块单独落库。
// ⛔ 存在理由：界址点 / 界址线由库里的地块图形推导，地块不落库就没有宿体；而「保存调查结果」
//   是整份提交（承包方必填校验 + 状态推进 + 关弹窗），为一块地付这个代价不合理。
// 语义边界由后端 `parcel_ops.persist_pending_operation` 守住：只写这一块地，
// 不碰承包方主体字段、不推进 survey_status、不处理其余待保存操作。
async function handlePersistPendingParcel(row) {
  if (!props.activeBatch || !activeTask.value) return;
  const dkbm = row?.dkbm;
  const index = pendingOperations.value.findIndex(
    (op) => op.type === "add_parcel" && op.payload?.dkbm === dkbm,
  );
  if (index === -1) {
    ElMessage.warning("该地块的待保存操作已失效，请重新打开录入页面后再试。");
    return;
  }
  persistingParcelDkbm.value = dkbm;
  try {
    await persistSurveyPendingOperation(
      props.activeBatch.id,
      activeTask.value.contractorUid,
      pendingOperations.value[index],
    );
    // ⛔ 落库后必须把这条从待保存清单里摘掉：否则整体保存时后端会再处理一次，
    // `add_parcel` 撞「编码已存在」把整次保存打回（连同表单里其它未保存的改动）。
    pendingOperations.value.splice(index, 1);
    await reloadParcelPreviewFromPendingOperations();
    const persisted = parcels.value.find((item) => item.dkbm === dkbm);
    if (persisted) selectedParcel.value = persisted;
    triggerFlash(dkbm);
    ElMessage.success(`地块 ${dkbm} 已保存，现在可以维护界址点 / 界址线`);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存地块失败");
  } finally {
    persistingParcelDkbm.value = "";
  }
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
  if (!props.activeBatch || !activeTask.value) { parcels.value = []; persistedParcelDkbms.value = []; parcelsLoaded.value = false; return; }
  parcelsLoading.value = true;
  try {
    const { data } = await fetchSurveyParcels(props.activeBatch.id, activeTask.value.contractorUid);
    parcels.value = data.data || [];
    // 只在"刚从服务端取回"的这一层记录，之后的待保存预览（applyPendingParcelPreview）
    // 追加出来的行不会进这个集合。
    persistedParcelDkbms.value = parcels.value.map((item) => item.dkbm).filter(Boolean);
    parcelsLoaded.value = true;
  } catch { parcels.value = []; persistedParcelDkbms.value = []; parcelsLoaded.value = false; } finally { parcelsLoading.value = false; }
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
    handlePendingOperation({ type: "rollback_swap_parcels", payload: { changeId: change.id, changeNo: change.changeNo, returnDkbms: [...(change.swappedIn || [])], restoreDkbms: [...(change.swappedOut || [])], restoreParcels, restoreStates: change.sourceStates || {}, reason: `撤回互换 ${change.changeNo}` } });
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
  if (!change.removedDkbm) { ElMessage.warning("该移除记录缺少地块编码，无法撤回，请联系管理员核查变更记录。"); return; }
  try {
    await ElMessageBox.confirm(`确定撤回这次已保存的地块移除吗？\n地块编码：${change.removedDkbm || "-"}`, "撤回已保存移除", { type: "warning", confirmButtonText: "加入待保存", cancelButtonText: "取消" });
    rollbackingSavedChangeId.value = change.id;
    // ⛔ 不能要求 parcels 里存在 resultStatus='removed' 的行：/parcels 接口刻意过滤已移除地块，
    // 那个判据永远 miss，导致「撤回已保存移除」在界面上 100% 不可达（2026-11-04 修）。
    // 撤回所需的信息全部在变更记录里（后端 rollback 也会按 change_id 重新校验）。
    handlePendingOperation({
      type: "rollback_remove_parcel",
      payload: {
        changeId: change.id,
        changeNo: change.changeNo,
        dkbm: change.removedDkbm,
        cbfbm: change.relationCbfbm || resultForm.code,
        sourceResultStatus: change.sourceResultStatus || "normal",
        sourceChangeType: change.sourceChangeType || "none",
        sourceChangeReason: change.sourceChangeReason || "",
        sourceIsChanged: Boolean(change.sourceIsChanged),
        // 快照行：pending 预览用（已移除行不在 parcels 里，需要凭它合成"撤回后"的预览行）。
        restoreParcel: {
          dkbm: change.removedDkbm,
          dkmc: change.removedDkmc || "",
          scmj: change.removedScmj,
          cbfbm: change.relationCbfbm || resultForm.code,
          cbfmc: resultForm.name,
          geometry: change.removedGeometry || null,
        },
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
  // 成员摸底「在户状态机」预检（与后端 sheet.py::validate_member_sheet_flow 同判据）：
  // 可以为空，但必须有进才有出，出了还可以再进 —— 违规逐条点名，不发请求。
  const sheetProblems = validateMemberSheetFlow((resultForm.familyMembers || []).filter((m) => !m._deleted));
  if (sheetProblems.length) { ElMessage.warning(sheetProblems.join("；")); return; }
  savingResult.value = true;
  creatingContractor.value = isCreatingContractorResult.value;
  try {
    const allMembers = resultForm.familyMembers || [];
    const validMembers = allMembers.filter((m) => !m._deleted);
    const cleanMembers = validMembers.map(({ _deleted, _isNew, ...rest }) => rest);
    const deletedMembers = allMembers.filter((m) => m._deleted && m.memberUid).map((m) => ({ memberUid: m.memberUid, changeReason: m.changeReason || resultForm.changeReason || "去世" }));
    // 地块信息面板的属性编辑（名称/面积/地类/四至/指界人/备注等）随保存统一提交；
    // 移除 / 切割源历史地块不在此列（由待保存操作负责）。
    const parcelUpdates = (parcels.value || [])
      .filter((parcel) => parcel?.dkbm && !["removed", "split_source"].includes(parcel.resultStatus))
      .map((parcel) => ({
        dkbm: parcel.dkbm,
        dkmc: parcel.dkmc ?? "",
        scmj: parcel.scmj ?? null,
        htmj: parcel.htmj ?? null,
        syqxz: parcel.syqxz ?? null,
        dklb: parcel.dklb ?? null,
        tdlylx: parcel.tdlylx ?? null,
        dldj: parcel.dldj ?? null,
        tdyt: parcel.tdyt ?? null,
        sfjbnt: parcel.sfjbnt ?? null,
        dkdz: parcel.dkdz ?? null,
        dkxz: parcel.dkxz ?? null,
        dknz: parcel.dknz ?? null,
        dkbz: parcel.dkbz ?? null,
        dkbzxx: parcel.dkbzxx ?? null,
        zjrxm: parcel.zjrxm ?? null,
      }));
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
    // 合户是「加入待保存 → 点「保存调查结果」才真正落库」，所以"是否进入新户页面"
    // 只能在这个时点问。先把合户操作捞出来（下面会把 pendingOperations 清空）。
    const mergeOperation = pendingOperations.value.find((op) => op.type === "merge_household") || null;
    const { data: savedResponse } = await updateSurveyResult(props.activeBatch.id, contractorUid, { ...contractorPayload, contractorUid, familyMembers: cleanMembers, deletedMembers, pendingOperations: pendingOperations.value, parcels: parcelUpdates });
    const createdContractors = savedResponse?.data?.createdContractors || [];
    ElMessage.success(isCreatingContractorResult.value ? "承包方调查数据已新增" : "调查结果已保存");
    pendingOperations.value = [];
    if (isCreatingContractorResult.value) {
      // 新增保存后不再关闭弹窗：切换成该新户的编辑态并重新加载，用户可继续核对/补充。
      isCreatingContractorResult.value = false;
      activeTask.value = {
        batchId: props.activeBatch.id,
        contractorUid,
        cbfbm: contractorPayload.code,
        cbfmc: contractorPayload.name,
        taskStatus: "surveyed",
        canWrite: true,
      };
    }
    emit("saved");
    // 重新拉取库内最新结果（任务状态、变化标记、地块等），保持当前弹窗打开。
    await reloadSurveyResult();
    if (mergeOperation) await offerOpenCreatedContractor(mergeOperation, createdContractors);
  } catch (error) { ElMessage.error(error.response?.data?.detail || (isCreatingContractorResult.value ? "新增承包方失败" : "保存调查结果失败")); } finally { savingResult.value = false; creatingContractor.value = false; }
}

// 合户完成后问一句「要不要直接进新户的录入页面」——新户刚生成，用户多半要接着录它。
// 新户标识以后端返回的 `createdContractors` 为准；万一拿不到（旧后端 / 编码冲突等），
// 用 payload 里的 newCbfbm/newCbfmc 兜底，至少让父组件能按编码去找。
async function offerOpenCreatedContractor(mergeOperation, createdContractors) {
  const target = createdContractors[0] || {
    cbfbm: mergeOperation?.payload?.newCbfbm || "",
    cbfmc: mergeOperation?.payload?.newCbfmc || "",
  };
  if (!target?.contractorUid && !target?.cbfbm) return;
  try {
    await ElMessageBox.confirm(
      `合户已完成${target.cbfmc ? `，新承包方「${target.cbfmc}」已生成` : ""}。是否进入该户的调查录入页面继续录入？`,
      "进入新户页面",
      { confirmButtonText: "进入新户", cancelButtonText: "留在当前列表", type: "success" },
    );
  } catch {
    return;
  }
  emit("openContractor", target);
}

// 确认前的提前提示：把当场就能自查的缺失项先说出来，免得用户点了按钮只拿到一句后端报错。
// ⛔ 口径与后端 backend/app/services/survey/base.py::_validate_confirmable 对齐，改一处要改两处。
//
// ⚠️「变化原因」**不在这里拦**（2026-09-27 用户决定）：空值由后端
// `_ensure_change_reasons` 在确认前按变更类型**自动写入默认值**（合户成员 →
// 「因合户转入新户」等），前端再拦一次只会变成"界面挡着、请求根本发不出去"的假故障
// ——那正是用户这次报的现象。保留这个函数是给**其他**当场可判的缺失项留钩子（当前无）。
function collectConfirmBlockers() {
  return [];
}

async function handleConfirmCurrent() {
  if (!props.activeBatch || !activeTask.value) return;
  // ⛔ 确认接口不接收 pendingOperations：待保存的互换/撤回互换不会被提交，只会被 close() 清掉。
  // 按钮侧已用 v-if 拦一次，这里再拦一次做兜底（模板条件将来被改动时不至于静默丢操作）。
  if (hasPendingOperations.value) {
    ElMessage.warning(`当前有 ${pendingOperations.value.length} 项操作尚未保存，请先点击「保存调查结果」。确认调查结果不会提交这些操作。`);
    return;
  }
  const blockers = collectConfirmBlockers();
  if (blockers.length) { ElMessage.warning(blockers.join("；")); return; }
  confirmingResult.value = true;
  try { await confirmSurveyResult(props.activeBatch.id, activeTask.value.contractorUid); ElMessage.success("调查结果已确认"); close(); emit("confirmed"); } catch (error) { ElMessage.error(error.response?.data?.detail || "确认失败"); } finally { confirmingResult.value = false; }
}

async function handleUnconfirmCurrent() {
  if (!props.activeBatch || !activeTask.value) return;
  if (!canUnconfirm.value) { ElMessage.warning("当前账号无权撤回确认"); return; }
  if (resultForm.surveyStatus !== "confirmed") { ElMessage.warning("本户调查成果尚未确认，无需撤回"); return; }
  try {
    await ElMessageBox.confirm(
      "撤回确认后，该承包方调查成果将回到可编辑状态，可重新录入并再次确认。确定要撤回确认吗？",
      "撤回确认",
      { type: "warning", confirmButtonText: "撤回确认", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  unconfirmingResult.value = true;
  try {
    await unconfirmSurveyResult(props.activeBatch.id, activeTask.value.contractorUid);
    ElMessage.success("已撤回确认，该户回到可编辑状态");
    await reloadSurveyResult();
    emit("saved");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "撤回确认失败");
  } finally {
    unconfirmingResult.value = false;
  }
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
async function openForResult(batch, row, options = {}) {
  isCreatingContractorResult.value = false; activeTask.value = row; selectedParcel.value = null; focusParcelDkbm.value = options.dkbm || ""; parcels.value = []; persistedParcelDkbms.value = []; parcelsLoaded.value = false;
  previewAttachmentVisible.value = false; previewAttachment.value = null; attachmentPreviewIndex.value = -1;
  pendingOperations.value = []; savedSwapChanges.value = []; savedSplitChanges.value = []; savedRemoveChanges.value = []; savedParcelChangeLoading.value = false; rollbackingSavedChangeId.value = null;
  const { data } = await fetchSurveyResult(row.batchId, row.contractorUid);
  Object.assign(resultForm, createEmptyResult(), data.data, { familyMembers: (data.data.familyMembers || []).map((item) => ({ ...item })) });
  // 调查员 / 调查日期取「本次」的默认值（当前登录用户 + 当天），不再沿用库里的历史痕迹。
  applyCurrentSurveyDefaults();
  const initialPanel = options.panel || "contractor";
  resetPhase2Forms(); activePanel.value = initialPanel; openedPanels.value = [initialPanel]; emit("update:modelValue", true);
  await loadDiffs(); await loadPhase2();
  if (initialPanel === "parcels") {
    await Promise.all([loadSurveyParcels(), loadSavedParcelChanges()]);
  }
}

function openForCreate(batch) {
  isCreatingContractorResult.value = true; activeTask.value = null; selectedParcel.value = null; focusParcelDkbm.value = ""; parcels.value = []; persistedParcelDkbms.value = [];
  diffRows.value = []; savedSwapChanges.value = []; savedSplitChanges.value = []; savedRemoveChanges.value = []; savedParcelChangeLoading.value = false;
  pendingOperations.value = []; rollbackingSavedChangeId.value = null;
  Object.assign(resultForm, createEmptyResult(), { code: batch?.regionCode || props.activeRegionCode || "", groupRegionCode: batch?.regionCode || props.activeRegionCode || "", groupRegionName: batch?.regionName || props.activeRegionLabel || "", resultStatus: "added", changeType: "add_contractor", isChanged: false });
  // 新增承包方：调查员 / 调查日期直接落「本次」的默认值（当前登录用户 + 当天）。
  applyCurrentSurveyDefaults();
  resetPhase2Forms(); activePanel.value = "contractor"; openedPanels.value = ["contractor"]; emit("update:modelValue", true);
}

function close() {
  emit("update:modelValue", false); isCreatingContractorResult.value = false;
  focusParcelDkbm.value = "";
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
/* 调查详情弹窗：压缩头/尾/正文留白，正文内部滚动，避免整页被弹窗撑高。 */
:global(.contractor-result-dialog .el-dialog__header) {
  padding: 12px 18px 8px;
  margin-right: 0;
}

:global(.contractor-result-dialog .el-dialog__title) {
  font-size: 16px;
  font-weight: 700;
}

:global(.contractor-result-dialog .el-dialog__body) {
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  padding: 8px 18px 4px;
}

:global(.contractor-result-dialog .el-dialog__footer) {
  padding: 8px 18px 12px;
  border-top: 1px solid var(--line);
}

.survey-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 8px; margin-bottom: 8px; }
.toolbar-print { display: flex; flex-wrap: wrap; gap: 6px; margin-left: auto; }
.survey-dialog-form { margin-top: 16px; }
.snapshot-member-title { color: #334155; font-size: 14px; font-weight: 700; margin: 16px 0 10px; }
.snapshot-changed-value { background: #fef3c7; border: 1px solid #f59e0b; border-radius: 4px; color: #92400e; display: inline-block; font-weight: 600; line-height: 1.5; padding: 0 6px; }
.phase2-actions, .phase2-upload { align-items: center; display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.phase2-form { margin: 10px 0; }
.phase2-submit { margin-top: 10px; }
.pending-operation-alert { margin-bottom: 8px; }
.pending-operation-list { display: flex; flex-direction: column; gap: 6px; margin: -2px 0 8px; }
.pending-operation-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 10px; border: 1px solid #f3d19e; border-radius: 6px; background: #fdf6ec; }
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

/* ---- 按钮式面板切换：横向铺满，淡色标签 ---- */
.survey-panel-switch {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px;
  width: 100%;
  margin-bottom: 8px;
}

.survey-panel-switch :deep(.el-button) {
  width: 100%;
  height: 30px;
  min-width: 0;
  margin-left: 0;
  padding: 5px 10px;
  overflow: hidden;
  color: #60758d;
  background: #f6f9fd;
  border: 1px solid #dce7f3;
  border-radius: 5px;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.survey-panel-switch :deep(.el-button:hover) {
  color: #2f7fd8;
  background: #eef6ff;
  border-color: #b8d7f7;
}

.survey-panel-switch :deep(.el-button.is-active) {
  color: #2f7fd8;
  background: #e5f1ff;
  border-color: #9dc8f5;
  font-weight: 600;
}

.survey-panel-switch :deep(.el-button.is-disabled) {
  color: #a5b4c5;
  background: #f8fafc;
  border-color: #e7eef6;
}

.survey-panel-body {
  min-height: 180px;
}

@media (max-width: 860px) {
  .survey-panel-switch {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.survey-panel-section {
  min-height: 0;
}
</style>


