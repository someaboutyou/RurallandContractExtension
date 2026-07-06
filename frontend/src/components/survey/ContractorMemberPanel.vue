<template>
  <div class="contractor-member-panel">
    <!-- 变化提示 -->
    <el-alert
      v-if="result.isChanged"
      title="承包方信息已发生变化"
      type="warning"
      :closable="false"
      show-icon
      class="change-alert"
    >
      <template #default>
        <el-button link type="warning" size="small" @click="diffViewer?.open(batchId, contractorUid)">
          查看变化详情
        </el-button>
      </template>
    </el-alert>

    <!-- 承包方基本信息（可编辑） -->
    <div class="section-heading">
      <span class="section-title">承包方信息</span>
      <el-tag v-if="isAddedContractor" type="success" effect="dark" size="small" class="new-tag">NEW</el-tag>
    </div>
    <el-form :model="result" label-position="left" label-width="118px" class="contractor-form">
      <div class="form-grid-3">
        <el-form-item label="承包方编码" :class="changedClass('code')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('code'), beforeValueText('code'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input :model-value="result.code" placeholder="18位编码" maxlength="18" readonly @input="handleCodeInput">
              <template v-if="canGenerateCode" #append>
                <el-button @click="emit('generate-code')">生成</el-button>
              </template>
            </el-input>
          </div>
        </el-form-item>
        <el-form-item label="承包方名称" :class="changedClass('name')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('name'), beforeValueText('name'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.name" placeholder="承包方名称" maxlength="50" />
          </div>
        </el-form-item>
        <el-form-item label="承包方类型" :class="changedClass('typeCode')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('typeCode'), beforeValueText('typeCode'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="result.typeCode">
              <el-option label="农户" value="1" />
              <el-option label="个人" value="2" />
              <el-option label="单位" value="3" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item label="证件类型" :class="changedClass('idType')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('idType'), beforeValueText('idType'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="result.idType">
              <el-option label="居民身份证" value="1" />
              <el-option label="户口簿" value="2" />
              <el-option label="军官证" value="3" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item label="证件号码" :class="changedClass('idNo')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('idNo'), beforeValueText('idNo'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.idNo" placeholder="证件号码" maxlength="20" />
          </div>
        </el-form-item>
        <el-form-item label="联系电话" :class="changedClass('mobile')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('mobile'), beforeValueText('mobile'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.mobile" placeholder="联系电话" maxlength="20" />
          </div>
        </el-form-item>
        <el-form-item label="承包方成员数量" :class="changedClass('memberCount')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('memberCount'), beforeValueText('memberCount'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input :model-value="currentMemberCount" readonly />
          </div>
        </el-form-item>
      </div>
      <el-form-item class="form-span-3" label="承包方地址" :class="changedClass('address')">
        <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('address'), beforeValueText('address'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
          <el-input v-model="result.address" placeholder="详细地址" maxlength="100" />
        </div>
      </el-form-item>
      <div class="form-grid-2">
        <el-form-item label="邮政编码" :class="changedClass('postcode')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('postcode'), beforeValueText('postcode'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.postcode" placeholder="6位邮编" maxlength="6" />
          </div>
        </el-form-item>
        <el-form-item label="村民小组" :class="changedClass('groupRegionName')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('groupRegionName'), beforeValueText('groupRegionName'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.groupRegionName" placeholder="村民小组" maxlength="120" />
          </div>
        </el-form-item>
      </div>
      <div class="section-subtitle">调查信息</div>
      <div class="form-grid-2">
        <el-form-item label="承包方调查员" :class="changedClass('surveyorName')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('surveyorName'), beforeValueText('surveyorName'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.surveyorName" placeholder="调查员姓名" maxlength="50" />
          </div>
        </el-form-item>
        <el-form-item label="承包方调查日期" :class="changedClass('surveyDate')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('surveyDate'), beforeValueText('surveyDate'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-date-picker
              v-model="result.surveyDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              placeholder="选择调查日期"
              style="width: 100%"
            />
          </div>
        </el-form-item>
      </div>
      <el-form-item class="form-span-2" label="承包方调查记事" :class="changedClass('surveyNote')">
        <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('surveyNote'), beforeValueText('surveyNote'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
          <el-input
            v-model="result.surveyNote"
            type="textarea"
            :rows="2"
            placeholder="调查记事"
            maxlength="254"
            show-word-limit
          />
        </div>
      </el-form-item>
      <div class="section-subtitle">公示审核信息</div>
      <el-form-item class="form-span-2" label="公示记事" :class="changedClass('publicNoticeNote')">
        <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('publicNoticeNote'), beforeValueText('publicNoticeNote'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
          <el-input
            v-model="result.publicNoticeNote"
            type="textarea"
            :rows="2"
            placeholder="公示记事"
            maxlength="254"
            show-word-limit
          />
        </div>
      </el-form-item>
      <div class="form-grid-3">
        <el-form-item label="公示记事人" :class="changedClass('publicNoticeRecorder')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('publicNoticeRecorder'), beforeValueText('publicNoticeRecorder'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.publicNoticeRecorder" placeholder="公示记事人" maxlength="50" />
          </div>
        </el-form-item>
        <el-form-item label="公示审核日期" :class="changedClass('publicNoticeReviewDate')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('publicNoticeReviewDate'), beforeValueText('publicNoticeReviewDate'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-date-picker
              v-model="result.publicNoticeReviewDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              placeholder="选择审核日期"
              style="width: 100%"
            />
          </div>
        </el-form-item>
        <el-form-item label="公示审核人" :class="changedClass('publicNoticeReviewer')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('publicNoticeReviewer'), beforeValueText('publicNoticeReviewer'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.publicNoticeReviewer" placeholder="公示审核人" maxlength="50" />
          </div>
        </el-form-item>
      </div>
    </el-form>

    <el-divider />

    <!-- 家庭成员（可编辑表格） -->
    <div class="section-header">
      <span class="section-title">家庭成员（{{ visibleMembers.length }} 人）</span>
      <el-button type="primary" plain size="small" @click="addMember">+ 添加成员</el-button>
    </div>

    <el-table :data="visibleMembers" border size="small" class="member-table">
      <!-- 状态 -->
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag v-if="isNewRow(row)" type="success" size="small">新增</el-tag>
          <el-tag v-else-if="isModifiedRow(row)" type="warning" size="small">已修改</el-tag>
          <el-tag v-else-if="row._deleted" type="danger" size="small">待删除</el-tag>
          <el-tag v-else type="info" size="small">正常</el-tag>
        </template>
      </el-table-column>

      <!-- 姓名 -->
      <el-table-column label="姓名" min-width="100">
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'name'), memberBeforeValueText(row, 'name'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="row.name" size="small" :disabled="row._deleted" :class="memberChangedClass(row, 'name')" />
          </div>
        </template>
      </el-table-column>

      <!-- 性别 -->
      <el-table-column label="性别" width="80">
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'gender'), memberBeforeValueText(row, 'gender'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="row.gender" size="small" :disabled="row._deleted" :class="memberChangedClass(row, 'gender')">
              <el-option label="男" value="1" />
              <el-option label="女" value="2" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 证件类型 -->
      <el-table-column label="证件类型" width="100">
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'idType'), memberBeforeValueText(row, 'idType'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="row.idType" size="small" :disabled="row._deleted" :class="memberChangedClass(row, 'idType')">
              <el-option label="身份证" value="1" />
              <el-option label="户口簿" value="2" />
              <el-option label="军官证" value="3" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 证件号码 -->
      <el-table-column label="证件号码" min-width="160">
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'idNo'), memberBeforeValueText(row, 'idNo'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="row.idNo" size="small" :disabled="row._deleted" :class="memberChangedClass(row, 'idNo')" />
          </div>
        </template>
      </el-table-column>

      <!-- 与户主关系 -->
      <el-table-column label="与户主关系" width="130">
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'relationToHead'), memberBeforeValueText(row, 'relationToHead'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select
              v-model="row.relationToHead"
              size="small"
              filterable
              :disabled="row._deleted"
              :class="memberChangedClass(row, 'relationToHead')"
              @change="handleRelationChange(row)"
            >
              <el-option
                v-for="opt in relationOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 共有人 -->
      <el-table-column label="共有人" width="80">
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'isCoOwner'), memberBeforeValueText(row, 'isCoOwner'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="row.isCoOwner" size="small" :disabled="row._deleted" :class="memberChangedClass(row, 'isCoOwner')">
              <el-option label="是" value="1" />
              <el-option label="否" value="0" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 户主标记与操作 -->
      <el-table-column label="户主" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.isHouseholdHead" type="danger" size="small" effect="dark">户主</el-tag>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'note'), memberBeforeValueText(row, 'note'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="row.note" size="small" :disabled="row._deleted" :class="memberChangedClass(row, 'note')" />
          </div>
        </template>
      </el-table-column>

      <el-table-column label="变化原因" min-width="130">
        <template #default="{ row }">
          <el-select
            v-if="isNewRow(row)"
            v-model="row.changeReason"
            size="small"
            placeholder="新增原因"
          >
            <el-option label="新生" value="新生" />
            <el-option label="婚进" value="婚进" />
            <el-option label="其他" value="其他" />
          </el-select>
          <el-select
            v-else-if="row._deleted"
            v-model="row.changeReason"
            size="small"
            placeholder="删除原因"
          >
            <el-option label="去世" value="去世" />
            <el-option label="婚出" value="婚出" />
            <el-option label="迁出" value="迁出" />
            <el-option label="其他" value="其他" />
          </el-select>
          <el-input
            v-else
            v-model="row.changeReason"
            size="small"
            placeholder="变化说明"
            maxlength="500"
          />
        </template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row._deleted && !row.isHouseholdHead"
            link
            type="danger"
            size="small"
            @click="toggleDelete(row)"
          >
            删除
          </el-button>
          <el-button
            v-if="row._deleted"
            link
            type="primary"
            size="small"
            @click="toggleDelete(row)"
          >
            恢复
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <ChangeDiffViewer ref="diffViewer" />
    <div
      v-if="diffTooltip.visible"
      class="floating-diff-tooltip"
      :style="{ left: `${diffTooltip.x}px`, top: `${diffTooltip.y}px` }"
    >
      {{ diffTooltip.text }}
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import ChangeDiffViewer from "./ChangeDiffViewer.vue";
import { useDictionary } from "../../composables/useDictionary";

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  result: { type: Object, required: true },
  changedFields: { type: Array, default: () => [] },
  canGenerateCode: { type: Boolean, default: false },
});

const emit = defineEmits(["update:result", "generate-code"]);

const { options: relationOptions } = useDictionary("nyt2539_c20_relation_to_head");

const diffViewer = ref(null);
const diffTooltip = ref({
  visible: false,
  text: "",
  x: 0,
  y: 0,
});
const isAddedContractor = computed(() => props.result.resultStatus === "added");
const typeLabelMap = { "1": "农户", "2": "个人", "3": "单位" };
const idTypeLabelMap = { "1": "居民身份证", "2": "户口簿", "3": "军官证" };
const genderLabelMap = { "1": "男", "2": "女" };
const yesNoLabelMap = { "1": "是", "0": "否" };
const dateFields = new Set(["surveyDate", "publicNoticeReviewDate"]);

function normalizeInput(value) {
  return String(value || "").trim();
}

function normalizeDigits(value) {
  return String(value || "").replace(/\D/g, "");
}

function handleCodeInput(value) {
  props.result.code = normalizeDigits(value).slice(0, 18);
}

function tooltipPosition(event) {
  const margin = 12;
  const tooltipWidth = Math.min(360, window.innerWidth - margin * 2);
  return {
    x: Math.max(margin, Math.min(event.clientX + margin, window.innerWidth - tooltipWidth - margin)),
    y: Math.max(margin, Math.min(event.clientY + margin, window.innerHeight - 80)),
  };
}

function showDiffTooltip(enabled, text, event) {
  if (!enabled) return;
  const position = tooltipPosition(event);
  diffTooltip.value = {
    visible: true,
    text,
    ...position,
  };
}

function moveDiffTooltip(event) {
  if (!diffTooltip.value.visible) return;
  Object.assign(diffTooltip.value, tooltipPosition(event));
}

function hideDiffTooltip() {
  diffTooltip.value.visible = false;
}

// 初始化：如果 groupRegionName 为空但 groupRegionCode 有值，用 code 填充
watch(
  () => props.result,
  (r) => {
    if (r && !r.groupRegionName && r.groupRegionCode) {
      r.groupRegionName = r.groupRegionCode;
    }
  },
  { immediate: true },
);

// 记录初始快照用于判断修改
const initialSnapshots = ref(new Map());

watch(
  () => props.result?.familyMembers,
  (members) => {
    initialSnapshots.value = new Map();
    if (!members) return;
    for (const m of members) {
      // 为新加载的成员初始化 UI 标记字段
      if (m._deleted === undefined) m._deleted = false;
      if (m._isNew === undefined) m._isNew = false;
      if (m.memberUid) {
        initialSnapshots.value.set(m.memberUid, {
          name: normalizeInput(m.name),
          gender: normalizeInput(m.gender),
          idType: normalizeInput(m.idType),
          idNo: normalizeInput(m.idNo),
          relationToHead: normalizeInput(m.relationToHead),
          isCoOwner: normalizeInput(m.isCoOwner),
          note: normalizeInput(m.note),
        });
      }
    }
  },
  { immediate: true },
);

// 直接返回原始数组，避免展开拷贝导致 v-model 和回调失效
const visibleMembers = computed(() => props.result.familyMembers || []);
const currentMemberCount = computed(() => visibleMembers.value.filter((m) => !m._deleted).length);
const baseMembersByUid = computed(() => {
  const pairs = (props.result.baseContractor?.familyMembers || []).map((member) => [member.memberUid, member]);
  return new Map(pairs);
});

function isNewRow(row) {
  return row._isNew || (!row.memberUid && row.memberResultStatus === "added");
}

function isModifiedRow(row) {
  if (row._deleted || isNewRow(row)) return false;
  const snap = getBaseMember(row);
  if (!snap) return row.isChanged;
  return ["name", "gender", "idType", "idNo", "relationToHead", "isCoOwner", "note"].some((field) =>
    isMemberFieldChanged(row, field),
  );
}

function addMember() {
  props.result.familyMembers.push({
    memberUid: "",
    name: "",
    gender: "1",
    idType: "1",
    idNo: "",
    relationToHead: "09",
    noteCode: "",
    isCoOwner: "0",
    note: "",
    memberResultStatus: "added",
    surveyStatus: "surveyed",
    isHouseholdHead: false,
    isUrbanSettled: false,
    isMarriedOutWoman: false,
    isDeceased: false,
    isFiveGuarantees: false,
    changeReason: "新生",
    policyBasis: "",
    rightsDisposition: "",
    remark: "",
    _isNew: true,
  });
}

function setAsHead(row) {
  // 取消所有成员的户主标记
  for (const m of props.result.familyMembers) {
    m.isHouseholdHead = false;
  }
  // 设置目标为户主
  row.isHouseholdHead = true;
  row.relationToHead = "01";
  // 承包方名称默认随户主名称
  if (row.name) {
    props.result.name = row.name;
  }
}

function isHeadRelation(value) {
  if (value === "01") return true;
  const label = relationOptions.value.find((item) => item.value === value)?.label || "";
  return label.includes("本人") || label.includes("户主");
}

function handleRelationChange(row) {
  if (isHeadRelation(row.relationToHead)) {
    setAsHead(row);
    return;
  }
  if (row.isHouseholdHead) {
    row.isHouseholdHead = false;
  }
}

function toggleDelete(row) {
  if (!row._deleted && !getBaseMember(row)) {
    const index = props.result.familyMembers.indexOf(row);
    if (index >= 0) {
      props.result.familyMembers.splice(index, 1);
    }
    return;
  }
  row._deleted = !row._deleted;
  if (row._deleted) {
    row.memberResultStatus = "deleted";
    row.changeReason = row.changeReason || "去世";
  } else {
    row.memberResultStatus = isNewRow(row) ? "added" : "normal";
    if (!isNewRow(row)) row.changeReason = "";
  }
}

// 获取有效成员（排除被标记删除的）
function getValidMembers() {
  return (props.result.familyMembers || []).filter((m) => !m._deleted);
}

// 变化高亮
function displayValue(field, value) {
  if (value === undefined || value === null || value === "") {
    return "空";
  }
  if (dateFields.has(field)) {
    return formatDateValue(value);
  }
  if (field === "typeCode") return typeLabelMap[value] || value;
  if (field === "idType") return idTypeLabelMap[value] || value;
  if (field === "gender") return genderLabelMap[value] || value;
  if (field === "isCoOwner") return yesNoLabelMap[value] || value;
  if (field === "relationToHead") {
    return relationOptions.value.find((item) => item.value === value)?.label || value;
  }
  return String(value);
}

function formatDateValue(value) {
  if (!value) return "空";
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.toISOString().slice(0, 10);
  }
  return String(value).slice(0, 10);
}

function contractorCurrentValue(field) {
  return field === "memberCount" ? currentMemberCount.value : props.result[field];
}

function contractorBaseValue(field) {
  return props.result.baseContractor?.[field];
}

function isContractorFieldChanged(field) {
  if (isAddedContractor.value || !props.result.baseContractor) {
    return false;
  }
  if (dateFields.has(field)) {
    return formatDateValue(contractorCurrentValue(field)) !== formatDateValue(contractorBaseValue(field));
  }
  return normalizeInput(contractorCurrentValue(field)) !== normalizeInput(contractorBaseValue(field));
}

function beforeValueText(field) {
  return `变更前：${displayValue(field, contractorBaseValue(field))}`;
}

function getBaseMember(row) {
  if (!row?.memberUid) return null;
  return baseMembersByUid.value.get(row.memberUid) || null;
}

function isMemberFieldChanged(row, field) {
  if (row._deleted || isNewRow(row)) {
    return false;
  }
  const base = getBaseMember(row);
  if (!base) {
    return false;
  }
  return normalizeInput(row[field]) !== normalizeInput(base[field]);
}

function memberChangedClass(row, field) {
  return isMemberFieldChanged(row, field) ? "cell-field-changed" : "";
}

function memberBeforeValueText(row, field) {
  return `变更前：${displayValue(field, getBaseMember(row)?.[field])}`;
}

function changedClass(field) {
  return isContractorFieldChanged(field) ? "field-changed" : "";
}

defineExpose({ getValidMembers });
</script>

<style scoped>
.contractor-member-panel { min-height: 200px; }
.change-alert { margin-bottom: 12px; }

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.section-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.section-heading .section-title {
  margin-bottom: 0;
}
.new-tag {
  flex: 0 0 auto;
}
.section-subtitle {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin: 4px 0 8px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.contractor-form {
  margin-bottom: 0;
  max-width: 1480px;
}
.contractor-form :deep(.el-form-item) {
  min-width: 0;
  margin-bottom: 10px;
  align-items: center;
}
.contractor-form :deep(.el-form-item__label) {
  height: 34px;
  line-height: 34px;
  justify-content: flex-start;
  padding-right: 10px;
  color: #606266;
}
.contractor-form :deep(.el-form-item__content) {
  min-width: 0;
  width: 100%;
  display: flex;
  flex: 1 1 auto;
}
.diff-trigger {
  display: block;
  width: 100%;
  min-width: 0;
}
.contractor-form :deep(.el-input),
.contractor-form :deep(.el-select),
.contractor-form :deep(.el-date-editor),
.contractor-form :deep(.el-textarea),
.member-table :deep(.el-input),
.member-table :deep(.el-select) {
  width: 100% !important;
}
.contractor-form :deep(.el-input__wrapper),
.contractor-form :deep(.el-select__wrapper),
.member-table :deep(.el-input__wrapper),
.member-table :deep(.el-select__wrapper) {
  width: 100%;
  box-sizing: border-box;
}
.form-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 18px;
  align-items: start;
}
.form-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
  align-items: start;
}
.form-span-2 {
  grid-column: span 2;
}
.form-span-3 {
  grid-column: 1 / -1;
}

.member-table { margin-top: 0; }

.field-changed :deep(.el-input__wrapper),
.field-changed :deep(.el-select__wrapper),
.field-changed :deep(.el-textarea__inner),
.cell-field-changed :deep(.el-input__wrapper),
.cell-field-changed :deep(.el-select__wrapper) {
  background-color: #fdf6ec;
  box-shadow: 0 0 0 1px #e6a23c inset;
}
.field-changed {
  position: relative;
}
.floating-diff-tooltip {
  position: fixed;
  z-index: 3000;
  pointer-events: none;
  max-width: min(360px, calc(100vw - 24px));
  padding: 6px 8px;
  color: #fff;
  font-size: 12px;
  line-height: 1.4;
  white-space: normal;
  background: #303133;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.16);
}
@media (max-width: 1180px) {
  .form-grid-3 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 860px) {
  .form-grid-3,
  .form-grid-2 {
    grid-template-columns: 1fr;
  }
}
</style>
