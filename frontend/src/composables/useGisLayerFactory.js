/**
 * GIS layer factory composable �?extracts heavy OpenLayers layer creation logic.
 */
import GeoJSON from "ol/format/GeoJSON";
import ImageLayer from "ol/layer/Image";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import WMTSGrid from "ol/tilegrid/WMTS";
import { get as getProjection } from "ol/proj";
import { OSM, Vector as VectorSource, XYZ } from "ol/source";
import ImageWMS from "ol/source/ImageWMS";
import WMTS from "ol/source/WMTS";

export function normalizeLayer(item) {
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
      serviceType: String(service.serviceType ?? service.layerType ?? item.layerType ?? item.layer_type ?? "WMS").toUpperCase(),
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

export function ensurePrimaryGeoServerLayer(rows) {
  const normalizedRows = rows.map(normalizeLayer).filter(Boolean);
  const primaryLayer = normalizedRows.find((item) => item.key === "survey_dk_result");
  if (primaryLayer) {
    primaryLayer.visible = true;
    primaryLayer.defaultVisible = true;
    primaryLayer.name = "\u627f\u5305\u5730\u5757";
    primaryLayer.groupName = "GeoServer\u56fe\u5c42";
    return normalizedRows;
  }

  const fallbackPrimary = normalizeLayer(fallbackVectors.find((item) => item.key === "survey_dk_result") || fallbackVectors[0]);
  if (!fallbackPrimary) {
    return normalizedRows;
  }
  fallbackPrimary.visible = true;
  fallbackPrimary.defaultVisible = true;
  fallbackPrimary.name = "\u627f\u5305\u5730\u5757";
  fallbackPrimary.groupName = "GeoServer\u56fe\u5c42";
  return [...normalizedRows, fallbackPrimary];
}


export function parseServiceUrl(rawUrl) {
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

export function resolveClientServiceUrl(rawUrl) {
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

export function getWmsLayerName(config) {
  const { params } = parseServiceUrl(config.serviceUrl);
  return params.LAYERS || params.LAYER || "";
}

export function inferLayerType(config) {
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

export function buildCapabilitiesUrl(rawUrl, serviceType) {
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


export function getWmtsLayerConfig(config) {
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

export function findXmlElement(parent, localName) {
  for (const node of parent?.childNodes || []) {
    if (node.nodeType === Node.ELEMENT_NODE && node.localName === localName) return node;
  }
  return null;
}

export function findXmlElements(parent, localName) {
  return Array.from(parent?.childNodes || []).filter(
    (node) => node.nodeType === Node.ELEMENT_NODE && node.localName === localName,
  );
}

export function parseWmtsTileGridFromXml(xmlText, matrixSetName) {
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

export async function getWmtsTileGrid(serviceUrl, matrixSet) {
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


export function createBasemapLayer(config) {
  const source =
    config.layerType === "OSM"
      ? new OSM()
      : new XYZ({
          url: config.serviceUrl,
          crossOrigin: "anonymous",
        });
  return new TileLayer({
    source,
    visible: true,
  });
}


export function createWmsLayer(config) {
  const { baseUrl, params } = parseServiceUrl(config.serviceUrl);
  return new ImageLayer({
    source: new ImageWMS({
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

export async function createWmtsLayer(config) {
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

export function createGeoJsonLayer(config) {
  return new VectorLayer({
    source: new VectorSource({
      url: config.serviceUrl,
      format: new GeoJSON(),
    }),
    visible: config.visible,
  });
}

export async function createOperationalLayer(config) {
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


export function buildLayerConfigForService(config, serviceConfig) {
  return {
    ...config,
    layerType: serviceConfig.serviceType,
    serviceUrl: serviceConfig.serviceUrl,
    projection: serviceConfig.projection,
    serviceConfigs: [serviceConfig],
  };
}

export async function createOperationalLayersForRow(config) {
  const results = [];
  const typesCreated = new Set();
  for (const sc of config.serviceConfigs) {
    if (!sc.enabled) continue;
    const subConfig = buildLayerConfigForService(config, sc);
    try {
      const layer = await createOperationalLayer(subConfig);
      if (layer) {
        layer.set("serviceType", String(sc.serviceType || "").toUpperCase());
        layer.set("parentKey", config.key);
        layer.set("serviceConfig", subConfig);
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


export async function fetchWmsLonLatExtent(config) {
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

export async function fetchWmtsLonLatExtent(config) {
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

