<template>
  <section v-if="!canView" class="panel page-grid">
    <div class="panel-title">字典管理</div>
    <el-empty description="当前账号暂无权限访问字典管理模块。" />
  </section>

  <section v-else class="panel table-page">
    <div class="toolbar toolbar-wrap">
      <div class="panel-title">字典管理</div>
      <div class="toolbar-actions toolbar-wrap">
        <el-input
          v-model="filters.keyword"
          clearable
          placeholder="搜索字典类型、名称"
          style="width: 220px"
          @keyup.enter="loadRows"
        />
        <el-button plain @click="loadRows">刷新</el-button>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
        <el-button v-if="canManage" type="success" @click="openCreateGroupDialog">新增字典组</el-button>
      </div>
    </div>

    <div class="table-shell dictionary-table-shell">
      <div class="table-scroll dictionary-table-scroll">
        <el-table
          v-loading="loading"
          :data="treeData"
          row-key="key"
          border
          :tree-props="{ children: 'children' }"
          :default-expand-all="false"
          :indent="24"
        >
          <el-table-column prop="label" label="字典名称 / 类型" min-width="280">
            <template #default="{ row }">
              <template v-if="row.isGroup">
                <div class="tree-group-row">
                  <svg class="tree-folder-icon" viewBox="0 0 24 24" width="16" height="16" fill="#409eff"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
                  <strong class="tree-group-name">{{ row.dictName }}</strong>
                  <el-tag size="small" type="info" effect="plain">{{ row.dictType }}</el-tag>
                  <span class="tree-group-count">{{ row.children?.length || 0 }} 项</span>
                </div>
              </template>
              <span v-else class="tree-item-name">{{ row.itemName }}</span>
            </template>
          </el-table-column>
          <el-table-column label="值" min-width="160">
            <template #default="{ row }">
              <code v-if="!row.isGroup" class="dict-value-code">{{ row.itemValue }}</code>
            </template>
          </el-table-column>
          <el-table-column label="排序" width="80" align="center">
            <template #default="{ row }">
              <span v-if="!row.isGroup">{{ row.sortOrder }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag
                v-if="!row.isGroup"
                :type="row.enabled ? 'success' : 'info'"
                effect="light"
                size="small"
              >
                {{ row.enabled ? "启用" : "停用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="!row.isGroup">{{ row.remark || "—" }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="canManage" label="操作" fixed="right" width="160">
            <template #default="{ row }">
              <div v-if="row.isGroup" class="table-actions">
                <el-button link type="success" @click.stop="openCreateItemDialog(row)">
                  <svg class="action-icon" viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>添加项
                </el-button>
                <el-popconfirm
                  :title="`确定删除「${row.dictName}」下的全部 ${row.children?.length || 0} 个字典项吗？该操作不可恢复。`"
                  confirm-button-text="删除"
                  cancel-button-text="取消"
                  @confirm="handleDeleteGroup(row)"
                >
                  <template #reference>
                    <el-button link type="danger">删除组</el-button>
                  </template>
                </el-popconfirm>
              </div>
              <div v-else class="table-actions">
                <el-button link type="primary" @click.stop="openEditDialog(row)">编辑</el-button>
                <el-popconfirm
                  :title="`确定删除字典项「${row.itemName}」吗？`"
                  confirm-button-text="删除"
                  cancel-button-text="取消"
                  @confirm="handleDelete(row)"
                >
                  <template #reference>
                    <el-button link type="danger">删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="680px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" class="compact-form" label-position="top" status-icon>
        <div class="form-grid">
          <el-form-item label="字典类型" prop="dictType">
            <el-input
              v-model="form.dictType"
              placeholder="如：custom_status"
              :disabled="dialogMode === 'addItem'"
            />
          </el-form-item>
          <el-form-item label="字典名称" prop="dictName">
            <el-input
              v-model="form.dictName"
              placeholder="如：自定义状态"
              :disabled="dialogMode === 'addItem'"
            />
          </el-form-item>
          <el-form-item label="值" prop="itemValue">
            <el-input v-model="form.itemValue" placeholder="如：active" />
          </el-form-item>
          <el-form-item label="名称" prop="itemName">
            <el-input v-model="form.itemName" placeholder="如：启用" />
          </el-form-item>
          <el-form-item label="排序" prop="sortOrder">
            <el-input-number v-model="form.sortOrder" :min="0" :max="9999" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="是否启用">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item class="form-span-2" label="备注" prop="remark">
            <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="请输入备注" />
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
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import {
  createDictionaryItem,
  deleteDictionaryItem,
  fetchDictionaryItems,
  updateDictionaryItem,
} from "../api/dictionary";
import { clearDictionaryCache } from "../composables/useDictionary";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const canView = computed(() => authStore.hasPermission("dictionaries.view"));
const canManage = computed(() => authStore.hasPermission("dictionaries.manage"));

const loading = ref(false);
const submitting = ref(false);
const dialogVisible = ref(false);
const editingId = ref(0);
const dialogMode = ref("newGroup");
const rows = ref([]);
const formRef = ref();

const filters = reactive({
  keyword: "",
});

const dialogTitle = computed(() => {
  if (dialogMode.value === "addItem") return "添加字典项";
  if (dialogMode.value === "edit") return "编辑字典项";
  return "新增字典组";
});

const form = reactive(createEmptyForm());

const rules = {
  dictType: [{ required: true, message: "请输入字典类型", trigger: "blur" }],
  dictName: [{ required: true, message: "请输入字典名称", trigger: "blur" }],
  itemValue: [{ required: true, message: "请输入字典值", trigger: "blur" }],
  itemName: [{ required: true, message: "请输入名称", trigger: "blur" }],
};

function createEmptyForm() {
  return {
    dictType: "",
    dictName: "",
    itemValue: "",
    itemName: "",
    sortOrder: 0,
    enabled: true,
    remark: "",
  };
}

function resetForm() {
  Object.assign(form, createEmptyForm());
  formRef.value?.clearValidate();
}

const treeData = computed(() => {
  const groups = new Map();
  for (const item of rows.value) {
    if (!groups.has(item.dictType)) {
      groups.set(item.dictType, {
        key: `group-${item.dictType}`,
        isGroup: true,
        dictType: item.dictType,
        dictName: item.dictName,
        children: [],
      });
    }
    const group = groups.get(item.dictType);
    group.children.push({
      ...item,
      key: `item-${item.id}`,
      isGroup: false,
    });
  }
  return [...groups.values()];
});

async function loadRows() {
  if (!canView.value) {
    return;
  }
  loading.value = true;
  try {
    const { data } = await fetchDictionaryItems({
      keyword: filters.keyword || undefined,
    });
    rows.value = data.data || [];
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  loadRows();
}

function resetFilters() {
  filters.keyword = "";
  loadRows();
}

function openCreateGroupDialog() {
  editingId.value = 0;
  dialogMode.value = "newGroup";
  resetForm();
  dialogVisible.value = true;
}

function openCreateItemDialog(groupRow) {
  editingId.value = 0;
  dialogMode.value = "addItem";
  resetForm();
  form.dictType = groupRow.dictType;
  form.dictName = groupRow.dictName;

  const maxOrder = groupRow.children?.reduce((max, c) => Math.max(max, c.sortOrder || 0), 0) || 0;
  form.sortOrder = maxOrder + 10;

  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingId.value = row.id;
  dialogMode.value = "edit";
  Object.assign(form, {
    dictType: row.dictType,
    dictName: row.dictName,
    itemValue: row.itemValue,
    itemName: row.itemName,
    sortOrder: row.sortOrder || 0,
    enabled: row.enabled,
    remark: row.remark || "",
  });
  formRef.value?.clearValidate();
  dialogVisible.value = true;
}

function buildPayload() {
  return {
    dictType: form.dictType.trim(),
    dictName: form.dictName.trim(),
    itemValue: form.itemValue.trim(),
    itemName: form.itemName.trim(),
    sortOrder: form.sortOrder || 0,
    enabled: form.enabled,
    remark: form.remark.trim() || null,
  };
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    ElMessage.warning("请先修正字典表单中的校验问题");
    return;
  }

  const payload = buildPayload();
  submitting.value = true;
  try {
    if (editingId.value) {
      await updateDictionaryItem(editingId.value, payload);
      ElMessage.success("字典项已更新");
      clearDictionaryCache(form.dictType);
      clearDictionaryCache(payload.dictType);
    } else {
      await createDictionaryItem(payload);
      ElMessage.success("字典项已新增");
    }
    clearDictionaryCache(payload.dictType);
    dialogVisible.value = false;
    await loadRows();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "字典保存失败");
  } finally {
    submitting.value = false;
  }
}

async function handleDelete(row) {
  try {
    await deleteDictionaryItem(row.id);
    clearDictionaryCache(row.dictType);
    ElMessage.success("字典项已删除");
    await loadRows();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "字典删除失败");
  }
}

async function handleDeleteGroup(groupRow) {
  try {
    const children = groupRow.children || [];
    for (const child of children) {
      await deleteDictionaryItem(child.id);
    }
    clearDictionaryCache(groupRow.dictType);
    ElMessage.success(`已删除字典组「${groupRow.dictName}」`);
    await loadRows();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "删除字典组失败");
  }
}

onMounted(loadRows);
</script>

<style scoped>
.tree-folder-icon {
  flex-shrink: 0;
}

.action-icon {
  vertical-align: -2px;
  margin-right: 2px;
}

.tree-group-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tree-group-name {
  font-size: 14px;
  margin-right: 4px;
}

.tree-group-count {
  margin-left: auto;
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.tree-item-name {
  padding-left: 4px;
}

.dict-value-code {
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--el-fill-color-light);
  font-size: 13px;
  color: var(--el-color-primary);
}

.table-actions {
  display: flex;
  gap: 4px;
  white-space: nowrap;
}

.dictionary-table-shell {
  flex: 0 1 auto;
  max-height: min(620px, calc(100vh - 190px));
}

.dictionary-table-scroll {
  max-height: inherit;
}
</style>
