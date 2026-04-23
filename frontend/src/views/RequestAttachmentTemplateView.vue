<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div>
        <div class="panel-title">材料模板管理</div>
        <div class="role-hint">维护不同业务类型、不同流程节点的附件模板和示例材料。</div>
      </div>
      <div class="toolbar-actions toolbar-wrap">
        <el-select v-model="tenantFilter" clearable placeholder="按租户筛选" style="width: 220px" @change="loadData">
          <el-option label="全局默认" value="" />
          <el-option v-for="item in tenants" :key="item.code" :label="item.name" :value="item.code" />
        </el-select>
        <el-button plain @click="loadData">刷新</el-button>
        <el-button type="success" @click="openCreateDialog">新增模板</el-button>
      </div>
    </div>

    <div class="table-shell">
      <div class="table-scroll">
        <el-table v-loading="loading" :data="rows" border>
          <el-table-column prop="tenantCode" label="租户" min-width="120">
            <template #default="{ row }">{{ tenantNameMap[row.tenantCode] || "全局默认" }}</template>
          </el-table-column>
          <el-table-column prop="requestType" label="业务类型" min-width="120" />
          <el-table-column prop="stageCode" label="节点编码" min-width="140" />
          <el-table-column prop="stageName" label="节点名称" min-width="140" />
          <el-table-column prop="category" label="材料分类" min-width="120" />
          <el-table-column prop="name" label="材料名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="exampleFileName" label="示例文件" min-width="180" show-overflow-tooltip />
          <el-table-column prop="sortOrder" label="排序" width="90" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="light">
                {{ row.enabled ? "启用" : "停用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="必传" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.required ? 'warning' : 'info'" effect="plain">
                {{ row.required ? "必传" : "选传" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" width="160">
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

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑材料模板' : '新增材料模板'" width="760px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="compact-form" status-icon>
        <div class="form-grid">
          <el-form-item label="租户" prop="tenantCode">
            <el-select v-model="form.tenantCode" clearable placeholder="为空表示全局默认">
              <el-option label="全局默认" value="" />
              <el-option v-for="item in tenants" :key="item.code" :label="item.name" :value="item.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="业务类型" prop="requestType">
            <el-select v-model="form.requestType" placeholder="请选择业务类型">
              <el-option v-for="item in requestTypeOptions" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="节点编码" prop="stageCode">
            <el-select v-model="form.stageCode" placeholder="请选择流程节点">
              <el-option v-for="item in stageOptions" :key="item.code" :label="item.name" :value="item.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="节点名称" prop="stageName">
            <el-input v-model="form.stageName" placeholder="可自动带出，也可手工调整" />
          </el-form-item>
          <el-form-item label="材料分类" prop="category">
            <el-input v-model="form.category" placeholder="如：申请材料、调查材料、审核材料" />
          </el-form-item>
          <el-form-item label="材料名称" prop="name">
            <el-input v-model="form.name" placeholder="请输入材料名称" />
          </el-form-item>
          <el-form-item label="示例文件名" prop="exampleFileName">
            <el-input v-model="form.exampleFileName" placeholder="如：首次登记申请书.docx" />
          </el-form-item>
          <el-form-item label="排序" prop="sortOrder">
            <el-input-number v-model="form.sortOrder" :min="0" :max="999" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="是否启用">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item label="是否必传">
            <el-switch v-model="form.required" />
          </el-form-item>
          <el-form-item class="form-span-2" label="模板说明" prop="description">
            <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入材料用途、来源或准备说明" />
          </el-form-item>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button :loading="submitting" type="success" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createRequestAttachmentTemplate,
  deleteRequestAttachmentTemplate,
  fetchRequestAttachmentTemplates,
  updateRequestAttachmentTemplate,
} from "../api/requestAttachmentTemplate";
import { fetchTenants } from "../api/tenant";

const requestTypeOptions = ["首次登记", "变更登记", "注销登记", "证书补发"];
const stageOptions = [
  { code: "apply", name: "申请" },
  { code: "village_review", name: "村级审核" },
  { code: "town_review", name: "镇级审核" },
  { code: "county_review", name: "县级审核" },
];

const loading = ref(false);
const submitting = ref(false);
const dialogVisible = ref(false);
const editingId = ref(0);
const tenantFilter = ref("");
const rows = ref([]);
const tenants = ref([]);
const formRef = ref();

const form = reactive({
  tenantCode: "",
  requestType: "首次登记",
  stageCode: "apply",
  stageName: "申请",
  category: "",
  name: "",
  required: true,
  description: "",
  exampleFileName: "",
  sortOrder: 0,
  enabled: true,
});

const rules = {
  requestType: [{ required: true, message: "请选择业务类型", trigger: "change" }],
  stageCode: [{ required: true, message: "请选择流程节点", trigger: "change" }],
  category: [{ required: true, message: "请输入材料分类", trigger: "blur" }],
  name: [{ required: true, message: "请输入材料名称", trigger: "blur" }],
};

const tenantNameMap = computed(() =>
  Object.fromEntries(tenants.value.map((item) => [item.code, item.name])),
);

watch(
  () => form.stageCode,
  (value) => {
    const target = stageOptions.find((item) => item.code === value);
    if (target) {
      form.stageName = target.name;
    }
  },
);

function resetForm() {
  Object.assign(form, {
    tenantCode: tenantFilter.value || "",
    requestType: "首次登记",
    stageCode: "apply",
    stageName: "申请",
    category: "",
    name: "",
    required: true,
    description: "",
    exampleFileName: "",
    sortOrder: 0,
    enabled: true,
  });
}

async function loadData() {
  loading.value = true;
  try {
    const [templateResponse, tenantResponse] = await Promise.all([
      fetchRequestAttachmentTemplates({ tenantCode: tenantFilter.value || undefined }),
      fetchTenants(),
    ]);
    rows.value = templateResponse.data.data || [];
    tenants.value = tenantResponse.data.data || [];
  } finally {
    loading.value = false;
  }
}

function openCreateDialog() {
  editingId.value = 0;
  resetForm();
  formRef.value?.clearValidate();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingId.value = row.id;
  Object.assign(form, {
    tenantCode: row.tenantCode || "",
    requestType: row.requestType,
    stageCode: row.stageCode,
    stageName: row.stageName || "",
    category: row.category,
    name: row.name,
    required: row.required,
    description: row.description || "",
    exampleFileName: row.exampleFileName || "",
    sortOrder: row.sortOrder || 0,
    enabled: row.enabled,
  });
  formRef.value?.clearValidate();
  dialogVisible.value = true;
}

function buildPayload() {
  return {
    tenantCode: form.tenantCode || null,
    requestType: form.requestType,
    stageCode: form.stageCode,
    stageName: form.stageName || null,
    category: form.category.trim(),
    name: form.name.trim(),
    required: form.required,
    description: form.description.trim() || null,
    exampleFileName: form.exampleFileName.trim() || null,
    sortOrder: form.sortOrder || 0,
    enabled: form.enabled,
  };
}

async function handleSubmit() {
  await formRef.value?.validate();
  submitting.value = true;
  try {
    const payload = buildPayload();
    if (editingId.value) {
      await updateRequestAttachmentTemplate(editingId.value, payload);
      ElMessage.success("材料模板已更新");
    } else {
      await createRequestAttachmentTemplate(payload);
      ElMessage.success("材料模板已新增");
    }
    dialogVisible.value = false;
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "材料模板保存失败");
  } finally {
    submitting.value = false;
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除模板“${row.name}”吗？`, "删除模板", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteRequestAttachmentTemplate(row.id);
    ElMessage.success("材料模板已删除");
    await loadData();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "材料模板删除失败");
    }
  }
}

onMounted(loadData);
</script>
