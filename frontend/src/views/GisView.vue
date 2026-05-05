<template>
  <section class="gis-page">
    <section class="gis-map-shell">
      <div class="gis-map-surface">
        <div ref="mapRootRef" class="gis-ol-map"></div>
        <div class="gis-map-vignette"></div>

        <div class="gis-scene-title">{{ ui.title }}</div>

        <div class="gis-floating-toolbar">
          <button
            v-for="tool in tools"
            :key="tool.key"
            type="button"
            class="gis-floating-tool"
            :class="{ 'is-active': activeTool === tool.key }"
            @click="toggleTool(tool.key)"
            :title="tool.label"
            :aria-label="tool.label"
          >
            <span class="gis-tool-label">{{ tool.label }}</span>
            <span class="gis-tool-icon" aria-hidden="true" v-html="tool.icon"></span>
          </button>
          <button
            type="button"
            class="gis-floating-tool gis-floating-tool--ghost"
            @click="resetView"
            :title="resetTool.label"
            :aria-label="resetTool.label"
          >
            <span class="gis-tool-label">{{ resetTool.label }}</span>
            <span class="gis-tool-icon" aria-hidden="true" v-html="resetTool.icon"></span>
          </button>
        </div>

        <div v-if="activeTool === 'layers'" class="gis-floating-panel gis-floating-panel--left">
          <div class="gis-panel-head">
            <div class="gis-floating-panel-title">{{ ui.layerControl }}</div>
            <button type="button" class="gis-panel-toggle" @click="collapseLayerPanel = !collapseLayerPanel">
              {{ collapseLayerPanel ? ui.expand : ui.collapse }}
            </button>
          </div>
          <div v-if="!collapseLayerPanel" class="gis-layer-tree">
            <div v-for="group in groupedLayerRows" :key="group.name" class="gis-layer-group">
              <div class="gis-layer-group-name">{{ group.name }}</div>
              <label v-for="layer in group.items" :key="layer.key" class="gis-layer-row">
                <input v-model="layer.visible" type="checkbox" @change="syncLayerVisibility(layer)" />
                <span>{{ layer.name }}</span>
              </label>
            </div>
          </div>
        </div>

        <div v-if="activeTool === 'measure'" class="gis-floating-panel gis-floating-panel--left secondary">
          <div class="gis-floating-panel-title">{{ ui.measureTool }}</div>
          <div class="gis-measure-actions">
            <el-button size="small" :type="measureMode === 'distance' ? 'primary' : 'default'" @click="activateMeasure('distance')">
              {{ ui.measureDistance }}
            </el-button>
            <el-button size="small" :type="measureMode === 'area' ? 'primary' : 'default'" @click="activateMeasure('area')">
              {{ ui.measureArea }}
            </el-button>
            <el-button size="small" plain @click="clearMeasure">{{ ui.clearMeasure }}</el-button>
          </div>
          <div class="gis-measure-result">
            <div>{{ ui.currentMode }}{{ measureMode === "distance" ? ui.measureDistance : ui.measureArea }}</div>
            <div>{{ ui.measureResult }}{{ measureResult }}</div>
          </div>
        </div>

        <div v-if="activeTool === 'label'" class="gis-floating-panel gis-floating-panel--left secondary">
          <div class="gis-floating-panel-title">{{ ui.labelTool }}</div>
          <el-input v-model="markText" :placeholder="ui.labelPlaceholder" />
          <div class="gis-measure-actions">
            <el-button size="small" type="primary" @click="activateLabel">{{ ui.startLabel }}</el-button>
            <el-button size="small" plain @click="clearLabels">{{ ui.clearLabel }}</el-button>
          </div>
          <div class="gis-hint">{{ ui.labelHint }}</div>
        </div>

        <div v-if="activeTool === 'query'" class="gis-floating-panel gis-floating-panel--left secondary">
          <div class="gis-floating-panel-title">{{ ui.queryTool }}</div>
          <el-input v-model="queryKeyword" :placeholder="ui.queryPlaceholder" />
          <div class="gis-measure-actions">
            <el-button size="small" type="primary" @click="performQuery">{{ ui.locateQuery }}</el-button>
            <el-button size="small" plain @click="clearSelection">{{ ui.clearSelection }}</el-button>
          </div>
          <div class="gis-query-result">
            <div v-if="queryMessage" class="gis-query-item">{{ queryMessage }}</div>
            <div class="gis-query-item">{{ ui.queryTip }}</div>
          </div>

          <div v-if="hasSearchResult" class="gis-query-sections">
            <div v-if="searchResult.requests.length" class="gis-query-section">
              <div class="gis-query-section-title">{{ ui.requestSection }}</div>
              <button
                v-for="item in searchResult.requests"
                :key="`request-${item.id}`"
                type="button"
                class="gis-query-business-item"
                @click="applyRequestResult(item)"
              >
                <div class="gis-query-business-title">{{ item.requestTitle || `${item.requestType}-${item.contractorName}` }}</div>
                <div class="gis-query-business-meta">
                  <span>{{ item.serialNo }}</span>
                  <span>{{ item.status }}</span>
                </div>
              </button>
            </div>

            <div v-if="searchResult.issuers.length" class="gis-query-section">
              <div class="gis-query-section-title">{{ ui.issuerSection }}</div>
              <button
                v-for="item in searchResult.issuers"
                :key="`issuer-${item.code}`"
                type="button"
                class="gis-query-business-item"
                @click="applyIssuerResult(item)"
              >
                <div class="gis-query-business-title">{{ item.name }}</div>
                <div class="gis-query-business-meta">
                  <span>{{ item.code }}</span>
                  <span>{{ item.ownerName || ui.notMaintainedOwner }}</span>
                </div>
              </button>
            </div>

            <div v-if="searchResult.contractors.length" class="gis-query-section">
              <div class="gis-query-section-title">{{ ui.contractorSection }}</div>
              <button
                v-for="item in searchResult.contractors"
                :key="`contractor-${item.code}`"
                type="button"
                class="gis-query-business-item"
                @click="applyContractorResult(item)"
              >
                <div class="gis-query-business-title">{{ item.name }}</div>
                <div class="gis-query-business-meta">
                  <span>{{ item.code }}</span>
                  <span>{{ item.idNo || ui.notMaintainedId }}</span>
                </div>
              </button>
            </div>
          </div>
        </div>

        <aside class="gis-property-panel">
          <div class="gis-property-title">{{ ui.attrTitle }}</div>
          <div class="gis-attr-card" v-for="item in attrs" :key="item.label">
            <div class="gis-attr-card-label">{{ item.label }}</div>
            <div class="gis-attr-card-value">{{ item.value }}</div>
          </div>
        </aside>

        <div class="gis-map-crosshair"></div>

        <div class="gis-bottom-bar">
          <div ref="scaleLineRef" class="gis-bottom-item gis-bottom-item--scale"></div>
          <div class="gis-bottom-item">{{ ui.coordPrefix }}{{ currentCoord }}</div>
          <div class="gis-bottom-item gis-bottom-basemap">
            <span>{{ ui.basemap }}</span>
            <el-segmented v-model="activeBasemap" :options="basemapOptions" size="small" @change="switchBasemap" />
          </div>
        </div>
      </div>
    </section>
  </section>
</template>

<script setup>
import "ol/ol.css";

import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from "vue";
import { ElMessage } from "element-plus";
import Feature from "ol/Feature";
import GeoJSON from "ol/format/GeoJSON";
import OlMap from "ol/Map";
import View from "ol/View";
import { ScaleLine } from "ol/control";
import { Draw } from "ol/interaction";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import WMTSGrid from "ol/tilegrid/WMTS";
import { fromLonLat, get as getProjection, toLonLat, transformExtent } from "ol/proj";
import { OSM, TileWMS, Vector as VectorSource, XYZ } from "ol/source";
import WMTS from "ol/source/WMTS";
import { Fill, Icon, Stroke, Style, Text } from "ol/style";
import Point from "ol/geom/Point";
import { getArea, getLength } from "ol/sphere";

import { searchGisBusiness } from "../api/gis";
import { fetchMapLayers } from "../api/mapLayer";
import { basemapConfigs as fallbackBasemaps, vectorLayerConfigs as fallbackVectors } from "../config/mapLayers";

const ui = {
  title: "\u519c\u6751\u627f\u5305\u7ecf\u8425\u6743 GIS \u4e00\u5f20\u56fe",
  reset: "\u590d\u4f4d",
  layerControl: "\u56fe\u5c42\u63a7\u5236",
  expand: "\u5c55\u5f00",
  collapse: "\u6536\u8d77",
  measureTool: "\u91cf\u6d4b\u5de5\u5177",
  measureDistance: "\u8ddd\u79bb\u91cf\u6d4b",
  measureArea: "\u9762\u79ef\u91cf\u6d4b",
  clearMeasure: "\u6e05\u9664\u91cf\u6d4b",
  currentMode: "\u5f53\u524d\u6a21\u5f0f\uff1a",
  measureResult: "\u91cf\u6d4b\u7ed3\u679c\uff1a",
  labelTool: "\u6807\u6ce8\u5de5\u5177",
  labelPlaceholder: "\u8bf7\u8f93\u5165\u6807\u6ce8\u5185\u5bb9",
  startLabel: "\u5f00\u59cb\u6807\u6ce8",
  clearLabel: "\u6e05\u9664\u6807\u6ce8",
  labelHint: "\u70b9\u51fb\u5730\u56fe\u4efb\u610f\u4f4d\u7f6e\u5373\u53ef\u843d\u70b9\uff0c\u6587\u5b57\u4f1a\u8ddf\u968f\u6807\u6ce8\u663e\u793a\u3002",
  queryTool: "\u67e5\u8be2\u5de5\u5177",
  queryPlaceholder: "\u8f93\u5165\u5730\u5757\u7f16\u7801\u3001\u53d1\u5305\u65b9\u3001\u627f\u5305\u65b9\u6216\u4e1a\u52a1\u6d41\u6c34\u53f7",
  locateQuery: "\u5b9a\u4f4d\u67e5\u8be2",
  clearSelection: "\u6e05\u9664\u9009\u62e9",
  queryTip: "\u652f\u6301\u4e1a\u52a1\u7533\u8bf7\u3001\u53d1\u5305\u65b9\u3001\u627f\u5305\u65b9\u4e09\u7c7b\u6570\u636e\u8054\u52a8\u67e5\u8be2\uff0c\u4e5f\u652f\u6301\u5730\u56fe\u70b9\u51fb\u67e5\u8be2\u3002",
  requestSection: "\u4e1a\u52a1\u7533\u8bf7",
  issuerSection: "\u53d1\u5305\u65b9",
  contractorSection: "\u627f\u5305\u65b9",
  notMaintainedOwner: "\u672a\u7ef4\u62a4\u8d1f\u8d23\u4eba",
  notMaintainedId: "\u672a\u7ef4\u62a4\u8bc1\u4ef6\u53f7",
  attrTitle: "\u8981\u7d20\u5c5e\u6027",
  coordPrefix: "\u7ecf\u7eac\u5ea6\uff1a",
  basemap: "\u5e95\u56fe",
  currentObject: "\u5f53\u524d\u5bf9\u8c61",
  currentBusiness: "\u5f53\u524d\u4e1a\u52a1",
  issuer: "\u53d1\u5305\u65b9",
  contractor: "\u627f\u5305\u65b9",
  parcelCode: "\u5730\u5757\u7f16\u7801",
  area: "\u9762\u79ef",
  status: "\u72b6\u6001",
  coord: "\u5750\u6807",
  requestType: "\u4e1a\u52a1\u7c7b\u578b",
  requestTitle: "\u4e1a\u52a1\u6807\u9898",
  serialNo: "\u4e1a\u52a1\u6d41\u6c34\u53f7",
  currentStep: "\u5f53\u524d\u73af\u8282",
  issuerName: "\u53d1\u5305\u65b9\u540d\u79f0",
  issuerCode: "\u53d1\u5305\u65b9\u7f16\u7801",
  ownerName: "\u8d1f\u8d23\u4eba",
  idNo: "\u8bc1\u4ef6\u53f7\u7801",
  mobile: "\u8054\u7cfb\u7535\u8bdd",
  address: "\u8054\u7cfb\u5730\u5740",
  contractorName: "\u627f\u5305\u65b9\u540d\u79f0",
  contractorCode: "\u627f\u5305\u65b9\u7f16\u7801",
  contractorType: "\u627f\u5305\u65b9\u7c7b\u578b",
  objectLayer: "\u5730\u5757\u56fe\u5c42",
  objectRequest: "\u4e1a\u52a1\u7533\u8bf7",
  objectIssuer: "\u53d1\u5305\u65b9",
  objectContractor: "\u627f\u5305\u65b9",
  defaultBusiness: "\u9996\u6b21\u767b\u8bb0 / \u7533\u8bf7\u9636\u6bb5",
  defaultIssuer: "\u6398\u6e2f\u8857\u9053\u67d0\u6751\u96c6\u4f53",
  defaultContractor: "\u738b\u4e94",
  defaultParcelCode: "321324-01-08-0032",
  defaultArea: "5.62 \u4ea9",
  defaultStatus: "\u5f85\u63d0\u4ea4",
  defaultCoord: "120.12345, 30.67890",
  emptyKeyword: "\u8bf7\u8f93\u5165\u5730\u5757\u7f16\u7801\u3001\u53d1\u5305\u65b9\u3001\u627f\u5305\u65b9\u6216\u4e1a\u52a1\u6d41\u6c34\u53f7\u3002",
  fallbackConfig: "\u56fe\u5c42\u914d\u7f6e\u63a5\u53e3\u6682\u4e0d\u53ef\u7528\uff0c\u5df2\u5207\u6362\u4e3a\u672c\u5730\u6f14\u793a\u914d\u7f6e\u3002",
  requestLinked: "\u5df2\u8054\u52a8\u4e1a\u52a1\u7533\u8bf7 ",
  issuerLinked: "\u5df2\u8054\u52a8\u53d1\u5305\u65b9 ",
  contractorLinked: "\u5df2\u8054\u52a8\u627f\u5305\u65b9 ",
  requestMatched: "\u5df2\u5339\u914d ",
  requestMatchedSuffix: " \u6761\u4e1a\u52a1\u7533\u8bf7",
  notFound: "\u672a\u67e5\u8be2\u5230\u5339\u914d\u7684\u4e1a\u52a1\u5bf9\u8c61\u3002",
  clickNoFeature: "\u5f53\u524d\u70b9\u51fb\u4f4d\u7f6e\u672a\u67e5\u8be2\u5230\u56fe\u5c42\u8981\u7d20\u3002",
  mapClickHit: "\u5df2\u901a\u8fc7\u5730\u56fe\u70b9\u51fb\u547d\u4e2d\u56fe\u5c42 ",
  clickPoint: "\u70b9\u51fb\u70b9",
  meters: "\u7c73",
  squareMeters: "\u5e73\u65b9\u7c73",
  unknown: "-",
  ungrouped: "\u672a\u5206\u7ec4",
};

const tools = [
  {
    key: "layers",
    label: "\u56fe\u5c42",
    icon:
      "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M12 3 3.5 7.5 12 12l8.5-4.5L12 3Z'/><path d='M3.5 12 12 16.5 20.5 12'/><path d='M3.5 16.5 12 21l8.5-4.5'/></svg>",
  },
  {
    key: "measure",
    label: "\u91cf\u6d4b",
    icon:
      "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M4 16 16 4'/><path d='M14 4h6v6'/><path d='M6.5 13.5 9 16'/><path d='M10 10 12.5 12.5'/><path d='M13.5 6.5 16 9'/></svg>",
  },
  {
    key: "label",
    label: "\u6807\u6ce8",
    icon:
      "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M12 21s6-5.2 6-10a6 6 0 1 0-12 0c0 4.8 6 10 6 10Z'/><circle cx='12' cy='11' r='2.2' fill='currentColor' stroke='none'/></svg>",
  },
  {
    key: "query",
    label: "\u67e5\u8be2",
    icon:
      "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='5.5'/><path d='m16 16 4.2 4.2'/></svg>",
  },
];

const resetTool = {
  label: ui.reset,
  icon: "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M20 6v6h-6'/><path d='M20 12a8 8 0 1 1-2.34-5.66L20 8.7'/></svg>",
};

const mapRootRef = ref(null);
const scaleLineRef = ref(null);
const mapRef = shallowRef(null);

const activeTool = ref("layers");
const activeBasemap = ref("image");
const collapseLayerPanel = ref(true);
const measureMode = ref("distance");
const measureResult = ref(`0 ${ui.meters}`);
const queryKeyword = ref("");
const queryMessage = ref("");
const currentCoord = ref(ui.defaultCoord);
const markText = ref("");

const basemapRows = ref([]);
const layerRows = ref([]);
const searchResult = ref({ requests: [], issuers: [], contractors: [] });
const attrs = ref([
  { label: ui.currentObject, value: ui.objectLayer },
  { label: ui.currentBusiness, value: ui.defaultBusiness },
  { label: ui.issuer, value: ui.unknown },
  { label: ui.contractor, value: ui.unknown },
  { label: ui.parcelCode, value: ui.unknown },
  { label: ui.area, value: ui.unknown },
  { label: ui.status, value: ui.unknown },
  { label: ui.coord, value: ui.defaultCoord },
]);

const groupedLayerRows = computed(() => {
  const groups = new globalThis.Map();
  for (const layer of layerRows.value) {
    const groupName = layer.groupName || ui.ungrouped;
    if (!groups.has(groupName)) {
      groups.set(groupName, []);
    }
    groups.get(groupName).push(layer);
  }
  return Array.from(groups.entries()).map(([name, items]) => ({ name, items }));
});

const basemapOptions = computed(() =>
  basemapRows.value.map((item) => ({
    label: item.name,
    value: item.key,
  })),
);

const hasSearchResult = computed(() => searchResult.value.requests.length || searchResult.value.issuers.length || searchResult.value.contractors.length);

const layerInstances = new globalThis.Map();
const basemapLayerInstances = new globalThis.Map();

let scaleControl = null;
let measureDrawInteraction = null;
let labelDrawInteraction = null;
let measureLayer = null;
let labelLayer = null;

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
  const normalizedConfigs = rawServiceConfigs.map((service) => {
    const url = service.serviceUrl ?? service.service_url ?? item.serviceUrl ?? item.service_url ?? "";
    return {
      id: service.id || `${item.key}_${service.serviceType ?? service.layerType ?? item.layerType}_${service.minZoom ?? 0}_${service.maxZoom ?? 24}`,
      serviceType: service.serviceType ?? service.layerType ?? item.layerType ?? item.layer_type ?? "WMS",
      serviceUrl: url,
      projection: service.projection ?? item.projection ?? "EPSG:3857",
      minZoom: Number(service.minZoom ?? service.min_zoom ?? 0),
      maxZoom: Number(service.maxZoom ?? service.max_zoom ?? 24),
      enabled: service.enabled ?? true,
    };
  });
  const primaryConfig = normalizedConfigs[0];
  return {
    id: item.id ?? item.key,
    name: item.name,
    key: item.key,
    category: item.category,
    groupName: item.groupName ?? item.group_name ?? "",
    layerType: primaryConfig.serviceType,
    serviceUrl: primaryConfig.serviceUrl,
    projection: primaryConfig.projection,
    defaultVisible: item.defaultVisible ?? item.default_visible ?? false,
    isDefault: item.isDefault ?? item.is_default ?? false,
    sortOrder: item.sortOrder ?? item.sort_order ?? 0,
    enabled: item.enabled ?? true,
    visible: item.defaultVisible ?? item.default_visible ?? false,
    serviceConfigs: normalizedConfigs,
  };
}

function ensurePrimaryGeoServerLayer(rows) {
  const normalizedRows = rows.map(normalizeLayer).filter(Boolean);
  const primaryLayer = normalizedRows.find((item) => item.key === "dk3213242017");
  if (primaryLayer) {
    primaryLayer.visible = true;
    primaryLayer.defaultVisible = true;
    primaryLayer.name = "GeoServer地块图层";
    primaryLayer.groupName = "GeoServer图层";
    return normalizedRows;
  }

  const fallbackPrimary = normalizeLayer(fallbackVectors.find((item) => item.key === "dk3213242017") || fallbackVectors[0]);
  if (!fallbackPrimary) {
    return normalizedRows;
  }
  fallbackPrimary.visible = true;
  fallbackPrimary.defaultVisible = true;
  return [...normalizedRows, fallbackPrimary];
}

async function loadLayerConfigs() {
  try {
    const { data } = await fetchMapLayers({ enabledOnly: true });
    const rows = ensurePrimaryGeoServerLayer(data.data || []);
    basemapRows.value = rows.filter((item) => item.category === "basemap").sort((a, b) => a.sortOrder - b.sortOrder);
    layerRows.value = rows.filter((item) => item.category === "vector").sort((a, b) => (a.groupName || "").localeCompare(b.groupName || "") || a.sortOrder - b.sortOrder);
  } catch (error) {
    basemapRows.value = fallbackBasemaps.map(normalizeLayer);
    layerRows.value = ensurePrimaryGeoServerLayer(fallbackVectors);
    if (![401, 403].includes(error?.response?.status)) {
      ElMessage.warning(ui.fallbackConfig);
    }
  }

  const defaultBasemap = basemapRows.value.find((item) => item.isDefault) || basemapRows.value[0];
  if (defaultBasemap) {
    activeBasemap.value = defaultBasemap.key;
  }
}

function parseServiceUrl(rawUrl) {
  const resolvedUrl = resolveClientServiceUrl(rawUrl);
  const url = new URL(resolvedUrl, window.location.origin);
  const params = {};
  url.searchParams.forEach((value, key) => {
    params[key.toUpperCase()] = value;
  });
  return {
    baseUrl: `${url.origin}${url.pathname}`,
    params,
  };
}

function resolveClientServiceUrl(rawUrl) {
  if (!rawUrl) {
    return rawUrl;
  }
  const url = new URL(rawUrl, window.location.origin);
  const isGeoServerLocal =
    (url.hostname === "localhost" || url.hostname === "127.0.0.1") &&
    url.port === "8080" &&
    url.pathname.startsWith("/geoserver");

  if (!isGeoServerLocal) {
    return rawUrl;
  }

  return `${window.location.origin}${url.pathname}${url.search}`;
}

function getWmsLayerName(config) {
  const { params } = parseServiceUrl(config.serviceUrl);
  return params.LAYERS || params.LAYER || "";
}

function inferLayerType(config) {
  const layerType = (config.layerType || "").toUpperCase();
  if (layerType === "WMTS") {
    return "WMTS";
  }
  const rawUrl = config.serviceUrl || "";
  if (/\/gwc\/service\/wmts/i.test(rawUrl) || /(?:^|[?&])service=wmts(?:&|$)/i.test(rawUrl) || /(?:^|[?&])request=gettile(?:&|$)/i.test(rawUrl)) {
    return "WMTS";
  }
  return layerType;
}

function buildCapabilitiesUrl(rawUrl, serviceType) {
  const url = new URL(rawUrl, window.location.origin);
  const version = serviceType === "WMTS" ? "1.0.0" : "1.1.1";
  const keysToRemove = new Set([
    "request", "service", "version", "layer", "layers",
    "style", "tilematrixset", "tilematrix", "tilerow", "tilecol",
    "format",
  ]);
  const paramsToDelete = [];
  url.searchParams.forEach((_value, key) => {
    if (keysToRemove.has(key.toLowerCase())) {
      paramsToDelete.push(key);
    }
  });
  paramsToDelete.forEach((key) => url.searchParams.delete(key));
  url.searchParams.set("service", serviceType);
  url.searchParams.set("request", "GetCapabilities");
  url.searchParams.set("version", version);
  return url.toString();
}

function getWmtsLayerConfig(config) {
  const { baseUrl, params } = parseServiceUrl(config.serviceUrl);
  const rawLayer = params.LAYER || params.LAYERS || "";
  const colonIdx = rawLayer.lastIndexOf(":");
  const layer = colonIdx >= 0 ? rawLayer.slice(colonIdx + 1) : rawLayer;
  return {
    baseUrl,
    layer,
    style: params.STYLE ?? "",
    matrixSet: params.TILEMATRIXSET || "",
    format: params.FORMAT || "image/png",
  };
}

const wmtsTileGridCache = new Map();

function findXmlElement(parent, localName) {
  for (const node of parent?.childNodes || []) {
    if (node.nodeType === Node.ELEMENT_NODE && node.localName === localName) return node;
  }
  return null;
}

function findXmlElements(parent, localName) {
  return Array.from(parent?.childNodes || []).filter(
    (node) => node.nodeType === Node.ELEMENT_NODE && node.localName === localName,
  );
}

function parseWmtsTileGridFromXml(xmlText, matrixSetName) {
  const xml = new DOMParser().parseFromString(xmlText, "text/xml");
  if (!xml?.documentElement) {
    console.error("WMTS tilegrid: capability XML parse failed (no documentElement)");
    return null;
  }
  if (xml.querySelector("parsererror")) {
    console.error("WMTS tilegrid: capability XML has parsererror");
    return null;
  }

  const contents = findXmlElement(xml.documentElement, "Contents");
  if (!contents) {
    console.error("WMTS tilegrid: no <Contents> element in capabilities");
    return null;
  }

  const matrixSets = findXmlElements(contents, "TileMatrixSet");
  if (!matrixSets.length) {
    console.error("WMTS tilegrid: no TileMatrixSet elements found, available children:", Array.from(contents.childNodes).filter(n => n.nodeType === 1).map(n => n.localName));
    return null;
  }
  const targetSet = matrixSets.find((ms) => {
    const id = findXmlElement(ms, "Identifier");
    return id?.textContent?.trim() === matrixSetName;
  });
  if (!targetSet) {
    console.error("WMTS tilegrid: TileMatrixSet not found for", matrixSetName, "available:", matrixSets.map(ms => findXmlElement(ms, "Identifier")?.textContent?.trim()).filter(Boolean));
    return null;
  }

  const matrices = findXmlElements(targetSet, "TileMatrix");
  if (!matrices.length) {
    console.error("WMTS tilegrid: no TileMatrix elements in TileMatrixSet");
    return null;
  }

  const matrixIds = [];
  const resolutions = [];
  let origin = null;
  let tileWidth = 256;
  let tileHeight = 256;

  for (const tm of matrices) {
    const idEl = findXmlElement(tm, "Identifier");
    if (!idEl?.textContent) continue;
    matrixIds.push(idEl.textContent.trim());

    if (!origin) {
      const corner = findXmlElement(tm, "TopLeftCorner");
      if (corner?.textContent) {
        const parts = corner.textContent.trim().split(/\s+/).map(Number);
        if (parts.length === 2 && parts.every(Number.isFinite)) {
          origin = [parts[1], parts[0]];
        }
      }
    }

    const sdEl = findXmlElement(tm, "ScaleDenominator");
    const scaleDenom = sdEl ? parseFloat(sdEl.textContent) : 0;
    if (scaleDenom > 0) {
      resolutions.push(scaleDenom * 0.00028 / 111319.9);
    }

    const tw = findXmlElement(tm, "TileWidth");
    const th = findXmlElement(tm, "TileHeight");
    if (tw) tileWidth = parseInt(tw.textContent, 10) || 256;
    if (th) tileHeight = parseInt(th.textContent, 10) || 256;
  }

  if (!origin) {
    console.error("WMTS tilegrid: no origin found (TopLeftCorner missing)");
    return null;
  }
  if (!resolutions.length) {
    console.error("WMTS tilegrid: no resolutions parsed (ScaleDenominator missing)");
    return null;
  }

  return new WMTSGrid({
    origin,
    resolutions,
    matrixIds,
    tileSize: [tileWidth, tileHeight],
  });
}

async function getWmtsTileGrid(serviceUrl, matrixSet) {
  const cacheKey = `${serviceUrl}::${matrixSet}`;
  if (wmtsTileGridCache.has(cacheKey)) {
    return wmtsTileGridCache.get(cacheKey);
  }

  try {
    const capabilityUrl = buildCapabilitiesUrl(serviceUrl, "WMTS");
    console.log("WMTS GetCapabilities:", capabilityUrl);
    const response = await fetch(capabilityUrl);
    if (!response.ok) {
      console.error("WMTS capabilities fetch failed:", response.status, response.statusText);
      return null;
    }
    const text = await response.text();
    const tileGrid = parseWmtsTileGridFromXml(text, matrixSet);
    if (tileGrid) {
      wmtsTileGridCache.set(cacheKey, tileGrid);
      return tileGrid;
    }
  } catch (e) {
    console.error("Failed to fetch WMTS capabilities for tile grid:", e);
  }
  return null;
}

function createBasemapLayer(config) {
  const source =
    config.layerType === "OSM"
      ? new OSM()
      : new XYZ({
          url: config.serviceUrl,
          crossOrigin: "anonymous",
        });
  return new TileLayer({
    source,
    visible: config.key === activeBasemap.value,
  });
}

function createPointStyle(labelText) {
  return new Style({
    image: new Icon({
      src: "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='6' fill='%23ffdd57' stroke='%230f2740' stroke-width='2'/></svg>",
      anchor: [0.5, 0.5],
    }),
    text: new Text({
      text: labelText,
      offsetY: -18,
      padding: [4, 6, 4, 6],
      fill: new Fill({ color: "#ffffff" }),
      backgroundFill: new Fill({ color: "rgba(11, 34, 58, 0.82)" }),
    }),
  });
}

function createWmsLayer(config) {
  const { baseUrl, params } = parseServiceUrl(config.serviceUrl);
  return new TileLayer({
    source: new TileWMS({
      url: baseUrl,
      params: {
        SERVICE: "WMS",
        VERSION: params.VERSION || "1.1.1",
        REQUEST: "GetMap",
        LAYERS: getWmsLayerName(config),
        STYLES: params.STYLES || "",
        FORMAT: params.FORMAT || "image/png",
        TRANSPARENT: "true",
      },
      serverType: "geoserver",
      crossOrigin: "anonymous",
    }),
    minZoom: config.serviceConfigs[0]?.minZoom ?? 0,
    maxZoom: config.serviceConfigs[0]?.maxZoom ?? 19,
    visible: config.visible,
  });
}

async function createWmtsLayer(config) {
  const wmtsConfig = getWmtsLayerConfig(config);
  const matrixSet = wmtsConfig.matrixSet || config.projection || "EPSG:4326";
  const projection = getProjection(matrixSet);

  const tileGrid = await getWmtsTileGrid(config.serviceUrl, matrixSet);
  if (!tileGrid) {
    throw new Error(`无法加载 WMTS 瓦片网格: ${matrixSet}`);
  }
  console.log("WMTS tileGrid loaded:", {
    origin: tileGrid.getOrigin(),
    resolutions: tileGrid.getResolutions().length + " levels",
    matrixIds: tileGrid.getMatrixIds().slice(0, 3).join(", ") + "...",
  });

  return new TileLayer({
    source: new WMTS({
      url: wmtsConfig.baseUrl,
      layer: wmtsConfig.layer,
      style: wmtsConfig.style ?? "",
      matrixSet,
      format: wmtsConfig.format,
      projection: projection || void 0,
      requestEncoding: "KVP",
      tileGrid,
      wrapX: false,
      crossOrigin: "anonymous",
    }),
    minZoom: config.serviceConfigs[0]?.minZoom ?? 0,
    maxZoom: config.serviceConfigs[0]?.maxZoom ?? 19,
    visible: config.visible,
  });
}

function createGeoJsonLayer(config) {
  return new VectorLayer({
    source: new VectorSource({
      url: config.serviceUrl,
      format: new GeoJSON(),
    }),
    visible: config.visible,
  });
}

async function createOperationalLayer(config) {
  const layerType = inferLayerType(config);
  if (layerType === "WMS") {
    return createWmsLayer(config);
  }
  if (layerType === "WMTS") {
    return createWmtsLayer(config);
  }
  if (layerType === "GEOJSON" || layerType === "WFS") {
    return createGeoJsonLayer(config);
  }
  return new VectorLayer({
    source: new VectorSource(),
    visible: config.visible,
  });
}

function buildLayerConfigForService(config, serviceConfig) {
  return {
    ...config,
    layerType: serviceConfig.serviceType,
    serviceUrl: serviceConfig.serviceUrl,
    projection: serviceConfig.projection,
    serviceConfigs: [serviceConfig],
  };
}

async function createOperationalLayersForRow(config) {
  const results = [];
  const typesCreated = new Set();
  for (const sc of config.serviceConfigs) {
    if (!sc.enabled) continue;
    const subConfig = buildLayerConfigForService(config, sc);
    try {
      const layer = await createOperationalLayer(subConfig);
      if (layer) {
        layer.set("serviceType", sc.serviceType);
        layer.set("parentKey", config.key);
        const subKey = `${config.key}_${sc.serviceType.toLowerCase()}_${sc.minZoom}_${sc.maxZoom}`;
        results.push({ key: subKey, layer });
        typesCreated.add(sc.serviceType);
      }
    } catch (e) {
      console.error(`Failed to create ${sc.serviceType} layer for ${config.key}:`, e);
    }
  }
  if (!results.length) {
    throw new Error(`图层"${config.name}"所有服务初始化失败`);
  }
  return results;
}

function getOrCreateQueryMarkerLayer() {
  let layer = layerInstances.get("query_marker");
  if (layer) {
    return layer;
  }
  layer = new VectorLayer({
    source: new VectorSource(),
    style: createPointStyle(ui.clickPoint),
    visible: true,
  });
  layer.set("systemOverlay", true);
  layerInstances.set("query_marker", layer);
  mapRef.value?.addLayer(layer);
  return layer;
}

function updateCurrentCoord(coordinate) {
  const [lon, lat] = toLonLat(coordinate);
  currentCoord.value = `${lon.toFixed(5)}, ${lat.toFixed(5)}`;
}

function clearMeasureInteraction() {
  if (measureDrawInteraction && mapRef.value) {
    mapRef.value.removeInteraction(measureDrawInteraction);
  }
  measureDrawInteraction = null;
}

function clearLabelInteraction() {
  if (labelDrawInteraction && mapRef.value) {
    mapRef.value.removeInteraction(labelDrawInteraction);
  }
  labelDrawInteraction = null;
}

function updateAttrsByEntries(entries) {
  attrs.value = entries;
}

function showMapClickMarker(coordinate) {
  const markerLayer = getOrCreateQueryMarkerLayer();
  const source = markerLayer.getSource();
  source.clear();
  source.addFeature(new Feature({ geometry: new Point(coordinate) }));
}

async function fetchWmsFeatureInfo(coordinate) {
  const view = mapRef.value?.getView();
  if (!view) {
    return false;
  }
  const resolution = view.getResolution();
  const projection = view.getProjection();

  const wmsLayers = [];
  layerInstances.forEach((instance, key) => {
    if (instance.get("serviceType") === "WMS" && instance.getVisible()) {
      wmsLayers.push({ key, instance });
    }
  });

  for (const { instance } of wmsLayers) {
    const source = instance?.getSource?.();
    if (!source?.getFeatureInfoUrl || !resolution) {
      continue;
    }
    const sourceParams = source.getParams?.() || {};
    const layerName = sourceParams.LAYERS || "";
    const url = source.getFeatureInfoUrl(coordinate, resolution, projection, {
      INFO_FORMAT: "application/json",
      FEATURE_COUNT: 10,
      QUERY_LAYERS: layerName,
    });
    if (!url) {
      continue;
    }
    try {
      const response = await fetch(url);
      const data = await response.json();
      const features = data?.features;
      if (!features?.length) {
        continue;
      }
      const parentKey = instance.get("parentKey") || "";
      const parentRow = layerRows.value.find((r) => r.key === parentKey);
      const layerLabel = parentRow?.name || parentKey || "WMS";
      const properties = features[0].properties || {};
      const entries = Object.entries(properties).slice(0, 8).map(([k, v]) => ({
        label: k,
        value: v == null || v === "" ? ui.unknown : String(v),
      }));
      updateAttrsByEntries([{ label: ui.currentObject, value: layerLabel }, { label: "\u56fe\u5c42\u7f16\u7801", value: parentKey }, ...entries]);
      queryMessage.value = `${ui.mapClickHit}${layerLabel}`;
      return true;
    } catch (_error) {
      continue;
    }
  }

  return false;
}

async function fetchWmsLonLatExtent(config) {
  const capabilityUrl = buildCapabilitiesUrl(config.serviceUrl, "WMS");
  const response = await fetch(capabilityUrl);
  const text = await response.text();
  const xml = new DOMParser().parseFromString(text, "text/xml");
  const targetName = getWmsLayerName(config);
  const layers = Array.from(xml.getElementsByTagName("Layer"));
  const targetLayer = layers.find((item) => {
    const nameNode = item.getElementsByTagName("Name")[0];
    return nameNode?.textContent?.trim() === targetName;
  });
  if (!targetLayer) {
    return null;
  }

  const latLon = targetLayer.getElementsByTagName("LatLonBoundingBox")[0];
  if (latLon) {
    const minx = Number(latLon.getAttribute("minx"));
    const miny = Number(latLon.getAttribute("miny"));
    const maxx = Number(latLon.getAttribute("maxx"));
    const maxy = Number(latLon.getAttribute("maxy"));
    if ([minx, miny, maxx, maxy].every(Number.isFinite)) {
      return [minx, miny, maxx, maxy];
    }
  }
  return null;
}

async function fetchWmtsLonLatExtent(config) {
  const capabilityUrl = buildCapabilitiesUrl(config.serviceUrl, "WMTS");
  const response = await fetch(capabilityUrl);
  const text = await response.text();
  const xml = new DOMParser().parseFromString(text, "text/xml");
  const targetName = getWmtsLayerConfig(config).layer;
  const contentsNode = Array.from(xml.documentElement.childNodes).find((node) => node.nodeType === Node.ELEMENT_NODE && node.localName === "Contents");
  const layers = Array.from(contentsNode?.childNodes || []).filter((node) => node.nodeType === Node.ELEMENT_NODE && node.localName === "Layer");
  const targetLayer = layers.find((node) => {
    const identifier = Array.from(node.childNodes).find((child) => child.nodeType === Node.ELEMENT_NODE && child.localName === "Identifier");
    return identifier?.textContent?.trim() === targetName;
  });
  if (!targetLayer) {
    return null;
  }
  const bboxNode = Array.from(targetLayer.childNodes).find((child) => child.nodeType === Node.ELEMENT_NODE && child.localName === "WGS84BoundingBox");
  if (!bboxNode) {
    return null;
  }
  const lowerCorner = Array.from(bboxNode.childNodes).find((child) => child.nodeType === Node.ELEMENT_NODE && child.localName === "LowerCorner");
  const upperCorner = Array.from(bboxNode.childNodes).find((child) => child.nodeType === Node.ELEMENT_NODE && child.localName === "UpperCorner");
  if (!lowerCorner?.textContent || !upperCorner?.textContent) {
    return null;
  }
  const [minx, miny] = lowerCorner.textContent.trim().split(/\s+/).map(Number);
  const [maxx, maxy] = upperCorner.textContent.trim().split(/\s+/).map(Number);
  if ([minx, miny, maxx, maxy].every(Number.isFinite)) {
    return [minx, miny, maxx, maxy];
  }
  return null;
}

async function fitToPrimaryLayer() {
  const primaryLayer =
    layerRows.value.find((item) => item.key === "dk3213242017") ||
    layerRows.value.find((item) => (item.groupName || "").includes("GeoServer"));
  if (!primaryLayer || !mapRef.value) {
    return;
  }

  if (!primaryLayer.visible) {
    primaryLayer.visible = true;
    syncLayerVisibility(primaryLayer);
  }

  try {
    const lonLatExtent =
      inferLayerType(primaryLayer) === "WMTS" ? await fetchWmtsLonLatExtent(primaryLayer) : await fetchWmsLonLatExtent(primaryLayer);
    if (lonLatExtent) {
      const webMercatorExtent = transformExtent(lonLatExtent, "EPSG:4326", "EPSG:3857");
      mapRef.value.getView().fit(webMercatorExtent, {
        padding: [80, 360, 120, 80],
        duration: 600,
        maxZoom: 18,
      });
      return;
    }
  } catch (_error) {
    // ignore capability parse failure
  }

  mapRef.value.getView().animate({
    center: fromLonLat([120.12345, 30.6789]),
    zoom: 15,
    duration: 500,
  });
}

async function buildMap() {
  basemapLayerInstances.clear();
  layerInstances.clear();

  const activeBasemapConfig =
    basemapRows.value.find((item) => item.key === activeBasemap.value) || basemapRows.value[0];
  if (activeBasemapConfig) {
    const layer = createBasemapLayer(activeBasemapConfig);
    basemapLayerInstances.set(activeBasemapConfig.key, layer);
  }
  for (const item of layerRows.value) {
    try {
      const entries = await createOperationalLayersForRow(item);
      for (const entry of entries) {
        layerInstances.set(entry.key, entry.layer);
      }
    } catch (error) {
      console.error("Failed to initialize layer", item.key, error);
      ElMessage.warning(`图层"${item.name}"初始化失败，已跳过。`);
    }
  }

  scaleControl = new ScaleLine({
    target: scaleLineRef.value,
    units: "metric",
  });

  mapRef.value = new OlMap({
    layers: [...basemapLayerInstances.values(), ...layerInstances.values()],
    controls: [scaleControl],
    view: new View({
      center: fromLonLat([120.12345, 30.6789]),
      zoom: 15,
      minZoom: 5,
      maxZoom: 19,
    }),
  });

  mapRef.value.on("pointermove", (event) => {
    updateCurrentCoord(event.coordinate);
  });

  mapRef.value.on("singleclick", async (event) => {
    updateCurrentCoord(event.coordinate);
    showMapClickMarker(event.coordinate);
    const hit = await fetchWmsFeatureInfo(event.coordinate);
    if (!hit && activeTool.value === "query") {
      queryMessage.value = ui.clickNoFeature;
    }
  });
}

function switchBasemap() {
  if (!mapRef.value) return;
  basemapLayerInstances.forEach((layer) => {
    mapRef.value.removeLayer(layer);
  });
  let newLayer = basemapLayerInstances.get(activeBasemap.value);
  if (!newLayer) {
    const config = basemapRows.value.find((item) => item.key === activeBasemap.value);
    if (config) {
      newLayer = createBasemapLayer(config);
      basemapLayerInstances.set(activeBasemap.value, newLayer);
    }
  }
  if (newLayer) {
    mapRef.value.addLayer(newLayer);
  }
}

function syncLayerVisibility(layer) {
  layerInstances.forEach((instance) => {
    if (instance.get("parentKey") === layer.key) {
      instance.setVisible(layer.visible);
    }
  });
}

function toggleTool(key) {
  activeTool.value = activeTool.value === key ? "" : key;
  if (activeTool.value !== "measure") {
    clearMeasureInteraction();
  }
  if (activeTool.value !== "label") {
    clearLabelInteraction();
  }
}

function activateMeasure(mode) {
  measureMode.value = mode;
  clearMeasureInteraction();

  if (!measureLayer) {
    measureLayer = new VectorLayer({
      source: new VectorSource(),
      style: new Style({
        fill: new Fill({ color: "rgba(73, 212, 255, 0.12)" }),
        stroke: new Stroke({ color: "#49d4ff", width: 2 }),
      }),
    });
    mapRef.value.addLayer(measureLayer);
  }

  measureDrawInteraction = new Draw({
    source: measureLayer.getSource(),
    type: mode === "distance" ? "LineString" : "Polygon",
  });
  measureDrawInteraction.on("drawend", (event) => {
    const geometry = event.feature.getGeometry();
    measureResult.value = mode === "distance" ? `${getLength(geometry).toFixed(2)} ${ui.meters}` : `${getArea(geometry).toFixed(2)} ${ui.squareMeters}`;
  });
  mapRef.value.addInteraction(measureDrawInteraction);
}

function clearMeasure() {
  clearMeasureInteraction();
  if (measureLayer) {
    measureLayer.getSource().clear();
  }
  measureResult.value = `0 ${ui.meters}`;
}

function activateLabel() {
  clearLabelInteraction();
  if (!labelLayer) {
    labelLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) =>
        new Style({
          image: new Icon({
            src: "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='6' fill='%2349d4ff' stroke='%23ffffff' stroke-width='2'/></svg>",
            anchor: [0.5, 0.5],
          }),
          text: new Text({
            text: feature.get("label") || "",
            offsetY: -18,
            padding: [4, 6, 4, 6],
            fill: new Fill({ color: "#ffffff" }),
            backgroundFill: new Fill({ color: "rgba(11, 34, 58, 0.82)" }),
          }),
        }),
    });
    mapRef.value.addLayer(labelLayer);
  }

  labelDrawInteraction = new Draw({
    source: labelLayer.getSource(),
    type: "Point",
  });
  labelDrawInteraction.on("drawend", (event) => {
    event.feature.set("label", markText.value.trim() || ui.labelTool);
  });
  mapRef.value.addInteraction(labelDrawInteraction);
}

function clearLabels() {
  clearLabelInteraction();
  if (labelLayer) {
    labelLayer.getSource().clear();
  }
}

async function applyRequestResult(item, silent = false) {
  await fitToPrimaryLayer();
  updateAttrsByEntries([
    { label: ui.currentObject, value: ui.objectRequest },
    { label: ui.requestType, value: item.requestType || ui.unknown },
    { label: ui.requestTitle, value: item.requestTitle || ui.unknown },
    { label: ui.issuer, value: item.issuerName || ui.unknown },
    { label: ui.contractor, value: item.contractorName || ui.unknown },
    { label: ui.serialNo, value: item.serialNo || ui.unknown },
    { label: ui.status, value: item.status || ui.unknown },
    { label: ui.currentStep, value: item.currentStep || ui.unknown },
  ]);
  if (!silent) {
    queryMessage.value = `${ui.requestLinked}${item.serialNo}`;
  }
}

async function applyIssuerResult(item) {
  await fitToPrimaryLayer();
  updateAttrsByEntries([
    { label: ui.currentObject, value: ui.objectIssuer },
    { label: ui.issuerName, value: item.name || ui.unknown },
    { label: ui.issuerCode, value: item.code || ui.unknown },
    { label: ui.ownerName, value: item.ownerName || ui.unknown },
    { label: ui.idNo, value: item.ownerIdNo || ui.unknown },
    { label: ui.mobile, value: item.mobile || ui.unknown },
    { label: ui.address, value: item.address || ui.unknown },
    { label: ui.coord, value: currentCoord.value },
  ]);
  queryMessage.value = `${ui.issuerLinked}${item.name}`;
}

async function applyContractorResult(item) {
  await fitToPrimaryLayer();
  updateAttrsByEntries([
    { label: ui.currentObject, value: ui.objectContractor },
    { label: ui.contractorName, value: item.name || ui.unknown },
    { label: ui.contractorCode, value: item.code || ui.unknown },
    { label: ui.idNo, value: item.idNo || ui.unknown },
    { label: ui.mobile, value: item.mobile || ui.unknown },
    { label: ui.address, value: item.address || ui.unknown },
    { label: ui.contractorType, value: item.type || ui.unknown },
    { label: ui.coord, value: currentCoord.value },
  ]);
  queryMessage.value = `${ui.contractorLinked}${item.name}`;
}

async function performQuery() {
  const keyword = queryKeyword.value.trim();
  if (!keyword) {
    queryMessage.value = ui.emptyKeyword;
    searchResult.value = { requests: [], issuers: [], contractors: [] };
    return;
  }

  try {
    const { data } = await searchGisBusiness({ keyword, limit: 6 });
    searchResult.value = data.data || { requests: [], issuers: [], contractors: [] };
  } catch (_error) {
    searchResult.value = { requests: [], issuers: [], contractors: [] };
  }

  if (searchResult.value.requests.length) {
    await applyRequestResult(searchResult.value.requests[0], true);
    queryMessage.value = `${ui.requestMatched}${searchResult.value.requests.length}${ui.requestMatchedSuffix}`;
  } else if (searchResult.value.issuers.length) {
    await applyIssuerResult(searchResult.value.issuers[0]);
  } else if (searchResult.value.contractors.length) {
    await applyContractorResult(searchResult.value.contractors[0]);
  } else {
    queryMessage.value = ui.notFound;
    await fitToPrimaryLayer();
  }
}

function clearSelection() {
  const markerLayer = layerInstances.get("query_marker");
  markerLayer?.getSource?.().clear();
  queryMessage.value = "";
  searchResult.value = { requests: [], issuers: [], contractors: [] };
}

async function resetView() {
  await fitToPrimaryLayer();
}

onMounted(async () => {
  await loadLayerConfigs();
  await buildMap();
  await fitToPrimaryLayer();
  mapRef.value.setTarget(mapRootRef.value);
});

onBeforeUnmount(() => {
  clearMeasureInteraction();
  clearLabelInteraction();
  if (mapRef.value) {
    mapRef.value.setTarget(undefined);
  }
});
</script>
