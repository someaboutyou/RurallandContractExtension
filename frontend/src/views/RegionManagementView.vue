<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div class="panel-title">区域管理</div>
      <div class="toolbar-actions">
        <el-button plain @click="loadRegions">刷新</el-button>
        <el-button v-if="canManage" type="success" @click="openCreateDialog()">新增区域</el-button>
      </div>
    </div>

    <el-table v-loading="loading" :data="regionTree" border row-key="id" default-expand-all>
      <el-table-column prop="name" label="区域名称" min-width="180" />
      <el-table-column prop="code" label="区域代码" min-width="150" />
      <el-table-column prop="level" label="级别" width="110">
        <template #default="{ row }">{{ levelLabel(row.level) }}</template>
      </el-table-column>
      <el-table-column prop="fullName" label="完整名称" min-width="260" show-overflow-tooltip />
      <el-table-column prop="tenantCode" label="租户代码" width="120" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === "active" ? "启用" : "停用" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sortOrder" label="排序" width="90" />
      <el-table-column v-if="canManage" label="操作" fixed="right" width="220">
        <template #default="{ row }">
          <div class="table-actions">
            <el-button link type="primary" @click="openCreateDialog(row)">新增下级</el-button>
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </section>

  <el-dialog v-model="dialogVisible" :title="editingId ? '编辑区域' : '新增区域'" width="640px" destroy-on-close>
    <el-form ref="formRef" :model="form" :rules="rules" class="compact-form" label-position="top">
      <div class="form-grid">
        <el-form-item label="区域名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="区域代码" prop="code">
          <el-input v-model="form.code" />
        </el-form-item>
        <el-form-item label="区域级别" prop="level">
          <el-select v-model="form.level">
            <el-option label="省级" value="province" />
            <el-option label="县级" value="county" />
            <el-option label="镇级" value="town" />
            <el-option label="村级" value="village" />
          </el-select>
        </el-form-item>
        <el-form-item label="父级区域">
          <el-tree-select
            v-model="form.parentId"
            clearable
            filterable
            check-strictly
            :data="regionTree"
            :props="treeProps"
            node-key="id"
            placeholder="请选择父级区域"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status">
            <el-option label="启用" value="active" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sortOrder" :min="0" controls-position="right" />
        </el-form-item>
        <el-form-item class="form-span-2" label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="3" />
        </el-form-item>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button :loading="submitting" type="success" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { createRegion, deleteRegion, fetchRegionTree, updateRegion } from "../api/region";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("regions.manage"));
const loading = ref(false);
const submitting = ref(false);
const dialogVisible = ref(false);
const editingId = ref(0);
const formRef = ref();
const regionTree = ref([]);
const treeProps = { label: "fullName", children: "children" };

const form = reactive(createEmptyForm());
const rules = {
  name: [{ required: true, message: "请输入区域名称", trigger: "blur" }],
  code: [{ required: true, message: "请输入区域代码", trigger: "blur" }],
  level: [{ required: true, message: "请选择区域级别", trigger: "change" }],
};

function createEmptyForm() {
  return {
    name: "",
    code: "",
    level: "village",
    parentId: undefined,
    status: "active",
    sortOrder: 0,
    remark: "",
  };
}

function levelLabel(value) {
  return { province: "省级", county: "县级", town: "镇级", village: "村级" }[value] || value;
}

function childLevel(parentLevel) {
  return { province: "county", county: "town", town: "village" }[parentLevel] || "village";
}

async function loadRegions() {
  loading.value = true;
  try {
    const { data } = await fetchRegionTree();
    regionTree.value = data.data;
  } finally {
    loading.value = false;
  }
}

function openCreateDialog(parent) {
  editingId.value = 0;
  Object.assign(form, createEmptyForm(), {
    parentId: parent?.id,
    level: parent ? childLevel(parent.level) : "county",
    code: parent?.code || "",
  });
  formRef.value?.clearValidate();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingId.value = row.id;
  Object.assign(form, {
    name: row.name,
    code: row.code,
    level: row.level,
    parentId: row.parentId || undefined,
    status: row.status || "active",
    sortOrder: row.sortOrder || 0,
    remark: row.remark || "",
  });
  formRef.value?.clearValidate();
  dialogVisible.value = true;
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    return;
  }
  const payload = { ...form, name: form.name.trim(), code: form.code.trim(), remark: form.remark?.trim() || null };
  submitting.value = true;
  try {
    if (editingId.value) {
      await updateRegion(editingId.value, payload);
      ElMessage.success("区域已更新");
    } else {
      await createRegion(payload);
      ElMessage.success("区域已创建");
    }
    dialogVisible.value = false;
    await loadRegions();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存区域失败");
  } finally {
    submitting.value = false;
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除区域“${row.fullName}”吗？`, "删除区域", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteRegion(row.id);
    ElMessage.success("区域已删除");
    await loadRegions();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "删除区域失败");
    }
  }
}

loadRegions();
</script>
