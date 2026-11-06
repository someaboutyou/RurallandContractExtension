<template>
  <el-dialog :model-value="modelValue" title="合并发包方" width="820px" @update:model-value="$emit('update:modelValue', $event)">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="merge-alert"
      title="合并后，被合并发包方的承包方、地块、合同等关联信息将全部划转到保留的发包方名下，被合并发包方将被删除，操作不可恢复。"
    />
    <el-table :data="rows" border stripe size="small">
      <el-table-column label="保留" width="70" align="center">
        <template #default="{ row }">
          <el-radio v-model="keepCode" :value="row.code" />
        </template>
      </el-table-column>
      <el-table-column prop="code" label="发包方编码" width="160" show-overflow-tooltip />
      <el-table-column prop="name" label="发包方名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="ownerName" label="负责人" width="110" />
      <el-table-column prop="address" label="地址" min-width="200" show-overflow-tooltip />
    </el-table>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!keepCode" @click="handleMerge">确认合并</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage } from "element-plus";

import { mergeIssuers } from "../../api/issuer";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  rows: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue", "merged"]);

const saving = ref(false);
const keepCode = ref("");

function close() {
  emit("update:modelValue", false);
}

function open() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选要合并的发包方");
    return;
  }
  keepCode.value = "";
  emit("update:modelValue", true);
}

async function handleMerge() {
  if (!keepCode.value) return;
  const mergeCodes = props.rows
    .map((row) => row.code)
    .filter((code) => code && code !== keepCode.value);
  if (!mergeCodes.length) {
    ElMessage.warning("请至少再选择一个要合并的发包方");
    return;
  }
  saving.value = true;
  try {
    const { data } = await mergeIssuers({ keepCode: keepCode.value, mergeCodes });
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
</style>
