<template>
  <el-dialog
    v-model="visible"
    title="已注销的承包方"
    width="86vw"
    top="4vh"
    destroy-on-close
  >
    <div class="toolbar">
      <el-input
        v-model="keyword"
        clearable
        placeholder="搜索承包方编码、姓名、地址、注销原因"
        style="width: 320px"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-button :icon="Search" plain @click="handleSearch">查询</el-button>
    </div>

    <el-alert
      v-if="activeBatch?.status === 'finished'"
      title="当前批次已结束，已注销承包方只可查看，不能撤回注销。"
      type="warning"
      :closable="false"
      show-icon
      class="status-alert"
    />

    <el-table v-loading="loading" :data="rows" border stripe size="small" class="dialog-table">
      <el-table-column prop="cbfbm" label="承包方编码" width="170" show-overflow-tooltip />
      <el-table-column prop="cbfmc" label="承包方姓名" min-width="120" show-overflow-tooltip />
      <el-table-column prop="cbfdz" label="承包方地址" min-width="180" show-overflow-tooltip />
      <el-table-column prop="cbfcysl" label="成员数量" width="90" align="center" />
      <el-table-column prop="lxdh" label="联系电话" width="130" show-overflow-tooltip />
      <el-table-column prop="deregisterReason" label="注销原因" min-width="220" show-overflow-tooltip />
      <el-table-column label="注销时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.deregisteredAt) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            :disabled="!canRollback(row)"
            :loading="rollbackingUid === row.contractorUid"
            @click="handleRollback(row)"
          >
            撤回注销
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="footer">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        background
        layout="total, prev, pager, next"
        :total="total"
        @current-change="loadRows"
      />
    </div>
  </el-dialog>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search } from "@element-plus/icons-vue";

import { fetchDeregisteredSurveyContractors, rollbackDeregisteredContractor } from "../../../api/survey";

const props = defineProps({
  activeBatch: { type: Object, default: null },
  canManage: { type: Boolean, default: false },
});

const emit = defineEmits(["restored"]);

const visible = ref(false);
const loading = ref(false);
const rollbackingUid = ref("");
const keyword = ref("");
const rows = ref([]);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

function formatDateTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 19);
}

function canRollback(row) {
  return Boolean(props.canManage && row?.canRollback);
}

async function loadRows() {
  if (!props.activeBatch?.id) {
    rows.value = [];
    total.value = 0;
    return;
  }
  loading.value = true;
  try {
    const { data } = await fetchDeregisteredSurveyContractors(props.activeBatch.id, {
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      regionCode: props.activeBatch?.regionCode || undefined,
    });
    rows.value = data.data.items || [];
    total.value = data.data.total || 0;
  } catch (error) {
    rows.value = [];
    total.value = 0;
    ElMessage.error(error.response?.data?.detail || "加载已注销承包方失败");
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  loadRows();
}

async function handleRollback(row) {
  if (!props.activeBatch?.id || !canRollback(row)) return;
  try {
    await ElMessageBox.confirm(
      `确定撤回承包方“${row.cbfmc}”的注销吗？撤回后该承包方会回到当前调查批次。`,
      "撤回注销",
      { type: "warning", confirmButtonText: "撤回注销", cancelButtonText: "取消" },
    );
    rollbackingUid.value = row.contractorUid;
    await rollbackDeregisteredContractor(props.activeBatch.id, row.contractorUid);
    ElMessage.success("已撤回注销");
    await loadRows();
    emit("restored");
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "撤回注销失败");
    }
  } finally {
    rollbackingUid.value = "";
  }
}

function open() {
  page.value = 1;
  keyword.value = "";
  visible.value = true;
  loadRows();
}

defineExpose({ open });
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.status-alert {
  margin-bottom: 12px;
}

.dialog-table {
  min-height: 420px;
}

.footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
