<template>
  <el-dialog :model-value="modelValue" :title="dialogTitle" width="960px" @update:model-value="$emit('update:modelValue', $event)">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="left" label-width="126px" status-icon class="survey-dialog-form">
      <div class="form-grid-2">
        <el-form-item label="发包方名称" prop="name">
          <el-input v-model="form.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="发包方编码" prop="code">
          <el-input :model-value="form.code" maxlength="14" readonly @input="handleCodeInput">
            <template v-if="isCreating" #append>
              <el-button @click="generateCode">生成</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="负责人姓名" prop="responsibleName">
          <el-input v-model="form.responsibleName" maxlength="50" />
        </el-form-item>
        <el-form-item label="负责人证件类型" prop="responsibleIdType">
          <el-select v-model="form.responsibleIdType">
            <el-option label="居民身份证" value="1" />
            <el-option label="户口簿" value="2" />
            <el-option label="军官证" value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人证件号码" prop="responsibleIdNo">
          <el-input v-model="form.responsibleIdNo" maxlength="30" />
        </el-form-item>
        <el-form-item label="联系电话" prop="phone">
          <el-input v-model="form.phone" maxlength="15" />
        </el-form-item>
      </div>
      <el-form-item label="发包方地址" prop="address">
        <el-input v-model="form.address" maxlength="100" />
      </el-form-item>
      <div class="form-grid-2">
        <el-form-item label="邮政编码" prop="postcode">
          <el-input v-model="form.postcode" maxlength="6" />
        </el-form-item>
        <el-form-item label="调查日期">
          <el-date-picker v-model="form.surveyDate" value-format="YYYY-MM-DD" type="date" style="width: 100%" />
        </el-form-item>
        <el-form-item label="调查员">
          <el-input v-model="form.surveyorName" maxlength="254" />
        </el-form-item>
      </div>
      <el-form-item label="调查记事">
        <el-input v-model="form.surveyNote" type="textarea" :rows="3" maxlength="254" show-word-limit />
      </el-form-item>
      <el-form-item label="变化原因">
        <el-input v-model="form.changeReason" type="textarea" :rows="2" maxlength="500" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button
        v-if="canManage && activeBatch?.status !== 'finished' && !LOCKED_SURVEY_STATUSES.includes(form.surveyStatus)"
        :loading="saving"
        type="primary"
        @click="handleSave"
      >
        {{ isCreating ? "新增并保存" : "保存发包方调查" }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { createSurveyIssuer, fetchSurveyIssuer, fetchSurveyIssuers, updateSurveyIssuer } from "../../../api/survey";
import { LOCKED_SURVEY_STATUSES } from "../../../config/surveyStatus";
import { useAuthStore } from "../../../stores/auth";
import { applySurveyActorDefaults } from "../../../utils/surveyActorDefaults";
import { validateChinaId, validateMobile, validatePostcode } from "../../../utils/validators";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  activeBatch: { type: Object, default: null },
  canManage: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "saved"]);

const authStore = useAuthStore();

const saving = ref(false);
const isCreating = ref(false);
const activeIssuer = ref(null);
const formRef = ref(null);

function createEmpty() {
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

const form = reactive(createEmpty());

// 表单只读判定：**与保存按钮的显示条件同源**（见模板 footer）——
// 不能提交的时候，就不该往表单里塞默认值，否则只读视图会凭空多出假的"已变化"高亮。
const formLocked = computed(
  () => !props.canManage || props.activeBatch?.status === "finished" || LOCKED_SURVEY_STATUSES.includes(form.surveyStatus),
);

// 调查员 / 调查日期默认取「本次」（当前登录用户 + 当天），
// 口径在 utils/surveyActorDefaults.js —— 与承包方侧 ContractorResultDialog 共用同一份。
function applyCurrentSurveyDefaults() {
  applySurveyActorDefaults(form, {
    base: form.baseIssuer,
    readonly: formLocked.value,
    displayName: authStore.displayName,
  });
}

const dialogTitle = computed(() => {
  const name = form.name ? ` - ${form.name}` : "";
  return `${isCreating.value ? "新增发包方调查录入" : "发包方调查录入"}${name}`;
});

// ---- Validators ----
function digitsOnly(value) {
  return String(value || "").replace(/\D/g, "");
}

function validateCodeField(_rule, value, callback) {
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
}

function validateIdNoField(_rule, value, callback) {
  const text = String(value || "").trim();
  if (!text) {
    callback(new Error("请输入负责人证件号码"));
    return;
  }
  if (form.responsibleIdType === "1" && !validateChinaId(text)) {
    callback(new Error("请输入正确的居民身份证号码"));
    return;
  }
  callback();
}

function validatePhoneField(_rule, value, callback) {
  const text = String(value || "").trim();
  if (text && !validateMobile(text)) {
    callback(new Error("请输入正确的联系电话"));
    return;
  }
  callback();
}

function validatePostcodeField(_rule, value, callback) {
  const text = String(value || "").trim();
  if (text && !validatePostcode(text)) {
    callback(new Error("邮政编码必须为6位数字"));
    return;
  }
  callback();
}

const rules = {
  code: [{ validator: validateCodeField, trigger: "blur" }],
  name: [{ required: true, message: "请输入发包方名称", trigger: "blur" }],
  responsibleName: [{ required: true, message: "请输入负责人姓名", trigger: "blur" }],
  responsibleIdType: [{ required: true, message: "请选择负责人证件类型", trigger: "change" }],
  responsibleIdNo: [{ validator: validateIdNoField, trigger: "blur" }],
  phone: [{ validator: validatePhoneField, trigger: "blur" }],
  address: [{ required: true, message: "请输入发包方地址", trigger: "blur" }],
  postcode: [{ validator: validatePostcodeField, trigger: "blur" }],
};

// ---- Code generation ----
function handleCodeInput(value) {
  form.code = digitsOnly(value).slice(0, 14);
}

async function buildNextCode(currentCode = "", batchCode = "", existingRows = []) {
  const batch = digitsOnly(batchCode);
  if (batch.length >= 14) return batch.slice(0, 14);
  const currentPrefix = digitsOnly(currentCode);
  const prefix = batch || currentPrefix.slice(0, Math.min(currentPrefix.length, 12));
  if (!prefix) return "";
  if (prefix.length >= 14) return prefix.slice(0, 14);
  const suffixLength = 14 - prefix.length;
  const existingSuffixes = existingRows
    .map((item) => digitsOnly(item.code))
    .filter((code) => code.length === 14 && code.startsWith(prefix))
    .map((code) => Number(code.slice(prefix.length)))
    .filter(Number.isFinite);
  const next = (existingSuffixes.length ? Math.max(...existingSuffixes) : 0) + 1;
  return `${prefix}${String(next).padStart(suffixLength, "0")}`.slice(0, 14);
}

async function generateCode() {
  let existingRows = [];
  if (props.activeBatch) {
    const { data } = await fetchSurveyIssuers(props.activeBatch.id, { page: 1, page_size: 10000 });
    existingRows = data.data.items || [];
  }
  const code = await buildNextCode(form.code, props.activeBatch?.regionCode || "", existingRows);
  if (!code) {
    ElMessage.warning("请先选择调查批次或输入区域前缀");
    return;
  }
  form.code = code;
}

// ---- Open / Close ----
function buildRegionParams() {
  const regionCode = props.activeBatch?.regionCode;
  return regionCode ? { regionCode } : {};
}

async function openForCreate(batch, regionCode) {
  isCreating.value = true;
  activeIssuer.value = null;
  const code = regionCode || batch?.regionCode || "";
  Object.assign(form, createEmpty(), {
    code: code.length >= 14 ? code.slice(0, 14) : code,
  });
  // 新增发包方：调查员 / 调查日期直接落「本次」的默认值（当前登录用户 + 当天）。
  applyCurrentSurveyDefaults();
  emit("update:modelValue", true);
}

async function openForEdit(batch, row) {
  isCreating.value = false;
  activeIssuer.value = row;
  const { data } = await fetchSurveyIssuer(batch.id, row.issuerUid);
  Object.assign(form, createEmpty(), data.data);
  // 调查员 / 调查日期取「本次」的默认值，不再沿用库里的历史痕迹
  // （survey_fbf_result 是全局唯一行，批次初始化时整行抄成快照，带着上一批的调查员/日期）。
  applyCurrentSurveyDefaults();
  emit("update:modelValue", true);
}

function close() {
  emit("update:modelValue", false);
  isCreating.value = false;
}

async function handleSave() {
  if (!props.activeBatch || (!activeIssuer.value && !isCreating.value)) {
    return;
  }
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) {
    return;
  }
  saving.value = true;
  try {
    const { baseIssuer, id, isChanged, ...payload } = form;
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
    let issuerUid = activeIssuer.value?.issuerUid;
    if (isCreating.value) {
      const { data } = await createSurveyIssuer(props.activeBatch.id, cleanPayload);
      issuerUid = data.data.issuerUid;
    }
    await updateSurveyIssuer(props.activeBatch.id, issuerUid, cleanPayload);
    ElMessage.success(isCreating.value ? "发包方调查数据已新增" : "发包方调查已保存");
    close();
    emit("saved");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || (isCreating.value ? "新增发包方失败" : "保存发包方调查失败"));
  } finally {
    saving.value = false;
  }
}

defineExpose({ openForCreate, openForEdit });
</script>

<style scoped>
.survey-dialog-form {
  margin-top: 16px;
}
.form-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
  align-items: start;
}
</style>
