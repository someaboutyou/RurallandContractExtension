<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div class="panel-title">串户调查成果</div>
      <div class="toolbar-actions">
        <el-tree-select
          v-model="activeRegionId"
          clearable
          filterable
          check-strictly
          :data="regionTree"
          :props="regionTreeProps"
          node-key="id"
          placeholder="按区域筛选成果"
          style="width: 260px"
          @change="handleActiveRegionChange"
        />
        <el-input v-model="batchKeyword" clearable placeholder="搜索调查批次" style="width: 220px" @keyup.enter="loadBatches" />
        <el-button plain @click="loadBatches">刷新</el-button>
        <el-button :disabled="!activeBatch" plain type="primary" @click="handleExportResults">导出成果</el-button>
        <el-button v-if="canManage" :disabled="!activeBatch || activeBatch.status === 'finished'" plain type="warning" @click="handleFinishBatch">
          结束批次
        </el-button>
        <el-button v-if="canManage" type="success" @click="openCreateBatch">新建调查批次</el-button>
      </div>
    </div>

    <el-table v-loading="batchLoading" :data="batches" border highlight-current-row @current-change="handleBatchSelect">
      <el-table-column prop="batchNo" label="批次号" min-width="160" />
      <el-table-column prop="batchName" label="批次名称" min-width="220" />
      <el-table-column prop="regionName" label="调查区域" min-width="180" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" min-width="100" />
      <el-table-column prop="taskCount" label="应调查" min-width="90" />
      <el-table-column prop="surveyedCount" label="已调查" min-width="90" />
      <el-table-column prop="changedCount" label="有变化" min-width="90" />
      <el-table-column prop="confirmedCount" label="已确认" min-width="90" />
      <el-table-column prop="skippedCount" label="已跳过" min-width="90" />
      <el-table-column prop="createdAt" label="创建时间" min-width="180" />
    </el-table>
  </section>

  <section class="panel table-page survey-task-panel">
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
        <el-button :disabled="!activeBatch" plain @click="loadTasks">查询</el-button>
      </div>
    </div>

    <el-table v-loading="taskLoading" :data="tasks" border>
      <el-table-column prop="cbfbm" label="承包方代码" min-width="180" />
      <el-table-column prop="cbfmc" label="承包方名称" min-width="180" />
      <el-table-column prop="taskStatus" label="调查状态" min-width="120">
        <template #default="{ row }">
          <el-tag :type="row.hasChange ? 'warning' : row.taskStatus === 'not_started' ? 'info' : 'success'">
            {{ taskStatusLabel(row.taskStatus) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="hasChange" label="是否变化" min-width="100">
        <template #default="{ row }">{{ row.hasChange ? "是" : "否" }}</template>
      </el-table-column>
      <el-table-column prop="investigatedAt" label="调查时间" min-width="180" />
      <el-table-column label="操作" fixed="right" min-width="120">
        <template #default="{ row }">
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
        </template>
      </el-table-column>
    </el-table>
  </section>

  <section class="panel table-page survey-task-panel">
    <div class="toolbar">
      <div class="panel-title">调查变化记录</div>
      <div class="toolbar-actions">
        <el-button :disabled="!activeBatch" plain @click="loadChanges">刷新</el-button>
      </div>
    </div>
    <el-table v-loading="changeLoading" :data="changes" border>
      <el-table-column prop="changeNo" label="变化编号" min-width="170" />
      <el-table-column prop="cbfbm" label="承包方代码" min-width="170" />
      <el-table-column prop="changeType" label="变化类型" min-width="130" />
      <el-table-column prop="changeStatus" label="状态" min-width="100" />
      <el-table-column prop="changeReason" label="变化原因" min-width="240" />
      <el-table-column prop="policyBasis" label="政策依据" min-width="240" />
      <el-table-column prop="investigatorName" label="调查人" min-width="120" />
      <el-table-column prop="createdAt" label="记录时间" min-width="180" />
    </el-table>
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
          check-strictly
          :data="regionTree"
          :props="regionTreeProps"
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

  <el-dialog v-model="resultVisible" :title="`调查录入 - ${resultForm.name || ''}`" width="92vw" top="3vh" destroy-on-close>
    <!-- 操作工具栏 -->
    <div class="survey-toolbar">
      <el-button type="danger" plain size="small" @click="handleOpDeregister">注销承包方</el-button>
      <el-button plain size="small" @click="handleOpSplitHousehold">分户</el-button>
      <el-button plain size="small" @click="handleOpMergeHousehold">合户</el-button>
      <span v-if="!canManage || isResultLocked" class="toolbar-lock-hint">（当前为只读模式）</span>
    </div>

    <!-- 4 个信息 Tab -->
    <el-tabs v-model="activeTab">
      <el-tab-pane :label="`承包方及家庭成员（${resultForm.familyMembers.length}人）`" name="contractor">
        <ContractorMemberPanel
          ref="contractorMemberPanel"
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
          :result="resultForm"
          :changed-fields="computedChangedFields"
        />
      </el-tab-pane>

      <el-tab-pane label="地块信息" name="parcels">
        <ParcelInfoPanel
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
          :parcels="parcels"
          :parcels-loading="parcelsLoading"
          :can-manage="canManage"
          :is-result-locked="isResultLocked"
          @swap-parcels="handleOpSwapParcels"
          @add-parcel="handleOpAddParcel"
          @split-parcel="handleOpSplitParcel"
          @remove-parcel="handleOpRemoveParcel"
        />
      </el-tab-pane>

      <el-tab-pane label="承包地块示意图" name="plotSketchMap">
        <PlotSketchMapPanel
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
          :refresh-key="plotSketchRefreshKey"
        />
      </el-tab-pane>

      <el-tab-pane label="合同信息" name="contract">
        <ContractInfoPanel
          :batch-id="activeBatch?.id"
          :contractor-uid="resultForm.contractorUid"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 辅助功能面板 -->
    <el-collapse class="survey-aux-panel">
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
      <el-button @click="resultVisible = false">取消</el-button>
      <el-button
        v-if="canManage && !isResultLocked"
        :loading="savingResult"
        type="success"
        @click="handleSaveResult"
      >
        保存调查结果
      </el-button>
      <el-button
        v-if="canManage && !isResultLocked && resultForm.surveyStatus !== 'not_surveyed'"
        :loading="confirmingResult"
        type="primary"
        @click="handleConfirmCurrent"
      >
        确认调查结果
      </el-button>
    </template>
  </el-dialog>

  <!-- 操作对话框 -->
  <DeregisterDialog ref="deregisterDialog" @done="handleDeregisterDone" />
  <AddParcelDialog ref="addParcelDialog" @done="reloadSurveyResult" />
  <SplitParcelDialog ref="splitParcelDialog" @done="reloadSurveyResult" />
  <SwapParcelsDialog ref="swapParcelsDialog" @done="reloadSurveyResult" />
  <SplitHouseholdDialog ref="splitHouseholdDialog" @done="reloadSurveyResult" />
  <MergeHouseholdDialog ref="mergeHouseholdDialog" @done="handleMergeDone" />
  <RemoveParcelDialog ref="removeParcelDialog" @done="reloadSurveyResult" />
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import ContractorMemberPanel from "../components/survey/ContractorMemberPanel.vue";
import ParcelInfoPanel from "../components/survey/ParcelInfoPanel.vue";
import PlotSketchMapPanel from "../components/survey/PlotSketchMapPanel.vue";
import ContractInfoPanel from "../components/survey/ContractInfoPanel.vue";
import DeregisterDialog from "../components/survey/DeregisterDialog.vue";
import AddParcelDialog from "../components/survey/AddParcelDialog.vue";
import SplitParcelDialog from "../components/survey/SplitParcelDialog.vue";
import SwapParcelsDialog from "../components/survey/SwapParcelsDialog.vue";
import SplitHouseholdDialog from "../components/survey/SplitHouseholdDialog.vue";
import MergeHouseholdDialog from "../components/survey/MergeHouseholdDialog.vue";
import RemoveParcelDialog from "../components/survey/RemoveParcelDialog.vue";

import {
  confirmSurveyResult,
  createSurveyAuthorization,
  createSurveyBatch,
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
  uploadSurveyAttachment,
  uploadSurveyAuthorizationFile,
} from "../api/survey";
import { fetchRegionTree } from "../api/region";
import { useAuthStore } from "../stores/auth";
import { useDialogMap } from "../composables/useDialogMap";
import { useDictionary } from "../composables/useDictionary";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));
const { labelOf: genderLabel } = useDictionary("nyt2539_c17_gender");
const { labelOf: yesNoLabel } = useDictionary("nyt2539_c19_yes_no");
const { labelOf: relationDictionaryLabel } = useDictionary("nyt2539_c20_relation_to_head");
const batchLoading = ref(false);
const taskLoading = ref(false);
const changeLoading = ref(false);
const diffLoading = ref(false);
const submittingBatch = ref(false);
const savingResult = ref(false);
const confirmingResult = ref(false);
const batches = ref([]);
const tasks = ref([]);
const changes = ref([]);
const diffRows = ref([]);
const phase2Loading = ref(false);
const phase2 = reactive({ tags: [], restructures: [], authorizations: [], attachments: [] });
const activeBatch = ref(null);
const activeTask = ref(null);
const activeRegionId = ref(undefined);
const activeRegionCode = ref("");
const activeRegionLabel = ref("");
const batchKeyword = ref("");
const taskKeyword = ref("");
const taskStatus = ref("");
const batchDialogVisible = ref(false);
const resultVisible = ref(false);
const activeTab = ref("contractor");
const plotSketchRefreshKey = ref(0);
const regionTree = ref([]);
const regionTreeProps = { label: "fullName", children: "children" };
const batchForm = reactive({ batchName: "", regionId: undefined, regionCode: "", regionName: "", remark: "" });
const resultForm = reactive(createEmptyResult());
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
const deregisterDialog = ref(null);
const addParcelDialog = ref(null);
const splitParcelDialog = ref(null);
const swapParcelsDialog = ref(null);
const splitHouseholdDialog = ref(null);
const mergeHouseholdDialog = ref(null);
const removeParcelDialog = ref(null);
const isResultLocked = computed(() => activeBatch.value?.status === "finished" || resultForm.surveyStatus === "confirmed");

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
  );
}
function handleOpAddParcel() {
  addParcelDialog.value.open(
    activeBatch.value.id,
    activeTask.value.contractorUid,
  );
}
function handleOpSplitParcel() {
  splitParcelDialog.value.open(
    activeBatch.value.id,
    activeTask.value.contractorUid,
    parcels.value,
  );
}
function handleOpRemoveParcel() {
  removeParcelDialog.value.open(
    activeBatch.value.id,
    activeTask.value.contractorUid,
    parcels.value,
  );
}
const taskPanelTitle = computed(() => {
  const batchName = activeBatch.value?.batchName || "调查任务";
  return activeRegionLabel.value ? `${batchName} - ${activeRegionLabel.value}` : batchName;
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
    postcode: "",
    mobile: "",
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
    familyMembers: [],
    generatedRequestId: null,
    generatedRequestNo: "",
  };
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
  return { not_started: "未调查", surveyed: "已调查", changed: "有变化", unchanged: "无变化", confirmed: "已确认", skipped: "已跳过" }[value] || value;
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
    activeBatch.value = batches.value.find((item) => item.id === previousBatchId) || batches.value[0] || null;
    if (activeBatch.value) {
      await loadTasks();
      await loadChanges();
    } else {
      tasks.value = [];
      changes.value = [];
    }
  } finally {
    batchLoading.value = false;
  }
}

async function reloadBatchesForRegion() {
  activeBatch.value = null;
  tasks.value = [];
  changes.value = [];
  await loadBatches();
}

function buildRegionParams() {
  return activeRegionCode.value ? { regionCode: activeRegionCode.value } : {};
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
  } finally {
    taskLoading.value = false;
  }
}

async function loadChanges() {
  if (!activeBatch.value) {
    changes.value = [];
    return;
  }
  changeLoading.value = true;
  try {
    const { data } = await fetchSurveyChanges(activeBatch.value.id, { page: 1, page_size: 100, ...buildRegionParams() });
    changes.value = data.data.items;
  } finally {
    changeLoading.value = false;
  }
}

function handleBatchSelect(row) {
  activeBatch.value = row;
  loadTasks();
  loadChanges();
}

function openCreateBatch() {
  const selectedRegion = flattenRegions(regionTree.value).find((item) => item.code === activeRegionCode.value);
  Object.assign(batchForm, {
    batchName: "",
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

function flattenRegions(nodes, result = []) {
  for (const item of nodes || []) {
    result.push(item);
    flattenRegions(item.children, result);
  }
  return result;
}

function handleBatchRegionChange(value) {
  const selected = flattenRegions(regionTree.value).find((item) => item.id === value);
  batchForm.regionCode = selected?.code || "";
  batchForm.regionName = selected?.fullName || "";
}

async function loadRegionTree() {
  const { data } = await fetchRegionTree();
  regionTree.value = data.data;
  applyDefaultRegionFilter();
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
  activeTask.value = row;
  selectedParcel.value = null;
  mapClearSelection();
  const { data } = await fetchSurveyResult(row.batchId, row.contractorUid);
  Object.assign(resultForm, createEmptyResult(), data.data, {
    familyMembers: (data.data.familyMembers || []).map((item) => ({ ...item })),
  });
  resetPhase2Forms();
  activeTab.value = "contractor";
  resultVisible.value = true;
  await loadDiffs();
  await loadPhase2();
  loadSurveyParcels();
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
  if (!activeBatch.value || !activeTask.value) {
    return;
  }
  savingResult.value = true;
  try {
    const validMembers = (resultForm.familyMembers || []).filter((m) => !m._deleted);
    const cleanMembers = validMembers.map(({ _deleted, _isNew, ...rest }) => rest);
    await updateSurveyResult(activeBatch.value.id, activeTask.value.contractorUid, {
      ...resultForm,
      familyMembers: cleanMembers,
    });
    ElMessage.success("调查结果已保存");
    resultVisible.value = false;
    await loadTasks();
    await loadBatches();
    await loadChanges();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存调查结果失败");
  } finally {
    savingResult.value = false;
  }
}

async function handleConfirmTask(row) {
  try {
    await confirmSurveyResult(row.batchId, row.contractorUid);
    ElMessage.success("调查结果已确认");
    await loadTasks();
    await loadBatches();
    await loadChanges();
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
    await loadChanges();
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
    await loadChanges();
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
  await loadChanges();
}

async function handleMergeDone() {
  resultVisible.value = false;
  await loadTasks();
  await loadBatches();
  await loadChanges();
}

watch(activeTab, (tab) => {
  if (tab === "parcels") {
    handleParcelTabEnter();
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
.survey-task-panel {
  margin-top: 16px;
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
</style>
