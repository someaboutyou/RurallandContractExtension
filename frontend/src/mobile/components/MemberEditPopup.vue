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
import { computed, reactive, ref, watch } from "vue";
import { evaluateIdNoIssue, ID_NO_MAX_LENGTH } from "../../utils/validators";
import OcrResultDialog from "./OcrResultDialog.vue";
import OcrScanOverlay from "./OcrScanOverlay.vue";
import { genderFromIdNo, isOcrAvailable, recognizeIdCardWithRetry } from "../ocr/idCapture.js";
import { VanButton, VanCellGroup, VanField, VanPicker, VanPopup, showToast } from "../ui.js";

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
    form[picker.key] = value;
    // 关系选到「本人 / 户主」类码 = 设为户主（与 PC 端 isHeadRelation → setAsHead 同口径）
    if (picker.key === "relationToHead" && isHeadRelation(value)) {
      form.isHouseholdHead = true;
      form.relationToHead = "02"; // ⛔ 户主码写 "02"，别写旧码 "01"
    } else if (picker.key === "relationToHead" && form.isHouseholdHead && !isHeadRelation(value)) {
      form.isHouseholdHead = false;
    }
  }
  picker.visible = false;
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
