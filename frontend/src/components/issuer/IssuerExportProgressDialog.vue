<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="520px"
    :close-on-click-modal="false"
    :show-close="jobStatus !== 'running'"
    @update:model-value="handleVisibleChange"
  >
    <div class="export-body">
      <template v-if="jobStatus === 'running'">
        <el-progress :percentage="percentage" :stroke-width="14" striped striped-flow />
        <div class="phase-line">{{ job.message || "正在启动…" }}</div>
        <div v-if="job.total" class="count-line">
          {{ job.done }} / {{ job.total }} 个村组
        </div>
        <div class="tip-line">
          数据量大时导出需要一些时间；可点「后台运行」关闭弹窗，导出完成后会自动下载并提示。
        </div>
      </template>

      <template v-else-if="jobStatus === 'done'">
        <el-result icon="success" title="导出完成" :sub-title="job.filename || ''">
          <template #extra>
            <el-button v-if="!autoDownloaded" type="primary" @click="download">重新下载</el-button>
            <el-button v-else type="primary" @click="close">关闭</el-button>
          </template>
        </el-result>
      </template>

      <template v-else-if="jobStatus === 'error'">
        <el-result icon="error" title="导出失败" :sub-title="job.error || '未知错误'" />
      </template>
    </div>

    <template #footer>
      <el-button v-if="jobStatus === 'running'" @click="close">后台运行</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
// 发包方批量导出进度弹窗：创建后台任务 → 轮询进度 → 完成后自动下载。
// 「后台运行」关闭弹窗后轮询继续（不重置状态），完成时静默下载 + ElMessage 提示。
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  downloadIssuerExportJob,
  getIssuerExportJob,
  startIssuerExportJob,
} from "../../api/issuer";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  kind: { type: String, default: "survey" }, // survey=发包方调查表 | publicity=村组公示签字表
  codes: { type: Array, default: () => [] },
  batchId: { type: Number, default: null }, // 未勾选时按批次导出全部
});
const emit = defineEmits(["update:modelValue"]);

const KIND_LABELS = { survey: "发包方调查表", publicity: "村组公示签字表" };

const job = ref({});
const jobStatus = ref("idle"); // idle / running / done / error
const autoDownloaded = ref(false);
let pollTimer = null;
let downloadSeq = 0;
const startedTaskId = ref("");

const dialogTitle = computed(() => `导出${KIND_LABELS[props.kind] || "文件"}`);

const percentage = computed(() => {
  const total = Number(job.value.total || 0);
  if (!total) return 5;
  if (job.value.percent) return Math.min(99, Number(job.value.percent));
  return Math.min(99, Math.round((Number(job.value.done || 0) / total) * 95) + 4);
});

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function start() {
  stopPoll();
  job.value = { message: "正在创建导出任务…" };
  jobStatus.value = "running";
  autoDownloaded.value = false;
  const payload = props.codes.length
    ? { kind: props.kind, codes: props.codes }
    : { kind: props.kind, batchId: props.batchId };
  startIssuerExportJob(payload)
    .then(({ data }) => {
      const taskId = data?.data?.taskId;
      if (!taskId) throw new Error("no taskId");
      startedTaskId.value = taskId;
      poll(taskId);
    })
    .catch((error) => {
      jobStatus.value = "error";
      job.value = { error: error.response?.data?.detail || "创建导出任务失败" };
    });
}

function poll(taskId) {
  stopPoll();
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getIssuerExportJob(taskId);
      const view = data.data || {};
      job.value = view;
      if (view.status === "completed") {
        stopPoll();
        jobStatus.value = "done";
        download();
      } else if (view.status === "failed") {
        stopPoll();
        jobStatus.value = "error";
        if (!isVisible()) {
          ElMessage.error(view.error || "导出失败");
        }
      }
    } catch (error) {
      stopPoll();
      jobStatus.value = "error";
      const detail = error.response?.data?.detail || "查询导出进度失败";
      job.value = { error: detail };
      if (!isVisible()) {
        ElMessage.error(detail);
      }
    }
  }, 1000);
}

function isVisible() {
  return props.modelValue;
}

async function download() {
  const seq = ++downloadSeq;
  try {
    const { data, headers } = await downloadIssuerExportJob(
      job.value?.id || startedTaskId.value || "",
    );
    if (seq !== downloadSeq) return;
    const disposition = headers?.["content-disposition"] || "";
    const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
    const filename = (match ? decodeURIComponent(match[1]) : "") || job.value.filename || "导出文件";
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    autoDownloaded.value = true;
    if (!isVisible()) {
      ElMessage.success(`已导出${KIND_LABELS[props.kind] || "文件"}：${filename}`);
      resetState();
    }
  } catch {
    if (seq !== downloadSeq) return;
    ElMessage.error("下载导出文件失败，请重新导出");
    if (!isVisible()) resetState();
  }
}

// 后台运行场景下 download() 需要 taskId；优先取 job.id（get_progress 返回），
// 兜底用创建任务时留存的 startedTaskId。
function resetState() {
  stopPoll();
  job.value = {};
  jobStatus.value = "idle";
  autoDownloaded.value = false;
  startedTaskId.value = "";
}

function handleVisibleChange(visible) {
  emit("update:modelValue", visible);
  if (!visible && jobStatus.value !== "running") {
    // 终态下关闭才重置；运行中关闭=后台运行，轮询继续
    resetState();
  }
}

function close() {
  handleVisibleChange(false);
}

defineExpose({ start, resetState });

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) start();
  },
);
</script>

<style scoped>
.export-body {
  padding: 8px 4px;
}
.phase-line {
  color: #1e293b;
  font-size: 14px;
  margin-top: 14px;
}
.count-line {
  color: #64748b;
  font-size: 13px;
  margin-top: 4px;
}
.tip-line {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 12px;
}
</style>
