<template>
  <el-dialog
    v-model="dialogVisible"
    :title="editingCode ? '编辑承包方' : '新增承包方'"
    class="contractor-dialog"
    width="92vw"
    top="3vh"
    destroy-on-close
  >
    <el-tabs v-model="activeMainTab" class="compact-dialog-tabs">
      <el-tab-pane label="承包方信息" name="base">
        <el-form ref="formRef" :model="form" :rules="rules" class="compact-form" label-position="top" status-icon>
          <div class="form-grid">
            <el-form-item label="承包方代码" prop="code">
              <el-input v-model="form.code" placeholder="请输入承包方代码" />
            </el-form-item>
            <el-form-item label="承包方类型" prop="typeCode">
              <DictionarySelect v-model="form.typeCode" dict-type="nyt2539_c16_contractor_type" placeholder="请选择承包方类型" />
            </el-form-item>
            <el-form-item label="承包方名称" prop="name">
              <el-input v-model="form.name" placeholder="请输入承包方名称" />
            </el-form-item>
            <el-form-item label="所属组" prop="groupRegionCode">
              <el-tree-select
                v-model="form.groupRegionCode"
                :data="regionTree"
                check-strictly
                clearable
                filterable
                node-key="value"
                placeholder="请选择所属组"
                :props="regionTreeProps"
                @change="handleGroupRegionChange"
              />
            </el-form-item>
            <el-form-item label="证件类型" prop="idType">
              <DictionarySelect v-model="form.idType" dict-type="nyt2539_c15_id_document_type" placeholder="请选择证件类型" />
            </el-form-item>
            <el-form-item label="证件号码" prop="idNo">
              <el-input v-model="form.idNo" placeholder="请输入证件号码" />
            </el-form-item>
            <el-form-item label="联系电话" prop="mobile">
              <el-input v-model="form.mobile" placeholder="请输入联系电话" />
            </el-form-item>
            <el-form-item label="邮政编码" prop="postcode">
              <el-input v-model="form.postcode" placeholder="请输入邮政编码" />
            </el-form-item>
            <el-form-item label="调查员" prop="surveyorName">
              <el-input v-model="form.surveyorName" placeholder="请输入调查员姓名" />
            </el-form-item>
            <el-form-item label="调查日期" prop="surveyDate">
              <el-date-picker
                class="form-date-picker"
                v-model="form.surveyDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="请选择调查日期"
              />
            </el-form-item>
            <el-form-item class="form-span-2" label="承包方地址" prop="address">
              <el-input v-model="form.address" placeholder="请输入承包方地址" />
            </el-form-item>
            <el-form-item class="form-span-2" label="调查记事" prop="surveyNote">
              <el-input v-model="form.surveyNote" :rows="3" type="textarea" placeholder="请输入调查记事" />
            </el-form-item>
            <el-form-item class="form-span-2" label="公示记事" prop="publicNoticeNote">
              <el-input v-model="form.publicNoticeNote" :rows="3" type="textarea" placeholder="请输入公示记事" />
            </el-form-item>
            <el-form-item label="公示记录人" prop="publicNoticeRecorder">
              <el-input v-model="form.publicNoticeRecorder" placeholder="请输入公示记录人" />
            </el-form-item>
            <el-form-item label="公示审核日期" prop="publicNoticeReviewDate">
              <el-date-picker
                class="form-date-picker"
                v-model="form.publicNoticeReviewDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="请选择公示审核日期"
              />
            </el-form-item>
            <el-form-item label="公示审核人" prop="publicNoticeReviewer">
              <el-input v-model="form.publicNoticeReviewer" placeholder="请输入公示审核人" />
            </el-form-item>
          </div>
        </el-form>
      </el-tab-pane>

      <el-tab-pane :disabled="form.typeCode !== '1'" label="家庭成员" name="family">
        <div v-if="familyMemberViewMode === 'list'" class="family-member-list-view">
          <div
            v-for="member in form.familyMembers"
            :key="member._tabKey"
            class="family-member-card"
            @click="openFamilyMemberForm(member._tabKey)"
          >
            <div class="family-member-card-name">{{ member.name || '未命名成员' }}</div>
            <div class="family-member-card-meta">
              <span>{{ genderLabel(member.gender, '--') }}</span>
              <span>{{ member.relationToHead || '--' }}</span>
              <span>{{ idDocumentTypeLabel(member.idType, '--') }}</span>
            </div>
          </div>
          <el-button class="add-member-btn" type="primary" plain @click="appendFamilyMember">添加成员</el-button>
        </div>

        <div v-else>
          <el-tabs
            v-model="activeMemberTab"
            type="card"
            class="member-tabs"
            addable
            @edit="handleMemberTabEdit"
            @tab-add="appendFamilyMember"
          >
            <el-tab-pane
              v-for="member in form.familyMembers"
              :key="member._tabKey"
              :label="member.name || '未命名成员'"
              :name="member._tabKey"
              closable
            >
              <el-form label-position="top" class="compact-form" size="small">
                <div class="form-grid">
                  <el-form-item label="姓名" required>
                    <el-input v-model="member.name" placeholder="请输入姓名" />
                  </el-form-item>
                  <el-form-item label="性别" required>
                    <DictionarySelect v-model="member.gender" dict-type="nyt2539_c17_gender" placeholder="请选择性别" />
                  </el-form-item>
                  <el-form-item label="证件类型" required>
                    <DictionarySelect v-model="member.idType" dict-type="nyt2539_c15_id_document_type" placeholder="请选择证件类型" />
                  </el-form-item>
                  <el-form-item label="证件号码" required>
                    <el-input v-model="member.idNo" placeholder="请输入证件号码" />
                  </el-form-item>
                  <el-form-item label="与户主关系" required>
                    <el-input v-model="member.relationToHead" placeholder="请输入与户主关系" />
                  </el-form-item>
                  <el-form-item label="备注代码">
                    <DictionarySelect v-model="member.noteCode" dict-type="nyt2539_c18_member_remark" placeholder="请选择备注代码" clearable />
                  </el-form-item>
                  <el-form-item label="是否共有人">
                    <DictionarySelect v-model="member.isCoOwner" dict-type="nyt2539_c19_yes_no" placeholder="请选择" clearable />
                  </el-form-item>
                  <el-form-item label="备注">
                    <el-input v-model="member.note" placeholder="请输入备注" />
                  </el-form-item>
                </div>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-tab-pane>

      <el-tab-pane :disabled="!editingCode" label="合同信息" name="contracts">
        <el-tabs
          v-model="activeContractTab"
          type="card"
          class="contract-tabs"
        >
          <el-tab-pane
            v-for="(contract, index) in form.contracts"
            :key="contract._tabKey"
            :label="contractTabLabel(contract, index)"
            :name="contract._tabKey"
          >
            <div class="contract-pane-card">
              <div class="contract-pane-header">
                <div>
                  <div class="contract-pane-title">{{ contract.title || contract.code }}</div>
                  <div class="contract-pane-meta">
                    <el-tag size="small" :type="contract.type === 'lzht' ? 'warning' : 'success'" effect="plain">
                      {{ contract.typeLabel }}
                    </el-tag>
                    <span v-if="contract.role">{{ contract.role }}</span>
                  </div>
                </div>
              </div>
              <el-descriptions class="contract-descriptions" :column="2" border>
                <el-descriptions-item
                  v-for="field in contractDetailFields(contract)"
                  :key="field.key"
                  :label="field.label"
                >
                  {{ displayValue(field.value) }}
                </el-descriptions-item>
              </el-descriptions>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-tab-pane>

      <el-tab-pane :disabled="!editingCode" label="地块信息" name="parcels">
        <div v-if="parcelsTabActivated" class="parcels-map-area">
          <div v-if="parcelsLoading" class="parcels-status">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>加载地块数据...</span>
          </div>
          <div v-else-if="parcelsError" class="parcels-status">
            <span>{{ parcelsError }}</span>
            <el-button size="small" @click="loadParcelData">重试</el-button>
          </div>
          <div v-else-if="parcelData.length === 0" class="parcels-status">
            <span>该承包方暂无关联地块信息。</span>
          </div>
          <template v-else>
            <div class="parcels-layout">
              <div class="parcels-map-container">
                <div ref="parcelMapRootRef" class="parcels-ol-map"></div>
                <div class="parcels-map-basemap">
                  <el-segmented
                    v-model="activeBasemap"
                    :options="basemapOptions"
                    size="small"
                    @change="switchBasemap"
                  />
                </div>
              </div>
              <div class="parcels-info-panel">
                <div class="parcels-info-title">地块列表 ({{ parcelData.length }})</div>
                <div class="parcels-info-list">
                  <div
                    v-for="item in parcelData"
                    :key="item.dkbm"
                    class="parcels-info-item"
                    :class="{ 'parcels-info-item--flash': flashDkbm === item.dkbm }"
                    @click="focusParcel(item)"
                  >
                    <div class="parcels-info-dkbm">{{ item.dkbm }}</div>
                    <div class="parcels-info-dkmc">{{ item.dkmc || '--' }}</div>
                    <div class="parcels-info-meta">
                      <span v-if="item.htmj">合同面积: {{ item.htmj }}m²</span>
                      <span v-if="item.scmj">实测面积: {{ item.scmj }}m²</span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="parcels-detail-panel">
                <div class="parcels-detail-title">地块详情</div>
                <div v-if="!selectedParcel" class="parcels-detail-empty">点击左侧地块查看详细信息</div>
                <div v-else class="parcels-detail-list">
                  <div v-for="f in parcelDetailFields" :key="f.key" class="parcels-detail-row">
                    <div class="parcels-detail-label">{{ f.label }}</div>
                    <div class="parcels-detail-value">{{ selectedParcel[f.key] || '--' }}</div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
        <div v-else class="parcels-status">
          <el-button type="primary" @click="activateParcelsTab">加载地块信息</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button :loading="submitting" type="success" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Loading } from "@element-plus/icons-vue";

import {
  createContractor,
  fetchContractorDetail,
  updateContractor,
} from "../../api/contractor";
import { fetchContractorParcels } from "../../api/landParcel";
import DictionarySelect from "../DictionarySelect.vue";
import { useDictionary } from "../../composables/useDictionary";
import { useDialogMap } from "../../composables/useDialogMap";
import { validateChinaId, validateMobile, validatePostcode } from "../../utils/validators";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  editingCode: { type: String, default: "" },
  regionTree: { type: Array, default: () => [] },
  canManage: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "saved"]);

const { labelOf: genderLabel } = useDictionary("nyt2539_c17_gender");
const { labelOf: idDocumentTypeLabel } = useDictionary("nyt2539_c15_id_document_type");
const { labelOf: yesNoLabel } = useDictionary("nyt2539_c19_yes_no");
const { labelOf: memberRemarkLabel } = useDictionary("nyt2539_c18_member_remark");

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

const submitting = ref(false);
const loading = ref(false);
const formRef = ref();
const activeMainTab = ref("base");
const activeMemberTab = ref("");
const activeContractTab = ref("");
const familyMemberViewMode = ref("tabs");
let memberTabSeed = 0;
let contractTabSeed = 0;

const regionTreeProps = { label: "label", children: "children" };

const createMemberTabKey = () => {
  memberTabSeed += 1;
  return `member-${memberTabSeed}`;
};

const createContractTabKey = () => {
  contractTabSeed += 1;
  return `contract-${contractTabSeed}`;
};

const createEmptyFamilyMember = () => ({
  _tabKey: createMemberTabKey(),
  name: "",
  gender: "1",
  idType: "1",
  idNo: "",
  relationToHead: "",
  noteCode: "",
  isCoOwner: "1",
  note: "",
});

const createEmptyForm = () => ({
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
  groupRegionCode: "",
  groupRegionName: "",
  familyMembers: [],
  contracts: [],
});

const form = reactive(createEmptyForm());

// --- Parcels tab state ---
const parcelsTabActivated = ref(false);
const parcelsLoading = ref(false);
const parcelsError = ref("");
const parcelData = ref([]);
const parcelMapRootRef = ref(null);

const {
  mapReady,
  activeBasemap,
  basemapOptions,
  initMap,
  switchBasemap,
  loadParcels,
  fitToParcels,
  focusParcel: focusParcelOnMap,
  updateMapSize,
  destroyMap,
} = useDialogMap(parcelMapRootRef);

const flashDkbm = ref(null);
const selectedParcel = ref(null);

const parcelDetailFields = [
  { key: "dkbm", label: "地块编码" },
  { key: "dkmc", label: "地块名称" },
  { key: "htmj", label: "合同面积(m²)" },
  { key: "scmj", label: "实测面积(m²)" },
  { key: "syqxz", label: "所有权性质" },
  { key: "dklb", label: "地块类别" },
  { key: "dkdz", label: "地块地址" },
];

// --- Display helpers ---
function normalizeContractInfos(contracts = []) {
  return contracts.map((item) => ({
    ...item,
    _tabKey: createContractTabKey(),
  }));
}

function formatArea(value, unit) {
  return hasDisplayValue(value) ? `${value}${unit}` : "";
}

function displayValue(value, fallback = "--") {
  return hasDisplayValue(value) ? value : fallback;
}

function hasDisplayValue(value) {
  return value !== null && value !== undefined && value !== "";
}

function contractTabLabel(contract, index) {
  const shortCode = contract.code ? contract.code.slice(-6) : index + 1;
  return `${contract.typeLabel || "合同"} ${shortCode}`;
}

function contractDetailFields(contract) {
  if (contract.type === "lzht") {
    return [
      { key: "code", label: "流转合同代码", value: contract.code },
      { key: "parentContractCode", label: "承包合同代码", value: contract.parentContractCode },
      { key: "contractorCode", label: "转出方代码", value: contract.contractorCode },
      { key: "recipientContractorCode", label: "受让方代码", value: contract.recipientContractorCode },
      { key: "role", label: "当前承包方角色", value: contract.role },
      { key: "transferMode", label: "流转方式", value: contract.transferMode },
      { key: "term", label: "流转期限", value: contract.term },
      { key: "dateRange", label: "流转起止日期", value: joinRange(contract.startDate, contract.endDate) },
      { key: "totalArea", label: "流转面积", value: formatArea(contract.totalArea, "m²") },
      { key: "parcelCount", label: "流转地块数", value: contract.parcelCount },
      { key: "priceDescription", label: "流转价款说明", value: contract.priceDescription },
      { key: "signDate", label: "合同签订日期", value: contract.signDate },
    ];
  }
  return [
    { key: "code", label: "承包合同代码", value: contract.code },
    { key: "originalCode", label: "原承包合同代码", value: contract.originalCode },
    { key: "issuerCode", label: "发包方代码", value: contract.issuerCode },
    { key: "contractorCode", label: "承包方代码", value: contract.contractorCode },
    { key: "contractMode", label: "承包方式", value: contract.contractMode },
    { key: "dateRange", label: "承包期限", value: joinRange(contract.startDate, contract.endDate) },
    { key: "totalArea", label: "合同总面积", value: formatArea(contract.totalArea, "m²") },
    { key: "totalAreaMu", label: "合同总面积（亩）", value: formatArea(contract.totalAreaMu, "亩") },
    { key: "originalTotalArea", label: "原合同总面积", value: formatArea(contract.originalTotalArea, "m²") },
    { key: "originalTotalAreaMu", label: "原合同总面积（亩）", value: formatArea(contract.originalTotalAreaMu, "亩") },
    { key: "parcelCount", label: "承包地块数", value: contract.parcelCount },
    { key: "signDate", label: "合同签订日期", value: contract.signDate },
  ];
}

function joinRange(start, end) {
  if (start && end) {
    return `${start} 至 ${end}`;
  }
  return start || end || "";
}

// --- Parcels tab ---
function triggerFlash(dkbm) {
  flashDkbm.value = dkbm;
  setTimeout(() => {
    if (flashDkbm.value === dkbm) {
      flashDkbm.value = null;
    }
  }, 2800);
}

async function activateParcelsTab() {
  parcelsTabActivated.value = true;
  await nextTick();
  await loadParcelData();
  await nextTick();
  if (parcelData.value.length > 0) {
    await initMap();
    setTimeout(() => updateMapSize(), 100);
  }
}

async function loadParcelData() {
  if (!props.editingCode) return;
  parcelsLoading.value = true;
  parcelsError.value = "";
  try {
    const { data } = await fetchContractorParcels(props.editingCode);
    parcelData.value = data.data || [];
    if (mapReady.value) {
      loadParcels(parcelData.value);
      if (parcelData.value.length > 0) {
        setTimeout(() => fitToParcels(), 300);
      }
    }
  } catch (error) {
    parcelsError.value = error.response?.data?.detail || "加载地块信息失败";
  } finally {
    parcelsLoading.value = false;
  }
}

function focusParcel(item) {
  selectedParcel.value = item;
  triggerFlash(item.dkbm);
  focusParcelOnMap(item.dkbm);
}

// --- Validation ---
const validateMainIdNo = (_rule, value, callback) => {
  if (!value) {
    callback(new Error("请输入证件号码"));
    return;
  }
  if (form.idType === "1" && !validateChinaId(value)) {
    callback(new Error("请输入正确的身份证号"));
    return;
  }
  callback();
};

const validateMobileField = (_rule, value, callback) => {
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

const validatePostcodeField = (_rule, value, callback) => {
  if (!value) {
    callback(new Error("请输入邮政编码"));
    return;
  }
  if (!validatePostcode(value)) {
    callback(new Error("请输入 6 位邮政编码"));
    return;
  }
  callback();
};

const rules = {
  code: [{ required: true, message: "请输入承包方代码", trigger: "blur" }],
  typeCode: [{ required: true, message: "请选择承包方类型", trigger: "change" }],
  name: [{ required: true, message: "请输入承包方名称", trigger: "blur" }],
  idType: [{ required: true, message: "请选择证件类型", trigger: "change" }],
  idNo: [{ validator: validateMainIdNo, trigger: "blur" }],
  address: [{ required: true, message: "请输入承包方地址", trigger: "blur" }],
  postcode: [{ validator: validatePostcodeField, trigger: "blur" }],
  mobile: [{ validator: validateMobileField, trigger: "blur" }],
  groupRegionCode: [{ required: true, message: "请选择所属组", trigger: "change" }],
  surveyorName: [{ required: true, message: "请输入调查员姓名", trigger: "blur" }],
};

// --- Region tree ---
function findRegionNode(nodes, code) {
  for (const node of nodes || []) {
    if (node.value === code) return node;
    const matched = findRegionNode(node.children || [], code);
    if (matched) return matched;
  }
  return null;
}

function handleGroupRegionChange(code) {
  const node = findRegionNode(props.regionTree, code);
  form.groupRegionName = node?.label || "";
}

// --- Family members ---
function appendFamilyMember() {
  const member = createEmptyFamilyMember();
  form.familyMembers.push(member);
  activeMemberTab.value = member._tabKey;
  familyMemberViewMode.value = "tabs";
}

function openFamilyMemberForm(tabKey) {
  activeMemberTab.value = tabKey;
  familyMemberViewMode.value = "tabs";
}

function removeFamilyMemberByKey(targetKey) {
  const index = form.familyMembers.findIndex((item) => item._tabKey === targetKey);
  if (index === -1) {
    return;
  }
  form.familyMembers.splice(index, 1);
  if (!form.familyMembers.length) {
    activeMemberTab.value = "";
    return;
  }
  const nextMember = form.familyMembers[index] || form.familyMembers[index - 1];
  activeMemberTab.value = nextMember._tabKey;
}

function handleMemberTabEdit(targetKey, action) {
  if (action === "remove") {
    removeFamilyMemberByKey(targetKey);
  }
}

// --- Form management ---
function resetForm() {
  Object.assign(form, createEmptyForm());
  activeMainTab.value = "base";
  activeMemberTab.value = "";
  activeContractTab.value = "";
  familyMemberViewMode.value = "tabs";
  formRef.value?.clearValidate();
}

async function openForCreate() {
  resetForm();
  appendFamilyMember();
  dialogVisible.value = true;
}

async function openForEdit(code) {
  loading.value = true;
  try {
    const { data } = await fetchContractorDetail(code);
    const detail = data.data;
    Object.assign(form, {
      code: detail.code,
      typeCode: detail.typeCode,
      name: detail.name,
      idType: detail.idType,
      idNo: detail.idNo,
      address: detail.address,
      postcode: detail.postcode,
      mobile: detail.mobile || "",
      surveyDate: detail.surveyDate || "",
      surveyorName: detail.surveyorName,
      surveyNote: detail.surveyNote || "",
      publicNoticeNote: detail.publicNoticeNote || "",
      publicNoticeRecorder: detail.publicNoticeRecorder || "",
      publicNoticeReviewDate: detail.publicNoticeReviewDate || "",
      publicNoticeReviewer: detail.publicNoticeReviewer || "",
      groupRegionCode: detail.groupRegionCode || "",
      groupRegionName: detail.groupRegionName || "",
      familyMembers: detail.familyMembers?.length
        ? detail.familyMembers.map((item) => ({ ...item, _tabKey: createMemberTabKey() }))
        : [],
      contracts: normalizeContractInfos(detail.contracts || []),
    });
    activeMainTab.value = "base";
    activeMemberTab.value = form.familyMembers[0]?._tabKey || "";
    activeContractTab.value = form.contracts[0]?._tabKey || "";
    familyMemberViewMode.value = "tabs";
    await nextTick();
    formRef.value?.clearValidate();
    dialogVisible.value = true;
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "加载承包方详情失败");
  } finally {
    loading.value = false;
  }
}

function validateFamilyMembers() {
  if (form.typeCode !== "1") {
    return true;
  }
  for (const member of form.familyMembers) {
    if (!member.name || !member.gender || !member.idType || !member.idNo || !member.relationToHead) {
      activeMainTab.value = "family";
      activeMemberTab.value = member._tabKey;
      familyMemberViewMode.value = "tabs";
      ElMessage.warning("农户类型下，家庭成员信息需要填写完整");
      return false;
    }
    if (member.idType === "1" && !validateChinaId(member.idNo)) {
      activeMainTab.value = "family";
      activeMemberTab.value = member._tabKey;
      familyMemberViewMode.value = "tabs";
      ElMessage.warning(`家庭成员"${member.name || "未命名成员"}"的身份证号格式不正确`);
      return false;
    }
  }
  return true;
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    activeMainTab.value = "base";
    ElMessage.warning("请先修正承包方信息中的校验问题");
    return;
  }
  if (!validateFamilyMembers()) {
    return;
  }

  const payload = {
    code: form.code.trim(),
    typeCode: form.typeCode,
    name: form.name.trim(),
    idType: form.idType,
    idNo: form.idNo.trim(),
    address: form.address.trim(),
    postcode: form.postcode.trim(),
    mobile: form.mobile.trim() || null,
    surveyDate: form.surveyDate || null,
    surveyorName: form.surveyorName.trim(),
    surveyNote: form.surveyNote.trim() || null,
    publicNoticeNote: form.publicNoticeNote.trim() || null,
    publicNoticeRecorder: form.publicNoticeRecorder.trim() || null,
    publicNoticeReviewDate: form.publicNoticeReviewDate || null,
    publicNoticeReviewer: form.publicNoticeReviewer.trim() || null,
    groupRegionCode: form.groupRegionCode || null,
    groupRegionName: form.groupRegionName || null,
    familyMembers:
      form.typeCode === "1"
        ? form.familyMembers.map((item) => ({
            name: item.name.trim(),
            gender: item.gender,
            idType: item.idType,
            idNo: item.idNo.trim(),
            relationToHead: item.relationToHead.trim(),
            noteCode: item.noteCode?.trim() || null,
            isCoOwner: item.isCoOwner || null,
            note: item.note?.trim() || null,
          }))
        : [],
  };

  submitting.value = true;
  try {
    if (props.editingCode) {
      await updateContractor(props.editingCode, payload);
      ElMessage.success("承包方已更新");
    } else {
      await createContractor(payload);
      ElMessage.success("承包方已创建");
    }
    dialogVisible.value = false;
    resetForm();
    emit("saved");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存失败");
  } finally {
    submitting.value = false;
  }
}

// --- Watchers ---
watch(
  () => form.typeCode,
  (value) => {
    if (value === "1" && !form.familyMembers.length) {
      appendFamilyMember();
    }
    activeMainTab.value = "base";
  },
);

watch(activeMainTab, (tabName) => {
  if (tabName === "parcels" && !parcelsTabActivated.value) {
    activateParcelsTab();
  }
});

watch(mapReady, (ready) => {
  if (ready && parcelData.value.length > 0) {
    loadParcels(parcelData.value);
    setTimeout(() => fitToParcels(), 300);
  }
});

watch(dialogVisible, (visible) => {
  if (!visible) {
    parcelsTabActivated.value = false;
    parcelsError.value = "";
    parcelData.value = [];
    selectedParcel.value = null;
    flashDkbm.value = null;
    destroyMap();
  }
});

onBeforeUnmount(() => {
  destroyMap();
});

// --- Expose open methods for parent ---
defineExpose({ openForCreate, openForEdit, loading });
</script>

