<template>
  <div class="m-sketch">
    <div class="m-sketch__summary">
      <span>地块数：{{ sketch?.plotCount ?? "—" }}</span>
      <span>总面积：{{ sketch?.totalArea || "—" }} 亩</span>
    </div>
    <ScaledHtmlFrame :html="sketch?.renderedHtml || ''" :loading="loading" empty-text="暂无承包地块示意图" />
  </div>
</template>

<script setup>
/**
 * 承包地块示意图（移动端只读查看）。
 *
 * 数据源与 PC 端 PlotSketchMapPanel 相同：`GET .../plot-sketch-map` →
 * `{ plotCount, totalArea, renderedHtml }`。渲染交给 ScaledHtmlFrame
 * （服务端 A4 定宽打印 HTML，按屏幕宽度整体缩放）。
 */
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { fetchSurveyPlotSketchMap } from "../../api/survey";
import ScaledHtmlFrame from "../components/ScaledHtmlFrame.vue";
import { showToast } from "../ui.js";

const route = useRoute();

const batchId = computed(() => route.params.batchId);
const contractorUid = computed(() => route.params.contractorUid);

const loading = ref(false);
const sketch = ref(null);

async function loadSketch() {
  loading.value = true;
  try {
    const { data } = await fetchSurveyPlotSketchMap(batchId.value, contractorUid.value);
    sketch.value = data?.data || null;
  } catch (error) {
    sketch.value = null;
    showToast(error?.response?.data?.detail || "示意图加载失败");
  } finally {
    loading.value = false;
  }
}

onMounted(loadSketch);
</script>

<style scoped>
.m-sketch__summary {
  display: flex;
  gap: 18px;
  padding: 12px 20px;
  font-size: 13px;
  color: #606976;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}
</style>
