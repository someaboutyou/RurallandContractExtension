<template>
  <section v-if="!canViewPage" class="panel page-grid">
    <div class="panel-title">人员权限</div>
    <el-empty description="当前账号暂无权限访问人员权限模块。" />
  </section>

  <section v-else class="panel table-page">
    <div class="toolbar">
      <div class="panel-title">人员权限</div>
      <div class="toolbar-actions">
        <el-button plain @click="refreshCurrentTab">刷新</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="manage-tabs">
      <el-tab-pane v-if="canViewUsers" label="用户管理" name="users">
        <div class="table-page">
          <div class="toolbar toolbar-wrap">
            <div class="toolbar-actions toolbar-wrap">
              <el-input
                v-model="userFilters.keyword"
                clearable
                placeholder="搜索登录账号或姓名"
                style="width: 220px"
                @keyup.enter="handleUserSearch"
              />
              <el-select v-model="userFilters.tenantCode" clearable placeholder="租户" style="width: 180px">
                <el-option v-for="item in tenantOptions" :key="item.code" :label="item.name" :value="item.code" />
              </el-select>
              <el-select v-model="userFilters.roleId" clearable placeholder="角色" style="width: 180px">
                <el-option v-for="item in roleOptions" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
              <el-select v-model="userFilters.status" clearable placeholder="状态" style="width: 140px">
                <el-option label="启用" value="active" />
                <el-option label="禁用" value="disabled" />
              </el-select>
              <el-button type="primary" @click="handleUserSearch">查询</el-button>
              <el-button @click="resetUserFilters">重置</el-button>
            </div>
            <div class="toolbar-actions">
              <el-button v-if="canManageUsers" type="success" @click="openCreateUserDialog">新增用户</el-button>
            </div>
          </div>

          <div class="table-shell">
            <div class="table-scroll">
              <el-table v-loading="usersLoading" :data="userRows" border>
                <el-table-column prop="username" label="登录账号" min-width="150" />
                <el-table-column prop="realName" label="姓名" min-width="120" />
                <el-table-column prop="tenantName" label="所属租户" min-width="150" />
                <el-table-column prop="mobile" label="手机号" min-width="140" />
                <el-table-column prop="role" label="角色" min-width="150">
                  <template #default="{ row }">
                    <div class="role-cell">
                      <span>{{ row.role }}</span>
                      <el-tag size="small" effect="plain">{{ dataScopeLabelMap[row.dataScope] || row.dataScope }}</el-tag>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="数据权限区域" min-width="300">
                  <template #default="{ row }">
                    <div class="permission-tags">
                      <el-tag
                        v-for="item in (row.regionPermissions || []).slice(0, 3)"
                        :key="item.regionCode"
                        size="small"
                        effect="plain"
                      >
                        {{ getRegionPermissionLabel(item) }}
                      </el-tag>
                      <el-tag v-if="(row.regionPermissions || []).length > 3" size="small" type="info" effect="light">
                        +{{ row.regionPermissions.length - 3 }}
                      </el-tag>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="status" label="状态" min-width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.status === 'active' ? 'success' : 'danger'" effect="light">
                      {{ row.status === "active" ? "启用" : "禁用" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column v-if="canManageUsers" label="操作" fixed="right" min-width="220">
                  <template #default="{ row }">
                    <div class="table-actions">
                      <el-button link type="primary" @click="openEditUserDialog(row)">编辑</el-button>
                      <el-button link type="warning" @click="openPasswordDialog(row)">重置密码</el-button>
                      <el-button link type="danger" @click="handleDeleteUser(row)">删除</el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>

          <div class="pagination-wrap">
            <el-pagination
              :current-page="userPage"
              :page-size="userPageSize"
              :page-sizes="[10, 20, 50, 100]"
              :total="userTotal"
              background
              layout="total, sizes, prev, pager, next, jumper"
              @current-change="handleUserPageChange"
              @size-change="handleUserPageSizeChange"
            />
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane v-if="canViewRoles" label="角色管理" name="roles">
        <div class="table-page">
          <div class="toolbar">
            <div class="toolbar-actions">
              <el-alert
                class="inline-alert"
                title="工作流审批依赖角色权限，请保留系统角色的审核权限配置。"
                type="warning"
                :closable="false"
              />
            </div>
            <div class="toolbar-actions">
              <el-button v-if="canManageRoles" type="success" @click="openCreateRoleDialog">新增角色</el-button>
            </div>
          </div>

          <div class="table-shell">
            <div class="table-scroll">
              <el-table v-loading="rolesLoading" :data="roleRows" border>
                <el-table-column prop="name" label="角色名称" min-width="160" />
                <el-table-column prop="code" label="角色编码" min-width="180" />
                <el-table-column prop="dataScope" label="数据范围" min-width="140">
                  <template #default="{ row }">
                    {{ dataScopeLabelMap[row.dataScope] || row.dataScope }}
                  </template>
                </el-table-column>
                <el-table-column prop="userCount" label="用户数" min-width="100" />
                <el-table-column label="权限项" min-width="260">
                  <template #default="{ row }">
                    <div class="permission-tags">
                      <el-tag
                        v-for="code in row.permissionCodes.slice(0, 4)"
                        :key="code"
                        size="small"
                        effect="plain"
                      >
                        {{ permissionLabelMap[code] || code }}
                      </el-tag>
                      <el-tag v-if="row.permissionCodes.length > 4" size="small" type="info" effect="light">
                        +{{ row.permissionCodes.length - 4 }}
                      </el-tag>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
                <el-table-column label="类型" min-width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.isSystem ? 'success' : 'info'" effect="light">
                      {{ row.isSystem ? "系统" : "自定义" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column v-if="canManageRoles" label="操作" fixed="right" min-width="160">
                  <template #default="{ row }">
                    <div class="table-actions">
                      <el-button link type="primary" @click="openEditRoleDialog(row)">编辑</el-button>
                      <el-button
                        link
                        type="danger"
                        :disabled="row.isSystem || row.userCount > 0"
                        @click="handleDeleteRole(row)"
                      >
                        删除
                      </el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </section>

  <el-dialog
    v-model="userDialogVisible"
    :title="editingUserId ? '编辑用户' : '新增用户'"
    width="760px"
    destroy-on-close
  >
    <el-form ref="userFormRef" :model="userForm" :rules="userRules" class="compact-form" label-position="top" status-icon>
      <div class="form-grid">
        <el-form-item label="登录账号" prop="username">
          <el-input v-model="userForm.username" placeholder="请输入登录账号" />
        </el-form-item>
        <el-form-item v-if="!editingUserId" label="初始密码" prop="password">
          <el-input v-model="userForm.password" show-password placeholder="请输入初始密码" />
        </el-form-item>
        <el-form-item v-else label="用户状态" prop="status">
          <el-select v-model="userForm.status" placeholder="请选择用户状态">
            <el-option label="启用" value="active" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="姓名" prop="realName">
          <el-input v-model="userForm.realName" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="手机号" prop="mobile">
          <el-input v-model="userForm.mobile" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="所属租户">
          <el-input :model-value="selectedTenantName" disabled placeholder="根据数据权限区域自动确定" />
        </el-form-item>
        <el-form-item label="角色" prop="roleId">
          <el-select v-model="userForm.roleId" placeholder="请选择角色">
            <el-option v-for="item in roleOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item class="form-span-2" label="数据权限区域" prop="regionCodes">
          <el-tree-select
            v-model="userForm.regionCodes"
            multiple
            show-checkbox
            filterable
            lazy
            collapse-tags
            collapse-tags-tooltip
            check-strictly
            :data="assignableRegionPermissionTree"
            :props="regionTreeProps"
            :load="loadRegionPermissionNode"
            :filter-method="handleRegionPermissionFilter"
            node-key="code"
            placeholder="请选择可操作区域"
          />
        </el-form-item>
        <el-form-item v-if="!editingUserId" label="用户状态" prop="status">
          <el-select v-model="userForm.status" placeholder="请选择用户状态">
            <el-option label="启用" value="active" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
      </div>
    </el-form>

    <template #footer>
      <el-button @click="userDialogVisible = false">取消</el-button>
      <el-button :loading="userSubmitting" type="success" @click="handleSubmitUser">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="roleDialogVisible" :title="editingRoleId ? '编辑角色' : '新增角色'" width="860px" destroy-on-close>
    <el-form ref="roleFormRef" :model="roleForm" :rules="roleRules" class="compact-form" label-position="top" status-icon>
      <div class="form-grid">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="roleForm.name" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="角色编码" prop="code">
          <el-input v-model="roleForm.code" :disabled="editingRoleSystem" placeholder="请输入角色编码" />
        </el-form-item>
        <el-form-item label="数据范围" prop="dataScope">
          <el-select v-model="roleForm.dataScope" placeholder="请选择数据范围">
            <el-option v-for="item in dataScopeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item class="form-span-2" label="说明" prop="description">
          <el-input v-model="roleForm.description" type="textarea" :rows="3" placeholder="请输入角色说明" />
        </el-form-item>
        <el-form-item class="form-span-2" label="角色权限">
          <div class="permission-panel">
            <el-tabs v-model="activePermissionGroup" class="permission-tabs">
              <el-tab-pane
                v-for="group in permissionGroups"
                :key="group.name"
                :label="`${group.name}（${group.items.length}）`"
                :name="group.name"
              >
                <div class="permission-group permission-group-pane">
                  <div class="permission-group-title">{{ group.name }}</div>
                  <el-checkbox-group v-model="roleForm.permissionCodes" class="permission-check-grid">
                    <el-checkbox v-for="item in group.items" :key="item.code" :label="item.code">
                      {{ item.name }}
                    </el-checkbox>
                  </el-checkbox-group>
                </div>
              </el-tab-pane>
            </el-tabs>
          </div>
        </el-form-item>
      </div>
    </el-form>

    <template #footer>
      <el-button @click="roleDialogVisible = false">取消</el-button>
      <el-button :loading="roleSubmitting" type="success" @click="handleSubmitRole">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="passwordDialogVisible" title="重置密码" width="420px" destroy-on-close>
    <el-form
      ref="passwordFormRef"
      :model="passwordForm"
      :rules="passwordRules"
      class="compact-form"
      label-position="top"
      status-icon
    >
      <el-form-item label="新密码" prop="password">
        <el-input v-model="passwordForm.password" show-password placeholder="请输入新密码" />
      </el-form-item>
      <el-form-item label="确认密码" prop="confirmPassword">
        <el-input v-model="passwordForm.confirmPassword" show-password placeholder="请再次输入新密码" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="passwordDialogVisible = false">取消</el-button>
      <el-button :loading="passwordSubmitting" type="warning" @click="handleResetPassword">确认重置</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, onUnmounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { fetchPermissions } from "../api/permission";
import { fetchRegionChildren, fetchRegions, searchRegions } from "../api/region";
import { createRole, deleteRole, fetchRoles, updateRole } from "../api/role";
import { fetchTenants } from "../api/tenant";
import { createUser, deleteUser, fetchUsers, resetUserPassword, updateUser } from "../api/user";
import { useAuthStore } from "../stores/auth";
import { validateMobile } from "../utils/validators";

const authStore = useAuthStore();

const canViewUsers = computed(() => authStore.hasPermission("users.view"));
const canManageUsers = computed(() => authStore.hasPermission("users.manage"));
const canViewRoles = computed(() => authStore.hasPermission("roles.view"));
const canManageRoles = computed(() => authStore.hasPermission("roles.manage"));
const canViewPage = computed(() => canViewUsers.value || canViewRoles.value);

const activeTab = ref(canViewUsers.value ? "users" : "roles");
const activePermissionGroup = ref("");
const usersLoading = ref(false);
const rolesLoading = ref(false);
const userSubmitting = ref(false);
const roleSubmitting = ref(false);
const passwordSubmitting = ref(false);

const userRows = ref([]);
const roleRows = ref([]);
const roleOptions = ref([]);
const regionOptions = ref([]);
const regionPermissionTree = ref([]);
const regionTreeProps = { label: "fullName", children: "children", disabled: "disabled", isLeaf: "leaf" };
const selectedRegionMap = ref(new Map());
const tenantOptions = ref([]);
const permissionsCatalog = ref([]);

const userPage = ref(1);
const userPageSize = ref(20);
const userTotal = ref(0);

const userDialogVisible = ref(false);
const roleDialogVisible = ref(false);
const passwordDialogVisible = ref(false);
const editingUserId = ref(0);
const editingRoleId = ref(0);
const editingRoleSystem = ref(false);
const passwordTargetUserId = ref(0);
let regionPermissionSearchTimer = null;

const userFormRef = ref();
const roleFormRef = ref();
const passwordFormRef = ref();

const dataScopeOptions = [
  { value: "all", label: "全部数据" },
  { value: "county", label: "县级范围" },
  { value: "town", label: "镇级范围" },
  { value: "village", label: "村级范围" },
  { value: "self", label: "本人数据" },
];

const dataScopeLabelMap = dataScopeOptions.reduce((result, item) => {
  result[item.value] = item.label;
  return result;
}, {});

const permissionGroups = computed(() => {
  const result = new Map();
  for (const item of permissionsCatalog.value) {
    if (!result.has(item.groupName)) {
      result.set(item.groupName, []);
    }
    result.get(item.groupName).push(item);
  }
  return Array.from(result.entries()).map(([name, items]) => ({ name, items }));
});

const permissionLabelMap = computed(() =>
  permissionsCatalog.value.reduce((result, item) => {
    result[item.code] = item.name;
    return result;
  }, {}),
);

const assignableRegionPermissionTree = computed(() =>
  markAssignedGroupNodes(regionPermissionTree.value, editingUserId.value),
);

const selectedTenantName = computed(() => {
  const firstRegionCode = userForm.regionCodes[0];
  if (!firstRegionCode) {
    return "";
  }
  const selectedRegion =
    regionOptions.value.find((item) => item.code === firstRegionCode) ||
    selectedRegionMap.value.get(firstRegionCode) ||
    findRegionTreeNode(regionPermissionTree.value, firstRegionCode);
  const tenantCode = selectedRegion?.tenantCode || firstRegionCode.slice(0, 6);
  const tenant = tenantOptions.value.find((item) => item.code === tenantCode);
  return tenant?.name || tenantCode;
});

const createEmptyUserFilters = () => ({
  keyword: "",
  tenantCode: "",
  roleId: undefined,
  status: "",
});

const createEmptyUserForm = () => ({
  username: "",
  realName: "",
  password: "",
  mobile: "",
  roleId: undefined,
  regionCodes: [],
  status: "active",
});

const createEmptyRoleForm = () => ({
  name: "",
  code: "",
  dataScope: "town",
  description: "",
  permissionCodes: [],
});

const createEmptyPasswordForm = () => ({
  password: "",
  confirmPassword: "",
});

const userFilters = reactive(createEmptyUserFilters());
const userForm = reactive(createEmptyUserForm());
const roleForm = reactive(createEmptyRoleForm());
const passwordForm = reactive(createEmptyPasswordForm());

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

const validatePasswordConfirm = (_rule, value, callback) => {
  if (!value) {
    callback(new Error("请再次输入新密码"));
    return;
  }
  if (value !== passwordForm.password) {
    callback(new Error("两次输入的密码不一致"));
    return;
  }
  callback();
};

const userRules = {
  username: [{ required: true, message: "请输入登录账号", trigger: "blur" }],
  realName: [{ required: true, message: "请输入姓名", trigger: "blur" }],
  password: [{ required: true, message: "请输入初始密码", trigger: "blur" }],
  mobile: [{ validator: validateMobileField, trigger: "blur" }],
  roleId: [{ required: true, message: "请选择角色", trigger: "change" }],
  regionCodes: [{ required: true, type: "array", min: 1, message: "请选择数据权限区域", trigger: "change" }],
  status: [{ required: true, message: "请选择用户状态", trigger: "change" }],
};

const roleRules = {
  name: [{ required: true, message: "请输入角色名称", trigger: "blur" }],
  code: [{ required: true, message: "请输入角色编码", trigger: "blur" }],
  dataScope: [{ required: true, message: "请选择数据范围", trigger: "change" }],
};

const passwordRules = {
  password: [{ required: true, message: "请输入新密码", trigger: "blur" }],
  confirmPassword: [{ validator: validatePasswordConfirm, trigger: "blur" }],
};

function resetUserForm() {
  Object.assign(userForm, createEmptyUserForm());
  userFormRef.value?.clearValidate();
}

function resetRoleForm() {
  Object.assign(roleForm, createEmptyRoleForm());
  roleFormRef.value?.clearValidate();
}

function resetPasswordForm() {
  Object.assign(passwordForm, createEmptyPasswordForm());
  passwordFormRef.value?.clearValidate();
}

async function loadUsers() {
  if (!canViewUsers.value) {
    return;
  }
  usersLoading.value = true;
  try {
    const { data } = await fetchUsers({
      page: userPage.value,
      page_size: userPageSize.value,
      keyword: userFilters.keyword || undefined,
      tenant_code: userFilters.tenantCode || undefined,
      role_id: userFilters.roleId,
      status: userFilters.status || undefined,
    });
    userRows.value = data.data.items;
    userTotal.value = data.data.total;
  } finally {
    usersLoading.value = false;
  }
}

async function loadRoles() {
  if (!canViewRoles.value) {
    return;
  }
  rolesLoading.value = true;
  try {
    const { data } = await fetchRoles();
    roleRows.value = data.data;
    roleOptions.value = data.data;
  } finally {
    rolesLoading.value = false;
  }
}

async function loadBaseOptions() {
  const tasks = [];

  if (canViewRoles.value) {
    tasks.push(
      fetchRoles().then(({ data }) => {
        roleRows.value = data.data;
        roleOptions.value = data.data;
      }),
      fetchPermissions().then(({ data }) => {
        permissionsCatalog.value = data.data;
      }),
    );
  }

  if (canViewUsers.value || canManageUsers.value) {
    tasks.push(
      fetchRegions().then(({ data }) => {
        regionOptions.value = data.data;
      }),
      fetchRegionChildren({ includeGroups: true }).then(({ data }) => {
        regionPermissionTree.value = data.data;
        rememberRegions(regionPermissionTree.value);
      }),
      fetchTenants().then(({ data }) => {
        tenantOptions.value = data.data;
      }),
    );
  }

  await Promise.all(tasks);
  if (!activePermissionGroup.value && permissionGroups.value.length) {
    activePermissionGroup.value = permissionGroups.value[0].name;
  }
}

async function bootstrapPage() {
  if (!canViewPage.value) {
    return;
  }
  await loadBaseOptions();
  if (canViewUsers.value) {
    await loadUsers();
  }
}

function refreshCurrentTab() {
  if (activeTab.value === "users") {
    loadUsers();
    return;
  }
  loadRoles();
}

function handleUserSearch() {
  userPage.value = 1;
  loadUsers();
}

function resetUserFilters() {
  Object.assign(userFilters, createEmptyUserFilters());
  userPage.value = 1;
  loadUsers();
}

function handleUserPageChange(value) {
  userPage.value = value;
  loadUsers();
}

function handleUserPageSizeChange(value) {
  userPageSize.value = value;
  userPage.value = 1;
  loadUsers();
}

function openCreateUserDialog() {
  editingUserId.value = 0;
  resetUserForm();
  userDialogVisible.value = true;
}

function getRegionPermissionLabel(item) {
  const region = regionOptions.value.find((option) => option.code === item.regionCode);
  return region?.fullName || selectedRegionMap.value.get(item.regionCode)?.fullName || findRegionTreeNode(regionPermissionTree.value, item.regionCode)?.fullName || item.regionCode;
}

function findRegionTreeNode(nodes, code) {
  for (const node of nodes) {
    if (node.code === code) {
      return node;
    }
    const matched = findRegionTreeNode(node.children || [], code);
    if (matched) {
      return matched;
    }
  }
  return null;
}

function rememberRegions(nodes) {
  for (const item of nodes || []) {
    selectedRegionMap.value.set(item.code, item);
    rememberRegions(item.children || []);
  }
}

async function loadRegionPermissionNode(node, resolve) {
  if (node.level === 0) {
    resolve(regionPermissionTree.value);
    return;
  }
  const { data } = await fetchRegionChildren({ parentId: node.data.id, includeGroups: true });
  rememberRegions(data.data);
  resolve(markAssignedGroupNodes(data.data, editingUserId.value));
}

function handleRegionPermissionFilter(keyword) {
  window.clearTimeout(regionPermissionSearchTimer);
  regionPermissionSearchTimer = window.setTimeout(async () => {
    if (!keyword) {
      const { data } = await fetchRegionChildren({ includeGroups: true });
      regionPermissionTree.value = data.data;
      rememberRegions(regionPermissionTree.value);
      return;
    }
    const { data } = await searchRegions({ keyword, includeGroups: true, limit: 100 });
    regionPermissionTree.value = data.data;
    rememberRegions(regionPermissionTree.value);
  }, 250);
}

function markAssignedGroupNodes(nodes, currentUserId) {
  return nodes.map((node) => {
    const assignedToOtherUser = node.level === "group" && node.assignedUserId && node.assignedUserId !== currentUserId;
    return {
      ...node,
      disabled: assignedToOtherUser,
      fullName: assignedToOtherUser ? `${node.fullName}（已分配）` : node.fullName,
      children: markAssignedGroupNodes(node.children || [], currentUserId),
    };
  });
}

function openEditUserDialog(row) {
  editingUserId.value = row.id;
  Object.assign(userForm, {
    username: row.username,
    realName: row.realName,
    password: "",
    mobile: row.mobile || "",
    roleId: row.roleId,
    regionCodes: (row.regionPermissions || []).map((item) => item.regionCode),
    status: row.status,
  });
  userFormRef.value?.clearValidate();
  userDialogVisible.value = true;
}

async function handleSubmitUser() {
  const valid = await userFormRef.value.validate().catch(() => false);
  if (!valid) {
    ElMessage.warning("请先修正用户表单中的校验问题");
    return;
  }

  const payload = {
    username: userForm.username.trim(),
    realName: userForm.realName.trim(),
    mobile: userForm.mobile.trim() || null,
    roleId: userForm.roleId,
    regionCodes: [...userForm.regionCodes],
    status: userForm.status,
  };

  userSubmitting.value = true;
  try {
    if (editingUserId.value) {
      await updateUser(editingUserId.value, payload);
      ElMessage.success("用户已更新");
    } else {
      await createUser({ ...payload, password: userForm.password });
      ElMessage.success("用户已创建");
    }
    userDialogVisible.value = false;
    resetUserForm();
    await loadUsers();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存用户失败");
  } finally {
    userSubmitting.value = false;
  }
}

function openPasswordDialog(row) {
  passwordTargetUserId.value = row.id;
  resetPasswordForm();
  passwordDialogVisible.value = true;
}

async function handleResetPassword() {
  const valid = await passwordFormRef.value.validate().catch(() => false);
  if (!valid) {
    ElMessage.warning("请先修正密码校验问题");
    return;
  }

  passwordSubmitting.value = true;
  try {
    await resetUserPassword(passwordTargetUserId.value, { password: passwordForm.password });
    ElMessage.success("密码已重置");
    passwordDialogVisible.value = false;
    resetPasswordForm();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "重置密码失败");
  } finally {
    passwordSubmitting.value = false;
  }
}

async function handleDeleteUser(row) {
  try {
    await ElMessageBox.confirm(`确定删除用户“${row.realName}”吗？该操作不可恢复。`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteUser(row.id);
    ElMessage.success("用户已删除");
    if (userRows.value.length === 1 && userPage.value > 1) {
      userPage.value -= 1;
    }
    await loadUsers();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "删除用户失败");
    }
  }
}

function openCreateRoleDialog() {
  editingRoleId.value = 0;
  editingRoleSystem.value = false;
  resetRoleForm();
  activePermissionGroup.value = permissionGroups.value[0]?.name || "";
  roleDialogVisible.value = true;
}

function openEditRoleDialog(row) {
  editingRoleId.value = row.id;
  editingRoleSystem.value = row.isSystem;
  Object.assign(roleForm, {
    name: row.name,
    code: row.code,
    dataScope: row.dataScope,
    description: row.description || "",
    permissionCodes: [...row.permissionCodes],
  });
  activePermissionGroup.value = permissionGroups.value[0]?.name || "";
  roleFormRef.value?.clearValidate();
  roleDialogVisible.value = true;
}

async function handleSubmitRole() {
  const valid = await roleFormRef.value.validate().catch(() => false);
  if (!valid) {
    ElMessage.warning("请先修正角色表单中的校验问题");
    return;
  }

  const payload = {
    name: roleForm.name.trim(),
    code: roleForm.code.trim(),
    dataScope: roleForm.dataScope,
    description: roleForm.description.trim() || null,
    permissionCodes: [...roleForm.permissionCodes],
  };

  roleSubmitting.value = true;
  try {
    if (editingRoleId.value) {
      await updateRole(editingRoleId.value, payload);
      ElMessage.success("角色已更新");
    } else {
      await createRole(payload);
      ElMessage.success("角色已创建");
    }
    roleDialogVisible.value = false;
    resetRoleForm();
    await loadRoles();
    if (canViewUsers.value) {
      await loadUsers();
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存角色失败");
  } finally {
    roleSubmitting.value = false;
  }
}

async function handleDeleteRole(row) {
  try {
    await ElMessageBox.confirm(`确定删除角色“${row.name}”吗？该操作不可恢复。`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteRole(row.id);
    ElMessage.success("角色已删除");
    await loadRoles();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "删除角色失败");
    }
  }
}

bootstrapPage();
onUnmounted(() => {
  window.clearTimeout(regionPermissionSearchTimer);
});
</script>
