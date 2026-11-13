import GeoJSON from "ol/format/GeoJSON";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import Snap from "ol/interaction/Snap";
import { Fill, Stroke, Style } from "ol/style";

/**
 * Composable for managing the OpenLayers draft layer used by both
 * add-parcel and split-parcel workflows.
 * Extracted from ParcelInfoPanel.vue to reduce component size.
 *
 * @param {import("vue").Ref} mapRoot - template ref for the map container
 * @param {Object} dialogMap - useDialogMap instance
 */
export function useParcelDraftMap(mapRoot, dialogMap) {
  const {
    mapRef, mapReady, activeBasemap, basemapOptions,
    initMap, switchBasemap, loadParcels, fitToParcels,
    focusParcel, clearSelection, updateMapSize, destroyMap,
    parcelSource,
  } = dialogMap;

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
  // 捕捉交互：绘制时吸附到已有地块图形的顶点/边线（新增地块、切割绘制共用）
  let snapInteraction = null;
  let snapInteractionMap = null;

  function ensureSnap() {
    const map = mapRef.value;
    if (!map || !parcelSource) return;
    // 地图销毁重建后 Snap 必须挂到新地图实例上
    if (!snapInteraction || snapInteractionMap !== map) {
      if (snapInteractionMap) {
        snapInteractionMap.removeInteraction(snapInteraction);
      }
      snapInteraction = new Snap({ source: parcelSource });
      snapInteractionMap = map;
    }
    if (!map.getInteractions().getArray().includes(snapInteraction)) {
      map.addInteraction(snapInteraction);
    }
  }

  function stopSnap() {
    if (snapInteraction && mapRef.value) {
      mapRef.value.removeInteraction(snapInteraction);
    }
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
    stopSnap();
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

  return {
    // Dialog map pass-through
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
    // Draft layer
    geoJsonFormat,
    draftSource,
    draftLayer,
    ensureDraftLayer,
    removeDraftLayer,
    stopDraw,
    ensureSnap,
    stopSnap,
    fitToDraftGeometry,
    writeDraftGeometry,
    writeCurrentDraftGeometry,
    // Mutable property for child composables to assign draw interactions
    get drawInteraction() { return drawInteraction; },
    set drawInteraction(v) { drawInteraction = v; },
  };
}
