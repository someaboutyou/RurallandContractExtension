<template>
  <div class="registration-app-panel">
    <el-skeleton v-if="loading" :rows="6" animated />

    <el-empty v-else-if="!renderedHtml" description="暂无登记申请书数据" />

    <div v-else class="registration-content">
      <div class="registration-toolbar">
        <el-button type="primary" @click="handlePrint">
          <el-icon><Printer /></el-icon>
          打印登记申请书
        </el-button>
      </div>

      <div class="registration-preview-wrapper">
        <iframe
          ref="iframeRef"
          :srcdoc="renderedHtml"
          :style="{ height: iframeHeight }"
          class="registration-iframe"
          frameborder="0"
          title="登记申请书预览"
          @load="syncIframeHeight"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Printer } from "@element-plus/icons-vue";
import { fetchSurveyRegistrationApplication } from "../../api/survey";

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
});

const loading = ref(false);
const renderedHtml = ref("");
const iframeRef = ref(null);
const measuredIframeHeight = ref(0);

const pageCount = computed(() => {
  const count = (renderedHtml.value.match(/<div class="page"/g) || []).length;
  return Math.max(1, count);
});

const iframeHeight = computed(() => {
  if (measuredIframeHeight.value) {
    return `${measuredIframeHeight.value}px`;
  }
  const pageHeightPx = 2049;
  const pageGapPx = 16;
  return `${pageCount.value * pageHeightPx + (pageCount.value - 1) * pageGapPx + 24}px`;
});

function syncIframeHeight() {
  const doc = iframeRef.value?.contentDocument;
  if (!doc) return;
  const height = Math.max(
    doc.documentElement?.scrollHeight || 0,
    doc.body?.scrollHeight || 0
  );
  measuredIframeHeight.value = height ? height + 24 : 0;
}

async function load() {
  if (!props.batchId || !props.contractorUid) return;
  loading.value = true;
  try {
    const { data } = await fetchSurveyRegistrationApplication(props.batchId, props.contractorUid);
    renderedHtml.value = data.data?.renderedHtml || "";
    measuredIframeHeight.value = 0;
    nextTick(() => {
      setTimeout(syncIframeHeight, 100);
    });
  } catch {
    renderedHtml.value = "";
  } finally {
    loading.value = false;
  }
}

async function handlePrint() {
  try {
    let html = renderedHtml.value;
    if (!html) {
      const { data } = await fetchSurveyRegistrationApplication(props.batchId, props.contractorUid);
      html = data.data?.renderedHtml || "";
    }
    if (!html) {
      ElMessage.warning("无可用数据");
      return;
    }
    const w = window.open("", "_blank", "width=1100,height=800");
    if (w) {
      w.document.write(html);
      w.document.close();
      setTimeout(() => w.print(), 500);
    }
  } catch {
    ElMessage.error("打印失败");
  }
}

watch(
  () => [props.batchId, props.contractorUid],
  () => { load(); },
  { immediate: true }
);
</script>

<style scoped>
.registration-app-panel {
  min-height: 400px;
}
.registration-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.registration-preview-wrapper {
  width: 100%;
  max-height: calc(92vh - 220px);
  min-height: 500px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: auto;
  background: #f2f3f5;
}
.registration-iframe {
  width: 100%;
  display: block;
  border: none;
}
</style>
