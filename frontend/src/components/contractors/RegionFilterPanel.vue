<template>
  <aside class="contractor-region-panel">
    <div class="region-panel-head">
      <div>
        <div class="region-panel-title">区域筛选</div>
        <div class="region-panel-subtitle">{{ activeRegionLabel || "全部区域" }}</div>
      </div>
      <el-button link type="primary" @click="$emit('clear')">全部</el-button>
    </div>
    <el-input
      v-model="regionNameKeyword"
      class="region-filter-search"
      clearable
      placeholder="按区域名称搜索"
    />
    <el-tree
      ref="treeRef"
      class="region-filter-tree"
      :data="displayRegionTree"
      node-key="value"
      highlight-current
      :current-node-key="activeRegionCode"
      :props="regionTreeProps"
      :expand-on-click-node="false"
      :default-expanded-keys="regionDefaultExpandedKeys"
      :filter-node-method="filterRegionNode"
      @node-expand="handleNodeExpand"
    >
      <template #default="{ node, data }">
        <div class="region-tree-node">
          <button
            class="region-tree-label"
            type="button"
            :class="{ 'is-placeholder': data.level === 'placeholder' }"
            @click.stop="data.level !== 'placeholder' && $emit('select', data)"
          >
            {{ node.label }}
          </button>
          <el-dropdown
            v-if="data.level !== 'placeholder'"
            trigger="click"
            @command="(command) => $emit('action', { command, data })"
          >
            <el-button link type="primary" class="region-tree-action" @click.stop>操作</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <!-- 「批量打印调查表」只在组级出现：整村一次上千户，整批渲染会拖垮浏览器 -->
                <el-dropdown-item v-if="data.level === 'group'" command="printSurveyForms">
                  批量打印调查表
                </el-dropdown-item>
                <el-dropdown-item command="exportSurveyForms">导出地籍调查表（Word）</el-dropdown-item>
                <el-dropdown-item command="printRoster">打印承包方清册</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>
    </el-tree>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { fetchRegionChildren } from "../../api/region";

const props = defineProps({
  /** 省 / 县 / 镇 / 村 四级树（同步加载，组不在其中） */
  regionTree: { type: Array, default: () => [] },
  activeRegionCode: { type: String, default: "" },
  activeRegionLabel: { type: String, default: "" },
});

defineEmits(["select", "clear", "action"]);

const treeRef = ref(null);
const regionNameKeyword = ref("");

const regionTreeProps = { label: "label", children: "children" };

//: 已加载的组：``村 code -> 子节点列表``。缓存在这里，搜索触发的树重建后不会丢。
const groupsByVillage = ref({});

const PLACEHOLDER_SUFFIX = "__pending__";

function normalizeNodes(nodes = []) {
  return nodes.map((item) => ({
    ...item,
    value: item.code,
    label: item.name,
    children: normalizeNodes(item.children || []),
  }));
}

/**
 * 给尚未展开的村挂一个占位子节点 —— Element Plus 的 tree 在非 lazy 模式下
 * 用「有没有 children」判断叶子，空数组会让村失去展开箭头。
 */
function decorate(nodes) {
  return nodes.map((item) => {
    const cached = groupsByVillage.value[item.code];
    if (cached) {
      return { ...item, children: cached };
    }
    const children = decorate(item.children || []);
    if (item.level === "village" && !children.length) {
      children.push({
        value: `${item.code}${PLACEHOLDER_SUFFIX}`,
        label: "加载中…",
        level: "placeholder",
        disabled: true,
        children: [],
      });
    }
    return { ...item, children };
  });
}

const displayRegionTree = computed(() => decorate(props.regionTree));

async function handleNodeExpand(data) {
  if (!data || data.level !== "village" || props.regionTree.length === 0) return;
  if (groupsByVillage.value[data.code]) return;

  try {
    const { data: response } = await fetchRegionChildren({
      parentId: data.id,
      includeGroups: true,
    });
    const groups = normalizeNodes(response.data || []);
    groupsByVillage.value = { ...groupsByVillage.value, [data.code]: groups };
    treeRef.value?.updateKeyChildren(data.code, groups);
  } catch (error) {
    treeRef.value?.updateKeyChildren(data.code, []);
    ElMessage.error(error?.response?.data?.detail || "加载组失败");
  }
}

function filterRegionNode(value, data) {
  if (!value) return true;
  const keyword = String(value);
  return (
    String(data.label || "").includes(keyword) ||
    String(data.fullName || data.full_name || "").includes(keyword)
  );
}

watch(regionNameKeyword, (value) => {
  treeRef.value?.filter(String(value || "").trim());
});

// 只展开顶层（省级），镇级以下依次展开，村展开时才异步取组。
const regionDefaultExpandedKeys = computed(() => props.regionTree.map((item) => item.value));
</script>

<style scoped>
.region-tree-label.is-placeholder {
  color: #a8abb2;
  cursor: default;
}
</style>
