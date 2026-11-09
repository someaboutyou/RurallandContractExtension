<template>
  <div
    v-loading.lock="isValidatingAddGeometry"
    class="parcel-info-panel"
    :class="{ 'is-fullscreen': isParcelFullscreen }"
    element-loading-text="正在核验新增地块图形，请稍候..."
    element-loading-background="rgba(255, 255, 255, 0.72)"
  >
    

    <div class="parcel-toolbar">
      <div class="parcel-toolbar-main">
        <el-button
          type="warning"
          plain
          size="small"
          :disabled="actionDisabled"
          @click="emit('swap-parcels')"
        >
          地块互换
        </el-button>
        <el-button
          type="success"
          plain
          size="small"
          :disabled="actionDisabled"
          @click="beginAddParcelMode"
        >
          新增地块
        </el-button>
        <el-button
          plain
          size="small"
          :disabled="actionDisabled || parcels.length === 0"
          @click="handleSplitParcel"
        >
          切割地块
        </el-button>
        <el-button
          type="danger"
          plain
          size="small"
          :disabled="actionDisabled || parcels.length === 0"
          @click="handleRemoveParcel"
        >
          移除地块
        </el-button>
        <span v-if="isResultLocked" class="toolbar-lock-hint">（只读）</span>
        <span class="toolbar-fullscreen-slot">
          <el-button
            size="small"
            :type="isParcelFullscreen ? 'primary' : 'default'"
            @click="toggleParcelFullscreen"
          >
            {{ isParcelFullscreen ? "退出全屏" : "地图全屏" }}
          </el-button>
        </span>
      </div>

      <div v-if="addModeActive" class="parcel-toolbar-add-mode">
        <label class="upload-button">
          <input
            class="upload-input"
            type="file"
            accept=".zip,application/zip"
            @change="handleShpUpload"
          />
          <span>上传 SHP</span>
        </label>
        <el-button size="small" @click="cancelAddParcelMode">取消新增</el-button>
        <span class="add-mode-hint">
          请直接在左侧地图上绘制新增地块，或上传 `shp(zip)` 图形。
        </span>
      </div>

      <div v-if="splitModeActive" class="parcel-toolbar-split-mode">
        <span class="mode-chip">切割地块：{{ splitSourceParcel?.dkbm || "-" }}</span>
        <el-button
          size="small"
          :type="splitForm.splitMethod === 'geometry' ? 'primary' : 'default'"
          @click="switchSplitMethod('geometry')"
        >
          按图形切割
        </el-button>
        <template v-if="splitForm.splitMethod === 'geometry'">
          <el-button
            size="small"
            :disabled="!splitSourceHasGeometry"
            @click="$refs.splitShpInput.click()"
          >
            上传 SHP
          </el-button>
          <input
            ref="splitShpInput"
            type="file"
            accept=".zip,application/zip"
            style="display: none"
            @change="handleSplitShpUpload"
          />
          
          <el-button
            size="small"
            :disabled="!splitSourceHasGeometry"
            :type="splitDrawMode === 'line' ? 'primary' : 'default'"
            @click="startSplitDrawMode('line')"
          >
            绘图切割线
          </el-button>
          <el-button
            size="small"
            :disabled="!splitSourceHasGeometry"
            :type="splitDrawMode === 'polygon' ? 'primary' : 'default'"
            @click="startSplitDrawMode('polygon')"
          >
            绘图切割面
          </el-button>
          <el-button size="small" :disabled="!splitGeometry" @click="clearSplitDraft">
            清除图形
          </el-button>
        </template>
        <el-button
          size="small"
          :type="splitForm.splitMethod === 'area' ? 'primary' : 'default'"
          @click="switchSplitMethod('area')"
        >
          按面积切割
        </el-button>
        <el-button
          v-if="splitForm.splitMethod === 'area'"
          size="small"
          :type="splitForm.splitBasis === 'edge' ? 'primary' : 'default'"
          @click="startEdgePickMode"
        >
          点选基准边
        </el-button>
        <el-button
          v-if="splitForm.splitMethod === 'area'"
          size="small"
          type="primary"
          :disabled="!splitForm.dkbm || !splitSourceHasGeometry"
          @click="splitConfigDialogVisible = true"
        >
          切割设置
        </el-button>
        <el-button size="small" @click="cancelSplitParcelMode">取消切割</el-button>
        <span class="add-mode-hint">
          先在右侧列表选择待切割地块，再通过上传、绘图或面积方向方式完成切割。
        </span>
      </div>
    </div>

    <el-alert
      v-if="addModeActive"
      :title="addModeAlertText"
      :type="addModeAlertType"
      :closable="false"
      show-icon
      class="add-mode-alert"
    />
    <el-alert
      v-if="splitModeActive"
      :title="splitModeAlertText"
      :type="splitModeAlertType"
      :closable="false"
      show-icon
      class="add-mode-alert"
    />

    

    <div class="parcel-layout">
      <div class="parcel-map-container" :class="{ 'is-add-mode': addModeActive, 'is-split-mode': splitModeActive }">
        <div ref="mapRoot" class="parcel-map"></div>
        <div class="basemap-switch">
          <el-select
            v-model="activeBasemap"
            size="small"
            placeholder="底图"
            :teleported="!isParcelFullscreen"
            @change="handleBasemapChange"
          >
            <el-option
              v-for="opt in basemapOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>

        <div v-if="addModeActive" class="map-add-overlay">
          <div class="map-add-badge">新增地块模式</div>
          <div class="map-add-meta">
            <span>图形面积：{{ addGeometryAreaText }}</span>
            <span>核验状态：{{ addGeometryValidationText }}</span>
            <span v-if="uploadedFilename">文件：{{ uploadedFilename }}</span>
          </div>
        </div>
        <div v-if="splitModeActive" class="map-add-overlay">
          <div class="map-add-badge split-badge">切割地块模式</div>
          <div class="map-add-meta">
            <span>切割方式：{{ splitForm.splitMethod === "geometry" ? "按图形切割" : "按面积切割" }}</span>
            <span>源地块：{{ splitSourceParcel?.dkbm || "-" }}</span>
            <span v-if="splitForm.splitMethod === 'geometry'">
              图形状态：{{ splitGeometry ? "已就绪" : "待提供" }}
            </span>
            <span v-if="splitUploadedFilename">文件：{{ splitUploadedFilename }}</span>
            <span v-if="splitForm.splitMethod === 'area'">预计剩余：{{ splitRemainingArea }} 亩</span>
          </div>
        </div>
      </div>
        <!-- Validation loading overlay on map -->
        <div v-if="splitPreviewLoading" class="split-validation-overlay">
          <div class="split-validation-spinner">
            <el-icon class="is-loading" :size="32"><Loading /></el-icon>
            <span>正在验证切割图形...</span>
          </div>
        </div>

      <div class="parcel-list">
        <el-table
          :data="parcels"
          border
          size="small"
          highlight-current-row
          v-loading="parcelsLoading"
          :row-class-name="parcelTableRowClassName"
          @row-click="selectParcel"
          :max-height="parcelTableMaxHeight"
        >
          <el-table-column label="状态" width="92">
            <template #default="{ row }">
              <el-tooltip
                v-if="parcelChangeTip(row)"
                effect="light"
                placement="top-start"
                :content="parcelChangeTip(row)"
              >
                <el-tag :type="parcelStatusType(row)" size="small">{{ parcelStatusLabel(row) }}</el-tag>
              </el-tooltip>
              <el-tag v-else :type="parcelStatusType(row)" size="small">{{ parcelStatusLabel(row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="dkbm" label="地块编码" width="140" />
          <el-table-column prop="dkmc" label="地块名称" min-width="120" />
          <el-table-column label="面积(亩)" width="100">
            <template #default="{ row }">
              <!-- scmj 库内口径 ㎡；界面列「亩」→ 换算显示（2026-11-04 统一） -->
              <span :class="parcelChangedClass(row)">{{ row.scmj == null ? "-" : (sqmToMu(row.scmj) ?? "-") }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类别" width="90">
            <template #default="{ row }">{{ parcelCategoryLabel(row.dklb) || row.dklb || "-" }}</template>
          </el-table-column>
          <el-table-column label="是否基本农田" width="100">
            <template #default="{ row }">{{ row.sfjbnt === "1" ? "是" : "否" }}</template>
          </el-table-column>
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <!-- 待保存的新增地块：给一个「保存」按钮，把**这一行**单独落库。
                   ⛔ 与底部「保存调查结果」的区别（也是它存在的理由）：只写这一块地，
                   不校验承包方必填项、不推进调查状态、不提交表单里其余待保存操作。
                   落库后界址点 / 界址线按钮才会解锁（界址点由库里的地块图形推导）。 -->
              <el-button
                v-if="isUnsavedAddedParcel(row)"
                link
                type="primary"
                size="small"
                :disabled="actionDisabled"
                :loading="persistingDkbm === row.dkbm"
                @click.stop="emit('persist-parcel', row)"
              >
                保存
              </el-button>
              <el-button
                v-else-if="parcelActionLabel(row)"
                link
                type="danger"
                size="small"
                :disabled="parcelActionDisabled(row)"
                :loading="rollbackChangeLoadingId === parcelRollbackChangeId(row)"
                @click.stop="handleParcelAction(row)"
              >
                {{ parcelActionLabel(row) }}
              </el-button>
              <span v-else class="parcel-row-action-placeholder">-</span>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="selectedParcel" class="parcel-detail" :class="{ 'is-removed': isHistoricalParcel(selectedParcel) }">
          <div class="parcel-detail-title">
            <span>{{ selectedParcel.dkmc || '地块详情' }}</span>
            <!-- ⛔ 界址点 / 界址线由**库里的地块图形**推导（后端 load_parcel_rings 直接读
                 survey_dk_result.geom），所以"还没落库"的行（新增地块 / 切割生成 /
                 互换换入这些待保存预览）点了只会拿到 404。这里与后端
                 `_ensure_parcel_in_batch` 的准入同源先挡住，并把原因放到 tooltip 上，
                 不许出现"界面能点、接口拒绝"的假故障。 -->
            <el-tooltip :content="boundaryBlockedReason" :disabled="!boundaryBlockedReason" placement="top">
              <span class="boundary-entry-wrap">
                <el-button
                  type="primary"
                  plain
                  size="small"
                  :disabled="actionDisabled || Boolean(boundaryBlockedReason)"
                  @click="openBoundaryDialog"
                >
                  界址点 / 界址线维护
                </el-button>
              </span>
            </el-tooltip>
          </div>
          <el-form label-position="left" label-width="104px" size="small" :disabled="isHistoricalParcel(selectedParcel)">
            <div class="parcel-detail-grid">
              <el-form-item label="地块编码">
                <el-input :model-value="selectedParcel.dkbm" disabled />
              </el-form-item>
              <el-form-item label="地块名称">
                <el-input v-model="selectedParcel.dkmc" placeholder="请输入地块名称" />
              </el-form-item>
            </div>
            <div class="parcel-detail-grid">
              <el-form-item label="实测面积（亩）">
                <!-- scmj 库内口径 ㎡，界面输入/显示亩：显示 ÷666.67、编辑 ×666.67（2026-11-04 统一） -->
                <el-input-number
                  :model-value="sqmToMu(selectedParcel.scmj)"
                  :min="0"
                  :precision="2"
                  style="width: 100%"
                  @update:model-value="selectedParcel.scmj = $event == null ? null : muToSqm($event)"
                />
              </el-form-item>
              <el-form-item label="合同面积（亩）">
                <el-input-number
                  :model-value="sqmToMu(selectedParcel.htmj)"
                  :min="0"
                  :precision="2"
                  style="width: 100%"
                  @update:model-value="selectedParcel.htmj = $event == null ? null : muToSqm($event)"
                />
              </el-form-item>
            </div>
            <div class="parcel-detail-grid">
              <el-form-item label="所有权性质">
                <el-select v-model="selectedParcel.syqxz" style="width: 100%" clearable>
                  <el-option v-for="item in ownershipOptions" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="地块类别">
                <el-select v-model="selectedParcel.dklb" style="width: 100%" clearable>
                  <el-option v-for="item in parcelCategoryOptions" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
            </div>
            <div class="parcel-detail-grid">
              <el-form-item label="土地利用类型">
                <el-select v-model="selectedParcel.tdlylx" style="width: 100%" clearable>
                  <el-option v-for="(label, code) in tdlylxMap" :key="code" :label="label" :value="code" />
                </el-select>
              </el-form-item>
              <el-form-item label="地力等级">
                <el-select v-model="selectedParcel.dldj" style="width: 100%" clearable>
                  <el-option v-for="item in landGradeOptions" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
            </div>
            <div class="parcel-detail-grid">
              <el-form-item label="土地用途">
                <el-select v-model="selectedParcel.tdyt" style="width: 100%" clearable>
                  <el-option v-for="item in landUseOptions" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="是否基本农田">
                <el-select v-model="selectedParcel.sfjbnt" style="width: 100%" clearable>
                  <el-option label="是" value="1" />
                  <el-option label="否" value="0" />
                </el-select>
              </el-form-item>
            </div>
            <div class="parcel-detail-grid">
              <el-form-item label="东至">
                <el-input v-model="selectedParcel.dkdz" placeholder="东至" />
              </el-form-item>
              <el-form-item label="西至">
                <el-input v-model="selectedParcel.dkxz" placeholder="西至" />
              </el-form-item>
            </div>
            <div class="parcel-detail-grid">
              <el-form-item label="南至">
                <el-input v-model="selectedParcel.dknz" placeholder="南至" />
              </el-form-item>
              <el-form-item label="北至">
                <el-input v-model="selectedParcel.dkbz" placeholder="北至" />
              </el-form-item>
            </div>
            <div class="parcel-detail-grid">
              <el-form-item label="指界人">
                <el-input v-model="selectedParcel.zjrxm" placeholder="请输入指界人" />
              </el-form-item>
              <el-form-item label="地块备注">
                <el-input
                  v-model="selectedParcel.dkbzxx"
                  type="textarea"
                  :rows="2"
                  maxlength="300"
                  show-word-limit
                  placeholder="请输入地块备注"
                />
              </el-form-item>
            </div>
            <div class="parcel-detail-grid">
              <el-form-item label="承包方">
                <el-input :model-value="selectedParcel.cbfmc || '-'" disabled />
              </el-form-item>
              <el-form-item label="合同编码">
                <el-input :model-value="selectedParcel.cbhtbm || '-'" disabled />
              </el-form-item>
            </div>
            <el-form-item v-if="selectedParcel.changeReason" label="变更原因">
              <el-input :model-value="selectedParcel.changeReason" disabled type="textarea" :rows="2" />
            </el-form-item>
          </el-form>
        </div>

        <div v-if="addModeActive && addValidation.checked && addValidation.overlaps.length" class="overlap-list">
          <div class="overlap-list-title">重叠地块</div>
          <div
            v-for="(item, index) in addValidation.overlaps"
            :key="`${item.source}-${item.dkbm || item.cbfmc || index}`"
            class="overlap-item"
          >
            <div class="overlap-item-main">
              <span class="overlap-code">{{ item.dkbm || "-" }}</span>
              <span class="overlap-name">{{ item.dkmc || "未命名地块" }}</span>
            </div>
            <div class="overlap-item-sub">
              <span>{{ item.cbfmc || item.cbfbm || "未知承包方" }}</span>
              <span>重叠约 {{ formatArea(item.overlapAreaMu) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Split config dialog -->
    <el-dialog
      v-model="splitConfigDialogVisible"
      title="切割设置"
      width="680px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <!-- Geometry mode content -->
      <template v-if="splitForm.splitMethod === 'geometry'">
        <div v-if="splitPreviewLoading" class="split-preview-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在验证切割图形...</span>
        </div>
        <template v-else-if="splitPreviewGenerated.length">
          <div class="split-original-parcel">
            <el-tag type="info" size="small">历史</el-tag>
            <span class="split-original-code">{{ splitSourceParcel?.dkbm || "-" }}</span>
            <span class="split-original-name">{{ splitSourceParcel?.dkmc || "-" }}</span>
            <span class="split-original-area">{{ splitSourceAreaMu }} 亩</span>
          </div>
          <el-tabs v-model="activeSplitTab" type="card" class="split-parcel-tabs">
            <el-tab-pane
              v-for="(parcel, index) in splitPreviewGenerated"
              :key="parcel.dkbm"
              :label="'地块 ' + (index + 1)"
              :name="String(index)"
            >
              <el-form label-position="top" size="small">
                <div class="split-config-grid">
                  <el-form-item label="地块编码">
                    <el-input :model-value="parcel.dkbm" disabled />
                  </el-form-item>
                  <el-form-item label="地块名称" required>
                    <el-input
                      v-model="splitParcelSettings[index].dkmc"
                      maxlength="50"
                      placeholder="请输入地块名称"
                    />
                  </el-form-item>
                </div>
                <div class="split-config-grid">
                  <el-form-item label="实测面积（亩）">
                    <!-- 预览返回的 scmj 已是 ㎡（后端统一口径），显示换算成亩 -->
                    <el-input :model-value="sqmToMu(parcel.scmj) ?? 0" disabled />
                  </el-form-item>
                  <el-form-item label="合同面积（亩）">
                    <!-- htmj 设置值按 ㎡ 存储（提交口径），输入亩、换算存储（2026-11-04 统一） -->
                    <el-input-number
                      :model-value="sqmToMu(splitParcelSettings[index].htmj)"
                      :min="0"
                      :precision="2"
                      style="width: 100%"
                      @update:model-value="splitParcelSettings[index].htmj = $event == null ? null : muToSqm($event)"
                    />
                  </el-form-item>
                </div>
                <el-form-item label="土地利用类型">
                  <el-select v-model="splitParcelSettings[index].tdlylx" style="width: 100%" clearable>
                    <el-option
                      v-for="(label, code) in tdlylxMap"
                      :key="code"
                      :label="label"
                      :value="code"
                    />
                  </el-select>
                </el-form-item>
                <div class="split-config-grid">
                  <el-form-item label="东至">
                    <el-input v-model="splitParcelSettings[index].dkdz" placeholder="东至" />
                  </el-form-item>
                  <el-form-item label="西至">
                    <el-input v-model="splitParcelSettings[index].dkxz" placeholder="西至" />
                  </el-form-item>
                </div>
                <div class="split-config-grid">
                  <el-form-item label="南至">
                    <el-input v-model="splitParcelSettings[index].dknz" placeholder="南至" />
                  </el-form-item>
                  <el-form-item label="北至">
                    <el-input v-model="splitParcelSettings[index].dkbz" placeholder="北至" />
                  </el-form-item>
                </div>
                <el-form-item label="承包方">
                  <el-input :model-value="splitSourceParcel?.cbfmc || '-'" disabled />
                </el-form-item>
              </el-form>
            </el-tab-pane>
          </el-tabs>
          <el-form-item label="切割原因" class="split-reason-field">
            <el-input
              v-model="splitForm.reason"
              type="textarea"
              :rows="2"
              maxlength="500"
              show-word-limit
              placeholder="请输入切割原因"
            />
          </el-form-item>
        </template>
      </template>
      <!-- Area mode content -->
      <template v-else>
        <el-form label-position="top" size="small">
          <div class="split-config-grid">
            <el-form-item label="新地块编码" required>
              <el-input v-model="splitForm.newDkbm" maxlength="19" placeholder="请输入新地块编码">
                <template #append>
                  <el-button :loading="generatingSplitCode" @click="handleGenerateSplitCode">自动生成</el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="新地块名称" required>
              <el-input v-model="splitForm.newDkmc" maxlength="50" placeholder="例如：切割地块A" />
            </el-form-item>
          </div>
          <div class="split-config-grid">
            <el-form-item label="切割基准" required>
              <el-radio-group v-model="splitForm.splitBasis" size="small" @change="handleSplitBasisChange">
                <el-radio-button value="direction">按四方向</el-radio-button>
                <el-radio-button value="edge">按边平行</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </div>
          <div class="split-config-grid">
            <el-form-item label="切出面积（亩）" required>
              <el-input-number
                v-model="splitForm.newScmj"
                :min="0.01"
                :max="splitMaxArea"
                :precision="2"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item v-if="splitForm.splitBasis === 'direction'" label="切割方向" required>
              <el-select v-model="splitForm.splitDirection" style="width: 100%">
                <el-option label="从东侧切割" value="east" />
                <el-option label="从西侧切割" value="west" />
                <el-option label="从南侧切割" value="south" />
                <el-option label="从北侧切割" value="north" />
              </el-select>
            </el-form-item>
            <el-form-item v-else label="切割基准边（切出块与所选边相邻）" required>
              <div class="edge-pick-row">
                <el-button
                  size="small"
                  :type="edgePickActive ? 'primary' : 'default'"
                  @click="splitConfigDialogVisible = false; startEdgePickMode()"
                >
                  {{ splitForm.edgeIndex === null ? "去地图选边" : "重新选边" }}
                </el-button>
                <span class="edge-pick-result">
                  {{ splitForm.edgeIndex === null ? "未选择" : `第 ${splitForm.edgeIndex + 1} 条边` }}
                </span>
                <el-button
                  v-if="splitForm.edgeIndex !== null"
                  size="small"
                  text
                  @click="clearEdgePickSelection"
                >
                  清除
                </el-button>
              </div>
              <div v-if="splitForm.edgeIndex === null" class="edge-pick-hint">
                点击后将关闭本弹窗，请在地图上点击要平行的边，选完再打开切割设置。
              </div>
            </el-form-item>
          </div>
          <el-form-item label="切割原因">
            <el-input
              v-model="splitForm.reason"
              type="textarea"
              :rows="3"
              maxlength="500"
              show-word-limit
              placeholder="请输入切割原因"
            />
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="splitConfigDialogVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="submittingSplitParcel"
          :disabled="!splitCanSubmit"
          @click="submitSplitParcel"
        >
          确认切割
        </el-button>
      </template>
    </el-dialog>
<AddParcelDialog
      ref="addParcelDialog"
      :batch-id="batchId"
      :contractor-uid="contractorUid"
      :existing-parcel-codes="parcels.map((item) => item?.dkbm).filter(Boolean)"
      @done="handleAddParcelDone"
      @closed="handleAddParcelDialogClosed"
    />
    <BoundaryMaintainDialog
      ref="boundaryDialog"
      :can-manage="canManage"
      @saved="handleBoundarySaved"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import AddParcelDialog from "./AddParcelDialog.vue";
import BoundaryMaintainDialog from "./BoundaryMaintainDialog.vue";
import { useDialogMap } from "../../composables/useDialogMap";
import { useDictionary } from "../../composables/useDictionary";
import { useParcelDraftMap } from "../../composables/survey/useParcelDraftMap";
import { useSplitParcel } from "../../composables/survey/useSplitParcel";
import { useAddParcelGeometry } from "../../composables/survey/useAddParcelGeometry";
import {
  tdlylxMap,
  formatArea,
  isCurrentParcel,
  isHistoricalParcel,
  isRemovedParcel,
  isSplitSourceParcel,
  isSplitGeneratedParcel,
  isSwappedInParcel,
  isSwappedOutParcel,
  isAddedParcel,
  parcelStatusLabel,
  parcelStatusType,
  parcelRowClassName,
  parcelChangedClass,
} from "../../utils/parcelStatusHelpers";
import { sqmToMu, muToSqm } from "../../utils/areaUnits";

const { options: ownershipOptions } = useDictionary("nyt2539_c06_ownership_property");
const { options: parcelCategoryOptions, labelOf: parcelCategoryLabel } = useDictionary("nyt2539_c07_parcel_category");
const { options: landGradeOptions } = useDictionary("nyt2539_c08_land_grade");
const { options: landUseOptions } = useDictionary("nyt2539_c09_land_use");

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  parcels: { type: Array, default: () => [] },
  // 外部（承包地块管理双击）指定的地块编码：清单行加重显示，地图定位到该地块。
  highlightDkbm: { type: String, default: "" },
  // 服务端已落库的地块编码（由 ContractorResultDialog 在 loadSurveyParcels 时记下）。
  persistedDkbms: { type: Array, default: () => [] },
  parcelsLoading: { type: Boolean, default: false },
  canManage: { type: Boolean, default: false },
  isResultLocked: { type: Boolean, default: false },
  savedSwapRecords: { type: Array, default: () => [] },
  savedSplitRecords: { type: Array, default: () => [] },
  savedRemoveRecords: { type: Array, default: () => [] },
  canRollbackSavedParcelChange: { type: Boolean, default: false },
  rollbackChangeLoadingId: { type: [Number, String], default: null },
  // 正在被单独落库的地块编码（操作列「保存」按钮的 loading 用）。
  // 实际落库由父组件调接口完成 —— 本组件只管显示与派发。
  persistingDkbm: { type: String, default: "" },
});

const emit = defineEmits(["swap-parcels", "add-parcel", "split-parcel", "remove-parcel", "rollback-saved-swap", "rollback-saved-split", "undo-pending-remove", "rollback-saved-remove", "persist-parcel", "boundary-saved"]);

const addParcelDialog = ref(null);
const boundaryDialog = ref(null);
const mapRoot = ref(null);
const selectedParcel = ref(null);

// --- 地图全屏 ---
// 面板整体 fixed 铺满视口；进出全屏后必须 updateMapSize，否则 OpenLayers 画布尺寸停留在旧容器。
const isParcelFullscreen = ref(false);
function toggleParcelFullscreen() {
  isParcelFullscreen.value = !isParcelFullscreen.value;
  nextTick(() => draftMap.updateMapSize());
}
function handleFullscreenKeydown(event) {
  if (event.key === "Escape" && isParcelFullscreen.value) toggleParcelFullscreen();
}

// --- Map + draft layer ---
const dialogMap = useDialogMap(mapRoot);
const draftMap = useParcelDraftMap(mapRoot, dialogMap);
const { activeBasemap, basemapOptions } = draftMap;

// --- Shared computed (defined before composables to avoid circular refs) ---
const toolModeActive = computed(() => addModeActive.value || splitModeActive.value);
const actionDisabled = computed(() => !props.canManage || props.isResultLocked || toolModeActive.value);
const parcelTableMaxHeight = computed(() => (
  splitModeActive.value
    ? "340px"
    : (isParcelFullscreen.value ? "calc(100vh - 240px)" : "calc(92vh - 380px)")
));

// --- Split parcel mode ---
const splitResult = useSplitParcel({
  parcels: computed(() => props.parcels),
  draftMap,
  emit,
  props,
});

const {
  splitModeActive,
  splitPreviewLoading,
  splitPreviewGenerated,
  splitParcelSettings,
  activeSplitTab,
  splitConfigDialogVisible,
  splitUploadedFilename,
  splitGeometry,
  splitDrawMode,
  generatingSplitCode,
  submittingSplitParcel,
  splitForm,
  splitSourceParcel,
  splitSourceHasGeometry,
  splitSourceAreaMu,
  splitRemainingArea,
  splitCanSubmit,
  splitModeAlertType,
  splitModeAlertText,
  beginSplitParcelMode,
  cancelSplitParcelMode,
  switchSplitMethod,
  clearSplitDraft,
  handleGenerateSplitCode,
  handleSplitShpUpload,
  startSplitDrawMode,
  submitSplitParcel,
  selectParcelInSplitMode,
  // 按边平行切割
  startEdgePickMode,
  clearEdgePickSelection,
  handleSplitBasisChange,
} = splitResult;

// --- Add parcel geometry mode ---
const addResult = useAddParcelGeometry({
  parcels: computed(() => props.parcels),
  draftMap,
  emit,
  props,
  addParcelDialog,
  selectedParcel,
});

const {
  addModeActive,
  uploadedFilename,
  isValidatingAddGeometry,
  addValidation,
  addModeAlertType,
  addModeAlertText,
  addGeometryAreaText,
  addGeometryValidationText,
  beginAddParcelMode,
  cancelAddParcelMode,
  handleShpUpload,
  handleAddParcelDone,
  handleAddParcelDialogClosed,
} = addResult;

// --- Parcel change records (need props/emit context) ---
function findSavedSwapRecord(parcel) {
  return (props.savedSwapRecords || []).find((item) => (item.swappedIn || []).includes(parcel?.dkbm)) || null;
}

function findSavedSplitRecord(parcel) {
  return (props.savedSplitRecords || []).find((item) => item.originalDkbm === parcel?.dkbm) || null;
}

function findSavedRemoveRecord(parcel) {
  if (!isRemovedParcel(parcel) || parcel._pending) return null;
  return (props.savedRemoveRecords || []).find((item) => item.removedDkbm === parcel?.dkbm) || null;
}

// ---- 操作列：「待保存的新增地块」单独落库 ----
//
// 判据与界址点闸门（boundaryBlockedReason）**同源**：都是"这一行在库里还没有"。
// ⛔ 不能只看 `changeType === 'add_parcel'` —— 落库后的新增地块同样是这个值，必须叠加
//   `_pending`（前端预览行标记）与 `persistedDkbms`（服务端返回过的编码）才区分得开。
// 落库成功后父组件会重拉服务端 + 重放剩余预览行，`_pending` 消失，按钮自动回到「-」。
function isUnsavedAddedParcel(parcel) {
  if (!parcel?.dkbm) return false;
  if (parcel.changeType !== "add_parcel") return false;
  if (!parcel._pending) return false;
  return !props.persistedDkbms.includes(parcel.dkbm);
}

function parcelRollbackChangeId(parcel) {
  if (isRemovedParcel(parcel) && parcel._pending) return undefined;
  return findSavedSplitRecord(parcel)?.id || findSavedSwapRecord(parcel)?.id || findSavedRemoveRecord(parcel)?.id || null;
}

function parcelActionLabel(parcel) {
  if (findSavedSplitRecord(parcel)) return "撤回切割";
  if (findSavedSwapRecord(parcel)) return "撤回互换";
  if (findSavedRemoveRecord(parcel)) return "撤回移除";
  if (isRemovedParcel(parcel) && parcel._pending && parcel.changeType === "remove_parcel") return "撤回移除";
  return "";
}

function parcelActionDisabled(parcel) {
  if (!parcelActionLabel(parcel)) return true;
  if (toolModeActive.value) return true;
  if (isRemovedParcel(parcel) && parcel._pending && parcel.changeType === "remove_parcel") return !props.canManage || props.isResultLocked;
  if (findSavedRemoveRecord(parcel)) return !props.canRollbackSavedParcelChange;
  return !props.canRollbackSavedParcelChange;
}

function handleParcelAction(parcel) {
  const splitRecord = findSavedSplitRecord(parcel);
  if (splitRecord) {
    emit("rollback-saved-split", splitRecord);
    return;
  }
  const swapRecord = findSavedSwapRecord(parcel);
  if (swapRecord) {
    emit("rollback-saved-swap", swapRecord);
    return;
  }
  const removeRecord = findSavedRemoveRecord(parcel);
  if (removeRecord) {
    emit("rollback-saved-remove", removeRecord);
    return;
  }
  if (isRemovedParcel(parcel) && parcel._pending && parcel.changeType === "remove_parcel") {
    emit("undo-pending-remove", parcel.dkbm);
  }
}

function parcelChangeTip(parcel) {
  if (!parcel?.isChanged && !isSplitSourceParcel(parcel) && !isSplitGeneratedParcel(parcel) && !isSwappedInParcel(parcel) && !isSwappedOutParcel(parcel)) {
    return "";
  }
  const messages = [];
  if (isSplitSourceParcel(parcel)) {
    const splitRecord = findSavedSplitRecord(parcel);
    messages.push(splitRecord ? `该地块已被切割为 ${splitRecord.generatedDkbms.length} 块，当前为历史地块` : "该地块已被切割，当前为历史地块");
  } else if (isSplitGeneratedParcel(parcel)) {
    messages.push("该地块由切割生成，当前为现势地块");
  } else if (isSwappedInParcel(parcel)) {
    const swapRecord = findSavedSwapRecord(parcel);
    messages.push(swapRecord ? `该地块为互换换入，对方承包方：${swapRecord.counterpartyLabel || "-"}` : "该地块为互换换入");
  } else if (isSwappedOutParcel(parcel)) {
    messages.push("该地块已互换换出");
  } else if (isRemovedParcel(parcel)) {
    messages.push("该地块已移除");
  } else if (isAddedParcel(parcel)) {
    messages.push("该地块为新增地块");
  } else {
    messages.push("该地块信息已发生变化");
  }
  if (parcel.changeReason) {
    messages.push(`原因：${parcel.changeReason}`);
  }
  return messages.join("；");
}

// --- Parcel selection ---
function selectParcel(parcel) {
  selectedParcel.value = parcel;
  draftMap.focusParcel(parcel.dkbm);
  selectParcelInSplitMode(parcel);
}

// 当前选中的地块：点击其他记录时加重颜色跟着切换；首次进入用外部指定地块兜底。
const activeParcelDkbm = computed(() => selectedParcel.value?.dkbm || props.highlightDkbm);

// 选中的地块在清单里用加重颜色显示（只改颜色，不改变行高）。
function parcelTableRowClassName(context) {
  const base = parcelRowClassName(context);
  const active = context?.row?.dkbm && context.row.dkbm === activeParcelDkbm.value;
  return [base, active ? "parcel-row-active" : ""].filter(Boolean).join(" ");
}

// --- 界址点 / 界址线维护 ---
//
// ⛔ 入口闸门 vs 后端闸门（`boundary.py::_ensure_parcel_in_batch`）：
//    界址点 / 界址线不是独立录入的，而是**从库里的地块图形推导**出来的
//    （`load_parcel_rings` 直接读 survey_dk_result.geom）。所以一块"只活在前端
//    的待保存预览行"（新增地块 / 切割生成 / 互换换入）在库里既没有地块行、
//    也没有承包方关联行，接口必然 404（事故：新增地块后立刻点维护 → 报
//    "该地块不属于当前承包方"）。这类行必须在这里就挡住，并且说清楚下一步动作。
//
// 判据取"服务端返回过的 dkbm 集合"而不是 `resultStatus === 'added'`：
// 落库后的新增地块 resultStatus 同样是 'added'，靠状态分不出"存没存过"。
const UNSAVED_PARCEL_BOUNDARY_HINT =
  "该地块尚未保存，请先点击「保存调查结果」，保存后即可维护界址点 / 界址线";
const REMOVED_PARCEL_BOUNDARY_HINT = "该地块已移除，不能维护界址点 / 界址线";

const boundaryBlockedReason = computed(() => {
  const parcel = selectedParcel.value;
  if (!parcel?.dkbm) return "";
  if (parcel._pending && !props.persistedDkbms.includes(parcel.dkbm)) {
    // 待保存预览 + 服务端没给过这一行 = 库里还没有这块地。
    // （`_pending` 但服务端给过的行——例如"待保存移除""已保存切割的历史源地块"——
    //   库里仍在，后端放行，这里也放行。）
    return UNSAVED_PARCEL_BOUNDARY_HINT;
  }
  if (parcel.resultStatus === "removed") {
    // 后端对已移除地块的地块行返回"该地块已移除，不能维护界址点 / 界址线"。
    return REMOVED_PARCEL_BOUNDARY_HINT;
  }
  return "";
});

function openBoundaryDialog() {
  const parcel = selectedParcel.value;
  if (!parcel || !parcel.dkbm) {
    ElMessage.warning("请先在右侧列表中选中需要维护的地块");
    return;
  }
  if (boundaryBlockedReason.value) {
    ElMessage.warning(boundaryBlockedReason.value);
    return;
  }
  boundaryDialog.value?.open({
    batchId: props.batchId,
    contractorUid: props.contractorUid,
    dkbm: parcel.dkbm,
  });
}

function handleBoundarySaved({ dkbm }) {
  emit("boundary-saved", { dkbm });
}

function handleSplitParcel() {
  const parcel =
    (isCurrentParcel(selectedParcel.value) ? selectedParcel.value : null) ||
    props.parcels.find((item) => isCurrentParcel(item)) ||
    null;
  if (!parcel) {
    ElMessage.warning("请先在右侧列表中选择需要切割的地块");
    return;
  }
  if (!selectedParcel.value) {
    selectedParcel.value = parcel;
    draftMap.focusParcel(parcel.dkbm);
  }
  beginSplitParcelMode(parcel);
}


function handleRemoveParcel() {
  const parcel = selectedParcel.value;
  if (!parcel || !isCurrentParcel(parcel) || isRemovedParcel(parcel)) {
    ElMessage.warning("请先在右侧列表中选中需要移除的地块");
    return;
  }
  if (isSwappedOutParcel(parcel) || isSwappedInParcel(parcel)) {
    ElMessage.warning("互换的地块不能直接移除，请先撤回互换操作");
    return;
  }
  if (isSplitSourceParcel(parcel) || isSplitGeneratedParcel(parcel)) {
    ElMessage.warning("切割相关的地块不能直接移除，请先撤回切割操作");
    return;
  }
  emit("remove-parcel", parcel.dkbm);
}
function handleBasemapChange(key) {
  draftMap.switchBasemap(key);
}

// --- Lifecycle ---
// 定位当前选中的地块：首次进入用外部指定地块，之后点击哪条记录就定位/高亮哪条。
function focusActiveParcel(list) {
  const preferred = selectedParcel.value?.dkbm || props.highlightDkbm;
  const parcel = preferred ? (list || []).find((item) => item?.dkbm === preferred) : null;
  if (!parcel) return false;
  selectedParcel.value = parcel;
  draftMap.focusParcel(parcel.dkbm);
  return true;
}

async function renderParcelsOnMap(list) {
  await nextTick();
  if (!draftMap.mapReady.value) await draftMap.initMap();
  draftMap.ensureDraftLayer();
  // Wait until the lazy tab and dialog transition have produced a measurable
  // map viewport before calculating the target extent.
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (!mapRoot.value?.clientWidth || !mapRoot.value?.clientHeight) return;
  draftMap.updateMapSize();
  draftMap.loadParcels(list || []);
  // 有选中地块时聚焦该地块；没有选中才把范围适配到本地块全部图形。
  if (focusActiveParcel(list)) return;
  if (list?.length) draftMap.fitToParcels();
}

watch(
  () => props.parcels,
  async (list) => {
    await renderParcelsOnMap(list);
    if (toolModeActive.value && draftMap.draftSource.getFeatures().length) {
      draftMap.fitToDraftGeometry();
    }
  },
  { immediate: false, deep: true },
);

// 外部指定地块变化（例如从列表双击另一块地进入）时重新定位与高亮。
watch(
  () => props.highlightDkbm,
  async (dkbm) => {
    if (!dkbm) return;
    selectedParcel.value = null;
    await renderParcelsOnMap(props.parcels);
  },
);

onMounted(async () => {
  window.addEventListener("keydown", handleFullscreenKeydown);
  await renderParcelsOnMap(props.parcels);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleFullscreenKeydown);
  draftMap.stopDraw();
  splitDrawMode.value = "";
  draftMap.removeDraftLayer();
  draftMap.destroyMap();
});
</script>

<style scoped>
.parcel-info-panel { min-height: 400px; }

.parcel-toolbar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}

.parcel-toolbar-main {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.parcel-toolbar-add-mode {
  align-items: center;
  background: linear-gradient(90deg, #eff6ff, #f8fafc);
  border: 1px dashed #93c5fd;
  border-radius: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 12px;
}

.parcel-toolbar-split-mode {
  align-items: center;
  background: linear-gradient(90deg, #fff7ed, #fffaf3);
  border: 1px dashed #fdba74;
  border-radius: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 12px;
}

.mode-chip {
  align-items: center;
  background: #ffedd5;
  border: 1px solid #fdba74;
  border-radius: 999px;
  color: #9a3412;
  display: inline-flex;
  font-size: 12px;
  font-weight: 700;
  min-height: 28px;
  padding: 0 10px;
}

.upload-button {
  align-items: center;
  background: #dbeafe;
  border: 1px solid #93c5fd;
  border-radius: 8px;
  color: #1d4ed8;
  cursor: pointer;
  display: inline-flex;
  font-size: 13px;
  font-weight: 600;
  min-height: 32px;
  padding: 0 14px;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.upload-button:hover {
  background: #bfdbfe;
  border-color: #60a5fa;
}

.upload-button.disabled {
  background: #f3f4f6;
  border-color: #d1d5db;
  color: #9ca3af;
  cursor: not-allowed;
}

.upload-input {
  display: none;
}

.add-mode-hint {
  color: #475569;
  font-size: 12px;
}

.add-mode-alert {
  margin-bottom: 12px;
}

.toolbar-lock-hint { color: #909399; font-size: 12px; }
.toolbar-fullscreen-slot { margin-left: auto; }

.parcel-layout { display: flex; gap: 12px; height: calc(92vh - 380px); min-height: 450px; }
.parcel-info-panel.is-fullscreen {
  position: fixed;
  inset: 0;
  /* 高于 el-dialog 遮罩（约 2000+），保证铺在最上层 */
  z-index: 3000;
  display: flex;
  flex-direction: column;
  background: #fff;
  padding: 12px 16px;
  overflow: auto;
}
.parcel-info-panel.is-fullscreen .parcel-layout {
  flex: 1;
  height: auto;
  min-height: 0;
}
.parcel-map-container { flex: 0 0 44%; position: relative; min-width: 0; border: 1px solid #ebeef5; border-radius: 4px; overflow: hidden; }
.parcel-map-container.is-add-mode { border-color: #60a5fa; box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.35); }
.parcel-map-container.is-split-mode { border-color: #fb923c; box-shadow: inset 0 0 0 1px rgba(251, 146, 60, 0.35); }
.parcel-map { width: 100%; height: 100%; }
.basemap-switch { position: absolute; top: 8px; right: 8px; z-index: 10; width: 140px; }

.map-add-overlay {
  align-items: flex-start;
  bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  left: 10px;
  position: absolute;
  z-index: 10;
}

.map-add-badge {
  background: rgba(29, 78, 216, 0.94);
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  padding: 6px 10px;
}

.split-badge {
  background: rgba(194, 65, 12, 0.92);
}

.split-validation-overlay {
  align-items: center;
  background: rgba(255, 255, 255, 0.85);
  border-radius: 4px;
  bottom: 0;
  display: flex;
  justify-content: center;
  left: 0;
  position: absolute;
  right: 0;
  top: 0;
  z-index: 20;
}

.split-validation-spinner {
  align-items: center;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  color: #9a3412;
  display: flex;
  font-size: 14px;
  font-weight: 600;
  gap: 10px;
  padding: 16px 24px;
}


.map-add-meta {
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(191, 219, 254, 0.95);
  border-radius: 10px;
  color: #334155;
  display: flex;
  flex-direction: column;
  font-size: 12px;
  gap: 4px;
  max-width: 260px;
  padding: 10px 12px;
}

.parcel-list {
  flex: 1 1 56%;
  width: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding-right: 2px;
}
.parcel-detail { flex-shrink: 0; max-height: 36vh; overflow-y: auto; border-radius: 4px; padding: 10px 12px; border: 1px solid #ebeef5; }
.parcel-detail.is-removed { background: #f4f4f5; }
.parcel-detail-title { color: #303133; font-size: 14px; font-weight: 600; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
/* 被禁用的按钮不触发鼠标事件，tooltip 的触发区要落在外面这层 span 上。 */
.boundary-entry-wrap { display: inline-flex; }
.parcel-detail-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.parcel-detail :deep(.el-form-item) { display: flex; min-height: 32px; margin-bottom: 8px; align-items: center; }
.parcel-detail :deep(.el-form-item__label) { display: flex; float: none; width: 104px; justify-content: flex-end; padding: 0 8px 0 0; font-size: 12px; line-height: 32px; text-align: right; white-space: nowrap; }
.parcel-detail :deep(.el-form-item__content) { flex: 1 1 auto; min-width: 0; margin-left: 0; }
.parcel-detail :deep(.el-input__wrapper),
.parcel-detail :deep(.el-select__wrapper) { min-height: 32px; }
.parcel-detail.is-removed { background: #f4f4f5; border: 1px solid #dcdfe6; padding: 8px; }
.field-changed { background-color: #fdf6ec; padding: 2px 6px; border-radius: 3px; }
.parcel-row-action-placeholder { color: #c0c4cc; }

.split-config-card {
  background: linear-gradient(180deg, #fffaf3, #ffffff);
  border: 1px solid #fed7aa;
  border-radius: 10px;
  flex-shrink: 0;
  padding: 12px;
}

.split-config-title {
  color: #9a3412;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 10px;
}

.split-config-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.edge-pick-row {
  align-items: center;
  display: flex;
  gap: 8px;
  width: 100%;
}
.edge-pick-result {
  color: #475569;
  font-size: 12px;
  white-space: nowrap;
}
.edge-pick-hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
  margin-top: 4px;
}
.split-preview-loading {
  align-items: center;
  color: #9a3412;
  display: flex;
  font-size: 13px;
  gap: 8px;
  justify-content: center;
  padding: 16px 0;
}

.split-original-parcel {
  align-items: center;
  background: #f4f4f5;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  display: flex;
  font-size: 12px;
  gap: 8px;
  margin-bottom: 10px;
  padding: 8px 10px;
}

.split-original-code {
  color: #606266;
  font-weight: 600;
}

.split-original-name {
  color: #909399;
  flex: 1;
}

.split-original-area {
  color: #909399;
}

.split-parcel-tabs {
  margin-bottom: 10px;
}

.split-parcel-tabs :deep(.el-tabs__header) {
  margin-bottom: 8px;
}

.split-parcel-info {
  color: #909399;
  display: flex;
  font-size: 12px;
  gap: 16px;
  margin-top: 4px;
}

.split-reason-field {
  margin-bottom: 0;
}

.overlap-list {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
}

.overlap-list-title { color: #9a3412; font-size: 13px; font-weight: 700; }
.overlap-item { border-top: 1px dashed #fdba74; padding-top: 8px; }
.overlap-item:first-of-type { border-top: none; padding-top: 0; }
.overlap-item-main, .overlap-item-sub { display: flex; gap: 10px; justify-content: space-between; }
.overlap-item-main { align-items: center; }
.overlap-code { color: #9a3412; font-size: 12px; font-weight: 700; }
.overlap-name { color: #7c2d12; flex: 1; font-size: 13px; text-align: right; }
.overlap-item-sub { color: #9a3412; font-size: 12px; margin-top: 6px; }

.parcel-list :deep(.el-table__row.parcel-row-removed > .el-table__cell) {
  background-color: #f4f4f5;
  color: #606266;
}

.parcel-list :deep(.el-table__row.parcel-row-removed.current-row > .el-table__cell),
.parcel-list :deep(.el-table__row.parcel-row-removed:hover > .el-table__cell) {
  background-color: #e9e9eb;
}

/* 选中地块：只改底色和文字颜色，不改变行高（历史地块也照此强调）。 */
.parcel-list :deep(.el-table__row.parcel-row-active > .el-table__cell),
.parcel-list :deep(.el-table__row.parcel-row-active.current-row > .el-table__cell),
.parcel-list :deep(.el-table__row.parcel-row-active:hover > .el-table__cell) {
  background-color: #ffd591;
  color: #8a3b00;
}

.parcel-detail.is-removed :deep(.el-descriptions__body),
.parcel-detail.is-removed :deep(.el-descriptions__label),
.parcel-detail.is-removed :deep(.el-descriptions__content) {
  background-color: #f4f4f5;
}

@media (max-width: 960px) {
  .parcel-layout {
    flex-direction: column;
    height: auto;
  }

  .parcel-map-container {
    min-height: 420px;
  }

  .parcel-list {
    width: 100%;
    flex: none;
  }

  .split-config-grid {
    grid-template-columns: 1fr;
  }
}
</style>



