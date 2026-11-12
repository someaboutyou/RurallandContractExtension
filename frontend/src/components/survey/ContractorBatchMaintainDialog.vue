<template>
  <el-dialog
    :model-value="modelValue"
    title="批量维护承包方"
    width="780px"
    top="8vh"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @open="resetForm"
  >
    <el-alert
      class="maintain-tip"
      type="info"
      :closable="false"
      show-icon
      :title="`已选 ${contractors.length} 户；只更新勾选的字段，未勾选字段保持原值`"
    />

    <el-tabs v-model="activeTab">
      <el-tab-pane label="承包方基本信息" name="basic">
        <el-form label-width="150px" class="maintain-form">
          <el-form-item>
            <template #label><el-checkbox v-model="basicEnabled.typeCode">承包方类型</el-checkbox></template>
            <DictionarySelect v-model="basicForm.typeCode" dict-type="nyt2539_c16_contractor_type" placeholder="请选择承包方类型" :disabled="!basicEnabled.typeCode" />
          </el-form-item>
          <el-form-item>
            <template #label><el-checkbox v-model="basicEnabled.idType">证件类型</el-checkbox></template>
            <DictionarySelect v-model="basicForm.idType" dict-type="nyt2539_c15_id_document_type" placeholder="请选择证件类型" :disabled="!basicEnabled.idType" />
          </el-form-item>
          <el-form-item>
            <template #label><el-checkbox v-model="basicEnabled.address">承包方地址</el-checkbox></template>
            <el-input v-model="basicForm.address" maxlength="100" placeholder="请输入承包方地址" :disabled="!basicEnabled.address" />
          </el-form-item>
          <el-form-item>
            <template #label><el-checkbox v-model="basicEnabled.postcode">邮政编码</el-checkbox></template>
            <el-input v-model="basicForm.postcode" maxlength="6" placeholder="请输入邮政编码" :disabled="!basicEnabled.postcode" />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="承包方调查信息" name="survey">
        <el-form label-width="150px" class="maintain-form">
          <el-form-item>
            <template #label><el-checkbox v-model="surveyEnabled.surveyorName">承包方调查员</el-checkbox></template>
            <el-input v-model="surveyForm.surveyorName" maxlength="50" placeholder="请输入调查员" :disabled="!surveyEnabled.surveyorName" />
          </el-form-item>
          <el-form-item>
            <template #label><el-checkbox v-model="surveyEnabled.surveyDate">承包方调查日期</el-checkbox></template>
            <el-date-picker v-model="surveyForm.surveyDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" placeholder="请选择调查日期" :disabled="!surveyEnabled.surveyDate" />
          </el-form-item>
          <el-form-item>
            <template #label><el-checkbox v-model="surveyEnabled.surveyNote">承包方调查记事</el-checkbox></template>
            <el-input v-model="surveyForm.surveyNote" type="textarea" :rows="2" maxlength="254" placeholder="请输入调查记事" :disabled="!surveyEnabled.surveyNote" />
          </el-form-item>
          <el-form-item>
            <template #label><el-checkbox v-model="surveyEnabled.publicNoticeNote">公示记事</el-checkbox></template>
            <el-input v-model="surveyForm.publicNoticeNote" type="textarea" :rows="2" maxlength="254" placeholder="请输入公示记事" :disabled="!surveyEnabled.publicNoticeNote" />
          </el-form-item>
          <el-form-item>
            <template #label><el-checkbox v-model="surveyEnabled.publicNoticeRecorder">公示记事人</el-checkbox></template>
            <el-input v-model="surveyForm.publicNoticeRecorder" maxlength="50" placeholder="请输入公示记事人" :disabled="!surveyEnabled.publicNoticeRecorder" />
          </el-form-item>
          <el-form-item>
            <template #label><el-checkbox v-model="surveyEnabled.publicNoticeReviewDate">公示审核日期</el-checkbox></template>
            <el-date-picker v-model="surveyForm.publicNoticeReviewDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" placeholder="请选择公示审核日期" :disabled="!surveyEnabled.publicNoticeReviewDate" />
          </el-form-item>
          <el-form-item>
            <template #label><el-checkbox v-model="surveyEnabled.publicNoticeReviewer">公示审核人</el-checkbox></template>
            <el-input v-model="surveyForm.publicNoticeReviewer" maxlength="50" placeholder="请输入公示审核人" :disabled="!surveyEnabled.publicNoticeReviewer" />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import DictionarySelect from "../DictionarySelect.vue";
import { batchMaintainContractors } from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  batch: { type: Object, default: null },
  contractors: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue", "updated"]);

const activeTab = ref("basic");
const submitting = ref(false);

const basicForm = reactive({ typeCode: "", idType: "", address: "", postcode: "" });
const basicEnabled = reactive({ typeCode: false, idType: false, address: false, postcode: false });
const surveyForm = reactive({
  surveyorName: "",
  surveyDate: "",
  surveyNote: "",
  publicNoticeNote: "",
  publicNoticeRecorder: "",
  publicNoticeReviewDate: "",
  publicNoticeReviewer: "",
});
const surveyEnabled = reactive({
  surveyorName: false,
  surveyDate: false,
  surveyNote: false,
  publicNoticeNote: false,
  publicNoticeRecorder: false,
  publicNoticeReviewDate: false,
  publicNoticeReviewer: false,
});

const BASIC_LABELS = {
  typeCode: "承包方类型",
  idType: "证件类型",
  address: "承包方地址",
  postcode: "邮政编码",
};
const SURVEY_LABELS = {
  surveyorName: "承包方调查员",
  surveyDate: "承包方调查日期",
  surveyNote: "承包方调查记事",
  publicNoticeNote: "公示记事",
  publicNoticeRecorder: "公示记事人",
  publicNoticeReviewDate: "公示审核日期",
  publicNoticeReviewer: "公示审核人",
};

function resetForm() {
  activeTab.value = "basic";
  submitting.value = false;
  Object.assign(basicForm, { typeCode: "", idType: "", address: "", postcode: "" });
  Object.assign(basicEnabled, { typeCode: false, idType: false, address: false, postcode: false });
  Object.assign(surveyForm, {
    surveyorName: "",
    surveyDate: "",
    surveyNote: "",
    publicNoticeNote: "",
    publicNoticeRecorder: "",
    publicNoticeReviewDate: "",
    publicNoticeReviewer: "",
  });
  Object.assign(surveyEnabled, {
    surveyorName: false,
    surveyDate: false,
    surveyNote: false,
    publicNoticeNote: false,
    publicNoticeRecorder: false,
    publicNoticeReviewDate: false,
    publicNoticeReviewer: false,
  });
}

function collectPayload(form, enabled, labels) {
  const payload = {};
  for (const [key, label] of Object.entries(labels)) {
    if (!enabled[key]) continue;
    const value = form[key] == null ? "" : String(form[key]).trim();
    if (!value) throw new Error(`${label}不能为空`);
    payload[key] = value;
  }
  return payload;
}

async function handleSubmit() {
  if (!props.batch?.id) {
    ElMessage.warning("请先选择调查批次");
    return;
  }
  if (!props.contractors.length) {
    ElMessage.warning("请先勾选要维护的承包方");
    return;
  }
  let basic;
  let survey;
  try {
    basic = collectPayload(basicForm, basicEnabled, BASIC_LABELS);
    survey = collectPayload(surveyForm, surveyEnabled, SURVEY_LABELS);
  } catch (error) {
    ElMessage.warning(error.message);
    return;
  }
  if (!Object.keys(basic).length && !Object.keys(survey).length) {
    ElMessage.warning("请至少勾选一项要维护的内容");
    return;
  }

  submitting.value = true;
  try {
    const { data } = await batchMaintainContractors(props.batch.id, {
      contractorUids: props.contractors.map((row) => row.contractorUid).filter(Boolean),
      basic,
      survey,
    });
    const result = data.data || {};
    if (result.failed) {
      ElMessage.warning(`已更新 ${result.updated || 0} 户，失败 ${result.failed} 户`);
    } else {
      ElMessage.success(`已批量维护 ${result.updated || 0} 户`);
    }
    emit("updated");
    emit("update:modelValue", false);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "批量维护失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.maintain-tip {
  margin-bottom: 12px;
}

.maintain-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.maintain-form :deep(.el-form-item__label) {
  display: flex;
  align-items: center;
}

.maintain-form :deep(.el-form-item__content) {
  flex: 1;
}
</style>
