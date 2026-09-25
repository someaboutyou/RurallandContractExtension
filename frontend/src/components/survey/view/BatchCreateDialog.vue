<template>
  <el-dialog :model-value="modelValue" title="新建调查批次" width="640px" @update:model-value="$emit('update:modelValue', $event)">
    <el-alert
      title="创建后会把当前正式承包方和家庭成员数据复制为调查前快照，并同步生成可编辑的调查结果。"
      type="info"
      show-icon
      :closable="false"
    >
      已经有进行中批次的区域（以及它的上级区域）会置灰不可选，避免重复初始化同一片区域。
    </el-alert>
    <el-form :model="batchForm" label-position="top" class="survey-dialog-form">
      <el-form-item label="批次名称">
        <el-input v-model="batchForm.batchName" placeholder="例如：2026年二轮延包承包方串户调查" />
      </el-form-item>
      <el-form-item label="区域代码">
        <el-tree-select
          v-model="batchForm.regionId"
          clearable
          filterable
          lazy
          check-strictly
          :data="batchRegionTree"
          :props="batchRegionTreeProps"
          :load="loadBatchRegionNode"
          :filter-method="handleBatchRegionFilter"
          node-key="id"
          placeholder="请选择调查区域；为空则按权限范围初始化"
          @change="handleBatchRegionChange"
        >
          <template #default="{ data }">
            <span class="batch-region-option" :class="{ 'is-initialized': data.disabled }">
              <span class="batch-region-option-name">{{ data.fullName }}</span>
              <span v-if="data.initializedLabel" class="batch-region-option-hint">{{ data.initializedLabel }}</span>
            </span>
          </template>
        </el-tree-select>
      </el-form-item>
      <!-- 指派调查员：只有**管理员**需要、也可以选择（能指派他人）。
           其他人新建批次一律自动派给自己——不显示选择器、也不把 assigneeIds 发给后端，
           由后端按角色再校验一次（非管理员传别人会 403），防止界面藏了控件接口还能打。 -->
      <el-form-item v-if="isAdmin" label="指派调查员" required>
        <el-select
          v-model="batchForm.assigneeIds"
          multiple
          filterable
          clearable
          :loading="assigneeLoading"
          placeholder="请至少选择一名调查员"
          style="width: 100%"
        >
          <el-option
            v-for="user in assigneeOptions"
            :key="user.id"
            :value="user.id"
            :label="user.realName"
            :disabled="!user.coversRegion"
          >
            <span>{{ user.realName }}</span>
            <span class="assign-option-meta">
              {{ user.roleName || "—" }}<template v-if="!user.coversRegion"> · 管辖范围不含所选区域</template>
            </span>
          </el-option>
        </el-select>
        <div class="assignee-tip">
          必填。选择多名调查员时，会按承包方编码顺序把本批次全部户轮流均分到各人名下，
          保证创建后每户都有归属调查员；创建后仍可在调查列表里勾选承包方改派。
        </div>
      </el-form-item>
      <el-alert
        v-else
        class="assignee-self-tip"
        type="info"
        :closable="false"
        show-icon
        :title="`创建后本批次全部承包户会自动指派给您本人（${authStore.displayName}）`"
      >
        只有管理员可以指派其他调查员，如需安排他人负责，请联系管理员创建批次。
      </el-alert>
      <el-form-item label="备注">
        <el-input v-model="batchForm.remark" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button :loading="submittingBatch" type="success" @click="handleCreateBatch">创建并初始化</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { createSurveyBatch, fetchActiveSurveyBatches, fetchSurveyAssignees } from "../../../api/survey";
import { fetchRegionChildren, searchRegions } from "../../../api/region";
import { useAuthStore } from "../../../stores/auth";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "created"]);

const authStore = useAuthStore();
// 只有管理员能指派他人；其他人新建批次一律派给自己（后端同口径再校验一次）。
const isAdmin = computed(() => authStore.user?.dataScope === "all");

const submittingBatch = ref(false);
// 可指派的调查员（不绑定批次，按所选区域顺带算出 coversRegion）。
const assigneeOptions = ref([]);
const assigneeLoading = ref(false);
const batchRegionTree = ref([]);
// 进行中的调查批次快照（区域码 + 创建人），用来把已初始化的区域置灰。
const initializedBatches = ref([]);
// disabled 用函数形式：节点数据在 resolve 时就被打上标记，树上同步生效。
const batchRegionTreeProps = {
  label: "fullName",
  children: "children",
  isLeaf: "leaf",
  disabled: (data) => Boolean(data?.disabled),
};
const rememberedBatchRegions = new Map();
let batchRegionSearchTimer = null;

const batchForm = reactive({
  batchName: "",
  regionId: undefined,
  regionCode: "",
  regionName: "",
  remark: "",
  assigneeIds: [],
});

function rememberBatchRegions(nodes) {
  for (const node of nodes || []) {
    rememberedBatchRegions.set(node.id, node);
    rememberBatchRegions(node.children);
  }
}

/**
 * 找到与当前节点冲突的进行中批次。
 * 口径与后端 create_batch 的校验一致：只要「该区域本身或它的下级区域」已有进行中批次，
 * 选中本节点就会报错，因此这里连带把上级节点一起置灰。
 * 反向不成立（上级有批次、下级仍可选），所以不做祖先判断。
 */
function findBlockingBatch(code) {
  if (!code) return null;
  return initializedBatches.value.find((item) => item.regionCode && item.regionCode.startsWith(code)) || null;
}

function initializedLabel(batch) {
  // 创建人只有管理员接口才会返回；普通用户只知道「已初始化」，看不到是谁做的。
  if (!batch.createdById) return "已初始化";
  return `已初始化：${batch.createdByName || "未知用户"}（${batch.batchNo}）`;
}

function decorateRegionNodes(nodes) {
  for (const node of nodes || []) {
    const blocking = findBlockingBatch(node.code);
    node.disabled = Boolean(blocking);
    node.initializedLabel = blocking ? initializedLabel(blocking) : "";
    decorateRegionNodes(node.children);
  }
  return nodes;
}

async function refreshInitializedBatches() {
  try {
    const { data } = await fetchActiveSurveyBatches();
    initializedBatches.value = data.data || [];
  } catch (error) {
    // 拿不到冲突清单时不拦人，交由后端在提交时兜底报错。
    initializedBatches.value = [];
  }
}

async function loadBatchRegionNode(node, resolve) {
  if (node.level === 0) {
    resolve(batchRegionTree.value);
    return;
  }
  const { data } = await fetchRegionChildren({ parentId: node.data.id, includeGroups: true });
  const children = decorateRegionNodes(data.data);
  rememberBatchRegions(children);
  resolve(children);
}

function handleBatchRegionFilter(keyword) {
  window.clearTimeout(batchRegionSearchTimer);
  batchRegionSearchTimer = window.setTimeout(async () => {
    if (!keyword) {
      const { data } = await fetchRegionChildren({ includeGroups: true });
      batchRegionTree.value = decorateRegionNodes(data.data);
      rememberBatchRegions(batchRegionTree.value);
      return;
    }
    const { data } = await searchRegions({ keyword, includeGroups: true, limit: 100 });
    batchRegionTree.value = decorateRegionNodes(data.data);
    rememberBatchRegions(batchRegionTree.value);
  }, 250);
}

async function loadAssigneeOptions(regionCode) {
  // 非管理员看不到选择器，也就没必要拉名单（接口本身要 contractors.manage）。
  if (!isAdmin.value) {
    assigneeOptions.value = [];
    return;
  }
  assigneeLoading.value = true;
  try {
    const { data } = await fetchSurveyAssignees({ regionCode: regionCode || undefined });
    assigneeOptions.value = data.data || [];
  } catch (error) {
    assigneeOptions.value = [];
    ElMessage.error(error.response?.data?.detail || "加载调查员名单失败，无法创建批次");
  } finally {
    assigneeLoading.value = false;
  }
}

function handleBatchRegionChange(value) {
  const selected = rememberedBatchRegions.get(value);
  batchForm.regionCode = selected?.code || "";
  batchForm.regionName = selected?.fullName || "";
  if (selected) {
    batchForm.batchName = (selected.name || "") + "调查批次";
  }
  if (!isAdmin.value) return;
  // 换了区域，管辖范围判定要跟着重算；已选中但不再覆盖新区域的人直接摘掉，
  // 免得提交时才被后端以「管辖区域不包含本调查批次范围」打回。
  loadAssigneeOptions(batchForm.regionCode).then(() => {
    const usable = new Set(assigneeOptions.value.filter((item) => item.coversRegion).map((item) => item.id));
    batchForm.assigneeIds = batchForm.assigneeIds.filter((id) => usable.has(id));
  });
}

async function open(activeRegionCode, activeRegionLabel) {
  const selectedRegion = [...rememberedBatchRegions.values()].find((item) => item.code === activeRegionCode);
  Object.assign(batchForm, {
    batchName: selectedRegion ? (selectedRegion.name || "") + "调查批次" : "",
    regionId: selectedRegion?.id,
    regionCode: selectedRegion?.code || "",
    regionName: selectedRegion?.fullName || "",
    remark: "",
    assigneeIds: [],
  });
  emit("update:modelValue", true);
  await loadAssigneeOptions(batchForm.regionCode || activeRegionCode);
  // 每次打开都重拉一次冲突清单：期间可能已经有别人初始化了某个区域。
  await refreshInitializedBatches();
  if (batchRegionTree.value.length) {
    // 已加载过就地重刷标记，不重建树，免得丢掉已展开的层级和已选节点。
    decorateRegionNodes(batchRegionTree.value);
    return;
  }
  await rebuildRegionTree();
}

async function rebuildRegionTree() {
  const { data } = await fetchRegionChildren({ includeGroups: true });
  batchRegionTree.value = decorateRegionNodes(data.data);
  rememberBatchRegions(batchRegionTree.value);
}

async function initRegionTree() {
  await refreshInitializedBatches();
  await rebuildRegionTree();
}

async function handleCreateBatch() {
  if (!batchForm.batchName.trim()) {
    ElMessage.warning("请输入批次名称");
    return;
  }
  if (!batchForm.regionCode) {
    ElMessage.warning("请选择调查区域");
    return;
  }
  // 管理员：指派调查员是必填（创建时就要把本批次全部户落到人头上）；
  // 其他人：不显示选择器，后端会自动派给本人，前端不校验也不提交该字段。
  if (isAdmin.value && !batchForm.assigneeIds.length) {
    ElMessage.warning("请至少指派一名调查员，保证每个承包户都有归属人");
    return;
  }
  submittingBatch.value = true;
  try {
    await createSurveyBatch({
      ...batchForm,
      batchName: batchForm.batchName.trim(),
      regionId: undefined,
      // 非管理员不发 assigneeIds：让后端按角色统一归一成「派给自己」，
      // 免得前端自己拼一个 id 出去、被后端当越权请求打回。
      assigneeIds: isAdmin.value ? batchForm.assigneeIds : undefined,
    });
    ElMessage.success("调查批次已创建并初始化");
    emit("update:modelValue", false);
    emit("created");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "创建调查批次失败");
  } finally {
    submittingBatch.value = false;
  }
}

defineExpose({ open, initRegionTree });
</script>

<style scoped>
.survey-dialog-form {
  margin-top: 16px;
}

.batch-region-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.batch-region-option-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.batch-region-option-hint {
  flex: none;
  font-size: 12px;
  color: var(--el-color-warning);
}

.assign-option-meta {
  float: right;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 12px;
}

.assignee-tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
  margin-top: 4px;
}

/* 非管理员：没有选择器，用一条提示说明「自动派给自己」。 */
.assignee-self-tip {
  margin-bottom: 18px;
}
</style>
