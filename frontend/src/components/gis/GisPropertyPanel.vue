<template>
  <Transition name="gis-property-panel">
    <aside v-if="modelValue" :key="panelKey" class="gis-property-panel" :style="dragStyle">
      <div class="gis-property-head" @pointerdown="startDrag">
        <div>
          <div class="gis-property-title">{{ parcel ? "承包方卡片" : "要素属性" }}</div>
          <div v-if="parcel" class="gis-property-subtitle">{{ parcel.cbfmc || parcel.dkbm || "未知" }}</div>
        </div>
        <button type="button" class="gis-property-close" aria-label="清除选择" @pointerdown.stop @click.stop="$emit('clear')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M6 6l12 12"/><path d="M18 6 6 18"/></svg>
        </button>
      </div>

      <template v-if="parcel">
        <div class="gis-card-tabs">
          <button v-for="tab in parcelTabs" :key="tab.value" type="button" class="gis-card-tab" :class="{ 'is-active': activeTab === tab.value }" @click="activeTab = tab.value">{{ tab.label }}</button>
        </div>
        <div v-if="activeTab === 'contractor'" class="gis-card-pane">
          <div class="gis-info-grid"><div v-for="item in contractorInfoRows" :key="item.label" class="gis-info-cell"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div></div>
          <div class="gis-table-title">家庭成员</div>
          <div class="gis-mini-table">
            <div class="gis-mini-table-row gis-mini-table-head"><span>序号</span><span>成员姓名</span><span>证件类型</span><span>证件号码</span><span>与户主关系</span><span>是否共有人</span></div>
            <div v-for="(member, index) in parcel.familyMembers || []" :key="`${member.idNo}-${index}`" class="gis-mini-table-row"><span>{{ index + 1 }}</span><span>{{ member.name || "未知" }}</span><span>{{ dictDisplay(idDocTypeLabel, member.idType) }}</span><span>{{ member.idNo || "未知" }}</span><span>{{ dictDisplay(relationLabel, member.relationToHead) }}</span><span>{{ booleanDisplay(member.isCoOwner) }}</span></div>
            <div v-if="!parcel.familyMembers?.length" class="gis-mini-empty">暂无家庭成员数据</div>
          </div>
        </div>
        <div v-else-if="activeTab === 'issuer'" class="gis-card-pane"><div class="gis-info-grid"><div v-for="item in issuerInfoRows" :key="item.label" class="gis-info-cell"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div></div></div>
        <div v-else-if="activeTab === 'parcel'" class="gis-card-pane"><div class="gis-info-grid"><div v-for="item in parcelInfoRows" :key="item.label" class="gis-info-cell"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div></div></div>
        <div v-else class="gis-card-pane"><div class="gis-info-grid"><div v-for="item in contractInfoRows" :key="item.label" class="gis-info-cell"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div></div></div>
      </template>
      <template v-else>
        <div class="gis-attr-card" v-for="item in attrs" :key="item.label"><div class="gis-attr-card-label">{{ item.label }}</div><div class="gis-attr-card-value">{{ item.value }}</div></div>
      </template>
    </aside>
  </Transition>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useDictionary } from "../../composables/useDictionary";
import { surveyStatusMap, resultStatusMap, changeTypeMap, landUseTypeMap } from "../../config/gisFieldMaps";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  parcel: { type: Object, default: null },
  attrs: { type: Array, default: () => [] },
  panelKey: { type: Number, default: 0 },
  containerRef: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue", "clear"]);

const activeTab = ref("contractor");
const position = ref(null);
let dragState = null;

const { labelOf: contractorTypeLabel } = useDictionary("nyt2539_c16_contractor_type");
const { labelOf: idDocTypeLabel } = useDictionary("nyt2539_c15_id_document_type");
const { labelOf: yesNoLabel } = useDictionary("nyt2539_c19_yes_no");
const { labelOf: parcelCategoryLabel } = useDictionary("nyt2539_c07_parcel_category");
const { labelOf: landGradeLabel } = useDictionary("nyt2539_c08_land_grade");
const { labelOf: landUseLabel } = useDictionary("nyt2539_c09_land_use");
const { labelOf: acquireMethodLabel } = useDictionary("nyt2539_c10_right_acquire_method");
const { labelOf: relationLabel } = useDictionary("nyt2539_c20_relation_to_head");

const parcelTabs = [
  { label: "发包方", value: "issuer" },
  { label: "承包方", value: "contractor" },
  { label: "承包地块", value: "parcel" },
  { label: "承包合同", value: "contract" },
];

function displayValue(v) { return v === undefined || v === null || v === "" ? "未知" : v; }
function dictDisplay(labelOf, v) { return displayValue(labelOf(v, v)); }
function mapDisplay(map, v) { return displayValue(map[v] || v); }
function booleanDisplay(v) { if (v === true) return "是"; if (v === false) return "否"; return dictDisplay(yesNoLabel, v); }
function withAreaUnit(v) { return v === undefined || v === null || v === "" ? "未知" : v + " 亩"; }

const contractorInfoRows = computed(() => { const p = props.parcel || {}; return [
  { label: "承包方编码", value: displayValue(p.cbfbm) }, { label: "承包方类型", value: dictDisplay(contractorTypeLabel, p.cbflx) },
  { label: "承包方名称", value: displayValue(p.cbfmc) }, { label: "证件类型", value: dictDisplay(idDocTypeLabel, p.cbfzjlx) },
  { label: "证件号码", value: displayValue(p.cbfzjhm) }, { label: "承包方地址", value: displayValue(p.cbfdz) },
  { label: "邮政编码", value: displayValue(p.cbfyzbm) }, { label: "联系电话", value: displayValue(p.cbflxdh) },
  { label: "家庭成员数", value: displayValue(p.cbfcysl) }, { label: "所属区域编码", value: displayValue(p.cbfGroupRegionCode) },
  { label: "所属区域名称", value: displayValue(p.cbfGroupRegionName) }, { label: "调查日期", value: displayValue(p.cbfdcrq) },
  { label: "调查员", value: displayValue(p.cbfdcy) }, { label: "调查记事", value: displayValue(p.cbfdcjs) },
  { label: "公示记事", value: displayValue(p.gsjs) }, { label: "公示记事人", value: displayValue(p.gsjsr) },
  { label: "公示审核日期", value: displayValue(p.gsshrq) }, { label: "公示审核人", value: displayValue(p.gsshr) },
  { label: "调查状态", value: mapDisplay(surveyStatusMap, p.cbfSurveyStatus) }, { label: "成果状态", value: mapDisplay(resultStatusMap, p.cbfResultStatus) },
  { label: "是否变更", value: booleanDisplay(p.cbfIsChanged) }, { label: "变更类型", value: mapDisplay(changeTypeMap, p.cbfChangeType) },
  { label: "变更原因", value: displayValue(p.cbfChangeReason) }, { label: "政策依据", value: displayValue(p.cbfPolicyBasis) },
  { label: "证据摘要", value: displayValue(p.cbfEvidenceSummary) }, { label: "调查处理人", value: displayValue(p.cbfInvestigatorName) },
  { label: "调查处理日期", value: displayValue(p.cbfInvestigatedAt) }, { label: "复核人", value: displayValue(p.cbfReviewerName) },
  { label: "复核日期", value: displayValue(p.cbfReviewedAt) }, { label: "确认日期", value: displayValue(p.cbfConfirmedAt) },
  { label: "备注", value: displayValue(p.cbfRemark) },
]; });

const issuerInfoRows = computed(() => { const p = props.parcel || {}; return [
  { label: "发包方编码", value: displayValue(p.fbfbm) }, { label: "发包方名称", value: displayValue(p.fbfmc) },
  { label: "负责人姓名", value: displayValue(p.fbffzrxm) }, { label: "负责人证件类型", value: dictDisplay(idDocTypeLabel, p.fbffzrzjlx) },
  { label: "负责人证件号码", value: displayValue(p.fbffzrzjhm) }, { label: "联系电话", value: displayValue(p.fbflxdh) },
  { label: "发包方地址", value: displayValue(p.fbfdz) }, { label: "邮政编码", value: displayValue(p.fbfyzbm) },
  { label: "发包方调查员", value: displayValue(p.fbfdcy) }, { label: "发包方调查日期", value: displayValue(p.fbfdcrq) },
  { label: "发包方调查记事", value: displayValue(p.fbfdcjs) }, { label: "调查状态", value: mapDisplay(surveyStatusMap, p.fbfSurveyStatus) },
  { label: "成果状态", value: mapDisplay(resultStatusMap, p.fbfResultStatus) }, { label: "是否变更", value: booleanDisplay(p.fbfIsChanged) },
  { label: "变更类型", value: mapDisplay(changeTypeMap, p.fbfChangeType) }, { label: "变更原因", value: displayValue(p.fbfChangeReason) },
  { label: "区域编码", value: displayValue(p.fbfRegionCode) }, { label: "租户编码", value: displayValue(p.fbfTenantCode) },
]; });

const parcelInfoRows = computed(() => { const p = props.parcel || {}; return [
  { label: "地块编码", value: displayValue(p.dkbm) }, { label: "地块名称", value: displayValue(p.dkmc) },
  { label: "地块类别", value: dictDisplay(parcelCategoryLabel, p.dklb) }, { label: "土地利用类型", value: mapDisplay(landUseTypeMap, p.tdlylx) },
  { label: "地力等级", value: dictDisplay(landGradeLabel, p.dldj) }, { label: "土地用途", value: dictDisplay(landUseLabel, p.tdyt) },
  { label: "是否基本农田", value: booleanDisplay(p.sfjbnt) }, { label: "合同面积", value: withAreaUnit(p.htmj) },
  { label: "实测面积", value: withAreaUnit(p.scmj) }, { label: "东至", value: displayValue(p.dkdz) },
  { label: "西至", value: displayValue(p.dkxz) }, { label: "南至", value: displayValue(p.dknz) },
  { label: "北至", value: displayValue(p.dkbz) }, { label: "备注", value: displayValue(p.dkbzxx) },
]; });

const contractInfoRows = computed(() => { const p = props.parcel || {}; const c = p.contract || {}; return [
  { label: "承包合同编码", value: displayValue(c.cbhtbm || p.cbhtbm) }, { label: "原承包合同编码", value: displayValue(c.ycbhtbm) },
  { label: "承包方式", value: dictDisplay(acquireMethodLabel, c.cbfs || p.cbjyqqdfs) }, { label: "合同开始日期", value: displayValue(c.htksrq || p.htksrq) },
  { label: "合同结束日期", value: displayValue(c.htjsrq || p.htjsrq) }, { label: "合同总面积", value: withAreaUnit(c.htzmj || p.htmj) },
  { label: "原合同总面积", value: withAreaUnit(c.yhtzmj || p.yhtmj) }, { label: "合同总面积(平方米)", value: displayValue(c.htzmjm || p.htmjm) },
  { label: "权证编码", value: displayValue(p.cbjyqzbm) }, { label: "是否确权确股", value: booleanDisplay(p.sfqqqg) },
]; });

const dragStyle = computed(() => {
  if (!position.value) return {};
  return { left: position.value.x + "px", top: position.value.y + "px", right: "auto", bottom: "auto" };
});

function clampNumber(value, min, max) { return max < min ? min : Math.min(Math.max(value, min), max); }

function stopDrag() {
  if (!dragState) return;
  window.removeEventListener("pointermove", moveDrag);
  window.removeEventListener("pointerup", stopDrag);
  window.removeEventListener("pointercancel", stopDrag);
  dragState = null;
}

function moveDrag(event) {
  if (!dragState) return;
  const { bounds, offsetX, offsetY, width, height } = dragState;
  position.value = { x: clampNumber(event.clientX - bounds.left - offsetX, 8, bounds.width - width - 8), y: clampNumber(event.clientY - bounds.top - offsetY, 8, bounds.height - height - 8) };
}

function startDrag(event) {
  if (event.button !== 0) return;
  const panel = event.currentTarget.closest(".gis-property-panel");
  const surface = props.containerRef?.value?.closest(".gis-map-surface");
  if (!panel || !surface) return;
  const panelRect = panel.getBoundingClientRect();
  const surfaceRect = surface.getBoundingClientRect();
  dragState = { bounds: { left: surfaceRect.left, top: surfaceRect.top, width: surfaceRect.width, height: surfaceRect.height }, width: panelRect.width, height: panelRect.height, offsetX: event.clientX - panelRect.left, offsetY: event.clientY - panelRect.top };
  position.value = { x: panelRect.left - surfaceRect.left, y: panelRect.top - surfaceRect.top };
  window.addEventListener("pointermove", moveDrag);
  window.addEventListener("pointerup", stopDrag);
  window.addEventListener("pointercancel", stopDrag);
  event.preventDefault();
}

watch(() => props.modelValue, (v) => { if (!v) { stopDrag(); position.value = null; activeTab.value = "contractor"; } });
watch(() => props.parcel, () => { activeTab.value = "contractor"; position.value = null; });
</script>