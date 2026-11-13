<template>
  <el-dialog
    append-to-body
    v-model="visible"
    title="承包方地块划转"
    width="860px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="把本方地块单方划转给另一承包户。目标承包方仅限本组，划转后地块归对方名下，可在对方调查页面撤回。"
      type="info"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-form :model="form" label-position="top">
      <el-form-item label="划转至承包方" required>
        <el-select
          v-model="form.targetContractorUid"
          placeholder="请选择本组承包户"
          filterable
          :loading="loadingTargets"
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
        <div class="field-hint">
          候选为本批次内同一村组、可接收地块的承包方（{{ targetOptions.length }} 户），不受上方任务列表的搜索条件影响。
        </div>
      </el-form-item>
    </el-form>

    <div v-if="form.targetContractorUid" class="transfer-tables">
      <div class="transfer-panel">
        <div class="transfer-panel-header">
          <span class="transfer-panel-title">本方地块（勾选要划转的）</span>
          <span class="transfer-panel-sub">{{ exchangeableSourceParcels.length }} 个地块</span>
        </div>
        <el-table
          ref="sourceTable"
          :data="exchangeableSourceParcels"
          border
          size="small"
          max-height="260"
          @selection-change="handleSourceSelection"
        >
          <el-table-column type="selection" width="40" />
          <el-table-column prop="dkbm" label="地块编码" min-width="150" />
          <el-table-column prop="dkmc" label="地块名称" min-width="120" show-overflow-tooltip />
          <el-table-column prop="scmj" label="实测面积（㎡）" width="120" />
          <el-table-column prop="dklb" label="类别" width="70" />
        </el-table>
      </div>

      <div class="transfer-arrow">
        <span class="arrow-icon">➜</span>
        <span class="arrow-label">{{ selectedDkbms.length }} 块划转</span>
      </div>

      <div class="transfer-panel">
        <div class="transfer-panel-header">
          <span class="transfer-panel-title">对方现有地块</span>
          <span class="transfer-panel-sub">{{ activeTargetParcels.length }} 个地块</span>
        </div>
        <el-table
          :data="activeTargetParcels"
          v-loading="targetLoading"
          border
          size="small"
          max-height="260"
        >
          <el-table-column prop="dkbm" label="地块编码" min-width="150" />
          <el-table-column prop="dkmc" label="地块名称" min-width="120" show-overflow-tooltip />
          <el-table-column prop="scmj" label="实测面积（㎡）" width="120" />
          <el-table-column prop="dklb" label="类别" width="70" />
        </el-table>
      </div>
    </div>

    <el-divider />

    <el-descriptions v-if="selectedDkbms.length" :column="2" border size="small" class="transfer-summary">
      <el-descriptions-item label="划转地块">
        <el-tag v-for="d in selectedDkbms" :key="d" size="small" type="warning" style="margin: 2px">{{ d }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="合计面积">
        {{ formattedSelectedArea }}
      </el-descriptions-item>
    </el-descriptions>

    <el-form :model="form" label-position="top" style="margin-top: 12px">
      <el-form-item label="划转原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          placeholder="说明本次地块划转的原因"
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
        确认划转
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { fetchSurveyParcels, fetchMergeCandidates } from "../../api/survey";
import { fallbackSameGroupTasks, taskGroupCode } from "../../utils/surveyCandidates";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const batchId = ref(null);
const contractorUid = ref("");
const currentGroupRegionCode = ref("");
const loadingTargets = ref(false);

const targetOptions = ref([]);
const sourceParcels = ref([]);
const targetParcels = ref([]);
const selectedDkbms = ref([]);
const targetLoading = ref(false);

const form = reactive({
  targetContractorUid: "",
  reason: "",
});

const exchangeableSourceParcels = computed(() =>
  (sourceParcels.value || []).filter((item) => !["removed", "split_source"].includes(item.resultStatus)),
);

// 「对方现有地块」只统计现行有效的关联行：接口返回里包含基线有、现势无的
// 已换出/已划出/已移除地块（resultStatus=removed 的遗留行），直接展示会把
// 对方地块数虚增（例如互换后仍把换出的那块算给对方）。
const activeTargetParcels = computed(() =>
  (targetParcels.value || []).filter((item) => !["removed", "split_source"].includes(item.resultStatus)),
);

const selectedAreaTotal = computed(() =>
  exchangeableSourceParcels.value
    .filter((item) => selectedDkbms.value.includes(item.dkbm))
    .reduce((sum, item) => sum + (Number(item.scmj) || 0), 0),
);
const formattedSelectedArea = computed(() =>
  selectedAreaTotal.value ? `${selectedAreaTotal.value.toFixed(2)} ㎡` : "-",
);

const canSubmit = computed(() =>
  form.targetContractorUid &&
  selectedDkbms.value.length > 0
);

function sameGroup(task) {
  if (!currentGroupRegionCode.value) return true;
  return taskGroupCode(task) === currentGroupRegionCode.value;
}

async function open(bid, cuid, taskList, parcelList, currentContractor) {
  batchId.value = bid;
  contractorUid.value = cuid;
  sourceParcels.value = parcelList || [];
  currentGroupRegionCode.value = taskGroupCode(currentContractor);
  // 先用任务列表快照秒开，随后用后端候选接口刷新（列表可能带搜索/分页条件）。
  // 划转的接收方允许名下没有地块，所以候选池用 merge-candidates 口径
  // （swap-candidates 会把没地的户过滤掉）。
  targetOptions.value = (taskList || []).filter((t) => t.contractorUid !== cuid && sameGroup(t));
  resetForm();
  visible.value = true;
  await refreshTargetOptions(taskList || []);
}

async function refreshTargetOptions(fallbackTasks) {
  loadingTargets.value = true;
  try {
    const { data } = await fetchMergeCandidates(batchId.value, contractorUid.value);
    const list = (data.data || []).filter((t) => t.contractorUid !== contractorUid.value);
    targetOptions.value = list;
  } catch (e) {
    try {
      const rows = await fallbackSameGroupTasks(batchId.value, contractorUid.value);
      targetOptions.value = rows.filter((t) => t.contractorUid !== contractorUid.value);
    } catch {
      targetOptions.value = fallbackTasks.filter((t) => t.contractorUid !== contractorUid.value && sameGroup(t));
      ElMessage.warning("候选承包方加载失败，已回退为当前任务列表中的承包方");
    }
  } finally {
    loadingTargets.value = false;
  }
}

function resetForm() {
  form.targetContractorUid = "";
  form.reason = "";
  selectedDkbms.value = [];
  targetParcels.value = [];
}

function handleSourceSelection(rows) {
  selectedDkbms.value = rows.map((r) => r.dkbm);
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
    ElMessage.warning("请选择划转至的承包方并勾选要划转的地块");
    return;
  }
  submitting.value = true;
  try {
    const target = targetOptions.value.find((t) => t.contractorUid === form.targetContractorUid) || {};
    const payload = {
      targetContractorUid: form.targetContractorUid,
      targetCbfbm: target.cbfbm || "",
      targetCbfmc: target.cbfmc || "",
      dkbms: selectedDkbms.value,
      sourceParcels: exchangeableSourceParcels.value.filter((item) => selectedDkbms.value.includes(item.dkbm)),
      reason: form.reason || undefined,
    };
    ElMessage.success("地块划转已加入待保存");
    visible.value = false;
    emit("done", { type: "transfer_parcels", payload });
  } catch (e) {
    ElMessage.error(e?.message || "划转失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert { margin-bottom: 16px; }
.field-hint { margin-top: 6px; color: #909399; font-size: 12px; line-height: 1.5; }
.transfer-tables { display: flex; gap: 16px; align-items: flex-start; margin-top: 12px; }
.transfer-panel { flex: 1; min-width: 0; }
.transfer-panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.transfer-panel-title { font-weight: 600; font-size: 13px; }
.transfer-panel-sub { color: #909399; font-size: 12px; }
.transfer-arrow {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding-top: 40px; flex-shrink: 0;
}
.arrow-icon { font-size: 28px; color: #e6a23c; }
.arrow-label { font-size: 11px; color: #909399; }
.transfer-summary { margin-top: 8px; }
</style>
