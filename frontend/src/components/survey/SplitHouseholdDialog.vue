<template>
  <el-dialog v-model="visible" title="分户" width="960px" destroy-on-close>
    <el-alert title="原承包户将注销，所有成员和有效地块必须分配到至少两个新承包户。" type="warning" :closable="false" show-icon />
    <div class="actions"><el-button type="primary" plain @click="addHousehold">新增承包户</el-button></div>
    <el-card v-for="(household, index) in households" :key="household.key" class="household-card" shadow="never">
      <template #header>
        <div class="card-header"><strong>新承包户 {{ index + 1 }}</strong><el-button v-if="households.length > 2" link type="danger" @click="removeHousehold(index)">删除</el-button></div>
      </template>
      <div class="grid">
        <el-form-item label="承包方编码（自动生成）" required><el-input v-model="household.newCbfbm" readonly /></el-form-item>
        <el-form-item label="承包方名称" required><el-input v-model="household.newCbfmc" maxlength="50" /></el-form-item>
        <el-form-item label="家庭成员" required>
          <el-select v-model="household.memberUids" multiple filterable style="width:100%" @change="handleAssignmentChange('memberUids', index)">
            <el-option v-for="item in allMembers" :key="item.memberUid" :label="item.name || item.cyxm" :value="item.memberUid" />
          </el-select>
        </el-form-item>
        <el-form-item label="承包地块" required>
          <el-select v-model="household.parcelDkbms" multiple filterable style="width:100%" @change="handleAssignmentChange('parcelDkbms', index)">
            <el-option v-for="item in allParcels" :key="item.dkbm" :label="`${item.dkbm}${item.dkmc ? ` - ${item.dkmc}` : ''}`" :value="item.dkbm" />
          </el-select>
        </el-form-item>
        <el-form-item label="户主" required>
          <el-select v-model="household.householdHeadMemberUid" style="width:100%" placeholder="请选择本户户主" @change="handleHeadChange(household)">
            <el-option v-for="item in membersFor(household)" :key="item.memberUid" :label="item.name || item.cyxm" :value="item.memberUid" />
          </el-select>
          <div class="head-hint">当前户主：{{ householdHeadName(household) || "尚未指定" }}</div>
        </el-form-item>
      </div>
    </el-card>
    <el-form-item label="分户原因" required><el-input v-model="reason" type="textarea" :rows="2" maxlength="500" show-word-limit /></el-form-item>
    <el-alert v-if="assignmentError" :title="assignmentError" type="error" :closable="false" show-icon />
    <template #footer><el-button @click="visible=false">取消</el-button><el-button type="primary" :disabled="Boolean(assignmentError)" @click="submit">加入待保存</el-button></template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { fetchContractorCodes } from "../../api/survey";
import { collectContractorCodes, fetchAllBatchTasks } from "../../utils/surveyCandidates";

const emit = defineEmits(["done"]);
const visible = ref(false);
const allMembers = ref([]);
const allParcels = ref([]);
const households = ref([]);
const reason = ref("");
let keySeed = 0;
const existingCodes = ref(new Set());
const codePrefix = ref("");
const assignmentSnapshots = new Map();
const emptyHousehold = () => ({ key: ++keySeed, newCbfbm: generateCode(), newCbfmc: "", memberUids: [], parcelDkbms: [], householdHeadMemberUid: "" });

const assignmentError = computed(() => {
  if (households.value.length < 2) return "至少需要两个新承包户";
  if (!reason.value.trim()) return "请填写分户原因";
  if (households.value.some(h => !h.newCbfbm.trim() || !h.newCbfmc.trim() || !h.memberUids.length || !h.parcelDkbms.length)) return "请完整填写每个新户，并至少分配一名成员和一块地";
  if (households.value.some(h => !h.householdHeadMemberUid || !h.memberUids.includes(h.householdHeadMemberUid))) return "请为每个新承包户指定户主";
  const codes = households.value.map(h => h.newCbfbm.trim());
  if (new Set(codes).size !== codes.length) return "新承包方编码不能重复";
  const members = households.value.flatMap(h => h.memberUids);
  if (members.length !== allMembers.value.length || new Set(members).size !== allMembers.value.length) return "所有成员必须且只能分配一次";
  const parcels = households.value.flatMap(h => h.parcelDkbms);
  if (parcels.length !== allParcels.value.length || new Set(parcels).size !== allParcels.value.length) return "所有有效地块必须且只能分配一次";
  return "";
});

async function open(batchId, _contractorUid, members, parcels, sourceCode, tasks) {
  allMembers.value = members || [];
  allParcels.value = (parcels || []).filter(item => !["removed", "split_source"].includes(item.resultStatus));
  const digits = String(sourceCode || "").replace(/\D/g, "");
  codePrefix.value = digits.slice(0, Math.min(14, digits.length));
  existingCodes.value = new Set(collectContractorCodes(tasks));
  households.value = [emptyHousehold(), emptyHousehold()];
  allMembers.value.forEach((m, i) => households.value[i % 2].memberUids.push(m.memberUid));
  allParcels.value.forEach((p, i) => households.value[i % 2].parcelDkbms.push(p.dkbm));
  households.value.forEach(item => {
    item.householdHeadMemberUid = item.memberUids[0] || "";
    applyDefaultContractorName(item);
    saveSnapshot(item);
  });
  reason.value = "";
  visible.value = true;
  await refreshExistingCodes(batchId);
}
async function refreshExistingCodes(batchId) {
  if (!batchId || !codePrefix.value) return;
  let codes = [];
  try {
    const { data } = await fetchContractorCodes(batchId, { prefix: codePrefix.value });
    codes = collectContractorCodes(data.data);
  } catch {
    try {
      codes = collectContractorCodes(await fetchAllBatchTasks(batchId));
    } catch {
      ElMessage.warning("已用承包方编码加载失败，若批次超过 100 户，请核对自动生成的新编码是否重复");
      return;
    }
  }
  if (!codes.length) return;
  existingCodes.value = new Set(codes);
  // 新编码是只读自动生成的，拿到全量编码后重算一遍，避免与任务列表外的户撞号。
  households.value.forEach(item => { item.newCbfbm = ""; });
  households.value.forEach(item => { item.newCbfbm = generateCode(); });
}
function generateCode() {
  const prefix = codePrefix.value;
  if (!prefix) return "";
  const suffixLength = 18 - prefix.length;
  const used = [...existingCodes.value, ...households.value.map(item => item.newCbfbm)].filter(code => code.startsWith(prefix) && code.length === 18);
  const next = Math.max(0, ...used.map(code => Number(code.slice(prefix.length))).filter(Number.isFinite)) + 1;
  const code = `${prefix}${String(next).padStart(suffixLength, "0")}`.slice(0, 18);
  existingCodes.value.add(code);
  return code;
}
function membersFor(household) { const ids = new Set(household.memberUids); return allMembers.value.filter(item => ids.has(item.memberUid)); }
function householdHeadName(household) { const item = allMembers.value.find(member => member.memberUid === household.householdHeadMemberUid); return item?.name || item?.cyxm || ""; }
function applyDefaultContractorName(household) {
  const name = householdHeadName(household);
  if (name) household.newCbfmc = name;
}
function handleHeadChange(household) { applyDefaultContractorName(household); }
function saveSnapshot(item) { assignmentSnapshots.set(item.key, { memberUids: [...item.memberUids], parcelDkbms: [...item.parcelDkbms] }); }
function addHousehold() {
  if (allMembers.value.length <= households.value.length) {
    ElMessage.warning("没有可继续分配的家庭成员，无法新增承包户");
    return;
  }
  if (allParcels.value.length <= households.value.length) {
    ElMessage.warning("没有可继续分配的有效地块，无法新增承包户");
    return;
  }
  const household = emptyHousehold();
  households.value.push(household);
  saveSnapshot(household);
}
function removeHousehold(index) { households.value.splice(index, 1); }
function handleAssignmentChange(field, currentIndex) {
  const current = households.value[currentIndex];
  if (!current[field].length) {
    const label = field === "memberUids" ? "家庭成员" : "地块";
    ElMessage.warning(`${label}不能为空，本次调整已取消`);
    current[field] = [...(assignmentSnapshots.get(current.key)?.[field] || [])];
    return;
  }
  const selected = new Set(households.value[currentIndex][field]);
  households.value.forEach((item, index) => { if (index !== currentIndex) item[field] = item[field].filter(value => !selected.has(value)); });
  const emptyOther = households.value.find((item, index) => index !== currentIndex && !item[field].length);
  if (emptyOther) {
    const label = field === "memberUids" ? "家庭成员" : "地块";
    ElMessage.warning(`调整后其他新承包户的${label}将为空，本次调整已取消`);
    households.value.forEach(item => { const snapshot = assignmentSnapshots.get(item.key); if (snapshot) item[field] = [...snapshot[field]]; });
    return;
  }
  if (field === "memberUids") households.value.forEach(item => {
    if (!item.memberUids.includes(item.householdHeadMemberUid)) {
      item.householdHeadMemberUid = item.memberUids[0] || "";
      applyDefaultContractorName(item);
    }
  });
  households.value.forEach(saveSnapshot);
}
function submit() {
  if (assignmentError.value) { ElMessage.warning(assignmentError.value); return; }
  emit("done", { type: "split_household", payload: { newHouseholds: households.value.map(({ newCbfbm, newCbfmc, memberUids, parcelDkbms, householdHeadMemberUid }) => ({ newCbfbm: newCbfbm.trim(), newCbfmc: newCbfmc.trim(), memberUids, parcelDkbms, householdHeadMemberUid })), reason: reason.value.trim() } });
  visible.value = false;
  ElMessage.success("分户已加入待保存");
}
defineExpose({ open });
</script>

<style scoped>
.actions { margin: 14px 0; text-align: right; }
.household-card { margin-bottom: 14px; }
.card-header { display:flex; align-items:center; justify-content:space-between; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:0 16px; }
.head-hint { margin-top:6px; color:#b88230; font-size:12px; }
@media (max-width: 720px) { .grid { grid-template-columns:1fr; } }
</style>
