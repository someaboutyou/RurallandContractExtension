<template>
  <van-popup
    :show="show"
    position="bottom"
    round
    :style="{ maxHeight: '86%' }"
    @update:show="emit('update:show', $event)"
  >
    <div class="ocr-dialog">
      <div class="ocr-dialog__header">
        <span class="ocr-dialog__title">{{ title }}</span>
        <span v-if="elapsedMs" class="ocr-dialog__meta">识别 {{ (elapsedMs / 1000).toFixed(1) }}s</span>
      </div>

      <p class="ocr-dialog__hint">识别结果仅供参考，请逐项核对后确认；点击字段可直接修改。</p>

      <van-cell-group inset>
        <van-field
          v-for="field in editableFields"
          :key="field.key"
          v-model="field.value"
          :label="field.label"
          :placeholder="`请输入${field.label}`"
          input-align="right"
          clearable
        >
          <template #right-icon>
            <van-tag v-if="field.score && field.score >= 0.85" type="success" plain>高</van-tag>
            <van-tag v-else-if="field.score" type="warning" plain>核对</van-tag>
            <van-tag v-else type="danger" plain>未识</van-tag>
          </template>
        </van-field>
      </van-cell-group>

      <p v-if="warnings.length" class="ocr-dialog__warning">
        {{ warnings.join("；") }}
      </p>

      <!-- 识别原文：字段抽不齐时用户截图回传，用于调解析规则 -->
      <div v-if="rawText" class="ocr-dialog__raw">
        <div class="ocr-dialog__raw-toggle" @click="rawVisible = !rawVisible">
          <span>{{ rawVisible ? "收起识别原文" : "字段不对？查看识别原文" }}</span>
          <van-icon :name="rawVisible ? 'arrow-down' : 'arrow-up'" />
        </div>
        <p v-if="rawVisible" class="ocr-dialog__raw-text">{{ rawText }}</p>
      </div>

      <div class="ocr-dialog__actions">
        <van-button block round plain @click="emit('update:show', false)">取消</van-button>
        <van-button block round type="primary" @click="onConfirm">确认并上传</van-button>
      </div>
    </div>
  </van-popup>
</template>

<script setup>
/**
 * 证件识别结果确认弹层。
 *
 * 收到 parser.js 的解析结果后把字段变成可编辑表单；确认时把（可能被人工改过的）
 * 字段值回传给调用方 —— OCR 只做预填，落库内容以人工确认为准。
 * 低置信度（<0.85）字段打「核对」标，识别失败字段打「未识」标。
 */
import { computed, reactive, ref, watch } from "vue";
import { VanButton, VanCellGroup, VanField, VanIcon, VanPopup, VanTag } from "../ui.js";

const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: "识别结果" },
  docType: { type: String, default: "" },
  fields: { type: Array, default: () => [] },
  elapsedMs: { type: Number, default: 0 },
  /** OCR 识别原文（各行拼合）；提供后展示可展开的「识别原文」区 */
  rawText: { type: String, default: "" },
});

const emit = defineEmits(["update:show", "confirm"]);

const rawVisible = ref(false);
const editableFields = reactive([]);

watch(
  () => [props.show, props.fields],
  ([visible, fields]) => {
    if (!visible) return;
    rawVisible.value = false;
    editableFields.splice(
      0,
      editableFields.length,
      ...(fields || []).map((field) => ({ ...field, value: String(field.value || "") })),
    );
  },
  { immediate: true },
);

const warnings = computed(() =>
  editableFields
    .filter((field) => field.warning)
    .map((field) => `${field.label}：${field.warning}`),
);

function onConfirm() {
  const values = {};
  for (const field of editableFields) {
    values[field.key] = field.value.trim();
  }
  emit("confirm", values);
  emit("update:show", false);
}
</script>

<style scoped>
.ocr-dialog {
  padding-bottom: calc(16px + env(safe-area-inset-bottom));
}

.ocr-dialog__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 18px 24px 0;
}

.ocr-dialog__title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2d3d;
}

.ocr-dialog__meta {
  font-size: 12px;
  color: #8a94a6;
}

.ocr-dialog__hint {
  margin: 8px 24px 12px;
  font-size: 12px;
  color: #8a94a6;
}

.ocr-dialog__warning {
  margin: 10px 24px 0;
  font-size: 12px;
  line-height: 1.7;
  color: #ee0a24;
}

.ocr-dialog__raw {
  margin: 12px 24px 0;
}

.ocr-dialog__raw-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 12px;
  color: #1989fa;
}

.ocr-dialog__raw-text {
  margin: 0;
  padding: 8px 10px;
  max-height: 160px;
  overflow-y: auto;
  font-size: 11px;
  line-height: 1.6;
  word-break: break-all;
  background: #f7f8fa;
  border-radius: 6px;
  color: #646566;
  white-space: pre-wrap;
}

.ocr-dialog__actions {
  display: flex;
  gap: 12px;
  padding: 18px 16px 0;
}
</style>
