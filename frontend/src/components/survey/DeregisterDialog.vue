<template>
  <el-dialog
    v-model="visible"
    title="注销承包方"
    width="520px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="注销后不会删除承包方、成员、地块和承包地块调查结果，只会把承包方标记为已注销，并将地块与承包地块信息标记为变更状态。"
      type="warning"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-descriptions :column="1" border size="small" style="margin-bottom: 16px">
      <el-descriptions-item label="承包方名称">{{ form.contractorName }}</el-descriptions-item>
      <el-descriptions-item label="承包方编码">{{ form.cbfbm }}</el-descriptions-item>
      <el-descriptions-item label="家庭成员数">{{ form.memberCount }}</el-descriptions-item>
    </el-descriptions>

    <el-form :model="form" label-position="top" @submit.prevent>
      <el-form-item label="注销原因" required>
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="3"
          placeholder="请说明注销原因，例如：整户消亡、全家迁出、自愿放弃承包权等"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="danger"
        :loading="submitting"
        :disabled="!form.reason.trim()"
        @click="handleSubmit"
      >
        确认注销
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);

const form = reactive({
  contractorName: "",
  cbfbm: "",
  memberCount: 0,
  reason: "",
});

function open(_batchId, _contractorUid, contractorName, cbfbm, memberCount) {
  form.contractorName = contractorName;
  form.cbfbm = cbfbm;
  form.memberCount = memberCount;
  form.reason = "";
  visible.value = true;
}

function resetForm() {
  form.reason = "";
}

async function handleSubmit() {
  if (!form.reason.trim()) {
    ElMessage.warning("请输入注销原因");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定注销承包方“${form.contractorName}”吗？注销后会保留调查结果，并将该承包方标记为已注销，地块和承包地块信息改为变更状态。`,
      "二次确认注销",
      { type: "error", confirmButtonText: "确认注销", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload = { reason: form.reason.trim() };
    ElMessage.success("注销承包方已加入待保存");
    visible.value = false;
    emit("done", { type: "deregister", payload });
  } catch (error) {
    ElMessage.error(error?.message || "注销失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert {
  margin-bottom: 16px;
}
</style>
