<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    title="家庭关系处理"
    width="920px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      class="relation-tip"
      type="info"
      :closable="false"
      show-icon
      :title="`处理范围：当前调查批次「${batch?.batchName || batch?.batchNo || ''}」全部承包方`"
    />

    <el-tabs v-model="activeTab">
      <el-tab-pane label="家庭关系检查" name="check">
        <div class="check-toolbar">
          <el-button type="primary" :loading="checking" @click="runCheck">开始检查</el-button>
          <template v-if="report">
            <el-tag type="primary">承包方 {{ report.contractorCount || 0 }} 户</el-tag>
            <el-tag type="info">家庭成员 {{ report.memberCount || 0 }} 人</el-tag>
            <el-tag :type="report.issueCount ? 'danger' : 'success'">
              问题 {{ report.issueCount || 0 }} 条
            </el-tag>
          </template>
        </div>

        <el-alert
          v-if="report && !report.issueCount"
          type="success"
          :closable="false"
          show-icon
          title="家庭关系检查通过，未发现问题。"
        />

        <el-table
          v-if="report && report.issueCount"
          :data="report.issues"
          border
          stripe
          size="small"
          max-height="420"
        >
          <el-table-column prop="contractorCode" label="承包方编码" width="165" show-overflow-tooltip />
          <el-table-column prop="contractorName" label="承包方姓名" width="110" show-overflow-tooltip />
          <el-table-column prop="memberName" label="成员姓名" width="100" show-overflow-tooltip />
          <el-table-column prop="memberIdNo" label="证件号码" width="180" show-overflow-tooltip />
          <el-table-column prop="relation" label="家庭关系" width="100" show-overflow-tooltip />
          <el-table-column label="问题类型" width="100">
            <template #default="{ row }">
              <el-tag :type="issueTagType(row.type)" size="small">{{ issueTypeLabel(row.type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="问题说明" min-width="260" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="家庭关系替换" name="replace">
        <el-alert
          class="relation-tip"
          type="warning"
          :closable="false"
          show-icon
          title="将当前批次内所有「查找内容」家庭关系批量替换为「替换内容」，请确认后再执行。"
        />
        <el-form label-width="100px" class="replace-form">
          <el-form-item label="查找内容">
            <el-select v-model="fromRelation" clearable placeholder="请选择要替换的家庭关系" style="width: 320px">
              <el-option v-for="item in relationOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="替换内容">
            <el-select v-model="toRelation" clearable placeholder="请选择替换后的家庭关系" style="width: 320px">
              <el-option v-for="item in relationOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              :loading="replacing"
              :disabled="!fromRelation || !toRelation || batch?.status !== 'active'"
              @click="handleReplace"
            >
              执行替换
            </el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="家庭成员修复" name="repair">
        <el-alert
          class="relation-tip"
          type="warning"
          :closable="false"
          show-icon
          title="修复家庭成员与承包方的关联关系（承包方 uid / 承包方编码），不会修改成员姓名、证件、家庭关系等业务信息。"
        />
        <div class="check-toolbar">
          <el-button type="primary" :loading="repairing" @click="handleRepair">开始修复</el-button>
          <template v-if="repairResult">
            <el-tag type="info">扫描成员 {{ repairResult.scannedMembers || 0 }} 人</el-tag>
            <el-tag :type="repairResult.repairedMembers ? 'success' : 'info'">
              修复成员 {{ repairResult.repairedMembers || 0 }} 人
            </el-tag>
            <el-tag type="warning">涉及承包方 {{ repairResult.repairedContractors || 0 }} 户</el-tag>
          </template>
        </div>
        <el-alert
          v-if="repairResult && !repairResult.repairedMembers"
          type="success"
          :closable="false"
          show-icon
          title="家庭成员关联数据正常，无需修复。"
        />
        <el-table
          v-if="repairResult && repairResult.samples?.length"
          :data="repairResult.samples"
          border
          stripe
          size="small"
          max-height="380"
        >
          <el-table-column prop="memberName" label="成员姓名" width="120" show-overflow-tooltip />
          <el-table-column prop="oldCbfbm" label="原承包方编码" width="170" show-overflow-tooltip />
          <el-table-column prop="newCbfbm" label="新承包方编码" width="170" show-overflow-tooltip />
          <el-table-column prop="oldContractorUid" label="原承包方 UID" min-width="220" show-overflow-tooltip />
          <el-table-column prop="newContractorUid" label="新承包方 UID" min-width="220" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { checkContractorRelations, repairContractorMembers, replaceContractorRelations } from "../../api/survey";
import { useDictionary } from "../../composables/useDictionary";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  batch: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue", "replaced"]);

const { options: relationOptions } = useDictionary("nyt2539_c20_relation_to_head");

const activeTab = ref("check");
const checking = ref(false);
const replacing = ref(false);
const repairing = ref(false);
const report = ref(null);
const repairResult = ref(null);
const fromRelation = ref("");
const toRelation = ref("");

const issueLabels = {
  self_relation: "本人关系",
  multiple_head: "多个户主",
  empty: "关系为空",
  invalid: "关系无效",
  age: "年龄不符",
};

function issueTypeLabel(type) {
  return issueLabels[type] || type;
}

function issueTagType(type) {
  return type === "age" ? "warning" : "danger";
}

async function runCheck() {
  if (!props.batch?.id) return;
  checking.value = true;
  try {
    const { data } = await checkContractorRelations(props.batch.id);
    report.value = data.data;
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "家庭关系检查失败");
  } finally {
    checking.value = false;
  }
}

async function handleReplace() {
  if (!props.batch?.id || !fromRelation.value || !toRelation.value) return;
  const fromLabel = relationOptions.value.find((item) => item.value === fromRelation.value)?.label || fromRelation.value;
  const toLabel = relationOptions.value.find((item) => item.value === toRelation.value)?.label || toRelation.value;
  try {
    await ElMessageBox.confirm(
      `确定将当前批次内家庭关系为「${fromLabel}」的成员全部改为「${toLabel}」吗？`,
      "家庭关系替换",
      { type: "warning", confirmButtonText: "执行替换", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  replacing.value = true;
  try {
    const { data } = await replaceContractorRelations(props.batch.id, {
      fromRelation: fromRelation.value,
      toRelation: toRelation.value,
    });
    const result = data.data || {};
    ElMessage.success(
      `替换完成：${result.updatedMembers || 0} 名成员，涉及 ${result.updatedContractors || 0} 户`,
    );
    emit("replaced");
    activeTab.value = "check";
    await runCheck();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "家庭关系替换失败");
  } finally {
    replacing.value = false;
  }
}

async function handleRepair() {
  if (!props.batch?.id) return;
  try {
    await ElMessageBox.confirm(
      "确定修复当前批次内家庭成员与承包方的关联关系吗？该操作只修正承包方 uid 和承包方编码，不修改成员业务数据。",
      "家庭成员修复",
      { type: "warning", confirmButtonText: "开始修复", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  repairing.value = true;
  try {
    const { data } = await repairContractorMembers(props.batch.id);
    repairResult.value = data.data;
    ElMessage.success(
      `修复完成：扫描 ${repairResult.value.scannedMembers || 0} 人，修复 ${repairResult.value.repairedMembers || 0} 人`,
    );
    emit("repaired");
    await runCheck();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "家庭成员修复失败");
  } finally {
    repairing.value = false;
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return;
    activeTab.value = "check";
    report.value = null;
    repairResult.value = null;
    fromRelation.value = "";
    toRelation.value = "";
    runCheck();
  },
);
</script>

<style scoped>
.relation-tip {
  margin-bottom: 12px;
}

.check-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.replace-form {
  margin-top: 18px;
}
</style>
