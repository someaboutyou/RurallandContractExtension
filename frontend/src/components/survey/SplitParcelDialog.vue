<template>
  <el-dialog
    v-model="visible"
    title="切割地块"
    width="680px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="选择一个地块进行切割。原地块面积将减少，切割部分生成新地块。手绘和 SHP 模式需要空间数据支持，当前暂不可用。"
      type="info"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-tabs v-model="activeMode">
      <el-tab-pane label="输入面积" name="area">
        <el-form :model="form" label-position="top" class="split-form">
          <el-form-item label="选择原地块" required>
            <el-select
              v-model="form.dkbm"
              placeholder="请选择要切割的地块"
              style="width: 100%"
              @change="onParcelSelect"
            >
              <el-option
                v-for="p in parcels"
                :key="p.dkbm"
                :label="`${p.dkbm} — ${p.dkmc || '未命名'}（${p.scmj || 0} 亩）`"
                :value="p.dkbm"
              >
                <span class="option-code">{{ p.dkbm }}</span>
                <span class="option-name">{{ p.dkmc || '未命名' }}</span>
                <span class="option-area">{{ p.scmj || 0 }} 亩</span>
              </el-option>
            </el-select>
          </el-form-item>

          <el-descriptions v-if="selectedParcel" :column="2" border size="small" style="margin-bottom: 16px">
            <el-descriptions-item label="原地块编码">{{ selectedParcel.dkbm }}</el-descriptions-item>
            <el-descriptions-item label="原地块名称">{{ selectedParcel.dkmc || '-' }}</el-descriptions-item>
            <el-descriptions-item label="原实测面积">{{ selectedParcel.scmj || 0 }} 亩</el-descriptions-item>
            <el-descriptions-item label="剩余面积">
              <span :class="{ 'area-warn': remainingArea <= 0 }">{{ remainingArea }} 亩</span>
            </el-descriptions-item>
          </el-descriptions>

          <el-divider />

          <div class="form-row">
            <el-form-item label="新地块编码" required class="form-half">
              <el-input v-model="form.newDkbm" placeholder="19位地块编码" maxlength="19" />
            </el-form-item>
            <el-form-item label="新地块名称" required class="form-half">
              <el-input v-model="form.newDkmc" placeholder="例如：切割地块A" maxlength="50" />
            </el-form-item>
          </div>

          <el-form-item label="切割面积（亩）" required>
            <el-input-number
              v-model="form.newScmj"
              :min="0.01"
              :max="maxSplitArea"
              :precision="2"
              style="width: 100%"
            />
            <div class="area-hint" v-if="selectedParcel">
              原地块 {{ selectedParcel.scmj || 0 }} 亩 → 切割 {{ form.newScmj || 0 }} 亩 → 剩余 {{ remainingArea }} 亩
            </div>
          </el-form-item>

          <el-form-item label="切割原因">
            <el-input
              v-model="form.reason"
              type="textarea"
              :rows="2"
              placeholder="说明本次切割地块的原因"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="手绘切割" name="draw">
        <div class="placeholder-mode">
          <el-icon :size="48" color="#c0c4cc"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M2 12h20"/></svg></el-icon>
          <p>在地图上通过手绘分割线进行切割。</p>
          <p class="placeholder-note">需要开启地图交互模块后实现。目前请使用「输入面积」模式。</p>
        </div>
      </el-tab-pane>

      <el-tab-pane label="上传 SHP" name="shp">
        <div class="placeholder-mode">
          <el-icon :size="48" color="#c0c4cc"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></el-icon>
          <p>上传 Shapefile 切割线/面进行空间分割。</p>
          <p class="placeholder-note">需要后端 PostGIS 空间函数支持后实现。目前请使用「输入面积」模式。</p>
        </div>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="handleSubmit"
      >
        确认切割
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { splitSurveyParcel } from "../../api/survey";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const batchId = ref(null);
const contractorUid = ref("");
const parcels = ref([]);
const activeMode = ref("area");

function defaultForm() {
  return {
    dkbm: "",
    newDkbm: "",
    newDkmc: "",
    newScmj: 0,
    reason: "",
  };
}
const form = reactive(defaultForm());

const selectedParcel = computed(() =>
  parcels.value.find((p) => p.dkbm === form.dkbm) || null
);

const maxSplitArea = computed(() => {
  if (!selectedParcel.value) return 0;
  const area = parseFloat(selectedParcel.value.scmj) || 0;
  return Math.max(0, area - 0.01);
});

const remainingArea = computed(() => {
  if (!selectedParcel.value) return 0;
  const area = parseFloat(selectedParcel.value.scmj) || 0;
  return Math.max(0, +(area - (form.newScmj || 0)).toFixed(2));
});

const canSubmit = computed(() =>
  activeMode.value === "area" &&
  form.dkbm &&
  form.newDkbm.trim() &&
  form.newDkmc.trim() &&
  form.newScmj > 0 &&
  form.newScmj < (parseFloat(selectedParcel.value?.scmj) || 0)
);

function open(bid, cuid, parcelList) {
  batchId.value = bid;
  contractorUid.value = cuid;
  parcels.value = parcelList || [];
  Object.assign(form, defaultForm());
  activeMode.value = "area";
  visible.value = true;
}

function resetForm() {
  Object.assign(form, defaultForm());
  activeMode.value = "area";
}

function onParcelSelect() {
  form.newScmj = 0;
}

async function handleSubmit() {
  if (!canSubmit.value) {
    ElMessage.warning("请填写完整信息，切割面积必须小于原地块面积");
    return;
  }
  submitting.value = true;
  try {
    await splitSurveyParcel(batchId.value, contractorUid.value, {
      dkbm: form.dkbm,
      newDkbm: form.newDkbm.trim(),
      newDkmc: form.newDkmc.trim(),
      newScmj: Number(form.newScmj),
      reason: form.reason || undefined,
    });
    ElMessage.success("地块切割完成");
    visible.value = false;
    emit("done");
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || "切割失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert { margin-bottom: 16px; }
.split-form { margin-top: 8px; }
.form-row { display: flex; gap: 12px; }
.form-half { flex: 1; min-width: 0; }
.area-hint { color: #909399; font-size: 12px; margin-top: 4px; }
.area-warn { color: #f56c6c; font-weight: 600; }

.option-code { font-weight: 600; margin-right: 8px; }
.option-name { color: #606266; margin-right: 8px; }
.option-area { color: #909399; font-size: 12px; }

.placeholder-mode {
  align-items: center;
  color: #909399;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 48px 0;
  text-align: center;
}
.placeholder-mode p { margin: 0; }
.placeholder-note { font-size: 12px; color: #c0c4cc; }
</style>
