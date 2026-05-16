<template>
  <el-dialog
    v-model="visible"
    title="更换户主"
    width="480px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="选择一名家庭成员作为新的户主。原户主将自动取消户主身份。"
      type="info"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-form :model="form" label-position="top" @submit.prevent>
      <el-form-item label="新户主">
        <el-select v-model="form.newHeadMemberUid" placeholder="请选择家庭成员" style="width: 100%">
          <el-option
            v-for="m in eligibleMembers"
            :key="m.memberUid"
            :label="`${m.name}（${m.idNo || '无证件号'}）`"
            :value="m.memberUid"
            :disabled="m.isDeceased"
          >
            <span>{{ m.name }}</span>
            <span class="member-extra">{{ m.idNo }} {{ m.isHouseholdHead ? '(当前户主)' : '' }}</span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="变更原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          placeholder="例如：原户主死亡/迁出/放弃"
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
        :disabled="!form.newHeadMemberUid"
        @click="handleSubmit"
      >
        确认更换
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { changeHouseholdHead } from "../../api/survey";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const batchId = ref(null);
const contractorUid = ref("");
const members = ref([]);

const form = reactive({ newHeadMemberUid: "", reason: "" });

const eligibleMembers = computed(() =>
  members.value.filter((m) => !m.isDeceased)
);

function open(bid, cuid, memberList) {
  batchId.value = bid;
  contractorUid.value = cuid;
  members.value = memberList || [];
  form.newHeadMemberUid = "";
  form.reason = "";
  visible.value = true;
}

function resetForm() {
  form.newHeadMemberUid = "";
  form.reason = "";
}

async function handleSubmit() {
  submitting.value = true;
  try {
    await changeHouseholdHead(batchId.value, contractorUid.value, {
      newHeadMemberUid: form.newHeadMemberUid,
      reason: form.reason || undefined,
    });
    ElMessage.success("户主更换成功");
    visible.value = false;
    emit("done");
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || "更换失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert { margin-bottom: 16px; }
.member-extra { color: #909399; font-size: 12px; margin-left: 8px; }
</style>
