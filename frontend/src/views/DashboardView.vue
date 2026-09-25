<template>
  <div class="bigscreen">
    <div class="screen-stage" :style="stageStyle">
      <header class="screen-head">
        <div class="head-title">
          <span class="head-badge">二轮延包</span>
          <div>
            <h1>农村土地承包经营权二轮延包 · 工作进展</h1>
            <p>
              <template v-if="batch">
                {{ batch.batchName }} · {{ batch.regionName || "—" }} ·
                <span class="state-chip" :class="`is-${batch.status}`">{{ statusLabel(batch.status) }}</span>
              </template>
              <template v-else>暂无调查批次</template>
            </p>
          </div>
        </div>

        <div class="head-controls">
          <el-select
            v-model="selectedBatchId"
            class="head-select"
            size="large"
            placeholder="选择调查批次"
            :disabled="!batches.length"
            @change="load()"
          >
            <el-option
              v-for="item in batches"
              :key="item.id"
              :label="`${item.batchName}（${statusLabel(item.status)}）`"
              :value="item.id"
            />
          </el-select>
          <div class="seg">
            <button
              v-for="item in levelOptions"
              :key="item.value"
              type="button"
              class="seg-btn"
              :class="{ 'is-active': regionLevel === item.value }"
              @click="switchLevel(item.value)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>

        <div class="head-right">
          <div class="clock">
            <strong>{{ clock.time }}</strong>
            <span>{{ clock.date }}</span>
          </div>
          <div class="head-actions">
            <button type="button" class="icon-btn" :title="autoRefresh ? '暂停自动刷新' : '开启自动刷新'" @click="toggleAutoRefresh">
              <span class="dot" :class="{ 'is-live': autoRefresh }"></span>{{ autoRefresh ? "实时" : "暂停" }}
            </button>
            <button type="button" class="icon-btn" :disabled="loading" @click="load()">
              {{ loading ? "加载中" : "刷新" }}
            </button>
            <button type="button" class="icon-btn" @click="toggleFullscreen">
              {{ isFullscreen ? "取消全屏" : "全屏" }}
            </button>
            <button type="button" class="icon-btn is-ghost" @click="exit">返回平台</button>
          </div>
        </div>
      </header>

      <div v-if="errorMessage" class="screen-error">
        <strong>数据加载失败</strong>
        <span>{{ errorMessage }}</span>
        <button type="button" @click="load()">重试</button>
      </div>

      <div v-else-if="!batch" class="screen-empty">
        <strong>暂无调查批次</strong>
        <span>先在「调查批次」里创建并初始化一个批次，这里就会出现工作进展。</span>
      </div>

      <main v-else class="screen-body">
        <!-- 左列：总量与分配 -->
        <section class="col col-left">
          <div class="metric-grid">
            <article v-for="item in metricCards" :key="item.key" class="metric-card" :class="`is-${item.tone}`">
              <header>
                <span>{{ item.label }}</span>
                <em>{{ item.rate }}%</em>
              </header>
              <strong>{{ formatNumber(item.value) }}</strong>
              <div class="metric-track"><i :style="{ width: `${Math.min(item.rate, 100)}%` }"></i></div>
              <small>{{ item.hint }}</small>
            </article>
          </div>

          <div class="stat-strip">
            <div v-for="item in stripItems" :key="item.label" class="strip-item">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}<em v-if="item.unit">{{ item.unit }}</em></strong>
            </div>
          </div>

          <section class="panel panel-grow">
            <header class="panel-head">
              <h2>调查员工作量</h2>
              <span class="panel-note">{{ assignees.length }} 人已领任务</span>
            </header>
            <div v-if="assignees.length" ref="assigneeChart" class="chart"></div>
            <p v-else class="panel-empty">本批次还没有把户分给任何调查员。</p>
          </section>
        </section>

        <!-- 中列：漏斗 · 趋势 · 区域 -->
        <section class="col col-center">
          <section class="panel">
            <header class="panel-head">
              <h2>办理进度漏斗</h2>
              <span class="panel-note">基线 → 分配 → 调查 → 确认 → 申请</span>
            </header>
            <div class="funnel-wrap">
              <div ref="funnelChart" class="chart chart-funnel"></div>
              <ul class="funnel-list">
                <li v-for="item in funnel" :key="item.key">
                  <span class="funnel-label">{{ item.label }}</span>
                  <strong>{{ formatNumber(item.count) }}</strong>
                  <em>{{ item.rate }}%</em>
                  <div class="funnel-track"><i :style="{ width: `${Math.min(item.rate, 100)}%` }"></i></div>
                  <small>{{ funnelHint(item.key) }}</small>
                </li>
              </ul>
            </div>
          </section>

          <section class="panel">
            <header class="panel-head">
              <h2>近 {{ trend.length || trendDays }} 天工作趋势</h2>
              <span class="panel-note">按日统计分配 / 调查 / 确认</span>
            </header>
            <div ref="trendChart" class="chart chart-trend"></div>
          </section>

          <section class="panel panel-grow">
            <header class="panel-head">
              <h2>{{ regionBoard.levelLabel }}进度榜</h2>
              <span class="panel-note">左：完成率领先　右：需要督办</span>
            </header>
            <div class="region-board">
              <div class="region-column">
                <h3 class="is-good">进度领先</h3>
                <div v-for="item in regionBoard.leading" :key="`l-${item.code}`" class="region-row">
                  <span class="region-name" :title="item.code">{{ item.name }}</span>
                  <div class="region-track"><i class="is-good" :style="{ width: `${item.surveyedRate}%` }"></i></div>
                  <strong>{{ item.surveyedRate }}%</strong>
                  <small>{{ item.surveyed }}/{{ item.total }}</small>
                </div>
                <p v-if="!regionBoard.leading.length" class="panel-empty">暂无数据</p>
              </div>
              <div class="region-column">
                <h3 class="is-risk">需要督办</h3>
                <div
                  v-for="item in regionBoard.lagging"
                  :key="`g-${item.code}`"
                  class="region-row"
                  :class="{ 'is-alert': item.surveyedRate < 60 }"
                >
                  <span class="region-name" :title="item.code">{{ item.name }}</span>
                  <div class="region-track"><i class="is-risk" :style="{ width: `${item.surveyedRate}%` }"></i></div>
                  <strong>{{ item.surveyedRate }}%</strong>
                  <small>{{ item.surveyed }}/{{ item.total }}</small>
                </div>
                <p v-if="!regionBoard.lagging.length" class="panel-empty">暂无数据</p>
              </div>
            </div>
          </section>
        </section>

        <!-- 右列：状态 · 变更 · 预警 -->
        <section class="col col-right">
          <section class="panel">
            <header class="panel-head">
              <h2>调查状态分布</h2>
              <span class="panel-note">共 {{ formatNumber(totalRows) }} 户</span>
            </header>
            <div ref="statusChart" class="chart chart-status"></div>
          </section>

          <section class="panel">
            <header class="panel-head">
              <h2>变更类型</h2>
              <span class="panel-note">{{ changeTypesTotal }} 条变更记录</span>
            </header>
            <div v-if="changeTypes.length" ref="changeChart" class="chart chart-change"></div>
            <p v-else class="panel-empty">本批次还没有变更记录。</p>
          </section>

          <section class="panel panel-grow">
            <header class="panel-head">
              <h2>异常预警</h2>
              <span class="panel-note">{{ alerts.length }} 项待处理</span>
            </header>
            <ul v-if="alerts.length" class="alert-list">
              <li v-for="item in alerts" :key="item.actionKey" :class="`is-${item.level}`">
                <span class="alert-mark"></span>
                <div>
                  <strong>{{ item.title }}</strong>
                  <p>{{ item.detail }}</p>
                </div>
                <em>{{ formatNumber(item.count) }}</em>
              </li>
            </ul>
            <p v-else class="panel-empty">没有需要关注的事项，进度正常。</p>
          </section>
        </section>
      </main>

      <footer class="screen-foot">
        <span>数据更新时间：{{ generatedAtText }}</span>
        <span>每次进入 / 刷新重新计算，口径与「调查批次」一致</span>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from "vue";
import { useRouter } from "vue-router";
import * as echarts from "echarts/core";
import { BarChart, FunnelChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

import { fetchBigscreen } from "../api/dashboard";

echarts.use([
  BarChart,
  FunnelChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

// 大屏按 1920×1080 设计，用 CSS transform 等比缩放铺满任意分辨率，
// 从而避免"换个屏幕就错位"。transform 不改变布局尺寸，ECharts 读 clientWidth 仍然正确。
const BASE_WIDTH = 1920;
const BASE_HEIGHT = 1080;
const REFRESH_INTERVAL = 60 * 1000;

const router = useRouter();

const loading = ref(false);
const errorMessage = ref("");
const payload = ref(null);
const selectedBatchId = ref(null);
const regionLevel = ref("town");
const trendDays = ref(15);
const autoRefresh = ref(true);
const scale = ref(1);

const levelOptions = [
  { value: "town", label: "镇级" },
  { value: "village", label: "村级" },
];

const TONE_COLORS = {
  slate: "#9aacc0",
  blue: "#2f6bbf",
  orange: "#ef9b2d",
  green: "#37b26c",
  teal: "#2aa5a5",
  purple: "#8b7bd8",
  gray: "#c2cdd9",
};
const INK = "#17324d";
const MUTED = "#6f88a3";
const AXIS_LINE = "rgba(56, 122, 196, 0.18)";

const batch = computed(() => payload.value?.batch || null);
const batches = computed(() => payload.value?.batches || []);
const overview = computed(() => payload.value?.overview || {});
const funnel = computed(() => payload.value?.funnel || []);
const taskStatus = computed(() => payload.value?.taskStatus || []);
const assignees = computed(() => payload.value?.assignees || []);
const regionBoard = computed(
  () => payload.value?.regionBoard || { level: "town", levelLabel: "镇级", leading: [], lagging: [] },
);
const changeTypes = computed(() => payload.value?.changeTypes || []);
const trend = computed(() => payload.value?.trend || []);
const alerts = computed(() => payload.value?.alerts || []);

const totalRows = computed(() => taskStatus.value.reduce((sum, item) => sum + item.count, 0));
const changeTypesTotal = computed(() => changeTypes.value.reduce((sum, item) => sum + item.count, 0));

const metricCards = computed(() => [
  {
    key: "total",
    label: "承包方基数",
    value: overview.value.contractorTotal || 0,
    rate: 100,
    tone: "blue",
    hint: `待调查 ${overview.value.contractorTotal - overview.value.surveyedCount} 户`,
  },
  {
    key: "assigned",
    label: "已分配到人",
    value: overview.value.assignedCount || 0,
    rate: overview.value.assignedRate || 0,
    tone: "teal",
    hint: `未分配 ${overview.value.contractorTotal - overview.value.assignedCount} 户`,
  },
  {
    key: "surveyed",
    label: "已调查录入",
    value: overview.value.surveyedCount || 0,
    rate: overview.value.surveyedRate || 0,
    tone: "orange",
    hint: `含变更 ${overview.value.changedCount} 户`,
  },
  {
    key: "confirmed",
    label: "已复核确认",
    value: overview.value.confirmedCount || 0,
    rate: overview.value.confirmedRate || 0,
    tone: "green",
    hint: `待生成申请 ${overview.value.surveyedCount - overview.value.requestGeneratedCount} 户`,
  },
]);

const stripItems = computed(() => [
  { label: "承包地块", value: formatNumber(overview.value.parcelTotal || 0), unit: "块" },
  { label: "合同面积", value: formatNumber(overview.value.contractAreaMu || 0, 2), unit: "亩" },
  { label: "发包方", value: formatNumber(overview.value.issuerTotal || 0), unit: "个" },
  { label: "家庭成员", value: formatNumber(overview.value.memberTotal || 0), unit: "人" },
  { label: "已生成申请", value: formatNumber(overview.value.requestGeneratedCount || 0), unit: "件" },
  { label: "采集材料", value: formatNumber(overview.value.attachmentCount || 0), unit: "份" },
]);

const stageStyle = computed(() => ({
  width: `${BASE_WIDTH}px`,
  height: `${BASE_HEIGHT}px`,
  transform: `scale(${scale.value})`,
}));

const generatedAtText = computed(() => {
  const value = payload.value?.generatedAt;
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const pad = (num) => String(num).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
});

const clock = ref({ time: "--:--:--", date: "----年--月--日" });

function formatNumber(value, digits = 0) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "0";
  return num.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function statusLabel(status) {
  return { draft: "草稿", in_progress: "进行中", finished: "已结束", pending: "待启动" }[status] || status || "—";
}

function funnelHint(key) {
  return {
    baseline: "本批次调查对象",
    assigned: "已指定调查员",
    surveyed: "已录入调查结果",
    confirmed: "复核通过可流转",
    request: "已生成业务申请",
  }[key] || "";
}

// ------------------------------------------------------------------ 图表

const assigneeChart = ref(null);
const funnelChart = ref(null);
const trendChart = ref(null);
const statusChart = ref(null);
const changeChart = ref(null);
const chartEls = { assignee: assigneeChart, funnel: funnelChart, trend: trendChart, status: statusChart, change: changeChart };
const charts = shallowRef({});
const resizeObserver = new WeakSet();

function ensureChart(key) {
  const el = chartEls[key]?.value;
  if (!el) {
    const stale = charts.value[key];
    if (stale) {
      stale.dispose();
      delete charts.value[key];
    }
    return null;
  }
  if (!charts.value[key]) {
    charts.value[key] = echarts.init(el);
  }
  return charts.value[key];
}

function renderAssignee() {
  const chart = ensureChart("assignee");
  if (!chart) return;
  const rows = assignees.value.slice(0, 8).reverse();
  chart.setOption(
    {
      grid: { left: 8, right: 46, top: 6, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params) => {
          const item = rows[params[0].dataIndex];
          return `${item.name}<br/>领任务 ${item.total} 户<br/>已调查 ${item.surveyed} 户（${item.surveyedRate}%）<br/>已确认 ${item.confirmed} 户`;
        },
      },
      xAxis: { type: "value", show: false, max: Math.max(...rows.map((item) => item.total), 1) },
      yAxis: {
        type: "category",
        data: rows.map((item) => item.name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: INK, fontSize: 13, width: 76, overflow: "truncate" },
      },
      series: [
        {
          name: "已调查",
          type: "bar",
          stack: "work",
          barWidth: 13,
          itemStyle: { color: "#37b26c", borderRadius: [3, 0, 0, 3] },
          label: {
            show: true,
            position: "right",
            color: MUTED,
            fontSize: 12,
            formatter: (params) => `${rows[params.dataIndex].surveyedRate}%`,
          },
          data: rows.map((item) => item.surveyed),
        },
        {
          name: "未调查",
          type: "bar",
          stack: "work",
          barWidth: 13,
          itemStyle: { color: "rgba(154, 172, 192, 0.45)", borderRadius: [0, 3, 3, 0] },
          data: rows.map((item) => Math.max(item.total - item.surveyed, 0)),
        },
      ],
    },
    true,
  );
}

function renderFunnel() {
  const chart = ensureChart("funnel");
  if (!chart) return;
  const rows = funnel.value;
  const max = Math.max(...rows.map((item) => item.count), 1);
  chart.setOption(
    {
      series: [
        {
          type: "funnel",
          left: 4,
          right: 4,
          top: 8,
          bottom: 8,
          minSize: "26%",
          maxSize: "100%",
          sort: "descending",
          gap: 3,
          label: { show: false },
          itemStyle: { borderWidth: 0 },
          data: rows.map((item, index) => ({
            name: item.label,
            value: Math.max(item.count, max * 0.04),
            itemStyle: { color: ["#2f6bbf", "#2aa5a5", "#ef9b2d", "#37b26c", "#8b7bd8"][index % 5], opacity: 0.88 },
          })),
        },
      ],
    },
    true,
  );
}

function renderTrend() {
  const chart = ensureChart("trend");
  if (!chart) return;
  const rows = trend.value;
  const compact = rows.length > 20;
  chart.setOption(
    {
      color: ["#2f6bbf", "#ef9b2d", "#37b26c"],
      grid: { left: 10, right: 18, top: 30, bottom: 6, containLabel: true },
      tooltip: { trigger: "axis" },
      legend: {
        right: 0,
        top: 0,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: MUTED, fontSize: 12 },
        data: ["已分配", "已调查", "已确认"],
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: rows.map((item) => item.date.slice(5)),
        axisLine: { lineStyle: { color: AXIS_LINE } },
        axisTick: { show: false },
        axisLabel: { color: MUTED, fontSize: 11, interval: compact ? Math.ceil(rows.length / 12) - 1 : 0 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: AXIS_LINE, type: "dashed" } },
        axisLabel: { color: MUTED, fontSize: 11 },
      },
      series: [
        { name: "已分配", type: "line", smooth: true, showSymbol: false, lineStyle: { width: 2 }, areaStyle: { opacity: 0.1 }, data: rows.map((item) => item.assigned) },
        { name: "已调查", type: "line", smooth: true, showSymbol: false, lineStyle: { width: 2 }, areaStyle: { opacity: 0.12 }, data: rows.map((item) => item.investigated) },
        { name: "已确认", type: "line", smooth: true, showSymbol: false, lineStyle: { width: 2 }, areaStyle: { opacity: 0.1 }, data: rows.map((item) => item.confirmed) },
      ],
    },
    true,
  );
}

function renderStatus() {
  const chart = ensureChart("status");
  if (!chart) return;
  const rows = taskStatus.value.filter((item) => item.count > 0);
  chart.setOption(
    {
      tooltip: { trigger: "item", formatter: "{b}：{c} 户（{d}%）" },
      legend: {
        type: "scroll",
        orient: "vertical",
        right: 0,
        top: "middle",
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { color: MUTED, fontSize: 12 },
      },
      series: [
        {
          type: "pie",
          radius: ["52%", "76%"],
          center: ["34%", "50%"],
          avoidLabelOverlap: true,
          label: { show: true, position: "center", formatter: () => `${totalRows.value}`, color: INK, fontSize: 26, fontWeight: 700 },
          labelLine: { show: false },
          itemStyle: { borderColor: "#fff", borderWidth: 2 },
          data: rows.map((item) => ({
            name: item.label,
            value: item.count,
            itemStyle: { color: TONE_COLORS[item.tone] || TONE_COLORS.gray },
          })),
        },
      ],
    },
    true,
  );
}

function renderChange() {
  const chart = ensureChart("change");
  if (!chart) return;
  const rows = changeTypes.value.slice(0, 7).reverse();
  chart.setOption(
    {
      grid: { left: 8, right: 40, top: 6, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: "{b}：{c} 条" },
      xAxis: { type: "value", show: false, max: Math.max(...rows.map((item) => item.count), 1) },
      yAxis: {
        type: "category",
        data: rows.map((item) => item.label),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: INK, fontSize: 12, width: 76, overflow: "truncate" },
      },
      series: [
        {
          type: "bar",
          barWidth: 12,
          itemStyle: { color: "#8b7bd8", borderRadius: [3, 3, 3, 3] },
          label: { show: true, position: "right", color: MUTED, fontSize: 12 },
          data: rows.map((item) => item.count),
        },
      ],
    },
    true,
  );
}

function renderCharts() {
  renderAssignee();
  renderFunnel();
  renderTrend();
  renderStatus();
  renderChange();
}

// ------------------------------------------------------------------ 生命周期

async function load() {
  loading.value = true;
  errorMessage.value = "";
  try {
    const { data } = await fetchBigscreen({
      batchId: selectedBatchId.value || undefined,
      trendDays: trendDays.value,
      regionLevel: regionLevel.value,
    });
    payload.value = data.data;
    // 首次加载（或后端切了默认批次）时把下拉回填成实际展示的批次，
    // 否则筛选框会停在"最新批次"上，而画面显示的是另一个批次。
    if (payload.value?.batch) {
      selectedBatchId.value = payload.value.batch.id;
    }
    await nextTick();
    renderCharts();
  } catch (error) {
    const detail = error?.response?.data?.detail;
    errorMessage.value = typeof detail === "string" ? detail : error?.message || "接口请求失败";
    payload.value = null;
  } finally {
    loading.value = false;
  }
}

function switchLevel(value) {
  if (regionLevel.value === value) return;
  regionLevel.value = value;
  load();
}

function updateScale() {
  scale.value = Math.min(window.innerWidth / BASE_WIDTH, window.innerHeight / BASE_HEIGHT);
}

function handleResize() {
  updateScale();
  Object.values(charts.value).forEach((chart) => chart && chart.resize());
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value;
  scheduleRefresh();
}

// 按钮文案跟随**真实**全屏状态，而不是本地开关：用户按 ESC 退出时也要同步回「全屏」。
const isFullscreen = ref(false);

function syncFullscreenState() {
  isFullscreen.value = Boolean(document.fullscreenElement);
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await document.documentElement.requestFullscreen();
    }
  } catch {
    // 浏览器拒绝（非用户手势 / 权限策略）时静默降级，不打断大屏展示。
  } finally {
    // requestFullscreen 是异步生效的；个别浏览器/场景下事件回调有延迟，这里再兜一次。
    syncFullscreenState();
  }
}

async function exit() {
  // ⛔ 必须先退出全屏再跳转：全屏是加在 document 上的，直接 router.push 只换路由不退出全屏，
  // 平台其它页面会继续停在全屏里 —— 用户会觉得「点了返回平台却还在全屏」。
  if (document.fullscreenElement) {
    try {
      await document.exitFullscreen();
    } catch {
      // 退出失败也要放行返回，不能把用户卡在大屏里。
    }
  }
  router.push({ name: "gis" });
}

let clockTimer = null;
let refreshTimer = null;

function scheduleRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  if (autoRefresh.value) {
    refreshTimer = setInterval(load, REFRESH_INTERVAL);
  }
}

onMounted(() => {
  updateScale();
  window.addEventListener("resize", handleResize);
  document.addEventListener("fullscreenchange", syncFullscreenState);
  syncFullscreenState();
  // 大屏常挂在外部显示器上，屏幕切换后窗口尺寸不变但设备像素比会变，补一次 resize。
  if (typeof ResizeObserver !== "undefined" && !resizeObserver.has(document.body)) {
    resizeObserver.add(document.body);
  }
  clockTimer = setInterval(() => {
    const now = new Date();
    const pad = (num) => String(num).padStart(2, "0");
    clock.value = {
      time: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
      date: `${now.getFullYear()}年${pad(now.getMonth() + 1)}月${pad(now.getDate())}日`,
    };
  }, 1000);
  load();
  scheduleRefresh();
});

onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer);
  if (refreshTimer) clearInterval(refreshTimer);
  window.removeEventListener("resize", handleResize);
  document.removeEventListener("fullscreenchange", syncFullscreenState);
  // 兜底：以「返回平台」以外的方式离开（浏览器后退、外部跳转）时，也别把用户留在全屏态。
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
  }
  Object.values(charts.value).forEach((chart) => chart && chart.dispose());
  charts.value = {};
});
</script>

<style scoped>
/* 大屏外层：占满视口，舞台按 1920×1080 固定布局后整体缩放。 */
.bigscreen {
  width: 100vw;
  height: 100vh;
  display: grid;
  place-items: center;
  overflow: hidden;
  background:
    radial-gradient(1200px 620px at 12% -8%, rgba(47, 107, 191, 0.16), transparent 62%),
    radial-gradient(900px 520px at 92% 6%, rgba(42, 165, 165, 0.14), transparent 58%),
    linear-gradient(160deg, #eef5fc 0%, #e7f0f9 46%, #e3ecf7 100%);
}

.screen-stage {
  transform-origin: center center;
  display: flex;
  flex-direction: column;
  padding: 14px 18px 10px;
  color: var(--text);
}

/* ---------------------------------------------------------------- 顶部 */
.screen-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 16px;
  padding: 12px 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: var(--shadow);
}

.head-title {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.head-badge {
  flex: 0 0 auto;
  padding: 7px 12px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #2f6bbf, #2aa5a5);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 1px;
  white-space: nowrap;
}

.head-title h1 {
  margin: 0 0 4px;
  font-size: 25px;
  line-height: 1.15;
  letter-spacing: 1px;
}

.head-title p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.state-chip {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(47, 107, 191, 0.12);
  color: #2f6bbf;
  font-weight: 700;
}

.state-chip.is-in_progress {
  background: rgba(55, 178, 108, 0.14);
  color: #2f8f57;
}

.head-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.head-select {
  width: 300px;
}

.seg {
  display: flex;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: rgba(240, 246, 252, 0.9);
}

.seg-btn {
  min-width: 62px;
  padding: 8px 12px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}

.seg-btn.is-active {
  background: #fff;
  color: #2f6bbf;
  box-shadow: 0 2px 8px rgba(25, 74, 128, 0.12);
}

.head-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
}

.clock {
  display: grid;
  justify-items: end;
  line-height: 1.2;
}

.clock strong {
  font-size: 26px;
  font-variant-numeric: tabular-nums;
  color: #1d3f6b;
}

.clock span {
  color: var(--muted);
  font-size: 12px;
}

.head-actions {
  display: flex;
  gap: 8px;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: #fff;
  color: #2f5b93;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.icon-btn:hover:not(:disabled) {
  background: rgba(47, 107, 191, 0.08);
}

.icon-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.icon-btn.is-ghost {
  color: var(--muted);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c2cdd9;
}

.dot.is-live {
  background: #37b26c;
  box-shadow: 0 0 0 4px rgba(55, 178, 108, 0.18);
}

/* ---------------------------------------------------------------- 状态占位 */
.screen-error,
.screen-empty {
  flex: 1;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  margin-top: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  background: rgba(255, 255, 255, 0.9);
  color: var(--muted);
  text-align: center;
}

.screen-error strong,
.screen-empty strong {
  font-size: 20px;
  color: var(--text);
}

.screen-error button {
  padding: 8px 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: #fff;
  color: #2f6bbf;
  font-weight: 700;
  cursor: pointer;
}

/* ---------------------------------------------------------------- 主体三列 */
.screen-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 400px minmax(0, 1fr) 400px;
  gap: 14px;
  margin-top: 14px;
}

.col {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--shadow);
}

.panel-grow {
  flex: 1;
}

.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.panel-head h2 {
  margin: 0;
  font-size: 17px;
  letter-spacing: 0.5px;
}

.panel-note {
  color: var(--muted);
  font-size: 12px;
}

.panel-empty {
  margin: auto;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}

/* ⛔ 不要给 .chart 无条件写 `flex: 1`：在 flex column 里它展开成 flex-basis: 0，
   优先级高于下面各 .chart-* 的 height（被静默忽略）；而 .panel 自身高度又由内容决定，
   于是「面板等图表撑开、图表等面板给空间」互相依赖，一起塌成 0 高 ⇒ 图表画不出来。
   只有真正需要吃掉剩余空间的图表（.panel-grow 内）才交给 flex。 */
.chart {
  min-height: 0;
  width: 100%;
}

.panel-grow > .chart {
  flex: 1;
}

.chart-funnel {
  height: 210px;
}

.chart-trend {
  height: 210px;
}

.chart-status {
  height: 220px;
}

.chart-change {
  height: 190px;
}

/* ---------------------------------------------------------------- 指标卡 */
.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--shadow);
}

.metric-card header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
}

.metric-card header em {
  font-style: normal;
  font-size: 13px;
}

.metric-card strong {
  font-size: 30px;
  line-height: 1.05;
  font-variant-numeric: tabular-nums;
}

.metric-card small {
  color: var(--muted);
  font-size: 12px;
}

.metric-track {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(46, 74, 109, 0.09);
}

.metric-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.metric-card.is-blue strong,
.metric-card.is-blue header em {
  color: #2f6bbf;
}

.metric-card.is-blue .metric-track i {
  background: #2f6bbf;
}

.metric-card.is-teal strong,
.metric-card.is-teal header em {
  color: #2aa5a5;
}

.metric-card.is-teal .metric-track i {
  background: #2aa5a5;
}

.metric-card.is-orange strong,
.metric-card.is-orange header em {
  color: #d98a1c;
}

.metric-card.is-orange .metric-track i {
  background: #ef9b2d;
}

.metric-card.is-green strong,
.metric-card.is-green header em {
  color: #2f8f57;
}

.metric-card.is-green .metric-track i {
  background: #37b26c;
}

.stat-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  background: rgba(248, 251, 255, 0.92);
}

.strip-item {
  display: grid;
  gap: 4px;
}

.strip-item span {
  color: var(--muted);
  font-size: 12px;
}

.strip-item strong {
  font-size: 19px;
  font-variant-numeric: tabular-nums;
}

.strip-item em {
  margin-left: 3px;
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
  font-weight: 600;
}

/* ---------------------------------------------------------------- 漏斗 */
.funnel-wrap {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.funnel-list {
  display: grid;
  align-content: space-between;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.funnel-list li {
  display: grid;
  grid-template-columns: 110px 74px 56px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.funnel-label {
  font-weight: 700;
}

.funnel-list strong {
  font-size: 20px;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.funnel-list em {
  color: #2f6bbf;
  font-size: 13px;
  font-style: normal;
  font-weight: 700;
  text-align: right;
}

.funnel-list small {
  grid-column: 4 / -1;
  color: var(--muted);
  font-size: 11px;
}

.funnel-track {
  grid-row: 1 / 3;
  grid-column: 4;
  align-self: center;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(46, 74, 109, 0.09);
}

.funnel-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #2f6bbf, #2aa5a5);
}

/* ---------------------------------------------------------------- 区域榜 */
.region-board {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.region-column h3 {
  margin: 0 0 10px;
  font-size: 13px;
  letter-spacing: 0.5px;
}

.region-column h3.is-good {
  color: #2f8f57;
}

.region-column h3.is-risk {
  color: #cf5954;
}

.region-row {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr) 52px 62px;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px dashed rgba(56, 122, 196, 0.12);
}

.region-row.is-alert .region-name {
  color: #cf5954;
  font-weight: 700;
}

.region-name {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.region-track {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(46, 74, 109, 0.09);
}

.region-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.region-track i.is-good {
  background: #37b26c;
}

.region-track i.is-risk {
  background: #ef9b2d;
}

.region-row strong {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.region-row small {
  color: var(--muted);
  font-size: 11px;
  text-align: right;
}

/* ---------------------------------------------------------------- 预警 */
.alert-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow: auto;
}

.alert-list li {
  display: grid;
  grid-template-columns: 6px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: rgba(248, 251, 255, 0.9);
}

.alert-mark {
  align-self: stretch;
  border-radius: 999px;
  background: #9aacc0;
}

.alert-list li.is-high .alert-mark {
  background: #ea5a69;
}

.alert-list li.is-medium .alert-mark {
  background: #ef9b2d;
}

.alert-list li.is-low .alert-mark {
  background: #2f6bbf;
}

.alert-list strong {
  font-size: 14px;
}

.alert-list p {
  margin: 3px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.alert-list em {
  font-size: 18px;
  font-style: normal;
  font-weight: 700;
  color: #1d3f6b;
}

/* ---------------------------------------------------------------- 页脚 */
.screen-foot {
  display: flex;
  justify-content: space-between;
  padding: 8px 4px 0;
  color: var(--muted);
  font-size: 12px;
}
</style>
