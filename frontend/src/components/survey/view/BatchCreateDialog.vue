<template>
  <el-dialog :model-value="modelValue" title="新建调查批次" width="640px" @update:model-value="$emit('update:modelValue', $event)">
    <el-alert
      title="创建后会把当前正式承包方和家庭成员数据复制为调查前快照，并同步生成可编辑的调查结果。"
      type="info"
      show-icon
      :closable="false"
    />
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
        />
      </el-form-item>
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
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { createSurveyBatch } from "../../../api/survey";
import { fetchRegionChildren, searchRegions } from "../../../api/region";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "created"]);

const submittingBatch = ref(false);
const batchRegionTree = ref([]);
const batchRegionTreeProps = { label: "fullName", children: "children", isLeaf: "leaf" };
const rememberedBatchRegions = new Map();
let batchRegionSearchTimer = null;

const batchForm = reactive({
  batchName: "",
  regionId: undefined,
  regionCode: "",
  regionName: "",
  remark: "",
});

function rememberBatchRegions(nodes) {
  for (const node of nodes || []) {
    rememberedBatchRegions.set(node.id, node);
    rememberBatchRegions(node.children);
  }
}

async function loadBatchRegionNode(node, resolve) {
  if (node.level === 0) {
    resolve(batchRegionTree.value);
    return;
  }
  const { data } = await fetchRegionChildren({ parentId: node.data.id, includeGroups: true });
  rememberBatchRegions(data.data);
  resolve(data.data);
}

function handleBatchRegionFilter(keyword) {
  window.clearTimeout(batchRegionSearchTimer);
  batchRegionSearchTimer = window.setTimeout(async () => {
    if (!keyword) {
      const { data } = await fetchRegionChildren({ includeGroups: true });
      batchRegionTree.value = data.data;
      rememberBatchRegions(batchRegionTree.value);
      return;
    }
    const { data } = await searchRegions({ keyword, includeGroups: true, limit: 100 });
    batchRegionTree.value = data.data;
    rememberBatchRegions(batchRegionTree.value);
  }, 250);
}

function handleBatchRegionChange(value) {
  const selected = rememberedBatchRegions.get(value);
  batchForm.regionCode = selected?.code || "";
  batchForm.regionName = selected?.fullName || "";
  if (selected) {
    batchForm.batchName = (selected.name || "") + "调查批次";
  }
}

function open(activeRegionCode, activeRegionLabel) {
  const selectedRegion = [...rememberedBatchRegions.values()].find((item) => item.code === activeRegionCode);
  Object.assign(batchForm, {
    batchName: selectedRegion ? (selectedRegion.name || "") + "调查批次" : "",
    regionId: selectedRegion?.id,
    regionCode: selectedRegion?.code || "",
    regionName: selectedRegion?.fullName || "",
    remark: "",
  });
  emit("update:modelValue", true);
}

async function initRegionTree() {
  const { data } = await fetchRegionChildren({ includeGroups: true });
  batchRegionTree.value = data.data;
  rememberBatchRegions(batchRegionTree.value);
}

async function handleCreateBatch() {
  if (!batchForm.batchName.trim()) {
    ElMessage.warning("请输入批次名称");
    return;
  }
  submittingBatch.value = true;
  try {
    await createSurveyBatch({
      ...batchForm,
      batchName: batchForm.batchName.trim(),
      regionId: undefined,
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
</style>
