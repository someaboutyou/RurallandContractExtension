<template>
  <section class="panel workflow-page">
    <div class="workflow-toolbar">
      <div>
        <div class="panel-title">流程设计</div>
        <div class="workflow-subtitle">基于 BPMN 2.0 在线编辑流程，支持节点业务配置、版本发布和草稿管理。</div>
      </div>
      <div class="toolbar-actions toolbar-wrap">
        <el-button plain @click="handleReloadList">刷新列表</el-button>
        <el-button type="primary" plain @click="handleCreateWorkflow">新建流程</el-button>
        <el-button plain @click="openMappingManager">业务流程映射</el-button>
        <el-button plain :disabled="!activeWorkflowKey" @click="handleValidate">校验</el-button>
        <el-button type="success" :disabled="!activeWorkflowKey" :loading="saving" @click="handleSave">保存流程</el-button>
        <el-button
          type="warning"
          plain
          :disabled="!activeWorkflowKey || publishing || !canPublish"
          :loading="publishing"
          @click="handlePublish"
        >
          发布版本
        </el-button>
      </div>
    </div>

    <div class="workflow-layout workflow-layout--designer">
      <aside class="workflow-sidebar workflow-sidebar--stack">
        <div>
          <div class="workflow-sidebar-title">流程文件</div>
          <div v-if="definitions.length" class="workflow-list">
            <button
              v-for="item in definitions"
              :key="item.key"
              type="button"
              class="workflow-list-item"
              :class="{ 'is-active': item.key === activeWorkflowKey }"
              @click="handleOpenWorkflow(item.key)"
            >
              <div class="workflow-list-name-row">
                <div class="workflow-list-name">{{ item.name }}</div>
                <el-tag v-if="item.hasDraft" size="small" type="warning" effect="light">草稿</el-tag>
              </div>
              <div class="workflow-list-meta">{{ item.filename }}</div>
              <div class="workflow-list-extra">
                <span>版本 {{ item.versionCount || 0 }}</span>
                <span v-if="item.activeVersionNo">生效 V{{ item.activeVersionNo }}</span>
              </div>
            </button>
          </div>
          <el-empty v-else description="当前还没有流程文件" />
        </div>

        <div class="workflow-version-panel">
          <div class="workflow-sidebar-title">版本记录</div>
          <div v-if="versions.length" class="workflow-version-list">
            <button
              v-for="item in versions"
              :key="item.id"
              type="button"
              class="workflow-version-item"
              :class="{ 'is-active': item.isActive }"
              @click="handleActivateVersion(item)"
            >
              <div class="workflow-version-head">
                <div class="workflow-version-name">V{{ item.versionNo }} · {{ item.name }}</div>
                <el-tag size="small" :type="item.isActive ? 'success' : 'info'" effect="light">
                  {{ item.isActive ? "当前生效" : "点击启用" }}
                </el-tag>
              </div>
              <div class="workflow-version-meta">
                {{ item.publishedByName || "系统发布" }}
                <span class="request-detail-dot">·</span>
                {{ formatDateTime(item.createdAt) }}
              </div>
              <div v-if="item.remark" class="workflow-version-remark">{{ item.remark }}</div>
            </button>
          </div>
          <el-empty v-else description="当前流程还没有发布版本" />
        </div>
      </aside>

      <div class="workflow-editor-panel">
        <div class="workflow-editor-header">
          <div>
            <div class="workflow-editor-title-row">
              <div class="workflow-editor-title">{{ activeWorkflowName || "未选择流程" }}</div>
              <el-tag v-if="activeDraftStatus" size="small" :type="hasLocalDraft ? 'danger' : 'warning'" effect="light">
                {{ activeDraftStatus }}
              </el-tag>
            </div>
            <div class="workflow-editor-meta">
              {{ activeWorkflowKey || "-" }}
              <span v-if="activeVersionLabel" class="request-detail-dot">·</span>
              <span v-if="activeVersionLabel">{{ activeVersionLabel }}</span>
              <span v-if="validationMessage" class="request-detail-dot">·</span>
              <span v-if="validationMessage">{{ validationMessage }}</span>
            </div>
          </div>
          <div class="workflow-editor-badges">
            <el-tag v-for="item in activeProcessIds" :key="item" size="small" effect="plain">{{ item }}</el-tag>
          </div>
        </div>

        <div class="workflow-hint-card">
          <div class="workflow-hint-title">节点业务配置说明</div>
          <div class="workflow-hint-text">
            选中 <code>User Task</code> 节点后，可在右侧属性面板中配置权限编码、数据范围、是否必须填写意见、候选角色和办理人选择方式。
          </div>
        </div>

        <div class="workflow-workspace">
          <div ref="canvasRef" class="workflow-canvas"></div>
          <aside ref="propertiesRef" class="workflow-properties"></aside>
        </div>
      </div>
    </div>

    <el-dialog v-model="mappingDialogVisible" title="业务类型与流程映射" width="980px" destroy-on-close>
      <div class="toolbar">
        <div class="role-hint">设置不同业务类型默认使用的流程定义，支持全局默认和按租户覆盖。</div>
        <div class="toolbar-actions">
          <el-button plain @click="loadMappingManager">刷新</el-button>
          <el-button type="primary" @click="openCreateMapping">新增映射</el-button>
        </div>
      </div>
      <el-table v-loading="mappingLoading" :data="workflowMappings" border>
        <el-table-column prop="requestType" label="业务类型" min-width="140" />
        <el-table-column prop="workflowName" label="流程定义" min-width="180" show-overflow-tooltip />
        <el-table-column prop="workflowKey" label="流程编码" min-width="160" />
        <el-table-column prop="workflowVersionLabel" label="绑定版本" min-width="150" />
        <el-table-column prop="tenantName" label="生效范围" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="light">
              {{ row.enabled ? "启用" : "停用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sortOrder" label="排序" width="90" />
        <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openEditMapping(row)">编辑</el-button>
              <el-button link type="danger" @click="handleDeleteMapping(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog
      v-model="mappingFormDialogVisible"
      :title="editingMappingId ? '编辑业务流程映射' : '新增业务流程映射'"
      width="680px"
      destroy-on-close
    >
      <el-form ref="mappingFormRef" :model="mappingForm" :rules="mappingRules" class="compact-form" label-position="top">
        <div class="form-grid">
          <el-form-item label="业务类型" prop="requestType">
            <el-select v-model="mappingForm.requestType" placeholder="请选择业务类型">
              <el-option v-for="item in requestTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="生效租户" prop="tenantCode">
            <el-select v-model="mappingForm.tenantCode" clearable placeholder="不选则为全局默认">
              <el-option label="全局默认" value="" />
              <el-option v-for="item in tenantOptions" :key="item.code" :label="item.name" :value="item.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="流程定义" prop="workflowKey">
            <el-select v-model="mappingForm.workflowKey" filterable placeholder="请选择流程定义">
              <el-option v-for="item in definitions" :key="item.key" :label="item.name" :value="item.key" />
            </el-select>
          </el-form-item>
          <el-form-item label="绑定版本" prop="workflowVersionId">
            <el-select
              v-model="mappingForm.workflowVersionId"
              clearable
              placeholder="不选则跟随当前生效版本"
            >
              <el-option label="跟随当前生效版本" :value="null" />
              <el-option
                v-for="item in workflowVersionOptions"
                :key="item.id"
                :label="`V${item.versionNo} · ${item.name}`"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="排序" prop="sortOrder">
            <el-input-number v-model="mappingForm.sortOrder" :min="0" :max="9999" style="width: 100%" />
          </el-form-item>
          <el-form-item label="是否启用" prop="enabled">
            <el-switch v-model="mappingForm.enabled" />
          </el-form-item>
          <el-form-item class="form-span-2" label="备注" prop="remark">
            <el-input v-model="mappingForm.remark" type="textarea" :rows="3" placeholder="可选填写映射说明" />
          </el-form-item>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="mappingFormDialogVisible = false">取消</el-button>
        <el-button type="success" :loading="mappingSubmitting" @click="handleSubmitMapping">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";
import "@bpmn-io/properties-panel/dist/assets/properties-panel.css";

import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import BpmnModeler from "bpmn-js/lib/Modeler";
import { BpmnPropertiesPanelModule, BpmnPropertiesProviderModule } from "bpmn-js-properties-panel";

import {
  activateWorkflowDefinition,
  fetchWorkflowDefinition,
  fetchWorkflowDefinitions,
  fetchWorkflowVersions,
  publishWorkflowDefinition,
  saveWorkflowDefinition,
  validateWorkflowDefinition,
} from "../api/workflow";
import { fetchTenants } from "../api/tenant";
import {
  createRequestWorkflowMapping,
  deleteRequestWorkflowMapping,
  fetchRequestWorkflowMappings,
  updateRequestWorkflowMapping,
} from "../api/requestWorkflowMapping";
import ruralModdle from "../workflow/rural-moddle.json";
import RuralPropertiesProviderModule from "../workflow/properties/RuralPropertiesProviderModule";

const canvasRef = ref(null);
const propertiesRef = ref(null);
const definitions = ref([]);
const versions = ref([]);
const activeWorkflowKey = ref("");
const activeWorkflowName = ref("");
const activeProcessIds = ref([]);
const validationMessage = ref("");
const saving = ref(false);
const publishing = ref(false);
const hasLocalDraft = ref(false);
const mappingDialogVisible = ref(false);
const mappingFormDialogVisible = ref(false);
const mappingLoading = ref(false);
const mappingSubmitting = ref(false);
const workflowMappings = ref([]);
const workflowVersionOptions = ref([]);
const tenantOptions = ref([]);
const mappingFormRef = ref(null);
const editingMappingId = ref(0);

const requestTypeOptions = [
  { label: "首次登记", value: "首次登记" },
  { label: "变更登记", value: "变更登记" },
  { label: "注销登记", value: "注销登记" },
  { label: "证书补发", value: "证书补发" },
];

const createEmptyMappingForm = () => ({
  tenantCode: "",
  requestType: "首次登记",
  workflowKey: "",
  workflowVersionId: null,
  enabled: true,
  sortOrder: 0,
  remark: "",
});

const mappingForm = reactive(createEmptyMappingForm());
const mappingRules = {
  requestType: [{ required: true, message: "请选择业务类型", trigger: "change" }],
  workflowKey: [{ required: true, message: "请选择流程定义", trigger: "change" }],
};

const activeDefinition = computed(() => definitions.value.find((item) => item.key === activeWorkflowKey.value) || null);
const activeDraftStatus = computed(() => {
  if (hasLocalDraft.value) {
    return "未保存修改";
  }
  if (activeDefinition.value?.hasDraft) {
    return "未发布草稿";
  }
  return "";
});
const activeVersionLabel = computed(() =>
  activeDefinition.value?.activeVersionNo ? `生效版本 V${activeDefinition.value.activeVersionNo}` : "",
);
const canPublish = computed(() => !hasLocalDraft.value && !!activeDefinition.value?.hasDraft);

let modeler = null;
let isImportingXml = false;

const createTemplateXml = (key, name) => `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
  xmlns:rural="http://ruralland.cn/schema/bpmn"
  id="Definitions_${key}"
  targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="${key}" name="${name}" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" name="开始">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:userTask id="Activity_1" name="办理节点">
      <bpmn:incoming>Flow_1</bpmn:incoming>
      <bpmn:outgoing>Flow_2</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:endEvent id="EndEvent_1" name="结束">
      <bpmn:incoming>Flow_2</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Activity_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Activity_1" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="${key}">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="180" y="160" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_1_di" bpmnElement="Activity_1">
        <dc:Bounds x="290" y="138" width="120" height="80" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="500" y="160" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Flow_1_di" bpmnElement="Flow_1">
        <di:waypoint x="216" y="178" />
        <di:waypoint x="290" y="178" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_2_di" bpmnElement="Flow_2">
        <di:waypoint x="410" y="178" />
        <di:waypoint x="500" y="178" />
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
`;

function sanitizeWorkflowKey(input) {
  return input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  return String(value).replace("T", " ").slice(0, 19);
}

function findDefinition(key) {
  return definitions.value.find((item) => item.key === key) || null;
}

function syncActiveDefinition(patch) {
  const index = definitions.value.findIndex((item) => item.key === activeWorkflowKey.value);
  if (index === -1) {
    return;
  }
  definitions.value[index] = {
    ...definitions.value[index],
    ...patch,
  };
}

function resetMappingForm() {
  Object.assign(mappingForm, createEmptyMappingForm());
  mappingFormRef.value?.clearValidate();
}

async function confirmDiscardChanges(actionText) {
  if (!hasLocalDraft.value) {
    return true;
  }
  try {
    await ElMessageBox.confirm(
      `当前流程存在未保存修改，继续${actionText}会丢失本次编辑内容。`,
      "未保存修改",
      {
        type: "warning",
        confirmButtonText: "继续",
        cancelButtonText: "取消",
      },
    );
    return true;
  } catch {
    return false;
  }
}

async function ensureModeler() {
  if (modeler || !canvasRef.value || !propertiesRef.value) {
    return;
  }

  modeler = new BpmnModeler({
    container: canvasRef.value,
    propertiesPanel: {
      parent: propertiesRef.value,
    },
    additionalModules: [BpmnPropertiesPanelModule, BpmnPropertiesProviderModule, RuralPropertiesProviderModule],
    moddleExtensions: {
      rural: ruralModdle,
    },
  });

  modeler.get("eventBus").on("commandStack.changed", () => {
    if (isImportingXml) {
      return;
    }
    hasLocalDraft.value = true;
    validationMessage.value = "当前存在未保存修改";
  });
}

async function importXml(xml) {
  await ensureModeler();
  isImportingXml = true;
  try {
    const result = await modeler.importXML(xml);
    modeler.get("canvas").zoom("fit-viewport", "auto");
    return result;
  } finally {
    hasLocalDraft.value = false;
    isImportingXml = false;
  }
}

async function exportXml() {
  const { xml } = await modeler.saveXML({ format: true });
  return xml;
}

async function loadDefinitions() {
  const { data } = await fetchWorkflowDefinitions();
  definitions.value = data.data;
}

async function loadVersions(key) {
  if (!key) {
    versions.value = [];
    return;
  }
  const { data } = await fetchWorkflowVersions(key);
  versions.value = data.data;
}

async function loadWorkflowVersionOptions(workflowKey, preferredVersionId = null) {
  if (!workflowKey) {
    workflowVersionOptions.value = [];
    mappingForm.workflowVersionId = null;
    return;
  }
  try {
    const { data } = await fetchWorkflowDefinition(workflowKey);
    workflowVersionOptions.value = data.data.versions || [];
    if (
      preferredVersionId &&
      workflowVersionOptions.value.some((item) => item.id === preferredVersionId)
    ) {
      mappingForm.workflowVersionId = preferredVersionId;
      return;
    }
    if (
      mappingForm.workflowVersionId &&
      !workflowVersionOptions.value.some((item) => item.id === mappingForm.workflowVersionId)
    ) {
      mappingForm.workflowVersionId = null;
    }
  } catch (error) {
    workflowVersionOptions.value = [];
    mappingForm.workflowVersionId = null;
    ElMessage.error(error.response?.data?.detail || "加载流程版本列表失败");
  }
}

async function loadMappingManager() {
  mappingLoading.value = true;
  try {
    const [mappingResponse, tenantResponse] = await Promise.all([fetchRequestWorkflowMappings(), fetchTenants()]);
    workflowMappings.value = mappingResponse.data.data;
    tenantOptions.value = tenantResponse.data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "加载业务流程映射失败");
  } finally {
    mappingLoading.value = false;
  }
}

async function openMappingManager() {
  mappingDialogVisible.value = true;
  await loadMappingManager();
}

async function openCreateMapping() {
  editingMappingId.value = 0;
  resetMappingForm();
  mappingForm.workflowKey = activeWorkflowKey.value || definitions.value[0]?.key || "";
  await loadWorkflowVersionOptions(mappingForm.workflowKey);
  mappingFormDialogVisible.value = true;
}

async function openEditMapping(row) {
  editingMappingId.value = row.id;
  Object.assign(mappingForm, {
    tenantCode: row.tenantCode || "",
    requestType: row.requestType,
    workflowKey: row.workflowKey,
    workflowVersionId: row.workflowVersionId || null,
    enabled: row.enabled,
    sortOrder: row.sortOrder,
    remark: row.remark || "",
  });
  await loadWorkflowVersionOptions(mappingForm.workflowKey, row.workflowVersionId || null);
  mappingFormRef.value?.clearValidate();
  mappingFormDialogVisible.value = true;
}

async function handleSubmitMapping() {
  const valid = await mappingFormRef.value.validate().catch(() => false);
  if (!valid) {
    ElMessage.warning("请先修正映射表单中的校验问题");
    return;
  }

  mappingSubmitting.value = true;
  try {
    const payload = {
      tenantCode: mappingForm.tenantCode || null,
      requestType: mappingForm.requestType,
      workflowKey: mappingForm.workflowKey,
      workflowVersionId: mappingForm.workflowVersionId || null,
      enabled: mappingForm.enabled,
      sortOrder: mappingForm.sortOrder,
      remark: mappingForm.remark?.trim() || null,
    };
    if (editingMappingId.value) {
      await updateRequestWorkflowMapping(editingMappingId.value, payload);
      ElMessage.success("业务流程映射已更新");
    } else {
      await createRequestWorkflowMapping(payload);
      ElMessage.success("业务流程映射已创建");
    }
    mappingFormDialogVisible.value = false;
    await loadMappingManager();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存业务流程映射失败");
  } finally {
    mappingSubmitting.value = false;
  }
}

async function handleDeleteMapping(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除“${row.requestType} -> ${row.workflowName || row.workflowKey}”这条映射吗？`,
      "删除业务流程映射",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
      },
    );
    await deleteRequestWorkflowMapping(row.id);
    ElMessage.success("业务流程映射已删除");
    await loadMappingManager();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "删除业务流程映射失败");
    }
  }
}

async function openWorkflow(key) {
  const { data } = await fetchWorkflowDefinition(key);
  activeWorkflowKey.value = data.data.key;
  activeWorkflowName.value = data.data.name;
  activeProcessIds.value = data.data.processIds || [];
  versions.value = data.data.versions || [];
  validationMessage.value = data.data.hasDraft ? "已加载流程定义，当前存在未发布草稿" : "已加载流程定义";
  await importXml(data.data.content);
}

async function validateCurrent({ silentSuccess = false } = {}) {
  if (!activeWorkflowKey.value) {
    return false;
  }
  const xml = await exportXml();
  const { data } = await validateWorkflowDefinition(xml);
  activeProcessIds.value = data.data.processIds || [];
  if (data.data.name) {
    activeWorkflowName.value = data.data.name;
  }
  validationMessage.value = hasLocalDraft.value ? "校验通过，当前存在未保存修改" : data.data.message;
  if (!silentSuccess) {
    ElMessage.success(data.data.message);
  }
  return true;
}

async function handleOpenWorkflow(key) {
  if (key === activeWorkflowKey.value && activeDefinition.value) {
    return;
  }
  const allowed = await confirmDiscardChanges("切换到其他流程");
  if (!allowed) {
    return;
  }
  try {
    await openWorkflow(key);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || "加载流程定义失败");
  }
}

async function handleReloadList() {
  const allowed = await confirmDiscardChanges("刷新流程列表");
  if (!allowed) {
    return;
  }
  try {
    const currentKey = activeWorkflowKey.value;
    await loadDefinitions();
    if (currentKey && findDefinition(currentKey)) {
      await openWorkflow(currentKey);
    } else if (definitions.value.length) {
      await openWorkflow(definitions.value[0].key);
    } else {
      activeWorkflowKey.value = "";
      activeWorkflowName.value = "";
      activeProcessIds.value = [];
      versions.value = [];
      validationMessage.value = "";
    }
    ElMessage.success("流程列表已刷新");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "刷新流程列表失败");
  }
}

async function handleCreateWorkflow() {
  const allowed = await confirmDiscardChanges("新建流程");
  if (!allowed) {
    return;
  }
  try {
    const { value: keyValue } = await ElMessageBox.prompt(
      "请输入流程编码，只能使用字母、数字、下划线和中划线。",
      "新建流程",
      {
        confirmButtonText: "下一步",
        cancelButtonText: "取消",
        inputPlaceholder: "例如：land_register_first",
        inputValidator: (value) => {
          const key = sanitizeWorkflowKey(value || "");
          if (!key) {
            return "请输入合法的流程编码";
          }
          if (definitions.value.some((item) => item.key === key)) {
            return "流程编码已存在，请更换后再创建";
          }
          return true;
        },
      },
    );
    const workflowKey = sanitizeWorkflowKey(keyValue);
    const { value: nameValue } = await ElMessageBox.prompt("请输入流程名称。", "流程名称", {
      confirmButtonText: "创建",
      cancelButtonText: "取消",
      inputPlaceholder: "例如：首次登记流程",
      inputValue: workflowKey,
      inputValidator: (value) => {
        if (!value?.trim()) {
          return "请输入流程名称";
        }
        return true;
      },
    });

    activeWorkflowKey.value = workflowKey;
    activeWorkflowName.value = nameValue.trim();
    activeProcessIds.value = [workflowKey];
    versions.value = [];
    validationMessage.value = "新流程尚未保存";
    await importXml(createTemplateXml(workflowKey, activeWorkflowName.value));
    hasLocalDraft.value = true;
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error("新建流程失败");
    }
  }
}

async function handleValidate() {
  if (!activeWorkflowKey.value) {
    return;
  }
  try {
    await validateCurrent();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || "流程校验失败");
  }
}

async function handleSave() {
  if (!activeWorkflowKey.value) {
    return;
  }
  saving.value = true;
  try {
    const xml = await exportXml();
    const { data } = await saveWorkflowDefinition(activeWorkflowKey.value, {
      name: activeWorkflowName.value || activeWorkflowKey.value,
      content: xml,
    });
    activeWorkflowName.value = data.data.name;
    activeProcessIds.value = data.data.processIds || [];
    hasLocalDraft.value = false;
    validationMessage.value = data.data.hasDraft ? "流程已保存，当前存在未发布草稿" : "流程定义已保存";
    await loadDefinitions();
    syncActiveDefinition({
      hasDraft: data.data.hasDraft,
      draftUpdatedAt: data.data.draftUpdatedAt,
      activeVersionId: data.data.activeVersionId,
      activeVersionNo: data.data.activeVersionNo,
      versionCount: data.data.versionCount,
      updatedAt: data.data.updatedAt,
      name: data.data.name,
      processIds: data.data.processIds || [],
      filename: data.data.filename,
    });
    await loadVersions(activeWorkflowKey.value);
    ElMessage.success("流程定义已保存");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || "保存流程定义失败");
  } finally {
    saving.value = false;
  }
}

async function handlePublish() {
  if (!activeWorkflowKey.value) {
    return;
  }
  if (hasLocalDraft.value) {
    ElMessage.warning("请先保存当前未落盘的修改，再发布版本");
    return;
  }
  if (!activeDefinition.value?.hasDraft) {
    ElMessage.info("当前没有新的草稿内容可发布");
    return;
  }
  try {
    await validateCurrent({ silentSuccess: true });
    const { value } = await ElMessageBox.prompt("请输入本次流程版本的发布说明，可留空。", "发布版本", {
      confirmButtonText: "发布并启用",
      cancelButtonText: "取消",
      inputPlaceholder: "例如：增加县级审核意见必填",
      inputValue: "",
    });
    publishing.value = true;
    const { data } = await publishWorkflowDefinition(activeWorkflowKey.value, {
      remark: value || null,
      activate: true,
    });
    await loadDefinitions();
    await openWorkflow(activeWorkflowKey.value);
    validationMessage.value = `已发布版本 V${data.data.versionNo}`;
    ElMessage.success(`流程已发布为 V${data.data.versionNo}`);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "发布流程版本失败");
    }
  } finally {
    publishing.value = false;
  }
}

async function handleActivateVersion(version) {
  if (!activeWorkflowKey.value || version.isActive) {
    return;
  }
  const allowed = await confirmDiscardChanges("启用其他流程版本");
  if (!allowed) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定启用版本 V${version.versionNo} 吗？启用后当前流程文件会切换到该版本内容。`,
      "启用流程版本",
      {
        type: "warning",
        confirmButtonText: "启用",
        cancelButtonText: "取消",
      },
    );
    await activateWorkflowDefinition(activeWorkflowKey.value, version.id);
    await loadDefinitions();
    await openWorkflow(activeWorkflowKey.value);
    ElMessage.success(`已启用版本 V${version.versionNo}`);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "启用流程版本失败");
    }
  }
}

function handleBeforeUnload(event) {
  if (!hasLocalDraft.value) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
}

onMounted(async () => {
  await nextTick();
  await ensureModeler();
  window.addEventListener("beforeunload", handleBeforeUnload);
  try {
    await loadDefinitions();
    if (definitions.value.length) {
      await openWorkflow(definitions.value[0].key);
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "初始化流程设计器失败");
  }
});

watch(
  () => mappingForm.workflowKey,
  async (value, oldValue) => {
    if (!mappingFormDialogVisible.value || !value || value === oldValue) {
      return;
    }
    await loadWorkflowVersionOptions(value);
  },
);

onBeforeRouteLeave(async () => {
  const allowed = await confirmDiscardChanges("离开当前页面");
  if (!allowed) {
    return false;
  }
  return true;
});

onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", handleBeforeUnload);
  if (modeler) {
    modeler.destroy();
    modeler = null;
  }
});
</script>
