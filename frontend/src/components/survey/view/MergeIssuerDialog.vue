<template>
  <el-dialog :model-value="modelValue" title="合并发包方" width="860px" @update:model-value="$emit('update:modelValue', $event)">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="merge-alert"
      title="合并后，被合并发包方的地块、承包方等关联信息将全部划转到保留的发包方名下，被合并发包方将被删除，操作不可恢复。"
    />
    <el-table :data="rows" border stripe size="small" class="merge-table">
      <el-table-column label="保留" width="70" align="center">
        <template #default="{ row }">
          <el-radio v-model="keepIssuerUid" :value="row.issuerUid" />
        </template>
      </el-table-column>
      <el-table-column prop="code" label="发包方编码" width="150" show-overflow-tooltip />
      <el-table-column prop="name" label="发包方名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="responsibleName" label="负责人" width="100" />
      <el-table-column label="关联承包方数" width="110" align="center">
        <template #default="{ row }">
          {{ row.relatedContractorCount ?? 0 }}
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!keepIssuerUid" @click="handleMerge">确认合并</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage } from "element-plus";

import { mergeSurveyIssuers } from "../../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  activeBatch: { type: Object, default: null },
  // 选中的发包方行（≥2 行才允许打开本弹窗，由父组件把关）
  rows: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue", "merged"]);

const saving = ref(false);
const keepIssuerUid = ref("");

function close() {
  emit("update:modelValue", false);
}

function open() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选要合并的发包方");
    return;
  }
  keepIssuerUid.value = "";
  emit("update:modelValue", true);
}

async function handleMerge() {
  if (!props.activeBatch || !keepIssuerUid.value) return;
  const mergeIssuerUids = props.rows.map((row) => row.issuerUid).filter((uid) => uid !== keepIssuerUid.value);
  if (!mergeIssuerUids.length) {
    ElMessage.warning("请至少再选择一个要合并的发包方");
    return;
  }
  saving.value = true;
  try {
    const { data } = await mergeSurveyIssuers(props.activeBatch.id, {
      keepIssuerUid: keepIssuerUid.value,
      mergeIssuerUids,
    });
    const result = data.data || {};
    const contractNote = Number(result.movedContractCount || 0) > 0 ? `、${result.movedContractCount} 份合同` : "";
    ElMessage.success(
      `合并完成：已划转 ${result.movedParcelCount ?? 0} 个地块关联、${result.movedContractorCount ?? 0} 个承包方${contractNote}到「${result.keepIssuer?.name || ""}」名下`,
    );
    close();
    emit("merged");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "合并发包方失败");
  } finally {
    saving.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.merge-alert {
  margin-bottom: 12px;
}
.merge-table {
  width: 100%;
}
</style>
