<template>
  <div class="contractor-info-panel">
    <!-- 黄色高亮提示 -->
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

    <!-- 承包方基本信息 -->
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item label="承包方编码">
        <span :class="changedClass('code')">{{ result.code }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="承包方名称">
        <span :class="changedClass('name')">{{ result.name }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="承包方类型">
        <span :class="changedClass('typeCode')">{{ typeLabel }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="证件类型">
        <span :class="changedClass('idType')">{{ idTypeLabel }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="证件号码">
        <span :class="changedClass('idNo')">{{ result.idNo }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="联系电话">
        <span :class="changedClass('mobile')">{{ result.mobile || '-' }}</span>
      </el-descriptions-item>
      <el-descriptions-item :span="2" label="承包方地址">
        <span :class="changedClass('address')">{{ result.address }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="邮政编码">
        <span :class="changedClass('postcode')">{{ result.postcode }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="成员数量">
        <span :class="changedClass('memberCount')">{{ result.memberCount }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="村民小组">
        <span :class="changedGroupClass('groupRegionCode')">{{ result.groupRegionName || result.groupRegionCode || '-' }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="调查员">
        <span :class="changedClass('surveyorName')">{{ result.surveyorName || '-' }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="调查日期">
        <span :class="changedClass('surveyDate')">{{ result.surveyDate || '-' }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="调查记述">
        <span :class="changedClass('surveyNote')">{{ result.surveyNote || '-' }}</span>
      </el-descriptions-item>
    </el-descriptions>

    <ChangeDiffViewer ref="diffViewer" />
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import ChangeDiffViewer from "./ChangeDiffViewer.vue";

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  result: { type: Object, required: true },
  changedFields: { type: Array, default: () => [] },
});

const diffViewer = ref(null);

const typeMap = { "1": "农户", "2": "个人", "3": "单位" };
const typeLabel = computed(() => typeMap[props.result.typeCode] || props.result.typeCode);
const idTypeMap = { "1": "居民身份证", "2": "户口簿", "3": "军官证" };
const idTypeLabel = computed(() => idTypeMap[props.result.idType] || props.result.idType);

const fieldKeyMap = {
  code: "code", name: "name", typeCode: "typeCode", idType: "idType",
  idNo: "idNo", mobile: "mobile", address: "address", postcode: "postcode",
  memberCount: "memberCount", surveyorName: "surveyorName", surveyDate: "surveyDate",
  surveyNote: "surveyNote", groupRegionCode: "groupRegionCode", groupRegionName: "groupRegionName",
};

function changedClass(field) {
  const key = fieldKeyMap[field];
  return props.changedFields.includes(key) ? "field-changed" : "";
}

function changedGroupClass(field) {
  const map = { groupRegionCode: ["groupRegionCode", "groupRegionName"] };
  const keys = map[field] || [fieldKeyMap[field]];
  return keys.some((k) => props.changedFields.includes(k)) ? "field-changed" : "";
}
</script>

<style scoped>
.contractor-info-panel { min-height: 200px; }
.change-alert { margin-bottom: 12px; }
.field-changed { background-color: #fdf6ec; padding: 2px 6px; border-radius: 3px; }
</style>
