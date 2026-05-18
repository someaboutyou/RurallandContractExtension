<template>
  <div class="plot-sketch-panel">
    <div class="plot-sketch-toolbar">
      <div class="plot-sketch-summary">
        <span>地块数：{{ sketch?.plotCount ?? "-" }}</span>
        <span>总面积：{{ sketch?.totalArea || "-" }} 亩</span>
      </div>
      <div class="plot-sketch-actions">
        <el-button size="small" plain @click="loadSketch">刷新</el-button>
        <el-button size="small" type="primary" :disabled="!sketch?.renderedHtml" @click="handlePrint">
          打印
        </el-button>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated />
    <el-empty v-else-if="!sketch?.renderedHtml" description="暂无承包地块示意图" />
    <div v-else class="plot-sketch-preview">
      <iframe
        :srcdoc="sketch.renderedHtml"
        class="plot-sketch-iframe"
        frameborder="0"
        :style="{ height: iframeHeight }"
        title="承包地块示意图预览"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { fetchSurveyPlotSketchMap } from "../../api/survey";

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  refreshKey: { type: Number, default: 0 },
});

const loading = ref(false);
const sketch = ref(null);

const pageCount = computed(() => {
  const html = sketch.value?.renderedHtml || "";
  return Math.max(1, (html.match(/<section class="page"/g) || []).length);
});

const iframeHeight = computed(() => `${pageCount.value * 820}px`);

async function loadSketch() {
  if (!props.batchId || !props.contractorUid) return;
  loading.value = true;
  try {
    const { data } = await fetchSurveyPlotSketchMap(props.batchId, props.contractorUid);
    sketch.value = data.data;
  } catch {
    sketch.value = null;
    ElMessage.error("加载承包地块示意图失败");
  } finally {
    loading.value = false;
  }
}

function handlePrint() {
  const html = sketch.value?.renderedHtml;
  if (!html) return;
  const w = window.open("", "_blank", "width=1100,height=760");
  if (w) {
    w.document.write(html);
    w.document.close();
    setTimeout(() => w.print(), 500);
  }
}

watch(
  () => [props.batchId, props.contractorUid, props.refreshKey],
  () => loadSketch(),
  { immediate: true },
);
</script>

<style scoped>
.plot-sketch-panel {
  min-height: 400px;
}

.plot-sketch-toolbar {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 12px;
}

.plot-sketch-summary {
  color: #606266;
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 13px;
}

.plot-sketch-actions {
  display: flex;
  gap: 8px;
}

.plot-sketch-preview {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  height: calc(92vh - 260px);
  min-height: 560px;
  overflow: auto;
}

.plot-sketch-iframe {
  border: none;
  width: 100%;
}
</style>
