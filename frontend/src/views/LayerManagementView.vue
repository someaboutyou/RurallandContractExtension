<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div class="panel-title">{{ ui.title }}</div>
      <div class="toolbar-actions">
        <el-button plain @click="loadLayers">{{ ui.refresh }}</el-button>
        <el-button v-if="canManage" plain :loading="bulkBboxLoading" @click="handleRecalculateAllBbox">{{ ui.recalculateAllBbox }}</el-button>
        <el-button v-if="canManage" type="success" @click="openCreateDialog">{{ ui.create }}</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="manage-tabs layer-config-tabs">
      <el-tab-pane :label="ui.vectorTab" name="vector">
        <div class="table-page">
          <div class="toolbar toolbar-wrap">
            <div class="toolbar-actions toolbar-wrap">
              <el-input v-model="vectorKeyword" clearable :placeholder="ui.vectorKeyword" style="width: 280px" />
              <el-select v-model="vectorType" clearable :placeholder="ui.serviceType" style="width: 160px">
                <el-option label="GeoJSON" value="GeoJSON" />
                <el-option label="WMS" value="WMS" />
                <el-option label="WMTS" value="WMTS" />
                <el-option label="WFS" value="WFS" />
                <el-option label="XYZ" value="XYZ" />
              </el-select>
              <el-select v-model="vectorGroup" clearable :placeholder="ui.layerGroup" style="width: 180px">
                <el-option v-for="group in vectorGroups" :key="group" :label="group" :value="group" />
              </el-select>
            </div>
          </div>

          <div class="table-shell">
            <div class="table-scroll">
              <el-table v-loading="loading" :data="filteredVectorLayers" border>
                <el-table-column prop="name" :label="ui.layerName" min-width="180" />
                <el-table-column prop="key" :label="ui.layerKey" min-width="140" />
                <el-table-column prop="groupName" :label="ui.layerGroup" min-width="120" />
                <el-table-column prop="serviceTypesSummary" :label="ui.serviceType" min-width="140" />
                <el-table-column prop="zoomSummary" :label="ui.zoomRange" min-width="220" show-overflow-tooltip />
                <el-table-column prop="serviceCount" :label="ui.serviceCount" min-width="90" />
                <el-table-column prop="defaultVisible" :label="ui.defaultVisible" min-width="90">
                  <template #default="{ row }">
                    <el-tag :type="row.defaultVisible ? 'success' : 'info'" effect="light">
                      {{ row.defaultVisible ? ui.yes : ui.no }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="enabled" :label="ui.enabled" min-width="80">
                  <template #default="{ row }">
                    <el-tag :type="row.enabled ? 'success' : 'info'" effect="light">
                      {{ row.enabled ? ui.enabled : ui.disabled }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="sortOrder" :label="ui.sortOrder" min-width="80" />
                <el-table-column v-if="canManage" :label="ui.actions" width="190" fixed="right">
                  <template #default="{ row }">
                    <div class="table-actions">
                      <el-button link type="success" @click="testLayer(row)">{{ ui.test }}</el-button>
                      <el-button link type="primary" @click="openEditDialog(row)">{{ ui.edit }}</el-button>
                      <el-dropdown trigger="click" @command="(command) => handleLayerCommand(row, command)">
                        <el-button link type="info">{{ ui.more }}</el-button>
                        <template #dropdown>
                          <el-dropdown-menu>
                            <el-dropdown-item
                              v-if="isGeoserverLayer(row)"
                              command="bbox"
                              :disabled="isRowBusy(row, 'bbox')"
                            >
                              {{ isRowBusy(row, "bbox") ? ui.processing : ui.recalculateBbox }}
                            </el-dropdown-item>
                            <el-dropdown-item command="up">{{ ui.moveUp }}</el-dropdown-item>
                            <el-dropdown-item command="down">{{ ui.moveDown }}</el-dropdown-item>
                            <el-dropdown-item command="delete" divided>{{ ui.delete }}</el-dropdown-item>
                          </el-dropdown-menu>
                        </template>
                      </el-dropdown>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane :label="ui.basemapTab" name="basemap">
        <div class="table-page">
          <div class="toolbar toolbar-wrap">
            <div class="toolbar-actions toolbar-wrap">
              <el-input v-model="basemapKeyword" clearable :placeholder="ui.basemapKeyword" style="width: 280px" />
            </div>
          </div>

          <div class="table-shell">
            <div class="table-scroll">
              <el-table v-loading="loading" :data="filteredBasemaps" border>
                <el-table-column prop="name" :label="ui.layerName" min-width="180" />
                <el-table-column prop="key" :label="ui.layerKey" min-width="120" />
                <el-table-column prop="serviceTypesSummary" :label="ui.serviceType" min-width="140" />
                <el-table-column prop="zoomSummary" :label="ui.zoomRange" min-width="220" show-overflow-tooltip />
                <el-table-column prop="serviceCount" :label="ui.serviceCount" min-width="90" />
                <el-table-column prop="isDefault" :label="ui.defaultBasemap" min-width="90">
                  <template #default="{ row }">
                    <el-tag :type="row.isDefault ? 'success' : 'info'" effect="light">
                      {{ row.isDefault ? ui.yes : ui.no }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="enabled" :label="ui.enabled" min-width="80">
                  <template #default="{ row }">
                    <el-tag :type="row.enabled ? 'success' : 'info'" effect="light">
                      {{ row.enabled ? ui.enabled : ui.disabled }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="sortOrder" :label="ui.sortOrder" min-width="80" />
                <el-table-column v-if="canManage" :label="ui.actions" width="190" fixed="right">
                  <template #default="{ row }">
                    <div class="table-actions">
                      <el-button link type="success" @click="testLayer(row)">{{ ui.test }}</el-button>
                      <el-button link type="primary" @click="openEditDialog(row)">{{ ui.edit }}</el-button>
                      <el-dropdown trigger="click" @command="(command) => handleLayerCommand(row, command)">
                        <el-button link type="info">{{ ui.more }}</el-button>
                        <template #dropdown>
                          <el-dropdown-menu>
                            <el-dropdown-item command="up">{{ ui.moveUp }}</el-dropdown-item>
                            <el-dropdown-item command="down">{{ ui.moveDown }}</el-dropdown-item>
                            <el-dropdown-item command="delete" divided>{{ ui.delete }}</el-dropdown-item>
                          </el-dropdown-menu>
                        </template>
                      </el-dropdown>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </section>

  <el-dialog v-model="dialogVisible" :title="editingId ? ui.editDialog : ui.createDialog" width="920px" destroy-on-close>
    <el-form ref="formRef" :model="form" :rules="rules" class="compact-form" label-position="top" status-icon>
      <div class="form-grid">
        <el-form-item :label="ui.layerCategory" prop="category">
          <el-select v-model="form.category" :placeholder="ui.selectCategory">
            <el-option :label="ui.vectorTab" value="vector" />
            <el-option :label="ui.basemapTab" value="basemap" />
          </el-select>
        </el-form-item>
        <el-form-item :label="ui.layerName" prop="name">
          <el-input v-model="form.name" :placeholder="ui.inputName" />
        </el-form-item>
        <el-form-item :label="ui.layerKey" prop="key">
          <el-input v-model="form.key" :placeholder="ui.inputKey" />
        </el-form-item>
        <el-form-item :label="ui.layerGroup" prop="groupName">
          <el-input v-model="form.groupName" :placeholder="ui.inputGroup" />
        </el-form-item>
        <el-form-item :label="ui.sortOrder" prop="sortOrder">
          <el-input-number v-model="form.sortOrder" :min="0" :step="10" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="ui.defaultVisible">
          <el-switch v-model="form.defaultVisible" />
        </el-form-item>
        <el-form-item :label="ui.defaultBasemap">
          <el-switch v-model="form.isDefault" :disabled="form.category !== 'basemap'" />
        </el-form-item>
        <el-form-item :label="ui.enabled">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </div>

      <div class="toolbar toolbar-wrap">
        <div class="panel-title">{{ ui.serviceConfigTitle }}</div>
        <div class="toolbar-actions">
          <el-button plain @click="addServiceConfig">{{ ui.addService }}</el-button>
          <el-button plain :disabled="form.serviceConfigs.length <= 1" @click="removeServiceConfig">{{ ui.removeService }}</el-button>
        </div>
      </div>

      <el-tabs v-model="activeServiceTab" class="compact-dialog-tabs">
        <el-tab-pane
          v-for="(service, index) in form.serviceConfigs"
          :key="service.id"
          :label="getServiceTabLabel(service, index)"
          :name="service.id"
        >
          <div class="form-grid">
            <el-form-item :label="ui.serviceType">
              <el-select v-model="service.serviceType" :placeholder="ui.selectType">
                <el-option label="GeoJSON" value="GeoJSON" />
                <el-option label="WMS" value="WMS" />
                <el-option label="WMTS" value="WMTS" />
                <el-option label="WFS" value="WFS" />
                <el-option label="XYZ" value="XYZ" />
                <el-option label="OSM" value="OSM" />
              </el-select>
            </el-form-item>
            <el-form-item :label="ui.projection">
              <el-input v-model="service.projection" :placeholder="ui.inputProjection" />
            </el-form-item>
            <el-form-item :label="ui.minZoom">
              <el-input-number v-model="service.minZoom" :min="0" :max="24" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="ui.maxZoom">
              <el-input-number v-model="service.maxZoom" :min="0" :max="24" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="ui.serviceEnabled">
              <el-switch v-model="service.enabled" />
            </el-form-item>
            <el-form-item class="form-span-2" :label="ui.serviceUrl">
              <div style="display: flex; gap: 8px; width: 100%;">
                <el-input v-model="service.serviceUrl" :placeholder="ui.inputServiceUrl" style="flex: 1;" />
                <el-button
                  v-if="service.serviceType === 'WMS' || service.serviceType === 'WMTS'"
                  plain
                  @click="openGeoserverPicker(service)"
                >
                  {{ ui.selectFromGeoserver }}
                </el-button>
                <el-button
                  v-if="service.serviceType === 'WMS' || service.serviceType === 'WMTS'"
                  plain
                  type="warning"
                  :disabled="!service.serviceUrl"
                  @click="openServiceCacheDialog(service)"
                >
                  {{ ui.seedCache }}
                </el-button>
              </div>
            </el-form-item>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-form>

    <template #footer>
      <el-button @click="dialogVisible = false">{{ ui.cancel }}</el-button>
      <el-button :loading="submitting" type="success" @click="handleSubmit">{{ ui.save }}</el-button>
    </template>
  </el-dialog>

  <!-- GeoServer 图层选择对话框 -->
  <el-dialog v-model="geoserverPickerVisible" :title="ui.geoserverPickerTitle" width="720px" destroy-on-close>
    <div style="margin-bottom: 16px; display: flex; gap: 8px;">
      <el-input v-model="geoserverUrl" :placeholder="ui.geoserverUrlPlaceholder" style="flex: 1;" clearable />
      <el-select v-model="geoserverServiceType" style="width: 100px;">
        <el-option label="WMS" value="WMS" />
        <el-option label="WMTS" value="WMTS" />
      </el-select>
      <el-button type="primary" :loading="geoserverLoading" @click="handleFetchGeoserverLayers">
        {{ ui.queryLayers }}
      </el-button>
    </div>
    <div style="margin-bottom: 12px; display: flex; gap: 12px; align-items: center;">
      <el-input v-model="geoserverFilter" :placeholder="ui.filterLayers" style="width: 260px;" clearable size="small" />
      <span style="font-size: 12px; color: #909399;">{{ ui.totalLayers }}: {{ filteredGeoserverLayers.length }}</span>
    </div>
    <el-table v-loading="geoserverLoading" :data="pagedGeoserverLayers" border max-height="380" size="small">
      <el-table-column prop="workspace" :label="ui.workspace" width="130" />
      <el-table-column prop="name" :label="ui.geoserverLayerName" min-width="200" show-overflow-tooltip />
      <el-table-column prop="title" :label="ui.geoserverLayerTitle" min-width="180" show-overflow-tooltip />
      <el-table-column :label="ui.select" width="80" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="selectGeoserverLayer(row)">{{ ui.select }}</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="margin-top: 12px; display: flex; justify-content: center;">
      <el-pagination
        v-model:current-page="geoserverPage"
        :page-size="geoserverPageSize"
        :total="filteredGeoserverLayers.length"
        layout="prev, pager, next"
        small
      />
    </div>
    <template #footer>
      <el-button @click="geoserverPickerVisible = false">{{ ui.cancel }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="cacheDialogVisible" :title="ui.cacheDialogTitle" width="520px" destroy-on-close>
    <el-form :model="cacheForm" class="compact-form" label-position="top">
      <div class="form-grid">
        <el-form-item :label="ui.geoserverLayerName">
          <el-input v-model="cacheForm.layerName" disabled />
        </el-form-item>
        <el-form-item :label="ui.gridSetId">
          <el-select v-model="cacheForm.gridSetId">
            <el-option label="EPSG:4326" value="EPSG:4326" />
            <el-option label="EPSG:900913" value="EPSG:900913" />
          </el-select>
        </el-form-item>
        <el-form-item :label="ui.zoomStart">
          <el-input-number v-model="cacheForm.zoomStart" :min="0" :max="24" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="ui.zoomStop">
          <el-input-number v-model="cacheForm.zoomStop" :min="0" :max="24" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="ui.cacheType">
          <el-select v-model="cacheForm.type">
            <el-option :label="ui.cacheTypeReseed" value="reseed" />
            <el-option :label="ui.cacheTypeSeed" value="seed" />
            <el-option :label="ui.cacheTypeTruncate" value="truncate" />
          </el-select>
        </el-form-item>
        <el-form-item :label="ui.threadCount">
          <el-input-number v-model="cacheForm.threadCount" :min="1" :max="8" style="width: 100%" />
        </el-form-item>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="cacheDialogVisible = false">{{ ui.cancel }}</el-button>
      <el-button type="warning" :loading="cacheSubmitting" @click="handleSeedCache">{{ ui.seedCache }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createMapLayer,
  deleteMapLayer,
  fetchGeoserverLayers,
  fetchMapLayers,
  recalculateAllMapLayerBboxes,
  recalculateMapLayerBbox,
  seedMapLayerServiceCache,
  updateMapLayer,
  validateMapLayerService,
} from "../api/mapLayer";
import { basemapConfigs, vectorLayerConfigs } from "../config/mapLayers";
import { useAuthStore } from "../stores/auth";

const ui = {
  title: "\u56fe\u5c42\u7ba1\u7406",
  refresh: "\u5237\u65b0",
  create: "\u65b0\u589e\u56fe\u5c42",
  vectorTab: "\u77e2\u91cf\u56fe\u5c42",
  basemapTab: "\u5e95\u56fe\u7ba1\u7406",
  vectorKeyword: "\u641c\u7d22\u56fe\u5c42\u540d\u79f0\u3001\u7f16\u7801\u6216\u670d\u52a1\u7c7b\u578b",
  basemapKeyword: "\u641c\u7d22\u5e95\u56fe\u540d\u79f0\u6216\u670d\u52a1\u7c7b\u578b",
  serviceType: "\u670d\u52a1\u7c7b\u578b",
  serviceUrl: "\u670d\u52a1\u5730\u5740",
  serviceConfigTitle: "\u670d\u52a1\u914d\u7f6e",
  serviceCount: "\u670d\u52a1\u6570",
  zoomRange: "\u7f29\u653e\u8303\u56f4",
  layerGroup: "\u56fe\u5c42\u5206\u7ec4",
  layerName: "\u56fe\u5c42\u540d\u79f0",
  layerKey: "\u56fe\u5c42\u7f16\u7801",
  defaultVisible: "\u9ed8\u8ba4\u663e\u793a",
  enabled: "\u542f\u7528",
  disabled: "\u505c\u7528",
  sortOrder: "\u6392\u5e8f",
  actions: "\u64cd\u4f5c",
  more: "\u66f4\u591a",
  processing: "\u5904\u7406\u4e2d...",
  defaultBasemap: "\u9ed8\u8ba4\u5e95\u56fe",
  projection: "\u5750\u6807\u7cfb",
  minZoom: "\u6700\u5c0f Zoom",
  maxZoom: "\u6700\u5927 Zoom",
  serviceEnabled: "\u670d\u52a1\u542f\u7528",
  yes: "\u662f",
  no: "\u5426",
  test: "\u6d4b\u8bd5\u670d\u52a1",
  recalculateAllBbox: "\u6279\u91cf\u91cd\u7b97bbox",
  recalculateBbox: "\u91cd\u7b97bbox",
  seedCache: "\u521b\u5efa\u7f13\u5b58",
  moveUp: "\u4e0a\u79fb",
  moveDown: "\u4e0b\u79fb",
  edit: "\u7f16\u8f91",
  delete: "\u5220\u9664",
  addService: "\u65b0\u589e\u670d\u52a1",
  removeService: "\u5220\u9664\u5f53\u524d\u670d\u52a1",
  editDialog: "\u7f16\u8f91\u56fe\u5c42",
  createDialog: "\u65b0\u589e\u56fe\u5c42",
  layerCategory: "\u56fe\u5c42\u5206\u7c7b",
  selectCategory: "\u8bf7\u9009\u62e9\u56fe\u5c42\u5206\u7c7b",
  selectType: "\u8bf7\u9009\u62e9\u670d\u52a1\u7c7b\u578b",
  inputName: "\u8bf7\u8f93\u5165\u56fe\u5c42\u540d\u79f0",
  inputKey: "\u8bf7\u8f93\u5165\u56fe\u5c42\u7f16\u7801",
  inputGroup: "\u5982\uff1aGeoServer\u56fe\u5c42\u3001\u57fa\u7840\u5e95\u56fe",
  inputProjection: "\u5982\uff1aEPSG:4326",
  inputServiceUrl: "\u8bf7\u8f93\u5165\u670d\u52a1\u5730\u5740",
  cancel: "\u53d6\u6d88",
  save: "\u4fdd\u5b58",
  saveCreated: "\u56fe\u5c42\u5df2\u521b\u5efa",
  saveUpdated: "\u56fe\u5c42\u5df2\u66f4\u65b0",
  saveFailed: "\u56fe\u5c42\u4fdd\u5b58\u5931\u8d25",
  deleteTitle: "\u5220\u9664\u786e\u8ba4",
  deleteConfirm: "\u786e\u5b9a\u5220\u9664\u56fe\u5c42\u201c{0}\u201d\u5417\uff1f",
  deleteSuccess: "\u56fe\u5c42\u5df2\u5220\u9664",
  deleteFailed: "\u56fe\u5c42\u5220\u9664\u5931\u8d25",
  sortSuccess: "\u56fe\u5c42\u6392\u5e8f\u5df2\u66f4\u65b0",
  sortFailed: "\u56fe\u5c42\u6392\u5e8f\u66f4\u65b0\u5931\u8d25",
  fallbackConfig: "\u56fe\u5c42\u63a5\u53e3\u6682\u4e0d\u53ef\u7528\uff0c\u5df2\u5207\u6362\u4e3a\u672c\u5730\u6f14\u793a\u914d\u7f6e\u3002",
  testFailed: "\u670d\u52a1\u5730\u5740\u6d4b\u8bd5\u5931\u8d25",
  ruleCategory: "\u8bf7\u9009\u62e9\u56fe\u5c42\u5206\u7c7b",
  ruleName: "\u8bf7\u8f93\u5165\u56fe\u5c42\u540d\u79f0",
  ruleKey: "\u8bf7\u8f93\u5165\u56fe\u5c42\u7f16\u7801",
  requireService: "\u81f3\u5c11\u914d\u7f6e\u4e00\u4e2a\u670d\u52a1",
  requireServiceType: "\u8bf7\u9009\u62e9\u670d\u52a1\u7c7b\u578b",
  requireServiceUrl: "\u8bf7\u8f93\u5165\u670d\u52a1\u5730\u5740",
  invalidZoomRange: "\u670d\u52a1\u7f29\u653e\u8303\u56f4\u65e0\u6548",
  selectFromGeoserver: "\u4eceGeoServer\u9009\u62e9",
  geoserverPickerTitle: "\u9009\u62e9 GeoServer \u56fe\u5c42",
  geoserverUrlPlaceholder: "GeoServer \u5730\u5740\uff0c\u5982 /geoserver",
  queryLayers: "\u67e5\u8be2\u56fe\u5c42",
  filterLayers: "\u8fc7\u6ee4\u56fe\u5c42\u540d\u79f0...",
  totalLayers: "\u56fe\u5c42\u6570",
  workspace: "\u5de5\u4f5c\u533a",
  geoserverLayerName: "\u56fe\u5c42\u540d\u79f0",
  geoserverLayerTitle: "\u6807\u9898",
  select: "\u9009\u62e9",
  geoserverFetchFailed: "\u65e0\u6cd5\u83b7\u53d6 GeoServer \u56fe\u5c42\u5217\u8868",
  geoserverEmpty: "\u672a\u627e\u5230\u56fe\u5c42\uff0c\u8bf7\u68c0\u67e5 GeoServer \u5730\u5740\u548c\u670d\u52a1\u7c7b\u578b\u3002",
  bboxSuccess: "bbox \u5df2\u91cd\u65b0\u8ba1\u7b97",
  bboxFailed: "bbox \u91cd\u65b0\u8ba1\u7b97\u5931\u8d25",
  bboxAllSuccess: "\u5df2\u91cd\u7b97 {0} \u4e2a\u56fe\u5c42 bbox",
  cacheDialogTitle: "\u521b\u5efa GeoServer \u5207\u7247\u7f13\u5b58",
  gridSetId: "\u7f51\u683c\u96c6",
  zoomStart: "\u8d77\u59cb Zoom",
  zoomStop: "\u7ed3\u675f Zoom",
  cacheType: "\u4efb\u52a1\u7c7b\u578b",
  cacheTypeSeed: "\u53ea\u521b\u5efa\u7f3a\u5931\u5207\u7247",
  cacheTypeReseed: "\u91cd\u65b0\u751f\u6210\u5207\u7247",
  cacheTypeTruncate: "\u6e05\u7a7a\u5207\u7247",
  threadCount: "\u7ebf\u7a0b\u6570",
  cacheSuccess: "\u7f13\u5b58\u4efb\u52a1\u5df2\u63d0\u4ea4",
  cacheFailed: "\u7f13\u5b58\u4efb\u52a1\u521b\u5efa\u5931\u8d25",
};

function formatText(template, value) {
  return template.replace("{0}", value);
}

function createServiceId() {
  return `service_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function createServiceConfig(serviceType = "WMS") {
  return {
    id: createServiceId(),
    serviceType,
    serviceUrl: "",
    projection: "EPSG:4326",
    minZoom: 0,
    maxZoom: 24,
    enabled: true,
  };
}

function normalizeServiceUrl(rawUrl) {
  const value = rawUrl?.trim() || "";
  if (!value) {
    return value;
  }
  try {
    const url = new URL(value, window.location.origin);
    const isGeoServerLocal =
      (url.hostname === "localhost" || url.hostname === "127.0.0.1") &&
      url.port === "8080" &&
      url.pathname.startsWith("/geoserver");
    if (isGeoServerLocal) {
      return `${url.pathname}${url.search}`;
    }
  } catch (_error) {
    return value;
  }
  return value;
}

function normalizeServiceConfig(item) {
  return {
    id: item.id || createServiceId(),
    serviceType: item.serviceType || item.layerType || "WMS",
    serviceUrl: normalizeServiceUrl(item.serviceUrl || ""),
    projection: item.projection || "EPSG:4326",
    minZoom: Number(item.minZoom ?? 0),
    maxZoom: Number(item.maxZoom ?? 24),
    enabled: item.enabled ?? true,
  };
}

function normalizeLayerRow(item) {
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
  const serviceConfigs = rawServiceConfigs.map(normalizeServiceConfig);
  const serviceTypes = [...new Set(serviceConfigs.map((service) => service.serviceType))];
  return {
    ...item,
    groupName: item.groupName || "",
    serviceConfigs,
    serviceTypesSummary: item.serviceTypesSummary || serviceTypes.join(" + "),
    zoomSummary:
      item.zoomSummary || serviceConfigs.map((service) => `${service.serviceType}: ${service.minZoom}-${service.maxZoom}`).join(" | "),
    serviceCount: serviceConfigs.length,
    serviceUrl: serviceConfigs[0]?.serviceUrl || item.serviceUrl || "",
    projection: serviceConfigs[0]?.projection || item.projection || "",
  };
}

function ensurePrimaryGeoServerLayer(rows) {
  const normalizedRows = (Array.isArray(rows) ? rows : []).map(normalizeLayerRow);
  if (normalizedRows.some((item) => item.key === "survey_dk_result")) {
    return normalizedRows;
  }

  const fallbackPrimary = vectorLayerConfigs.find((item) => item.key === "survey_dk_result");
  if (!fallbackPrimary) {
    return normalizedRows;
  }
  return [...normalizedRows, normalizeLayerRow(fallbackPrimary)];
}

function createEmptyForm() {
  return {
    category: "vector",
    name: "",
    key: "",
    groupName: "",
    defaultVisible: true,
    isDefault: false,
    sortOrder: 10,
    enabled: true,
    serviceConfigs: [createServiceConfig("WMS")],
  };
}

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("layers.manage"));

const activeTab = ref("vector");
const loading = ref(false);
const submitting = ref(false);
const bulkBboxLoading = ref(false);
const dialogVisible = ref(false);
const cacheDialogVisible = ref(false);
const cacheSubmitting = ref(false);
const editingId = ref(0);
const formRef = ref();
const activeServiceTab = ref("");
const geoserverPickerVisible = ref(false);
const geoserverUrl = ref("/geoserver");
const geoserverServiceType = ref("WMS");
const geoserverLoading = ref(false);
const geoserverLayers = ref([]);
const geoserverFilter = ref("");
const geoserverPage = ref(1);
const geoserverPageSize = 10;
let pendingService = null;
let pendingCacheService = null;

const filteredGeoserverLayers = computed(() => {
  const keyword = geoserverFilter.value.trim().toLowerCase();
  if (!keyword) {
    return geoserverLayers.value;
  }
  return geoserverLayers.value.filter(
    (item) => item.name.toLowerCase().includes(keyword) || item.title.toLowerCase().includes(keyword),
  );
});

const pagedGeoserverLayers = computed(() => {
  const start = (geoserverPage.value - 1) * geoserverPageSize;
  return filteredGeoserverLayers.value.slice(start, start + geoserverPageSize);
});

const vectorKeyword = ref("");
const vectorType = ref("");
const vectorGroup = ref("");
const basemapKeyword = ref("");
const rows = ref([]);
const form = reactive(createEmptyForm());
const cacheForm = reactive({
  layerId: 0,
  layerName: "",
  gridSetId: "EPSG:4326",
  zoomStart: 0,
  zoomStop: 15,
  type: "reseed",
  threadCount: 2,
});
const rowBusyKeys = ref(new Set());

const rules = {
  category: [{ required: true, message: ui.ruleCategory, trigger: "change" }],
  name: [{ required: true, message: ui.ruleName, trigger: "blur" }],
  key: [{ required: true, message: ui.ruleKey, trigger: "blur" }],
};

const filteredVectorLayers = computed(() =>
  rows.value
    .filter((item) => item.category === "vector")
    .filter((item) => {
      const keyword = vectorKeyword.value.trim().toLowerCase();
      const serviceTexts = item.serviceConfigs.map((service) => `${service.serviceType} ${service.serviceUrl}`.toLowerCase());
      const matchesKeyword =
        !keyword ||
        item.name.toLowerCase().includes(keyword) ||
        item.key.toLowerCase().includes(keyword) ||
        serviceTexts.some((text) => text.includes(keyword));
      const matchesType = !vectorType.value || item.serviceConfigs.some((service) => service.serviceType === vectorType.value);
      const matchesGroup = !vectorGroup.value || (item.groupName || "") === vectorGroup.value;
      return matchesKeyword && matchesType && matchesGroup;
    })
    .sort((a, b) => (a.groupName || "").localeCompare(b.groupName || "") || a.sortOrder - b.sortOrder),
);

const filteredBasemaps = computed(() =>
  rows.value
    .filter((item) => item.category === "basemap")
    .filter((item) => {
      const keyword = basemapKeyword.value.trim().toLowerCase();
      const serviceTexts = item.serviceConfigs.map((service) => `${service.serviceType} ${service.serviceUrl}`.toLowerCase());
      return !keyword || item.name.toLowerCase().includes(keyword) || serviceTexts.some((text) => text.includes(keyword));
    })
    .sort((a, b) => a.sortOrder - b.sortOrder),
);

const vectorGroups = computed(() => Array.from(new Set(rows.value.filter((item) => item.category === "vector").map((item) => item.groupName).filter(Boolean))).sort());

function getServiceTabLabel(service, index) {
  return `${service.serviceType || ui.serviceType} ${index + 1}`;
}

function resetForm() {
  Object.assign(form, createEmptyForm());
  activeServiceTab.value = form.serviceConfigs[0].id;
  formRef.value?.clearValidate();
}

function addServiceConfig() {
  const serviceType = form.category === "basemap" ? "XYZ" : "WMS";
  const service = createServiceConfig(serviceType);
  form.serviceConfigs.push(service);
  activeServiceTab.value = service.id;
}

function removeServiceConfig() {
  if (form.serviceConfigs.length <= 1) {
    return;
  }
  const index = form.serviceConfigs.findIndex((item) => item.id === activeServiceTab.value);
  const targetIndex = index >= 0 ? index : form.serviceConfigs.length - 1;
  form.serviceConfigs.splice(targetIndex, 1);
  activeServiceTab.value = form.serviceConfigs[Math.max(0, targetIndex - 1)]?.id || form.serviceConfigs[0].id;
}

function buildPayloadFromForm() {
  const serviceConfigs = form.serviceConfigs.map((service) => ({
    serviceType: service.serviceType,
    serviceUrl: normalizeServiceUrl(service.serviceUrl),
    projection: service.projection?.trim() || null,
    minZoom: Number(service.minZoom ?? 0),
    maxZoom: Number(service.maxZoom ?? 24),
    enabled: service.enabled,
  }));
  return {
    name: form.name.trim(),
    key: form.key.trim(),
    category: form.category,
    groupName: form.groupName?.trim() || null,
    defaultVisible: form.defaultVisible,
    isDefault: form.isDefault,
    sortOrder: Number(form.sortOrder || 0),
    enabled: form.enabled,
    serviceConfigs,
  };
}

function validateServiceConfigs() {
  if (!form.serviceConfigs.length) {
    ElMessage.warning(ui.requireService);
    return false;
  }
  for (const service of form.serviceConfigs) {
    if (!service.serviceType) {
      ElMessage.warning(ui.requireServiceType);
      activeServiceTab.value = service.id;
      return false;
    }
    if (!service.serviceUrl?.trim()) {
      ElMessage.warning(ui.requireServiceUrl);
      activeServiceTab.value = service.id;
      return false;
    }
    if (Number(service.maxZoom) < Number(service.minZoom)) {
      ElMessage.warning(ui.invalidZoomRange);
      activeServiceTab.value = service.id;
      return false;
    }
  }
  return true;
}

async function loadLayers() {
  loading.value = true;
  try {
    const { data } = await fetchMapLayers();
    rows.value = ensurePrimaryGeoServerLayer(data.data);
  } catch (_error) {
    rows.value = ensurePrimaryGeoServerLayer([...vectorLayerConfigs, ...basemapConfigs]);
    ElMessage.warning(ui.fallbackConfig);
  } finally {
    loading.value = false;
  }
}

function openCreateDialog() {
  editingId.value = 0;
  resetForm();
  form.category = activeTab.value === "basemap" ? "basemap" : "vector";
  form.defaultVisible = form.category === "vector";
  form.serviceConfigs = [createServiceConfig(form.category === "basemap" ? "XYZ" : "WMS")];
  activeServiceTab.value = form.serviceConfigs[0].id;
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingId.value = row.id || 0;
  resetForm();
  Object.assign(form, {
    category: row.category,
    name: row.name,
    key: row.key,
    groupName: row.groupName || "",
    defaultVisible: row.defaultVisible,
    isDefault: row.isDefault,
    sortOrder: row.sortOrder,
    enabled: row.enabled,
    serviceConfigs: row.serviceConfigs.map(normalizeServiceConfig),
  });
  activeServiceTab.value = form.serviceConfigs[0]?.id || "";
  dialogVisible.value = true;
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid || !validateServiceConfigs()) {
    return;
  }

  submitting.value = true;
  try {
    const payload = buildPayloadFromForm();
    if (editingId.value) {
      await updateMapLayer(editingId.value, payload);
      ElMessage.success(ui.saveUpdated);
    } else {
      await createMapLayer(payload);
      ElMessage.success(ui.saveCreated);
    }
    dialogVisible.value = false;
    await loadLayers();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.saveFailed);
  } finally {
    submitting.value = false;
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(formatText(ui.deleteConfirm, row.name), ui.deleteTitle, {
    type: "warning",
    confirmButtonText: ui.delete,
    cancelButtonText: ui.cancel,
  });
  try {
    await deleteMapLayer(row.id);
    ElMessage.success(ui.deleteSuccess);
    await loadLayers();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.deleteFailed);
  }
}

async function moveLayer(row, delta) {
  if (!row.id) {
    return;
  }
  const nextSort = Math.max(0, Number(row.sortOrder || 0) + delta);
  try {
    await updateMapLayer(row.id, {
      ...buildPayloadFromRow(row),
      sortOrder: nextSort,
    });
    ElMessage.success(ui.sortSuccess);
    await loadLayers();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.sortFailed);
  }
}

function handleLayerCommand(row, command) {
  if (command === "bbox") {
    handleRecalculateBbox(row);
    return;
  }
  if (command === "up") {
    moveLayer(row, -10);
    return;
  }
  if (command === "down") {
    moveLayer(row, 10);
    return;
  }
  if (command === "delete") {
    handleDelete(row);
  }
}

function buildPayloadFromRow(row) {
  return {
    name: row.name,
    key: row.key,
    category: row.category,
    groupName: row.groupName || null,
    defaultVisible: row.defaultVisible,
    isDefault: row.isDefault,
    sortOrder: row.sortOrder,
    enabled: row.enabled,
    serviceConfigs: row.serviceConfigs.map((service) => ({
      serviceType: service.serviceType,
      serviceUrl: normalizeServiceUrl(service.serviceUrl),
      projection: service.projection || null,
      minZoom: Number(service.minZoom ?? 0),
      maxZoom: Number(service.maxZoom ?? 24),
      enabled: service.enabled,
    })),
  };
}

function getGeoServerLayerName(row) {
  for (const service of row.serviceConfigs || []) {
    const serviceUrl = service.serviceUrl || "";
    if (!serviceUrl.includes("/geoserver")) {
      continue;
    }
    const name = getGeoServerLayerNameFromUrl(serviceUrl);
    if (name) {
      return name;
    }
  }
  if ((row.groupName || "").includes("GeoServer")) {
    return `erlunyanbao:${row.key}`;
  }
  return "";
}

function isGeoserverLayer(row) {
  return Boolean(getGeoServerLayerName(row));
}

function isRowBusy(row, action) {
  return rowBusyKeys.value.has(`${row.id}:${action}`);
}

function setRowBusy(row, action, busy) {
  const next = new Set(rowBusyKeys.value);
  const key = `${row.id}:${action}`;
  if (busy) {
    next.add(key);
  } else {
    next.delete(key);
  }
  rowBusyKeys.value = next;
}

async function handleRecalculateBbox(row) {
  if (!row.id) {
    return;
  }
  setRowBusy(row, "bbox", true);
  try {
    await recalculateMapLayerBbox(row.id);
    ElMessage.success(ui.bboxSuccess);
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.bboxFailed);
  } finally {
    setRowBusy(row, "bbox", false);
  }
}

async function handleRecalculateAllBbox() {
  bulkBboxLoading.value = true;
  try {
    const { data } = await recalculateAllMapLayerBboxes();
    ElMessage.success(formatText(ui.bboxAllSuccess, data.data?.updatedCount ?? 0));
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.bboxFailed);
  } finally {
    bulkBboxLoading.value = false;
  }
}

function getGeoServerLayerNameFromUrl(serviceUrl) {
  if (!serviceUrl) {
    return "";
  }
  try {
    const url = new URL(serviceUrl, window.location.origin);
    return url.searchParams.get("layers") || url.searchParams.get("layer") || "";
  } catch (_error) {
    return "";
  }
}

function openServiceCacheDialog(service) {
  pendingCacheService = service;
  Object.assign(cacheForm, {
    layerId: 0,
    layerName: getGeoServerLayerNameFromUrl(service.serviceUrl),
    gridSetId: service.projection === "EPSG:3857" || service.projection === "EPSG:900913" ? "EPSG:900913" : "EPSG:4326",
    zoomStart: Number(service.minZoom ?? 0),
    zoomStop: Math.min(Number(service.maxZoom ?? 15), 18),
    type: "reseed",
    threadCount: 2,
  });
  cacheDialogVisible.value = true;
}

async function handleSeedCache() {
  if (Number(cacheForm.zoomStop) < Number(cacheForm.zoomStart)) {
    ElMessage.warning(ui.invalidZoomRange);
    return;
  }
  cacheSubmitting.value = true;
  try {
    const { data } = await seedMapLayerServiceCache({
      serviceUrl: pendingCacheService?.serviceUrl || "",
      gridSetId: cacheForm.gridSetId,
      zoomStart: Number(cacheForm.zoomStart),
      zoomStop: Number(cacheForm.zoomStop),
      type: cacheForm.type,
      threadCount: Number(cacheForm.threadCount),
    });
    const wmtsUrl = data.data?.wmtsUrl;
    if (wmtsUrl) {
      const nextConfig = {
        serviceType: "WMTS",
        serviceUrl: wmtsUrl,
        projection: cacheForm.gridSetId,
        minZoom: Number(cacheForm.zoomStart),
        maxZoom: Number(cacheForm.zoomStop),
        enabled: true,
      };
      const existingWmts = form.serviceConfigs.find(
        (service) => service.serviceType === "WMTS" && getGeoServerLayerNameFromUrl(service.serviceUrl) === cacheForm.layerName,
      );
      if (existingWmts) {
        Object.assign(existingWmts, nextConfig);
      } else {
        const service = { id: createServiceId(), ...nextConfig };
        form.serviceConfigs.push(service);
        activeServiceTab.value = service.id;
      }
    }
    ElMessage.success(ui.cacheSuccess);
    cacheDialogVisible.value = false;
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.cacheFailed);
  } finally {
    cacheSubmitting.value = false;
    pendingCacheService = null;
  }
}

function openGeoserverPicker(service) {
  pendingService = service;
  geoserverUrl.value = "/geoserver";
  geoserverServiceType.value = service.serviceType || "WMS";
  geoserverLayers.value = [];
  geoserverFilter.value = "";
  geoserverPage.value = 1;
  geoserverPickerVisible.value = true;
}

async function handleFetchGeoserverLayers() {
  geoserverLoading.value = true;
  geoserverLayers.value = [];
  geoserverPage.value = 1;
  try {
    const { data } = await fetchGeoserverLayers({
      geoserverUrl: geoserverUrl.value,
      serviceType: geoserverServiceType.value,
    });
    geoserverLayers.value = data.data || [];
    if (!geoserverLayers.value.length) {
      ElMessage.info(ui.geoserverEmpty);
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.geoserverFetchFailed);
  } finally {
    geoserverLoading.value = false;
  }
}

function selectGeoserverLayer(row) {
  if (!pendingService) {
    geoserverPickerVisible.value = false;
    return;
  }
  const { name, workspace: ws } = row;
  const resolvedWorkspace = ws || name.split(":")[0] || "";
  const basePath = geoserverUrl.value.startsWith("/") ? geoserverUrl.value : "/geoserver";

  if (geoserverServiceType.value === "WMTS") {
    const wmtsWorkspace = resolvedWorkspace || name;
    pendingService.serviceUrl =
      `${basePath}/${wmtsWorkspace}/gwc/service/wmts?layer=${name}&style=&tilematrixset=EPSG:4326&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png`;
  } else {
    pendingService.serviceUrl =
      `${basePath}/wms?service=WMS&version=1.1.1&request=GetMap&layers=${name}&styles=&format=image/png&transparent=true`;
  }
  pendingService.projection = pendingService.projection || "EPSG:4326";
  geoserverPickerVisible.value = false;
  ElMessage.success(`已选择图层：${name}`);
}

async function testLayer(row) {
  try {
    const messages = [];
    for (const service of row.serviceConfigs) {
      const { data } = await validateMapLayerService({
        serviceUrl: service.serviceUrl,
        layerType: service.serviceType,
      });
      messages.push(`${service.serviceType}: ${data.data.message}`);
      if (!data.data.ok) {
        ElMessage.warning(messages[messages.length - 1]);
        return;
      }
    }
    ElMessage.success(messages.join(" | "));
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.testFailed);
  }
}

loadLayers();
</script>
