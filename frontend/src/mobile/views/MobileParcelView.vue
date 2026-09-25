<template>
  <div class="m-parcel">
    <van-cell-group inset title="现场定位">
      <van-cell title="当前坐标" :value="coordinateText" />
      <van-cell title="定位精度" :value="accuracyText" />
      <van-cell title="定位来源" :value="sourceText" />
    </van-cell-group>

    <div class="m-parcel__action">
      <van-button block round type="primary" :loading="locating" @click="onLocate">
        获取当前位置
      </van-button>
    </div>

    <van-cell-group inset :title="`地块清单（${parcels.length}）`">
      <van-cell
        v-for="(parcel, index) in parcels"
        :key="parcel.dkbm || index"
        :title="parcel.dkmc || parcel.dkbm || `地块 ${index + 1}`"
        :label="parcel.dkbm || '—'"
      />
      <van-cell v-if="!parcels.length" title="暂无地块数据" />
    </van-cell-group>

    <van-cell-group inset title="地块勾绘">
      <van-cell title="打开勾绘地图" is-link value="待接入" @click="onDrawHint" />
    </van-cell-group>

    <p class="m-parcel__hint">
      正式界址点坐标请在 PC 端维护；手机定位仅用于辅助查找地块。
    </p>
  </div>
</template>

<script setup>
/**
 * 地块清单 + 现场定位（勾绘的地图载体留待二期接入）。
 *
 * 已接通的：
 * - 地块清单 `GET /surveys/batches/{id}/results/{uid}/parcels` → `data.data.items`
 * - 现场定位走 `native/location.js`：
 *   **App 内用 Capacitor 原生定位，不受 HTTPS 约束**（这是套壳相比纯 H5 的实打实的优势）；
 *   浏览器打开则需要 HTTPS 安全上下文，否则会明确提示"浏览器已禁用定位"。
 * - 坐标系为 WGS84，与项目 EPSG:4326/3857 地图直接一致，无需纠偏。
 *
 * 待接入（二期）：
 * - 勾绘地图 = OpenLayers 内嵌页，直接复用 PC 端的
 *   `composables/survey/useAddParcelGeometry.js`（`ol/interaction/Draw`）
 *   与 `useSplitParcel.js` / `useParcelDraftMap.js`；
 *   界址点/界址线的正式维护仍按既定边界留在 PC 端。
 */
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { fetchSurveyParcels } from "../../api/survey";
import { describeAccuracy, getCurrentPosition, isNativePlatform } from "../native/location.js";
import { VanButton, VanCell, VanCellGroup, showToast } from "../ui.js";

const route = useRoute();

const batchId = computed(() => String(route.params.batchId || ""));
const contractorUid = computed(() => String(route.params.contractorUid || ""));

const parcels = ref([]);
const locating = ref(false);
const position = ref(null);

const coordinateText = computed(() =>
  position.value
    ? `${position.value.longitude.toFixed(6)}, ${position.value.latitude.toFixed(6)}`
    : "尚未定位",
);
const accuracyText = computed(() =>
  position.value ? describeAccuracy(position.value.accuracy) : "—",
);
const sourceText = computed(() => {
  if (!position.value) return isNativePlatform() ? "原生定位" : "浏览器定位";
  return position.value.source === "native" ? "原生定位（App）" : "浏览器定位（需 HTTPS）";
});

async function loadParcels() {
  try {
    const { data } = await fetchSurveyParcels(batchId.value, contractorUid.value, {
      page: 1,
      page_size: 200,
    });
    parcels.value = data?.data?.items || data?.data || [];
  } catch (error) {
    showToast(error?.response?.data?.detail || "地块加载失败");
    parcels.value = [];
  }
}

async function onLocate() {
  locating.value = true;
  try {
    position.value = await getCurrentPosition({ enableHighAccuracy: true, timeout: 15000 });
  } catch (error) {
    showToast(error?.message || "定位失败");
  } finally {
    locating.value = false;
  }
}

function onDrawHint() {
  showToast("勾绘地图将在二期接入（复用 PC 端 OpenLayers 勾绘能力）");
}

onMounted(loadParcels);
</script>

<style scoped>
.m-parcel {
  padding-bottom: 24px;
}

.m-parcel__action {
  padding: 16px 16px 6px;
}

.m-parcel__hint {
  margin: 16px 24px 0;
  font-size: 12px;
  line-height: 1.7;
  color: #a6adbb;
  text-align: center;
}
</style>
