<template>
  <el-dialog
    v-model="visible"
    title="移除地块"
    width="560px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="移除地块会将该地块从当前承包方名下移除，原地块数据保留但不再关联。请确认操作。"
      type="warning"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-form :model="form" label-position="top" class="parcel-form">
      <el-form-item label="选择要移除的地块" required>
        <el-select
          v-model="form.dkbm"
          placeholder="请选择要移除的地块"
          style="width: 100%"
          @change="onParcelSelect"
        >
          <el-option
            v-for="p in parcels"
            :key="p.dkbm"
            :label="`${p.dkbm} — ${p.dkmc || '未命名'}（${p.scmj || 0} 亩）`"
            :value="p.dkbm"
          >
            <span class="option-code">{{ p.dkbm }}</span>
            <span class="option-name">{{ p.dkmc || '未命名' }}</span>
            <span class="option-area">{{ p.scmj || 0 }} 亩</span>
          </el-option>
        </el-select>
      </el-form-item>

      <el-descriptions v-if="selectedParcel" :column="2" border size="small" style="margin-bottom: 16px">
        <el-descriptions-item label="地块编码">{{ selectedParcel.dkbm }}</el-descriptions-item>
        <el-descriptions-item label="地块名称">{{ selectedParcel.dkmc || '-' }}</el-descriptions-item>
        <el-descriptions-item label="实测面积">{{ selectedParcel.scmj || 0 }} 亩</el-descriptions-item>
        <el-descriptions-item label="地块类别">
          {{ dklbMap[selectedParcel.dklb] || selectedParcel.dklb || '-' }}
        </el-descriptions-item>
      </el-descriptions>

      <el-form-item label="移除原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          placeholder="说明本次移除地块的原因"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="danger"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="handleSubmit"
      >
        确认移除
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const batchId = ref(null);
const contractorUid = ref("");
const parcels = ref([]);

const dklbMap = { "01": "耕地", "02": "园地", "03": "林地", "04": "草地", "05": "养殖水面", "09": "其他" };

function defaultForm() {
  return {
    dkbm: "",
    reason: "",
  };
}
const form = reactive(defaultForm());

const selectedParcel = computed(() =>
  parcels.value.find((p) => p.dkbm === form.dkbm) || null
);

const canSubmit = computed(() => form.dkbm.trim());

function open(bid, cuid, parcelList) {
  batchId.value = bid;
  contractorUid.value = cuid;
  parcels.value = parcelList || [];
  Object.assign(form, defaultForm());
  visible.value = true;
}

function resetForm() {
  Object.assign(form, defaultForm());
}

function onParcelSelect() {
  // nothing needed on select
}

async function handleSubmit() {
  if (!canSubmit.value) {
    ElMessage.warning("请选择要移除的地块");
    return;
  }
  submitting.value = true;
  try {
    const payload = {
      dkbm: form.dkbm,
      reason: form.reason || undefined,
    };
    ElMessage.success("移除地块已加入待保存");
    visible.value = false;
    emit("done", { type: "remove_parcel", payload });
  } catch (e) {
    ElMessage.error(e?.message || "移除地块失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert { margin-bottom: 16px; }
.parcel-form { margin-top: 8px; }
.option-code { font-weight: 600; margin-right: 8px; }
.option-name { color: #606266; margin-right: 8px; }
.option-area { color: #909399; font-size: 12px; }
</style>
