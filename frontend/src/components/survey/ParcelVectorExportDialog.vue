<template>
  <el-dialog
    :model-value="modelValue"
    title="导出矢量数据"
    width="560px"
    top="12vh"
    :close-on-click-modal="false"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="vector-head">
      已勾选 <strong>{{ rows.length }}</strong> 个承包地块
    </div>

    <el-form label-width="92px" size="default">
      <el-form-item label="数据类型">
        <el-checkbox-group v-model="layers">
          <el-checkbox label="dk">承包地块</el-checkbox>
          <el-checkbox label="jzd">界址点</el-checkbox>
          <el-checkbox label="jzx">界址线</el-checkbox>
        </el-checkbox-group>
      </el-form-item>
      <el-form-item label="输出格式">
        <el-radio-group v-model="format">
          <el-radio label="shp">Shapefile</el-radio>
          <el-radio label="gdb">GDB 数据库</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <div class="vector-tip">
      Shapefile 与 GDB 均以 ZIP 打包下载；界址点/界址线按勾选地块的边界空间范围提取。
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="exporting" @click="handleExport">导出</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { exportParcelVector } from "../../api/survey";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  rows: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);

const layers = ref(["dk", "jzd", "jzx"]);
const format = ref("shp");
const exporting = ref(false);

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return;
    layers.value = ["dk", "jzd", "jzx"];
    format.value = "shp";
    exporting.value = false;
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
  if (!props.rows.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  if (!layers.value.length) {
    ElMessage.warning("请至少选择一种数据类型");
    return;
  }
  const items = props.rows
    .filter((row) => row?.cbfbm && row?.dkbm)
    .map((row) => ({ cbfbm: row.cbfbm, dkbm: row.dkbm }));
  if (!items.length) {
    ElMessage.warning("请先勾选承包地块");
    return;
  }
  exporting.value = true;
  try {
    const { data, headers } = await exportParcelVector({
      items,
      layers: layers.value,
      format: format.value,
    });
    const fallback = `承包地块矢量数据_${format.value === "gdb" ? "gdb" : "shapefile"}.zip`;
    downloadBlob(data, filenameFromDisposition(headers?.["content-disposition"]) || fallback);
    ElMessage.success("矢量数据已导出");
    emit("update:modelValue", false);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "导出矢量数据失败");
  } finally {
    exporting.value = false;
  }
}
</script>

<style scoped>
.vector-head {
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-size: 13px;
}

.vector-head strong {
  color: var(--text);
  font-size: 15px;
}

.vector-tip {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: 4px;
  background: var(--panel-strong);
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}
</style>
