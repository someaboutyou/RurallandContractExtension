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
      class="region-filter-tree"
      :data="displayRegionTree"
      node-key="value"
      highlight-current
      :current-node-key="activeRegionCode"
      :props="regionTreeProps"
      :expand-on-click-node="false"
      :default-expanded-keys="regionDefaultExpandedKeys"
    >
      <template #default="{ node, data }">
        <div class="region-tree-node">
          <button class="region-tree-label" type="button" @click.stop="$emit('select', data)">
            {{ node.label }}
          </button>
          <el-dropdown trigger="click" @command="(command) => $emit('action', { command, data })">
            <el-button link type="primary" class="region-tree-action" @click.stop>操作</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="printSurveyForms">批量打印调查表</el-dropdown-item>
                <el-dropdown-item command="printRoster">打印承包方清册</el-dropdown-item>
                <el-dropdown-item command="exportSurveyForms">导出调查表信息</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>
    </el-tree>
  </aside>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  regionTree: { type: Array, default: () => [] },
  activeRegionCode: { type: String, default: "" },
  activeRegionLabel: { type: String, default: "" },
});

defineEmits(["select", "clear", "action"]);

const regionNameKeyword = ref("");

const regionTreeProps = { label: "label", children: "children" };

function filterRegionNodesByName(nodes, keyword) {
  const result = [];
  for (const item of nodes || []) {
    const children = filterRegionNodesByName(item.children || [], keyword);
    if (item.label?.includes(keyword) || children.length) {
      result.push({ ...item, children });
    }
  }
  return result;
}

function collectDefaultExpandedRegionKeys(nodes, expandTownLevel = false) {
  const keys = [];
  for (const item of nodes || []) {
    const children = item.children || [];
    const childKeys = collectDefaultExpandedRegionKeys(children, expandTownLevel);
    if (expandTownLevel || childKeys.length || children.length) {
      keys.push(item.value, ...childKeys);
    }
  }
  return keys;
}

const displayRegionTree = computed(() => {
  const keyword = regionNameKeyword.value.trim();
  return keyword ? filterRegionNodesByName(props.regionTree, keyword) : props.regionTree;
});

const regionDefaultExpandedKeys = computed(() =>
  collectDefaultExpandedRegionKeys(props.regionTree),
);
</script>
