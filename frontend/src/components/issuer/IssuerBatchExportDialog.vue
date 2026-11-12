<template>
  <el-dialog
    :model-value="modelValue"
    title="导出发包方资料"
    width="640px"
    top="10vh"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="export-head">
      <span class="export-count">
        已勾选 <strong>{{ rows.length }}</strong> 个发包方
      </span>
      <span class="export-tip-inline">导出内容仅包含勾选记录</span>
    </div>

    <el-checkbox-group v-model="selectedItems" class="doc-grid">
      <el-checkbox v-for="item in options" :key="item.value" :label="item.value" class="doc-item">
        <span class="doc-label">{{ item.label }}</span>
        <span class="doc-format" :class="item.format === 'Excel' ? 'is-excel' : 'is-word'">
          {{ item.format }}
        </span>
      </el-checkbox>
    </el-checkbox-group>

    <div v-if="selectedItems.includes('announcement')" v-loading="defaultsLoading" class="announcement-settings">
      <div class="settings-title">村组公告表设置</div>
      <el-form label-width="86px" size="default">
        <el-form-item label="公告日期">
          <el-date-picker
            v-model="announcement.announceDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="请选择公告日期"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker
            v-model="announcement.endDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="请选择异议截止日期"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="盖章单位">
          <el-input v-model="announcement.stampUnit" maxlength="100" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="announcement.address" maxlength="255" />
        </el-form-item>
      </el-form>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="handleConfirm">导出</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { fetchAnnouncementDefaults } from "../../api/issuer";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  rows: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue", "submit"]);

const options = [
  { value: "list", label: "发包方清单", format: "Excel" },
  { value: "survey", label: "发包方调查表", format: "Word" },
  { value: "publicity", label: "村组公示签字表", format: "Excel" },
  { value: "announcement", label: "村组公告表", format: "Word" },
];

const selectedItems = ref(options.map((item) => item.value));
const defaultsLoading = ref(false);
const announcement = reactive({
  announceDate: "",
  endDate: "",
  stampUnit: "",
  address: "",
});

function today() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/** 公告日期 + 1 个月（月末溢出自动收敛，如 1 月 31 日 → 2 月 28 日） */
function nextMonth(value) {
  const d = new Date(`${value}T00:00:00`);
  const target = new Date(d.getFullYear(), d.getMonth() + 1, d.getDate());
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  const day = String(Math.min(d.getDate(), lastDay)).padStart(2, "0");
  const month = String(target.getMonth() + 1).padStart(2, "0");
  return `${target.getFullYear()}-${month}-${day}`;
}

async function loadDefaults() {
  const code = props.rows[0]?.code;
  const current = today();
  announcement.announceDate = current;
  announcement.endDate = nextMonth(current);
  announcement.stampUnit = "";
  announcement.address = "";
  if (!code) return;
  defaultsLoading.value = true;
  try {
    const { data } = await fetchAnnouncementDefaults(code);
    const payload = data?.data || {};
    announcement.announceDate = payload.announceDate || current;
    announcement.endDate = payload.endDate || nextMonth(current);
    announcement.stampUnit = payload.stampUnit || "";
    announcement.address = payload.requestAddress || "";
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "读取村组公告默认信息失败");
  } finally {
    defaultsLoading.value = false;
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      selectedItems.value = options.map((item) => item.value);
      loadDefaults();
    }
  },
);

function handleConfirm() {
  if (!props.rows.length) {
    ElMessage.warning("请先勾选发包方");
    return;
  }
  if (!selectedItems.value.length) {
    ElMessage.warning("请至少选择一种导出内容");
    return;
  }
  const payload = {
    codes: props.rows.map((row) => row.code),
    items: [...selectedItems.value],
  };
  if (selectedItems.value.includes("announcement")) {
    if (!announcement.announceDate || !announcement.endDate) {
      ElMessage.warning("请选择公告日期和截止日期");
      return;
    }
    if (announcement.endDate < announcement.announceDate) {
      ElMessage.warning("截止日期不能小于公告日期");
      return;
    }
    if (!announcement.stampUnit.trim() || !announcement.address.trim()) {
      ElMessage.warning("请填写盖章单位和地址");
      return;
    }
    payload.announceDate = announcement.announceDate;
    payload.endDate = announcement.endDate;
    payload.stampUnit = announcement.stampUnit.trim();
    payload.address = announcement.address.trim();
  }
  emit("submit", payload);
}
</script>

<style scoped>
.export-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}

.export-count {
  color: var(--muted);
  font-size: 13px;
}

.export-count strong {
  color: var(--text);
  font-size: 15px;
}

.export-tip-inline {
  color: var(--muted);
  font-size: 12px;
}

.doc-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.doc-item {
  height: auto;
  margin-right: 0;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--panel-strong);
}

.doc-item.is-checked {
  border-color: var(--accent);
  background: rgba(47, 143, 255, 0.06);
}

.doc-item :deep(.el-checkbox__label) {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  padding-left: 8px;
}

.doc-label {
  overflow: hidden;
  color: var(--text);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-format {
  flex: 0 0 auto;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 18px;
}

.doc-format.is-excel {
  color: #1f7a4d;
  background: rgba(55, 178, 108, 0.12);
}

.doc-format.is-word {
  color: #1e5fa8;
  background: rgba(47, 143, 255, 0.12);
}

.announcement-settings {
  margin-top: 14px;
  padding: 12px 14px 2px;
  border: 1px dashed var(--line);
  border-radius: var(--radius-md);
}

.settings-title {
  margin-bottom: 10px;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}
</style>
