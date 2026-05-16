import { ref, shallowRef } from "vue";
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
  const sc = config.serviceConfigs?.[0];
  if (!sc) return null;
  if (sc.serviceType === "OSM") {
    return new TileLayer({ source: new OSM() });
  }
  return new TileLayer({
    source: new XYZ({ url: sc.serviceUrl, crossOrigin: "anonymous" }),
  });
}

export function useDialogMap(targetRef) {
  const mapRef = shallowRef(null);
  const mapReady = ref(false);
  const activeBasemap = ref("image");
  const parcelSource = new VectorSource();
  const selectedParcelDkbm = ref(null);

  const basemapOptions = basemapConfigs.map((b) => ({
    label: b.name,
    value: b.key,
  }));

  const basemapLayers = new Map();
  let dkLayers = [];
  let parcelLayer = null;

  async function initMap() {
    if (mapRef.value) return;

    const activeConfig = basemapConfigs.find((c) => c.key === activeBasemap.value) || basemapConfigs[0];
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
      const config = basemapConfigs.find((c) => c.key === key);
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
