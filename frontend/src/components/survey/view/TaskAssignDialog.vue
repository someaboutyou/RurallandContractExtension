<template>
  <el-dialog v-model="visible" title="分配调查任务" width="680px" top="6vh" destroy-on-close>
    <el-alert
      v-if="rows.length"
      :title="`已选择 ${rows.length} 户承包方`"
      type="info"
      :closable="false"
      show-icon
      class="assign-alert"
    />

    <!-- ⛔ 必须区分「接口被拒」与「真的没有候选人」：把 403（无权分配）
         渲染成"当前区域没有可分配的调查员"，等于把权限问题伪装成数据问题。 -->
    <el-alert
      v-if="!users.length && !usersLoading"
      :title="
        usersError ||
        '当前区域没有可分配的调查员，请先在「系统管理 - 用户管理」中创建在职用户，并为其配置本区域的数据权限。'
      "
      :type="usersError ? 'error' : 'warning'"
      :closable="false"
      show-icon
      class="assign-alert"
    />

    <el-table :data="rows" border stripe size="small" max-height="260" class="assign-table">
      <el-table-column prop="cbfbm" label="承包方编码" width="170" show-overflow-tooltip />
      <el-table-column prop="cbfmc" label="承包方姓名" min-width="110" show-overflow-tooltip />
      <el-table-column prop="cbfdz" label="承包方地址" min-width="180" show-overflow-tooltip />
      <el-table-column label="当前调查员" width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.assignedToName || "未分配" }}</template>
      </el-table-column>
    </el-table>

    <el-form label-width="112px" class="assign-form">
      <el-form-item label="分配给调查员">
        <el-select
          v-model="assigneeId"
          filterable
          :loading="usersLoading"
          placeholder="选择调查员"
          style="width: 100%"
        >
          <el-option
            v-for="user in users"
            :key="user.id"
            :value="user.id"
            :label="user.realName"
            :disabled="!user.coversBatch"
          >
            <span>{{ user.realName }}</span>
            <span class="assign-option-meta">
              {{ user.roleName || "—" }}<template v-if="!user.coversBatch"> · 管辖范围不含本批次</template>
            </span>
          </el-option>
        </el-select>
      </el-form-item>
      <div class="assign-tip">
        分配后，这些承包方只有被分配的调查员（以及批次创建人、系统管理员）可以录入和修改。
      </div>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button :loading="submitting" plain type="warning" :disabled="!rows.length" @click="handleSubmit(null)">
        收回分配
      </el-button>
      <el-button
        :loading="submitting"
        type="primary"
        :disabled="!rows.length || assigneeId === null"
        @click="handleSubmit(assigneeId)"
      >
        确认分配
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { assignSurveyTasks, fetchAssignableUsers } from "../../../api/survey";

const props = defineProps({
  activeBatch: { type: Object, default: null },
});

const emit = defineEmits(["assigned"]);

const visible = ref(false);
const rows = ref([]);
const users = ref([]);
const usersLoading = ref(false);
// 接口失败的原因（403「数据权限区域不包含本调查批次」等）。有值时按错误展示，
// 绝不能再落到"没有可分配的调查员"那句提示上。
const usersError = ref("");
const assigneeId = ref(null);
const submitting = ref(false);

async function loadUsers() {
  if (!props.activeBatch?.id) {
    users.value = [];
    usersError.value = "";
    return;
  }
  usersLoading.value = true;
  usersError.value = "";
  try {
    const { data } = await fetchAssignableUsers(props.activeBatch.id);
    users.value = data.data || [];
  } catch (error) {
    users.value = [];
    usersError.value = error.response?.data?.detail || "加载调查员列表失败";
    ElMessage.error(usersError.value);
  } finally {
    usersLoading.value = false;
  }
}

async function handleSubmit(targetAssigneeId) {
  if (!props.activeBatch?.id || !rows.value.length) return;
  const contractorUids = rows.value.map((row) => row.contractorUid).filter(Boolean);
  const assignee = users.value.find((item) => item.id === targetAssigneeId);
  const confirmText = assignee
    ? `确定把 ${contractorUids.length} 户承包方分配给「${assignee.realName}」吗？`
    : `确定收回这 ${contractorUids.length} 户承包方的分配吗？收回后回到「未分配」状态。`;
  try {
    await ElMessageBox.confirm(confirmText, "分配调查任务", {
      type: "warning",
      confirmButtonText: "确定",
      cancelButtonText: "取消",
    });
  } catch (error) {
    if (error === "cancel" || error === "close") return;
    throw error;
  }
  submitting.value = true;
  try {
    const { data } = await assignSurveyTasks(props.activeBatch.id, {
      contractorUids,
      assigneeId: targetAssigneeId ?? null,
    });
    const result = data.data || {};
    if (result.missing?.length) {
      ElMessage.warning(`已更新 ${result.updated} 户，另有 ${result.missing.length} 户未找到对应任务，已跳过`);
    } else {
      ElMessage.success(assignee ? `已分配给「${assignee.realName}」` : "已收回分配");
    }
    visible.value = false;
    emit("assigned");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "分配失败");
  } finally {
    submitting.value = false;
  }
}

function open(selectedRows) {
  rows.value = [...(selectedRows || [])];
  assigneeId.value = null;
  visible.value = true;
  loadUsers();
}

defineExpose({ open });
</script>

<style scoped>
.assign-alert {
  margin-bottom: 12px;
}

.assign-table {
  margin-bottom: 16px;
}

.assign-form {
  margin-top: 4px;
}

.assign-option-meta {
  float: right;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 12px;
}

.assign-tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
</style>
