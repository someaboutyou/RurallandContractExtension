<template>
  <div class="family-member-panel">
    <!-- 变化提示 -->
    <el-alert
      v-if="changedMembers.length > 0"
      title="家庭成员信息发生变化"
      type="warning"
      :closable="false"
      show-icon
      class="change-alert"
    >
      <template #default>
        共 {{ changedMembers.length }} 名成员发生变化，
        <el-button link type="warning" size="small" @click="diffViewer?.open(batchId, contractorUid)">
          查看变化详情
        </el-button>
      </template>
    </el-alert>

    <!-- 成员表格 -->
    <el-table :data="members" border size="small" v-loading="loading">
      <el-table-column prop="name" label="姓名" min-width="100">
        <template #default="{ row }">
          <span :class="memberChangedClass(row, 'name')">{{ row.name || '-' }}</span>
          <el-tag v-if="row.isHouseholdHead" type="danger" size="small" class="head-tag">户主</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="gender" label="性别" width="70">
        <template #default="{ row }">
          <span :class="memberChangedClass(row, 'gender')">{{ genderLabel(row.gender) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="idNo" label="证件号码" min-width="170">
        <template #default="{ row }">
          <span :class="memberChangedClass(row, 'idNo')">{{ row.idNo || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="relationToHead" label="与户主关系" width="110">
        <template #default="{ row }">
          <span :class="memberChangedClass(row, 'relationToHead')">{{ relationLabel(row.relationToHead) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="isCoOwner" label="共有人" width="80">
        <template #default="{ row }">
          <span :class="memberChangedClass(row, 'isCoOwner')">{{ row.isCoOwner === '1' ? '是' : '否' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="memberResultStatus" label="状态" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.isChanged" type="warning" size="small">已变更</el-tag>
          <el-tag v-else-if="row.memberResultStatus === 'normal'" type="success" size="small">正常</el-tag>
          <el-tag v-else size="small" type="info">{{ row.memberResultStatus }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="标记" min-width="180">
        <template #default="{ row }">
          <el-tag v-if="row.isUrbanSettled" type="warning" size="small" class="flag-tag">进城落户</el-tag>
          <el-tag v-if="row.isMarriedOutWoman" type="info" size="small" class="flag-tag">出嫁女</el-tag>
          <el-tag v-if="row.isDeceased" type="danger" size="small" class="flag-tag">死亡</el-tag>
          <el-tag v-if="row.isFiveGuarantees" size="small" class="flag-tag">五保户</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <span :class="memberChangedClass(row, 'remark')">{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <ChangeDiffViewer ref="diffViewer" />
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import ChangeDiffViewer from "./ChangeDiffViewer.vue";
import { useDictionary } from "../../composables/useDictionary";

const { labelOf: genderLabel } = useDictionary("nyt2539_c17_gender");
const { labelOf: relationDictionaryLabel } = useDictionary("nyt2539_c20_relation_to_head");

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  members: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
});

const diffViewer = ref(null);

const relationFallback = {
  "01": "户主", "02": "配偶", "03": "子", "04": "女",
  "05": "孙子/外孙", "06": "父母", "07": "祖父母/外祖父母", "08": "兄弟姐妹", "09": "其他",
};

function relationLabel(v) {
  return relationDictionaryLabel(v, relationFallback[v] || v || "-");
}

const changedMembers = computed(() => props.members.filter((m) => m.isChanged));
function memberChangedClass(row, field) {
  // 简化判断：如果成员标记了 isChanged，整行关键字段高亮
  if (!row.isChanged) return "";
  const keyFields = ["name", "gender", "idNo", "relationToHead", "isCoOwner", "remark"];
  return keyFields.includes(field) ? "field-changed" : "";
}
</script>

<style scoped>
.family-member-panel { min-height: 200px; }
.change-alert { margin-bottom: 12px; }
.head-tag { margin-left: 6px; }
.flag-tag { margin-right: 4px; }
.field-changed { background-color: #fdf6ec; padding: 2px 6px; border-radius: 3px; }
</style>
