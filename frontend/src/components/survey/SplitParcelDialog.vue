<template>
  <el-dialog
    v-model="visible"
    title="切割地块"
    width="1120px"
    destroy-on-close
    @opened="handleDialogOpened"
    @closed="handleDialogClosed"
  >
    <el-alert
      title="切割地块支持两种方式：1. 按图形切割，可上传 SHP 或在地图中绘制切割线/切割面；2. 按面积和方向切割，从东、西、南、北四个方向按指定面积切出新地块。"
      type="info"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <div class="base-grid">
      <el-form-item label="待切割地块" required class="base-field">
        <el-select
          v-model="form.dkbm"
          placeholder="请先选择右侧列表中的地块"
          style="width: 100%"
        >
          <el-option
            v-for="item in parcels"
            :key="item.dkbm"
            :label="`${item.dkbm} - ${item.dkmc || '未命名地块'}（${item.scmj || 0} 亩）`"
            :value="item.dkbm"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="新地块编码" required class="base-field">
        <el-input v-model="form.newDkbm" maxlength="19" placeholder="请输入 19 位地块编码">
          <template #append>
            <el-button :loading="generatingCode" @click="handleGenerateCode">自动生成</el-button>
          </template>
        </el-input>
      </el-form-item>

      <el-form-item label="新地块名称" required class="base-field">
        <el-input v-model="form.newDkmc" maxlength="50" placeholder="例如：切割地块 A" />
      </el-form-item>
    </div>

    <el-descriptions v-if="selectedParcel" :column="4" border size="small" class="source-summary">
      <el-descriptions-item label="原地块编码">{{ selectedParcel.dkbm }}</el-descriptions-item>
      <el-descriptions-item label="原地块名称">{{ selectedParcel.dkmc || "-" }}</el-descriptions-item>
      <el-descriptions-item label="原实测面积">{{ selectedParcel.scmj || 0 }} 亩</el-descriptions-item>
      <el-descriptions-item label="四至">
        东 {{ selectedParcel.dkdz || "-" }} / 西 {{ selectedParcel.dkxz || "-" }}
      </el-descriptions-item>
    </el-descriptions>

    <el-alert
      v-if="selectedParcel && !selectedParcel.geometry"
      title="当前选中的地块没有空间图形，无法使用图形切割或按方向切割。请先确认该地块已具备图形数据。"
      type="warning"
      :closable="false"
      show-icon
      class="geometry-alert"
    />

    <el-tabs v-model="activeMode">
      <el-tab-pane label="按图形切割" name="geometry">
        <div class="graphic-layout">
          <div class="graphic-map-card">
            <div class="graphic-toolbar">
              <el-button
                size="small"
                :type="drawMode === 'line' ? 'primary' : 'default'"
                :disabled="!selectedParcelHasGeometry"
                @click="startDrawMode('line')"
              >
                绘制切割线
              </el-button>
              <el-button
                size="small"
                :type="drawMode === 'polygon' ? 'primary' : 'default'"
                :disabled="!selectedParcelHasGeometry"
                @click="startDrawMode('polygon')"
              >
                绘制切割面
              </el-button>
              <label class="upload-button" :class="{ disabled: !selectedParcelHasGeometry }">
                <input
                  class="upload-input"
                  type="file"
                  accept=".zip,application/zip"
                  :disabled="!selectedParcelHasGeometry"
                  @change="handleShpUpload"
                />
                <span>上传 SHP</span>
              </label>
              <el-button size="small" :disabled="!splitGeometry" @click="clearSplitGeometry">清除图形</el-button>
              <el-select
                v-model="activeBasemap"
                size="small"
                placeholder="底图"
                class="basemap-select"
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

            <div ref="mapRoot" class="split-map"></div>

            <div class="graphic-status">
              <span>当前地块：{{ selectedParcel?.dkbm || "-" }}</span>
              <span>图形来源：{{ geometrySourceLabel }}</span>
              <span>图形类型：{{ splitGeometryTypeLabel }}</span>
              <span v-if="uploadedFilename">文件：{{ uploadedFilename }}</span>
            </div>
          </div>

          <div class="graphic-side">
            <el-alert
              :title="graphicHintText"
              :type="selectedParcelHasGeometry ? 'success' : 'warning'"
              :closable="false"
              show-icon
            />

            <div class="graphic-help">
              <div class="help-title">图形切割说明</div>
              <div class="help-line">1. 先在上方选择待切割地块。</div>
              <div class="help-line">2. 选择“绘制切割线”或“绘制切割面”，也可以直接上传 SHP。</div>
              <div class="help-line">3. 保存时系统会按切割图形把原地块分成两部分，并生成新地块。</div>
              <div class="help-line">4. 绘制切割线时，系统会保留面积较大的部分作为原地块。</div>
            </div>

            <el-form-item label="切割原因" class="reason-field">
              <el-input
                v-model="form.reason"
                type="textarea"
                :rows="4"
                maxlength="500"
                show-word-limit
                placeholder="请输入本次切割原因"
              />
            </el-form-item>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="按面积和方向切割" name="area">
        <el-form label-position="top" class="area-form">
          <div class="area-grid">
            <el-form-item label="切出面积（亩）" required class="base-field">
              <el-input-number
                v-model="form.newScmj"
                :min="0.01"
                :max="maxSplitArea"
                :precision="2"
                style="width: 100%"
              />
              <div v-if="selectedParcel" class="area-hint">
                原地块 {{ selectedParcel.scmj || 0 }} 亩，预计剩余 {{ remainingArea }} 亩
              </div>
            </el-form-item>

            <el-form-item label="切割方向" required class="base-field direction-field">
              <el-radio-group v-model="form.splitDirection" class="direction-grid">
                <el-radio-button
                  v-for="item in directionOptions"
                  :key="item.value"
                  :label="item.value"
                >
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>
          </div>

          <el-form-item label="切割原因">
            <el-input
              v-model="form.reason"
              type="textarea"
              :rows="3"
              maxlength="500"
              show-word-limit
              placeholder="请输入本次切割原因"
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="handleSubmit"
      >
        确认切割
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import shp from "shpjs";
import Draw from "ol/interaction/Draw";
import GeoJSON from "ol/format/GeoJSON";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import { Fill, Stroke, Style } from "ol/style";

import { generateNextSurveyParcelCode } from "../../api/survey";
import { useDialogMap } from "../../composables/useDialogMap";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const generatingCode = ref(false);
const batchId = ref(null);
const contractorUid = ref("");
const parcels = ref([]);
const activeMode = ref("geometry");
const mapRoot = ref(null);
const uploadedFilename = ref("");
const splitGeometry = ref(null);
const geometrySource = ref("");
const drawMode = ref("");

function defaultForm() {
  return {
    dkbm: "",
    newDkbm: "",
    newDkmc: "",
    newScmj: 0,
    splitDirection: "east",
    reason: "",
  };
}

const form = reactive(defaultForm());

const selectedParcel = computed(() =>
  parcels.value.find((item) => item.dkbm === form.dkbm) || null
);
const selectedParcelHasGeometry = computed(() => Boolean(selectedParcel.value?.geometry));
const maxSplitArea = computed(() => {
  if (!selectedParcel.value) return 0;
  const area = Number(selectedParcel.value.scmj || 0);
  return Math.max(0, +(area - 0.01).toFixed(2));
});
const remainingArea = computed(() => {
  if (!selectedParcel.value) return 0;
  const area = Number(selectedParcel.value.scmj || 0);
  return Math.max(0, +(area - Number(form.newScmj || 0)).toFixed(2));
});
const geometrySourceLabel = computed(() => {
  if (geometrySource.value === "draw-line") return "手绘切割线";
  if (geometrySource.value === "draw-polygon") return "手绘切割面";
  if (geometrySource.value === "upload") return "上传 SHP";
  return "未提供";
});
const splitGeometryTypeLabel = computed(() => {
  if (!splitGeometry.value?.type) return "未提供";
  if (splitGeometry.value.type === "LineString") return "LineString";
  if (splitGeometry.value.type === "MultiLineString") return "MultiLineString";
  if (splitGeometry.value.type === "Polygon") return "Polygon";
  if (splitGeometry.value.type === "MultiPolygon") return "MultiPolygon";
  return splitGeometry.value.type;
});
const graphicHintText = computed(() => {
  if (!selectedParcel.value) {
    return "请先在弹框顶部选择待切割地块。";
  }
  if (!selectedParcelHasGeometry.value) {
    return "当前地块没有图形数据，暂时无法切割。";
  }
  if (!splitGeometry.value) {
    return "请上传 SHP，或在地图中绘制切割线/切割面。";
  }
  return "切割图形已准备好，确认后会进入待保存队列。";
});
const directionOptions = computed(() => [
  { value: "east", label: `从东侧切割（东至：${selectedParcel.value?.dkdz || "-"}）` },
  { value: "west", label: `从西侧切割（西至：${selectedParcel.value?.dkxz || "-"}）` },
  { value: "south", label: `从南侧切割（南至：${selectedParcel.value?.dknz || "-"}）` },
  { value: "north", label: `从北侧切割（北至：${selectedParcel.value?.dkbz || "-"}）` },
]);
const canSubmit = computed(() => {
  if (!form.dkbm || !form.newDkbm.trim() || !form.newDkmc.trim() || !selectedParcelHasGeometry.value) {
    return false;
  }
  if (activeMode.value === "geometry") {
    return Boolean(splitGeometry.value);
  }
  return (
    Number(form.newScmj) > 0 &&
    Number(form.newScmj) < Number(selectedParcel.value?.scmj || 0) &&
    Boolean(form.splitDirection)
  );
});

const {
  mapRef,
  mapReady,
  activeBasemap,
  basemapOptions,
  initMap,
  switchBasemap,
  loadParcels,
  fitToParcels,
  focusParcel,
  updateMapSize,
  destroyMap,
} = useDialogMap(mapRoot);

const geoJsonFormat = new GeoJSON();
const draftSource = new VectorSource();
const draftLayer = new VectorLayer({
  source: draftSource,
  style: new Style({
    fill: new Fill({ color: "rgba(37, 99, 235, 0.18)" }),
    stroke: new Stroke({ color: "#2563eb", width: 3, lineDash: [10, 6] }),
  }),
  zIndex: 1100,
});
let drawInteraction = null;
let draftLayerMounted = false;

function buildExistingCodeSet() {
  return new Set(
    parcels.value
      .map((item) => String(item?.dkbm || "").trim())
      .filter(Boolean),
  );
}

function ensureLocalUniqueParcelCode(prefix, sequence, candidate) {
  const existingCodes = buildExistingCodeSet();
  let nextSequence = Number(sequence) || 1;
  let nextCode = String(candidate || "").trim();
  if (!prefix) {
    return nextCode;
  }
  while (existingCodes.has(nextCode)) {
    nextSequence += 1;
    nextCode = `${prefix}${String(nextSequence).padStart(5, "0")}`;
  }
  return nextCode;
}

function stopDraw() {
  if (drawInteraction && mapRef.value) {
    mapRef.value.removeInteraction(drawInteraction);
  }
  drawInteraction = null;
  drawMode.value = "";
}

function ensureDraftLayer() {
  if (!mapRef.value || draftLayerMounted) return;
  mapRef.value.addLayer(draftLayer);
  draftLayerMounted = true;
}

function removeDraftLayer() {
  if (!mapRef.value || !draftLayerMounted) return;
  mapRef.value.removeLayer(draftLayer);
  draftLayerMounted = false;
}

function writeGeometryObject(feature) {
  if (!feature) return null;
  return geoJsonFormat.writeGeometryObject(feature.getGeometry(), {
    featureProjection: "EPSG:3857",
    dataProjection: "EPSG:4326",
    decimals: 8,
  });
}

function fitToDraftGeometry() {
  if (!mapRef.value || draftSource.getFeatures().length === 0) return;
  mapRef.value.getView().fit(draftSource.getExtent(), {
    padding: [50, 50, 50, 50],
    duration: 250,
    maxZoom: 18,
  });
}

function applySplitGeometry(geometry, source) {
  draftSource.clear();
  if (!geometry) {
    splitGeometry.value = null;
    geometrySource.value = "";
    uploadedFilename.value = "";
    return;
  }
  const feature = geoJsonFormat.readFeature(
    { type: "Feature", geometry, properties: {} },
    {
      dataProjection: "EPSG:4326",
      featureProjection: "EPSG:3857",
    },
  );
  draftSource.addFeature(feature);
  splitGeometry.value = geometry;
  geometrySource.value = source;
  fitToDraftGeometry();
}

function clearSplitGeometry() {
  draftSource.clear();
  splitGeometry.value = null;
  geometrySource.value = "";
  uploadedFilename.value = "";
}

async function syncMapSelection() {
  if (!visible.value || !mapReady.value) return;
  loadParcels(parcels.value || []);
  ensureDraftLayer();
  await nextTick();
  updateMapSize();
  if (form.dkbm) {
    focusParcel(form.dkbm);
  } else if (parcels.value.length) {
    fitToParcels();
  }
  if (draftSource.getFeatures().length) {
    fitToDraftGeometry();
  }
}

function extractSplitGeometries(candidate, bucket) {
  if (!candidate) return;
  if (Array.isArray(candidate)) {
    for (const item of candidate) {
      extractSplitGeometries(item, bucket);
    }
    return;
  }
  if (candidate.type === "Feature") {
    extractSplitGeometries(candidate.geometry, bucket);
    return;
  }
  if (candidate.type === "FeatureCollection") {
    for (const feature of candidate.features || []) {
      extractSplitGeometries(feature, bucket);
    }
    return;
  }
  if (candidate.type === "LineString") {
    bucket.lines.push(candidate.coordinates);
    return;
  }
  if (candidate.type === "MultiLineString") {
    for (const line of candidate.coordinates || []) {
      bucket.lines.push(line);
    }
    return;
  }
  if (candidate.type === "Polygon") {
    bucket.polygons.push(candidate.coordinates);
    return;
  }
  if (candidate.type === "MultiPolygon") {
    for (const polygon of candidate.coordinates || []) {
      bucket.polygons.push(polygon);
    }
  }
}

function normalizeUploadedSplitGeometry(parsed) {
  const bucket = { lines: [], polygons: [] };
  extractSplitGeometries(parsed, bucket);
  if (bucket.lines.length && bucket.polygons.length) {
    throw new Error("上传文件不能同时包含线和面，请拆分后重新上传。");
  }
  if (bucket.lines.length === 1) {
    return { type: "LineString", coordinates: bucket.lines[0] };
  }
  if (bucket.lines.length > 1) {
    return { type: "MultiLineString", coordinates: bucket.lines };
  }
  if (bucket.polygons.length === 1) {
    return { type: "Polygon", coordinates: bucket.polygons[0] };
  }
  if (bucket.polygons.length > 1) {
    return { type: "MultiPolygon", coordinates: bucket.polygons };
  }
  throw new Error("上传文件中未识别到可用于切割的线或面。");
}

async function handleShpUpload(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file || !selectedParcelHasGeometry.value) return;
  try {
    const buffer = await file.arrayBuffer();
    const parsed = await shp(buffer);
    const geometry = normalizeUploadedSplitGeometry(parsed);
    uploadedFilename.value = file.name;
    stopDraw();
    applySplitGeometry(geometry, "upload");
    ElMessage.success("切割图形已载入");
  } catch (error) {
    uploadedFilename.value = "";
    clearSplitGeometry();
    ElMessage.error(error?.message || "SHP 解析失败");
  }
}

function startDrawMode(mode) {
  if (!selectedParcelHasGeometry.value || !mapRef.value) {
    ElMessage.warning("当前地块没有可切割图形");
    return;
  }
  stopDraw();
  clearSplitGeometry();
  drawMode.value = mode;
  drawInteraction = new Draw({
    source: draftSource,
    type: mode === "polygon" ? "Polygon" : "LineString",
  });
  drawInteraction.on("drawstart", () => {
    draftSource.clear();
    splitGeometry.value = null;
    geometrySource.value = "";
    uploadedFilename.value = "";
  });
  drawInteraction.on("drawend", (event) => {
    const geometry = writeGeometryObject(event.feature);
    if (!geometry) {
      ElMessage.warning("切割图形无效，请重新绘制");
      return;
    }
    applySplitGeometry(geometry, mode === "polygon" ? "draw-polygon" : "draw-line");
    stopDraw();
  });
  mapRef.value.addInteraction(drawInteraction);
}

function handleBasemapChange(key) {
  switchBasemap(key);
}

async function handleGenerateCode() {
  if (!batchId.value || !contractorUid.value) {
    ElMessage.warning("当前承包方信息不完整，无法生成地块编码");
    return;
  }
  generatingCode.value = true;
  try {
    const { data } = await generateNextSurveyParcelCode(batchId.value, contractorUid.value);
    const payload = data.data || {};
    form.newDkbm = ensureLocalUniqueParcelCode(payload.prefix, payload.sequence, payload.dkbm);
    ElMessage.success("已生成新地块编码");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "生成地块编码失败");
  } finally {
    generatingCode.value = false;
  }
}

function open(bid, cuid, parcelList, presetDkbm = "") {
  batchId.value = bid;
  contractorUid.value = cuid;
  parcels.value = Array.isArray(parcelList) ? parcelList : [];
  Object.assign(form, defaultForm(), {
    dkbm: presetDkbm || parcelList?.[0]?.dkbm || "",
  });
  activeMode.value = "geometry";
  clearSplitGeometry();
  visible.value = true;
}

async function handleDialogOpened() {
  await nextTick();
  if (!mapReady.value) {
    await initMap();
  }
  ensureDraftLayer();
  await syncMapSelection();
}

function resetState() {
  stopDraw();
  clearSplitGeometry();
  Object.assign(form, defaultForm());
  activeMode.value = "geometry";
  uploadedFilename.value = "";
}

function handleDialogClosed() {
  resetState();
  removeDraftLayer();
  destroyMap();
}

async function handleSubmit() {
  if (!canSubmit.value) {
    ElMessage.warning(
      activeMode.value === "geometry"
        ? "请先选择地块并提供切割图形"
        : "请填写切出面积、切割方向，并确保面积小于原地块面积",
    );
    return;
  }

  submitting.value = true;
  try {
    const payload = {
      dkbm: form.dkbm,
      newDkbm: form.newDkbm.trim(),
      newDkmc: form.newDkmc.trim(),
      reason: form.reason?.trim() || undefined,
    };
    if (activeMode.value === "geometry") {
      payload.splitMode = "geometry";
      payload.splitGeometry = splitGeometry.value;
      payload.geometrySourceSrid = 4326;
    } else {
      payload.splitMode = "area";
      payload.newScmj = Number(form.newScmj);
      payload.splitDirection = form.splitDirection;
    }
    emit("done", { type: "split_parcel", payload });
    ElMessage.success("切割地块已加入待保存");
    visible.value = false;
  } catch (error) {
    ElMessage.error(error?.message || "切割地块失败");
  } finally {
    submitting.value = false;
  }
}

watch(
  () => activeMode.value,
  (value) => {
    if (value !== "geometry") {
      stopDraw();
    }
  },
);

watch(
  () => form.dkbm,
  async (value, oldValue) => {
    if (!value || value === oldValue) return;
    clearSplitGeometry();
    form.newScmj = 0;
    if (visible.value && mapReady.value) {
      await syncMapSelection();
    }
  },
);

watch(
  () => parcels.value,
  async () => {
    if (visible.value && mapReady.value) {
      await syncMapSelection();
    }
  },
  { deep: true },
);

onBeforeUnmount(() => {
  stopDraw();
  removeDraftLayer();
  destroyMap();
});

defineExpose({ open });
</script>

<style scoped>
.dialog-alert,
.geometry-alert {
  margin-bottom: 16px;
}

.base-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 16px;
}

.base-field {
  margin-bottom: 0;
}

.source-summary {
  margin-bottom: 16px;
}

.graphic-layout {
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(0, 1.7fr) minmax(320px, 0.9fr);
  min-height: 520px;
}

.graphic-map-card {
  background: linear-gradient(180deg, #f8fbff, #ffffff);
  border: 1px solid #dbeafe;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
}

.graphic-toolbar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.upload-button {
  align-items: center;
  background: #dbeafe;
  border: 1px solid #93c5fd;
  border-radius: 8px;
  color: #1d4ed8;
  cursor: pointer;
  display: inline-flex;
  font-size: 13px;
  font-weight: 600;
  min-height: 32px;
  padding: 0 14px;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.upload-button:hover {
  background: #bfdbfe;
  border-color: #60a5fa;
}

.upload-button.disabled {
  background: #f3f4f6;
  border-color: #d1d5db;
  color: #9ca3af;
  cursor: not-allowed;
}

.upload-input {
  display: none;
}

.basemap-select {
  margin-left: auto;
  width: 140px;
}

.split-map {
  border: 1px solid #dbeafe;
  border-radius: 12px;
  height: 420px;
  overflow: hidden;
  width: 100%;
}

.graphic-status {
  color: #475569;
  display: flex;
  flex-wrap: wrap;
  font-size: 12px;
  gap: 8px 14px;
}

.graphic-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.graphic-help {
  background: #fffdf7;
  border: 1px solid #fde68a;
  border-radius: 12px;
  color: #854d0e;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
}

.help-title {
  color: #713f12;
  font-size: 13px;
  font-weight: 700;
}

.help-line {
  font-size: 13px;
  line-height: 1.6;
}

.reason-field {
  margin-bottom: 0;
}

.area-form {
  padding-top: 8px;
}

.area-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
}

.area-hint {
  color: #64748b;
  font-size: 12px;
  margin-top: 6px;
}

.direction-field {
  margin-bottom: 0;
}

.direction-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  width: 100%;
}

.direction-grid :deep(.el-radio-button__inner) {
  border-radius: 10px;
  height: auto;
  line-height: 1.5;
  padding: 12px 10px;
  white-space: normal;
  width: 100%;
}

@media (max-width: 1180px) {
  .base-grid,
  .graphic-layout,
  .area-grid {
    grid-template-columns: 1fr;
  }

  .split-map {
    height: 360px;
  }

  .basemap-select {
    margin-left: 0;
  }
}
</style>
