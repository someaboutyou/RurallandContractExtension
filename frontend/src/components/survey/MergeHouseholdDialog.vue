<template>
  <el-dialog
    v-model="visible"
    title="合户"
    width="650px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="将当前户的全部成员和地块合并到目标户，当前户将被注销。此操作不可撤销。"
      type="warning"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-descriptions :column="2" border size="small" class="source-summary">
      <el-descriptions-item label="当前户名称">{{ sourceName }}</el-descriptions-item>
      <el-descriptions-item label="承包方编码">{{ sourceCode }}</el-descriptions-item>
      <el-descriptions-item label="成员数量">{{ members.length }} 人</el-descriptions-item>
      <el-descriptions-item label="地块数量">{{ parcels.length }} 块</el-descriptions-item>
    </el-descriptions>

    <el-form :model="form" label-position="top" class="merge-form">
      <el-form-item label="合并到目标户" required>
        <el-select
          v-model="form.targetContractorUid"
          filterable
          placeholder="请选择目标承包方"
          style="width: 100%"
          @change="handleTargetChange"
        >
          <el-option
            v-for="t in filteredTasks"
            :key="t.contractorUid"
            :label="`${t.cbfbm} - ${t.cbfmc}`"
            :value="t.contractorUid"
          />
        </el-select>
      </el-form-item>

      <el-form-item v-if="selectedTarget" label="合并预览">
        <div class="merge-preview">
          <div class="preview-row">
            <span class="preview-label">迁出方</span>
            <span class="preview-arrow">→</span>
            <span class="preview-label preview-label-target">目标方</span>
          </div>
          <div class="preview-row">
            <span class="preview-detail">{{ sourceName }}（{{ sourceCode }}）</span>
            <span class="preview-arrow">→</span>
            <span class="preview-detail preview-detail-target">{{ selectedTarget.cbfmc }}（{{ selectedTarget.cbfbm }}）</span>
          </div>
          <div class="preview-transfer">
            <el-tag size="small" type="warning">迁移 {{ members.length }} 人</el-tag>
            <el-tag size="small" type="warning">迁移 {{ parcels.length }} 块地</el-tag>
            <el-tag size="small" type="danger">注销当前户</el-tag>
          </div>
        </div>
      </el-form-item>

      <el-form-item label="合户原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          placeholder="说明本次合户的原因"
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
        确认合户
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { mergeSurveyHousehold } from "../../api/survey";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const batchId = ref(null);
const contractorUid = ref("");
const sourceName = ref("");
const sourceCode = ref("");
const members = ref([]);
const parcels = ref([]);
const tasks = ref([]);

const form = reactive({
  targetContractorUid: "",
  reason: "",
});

const filteredTasks = computed(() =>
  tasks.value.filter((t) => t.contractorUid !== contractorUid.value)
);

const selectedTarget = computed(() =>
  filteredTasks.value.find((t) => t.contractorUid === form.targetContractorUid) || null
);

const canSubmit = computed(() =>
  form.targetContractorUid && members.value.length > 0
);

function open(bid, cuid, name, code, memberList, parcelList, taskList) {
  batchId.value = bid;
  contractorUid.value = cuid;
  sourceName.value = name;
  sourceCode.value = code;
  members.value = memberList || [];
  parcels.value = parcelList || [];
  tasks.value = taskList || [];
  form.targetContractorUid = "";
  form.reason = "";
  visible.value = true;
}

function handleTargetChange() {
  // preview auto-updates via computed
}

function resetForm() {
  form.targetContractorUid = "";
  form.reason = "";
}

async function handleSubmit() {
  if (!canSubmit.value) {
    ElMessage.warning("请选择目标户");
    return;
  }
  const target = selectedTarget.value;
  try {
    await ElMessageBox.confirm(
      `确定将「${sourceName.value}」的全部 ${members.value.length} 名成员和 ${parcels.value.length} 块地块合并到「${target.cbfmc}」吗？当前户将被注销，且此操作不可撤销。`,
      "确认合户",
      { type: "warning", confirmButtonText: "确认合户", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  submitting.value = true;
  try {
    await mergeSurveyHousehold(batchId.value, contractorUid.value, {
      targetContractorUid: form.targetContractorUid,
      reason: form.reason || undefined,
    });
    ElMessage.success("合户完成");
    visible.value = false;
    emit("done");
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || "合户失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert { margin-bottom: 16px; }
.source-summary { margin-bottom: 16px; }
.merge-form { margin-top: 0; }

.merge-preview {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 12px 16px;
  width: 100%;
}
.preview-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.preview-label {
  font-size: 12px;
  color: #909399;
  flex: 1;
  text-align: center;
}
.preview-label-target {
  color: #409eff;
}
.preview-arrow {
  font-size: 18px;
  color: #c0c4cc;
  flex-shrink: 0;
}
.preview-detail {
  font-size: 13px;
  font-weight: 600;
  flex: 1;
  text-align: center;
}
.preview-detail-target {
  color: #409eff;
}
.preview-transfer {
  display: flex;
  gap: 8px;
  justify-content: center;
}
</style>
