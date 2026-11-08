<template>
  <el-dialog
    :model-value="modelValue"
    title="村组公告表"
    width="580px"
    top="12vh"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form v-loading="loading" label-width="92px" size="default" class="announcement-form">
      <el-form-item label="发包方">
        <el-input :model-value="issuer?.name || issuer?.code || ''" disabled />
      </el-form-item>
      <el-form-item label="公告日期">
        <el-date-picker
          v-model="form.announceDate"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="请选择公告日期"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="截止日期">
        <el-date-picker
          v-model="form.endDate"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="请选择异议截止日期"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="盖章单位">
        <el-input v-model="form.stampUnit" maxlength="100" placeholder="例如：宏伟居村委会" />
      </el-form-item>
      <el-form-item label="地址">
        <el-input
          v-model="form.address"
          maxlength="255"
          placeholder="例如：宏伟居村委会(地址:泗洪县青阳镇宏伟居委会)"
        />
      </el-form-item>
      <div class="announcement-tip">
        公告正文中的户数、宗地块数、总面积按该发包方当前调查成果自动统计；截止日期不能早于公告日期。
      </div>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="exporting" @click="handleExport">导出</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import {
  exportVillageAnnouncement,
  fetchAnnouncementDefaults,
} from "../../api/issuer";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  issuer: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue"]);

const loading = ref(false);
const exporting = ref(false);
const form = reactive({
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

async function loadDefaults() {
  const code = props.issuer?.code;
  if (!code) return;
  loading.value = true;
  const current = today();
  form.announceDate = current;
  form.endDate = current;
  form.stampUnit = "";
  form.address = "";
  try {
    const { data } = await fetchAnnouncementDefaults(code);
    const payload = data?.data || {};
    form.announceDate = payload.announceDate || current;
    form.endDate = payload.endDate || current;
    form.stampUnit = payload.stampUnit || "";
    form.address = payload.requestAddress || "";
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "读取村组公告默认信息失败");
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) loadDefaults();
  },
);

function filenameFromDisposition(disposition) {
  const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition || "");
  return match ? decodeURIComponent(match[1]) : "";
}

function downloadBlob(data, filename) {
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function handleExport() {
  const code = props.issuer?.code;
  if (!code) return;
  if (!form.announceDate || !form.endDate) {
    ElMessage.warning("请选择公告日期和截止日期");
    return;
  }
  if (form.endDate < form.announceDate) {
    ElMessage.warning("截止日期不能小于公告日期");
    return;
  }
  if (!form.stampUnit.trim() || !form.address.trim()) {
    ElMessage.warning("请填写盖章单位和地址");
    return;
  }
  exporting.value = true;
  try {
    const { data, headers } = await exportVillageAnnouncement(code, {
      announceDate: form.announceDate,
      endDate: form.endDate,
      stampUnit: form.stampUnit.trim(),
      address: form.address.trim(),
    });
    const fallback = `${props.issuer?.name || code}农村土地承包经营权村组公示公告.docx`;
    downloadBlob(data, filenameFromDisposition(headers?.["content-disposition"]) || fallback);
    ElMessage.success("村组公告表已导出");
    emit("update:modelValue", false);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导出村组公告表失败");
  } finally {
    exporting.value = false;
  }
}
</script>

<style scoped>
.announcement-form {
  padding: 4px 4px 0;
}

.announcement-tip {
  margin-top: 4px;
  padding: 8px 10px;
  border-radius: 4px;
  background: var(--panel-strong);
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}
</style>
