<template>
  <el-dialog
    :model-value="modelValue"
    :title="attachmentPreviewName || '附件预览'"
    width="960px"
    destroy-on-close
    append-to-body
    class="attachment-preview-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
    @closed="handleClosed"
  >
    <div v-loading="loading" class="attachment-preview-shell">
      <template v-if="previewUrl">
        <img
          v-if="previewType === 'image'"
          :src="previewUrl"
          :alt="attachmentPreviewName || '附件预览'"
          class="attachment-preview-image"
        />
        <iframe
          v-else-if="previewType === 'pdf'"
          :src="previewUrl"
          class="attachment-preview-pdf"
          title="附件预览"
        ></iframe>
      </template>
      <el-empty v-else description="当前附件暂不支持在线预览" />
    </div>
    <template #footer>
      <div class="attachment-preview-footer">
        <span v-if="navigation" class="attachment-preview-position">
          第 {{ navigation.index + 1 }} / {{ navigation.total }} 个附件
        </span>
        <div class="attachment-preview-footer-actions">
          <el-button v-if="navigation" :disabled="navigation.index <= 0" @click="$emit('prev')">上一个</el-button>
          <el-button v-if="navigation" :disabled="navigation.index >= navigation.total - 1" @click="$emit('next')">下一个</el-button>
          <el-button v-if="source" plain type="primary" @click="$emit('download', source)">下载原件</el-button>
          <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { downloadRequestAttachment } from "../../api/request";
import { getAttachmentPreviewKind } from "../../utils/attachmentHelpers";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  source: { type: Object, default: null },
  // 附件数据加载器：默认取「业务申请附件」；其他模块（如调查附件）可注入自己的实现，
  // 只要返回 axios 响应（含 data 与 headers.content-type）即可复用本弹窗。
  loader: { type: Function, default: null },
  // 传 { index, total } 才显示「上一个 / 下一个」；不传（如业务申请页）保持原样。
  // 翻页只改 source，本组件靠 source 的 watch 重新取数，父组件不必关心加载逻辑。
  navigation: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue", "download", "prev", "next"]);

const loading = ref(false);
const previewUrl = ref("");
const previewType = ref("");
const attachmentPreviewName = ref("");
// 连续翻页时旧请求可能后到，用自增票号丢弃过期响应。
let loadToken = 0;

async function loadPreview(item) {
  const token = ++loadToken;
  if (previewUrl.value) { URL.revokeObjectURL(previewUrl.value); previewUrl.value = ""; }
  const kind = getAttachmentPreviewKind(item);
  if (!kind) {
    attachmentPreviewName.value = item?.originalName || "附件预览";
    previewType.value = "";
    loading.value = false;
    return;
  }
  loading.value = true;
  previewType.value = kind;
  attachmentPreviewName.value = item?.originalName || "附件预览";
  try {
    const caseId = item?.__caseId;
    const response = props.loader
      ? await props.loader(item)
      : await downloadRequestAttachment(caseId, item.id);
    if (token !== loadToken) return;
    const blob = new Blob([response.data], {
      type: item.contentType || response.headers["content-type"] || "application/octet-stream",
    });
    previewUrl.value = URL.createObjectURL(blob);
  } catch (error) {
    if (token !== loadToken) return;
    emit("update:modelValue", false);
    ElMessage.error(error.response?.data?.detail || "附件预览失败");
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

function handleClosed() {
  loadToken += 1;
  if (previewUrl.value) { URL.revokeObjectURL(previewUrl.value); previewUrl.value = ""; }
  loading.value = false;
  attachmentPreviewName.value = "";
  previewType.value = "";
}

watch(() => props.modelValue, (visible) => {
  if (visible && props.source) loadPreview(props.source);
  else handleClosed();
});

watch(() => props.source, (item) => {
  if (props.modelValue && item) loadPreview(item);
});
</script>