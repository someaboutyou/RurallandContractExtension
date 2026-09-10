import { computed, reactive, ref, nextTick } from "vue";
import { ElMessage } from "element-plus";
import shp from "shpjs";
import Draw from "ol/interaction/Draw";
import { generateNextSurveyParcelCode, previewSplitSurveyParcel } from "../../api/survey";
import { isCurrentParcel, isSplitSourceParcel } from "../../utils/parcelStatusHelpers";

/**
 * Composable for split-parcel mode logic.
 * Extracted from ParcelInfoPanel.vue to reduce component size.
 *
 * @param {Object} ctx - shared dependencies from the host component
 * @param {import("vue").Ref} ctx.parcels - current parcel list
 * @param {import("vue").ComputedRef} ctx.toolModeActive - true when any tool mode is active
 * @param {Object} ctx.draftMap - useParcelDraftMap instance
 * @param {Function} ctx.emit - component emit function
 * @param {Object} ctx.props - component props
 */
export function useSplitParcel(ctx) {
  const { parcels, draftMap, emit, props } = ctx;
  const {
    mapRef, mapReady, initMap, focusParcel,
    draftSource, geoJsonFormat,
    stopDraw, ensureDraftLayer,
    writeDraftGeometry, writeCurrentDraftGeometry, fitToDraftGeometry,
  } = draftMap;


  /** Wraps draftMap.stopDraw to also reset splitDrawMode */
  function stopSplitDraw() {
    draftMap.stopDraw();
    splitDrawMode.value = "";
  }
  // --- State ---
  const splitModeActive = ref(false);
  const splitUploadedFilename = ref("");
  const splitGeometry = ref(null);
  const splitDrawMode = ref("");
  const generatingSplitCode = ref(false);
  const submittingSplitParcel = ref(false);

  // --- Split preview state ---
  const splitPreviewLoading = ref(false);
  const splitPreviewGenerated = ref([]);
  const splitParcelSettings = ref([]);
  const activeSplitTab = ref("0");
  const splitConfigDialogVisible = ref(false);

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

  // --- Computed ---
  const splitSourceParcel = computed(() =>
    parcels.value.find((item) => item?.dkbm === splitForm.dkbm && isCurrentParcel(item)) || null
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
    if (!splitForm.dkbm || !splitSourceHasGeometry.value) return false;
    if (splitForm.splitMethod === "geometry") {
      if (!splitGeometry.value || !splitPreviewGenerated.value.length) return false;
      return splitParcelSettings.value.every((s) => s.dkmc?.trim());
    }
    // Area mode
    if (!splitForm.newDkbm.trim() || !splitForm.newDkmc.trim()) return false;
    return (
      Number(splitForm.newScmj) > 0 &&
      Number(splitForm.newScmj) < Number(splitSourceParcel.value?.scmj || 0) &&
      Boolean(splitForm.splitDirection)
    );
  });
  const splitModeAlertType = computed(() => {
    if (!splitSourceParcel.value) return "warning";
    if (!splitSourceHasGeometry.value) return "warning";
    if (splitForm.splitMethod === "geometry") {
      if (splitPreviewLoading.value) return "info";
      if (splitPreviewGenerated.value.length) return "success";
      return splitGeometry.value ? "info" : "info";
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
      if (splitPreviewLoading.value) {
        return "正在验证切割图形，请稍候...";
      }
      if (splitPreviewGenerated.value.length) {
        return `验证通过，将生成 ${splitPreviewGenerated.value.length} 个现势地块，请填写每个地块的名称。`;
      }
      return "切割图形已准备好，正在等待验证。";
    }
    return `请填写切出面积和方向，当前预计剩余 ${splitRemainingArea.value} 亩。`;
  });

  // --- Helpers ---
  function buildExistingParcelCodeSet() {
    return new Set(
      parcels.value
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

  function clearSplitDraft() {
    draftSource.clear();
    splitGeometry.value = null;
    splitUploadedFilename.value = "";
    splitPreviewGenerated.value = [];
    splitParcelSettings.value = [];
    activeSplitTab.value = "0";
    splitConfigDialogVisible.value = false;
  }

  /**
   * Analyze split geometry to determine cutting orientation
   * Returns 'ns' if cutting North-South (divides into E/W parts)
   * Returns 'ew' if cutting East-West (divides into N/S parts)
   */
  function getSplitOrientation(geometry) {
    if (!geometry) return 'ns';
    let coords = [];
    if (geometry.type === 'LineString') {
      coords = geometry.coordinates || [];
    } else if (geometry.type === 'MultiLineString') {
      coords = (geometry.coordinates || []).flat();
    } else if (geometry.type === 'Polygon') {
      coords = (geometry.coordinates?.[0] || []).slice(0, -1);
    } else if (geometry.type === 'MultiPolygon') {
      coords = (geometry.coordinates?.[0]?.[0] || []).slice(0, -1);
    }
    if (coords.length < 2) return 'ns';
    
    // Calculate bounding box
    let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity;
    for (const [lng, lat] of coords) {
      if (lng < minLng) minLng = lng;
      if (lng > maxLng) maxLng = lng;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    }
    const lngRange = maxLng - minLng;
    const latRange = maxLat - minLat;
    
    // If the geometry spans more in longitude, it's a N-S cut (divides E/W)
    // If the geometry spans more in latitude, it's an E-W cut (divides N/S)
    return lngRange >= latRange ? 'ns' : 'ew';
  }

  /**
   * Calculate centroid of a geometry for position comparison
   */
  function getGeometryCentroid(geometry) {
    if (!geometry?.coordinates) return null;
    let coords = [];
    if (geometry.type === 'Polygon') {
      coords = geometry.coordinates[0] || [];
    } else if (geometry.type === 'MultiPolygon') {
      coords = geometry.coordinates[0]?.[0] || [];
    }
    if (!coords.length) return null;
    let sumLng = 0, sumLat = 0;
    for (const [lng, lat] of coords) {
      sumLng += lng;
      sumLat += lat;
    }
    return { lng: sumLng / coords.length, lat: sumLat / coords.length };
  }

  /**
   * Auto-calculate boundary fields based on cutting orientation
   */
  function calculateBoundaries(generatedParcels, sourceParcel, splitGeometry) {
    if (generatedParcels.length !== 2 || !sourceParcel) return;
    
    const orientation = getSplitOrientation(splitGeometry);
    const centroids = generatedParcels.map(p => getGeometryCentroid(p.geometry)).filter(Boolean);
    
    if (centroids.length !== 2) return;
    
    // Determine which parcel is on which side
    const [centroid0, centroid1] = centroids;
    
    // Get the parcel codes for reference
    const code0 = generatedParcels[0].dkbm;
    const code1 = generatedParcels[1].dkbm;
    
    if (orientation === 'ns') {
      // N-S cut: divides into East and West parts
      // Parcel with larger longitude is East, smaller is West
      const [eastIndex, westIndex] = centroid0.lng > centroid1.lng ? [0, 1] : [1, 0];
      
      splitParcelSettings.value[eastIndex].dkdz = code1;
      splitParcelSettings.value[eastIndex].dkxz = sourceParcel.dkxz || "";
      splitParcelSettings.value[eastIndex].dknz = sourceParcel.dknz || "";
      splitParcelSettings.value[eastIndex].dkbz = sourceParcel.dkbz || "";
      
      splitParcelSettings.value[westIndex].dkdz = sourceParcel.dkdz || "";
      splitParcelSettings.value[westIndex].dkxz = code0;
      splitParcelSettings.value[westIndex].dknz = sourceParcel.dknz || "";
      splitParcelSettings.value[westIndex].dkbz = sourceParcel.dkbz || "";
    } else {
      // E-W cut: divides into North and South parts
      // Parcel with larger latitude is North, smaller is South
      const [northIndex, southIndex] = centroid0.lat > centroid1.lat ? [0, 1] : [1, 0];
      
      splitParcelSettings.value[northIndex].dkdz = sourceParcel.dkdz || "";
      splitParcelSettings.value[northIndex].dkxz = sourceParcel.dkxz || "";
      splitParcelSettings.value[northIndex].dknz = code1;
      splitParcelSettings.value[northIndex].dkbz = sourceParcel.dkbz || "";
      
      splitParcelSettings.value[southIndex].dkdz = sourceParcel.dkdz || "";
      splitParcelSettings.value[southIndex].dkxz = sourceParcel.dkxz || "";
      splitParcelSettings.value[southIndex].dknz = sourceParcel.dknz || "";
      splitParcelSettings.value[southIndex].dkbz = code0;
    }
  }
  async function validateSplitGeometry() {
    if (!splitGeometry.value || !splitForm.dkbm || !splitSourceHasGeometry.value) {
      splitPreviewGenerated.value = [];
      splitParcelSettings.value = [];
      return;
    }
    splitPreviewLoading.value = true;
    try {
      const payload = {
        dkbm: splitForm.dkbm,
        splitMode: "geometry",
        splitGeometry: splitGeometry.value,
        geometrySourceSrid: 4326,
      };
      if (splitSourceParcel.value?.geometry) {
        payload.sourceGeometry = splitSourceParcel.value.geometry;
        payload.sourceGeometrySrid = 4326;
      }
      const { data } = await previewSplitSurveyParcel(props.batchId, props.contractorUid, payload);
      const generatedParcels = Array.isArray(data.data?.generatedParcels) ? data.data.generatedParcels : [];
      if (generatedParcels.length < 2) {
        ElMessage.error("切割结果至少应生成 2 个现势地块");
        splitPreviewGenerated.value = [];
        splitParcelSettings.value = [];
        return;
      }
      splitPreviewGenerated.value = generatedParcels;
      // Initialize settings with source parcel defaults
      const source = splitSourceParcel.value;
      splitParcelSettings.value = generatedParcels.map((item) => ({
        dkbm: item.dkbm,
        dkmc: item.dkmc || "",
        htmj: item.htmj ?? source?.htmj ?? 0,
        tdlylx: source?.tdlylx || "",
        dkdz: source?.dkdz || "",
        dkxz: source?.dkxz || "",
        dknz: source?.dknz || "",
        dkbz: source?.dkbz || "",
      }));
      // Auto-calculate boundaries based on cutting orientation
      calculateBoundaries(generatedParcels, source, splitGeometry.value);
      activeSplitTab.value = "0";
      splitConfigDialogVisible.value = true;
      ElMessage.success(`验证通过，将生成 ${generatedParcels.length} 个现势地块`);
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || "切割验证失败，请检查图形是否正确");
      splitPreviewGenerated.value = [];
      splitParcelSettings.value = [];
    } finally {
      splitPreviewLoading.value = false;
    }
  }

  // --- Mode lifecycle ---
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
    stopSplitDraw();
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
      stopSplitDraw();
      clearSplitDraft();
    }
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

  // --- Geometry collection ---
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
    splitPreviewGenerated.value = [];
    splitParcelSettings.value = [];
    if (!geometry) {
      splitGeometry.value = null;
      splitUploadedFilename.value = "";
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
    fitToDraftGeometry();
    validateSplitGeometry();
  }

  // --- Upload & draw ---
  async function handleSplitShpUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !splitModeActive.value || !splitSourceHasGeometry.value) return;
    try {
      const buffer = await file.arrayBuffer();
      const parsed = await shp(buffer);
      const geometry = normalizeUploadedSplitGeometry(parsed);
      splitUploadedFilename.value = file.name;
      stopSplitDraw();
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
    stopSplitDraw();
    clearSplitDraft();
    splitDrawMode.value = mode;
    const interaction = new Draw({
      source: draftSource,
      type: mode === "polygon" ? "Polygon" : "LineString",
    });
    interaction.on("drawstart", () => {
      draftSource.clear();
      splitGeometry.value = null;
      splitUploadedFilename.value = "";
      splitPreviewGenerated.value = [];
      splitParcelSettings.value = [];
    });
    interaction.on("drawend", (event) => {
      const geometry = writeDraftGeometry(event.feature) || writeCurrentDraftGeometry();
      if (!geometry) {
        ElMessage.warning("切割图形无效，请重新绘制");
        return;
      }
      applySplitGeometryToMap(geometry);
      stopSplitDraw();
    });
    mapRef.value.addInteraction(interaction);
    draftMap.drawInteraction = interaction;
  }

  // --- Submit ---
  async function submitSplitParcel() {
    if (!splitCanSubmit.value) {
      ElMessage.warning("请先补全切割信息");
      return;
    }
    const payload = {
      dkbm: splitForm.dkbm,
      reason: splitForm.reason?.trim() || undefined,
    };
    if (splitSourceParcel.value?.geometry) {
      payload.sourceGeometry = splitSourceParcel.value.geometry;
      payload.sourceGeometrySrid = 4326;
    }
    submittingSplitParcel.value = true;
    try {
      if (splitForm.splitMethod === "geometry") {
        payload.splitMode = "geometry";
        payload.splitGeometry = splitGeometry.value;
        payload.geometrySourceSrid = 4326;
        payload.generatedParcels = splitPreviewGenerated.value.map((item, index) => {
          const settings = splitParcelSettings.value[index] || {};
          return {
            dkbm: settings.dkbm || item.dkbm,
            dkmc: settings.dkmc || item.dkmc,
            scmj: item.scmj,
            htmj: settings.htmj ?? item.htmj,
            tdlylx: settings.tdlylx || "",
            dkdz: settings.dkdz || "",
            dkxz: settings.dkxz || "",
            dknz: settings.dknz || "",
            dkbz: settings.dkbz || "",
            geometry: item.geometry,
          };
        });
      } else {
        payload.splitMode = "area";
        payload.newDkbm = splitForm.newDkbm.trim();
        payload.newDkmc = splitForm.newDkmc.trim();
        payload.newScmj = Number(splitForm.newScmj);
        payload.splitDirection = splitForm.splitDirection;
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
      }
      emit("split-parcel", { type: "split_parcel", payload });
      finishSplitParcelMode();
      ElMessage.success(`切割地块已加入待保存，将生成 ${payload.generatedParcels.length} 个现势地块`);
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || error?.message || "切割地块失败");
    } finally {
      submittingSplitParcel.value = false;
    }
  }

  // --- Select parcel in split mode ---
  function selectParcelInSplitMode(parcel) {
    if (splitModeActive.value && isCurrentParcel(parcel)) {
      if (splitForm.dkbm !== parcel.dkbm) {
        splitForm.dkbm = parcel.dkbm;
        splitForm.newScmj = 0;
        clearSplitDraft();
      }
    }
  }

  return {
    // State
    splitModeActive,
    splitUploadedFilename,
    splitGeometry,
    splitDrawMode,
    generatingSplitCode,
    submittingSplitParcel,
    splitForm,
    splitPreviewLoading,
    splitPreviewGenerated,
    splitParcelSettings,
    activeSplitTab,
    splitConfigDialogVisible,
    // Computed
    splitSourceParcel,
    splitSourceHasGeometry,
    splitRemainingArea,
    splitMaxArea,
    splitCanSubmit,
    splitModeAlertType,
    splitModeAlertText,
    // Methods
    beginSplitParcelMode,
    finishSplitParcelMode,
    cancelSplitParcelMode,
    switchSplitMethod,
    clearSplitDraft,
    handleGenerateSplitCode,
    handleSplitShpUpload,
    startSplitDrawMode,
    submitSplitParcel,
    selectParcelInSplitMode,
    validateSplitGeometry,
  };
}


