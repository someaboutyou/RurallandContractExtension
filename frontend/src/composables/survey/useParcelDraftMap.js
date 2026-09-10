import GeoJSON from "ol/format/GeoJSON";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
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
    fitToDraftGeometry,
    writeDraftGeometry,
    writeCurrentDraftGeometry,
    // Mutable property for child composables to assign draw interactions
    get drawInteraction() { return drawInteraction; },
    set drawInteraction(v) { drawInteraction = v; },
  };
}
