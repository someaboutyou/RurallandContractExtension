<template>
  <el-dialog
    v-model="visible"
    title="新增地块"
    width="640px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      title="新增地块将直接写入调查结果，不关联 base 快照。请确认信息准确。"
      type="info"
      :closable="false"
      show-icon
      class="dialog-alert"
    />

    <el-form :model="form" label-position="top" class="parcel-form">
      <div class="form-row">
        <el-form-item label="地块编码" required class="form-half">
          <el-input v-model="form.dkbm" placeholder="19位地块编码" maxlength="19" />
        </el-form-item>
        <el-form-item label="地块名称" required class="form-half">
          <el-input v-model="form.dkmc" placeholder="例如：村东水田" maxlength="50" />
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
            <el-option label="林地" value="02" />
            <el-option label="草地" value="03" />
            <el-option label="水域" value="04" />
            <el-option label="其他" value="99" />
          </el-select>
        </el-form-item>
        <el-form-item label="土地用途" required class="form-third">
          <el-select v-model="form.tdyt" style="width: 100%">
            <el-option label="种植业" value="1" />
            <el-option label="林业" value="2" />
            <el-option label="畜牧业" value="3" />
            <el-option label="渔业" value="4" />
            <el-option label="其他" value="9" />
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
          <el-input v-model="form.dldj" placeholder="2位代码" maxlength="2" />
        </el-form-item>
        <el-form-item label="所有权性质" class="form-third">
          <el-input v-model="form.syqxz" placeholder="2位代码" maxlength="2" />
        </el-form-item>
        <el-form-item label="土地来源类型" class="form-third">
          <el-input v-model="form.tdlylx" placeholder="3位代码" maxlength="3" />
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
          <el-input v-model="form.cbhtbm" placeholder="关联合同编码" maxlength="19" />
        </el-form-item>
        <el-form-item label="权证编码" class="form-half">
          <el-input v-model="form.cbjyqzbm" placeholder="经营权证编码" maxlength="19" />
        </el-form-item>
      </div>

      <div class="form-row">
        <el-form-item label="地块地址" class="form-half">
          <el-input v-model="form.dkdz" maxlength="50" />
        </el-form-item>
        <el-form-item label="四至" class="form-half">
          <el-input v-model="form.dkxz" placeholder="东至/西至/南至/北至" maxlength="50" />
        </el-form-item>
      </div>

      <el-form-item label="备注">
        <el-input v-model="form.dkbz" maxlength="50" />
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
import { addSurveyParcel } from "../../api/survey";

const emit = defineEmits(["done"]);

const visible = ref(false);
const submitting = ref(false);
const batchId = ref(null);
const contractorUid = ref("");

function defaultForm() {
  return {
    dkbm: "", dkmc: "", scmj: 0, htmj: null, dklb: "01", tdyt: "1",
    sfjbnt: "1", dldj: "01", syqxz: "10", tdlylx: "001",
    cbjyqqdfs: "001", sfqqqg: null, cbhtbm: "", cbjyqzbm: "",
    dkdz: "", dkxz: "", dkbz: "", reason: "",
  };
}
const form = reactive(defaultForm());

const canSubmit = computed(() =>
  form.dkbm.trim() && form.dkmc.trim() && form.scmj > 0 &&
  form.dklb && form.tdyt && form.sfjbnt && form.dldj.trim()
);

function open(bid, cuid) {
  batchId.value = bid;
  contractorUid.value = cuid;
  Object.assign(form, defaultForm());
  visible.value = true;
}

function resetForm() {
  Object.assign(form, defaultForm());
}

async function handleSubmit() {
  if (!canSubmit.value) {
    ElMessage.warning("请填写必填项");
    return;
  }
  submitting.value = true;
  try {
    await addSurveyParcel(batchId.value, contractorUid.value, {
      ...form,
      scmj: Number(form.scmj),
      htmj: form.htmj != null ? Number(form.htmj) : undefined,
    });
    ElMessage.success("地块已新增");
    visible.value = false;
    emit("done");
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || "新增地块失败");
  } finally {
    submitting.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert { margin-bottom: 16px; }
.parcel-form { margin-top: 8px; }
.form-row { display: flex; gap: 12px; }
.form-half { flex: 1; min-width: 0; }
.form-third { flex: 1; min-width: 0; }
</style>
