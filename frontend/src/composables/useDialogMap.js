import { computed, ref, shallowRef } from "vue";
import "ol/ol.css";
import OlMap from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { OSM, Vector as VectorSource, XYZ, TileWMS } from "ol/source";
import WMTS, { optionsFromCapabilities } from "ol/source/WMTS";
import WMTSTileGrid from "ol/tilegrid/WMTS";
import { get as getProjection } from "ol/proj";
import { Fill, Stroke, Style } from "ol/style";

import { fetchMapLayers } from "../api/mapLayer";
import { basemapConfigs } from "../config/mapLayers";

const WMTS_CAPABILITIES_URL =
  "/geoserver/erlunyanbao/gwc/service/wmts?service=WMTS&version=1.0.0&request=GetCapabilities";

let cachedWmtsCapabilities = null;

async function fetchWmtsCapabilities() {
  if (cachedWmtsCapabilities) return cachedWmtsCapabilities;
  try {
    const resp = await fetch(WMTS_CAPABILITIES_URL);
    if (!resp.ok) return null;
    cachedWmtsCapabilities = await resp.text();
    return cachedWmtsCapabilities;
  } catch {
    return null;
  }
}

function buildDefaultEpsg4326TileGrid() {
  const resolutions = Array.from({ length: 22 }, (_, i) => 0.703125 / Math.pow(2, i));
  const matrixIds = Array.from({ length: 22 }, (_, i) => `EPSG:4326:${i}`);
  return new WMTSTileGrid({
    origin: [-180, 90],
    resolutions,
    matrixIds,
  });
}

async function createSurveyDkResultLayer() {
  const projection = getProjection("EPSG:4326");
  const wmtsUrl =
    "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:survey_dk_result&style=&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png";
  const wmsUrl =
    "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:survey_dk_result&styles=&format=image/png&transparent=true";

  let wmtsSource;
  const capabilities = await fetchWmtsCapabilities();
  if (capabilities) {
    try {
      const parser = new DOMParser();
      const xml = parser.parseFromString(capabilities, "text/xml");
      if (!xml.querySelector("parsererror")) {
        const opts = optionsFromCapabilities(xml, {
          layer: "erlunyanbao:survey_dk_result",
          matrixSet: "EPSG:4326",
          requestEncoding: "KVP",
        });
        if (opts) {
          opts.url = wmtsUrl;
          opts.crossOrigin = "anonymous";
          wmtsSource = new WMTS(opts);
        }
      }
    } catch (e) {
      console.warn("Failed to parse WMTS capabilities, using default tile grid:", e);
    }
  }

  if (!wmtsSource) {
    wmtsSource = new WMTS({
      url: wmtsUrl,
      layer: "erlunyanbao:survey_dk_result",
      matrixSet: "EPSG:4326",
      format: "image/png",
      projection,
      requestEncoding: "KVP",
      tileGrid: buildDefaultEpsg4326TileGrid(),
      crossOrigin: "anonymous",
    });
  }

  const wmtsLayer = new TileLayer({
    source: wmtsSource,
    minZoom: 0,
    maxZoom: 15,
    visible: true,
  });

  const wmsLayer = new TileLayer({
    source: new TileWMS({
      url: wmsUrl,
      params: {
        LAYERS: "erlunyanbao:survey_dk_result",
        FORMAT: "image/png",
        TRANSPARENT: true,
      },
      projection,
      crossOrigin: "anonymous",
    }),
    minZoom: 16,
    maxZoom: 19,
    visible: true,
  });

  return [wmtsLayer, wmsLayer];
}

function createBasemapLayer(config) {
  const sc = config.serviceConfigs?.find((item) => item.enabled !== false) || config.serviceConfigs?.[0];
  if (!sc) return null;
  if (sc.serviceType === "OSM") {
    return new TileLayer({ source: new OSM() });
  }
  return new TileLayer({
    source: new XYZ({ url: sc.serviceUrl, crossOrigin: "anonymous" }),
  });
}

function normalizeLayer(item) {
  const rawServiceConfigs =
    item.serviceConfigs?.length
      ? item.serviceConfigs
      : item.layerType && item.serviceUrl
        ? [
            {
              serviceType: item.layerType,
              serviceUrl: item.serviceUrl,
              projection: item.projection,
              minZoom: 0,
              maxZoom: 24,
              enabled: true,
            },
          ]
        : [];
  if (!rawServiceConfigs.length) {
    return null;
  }
  const serviceConfigs = rawServiceConfigs.map((service) => ({
    serviceType: String(service.serviceType ?? service.layerType ?? item.layerType ?? "XYZ").toUpperCase(),
    serviceUrl: service.serviceUrl ?? service.service_url ?? item.serviceUrl ?? item.service_url ?? "",
    projection: service.projection ?? item.projection ?? "EPSG:3857",
    minZoom: Number(service.minZoom ?? service.min_zoom ?? 0),
    maxZoom: Number(service.maxZoom ?? service.max_zoom ?? 24),
    enabled: service.enabled ?? true,
  }));
  const primaryConfig = serviceConfigs.find((service) => service.enabled !== false) || serviceConfigs[0];
  return {
    id: item.id ?? item.key,
    key: item.key,
    name: item.name,
    category: item.category,
    layerType: primaryConfig.serviceType,
    serviceUrl: primaryConfig.serviceUrl,
    projection: primaryConfig.projection,
    defaultVisible: item.defaultVisible ?? item.default_visible ?? false,
    isDefault: item.isDefault ?? item.is_default ?? false,
    sortOrder: item.sortOrder ?? item.sort_order ?? 0,
    enabled: item.enabled ?? true,
    serviceConfigs,
  };
}

export function useDialogMap(targetRef) {
  const mapRef = shallowRef(null);
  const mapReady = ref(false);
  const activeBasemap = ref("image");
  const basemapRows = ref(basemapConfigs.map(normalizeLayer).filter(Boolean));
  const parcelSource = new VectorSource();
  const selectedParcelDkbm = ref(null);

  const basemapOptions = computed(() =>
    basemapRows.value.map((b) => ({
      label: b.name,
      value: b.key,
    })),
  );

  const basemapLayers = new Map();
  let dkLayers = [];
  let parcelLayer = null;

  async function loadBasemapConfigs() {
    try {
      const { data } = await fetchMapLayers({ category: "basemap", enabledOnly: true });
      const rows = (data.data || []).map(normalizeLayer).filter(Boolean).sort((a, b) => a.sortOrder - b.sortOrder);
      if (rows.length) {
        basemapRows.value = rows;
      }
    } catch (e) {
      console.warn("Failed to load configured basemaps, using fallback basemaps:", e);
    }
    const defaultBasemap = basemapRows.value.find((item) => item.isDefault) || basemapRows.value[0];
    if (defaultBasemap) {
      activeBasemap.value = defaultBasemap.key;
    }
  }

  async function initMap() {
    if (mapRef.value) return;

    await loadBasemapConfigs();

    const activeConfig = basemapRows.value.find((c) => c.key === activeBasemap.value) || basemapRows.value[0];
    if (activeConfig) {
      const layer = createBasemapLayer(activeConfig);
      if (layer) {
        basemapLayers.set(activeConfig.key, layer);
      }
    }

    try {
      dkLayers = await createSurveyDkResultLayer();
    } catch (e) {
      console.warn("Failed to create survey_dk_result layer:", e);
      dkLayers = [];
    }

    parcelLayer = new VectorLayer({
      source: parcelSource,
      style: (feature) => {
        const isSelected = feature.get("dkbm") === selectedParcelDkbm.value;
        const isHistorical = ["removed", "split_source"].includes(feature.get("resultStatus"));
        if (isHistorical) {
          return new Style({
            fill: new Fill({ color: "rgba(100, 116, 139, 0.06)" }),
            stroke: new Stroke({
              color: isSelected ? "#dc2626" : "#64748b",
              width: isSelected ? 3 : 2,
              lineDash: [8, 6],
            }),
          });
        }
        if (isSelected) {
          return new Style({
            fill: new Fill({ color: "rgba(255, 255, 0, 0.4)" }),
            stroke: new Stroke({ color: "#ff0000", width: 4 }),
          });
        }
        return new Style({
          fill: new Fill({ color: "rgba(255, 165, 0, 0.25)" }),
          stroke: new Stroke({ color: "#ff6600", width: 2 }),
        });
      },
      visible: true,
    });

    const layers = [...basemapLayers.values(), ...dkLayers, parcelLayer];

    mapRef.value = new OlMap({
      target: targetRef.value,
      layers,
      view: new View({
        center: [13350000, 3500000],
        zoom: 5,
        minZoom: 5,
        maxZoom: 19,
      }),
    });

    mapReady.value = true;
  }

  function switchBasemap(key) {
    activeBasemap.value = key;
    if (!mapRef.value) return;
    basemapLayers.forEach((layer) => {
      mapRef.value.removeLayer(layer);
    });
    let newLayer = basemapLayers.get(key);
    if (!newLayer) {
      const config = basemapRows.value.find((c) => c.key === key);
      if (config) {
        newLayer = createBasemapLayer(config);
        if (newLayer) basemapLayers.set(key, newLayer);
      }
    }
    if (newLayer) {
      mapRef.value.addLayer(newLayer);
    }
  }

  function loadParcels(parcelDataList) {
    parcelSource.clear();
    clearSelection();
    if (!parcelDataList?.length) return;

    const geoJsonFormat = new GeoJSON();
    for (const item of parcelDataList) {
      if (!item.geometry) continue;
      try {
        const feature = geoJsonFormat.readFeature(item.geometry, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        });
        feature.set("dkbm", item.dkbm);
        feature.set("dkmc", item.dkmc);
        feature.set("scmj", item.scmj);
        feature.set("htmj", item.htmj);
        feature.set("resultStatus", item.resultStatus);
        feature.set("changeType", item.changeType);
        feature.set("changeReason", item.changeReason);
        parcelSource.addFeature(feature);
      } catch (e) {
        console.warn("Failed to parse geometry for parcel", item.dkbm, e);
      }
    }
  }

  function fitToParcels() {
    const extent = parcelSource.getExtent();
    if (!extent || extent[0] === Infinity) return;
    mapRef.value?.getView().fit(extent, {
      padding: [40, 40, 40, 40],
      duration: 400,
      maxZoom: 18,
    });
  }

  function focusParcel(dkbm) {
    const feature = parcelSource.getFeatures().find((f) => f.get("dkbm") === dkbm);
    if (!feature) return;
    selectedParcelDkbm.value = dkbm;
    parcelLayer?.changed();
    const extent = feature.getGeometry().getExtent();
    mapRef.value?.getView().fit(extent, {
      padding: [60, 60, 60, 60],
      duration: 300,
      maxZoom: 18,
    });
  }

  function clearSelection() {
    selectedParcelDkbm.value = null;
    parcelLayer?.changed();
  }

  function updateMapSize() {
    mapRef.value?.updateSize();
  }

  function destroyMap() {
    if (mapRef.value) {
      mapRef.value.setTarget(undefined);
      mapRef.value = null;
    }
    basemapLayers.clear();
    dkLayers = [];
    parcelLayer = null;
    parcelSource.clear();
    mapReady.value = false;
  }

  return {
    mapRef,
    mapReady,
    activeBasemap,
    basemapOptions,
    selectedParcelDkbm,
    initMap,
    switchBasemap,
    loadParcels,
    fitToParcels,
    focusParcel,
    clearSelection,
    updateMapSize,
    destroyMap,
  };
}
