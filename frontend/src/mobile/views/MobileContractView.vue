<template>
  <div class="m-contract">
    <van-cell-group inset title="合同版本">
      <van-field
        :model-value="versionLabel"
        readonly
        is-link
        label="当前版本"
        placeholder="暂无合同"
        @click="contracts.length > 1 && (versionPickerVisible = true)"
      />
    </van-cell-group>

    <van-cell-group v-if="detail" title="合同信息">
      <van-cell title="合同编号" :value="detail.cbhtbm || '—'" />
      <van-cell v-if="detail.ycbhtbm" title="原合同编号" :value="detail.ycbhtbm" />
      <van-cell title="发包方" :value="detail.fbfmc || detail.fbfbm || '—'" />
      <van-cell title="承包方编码" :value="detail.cbfbm || '—'" />
      <van-cell title="承包方式" :value="cbfsLabel" />
      <van-cell title="承包期限" :value="termText" />
      <van-cell title="合同面积（亩）" :value="formatNumber(detail.htzmj)" />
      <van-cell title="合同面积（㎡）" :value="formatNumber(detail.htzmjm)" />
      <van-cell title="地块数" :value="detail.cbdkzs ?? '—'" />
      <van-cell title="签订时间" :value="detail.qdsj || '—'" />
      <van-cell v-if="detail.contractStatusText" title="合同状态" :value="detail.contractStatusText" />
      <van-cell v-if="generatedAtText !== '—'" title="生成时间" :value="generatedAtText" />
    </van-cell-group>

    <van-empty v-if="!loading && !contracts.length" description="该户暂无合同信息" />

    <div v-if="detail?.renderedHtml" class="m-contract__preview">
      <van-cell-group inset title="合同文本预览">
        <ScaledHtmlFrame :html="detail.renderedHtml" :loading="detailLoading" empty-text="暂无合同文本" />
      </van-cell-group>
    </div>

    <van-popup v-model:show="versionPickerVisible" position="bottom" round>
      <van-picker
        :columns="versionColumns"
        title="选择合同版本"
        @confirm="onVersionConfirm"
        @cancel="versionPickerVisible = false"
      />
    </van-popup>
  </div>
</template>

<script setup>
/**
 * 合同信息（移动端只读查看）。
 *
 * 数据源与 PC 端 ContractInfoPanel 相同：
 * - 版本目录：`GET .../contracts` → `{ contracts[], currentCode, originalCode }`
 * - 明细：`GET .../contracts/{cbhtbm}`（含 renderedHtml 合同文本）
 * 移动端只做查看：字段浏览 + 合同文本缩放预览；生成 / 打印 / 上传仍走 PC 端。
 */
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  fetchSurveyContractDetail,
  fetchSurveyContracts,
} from "../../api/survey";
import ScaledHtmlFrame from "../components/ScaledHtmlFrame.vue";
import {
  VanCell,
  VanCellGroup,
  VanEmpty,
  VanField,
  VanPicker,
  VanPopup,
  showToast,
} from "../ui.js";

const CBFS_OPTIONS = {
  "001": "家庭承包",
  "002": "其他方式承包",
  "003": "招标",
  "004": "拍卖",
  "005": "公开协商",
};

const route = useRoute();

const batchId = computed(() => route.params.batchId);
const contractorUid = computed(() => route.params.contractorUid);

const loading = ref(false);
const detailLoading = ref(false);
const contracts = ref([]);
const activeCode = ref(null);
const detail = ref(null);
const versionPickerVisible = ref(false);

const activeContract = computed(() => contracts.value.find((item) => item.cbhtbm === activeCode.value) || null);

const versionLabel = computed(() => {
  if (!activeContract.value) return "";
  const kind = activeContract.value.contractSourceText || "合同";
  const status = activeContract.value.contractStatusText || "";
  const suffix = status ? `·${status}` : "";
  return `${kind}${suffix}`;
});

const versionColumns = computed(() =>
  contracts.value.map((item) => ({
    text: `${item.contractSourceText || "合同"}·${item.contractStatusText || ""}（${item.cbhtbm}）`,
    value: item.cbhtbm,
  })),
);

const cbfsLabel = computed(() => CBFS_OPTIONS[detail.value?.cbfs] || detail.value?.cbfs || "—");
const termText = computed(() => {
  const start = detail.value?.cbqxq || "—";
  const end = detail.value?.cbqxz || "—";
  return `${start} 至 ${end}`;
});
const generatedAtText = computed(() => {
  const text = detail.value?.generatedAt || "";
  return text ? text.slice(0, 19).replace("T", " ") : "—";
});

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  return Number(value).toFixed(2);
}

async function loadContracts() {
  loading.value = true;
  try {
    const { data } = await fetchSurveyContracts(batchId.value, contractorUid.value);
    const catalog = data?.data || {};
    contracts.value = catalog.contracts || [];
    activeCode.value = catalog.currentCode || catalog.originalCode || contracts.value[0]?.cbhtbm || null;
    await loadDetail();
  } catch (error) {
    contracts.value = [];
    activeCode.value = null;
    detail.value = null;
    showToast(error?.response?.data?.detail || "合同信息加载失败");
  } finally {
    loading.value = false;
  }
}

async function loadDetail() {
  if (!activeCode.value) {
    detail.value = null;
    return;
  }
  detailLoading.value = true;
  try {
    const { data } = await fetchSurveyContractDetail(batchId.value, contractorUid.value, activeCode.value);
    detail.value = data?.data || null;
  } catch {
    detail.value = null;
  } finally {
    detailLoading.value = false;
  }
}

function onVersionConfirm({ selectedOptions }) {
  activeCode.value = selectedOptions?.[0]?.value || activeCode.value;
  versionPickerVisible.value = false;
  void loadDetail();
}

onMounted(loadContracts);
</script>

<style scoped>
.m-contract {
  padding-bottom: 24px;
}

.m-contract__preview {
  margin-top: 12px;
}
</style>
