<template>
  <el-dialog
    v-model="visible"
    title="家庭成员维护"
    width="820px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="可批量新增、编辑、删除家庭成员。所有修改仅影响当前调查结果，base 快照保持不变。"
      type="info"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-tabs v-model="activeTab">
      <!-- 新增 -->
      <el-tab-pane label="新增成员" name="add">
        <el-table :data="form.membersToAdd" border size="small">
          <el-table-column prop="name" label="姓名" min-width="100">
            <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
          </el-table-column>
          <el-table-column prop="gender" label="性别" width="80">
            <template #default="{ row }">
              <el-select v-model="row.gender" size="small">
                <el-option label="男" value="1" />
                <el-option label="女" value="2" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="idNo" label="证件号码" min-width="160">
            <template #default="{ row }"><el-input v-model="row.idNo" size="small" /></template>
          </el-table-column>
          <el-table-column prop="relationToHead" label="关系" width="90">
            <template #default="{ row }">
              <el-select v-model="row.relationToHead" size="small">
                <el-option label="本人" value="01" />
                <el-option label="配偶" value="02" />
                <el-option label="子女" value="03" />
                <el-option label="父母" value="06" />
                <el-option label="兄弟姐妹" value="08" />
                <el-option label="其他" value="09" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="isCoOwner" label="共有人" width="80">
            <template #default="{ row }">
              <el-select v-model="row.isCoOwner" size="small">
                <el-option label="是" value="1" />
                <el-option label="否" value="0" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="isHouseholdHead" label="户主" width="70">
            <template #default="{ row }">
              <el-checkbox v-model="row.isHouseholdHead" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="form.membersToAdd.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
          <el-table-column prop="changeReason" label="新增原因" width="110">
            <template #default="{ row }">
              <el-select v-model="row.changeReason" size="small">
                <el-option label="新生" value="新生" />
                <el-option label="婚进" value="婚进" />
                <el-option label="其他" value="其他" />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
        <el-button style="margin-top: 8px" type="primary" plain size="small" @click="addRow">+ 添加行</el-button>
      </el-tab-pane>

      <!-- 编辑 -->
      <el-tab-pane label="编辑成员" name="edit">
        <el-table :data="form.membersToUpdate" border size="small">
          <el-table-column prop="name" label="姓名" min-width="100">
            <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
          </el-table-column>
          <el-table-column prop="gender" label="性别" width="80">
            <template #default="{ row }">
              <el-select v-model="row.gender" size="small">
                <el-option label="男" value="1" />
                <el-option label="女" value="2" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="idNo" label="证件号码" min-width="160">
            <template #default="{ row }"><el-input v-model="row.idNo" size="small" /></template>
          </el-table-column>
          <el-table-column prop="relationToHead" label="关系" width="90">
            <template #default="{ row }">
              <el-select v-model="row.relationToHead" size="small">
                <el-option label="本人" value="01" />
                <el-option label="配偶" value="02" />
                <el-option label="子女" value="03" />
                <el-option label="父母" value="06" />
                <el-option label="兄弟姐妹" value="08" />
                <el-option label="其他" value="09" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="form.membersToUpdate.splice($index, 1)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!form.membersToUpdate.length" style="margin-top:8px;color:#909399;">
          从当前成员列表点击"加入编辑"以添加到此表
        </div>
      </el-tab-pane>

      <!-- 删除 -->
      <el-tab-pane label="删除成员" name="delete">
        <el-table
          :data="currentMembers"
          border
          size="small"
          @selection-change="handleDeleteSelection"
          ref="deleteTable"
        >
          <el-table-column type="selection" width="50" />
          <el-table-column prop="name" label="姓名" min-width="100" />
          <el-table-column prop="idNo" label="证件号码" min-width="160" />
          <el-table-column label="与户主关系" width="100">
            <template #default="{ row }">{{ relationLabel(row.relationToHead) }}</template>
          </el-table-column>
          <el-table-column label="删除原因" width="120">
            <template #default="{ row }">
              <el-select v-model="row.changeReason" size="small" @change="syncDeleteSelection">
                <el-option label="去世" value="去世" />
                <el-option label="婚出" value="婚出" />
                <el-option label="迁出" value="迁出" />
                <el-option label="其他" value="其他" />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 当前成员（用于编辑加入） -->
    <el-divider />
    <div class="current-members-header">当前成员（点击加入编辑）</div>
    <div class="current-member-chips">
      <el-tag
        v-for="m in currentMembers"
        :key="m.memberUid"
        :type="m.isChanged ? 'warning' : ''"
        class="member-chip"
        @click="addToUpdate(m)"
      >
        {{ m.name }}{{ m.isHouseholdHead ? '(户主)' : '' }}
      </el-tag>
    </div>

    <!-- 原因 -->
    <el-form :model="form" label-position="top" style="margin-top: 12px">
      <el-form-item label="变更原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          placeholder="说明本次成员维护的原因"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const batchId = ref(null);
const contractorUid = ref("");
const currentMembers = ref([]);
const activeTab = ref("add");
const deleteTable = ref(null);

const form = reactive({
  membersToAdd: [],
  membersToUpdate: [],
  reason: "",
});

const relationMap = {
  "01": "户主", "02": "配偶", "03": "子女", "04": "子女",
  "06": "父母", "08": "兄弟姐妹", "09": "其他",
};
function relationLabel(v) {
  return relationMap[v] || v || "-";
}

function open(bid, cuid, memberList) {
  batchId.value = bid;
  contractorUid.value = cuid;
  currentMembers.value = memberList || [];
  form.membersToAdd = [];
  form.membersToUpdate = [];
  form.reason = "";
  visible.value = true;
}

function resetForm() {
  form.membersToAdd = [];
  form.membersToUpdate = [];
  form.reason = "";
}

function addRow() {
  form.membersToAdd.push({
    name: "", gender: "1", idType: "1", idNo: "",
    relationToHead: "09", noteCode: "", isCoOwner: "0",
    isHouseholdHead: false, changeReason: "新生",
  });
}

function addToUpdate(member) {
  const exists = form.membersToUpdate.find((m) => m.memberUid === member.memberUid);
  if (!exists) {
    form.membersToUpdate.push({
      memberUid: member.memberUid,
      name: member.name,
      gender: member.gender || "1",
      idType: member.idType || "1",
      idNo: member.idNo || "",
      relationToHead: member.relationToHead || "09",
      noteCode: member.noteCode || "",
      isCoOwner: member.isCoOwner || "0",
      isHouseholdHead: member.isHouseholdHead || false,
    });
    ElMessage.success(`${member.name} 已加入编辑列表`);
  }
}

function handleDeleteSelection(selection) {
  form._deleteRows = selection;
}

function syncDeleteSelection() {
  if (deleteTable.value) {
    form._deleteRows = deleteTable.value.getSelectionRows();
  }
}

async function handleSubmit() {
  const toDelete = (form._deleteRows || []).map((m) => ({
    memberUid: m.memberUid,
    changeReason: m.changeReason || "去世",
  }));
  if (!form.membersToAdd.length && !form.membersToUpdate.length && !toDelete.length) {
    ElMessage.warning("请至少添加、编辑或选择删除成员");
    return;
  }
  submitting.value = true;
  try {
    const payload = {
      membersToAdd: form.membersToAdd,
      membersToUpdate: form.membersToUpdate,
      membersToDelete: toDelete,
      reason: form.reason || undefined,
    };
    ElMessage.success("成员维护已加入待保存");
    visible.value = false;
    emit("done", { type: "maintain_members", payload });
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert { margin-bottom: 16px; }
.current-members-header { font-size: 13px; font-weight: 500; margin-bottom: 8px; }
.current-member-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.member-chip { cursor: pointer; }
.member-chip:hover { opacity: 0.8; }
</style>
