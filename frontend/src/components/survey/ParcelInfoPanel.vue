<template>
  <div class="parcel-info-panel">
    <!-- 变化提示 -->
    <el-alert
      v-if="changedParcels.length > 0"
      title="地块信息发生变化"
      type="warning"
      :closable="false"
      show-icon
      class="change-alert"
    >
      <template #default>
        共 {{ changedParcels.length }} 处地块发生变化，
        <el-button link type="warning" size="small" @click="diffViewer?.open(batchId, contractorUid)">
          查看变化详情
        </el-button>
      </template>
    </el-alert>

    <div class="parcel-layout">
      <!-- 左侧地图 -->
      <div class="parcel-map-container">
        <div ref="mapRoot" class="parcel-map"></div>
        <div class="basemap-switch">
          <el-select
            v-model="activeBasemap"
            size="small"
            placeholder="底图"
            @change="handleBasemapChange"
          >
            <el-option
              v-for="opt in basemapOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
      </div>

      <!-- 右侧地块列表 -->
      <div class="parcel-list">
        <el-table
          :data="parcels"
          border
          size="small"
          highlight-current-row
          v-loading="parcelsLoading"
          @row-click="selectParcel"
          max-height="calc(92vh - 380px)"
        >
          <el-table-column prop="dkbm" label="地块编码" width="140" />
          <el-table-column prop="dkmc" label="地块名称" min-width="120" />
          <el-table-column label="面积(㎡)" width="100">
            <template #default="{ row }">
              <span :class="parcelChangedClass(row, 'scmj')">{{ row.scmj ?? '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类别" width="80">
            <template #default="{ row }">{{ dklbMap[row.dklb] || row.dklb || '-' }}</template>
          </el-table-column>
          <el-table-column label="是否基本农田" width="100">
            <template #default="{ row }">{{ row.sfjbnt === '1' ? '是' : '否' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.isChanged" type="warning" size="small">变更</el-tag>
              <el-tag v-else type="success" size="small">正常</el-tag>
            </template>
          </el-table-column>
        </el-table>

        <!-- 选中地块详情 -->
        <div v-if="selectedParcel" class="parcel-detail">
          <el-descriptions :column="2" border size="small" :title="selectedParcel.dkmc">
            <el-descriptions-item label="地块编码">{{ selectedParcel.dkbm }}</el-descriptions-item>
            <el-descriptions-item label="实测面积">{{ selectedParcel.scmj }} ㎡</el-descriptions-item>
            <el-descriptions-item label="合同面积">{{ selectedParcel.htmj }} ㎡</el-descriptions-item>
            <el-descriptions-item label="土地利用类型">{{ tdlylxMap[selectedParcel.tdlylx] || selectedParcel.tdlylx || '-' }}</el-descriptions-item>
            <el-descriptions-item label="东至">{{ selectedParcel.dkdz || '-' }}</el-descriptions-item>
            <el-descriptions-item label="西至">{{ selectedParcel.dkxz || '-' }}</el-descriptions-item>
            <el-descriptions-item label="南至">{{ selectedParcel.dknz || '-' }}</el-descriptions-item>
            <el-descriptions-item label="北至">{{ selectedParcel.dkbz || '-' }}</el-descriptions-item>
            <el-descriptions-item label="承包方">{{ selectedParcel.cbfmc || '-' }}</el-descriptions-item>
            <el-descriptions-item label="合同编码">{{ selectedParcel.cbhtbm || '-' }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </div>

    <ChangeDiffViewer ref="diffViewer" />
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from "vue";
import ChangeDiffViewer from "./ChangeDiffViewer.vue";
import { useDialogMap } from "../../composables/useDialogMap";

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  parcels: { type: Array, default: () => [] },
  parcelsLoading: { type: Boolean, default: false },
});

const diffViewer = ref(null);
const mapRoot = ref(null);
const selectedParcel = ref(null);

const dklbMap = { "01": "耕地", "02": "园地", "03": "林地", "04": "草地", "05": "养殖水面", "09": "其他" };
const tdlylxMap = {
  "011": "水田", "012": "水浇地", "013": "旱地",
  "021": "果园", "022": "茶园", "023": "其他园地",
  "031": "有林地", "032": "灌木林地", "033": "其他林地",
  "041": "天然牧草地", "042": "人工牧草地",
  "111": "设施农用地", "114": "坑塘水面",
};

const {
  mapReady, activeBasemap, basemapOptions,
  initMap, loadParcels, fitToParcels, focusParcel, clearSelection, updateMapSize, destroyMap,
} = useDialogMap(mapRoot);

const changedParcels = computed(() => props.parcels.filter((p) => p.isChanged));

function parcelChangedClass(row, field) {
  if (!row.isChanged) return "";
  return "field-changed";
}

function selectParcel(parcel) {
  selectedParcel.value = parcel;
  focusParcel(parcel.dkbm);
}

function handleBasemapChange() {
  // handled by useDialogMap composable
}

watch(() => props.parcels, async (list) => {
  if (!mapReady.value) {
    await initMap();
  }
  if (list.length) {
    loadParcels(list);
    fitToParcels();
  }
}, { immediate: false });

onMounted(async () => {
  if (!mapReady.value) {
    await initMap();
  }
  setTimeout(() => {
    if (mapRoot.value) updateMapSize();
  }, 200);
});

onBeforeUnmount(() => {
  destroyMap();
});
</script>

<style scoped>
.parcel-info-panel { min-height: 400px; }
.change-alert { margin-bottom: 12px; }
.parcel-layout { display: flex; gap: 12px; height: calc(92vh - 340px); min-height: 450px; }
.parcel-map-container { flex: 1; position: relative; min-width: 0; border: 1px solid #ebeef5; border-radius: 4px; overflow: hidden; }
.parcel-map { width: 100%; height: 100%; }
.basemap-switch { position: absolute; top: 8px; right: 8px; z-index: 10; width: 140px; }
.parcel-list { width: 420px; display: flex; flex-direction: column; gap: 8px; overflow: hidden; }
.parcel-detail { flex-shrink: 0; max-height: 220px; overflow-y: auto; }
.field-changed { background-color: #fdf6ec; padding: 2px 6px; border-radius: 3px; }
</style>
