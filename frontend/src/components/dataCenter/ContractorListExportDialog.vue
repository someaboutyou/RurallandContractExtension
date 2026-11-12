<template>
  <el-dialog
    :model-value="modelValue"
    title="清单导出（数据中心）"
    width="560px"
    :close-on-click-modal="false"
    :show-close="jobStatus !== 'running'"
    @update:model-value="handleVisibleChange"
    @closed="resetDialog"
  >
    <el-alert
      class="scope-tip"
      type="info"
      :closable="false"
      show-icon
      :title="scopeTitle"
      description="发包方清单为同步生成（数据量小）；承包方清单走后台任务，完成后自动下载。"
    />

    <!-- 承包方清单后台任务进度 -->
    <div v-if="jobStatus === 'running'" class="export-body">
      <el-progress :percentage="percentage" :stroke-width="14" striped striped-flow />
      <div class="phase-line">{{ job.phase || "正在启动…" }}</div>
      <div v-if="job.total" class="count-line">{{ job.done }} / {{ job.total }} 户<span v-if="job.current">　当前：{{ job.current }}</span></div>
      <div class="tip-line">数据量大的导出需要一些时间；可点「后台运行」关闭弹窗，完成后会自动下载并提示。</div>
    </div>

    <div v-else-if="jobStatus === 'done'" class="export-body">
      <el-result icon="success" title="导出完成" :sub-title="job.filename || ''">
        <template #extra>
          <el-button v-if="!autoDownloaded" type="primary" @click="download">重新下载</el-button>
          <el-button v-else type="primary" @click="close">关闭</el-button>
        </template>
      </el-result>
    </div>

    <div v-else-if="jobStatus === 'error'" class="export-body">
      <el-result icon="error" title="导出失败" :sub-title="job.error || '未知错误'" />
    </div>

    <div v-else class="export-body">
      <!-- 发包方清单：同步导出 -->
      <div class="export-block">
        <div class="block-title">发包方清单</div>
        <div class="block-desc">主表 FBF 数据（Excel，可直接修改后经「数据导入 → 清单导入」回传）。</div>
        <el-button type="primary" plain :loading="issuerExporting" @click="exportIssuer">导出发包方清单</el-button>
      </div>

      <el-divider />

      <!-- 承包方清单：后台任务 -->
      <div class="export-block">
        <div class="block-title">承包方清单</div>
        <div class="block-desc">主表承包方成果（Excel 格式；不含已注销户）。</div>
        <el-radio-group v-model="exportMode" class="mode-group">
          <el-radio value="single">整体导出（一个 Excel）</el-radio>
          <el-radio value="group">按发包方分组（每村一个 Excel，打包 ZIP）</el-radio>
        </el-radio-group>
        <el-button type="primary" plain @click="startExport">导出承包方清单</el-button>
      </div>
    </div>

    <template #footer>
      <el-button v-if="jobStatus === 'running'" @click="close">后台运行</el-button>
      <el-button v-else @click="close">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
// 数据中心清单导出弹窗：发包方同步下载 + 承包方后台任务（进度/自动下载）。
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { exportIssuerXls } from "../../api/issuer";
import {
  downloadContractorListExportJob,
  getContractorListExportJob,
  startContractorListExportJob,
} from "../../api/dataCenter";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  regionCode: { type: String, default: "" },
  regionName: { type: String, default: "" },
  // 已选户编码清单（承包方页面勾选行传入）：非空时承包方清单只导出这些户，优先于区域/整库。
  selectedCodes: { type: Array, default: null },
});
const emit = defineEmits(["update:modelValue"]);

const issuerExporting = ref(false);
const exportMode = ref("single");

const jobStatus = ref("idle"); // idle / running / done / error
const job = ref({});
const autoDownloaded = ref(false);
let pollTimer = null;
let downloadSeq = 0;
const startedJobId = ref("");

const scopeTitle = computed(() => {
  if (props.selectedCodes?.length) {
    return `导出范围：已选 ${props.selectedCodes.length} 户（承包方清单按勾选导出）`;
  }
  const name = props.regionName || "整库";
  return props.regionCode ? `导出范围：${name}（${props.regionCode}）` : `导出范围：${name}`;
});

const percentage = computed(() => {
  const total = Number(job.value.total || 0);
  const done = Number(job.value.done || 0);
  if (!total) return 5;
  return Math.min(99, Math.round((done / total) * 95) + 4);
});

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function resetDialog() {
  stopPoll();
  job.value = {};
  jobStatus.value = "idle";
  autoDownloaded.value = false;
  startedJobId.value = "";
  downloadSeq += 1;
}

function handleVisibleChange(visible) {
  emit("update:modelValue", visible);
  if (!visible) stopPoll();
}

function close() {
  emit("update:modelValue", false);
}

function saveBlob(data, headers, fallback) {
  let filename = fallback;
  const match = /filename\*=UTF-8''([^;]+)/i.exec(headers?.["content-disposition"] || "");
  if (match) filename = decodeURIComponent(match[1]);
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function exportIssuer() {
  issuerExporting.value = true;
  try {
    const { data, headers } = await exportIssuerXls({
      regionCode: props.regionCode || undefined,
    });
    saveBlob(data, headers, `发包方清单_${props.regionCode || "整库"}.xls`);
    ElMessage.success("发包方清单已导出");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导出发包方清单失败");
  } finally {
    issuerExporting.value = false;
  }
}

async function startExport() {
  jobStatus.value = "running";
  job.value = { phase: "正在创建导出任务…" };
  try {
    const { data } = await startContractorListExportJob({
      regionCode: props.selectedCodes?.length ? "" : props.regionCode || "",
      codes: props.selectedCodes?.length ? props.selectedCodes : undefined,
      mode: exportMode.value,
    });
    startedJobId.value = data.data.jobId;
    poll(startedJobId.value);
  } catch (error) {
    jobStatus.value = "idle";
    ElMessage.error(error.response?.data?.detail || "创建导出任务失败");
  }
}

function poll(jobId) {
  stopPoll();
  const seq = ++downloadSeq;
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getContractorListExportJob(jobId);
      const view = data.data;
      job.value = view;
      if (view.status === "done") {
        stopPoll();
        jobStatus.value = "done";
        if (seq === downloadSeq) {
          autoDownloaded.value = true;
          await download();
        }
      } else if (view.status === "error") {
        stopPoll();
        jobStatus.value = "error";
      }
    } catch (error) {
      stopPoll();
      ElMessage.error(error.response?.data?.detail || "查询导出进度失败");
      jobStatus.value = "idle";
    }
  }, 1000);
}

async function download() {
  if (!startedJobId.value) return;
  try {
    const { data, headers } = await downloadContractorListExportJob(startedJobId.value);
    saveBlob(data, headers, job.value.filename || "承包方清单.zip");
    ElMessage.success("已下载导出文件");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "下载导出文件失败");
  }
}

watch(() => props.modelValue, (visible) => {
  if (!visible) stopPoll();
});
</script>

<style scoped>
.scope-tip {
  margin-bottom: 12px;
}
.export-body {
  padding: 4px 0;
}
.export-block {
  padding: 6px 0;
}
.block-title {
  color: #1e293b;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 6px;
}
.block-desc {
  color: #64748b;
  font-size: 12px;
  margin-bottom: 10px;
}
.mode-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
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
