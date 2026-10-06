<template>
  <div ref="wrapRef" class="scaled-frame">
    <div v-if="loading" class="scaled-frame__loading">
      <van-loading size="22px" vertical>加载中…</van-loading>
    </div>
    <van-empty v-else-if="!html" :description="emptyText" />
    <template v-else>
      <div class="scaled-frame__viewport" :style="viewportStyle">
        <iframe
          ref="frameRef"
          :srcdoc="html"
          frameborder="0"
          class="scaled-frame__iframe"
          :style="iframeStyle"
          title="文档预览"
          @load="onFrameLoad"
        />
      </div>
      <div class="scaled-frame__toolbar">
        <van-button size="small" plain round icon="scan" @click="fit = !fit">
          {{ fit ? "原始大小" : "适应宽度" }}
        </van-button>
      </div>
    </template>
  </div>
</template>

<script setup>
/**
 * 服务端渲染 HTML（承包地示意图 / 合同文本等）的手机端预览容器。
 *
 * 服务端出的是 A4 定宽打印 HTML，直接塞 iframe 手机上得横向滚动。
 * 这里在 iframe load 后读 srcdoc 文档的实际宽度（srcdoc 与父页同源，可读），
 * 默认按容器宽度整体 scale 缩放（「适应宽度」），可一键切回原始大小。
 * 缩放失败的兜底就是 scale=1 + 容器内滚动，不会白屏。
 */
import { computed, ref } from "vue";
import { VanButton, VanEmpty, VanLoading } from "../ui.js";

const props = defineProps({
  html: { type: String, default: "" },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: "暂无内容" },
});

const wrapRef = ref(null);
const frameRef = ref(null);
const fit = ref(true);
const natural = ref({ width: 0, height: 0 });

const scale = computed(() => {
  if (!fit.value || !natural.value.width || !wrapRef.value) return 1;
  const containerWidth = wrapRef.value.clientWidth || 360;
  return Math.min(1, containerWidth / natural.value.width);
});

const viewportStyle = computed(() => ({
  height: natural.value.height ? `${Math.ceil(natural.value.height * scale.value)}px` : "70vh",
}));

const iframeStyle = computed(() => ({
  width: natural.value.width ? `${natural.value.width}px` : "100%",
  height: natural.value.height ? `${natural.value.height}px` : "100%",
  transform: scale.value === 1 ? "none" : `scale(${scale.value})`,
}));

function onFrameLoad() {
  try {
    const doc = frameRef.value?.contentDocument;
    if (!doc) return;
    natural.value = {
      width: Math.max(doc.documentElement.scrollWidth, doc.body?.scrollWidth || 0) || 0,
      height: Math.max(doc.documentElement.scrollHeight, doc.body?.scrollHeight || 0) || 0,
    };
  } catch {
    natural.value = { width: 0, height: 0 };
  }
}
</script>

<style scoped>
.scaled-frame {
  padding-bottom: 16px;
}

.scaled-frame__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
}

.scaled-frame__viewport {
  overflow: hidden;
  background: #fff;
}

.scaled-frame__iframe {
  border: none;
  transform-origin: top left;
  background: #fff;
}

.scaled-frame__toolbar {
  display: flex;
  justify-content: center;
  padding: 10px 16px 0;
}
</style>
