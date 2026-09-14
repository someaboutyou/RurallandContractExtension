<template>
  <el-dialog
    v-model="visible"
    title="发布影像到底图"
    width="900px"
    :close-on-click-modal="false"
    :close-on-press-escape="!publishing"
    @close="handleClose"
  >
    <!-- 步骤条 -->
    <el-steps :active="currentStep" finish-status="success" align-center style="margin-bottom: 24px">
      <el-step title="填写TIFF路径" />
      <el-step title="选择裁剪范围" />
      <el-step title="确认发布" />
      <el-step title="发布进度" />
    </el-steps>

    <!-- Step 0: 填写TIFF路径 -->
    <div v-show="currentStep === 0">
      <el-form label-width="120px">
        <el-form-item label="TIFF文件路径" required>
          <el-input
            v-model="form.tifPath"
            placeholder="请输入服务器上tif文件的完整路径，如 E:\data\image.tif"
            clearable
          >
            <template #append>
              <el-button :loading="validating" @click="handleValidateTif">验证</el-button>
            </template>
          </el-input>
        </el-form-item>
      </el-form>

      <!-- TIF元数据展示 -->
      <el-descriptions
        v-if="tifInfo"
        title="TIFF文件信息"
        :column="2"
        border
        style="margin-top: 16px"
      >
        <el-descriptions-item label="文件名">{{ tifInfo.filename }}</el-descriptions-item>
        <el-descriptions-item label="大小">{{ tifInfo.size_mb }} MB</el-descriptions-item>
        <el-descriptions-item label="尺寸">{{ tifInfo.width }} × {{ tifInfo.height }} px</el-descriptions-item>
        <el-descriptions-item label="波段数">{{ tifInfo.bands }}</el-descriptions-item>
        <el-descriptions-item label="数据类型">{{ tifInfo.dtype }}</el-descriptions-item>
        <el-descriptions-item label="坐标系">{{ tifInfo.crs }}</el-descriptions-item>
        <el-descriptions-item label="像素分辨率">
          X: {{ tifInfo.pixel_size.x }}m / Y: {{ tifInfo.pixel_size.y }}m
        </el-descriptions-item>
        <el-descriptions-item label="建议切片级别">
          {{ tifInfo.suggested_zoom.min }} ~ {{ tifInfo.suggested_zoom.max }}
        </el-descriptions-item>
        <el-descriptions-item label="空间范围" :span="2">
          [{{ tifInfo.bounds.left.toFixed(6) }}, {{ tifInfo.bounds.bottom.toFixed(6) }}] ~
          [{{ tifInfo.bounds.right.toFixed(6) }}, {{ tifInfo.bounds.top.toFixed(6) }}]
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- Step 1: 选择裁剪范围 -->
    <div v-show="currentStep === 1">
      <el-alert type="info" :closable="false" style="margin-bottom: 16px">
        选择裁剪范围（可选）。如果不裁剪，将发布整个TIFF文件。
      </el-alert>

      <el-radio-group v-model="clipMode" style="margin-bottom: 16px">
        <el-radio value="none">不裁剪</el-radio>
        <el-radio value="shp">上传SHP</el-radio>
        <el-radio value="draw">手绘范围</el-radio>
      </el-radio-group>

      <!-- 上传SHP -->
      <div v-if="clipMode === 'shp'">
        <el-upload
          ref="shpUploadRef"
          drag
          :auto-upload="false"
          :limit="1"
          accept=".zip"
          :on-change="handleShpFileChange"
          :on-remove="handleShpFileRemove"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">将Shapefile压缩包拖到此处，或<em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">请上传包含 .shp/.dbf/.shx/.prj 的 .zip 压缩包</div>
          </template>
        </el-upload>
        <el-button
          v-if="shpFile"
          type="primary"
          :loading="parsingShp"
          style="margin-top: 12px"
          @click="handleParseShp"
        >
          解析SHP范围
        </el-button>
        <el-descriptions v-if="shpGeojson" title="SHP范围信息" :column="2" border style="margin-top: 16px">
          <el-descriptions-item label="要素数量">{{ shpGeojson.feature_count }}</el-descriptions-item>
          <el-descriptions-item label="坐标系">{{ shpGeojson.crs }}</el-descriptions-item>
          <el-descriptions-item label="范围" :span="2">
            [{{ shpGeojson.bounds.left.toFixed(6) }}, {{ shpGeojson.bounds.bottom.toFixed(6) }}] ~
            [{{ shpGeojson.bounds.right.toFixed(6) }}, {{ shpGeojson.bounds.top.toFixed(6) }}]
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 手绘范围 -->
      <div v-if="clipMode === 'draw'">
        <el-alert type="warning" :closable="false" style="margin-bottom: 8px">
          请在地图上绘制多边形作为裁剪范围。双击结束绘制。
        </el-alert>
        <div class="draw-map-toolbar">
          <el-button size="small" :type="drawActive ? 'danger' : 'primary'" @click="toggleDraw">
            {{ drawActive ? '停止绘制' : '开始绘制' }}
          </el-button>
          <el-button size="small" @click="clearDraw">清除绘制</el-button>
        </div>
        <div ref="drawMapRef" class="draw-map-container"></div>
      </div>
    </div>

    <!-- Step 2: 确认发布 -->
    <div v-show="currentStep === 2">
      <el-descriptions title="发布配置确认" :column="1" border>
        <el-descriptions-item label="TIFF路径">{{ form.tifPath }}</el-descriptions-item>
        <el-descriptions-item label="裁剪方式">
          {{ clipMode === 'none' ? '不裁剪（发布整个文件）' : clipMode === 'shp' ? 'SHP范围裁剪' : '手绘范围裁剪' }}
        </el-descriptions-item>
        <el-descriptions-item label="存储名称">
          <el-input v-model="form.storeName" placeholder="自动生成" style="width: 300px" />
        </el-descriptions-item>
        <el-descriptions-item v-if="tifInfo" label="文件大小">{{ tifInfo.size_mb }} MB</el-descriptions-item>
        <el-descriptions-item v-if="tifInfo" label="建议切片级别">
          {{ tifInfo.suggested_zoom.min }} ~ {{ tifInfo.suggested_zoom.max }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- Step 3: 发布进度 -->
    <div v-show="currentStep === 3">
      <div style="text-align: center; padding: 20px 0">
        <el-progress
          :percentage="progress"
          :status="progressStatus"
          :stroke-width="20"
          striped
          striped-flow
          style="margin-bottom: 20px"
        />
        <p style="color: #606266; font-size: 14px">{{ progressMessage }}</p>
      </div>

      <!-- 发布成功后的结果 -->
      <el-result
        v-if="publishResult && publishResult.success"
        icon="success"
        title="影像发布成功"
        sub-title="底图已成功发布到GeoServer，可以在底图管理中配置使用"
      >
        <template #extra>
          <el-descriptions :column="1" border style="text-align: left">
            <el-descriptions-item label="图层名称">{{ publishResult.layer_name }}</el-descriptions-item>
            <el-descriptions-item label="切片级别">
              {{ publishResult.zoom_range.min }} ~ {{ publishResult.zoom_range.max }}
            </el-descriptions-item>
          </el-descriptions>
          <div style="margin-top: 20px">
            <el-checkbox v-model="autoCreateLayer">自动添加到底图管理</el-checkbox>
          </div>
        </template>
      </el-result>

      <!-- 发布失败 -->
      <el-result
        v-if="publishFailed"
        icon="error"
        title="发布失败"
        :sub-title="progressMessage"
      />
    </div>

    <template #footer>
      <el-button @click="handleClose" :disabled="publishing">取消</el-button>
      <el-button v-if="currentStep > 0 && currentStep < 3" @click="prevStep">上一步</el-button>
      <el-button
        v-if="currentStep < 2"
        type="primary"
        :disabled="!canNext"
        @click="nextStep"
      >
        下一步
      </el-button>
      <el-button
        v-if="currentStep === 2"
        type="primary"
        :loading="publishing"
        @click="handlePublish"
      >
        开始发布
      </el-button>
      <el-button
        v-if="currentStep === 3 && publishResult && publishResult.success"
        type="primary"
        @click="handleFinish"
      >
        完成
      </el-button>
      <el-button
        v-if="currentStep === 3 && publishFailed"
        type="warning"
        @click="currentStep = 0"
      >
        重新开始
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { UploadFilled } from "@element-plus/icons-vue";
import "ol/ol.css";
import OlMap from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import { OSM, Vector as VectorSource, XYZ, TileWMS } from "ol/source";
import { Draw } from "ol/interaction";
import GeoJSON from "ol/format/GeoJSON";
import Feature from "ol/Feature";
import { Polygon } from "ol/geom";
import { Fill, Stroke, Style } from "ol/style";
import { validateTif, uploadShp, publishRaster, getPublishProgress } from "../../api/rasterPublish";
import { createMapLayer } from "../../api/mapLayer";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue", "published"]);

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

// State
const currentStep = ref(0);
const form = ref({ tifPath: "", storeName: "" });
const validating = ref(false);
const tifInfo = ref(null);
const clipMode = ref("none");
const shpFile = ref(null);
const parsingShp = ref(false);
const shpGeojson = ref(null);
const publishing = ref(false);
const progress = ref(0);
const progressMessage = ref("");
const publishResult = ref(null);
const publishFailed = ref(false);
const autoCreateLayer = ref(true);
const taskId = ref(null);
let pollTimer = null;

// Draw map
const drawMapRef = ref(null);
let drawMap = null;
let drawInteraction = null;
let drawVectorSource = null;
let drawVectorLayer = null;
const drawActive = ref(false);
let tifBoundsSource = null;
let tifBoundsLayer = null;
const drawnGeojson = ref(null);

// Computed
const canNext = computed(() => {
  if (currentStep.value === 0) return !!tifInfo.value;
  if (currentStep.value === 1) {
    if (clipMode.value === "none") return true;
    if (clipMode.value === "shp") return !!shpGeojson.value;
    if (clipMode.value === "draw") return !!drawnGeojson.value;
  }
  return false;
});

const progressStatus = computed(() => {
  if (progress.value < 0) return "exception";
  if (progress.value >= 100) return "success";
  return "";
});

// Watch clip mode to init draw map
watch(clipMode, async (mode) => {
  if (mode === "draw") {
    await nextTick();
    initDrawMap();
  }
});

function prevStep() {
  if (currentStep.value > 0) currentStep.value--;
}

function nextStep() {
  if (currentStep.value < 3) currentStep.value++;
}

async function handleValidateTif() {
  if (!form.value.tifPath.trim()) {
    ElMessage.warning("请输入TIFF文件路径");
    return;
  }
  validating.value = true;
  tifInfo.value = null;
  try {
    const { data } = await validateTif(form.value.tifPath.trim());
    tifInfo.value = data.data;
    // 如果地图已初始化，显示 tif 范围并缩放
    const bounds = tifInfo.value.bounds_wgs84 || tifInfo.value.bounds;
    if (tifBoundsSource && drawMap) {
      showTifBounds(bounds);
      drawMap.getView().fit([
        bounds.left,
        bounds.bottom,
        bounds.right,
        bounds.top
      ], { padding: [50, 50, 50, 50], maxZoom: 16 });
    }
    ElMessage.success("TIFF文件验证通过");
  } catch (err) {
    const msg = err?.response?.data?.detail || "验证失败";
    ElMessage.error(msg);
  } finally {
    validating.value = false;
  }
}

function handleShpFileChange(file) {
  shpFile.value = file.raw;
}

function handleShpFileRemove() {
  shpFile.value = null;
  shpGeojson.value = null;
}

async function handleParseShp() {
  if (!shpFile.value) return;
  parsingShp.value = true;
  shpGeojson.value = null;
  try {
    const { data } = await uploadShp(shpFile.value);
    shpGeojson.value = data.data;
    ElMessage.success("SHP解析成功");
  } catch (err) {
    const msg = err?.response?.data?.detail || "SHP解析失败";
    ElMessage.error(msg);
  } finally {
    parsingShp.value = false;
  }
}

function initDrawMap() {
  if (drawMap) return;
  if (!drawMapRef.value) return;

  drawVectorSource = new VectorSource();
  drawVectorLayer = new VectorLayer({
    source: drawVectorSource,
    style: new Style({
      stroke: new Stroke({ color: "#409EFF", width: 2 }),
      fill: new Fill({ color: "rgba(64, 158, 255, 0.2)" }),
    }),
  });

  // 天地图遥感底图
  const tiandituLayer = new TileLayer({
    source: new XYZ({
      url: "https://t6.tianditu.gov.cn/DataServer?T=img_w&x={x}&y={y}&l={z}&tk=d9d9f17f6979a9b6cc681e5b1589f750",
      crossOrigin: "anonymous",
    }),
  });

  // 天地图注记层
  const tiandituLabelLayer = new TileLayer({
    source: new XYZ({
      url: "https://t6.tianditu.gov.cn/DataServer?T=cia_w&x={x}&y={y}&l={z}&tk=d9d9f17f6979a9b6cc681e5b1589f750",
      crossOrigin: "anonymous",
    }),
  });

  // 矢量图层 - 承包地块（与项目配置一致）
  const surveyDkLayer = new TileLayer({
    source: new TileWMS({
      url: "/geoserver/erlunyanbao/wms",
      params: {
        LAYERS: "erlunyanbao:survey_dk_result",
        FORMAT: "image/png",
        TRANSPARENT: true,
        STYLES: "dk",
      },
      crossOrigin: "anonymous",
    }),
  });

  // 矢量图层 - 行政区
  const xzqLayer = new TileLayer({
    source: new TileWMS({
      url: "/geoserver/erlunyanbao/wms",
      params: {
        LAYERS: "erlunyanbao:xzq",
        FORMAT: "image/png",
        TRANSPARENT: true,
        STYLES: "xzq",
      },
      crossOrigin: "anonymous",
    }),
  });

  // 矢量图层 - 行政区界线
  const xzqjxLayer = new TileLayer({
    source: new TileWMS({
      url: "/geoserver/erlunyanbao/wms",
      params: {
        LAYERS: "erlunyanbao:xzqjx",
        FORMAT: "image/png",
        TRANSPARENT: true,
        STYLES: "xzqjx",
      },
      crossOrigin: "anonymous",
    }),
  });

  drawMap = new OlMap({
    target: drawMapRef.value,
    layers: [
      tiandituLayer,
      tiandituLabelLayer,
      xzqLayer,
      xzqjxLayer,
      surveyDkLayer,
      drawVectorLayer,
    ],
    view: new View({
      center: [116.4, 39.9],
      zoom: 10,
      projection: "EPSG:4326",
    }),
  });

  // 创建 tif 范围显示图层（在最上层）
  tifBoundsSource = new VectorSource();
  tifBoundsLayer = new VectorLayer({
    source: tifBoundsSource,
    style: new Style({
      stroke: new Stroke({ color: "#E6A23C", width: 3, lineDash: [10, 5] }),
      fill: new Fill({ color: "rgba(230, 162, 60, 0.15)" }),
    }),
    zIndex: 999, // 确保在最上层
  });
  drawMap.addLayer(tifBoundsLayer);

  // 如果已有 tif 信息，显示其范围
  if (tifInfo.value) {
    const tifBounds = tifInfo.value.bounds_wgs84 || tifInfo.value.bounds;
    showTifBounds(tifBounds);
    drawMap.getView().fit([
      tifBounds.left,
      tifBounds.bottom,
      tifBounds.right,
      tifBounds.top
    ], { padding: [50, 50, 50, 50], maxZoom: 16 });
  } else {
    // 尝试获取承包地块的bounds并缩放
    fetchLayerBounds().then((bounds) => {
      if (bounds && drawMap) {
        drawMap.getView().fit(bounds, { padding: [50, 50, 50, 50] });
      }
    });
  }
}

function showTifBounds(bounds) {
  if (!tifBoundsSource) return;
  tifBoundsSource.clear();
  const feature = new Feature({
    geometry: new Polygon([[
      [bounds.left, bounds.bottom],
      [bounds.right, bounds.bottom],
      [bounds.right, bounds.top],
      [bounds.left, bounds.top],
      [bounds.left, bounds.bottom],
    ]]),
    name: "tif_bounds",
  });
  tifBoundsSource.addFeature(feature);
}

async function fetchLayerBounds() {
  try {
    // 使用 GeoServer REST API 获取图层 bounds
    const resp = await fetch("/geoserver/rest/workspaces/erlunyanbao/datastores/postgis/featuretypes/survey_dk_result.json");
    if (!resp.ok) return null;
    const data = await resp.json();
    const ft = data?.featureType;
    if (!ft) return null;
    
    // 优先使用 latLonBoundingBox (EPSG:4326)
    const bbox = ft.latLonBoundingBox || ft.nativeBoundingBox;
    if (bbox) {
      return [
        parseFloat(bbox.minx),
        parseFloat(bbox.miny),
        parseFloat(bbox.maxx),
        parseFloat(bbox.maxy),
      ];
    }
  } catch (e) {
    console.warn("Failed to fetch layer bounds via REST API:", e);
  }
  return null;
}

function toggleDraw() {
  if (drawActive.value) {
    removeDrawInteraction();
  } else {
    addDrawInteraction();
  }
}

function addDrawInteraction() {
  if (!drawMap) return;
  drawInteraction = new Draw({
    source: drawVectorSource,
    type: "Polygon",
  });
  drawInteraction.on("drawend", (event) => {
    const feature = event.feature;
    const geojsonFmt = new GeoJSON();
    const geom = geojsonFmt.writeGeometryObject(feature.getGeometry());
    drawnGeojson.value = geom;
    ElMessage.success("多边形绘制完成");
    // Remove interaction after draw
    removeDrawInteraction();
  });
  drawMap.addInteraction(drawInteraction);
  drawActive.value = true;
}

function removeDrawInteraction() {
  if (drawMap && drawInteraction) {
    drawMap.removeInteraction(drawInteraction);
    drawInteraction = null;
  }
  drawActive.value = false;
}

function clearDraw() {
  if (drawVectorSource) drawVectorSource.clear();
  drawnGeojson.value = null;
  removeDrawInteraction();
}

async function handlePublish() {
  publishing.value = true;
  progress.value = 0;
  progressMessage.value = "正在启动发布任务...";
  publishResult.value = null;
  publishFailed.value = false;
  currentStep.value = 3;

  // Build clip geojson
  let clipGeojson = null;
  if (clipMode.value === "shp" && shpGeojson.value) {
    clipGeojson = shpGeojson.value.geojson;
  } else if (clipMode.value === "draw" && drawnGeojson.value) {
    clipGeojson = drawnGeojson.value;
  }

  try {
    const { data } = await publishRaster({
      tif_path: form.value.tifPath.trim(),
      clip_geojson: clipGeojson,
      store_name: form.value.storeName.trim() || undefined,
    });
    taskId.value = data.data.task_id;
    pollProgress();
  } catch (err) {
    const msg = err?.response?.data?.detail || "发布请求失败";
    progressMessage.value = msg;
    progress.value = -1;
    publishFailed.value = true;
    publishing.value = false;
  }
}

function pollProgress() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getPublishProgress(taskId.value);
      const task = data.data;
      progress.value = task.progress >= 0 ? task.progress : 0;
      progressMessage.value = task.message;

      if (task.status === "completed") {
        clearInterval(pollTimer);
        pollTimer = null;
        publishing.value = false;
        publishResult.value = task.result;
        progress.value = 100;
      } else if (task.status === "failed") {
        clearInterval(pollTimer);
        pollTimer = null;
        publishing.value = false;
        publishFailed.value = true;
        progress.value = Math.abs(task.progress);
      }
    } catch {
      // ignore polling errors
    }
  }, 1500);
}

async function handleFinish() {
  // Auto create map layer record
  if (autoCreateLayer.value && publishResult.value) {
    try {
      // 询问用户是否设为默认底图
      const isDefault = await ElMessageBox.confirm(
        "是否将此影像设为默认底图？设为默认后，打开一张图时会自动缩放到此影像范围。",
        "设为默认底图",
        {
          confirmButtonText: "设为默认",
          cancelButtonText: "不设为默认",
          type: "info",
        }
      ).then(() => true).catch(() => false);

      await createMapLayer({
        name: publishResult.value.store_name,
        key: publishResult.value.store_name,
        groupName: "影像底图",
        category: "basemap",
        enabled: true,
        defaultVisible: true,
        isDefault: isDefault,
        sortOrder: isDefault ? 0 : 99,
        serviceConfigs: [
          {
            serviceType: "WMTS",
            serviceUrl: publishResult.value.wmts_url,
            projection: "EPSG:4326",
            minZoom: publishResult.value.zoom_range.min,
            maxZoom: publishResult.value.zoom_range.max,
            enabled: true,
          },
        ],
      });
      
      if (isDefault) {
        ElMessage.success("已设为默认底图，打开一张图时会自动缩放到此影像范围");
      } else {
        ElMessage.success("已添加到底图管理");
      }
      emit("published");
    } catch {
      ElMessage.warning("自动添加底图失败，请手动在底图管理中添加");
    }
  }
  handleClose();
}

function handleClose() {
  if (publishing.value) {
    ElMessage.warning("发布进行中，请等待完成");
    return;
  }
  // Cleanup
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (drawMap) {
    drawMap.setTarget(null);
    drawMap = null;
    drawInteraction = null;
    drawVectorSource = null;
    drawVectorLayer = null;
  }
  // Reset state
  currentStep.value = 0;
  form.value = { tifPath: "", storeName: "" };
  tifInfo.value = null;
  clipMode.value = "none";
  shpFile.value = null;
  shpGeojson.value = null;
  drawnGeojson.value = null;
  progress.value = 0;
  progressMessage.value = "";
  publishResult.value = null;
  publishFailed.value = false;
  taskId.value = null;
  drawActive.value = false;
  visible.value = false;
}

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  if (drawMap) drawMap.setTarget(null);
});
</script>

<style scoped>
.draw-map-container {
  width: 100%;
  height: 360px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  margin-top: 8px;
}
.draw-map-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
}
</style>






