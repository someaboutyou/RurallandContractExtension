<template>
  <el-dialog
    :model-value="modelValue"
    title="数据初始化"
    width="760px"
    top="8vh"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="init-head">
      已勾选 <strong>{{ rows.length }}</strong> 个承包地块，初始化仅对勾选地块生效。
    </div>

    <el-tabs v-model="activeTab" class="init-tabs">
      <el-tab-pane label="基础信息初始化" name="basic">
        <div class="init-grid">
          <div v-for="field in fields" :key="field.key" class="init-row">
            <el-checkbox v-model="enabled[field.key]" class="init-check">
              {{ field.label }}
            </el-checkbox>
            <el-select
              v-model="values[field.key]"
              :disabled="!enabled[field.key]"
              clearable
              filterable
              placeholder="请选择"
              style="width: 100%"
            >
              <el-option
                v-for="option in field.options"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>

          <div class="init-row">
            <el-checkbox v-model="enabled.awareArea" class="init-check">确权面积</el-checkbox>
            <el-select
              v-model="values.awareArea"
              :disabled="!enabled.awareArea"
              placeholder="请选择初始化方式"
              style="width: 100%"
            >
              <el-option label="按实测面积" value="actual" />
              <el-option label="按合同面积" value="contract" />
            </el-select>
          </div>

          <div class="init-row init-row-tall">
            <el-checkbox v-model="enabled.referPerson" class="init-check">指界人</el-checkbox>
            <div class="init-inline">
              <el-input
                v-model="values.referPerson"
                :disabled="!enabled.referPerson || referPersonByOwner"
                maxlength="100"
                placeholder="请输入指界人"
              />
              <el-checkbox v-model="referPersonByOwner" :disabled="!enabled.referPerson">
                按户主姓名
              </el-checkbox>
            </div>
          </div>

          <div class="init-row">
            <el-checkbox v-model="enabled.comment" class="init-check">地块备注</el-checkbox>
            <el-input
              v-model="values.comment"
              :disabled="!enabled.comment"
              maxlength="300"
              placeholder="请输入地块备注"
            />
          </div>
        </div>

        <div class="init-options">
          <el-checkbox v-model="initializeNull">仅初始化空值</el-checkbox>
          <el-checkbox v-model="onlyContractParcels">仅处理承包地块（地块类别 10）</el-checkbox>
        </div>
      </el-tab-pane>

      <el-tab-pane label="地块编码与四至获取" name="code">
        <el-empty description="功能建设中，后续接入" :image-size="80" />
      </el-tab-pane>
      <el-tab-pane label="图幅编号" name="sheet">
        <el-empty description="功能建设中，后续接入" :image-size="80" />
      </el-tab-pane>
      <el-tab-pane label="界址初始化" name="boundary">
        <el-empty description="功能建设中，后续接入" :image-size="80" />
      </el-tab-pane>
      <el-tab-pane label="面积处理" name="area">
        <el-empty description="功能建设中，后续接入" :image-size="80" />
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleConfirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { useDictionary } from "../../composables/useDictionary";
import { tdlylxMap } from "../../utils/parcelStatusHelpers";
import { initializeParcelAttributes } from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  rows: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue", "initialized"]);

const { options: ownershipOptions } = useDictionary("nyt2539_c06_ownership_property");
const { options: categoryOptions } = useDictionary("nyt2539_c07_parcel_category");
const { options: gradeOptions } = useDictionary("nyt2539_c08_land_grade");
const { options: landUseOptions } = useDictionary("nyt2539_c09_land_use");

const fields = computed(() => [
  { key: "syqxz", label: "所有权性质", options: ownershipOptions.value || [] },
  { key: "dklb", label: "地块类别", options: categoryOptions.value || [] },
  {
    key: "tdlylx",
    label: "土地利用类型",
    options: Object.entries(tdlylxMap).map(([value, label]) => ({ value, label })),
  },
  { key: "dldj", label: "地力等级", options: gradeOptions.value || [] },
  { key: "tdyt", label: "土地用途", options: landUseOptions.value || [] },
  {
    key: "sfjbnt",
    label: "是否基本农田",
    options: [
      { value: "1", label: "是" },
      { value: "0", label: "否" },
    ],
  },
]);

const attributeKeys = ["syqxz", "dklb", "tdlylx", "dldj", "tdyt", "sfjbnt"];
const allKeys = [...attributeKeys, "awareArea", "referPerson", "comment"];

const enabled = reactive(Object.fromEntries(allKeys.map((key) => [key, false])));
const values = reactive(Object.fromEntries(allKeys.map((key) => [key, ""])));
const referPersonByOwner = ref(false);
const initializeNull = ref(false);
const onlyContractParcels = ref(false);
const submitting = ref(false);
const activeTab = ref("basic");

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return;
    submitting.value = false;
    referPersonByOwner.value = false;
    initializeNull.value = false;
    onlyContractParcels.value = false;
    activeTab.value = "basic";
    for (const key of allKeys) {
      enabled[key] = false;
      values[key] = "";
    }
  },
);

function fieldLabel(key) {
  return fields.value.find((item) => item.key === key)?.label || "确权面积";
}

async function handleConfirm() {
  if (activeTab.value !== "basic") {
    ElMessage.warning("该功能尚未开放，请切换到「基础信息初始化」");
    return;
  }
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  const payload = {
    items: props.rows
      .filter((row) => row?.cbfbm && row?.dkbm)
      .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm })),
    initializeNull: initializeNull.value,
    onlyContractParcels: onlyContractParcels.value,
  };
  const picked = [];
  for (const key of attributeKeys) {
    if (!enabled[key]) continue;
    const value = values[key];
    if (value === "" || value === null || value === undefined) {
      ElMessage.warning(`请选择「${fields.value.find((item) => item.key === key)?.label || key}」的初始化值`);
      return;
    }
    payload[key] = value;
    picked.push(key);
  }
  if (enabled.awareArea) {
    if (!values.awareArea) {
      ElMessage.warning("请选择确权面积的初始化方式");
      return;
    }
    payload.awareAreaMode = values.awareArea;
    picked.push("awareArea");
  }
  if (enabled.referPerson) {
    if (!referPersonByOwner.value && !values.referPerson.trim()) {
      ElMessage.warning("请输入指界人，或勾选「按户主姓名」");
      return;
    }
    payload.referPerson = values.referPerson.trim();
    payload.referPersonByOwner = referPersonByOwner.value;
    picked.push("referPerson");
  }
  if (enabled.comment) {
    payload.comment = values.comment;
    picked.push("comment");
  }
  if (!picked.length) {
    ElMessage.warning("请至少选择一个初始化项");
    return;
  }
  submitting.value = true;
  try {
    const { data } = await initializeParcelAttributes(payload);
    const result = data?.data || {};
    ElMessage.success(
      `数据初始化完成：处理 ${result.processed ?? payload.items.length} 个地块` +
        (result.updated != null ? `，实际变更 ${result.updated} 个` : "") +
        (result.skipped ? `，跳过 ${result.skipped} 个` : ""),
    );
    emit("update:modelValue", false);
    emit("initialized");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "数据初始化失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.init-head {
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-size: 13px;
}

.init-head strong {
  color: var(--text);
  font-size: 15px;
}

.init-grid {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.init-row {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
}

.init-check {
  margin-right: 0;
}

.init-inline {
  display: flex;
  align-items: center;
  gap: 12px;
}

.init-options {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
}
</style>
