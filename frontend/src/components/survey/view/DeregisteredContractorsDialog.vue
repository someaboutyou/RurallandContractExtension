<template>
  <el-dialog
    v-model="visible"
    title="已退出待办的承包方（注销 / 合并户 / 分户）"
    width="86vw"
    top="4vh"
    destroy-on-close
  >
    <div class="toolbar">
      <el-input
        v-model="keyword"
        clearable
        placeholder="搜索承包方编码、姓名、地址、变更原因"
        style="width: 320px"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-button :icon="Search" plain @click="handleSearch">查询</el-button>
    </div>

    <el-alert
      v-if="activeBatch?.status === 'finished'"
      title="当前批次已结束，只能查看，不能撤回。"
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
      <el-table-column label="变更类型" width="104">
        <template #default="{ row }">
          <el-tag :type="changeTypeTag(row.changeType)" size="small" effect="plain">
            {{ changeTypeLabel(row.changeType) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="deregisterReason" label="变更原因" min-width="200" show-overflow-tooltip />
      <el-table-column label="变更时间" width="170">
        <template #default="{ row }">{{ formatDateTime(row.deregisteredAt) }}</template>
      </el-table-column>
      <el-table-column label="变更单号" width="152" show-overflow-tooltip>
        <template #default="{ row }">{{ row.changeNo || "-" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            :disabled="!canRollback(row)"
            :loading="rollbackingUid === row.contractorUid"
            @click="handleRollback(row)"
          >
            {{ rollbackLabel(row.changeType) }}
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

import {
  fetchDeregisteredSurveyContractors,
  rollbackDeregisteredContractor,
  rollbackMergeSurveyHousehold,
  rollbackSplitSurveyHousehold,
} from "../../../api/survey";

/**
 * 这个列表里会出现**三种**"让户离开待办"的终态操作，按钮必须按 `changeType` 分流。
 *
 * ⛔ 历史事故（2026-09-25 修）：界面只有一个写死「撤回注销」的按钮，一律打
 * `rollback-deregister`；而后端 `rollback_deregistered_contractor` 只认
 * `change_type == "deregister"` 的记录，合户写的是 `merge_household`、分户写的是
 * `split_household` ⇒ 对这两类行，按钮**渲染得出来但点下去必然 400**。
 * 根因是"谁能点按钮"（列表的 canRollback）与"接口拦不拦"不同源。
 *
 * 分组口径与后端 `SurveyServiceBase.terminal_operation_types` 一致。
 */
const TERMINAL_OPERATIONS = {
  deregister: {
    label: "注销",
    tag: "info",
    button: "撤回注销",
    confirm: (row) => `确定撤回承包方“${row.cbfmc}”的注销吗？撤回后该承包方会回到当前调查批次。`,
    call: (batchId, uid) => rollbackDeregisteredContractor(batchId, uid),
    success: "已撤回注销",
  },
  merge_household: {
    label: "合并户",
    tag: "warning",
    button: "撤回合户",
    confirm: (row) =>
      `确定撤回“${row.cbfmc}”参与的合户吗？合户生成的新承包方将被删除，所有原承包方、家庭成员和地块恢复到合户前状态。`,
    call: (batchId, uid) => rollbackMergeSurveyHousehold(batchId, uid),
    success: "已撤回合户",
  },
  split_household: {
    label: "分户",
    tag: "warning",
    button: "撤回分户",
    confirm: (row) =>
      `确定撤回“${row.cbfmc}”的分户吗？分户生成的新承包方将被删除，原承包户、成员和地块恢复到分户前状态。`,
    call: (batchId, uid) => rollbackSplitSurveyHousehold(batchId, uid),
    success: "已撤回分户",
  },
};

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

function changeTypeLabel(type) {
  return TERMINAL_OPERATIONS[type]?.label || type || "-";
}

function changeTypeTag(type) {
  return TERMINAL_OPERATIONS[type]?.tag || "info";
}

function rollbackLabel(type) {
  return TERMINAL_OPERATIONS[type]?.button || "撤回";
}

/**
 * 按钮能不能点，必须与"接口能不能拦"同源：
 * 既要有后端给的 `canRollback`，又要有一个**已知的 changeType**（否则不知道该打哪个接口）。
 * 这样就不会再渲染出"渲染得出来、点下去必然 400"的按钮。
 */
function canRollback(row) {
  return Boolean(props.canManage && row?.canRollback && TERMINAL_OPERATIONS[row?.changeType]);
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
  // 按 changeType 分流到各自的撤回接口 —— 三种操作的确认文案与成功提示都不同。
  const operation = TERMINAL_OPERATIONS[row.changeType];
  try {
    await ElMessageBox.confirm(operation.confirm(row), operation.button, {
      type: "warning",
      confirmButtonText: "确认撤回",
      cancelButtonText: "取消",
    });
    rollbackingUid.value = row.contractorUid;
    await operation.call(props.activeBatch.id, row.contractorUid);
    ElMessage.success(operation.success);
    await loadRows();
    emit("restored");
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || `${operation.button}失败`);
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
