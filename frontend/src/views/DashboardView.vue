<template>
  <div class="viz-page">
    <section class="viz-toolbar">
      <div>
        <div class="eyebrow">数据可视化</div>
        <h1>延包业务数据驾驶舱</h1>
        <p>围绕调查进度、地块面积、流程审核和档案归集做作业监测，异常事项可直接下钻处理。</p>
      </div>
      <div class="viz-actions">
        <el-select v-model="selectedBatch" class="batch-select" size="large">
          <el-option v-for="item in batches" :key="item" :label="item" :value="item" />
        </el-select>
        <el-radio-group v-model="scope" size="large">
          <el-radio-button label="县域" />
          <el-radio-button label="乡镇" />
          <el-radio-button label="村组" />
        </el-radio-group>
      </div>
    </section>

    <section class="metric-grid">
      <article v-for="item in metrics" :key="item.label" class="metric-card" :class="`is-${item.tone}`">
        <div class="metric-head">
          <span>{{ item.label }}</span>
          <el-icon><component :is="item.icon" /></el-icon>
        </div>
        <div class="metric-value">{{ item.value }}</div>
        <div class="metric-foot">
          <span>{{ item.hint }}</span>
          <strong>{{ item.delta }}</strong>
        </div>
      </article>
    </section>

    <section class="viz-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="viz-tab"
        :class="{ 'is-active': activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </section>

    <section v-if="activeTab === 'overview'" class="overview-grid">
      <article class="viz-panel map-panel">
        <div class="panel-head">
          <div>
            <h2>县域作业热力</h2>
            <p>按村组调查完成率、异常地块和待审核事项叠加展示</p>
          </div>
          <el-tag type="warning" effect="plain">18 个重点村组</el-tag>
        </div>
        <div class="county-map">
          <div
            v-for="area in mapAreas"
            :key="area.name"
            class="map-area"
            :class="`level-${area.level}`"
            :style="area.style"
          >
            <span>{{ area.name }}</span>
            <strong>{{ area.rate }}%</strong>
          </div>
        </div>
        <div class="map-legend">
          <span><i class="legend-dot is-good"></i>完成较好</span>
          <span><i class="legend-dot is-warn"></i>需跟进</span>
          <span><i class="legend-dot is-risk"></i>重点督办</span>
        </div>
      </article>

      <article class="viz-panel">
        <div class="panel-head">
          <div>
            <h2>调查状态分布</h2>
            <p>承包方调查任务当前状态</p>
          </div>
        </div>
        <div class="status-list">
          <div v-for="item in surveyStatus" :key="item.label" class="status-row">
            <div class="status-info">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }} 户</strong>
            </div>
            <div class="progress-track">
              <span :class="`is-${item.tone}`" :style="{ width: `${item.percent}%` }"></span>
            </div>
          </div>
        </div>
      </article>

      <article class="viz-panel wide-panel">
        <div class="panel-head">
          <div>
            <h2>近 30 天办理趋势</h2>
            <p>调查完成、业务申请和档案归集按日汇总</p>
          </div>
        </div>
        <div class="trend-chart" aria-label="近30天办理趋势">
          <div v-for="point in trends" :key="point.day" class="trend-column">
            <span class="bar is-survey" :style="{ height: `${point.survey}%` }"></span>
            <span class="bar is-request" :style="{ height: `${point.request}%` }"></span>
            <span class="bar is-archive" :style="{ height: `${point.archive}%` }"></span>
            <small>{{ point.day }}</small>
          </div>
        </div>
        <div class="chart-legend">
          <span><i class="legend-line is-survey"></i>调查完成</span>
          <span><i class="legend-line is-request"></i>业务申请</span>
          <span><i class="legend-line is-archive"></i>档案归集</span>
        </div>
      </article>

      <article class="viz-panel">
        <div class="panel-head">
          <div>
            <h2>待办优先级</h2>
            <p>按风险和超期情况排序</p>
          </div>
        </div>
        <div class="todo-list">
          <RouterLink v-for="item in todos" :key="item.title" class="todo-item" :to="item.to">
            <span :class="`todo-mark is-${item.tone}`"></span>
            <div>
              <strong>{{ item.title }}</strong>
              <small>{{ item.meta }}</small>
            </div>
            <el-icon><ArrowRight /></el-icon>
          </RouterLink>
        </div>
      </article>
    </section>

    <section v-else-if="activeTab === 'survey'" class="analysis-grid">
      <article class="viz-panel wide-panel">
        <div class="panel-head">
          <div>
            <h2>乡镇调查进度排行</h2>
            <p>点击后可按行政区筛选承包方和调查任务</p>
          </div>
        </div>
        <div class="ranking-list">
          <div v-for="item in townProgress" :key="item.name" class="ranking-row">
            <span>{{ item.name }}</span>
            <div class="ranking-track"><i :style="{ width: `${item.rate}%` }"></i></div>
            <strong>{{ item.rate }}%</strong>
            <small>{{ item.done }}/{{ item.total }} 户</small>
          </div>
        </div>
      </article>
      <article class="viz-panel">
        <div class="panel-head">
          <div>
            <h2>变更类型</h2>
            <p>调查成果相对基准快照的变化</p>
          </div>
        </div>
        <div class="change-grid">
          <div v-for="item in changeTypes" :key="item.label" class="change-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.note }}</small>
          </div>
        </div>
      </article>
      <article class="viz-panel full-panel">
        <div class="panel-head">
          <div>
            <h2>村组推进明细</h2>
            <p>用于每日调度和现场作业复盘</p>
          </div>
        </div>
        <el-table :data="villageRows" height="286" stripe>
          <el-table-column prop="village" label="村组" min-width="140" />
          <el-table-column prop="contractors" label="承包方" width="100" />
          <el-table-column prop="parcels" label="地块" width="100" />
          <el-table-column prop="progress" label="完成率" width="160">
            <template #default="{ row }">
              <el-progress :percentage="row.progress" :stroke-width="8" />
            </template>
          </el-table-column>
          <el-table-column prop="changes" label="变更数" width="100" />
          <el-table-column prop="risk" label="风险提示" min-width="180" />
        </el-table>
      </article>
    </section>

    <section v-else-if="activeTab === 'parcel'" class="analysis-grid">
      <article class="viz-panel map-panel wide-panel">
        <div class="panel-head">
          <div>
            <h2>地块异常定位</h2>
            <p>按面积差异、切割互换、归属变化生成核查图层</p>
          </div>
          <RouterLink class="panel-link" to="/gis">进入一张图</RouterLink>
        </div>
        <div class="parcel-map">
          <span v-for="plot in plots" :key="plot.id" :class="`plot is-${plot.tone}`" :style="plot.style">
            {{ plot.id }}
          </span>
        </div>
      </article>
      <article class="viz-panel">
        <div class="panel-head">
          <div>
            <h2>面积差异 Top 5</h2>
            <p>合同面积与实测面积偏差</p>
          </div>
        </div>
        <div class="diff-list">
          <div v-for="item in areaDiffs" :key="item.code" class="diff-row">
            <div>
              <strong>{{ item.code }}</strong>
              <small>{{ item.owner }}</small>
            </div>
            <span>{{ item.diff }} 亩</span>
          </div>
        </div>
      </article>
      <article class="viz-panel full-panel">
        <div class="panel-head">
          <div>
            <h2>地块类别结构</h2>
            <p>用于判断承包地、自留地、机动地等结构变化</p>
          </div>
        </div>
        <div class="category-bars">
          <div v-for="item in parcelCategories" :key="item.label" class="category-row">
            <span>{{ item.label }}</span>
            <div><i :style="{ width: `${item.percent}%`, background: item.color }"></i></div>
            <strong>{{ item.value }} 块</strong>
          </div>
        </div>
      </article>
    </section>

    <section v-else class="analysis-grid">
      <article class="viz-panel wide-panel">
        <div class="panel-head">
          <div>
            <h2>村镇县审核链路</h2>
            <p>关注超期、退回和节点积压</p>
          </div>
        </div>
        <div class="workflow-funnel">
          <div v-for="item in workflowNodes" :key="item.label" class="funnel-step">
            <span>{{ item.label }}</span>
            <strong>{{ item.count }}</strong>
            <small>{{ item.note }}</small>
          </div>
        </div>
      </article>
      <article class="viz-panel">
        <div class="panel-head">
          <div>
            <h2>归档完整率</h2>
            <p>按案卷材料清单自动校验</p>
          </div>
        </div>
        <div class="archive-score">
          <div class="score-ring">86%</div>
          <div class="score-notes">
            <span>已归档 1,928 卷</span>
            <span>待补材料 214 卷</span>
            <span>目录待复核 76 卷</span>
          </div>
        </div>
      </article>
      <article class="viz-panel full-panel">
        <div class="panel-head">
          <div>
            <h2>材料缺失清单</h2>
            <p>优先补齐影响办结和归档的关键材料</p>
          </div>
          <RouterLink class="panel-link" to="/archives">进入档案管理</RouterLink>
        </div>
        <el-table :data="archiveRows" height="286" stripe>
          <el-table-column prop="caseNo" label="业务编号" min-width="160" />
          <el-table-column prop="owner" label="承包方" width="120" />
          <el-table-column prop="node" label="当前环节" width="120" />
          <el-table-column prop="missing" label="缺失材料" min-width="220" />
          <el-table-column prop="days" label="滞留天数" width="100" />
        </el-table>
      </article>
    </section>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { ArrowRight, Collection, Files, MapLocation, TrendCharts } from "@element-plus/icons-vue";

const selectedBatch = ref("2026 年二轮延包调查批次");
const scope = ref("县域");
const activeTab = ref("overview");

const batches = ["2026 年二轮延包调查批次", "泗洪县试点村核查批次", "历史确权数据复核批次"];
const tabs = [
  { key: "overview", label: "总览" },
  { key: "survey", label: "调查进度" },
  { key: "parcel", label: "地块面积" },
  { key: "archive", label: "流程归档" },
];

const metrics = [
  { label: "调查完成率", value: "78.6%", hint: "较昨日", delta: "+3.2%", tone: "blue", icon: TrendCharts },
  { label: "已核查承包方", value: "12,486", hint: "剩余 3,402 户", delta: "82%", tone: "green", icon: Collection },
  { label: "异常地块", value: "326", hint: "面积差异/归属变化", delta: "待核查", tone: "orange", icon: MapLocation },
  { label: "待归档案卷", value: "214", hint: "缺少关键材料", delta: "需补齐", tone: "red", icon: Files },
];

const mapAreas = [
  { name: "青阳", rate: 91, level: 1, style: { left: "10%", top: "18%", width: "24%", height: "26%" } },
  { name: "双沟", rate: 76, level: 2, style: { left: "35%", top: "12%", width: "22%", height: "30%" } },
  { name: "归仁", rate: 68, level: 2, style: { left: "59%", top: "20%", width: "26%", height: "24%" } },
  { name: "半城", rate: 84, level: 1, style: { left: "17%", top: "48%", width: "26%", height: "28%" } },
  { name: "魏营", rate: 53, level: 3, style: { left: "47%", top: "48%", width: "22%", height: "32%" } },
  { name: "孙园", rate: 71, level: 2, style: { left: "71%", top: "50%", width: "18%", height: "28%" } },
];

const surveyStatus = [
  { label: "已完成", value: 12486, percent: 79, tone: "green" },
  { label: "进行中", value: 2418, percent: 15, tone: "blue" },
  { label: "待入户", value: 984, percent: 6, tone: "orange" },
  { label: "退回修正", value: 326, percent: 4, tone: "red" },
];

const trends = [
  { day: "1日", survey: 42, request: 28, archive: 18 },
  { day: "5日", survey: 55, request: 35, archive: 24 },
  { day: "10日", survey: 63, request: 48, archive: 36 },
  { day: "15日", survey: 78, request: 58, archive: 42 },
  { day: "20日", survey: 84, request: 66, archive: 55 },
  { day: "25日", survey: 92, request: 72, archive: 62 },
  { day: "30日", survey: 88, request: 69, archive: 74 },
];

const todos = [
  { title: "魏营镇 42 户调查超期", meta: "平均滞留 6.4 天", tone: "red", to: "/surveys" },
  { title: "18 块地面积差异大于 5 亩", meta: "需 GIS 复核", tone: "orange", to: "/gis" },
  { title: "镇级审核积压 37 件", meta: "今日新增 9 件", tone: "blue", to: "/requests" },
  { title: "合同附件缺失 126 份", meta: "影响归档完整率", tone: "brown", to: "/archives" },
];

const townProgress = [
  { name: "青阳街道", rate: 91, done: 2280, total: 2506 },
  { name: "半城镇", rate: 84, done: 1836, total: 2187 },
  { name: "双沟镇", rate: 76, done: 1598, total: 2102 },
  { name: "孙园镇", rate: 71, done: 1392, total: 1960 },
  { name: "归仁镇", rate: 68, done: 1197, total: 1760 },
  { name: "魏营镇", rate: 53, done: 980, total: 1849 },
];

const changeTypes = [
  { label: "分户", value: 184, note: "含成员和地块分配" },
  { label: "合户", value: 67, note: "源户已注销" },
  { label: "地块互换", value: 93, note: "跨承包方调整" },
  { label: "新增地块", value: 128, note: "需补空间核验" },
  { label: "切割地块", value: 56, note: "面积待复核" },
  { label: "注销承包方", value: 41, note: "原始快照保留" },
];

const villageRows = [
  { village: "青阳街道 大楼社区", contractors: 526, parcels: 2184, progress: 94, changes: 42, risk: "材料完整，按计划推进" },
  { village: "双沟镇 李庄村", contractors: 418, parcels: 1690, progress: 79, changes: 36, risk: "合同附件缺失较多" },
  { village: "归仁镇 张宅村", contractors: 392, parcels: 1458, progress: 71, changes: 58, risk: "地块归属变化偏多" },
  { village: "魏营镇 涧圩村", contractors: 366, parcels: 1302, progress: 54, changes: 61, risk: "入户调查滞后" },
  { village: "半城镇 洪安村", contractors: 448, parcels: 1765, progress: 86, changes: 29, risk: "少量面积差异待核查" },
];

const plots = [
  { id: "DK01", tone: "ok", style: { left: "8%", top: "16%", width: "18%", height: "24%" } },
  { id: "DK02", tone: "warn", style: { left: "30%", top: "12%", width: "20%", height: "31%" } },
  { id: "DK03", tone: "risk", style: { left: "54%", top: "18%", width: "16%", height: "25%" } },
  { id: "DK04", tone: "ok", style: { left: "73%", top: "16%", width: "18%", height: "30%" } },
  { id: "DK05", tone: "warn", style: { left: "13%", top: "50%", width: "22%", height: "28%" } },
  { id: "DK06", tone: "ok", style: { left: "39%", top: "52%", width: "20%", height: "27%" } },
  { id: "DK07", tone: "risk", style: { left: "63%", top: "51%", width: "25%", height: "30%" } },
];

const areaDiffs = [
  { code: "32132410120300019", owner: "王明华", diff: "+8.72" },
  { code: "32132410120300026", owner: "张国林", diff: "-6.35" },
  { code: "32132410210800011", owner: "李秀兰", diff: "+5.94" },
  { code: "32132410401600008", owner: "陈建军", diff: "+5.48" },
  { code: "32132410502200031", owner: "周启明", diff: "-4.91" },
];

const parcelCategories = [
  { label: "承包地块", value: 48216, percent: 82, color: "#4f8f59" },
  { label: "自留地", value: 5362, percent: 9, color: "#3d77b8" },
  { label: "机动地", value: 2984, percent: 5, color: "#d99837" },
  { label: "其他", value: 2148, percent: 4, color: "#9b6b54" },
];

const workflowNodes = [
  { label: "申请提交", count: 2946, note: "本批次累计" },
  { label: "村级审核", count: 426, note: "退回 38 件" },
  { label: "镇级审核", count: 317, note: "超期 21 件" },
  { label: "县级审核", count: 148, note: "待集中复核" },
  { label: "归档办结", count: 1928, note: "完整率 86%" },
];

const archiveRows = [
  { caseNo: "YB202605240018", owner: "张国林", node: "镇级审核", missing: "承包合同扫描件、户主身份证复印件", days: 7 },
  { caseNo: "YB202605240026", owner: "王明华", node: "归档复核", missing: "地块示意图、调查表签字页", days: 5 },
  { caseNo: "YB202605230091", owner: "李秀兰", node: "村级补正", missing: "家庭成员确认表", days: 4 },
  { caseNo: "YB202605220067", owner: "陈建军", node: "县级审核", missing: "面积差异说明", days: 8 },
  { caseNo: "YB202605210044", owner: "周启明", node: "归档复核", missing: "审批流转单", days: 6 },
];
</script>

<style scoped>
.viz-page {
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.viz-toolbar,
.metric-card,
.viz-panel,
.viz-tabs {
  border: 1px solid rgba(56, 122, 196, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 12px 28px rgba(25, 74, 128, 0.08);
}

.viz-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: center;
  padding: 16px 18px;
  margin-bottom: 12px;
}

.viz-toolbar h1 {
  margin: 8px 0 6px;
  font-size: 26px;
  line-height: 1.2;
}

.viz-toolbar p,
.panel-head p {
  margin: 0;
  color: var(--muted);
  line-height: 1.55;
}

.viz-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.batch-select {
  width: 250px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.metric-card {
  padding: 14px 16px;
}

.metric-head,
.metric-foot,
.panel-head,
.todo-item,
.diff-row,
.ranking-row,
.category-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.metric-head {
  color: var(--muted);
  font-weight: 700;
}

.metric-value {
  margin-top: 10px;
  font-size: 30px;
  font-weight: 800;
  color: var(--text);
}

.metric-foot {
  margin-top: 8px;
  color: var(--muted);
  font-size: 13px;
}

.metric-foot strong,
.is-blue .metric-head .el-icon {
  color: #356fb2;
}

.is-green .metric-head .el-icon,
.is-green .metric-foot strong {
  color: #3f8d55;
}

.is-orange .metric-head .el-icon,
.is-orange .metric-foot strong {
  color: #c7801f;
}

.is-red .metric-head .el-icon,
.is-red .metric-foot strong {
  color: #c95454;
}

.viz-tabs {
  display: flex;
  gap: 6px;
  padding: 6px;
  margin-bottom: 12px;
}

.viz-tab {
  min-height: 36px;
  padding: 0 18px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-weight: 800;
  cursor: pointer;
}

.viz-tab.is-active {
  color: #25456e;
  border-color: rgba(53, 95, 159, 0.18);
  background: rgba(53, 95, 159, 0.09);
}

.overview-grid,
.analysis-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr);
  gap: 12px;
  padding-bottom: 16px;
}

.viz-panel {
  min-width: 0;
  padding: 14px 16px;
}

.wide-panel {
  grid-column: span 1;
}

.full-panel {
  grid-column: 1 / -1;
}

.panel-head {
  margin-bottom: 14px;
  align-items: flex-start;
}

.panel-head h2 {
  margin: 0 0 4px;
  font-size: 17px;
}

.panel-link {
  flex: 0 0 auto;
  color: #356fb2;
  font-weight: 800;
}

.county-map,
.parcel-map {
  position: relative;
  height: 330px;
  border: 1px solid rgba(48, 101, 81, 0.16);
  border-radius: 8px;
  overflow: hidden;
  background:
    linear-gradient(rgba(53, 95, 159, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(53, 95, 159, 0.08) 1px, transparent 1px),
    linear-gradient(135deg, #eaf3ee, #eef5fb);
  background-size: 32px 32px, 32px 32px, auto;
}

.map-area,
.plot {
  position: absolute;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.72);
  color: #203b32;
  font-weight: 800;
  text-align: center;
  box-shadow: 0 12px 22px rgba(24, 67, 71, 0.12);
}

.map-area {
  border-radius: 32% 48% 38% 44%;
}

.map-area strong {
  font-size: 18px;
}

.level-1 {
  background: rgba(87, 151, 93, 0.62);
}

.level-2 {
  background: rgba(226, 168, 72, 0.62);
}

.level-3 {
  background: rgba(207, 89, 84, 0.62);
}

.map-legend,
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 12px;
  color: var(--muted);
  font-size: 13px;
}

.legend-dot,
.legend-line {
  display: inline-block;
  margin-right: 6px;
  vertical-align: middle;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-line {
  width: 18px;
  height: 6px;
  border-radius: 999px;
}

.is-good,
.legend-line.is-archive {
  background: #57975d;
}

.is-warn,
.legend-line.is-request {
  background: #e2a848;
}

.is-risk {
  background: #cf5954;
}

.legend-line.is-survey {
  background: #356fb2;
}

.status-list,
.todo-list,
.diff-list,
.ranking-list,
.category-bars {
  display: grid;
  gap: 12px;
}

.status-row {
  display: grid;
  gap: 8px;
}

.status-info {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.progress-track,
.ranking-track,
.category-row div {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(46, 74, 109, 0.08);
}

.progress-track span,
.ranking-track i,
.category-row i {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.progress-track .is-green,
.ranking-track i {
  background: #57975d;
}

.progress-track .is-blue {
  background: #356fb2;
}

.progress-track .is-orange {
  background: #d99837;
}

.progress-track .is-red {
  background: #cf5954;
}

.trend-chart {
  height: 250px;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 14px;
  align-items: end;
  padding: 18px 6px 0;
  border-bottom: 1px solid rgba(46, 74, 109, 0.1);
}

.trend-column {
  height: 100%;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  align-items: end;
  position: relative;
  padding-bottom: 24px;
}

.trend-column small {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 2px;
  color: var(--muted);
  text-align: center;
}

.bar {
  min-height: 12px;
  border-radius: 4px 4px 0 0;
}

.bar.is-survey {
  background: #356fb2;
}

.bar.is-request {
  background: #d99837;
}

.bar.is-archive {
  background: #57975d;
}

.todo-item {
  min-height: 58px;
  padding: 10px 12px;
  border: 1px solid rgba(46, 74, 109, 0.1);
  border-radius: 7px;
  background: rgba(248, 251, 255, 0.82);
}

.todo-item div {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 4px;
}

.todo-item small,
.diff-row small,
.change-card small,
.ranking-row small {
  color: var(--muted);
}

.todo-mark {
  width: 9px;
  height: 36px;
  border-radius: 999px;
}

.todo-mark.is-red {
  background: #cf5954;
}

.todo-mark.is-orange {
  background: #d99837;
}

.todo-mark.is-blue {
  background: #356fb2;
}

.todo-mark.is-brown {
  background: #7b643f;
}

.ranking-row {
  grid-template-columns: 110px minmax(0, 1fr) 56px 92px;
}

.change-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.change-card {
  padding: 12px;
  border-radius: 7px;
  background: rgba(53, 95, 159, 0.07);
}

.change-card strong {
  display: block;
  margin: 8px 0 4px;
  font-size: 24px;
}

.parcel-map {
  height: 360px;
  background:
    linear-gradient(rgba(75, 114, 75, 0.12) 1px, transparent 1px),
    linear-gradient(90deg, rgba(75, 114, 75, 0.12) 1px, transparent 1px),
    linear-gradient(135deg, #eff7ec, #e7f1f4);
  background-size: 42px 42px, 42px 42px, auto;
}

.plot {
  border-radius: 7px;
}

.plot.is-ok {
  background: rgba(87, 151, 93, 0.58);
}

.plot.is-warn {
  background: rgba(226, 168, 72, 0.68);
}

.plot.is-risk {
  background: rgba(207, 89, 84, 0.68);
}

.diff-row {
  padding: 11px 12px;
  border-radius: 7px;
  background: rgba(248, 251, 255, 0.9);
}

.diff-row div {
  display: grid;
  gap: 4px;
}

.diff-row span {
  color: #c95454;
  font-weight: 800;
}

.category-row {
  grid-template-columns: 110px minmax(0, 1fr) 90px;
}

.workflow-funnel {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.funnel-step {
  min-height: 140px;
  display: grid;
  align-content: center;
  gap: 8px;
  padding: 14px;
  border-radius: 7px;
  background: linear-gradient(180deg, rgba(53, 95, 159, 0.1), rgba(255, 255, 255, 0.92));
  text-align: center;
}

.funnel-step strong {
  font-size: 28px;
  color: #25456e;
}

.funnel-step small {
  color: var(--muted);
}

.archive-score {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  gap: 16px;
  align-items: center;
}

.score-ring {
  width: 142px;
  height: 142px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background:
    radial-gradient(circle, #fff 56%, transparent 57%),
    conic-gradient(#57975d 0 86%, rgba(46, 74, 109, 0.1) 86% 100%);
  color: #2f6b40;
  font-size: 28px;
  font-weight: 800;
}

.score-notes {
  display: grid;
  gap: 10px;
  color: var(--muted);
}

@media (max-width: 1180px) {
  .metric-grid,
  .overview-grid,
  .analysis-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .wide-panel,
  .map-panel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 760px) {
  .viz-toolbar,
  .panel-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .viz-actions,
  .batch-select {
    width: 100%;
  }

  .metric-grid,
  .overview-grid,
  .analysis-grid,
  .workflow-funnel,
  .archive-score {
    grid-template-columns: 1fr;
  }

  .viz-tabs {
    overflow-x: auto;
  }

  .ranking-row,
  .category-row {
    grid-template-columns: 1fr;
    align-items: start;
  }
}
</style>
