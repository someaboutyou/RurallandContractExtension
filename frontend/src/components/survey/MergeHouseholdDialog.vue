<template>
  <el-dialog v-model="visible" title="合户" width="720px" destroy-on-close>
    <el-alert title="选择两个或多个原承包方，系统将注销全部原户并创建一个全新的承包方。" type="warning" :closable="false" show-icon />
    <el-form label-position="top" class="form">
      <el-form-item label="参与合户的原承包方" required>
        <el-select v-model="form.sourceContractorUids" multiple filterable :loading="loadingCandidates" style="width:100%" @change="loadSelectedMembers">
          <el-option v-for="t in availableTasks" :key="t.contractorUid" :label="optionLabel(t)" :value="t.contractorUid" :disabled="t.contractorUid === currentUid" />
        </el-select>
        <div class="hint">当前户已固定参与，请再选择至少一个原承包方。候选为该批次内同一村组可合户的承包方（{{ availableTasks.length }} 户），不受上方任务列表的搜索条件影响。</div>
      </el-form-item>
      <el-divider content-position="left">新承包方信息</el-divider>
      <div class="grid">
        <el-form-item label="新承包方编码（自动生成）" required><el-input v-model="form.newCbfbm" readonly /></el-form-item>
        <el-form-item label="新户户主" required>
          <el-select v-model="form.householdHeadMemberUid" filterable style="width:100%" @change="applyHead">
            <el-option v-for="m in mergedMembers" :key="memberUid(m)" :label="`${m.name || m.cyxm}（${m.idNo || m.cyzjhm || '-'}）`" :value="memberUid(m)" />
          </el-select>
        </el-form-item>
        <el-form-item label="新承包方名称" required><el-input v-model="form.newCbfmc" maxlength="50" /></el-form-item>
        <el-form-item label="新承包方地址" required><el-input v-model="form.newAddress" maxlength="100" /></el-form-item>
      </div>
      <el-form-item label="合户原因"><el-input v-model="form.reason" type="textarea" :rows="2" maxlength="500" show-word-limit /></el-form-item>
      <el-alert v-if="loading" title="正在加载参与户成员……" type="info" :closable="false" />
      <div v-else class="summary">共 {{ form.sourceContractorUids.length }} 个原户、{{ mergedMembers.length }} 名成员。保存后全部原户注销，新户独立生成。</div>
    </el-form>
    <template #footer>
      <el-button @click="visible=false">取消</el-button>
      <el-button type="primary" :disabled="!canSubmit" @click="submit">确认合户</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { fetchContractorCodes, fetchMergeCandidates, fetchSurveyResult } from "../../api/survey";
import { collectContractorCodes, fallbackSameGroupTasks, fetchAllBatchTasks } from "../../utils/surveyCandidates";

const emit = defineEmits(["done"]);
const visible = ref(false);
const loading = ref(false);
const loadingCandidates = ref(false);
const batchId = ref(null);
const currentUid = ref("");
const tasks = ref([]);
const candidates = ref([]);
const mergedMembers = ref([]);
const resultCache = new Map();
const existingCodes = ref(new Set());
const codePrefix = ref("");
const form = reactive({ sourceContractorUids: [], newCbfbm: "", newCbfmc: "", householdHeadMemberUid: "", newAddress: "", reason: "" });
const taskStatusText = { not_started: "未调查", not_surveyed: "未调查", in_progress: "调查中", surveyed: "已调查", changed: "有变化", unchanged: "无变化", confirmed: "已确认", skipped: "已跳过", deregistered: "已注销" };
const availableTasks = computed(() => {
  const rows = candidates.value.filter(t => !["deregistered", "finished", "confirmed"].includes(t.taskStatus));
  const current = candidates.value.find(t => t.contractorUid === currentUid.value);
  return current && !rows.some(t => t.contractorUid === currentUid.value) ? [current, ...rows] : rows;
});
function optionLabel(t) {
  const status = taskStatusText[t.taskStatus];
  return `${t.cbfbm} - ${t.cbfmc}${status && status !== "未调查" ? `（${status}）` : ""}`;
}
const canSubmit = computed(() => form.sourceContractorUids.length >= 2 && /^\d{18}$/.test(form.newCbfbm) && form.newCbfmc.trim() && form.newAddress.trim() && form.householdHeadMemberUid && !loading.value);

async function getResult(uid) {
  if (!resultCache.has(uid)) {
    const { data } = await fetchSurveyResult(batchId.value, uid);
    resultCache.set(uid, data.data || {});
  }
  return resultCache.get(uid);
}
async function loadSelectedMembers() {
  if (!form.sourceContractorUids.includes(currentUid.value)) form.sourceContractorUids.unshift(currentUid.value);
  loading.value = true;
  try {
    const results = await Promise.all(form.sourceContractorUids.map(getResult));
    mergedMembers.value = results.flatMap(r => r.familyMembers || []);
    if (!mergedMembers.value.some(m => memberUid(m) === form.householdHeadMemberUid)) form.householdHeadMemberUid = "";
  } catch (e) { ElMessage.error(e.response?.data?.detail || "加载参与户成员失败"); }
  finally { loading.value = false; }
}
function applyHead(uid) {
  const head = mergedMembers.value.find(m => memberUid(m) === uid);
  if (head) form.newCbfmc = head.name || head.cyxm || form.newCbfmc;
}
function memberUid(member) { return member?.memberUid || member?.member_uid || ""; }
function generateCode() {
  const prefix = codePrefix.value;
  if (!prefix) return "";
  const suffixLength = 18 - prefix.length;
  const used = [...existingCodes.value].filter(code => code.startsWith(prefix) && code.length === 18);
  const next = Math.max(0, ...used.map(code => Number(code.slice(prefix.length))).filter(Number.isFinite)) + 1;
  return `${prefix}${String(next).padStart(suffixLength, "0")}`.slice(0, 18);
}
function fallbackCandidates(name, code, includeTaskList = false) {
  const rows = includeTaskList ? (tasks.value || []) : [];
  const current = rows.find(t => t.contractorUid === currentUid.value)
    || { contractorUid: currentUid.value, cbfbm: code || "", cbfmc: name || "", taskStatus: "unknown" };
  return [current, ...rows.filter(t => t.contractorUid !== currentUid.value)];
}
async function refreshExistingCodes() {
  existingCodes.value = new Set(collectContractorCodes(candidates.value));
  if (!batchId.value || !codePrefix.value) return;
  let codes = [];
  try {
    const { data } = await fetchContractorCodes(batchId.value, { prefix: codePrefix.value });
    codes = collectContractorCodes(data.data);
  } catch {
    try {
      codes = collectContractorCodes(await fetchAllBatchTasks(batchId.value));
    } catch {
      return;
    }
  }
  if (codes.length) existingCodes.value = new Set(codes);
}
async function loadCandidates(name, code) {
  loadingCandidates.value = true;
  try {
    const { data } = await fetchMergeCandidates(batchId.value, currentUid.value);
    const list = data.data || [];
    candidates.value = list.length ? list : fallbackCandidates(name, code);
  } catch (e) {
    try {
      const rows = await fallbackSameGroupTasks(batchId.value, currentUid.value);
      candidates.value = rows.length ? rows : fallbackCandidates(name, code, true);
    } catch (inner) {
      candidates.value = fallbackCandidates(name, code, true);
      ElMessage.warning("候选承包方加载失败，已回退为当前列表数据");
    }
  } finally {
    loadingCandidates.value = false;
    await refreshExistingCodes();
    form.newCbfbm = generateCode();
  }
}
async function open(bid, cuid, name, code, members, parcels, taskList, address = "") {
  batchId.value = bid; currentUid.value = cuid; tasks.value = taskList || [];
  resultCache.clear(); resultCache.set(cuid, { familyMembers: members || [] });
  const digits = String(code || "").replace(/\D/g, "");
  codePrefix.value = digits.slice(0, Math.min(14, digits.length));
  candidates.value = fallbackCandidates(name, code, true);
  existingCodes.value = new Set(collectContractorCodes(tasks.value));
  // 户主判定与后端同源：优先显式标记 → 户主(02) → 本人(01) → 兜底第一条。
  // ⛔ 旧实现按 relationToHead === "01" 找，而字典与真实数据里户主是 "02"，
  // 导致默认户主恒落空、退化成"随便挑第一个成员"（2026-09-25 修）。
  const currentHead = (members || []).find(item => item.isHouseholdHead)
    || (members || []).find(item => item.relationToHead === "02" || item.yhzgx === "02")
    || (members || []).find(item => item.relationToHead === "01" || item.yhzgx === "01")
    || (members || [])[0];
  Object.assign(form, { sourceContractorUids: [cuid], newCbfbm: generateCode(), newCbfmc: currentHead?.name || currentHead?.cyxm || name || "", householdHeadMemberUid: memberUid(currentHead), newAddress: address || "", reason: "" });
  mergedMembers.value = members || []; visible.value = true;
  await loadCandidates(name, code);
}
async function submit() {
  if (!canSubmit.value) { ElMessage.warning("请完整填写合户和新承包方信息"); return; }
  try {
    await ElMessageBox.confirm(`确定注销所选 ${form.sourceContractorUids.length} 个原承包方，并创建新承包方“${form.newCbfmc}”吗？`, "确认合户", { type: "warning" });
  } catch { return; }
  emit("done", { type: "merge_household", payload: {
    sourceContractorUids: [...form.sourceContractorUids], newCbfbm: form.newCbfbm,
    newCbfmc: form.newCbfmc.trim(), householdHeadMemberUid: form.householdHeadMemberUid,
    newAddress: form.newAddress.trim(), reason: form.reason.trim() || undefined,
  }});
  visible.value = false; ElMessage.success("合户已加入待保存");
}
defineExpose({ open });
</script>

<style scoped>
.form { margin-top:16px }.grid{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}.hint{font-size:12px;color:#909399;margin-top:6px}.summary{padding:10px 12px;background:#f5f7fa;border-radius:4px;color:#606266}@media(max-width:720px){.grid{grid-template-columns:1fr}}
</style>
