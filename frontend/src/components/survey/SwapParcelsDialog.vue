<template>
  <el-dialog
    v-model="visible"
    title="承包方地块互换"
    width="860px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="选择目标承包方后，勾选双方要交换的地块，确认后交换归属。"
      type="info"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <!-- 选择目标承包方 -->
    <el-form :model="form" label-position="top">
      <el-form-item label="目标承包方" required>
        <el-select
          v-model="form.targetContractorUid"
          placeholder="请选择互换对象"
          filterable
          style="width: 100%"
          @change="onTargetChange"
        >
          <el-option
            v-for="t in targetOptions"
            :key="t.contractorUid"
            :label="`${t.cbfmc}（${t.cbfbm}）`"
            :value="t.contractorUid"
          />
        </el-select>
      </el-form-item>
    </el-form>

    <!-- 互换表格 -->
    <div v-if="form.targetContractorUid" class="swap-tables">
      <div class="swap-panel">
        <div class="swap-panel-header">
          <span class="swap-panel-title">本方地块</span>
          <span class="swap-panel-sub">{{ sourceParcels.length }} 个地块</span>
        </div>
        <el-table
          :data="sourceParcels"
          border
          size="small"
          max-height="260"
          @selection-change="handleSourceSelection"
          ref="sourceTable"
        >
          <el-table-column type="selection" width="40" />
          <el-table-column prop="dkbm" label="地块编码" min-width="150" />
          <el-table-column prop="dkmc" label="地块名称" min-width="120" show-overflow-tooltip />
          <el-table-column prop="scmj" label="实测面积（亩）" width="110" />
          <el-table-column prop="dklb" label="类别" width="70" />
        </el-table>
      </div>

      <div class="swap-arrow">
        <span class="arrow-icon">⇄</span>
        <span class="arrow-label">{{ swappedCount }} 对互换</span>
      </div>

      <div class="swap-panel">
        <div class="swap-panel-header">
          <span class="swap-panel-title">对方地块</span>
          <span class="swap-panel-sub">{{ targetParcels.length }} 个地块</span>
        </div>
        <el-table
          :data="targetParcels"
          border
          size="small"
          max-height="260"
          @selection-change="handleTargetSelection"
          ref="targetTable"
        >
          <el-table-column type="selection" width="40" />
          <el-table-column prop="dkbm" label="地块编码" min-width="150" />
          <el-table-column prop="dkmc" label="地块名称" min-width="120" show-overflow-tooltip />
          <el-table-column prop="scmj" label="实测面积（亩）" width="110" />
          <el-table-column prop="dklb" label="类别" width="70" />
        </el-table>
      </div>
    </div>

    <el-divider />

    <!-- 互换预览 -->
    <el-descriptions v-if="swappedCount" :column="2" border size="small" class="swap-summary">
      <el-descriptions-item label="本方换出">
        <el-tag v-for="d in selectedSource" :key="d" size="small" type="warning" style="margin: 2px">{{ d }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="本方换入">
        <el-tag v-for="d in selectedTarget" :key="d" size="small" type="success" style="margin: 2px">{{ d }}</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <!-- 原因 -->
    <el-form :model="form" label-position="top" style="margin-top: 12px">
      <el-form-item label="互换原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          placeholder="说明本次地块互换的原因"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="handleSubmit"
      >
        确认互换
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { fetchSurveyParcels, swapSurveyParcels } from "../../api/survey";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const batchId = ref(null);
const contractorUid = ref("");

const targetOptions = ref([]);
const sourceParcels = ref([]);
const targetParcels = ref([]);
const selectedSourceDkbms = ref([]);
const selectedTargetDkbms = ref([]);
const targetLoading = ref(false);
const sourceTable = ref(null);
const targetTable = ref(null);

const form = reactive({
  targetContractorUid: "",
  reason: "",
});

const selectedSource = computed(() => selectedSourceDkbms.value);
const selectedTarget = computed(() => selectedTargetDkbms.value);
const swappedCount = computed(() => Math.min(selectedSource.value.length, selectedTarget.value.length));

const canSubmit = computed(() =>
  form.targetContractorUid &&
  selectedSourceDkbms.value.length > 0 &&
  selectedTargetDkbms.value.length > 0
);

function open(bid, cuid, taskList, parcelList) {
  batchId.value = bid;
  contractorUid.value = cuid;
  sourceParcels.value = parcelList || [];
  targetOptions.value = (taskList || []).filter((t) => t.contractorUid !== cuid);
  form.targetContractorUid = "";
  form.reason = "";
  selectedSourceDkbms.value = [];
  selectedTargetDkbms.value = [];
  targetParcels.value = [];
  visible.value = true;
}

function resetForm() {
  form.targetContractorUid = "";
  form.reason = "";
  selectedSourceDkbms.value = [];
  selectedTargetDkbms.value = [];
  targetParcels.value = [];
}

function handleSourceSelection(rows) {
  selectedSourceDkbms.value = rows.map((r) => r.dkbm);
}

function handleTargetSelection(rows) {
  selectedTargetDkbms.value = rows.map((r) => r.dkbm);
}

async function onTargetChange(uid) {
  if (!uid) {
    targetParcels.value = [];
    return;
  }
  targetLoading.value = true;
  try {
    const { data } = await fetchSurveyParcels(batchId.value, uid);
    targetParcels.value = data.data || [];
  } catch {
    targetParcels.value = [];
  } finally {
    targetLoading.value = false;
  }
}

async function handleSubmit() {
  if (!canSubmit.value) {
    ElMessage.warning("请选择目标承包方并勾选双方地块");
    return;
  }
  submitting.value = true;
  try {
    await swapSurveyParcels(batchId.value, contractorUid.value, {
      targetContractorUid: form.targetContractorUid,
      sourceDkbms: selectedSourceDkbms.value,
      targetDkbms: selectedTargetDkbms.value,
      reason: form.reason || undefined,
    });
    ElMessage.success("地块互换完成");
    visible.value = false;
    emit("done");
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || "互换失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert { margin-bottom: 16px; }
.swap-tables { display: flex; gap: 16px; align-items: flex-start; margin-top: 12px; }
.swap-panel { flex: 1; min-width: 0; }
.swap-panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.swap-panel-title { font-weight: 600; font-size: 13px; }
.swap-panel-sub { color: #909399; font-size: 12px; }
.swap-arrow {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding-top: 40px; flex-shrink: 0;
}
.arrow-icon { font-size: 28px; color: #409eff; }
.arrow-label { font-size: 11px; color: #909399; }
.swap-summary { margin-top: 8px; }
</style>
