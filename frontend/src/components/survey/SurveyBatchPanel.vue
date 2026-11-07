<template>
  <section class="panel survey-batch-panel">
    <div class="batch-panel-header">
      <div class="panel-title">{{ title }}</div>
      <el-select
        v-model="surveyStatusFilter"
        clearable
        placeholder="调查状态"
        class="batch-header-filter"
        size="small"
      >
        <el-option label="未开始" value="not_started" />
        <el-option label="进行中" value="in_progress" />
        <el-option label="已调查" value="surveyed" />
        <el-option label="已确认" value="confirmed" />
        <el-option label="已跳过" value="skipped" />
      </el-select>
    </div>

    <el-input
      v-model="keyword"
      :prefix-icon="Search"
      clearable
      placeholder="搜索批次"
      class="batch-search"
      @keyup.enter="loadBatches"
      @clear="loadBatches"
    />

    <div v-loading="loading" class="batch-card-list">
      <el-empty v-if="!filteredBatches.length && !loading" description="暂无调查批次" :image-size="88" />
      <el-tooltip
        v-for="batch in filteredBatches"
        :key="batch.id"
        placement="right"
        effect="light"
        :show-after="250"
        popper-class="batch-detail-tooltip"
      >
        <template #content>
          <div class="batch-tooltip-content">
            <div><span>批次号</span>{{ batch.batchNo || "-" }}</div>
            <div><span>创建时间</span>{{ formatDateTime(batch.createdAt) }}</div>
            <div><span>调查区域</span>{{ batch.regionName || batch.regionCode || "-" }}</div>
            <div><span>调查员</span>{{ assigneeSummary(batch) }}</div>
            <div><span>已调查</span>{{ batch.surveyedCount || 0 }} 户</div>
            <div><span>已确认</span>{{ batch.confirmedCount || 0 }} 户</div>
          </div>
        </template>
        <div
          class="batch-card"
          :class="{ 'is-active': modelValue?.id === batch.id }"
          tabindex="0"
          @click="handleBatchSelect(batch)"
          @keydown.enter.prevent="handleBatchSelect(batch)"
        >
          <span class="batch-card-title">{{ batch.batchName || batch.batchNo }}</span>
          <span class="batch-card-status-row">
            <el-tag :type="batchStatusType(batch.status)" size="small">{{ batchStatusLabel(batch.status) }}</el-tag>
            <span class="batch-card-progress">{{ batchSurveySummary(batch) }}</span>
          </span>
          <span class="batch-card-meta-row">
            <span class="batch-card-assignee" :class="{ 'is-empty': !batch.assigneeCount }">
              调查员：{{ assigneeSummary(batch) }}
            </span>
          </span>
        </div>
      </el-tooltip>
    </div>

    <div class="batch-panel-footnote">点击批次按其范围过滤列表，再次点击取消过滤</div>
  </section>
</template>

<script setup>
// 建库中心（发包方 / 承包方管理）右侧的调查批次选择面板。
// 与「/surveys 调查批次管理」的区别：无新建按钮，仅作批次筛选入口，
// 选中批次后由父视图把 batchId 传给列表接口做数据过滤。
import { computed, onMounted, ref } from "vue";
import { Search } from "@element-plus/icons-vue";

import { fetchSurveyBatches } from "../../api/survey";

const props = defineProps({
  /** 当前选中批次（完整批次对象或 null）。 */
  modelValue: { type: Object, default: null },
  /** 面板标题。 */
  title: { type: String, default: "调查批次" },
});

const emit = defineEmits(["update:modelValue"]);

const loading = ref(false);
const batches = ref([]);
const keyword = ref("");
const surveyStatusFilter = ref("");

const filteredBatches = computed(() => {
  if (!surveyStatusFilter.value) return batches.value;
  return batches.value.filter((batch) => batchSurveyStatusValue(batch) === surveyStatusFilter.value);
});

// ---- Helpers（口径与 /surveys 调查批次管理保持一致） ----
function formatDateTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 19);
}

function batchStatusLabel(value) {
  return { active: "进行中", finished: "已结束", draft: "草稿" }[value] || value || "-";
}

function batchStatusType(value) {
  return { active: "success", finished: "info", draft: "warning" }[value] || "info";
}

function batchSurveySummary(batch) {
  const total = Number(batch.taskCount || 0);
  if (!total) return "暂无任务";
  return `${Number(batch.surveyedCount || 0)}/${total} 已调查`;
}

function batchSurveyStatusValue(batch) {
  const total = Number(batch.taskCount || 0);
  const surveyed = Number(batch.surveyedCount || 0);
  const confirmed = Number(batch.confirmedCount || 0);
  const skipped = Number(batch.skippedCount || 0);
  if (!total || surveyed === 0) return "not_started";
  if (confirmed >= total) return "confirmed";
  if (skipped >= total) return "skipped";
  if (surveyed >= total) return "surveyed";
  return "in_progress";
}

function assigneeSummary(batch) {
  const names = (batch?.assigneeNames || []).filter(Boolean);
  if (!names.length) return "未分配";
  const shown = names.slice(0, 3).join("、");
  return names.length > 3 ? `${shown} 等 ${names.length} 人` : shown;
}

function handleBatchSelect(batch) {
  // 再点一次已选中的批次 = 取消过滤，回到全量列表。
  emit("update:modelValue", props.modelValue?.id === batch.id ? null : batch);
}

async function loadBatches() {
  loading.value = true;
  try {
    const { data } = await fetchSurveyBatches({
      page: 1,
      page_size: 50,
      keyword: keyword.value || undefined,
    });
    batches.value = data.data.items || [];
    // 已选批次不在最新列表里（被删/无权限）时自动取消选中。
    if (props.modelValue && !batches.value.some((item) => item.id === props.modelValue.id)) {
      emit("update:modelValue", null);
    }
  } finally {
    loading.value = false;
  }
}

onMounted(loadBatches);
</script>

<style scoped>
.survey-batch-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
}

.batch-panel-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.batch-header-filter {
  width: 104px;
}

.batch-search {
  margin-top: 10px;
}

.batch-card-list {
  flex: 1 1 auto;
  min-height: 0;
  margin-top: 10px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.batch-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md, 8px);
  background: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.batch-card:hover,
.batch-card.is-active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-7) inset;
}

.batch-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.batch-card-status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.batch-card-progress {
  font-size: 12px;
  color: var(--text-secondary, #606266);
}

.batch-card-meta-row {
  display: flex;
  align-items: center;
}

.batch-card-assignee {
  font-size: 12px;
  color: var(--text-secondary, #606266);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.batch-card-assignee.is-empty {
  color: var(--text-placeholder, #909399);
}

.batch-panel-footnote {
  margin-top: 8px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-placeholder, #909399);
}

.batch-tooltip-content div {
  display: flex;
  gap: 8px;
  font-size: 12px;
  line-height: 1.8;
}

.batch-tooltip-content span {
  color: var(--text-secondary, #909399);
  min-width: 56px;
}
</style>
