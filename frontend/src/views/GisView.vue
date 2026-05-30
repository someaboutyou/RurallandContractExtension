<template>
  <section class="gis-page">
    <section class="gis-map-shell">
      <div class="gis-map-surface">
        <div ref="mapRootRef" class="gis-ol-map"></div>
        <div class="gis-map-vignette"></div>

        <div class="gis-scene-title">{{ ui.title }}</div>

        <div class="gis-search-dock">
          <div class="gis-search-bar">
            <select v-model="searchType" class="gis-search-select" :aria-label="ui.searchType">
              <option v-for="option in searchTypeOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
            <input
              v-model="queryKeyword"
              class="gis-search-input"
              type="search"
              :placeholder="ui.searchPlaceholder"
              @keyup.enter="performQuery"
            />
            <button type="button" class="gis-search-button" :disabled="searchLoading" @click="performQuery">
              <span class="gis-search-button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="11" cy="11" r="5.5" />
                  <path d="m16 16 4.2 4.2" />
                </svg>
              </span>
              <span>{{ searchLoading ? ui.searching : ui.locateQuery }}</span>
            </button>
          </div>

          <Transition name="gis-search-panel">
            <section v-if="searchPanelVisible" class="gis-search-panel">
              <div class="gis-search-panel-head">
                <div class="gis-search-counts">
                  <div>
                    <span>{{ activeSearchCountLabel }}</span>
                    <strong>{{ activeSearchCount }}</strong>
                    <span>{{ ui.countUnit }}</span>
                  </div>
                  <div>
                    <span>{{ ui.parcelAmount }}</span>
                    <strong>{{ searchParcelCount }}</strong>
                    <span>{{ ui.countUnit }}</span>
                  </div>
                </div>
                <button type="button" class="gis-search-close" :aria-label="ui.closeSearchPanel" @click="searchPanelVisible = false">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round">
                    <path d="M6 6l12 12" />
                    <path d="M18 6 6 18" />
                  </svg>
                </button>
              </div>

              <div class="gis-search-tabs">
                <button
                  v-for="tab in visibleSearchTabs"
                  :key="tab.value"
                  type="button"
                  class="gis-search-tab"
                  :class="{ 'is-active': activeSearchTab === tab.value }"
                  @click="activeSearchTab = tab.value"
                >
                  {{ tab.label }}
                </button>
              </div>

              <div class="gis-search-message" v-if="queryMessage">{{ queryMessage }}</div>
              <div class="gis-search-list" v-if="activeSearchItems.length">
                <button
                  v-for="item in activeSearchItems"
                  :key="`${item.resultType}-${item.code}`"
                  type="button"
                  class="gis-search-result"
                  @click="applySearchResult(item)"
                >
                  <div class="gis-search-result-main">
                    <div class="gis-search-result-title">{{ item.name || ui.unknown }}</div>
                    <div class="gis-search-result-lines">
                      <span>{{ resultCodeLabel(item) }}：{{ item.code || ui.unknown }}</span>
                      <span>{{ resultSubLabel(item) }}：{{ resultSubValue(item) }}</span>
                    </div>
                  </div>
                  <div class="gis-search-result-actions">
                    <span :title="ui.parcelAmount">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M4 6h12l4 4v8H4z" />
                        <path d="M16 6v4h4" />
                      </svg>
                      {{ item.parcelCount || 0 }}
                    </span>
                    <span :title="ui.locateQuery">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 21s6-5.2 6-10a6 6 0 1 0-12 0c0 4.8 6 10 6 10Z" />
                        <circle cx="12" cy="11" r="2.2" />
                      </svg>
                    </span>
                  </div>
                </button>
              </div>
              <div v-else class="gis-search-empty">{{ ui.notFound }}</div>
            </section>
          </Transition>
        </div>

        <div v-show="selectedParcel" ref="parcelPopupRef" class="gis-parcel-popup">
          <div class="gis-parcel-popup-title">{{ selectedParcel?.dkmc || selectedParcel?.dkbm || ui.objectParcel }}</div>
          <div class="gis-parcel-popup-grid">
            <span>{{ ui.parcelCode }}</span>
            <strong>{{ selectedParcel?.dkbm || ui.unknown }}</strong>
            <span>{{ ui.contractor }}</span>
            <strong>{{ selectedParcel?.cbfmc || ui.unknown }}</strong>
            <span>{{ ui.issuer }}</span>
            <strong>{{ selectedParcel?.fbfmc || ui.unknown }}</strong>
            <span>{{ ui.area }}</span>
            <strong>{{ selectedParcel?.htmj || selectedParcel?.scmj || ui.unknown }}</strong>
          </div>
        </div>

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

        <Transition name="gis-property-panel">
          <aside v-if="propertyPanelVisible" :key="propertyPanelKey" class="gis-property-panel" :style="propertyPanelDragStyle">
            <div class="gis-property-head" @pointerdown="startPropertyPanelDrag">
              <div>
                <div class="gis-property-title">{{ selectedParcel ? "承包方卡片" : ui.attrTitle }}</div>
                <div v-if="selectedParcel" class="gis-property-subtitle">{{ selectedParcel.cbfmc || selectedParcel.dkbm || ui.unknown }}</div>
              </div>
              <button type="button" class="gis-property-close" :aria-label="ui.clearSelection" @pointerdown.stop @click.stop="clearSelection">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round">
                  <path d="M6 6l12 12" />
                  <path d="M18 6 6 18" />
                </svg>
              </button>
            </div>

            <template v-if="selectedParcel">
              <div class="gis-card-tabs">
                <button
                  v-for="tab in parcelTabs"
                  :key="tab.value"
                  type="button"
                  class="gis-card-tab"
                  :class="{ 'is-active': activeParcelTab === tab.value }"
                  @click="activeParcelTab = tab.value"
                >
                  {{ tab.label }}
                </button>
              </div>

              <div v-if="activeParcelTab === 'contractor'" class="gis-card-pane">
                <div class="gis-info-grid">
                  <div v-for="item in contractorInfoRows" :key="item.label" class="gis-info-cell">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>
                <div class="gis-table-title">家庭成员</div>
                <div class="gis-mini-table">
                  <div class="gis-mini-table-row gis-mini-table-head">
                    <span>序号</span>
                    <span>成员姓名</span>
                    <span>证件类型</span>
                    <span>证件号码</span>
                    <span>与户主关系</span>
                    <span>是否共有人</span>
                  </div>
                  <div v-for="(member, index) in selectedParcel.familyMembers || []" :key="`${member.idNo}-${index}`" class="gis-mini-table-row">
                    <span>{{ index + 1 }}</span>
                    <span>{{ member.name || ui.unknown }}</span>
                    <span>{{ dictDisplay(idDocTypeLabel, member.idType) }}</span>
                    <span>{{ member.idNo || ui.unknown }}</span>
                    <span>{{ dictDisplay(relationLabel, member.relationToHead) }}</span>
                    <span>{{ booleanDisplay(member.isCoOwner) }}</span>
                  </div>
                  <div v-if="!selectedParcel.familyMembers?.length" class="gis-mini-empty">暂无家庭成员数据</div>
                </div>
              </div>

              <div v-else-if="activeParcelTab === 'issuer'" class="gis-card-pane">
                <div class="gis-info-grid">
                  <div v-for="item in issuerInfoRows" :key="item.label" class="gis-info-cell">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>
              </div>

              <div v-else-if="activeParcelTab === 'parcel'" class="gis-card-pane">
                <div class="gis-info-grid">
                  <div v-for="item in parcelInfoRows" :key="item.label" class="gis-info-cell">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>
              </div>

              <div v-else class="gis-card-pane">
                <div class="gis-info-grid">
                  <div v-for="item in contractInfoRows" :key="item.label" class="gis-info-cell">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>
              </div>
            </template>

            <template v-else>
              <div class="gis-attr-card" v-for="item in attrs" :key="item.label">
                <div class="gis-attr-card-label">{{ item.label }}</div>
                <div class="gis-attr-card-value">{{ item.value }}</div>
              </div>
            </template>
          </aside>
        </Transition>

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

import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from "vue";
import { ElMessage } from "element-plus";
import Feature from "ol/Feature";
import GeoJSON from "ol/format/GeoJSON";
import OlMap from "ol/Map";
import View from "ol/View";
import { ScaleLine } from "ol/control";
import { Draw } from "ol/interaction";
import ImageLayer from "ol/layer/Image";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import Overlay from "ol/Overlay";
import { getCenter } from "ol/extent";
import WMTSGrid from "ol/tilegrid/WMTS";
import { fromLonLat, get as getProjection, toLonLat, transformExtent } from "ol/proj";
import { OSM, Vector as VectorSource, XYZ } from "ol/source";
import ImageWMS from "ol/source/ImageWMS";
import WMTS from "ol/source/WMTS";
import { Fill, Icon, Stroke, Style, Text } from "ol/style";
import MultiPolygon from "ol/geom/MultiPolygon";
import Point from "ol/geom/Point";
import Polygon from "ol/geom/Polygon";
import { getArea, getLength } from "ol/sphere";

import { fetchGisParcel, searchGisBusiness } from "../api/gis";
import { useDictionary } from "../composables/useDictionary";
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
  searchPlaceholder: "\u8bf7\u8f93\u5165\u627f\u5305\u65b9\u6216\u53d1\u5305\u65b9\u540d\u79f0",
  searchType: "\u641c\u7d22\u7c7b\u578b",
  searchAll: "\u627f\u5305\u65b9 / \u53d1\u5305\u65b9",
  searching: "\u67e5\u8be2\u4e2d",
  closeSearchPanel: "\u5173\u95ed\u641c\u7d22\u7ed3\u679c",
  countUnit: "\u4e2a",
  contractorAmount: "\u627f\u5305\u65b9\u6570\u91cf\uff1a",
  issuerAmount: "\u53d1\u5305\u65b9\u6570\u91cf\uff1a",
  parcelAmount: "\u5730\u5757\u6570\u91cf\uff1a",
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
  objectParcel: "\u627f\u5305\u5730\u5757",
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
  parcelClickHit: "\u5df2\u547d\u4e2d\u627f\u5305\u5730\u5757 ",
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

// Dictionary label resolvers (NY/T 2539-2016 Appendix C)
const { labelOf: contractorTypeLabel } = useDictionary("nyt2539_c16_contractor_type");
const { labelOf: idDocTypeLabel } = useDictionary("nyt2539_c15_id_document_type");
const { labelOf: yesNoLabel } = useDictionary("nyt2539_c19_yes_no");
const { labelOf: parcelCategoryLabel } = useDictionary("nyt2539_c07_parcel_category");
const { labelOf: landGradeLabel } = useDictionary("nyt2539_c08_land_grade");
const { labelOf: landUseLabel } = useDictionary("nyt2539_c09_land_use");
const { labelOf: acquireMethodLabel } = useDictionary("nyt2539_c10_right_acquire_method");
const { labelOf: relationLabel } = useDictionary("nyt2539_c20_relation_to_head");

const surveyStatusMap = {
  not_surveyed: "未调查",
  not_started: "未调查",
  surveyed: "已调查",
  changed: "有变化",
  unchanged: "无变化",
  confirmed: "已确认",
  skipped: "已跳过",
};

const resultStatusMap = {
  normal: "正常",
  added: "新增",
  removed: "已移除",
  extinct: "整户消亡",
  cancelled: "已注销",
  deregistered: "已注销",
  merged: "已合并",
  deceased: "死亡",
  urbanized: "转为城镇居民",
  little_or_no_land: "少地或无地",
};

const changeTypeMap = {
  none: "无变化",
  info_change: "信息变更",
  change_head: "户主变更",
  member_maintain: "成员维护",
  deregister: "注销承包方",
  add_parcel: "新增地块",
  split_parcel: "地块分割",
  swap_parcels: "地块互换",
  remove_parcel: "移除地块",
  split_household: "分户",
  merge_household: "并户",
  household_extinct: "整户消亡户",
  household_urbanized: "整户转为城镇居民",
  little_or_no_land: "少地或无地户",
};

const landUseTypeMap = {
  "011": "水田",
  "012": "水浇地",
  "013": "旱地",
  "021": "果园",
  "022": "茶园",
  "023": "其他园地",
  "031": "有林地",
  "032": "灌木林地",
  "033": "其他林地",
  "041": "天然牧草地",
  "042": "人工牧草地",
  "111": "设施农用地",
  "114": "坑塘水面",
};


const mapRootRef = ref(null);
const scaleLineRef = ref(null);
const parcelPopupRef = ref(null);
const mapRef = shallowRef(null);

const activeTool = ref("layers");
const activeBasemap = ref("image");
const collapseLayerPanel = ref(true);
const measureMode = ref("distance");
const measureResult = ref(`0 ${ui.meters}`);
const queryKeyword = ref("");
const queryMessage = ref("");
const searchType = ref("all");
const searchLoading = ref(false);
const searchPanelVisible = ref(false);
const activeSearchTab = ref("contractors");
const currentCoord = ref(ui.defaultCoord);
const markText = ref("");

const basemapRows = ref([]);
const layerRows = ref([]);
const searchResult = ref({ requests: [], issuers: [], contractors: [] });
const selectedParcel = ref(null);
const activeParcelTab = ref("contractor");
const propertyPanelPosition = ref(null);
const propertyPanelVisible = ref(false);
const propertyPanelKey = ref(0);
const attrs = ref([]);

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

const visibleSearchTabs = computed(() =>
  searchTypeOptions
    .filter((option) => option.value !== "all")
    .filter((option) => searchType.value === "all" || option.value === searchType.value),
);

const activeSearchItems = computed(() => searchResult.value[activeSearchTab.value] || []);

const activeSearchCountLabel = computed(() => (activeSearchTab.value === "issuers" ? ui.issuerAmount : ui.contractorAmount));

const activeSearchCount = computed(() => activeSearchItems.value.length);

const searchParcelCount = computed(() =>
  activeSearchItems.value.reduce((total, item) => total + Number(item.parcelCount || 0), 0),
);

const propertyPanelDragStyle = computed(() => {
  if (!propertyPanelPosition.value) {
    return {};
  }
  return {
    left: `${propertyPanelPosition.value.x}px`,
    top: `${propertyPanelPosition.value.y}px`,
    right: "auto",
    bottom: "auto",
  };
});

const parcelTabs = [
  { label: "发包方", value: "issuer" },
  { label: "承包方", value: "contractor" },
  { label: "承包地块", value: "parcel" },
  { label: "承包合同", value: "contract" },
];

function displayValue(value) {
  return value === undefined || value === null || value === "" ? ui.unknown : value;
}

function dictDisplay(labelOf, value) {
  return displayValue(labelOf(value, value));
}

function mapDisplay(map, value) {
  return displayValue(map[value] || value);
}

function booleanDisplay(value) {
  if (value === true) return "是";
  if (value === false) return "否";
  return dictDisplay(yesNoLabel, value);
}

function withAreaUnit(value) {
  return value === undefined || value === null || value === "" ? ui.unknown : `${value} 亩`;
}

const contractorInfoRows = computed(() => {
  const parcel = selectedParcel.value || {};
  return [
    { label: "承包方编码", value: displayValue(parcel.cbfbm) },
    { label: "承包方类型", value: dictDisplay(contractorTypeLabel, parcel.cbflx) },
    { label: "承包方名称", value: displayValue(parcel.cbfmc) },
    { label: "证件类型", value: dictDisplay(idDocTypeLabel, parcel.cbfzjlx) },
    { label: "证件号码", value: displayValue(parcel.cbfzjhm) },
    { label: "承包方地址", value: displayValue(parcel.cbfdz) },
    { label: "邮政编码", value: displayValue(parcel.cbfyzbm) },
    { label: "联系电话", value: displayValue(parcel.cbflxdh) },
    { label: "家庭成员数", value: displayValue(parcel.cbfcysl) },
    { label: "所属区域编码", value: displayValue(parcel.cbfGroupRegionCode) },
    { label: "所属区域名称", value: displayValue(parcel.cbfGroupRegionName) },
    { label: "调查日期", value: displayValue(parcel.cbfdcrq) },
    { label: "调查员", value: displayValue(parcel.cbfdcy) },
    { label: "调查记事", value: displayValue(parcel.cbfdcjs) },
    { label: "公示记事", value: displayValue(parcel.gsjs) },
    { label: "公示记事人", value: displayValue(parcel.gsjsr) },
    { label: "公示审核日期", value: displayValue(parcel.gsshrq) },
    { label: "公示审核人", value: displayValue(parcel.gsshr) },
    { label: "调查状态", value: mapDisplay(surveyStatusMap, parcel.cbfSurveyStatus) },
    { label: "成果状态", value: mapDisplay(resultStatusMap, parcel.cbfResultStatus) },
    { label: "是否变更", value: booleanDisplay(parcel.cbfIsChanged) },
    { label: "变更类型", value: mapDisplay(changeTypeMap, parcel.cbfChangeType) },
    { label: "变更原因", value: displayValue(parcel.cbfChangeReason) },
    { label: "政策依据", value: displayValue(parcel.cbfPolicyBasis) },
    { label: "证据摘要", value: displayValue(parcel.cbfEvidenceSummary) },
    { label: "调查处理人", value: displayValue(parcel.cbfInvestigatorName) },
    { label: "调查处理日期", value: displayValue(parcel.cbfInvestigatedAt) },
    { label: "复核人", value: displayValue(parcel.cbfReviewerName) },
    { label: "复核日期", value: displayValue(parcel.cbfReviewedAt) },
    { label: "确认日期", value: displayValue(parcel.cbfConfirmedAt) },
    { label: "备注", value: displayValue(parcel.cbfRemark) },
  ];
});

const issuerInfoRows = computed(() => {
  const parcel = selectedParcel.value || {};
  return [
    { label: "发包方编码", value: displayValue(parcel.fbfbm) },
    { label: "发包方名称", value: displayValue(parcel.fbfmc) },
    { label: "负责人姓名", value: displayValue(parcel.fbffzrxm) },
    { label: "负责人证件类型", value: dictDisplay(idDocTypeLabel, parcel.fbffzrzjlx) },
    { label: "负责人证件号码", value: displayValue(parcel.fbffzrzjhm) },
    { label: "联系电话", value: displayValue(parcel.fbflxdh) },
    { label: "发包方地址", value: displayValue(parcel.fbfdz) },
    { label: "邮政编码", value: displayValue(parcel.fbfyzbm) },
    { label: "发包方调查员", value: displayValue(parcel.fbfdcy) },
    { label: "发包方调查日期", value: displayValue(parcel.fbfdcrq) },
    { label: "发包方调查记事", value: displayValue(parcel.fbfdcjs) },
    { label: "调查状态", value: mapDisplay(surveyStatusMap, parcel.fbfSurveyStatus) },
    { label: "成果状态", value: mapDisplay(resultStatusMap, parcel.fbfResultStatus) },
    { label: "是否变更", value: booleanDisplay(parcel.fbfIsChanged) },
    { label: "变更类型", value: mapDisplay(changeTypeMap, parcel.fbfChangeType) },
    { label: "变更原因", value: displayValue(parcel.fbfChangeReason) },
    { label: "区域编码", value: displayValue(parcel.fbfRegionCode) },
    { label: "租户编码", value: displayValue(parcel.fbfTenantCode) },
  ];
});

const parcelInfoRows = computed(() => {
  const parcel = selectedParcel.value || {};
  return [
    { label: "地块编码", value: displayValue(parcel.dkbm) },
    { label: "地块名称", value: displayValue(parcel.dkmc) },
    { label: "地块类别", value: dictDisplay(parcelCategoryLabel, parcel.dklb) },
    { label: "土地利用类型", value: mapDisplay(landUseTypeMap, parcel.tdlylx) },
    { label: "地力等级", value: dictDisplay(landGradeLabel, parcel.dldj) },
    { label: "土地用途", value: dictDisplay(landUseLabel, parcel.tdyt) },
    { label: "是否基本农田", value: booleanDisplay(parcel.sfjbnt) },
    { label: "合同面积", value: withAreaUnit(parcel.htmj) },
    { label: "实测面积", value: withAreaUnit(parcel.scmj) },
    { label: "东至", value: displayValue(parcel.dkdz) },
    { label: "西至", value: displayValue(parcel.dkxz) },
    { label: "南至", value: displayValue(parcel.dknz) },
    { label: "北至", value: displayValue(parcel.dkbz) },
    { label: "备注", value: displayValue(parcel.dkbzxx) },
  ];
});

const contractInfoRows = computed(() => {
  const parcel = selectedParcel.value || {};
  const contract = parcel.contract || {};
  return [
    { label: "承包合同编码", value: displayValue(contract.cbhtbm || parcel.cbhtbm) },
    { label: "原承包合同编码", value: displayValue(contract.ycbhtbm) },
    { label: "承包方式", value: dictDisplay(acquireMethodLabel, contract.cbfs || parcel.cbjyqqdfs) },
    { label: "承包期限起", value: displayValue(contract.cbqxq) },
    { label: "承包期限止", value: displayValue(contract.cbqxz) },
    { label: "签订时间", value: displayValue(contract.qdsj) },
    { label: "承包地块数", value: displayValue(contract.cbdkzs) },
    { label: "合同总面积", value: withAreaUnit(contract.htzmj) },
    { label: "原合同总面积", value: withAreaUnit(contract.yhtzmj || parcel.yhtmj) },
    { label: "合同总面积(平方米)", value: displayValue(contract.htzmjm || parcel.htmjm) },
    { label: "权证编码", value: displayValue(parcel.cbjyqzbm) },
    { label: "是否确权确股", value: booleanDisplay(parcel.sfqqqg) },
  ];
});

const layerInstances = new globalThis.Map();
const basemapLayerInstances = new globalThis.Map();

const basemapThemeMap = {
  image: { topbarBg: "rgba(229, 237, 221, 0.96)", topbarAccent: "#5f7f44", topbarText: "#243325" },
  vector: { topbarBg: "rgba(226, 237, 246, 0.96)", topbarAccent: "#2f70a2", topbarText: "#213447" },
  terrain: { topbarBg: "rgba(237, 231, 214, 0.96)", topbarAccent: "#786f45", topbarText: "#393525" },
};

const searchTypeOptions = [
  { label: ui.searchAll, value: "all" },
  { label: ui.contractorSection, value: "contractors" },
  { label: ui.issuerSection, value: "issuers" },
];

let scaleControl = null;
let measureDrawInteraction = null;
let labelDrawInteraction = null;
let measureLayer = null;
let labelLayer = null;
let parcelHighlightLayer = null;
let parcelPopupOverlay = null;
let propertyPanelDragState = null;

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

function ensurePrimaryGeoServerLayer(rows) {
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

async function loadLayerConfigs() {
  try {
    const { data } = await fetchMapLayers({ enabledOnly: true });
    const rows = ensurePrimaryGeoServerLayer(data.data || []);
    basemapRows.value = rows.filter((item) => item.category === "basemap").sort((a, b) => a.sortOrder - b.sortOrder);
    layerRows.value = rows.filter((item) => item.category === "vector").sort((a, b) => (a.groupName || "").localeCompare(b.groupName || "") || a.sortOrder - b.sortOrder);

    // If the API returned successfully but returned zero basemap layers
    // (e.g. DB has only user-created vector layers), inject the local
    // config basemaps so the map still gets a tile background.
    if (!basemapRows.value.length) {
      basemapRows.value = fallbackBasemaps.map(normalizeLayer);
    }
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
    emitBasemapTheme(defaultBasemap.key);
  }
}

function emitBasemapTheme(key = activeBasemap.value) {
  window.dispatchEvent(
    new CustomEvent("app-theme-change", {
      detail: basemapThemeMap[key] || basemapThemeMap.image,
    }),
  );
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

function createParcelHighlightStyle() {
  return new Style({
    fill: new Fill({ color: "rgba(255, 64, 129, 0.26)" }),
    stroke: new Stroke({ color: "#ff4081", width: 5 }),
  });
}

function createWmsLayer(config) {
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

function getOrCreateParcelHighlightLayer() {
  if (parcelHighlightLayer) {
    return parcelHighlightLayer;
  }
  parcelHighlightLayer = new VectorLayer({
    source: new VectorSource(),
    style: createParcelHighlightStyle(),
    visible: true,
  });
  parcelHighlightLayer.set("systemOverlay", true);
  parcelHighlightLayer.setZIndex(1000);
  mapRef.value?.addLayer(parcelHighlightLayer);
  return parcelHighlightLayer;
}

function getFeatureProperty(properties, candidates) {
  const entries = Object.entries(properties || {});
  for (const candidate of candidates) {
    const found = entries.find(([key]) => key.toLowerCase() === candidate.toLowerCase());
    if (found?.[1] != null && found[1] !== "") {
      return String(found[1]).trim();
    }
  }
  return "";
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

function clampNumber(value, min, max) {
  if (max < min) {
    return min;
  }
  return Math.min(Math.max(value, min), max);
}

function stopPropertyPanelDrag() {
  if (!propertyPanelDragState) {
    return;
  }
  window.removeEventListener("pointermove", movePropertyPanel);
  window.removeEventListener("pointerup", stopPropertyPanelDrag);
  window.removeEventListener("pointercancel", stopPropertyPanelDrag);
  propertyPanelDragState = null;
}

function movePropertyPanel(event) {
  if (!propertyPanelDragState) {
    return;
  }
  const { bounds, offsetX, offsetY, width, height } = propertyPanelDragState;
  propertyPanelPosition.value = {
    x: clampNumber(event.clientX - bounds.left - offsetX, 8, bounds.width - width - 8),
    y: clampNumber(event.clientY - bounds.top - offsetY, 8, bounds.height - height - 8),
  };
}

function startPropertyPanelDrag(event) {
  if (event.button !== 0) {
    return;
  }
  const panel = event.currentTarget.closest(".gis-property-panel");
  const surface = mapRootRef.value?.closest(".gis-map-surface");
  if (!panel || !surface) {
    return;
  }
  const panelRect = panel.getBoundingClientRect();
  const surfaceRect = surface.getBoundingClientRect();
  propertyPanelDragState = {
    bounds: {
      left: surfaceRect.left,
      top: surfaceRect.top,
      width: surfaceRect.width,
      height: surfaceRect.height,
    },
    width: panelRect.width,
    height: panelRect.height,
    offsetX: event.clientX - panelRect.left,
    offsetY: event.clientY - panelRect.top,
  };
  propertyPanelPosition.value = {
    x: panelRect.left - surfaceRect.left,
    y: panelRect.top - surfaceRect.top,
  };
  window.addEventListener("pointermove", movePropertyPanel);
  window.addEventListener("pointerup", stopPropertyPanelDrag);
  window.addEventListener("pointercancel", stopPropertyPanelDrag);
  event.preventDefault();
}

function showMapClickMarker(coordinate) {
  const markerLayer = getOrCreateQueryMarkerLayer();
  const source = markerLayer.getSource();
  source.clear();
  source.addFeature(new Feature({ geometry: new Point(coordinate) }));
}

function getGeometryProjection(geometry) {
  if (geometry?.crs?.properties?.name) {
    const crsName = String(geometry.crs.properties.name);
    const epsgMatch = crsName.match(/EPSG[:/](\d+)/i);
    if (epsgMatch?.[1] === "3857") {
      return "EPSG:3857";
    }
    if (epsgMatch?.[1] === "4326" || epsgMatch?.[1] === "4490") {
      return "EPSG:4326";
    }
  }
  const firstNumberPair = (coords) => {
    if (!Array.isArray(coords)) return null;
    if (typeof coords[0] === "number" && typeof coords[1] === "number") {
      return coords;
    }
    for (const item of coords) {
      const pair = firstNumberPair(item);
      if (pair) return pair;
    }
    return null;
  };
  const pair = firstNumberPair(geometry?.coordinates);
  if (!pair) {
    return "EPSG:4326";
  }
  return Math.abs(pair[0]) > 180 || Math.abs(pair[1]) > 90 ? "EPSG:3857" : "EPSG:4326";
}

function coordinatesLookLikeLonLat(coords) {
  if (!Array.isArray(coords)) return false;
  if (typeof coords[0] === "number" && typeof coords[1] === "number") {
    return Math.abs(coords[0]) <= 180 && Math.abs(coords[1]) <= 90;
  }
  return coords.some(coordinatesLookLikeLonLat);
}

function projectLonLatCoordinates(coords) {
  if (!Array.isArray(coords)) return coords;
  if (typeof coords[0] === "number" && typeof coords[1] === "number") {
    return fromLonLat(coords);
  }
  return coords.map(projectLonLatCoordinates);
}

function readLonLatParcelFeature(parcel, geometry) {
  if (!geometry || !coordinatesLookLikeLonLat(geometry.coordinates)) {
    return null;
  }
  if (geometry.type === "Polygon") {
    return new Feature({
      ...parcel,
      geometry: new Polygon(projectLonLatCoordinates(geometry.coordinates)),
    });
  }
  if (geometry.type === "MultiPolygon") {
    return new Feature({
      ...parcel,
      geometry: new MultiPolygon(projectLonLatCoordinates(geometry.coordinates)),
    });
  }
  return null;
}

function readParcelFeature(parcel, fallbackFeature) {
  const geometries = [parcel.geometry, fallbackFeature?.geometry].filter(Boolean);
  for (const geometry of geometries) {
    try {
      const manualFeature = readLonLatParcelFeature(parcel, geometry);
      if (manualFeature) {
        return manualFeature;
      }
      return new GeoJSON().readFeature(
        {
          type: "Feature",
          geometry,
          properties: parcel,
        },
        { dataProjection: getGeometryProjection(geometry), featureProjection: "EPSG:3857" },
      );
    } catch (error) {
      console.warn("Failed to parse parcel geometry:", error);
    }
  }
  return null;
}

function highlightParcel(parcel, coordinate, fallbackFeature = null) {
  const highlightLayer = getOrCreateParcelHighlightLayer();
  const source = highlightLayer.getSource();
  source.clear();

  let popupCoordinate = coordinate;
  const feature = readParcelFeature(parcel, fallbackFeature);
  if (feature) {
    source.addFeature(feature);
    const extent = feature.getGeometry()?.getExtent();
    if (extent && extent.every(Number.isFinite)) {
      popupCoordinate = popupCoordinate || getCenter(extent);
      mapRef.value.getView().fit(extent, {
        padding: [110, 380, 130, 90],
        duration: 450,
        maxZoom: 18,
      });
    }
  }

  parcelPopupOverlay?.setPosition(popupCoordinate);
}

function updateAttrsByParcel(parcel) {
  updateAttrsByEntries([
    { label: "\u5730\u5757\u4fe1\u606f", value: parcel.dkmc || parcel.dkbm || ui.unknown },
    { label: "\u5408\u540c\u9762\u79ef", value: parcel.htmj || ui.unknown },
    { label: "\u5b9e\u6d4b\u9762\u79ef", value: parcel.scmj || ui.unknown },
    { label: ui.contractor, value: parcel.cbfmc || ui.unknown },
    { label: ui.issuer, value: parcel.fbfmc || ui.unknown },
  ]);
}

async function showPropertyPanel() {
  const wasVisible = propertyPanelVisible.value;
  propertyPanelVisible.value = false;
  if (wasVisible) {
    await new Promise((resolve) => window.setTimeout(resolve, 160));
  }
  await nextTick();
  propertyPanelKey.value += 1;
  propertyPanelVisible.value = true;
}

async function applyParcelSelection(dkbm, coordinate, fallbackFeature = null) {
  if (!dkbm) {
    return false;
  }
  let parcel = null;
  try {
    const { data } = await fetchGisParcel(dkbm);
    parcel = data.data;
    if (!parcel) {
      return false;
    }
  } catch (_error) {
    return false;
  }

  selectedParcel.value = parcel;
  activeParcelTab.value = "contractor";
  updateAttrsByParcel(parcel);
  await showPropertyPanel();
  try {
    highlightParcel(parcel, coordinate, fallbackFeature);
  } catch (error) {
    console.warn("Failed to highlight parcel:", error);
  }
  queryMessage.value = `${ui.parcelClickHit}${parcel.dkbm}`;
  return true;
}

async function locateParcelByCode(dkbm, silent = false) {
  if (!dkbm) {
    return false;
  }
  let parcel = null;
  try {
    const { data } = await fetchGisParcel(dkbm);
    parcel = data.data;
  } catch (_error) {
    return false;
  }
  if (!parcel) {
    return false;
  }

  selectedParcel.value = parcel;
  activeParcelTab.value = "contractor";
  updateAttrsByParcel(parcel);
  await showPropertyPanel();
  try {
    highlightParcel(parcel, null);
  } catch (error) {
    console.warn("Failed to locate parcel:", error);
  }
  if (!silent) {
    queryMessage.value = `${ui.parcelClickHit}${parcel.dkbm}`;
  }
  return true;
}

function buildWmsFeatureInfoUrl(instance, coordinate) {
  const map = mapRef.value;
  const view = map?.getView();
  const size = map?.getSize();
  if (!map || !view || !size) {
    return "";
  }

  const source = instance?.getSource?.();
  const sourceParams = source?.getParams?.() || {};
  const serviceConfig = instance.get("serviceConfig") || {};
  const parsed = parseServiceUrl(serviceConfig.serviceUrl || source?.getUrls?.()?.[0] || source?.getUrl?.() || "");
  const params = { ...parsed.params, ...sourceParams };
  const version = params.VERSION || "1.1.1";
  const layerName = params.LAYERS || params.LAYER || getWmsLayerName(serviceConfig);
  if (!parsed.baseUrl || !layerName) {
    return "";
  }

  const pixel = map.getPixelFromCoordinate(coordinate);
  const width = Math.round(size[0]);
  const height = Math.round(size[1]);
  const extent = view.calculateExtent(size);
  const projectionCode = view.getProjection().getCode();
  const isV13 = version === "1.3.0";
  const requestParams = new URLSearchParams({
    SERVICE: "WMS",
    VERSION: version,
    REQUEST: "GetFeatureInfo",
    FORMAT: params.FORMAT || "image/png",
    TRANSPARENT: "true",
    LAYERS: layerName,
    QUERY_LAYERS: layerName,
    STYLES: params.STYLES || "",
    INFO_FORMAT: "application/json",
    FEATURE_COUNT: "10",
    WIDTH: String(width),
    HEIGHT: String(height),
    BBOX: extent.join(","),
  });

  requestParams.set(isV13 ? "CRS" : "SRS", projectionCode);
  requestParams.set(isV13 ? "I" : "X", String(Math.round(pixel[0])));
  requestParams.set(isV13 ? "J" : "Y", String(Math.round(pixel[1])));

  return `${parsed.baseUrl}?${requestParams.toString()}`;
}

async function fetchWmsFeatureInfo(coordinate) {
  const view = mapRef.value?.getView();
  if (!view) {
    return false;
  }

  const wmsLayers = [];
  layerInstances.forEach((instance, key) => {
    if (instance.get("serviceType") === "WMS" && instance.get("parentKey") === "survey_dk_result" && instance.getVisible()) {
      wmsLayers.push({ key, instance });
    }
  });

  for (const { instance } of wmsLayers) {
    const url = buildWmsFeatureInfoUrl(instance, coordinate);
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
      const dkbm = getFeatureProperty(properties, ["dkbm", "DKBM", "source_dkbm", "SOURCE_DKBM", "地块代码"]);
      if (await applyParcelSelection(dkbm, coordinate, features[0])) {
        return true;
      }
      selectedParcel.value = null;
      propertyPanelVisible.value = false;
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
    layerRows.value.find((item) => item.key === "survey_dk_result") ||
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

  // Sync initial visibility for all rows — layer instances are created with
  // per-config visibility from normalizeLayer(), but the UI checkbox state
  // in layerRows may diverge, so force a full pass here.
  for (const item of layerRows.value) {
    syncLayerVisibility(item);
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

  parcelPopupOverlay = new Overlay({
    element: parcelPopupRef.value,
    positioning: "bottom-center",
    offset: [0, -18],
    stopEvent: false,
  });
  mapRef.value.addOverlay(parcelPopupOverlay);

  mapRef.value.on("pointermove", (event) => {
    updateCurrentCoord(event.coordinate);
  });

  mapRef.value.on("singleclick", async (event) => {
    updateCurrentCoord(event.coordinate);
    showMapClickMarker(event.coordinate);
    const hit = await fetchWmsFeatureInfo(event.coordinate);
    if (!hit) {
      parcelHighlightLayer?.getSource?.().clear();
      parcelPopupOverlay?.setPosition(undefined);
      selectedParcel.value = null;
      propertyPanelVisible.value = false;
    }
    if (!hit && activeTool.value === "query") {
      queryMessage.value = ui.clickNoFeature;
    }
  });
}

function switchBasemap() {
  if (!mapRef.value) return;
  emitBasemapTheme();
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
  const located = await locateParcelByCode(item.primaryParcelCode, true);
  if (!located) {
    await fitToPrimaryLayer();
    selectedParcel.value = null;
  }
  activeParcelTab.value = located ? "contract" : "contractor";
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
  await showPropertyPanel();
  if (!silent) {
    queryMessage.value = `${ui.requestLinked}${item.serialNo}`;
  }
}

async function applyIssuerResult(item) {
  const located = await locateParcelByCode(item.primaryParcelCode, true);
  if (!located) {
    await fitToPrimaryLayer();
    selectedParcel.value = null;
  }
  activeParcelTab.value = located ? "issuer" : "contractor";
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
  await showPropertyPanel();
  queryMessage.value = `${ui.issuerLinked}${item.name}`;
}

async function applyContractorResult(item) {
  const located = await locateParcelByCode(item.primaryParcelCode, true);
  if (!located) {
    await fitToPrimaryLayer();
    selectedParcel.value = null;
  }
  activeParcelTab.value = "contractor";
  updateAttrsByEntries([
    { label: ui.currentObject, value: ui.objectContractor },
    { label: ui.contractorName, value: item.name || ui.unknown },
    { label: ui.contractorCode, value: item.code || ui.unknown },
    { label: ui.idNo, value: item.idNo || ui.unknown },
    { label: ui.mobile, value: item.mobile || ui.unknown },
    { label: ui.address, value: item.address || ui.unknown },
    { label: ui.contractorType, value: dictDisplay(contractorTypeLabel, item.type) },
    { label: ui.coord, value: currentCoord.value },
  ]);
  await showPropertyPanel();
  queryMessage.value = `${ui.contractorLinked}${item.name}`;
}

function normalizeSearchResultForType(data) {
  const result = data || { requests: [], issuers: [], contractors: [] };
  return {
    requests: result.requests || [],
    issuers: searchType.value === "contractors" ? [] : result.issuers || [],
    contractors: searchType.value === "issuers" ? [] : result.contractors || [],
  };
}

function activateFirstSearchTab() {
  if (searchType.value !== "issuers" && searchResult.value.contractors.length) {
    activeSearchTab.value = "contractors";
    return;
  }
  if (searchType.value !== "contractors" && searchResult.value.issuers.length) {
    activeSearchTab.value = "issuers";
    return;
  }
  activeSearchTab.value = searchType.value === "issuers" ? "issuers" : "contractors";
}

async function applySearchResult(item) {
  if (item.resultType === "issuer") {
    await applyIssuerResult(item);
    return;
  }
  await applyContractorResult(item);
}

function resultCodeLabel(item) {
  return item.resultType === "issuer" ? ui.issuerCode : ui.contractorCode;
}

function resultSubLabel(item) {
  return item.resultType === "issuer" ? ui.ownerName : ui.idNo;
}

function resultSubValue(item) {
  if (item.resultType === "issuer") {
    return item.ownerName || ui.notMaintainedOwner;
  }
  return item.idNo || ui.notMaintainedId;
}

async function performQuery() {
  const keyword = queryKeyword.value.trim();
  if (!keyword) {
    queryMessage.value = ui.emptyKeyword;
    searchResult.value = { requests: [], issuers: [], contractors: [] };
    searchPanelVisible.value = true;
    return;
  }

  searchLoading.value = true;
  searchPanelVisible.value = true;
  try {
    const { data } = await searchGisBusiness({ keyword, limit: 10 });
    searchResult.value = normalizeSearchResultForType(data.data);
  } catch (_error) {
    searchResult.value = { requests: [], issuers: [], contractors: [] };
  } finally {
    searchLoading.value = false;
  }
  activateFirstSearchTab();

  if (searchResult.value.contractors.length) {
    await applyContractorResult(searchResult.value.contractors[0]);
  } else if (searchResult.value.issuers.length) {
    await applyIssuerResult(searchResult.value.issuers[0]);
  } else if (activeTool.value === "query" && searchResult.value.requests.length) {
    await applyRequestResult(searchResult.value.requests[0], true);
    queryMessage.value = `${ui.requestMatched}${searchResult.value.requests.length}${ui.requestMatchedSuffix}`;
  } else {
    const located = await locateParcelByCode(keyword, true);
    queryMessage.value = located ? `${ui.parcelClickHit}${keyword}` : ui.notFound;
    if (!located) {
      await fitToPrimaryLayer();
    }
  }
}

function clearSelection() {
  const markerLayer = layerInstances.get("query_marker");
  markerLayer?.getSource?.().clear();
  parcelHighlightLayer?.getSource?.().clear();
  parcelPopupOverlay?.setPosition(undefined);
  selectedParcel.value = null;
  propertyPanelVisible.value = false;
  queryMessage.value = "";
  searchResult.value = { requests: [], issuers: [], contractors: [] };
  searchPanelVisible.value = false;
}

async function resetView() {
  await fitToPrimaryLayer();
}

onMounted(async () => {
  await loadLayerConfigs();
  await buildMap();
  mapRef.value.setTarget(mapRootRef.value);
  await fitToPrimaryLayer();
});

onBeforeUnmount(() => {
  clearMeasureInteraction();
  clearLabelInteraction();
  stopPropertyPanelDrag();
  if (mapRef.value) {
    mapRef.value.setTarget(undefined);
  }
});
</script>
