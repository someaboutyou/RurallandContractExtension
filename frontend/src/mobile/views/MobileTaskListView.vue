<template>
  <div class="m-tasks">
    <van-cell-group inset>
      <van-field
        :model-value="activeBatchLabel"
        label="批次"
        readonly
        is-link
        placeholder="请选择调查批次"
        @click="batchPickerVisible = true"
      />
      <van-field
        v-model="keyword"
        label="搜索"
        placeholder="承包方姓名 / 编码"
        clearable
        @keyup.enter="reload"
      />
    </van-cell-group>

    <div v-if="activeBatchId" class="m-tasks__summary">
      <span>共 {{ total }} 户</span>
      <span class="m-tasks__summary-split">未完成 {{ pendingCount }} 户</span>
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="reload">
      <van-list
        v-model:loading="loading"
        :finished="finished"
        :error="loadError"
        finished-text="没有更多了"
        error-text="加载失败，点击重试"
        @load="loadMore"
      >
        <van-cell
          v-for="task in tasks"
          :key="`${task.batchId}-${task.contractorUid}`"
          is-link
          center
          @click="openTask(task)"
        >
          <template #title>
            <span class="m-task__name">{{ task.cbfmc || "（未命名）" }}</span>
            <van-tag :type="statusTagType(task.taskStatus)">{{ statusLabel(task.taskStatus) }}</van-tag>
          </template>
          <template #label>
            <div class="m-task__meta">{{ task.cbfbm }}</div>
            <div class="m-task__meta">{{ task.cbfdz || "地址未填" }}</div>
            <div class="m-task__meta">
              成员 {{ task.cbfcysl ?? 0 }} 人<template v-if="task.lxdh"> · {{ task.lxdh }}</template>
            </div>
          </template>
        </van-cell>
      </van-list>
    </van-pull-refresh>

    <van-empty v-if="!loading && !tasks.length" :description="emptyText" />

    <van-popup v-model:show="batchPickerVisible" position="bottom" round>
      <van-picker
        :columns="batchColumns"
        :default-index="defaultBatchIndex"
        title="选择调查批次"
        @confirm="onBatchConfirm"
        @cancel="batchPickerVisible = false"
      />
    </van-popup>
  </div>
</template>

<script setup>
/**
 * 「我的待调查」清单。
 *
 * 数据源：`GET /surveys/batches/{id}/tasks?mine=1`
 * —— `mine=1` 依赖后端 2026-09-21 接线的任务归属（`survey_cbf_base.assigned_to`）。
 * 注意后端那条铁律：**`assigned_to` 为空 = 不限制归属**（未分配的任务所有人可见），
 * 所以这里用 `mine=1` 拿到的是"我负责的 + 尚未分配的"，符合调查员实际预期。
 *
 * 状态标签口径与 PC 端 `taskStatusLabel()` 保持一致（后端 taskStatus 取值见
 * `backend/app/services/survey/assignment.py`）。
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { fetchSurveyBatches, fetchSurveyTasks } from "../../api/survey";
import {
  VanCell,
  VanCellGroup,
  VanEmpty,
  VanField,
  VanList,
  VanPicker,
  VanPopup,
  VanPullRefresh,
  VanTag,
  showToast,
} from "../ui.js";

const PAGE_SIZE = 20;

const STATUS_LABELS = {
  not_started: "未调查",
  not_surveyed: "未调查",
  in_progress: "调查中",
  surveyed: "已调查",
  changed: "有变化",
  unchanged: "无变化",
  confirmed: "已确认",
  skipped: "已跳过",
  deregistered: "已注销",
};

/** 视为「已完成」、不计入待办数的状态。 */
const DONE_STATUSES = ["confirmed", "skipped", "deregistered"];

const router = useRouter();

const batches = ref([]);
const activeBatchId = ref(null);
const batchPickerVisible = ref(false);
const keyword = ref("");

const tasks = ref([]);
const total = ref(0);
const page = ref(1);
const loading = ref(false);
const finished = ref(false);
const refreshing = ref(false);
const loadError = ref(false);

const activeBatch = computed(() => batches.value.find((item) => item.id === activeBatchId.value) || null);
const activeBatchLabel = computed(() => activeBatch.value?.batchName || "");
const batchColumns = computed(() =>
  batches.value.map((item) => ({ text: item.batchName || item.batchNo || `批次 ${item.id}`, value: item.id })),
);
const defaultBatchIndex = computed(() => {
  const index = batches.value.findIndex((item) => item.id === activeBatchId.value);
  return index < 0 ? 0 : index;
});
const pendingCount = computed(() => tasks.value.filter((item) => !DONE_STATUSES.includes(item.taskStatus)).length);
const emptyText = computed(() => (activeBatchId.value ? "没有符合条件的任务" : "请先选择调查批次"));

function statusLabel(status) {
  return STATUS_LABELS[status] || status || "未知";
}

function statusTagType(status) {
  switch (status) {
    case "confirmed":
      return "success";
    case "surveyed":
    case "changed":
      return "primary";
    case "skipped":
    case "deregistered":
      return "warning";
    case "in_progress":
      return "primary";
    default:
      return "default";
  }
}

async function loadBatches() {
  try {
    const { data } = await fetchSurveyBatches({ page: 1, page_size: 50 });
    batches.value = data?.data?.items || [];
    const preferred =
      batches.value.find((item) => item.status === "active") || batches.value[0] || null;
    activeBatchId.value = preferred?.id ?? null;
    return Boolean(activeBatchId.value);
  } catch (error) {
    showToast(error?.response?.data?.detail || "批次加载失败");
    return false;
  }
}

async function loadMore() {
  if (!activeBatchId.value) {
    loading.value = false;
    finished.value = true;
    return;
  }

  loading.value = true;
  loadError.value = false;
  try {
    const { data } = await fetchSurveyTasks(activeBatchId.value, {
      page: page.value,
      page_size: PAGE_SIZE,
      keyword: keyword.value.trim() || undefined,
      mine: 1,
    });
    const items = data?.data?.items || [];
    total.value = data?.data?.total ?? items.length;

    tasks.value = page.value === 1 ? items : [...tasks.value, ...items];
    finished.value = items.length === 0 || tasks.value.length >= total.value;
    page.value += 1;
  } catch (error) {
    loadError.value = true;
    showToast(error?.response?.data?.detail || "任务加载失败");
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

function reload() {
  page.value = 1;
  finished.value = false;
  loadError.value = false;
  tasks.value = [];
  total.value = 0;
  return loadMore();
}

function onBatchConfirm({ selectedOptions }) {
  activeBatchId.value = selectedOptions?.[0]?.value ?? null;
  batchPickerVisible.value = false;
  reload();
}

function openTask(task) {
  router.push({
    name: "mobile-task-detail",
    params: { batchId: String(task.batchId), contractorUid: task.contractorUid },
  });
}

onMounted(async () => {
  const ok = await loadBatches();
  if (ok) {
    await reload();
  } else {
    finished.value = true;
  }
});
</script>

<style scoped>
.m-tasks {
  padding-bottom: 12px;
}

.m-tasks__summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px 6px;
  font-size: 12px;
  color: #8a94a6;
}

.m-tasks__summary-split::before {
  content: "·";
  margin-right: 12px;
  color: #d3d6dd;
}

.m-task__name {
  margin-right: 8px;
  font-size: 15px;
  font-weight: 500;
}

.m-task__meta {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: #8a94a6;
}
</style>
