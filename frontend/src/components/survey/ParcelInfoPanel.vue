<template>
  <div
    v-loading.lock="isValidatingAddGeometry"
    class="parcel-info-panel"
    element-loading-text="正在核验新增地块图形，请稍候..."
    element-loading-background="rgba(255, 255, 255, 0.72)"
  >
    

    <div class="parcel-toolbar">
      <div class="parcel-toolbar-main">
        <el-button
          type="warning"
          plain
          size="small"
          :disabled="actionDisabled"
          @click="emit('swap-parcels')"
        >
          地块互换
        </el-button>
        <el-button
          type="success"
          plain
          size="small"
          :disabled="actionDisabled"
          @click="beginAddParcelMode"
        >
          新增地块
        </el-button>
        <el-button
          plain
          size="small"
          :disabled="actionDisabled || parcels.length === 0"
          @click="handleSplitParcel"
        >
          切割地块
        </el-button>
        <el-button
          type="danger"
          plain
          size="small"
          :disabled="actionDisabled || parcels.length === 0"
          @click="emit('remove-parcel')"
        >
          移除地块
        </el-button>
        <span v-if="isResultLocked" class="toolbar-lock-hint">（只读）</span>
      </div>

      <div v-if="addModeActive" class="parcel-toolbar-add-mode">
        <label class="upload-button">
          <input
            class="upload-input"
            type="file"
            accept=".zip,application/zip"
            @change="handleShpUpload"
          />
          <span>上传 SHP</span>
        </label>
        <el-button size="small" @click="cancelAddParcelMode">取消新增</el-button>
        <span class="add-mode-hint">
          请直接在左侧地图上绘制新增地块，或上传 `shp(zip)` 图形。
        </span>
      </div>

      <div v-if="splitModeActive" class="parcel-toolbar-split-mode">
        <span class="mode-chip">切割地块：{{ splitSourceParcel?.dkbm || "-" }}</span>
        <el-button
          size="small"
          :type="splitForm.splitMethod === 'geometry' ? 'primary' : 'default'"
          @click="switchSplitMethod('geometry')"
        >
          按图形切割
        </el-button>
        <template v-if="splitForm.splitMethod === 'geometry'">
          <label class="upload-button" :class="{ disabled: !splitSourceHasGeometry }">
            <input
              class="upload-input"
              type="file"
              accept=".zip,application/zip"
              :disabled="!splitSourceHasGeometry"
              @change="handleSplitShpUpload"
            />
            <span>上传 SHP</span>
          </label>
          <el-button
            size="small"
            :disabled="!splitSourceHasGeometry"
            :type="splitDrawMode === 'line' ? 'primary' : 'default'"
            @click="startSplitDrawMode('line')"
          >
            绘图切割线
          </el-button>
          <el-button
            size="small"
            :disabled="!splitSourceHasGeometry"
            :type="splitDrawMode === 'polygon' ? 'primary' : 'default'"
            @click="startSplitDrawMode('polygon')"
          >
            绘图切割面
          </el-button>
          <el-button size="small" :disabled="!splitGeometry" @click="clearSplitDraft">
            清除图形
          </el-button>
        </template>
        <el-button
          size="small"
          :type="splitForm.splitMethod === 'area' ? 'primary' : 'default'"
          @click="switchSplitMethod('area')"
        >
          按面积切割
        </el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="!splitCanSubmit"
          :loading="submittingSplitParcel"
          @click="submitSplitParcel"
        >
          加入待保存
        </el-button>
        <el-button size="small" @click="cancelSplitParcelMode">取消切割</el-button>
        <span class="add-mode-hint">
          先在右侧列表选择待切割地块，再通过上传、绘图或面积方向方式完成切割。
        </span>
      </div>
    </div>

    <el-alert
      v-if="addModeActive"
      :title="addModeAlertText"
      :type="addModeAlertType"
      :closable="false"
      show-icon
      class="add-mode-alert"
    />
    <el-alert
      v-if="splitModeActive"
      :title="splitModeAlertText"
      :type="splitModeAlertType"
      :closable="false"
      show-icon
      class="add-mode-alert"
    />

    

    <div class="parcel-layout">
      <div class="parcel-map-container" :class="{ 'is-add-mode': addModeActive, 'is-split-mode': splitModeActive }">
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

        <div v-if="addModeActive" class="map-add-overlay">
          <div class="map-add-badge">新增地块模式</div>
          <div class="map-add-meta">
            <span>图形面积：{{ addGeometryAreaText }}</span>
            <span>核验状态：{{ addGeometryValidationText }}</span>
            <span v-if="uploadedFilename">文件：{{ uploadedFilename }}</span>
          </div>
        </div>
        <div v-if="splitModeActive" class="map-add-overlay">
          <div class="map-add-badge split-badge">切割地块模式</div>
          <div class="map-add-meta">
            <span>切割方式：{{ splitForm.splitMethod === "geometry" ? "按图形切割" : "按面积切割" }}</span>
            <span>源地块：{{ splitSourceParcel?.dkbm || "-" }}</span>
            <span v-if="splitForm.splitMethod === 'geometry'">
              图形状态：{{ splitGeometry ? "已就绪" : "待提供" }}
            </span>
            <span v-if="splitUploadedFilename">文件：{{ splitUploadedFilename }}</span>
            <span v-if="splitForm.splitMethod === 'area'">预计剩余：{{ splitRemainingArea }} 亩</span>
          </div>
        </div>
      </div>

      <div class="parcel-list">
        <el-table
          :data="parcels"
          border
          size="small"
          highlight-current-row
          v-loading="parcelsLoading"
          :row-class-name="parcelRowClassName"
          @row-click="selectParcel"
          :max-height="parcelTableMaxHeight"
        >
          <el-table-column label="状态" width="92">
            <template #default="{ row }">
              <el-tooltip
                v-if="parcelChangeTip(row)"
                effect="light"
                placement="top-start"
                :content="parcelChangeTip(row)"
              >
                <el-tag :type="parcelStatusType(row)" size="small">{{ parcelStatusLabel(row) }}</el-tag>
              </el-tooltip>
              <el-tag v-else :type="parcelStatusType(row)" size="small">{{ parcelStatusLabel(row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="dkbm" label="地块编码" width="140" />
          <el-table-column prop="dkmc" label="地块名称" min-width="120" />
          <el-table-column label="面积(亩)" width="100">
            <template #default="{ row }">
              <span :class="parcelChangedClass(row)">{{ row.scmj ?? "-" }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类别" width="80">
            <template #default="{ row }">{{ dklbMap[row.dklb] || row.dklb || "-" }}</template>
          </el-table-column>
          <el-table-column label="是否基本农田" width="100">
            <template #default="{ row }">{{ row.sfjbnt === "1" ? "是" : "否" }}</template>
          </el-table-column>
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="parcelActionLabel(row)"
                link
                type="danger"
                size="small"
                :disabled="parcelActionDisabled(row)"
                :loading="rollbackChangeLoadingId === parcelRollbackChangeId(row)"
                @click.stop="handleParcelAction(row)"
              >
                {{ parcelActionLabel(row) }}
              </el-button>
              <span v-else class="parcel-row-action-placeholder">-</span>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="selectedParcel" class="parcel-detail" :class="{ 'is-removed': isHistoricalParcel(selectedParcel) }">
          <el-descriptions :column="2" border size="small" :title="selectedParcel.dkmc">
            <el-descriptions-item label="地块编码">{{ selectedParcel.dkbm }}</el-descriptions-item>
            <el-descriptions-item label="实测面积">{{ selectedParcel.scmj }} 亩</el-descriptions-item>
            <el-descriptions-item label="合同面积">{{ selectedParcel.htmj }} 亩</el-descriptions-item>
            <el-descriptions-item label="土地利用类型">{{ tdlylxMap[selectedParcel.tdlylx] || selectedParcel.tdlylx || "-" }}</el-descriptions-item>
            <el-descriptions-item label="东至">{{ selectedParcel.dkdz || "-" }}</el-descriptions-item>
            <el-descriptions-item label="西至">{{ selectedParcel.dkxz || "-" }}</el-descriptions-item>
            <el-descriptions-item label="南至">{{ selectedParcel.dknz || "-" }}</el-descriptions-item>
            <el-descriptions-item label="北至">{{ selectedParcel.dkbz || "-" }}</el-descriptions-item>
            <el-descriptions-item label="承包方">{{ selectedParcel.cbfmc || "-" }}</el-descriptions-item>
            <el-descriptions-item label="合同编码">{{ selectedParcel.cbhtbm || "-" }}</el-descriptions-item>
            <el-descriptions-item v-if="selectedParcel.changeReason" label="变更原因" :span="2">
              {{ selectedParcel.changeReason }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <div v-if="splitModeActive" class="split-config-card">
          <div class="split-config-title">切割设置</div>
          <el-form label-position="top" size="small">
            <div class="split-config-grid">
              <el-form-item label="新地块编码" required>
                <el-input v-model="splitForm.newDkbm" maxlength="19" placeholder="请输入新地块编码">
                  <template #append>
                    <el-button :loading="generatingSplitCode" @click="handleGenerateSplitCode">自动生成</el-button>
                  </template>
                </el-input>
              </el-form-item>
              <el-form-item label="新地块名称" required>
                <el-input v-model="splitForm.newDkmc" maxlength="50" placeholder="例如：切割地块A" />
              </el-form-item>
            </div>

            <div v-if="splitForm.splitMethod === 'area'" class="split-config-grid">
              <el-form-item label="切出面积（亩）" required>
                <el-input-number
                  v-model="splitForm.newScmj"
                  :min="0.01"
                  :max="splitMaxArea"
                  :precision="2"
                  style="width: 100%"
                />
              </el-form-item>
              <el-form-item label="切割方向" required>
                <el-select v-model="splitForm.splitDirection" style="width: 100%">
                  <el-option label="从东侧切割" value="east" />
                  <el-option label="从西侧切割" value="west" />
                  <el-option label="从南侧切割" value="south" />
                  <el-option label="从北侧切割" value="north" />
                </el-select>
              </el-form-item>
            </div>

            <el-form-item label="切割原因">
              <el-input
                v-model="splitForm.reason"
                type="textarea"
                :rows="3"
                maxlength="500"
                show-word-limit
                placeholder="请输入切割原因"
              />
            </el-form-item>
          </el-form>
        </div>

        <div v-if="addModeActive && addValidation.checked && addValidation.overlaps.length" class="overlap-list">
          <div class="overlap-list-title">重叠地块</div>
          <div
            v-for="(item, index) in addValidation.overlaps"
            :key="`${item.source}-${item.dkbm || item.cbfmc || index}`"
            class="overlap-item"
          >
            <div class="overlap-item-main">
              <span class="overlap-code">{{ item.dkbm || "-" }}</span>
              <span class="overlap-name">{{ item.dkmc || "未命名地块" }}</span>
            </div>
            <div class="overlap-item-sub">
              <span>{{ item.cbfmc || item.cbfbm || "未知承包方" }}</span>
              <span>重叠约 {{ formatArea(item.overlapAreaMu) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <AddParcelDialog
      ref="addParcelDialog"
      :batch-id="batchId"
      :contractor-uid="contractorUid"
      :existing-parcel-codes="parcels.map((item) => item?.dkbm).filter(Boolean)"
      @done="handleAddParcelDone"
      @closed="handleAddParcelDialogClosed"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import shp from "shpjs";
import Draw from "ol/interaction/Draw";
import GeoJSON from "ol/format/GeoJSON";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import { Fill, Stroke, Style } from "ol/style";

import AddParcelDialog from "./AddParcelDialog.vue";
import { useDialogMap } from "../../composables/useDialogMap";
import { generateNextSurveyParcelCode, previewSplitSurveyParcel, validateSurveyParcelGeometry } from "../../api/survey";

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  parcels: { type: Array, default: () => [] },
  parcelsLoading: { type: Boolean, default: false },
  canManage: { type: Boolean, default: false },
  isResultLocked: { type: Boolean, default: false },
  savedSwapRecords: { type: Array, default: () => [] },
  savedSplitRecords: { type: Array, default: () => [] },
  canRollbackSavedParcelChange: { type: Boolean, default: false },
  rollbackChangeLoadingId: { type: [Number, String], default: null },
});

const emit = defineEmits(["swap-parcels", "add-parcel", "split-parcel", "remove-parcel", "rollback-saved-swap", "rollback-saved-split"]);

const addParcelDialog = ref(null);
const mapRoot = ref(null);
const selectedParcel = ref(null);
const addModeActive = ref(false);
const splitModeActive = ref(false);
const uploadedFilename = ref("");
const splitUploadedFilename = ref("");
const addValidationError = ref("");
const addGeometry = ref(null);
const splitGeometry = ref(null);
const addDialogSubmitted = ref(false);
const isValidatingAddGeometry = ref(false);
const splitDrawMode = ref("");
const generatingSplitCode = ref(false);
const submittingSplitParcel = ref(false);

function defaultSplitForm() {
  return {
    dkbm: "",
    newDkbm: "",
    newDkmc: "",
    newScmj: 0,
    splitDirection: "east",
    splitMethod: "geometry",
    reason: "",
  };
}

const splitForm = reactive(defaultSplitForm());

const addValidation = reactive({
  checked: false,
  valid: false,
  areaMu: null,
  overlaps: [],
});

const dklbMap = { "01": "耕地", "02": "园地", "03": "林地", "04": "草地", "05": "养殖水面", "09": "其他" };
const tdlylxMap = {
  "011": "水田", "012": "水浇地", "013": "旱地",
  "021": "果园", "022": "茶园", "023": "其他园地",
  "031": "有林地", "032": "灌木林地", "033": "其他林地",
  "041": "天然牧草地", "042": "人工牧草地",
  "111": "设施农用地", "114": "坑塘水面",
};

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
  clearSelection,
  updateMapSize,
  destroyMap,
} = useDialogMap(mapRoot);

const toolModeActive = computed(() => addModeActive.value || splitModeActive.value);
const actionDisabled = computed(() => !props.canManage || props.isResultLocked || toolModeActive.value);
const parcelTableMaxHeight = computed(() => (
  splitModeActive.value ? "220px" : "calc(92vh - 380px)"
));
const splitSourceParcel = computed(() =>
  props.parcels.find((item) => item?.dkbm === splitForm.dkbm && isCurrentParcel(item)) || null
);
const splitSourceHasGeometry = computed(() => Boolean(splitSourceParcel.value?.geometry));
const splitRemainingArea = computed(() => {
  if (!splitSourceParcel.value) return 0;
  const area = Number(splitSourceParcel.value.scmj || 0);
  return Math.max(0, +(area - Number(splitForm.newScmj || 0)).toFixed(2));
});
const splitMaxArea = computed(() => {
  if (!splitSourceParcel.value) return 0;
  const area = Number(splitSourceParcel.value.scmj || 0);
  return Math.max(0, +(area - 0.01).toFixed(2));
});
const splitCanSubmit = computed(() => {
  if (!splitModeActive.value) return false;
  if (!splitForm.dkbm || !splitForm.newDkbm.trim() || !splitForm.newDkmc.trim()) {
    return false;
  }
  if (splitForm.splitMethod === "geometry") {
    return splitSourceHasGeometry.value && Boolean(splitGeometry.value);
  }
  return (
    splitSourceHasGeometry.value &&
    Number(splitForm.newScmj) > 0 &&
    Number(splitForm.newScmj) < Number(splitSourceParcel.value?.scmj || 0) &&
    Boolean(splitForm.splitDirection)
  );
});
const splitModeAlertType = computed(() => {
  if (!splitSourceParcel.value) return "warning";
  if (!splitSourceHasGeometry.value) return "warning";
  if (splitForm.splitMethod === "geometry") {
    return splitGeometry.value ? "success" : "info";
  }
  return splitCanSubmit.value ? "success" : "info";
});
const splitModeAlertText = computed(() => {
  if (!splitSourceParcel.value) {
    return "请先在右侧列表中选择待切割地块。";
  }
  if (!splitSourceHasGeometry.value) {
    return "当前地块没有图形数据，无法进行切割。";
  }
  if (splitForm.splitMethod === "geometry") {
    if (!splitGeometry.value) {
      return "请上传 SHP，或在左侧地图中绘制切割线/切割面。";
    }
    return "切割图形已准备好，可以加入待保存。";
  }
  return `请填写切出面积和方向，当前预计剩余 ${splitRemainingArea.value} 亩。`;
});

const addModeAlertType = computed(() => {
  if (addValidationError.value) return "error";
  if (isValidatingAddGeometry.value) return "warning";
  if (!addGeometry.value) return "info";
  if (!addValidation.checked) return "warning";
  return addValidation.valid ? "success" : "warning";
});

const addModeAlertText = computed(() => {
  if (addValidationError.value) return addValidationError.value;
  if (isValidatingAddGeometry.value) return "正在核验新增地块图形，请稍候。";
  if (!addGeometry.value) return "请在左侧地图上直接绘制新增地块，或上传 shp(zip) 图形。";
  if (!addValidation.checked) return "已获取图形，正在等待核验结果。";
  if (addValidation.valid) return "图形核验通过，正在打开属性表单。";
  return "图形与其他地块存在重叠，请重新绘制或重新上传。";
});

const addGeometryAreaText = computed(() => formatArea(addValidation.areaMu));
const addGeometryValidationText = computed(() => {
  if (!addGeometry.value) return "未录入";
  if (isValidatingAddGeometry.value) return "核验中";
  if (!addValidation.checked) return "待核验";
  return addValidation.valid ? "已通过" : `发现 ${addValidation.overlaps.length} 处重叠`;
});

const geoJsonFormat = new GeoJSON();
const draftSource = new VectorSource();
const draftLayer = new VectorLayer({
  source: draftSource,
  style: new Style({
    fill: new Fill({ color: "rgba(37, 99, 235, 0.18)" }),
    stroke: new Stroke({ color: "#2563eb", width: 2.4 }),
  }),
  zIndex: 1000,
});
let drawInteraction = null;
let draftLayerMounted = false;

function logAddParcel(message, extra) {
  if (extra === undefined) {
    console.info(`[ParcelInfoPanel:add] ${message}`);
    return;
  }
  console.info(`[ParcelInfoPanel:add] ${message}`, extra);
}

function formatArea(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(2)} 亩`;
}

function buildExistingParcelCodeSet() {
  return new Set(
    props.parcels
      .map((item) => String(item?.dkbm || "").trim())
      .filter(Boolean),
  );
}

function ensureLocalUniqueParcelCode(prefix, sequence, candidate) {
  const existingCodes = buildExistingParcelCodeSet();
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

function resetAddValidation() {
  addValidation.checked = false;
  addValidation.valid = false;
  addValidation.areaMu = null;
  addValidation.overlaps = [];
  addValidationError.value = "";
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

function stopDraw() {
  if (drawInteraction && mapRef.value) {
    mapRef.value.removeInteraction(drawInteraction);
  }
  drawInteraction = null;
  splitDrawMode.value = "";
}

function clearDraftGeometry() {
  draftSource.clear();
  addGeometry.value = null;
  uploadedFilename.value = "";
  resetAddValidation();
}

function fitToDraftGeometry() {
  if (!mapRef.value || draftSource.getFeatures().length === 0) return;
  mapRef.value.getView().fit(draftSource.getExtent(), {
    padding: [50, 50, 50, 50],
    duration: 250,
    maxZoom: 18,
  });
}

function writeDraftGeometry(feature) {
  if (!feature) return null;
  return geoJsonFormat.writeGeometryObject(feature.getGeometry(), {
    featureProjection: "EPSG:3857",
    dataProjection: "EPSG:4326",
    decimals: 8,
  });
}

function writeCurrentDraftGeometry() {
  return writeDraftGeometry(draftSource.getFeatures()[0]);
}

function parcelChangedClass(row) {
  return row.isChanged ? "field-changed" : "";
}

function isRemovedParcel(parcel) {
  return parcel?.resultStatus === "removed";
}

function isHistoricalParcel(parcel) {
  return ["removed", "split_source"].includes(parcel?.resultStatus);
}

function isCurrentParcel(parcel) {
  return !isHistoricalParcel(parcel);
}

function isSwappedOutParcel(parcel) {
  return isRemovedParcel(parcel) && parcel?.changeType === "swap_parcels";
}

function isSwappedInParcel(parcel) {
  return !isRemovedParcel(parcel) && parcel?.changeType === "swap_parcels";
}

function isSplitSourceParcel(parcel) {
  return parcel?.resultStatus === "split_source";
}

function isSplitGeneratedParcel(parcel) {
  return isCurrentParcel(parcel) && parcel?.resultStatus === "split_generated";
}

function isAddedParcel(parcel) {
  return (
    isCurrentParcel(parcel) &&
    (
      parcel?.resultStatus === "added" ||
      parcel?.changeType === "add_parcel"
    )
  );
}

function parcelStatusLabel(parcel) {
  if (isSplitSourceParcel(parcel)) return "被切割";
  if (isSplitGeneratedParcel(parcel)) return "切割生成";
  if (isSwappedOutParcel(parcel)) return "已换出";
  if (isSwappedInParcel(parcel)) return "已换入";
  if (isAddedParcel(parcel)) return "新增";
  if (parcel?.isChanged || isRemovedParcel(parcel)) return "变更";
  return "正常";
}

function parcelStatusType(parcel) {
  if (isSplitSourceParcel(parcel)) return "warning";
  if (isSplitGeneratedParcel(parcel)) return "success";
  if (isSwappedOutParcel(parcel)) return "info";
  if (isSwappedInParcel(parcel)) return "warning";
  if (isAddedParcel(parcel)) return "success";
  if (parcel?.isChanged || isRemovedParcel(parcel)) return "warning";
  return "success";
}

function parcelRowClassName({ row }) {
  return isHistoricalParcel(row) ? "parcel-row-removed" : "";
}

function findSavedSwapRecord(parcel) {
  return (props.savedSwapRecords || []).find((item) => (item.swappedIn || []).includes(parcel?.dkbm)) || null;
}

function findSavedSplitRecord(parcel) {
  return (props.savedSplitRecords || []).find((item) => item.originalDkbm === parcel?.dkbm) || null;
}

function parcelRollbackChangeId(parcel) {
  return findSavedSplitRecord(parcel)?.id || findSavedSwapRecord(parcel)?.id || null;
}

function parcelActionLabel(parcel) {
  if (findSavedSplitRecord(parcel)) return "撤回切割";
  if (findSavedSwapRecord(parcel)) return "撤回互换";
  return "";
}

function parcelActionDisabled(parcel) {
  return !props.canRollbackSavedParcelChange || toolModeActive.value || !parcelActionLabel(parcel);
}

function handleParcelAction(parcel) {
  const splitRecord = findSavedSplitRecord(parcel);
  if (splitRecord) {
    emit("rollback-saved-split", splitRecord);
    return;
  }
  const swapRecord = findSavedSwapRecord(parcel);
  if (swapRecord) {
    emit("rollback-saved-swap", swapRecord);
  }
}

function parcelChangeTip(parcel) {
  if (!parcel?.isChanged && !isSplitSourceParcel(parcel) && !isSplitGeneratedParcel(parcel) && !isSwappedInParcel(parcel) && !isSwappedOutParcel(parcel)) {
    return "";
  }
  const messages = [];
  if (isSplitSourceParcel(parcel)) {
    const splitRecord = findSavedSplitRecord(parcel);
    messages.push(splitRecord ? `该地块已被切割为 ${splitRecord.generatedDkbms.length} 块，当前为历史地块` : "该地块已被切割，当前为历史地块");
  } else if (isSplitGeneratedParcel(parcel)) {
    messages.push("该地块由切割生成，当前为现势地块");
  } else if (isSwappedInParcel(parcel)) {
    const swapRecord = findSavedSwapRecord(parcel);
    messages.push(swapRecord ? `该地块为互换换入，对方承包方：${swapRecord.counterpartyLabel || "-"}` : "该地块为互换换入");
  } else if (isSwappedOutParcel(parcel)) {
    messages.push("该地块已互换换出");
  } else if (isRemovedParcel(parcel)) {
    messages.push("该地块已移除");
  } else if (isAddedParcel(parcel)) {
    messages.push("该地块为新增地块");
  } else {
    messages.push("该地块信息已发生变化");
  }
  if (parcel.changeReason) {
    messages.push(`原因：${parcel.changeReason}`);
  }
  return messages.join("；");
}

function selectParcel(parcel) {
  selectedParcel.value = parcel;
  focusParcel(parcel.dkbm);
  if (splitModeActive.value && isCurrentParcel(parcel)) {
    if (splitForm.dkbm !== parcel.dkbm) {
      splitForm.dkbm = parcel.dkbm;
      splitForm.newScmj = 0;
      clearSplitDraft();
    }
  }
}

function handleSplitParcel() {
  const parcel =
    (isCurrentParcel(selectedParcel.value) ? selectedParcel.value : null) ||
    props.parcels.find((item) => isCurrentParcel(item)) ||
    null;
  if (!parcel) {
    ElMessage.warning("请先在右侧列表中选择需要切割的地块");
    return;
  }
  if (!selectedParcel.value) {
    selectedParcel.value = parcel;
    focusParcel(parcel.dkbm);
  }
  beginSplitParcelMode(parcel);
}

function handleBasemapChange(key) {
  switchBasemap(key);
}

async function startDrawMode() {
  if (!addModeActive.value || !mapRef.value) return;
  logAddParcel("startDrawMode", {
    addModeActive: addModeActive.value,
    hasMap: Boolean(mapRef.value),
  });
  stopDraw();
  drawInteraction = new Draw({
    source: draftSource,
    type: "Polygon",
  });
  drawInteraction.on("drawstart", () => {
    logAddParcel("drawstart");
    draftSource.clear();
    addGeometry.value = null;
    resetAddValidation();
    uploadedFilename.value = "";
  });
  drawInteraction.on("drawend", async (event) => {
    logAddParcel("drawend");
    addGeometry.value = writeDraftGeometry(event.feature) || writeCurrentDraftGeometry();
    logAddParcel("draw geometry prepared", {
      geometryType: addGeometry.value?.type || null,
      hasGeometry: Boolean(addGeometry.value),
    });
    fitToDraftGeometry();
    await validateAddGeometry();
  });
  mapRef.value.addInteraction(drawInteraction);
}

async function beginAddParcelMode() {
  logAddParcel("beginAddParcelMode", {
    batchId: props.batchId,
    contractorUid: props.contractorUid,
    parcelCount: props.parcels.length,
  });
  addModeActive.value = true;
  clearSelection();
  selectedParcel.value = null;
  clearDraftGeometry();
  await nextTick();
  if (!mapReady.value) {
    await initMap();
  }
  ensureDraftLayer();
  mapRef.value?.updateSize();
  await startDrawMode();
  ElMessage.info("请直接在地图上绘制新增地块，或上传 SHP 图形");
}

function finishAddParcelMode() {
  addModeActive.value = false;
  stopDraw();
  clearDraftGeometry();
}

function cancelAddParcelMode() {
  addDialogSubmitted.value = false;
  finishAddParcelMode();
}

async function beginSplitParcelMode(parcel) {
  if (!parcel) return;
  splitModeActive.value = true;
  splitForm.dkbm = parcel.dkbm;
  splitForm.newScmj = 0;
  splitForm.splitMethod = "geometry";
  splitForm.reason = "";
  splitForm.newDkbm = "";
  splitForm.newDkmc = "";
  clearSplitDraft();
  await nextTick();
  if (!mapReady.value) {
    await initMap();
  }
  ensureDraftLayer();
  mapRef.value?.updateSize();
  focusParcel(parcel.dkbm);
  ElMessage.info("请在工具栏下方选择上传 SHP、绘图切割，或切换到按面积切割。");
}

function finishSplitParcelMode() {
  splitModeActive.value = false;
  stopDraw();
  clearSplitDraft();
  Object.assign(splitForm, defaultSplitForm());
}

function cancelSplitParcelMode() {
  finishSplitParcelMode();
}

function switchSplitMethod(method) {
  splitForm.splitMethod = method;
  splitForm.newScmj = 0;
  if (method !== "geometry") {
    stopDraw();
    clearSplitDraft();
  }
}

function clearSplitDraft() {
  draftSource.clear();
  splitGeometry.value = null;
  splitUploadedFilename.value = "";
}

async function handleGenerateSplitCode() {
  if (!props.batchId || !props.contractorUid) {
    ElMessage.warning("当前承包方信息不完整，无法生成地块编码");
    return;
  }
  generatingSplitCode.value = true;
  try {
    const { data } = await generateNextSurveyParcelCode(props.batchId, props.contractorUid);
    const payload = data.data || {};
    splitForm.newDkbm = ensureLocalUniqueParcelCode(payload.prefix, payload.sequence, payload.dkbm);
    ElMessage.success("已生成新地块编码");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "生成地块编码失败");
  } finally {
    generatingSplitCode.value = false;
  }
}

function collectSplitGeometries(geometry, bucket) {
  if (!geometry || typeof geometry !== "object") return;
  if (geometry.type === "Feature") {
    collectSplitGeometries(geometry.geometry, bucket);
    return;
  }
  if (geometry.type === "FeatureCollection") {
    for (const feature of geometry.features || []) {
      collectSplitGeometries(feature, bucket);
    }
    return;
  }
  if (Array.isArray(geometry)) {
    for (const item of geometry) {
      collectSplitGeometries(item, bucket);
    }
    return;
  }
  if (geometry.type === "LineString") {
    bucket.lines.push(geometry.coordinates);
    return;
  }
  if (geometry.type === "MultiLineString") {
    for (const line of geometry.coordinates || []) {
      bucket.lines.push(line);
    }
    return;
  }
  if (geometry.type === "Polygon") {
    bucket.polygons.push(geometry.coordinates);
    return;
  }
  if (geometry.type === "MultiPolygon") {
    for (const polygon of geometry.coordinates || []) {
      bucket.polygons.push(polygon);
    }
  }
}

function normalizeUploadedSplitGeometry(parsed) {
  const bucket = { lines: [], polygons: [] };
  collectSplitGeometries(parsed, bucket);
  if (bucket.lines.length && bucket.polygons.length) {
    throw new Error("上传文件不能同时包含切割线和切割面");
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
  throw new Error("上传文件中未识别到可用于切割的线或面");
}

function applySplitGeometryToMap(geometry) {
  draftSource.clear();
  const feature = geoJsonFormat.readFeature(
    { type: "Feature", geometry, properties: {} },
    {
      dataProjection: "EPSG:4326",
      featureProjection: "EPSG:3857",
    },
  );
  draftSource.addFeature(feature);
  splitGeometry.value = geometry;
  fitToDraftGeometry();
}

async function handleSplitShpUpload(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file || !splitModeActive.value || !splitSourceHasGeometry.value) return;
  try {
    const buffer = await file.arrayBuffer();
    const parsed = await shp(buffer);
    const geometry = normalizeUploadedSplitGeometry(parsed);
    splitUploadedFilename.value = file.name;
    stopDraw();
    applySplitGeometryToMap(geometry);
    ElMessage.success("切割图形已载入");
  } catch (error) {
    splitUploadedFilename.value = "";
    clearSplitDraft();
    ElMessage.error(error?.message || "SHP 解析失败");
  }
}

function startSplitDrawMode(mode) {
  if (!splitModeActive.value || !mapRef.value || !splitSourceHasGeometry.value) {
    ElMessage.warning("请先选择带图形的地块");
    return;
  }
  splitForm.splitMethod = "geometry";
  stopDraw();
  clearSplitDraft();
  splitDrawMode.value = mode;
  drawInteraction = new Draw({
    source: draftSource,
    type: mode === "polygon" ? "Polygon" : "LineString",
  });
  drawInteraction.on("drawstart", () => {
    draftSource.clear();
    splitGeometry.value = null;
    splitUploadedFilename.value = "";
  });
  drawInteraction.on("drawend", (event) => {
    const geometry = writeDraftGeometry(event.feature) || writeCurrentDraftGeometry();
    if (!geometry) {
      ElMessage.warning("切割图形无效，请重新绘制");
      return;
    }
    splitGeometry.value = geometry;
    splitUploadedFilename.value = "";
    fitToDraftGeometry();
    stopDraw();
  });
  mapRef.value.addInteraction(drawInteraction);
}

async function submitSplitParcel() {
  if (!splitCanSubmit.value) {
    ElMessage.warning("请先补全切割信息");
    return;
  }
  const payload = {
    dkbm: splitForm.dkbm,
    newDkbm: splitForm.newDkbm.trim(),
    newDkmc: splitForm.newDkmc.trim(),
    reason: splitForm.reason?.trim() || undefined,
  };
  if (splitForm.splitMethod === "geometry") {
    payload.splitMode = "geometry";
    payload.splitGeometry = splitGeometry.value;
    payload.geometrySourceSrid = 4326;
  } else {
    payload.splitMode = "area";
    payload.newScmj = Number(splitForm.newScmj);
    payload.splitDirection = splitForm.splitDirection;
  }
  submittingSplitParcel.value = true;
  try {
    const { data } = await previewSplitSurveyParcel(props.batchId, props.contractorUid, payload);
    const generatedParcels = Array.isArray(data.data?.generatedParcels) ? data.data.generatedParcels : [];
    if (generatedParcels.length < 2) {
      ElMessage.error("切割结果至少应生成 2 个现势地块");
      return;
    }
    payload.generatedParcels = generatedParcels.map((item) => ({
      dkbm: item.dkbm,
      dkmc: item.dkmc,
      scmj: item.scmj,
      htmj: item.htmj,
      geometry: item.geometry,
    }));
    emit("split-parcel", { type: "split_parcel", payload });
    finishSplitParcelMode();
    ElMessage.success(`切割地块已加入待保存，将生成 ${generatedParcels.length} 个现势地块`);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "切割地块失败");
  } finally {
    submittingSplitParcel.value = false;
  }
}

function collectPolygonCoordinates(geometry, target) {
  if (!geometry || typeof geometry !== "object") return;
  if (geometry.type === "Feature") {
    collectPolygonCoordinates(geometry.geometry, target);
    return;
  }
  if (geometry.type === "FeatureCollection") {
    for (const feature of geometry.features || []) {
      collectPolygonCoordinates(feature, target);
    }
    return;
  }
  if (Array.isArray(geometry)) {
    for (const item of geometry) {
      collectPolygonCoordinates(item, target);
    }
    return;
  }
  if (geometry.type === "Polygon") {
    target.push(geometry.coordinates);
    return;
  }
  if (geometry.type === "MultiPolygon") {
    for (const polygon of geometry.coordinates || []) {
      target.push(polygon);
    }
  }
}

function normalizeUploadedGeometry(parsed) {
  const polygons = [];
  collectPolygonCoordinates(parsed, polygons);
  if (!polygons.length) {
    throw new Error("上传文件中未识别到面要素");
  }
  if (polygons.length === 1) {
    return { type: "Polygon", coordinates: polygons[0] };
  }
  return { type: "MultiPolygon", coordinates: polygons };
}

function applyUploadedGeometryToMap(geometry) {
  draftSource.clear();
  const feature = geoJsonFormat.readFeature(
    { type: "Feature", geometry, properties: {} },
    {
      dataProjection: "EPSG:4326",
      featureProjection: "EPSG:3857",
    },
  );
  draftSource.addFeature(feature);
  addGeometry.value = geometry;
  fitToDraftGeometry();
}

async function handleShpUpload(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file || !addModeActive.value) return;
  uploadedFilename.value = file.name;
  logAddParcel("handleShpUpload", {
    filename: file.name,
    size: file.size,
  });
  try {
    const buffer = await file.arrayBuffer();
    const parsed = await shp(buffer);
    const geometry = normalizeUploadedGeometry(parsed);
    applyUploadedGeometryToMap(geometry);
    logAddParcel("shp geometry prepared", {
      geometryType: geometry?.type || null,
    });
    await validateAddGeometry();
  } catch (error) {
    logAddParcel("handleShpUpload error", {
      message: error?.message || String(error),
    });
    uploadedFilename.value = "";
    addValidationError.value = error.message || "SHP 解析失败，请确认上传的是标准 shp 压缩包";
    draftSource.clear();
    addGeometry.value = null;
    resetAddValidation();
    ElMessage.error(addValidationError.value);
  }
}

async function validateAddGeometry() {
  if (!addModeActive.value || !addGeometry.value || !props.batchId || !props.contractorUid) {
    logAddParcel("validateAddGeometry skipped", {
      addModeActive: addModeActive.value,
      hasGeometry: Boolean(addGeometry.value),
      batchId: props.batchId,
      contractorUid: props.contractorUid,
    });
    return;
  }
  isValidatingAddGeometry.value = true;
  resetAddValidation();
  stopDraw();
  try {
    const payload = {
      geometry: addGeometry.value,
      geometrySourceSrid: 4326,
      localParcels: props.parcels
        .filter((item) => item?.geometry && isCurrentParcel(item))
        .map((item) => ({
          dkbm: item.dkbm,
          dkmc: item.dkmc,
          cbfbm: item.cbfbm,
          cbfmc: item.cbfmc,
          resultStatus: item.resultStatus,
          geometry: item.geometry,
        })),
    };
    logAddParcel("validateAddGeometry request", {
      batchId: props.batchId,
      contractorUid: props.contractorUid,
      geometryType: payload.geometry?.type || null,
      localParcelCount: payload.localParcels.length,
    });
    const { data } = await validateSurveyParcelGeometry(props.batchId, props.contractorUid, payload);
    const result = data.data || {};
    logAddParcel("validateAddGeometry response", result);
    addValidation.checked = true;
    addValidation.valid = Boolean(result.valid);
    addValidation.areaMu = result.areaMu ?? null;
    addValidation.overlaps = Array.isArray(result.overlaps) ? result.overlaps : [];
    if (result.valid) {
      stopDraw();
      addDialogSubmitted.value = false;
      addParcelDialog.value?.open({
        geometry: addGeometry.value,
        geometrySourceSrid: 4326,
        scmj: result.areaMu ?? null,
        htmj: result.areaMu ?? null,
      });
    } else {
      ElMessage.warning("新增地块图形与其他地块存在重叠，请重新绘制或重新上传");
      logAddParcel("validateAddGeometry invalid", {
        overlapCount: addValidation.overlaps.length,
      });
      clearDraftGeometry();
      await startDrawMode();
    }
  } catch (error) {
    logAddParcel("validateAddGeometry error", {
      message: error?.response?.data?.detail || error?.message || String(error),
    });
    addValidation.checked = true;
    addValidation.valid = false;
    addValidation.areaMu = null;
    addValidation.overlaps = [];
    addValidationError.value = error.response?.data?.detail || error.message || "图形核验失败";
    clearDraftGeometry();
    ElMessage.error(addValidationError.value);
    await startDrawMode();
  } finally {
    isValidatingAddGeometry.value = false;
  }
}

function handleAddParcelDone(operation) {
  addDialogSubmitted.value = true;
  emit("add-parcel", operation);
  finishAddParcelMode();
}

function handleAddParcelDialogClosed({ submitted }) {
  if (submitted || addDialogSubmitted.value) {
    addDialogSubmitted.value = false;
    return;
  }
  cancelAddParcelMode();
}

watch(
  () => props.parcels,
  async (list) => {
    if (!mapReady.value) {
      await initMap();
      ensureDraftLayer();
    }
    loadParcels(list || []);
    if (list?.length) {
      fitToParcels();
    }
    if (toolModeActive.value && draftSource.getFeatures().length) {
      fitToDraftGeometry();
    }
  },
  { immediate: false, deep: true },
);

onMounted(async () => {
  if (!mapReady.value) {
    await initMap();
  }
  ensureDraftLayer();
  setTimeout(() => {
    if (mapRoot.value) updateMapSize();
  }, 200);
});

onBeforeUnmount(() => {
  stopDraw();
  removeDraftLayer();
  destroyMap();
});
</script>

<style scoped>
.parcel-info-panel { min-height: 400px; }

.parcel-toolbar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}

.parcel-toolbar-main {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.parcel-toolbar-add-mode {
  align-items: center;
  background: linear-gradient(90deg, #eff6ff, #f8fafc);
  border: 1px dashed #93c5fd;
  border-radius: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 12px;
}

.parcel-toolbar-split-mode {
  align-items: center;
  background: linear-gradient(90deg, #fff7ed, #fffaf3);
  border: 1px dashed #fdba74;
  border-radius: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 12px;
}

.mode-chip {
  align-items: center;
  background: #ffedd5;
  border: 1px solid #fdba74;
  border-radius: 999px;
  color: #9a3412;
  display: inline-flex;
  font-size: 12px;
  font-weight: 700;
  min-height: 28px;
  padding: 0 10px;
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
  transition: background 0.2s ease, border-color 0.2s ease;
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

.add-mode-hint {
  color: #475569;
  font-size: 12px;
}

.add-mode-alert {
  margin-bottom: 12px;
}

.toolbar-lock-hint { color: #909399; font-size: 12px; }

.parcel-layout { display: flex; gap: 12px; height: calc(92vh - 380px); min-height: 450px; }
.parcel-map-container { flex: 1; position: relative; min-width: 0; border: 1px solid #ebeef5; border-radius: 4px; overflow: hidden; }
.parcel-map-container.is-add-mode { border-color: #60a5fa; box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.35); }
.parcel-map-container.is-split-mode { border-color: #fb923c; box-shadow: inset 0 0 0 1px rgba(251, 146, 60, 0.35); }
.parcel-map { width: 100%; height: 100%; }
.basemap-switch { position: absolute; top: 8px; right: 8px; z-index: 10; width: 140px; }

.map-add-overlay {
  align-items: flex-start;
  bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  left: 10px;
  position: absolute;
  z-index: 10;
}

.map-add-badge {
  background: rgba(29, 78, 216, 0.94);
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  padding: 6px 10px;
}

.split-badge {
  background: rgba(194, 65, 12, 0.92);
}

.map-add-meta {
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(191, 219, 254, 0.95);
  border-radius: 10px;
  color: #334155;
  display: flex;
  flex-direction: column;
  font-size: 12px;
  gap: 4px;
  max-width: 260px;
  padding: 10px 12px;
}

.parcel-list {
  width: 420px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding-right: 2px;
}
.parcel-detail { flex-shrink: 0; max-height: 36vh; overflow-y: auto; border-radius: 4px; }
.parcel-detail.is-removed { background: #f4f4f5; border: 1px solid #dcdfe6; padding: 8px; }
.field-changed { background-color: #fdf6ec; padding: 2px 6px; border-radius: 3px; }
.parcel-row-action-placeholder { color: #c0c4cc; }

.split-config-card {
  background: linear-gradient(180deg, #fffaf3, #ffffff);
  border: 1px solid #fed7aa;
  border-radius: 10px;
  flex-shrink: 0;
  order: -1;
  padding: 12px;
  position: sticky;
  top: 0;
  z-index: 1;
}

.split-config-title {
  color: #9a3412;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 10px;
}

.split-config-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.overlap-list {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
}

.overlap-list-title { color: #9a3412; font-size: 13px; font-weight: 700; }
.overlap-item { border-top: 1px dashed #fdba74; padding-top: 8px; }
.overlap-item:first-of-type { border-top: none; padding-top: 0; }
.overlap-item-main, .overlap-item-sub { display: flex; gap: 10px; justify-content: space-between; }
.overlap-item-main { align-items: center; }
.overlap-code { color: #9a3412; font-size: 12px; font-weight: 700; }
.overlap-name { color: #7c2d12; flex: 1; font-size: 13px; text-align: right; }
.overlap-item-sub { color: #9a3412; font-size: 12px; margin-top: 6px; }

.parcel-list :deep(.el-table__row.parcel-row-removed > .el-table__cell) {
  background-color: #f4f4f5;
  color: #606266;
}

.parcel-list :deep(.el-table__row.parcel-row-removed.current-row > .el-table__cell),
.parcel-list :deep(.el-table__row.parcel-row-removed:hover > .el-table__cell) {
  background-color: #e9e9eb;
}

.parcel-detail.is-removed :deep(.el-descriptions__body),
.parcel-detail.is-removed :deep(.el-descriptions__label),
.parcel-detail.is-removed :deep(.el-descriptions__content) {
  background-color: #f4f4f5;
}

@media (max-width: 1180px) {
  .parcel-layout {
    flex-direction: column;
    height: auto;
  }

  .parcel-map-container {
    min-height: 420px;
  }

  .parcel-list {
    width: 100%;
  }

  .split-config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
