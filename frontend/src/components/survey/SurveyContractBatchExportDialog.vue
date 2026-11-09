<template>
  <el-dialog
    v-model="visible"
    title="批量导出延包合同"
    :width="620"
    :close-on-click-modal="!running"
    :close-on-press-escape="!running"
    :show-close="!running"
    append-to-body
    @closed="onClosed"
  >
    <el-alert type="info" :closable="false" show-icon class="batch-tip">
      <template #title>
        将逐户导出 <b>{{ targets.length }}</b> 户现行延包合同 Word（与打印同一 HTML 母版，
        不含末页「承包地块示意图」），完成后自动打包为一个 zip 压缩包下载。
      </template>
    </el-alert>

    <!-- 批量进度：运行中/结束时替换提示展示 -->
    <div v-if="running || progress.finished" class="progress-block">
      <el-progress
        :percentage="progressPercent"
        :status="progress.finished ? (progress.failCount ? 'warning' : 'success') : undefined"
      />
      <div class="progress-text">
        <template v-if="running">
          正在导出：{{ progress.current || "" }}（{{ progress.done }}/{{ progress.total }}）
        </template>
        <template v-else>
          完成：成功 {{ progress.successCount }} 户<template v-if="progress.failCount">，失败 {{ progress.failCount }} 户</template>
          <template v-if="progress.successCount">，压缩包已开始下载</template>
        </template>
      </div>
      <el-alert
        v-if="progress.finished && progress.failures.length"
        type="error"
        :closable="false"
        show-icon
        class="fail-list"
      >
        <template #title>以下承包户合同导出失败（未包含在压缩包中）：</template>
        <div v-for="item in progress.failures" :key="item.contractorUid" class="fail-item">
          {{ item.cbfmc || item.contractorUid }}：{{ item.reason }}
        </div>
      </el-alert>
    </div>

    <template #footer>
      <template v-if="progress.finished">
        <el-button type="primary" @click="visible = false">关闭</el-button>
      </template>
      <template v-else-if="running">
        <el-button disabled>导出中，请勿关闭…</el-button>
      </template>
      <template v-else>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="submit">开始导出</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 「批量导出延包合同」对话框 —— 承包合同管理页专用。
 *
 * 逐户串行调用「现行延包合同导出 Word」接口（同一 HTML 母版转写 docx），
 * 前端推进进度条并逐户记录成功 / 失败；结束后用 fflate 在浏览器端打包 zip
 * 触发下载（docx 本身已压缩，zip 用 level 0 仅装填，速度最快）。
 *
 * ⚠️ 口径：只导出**本平台生成的现行延包合同**。库里可能存在导入的「现行合同」
 * （二轮承包合同标 active），不算已生成合同——后端对此类户返回 404，
 * 逐户落入下方失败清单提示。
 */
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { exportSurveyContractDocx } from "../../api/survey";

const props = defineProps({
  batchId: { type: Number, default: null },
  // 压缩包文件名（不含扩展名），由调用方按批次区域拼接
  zipName: { type: String, default: "延包合同" },
});

const visible = ref(false);
const running = ref(false);
const targets = ref([]);
const progress = reactive({
  total: 0,
  done: 0,
  successCount: 0,
  failCount: 0,
  failures: [],
  current: "",
  finished: false,
});

const progressPercent = computed(() =>
  progress.total ? Math.round((progress.done / progress.total) * 100) : 0,
);

/**
 * 打开对话框。contractors: [{ contractorUid, cbfmc, cbfbm }]，
 * 只应传入已生成延包合同（row.signed）的户。
 */
function open({ contractors }) {
  const list = (contractors || []).filter((item) => item?.contractorUid);
  if (!list.length) {
    ElMessage.warning("没有可导出合同的承包户");
    return;
  }
  if (!props.batchId) {
    ElMessage.warning("请先选择调查批次");
    return;
  }
  targets.value = list;
  progress.total = list.length;
  progress.done = 0;
  progress.successCount = 0;
  progress.failCount = 0;
  progress.failures = [];
  progress.current = "";
  progress.finished = false;
  running.value = false;
  visible.value = true;
}

// Windows 文件名非法字符（zip 内条目名同受其影响）
function sanitizeFilename(name) {
  return String(name).replace(/[\\/:*?"<>|\r\n]/g, "_").trim() || "未命名";
}

function entryName(item, used) {
  const base = `${sanitizeFilename(item.cbfmc || item.cbfbm || item.contractorUid)}农村土地（耕地）承包合同`;
  let name = `${base}.docx`;
  // 同名承包户：追加承包方编码去重
  if (used.has(name)) name = `${base}_${sanitizeFilename(item.cbfbm || item.contractorUid)}.docx`;
  used.add(name);
  return name;
}

// blob 形式的错误响应里抠出 detail（axios 对 blob 响应的报错不会自动解析 JSON）
async function extractErrorDetail(error) {
  const body = error?.response?.data;
  if (body instanceof Blob) {
    try {
      const parsed = JSON.parse(await body.text());
      return parsed?.detail || parsed?.message || "导出失败";
    } catch {
      return "导出失败";
    }
  }
  return error?.response?.data?.detail || "导出失败";
}

async function submit() {
  running.value = true;
  const files = {}; // zip 内条目名 → docx 字节
  const used = new Set();
  try {
    for (const target of targets.value) {
      progress.current = target.cbfmc || target.cbfbm || target.contractorUid;
      try {
        const { data } = await exportSurveyContractDocx(
          props.batchId,
          target.contractorUid,
          { timeout: 120000 }, // 渲染含地块/成员/示意图数据装配，放宽默认 10s 超时
        );
        files[entryName(target, used)] = new Uint8Array(await data.arrayBuffer());
        progress.successCount += 1;
      } catch (error) {
        progress.failCount += 1;
        progress.failures.push({
          contractorUid: target.contractorUid,
          cbfmc: target.cbfmc || "",
          reason: await extractErrorDetail(error),
        });
      }
      progress.done += 1;
    }

    if (progress.successCount) {
      const { zipSync } = await import("fflate");
      // docx 自身已是 deflate 压缩格式，level 0 只装填不再压缩
      const zipped = zipSync(files, { level: 0 });
      const blob = new Blob([zipped], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${sanitizeFilename(props.zipName)}.zip`;
      link.click();
      URL.revokeObjectURL(url);
    }
  } finally {
    running.value = false;
    progress.finished = true;
  }

  if (!progress.failCount) ElMessage.success(`批量导出完成：共 ${progress.successCount} 户`);
  else ElMessage.warning(`批量导出完成：成功 ${progress.successCount} 户，失败 ${progress.failCount} 户`);
}

function onClosed() {
  // 全部成功后自动清场；有失败时保留面板供用户查看失败清单
  if (progress.finished && !progress.failCount) {
    progress.finished = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.batch-tip {
  margin-bottom: 12px;
}
.progress-block {
  padding: 8px 4px 4px;
}
.progress-text {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}
.fail-list {
  margin-top: 12px;
}
.fail-item {
  font-size: 12px;
  line-height: 1.8;
}
</style>
