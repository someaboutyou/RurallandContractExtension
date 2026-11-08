<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    :width="620"
    :close-on-click-modal="!running"
    :close-on-press-escape="!running"
    :show-close="!running"
    append-to-body
    @closed="onClosed"
  >
    <el-alert type="info" :closable="false" show-icon class="generate-tip">
      <template #title>
        <template v-if="isBatch">
          将按下方统一口径为 <b>{{ targets.length }}</b> 户承包方逐户生成延包合同；每户生成后其上一份合同置为<b>历史状态</b>（仍可查看与打印）。
        </template>
        <template v-else>
          按当前调查信息生成新的延包合同；生成后上一份合同将置为<b>历史状态</b>，仍可随时查看与打印。
        </template>
      </template>
    </el-alert>

    <!-- 批量签订进度：运行中/结束时替换表单展示 -->
    <div v-if="running || progress.finished" class="progress-block">
      <el-progress
        :percentage="progressPercent"
        :status="progress.finished ? (progress.failCount ? 'warning' : 'success') : undefined"
      />
      <div class="progress-text">
        <template v-if="running">正在签订：{{ progress.current || "" }}（{{ progress.done }}/{{ progress.total }}）</template>
        <template v-else>
          完成：成功 {{ progress.successCount }} 户<template v-if="progress.failCount">，失败 {{ progress.failCount }} 户</template>
        </template>
      </div>
      <el-alert
        v-if="progress.finished && progress.failures.length"
        type="error"
        :closable="false"
        show-icon
        class="fail-list"
      >
        <template #title>以下承包户签订失败：</template>
        <div v-for="item in progress.failures" :key="item.contractorUid" class="fail-item">
          {{ item.cbfmc || item.contractorUid }}：{{ item.reason }}
        </div>
      </el-alert>
    </div>

    <el-form v-else :model="termForm" label-width="130px" class="generate-form" v-loading="catalogLoading">
      <el-form-item v-if="isBatch" label="签订范围">
        <span class="read-only-text">已选 {{ targets.length }} 户（{{ targetNames }}{{ targets.length > 3 ? " 等" : "" }}）</span>
      </el-form-item>
      <el-form-item v-if="!isBatch" label="上次合同到期">
        <span class="read-only-text">
          {{ catalog.defaultTermStart || "（无上次承包合同，需人工填写起始日期）" }}
        </span>
      </el-form-item>
      <el-form-item label="承包期限起" required>
        <el-date-picker
          v-model="termForm.cbqxq"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="默认为上次合同到期时间"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="承包期限（年）">
        <el-input-number v-model="termForm.years" :min="1" :max="100" :step="1" />
      </el-form-item>
      <el-form-item label="承包期限止">
        <el-date-picker
          v-model="termForm.cbqxz"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="按起期 + 年限自动计算，可修改"
          style="width: 100%"
          @change="endTouched = true"
        />
      </el-form-item>
      <el-form-item label="签订日期">
        <el-date-picker
          v-model="termForm.qdsj"
          type="date"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="承包方式">
        <el-select v-model="termForm.cbfs" style="width: 100%">
          <el-option
            v-for="(label, value) in CBFS_OPTIONS"
            :key="value"
            :label="label"
            :value="value"
          />
        </el-select>
      </el-form-item>
      <el-form-item v-if="!isBatch" label="合同面积/地块">
        <span class="read-only-text">
          {{ formatNumber(catalog.activeContract?.htzmj) }} ㎡（{{ catalog.activeContract?.cbdkzs ?? 0 }} 个地块，按当前调查信息计算）
        </span>
      </el-form-item>
      <el-form-item v-if="!isBatch && catalog.currentCode" label="现有延包合同">
        <span class="read-only-text warn">{{ catalog.currentCode }}（生成后置为历史）</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <template v-if="progress.finished">
        <el-button type="primary" @click="visible = false">关闭</el-button>
      </template>
      <template v-else-if="!running">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="submit">确认{{ isBatch ? "批量" : "" }}生成</el-button>
      </template>
      <template v-else>
        <el-button disabled>签订中，请勿关闭…</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 「生成延包合同」共用对话框 —— 承包方调查录入（ContractInfoPanel）与
 * 承包合同管理页两个入口共用同一份表单与提交逻辑，禁止各写各的。
 *
 * - 单户模式（targets.length === 1）：先拉该户合同清单做默认值
 *   （承包期限起 = 上次合同到期，承包方式沿用现行合同）。
 * - 批量模式：表单统一填一次口径，逐户调用同一个
 *   ``generateSurveyContract`` 单户接口（服务端口径完全一致），
 *   前端串行推进并显示进度条，逐户记录成功 / 失败。
 */
import { computed, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { generateSurveyContract, fetchSurveyContracts } from "../../api/survey";

const props = defineProps({
  batchId: { type: Number, default: null },
  batchStatus: { type: String, default: "active" },
});

const emit = defineEmits(["completed"]);

const CBFS_OPTIONS = {
  "001": "家庭承包",
  "002": "其他方式承包",
  "003": "招标",
  "004": "拍卖",
  "005": "公开协商",
};

const visible = ref(false);
const running = ref(false);
const generating = ref(false);
const catalogLoading = ref(false);
const endTouched = ref(false);
const targets = ref([]);
const termForm = reactive({ cbqxq: "", cbqxz: "", years: 30, qdsj: "", cbfs: "001" });
// 单户模式下的合同清单（默认值来源）；批量模式不预取
const catalog = ref({ currentCode: null, defaultTermStart: null, defaultYears: 30, activeContract: null });
const progress = reactive({
  total: 0,
  done: 0,
  successCount: 0,
  failCount: 0,
  failures: [],
  current: "",
  finished: false,
});

const isBatch = computed(() => targets.value.length > 1);
const dialogTitle = computed(() =>
  isBatch.value ? `批量签订延包合同（${targets.value.length} 户）` : "生成延包合同",
);
const targetNames = computed(() => targets.value.slice(0, 3).map((item) => item.cbfmc || item.contractorUid).join("、"));
const progressPercent = computed(() =>
  progress.total ? Math.round((progress.done / progress.total) * 100) : 0,
);

function todayString() {
  const now = new Date();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

// 止期 = 起期 + 年限 − 1 天，使打印件上的「承包期限」正好等于所填年限
function computeTermEnd(start, years) {
  if (!start || !years) return "";
  const date = new Date(`${start}T00:00:00`);
  date.setFullYear(date.getFullYear() + Number(years));
  date.setDate(date.getDate() - 1);
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  return Number(value).toFixed(2);
}

/**
 * 打开对话框。contractors: [{ contractorUid, cbfmc }]，单项=单户，多项=批量。
 */
async function open({ contractors }) {
  const list = (contractors || []).filter((item) => item?.contractorUid);
  if (!list.length) {
    ElMessage.warning("没有可签订合同的承包方");
    return;
  }
  if (!props.batchId) {
    ElMessage.warning("请先选择调查批次");
    return;
  }
  if (props.batchStatus === "finished") {
    ElMessage.warning("调查批次已结束，不能生成合同");
    return;
  }
  targets.value = list;
  progress.total = list.length;
  progress.done = 0;
  progress.successCount = 0;
  progress.failCount = 0;
  progress.failures = [];
  progress.current = "";
  progress.finished = false;
  running.value = false;
  generating.value = false;
  catalog.value = { currentCode: null, defaultTermStart: null, defaultYears: 30, activeContract: null };
  endTouched.value = false;
  termForm.years = 30;
  termForm.cbqxq = "";
  termForm.cbqxz = "";
  termForm.qdsj = todayString();
  termForm.cbfs = "001";
  visible.value = true;

  if (!isBatch.value) {
    // 单户模式：拉合同清单填默认值（与调查录入「合同生成」同一数据源）
    catalogLoading.value = true;
    try {
      const { data } = await fetchSurveyContracts(props.batchId, list[0].contractorUid);
      const payload = data.data || {};
      const contracts = payload.contracts || [];
      // 与原「合同生成」口径一致：现行 → 上次承包合同 → 首个版本
      const preferredCode = payload.currentCode || payload.originalCode || contracts[0]?.cbhtbm || null;
      catalog.value = {
        ...payload,
        activeContract: contracts.find((item) => item.cbhtbm === preferredCode) || null,
      };
      termForm.cbqxq = payload.defaultTermStart || "";
      termForm.years = payload.defaultYears || 30;
      termForm.cbqxz = computeTermEnd(termForm.cbqxq, termForm.years);
      const cbfs = catalog.value.activeContract?.cbfs || "";
      termForm.cbfs = CBFS_OPTIONS[cbfs] ? cbfs : "001";
    } catch {
      /* 拿不到清单就保持空默认值，人工填写 */
    } finally {
      catalogLoading.value = false;
    }
  }
}

function syncTermEnd() {
  if (endTouched.value) return;
  termForm.cbqxz = computeTermEnd(termForm.cbqxq, termForm.years);
}

async function submit() {
  if (!termForm.cbqxq) {
    ElMessage.warning("请填写承包期限起始日期");
    return;
  }
  if (termForm.cbqxz && termForm.cbqxz < termForm.cbqxq) {
    ElMessage.warning("承包期限止不能早于起始日期");
    return;
  }
  try {
    if (isBatch.value) {
      await ElMessageBox.confirm(
        `将为 ${targets.value.length} 户承包方生成延包合同；已签订的承包户会重新生成并把原合同置为历史状态。是否继续？`,
        "确认批量签订",
        { type: "warning", confirmButtonText: "开始签订", cancelButtonText: "取消" },
      );
    } else if (catalog.value.currentCode) {
      await ElMessageBox.confirm(
        `生成后现有延包合同（${catalog.value.currentCode}）将置为历史状态，是否继续？`,
        "确认生成延包合同",
        { type: "warning" },
      );
    }
  } catch {
    return; // 用户取消
  }

  const payload = {
    cbqxq: termForm.cbqxq,
    cbqxz: termForm.cbqxz || null,
    years: termForm.years,
    qdsj: termForm.qdsj || null,
    cbfs: termForm.cbfs || null,
  };

  running.value = true;
  generating.value = true;
  let lastCode = null;
  try {
    for (const target of targets.value) {
      progress.current = target.cbfmc || target.contractorUid;
      try {
        const { data } = await generateSurveyContract(props.batchId, target.contractorUid, payload);
        lastCode = data.data?.cbhtbm || lastCode;
        progress.successCount += 1;
      } catch (error) {
        progress.failCount += 1;
        progress.failures.push({
          contractorUid: target.contractorUid,
          cbfmc: target.cbfmc || "",
          reason: error?.response?.data?.detail || "生成失败",
        });
      }
      progress.done += 1;
    }
  } finally {
    running.value = false;
    generating.value = false;
    progress.finished = true;
  }

  if (isBatch.value) {
    if (!progress.failCount) ElMessage.success(`批量签订完成：成功 ${progress.successCount} 户`);
    else ElMessage.warning(`批量签订完成：成功 ${progress.successCount} 户，失败 ${progress.failCount} 户`);
  } else if (!progress.failCount) {
    ElMessage.success(`延包合同已生成：${lastCode || ""}`);
  }
  emit("completed", {
    total: progress.total,
    successCount: progress.successCount,
    failCount: progress.failCount,
    failures: [...progress.failures],
    lastCode,
  });
}

function onClosed() {
  // 全部成功后自动清场；有失败时保留面板供用户查看失败清单
  if (progress.finished && !progress.failCount) {
    progress.finished = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.generate-tip {
  margin-bottom: 12px;
}
.generate-form {
  margin-top: 4px;
}
.read-only-text {
  font-size: 13px;
  color: #606266;
}
.read-only-text.warn {
  color: #e6a23c;
}
.progress-block {
  padding: 8px 4px 4px;
}
.progress-text {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}
.fail-list {
  margin-top: 12px;
}
.fail-item {
  font-size: 12px;
  line-height: 1.8;
}
</style>
