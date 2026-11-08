<template>
  <el-dialog
    :model-value="modelValue"
    title="数据初始化"
    width="760px"
    top="8vh"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="init-head">
      已勾选 <strong>{{ rows.length }}</strong> 个承包地块，初始化仅对勾选地块生效。
    </div>

    <el-tabs v-model="activeTab" class="init-tabs">
      <el-tab-pane label="基础信息" name="basic">
        <div class="init-grid">
          <div v-for="field in fields" :key="field.key" class="init-row">
            <el-checkbox v-model="enabled[field.key]" class="init-check">
              {{ field.label }}
            </el-checkbox>
            <el-select
              v-model="values[field.key]"
              :disabled="!enabled[field.key]"
              clearable
              filterable
              placeholder="请选择"
              style="width: 100%"
            >
              <el-option
                v-for="option in field.options"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>

          <div class="init-row">
            <el-checkbox v-model="enabled.awareArea" class="init-check">确权面积</el-checkbox>
            <el-select
              v-model="values.awareArea"
              :disabled="!enabled.awareArea"
              placeholder="请选择初始化方式"
              style="width: 100%"
            >
              <el-option label="按实测面积" value="actual" />
              <el-option label="按合同面积" value="contract" />
            </el-select>
          </div>

          <div class="init-row">
            <el-checkbox v-model="enabled.comment" class="init-check">地块备注</el-checkbox>
            <el-input
              v-model="values.comment"
              :disabled="!enabled.comment"
              maxlength="300"
              placeholder="请输入地块备注"
            />
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="调查信息" name="survey">
        <div class="init-grid">
          <div class="init-row">
            <el-checkbox v-model="enabled.surveyPerson" class="init-check">调查员</el-checkbox>
            <el-input
              v-model="values.surveyPerson"
              :disabled="!enabled.surveyPerson"
              maxlength="50"
              placeholder="请输入调查员"
            />
          </div>
          <div class="init-row">
            <el-checkbox v-model="enabled.surveyDate" class="init-check">调查日期</el-checkbox>
            <el-date-picker
              v-model="values.surveyDate"
              :disabled="!enabled.surveyDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="请选择调查日期"
              style="width: 100%"
            />
          </div>
          <div class="init-row">
            <el-checkbox v-model="enabled.surveyNote" class="init-check">调查记事</el-checkbox>
            <el-input
              v-model="values.surveyNote"
              :disabled="!enabled.surveyNote"
              maxlength="300"
              placeholder="请输入调查记事"
            />
          </div>
          <div class="init-row">
            <el-checkbox v-model="enabled.checkPerson" class="init-check">审核员</el-checkbox>
            <el-input
              v-model="values.checkPerson"
              :disabled="!enabled.checkPerson"
              maxlength="50"
              placeholder="请输入审核员"
            />
          </div>
          <div class="init-row">
            <el-checkbox v-model="enabled.checkDate" class="init-check">审核日期</el-checkbox>
            <el-date-picker
              v-model="values.checkDate"
              :disabled="!enabled.checkDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="请选择审核日期"
              style="width: 100%"
            />
          </div>
          <div class="init-row">
            <el-checkbox v-model="enabled.checkOpinion" class="init-check">审核意见</el-checkbox>
            <el-input
              v-model="values.checkOpinion"
              :disabled="!enabled.checkOpinion"
              maxlength="300"
              placeholder="请输入审核意见"
            />
          </div>
          <div class="init-row init-row-tall">
            <el-checkbox v-model="enabled.referPerson" class="init-check">指界人</el-checkbox>
            <div class="init-inline">
              <el-input
                v-model="values.referPerson"
                :disabled="!enabled.referPerson || referPersonByOwner"
                maxlength="100"
                placeholder="请输入指界人"
              />
              <el-checkbox v-model="referPersonByOwner" :disabled="!enabled.referPerson">
                以地块当前承包方为指界人
              </el-checkbox>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="地块编码与四至获取" name="code">
        <div class="init-grid">
          <div class="init-row init-row-tall">
            <el-checkbox v-model="codeEnabled" class="init-check">地块编码</el-checkbox>
            <div class="code-inline">
              <el-radio-group v-model="codeMode" :disabled="!codeEnabled">
                <el-radio label="all">全部重新生成</el-radio>
                <el-radio label="merge">重编合并部分</el-radio>
              </el-radio-group>
              <el-checkbox v-model="codeSortByPosition" :disabled="!codeEnabled">
                地块编码从上往下从左往右排序
              </el-checkbox>
              <el-checkbox v-model="codeKeepSurveyNumber" :disabled="!codeEnabled">
                发包方编码 + 调查编码
              </el-checkbox>
            </div>
          </div>
          <div class="init-row">
            <el-checkbox v-model="trimNeighborNote" class="init-check">
              获取四至（取括号前的内容）
            </el-checkbox>
            <span class="init-label-sub">去除四至中括号及其后的说明文字</span>
          </div>
          <div class="init-row">
            <el-checkbox v-model="fillNeighbors" class="init-check">
              获取地块周边相邻地块
            </el-checkbox>
            <span class="init-label-sub">按空间相邻关系把周边承包方名称写入四至</span>
          </div>
        </div>
        <div class="sheet-tip">
          地块编码按所选地块所属发包方的全部地块统一重编；四至获取仅作用于勾选地块。
        </div>
      </el-tab-pane>
      <el-tab-pane label="图幅编号" name="sheet">
        <div class="init-grid">
          <div class="init-row">
            <span class="init-label">比例尺</span>
            <el-select v-model="sheetScale" style="width: 100%">
              <el-option label="1:2000（1km 格网）" value="1:2000" />
              <el-option label="1:1000（500m 格网）" value="1:1000" />
              <el-option label="1:500（250m 格网）" value="1:500" />
            </el-select>
          </div>
          <div class="init-row">
            <span class="init-label">编号顺序</span>
            <el-radio-group v-model="sheetOrder">
              <el-radio label="yx">Y-X（默认）</el-radio>
              <el-radio label="xy">X-Y</el-radio>
            </el-radio-group>
          </div>
          <div class="init-row">
            <span class="init-label">取点方式</span>
            <el-checkbox v-model="sheetInitialAll">
              初始化全部图幅编号（长边加密取点）
            </el-checkbox>
          </div>
        </div>
        <div class="sheet-tip">
          按勾选地块的投影坐标计算公里格网图幅编号；未勾选「初始化全部图幅编号」时取图形顶点与外接矩形角点，无图形地块将跳过。
        </div>
      </el-tab-pane>
      <el-tab-pane label="界址初始化" name="boundary">
        <div class="init-grid">
          <div class="init-row">
            <span class="init-label">界标类型</span>
            <el-select v-model="boundaryMarkType" clearable placeholder="请选择" style="width: 100%">
              <el-option
                v-for="option in markerOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>
          <div class="init-row">
            <span class="init-label">界址线类别</span>
            <el-select v-model="boundaryLineType" clearable placeholder="请选择" style="width: 100%">
              <el-option
                v-for="option in lineCategoryOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>
          <div class="init-row">
            <span class="init-label">界址线位置</span>
            <el-select v-model="boundaryLinePosition" clearable placeholder="请选择" style="width: 100%">
              <el-option
                v-for="option in linePositionOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>
          <div class="init-row init-row-tall">
            <el-checkbox v-model="boundaryFilterByAngle" class="init-check">
              按角度过滤界址点
            </el-checkbox>
            <div class="code-inline">
              <span class="init-label-sub">最小角度</span>
              <el-input-number
                v-model="boundaryMinAngle"
                :min="0"
                :max="200"
                :precision="1"
                :disabled="!boundaryFilterByAngle"
                style="width: 130px"
              />
              <span class="init-label-sub">最大角度</span>
              <el-input-number
                v-model="boundaryMaxAngle"
                :min="0"
                :max="200"
                :precision="1"
                :disabled="!boundaryFilterByAngle"
                style="width: 130px"
              />
            </div>
          </div>
          <div class="init-row">
            <span class="init-label">邻宗地距离</span>
            <div class="code-inline">
              <el-input-number
                v-model="boundaryNeighborDistance"
                :min="0"
                :max="100"
                :precision="1"
                style="width: 130px"
              />
              <span class="init-label-sub">米</span>
              <el-checkbox v-model="boundaryWriteNeighbor">写入邻宗地权利人/指界人</el-checkbox>
            </div>
          </div>
          <div class="init-row">
            <el-checkbox v-model="boundaryWriteLength" class="init-check">
              写入界址线长度
            </el-checkbox>
            <span class="init-label-sub">界址线说明写为线长（保留 2 位小数）</span>
          </div>
        </div>
        <div class="sheet-tip">
          按勾选地块图形生成界址点/界址线；相邻地块共用点、共用线自动复用；已有属性按本次设置更新。
        </div>
      </el-tab-pane>
      <el-tab-pane label="面积处理" name="area">
        <div class="area-card">
          <div class="area-title">面积量算</div>
          <el-form label-width="110px" size="default">
            <el-form-item label="设置小数">
              <el-input-number v-model="calcDecimals" :min="0" :max="2" />
              <span class="area-unit">位</span>
            </el-form-item>
            <el-form-item label="设置模式">
              <el-select v-model="calcMode" style="width: 180px">
                <el-option label="四舍五入" value="round" />
                <el-option label="直接舍去" value="cut" />
              </el-select>
            </el-form-item>
            <el-form-item label="面积量算方式">
              <el-checkbox v-model="calcActual">平面面积到实测面积</el-checkbox>
              <el-checkbox v-model="calcAware">平面面积到确权面积</el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="submitting" @click="handleCalculateArea">
                执行面积量算
              </el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="area-card">
          <div class="area-title">面积截取</div>
          <el-form label-width="110px" size="default">
            <el-form-item label="设置小数">
              <el-input-number v-model="truncateDecimals" :min="0" :max="2" />
              <span class="area-unit">位</span>
            </el-form-item>
            <el-form-item label="设置模式">
              <el-select v-model="truncateMode" style="width: 180px">
                <el-option label="四舍五入" value="round" />
                <el-option label="直接舍去" value="cut" />
              </el-select>
            </el-form-item>
            <el-form-item label="面积选择">
              <el-checkbox v-model="truncateActual">实测面积</el-checkbox>
              <el-checkbox v-model="truncateAware">确权面积</el-checkbox>
              <el-checkbox v-model="truncateTable">二轮合同面积</el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="submitting" @click="handleTruncateArea">
                执行面积截取
              </el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <el-tab-pane label="基本农田分析" name="farmland">
        <div class="area-card">
          <div class="area-title">基本农田分析</div>
          <p class="sheet-tip">
            基于勾选地块与永久基本农田保护图斑（yjjbntbhtb）做空间相交分析：相交 → 是否基本农田 = 是，否则 = 否。
          </p>
          <el-button
            type="primary"
            :loading="submitting"
            style="margin-top: 12px"
            @click="handleAnalyzeFarmland"
          >
            执行基本农田分析
          </el-button>
        </div>
      </el-tab-pane>
    </el-tabs>

    <div v-if="['basic', 'survey'].includes(activeTab)" class="init-options">
      <el-checkbox v-model="initializeNull">仅初始化空值</el-checkbox>
      <el-checkbox v-model="onlyContractParcels">仅处理承包地块（地块类别 10）</el-checkbox>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        v-if="!['area', 'farmland'].includes(activeTab)"
        :loading="submitting"
        @click="handleConfirm"
      >
        {{ ["sheet", "survey", "code", "boundary"].includes(activeTab) ? "开始初始化" : "确定" }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { useDictionary } from "../../composables/useDictionary";
import { tdlylxMap } from "../../utils/parcelStatusHelpers";
import {
  analyzeParcelBasicFarmland,
  calculateParcelAreas,
  initializeParcelAttributes,
  initializeParcelBoundary,
  initializeParcelCodeBoundary,
  initializeParcelImageNumbers,
  initializeParcelSurveyInfo,
  truncateParcelAreas,
} from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  rows: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue", "initialized"]);

const { options: ownershipOptions } = useDictionary("nyt2539_c06_ownership_property");
const { options: categoryOptions } = useDictionary("nyt2539_c07_parcel_category");
const { options: gradeOptions } = useDictionary("nyt2539_c08_land_grade");
const { options: landUseOptions } = useDictionary("nyt2539_c09_land_use");
const { options: markerOptions } = useDictionary("nyt2539_c12_boundary_marker_type");
const { options: lineCategoryOptions } = useDictionary("nyt2539_c13_boundary_line_category");
const { options: linePositionOptions } = useDictionary("nyt2539_c14_boundary_line_position");

const fields = computed(() => [
  { key: "syqxz", label: "所有权性质", options: ownershipOptions.value || [] },
  { key: "dklb", label: "地块类别", options: categoryOptions.value || [] },
  {
    key: "tdlylx",
    label: "土地利用类型",
    options: Object.entries(tdlylxMap).map(([value, label]) => ({ value, label })),
  },
  { key: "dldj", label: "地力等级", options: gradeOptions.value || [] },
  { key: "tdyt", label: "土地用途", options: landUseOptions.value || [] },
  {
    key: "sfjbnt",
    label: "是否基本农田",
    options: [
      { value: "1", label: "是" },
      { value: "0", label: "否" },
    ],
  },
]);

const attributeKeys = ["syqxz", "dklb", "tdlylx", "dldj", "tdyt", "sfjbnt"];
const allKeys = [
  ...attributeKeys,
  "awareArea",
  "referPerson",
  "comment",
  "surveyPerson",
  "surveyDate",
  "surveyNote",
  "checkPerson",
  "checkDate",
  "checkOpinion",
];

const enabled = reactive(Object.fromEntries(allKeys.map((key) => [key, false])));
const values = reactive(Object.fromEntries(allKeys.map((key) => [key, ""])));
const referPersonByOwner = ref(false);
const initializeNull = ref(false);
const onlyContractParcels = ref(false);
const submitting = ref(false);
const activeTab = ref("basic");
const sheetScale = ref("1:2000");
const sheetOrder = ref("yx");
const sheetInitialAll = ref(false);
const codeEnabled = ref(false);
const codeMode = ref("merge");
const codeSortByPosition = ref(false);
const codeKeepSurveyNumber = ref(false);
const trimNeighborNote = ref(false);
const fillNeighbors = ref(false);
const calcDecimals = ref(2);
const calcMode = ref("round");
const calcActual = ref(false);
const calcAware = ref(false);
const truncateDecimals = ref(2);
const truncateMode = ref("round");
const truncateActual = ref(false);
const truncateAware = ref(false);
const truncateTable = ref(false);
const boundaryMarkType = ref("1");
const boundaryLineType = ref("01");
const boundaryLinePosition = ref("03");
const boundaryFilterByAngle = ref(true);
const boundaryMinAngle = ref(160);
const boundaryMaxAngle = ref(200);
const boundaryWriteLength = ref(true);
const boundaryNeighborDistance = ref(1.5);
const boundaryWriteNeighbor = ref(true);

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return;
    submitting.value = false;
    referPersonByOwner.value = false;
    initializeNull.value = false;
    onlyContractParcels.value = false;
    activeTab.value = "basic";
    sheetScale.value = "1:2000";
    sheetOrder.value = "yx";
    sheetInitialAll.value = false;
    codeEnabled.value = false;
    codeMode.value = "merge";
    codeSortByPosition.value = false;
    codeKeepSurveyNumber.value = false;
    trimNeighborNote.value = false;
    fillNeighbors.value = false;
    calcDecimals.value = 2;
    calcMode.value = "round";
    calcActual.value = false;
    calcAware.value = false;
    truncateDecimals.value = 2;
    truncateMode.value = "round";
    truncateActual.value = false;
    truncateAware.value = false;
    truncateTable.value = false;
    boundaryMarkType.value = "1";
    boundaryLineType.value = "01";
    boundaryLinePosition.value = "03";
    boundaryFilterByAngle.value = true;
    boundaryMinAngle.value = 160;
    boundaryMaxAngle.value = 200;
    boundaryWriteLength.value = true;
    boundaryNeighborDistance.value = 1.5;
    boundaryWriteNeighbor.value = true;
    for (const key of allKeys) {
      enabled[key] = false;
      values[key] = "";
    }
  },
);

function fieldLabel(key) {
  return fields.value.find((item) => item.key === key)?.label || "确权面积";
}

async function handleInitializeSheet() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  const items = props.rows
    .filter((row) => row?.cbfbm && row?.dkbm)
    .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm }));
  if (!items.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  submitting.value = true;
  try {
    const { data } = await initializeParcelImageNumbers({
      items,
      scale: sheetScale.value,
      useYX: sheetOrder.value === "xy",
      initialAll: sheetInitialAll.value,
    });
    const result = data?.data || {};
    ElMessage.success(
      `图幅编号初始化完成：处理 ${result.processed ?? items.length} 个地块` +
        (result.updated != null ? `，实际变更 ${result.updated} 个` : "") +
        (result.skipped ? `，跳过 ${result.skipped} 个` : ""),
    );
    emit("update:modelValue", false);
    emit("initialized");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "图幅编号初始化失败");
  } finally {
    submitting.value = false;
  }
}

async function handleInitializeSurvey() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  const items = props.rows
    .filter((row) => row?.cbfbm && row?.dkbm)
    .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm }));
  if (!items.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  const payload = {
    items,
    initializeNull: initializeNull.value,
    onlyContractParcels: onlyContractParcels.value,
  };
  let picked = 0;
  const textFields = [
    ["surveyPerson", "调查员"],
    ["surveyDate", "调查日期"],
    ["surveyNote", "调查记事"],
    ["checkPerson", "审核员"],
    ["checkDate", "审核日期"],
    ["checkOpinion", "审核意见"],
  ];
  for (const [key, label] of textFields) {
    if (!enabled[key]) continue;
    const value = values[key];
    if (value === "" || value === null || value === undefined) {
      ElMessage.warning(`请填写「${label}」的初始化值`);
      return;
    }
    payload[key] = value;
    picked += 1;
  }
  if (enabled.referPerson) {
    if (!referPersonByOwner.value && !values.referPerson.trim()) {
      ElMessage.warning("请输入指界人，或勾选「以地块当前承包方为指界人」");
      return;
    }
    payload.referPerson = values.referPerson.trim();
    payload.referPersonByOwner = referPersonByOwner.value;
    picked += 1;
  }
  if (!picked) {
    ElMessage.warning("请至少选择一个初始化项");
    return;
  }
  if (
    payload.surveyDate &&
    payload.checkDate &&
    payload.surveyDate > payload.checkDate
  ) {
    ElMessage.warning("调查日期必须小于审核日期");
    return;
  }
  submitting.value = true;
  try {
    const { data } = await initializeParcelSurveyInfo(payload);
    const result = data?.data || {};
    ElMessage.success(
      `调查信息初始化完成：处理 ${result.processed ?? items.length} 个地块` +
        (result.updated != null ? `，实际变更 ${result.updated} 个` : "") +
        (result.skipped ? `，跳过 ${result.skipped} 个` : ""),
    );
    emit("update:modelValue", false);
    emit("initialized");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "调查信息初始化失败");
  } finally {
    submitting.value = false;
  }
}

async function handleInitializeCodeBoundary() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  const items = props.rows
    .filter((row) => row?.cbfbm && row?.dkbm)
    .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm }));
  if (!items.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  if (!codeEnabled.value && !trimNeighborNote.value && !fillNeighbors.value) {
    ElMessage.warning("请至少选择一个初始化项");
    return;
  }
  if (codeEnabled.value && codeMode.value === "all") {
    try {
      await ElMessageBox.confirm(
        "「全部重新生成」会重编所选地块所属发包方下的全部地块编码，是否继续？",
        "全部重新生成",
        { type: "warning", confirmButtonText: "继续", cancelButtonText: "取消" },
      );
    } catch {
      return;
    }
  }
  submitting.value = true;
  try {
    const { data } = await initializeParcelCodeBoundary({
      items,
      landCodeMode: codeEnabled.value ? codeMode.value : "none",
      sortByPosition: codeEnabled.value && codeSortByPosition.value,
      keepSurveyNumber: codeEnabled.value && codeKeepSurveyNumber.value,
      trimNeighborNote: trimNeighborNote.value,
      fillNeighbors: fillNeighbors.value,
    });
    const result = data?.data || {};
    ElMessage.success(
      `地块编码与四至获取完成：处理 ${result.processed ?? items.length} 个地块` +
        (result.renumbered != null ? `，重编编码 ${result.renumbered} 个` : "") +
        (result.updated != null ? `，实际变更 ${result.updated} 个` : "") +
        (result.skipped ? `，跳过 ${result.skipped} 个` : ""),
    );
    emit("update:modelValue", false);
    emit("initialized");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "地块编码与四至获取失败");
  } finally {
    submitting.value = false;
  }
}

async function handleCalculateArea() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  if (!calcActual.value && !calcAware.value) {
    ElMessage.warning("请选择面积量算方式");
    return;
  }
  const items = props.rows
    .filter((row) => row?.cbfbm && row?.dkbm)
    .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm }));
  submitting.value = true;
  try {
    const { data } = await calculateParcelAreas({
      items,
      decimals: calcDecimals.value,
      roundMode: calcMode.value,
      toActualArea: calcActual.value,
      toAwareArea: calcAware.value,
    });
    const result = data?.data || {};
    ElMessage.success(
      `面积量算完成：处理 ${result.processed ?? items.length} 个地块` +
        (result.updated != null ? `，实际变更 ${result.updated} 个` : "") +
        (result.skipped ? `，跳过 ${result.skipped} 个` : ""),
    );
    emit("update:modelValue", false);
    emit("initialized");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "面积量算失败");
  } finally {
    submitting.value = false;
  }
}

async function handleTruncateArea() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  if (!truncateActual.value && !truncateAware.value && !truncateTable.value) {
    ElMessage.warning("请选择要截取的面积");
    return;
  }
  const items = props.rows
    .filter((row) => row?.cbfbm && row?.dkbm)
    .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm }));
  submitting.value = true;
  try {
    const { data } = await truncateParcelAreas({
      items,
      decimals: truncateDecimals.value,
      roundMode: truncateMode.value,
      actualArea: truncateActual.value,
      awareArea: truncateAware.value,
      tableArea: truncateTable.value,
    });
    const result = data?.data || {};
    ElMessage.success(
      `面积截取完成：处理 ${result.processed ?? items.length} 个地块` +
        (result.updated != null ? `，实际变更 ${result.updated} 个` : "") +
        (result.skipped ? `，跳过 ${result.skipped} 个` : ""),
    );
    emit("update:modelValue", false);
    emit("initialized");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "面积截取失败");
  } finally {
    submitting.value = false;
  }
}

async function handleInitializeBoundary() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  if (
    boundaryFilterByAngle.value &&
    Number(boundaryMinAngle.value) > Number(boundaryMaxAngle.value)
  ) {
    ElMessage.warning("最小角度不能大于最大角度");
    return;
  }
  const items = props.rows
    .filter((row) => row?.cbfbm && row?.dkbm)
    .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm }));
  submitting.value = true;
  try {
    const { data } = await initializeParcelBoundary({
      items,
      markType: boundaryMarkType.value || null,
      lineType: boundaryLineType.value || null,
      linePosition: boundaryLinePosition.value || null,
      filterByAngle: boundaryFilterByAngle.value,
      minAngle: boundaryMinAngle.value,
      maxAngle: boundaryMaxAngle.value,
      writeLineLength: boundaryWriteLength.value,
      neighborDistance: boundaryNeighborDistance.value,
      writeNeighbor: boundaryWriteNeighbor.value,
    });
    const result = data?.data || {};
    ElMessage.success(
      `界址初始化完成：处理 ${result.processed ?? items.length} 个地块` +
        (result.points != null ? `，界址点 ${result.points} 个` : "") +
        (result.lines != null ? `，界址线 ${result.lines} 条` : "") +
        (result.skipped ? `，跳过 ${result.skipped} 个` : ""),
    );
    emit("update:modelValue", false);
    emit("initialized");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "界址初始化失败");
  } finally {
    submitting.value = false;
  }
}

async function handleAnalyzeFarmland() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  const items = props.rows
    .filter((row) => row?.cbfbm && row?.dkbm)
    .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm }));
  submitting.value = true;
  try {
    const { data } = await analyzeParcelBasicFarmland({ items });
    const result = data?.data || {};
    ElMessage.success(
      `基本农田分析完成：处理 ${result.processed ?? items.length} 个地块` +
        (result.yes != null ? `，基本农田 ${result.yes} 个` : "") +
        (result.no != null ? `，非基本农田 ${result.no} 个` : "") +
        (result.skipped ? `，跳过 ${result.skipped} 个` : ""),
    );
    emit("update:modelValue", false);
    emit("initialized");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "基本农田分析失败");
  } finally {
    submitting.value = false;
  }
}

async function handleConfirm() {
  if (activeTab.value === "sheet") {
    await handleInitializeSheet();
    return;
  }
  if (activeTab.value === "survey") {
    await handleInitializeSurvey();
    return;
  }
  if (activeTab.value === "code") {
    await handleInitializeCodeBoundary();
    return;
  }
  if (activeTab.value === "boundary") {
    await handleInitializeBoundary();
    return;
  }
  if (activeTab.value !== "basic") {
    ElMessage.warning("该功能尚未开放，请切换到「基础信息」");
    return;
  }
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  const payload = {
    items: props.rows
      .filter((row) => row?.cbfbm && row?.dkbm)
      .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm })),
    initializeNull: initializeNull.value,
    onlyContractParcels: onlyContractParcels.value,
  };
  const picked = [];
  for (const key of attributeKeys) {
    if (!enabled[key]) continue;
    const value = values[key];
    if (value === "" || value === null || value === undefined) {
      ElMessage.warning(`请选择「${fields.value.find((item) => item.key === key)?.label || key}」的初始化值`);
      return;
    }
    payload[key] = value;
    picked.push(key);
  }
  if (enabled.awareArea) {
    if (!values.awareArea) {
      ElMessage.warning("请选择确权面积的初始化方式");
      return;
    }
    payload.awareAreaMode = values.awareArea;
    picked.push("awareArea");
  }
  if (enabled.comment) {
    payload.comment = values.comment;
    picked.push("comment");
  }
  if (!picked.length) {
    ElMessage.warning("请至少选择一个初始化项");
    return;
  }
  submitting.value = true;
  try {
    const { data } = await initializeParcelAttributes(payload);
    const result = data?.data || {};
    ElMessage.success(
      `数据初始化完成：处理 ${result.processed ?? payload.items.length} 个地块` +
        (result.updated != null ? `，实际变更 ${result.updated} 个` : "") +
        (result.skipped ? `，跳过 ${result.skipped} 个` : ""),
    );
    emit("update:modelValue", false);
    emit("initialized");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "数据初始化失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.init-head {
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-size: 13px;
}

.init-head strong {
  color: var(--text);
  font-size: 15px;
}

.init-grid {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.init-row {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
}

.init-check {
  margin-right: 0;
}

.init-label {
  color: var(--text);
  font-size: 13px;
}

.init-label-sub {
  color: var(--muted);
  font-size: 12px;
}

.code-inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 24px;
}

.sheet-tip {
  margin-top: 14px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}

.area-card {
  margin-bottom: 14px;
  padding: 14px 16px 4px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--panel-strong);
}

.area-title {
  margin-bottom: 12px;
  color: var(--text);
  font-size: 14px;
  font-weight: 600;
}

.area-unit {
  margin-left: 8px;
  color: var(--muted);
  font-size: 12px;
}

.init-inline {
  display: flex;
  align-items: center;
  gap: 12px;
}

.init-options {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
}
</style>
