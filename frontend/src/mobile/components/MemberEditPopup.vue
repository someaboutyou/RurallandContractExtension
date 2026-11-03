<template>
  <van-popup
    :show="show"
    position="bottom"
    round
    :style="{ maxHeight: '88%' }"
    @update:show="emit('update:show', $event)"
    @open="initForm"
  >
    <div class="member-edit">
      <div class="member-edit__header">
        <span class="member-edit__title">{{ isNew ? "添加家庭成员" : "编辑成员" }}</span>
        <div v-if="ocrAvailable" class="member-edit__scan-btns">
          <van-button size="small" type="success" plain icon="scan" @click="openScan('idcard')">
            身份证采集
          </van-button>
        </div>
      </div>

      <van-cell-group inset>
        <van-field
          v-model="form.name"
          required
          label="姓名"
          placeholder="请输入姓名"
          maxlength="50"
          clearable
        />
        <van-field
          :model-value="genderLabel"
          readonly
          required
          is-link
          label="性别"
          placeholder="请选择"
          @click="pick('gender', '性别', GENDER_OPTIONS)"
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
        <van-field
          v-model="form.idNo"
          required
          label="证件号码"
          placeholder="请输入证件号码"
          :maxlength="ID_NO_MAX_LENGTH"
          clearable
          :error-message="idNoIssue ? idNoIssue.message : ''"
          error-message-align="right"
        />
        <van-field
          :model-value="relationLabel"
          readonly
          required
          is-link
          label="与户主关系"
          placeholder="请选择"
          @click="pick('relationToHead', '与户主关系', relationOptions)"
        />
        <van-field
          :model-value="coOwnerLabel"
          readonly
          is-link
          label="共有人"
          placeholder="请选择"
          @click="pick('isCoOwner', '是否共有人', CO_OWNER_OPTIONS)"
        />
        <van-field
          v-if="showChangeReason"
          v-model="form.changeReason"
          label="变化原因"
          placeholder="新生 / 婚进 / 其他"
          maxlength="500"
        />
        <van-field
          v-model="form.note"
          label="备注"
          type="textarea"
          rows="1"
          autosize
          placeholder="选填"
          maxlength="254"
        />
      </van-cell-group>

      <!-- 成员变化摸底（家庭成员变化摸底表采集，随「保存调查结果」一并提交）。
           字段与状态机口径同 PC 端 ContractorMemberPanel：判据全部来自
           config/surveySheets.js（与后端 sheet.py 同源），本组件只做绑定与展示。 -->
      <van-collapse v-model="sheetOpen" class="member-edit__sheet">
        <van-collapse-item :title="sheetSectionTitle" name="sheet">
          <van-cell-group inset>
            <van-field
              :model-value="secondRoundLabel"
              readonly
              is-link
              label="1996 年二轮承包时是否本户成员"
              placeholder="请选择"
              @click="pickSheet('isSecondRoundMember', '当时是否本户家庭成员（1996 年）', TRI_OPTIONS)"
            />
          </van-cell-group>
          <p class="member-edit__hint">
            「参与二轮承包人口」「确权登记家庭成员」由系统自动推导，无需填写；事件可以留空。
          </p>

          <van-cell-group inset title="二轮承包期 · 1996 — 2018（确权颁证前）">
            <van-field
              :model-value="srEventLabel"
              readonly
              is-link
              label="期内事件"
              placeholder="未填"
              @click="pickSheet('srEventType', '二轮期内事件', srEventOpts)"
            />
            <van-field
              :model-value="form.sheet.srEventDate || ''"
              readonly
              is-link
              label="事件时间"
              placeholder="未填（不晚于 2018-12-31）"
              @click="srDateVisible = true"
            />
            <div class="member-edit__checks">
              <van-checkbox v-model="form.sheet.srCompensated" shape="square">已补地</van-checkbox>
              <van-checkbox v-model="form.sheet.srWithdraw" shape="square">被抽回或放弃承包地</van-checkbox>
            </div>
          </van-cell-group>

          <van-cell-group inset title="延包期 · 2018 — 2026（确权颁证后）">
            <van-field
              :model-value="extEventLabel"
              readonly
              is-link
              label="期内事件"
              placeholder="未填"
              @click="pickSheet('extEventType', '延包期内事件', extEventOpts)"
            />
            <van-field
              :model-value="form.sheet.extEventDate || ''"
              readonly
              is-link
              label="事件时间"
              placeholder="未填（不早于 2019-01-01）"
              @click="extDateVisible = true"
            />
            <div class="member-edit__checks">
              <van-checkbox v-model="form.sheet.extCompensated" shape="square">已补地</van-checkbox>
              <van-checkbox v-model="form.sheet.extWithdraw" shape="square">被抽回或放弃承包地</van-checkbox>
            </div>
          </van-cell-group>

          <van-cell-group inset title="成员属性与身份标识">
            <van-field
              :model-value="economicRelationLabel"
              readonly
              is-link
              label="是否本集体经济组织成员"
              placeholder="未填"
              @click="pickSheet('economicRelation', '是否本集体经济组织成员', ECONOMIC_OPTIONS)"
            />
            <van-field
              v-model="form.sheet.hukouPlace"
              label="现户口所在地"
              placeholder="如：泗阳县××镇××村"
              maxlength="200"
            />
            <van-field
              v-model="form.sheet.residencePlace"
              label="现居住地"
              placeholder="如：泗阳县××镇××村××组"
              maxlength="200"
            />
            <van-field
              :model-value="institutionLabel"
              readonly
              is-link
              label="财政供养人员（国企正式编制、部队军官等）"
              placeholder="未填"
              @click="pickSheet('isInstitutionStaff', '是否财政供养人员', TRI_OPTIONS)"
            />
            <van-field
              :model-value="civilServantLabel"
              readonly
              is-link
              label="其中：为国家公务员"
              placeholder="未填"
              @click="pickSheet('isCivilServant', '是否国家公务员', TRI_OPTIONS)"
            />
            <van-field
              v-model="form.sheet.remark"
              label="摸底备注"
              type="textarea"
              rows="1"
              autosize
              placeholder="公职单位、补地 / 抽回原因等（选填）"
              maxlength="500"
            />
          </van-cell-group>
          <p class="member-edit__hint">
            「成员增减变动时间」由两期事件时间自动取最后者，无需填写。必须有进才有出，出了还可以再进。
          </p>
        </van-collapse-item>
      </van-collapse>

      <div class="member-edit__actions">
        <van-button block round plain @click="emit('update:show', false)">取消</van-button>
        <van-button block round type="primary" :loading="false" @click="onConfirm">确定</van-button>
      </div>
    </div>

    <van-popup :show="picker.visible" position="bottom" round>
      <van-picker
        :title="picker.title"
        :columns="picker.options.map((o) => ({ text: o.label, value: o.value }))"
        @confirm="onPickConfirm"
        @cancel="picker.visible = false"
      />
    </van-popup>

    <!-- 摸底事件时间选择（两期各自限界：二轮 ≤ 2018-12-31，延包 ≥ 2019-01-01） -->
    <van-popup :show="srDateVisible" position="bottom" round @update:show="srDateVisible = $event">
      <van-date-picker
        title="二轮期事件时间（≤ 2018-12-31）"
        :model-value="srDateModel"
        :min-date="SR_DATE_MIN"
        :max-date="SR_DATE_MAX"
        @confirm="onSrDateConfirm"
        @cancel="srDateVisible = false"
      />
    </van-popup>
    <van-popup :show="extDateVisible" position="bottom" round @update:show="extDateVisible = $event">
      <van-date-picker
        title="延包期事件时间（≥ 2019-01-01）"
        :model-value="extDateModel"
        :min-date="EXT_DATE_MIN"
        :max-date="EXT_DATE_MAX"
        @confirm="onExtDateConfirm"
        @cancel="extDateVisible = false"
      />
    </van-popup>

    <OcrResultDialog
      v-model:show="ocrDialogVisible"
      :title="ocrTitle"
      :doc-type="ocrDocType"
      :fields="ocrFields"
      :elapsed-ms="ocrElapsedMs"
      :raw-text="ocrRawText"
      @confirm="onOcrConfirm"
    />

    <OcrScanOverlay
      v-if="ocrScanVisible"
      :try-recognize="tryRecognize"
      :mode="ocrMode"
      @close="ocrScanVisible = false"
    />

    <!-- 识别诊断层：显示 OCR 实际收到的裁框图 + 原生解码尺寸 + 识别原文，截图回传即可定性 -->
    <van-popup
      v-model:show="diagVisible"
      position="center"
      round
      :style="{ width: '86%', padding: '16px' }"
    >
      <p class="member-edit__diag-title">识别诊断</p>
      <p class="member-edit__diag-text">{{ diagMessage }}</p>
      <p v-if="diagDims" class="member-edit__diag-text">引擎收到的图像尺寸：{{ diagDims.w }}×{{ diagDims.h }}px</p>
      <img v-if="diagUrl" :src="diagUrl" class="member-edit__diag-img" alt="OCR 输入图" />
      <p class="member-edit__diag-hint">上图即 OCR 实际收到的画面，截图发群里即可定位问题</p>
      <van-button block type="primary" @click="diagVisible = false">知道了</van-button>
    </van-popup>
  </van-popup>
</template>

<script setup>
/**
 * 家庭成员编辑 / 新增弹层（移动端）。
 *
 * 字段与校验口径同 PC 端 ContractorMemberPanel：
 * - 姓名 / 性别 / 证件类型 / 证件号码 / 与户主关系必填（后端 schema 同口径）；
 * - 证件号码走 evaluateIdNoIssue 三档口径（本次录入从严、历史值降级提示）；
 * - 关系选到「本人 / 户主」类码 = 设为户主：isHouseholdHead 置真、关系码写
 *   "02"（存量旧数据是 "01"，新写入统一 "02"），承包方名称随户主（父组件处理）；
 * - 新增成员变化原因默认「新生」（可改）。
 *
 * 「证件采集」复用附件页同一套 OCR 链路（OcrScanOverlay 自动抓拍 + 方向重试 +
 * OcrResultDialog 人工确认）：身份证识别回填姓名/证件号码，性别由号码反推。
 * ⛔ 户口簿 OCR 已下线（识别慢、准确率差、真机体感不好）：采集入口只留身份证，
 * 未成年人/无证人员走手动填写（证件类型选「户口簿」）。parser.js 里的户口簿
 * 解析保留未删 —— 附件页 auto 模式仍在用，且链路修好后可随时捞回。
 */
import { computed, reactive, ref } from "vue";
import { evaluateIdNoIssue, ID_NO_MAX_LENGTH } from "../../utils/validators";
import {
  MEMBER_EVENT_MAP,
  createEmptyMemberSheet,
  extEventOptions,
  memberSheetFilled,
  srEventOptions,
  validateMemberSheetFlow,
} from "../../config/surveySheets";
import OcrResultDialog from "./OcrResultDialog.vue";
import OcrScanOverlay from "./OcrScanOverlay.vue";
import { genderFromIdNo, isOcrAvailable, recognizeIdCardWithRetry } from "../ocr/idCapture.js";
import {
  VanButton,
  VanCellGroup,
  VanCheckbox,
  VanCollapse,
  VanCollapseItem,
  VanDatePicker,
  VanField,
  VanPicker,
  VanPopup,
  showDialog,
  showToast,
} from "../ui.js";

const props = defineProps({
  show: { type: Boolean, default: false },
  /** null = 新增；对象 = 编辑（含 _isNew 标记） */
  member: { type: Object, default: null },
  /** 与户主关系字典项 [{label, value}] */
  relationOptions: { type: Array, default: () => [] },
  /** 打开弹层时立即进入扫描（「证件采集添加」入口用） */
  autoScan: { type: Boolean, default: false },
  /** autoScan 为真时的扫描入口："idcard"（默认）| "household" */
  scanMode: { type: String, default: "idcard" },
});

const emit = defineEmits(["update:show", "confirm"]);

const GENDER_OPTIONS = [
  { label: "男", value: "1" },
  { label: "女", value: "2" },
];
const ID_TYPE_OPTIONS = [
  { label: "身份证", value: "1" },
  { label: "户口簿", value: "2" },
  { label: "军官证", value: "3" },
];
const CO_OWNER_OPTIONS = [
  { label: "是", value: "1" },
  { label: "否", value: "0" },
];

const isNew = computed(() => !props.member?.memberUid);
const showChangeReason = computed(() => isNew.value);

const form = reactive({
  name: "",
  gender: "1",
  idType: "1",
  idNo: "",
  relationToHead: "09",
  isCoOwner: "0",
  note: "",
  changeReason: "新生",
  isHouseholdHead: false,
  // 成员变化摸底（家庭成员变化摸底表）：后端 GET 结果已按成员注入 sheet 子对象
  // （attach_member_sheet_info），这里只防整体缺失；新增成员默认"否"
  // （与 PC 端 isAddedMemberRow 口径一致：系统新增的行不该默认"是"）。
  sheet: createEmptyMemberSheet(),
});

const ocrAvailable = isOcrAvailable();
const ocrScanVisible = ref(false);
/** 当前扫描入口："idcard" | "household"（两证分入口，各用各的取景框/相机/管线） */
const ocrMode = ref("idcard");
const ocrDialogVisible = ref(false);
const ocrDocType = ref("");
const ocrTitle = ref("识别结果");
const ocrFields = ref([]);
const ocrRawText = ref("");
const ocrElapsedMs = ref(0);

/* ---- 识别诊断层状态 ---- */
const diagVisible = ref(false);
const diagMessage = ref("");
const diagDims = ref(null);
const diagUrl = ref("");

function showDiag(result) {
  diagMessage.value = [result.message, result.preview ? `识别原文：${result.preview}` : ""]
    .filter(Boolean)
    .join("\n");
  diagDims.value = result.dims || null;
  if (diagUrl.value) {
    URL.revokeObjectURL(diagUrl.value);
    diagUrl.value = "";
  }
  if (result.inputBlob) {
    try {
      diagUrl.value = URL.createObjectURL(result.inputBlob);
    } catch {
      /* 生成预览失败不影响诊断文字 */
    }
  }
  diagVisible.value = true;
}

/** 编辑时拿来判定"证件号码是否本次改动过"的基线 */
let originalIdNo = "";

const genderLabel = computed(() => GENDER_OPTIONS.find((o) => o.value === form.gender)?.label || form.gender || "");
const idTypeLabel = computed(() => ID_TYPE_OPTIONS.find((o) => o.value === form.idType)?.label || form.idType || "");
const coOwnerLabel = computed(() => CO_OWNER_OPTIONS.find((o) => o.value === form.isCoOwner)?.label || form.isCoOwner || "");
const relationLabel = computed(
  () => props.relationOptions.find((o) => o.value === form.relationToHead)?.label || form.relationToHead || "",
);

const idNoIssue = computed(() =>
  evaluateIdNoIssue(form.idType, form.idNo, {
    changed: isNew.value || String(form.idNo || "").trim() !== originalIdNo,
    incompleteOk: true,
  }),
);

function initForm() {
  const source = props.member;
  form.name = source?.name || "";
  form.gender = source?.gender || "1";
  form.idType = source?.idType || "1";
  form.idNo = source?.idNo || "";
  form.relationToHead = source?.relationToHead || "09";
  form.isCoOwner = source?.isCoOwner || "0";
  form.note = source?.note || "";
  form.changeReason = isNew.value ? source?.changeReason || "新生" : source?.changeReason || "";
  form.isHouseholdHead = Boolean(source?.isHouseholdHead) || false;
  // 摸底数据：后端已注入 sheet 的直接展开；缺失时按"新增行=否 / 历史行=是"兜底
  // （同 PC 端 ContractorMemberPanel 的 isAddedMemberRow 口径，勿用 null 兜底覆盖"未填"）
  if (source?.sheet && typeof source.sheet === "object") {
    form.sheet = { ...createEmptyMemberSheet(), ...source.sheet };
  } else {
    const isAddedRow = isNew.value || source?.memberResultStatus === "added";
    form.sheet = { ...createEmptyMemberSheet(), isSecondRoundMember: isAddedRow ? false : true };
  }
  sheetOpen.value = [];
  originalIdNo = String(source?.idNo || "").trim();
  // 「证件采集添加」入口：弹层一打开就进入身份证扫描（户口簿识别已下线，
  // 小孩/无证人员走手动填写，证件类型选「户口簿」）
  if (props.show && props.autoScan && ocrAvailable) {
    openScan("idcard");
  }
}

/** 进入证件扫描（分入口）：mode = "idcard" | "household" */
function openScan(mode) {
  ocrMode.value = mode;
  ocrScanVisible.value = true;
}

/* ---- 通用 picker ---- */
const picker = reactive({ visible: false, title: "", key: "", options: [] });

function pick(key, title, options) {
  Object.assign(picker, { visible: true, title, key, options });
}

function onPickConfirm({ selectedOptions }) {
  const value = selectedOptions?.[0]?.value;
  if (value !== undefined) {
    if (picker.key.startsWith("sheet.")) {
      // 摸底字段：写进 form.sheet；三态布尔是 yes/no/"" 字符串，映射回 true/false/null
      const key = picker.key.slice(6);
      if (key === "isSecondRoundMember") {
        form.sheet.isSecondRoundMember = stringToTri(value);
        reconcileSheetEvents();
      } else if (key === "srEventType") {
        form.sheet.srEventType = value || "";
        reconcileSheetEvents();
      } else if (key === "extEventType") {
        form.sheet.extEventType = value || "";
        reconcileSheetEvents();
      } else if (key === "economicRelation") {
        form.sheet.economicRelation = value || "";
      } else if (key === "isInstitutionStaff") {
        form.sheet.isInstitutionStaff = stringToTri(value);
      } else if (key === "isCivilServant") {
        form.sheet.isCivilServant = stringToTri(value);
        // 列 34 ⊂ 列 33（纸质表口径）：选了"为国家公务员"，财政供养人员必然点亮
        if (form.sheet.isCivilServant === true) form.sheet.isInstitutionStaff = true;
      }
    } else {
      form[picker.key] = value;
      // 关系选到「本人 / 户主」类码 = 设为户主（与 PC 端 isHeadRelation → setAsHead 同口径）
      if (picker.key === "relationToHead" && isHeadRelation(value)) {
        form.isHouseholdHead = true;
        form.relationToHead = "02"; // ⛔ 户主码写 "02"，别写旧码 "01"
      } else if (picker.key === "relationToHead" && form.isHouseholdHead && !isHeadRelation(value)) {
        form.isHouseholdHead = false;
      }
    }
  }
  picker.visible = false;
}

/* ---- 成员变化摸底（判据全部来自 config/surveySheets.js，与 PC/后端同源） ---- */
const sheetOpen = ref([]);
const sheetSectionTitle = computed(() => (sheetFilled.value ? "成员变化摸底（已填）" : "成员变化摸底"));

const sheetFilled = computed(() => memberSheetFilled(form.sheet));

/** 三态（是/否/未填）picker 的字符串值形态（van-picker 的 value 不能是 undefined） */
const TRI_OPTIONS = [
  { label: "是", value: "yes" },
  { label: "否", value: "no" },
  { label: "未填", value: "" },
];
const ECONOMIC_OPTIONS = [
  { label: "是", value: "1" },
  { label: "否", value: "0" },
  { label: "未填", value: "" },
];

function triToString(v) {
  return v === true ? "yes" : v === false ? "no" : "";
}

function stringToTri(v) {
  return v === "yes" ? true : v === "no" ? false : null;
}

const secondRoundLabel = computed(() => {
  const v = form.sheet.isSecondRoundMember;
  return v === true ? "是" : v === false ? "否" : "未填";
});
const economicRelationLabel = computed(
  () => ECONOMIC_OPTIONS.find((o) => o.value === (form.sheet.economicRelation || ""))?.label || "未填",
);
const institutionLabel = computed(() => (form.sheet.isInstitutionStaff === true ? "是" : form.sheet.isInstitutionStaff === false ? "否" : "未填"));
const civilServantLabel = computed(() => (form.sheet.isCivilServant === true ? "是" : form.sheet.isCivilServant === false ? "否" : "未填"));

// 两期事件下拉按「在户状态机」过滤 + 矛盾值兜底显示（历史数据）。
// ⛔ 与 PC 端 ContractorMemberPanel.withCurrentValue 同口径，否则会露出原始码值。
function withCurrentValue(value, options) {
  if (value && !options.some((opt) => opt.value === value)) {
    return [...options, { value, label: `${MEMBER_EVENT_MAP[value] || value}（与在户状态矛盾）` }];
  }
  return options;
}

const EVENT_CLEAR_OPTION = [{ label: "未填", value: "" }];
const srEventOpts = computed(() => [
  ...EVENT_CLEAR_OPTION,
  ...withCurrentValue(form.sheet.srEventType || "", srEventOptions(form.sheet)),
]);
const extEventOpts = computed(() => [
  ...EVENT_CLEAR_OPTION,
  ...withCurrentValue(form.sheet.extEventType || "", extEventOptions(form.sheet)),
]);
const srEventLabel = computed(
  () => srEventOpts.value.find((o) => o.value === (form.sheet.srEventType || ""))?.label || "未填",
);
const extEventLabel = computed(
  () => extEventOpts.value.find((o) => o.value === (form.sheet.extEventType || ""))?.label || "未填",
);

function pickSheet(key, title, options) {
  // sheet 字段的 picker：key 直接用字段名，确认时写进 form.sheet
  Object.assign(picker, { visible: true, title, key: `sheet.${key}`, options });
}

/** 列7 / 事件变化后，若另一期已选事件与新状态矛盾，自动清空并提示（PC 端同口径） */
function reconcileSheetEvents() {
  const s = form.sheet;
  if (s.srEventType && !srEventOpts.value.some((opt) => opt.value === s.srEventType)) {
    showToast("二轮期事件与「1996 年是否家庭成员」矛盾，已清空（必须有进才有出）");
    s.srEventType = "";
    s.srEventDate = null;
  }
  if (s.extEventType && !extEventOpts.value.some((opt) => opt.value === s.extEventType)) {
    showToast("延包期事件与前期在户状态矛盾，已清空（出了还可以再进，反之须先出）");
    s.extEventType = "";
    s.extEventDate = null;
  }
}

// 摸底事件时间：van-date-picker 的 model 是 [年, 月, 日] 数字数组；confirm 直接给 Date
const srDateVisible = ref(false);
const extDateVisible = ref(false);
const SR_DATE_MIN = new Date(1900, 0, 1);
const SR_DATE_MAX = new Date(2018, 11, 31);
const EXT_DATE_MIN = new Date(2019, 0, 1);
const EXT_DATE_MAX = new Date(2099, 11, 31);

function dateToModel(value) {
  const parts = String(value || "").slice(0, 10).split("-");
  if (parts.length !== 3 || parts.some((p) => !/^\d+$/.test(p))) return [];
  return [Number(parts[0]), Number(parts[1]), Number(parts[2])];
}

const srDateModel = computed(() => dateToModel(form.sheet.srEventDate));
const extDateModel = computed(() => dateToModel(form.sheet.extEventDate));

function formatDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function onSrDateConfirm({ selectedDate }) {
  form.sheet.srEventDate = formatDate(selectedDate);
  srDateVisible.value = false;
}

function onExtDateConfirm({ selectedDate }) {
  form.sheet.extEventDate = formatDate(selectedDate);
  extDateVisible.value = false;
}

function isHeadRelation(value) {
  if (value === "01") return true;
  return (props.relationOptions.find((item) => item.value === value)?.label || "").includes("本人") ||
    (props.relationOptions.find((item) => item.value === value)?.label || "").includes("户主");
}

/* ---- 证件 OCR 采集（身份证 / 户口簿分入口） ---- */
async function tryRecognize(photo) {
  const mode = photo.mode || ocrMode.value;
  const result = await recognizeIdCardWithRetry(photo, { mode });
  if (!result.ok) {
    // 带识别输入图的诊断弹层：图坏/图糊/图好但识别坏，用户截图回传即可定性
    showDiag(result);
    return result;
  }
  ocrDocType.value = result.docType;
  ocrTitle.value =
    result.docType === "id_front" ? "身份证人像面识别" : "身份证国徽面识别";
  ocrFields.value = result.parsed.fields;
  ocrRawText.value = result.parsed.rawText || "";
  ocrElapsedMs.value = result.elapsedMs;
  ocrDialogVisible.value = true;
  return { ok: true };
}

function onOcrConfirm(values) {
  ocrDialogVisible.value = false;
  ocrScanVisible.value = false;
  if (values.name) form.name = values.name;
  if (values.idNo) {
    form.idNo = values.idNo;
    form.idType = "1"; // 识别的是身份证 ⇒ 证件类型跟着切
    const gender = genderFromIdNo(values.idNo);
    if (gender) form.gender = gender;
  }
  showToast("已回填识别结果，请核对并选择与户主关系");
}

/* ---- 确认 ---- */
function onConfirm() {
  if (!form.name.trim()) {
    showToast("请填写姓名");
    return;
  }
  const issue = evaluateIdNoIssue(form.idType, form.idNo, {
    requireValue: true,
    changed: isNew.value || String(form.idNo || "").trim() !== originalIdNo,
  });
  if (issue?.level === "error") {
    showToast(issue.message);
    return;
  }
  if (!form.relationToHead) {
    showToast("请选择与户主关系");
    return;
  }
  // 摸底状态机预检（单成员，与后端闸门/PC 保存预检同判据）：违规当场拦，
  // 别等整户保存才被 400 打回
  const sheetProblems = validateMemberSheetFlow([{ name: form.name.trim(), sheet: form.sheet }]);
  if (sheetProblems.length) {
    showDialog({
      title: "摸底信息有误",
      message: sheetProblems.join("\n"),
      confirmButtonText: "知道了",
    });
    return;
  }
  emit("confirm", {
    name: form.name.trim(),
    gender: form.gender,
    idType: form.idType,
    idNo: String(form.idNo).trim(),
    relationToHead: form.relationToHead,
    isCoOwner: form.isCoOwner,
    note: form.note || "",
    changeReason: form.changeReason || null,
    isHouseholdHead: form.isHouseholdHead,
    // 摸底数据随成员行提交：后端 update_result 按 item.sheet upsert 摸底表
    sheet: { ...form.sheet },
  });
  emit("update:show", false);
}
</script>

<style scoped>
.member-edit {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 0 24px;
  overflow-y: auto;
}

.member-edit__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 20px;
}

.member-edit__scan-btns {
  display: flex;
  align-items: center;
  gap: 8px;
}

.member-edit__title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2d3d;
}

.member-edit__issue {
  display: block;
  max-width: 150px;
  font-size: 11px;
  line-height: 1.4;
  text-align: right;
}

.member-edit__issue.is-error {
  color: #ee0a24;
}

.member-edit__issue.is-warn {
  color: #ff976a;
}

.member-edit__actions {
  display: flex;
  gap: 12px;
  padding: 4px 16px 0;
}

/* 摸底采集区 */
.member-edit__sheet {
  margin: 0 4px;
}

.member-edit__hint {
  margin: 8px 20px 0;
  font-size: 12px;
  line-height: 1.5;
  color: #969799;
}

.member-edit__checks {
  display: flex;
  gap: 24px;
  padding: 10px 16px 4px;
  font-size: 14px;
}

/* 识别诊断层 */
.member-edit__diag-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  text-align: center;
  color: #1f2d3d;
}

.member-edit__diag-text {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.5;
  color: #333;
  word-break: break-all;
}

.member-edit__diag-img {
  display: block;
  width: 100%;
  margin: 8px 0;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
}

.member-edit__diag-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #969799;
}
</style>
