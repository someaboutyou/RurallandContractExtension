import { computed, nextTick, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import shp from "shpjs";
import Draw from "ol/interaction/Draw";
import { validateSurveyParcelGeometry } from "../../api/survey";
import { isCurrentParcel } from "../../utils/parcelStatusHelpers";

/**
 * Composable for add-parcel geometry mode logic (draw, upload, validate).
 * Extracted from ParcelInfoPanel.vue to reduce component size.
 *
 * @param {Object} ctx - shared dependencies from the host component
 * @param {import("vue").Ref} ctx.parcels - current parcel list
 * @param {Object} ctx.draftMap - useParcelDraftMap instance
 * @param {Function} ctx.emit - component emit function
 * @param {Object} ctx.props - component props
 * @param {import("vue").Ref} ctx.addParcelDialog - ref to AddParcelDialog
 * @param {import("vue").Ref} ctx.selectedParcel - currently selected parcel
 * @param {import("vue").Ref} ctx.splitModeActive - whether split mode is active
 */
export function useAddParcelGeometry(ctx) {
  const { parcels, draftMap, emit, props, addParcelDialog, selectedParcel } = ctx;
  const {
    mapRef, mapReady, initMap, clearSelection,
    draftSource, geoJsonFormat,
    stopDraw, ensureDraftLayer,
    writeDraftGeometry, writeCurrentDraftGeometry, fitToDraftGeometry,
  } = draftMap;

  // --- State ---
  const addModeActive = ref(false);
  const uploadedFilename = ref("");
  const addValidationError = ref("");
  const addGeometry = ref(null);
  const addDialogSubmitted = ref(false);
  const isValidatingAddGeometry = ref(false);

  const addValidation = reactive({
    checked: false,
    valid: false,
    areaMu: null,
    overlaps: [],
  });

  // --- Computed ---
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

  const addGeometryAreaText = computed(() => {
    const value = addValidation.areaMu;
    if (value == null || Number.isNaN(Number(value))) return "-";
    return `${Number(value).toFixed(2)} 亩`;
  });

  const addGeometryValidationText = computed(() => {
    if (!addGeometry.value) return "未录入";
    if (isValidatingAddGeometry.value) return "核验中";
    if (!addValidation.checked) return "待核验";
    return addValidation.valid ? "已通过" : `发现 ${addValidation.overlaps.length} 处重叠`;
  });

  // --- Helpers ---
  function logAddParcel(message, extra) {
    if (extra === undefined) {
      console.info(`[ParcelInfoPanel:add] ${message}`);
      return;
    }
    console.info(`[ParcelInfoPanel:add] ${message}`, extra);
  }

  function resetAddValidation() {
    addValidation.checked = false;
    addValidation.valid = false;
    addValidation.areaMu = null;
    addValidation.overlaps = [];
    addValidationError.value = "";
  }

  function clearDraftGeometry() {
    draftSource.clear();
    addGeometry.value = null;
    uploadedFilename.value = "";
    resetAddValidation();
  }

  // --- Draw mode ---
  async function startDrawMode() {
    if (!addModeActive.value || !mapRef.value) return;
    logAddParcel("startDrawMode", {
      addModeActive: addModeActive.value,
      hasMap: Boolean(mapRef.value),
    });
    stopDraw();
    const interaction = new Draw({
      source: draftSource,
      type: "Polygon",
    });
    interaction.on("drawstart", () => {
      logAddParcel("drawstart");
      draftSource.clear();
      addGeometry.value = null;
      resetAddValidation();
      uploadedFilename.value = "";
    });
    interaction.on("drawend", async (event) => {
      logAddParcel("drawend");
      addGeometry.value = writeDraftGeometry(event.feature) || writeCurrentDraftGeometry();
      logAddParcel("draw geometry prepared", {
        geometryType: addGeometry.value?.type || null,
        hasGeometry: Boolean(addGeometry.value),
      });
      fitToDraftGeometry();
      await validateAddGeometry();
    });
    mapRef.value.addInteraction(interaction);
    draftMap.drawInteraction = interaction;
  }

  // --- Mode lifecycle ---
  async function beginAddParcelMode() {
    logAddParcel("beginAddParcelMode", {
      batchId: props.batchId,
      contractorUid: props.contractorUid,
      parcelCount: parcels.value.length,
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

  // --- SHP upload ---
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

  // --- Validation ---
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
        localParcels: parcels.value
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

  return {
    // State
    addModeActive,
    uploadedFilename,
    addValidationError,
    addGeometry,
    addDialogSubmitted,
    isValidatingAddGeometry,
    addValidation,
    // Computed
    addModeAlertType,
    addModeAlertText,
    addGeometryAreaText,
    addGeometryValidationText,
    // Methods
    beginAddParcelMode,
    finishAddParcelMode,
    cancelAddParcelMode,
    clearDraftGeometry,
    handleShpUpload,
    handleAddParcelDone,
    handleAddParcelDialogClosed,
  };
}


