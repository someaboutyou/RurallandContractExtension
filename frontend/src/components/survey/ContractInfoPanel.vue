<template>
  <div class="contract-info-panel">
    <!-- 加载中 -->
    <el-skeleton v-if="loading" :rows="6" animated />

    <!-- 无合同 -->
    <el-empty v-else-if="!contracts.length" description="该承包方暂无关联合同" />

    <!-- 合同信息 -->
    <div v-else class="contract-content">
      <!-- 合同版本切换：现行延包合同 / 历史合同 / 上次承包合同 -->
      <div class="contract-switch">
        <span class="switch-label">合同版本</span>
        <el-radio-group v-model="activeCode" size="small">
          <el-radio-button v-for="item in contracts" :key="item.cbhtbm" :value="item.cbhtbm">
            {{ contractOptionLabel(item) }}
          </el-radio-button>
        </el-radio-group>
        <el-tag
          v-if="activeContract"
          :type="activeContract.contractStatus === 'active' ? 'success' : 'info'"
          size="small"
          effect="plain"
        >
          {{ activeContract.contractStatusText }}
        </el-tag>
      </div>

      <!-- 合同基本信息栏 -->
      <div class="contract-summary">
        <el-descriptions v-loading="detailLoading" :column="4" border size="small">
          <el-descriptions-item label="合同编码">{{ activeContract?.cbhtbm || "-" }}</el-descriptions-item>
          <el-descriptions-item label="合同类型">{{ activeContract?.contractSourceText || "-" }}</el-descriptions-item>
          <el-descriptions-item label="上一份合同">{{ activeContract?.ycbhtbm || "-" }}</el-descriptions-item>
          <el-descriptions-item label="承包方式">{{ cbfsLabel }}</el-descriptions-item>
          <el-descriptions-item label="地块总数">{{ activeContract?.cbdkzs ?? "-" }}</el-descriptions-item>
          <el-descriptions-item label="签订日期">{{ activeContract?.qdsj || "-" }}</el-descriptions-item>
          <el-descriptions-item label="承包期限起">{{ activeContract?.cbqxq || "（空，待填）" }}</el-descriptions-item>
          <el-descriptions-item label="承包期限止">{{ activeContract?.cbqxz || "（空，待填）" }}</el-descriptions-item>
          <el-descriptions-item label="合同总面积(㎡)">{{ formatNumber(activeContract?.htzmj) }}</el-descriptions-item>
          <el-descriptions-item label="合同总面积(亩)">{{ formatNumber(activeContract?.htzmjm) }}</el-descriptions-item>
          <el-descriptions-item label="生成人">{{ activeContract?.generatedBy || "-" }}</el-descriptions-item>
          <el-descriptions-item label="生成时间">{{ generatedAtText }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 操作工具栏 -->
      <div class="contract-toolbar">
        <el-button type="primary" @click="handlePrint">
          <el-icon><Printer /></el-icon>
          打印合同
        </el-button>
        <el-button
          v-if="canManage"
          type="warning"
          plain
          :disabled="!canGenerate"
          :loading="generating"
          @click="openGenerateDialog"
        >
          <el-icon><DocumentAdd /></el-icon>
          合同生成
        </el-button>
        <el-upload
          ref="uploadRef"
          v-if="canManage"
          :show-file-list="false"
          :before-upload="beforeUpload"
          :http-request="handleUpload"
          accept=".pdf,.jpg,.jpeg,.png"
        >
          <el-button type="success">
            <el-icon><Upload /></el-icon>
            上传合同附件
          </el-button>
        </el-upload>
        <span v-if="generateHint" class="toolbar-hint">{{ generateHint }}</span>
      </div>

      <!-- 电子合同预览 / 合同附件 -->
      <el-tabs v-model="contractTab" class="contract-view-tabs">
        <el-tab-pane label="电子合同" name="preview">
          <div class="contract-preview-wrapper">
            <iframe
              :srcdoc="detail?.renderedHtml || ''"
              class="contract-iframe"
              frameborder="0"
              title="合同预览"
            />
          </div>
        </el-tab-pane>
        <el-tab-pane :label="`合同附件（${attachments.length}）`" name="attachments">
          <el-table :data="attachments" border size="small" v-loading="attLoading">
            <el-table-column prop="originalName" label="文件名" min-width="200" />
            <el-table-column prop="category" label="类别" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ row.category }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
            <el-table-column label="上传时间" width="170">
              <template #default="{ row }">{{ row.createdAt?.slice(0, 16) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="handleDownload(row.id)">下载</el-button>
                <el-button link type="danger" size="small" @click="handleDelete(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 生成延包合同 -->
    <el-dialog v-model="dialogVisible" title="生成延包合同" width="620px" append-to-body>
      <el-alert type="info" :closable="false" show-icon class="generate-tip">
        <template #title>
          按当前调查信息生成新的延包合同；生成后上一份合同将置为<b>历史状态</b>，仍可随时查看与打印。
        </template>
      </el-alert>
      <el-form :model="termForm" label-width="130px" class="generate-form">
        <el-form-item label="上次合同到期">
          <span class="read-only-text">
            {{ catalog.defaultTermStart || "（无上次承包合同，需人工填写起始日期）" }}
          </span>
        </el-form-item>
        <el-form-item label="承包期限起" required>
          <el-date-picker
            v-model="termForm.cbqxq"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="默认为上次合同到期时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="承包期限（年）">
          <el-input-number v-model="termForm.years" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="承包期限止">
          <el-date-picker
            v-model="termForm.cbqxz"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="按起期 + 年限自动计算，可修改"
            style="width: 100%"
            @change="endTouched = true"
          />
        </el-form-item>
        <el-form-item label="签订日期">
          <el-date-picker
            v-model="termForm.qdsj"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="承包方式">
          <el-select v-model="termForm.cbfs" style="width: 100%">
            <el-option
              v-for="(label, value) in CBFS_OPTIONS"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="合同面积/地块">
          <span class="read-only-text">
            {{ formatNumber(activeContract?.htzmj) }} ㎡（{{ activeContract?.cbdkzs ?? 0 }} 个地块，按当前调查信息计算）
          </span>
        </el-form-item>
        <el-form-item v-if="catalog.currentCode" label="现有延包合同">
          <span class="read-only-text warn">{{ catalog.currentCode }}（生成后置为历史）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="submitGenerate">确认生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { DocumentAdd, Printer, Upload } from "@element-plus/icons-vue";
import {
  fetchSurveyContractDetail,
  fetchSurveyContracts,
  fetchSurveyPhase2,
  generateSurveyContract,
  printSurveyContract,
  uploadSurveyAttachment,
  downloadSurveyAttachment,
  deleteSurveyAttachment,
} from "../../api/survey";

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  canManage: { type: Boolean, default: false },
  batchStatus: { type: String, default: "active" },
});

const CBFS_OPTIONS = {
  "001": "家庭承包",
  "002": "其他方式承包",
  "003": "招标",
  "004": "拍卖",
  "005": "公开协商",
};

const loading = ref(false);
const detailLoading = ref(false);
const generating = ref(false);
const catalog = ref({ contracts: [], currentCode: null, originalCode: null, defaultTermStart: null, defaultYears: 30 });
const activeCode = ref(null);
const detail = ref(null);
const detailCache = ref({});
const contractTab = ref("preview");
const attachments = ref([]);
const attLoading = ref(false);
const uploadRef = ref(null);

const dialogVisible = ref(false);
const endTouched = ref(false);
const termForm = reactive({ cbqxq: "", cbqxz: "", years: 30, qdsj: "", cbfs: "001" });

const contracts = computed(() => catalog.value.contracts || []);
const activeContract = computed(() => contracts.value.find((item) => item.cbhtbm === activeCode.value) || null);
const cbfsLabel = computed(() => CBFS_OPTIONS[activeContract.value?.cbfs] || activeContract.value?.cbfs || "-");
const generatedAtText = computed(() => (activeContract.value?.generatedAt || "").slice(0, 19).replace("T", " ") || "-");
// 批次已结束不能生成；调查结果确认后仍允许生成（延包合同是调查完成后的下一环节）
const canGenerate = computed(() => props.canManage && props.batchStatus !== "finished");
const generateHint = computed(() => {
  if (!props.canManage) return "";
  if (props.batchStatus === "finished") return "（批次已结束，不能生成合同）";
  return "";
});

function contractOptionLabel(item) {
  const kind = item.contractSourceText || "合同";
  const status = item.contractStatusText || "";
  return `${kind}·${status}`;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  return Number(value).toFixed(2);
}

function todayString() {
  const now = new Date();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

// 止期 = 起期 + 年限 − 1 天，使打印件上的「承包期限」正好等于所填年限
function computeTermEnd(start, years) {
  if (!start || !years) return "";
  const date = new Date(`${start}T00:00:00`);
  date.setFullYear(date.getFullYear() + Number(years));
  date.setDate(date.getDate() - 1);
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

async function loadContracts(preferCode) {
  if (!props.batchId || !props.contractorUid) return;
  loading.value = true;
  try {
    const { data } = await fetchSurveyContracts(props.batchId, props.contractorUid);
    catalog.value = data.data || { contracts: [] };
    const fallback =
      catalog.value.currentCode ||
      catalog.value.originalCode ||
      (catalog.value.contracts || [])[0]?.cbhtbm ||
      null;
    activeCode.value = preferCode || fallback;
    detailCache.value = {};
    await loadDetail();
  } catch {
    catalog.value = { contracts: [] };
    activeCode.value = null;
    detail.value = null;
  } finally {
    loading.value = false;
  }
}

async function loadDetail() {
  if (!activeCode.value) {
    detail.value = null;
    return;
  }
  const cached = detailCache.value[activeCode.value];
  if (cached) {
    detail.value = cached;
    return;
  }
  detailLoading.value = true;
  try {
    const { data } = await fetchSurveyContractDetail(props.batchId, props.contractorUid, activeCode.value);
    detail.value = data.data;
    detailCache.value = { ...detailCache.value, [activeCode.value]: data.data };
  } catch {
    detail.value = null;
  } finally {
    detailLoading.value = false;
  }
}

async function loadAttachments() {
  attLoading.value = true;
  try {
    const { data } = await fetchSurveyPhase2(props.batchId, props.contractorUid);
    attachments.value = (data.data?.attachments || []).filter((item) => item.category === "contract");
  } catch {
    attachments.value = [];
  } finally {
    attLoading.value = false;
  }
}

function openGenerateDialog() {
  const start = catalog.value.defaultTermStart || "";
  termForm.cbqxq = start;
  termForm.years = catalog.value.defaultYears || 30;
  termForm.cbqxz = computeTermEnd(start, termForm.years);
  termForm.qdsj = todayString();
  // 上次承包合同的承包方式码值与合同表口径可能不同，选不到时回落「家庭承包」
  const cbfs = activeContract.value?.cbfs || "";
  termForm.cbfs = CBFS_OPTIONS[cbfs] ? cbfs : "001";
  endTouched.value = false;
  dialogVisible.value = true;
}

function syncTermEnd() {
  if (endTouched.value) return;
  termForm.cbqxz = computeTermEnd(termForm.cbqxq, termForm.years);
}

async function submitGenerate() {
  if (!termForm.cbqxq) {
    ElMessage.warning("请填写承包期限起始日期");
    return;
  }
  if (termForm.cbqxz && termForm.cbqxz < termForm.cbqxq) {
    ElMessage.warning("承包期限止不能早于起始日期");
    return;
  }
  if (catalog.value.currentCode) {
    try {
      await ElMessageBox.confirm(
        `生成后现有延包合同（${catalog.value.currentCode}）将置为历史状态，是否继续？`,
        "确认生成延包合同",
        { type: "warning" }
      );
    } catch {
      return;
    }
  }
  generating.value = true;
  try {
    const { data } = await generateSurveyContract(props.batchId, props.contractorUid, {
      cbqxq: termForm.cbqxq,
      cbqxz: termForm.cbqxz || null,
      years: termForm.years,
      qdsj: termForm.qdsj || null,
      cbfs: termForm.cbfs || null,
    });
    dialogVisible.value = false;
    ElMessage.success(`延包合同已生成：${data.data?.cbhtbm || ""}`);
    await loadContracts(data.data?.cbhtbm);
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "合同生成失败");
  } finally {
    generating.value = false;
  }
}

async function handlePrint() {
  try {
    let html = detail.value?.renderedHtml;
    if (!html) {
      const { data } = await printSurveyContract(props.batchId, props.contractorUid, activeCode.value);
      html = data;
    }
    if (!html) {
      ElMessage.warning("暂无可打印的合同内容");
      return;
    }
    const win = window.open("", "_blank", "width=900,height=700");
    if (win) {
      win.document.write(html);
      win.document.close();
      setTimeout(() => win.print(), 500);
    }
  } catch {
    ElMessage.error("打印合同失败");
  }
}

async function beforeUpload(file) {
  const isValid = ["application/pdf", "image/jpeg", "image/png"].includes(file.type);
  if (!isValid) {
    ElMessage.error("仅支持 PDF、JPG、PNG 格式");
  }
  return isValid;
}

async function handleUpload({ file }) {
  const formData = new FormData();
  formData.append("category", "contract");
  formData.append("description", file.name);
  formData.append("file", file);
  try {
    await uploadSurveyAttachment(props.batchId, props.contractorUid, formData);
    ElMessage.success("上传成功");
    await loadAttachments();
  } catch {
    ElMessage.error("上传失败");
  }
}

async function handleDownload(attId) {
  try {
    const { data } = await downloadSurveyAttachment(attId);
    const url = window.URL.createObjectURL(new Blob([data]));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "";
    anchor.click();
    window.URL.revokeObjectURL(url);
  } catch {
    ElMessage.error("下载失败");
  }
}

async function handleDelete(attId) {
  try {
    await ElMessageBox.confirm("确定要删除此附件吗？", "确认删除", { type: "warning" });
    await deleteSurveyAttachment(attId);
    ElMessage.success("已删除");
    await loadAttachments();
  } catch {
    // cancelled
  }
}

watch(
  () => [props.batchId, props.contractorUid],
  () => {
    loadContracts();
    loadAttachments();
  },
  { immediate: true }
);

watch(activeCode, () => {
  loadDetail();
});

watch(
  () => [termForm.cbqxq, termForm.years],
  () => {
    syncTermEnd();
  }
);
</script>

<style scoped>
.contract-info-panel {
  min-height: 400px;
}
.contract-switch {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.switch-label {
  font-size: 13px;
  color: #606266;
}
.contract-summary {
  margin-bottom: 12px;
}
.contract-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-hint {
  font-size: 12px;
  color: #909399;
}
.contract-view-tabs {
  margin-top: 4px;
}
.contract-preview-wrapper {
  width: 100%;
  height: calc(92vh - 380px);
  min-height: 460px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: hidden;
}
.contract-iframe {
  width: 100%;
  height: 100%;
  border: none;
}
.generate-tip {
  margin-bottom: 12px;
}
.generate-form {
  margin-top: 4px;
}
.read-only-text {
  font-size: 13px;
  color: #606266;
}
.read-only-text.warn {
  color: #e6a23c;
}
</style>
