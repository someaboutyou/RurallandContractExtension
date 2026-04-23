<template>
  <div class="page-grid">
    <section class="hero-card">
      <div class="eyebrow">第一阶段启动中</div>
      <h1>农村承包经营权平台开发底座已建立</h1>
      <p>
        当前已经具备工作台、人员权限、发包方管理、业务申请四个模块入口，后续可以在这个基础上继续接审批流和 WebGIS。
      </p>
    </section>

    <section class="stat-grid">
      <article class="stat-card" v-for="item in statCards" :key="item.label">
        <div class="stat-label">{{ item.label }}</div>
        <div class="stat-value">{{ item.value }}</div>
      </article>
    </section>

    <section class="panel">
      <div class="panel-title">下一步开发建议</div>
      <ul class="panel-list">
        <li>接入 PostgreSQL 和 PostGIS</li>
        <li>补登录认证和 JWT</li>
        <li>引入 PyCasbin 做区域 / 数据权限</li>
        <li>引入 SpiffWorkflow 做村镇县三级审核</li>
        <li>引入 OpenLayers 做一张图模块</li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { fetchDashboardSummary } from "../api/dashboard";

const summary = ref({
  userCount: 0,
  issuerCount: 0,
  requestCount: 0,
  todoCount: 0,
});

const statCards = computed(() => [
  { label: "用户数量", value: summary.value.userCount },
  { label: "发包方数量", value: summary.value.issuerCount },
  { label: "业务申请数", value: summary.value.requestCount },
  { label: "待处理事项", value: summary.value.todoCount },
]);

onMounted(async () => {
  const { data } = await fetchDashboardSummary();
  summary.value = data.data;
});
</script>
