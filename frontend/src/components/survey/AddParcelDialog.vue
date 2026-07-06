<template>
  <el-dialog
    v-model="visible"
    title="新增地块属性信息"
    width="720px"
    destroy-on-close
    @closed="handleClosed"
  >
    <el-alert
      title="请补充新增地块的属性信息，保存调查结果时会与已核验通过的图形一起提交。"
      type="info"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-form :model="form" label-position="top" class="parcel-form">
      <div class="form-row">
        <el-form-item label="地块编码" required class="form-half">
          <el-input v-model="form.dkbm" placeholder="19位地块编码" maxlength="19">
            <template #append>
              <el-button :loading="generatingCode" @click="handleGenerateCode">自动生成</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="地块名称" required class="form-half">
          <el-input v-model="form.dkmc" placeholder="例如：东沟南地" maxlength="50" />
        </el-form-item>
      </div>

      <div class="form-row">
        <el-form-item label="实测面积（亩）" required class="form-half">
          <el-input-number v-model="form.scmj" :min="0.01" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="合同面积（亩）" class="form-half">
          <el-input-number v-model="form.htmj" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
      </div>

      <div class="form-row">
        <el-form-item label="地块类别" required class="form-third">
          <el-select v-model="form.dklb" style="width: 100%">
            <el-option label="耕地" value="01" />
            <el-option label="园地" value="02" />
            <el-option label="林地" value="03" />
            <el-option label="草地" value="04" />
            <el-option label="其他" value="99" />
          </el-select>
        </el-form-item>
        <el-form-item label="土地用途" required class="form-third">
          <el-select v-model="form.tdyt" style="width: 100%">
            <el-option label="种植业" value="1" />
            <el-option label="林业" value="2" />
            <el-option label="畜牧业" value="3" />
            <el-option label="渔业" value="4" />
            <el-option label="其他" value="5" />
          </el-select>
        </el-form-item>
        <el-form-item label="是否基本农田" required class="form-third">
          <el-select v-model="form.sfjbnt" style="width: 100%">
            <el-option label="是" value="1" />
            <el-option label="否" value="0" />
          </el-select>
        </el-form-item>
      </div>

      <div class="form-row">
        <el-form-item label="地类等级" required class="form-third">
          <el-select v-model="form.dldj" :loading="landGradeLoading" filterable style="width: 100%">
            <el-option v-for="item in landGradeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="所有权性质" class="form-third">
          <el-select v-model="form.syqxz" :loading="ownershipLoading" filterable clearable style="width: 100%">
            <el-option v-for="item in ownershipOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="土地利用类型" class="form-third">
          <el-select v-model="form.tdlylx" filterable clearable style="width: 100%">
            <el-option v-for="item in tdlylxOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
      </div>

      <div class="form-row">
        <el-form-item label="取得方式" class="form-half">
          <el-select v-model="form.cbjyqqdfs" style="width: 100%">
            <el-option label="家庭承包" value="001" />
            <el-option label="其他方式" value="002" />
          </el-select>
        </el-form-item>
        <el-form-item label="是否确权确股" class="form-half">
          <el-select v-model="form.sfqqqg" clearable style="width: 100%">
            <el-option label="是" value="1" />
            <el-option label="否" value="0" />
          </el-select>
        </el-form-item>
      </div>

      <div class="form-row">
        <el-form-item label="合同编码" class="form-half">
          <el-input v-model="form.cbhtbm" placeholder="关联承包合同编码" maxlength="19" />
        </el-form-item>
        <el-form-item label="权证编码" class="form-half">
          <el-input v-model="form.cbjyqzbm" placeholder="经营权证编码" maxlength="19" />
        </el-form-item>
      </div>

      <div class="form-row">
        <el-form-item label="地块东至" class="form-half">
          <el-input v-model="form.dkdz" maxlength="50" />
        </el-form-item>
        <el-form-item label="地块西至" class="form-half">
          <el-input v-model="form.dkxz" maxlength="50" />
        </el-form-item>
      </div>

      <div class="form-row">
        <el-form-item label="地块南至" class="form-half">
          <el-input v-model="form.dknz" maxlength="50" />
        </el-form-item>
        <el-form-item label="地块北至" class="form-half">
          <el-input v-model="form.dkbz" maxlength="50" />
        </el-form-item>
      </div>

      <el-form-item label="备注">
        <el-input v-model="form.dkbzxx" maxlength="300" />
      </el-form-item>

      <el-form-item label="变更原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          placeholder="说明本次新增地块的原因"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="handleSubmit"
      >
        确认新增
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { generateNextSurveyParcelCode } from "../../api/survey";
import { useDictionary } from "../../composables/useDictionary";

const props = defineProps({
  batchId: { type: Number, default: null },
  contractorUid: { type: String, default: "" },
  existingParcelCodes: { type: Array, default: () => [] },
});

const emit = defineEmits(["done", "closed"]);

const visible = ref(false);
const submitting = ref(false);
const submittedThisRound = ref(false);
const geometryPayload = ref(null);
const generatingCode = ref(false);

const { options: landGradeOptions, loading: landGradeLoading } = useDictionary("nyt2539_c08_land_grade");
const { options: ownershipOptions, loading: ownershipLoading } = useDictionary("nyt2539_c06_ownership_property");
const { options: tdlylxDictionaryOptions } = useDictionary("survey_tdlylx_land_use_type");

const tdlylxFallbackOptions = [
  { value: "011", label: "水田" },
  { value: "012", label: "水浇地" },
  { value: "013", label: "旱地" },
  { value: "021", label: "果园" },
  { value: "022", label: "茶园" },
  { value: "023", label: "其他园地" },
  { value: "031", label: "有林地" },
  { value: "032", label: "灌木林地" },
  { value: "033", label: "其他林地" },
  { value: "041", label: "天然牧草地" },
  { value: "042", label: "人工牧草地" },
];

const tdlylxOptions = computed(() =>
  tdlylxDictionaryOptions.value?.length ? tdlylxDictionaryOptions.value : tdlylxFallbackOptions
);

function defaultForm() {
  return {
    dkbm: "",
    dkmc: "",
    scmj: 0,
    htmj: null,
    dklb: "01",
    tdyt: "1",
    sfjbnt: "1",
    dldj: "01",
    syqxz: "10",
    tdlylx: "011",
    cbjyqqdfs: "001",
    sfqqqg: null,
    cbhtbm: "",
    cbjyqzbm: "",
    dkdz: "",
    dkxz: "",
    dknz: "",
    dkbz: "",
    dkbzxx: "",
    reason: "",
  };
}

const form = reactive(defaultForm());

const canSubmit = computed(() =>
  form.dkbm.trim() &&
  form.dkmc.trim() &&
  Number(form.scmj) > 0 &&
  form.dklb &&
  form.tdyt &&
  form.sfjbnt &&
  form.dldj &&
  geometryPayload.value?.geometry
);

function buildExistingCodeSet() {
  return new Set(
    (props.existingParcelCodes || [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  );
}

function ensureLocalUniqueParcelCode(prefix, sequence, candidate) {
  const existingCodes = buildExistingCodeSet();
  let nextSequence = Number(sequence) || 1;
  let nextCode = String(candidate || "").trim();
  if (!prefix) {
    return nextCode;
  }
  while (existingCodes.has(nextCode)) {
    nextSequence += 1;
    nextCode = `${prefix}${String(nextSequence).padStart(5, "0")}`;
  }
  return nextCode;
}

async function handleGenerateCode() {
  if (!props.batchId || !props.contractorUid) {
    ElMessage.warning("当前承包方信息不完整，无法生成地块编码");
    return;
  }
  generatingCode.value = true;
  try {
    const { data } = await generateNextSurveyParcelCode(props.batchId, props.contractorUid);
    const payload = data.data || {};
    form.dkbm = ensureLocalUniqueParcelCode(payload.prefix, payload.sequence, payload.dkbm);
    ElMessage.success("已生成地块编码");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "生成地块编码失败");
  } finally {
    generatingCode.value = false;
  }
}

function open(initialPayload = {}) {
  submittedThisRound.value = false;
  geometryPayload.value = {
    geometry: initialPayload.geometry || null,
    geometrySourceSrid: initialPayload.geometrySourceSrid || 4326,
  };
  Object.assign(form, defaultForm(), {
    scmj: initialPayload.scmj != null ? Number(initialPayload.scmj) : 0,
    htmj: initialPayload.htmj != null ? Number(initialPayload.htmj) : initialPayload.scmj != null ? Number(initialPayload.scmj) : null,
  });
  visible.value = true;
}

function handleClosed() {
  Object.assign(form, defaultForm());
  geometryPayload.value = null;
  emit("closed", { submitted: submittedThisRound.value });
  submittedThisRound.value = false;
}

async function handleSubmit() {
  if (!canSubmit.value) {
    ElMessage.warning("请补充完整属性信息");
    return;
  }
  submitting.value = true;
  try {
    submittedThisRound.value = true;
    emit("done", {
      type: "add_parcel",
      payload: {
        ...form,
        dkbm: form.dkbm.trim(),
        dkmc: form.dkmc.trim(),
        scmj: Number(form.scmj),
        htmj: form.htmj != null ? Number(form.htmj) : undefined,
        geometry: geometryPayload.value?.geometry || null,
        geometrySourceSrid: geometryPayload.value?.geometrySourceSrid || 4326,
      },
    });
    ElMessage.success("新增地块已加入待保存");
    visible.value = false;
  } catch (error) {
    submittedThisRound.value = false;
    ElMessage.error(error?.message || "新增地块失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert {
  margin-bottom: 16px;
}

.parcel-form {
  margin-top: 8px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-half,
.form-third {
  flex: 1;
  min-width: 0;
}
</style>
