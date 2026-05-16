<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div>
        <div class="panel-title">发包方管理</div>
      </div>
      <div class="toolbar-actions toolbar-wrap">
        <el-input
          v-model="keyword"
          clearable
          placeholder="搜索代码、名称、负责人、证件号、电话"
          style="width: 320px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button plain @click="handleSearch">查询</el-button>
        <el-button plain @click="resetFilters">重置</el-button>
        <el-button plain @click="loadData">刷新</el-button>
        <el-button v-if="canManage" type="success" @click="openCreateDialog">新增发包方</el-button>
      </div>
    </div>

    <div class="table-shell">
      <div class="table-scroll">
        <el-table v-loading="loading" :data="rows" border>
          <el-table-column prop="code" label="发包方代码" min-width="180" />
          <el-table-column prop="name" label="发包方名称" min-width="220" />
          <el-table-column prop="ownerName" label="负责人" min-width="120" />
          <el-table-column prop="ownerIdType" label="证件类型" min-width="100" />
          <el-table-column prop="mobile" label="联系电话" min-width="140" />
          <el-table-column prop="address" label="发包方地址" min-width="260" />
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
  </section>

  <el-dialog
    v-model="dialogVisible"
    :title="editingCode ? '编辑发包方' : '新增发包方'"
    class="contractor-dialog"
    width="92vw"
    top="3vh"
    destroy-on-close
  >
    <el-tabs v-model="activeMainTab" class="compact-dialog-tabs">
      <el-tab-pane label="发包方信息" name="base">
        <el-form ref="formRef" :model="form" :rules="rules" class="compact-form" label-position="top" status-icon>
          <div class="form-grid">
            <el-form-item label="发包方代码" prop="code">
              <el-input v-model="form.code" placeholder="请输入发包方代码" />
            </el-form-item>
            <el-form-item label="发包方名称" prop="name">
              <el-input v-model="form.name" placeholder="请输入发包方名称" />
            </el-form-item>
            <el-form-item label="负责人姓名" prop="ownerName">
              <el-input v-model="form.ownerName" placeholder="请输入负责人姓名" />
            </el-form-item>
            <el-form-item label="负责人证件类型" prop="ownerIdType">
              <el-select v-model="form.ownerIdType" placeholder="请选择证件类型">
                <el-option label="居民身份证" value="1" />
                <el-option label="军官证" value="2" />
                <el-option label="护照" value="3" />
                <el-option label="户口簿" value="4" />
                <el-option label="其他" value="9" />
              </el-select>
            </el-form-item>
            <el-form-item label="负责人证件号" prop="ownerIdNo">
              <el-input v-model="form.ownerIdNo" placeholder="请输入负责人证件号" />
            </el-form-item>
            <el-form-item label="联系电话" prop="mobile">
              <el-input v-model="form.mobile" placeholder="请输入联系电话" />
            </el-form-item>
            <el-form-item label="邮政编码" prop="postcode">
              <el-input v-model="form.postcode" placeholder="请输入邮政编码" />
            </el-form-item>
            <el-form-item label="调查员" prop="surveyorName">
              <el-input v-model="form.surveyorName" placeholder="请输入调查员姓名" />
            </el-form-item>
            <el-form-item label="调查日期" prop="surveyDate">
              <el-date-picker
                v-model="form.surveyDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="请选择调查日期"
              />
            </el-form-item>
            <el-form-item class="form-span-2" label="发包方地址" prop="address">
              <el-input v-model="form.address" placeholder="请输入发包方地址" />
            </el-form-item>
            <el-form-item class="form-span-2" label="调查记事" prop="notes">
              <el-input v-model="form.notes" type="textarea" :rows="4" placeholder="请输入调查记事" />
            </el-form-item>
          </div>
        </el-form>
      </el-tab-pane>

      <el-tab-pane :disabled="!editingCode" :label="`承包方信息（${issuerContractors.length}）`" name="contractors">
        <div v-if="!editingCode" class="family-empty">
          新增发包方保存后可查看关联承包方。
        </div>
        <div v-else-if="issuerContractorsLoading" class="parcels-status">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>加载承包方数据...</span>
        </div>
        <div v-else-if="issuerContractorsError" class="parcels-status">
          <span>{{ issuerContractorsError }}</span>
          <el-button size="small" @click="loadIssuerContractors">重试</el-button>
        </div>
        <div v-else-if="!issuerContractors.length" class="family-empty">
          该发包方暂无关联承包方。
        </div>
        <div v-else class="member-table-wrap">
          <el-table :data="issuerContractors" border>
            <el-table-column type="index" label="序号" width="70" />
            <el-table-column prop="code" label="承包方代码" min-width="180" />
            <el-table-column prop="name" label="承包方名称" min-width="180" />
            <el-table-column prop="typeCode" label="承包方类型" min-width="110" />
            <el-table-column prop="mobile" label="联系电话" min-width="140" />
            <el-table-column prop="groupRegionName" label="所属组" min-width="160" show-overflow-tooltip />
            <el-table-column prop="address" label="承包方地址" min-width="240" show-overflow-tooltip />
            <el-table-column prop="memberCount" label="家庭成员数" min-width="110" />
            <el-table-column prop="surveyorName" label="调查员" min-width="120" />
            <el-table-column prop="surveyDate" label="调查日期" min-width="120" />
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane :disabled="!editingCode" label="地块信息" name="parcels">
        <div v-if="parcelsTabActivated" class="parcels-map-area">
          <div v-if="parcelsLoading" class="parcels-status">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>加载地块数据...</span>
          </div>
          <div v-else-if="parcelsError" class="parcels-status">
            <span>{{ parcelsError }}</span>
            <el-button size="small" @click="loadParcelData">重试</el-button>
          </div>
          <div v-else-if="parcelData.length === 0" class="parcels-status">
            <span>该发包方暂无关联地块信息。</span>
          </div>
          <template v-else>
            <div class="parcels-layout">
              <div class="parcels-map-container">
                <div ref="parcelMapRootRef" class="parcels-ol-map"></div>
                <div class="parcels-map-basemap">
                  <el-segmented
                    v-model="activeBasemap"
                    :options="basemapOptions"
                    size="small"
                    @change="switchBasemap"
                  />
                </div>
              </div>
              <div class="parcels-info-panel">
                <div class="parcels-info-title">地块列表 ({{ parcelData.length }})</div>
                <div class="parcels-info-list">
                  <div
                    v-for="item in parcelData"
                    :key="item.dkbm"
                    class="parcels-info-item"
                    :class="{ 'parcels-info-item--flash': flashDkbm === item.dkbm }"
                    @click="focusParcel(item)"
                  >
                    <div class="parcels-info-dkbm">{{ item.dkbm }}</div>
                    <div class="parcels-info-dkmc">{{ item.dkmc || '--' }}</div>
                    <div class="parcels-info-meta">
                      <span v-if="item.cbfbm">承包方: {{ item.cbfbm }}</span>
                      <span v-if="item.htmj">合同面积: {{ item.htmj }}m²</span>
                      <span v-if="item.scmj">实测面积: {{ item.scmj }}m²</span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="parcels-detail-panel">
                <div class="parcels-detail-title">地块详情</div>
                <div v-if="!selectedParcel" class="parcels-detail-empty">点击左侧地块查看详细信息</div>
                <div v-else class="parcels-detail-list">
                  <div v-for="f in parcelDetailFields" :key="f.key" class="parcels-detail-row">
                    <div class="parcels-detail-label">{{ f.label }}</div>
                    <div class="parcels-detail-value">{{ selectedParcel[f.key] || '--' }}</div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
        <div v-else class="parcels-status">
          <el-button type="primary" @click="activateParcelsTab">加载地块信息</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button :loading="submitting" type="success" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Loading } from "@element-plus/icons-vue";

import {
  createIssuer,
  deleteIssuer,
  fetchIssuerContractors,
  fetchIssuerParcels,
  fetchIssuers,
  updateIssuer,
} from "../api/issuer";
import { useDialogMap } from "../composables/useDialogMap";
import { useAuthStore } from "../stores/auth";
import { validateChinaId, validateMobile, validatePostcode } from "../utils/validators";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("issuers.manage"));

const loading = ref(false);
const submitting = ref(false);
const dialogVisible = ref(false);
const editingCode = ref("");
const rows = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const formRef = ref();
const activeMainTab = ref("base");

const issuerContractors = ref([]);
const issuerContractorsLoading = ref(false);
const issuerContractorsError = ref("");

const parcelsTabActivated = ref(false);
const parcelsLoading = ref(false);
const parcelsError = ref("");
const parcelData = ref([]);
const parcelMapRootRef = ref(null);

const {
  mapReady,
  activeBasemap,
  basemapOptions,
  initMap,
  switchBasemap,
  loadParcels,
  fitToParcels,
  focusParcel: focusParcelOnMap,
  updateMapSize,
  destroyMap,
} = useDialogMap(parcelMapRootRef);

const flashDkbm = ref(null);
const selectedParcel = ref(null);

const parcelDetailFields = [
  { key: "dkbm", label: "地块编码" },
  { key: "dkmc", label: "地块名称" },
  { key: "cbfbm", label: "承包方代码" },
  { key: "htmj", label: "合同面积(m²)" },
  { key: "scmj", label: "实测面积(m²)" },
  { key: "syqxz", label: "所有权性质" },
  { key: "dklb", label: "地块类别" },
  { key: "dkdz", label: "地块地址" },
];

const createEmptyForm = () => ({
  code: "",
  name: "",
  ownerName: "",
  ownerIdType: "1",
  ownerIdNo: "",
  mobile: "",
  address: "",
  postcode: "",
  surveyorName: "",
  surveyDate: "",
  notes: "",
});

const form = reactive(createEmptyForm());

const validateOwnerIdNo = (_rule, value, callback) => {
  if (!value) {
    callback(new Error("请输入负责人证件号"));
    return;
  }
  if (form.ownerIdType === "1" && !validateChinaId(value)) {
    callback(new Error("请输入正确的身份证号"));
    return;
  }
  callback();
};

const validateMobileField = (_rule, value, callback) => {
  if (!value) {
    callback();
    return;
  }
  if (!validateMobile(value)) {
    callback(new Error("请输入正确的手机号"));
    return;
  }
  callback();
};

const validatePostcodeField = (_rule, value, callback) => {
  if (!value) {
    callback(new Error("请输入邮政编码"));
    return;
  }
  if (!validatePostcode(value)) {
    callback(new Error("请输入 6 位邮政编码"));
    return;
  }
  callback();
};

const rules = {
  code: [{ required: true, message: "请输入发包方代码", trigger: "blur" }],
  name: [{ required: true, message: "请输入发包方名称", trigger: "blur" }],
  ownerName: [{ required: true, message: "请输入负责人姓名", trigger: "blur" }],
  ownerIdType: [{ required: true, message: "请选择负责人证件类型", trigger: "change" }],
  ownerIdNo: [{ validator: validateOwnerIdNo, trigger: "blur" }],
  mobile: [{ validator: validateMobileField, trigger: "blur" }],
  address: [{ required: true, message: "请输入发包方地址", trigger: "blur" }],
  postcode: [{ validator: validatePostcodeField, trigger: "blur" }],
  surveyorName: [{ required: true, message: "请输入调查员姓名", trigger: "blur" }],
};

function resetForm() {
  Object.assign(form, createEmptyForm());
  activeMainTab.value = "base";
  formRef.value?.clearValidate();
}

function resetRelationState() {
  issuerContractors.value = [];
  issuerContractorsError.value = "";
  parcelsTabActivated.value = false;
  parcelsError.value = "";
  parcelData.value = [];
  selectedParcel.value = null;
  flashDkbm.value = null;
  destroyMap();
}

function triggerFlash(dkbm) {
  flashDkbm.value = dkbm;
  setTimeout(() => {
    if (flashDkbm.value === dkbm) {
      flashDkbm.value = null;
    }
  }, 2800);
}

async function loadIssuerContractors() {
  if (!editingCode.value) return;
  issuerContractorsLoading.value = true;
  issuerContractorsError.value = "";
  try {
    const { data } = await fetchIssuerContractors(editingCode.value);
    issuerContractors.value = data.data || [];
  } catch (error) {
    issuerContractorsError.value = error.response?.data?.detail || "加载承包方信息失败";
  } finally {
    issuerContractorsLoading.value = false;
  }
}

async function activateParcelsTab() {
  parcelsTabActivated.value = true;
  await nextTick();
  await loadParcelData();
  await nextTick();
  if (parcelData.value.length > 0) {
    await initMap();
    setTimeout(() => updateMapSize(), 100);
  }
}

async function loadParcelData() {
  if (!editingCode.value) return;
  parcelsLoading.value = true;
  parcelsError.value = "";
  try {
    const { data } = await fetchIssuerParcels(editingCode.value);
    parcelData.value = data.data || [];
    if (mapReady.value) {
      loadParcels(parcelData.value);
      if (parcelData.value.length > 0) {
        setTimeout(() => fitToParcels(), 300);
      }
    }
  } catch (error) {
    parcelsError.value = error.response?.data?.detail || "加载地块信息失败";
  } finally {
    parcelsLoading.value = false;
  }
}

function focusParcel(item) {
  selectedParcel.value = item;
  triggerFlash(item.dkbm);
  focusParcelOnMap(item.dkbm);
}

watch(activeMainTab, (tabName) => {
  if (tabName === "contractors" && editingCode.value && !issuerContractors.value.length) {
    loadIssuerContractors();
  }
  if (tabName === "parcels" && !parcelsTabActivated.value) {
    activateParcelsTab();
  }
});

watch(mapReady, (ready) => {
  if (ready && parcelData.value.length > 0) {
    loadParcels(parcelData.value);
    setTimeout(() => fitToParcels(), 300);
  }
});

watch(dialogVisible, (visible) => {
  if (!visible) {
    resetRelationState();
  }
});

onBeforeUnmount(() => {
  destroyMap();
});

async function loadData() {
  loading.value = true;
  try {
    const { data } = await fetchIssuers({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value.trim() || undefined,
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
  keyword.value = "";
  handleSearch();
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
  resetForm();
  resetRelationState();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingCode.value = row.code;
  resetRelationState();
  Object.assign(form, {
    code: row.code,
    name: row.name,
    ownerName: row.ownerName,
    ownerIdType: row.ownerIdType || "1",
    ownerIdNo: row.ownerIdNo || "",
    mobile: row.mobile || "",
    address: row.address || "",
    postcode: row.postcode || "",
    surveyorName: row.surveyorName || "",
    surveyDate: row.surveyDate || "",
    notes: row.notes || "",
  });
  activeMainTab.value = "base";
  formRef.value?.clearValidate();
  dialogVisible.value = true;
  loadIssuerContractors();
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    activeMainTab.value = "base";
    ElMessage.warning("请先修正表单中的校验问题");
    return;
  }

  const payload = {
    code: form.code.trim(),
    name: form.name.trim(),
    ownerName: form.ownerName.trim(),
    ownerIdType: form.ownerIdType,
    ownerIdNo: form.ownerIdNo.trim(),
    mobile: form.mobile.trim() || null,
    address: form.address.trim(),
    postcode: form.postcode.trim(),
    surveyorName: form.surveyorName.trim(),
    surveyDate: form.surveyDate || null,
    notes: form.notes.trim() || null,
  };

  submitting.value = true;
  try {
    if (editingCode.value) {
      await updateIssuer(editingCode.value, payload);
      ElMessage.success("发包方已更新");
    } else {
      await createIssuer(payload);
      ElMessage.success("发包方已创建");
    }
    dialogVisible.value = false;
    resetForm();
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存失败");
  } finally {
    submitting.value = false;
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除发包方“${row.name}”吗？该操作不可恢复。`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteIssuer(row.code);
    ElMessage.success("发包方已删除");
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

loadData();
</script>
