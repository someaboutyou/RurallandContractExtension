<template>
  <el-dialog
    v-model="visible"
    title="分户"
    width="900px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="填写新户信息，分配成员和地块。户主将留在原户，至少保留 1 名成员在原户。"
      type="info"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-form :model="form" label-position="top" class="split-form">
      <div class="form-row">
        <el-form-item label="新承包方编码" required class="form-half">
          <el-input v-model="form.newCbfbm" placeholder="18位编码" maxlength="18" />
        </el-form-item>
        <el-form-item label="新承包方名称" required class="form-half">
          <el-input v-model="form.newCbfmc" placeholder="例如：张三户（分户）" maxlength="50" />
        </el-form-item>
      </div>
    </el-form>

    <el-divider />

    <!-- 成员分配 -->
    <div class="assign-section">
      <div class="assign-header">
        <span class="assign-title">成员分配</span>
        <span class="assign-hint">原户 {{ stayMembers.length }} 人，新户 {{ moveMembers.length }} 人</span>
      </div>
      <div class="assign-panels member-panels">
        <div class="assign-panel">
          <div class="panel-label">原户保留</div>
          <el-table :data="stayMembers" border size="small" max-height="240" @row-click="moveMemberToNew">
            <el-table-column prop="name" label="姓名" min-width="80" />
            <el-table-column label="与户主关系" width="90">
              <template #default="{ row }">{{ relationLabel(row.relationToHead || row.yhzgx) }}</template>
            </el-table-column>
            <el-table-column label="户主" width="60">
              <template #default="{ row }">
                <el-tag v-if="row.isHouseholdHead" size="small" type="warning">户主</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="assign-actions">
          <el-button size="small" @click="moveAllMembersToNew">≫</el-button>
          <el-button size="small" @click="moveAllMembersToStay">≪</el-button>
        </div>

        <div class="assign-panel">
          <div class="panel-label panel-label-new">移至新户</div>
          <el-table :data="moveMembers" border size="small" max-height="240" @row-click="moveMemberToStay">
            <el-table-column prop="name" label="姓名" min-width="80" />
            <el-table-column label="与户主关系" width="90">
              <template #default="{ row }">{{ relationLabel(row.relationToHead || row.yhzgx) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>

    <el-divider />

    <!-- 地块分配 -->
    <div class="assign-section">
      <div class="assign-header">
        <span class="assign-title">地块分配</span>
        <span class="assign-hint">原户 {{ stayParcels.length }} 块，新户 {{ moveParcels.length }} 块</span>
      </div>
      <div class="assign-panels">
        <div class="assign-panel">
          <div class="panel-label">原户保留</div>
          <el-table :data="stayParcels" border size="small" max-height="200" @row-click="moveParcelToNew">
            <el-table-column prop="dkbm" label="地块编码" min-width="140" />
            <el-table-column prop="dkmc" label="地块名称" min-width="100" show-overflow-tooltip />
            <el-table-column prop="scmj" label="面积（亩）" width="90" />
          </el-table>
        </div>

        <div class="assign-actions">
          <el-button size="small" @click="moveAllParcelsToNew">≫</el-button>
          <el-button size="small" @click="moveAllParcelsToStay">≪</el-button>
        </div>

        <div class="assign-panel">
          <div class="panel-label panel-label-new">移至新户</div>
          <el-table :data="moveParcels" border size="small" max-height="200" @row-click="moveParcelToStay">
            <el-table-column prop="dkbm" label="地块编码" min-width="140" />
            <el-table-column prop="dkmc" label="地块名称" min-width="100" show-overflow-tooltip />
            <el-table-column prop="scmj" label="面积（亩）" width="90" />
          </el-table>
        </div>
      </div>
    </div>

    <el-divider />

    <el-form :model="form" label-position="top">
      <el-form-item label="分户原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          placeholder="说明本次分户的原因"
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
        确认分户
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { splitSurveyHousehold } from "../../api/survey";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const batchId = ref(null);
const contractorUid = ref("");

const allMembers = ref([]);
const allParcels = ref([]);
const memberUidsToMove = ref(new Set());
const parcelDkbmsToMove = ref(new Set());

const relationMap = {
  "01": "户主", "02": "配偶", "03": "子女", "04": "子女",
  "06": "父母", "08": "兄弟姐妹", "09": "其他",
};
function relationLabel(v) {
  return relationMap[v] || v || "-";
}

const form = reactive({
  newCbfbm: "",
  newCbfmc: "",
  reason: "",
});

const stayMembers = computed(() =>
  allMembers.value.filter((m) => !memberUidsToMove.value.has(m.memberUid))
);
const moveMembers = computed(() =>
  allMembers.value.filter((m) => memberUidsToMove.value.has(m.memberUid))
);
const stayParcels = computed(() =>
  allParcels.value.filter((p) => !parcelDkbmsToMove.value.has(p.dkbm))
);
const moveParcels = computed(() =>
  allParcels.value.filter((p) => parcelDkbmsToMove.value.has(p.dkbm))
);

const canSubmit = computed(() =>
  form.newCbfbm.trim() &&
  form.newCbfmc.trim() &&
  memberUidsToMove.value.size > 0 &&
  stayMembers.value.length > 0
);

function open(bid, cuid, members, parcels) {
  batchId.value = bid;
  contractorUid.value = cuid;
  allMembers.value = members || [];
  allParcels.value = parcels || [];
  memberUidsToMove.value = new Set();
  parcelDkbmsToMove.value = new Set();

  // 默认建议：户主留在原户，其余均分
  const head = allMembers.value.find((m) => m.isHouseholdHead);
  const others = allMembers.value.filter((m) => m !== head);
  const half = Math.ceil(others.length / 2);
  for (let i = 0; i < half; i++) {
    if (others[i]) memberUidsToMove.value.add(others[i].memberUid);
  }

  // 地块默认均分
  const parcelHalf = Math.ceil(allParcels.value.length / 2);
  for (let i = 0; i < parcelHalf; i++) {
    if (allParcels.value[i]) parcelDkbmsToMove.value.add(allParcels.value[i].dkbm);
  }

  form.newCbfbm = "";
  form.newCbfmc = "";
  form.reason = "";
  visible.value = true;
}

function resetForm() {
  memberUidsToMove.value = new Set();
  parcelDkbmsToMove.value = new Set();
}

function moveMemberToNew(row) {
  memberUidsToMove.value.add(row.memberUid);
  memberUidsToMove.value = new Set(memberUidsToMove.value);
}
function moveMemberToStay(row) {
  memberUidsToMove.value.delete(row.memberUid);
  memberUidsToMove.value = new Set(memberUidsToMove.value);
}
function moveAllMembersToNew() {
  for (const m of allMembers.value) memberUidsToMove.value.add(m.memberUid);
  memberUidsToMove.value = new Set(memberUidsToMove.value);
}
function moveAllMembersToStay() {
  memberUidsToMove.value = new Set();
}

function moveParcelToNew(row) {
  parcelDkbmsToMove.value.add(row.dkbm);
  parcelDkbmsToMove.value = new Set(parcelDkbmsToMove.value);
}
function moveParcelToStay(row) {
  parcelDkbmsToMove.value.delete(row.dkbm);
  parcelDkbmsToMove.value = new Set(parcelDkbmsToMove.value);
}
function moveAllParcelsToNew() {
  for (const p of allParcels.value) parcelDkbmsToMove.value.add(p.dkbm);
  parcelDkbmsToMove.value = new Set(parcelDkbmsToMove.value);
}
function moveAllParcelsToStay() {
  parcelDkbmsToMove.value = new Set();
}

async function handleSubmit() {
  if (!canSubmit.value) {
    ElMessage.warning("请填写新户信息，至少移入 1 名成员且原户保留至少 1 名成员");
    return;
  }
  submitting.value = true;
  try {
    await splitSurveyHousehold(batchId.value, contractorUid.value, {
      newCbfbm: form.newCbfbm.trim(),
      newCbfmc: form.newCbfmc.trim(),
      memberUids: [...memberUidsToMove.value],
      parcelDkbms: [...parcelDkbmsToMove.value],
      reason: form.reason || undefined,
    });
    ElMessage.success("分户完成");
    visible.value = false;
    emit("done");
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || "分户失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert { margin-bottom: 16px; }
.split-form { margin-bottom: 0; }
.form-row { display: flex; gap: 12px; }
.form-half { flex: 1; min-width: 0; }

.assign-section { margin: 12px 0; }
.assign-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.assign-title { font-weight: 600; font-size: 14px; }
.assign-hint { color: #909399; font-size: 12px; }

.assign-panels { display: flex; gap: 10px; align-items: flex-start; }
.member-panels .assign-panel { flex: 1; min-width: 0; }
.assign-panel { flex: 1; min-width: 0; }
.panel-label { font-size: 12px; font-weight: 500; color: #606266; margin-bottom: 4px; }
.panel-label-new { color: #409eff; }
.assign-actions {
  display: flex; flex-direction: column; gap: 4px; padding-top: 20px; flex-shrink: 0;
}
</style>
