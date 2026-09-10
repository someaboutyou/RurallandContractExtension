<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div>
        <div class="panel-title">承包方管理</div>
      </div>
      <div class="toolbar-actions toolbar-wrap">
        <el-input
          v-model="filters.name"
          clearable
          placeholder="承包方名称"
          style="width: 160px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filters.memberName"
          clearable
          placeholder="家庭成员名称"
          style="width: 160px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filters.idNo"
          clearable
          placeholder="证件号码"
          style="width: 180px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filters.address"
          clearable
          placeholder="承包方地址"
          style="width: 180px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button plain @click="handleSearch">查询</el-button>
        <el-button plain @click="resetFilters">重置</el-button>
        <el-button plain @click="loadData">刷新</el-button>
        <el-button v-if="canManage" type="success" @click="openCreateDialog">新增承包方</el-button>
      </div>
    </div>

    <div class="contractor-workspace">
      <div class="contractor-table-area">
        <div class="table-shell">
          <div class="table-scroll">
            <el-table v-loading="loading" :data="rows" border>
              <el-table-column prop="code" label="承包方代码" min-width="180" />
              <el-table-column prop="name" label="承包方名称" min-width="180" />
              <el-table-column prop="typeCode" label="承包方类型" min-width="120">
                <template #default="{ row }">{{ contractorTypeLabel(row.typeCode) }}</template>
              </el-table-column>
              <el-table-column prop="mobile" label="联系电话" min-width="140" />
              <el-table-column prop="groupRegionName" label="所属组" min-width="180" show-overflow-tooltip />
              <el-table-column prop="address" label="承包方地址" min-width="260" />
              <el-table-column prop="memberCount" label="家庭成员数" min-width="110" />
              <el-table-column prop="surveyorName" label="调查员" min-width="120" />
              <el-table-column prop="surveyDate" label="调查日期" min-width="120" />
              <el-table-column v-if="canManage" label="操作" fixed="right" min-width="160">
                <template #default="{ row }">
                  <div class="table-actions">
                    <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
                    <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <div class="pagination-wrap">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            background
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </div>

      <RegionFilterPanel
        :region-tree="filterRegionTree"
        :active-region-code="activeRegionCode"
        :active-region-label="activeRegionLabel"
        @select="handleRegionNodeClick"
        @clear="clearRegionFilter"
        @action="handleRegionAction"
      />
    </div>
  </section>

  <ContractorDialog
    ref="contractorDialogRef"
    v-model="dialogVisible"
    :editing-code="editingCode"
    :region-tree="regionTree"
    :can-manage="canManage"
    @saved="handleDialogSaved"
  />
</template>

<script setup>
import { reactive, ref, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  deleteContractor,
  fetchContractors,
} from "../api/contractor";
import { fetchRegionTree } from "../api/region";
import { useDictionary } from "../composables/useDictionary";
import { useAuthStore } from "../stores/auth";
import ContractorDialog from "../components/contractors/ContractorDialog.vue";
import RegionFilterPanel from "../components/contractors/RegionFilterPanel.vue";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));
const { labelOf: contractorTypeLabel } = useDictionary("nyt2539_c16_contractor_type");

const loading = ref(false);
const dialogVisible = ref(false);
const editingCode = ref("");
const contractorDialogRef = ref(null);
const rows = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const filters = reactive({
  name: "",
  memberName: "",
  idNo: "",
  address: "",
});
const regionTree = ref([]);
const filterRegionTree = ref([]);
const activeRegionCode = ref("");
const activeRegionLabel = ref("");

function normalizeRegionTree(nodes = []) {
  return nodes.map((item) => ({
    ...item,
    value: item.code,
    label: item.name,
    children: normalizeRegionTree(item.children || []),
  }));
}

async function loadRegionTree() {
  const [{ data: groupTree }, { data: villageTree }] = await Promise.all([
    fetchRegionTree(undefined, { includeGroups: true }),
    fetchRegionTree("village"),
  ]);
  regionTree.value = normalizeRegionTree(groupTree.data || []);
  filterRegionTree.value = normalizeRegionTree(villageTree.data || []);
}

async function loadData() {
  loading.value = true;
  try {
    const { data } = await fetchContractors({
      page: page.value,
      page_size: pageSize.value,
      name: filters.name.trim() || undefined,
      memberName: filters.memberName.trim() || undefined,
      idNo: filters.idNo.trim() || undefined,
      address: filters.address.trim() || undefined,
      regionCode: activeRegionCode.value || undefined,
    });
    rows.value = data.data.items;
    total.value = data.data.total;
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  loadData();
}

function resetFilters() {
  filters.name = "";
  filters.memberName = "";
  filters.idNo = "";
  filters.address = "";
  handleSearch();
}

function handleRegionNodeClick(data) {
  activeRegionCode.value = data.value;
  activeRegionLabel.value = data.label;
  handleSearch();
}

function clearRegionFilter() {
  activeRegionCode.value = "";
  activeRegionLabel.value = "";
  handleSearch();
}

function handleRegionAction({ command, data }) {
  const actionMap = {
    printSurveyForms: "批量打印调查表",
    printRoster: "打印承包方清册",
    exportSurveyForms: "导出调查表信息",
  };
  ElMessage.info(`${data.label}：${actionMap[command]}功能已预留`);
}

function handlePageChange(value) {
  page.value = value;
  loadData();
}

function handlePageSizeChange(value) {
  pageSize.value = value;
  page.value = 1;
  loadData();
}

function openCreateDialog() {
  editingCode.value = "";
  contractorDialogRef.value?.openForCreate();
}

async function openEditDialog(row) {
  editingCode.value = row.code;
  await contractorDialogRef.value?.openForEdit(row.code);
}

function handleDialogSaved() {
  editingCode.value = "";
  loadData();
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除承包方"${row.name}"吗？该操作不可恢复。`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteContractor(row.code);
    ElMessage.success("承包方已删除");
    if (rows.value.length === 1 && page.value > 1) {
      page.value -= 1;
    }
    await loadData();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "删除失败");
    }
  }
}

loadRegionTree();
loadData();
</script>
