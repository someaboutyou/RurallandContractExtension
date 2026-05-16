<template>
  <el-dialog
    v-model="visible"
    title="变化详情对比"
    width="860px"
    destroy-on-close
  >
    <div v-if="diffs.length === 0" class="no-diff">
      <el-empty description="暂无字段级差异记录" />
    </div>
    <el-table v-else :data="diffs" border max-height="70vh">
      <el-table-column prop="entityType" label="实体类型" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="entityTypeTag(row.entityType)">
            {{ entityTypeLabel(row.entityType) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="entityName" label="实体名称" min-width="120" show-overflow-tooltip />
      <el-table-column prop="fieldLabel" label="字段" width="130" />
      <el-table-column label="变化前（base）" min-width="180">
        <template #default="{ row }">
          <span class="before-value">{{ row.beforeValue ?? '(空)' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变化后（result）" min-width="180">
        <template #default="{ row }">
          <span class="after-value">{{ row.afterValue ?? '(空)' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="changeReason" label="变更原因" width="140" show-overflow-tooltip />
    </el-table>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from "vue";
import { fetchSurveyDiffs } from "../../api/survey";

const visible = ref(false);
const diffs = ref([]);

const entityTypeMap = { cbf: "承包方", cbf_jtcy: "家庭成员", cbdkxx: "地块关系", dk: "地块" };

function entityTypeLabel(type) {
  return entityTypeMap[type] || type;
}
function entityTypeTag(type) {
  return { cbf: "", cbf_jtcy: "success", cbdkxx: "warning", dk: "info" }[type] || "";
}

async function open(batchId, contractorUid) {
  visible.value = true;
  diffs.value = [];
  try {
    const { data } = await fetchSurveyDiffs(batchId, contractorUid, { pageSize: 500 });
    diffs.value = data.data?.items || [];
  } catch {
    diffs.value = [];
  }
}

defineExpose({ open });
</script>

<style scoped>
.before-value { color: #909399; }
.after-value { color: #e6a23c; font-weight: 500; }
.no-diff { padding: 24px 0; }
</style>
