<template>
  <div class="m-detail">
    <div v-if="loading" class="m-detail__loading">
      <van-loading size="22px" vertical>加载中…</van-loading>
    </div>

    <template v-else-if="result">
      <div class="m-detail__hero">
        <div class="m-detail__hero-row">
          <p class="m-detail__name">{{ form.name || "（未命名）" }}</p>
          <van-button
            v-if="writable"
            size="small"
            :type="editing ? 'default' : 'primary'"
            round
            @click="toggleEditing"
          >
            {{ editing ? "退出编辑" : "编辑资料" }}
          </van-button>
          <span v-else-if="isLocked" class="m-detail__readonly-hint">已定案·仅查看</span>
          <span v-else class="m-detail__readonly-hint">未分配·仅查看</span>
        </div>
        <div v-if="statusText || resultStatusText || result.isChanged" class="m-detail__tags">
          <van-tag v-if="statusText" :type="statusTagType">{{ statusText }}</van-tag>
          <van-tag v-if="resultStatusText" type="warning" plain>{{ resultStatusText }}</van-tag>
          <van-tag v-if="result.isChanged" type="danger" plain>信息有变化</van-tag>
        </div>
      </div>

      <!-- ══════════ 编辑模式：承包方信息表单 ══════════ -->
      <template v-if="editing">
        <van-cell-group inset title="承包方信息（18位编码由系统管理）">
          <van-field v-model="form.code" label="承包方编码" readonly />
          <van-field v-model="form.name" required label="承包方名称" placeholder="请输入名称" maxlength="50" clearable />
          <van-field
            :model-value="typeLabel"
            readonly
            required
            is-link
            label="承包方类型"
            placeholder="请选择"
            @click="pick('typeCode', '承包方类型', TYPE_OPTIONS)"
          />
          <van-field
            :model-value="idTypeLabel"
            readonly
            required
            is-link
            label="证件类型"
            placeholder="请选择"
            @click="pick('idType', '证件类型', ID_TYPE_OPTIONS)"
          />
          <van-field v-model="form.idNo" required label="证件号码" placeholder="请输入证件号码" :maxlength="20" clearable />
          <van-field v-model="form.mobile" label="联系电话" placeholder="选填" maxlength="20" clearable />
          <van-field v-model="form.address" required label="承包方地址" placeholder="请输入详细地址" maxlength="100" clearable />
          <van-field v-model="form.postcode" required label="邮政编码" placeholder="6位邮编" maxlength="6" clearable />
          <van-field v-model="form.groupRegionName" label="村民小组" placeholder="选填" maxlength="120" clearable />
        </van-cell-group>

        <van-cell-group inset title="调查信息">
          <van-field v-model="form.surveyorName" label="调查员" placeholder="调查员姓名" maxlength="50" clearable />
          <van-field
            :model-value="form.surveyDate || ''"
            readonly
            is-link
            label="调查日期"
            placeholder="请选择"
            @click="pickDate('surveyDate', '调查日期')"
          />
          <van-field
            v-model="form.surveyNote"
            label="调查记事"
            type="textarea"
            rows="2"
            autosize
            placeholder="选填"
            maxlength="254"
            show-word-limit
          />
        </van-cell-group>

        <van-cell-group inset title="公示审核信息">
          <van-field
            v-model="form.publicNoticeNote"
            label="公示记事"
            type="textarea"
            rows="2"
            autosize
            placeholder="选填"
            maxlength="254"
            show-word-limit
          />
          <van-field v-model="form.publicNoticeRecorder" label="公示记事人" placeholder="选填" maxlength="50" clearable />
          <van-field
            :model-value="form.publicNoticeReviewDate || ''"
            readonly
            is-link
            label="审核日期"
            placeholder="请选择"
            @click="pickDate('publicNoticeReviewDate', '公示审核日期')"
          />
          <van-field v-model="form.publicNoticeReviewer" label="公示审核人" placeholder="选填" maxlength="50" clearable />
        </van-cell-group>

        <van-cell-group v-if="showChangeFields" inset title="变化信息">
          <van-field
            v-model="form.changeReason"
            label="变化原因"
            type="textarea"
            rows="2"
            autosize
            placeholder="留空将由系统按操作类型自动填写"
            maxlength="500"
            show-word-limit
          />
          <van-field
            v-model="form.policyBasis"
            label="政策依据"
            type="textarea"
            rows="2"
            autosize
            placeholder="选填：如 XX 文件 / 村组决议"
            maxlength="500"
            show-word-limit
          />
        </van-cell-group>

        <van-cell-group :title="`家庭成员（${validMembers.length}）`">
          <div v-for="member in members" :key="memberKey(member)" class="m-member">
            <template v-if="!member._deleted">
              <div class="m-member__head">
                <div class="m-member__head-main">
                  <span class="m-member__name">{{ member.name || "（未填姓名）" }}</span>
                  <van-tag v-if="member.gender" type="primary" plain>{{ genderLabel(member.gender) }}</van-tag>
                  <van-tag v-if="isHouseholdHead(member)" color="#ee0a24" plain>户主</van-tag>
                  <van-tag v-if="member.isCoOwner === '1'" type="success" plain>共有人</van-tag>
                  <van-tag v-if="member._isNew" type="success">新增</van-tag>
                </div>
                <div class="m-member__ops">
                  <van-button size="mini" plain type="primary" @click="openMemberEdit(member)">编辑</van-button>
                  <van-button size="mini" plain type="danger" @click="openDeleteMember(member)">删除</van-button>
                </div>
              </div>
              <div class="m-member__row">
                <span class="m-member__label">{{ idTypeLabelOf(member.idType) }}</span>
                <span class="m-member__value">{{ member.idNo ? maskIdNo(member.idNo) : "—" }}</span>
              </div>
              <div class="m-member__row">
                <span class="m-member__label">与户主关系</span>
                <span class="m-member__value">{{ relationLabel(member.relationToHead) }}</span>
              </div>
            </template>
            <template v-else>
              <div class="m-member__head">
                <div class="m-member__head-main">
                  <span class="m-member__name m-member__name--deleted">{{ member.name || "（未填姓名）" }}</span>
                  <van-tag type="danger">待删除</van-tag>
                  <span class="m-member__reason">{{ member.changeReason || "" }}</span>
                </div>
                <div class="m-member__ops">
                  <van-button size="mini" plain type="warning" @click="restoreMember(member)">恢复</van-button>
                </div>
              </div>
            </template>
          </div>
          <van-cell v-if="!members.length" title="暂无成员" label="点下方按钮添加" />
        </van-cell-group>

        <div class="m-detail__add-member">
          <van-button round type="success" icon="scan" :disabled="!ocrAvailable" @click="openAddMember('idcard')">
            身份证采集添加
          </van-button>
          <van-button round plain icon="plus" @click="openAddMember(false)">手动填写</van-button>
        </div>
        <p v-if="!ocrAvailable" class="m-detail__hint">证件采集仅 App 内可用，浏览器请手动填写</p>

        <div class="m-detail__save-bar">
          <span class="m-detail__save-hint">{{ hasUnsaved ? `有修改尚未保存` : "暂无修改" }}</span>
          <van-button round type="success" :loading="saving" @click="handleSave">保存调查结果</van-button>
        </div>
      </template>

      <!-- ══════════ 查看模式 ══════════ -->
      <template v-else>
        <van-cell-group inset title="承包方信息">
          <van-cell title="承包方编码" :value="result.code || '—'" />
          <van-cell title="承包方类型" :value="typeLabel" />
          <van-cell title="证件类型" :value="idTypeLabel" />
          <van-cell title="证件号码" :value="result.idNo || '—'" />
          <van-cell title="联系电话" :value="result.mobile || '—'" />
          <van-cell title="邮政编码" :value="result.postcode || '—'" />
          <van-cell title="村民小组" :value="groupRegionText" />
          <van-cell title="成员数量" :value="`${displayMemberCount} 人`" />
          <van-cell title="调查员" :value="result.surveyorName || '—'" />
          <van-cell title="调查日期" :value="result.surveyDate || '—'" />
          <van-cell title="承包方地址" :value="result.address || '—'" value-class="m-cell-long" />
          <van-cell title="调查记述" :value="result.surveyNote || '—'" value-class="m-cell-long" />
          <van-cell title="公示记事" :value="result.publicNoticeNote || '—'" value-class="m-cell-long" />
        </van-cell-group>

        <van-cell-group v-if="hasChangeInfo" inset title="变化信息">
          <van-cell title="变化类型" :value="changeTypeLabel" />
          <van-cell title="变化原因" :value="result.changeReason || '—'" value-class="m-cell-long" />
          <van-cell title="政策依据" :value="result.policyBasis || '—'" value-class="m-cell-long" />
          <van-cell title="依据说明" :value="result.evidenceSummary || '—'" value-class="m-cell-long" />
          <van-cell title="备注" :value="result.remark || '—'" value-class="m-cell-long" />
        </van-cell-group>

        <van-cell-group inset :title="`家庭成员（${members.length}）`">
          <div
            v-for="member in members"
            :key="memberKey(member)"
            class="m-member"
          >
            <div class="m-member__head">
              <span class="m-member__name">{{ member.name || "（未填姓名）" }}</span>
              <van-tag v-if="member.gender" type="primary" plain>{{ genderLabel(member.gender) }}</van-tag>
              <van-tag v-if="isHouseholdHead(member)" color="#ee0a24" plain>户主</van-tag>
              <van-tag v-if="member.isCoOwner === '1'" type="success" plain>共有人</van-tag>
            </div>
            <div class="m-member__row">
              <span class="m-member__label">{{ idTypeLabelOf(member.idType) }}</span>
              <span class="m-member__value">{{ member.idNo ? maskIdNo(member.idNo) : "—" }}</span>
            </div>
            <div class="m-member__row">
              <span class="m-member__label">与户主关系</span>
              <span class="m-member__value">{{ relationLabel(member.relationToHead) }}</span>
            </div>
            <div v-if="member.note" class="m-member__row">
              <span class="m-member__label">备注</span>
              <span class="m-member__value">{{ member.note }}</span>
            </div>
          </div>
          <van-cell v-if="!members.length" title="暂无成员数据" />
        </van-cell-group>

        <van-cell-group inset title="成果查看">
          <van-cell title="承包地示意图" is-link value="查看" @click="goSketch" />
          <van-cell title="合同信息" is-link value="查看" @click="goContract" />
        </van-cell-group>

        <van-cell-group inset title="采集作业">
          <van-cell title="地块与勾绘" is-link value="进入" @click="goParcels" />
          <van-cell title="拍照附件" is-link value="进入" @click="goAttachments" />
        </van-cell-group>

        <div class="m-detail__actions">
          <van-button round block type="primary" @click="goAttachments">继续采集</van-button>
        </div>
      </template>
    </template>

    <van-empty v-else description="未找到该承包方的调查数据" />

    <!-- 通用 picker（承包方表单用） -->
    <van-popup :show="picker.visible" position="bottom" round>
      <van-picker
        :title="picker.title"
        :columns="picker.options.map((o) => ({ text: o.label, value: o.value }))"
        @confirm="onPickConfirm"
        @cancel="picker.visible = false"
      />
    </van-popup>

    <!-- 通用日期 picker -->
    <van-popup :show="datePick.visible" position="bottom" round>
      <van-date-picker
        v-model="datePick.value"
        :title="datePick.title"
        :min-date="MIN_DATE"
        :max-date="MAX_DATE"
        @confirm="onDateConfirm"
        @cancel="datePick.visible = false"
      />
    </van-popup>

    <!-- 删除成员原因 picker -->
    <van-popup :show="deleteReason.visible" position="bottom" round>
      <van-picker
        title="选择删除原因"
        :columns="DELETE_REASON_OPTIONS.map((o) => ({ text: o, value: o }))"
        @confirm="onDeleteMemberConfirm"
        @cancel="deleteReason.visible = false"
      />
    </van-popup>

    <!-- 成员编辑 / 新增弹层 -->
    <MemberEditPopup
      v-model:show="memberPopupVisible"
      :member="editingMember"
      :relation-options="relationOptions"
      :auto-scan="memberAutoScan"
      :scan-mode="addMemberScanMode"
      @confirm="onMemberConfirm"
    />
  </div>
</template>

<script setup>
/**
 * 承包方调查录入（移动端）：查看 + 编辑 + 作业入口。
 *
 * ## 数据源
 * - 结果：`GET /surveys/batches/{batchId}/results/{contractorUid}` → SurveyContractorRead
 * - 写权限：任务行 `SurveyTaskRead.canWrite`（后端按 ensure_task_write_permission 算，
 *   与 PC 端同一口径；前端只消费不自算，取不到时按只读兜底）
 * - 编辑闸门：`LOCKED_SURVEY_STATUSES`（只有 confirmed 锁编辑；skipped 仍可补录），
 *   与 PC 端 / 后端 base.py 三方同源，别改成定案态集合
 *
 * ## 编辑模型（对齐 PC 端 ContractorResultDialog.handleSaveResult）
 * - 承包方字段与成员改动**先在本页暂存**（成员标 `_isNew` / `_deleted`），
 *   点「保存调查结果」一次性走 `updateSurveyResult`：
 *   familyMembers 提交未删除成员（去掉暂存标记），deletedMembers 提交
 *   `{memberUid, changeReason}`，pendingOperations 恒为空（移动端不做地块互换等操作）；
 * - issuer / baseIssuer 不回传（PC 端同样剥离；回传打开弹窗时的旧值会把
 *   发包方改回去 —— 状态机回退的同类坑）；
 * - surveyStatus 原样回传（页面不提供状态选择，用户没有显式改状态）；
 * - 证件号码校验走 evaluateIdNoIssue 三档口径：本次录入/改动从严拦，
 *   未改动的历史值（存量校验位有误）降级为提示，避免整户被锁死；
 * - 关系选「本人/户主」= 设为户主：isHouseholdHead 置真 + 关系码写 "02"
 *   （存量 "01"/"02" 并存，新写入统一 "02"），承包方名称随户主。
 *
 * ## 成员 OCR 采集
 * 添加成员默认走「身份证采集」：复用附件页同一套链路（自动抓拍 → 方向重试识别 →
 * 人工确认），识别结果回填姓名/证件号码，性别由号码反推。
 */
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { fetchSurveyResult, fetchSurveyTasks, updateSurveyResult } from "../../api/survey";
import { useDictionary } from "../../composables/useDictionary";
import { changeTypeMap, resultStatusMap, surveyStatusMap } from "../../config/gisFieldMaps";
import { LOCKED_SURVEY_STATUSES } from "../../config/surveyStatus";
import { evaluateIdNoIssue } from "../../utils/validators";
import { markTaskListDirty } from "../taskListState";
import { isOcrAvailable } from "../ocr/idCapture.js";
import MemberEditPopup from "../components/MemberEditPopup.vue";
import {
  VanButton,
  VanCell,
  VanCellGroup,
  VanDatePicker,
  VanEmpty,
  VanField,
  VanLoading,
  VanPicker,
  VanPopup,
  VanTag,
  showDialog,
  showToast,
} from "../ui.js";

const MIN_DATE = new Date(1900, 0, 1);
const MAX_DATE = new Date(2100, 11, 31);

const TYPE_OPTIONS = [
  { label: "农户", value: "1" },
  { label: "个人", value: "2" },
  { label: "单位", value: "3" },
];
const ID_TYPE_OPTIONS = [
  { label: "居民身份证", value: "1" },
  { label: "户口簿", value: "2" },
  { label: "军官证", value: "3" },
];
const DELETE_REASON_OPTIONS = ["去世", "婚出", "迁出", "其他"];

const MEMBER_GENDER_MAP = { "1": "男", "2": "女" };
const MEMBER_ID_TYPE_MAP = { "1": "身份证", "2": "户口簿", "3": "军官证" };
const extraStatusMap = { in_progress: "调查中", deregistered: "已注销" };

const route = useRoute();
const router = useRouter();

const batchId = computed(() => route.params.batchId);
const contractorUid = computed(() => route.params.contractorUid);

// 与户主关系字典（码 → 中文标签），与 PC 端 ContractorMemberPanel 同一字典
const { options: relationOptions, labelOf: relationLabelOf } = useDictionary(
  "nyt2539_c20_relation_to_head",
);

const loading = ref(true);
const result = ref(null);
const canWrite = ref(false);
const editing = ref(false);
const saving = ref(false);
const ocrAvailable = isOcrAvailable();

/** 承包方可编辑字段（暂存态，保存时一次性提交） */
const form = reactive({
  code: "", typeCode: "1", name: "", idType: "1", idNo: "", mobile: "",
  address: "", postcode: "", groupRegionCode: "", groupRegionName: "",
  surveyorName: "", surveyDate: "", surveyNote: "",
  publicNoticeNote: "", publicNoticeRecorder: "", publicNoticeReviewDate: "", publicNoticeReviewer: "",
  surveyStatus: "surveyed", resultStatus: "normal", changeType: "none",
  changeReason: "", policyBasis: "", remark: "",
});
let formSnapshot = "{}";
/** 成员暂存数组（含 _isNew/_deleted 标记）；originalMembers 保存加载时的基线快照 */
const members = ref([]);
let originalMembers = [];

const editingMember = ref(null);
const memberPopupVisible = ref(false);
const memberAutoScan = ref(false);
/** 新增成员时的扫描入口模式："idcard" | "household" */
const addMemberScanMode = ref("idcard");
let editingMemberWasHead = false;
const deleteReason = reactive({ visible: false, target: null });

/* ---- 通用 picker / date picker ---- */
const picker = reactive({ visible: false, title: "", key: "", options: [] });
const datePick = reactive({ visible: false, title: "", key: "", value: [] });

function pick(key, title, options) {
  Object.assign(picker, { visible: true, title, key, options });
}

function onPickConfirm({ selectedOptions }) {
  const value = selectedOptions?.[0]?.value;
  if (value !== undefined) form[picker.key] = value;
  picker.visible = false;
}

function pickDate(key, title) {
  const current = String(form[key] || "");
  const now = new Date();
  const [y, m, d] = current
    ? current.split("-").map(Number)
    : [now.getFullYear(), now.getMonth() + 1, now.getDate()];
  Object.assign(datePick, {
    visible: true,
    title,
    key,
    value: [String(y), String(m).padStart(2, "0"), String(d).padStart(2, "0")],
  });
}

function onDateConfirm({ selectedValues }) {
  form[datePick.key] = (selectedValues || []).join("-");
  datePick.visible = false;
}

/* ---- 派生状态 ---- */
const rawStatus = computed(() => result.value?.surveyStatus || result.value?.taskStatus || "");
const statusText = computed(() => surveyStatusMap[rawStatus.value] || extraStatusMap[rawStatus.value] || "");
const statusTagType = computed(() => {
  switch (rawStatus.value) {
    case "confirmed":
      return "success";
    case "surveyed":
    case "changed":
    case "in_progress":
      return "primary";
    case "skipped":
    case "deregistered":
      return "warning";
    default:
      return "default";
  }
});
const resultStatusText = computed(() => {
  const status = result.value?.resultStatus || "normal";
  return status === "normal" ? "" : resultStatusMap[status] || status;
});
const isLocked = computed(() => LOCKED_SURVEY_STATUSES.includes(rawStatus.value));
const writable = computed(() => canWrite.value && !isLocked.value);

const hasChangeInfo = computed(
  () => Boolean(result.value?.isChanged) || (result.value?.changeType && result.value.changeType !== "none"),
);
const showChangeFields = computed(
  () => hasChangeInfo.value || (form.changeType && form.changeType !== "none"),
);
const changeTypeLabel = computed(() => changeTypeMap[form.changeType] || form.changeType || "—");

const typeLabel = computed(() => TYPE_OPTIONS.find((o) => o.value === form.typeCode)?.label || form.typeCode || "—");
const idTypeLabel = computed(() => ID_TYPE_OPTIONS.find((o) => o.value === form.idType)?.label || form.idType || "—");
const groupRegionText = computed(() => result.value?.groupRegionName || result.value?.groupRegionCode || "—");
const displayMemberCount = computed(() => result.value?.memberCount ?? members.value.length);
const validMembers = computed(() => members.value.filter((m) => !m._deleted));

const MEMBER_DIFF_KEYS = ["name", "gender", "idType", "idNo", "relationToHead", "isCoOwner", "note", "isHouseholdHead", "changeReason"];

/** 暂存改动（保存条提示用） */
const hasUnsaved = computed(() => {
  if (JSON.stringify(form) !== formSnapshot) return true;
  if (members.value.length !== originalMembers.length) return true;
  return members.value.some((m) => {
    if (m._isNew || m._deleted) return true;
    const orig = originalMembers.find((o) => o.memberUid && o.memberUid === m.memberUid);
    if (!orig) return true;
    return MEMBER_DIFF_KEYS.some((k) => String(m[k] ?? "") !== String(orig[k] ?? ""));
  });
});

/* ---- 展示辅助（沿用查看视图的口径） ---- */
function memberKey(member) {
  return member.memberUid || member.idNo || member.name || `idx-${members.value.indexOf(member)}`;
}

function genderLabel(value) {
  return MEMBER_GENDER_MAP[value] || value || "";
}

function idTypeLabelOf(value) {
  return MEMBER_ID_TYPE_MAP[value] || value || "证件";
}

function relationLabel(value) {
  if (!value) return "—";
  return relationLabelOf(value, "") || value;
}

function isHouseholdHead(member) {
  if (!member) return false;
  if (member.isHouseholdHead) return true;
  // 接口不一定回传 isHouseholdHead，兜底按关系码判（存量 01/02 并存，两个都认）
  if (member.relationToHead === "01") return true;
  const label = relationOptions.value.find((item) => item.value === member.relationToHead)?.label || "";
  return label.includes("本人") || label.includes("户主");
}

function maskIdNo(value) {
  const text = String(value);
  if (text.length < 8) return text;
  return `${text.slice(0, 6)}${"*".repeat(text.length - 10)}${text.slice(-4)}`;
}

/* ---- 数据加载 ---- */
function hydrateForm(data) {
  Object.assign(form, {
    code: data.code || "",
    typeCode: data.typeCode || "1",
    name: data.name || "",
    idType: data.idType || "1",
    idNo: data.idNo || "",
    mobile: data.mobile || "",
    address: data.address || "",
    postcode: data.postcode || "",
    groupRegionCode: data.groupRegionCode || "",
    groupRegionName: data.groupRegionName || "",
    surveyorName: data.surveyorName || "",
    surveyDate: data.surveyDate || "",
    surveyNote: data.surveyNote || "",
    publicNoticeNote: data.publicNoticeNote || "",
    publicNoticeRecorder: data.publicNoticeRecorder || "",
    publicNoticeReviewDate: data.publicNoticeReviewDate || "",
    publicNoticeReviewer: data.publicNoticeReviewer || "",
    surveyStatus: data.surveyStatus || "surveyed",
    resultStatus: data.resultStatus || "normal",
    changeType: data.changeType || "none",
    changeReason: data.changeReason || "",
    policyBasis: data.policyBasis || "",
    remark: data.remark || "",
  });
  formSnapshot = JSON.stringify(form);
  members.value = (data.familyMembers || []).map((m) => ({ ...m }));
  originalMembers = (data.familyMembers || []).map((m) => ({ ...m }));
}

async function loadCanWrite(code) {
  try {
    const { data } = await fetchSurveyTasks(batchId.value, {
      page: 1,
      page_size: 100,
      keyword: code || undefined,
    });
    const items = data?.data?.items || [];
    const row = items.find((item) => item.contractorUid === contractorUid.value);
    canWrite.value = Boolean(row?.canWrite);
  } catch {
    canWrite.value = false; // 取不到任务行按只读兜底（与后端默认 False 同方向）
  }
}

async function loadResult() {
  loading.value = true;
  try {
    const { data } = await fetchSurveyResult(batchId.value, contractorUid.value);
    result.value = data?.data || null;
    if (result.value) {
      hydrateForm(result.value);
      await loadCanWrite(result.value.code);
    }
  } catch (error) {
    showToast(error?.response?.data?.detail || "调查数据加载失败");
    result.value = null;
  } finally {
    loading.value = false;
  }
}

/* ---- 编辑模式进出 ---- */
function toggleEditing() {
  if (editing.value) {
    // 退出编辑：丢弃暂存改动，回到基线
    hydrateForm(result.value);
  }
  editing.value = !editing.value;
}

/* ---- 成员编辑 / 新增 / 删除 ---- */
/**
 * 打开新增成员弹层。scanMode = "idcard" | "household"（分入口直接进对应扫描）；
 * false = 手动填写不进扫描。
 */
function openAddMember(scanMode) {
  editingMember.value = null;
  editingMemberWasHead = false;
  memberAutoScan.value = Boolean(scanMode) && ocrAvailable;
  addMemberScanMode.value = scanMode || "idcard";
  memberPopupVisible.value = true;
}

function openMemberEdit(member) {
  editingMember.value = member;
  editingMemberWasHead = isHouseholdHead(member);
  memberAutoScan.value = false;
  memberPopupVisible.value = true;
}

function onMemberConfirm(data) {
  const target = editingMember.value;
  if (target) {
    Object.assign(target, data);
    if (data.isHouseholdHead && !editingMemberWasHead) {
      // 新户主：清掉其他成员的户主标记，承包方名称随户主（同 PC setAsHead）
      for (const m of members.value) {
        if (m !== target) m.isHouseholdHead = false;
      }
      form.name = data.name;
    }
  } else {
    members.value.push({
      memberUid: "",
      noteCode: "",
      memberResultStatus: "added",
      surveyStatus: "surveyed",
      isUrbanSettled: false,
      isMarriedOutWoman: false,
      isDeceased: false,
      isFiveGuarantees: false,
      policyBasis: "",
      rightsDisposition: "",
      remark: "",
      ...data,
      _isNew: true,
    });
    if (data.isHouseholdHead) {
      for (const m of members.value) {
        if (m !== members.value[members.value.length - 1]) m.isHouseholdHead = false;
      }
      form.name = data.name;
    }
  }
}

function openDeleteMember(member) {
  deleteReason.target = member;
  deleteReason.visible = true;
}

function onDeleteMemberConfirm({ selectedOptions }) {
  const reason = selectedOptions?.[0]?.value || "其他";
  const target = deleteReason.target;
  if (target) {
    target._deleted = true;
    target.memberResultStatus = "deleted";
    target.changeReason = target.changeReason || reason;
  }
  deleteReason.visible = false;
  deleteReason.target = null;
}

function restoreMember(member) {
  member._deleted = false;
  member.memberResultStatus = member._isNew ? "added" : "normal";
  if (!member._isNew) member.changeReason = "";
}

/* ---- 保存（对齐 PC 端 handleSaveResult 的 payload 与校验口径） ---- */
function collectValidationProblems() {
  const problems = [];
  if (String(form.code || "").replace(/\D/g, "").length !== 18) {
    problems.push("承包方编码必须为18位数字");
  }
  if (!form.name?.trim()) problems.push("请填写承包方名称");
  if (!form.address?.trim()) problems.push("请填写承包方地址");
  if (!String(form.postcode || "").trim()) problems.push("请填写邮政编码");
  const contractorIssue = evaluateIdNoIssue(form.idType, form.idNo, {
    requireValue: true,
    changed: String(form.idNo || "").trim() !== String(result.value?.idNo ?? ""),
  });
  if (contractorIssue?.level === "error") {
    problems.push(`承包方证件号码：${contractorIssue.message}`);
  }

  for (const row of validMembers.value) {
    const label = String(row.name ?? "").trim() || "未命名成员";
    if (!row.gender) problems.push(`成员「${label}」：请选择性别`);
    if (!row.idType) problems.push(`成员「${label}」：请选择证件类型`);
    if (!row.relationToHead) problems.push(`成员「${label}」：请选择与户主关系`);
    const memberIssue = evaluateIdNoIssue(row.idType, row.idNo, {
      requireValue: true,
      changed: Boolean(row._isNew) ||
        String(row.idNo ?? "").trim() !==
          String(originalMembers.find((o) => o.memberUid && o.memberUid === row.memberUid)?.idNo ?? ""),
    });
    if (memberIssue?.level === "error") {
      problems.push(`成员「${label}」的证件号码：${memberIssue.message}`);
    }
  }
  return problems;
}

async function handleSave() {
  const problems = collectValidationProblems();
  if (problems.length) {
    showDialog({
      title: "请先完善以下内容",
      message: problems.join("\n"),
      confirmButtonText: "知道了",
    });
    return;
  }
  saving.value = true;
  try {
    // cleanMembers 去掉暂存标记（PC 端同口径）；memberResultStatus/surveyStatus 等
    // 业务字段原样回传，后端按 schema 校验
    const cleanMembers = validMembers.value.map(({ _deleted, _isNew, ...rest }) => rest);
    const deletedMembers = members.value
      .filter((m) => m._deleted && m.memberUid)
      .map((m) => ({ memberUid: m.memberUid, changeReason: m.changeReason || "去世" }));
    const payload = {
      code: String(form.code || "").replace(/\D/g, ""),
      typeCode: form.typeCode,
      name: form.name.trim(),
      idType: form.idType,
      idNo: String(form.idNo || "").trim(),
      address: form.address.trim(),
      postcode: String(form.postcode || "").trim(),
      mobile: form.mobile?.trim() || null,
      surveyDate: form.surveyDate || null,
      surveyorName: form.surveyorName?.trim() || null,
      surveyNote: form.surveyNote || null,
      publicNoticeNote: form.publicNoticeNote || null,
      publicNoticeRecorder: form.publicNoticeRecorder?.trim() || null,
      publicNoticeReviewDate: form.publicNoticeReviewDate || null,
      publicNoticeReviewer: form.publicNoticeReviewer?.trim() || null,
      groupRegionCode: form.groupRegionCode || null,
      groupRegionName: form.groupRegionName?.trim() || null,
      surveyStatus: form.surveyStatus,
      resultStatus: form.resultStatus,
      changeType: form.changeType,
      changeReason: form.changeReason || null,
      policyBasis: form.policyBasis || null,
      remark: form.remark || null,
      contractorUid: contractorUid.value,
      familyMembers: cleanMembers,
      deletedMembers,
      pendingOperations: [],
    };
    await updateSurveyResult(batchId.value, contractorUid.value, payload);
    showToast("调查结果已保存");
    markTaskListDirty();
    editing.value = false;
    await loadResult();
  } catch (error) {
    showDialog({
      title: "保存失败",
      message: error?.response?.data?.detail || "保存调查结果失败，请稍后重试",
      confirmButtonText: "知道了",
    });
  } finally {
    saving.value = false;
  }
}

/* ---- 页面跳转 ---- */
function goParcels() {
  router.push({ name: "mobile-task-parcels", params: { batchId: batchId.value, contractorUid: contractorUid.value } });
}

function goAttachments() {
  router.push({ name: "mobile-task-attachments", params: { batchId: batchId.value, contractorUid: contractorUid.value } });
}

function goSketch() {
  router.push({ name: "mobile-task-sketch", params: { batchId: batchId.value, contractorUid: contractorUid.value } });
}

function goContract() {
  router.push({ name: "mobile-task-contract", params: { batchId: batchId.value, contractorUid: contractorUid.value } });
}

onMounted(loadResult);
</script>

<style scoped>
.m-detail {
  padding-bottom: 24px;
}

.m-detail__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
}

/* 吸顶头部：top 对齐 fixed 导航栏底沿（46px + 刘海安全区）。
   z-index 必须给足：下方 van-cell-group 带 .van-hairline--top-bottom（position:relative、
   z-index auto），与 z-index:0 的吸顶头同层且 DOM 靠后 ⇒ 会盖上来（2026-10-04 实测）。
   取 10，导航栏经 MobileLayout 抬到 20（--van-nav-bar-z-index），层级：导航栏 > 吸顶头 > 内容。 */
.m-detail__hero {
  position: sticky;
  top: calc(var(--van-nav-bar-height, 46px) + env(safe-area-inset-top, 0px));
  z-index: 10;
  padding: 8px 16px 8px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(25, 74, 128, 0.08);
}

.m-detail__hero-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.m-detail__name {
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: 17px;
  font-weight: 600;
  color: #1f2d3d;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.m-detail__tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.m-detail__readonly-hint {
  flex-shrink: 0;
  font-size: 12px;
  color: #a6adbb;
}

.m-cell-long {
  text-align: left;
}

/* 成员卡片 */
.m-member {
  padding: 9px 12px 6px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}

.m-member__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.m-member__head-main {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.m-member__name {
  font-size: 16px;
  font-weight: 500;
  color: #1f2d3d;
}

.m-member__name--deleted {
  text-decoration: line-through;
  color: #a6adbb;
}

.m-member__reason {
  font-size: 12px;
  color: #ee0a24;
}

.m-member__row {
  display: flex;
  font-size: 13px;
  line-height: 1.7;
}

.m-member__label {
  flex: 0 0 78px;
  color: #969799;
}

.m-member__value {
  flex: 1;
  color: #323233;
  word-break: break-all;
}

.m-member__ops {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.m-detail__add-member {
  display: flex;
  gap: 12px;
  justify-content: center;
  padding: 14px 16px 0;
}

.m-detail__hint {
  margin: 10px 24px 0;
  font-size: 12px;
  line-height: 1.6;
  color: #a6adbb;
  text-align: center;
}

.m-detail__save-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom));
  background: #fff;
  box-shadow: 0 -2px 8px rgba(25, 74, 128, 0.08);
  margin-top: 16px;
}

.m-detail__save-hint {
  flex: 1;
  font-size: 12px;
  color: #8a94a6;
}

.m-detail__actions {
  padding: 20px 16px 0;
}
</style>
