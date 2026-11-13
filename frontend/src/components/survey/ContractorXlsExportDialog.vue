<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    title="承包户清单导出（Excel）"
    width="520px"
    :close-on-click-modal="false"
    :show-close="jobStatus !== 'running'"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="resetDialog"
  >
    <div class="export-body">
      <template v-if="jobStatus === 'running'">
        <el-progress :percentage="percentage" :stroke-width="14" striped striped-flow />
        <div class="phase-line">{{ job.phase || "正在启动…" }}</div>
        <div v-if="job.total" class="count-line">
          {{ job.done }} / {{ job.total }} 户<span v-if="job.current">　当前：{{ job.current }}</span>
        </div>
        <div class="tip-line">数据量大的批次导出需要一些时间，可关闭弹窗稍后在通知中下载；也可保持等待自动下载。</div>
      </template>

      <template v-else-if="jobStatus === 'done'">
        <el-result icon="success" title="导出完成" :sub-title="job.filename">
          <template #extra>
            <el-button v-if="!autoDownloaded" type="primary" @click="download">重新下载</el-button>
            <el-button v-else type="primary" @click="emit('update:modelValue', false)">关闭</el-button>
          </template>
        </el-result>
      </template>

      <template v-else-if="jobStatus === 'error'">
        <el-result icon="error" title="导出失败" :sub-title="job.error || '未知错误'" />
      </template>
    </div>

    <template #footer>
      <el-button v-if="jobStatus === 'running'" @click="emit('update:modelValue', false)">后台运行</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { downloadXlsExportJob, getXlsExportJob, startXlsExportJob } from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  batch: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue"]);

const job = ref({});
const jobStatus = ref("idle"); // idle / running / done / error
const autoDownloaded = ref(false);
let pollTimer = null;
let downloadSeq = 0;

const percentage = computed(() => {
  const total = Number(job.value.total || 0);
  if (!total) return 5;
  return Math.min(99, Math.round((Number(job.value.done || 0) / total) * 95) + 4);
});

function resetDialog() {
  stopPoll();
  job.value = {};
  jobStatus.value = "idle";
  autoDownloaded.value = false;
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function start() {
  if (!props.batch?.id) return;
  jobStatus.value = "running";
  job.value = { phase: "正在创建导出任务…" };
  try {
    const { data } = await startXlsExportJob(props.batch.id);
    poll(data.data.jobId);
  } catch (error) {
    jobStatus.value = "error";
    job.value = { error: error.response?.data?.detail || "创建导出任务失败" };
  }
}

function poll(jobId) {
  stopPoll();
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getXlsExportJob(props.batch.id, jobId);
      const view = data.data;
      job.value = view;
      if (view.status === "done") {
        stopPoll();
        jobStatus.value = "done";
        download();
      } else if (view.status === "error") {
        stopPoll();
        jobStatus.value = "error";
      }
    } catch (error) {
      stopPoll();
      jobStatus.value = "error";
      job.value = { error: error.response?.data?.detail || "查询导出进度失败" };
    }
  }, 1000);
}

async function download() {
  const seq = ++downloadSeq;
  try {
    const { data } = await downloadXlsExportJob(props.batch.id, job.value.jobId);
    if (seq !== downloadSeq) return;
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = job.value.filename || "承包方调查表.xls";
    link.click();
    URL.revokeObjectURL(url);
    autoDownloaded.value = true;
  } catch (error) {
    ElMessage.error("下载导出文件失败，请点击「重新下载」重试");
  }
}

watch(() => props.modelValue, (visible) => { if (visible) start(); });
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
