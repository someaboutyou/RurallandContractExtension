<template>
  <section class="panel table-page attachment-group-page">
    <div class="toolbar attachment-group-toolbar">
      <div class="panel-title">附件组管理</div>
      <div class="toolbar-actions toolbar-wrap">
        <el-select v-model="tenantFilter" clearable placeholder="按租户筛选" style="width: 180px" @change="reloadTable">
          <el-option label="全部租户" value="" />
          <el-option label="全局默认" value="__global__" />
          <el-option v-for="item in tenants" :key="item.code" :label="item.name" :value="item.code" />
        </el-select>
        <el-select v-model="requestTypeFilter" clearable placeholder="按业务类型筛选" style="width: 180px" @change="reloadTable">
          <el-option v-for="item in requestTypeOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="stageFilter" clearable placeholder="按流程节点筛选" style="width: 180px" @change="reloadTable">
          <el-option v-for="item in filterStageOptions" :key="item.code" :label="item.name" :value="item.code" />
        </el-select>
        <el-select v-model="sourceFilter" clearable placeholder="按来源筛选" style="width: 150px" @change="reloadTable">
          <el-option label="全局默认" value="global" />
          <el-option label="租户覆盖" value="tenant" />
        </el-select>
        <el-button plain @click="reloadTable">刷新</el-button>
        <el-button type="success" @click="openCreateDialog">新增附件组</el-button>
      </div>
    </div>

    <div class="table-shell">
      <div class="table-scroll">
        <el-table
          v-loading="loading"
          :data="rootRows"
          row-key="tableKey"
          border
          lazy
          :load="loadTreeChildren"
          class="attachment-tree-table"
        >
          <el-table-column label="业务类型 / 附件组" min-width="360">
            <template #default="{ row }">
              <span v-if="row.rowType === 'requestType'" class="attachment-tree-table-title attachment-tree-table-title--single">
                {{ row.requestType }}
              </span>
              <span v-else class="attachment-tree-table-node attachment-tree-table-node--single">
                <span class="attachment-tree-prefix">{{ treePrefix(row.level) }}</span>
                <span class="attachment-tree-table-node-name">{{ row.name }}</span>
                <el-tag v-if="row.required" size="small" type="warning" effect="plain">必传</el-tag>
                <el-tag v-if="!row.enabled" size="small" type="info" effect="plain">停用</el-tag>
              </span>
            </template>
          </el-table-column>

          <el-table-column label="覆盖范围" min-width="170">
            <template #default="{ row }">
              <template v-if="row.rowType === 'group'">
                <div class="role-cell">
                  <el-tag size="small" :type="row.source === 'tenant' ? 'success' : 'info'" effect="light">
                    {{ row.source === "tenant" ? "租户覆盖" : "全局默认" }}
                  </el-tag>
                  <span>{{ row.tenantCode ? tenantNameMap[row.tenantCode] || row.tenantCode : "全局默认" }}</span>
                </div>
              </template>
              <span v-else class="role-hint">展开查看附件组树</span>
            </template>
          </el-table-column>

          <el-table-column label="流程节点 / 编码" min-width="220">
            <template #default="{ row }">
              <template v-if="row.rowType === 'group'">
                {{ resolveStageName(row.requestType, row.stageCode, row.stageName) }} / {{ row.stageCode }}
              </template>
              <span v-else>-</span>
            </template>
          </el-table-column>

          <el-table-column label="示例文件" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.rowType === "group" ? row.exampleFileName || "-" : "-" }}</template>
          </el-table-column>

          <el-table-column label="排序" width="90" align="center">
            <template #default="{ row }">{{ row.rowType === "group" ? row.sortOrder || 0 : "-" }}</template>
          </el-table-column>

          <el-table-column label="操作" fixed="right" width="160">
            <template #default="{ row }">
              <div v-if="row.rowType === 'group'" class="table-actions">
                <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
                <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
              </div>
              <span v-else class="role-hint">业务类型行</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑附件组' : '新增附件组'" width="820px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="compact-form" status-icon>
        <div class="form-grid">
          <el-form-item label="覆盖范围" prop="tenantCode">
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

          <el-form-item class="form-span-2">
            <el-alert :title="currentWorkflowHint" type="info" :closable="false" show-icon />
          </el-form-item>

          <el-form-item label="流程节点" prop="stageCode">
            <el-select v-model="form.stageCode" placeholder="请选择流程节点">
              <el-option v-for="item in currentStageOptions" :key="item.code" :label="item.name" :value="item.code" />
            </el-select>
          </el-form-item>

          <el-form-item label="节点名称" prop="stageName">
            <el-input v-model="form.stageName" placeholder="会随节点自动带出，也可微调" />
          </el-form-item>

          <el-form-item label="上级分组" prop="parentId">
            <el-select v-model="form.parentId" clearable placeholder="不选则为一级分组">
              <el-option label="一级分组" :value="null" />
              <el-option v-for="item in parentOptions" :key="item.id" :label="item.label" :value="item.id" />
            </el-select>
          </el-form-item>

          <el-form-item label="附件组名称" prop="name">
            <el-input v-model="form.name" placeholder="如：合同材料、身份信息、身份证附件" />
          </el-form-item>

          <el-form-item label="示例文件名" prop="exampleFileName">
            <el-input v-model="form.exampleFileName" placeholder="如：身份证.pdf、承包合同.pdf" />
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

          <el-form-item class="form-span-2" label="分组说明" prop="description">
            <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入该附件组的用途和说明" />
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
import { fetchRequestWorkflowOptions } from "../api/request";
import { fetchWorkflowDefinition } from "../api/workflow";

const requestTypeOptions = ["首次登记", "变更登记", "注销登记", "证书补发"];
const fallbackStageOptions = [
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
const requestTypeFilter = ref("");
const stageFilter = ref("");
const sourceFilter = ref("");
const tenants = ref([]);
const workflowMappings = ref([]);
const workflowNodeMap = ref({});
const rootRows = ref([]);
const formRef = ref();
const treeCache = new Map();
const rootMetaCache = ref([]);

const form = reactive({
  tenantCode: "",
  parentId: null,
  requestType: "首次登记",
  stageCode: "apply",
  stageName: "申请",
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
  name: [{ required: true, message: "请输入附件组名称", trigger: "blur" }],
};

const tenantNameMap = computed(() => Object.fromEntries(tenants.value.map((item) => [item.code, item.name])));
const requestTypeWorkflowMap = computed(() => Object.fromEntries(workflowMappings.value.map((item) => [item.requestType, item])));
const currentStageOptions = computed(() => workflowNodeMap.value[form.requestType] || fallbackStageOptions);
const filterStageOptions = computed(() => {
  const requestType = requestTypeFilter.value || form.requestType;
  return workflowNodeMap.value[requestType] || fallbackStageOptions;
});

const currentWorkflowHint = computed(() => {
  const mapping = requestTypeWorkflowMap.value[form.requestType];
  if (!mapping) {
    return "当前业务类型还没有绑定流程定义，节点列表先使用默认审核节点。";
  }
  const scope = mapping.source === "tenant" ? "租户覆盖" : "全局默认";
  return `当前业务类型绑定流程：${mapping.workflowName}，来源：${scope}。`;
});

const parentOptions = computed(() =>
  rootMetaCache.value
    .filter(
      (item) =>
        item.id !== editingId.value &&
        item.requestType === form.requestType &&
        item.stageCode === form.stageCode &&
        (item.tenantCode || null) === (form.tenantCode || null),
    )
    .map((item) => ({
      id: item.id,
      label: `${treePrefix(item.level)} ${item.name}`,
    })),
);

watch(
  () => form.requestType,
  (value) => {
    const options = workflowNodeMap.value[value] || fallbackStageOptions;
    if (!options.some((item) => item.code === form.stageCode)) {
      form.stageCode = options[0]?.code || "apply";
    }
    const current = options.find((item) => item.code === form.stageCode);
    if (current) {
      form.stageName = current.name;
    }
  },
);

watch(
  () => form.stageCode,
  (value) => {
    const target = currentStageOptions.value.find((item) => item.code === value);
    if (target) {
      form.stageName = target.name;
    }
  },
);

function treePrefix(level = 0) {
  return `|${"-".repeat((level || 0) + 1)}`;
}

function buildQueryParams(extra = {}) {
  return {
    tenantCode:
      tenantFilter.value && tenantFilter.value !== "__global__"
        ? tenantFilter.value
        : tenantFilter.value === "__global__"
          ? "__global__"
          : undefined,
    requestType: requestTypeFilter.value || undefined,
    stageCode: stageFilter.value || undefined,
    source: sourceFilter.value || undefined,
    applyParentFilter: undefined,
    ...extra,
  };
}

function normalizeTenantCode(value) {
  return value === "__global__" ? "" : value;
}

function parseWorkflowUserTasks(xml) {
  if (!xml) {
    return fallbackStageOptions;
  }
  const parser = new DOMParser();
  const doc = parser.parseFromString(xml, "text/xml");
  const tasks = Array.from(doc.getElementsByTagNameNS("*", "userTask")).map((node) => ({
    code: node.getAttribute("id"),
    name: node.getAttribute("name") || node.getAttribute("id"),
  }));
  return [{ code: "apply", name: "申请" }, ...tasks];
}

async function loadWorkflowNodeOptions() {
  const response = await fetchRequestWorkflowOptions();
  workflowMappings.value = response.data.data.mappings || [];

  for (const mapping of workflowMappings.value) {
    if (workflowNodeMap.value[mapping.requestType]) {
      continue;
    }
    try {
      const detail = await fetchWorkflowDefinition(mapping.workflowKey);
      workflowNodeMap.value = {
        ...workflowNodeMap.value,
        [mapping.requestType]: parseWorkflowUserTasks(detail.data.data.content),
      };
    } catch {
      workflowNodeMap.value = {
        ...workflowNodeMap.value,
        [mapping.requestType]: fallbackStageOptions,
      };
    }
  }
}

function buildRootRows() {
  const types = requestTypeFilter.value
    ? [requestTypeFilter.value]
    : requestTypeOptions.filter((item) => rootMetaCache.value.some((row) => row.requestType === item));
  rootRows.value = types.map((requestType) => ({
    tableKey: `request-type-${requestType}`,
    id: `request-type-${requestType}`,
    rowType: "requestType",
    requestType,
    hasChildren: true,
  }));
}

async function preloadMeta() {
  const params = buildQueryParams();
  params.tenantCode = normalizeTenantCode(params.tenantCode);
  const response = await fetchRequestAttachmentTemplates(params);
  const rows = response.data.data || [];
  const levelMap = new Map();
  const childMap = new Map();
  rows.forEach((item) => {
    if (item.parentId) {
      if (!childMap.has(item.parentId)) {
        childMap.set(item.parentId, []);
      }
      childMap.get(item.parentId).push(item.id);
    }
  });
  const findLevel = (item) => {
    if (!item.parentId) {
      return 0;
    }
    if (levelMap.has(item.id)) {
      return levelMap.get(item.id);
    }
    const parent = rows.find((candidate) => candidate.id === item.parentId);
    const level = parent ? findLevel(parent) + 1 : 0;
    levelMap.set(item.id, level);
    return level;
  };
  rootMetaCache.value = rows.map((item) => ({
    ...item,
    level: findLevel(item),
    source: item.tenantCode ? "tenant" : "global",
    hasChildren: childMap.has(item.id) || item.hasChildren,
  }));
}

async function fetchTemplateNodes({ requestType, parentId = null }) {
  const params = buildQueryParams({
    requestType,
    parentId,
    applyParentFilter: true,
  });
  params.tenantCode = normalizeTenantCode(params.tenantCode);
  const response = await fetchRequestAttachmentTemplates(params);
  return (response.data.data || []).map((item) => {
    const meta = rootMetaCache.value.find((candidate) => candidate.id === item.id);
    return {
      ...item,
      rowType: "group",
      tableKey: `group-${item.id}`,
      source: item.tenantCode ? "tenant" : "global",
      level: meta?.level ?? 0,
      parentName: rootMetaCache.value.find((candidate) => candidate.id === item.parentId)?.name || "",
      hasChildren: item.hasChildren || false,
    };
  });
}

async function loadTreeChildren(row, _treeNode, resolve) {
  const cacheKey = row.rowType === "requestType" ? `root:${row.requestType}` : `child:${row.id}`;
  if (treeCache.has(cacheKey)) {
    resolve(treeCache.get(cacheKey));
    return;
  }
  const nodes = await fetchTemplateNodes({
    requestType: row.requestType,
    parentId: row.rowType === "requestType" ? null : row.id,
  });
  treeCache.set(cacheKey, nodes);
  resolve(nodes);
}

function resetForm() {
  Object.assign(form, {
    tenantCode: tenantFilter.value && tenantFilter.value !== "__global__" ? tenantFilter.value : "",
    parentId: null,
    requestType: requestTypeFilter.value || "首次登记",
    stageCode: "apply",
    stageName: "申请",
    name: "",
    required: true,
    description: "",
    exampleFileName: "",
    sortOrder: 0,
    enabled: true,
  });
}

function resolveStageName(requestType, stageCode, stageName) {
  if (stageName) {
    return stageName;
  }
  const target = (workflowNodeMap.value[requestType] || fallbackStageOptions).find((item) => item.code === stageCode);
  return target?.name || stageCode || "-";
}

async function reloadTable() {
  loading.value = true;
  try {
    treeCache.clear();
    await preloadMeta();
    buildRootRows();
  } finally {
    loading.value = false;
  }
}

async function loadBaseData() {
  loading.value = true;
  try {
    const [tenantResponse] = await Promise.all([fetchTenants(), loadWorkflowNodeOptions()]);
    tenants.value = tenantResponse.data.data || [];
    await reloadTable();
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
    parentId: row.parentId || null,
    requestType: row.requestType,
    stageCode: row.stageCode,
    stageName: resolveStageName(row.requestType, row.stageCode, row.stageName),
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
  const trimmedName = form.name.trim();
  return {
    tenantCode: form.tenantCode || null,
    parentId: form.parentId || null,
    requestType: form.requestType,
    stageCode: form.stageCode,
    stageName: resolveStageName(form.requestType, form.stageCode, form.stageName),
    category: trimmedName,
    name: trimmedName,
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
      ElMessage.success("附件组已更新");
    } else {
      await createRequestAttachmentTemplate(payload);
      ElMessage.success("附件组已新增");
    }
    dialogVisible.value = false;
    await reloadTable();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "附件组保存失败");
  } finally {
    submitting.value = false;
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除附件组“${row.name}”吗？子分组会一起删除。`, "删除附件组", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteRequestAttachmentTemplate(row.id);
    ElMessage.success("附件组已删除");
    await reloadTable();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "附件组删除失败");
    }
  }
}

onMounted(loadBaseData);
</script>
