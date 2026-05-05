export const basemapConfigs = [
  {
    id: "fallback-image",
    key: "image",
    name: "\u9065\u611f\u5e95\u56fe",
    category: "basemap",
    groupName: "\u57fa\u7840\u5e95\u56fe",
    defaultVisible: true,
    isDefault: true,
    sortOrder: 10,
    enabled: true,
    serviceConfigs: [
      {
        serviceType: "XYZ",
        serviceUrl: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        projection: "EPSG:3857",
        minZoom: 0,
        maxZoom: 19,
        enabled: true,
      },
    ],
  },
  {
    id: "fallback-vector",
    key: "vector",
    name: "\u7535\u5b50\u5730\u56fe",
    category: "basemap",
    groupName: "\u57fa\u7840\u5e95\u56fe",
    defaultVisible: false,
    isDefault: false,
    sortOrder: 20,
    enabled: true,
    serviceConfigs: [
      {
        serviceType: "OSM",
        serviceUrl: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        projection: "EPSG:3857",
        minZoom: 0,
        maxZoom: 19,
        enabled: true,
      },
    ],
  },
  {
    id: "fallback-terrain",
    key: "terrain",
    name: "\u5730\u5f62\u56fe",
    category: "basemap",
    groupName: "\u57fa\u7840\u5e95\u56fe",
    defaultVisible: false,
    isDefault: false,
    sortOrder: 30,
    enabled: true,
    serviceConfigs: [
      {
        serviceType: "XYZ",
        serviceUrl: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        projection: "EPSG:3857",
        minZoom: 0,
        maxZoom: 19,
        enabled: true,
      },
    ],
  },
];

export const vectorLayerConfigs = [
  {
    id: "fallback-geoserver-contract-land",
    key: "dk3213242017",
    name: "GeoServer\u5730\u5757\u56fe\u5c42",
    category: "vector",
    groupName: "GeoServer\u56fe\u5c42",
    defaultVisible: true,
    isDefault: false,
    sortOrder: 5,
    enabled: true,
    serviceConfigs: [
      {
        serviceType: "WMTS",
        serviceUrl:
          "/geoserver/erlunyanbao/gwc/service/wmts?layer=erlunyanbao:DK3213242017&style=&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png",
        projection: "EPSG:4326",
        minZoom: 0,
        maxZoom: 15,
        enabled: true,
      },
      {
        serviceType: "WMS",
        serviceUrl:
          "/geoserver/erlunyanbao/wms?service=WMS&version=1.1.1&request=GetMap&layers=erlunyanbao:DK3213242017&styles=&format=image/png&transparent=true",
        projection: "EPSG:4326",
        minZoom: 16,
        maxZoom: 19,
        enabled: true,
      },
    ],
  },
];
