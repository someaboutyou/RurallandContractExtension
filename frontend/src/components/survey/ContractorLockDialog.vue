<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    title="锁定/解锁户"
    width="620px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @open="syncStates"
  >
    <el-alert
      class="lock-tip"
      type="warning"
      :closable="false"
      show-icon
      title="锁定后，该承包方调查数据将不能修改、删除；再次取消勾选并确定即可解锁。"
    />

    <div class="lock-toolbar">
      <el-checkbox
        v-model="allLocked"
        :indeterminate="isIndeterminate"
      >全选（全部锁定）</el-checkbox>
      <span class="lock-count">已选 {{ contractors.length }} 户</span>
    </div>

    <el-table :data="contractors" border size="small" max-height="380">
      <el-table-column label="锁定" width="70" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="lockStates[row.contractorUid]" />
        </template>
      </el-table-column>
      <el-table-column prop="cbfbm" label="承包方编码" width="170" show-overflow-tooltip />
      <el-table-column prop="cbfmc" label="承包方姓名" min-width="130" show-overflow-tooltip />
      <el-table-column label="当前状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isLocked ? 'info' : 'success'" size="small" effect="plain">
            {{ row.isLocked ? "已锁定" : "未锁定" }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleConfirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { lockSurveyContractors } from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  batch: { type: Object, default: null },
  contractors: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue", "locked"]);

const lockStates = reactive({});
const saving = ref(false);

function syncStates() {
  Object.keys(lockStates).forEach((key) => delete lockStates[key]);
  props.contractors.forEach((item) => {
    lockStates[item.contractorUid] = Boolean(item.isLocked);
  });
}

const allLocked = computed({
  get: () => props.contractors.length > 0 && props.contractors.every((item) => lockStates[item.contractorUid]),
  set: (checked) => {
    props.contractors.forEach((item) => {
      lockStates[item.contractorUid] = checked;
    });
  },
});
const isIndeterminate = computed(() => {
  const count = props.contractors.filter((item) => lockStates[item.contractorUid]).length;
  return count > 0 && count < props.contractors.length;
});

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) syncStates();
  },
);

async function handleConfirm() {
  if (!props.batch?.id || !props.contractors.length) {
    ElMessage.warning("请先选择承包方");
    return;
  }
  const items = props.contractors.map((item) => ({
    contractorUid: item.contractorUid,
    locked: Boolean(lockStates[item.contractorUid]),
  }));
  saving.value = true;
  try {
    const { data } = await lockSurveyContractors(props.batch.id, { items });
    const result = data.data || {};
    ElMessage.success(
      `操作完成：锁定 ${result.locked || 0} 户，解锁 ${result.unlocked || 0} 户`,
    );
    emit("locked");
    emit("update:modelValue", false);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "锁定/解锁失败");
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.lock-tip {
  margin-bottom: 12px;
}

.lock-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.lock-count {
  color: var(--muted);
  font-size: 13px;
}
</style>
