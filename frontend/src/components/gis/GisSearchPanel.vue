<template>
  <Transition name="gis-search-panel">
    <section v-if="visible" class="gis-search-panel">
      <div class="gis-search-panel-head">
        <div class="gis-search-counts">
          <div><span>{{ activeCountLabel }}</span><strong>{{ activeCount }}</strong><span>{{ ui.countUnit }}</span></div>
          <div><span>{{ ui.parcelAmount }}</span><strong>{{ parcelCount }}</strong><span>{{ ui.countUnit }}</span></div>
        </div>
        <button type="button" class="gis-search-close" :aria-label="ui.closeSearchPanel" @click="$emit('update:visible', false)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M6 6l12 12"/><path d="M18 6 6 18"/></svg>
        </button>
      </div>
      <div class="gis-search-tabs">
        <button v-for="tab in visibleTabs" :key="tab.value" type="button" class="gis-search-tab" :class="{ 'is-active': activeTab === tab.value }" @click="activeTab = tab.value">{{ tab.label }}</button>
      </div>
      <div class="gis-search-message" v-if="message">{{ message }}</div>
      <div class="gis-search-list" v-if="activeItems.length">
        <button v-for="item in activeItems" :key="`${item.resultType}-${item.code}`" type="button" class="gis-search-result" @click="$emit('apply-result', item)">
          <div class="gis-search-result-main">
            <div class="gis-search-result-title">{{ item.name || ui.unknown }}</div>
            <div class="gis-search-result-lines">
              <span>{{ resultCodeLabel(item) }}：{{ item.code || ui.unknown }}</span>
              <span>{{ resultSubLabel(item) }}：{{ resultSubValue(item) }}</span>
            </div>
          </div>
          <div class="gis-search-result-actions">
            <span :title="ui.parcelAmount"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h12l4 4v8H4z"/><path d="M16 6v4h4"/></svg>{{ item.parcelCount || 0 }}</span>
            <span :title="ui.locateQuery"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s6-5.2 6-10a6 6 0 1 0-12 0c0 4.8 6 10 6 10Z"/><circle cx="12" cy="11" r="2.2"/></svg></span>
          </div>
        </button>
      </div>
      <div v-else class="gis-search-empty">{{ ui.notFound }}</div>
    </section>
  </Transition>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  visible: { type: Boolean, default: false },
  searchType: { type: String, default: "all" },
  searchResult: { type: Object, default: () => ({ requests: [], issuers: [], contractors: [] }) },
  message: { type: String, default: "" },
  ui: { type: Object, required: true },
  searchTypeOptions: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:visible", "apply-result"]);

const activeTab = ref("contractors");

const visibleTabs = computed(() =>
  props.searchTypeOptions.filter((o) => o.value !== "all").filter((o) => props.searchType === "all" || o.value === props.searchType),
);
const activeItems = computed(() => props.searchResult[activeTab.value] || []);
const activeCountLabel = computed(() => (activeTab.value === "issuers" ? props.ui.issuerAmount : props.ui.contractorAmount));
const activeCount = computed(() => activeItems.value.length);
const parcelCount = computed(() => activeItems.value.reduce((t, item) => t + Number(item.parcelCount || 0), 0));

function activateFirstTab() {
  if (props.searchType !== "issuers" && props.searchResult.contractors.length) { activeTab.value = "contractors"; return; }
  if (props.searchType !== "contractors" && props.searchResult.issuers.length) { activeTab.value = "issuers"; return; }
  activeTab.value = props.searchType === "issuers" ? "issuers" : "contractors";
}

function resultCodeLabel(item) { return item.resultType === "issuer" ? props.ui.issuerCode : props.ui.contractorCode; }
function resultSubLabel(item) { return item.resultType === "issuer" ? props.ui.ownerName : props.ui.idNo; }
function resultSubValue(item) { return item.resultType === "issuer" ? (item.ownerName || props.ui.notMaintainedOwner) : (item.idNo || props.ui.notMaintainedId); }

watch(() => props.visible, (v) => { if (v) activateFirstTab(); });

defineExpose({ activateFirstTab });
</script>