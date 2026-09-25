<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="1000px"
    destroy-on-close
    @closed="handleClosed"
  >
    <div v-loading="loading" element-loading-text="正在读取界址点 / 界址线...">
      <el-alert
        title="界址点与界址线由地块图形自动生成，相邻地块共点共线时全库只存一条；此处只维护属性，保存后立即生效。"
        type="info"
        :closable="false"
        show-icon
        class="dialog-alert"
      />

      <el-descriptions :column="4" size="small" border class="boundary-meta">
        <el-descriptions-item label="地块编码">{{ boundary.dkbm || "-" }}</el-descriptions-item>
        <el-descriptions-item label="地块名称">{{ boundary.dkmc || "-" }}</el-descriptions-item>
        <el-descriptions-item label="界址点 / 界址线">
          {{ points.length }} 点 / {{ lines.length }} 线
        </el-descriptions-item>
        <el-descriptions-item label="坐标系统">
          {{ boundary.mappingUnit || "米" }} · {{ boundary.cordSystem || "-" }}
        </el-descriptions-item>
      </el-descriptions>

      <el-tabs v-model="activeTab" class="boundary-tabs">
        <el-tab-pane :label="`界址点（${points.length}）`" name="points">
          <div class="boundary-bulk">
            <span class="bulk-label">界标类型批量设置</span>
            <el-select
              v-model="bulkMark"
              size="small"
              clearable
              placeholder="选择界标类型"
              style="width: 140px"
            >
              <el-option
                v-for="item in markTypes"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-button
              size="small"
              :disabled="!canEdit || !bulkMark"
              @click="applyBulkMark"
            >
              应用到全部界址点
            </el-button>
          </div>

          <el-table :data="points" border size="small" max-height="46vh">
            <el-table-column prop="seq" label="序号" width="60" align="center" />
            <el-table-column prop="code" label="点号" width="78" align="center" />
            <el-table-column prop="x" label="X（北，m）" width="126" align="right" />
            <el-table-column prop="y" label="Y（东，m）" width="138" align="right" />
            <el-table-column prop="edge" label="边长（m）" width="100" align="right" />
            <el-table-column label="界标类型" width="132">
              <template #default="{ row }">
                <el-select
                  v-model="row.jblx"
                  size="small"
                  clearable
                  :disabled="!canEdit"
                  placeholder="未填"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in markTypes"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="150">
              <template #default="{ row }">
                <el-input
                  v-model="row.bz"
                  size="small"
                  maxlength="200"
                  :disabled="!canEdit"
                  placeholder="选填"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`界址线（${lines.length}）`" name="lines">
          <div class="boundary-bulk">
            <span class="bulk-label">界址线类别批量设置</span>
            <el-select
              v-model="bulkCategory"
              size="small"
              clearable
              placeholder="选择类别"
              style="width: 140px"
            >
              <el-option
                v-for="item in lineCategories"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-button
              size="small"
              :disabled="!canEdit || !bulkCategory"
              @click="applyBulkCategory"
            >
              应用到全部界址线
            </el-button>

            <span class="bulk-label bulk-label-gap">界址线位置批量设置</span>
            <el-select
              v-model="bulkPosition"
              size="small"
              clearable
              placeholder="选择位置"
              style="width: 120px"
            >
              <el-option
                v-for="item in linePositions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-button
              size="small"
              :disabled="!canEdit || !bulkPosition"
              @click="applyBulkPosition"
            >
              应用到全部界址线
            </el-button>
          </div>

          <el-table :data="lines" border size="small" max-height="46vh">
            <el-table-column prop="seq" label="序号" width="60" align="center" />
            <el-table-column label="起点 → 终点" width="130" align="center">
              <template #default="{ row }">{{ row.fromCode }} → {{ row.toCode }}</template>
            </el-table-column>
            <el-table-column label="界址线类别" width="150">
              <template #default="{ row }">
                <el-select
                  v-model="row.jzxlb"
                  size="small"
                  clearable
                  :disabled="!canEdit"
                  placeholder="未填"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in lineCategories"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="界址线位置" width="130">
              <template #default="{ row }">
                <el-select
                  v-model="row.jzxwz"
                  size="small"
                  clearable
                  :disabled="!canEdit"
                  placeholder="未填"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in linePositions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="界址线说明" min-width="180">
              <template #default="{ row }">
                <el-input
                  v-model="row.jzxsm"
                  size="small"
                  maxlength="200"
                  :disabled="!canEdit"
                  placeholder="选填，如：与张三户相邻"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>

      <div v-if="!loading && !points.length && !lines.length" class="boundary-empty">
        该地块没有图形（或图形只有少于 2 个界址点），无法维护界址点 / 界址线。
      </div>
    </div>

    <template #footer>
      <span v-if="!canEdit" class="boundary-readonly">当前状态只读，不能修改界址属性</span>
      <el-button @click="visible = false">关闭</el-button>
      <el-button v-if="canEdit" type="primary" :loading="saving" @click="handleSave">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";

import { fetchParcelBoundary, saveParcelBoundary } from "../../api/survey";

const props = defineProps({
  canManage: { type: Boolean, default: false },
});

const emit = defineEmits(["saved"]);

const visible = ref(false);
const loading = ref(false);
const saving = ref(false);
const activeTab = ref("points");

const boundary = ref({});
const points = ref([]);
const lines = ref([]);

const target = { batchId: null, contractorUid: "", dkbm: "" };

const bulkMark = ref("");
const bulkCategory = ref("");
const bulkPosition = ref("");

const canEdit = computed(() => props.canManage && boundary.value.editable !== false);
const markTypes = computed(() => boundary.value.options?.markTypes || []);
const lineCategories = computed(() => boundary.value.options?.lineCategories || []);
const linePositions = computed(() => boundary.value.options?.linePositions || []);
const dialogTitle = computed(() =>
  target.dkbm ? `界址点 / 界址线维护 - ${target.dkbm}` : "界址点 / 界址线维护"
);

async function open({ batchId, contractorUid, dkbm }) {
  target.batchId = batchId;
  target.contractorUid = contractorUid;
  target.dkbm = dkbm;
  visible.value = true;
  await load();
}

async function load() {
  if (!target.batchId || !target.contractorUid || !target.dkbm) return;
  loading.value = true;
  try {
    const { data } = await fetchParcelBoundary(
      target.batchId,
      target.contractorUid,
      target.dkbm
    );
    applyBoundary(data?.data);
  } catch (error) {
    ElMessage.error(
      error?.response?.data?.detail || "界址点 / 界址线读取失败，请稍后重试。"
    );
  } finally {
    loading.value = false;
  }
}

function applyBoundary(payload) {
  boundary.value = payload || {};
  // 复制一份，避免直接改动接口返回对象
  points.value = (payload?.points || []).map((item) => ({ ...item }));
  lines.value = (payload?.lines || []).map((item) => ({ ...item }));
}

function handleClosed() {
  boundary.value = {};
  points.value = [];
  lines.value = [];
  activeTab.value = "points";
  bulkMark.value = "";
  bulkCategory.value = "";
  bulkPosition.value = "";
  target.batchId = null;
  target.contractorUid = "";
  target.dkbm = "";
}

function applyBulkMark() {
  points.value.forEach((item) => {
    item.jblx = bulkMark.value;
  });
}

function applyBulkCategory() {
  lines.value.forEach((item) => {
    item.jzxlb = bulkCategory.value;
  });
}

function applyBulkPosition() {
  lines.value.forEach((item) => {
    item.jzxwz = bulkPosition.value;
  });
}

async function handleSave() {
  saving.value = true;
  try {
    const payload = {
      points: points.value.map((item) => ({
        seq: item.seq,
        jzdh: item.jzdh || null,
        jblx: item.jblx || null,
        bz: item.bz || null,
      })),
      lines: lines.value.map((item) => ({
        seq: item.seq,
        fromCode: item.fromCode || null,
        toCode: item.toCode || null,
        jzxlb: item.jzxlb || null,
        jzxwz: item.jzxwz || null,
        jzxsm: item.jzxsm || null,
      })),
    };
    const { data } = await saveParcelBoundary(
      target.batchId,
      target.contractorUid,
      target.dkbm,
      payload
    );
    applyBoundary(data?.data);
    ElMessage.success("界址点 / 界址线属性已保存");
    emit("saved", { dkbm: target.dkbm });
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || "保存失败，请稍后重试。");
  } finally {
    saving.value = false;
  }
}

defineExpose({ open });
</script>

<style scoped>
.dialog-alert {
  margin-bottom: 12px;
}

.boundary-meta {
  margin-bottom: 8px;
}

.boundary-tabs {
  margin-top: 4px;
}

.boundary-bulk {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.bulk-label {
  font-size: 12px;
  color: #606266;
}

.bulk-label-gap {
  margin-left: 12px;
}

.boundary-empty {
  margin-top: 12px;
  font-size: 13px;
  color: #909399;
  text-align: center;
}

.boundary-readonly {
  margin-right: 12px;
  font-size: 12px;
  color: #e6a23c;
}
</style>
