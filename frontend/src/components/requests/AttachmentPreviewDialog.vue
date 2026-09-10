<template>
  <el-dialog
    :model-value="modelValue"
    :title="attachmentPreviewName || '附件预览'"
    width="960px"
    destroy-on-close
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
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
      <el-button v-if="source" plain type="primary" @click="$emit('download', source)">下载原件</el-button>
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
});
const emit = defineEmits(["update:modelValue", "download"]);

const loading = ref(false);
const previewUrl = ref("");
const previewType = ref("");
const attachmentPreviewName = ref("");

async function loadPreview(item) {
  const kind = getAttachmentPreviewKind(item);
  if (!kind) {
    attachmentPreviewName.value = item?.originalName || "附件预览";
    previewType.value = "";
    return;
  }
  loading.value = true;
  previewType.value = kind;
  attachmentPreviewName.value = item?.originalName || "附件预览";
  try {
    const caseId = item?.__caseId;
    const response = await downloadRequestAttachment(caseId, item.id);
    const blob = new Blob([response.data], {
      type: item.contentType || response.headers["content-type"] || "application/octet-stream",
    });
    previewUrl.value = URL.createObjectURL(blob);
  } catch (error) {
    emit("update:modelValue", false);
    ElMessage.error(error.response?.data?.detail || "附件预览失败");
  } finally {
    loading.value = false;
  }
}

function handleClosed() {
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