<template>
  <div class="contractor-member-panel">
    <!-- 变化提示 -->
    <el-alert
      v-if="result.isChanged"
      title="承包方信息已发生变化"
      type="warning"
      :closable="false"
      show-icon
      class="change-alert"
    >
      <template #default>
        <el-button link type="warning" size="small" @click="diffViewer?.open(batchId, contractorUid)">
          查看变化详情
        </el-button>
      </template>
    </el-alert>

    <!-- 承包方基本信息（可编辑） -->
    <div class="section-title">承包方信息</div>
    <el-form :model="contractorForm" label-position="top" class="contractor-form">
      <div class="form-grid-3">
        <el-form-item label="承包方编码" :class="changedClass('code')">
          <el-input v-model="contractorForm.code" placeholder="18位编码" maxlength="18" />
        </el-form-item>
        <el-form-item label="承包方名称" :class="changedClass('name')">
          <el-input v-model="contractorForm.name" placeholder="承包方名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="承包方类型" :class="changedClass('typeCode')">
          <el-select v-model="contractorForm.typeCode">
            <el-option label="农户" value="1" />
            <el-option label="个人" value="2" />
            <el-option label="单位" value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="证件类型" :class="changedClass('idType')">
          <el-select v-model="contractorForm.idType">
            <el-option label="居民身份证" value="1" />
            <el-option label="户口簿" value="2" />
            <el-option label="军官证" value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="证件号码" :class="changedClass('idNo')">
          <el-input v-model="contractorForm.idNo" placeholder="证件号码" maxlength="20" />
        </el-form-item>
        <el-form-item label="联系电话" :class="changedClass('mobile')">
          <el-input v-model="contractorForm.mobile" placeholder="联系电话" maxlength="20" />
        </el-form-item>
      </div>
      <el-form-item label="承包方地址" :class="changedClass('address')">
        <el-input v-model="contractorForm.address" placeholder="详细地址" maxlength="100" />
      </el-form-item>
      <div class="form-grid-2">
        <el-form-item label="邮政编码" :class="changedClass('postcode')">
          <el-input v-model="contractorForm.postcode" placeholder="6位邮编" maxlength="6" />
        </el-form-item>
        <el-form-item label="村民小组" :class="changedClass('groupRegionName')">
          <el-input v-model="contractorForm.groupRegionName" placeholder="村民小组" maxlength="120" />
        </el-form-item>
      </div>
    </el-form>

    <el-divider />

    <!-- 家庭成员（可编辑表格） -->
    <div class="section-header">
      <span class="section-title">家庭成员（{{ visibleMembers.length }} 人）</span>
      <el-button type="primary" plain size="small" @click="addMember">+ 添加成员</el-button>
    </div>

    <el-table :data="visibleMembers" border size="small" class="member-table">
      <!-- 状态 -->
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag v-if="isNewRow(row)" type="success" size="small">新增</el-tag>
          <el-tag v-else-if="isModifiedRow(row)" type="warning" size="small">已修改</el-tag>
          <el-tag v-else-if="row._deleted" type="danger" size="small">待删除</el-tag>
          <el-tag v-else type="info" size="small">正常</el-tag>
        </template>
      </el-table-column>

      <!-- 姓名 -->
      <el-table-column label="姓名" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.name" size="small" :disabled="row._deleted" @change="markModified(row)" />
        </template>
      </el-table-column>

      <!-- 性别 -->
      <el-table-column label="性别" width="80">
        <template #default="{ row }">
          <el-select v-model="row.gender" size="small" :disabled="row._deleted" @change="markModified(row)">
            <el-option label="男" value="1" />
            <el-option label="女" value="2" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 证件类型 -->
      <el-table-column label="证件类型" width="100">
        <template #default="{ row }">
          <el-select v-model="row.idType" size="small" :disabled="row._deleted" @change="markModified(row)">
            <el-option label="身份证" value="1" />
            <el-option label="户口簿" value="2" />
            <el-option label="军官证" value="3" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 证件号码 -->
      <el-table-column label="证件号码" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.idNo" size="small" :disabled="row._deleted" @change="markModified(row)" />
        </template>
      </el-table-column>

      <!-- 与户主关系 -->
      <el-table-column label="与户主关系" width="110">
        <template #default="{ row }">
          <el-select v-model="row.relationToHead" size="small" :disabled="row._deleted" @change="markModified(row)">
            <el-option label="本人" value="01" />
            <el-option label="配偶" value="02" />
            <el-option label="子女" value="03" />
            <el-option label="父母" value="06" />
            <el-option label="兄弟姐妹" value="08" />
            <el-option label="其他" value="09" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 共有人 -->
      <el-table-column label="共有人" width="80">
        <template #default="{ row }">
          <el-select v-model="row.isCoOwner" size="small" :disabled="row._deleted" @change="markModified(row)">
            <el-option label="是" value="1" />
            <el-option label="否" value="0" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 户主标记与操作 -->
      <el-table-column label="户主" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.isHouseholdHead" type="danger" size="small" effect="dark">户主</el-tag>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.note" size="small" :disabled="row._deleted" @change="markModified(row)" />
        </template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row.isHouseholdHead"
            link
            type="warning"
            size="small"
            :disabled="row._deleted"
            @click="setAsHead(row)"
          >
            设为户主
          </el-button>
          <el-button
            v-if="!row._deleted && !row.isHouseholdHead"
            link
            type="danger"
            size="small"
            @click="toggleDelete(row)"
          >
            删除
          </el-button>
          <el-button
            v-if="row._deleted"
            link
            type="primary"
            size="small"
            @click="toggleDelete(row)"
          >
            恢复
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <ChangeDiffViewer ref="diffViewer" />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import ChangeDiffViewer from "./ChangeDiffViewer.vue";

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  result: { type: Object, required: true },
  changedFields: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:result"]);

const diffViewer = ref(null);

// 承包方可编辑表单（双向同步到 result）
const contractorForm = reactive({
  code: "",
  name: "",
  typeCode: "1",
  idType: "1",
  idNo: "",
  mobile: "",
  address: "",
  postcode: "",
  groupRegionName: "",
});

// 初始化 contractorForm 并保持同步
watch(
  () => props.result,
  (r) => {
    if (!r) return;
    Object.assign(contractorForm, {
      code: r.code || "",
      name: r.name || "",
      typeCode: r.typeCode || "1",
      idType: r.idType || "1",
      idNo: r.idNo || "",
      mobile: r.mobile || "",
      address: r.address || "",
      postcode: r.postcode || "",
      groupRegionName: r.groupRegionName || r.groupRegionCode || "",
    });
  },
  { immediate: true, deep: true },
);

// 反向同步：表单变更 → result
watch(contractorForm, () => {
  const r = props.result;
  if (!r) return;
  r.code = contractorForm.code;
  r.name = contractorForm.name;
  r.typeCode = contractorForm.typeCode;
  r.idType = contractorForm.idType;
  r.idNo = contractorForm.idNo;
  r.mobile = contractorForm.mobile;
  r.address = contractorForm.address;
  r.postcode = contractorForm.postcode;
  r.groupRegionName = contractorForm.groupRegionName;
}, { deep: true });

// 记录初始快照用于判断修改
const initialSnapshots = ref(new Map());

watch(
  () => props.result?.familyMembers,
  (members) => {
    initialSnapshots.value = new Map();
    if (!members) return;
    for (const m of members) {
      if (m.memberUid) {
        initialSnapshots.value.set(m.memberUid, {
          name: m.name,
          gender: m.gender,
          idType: m.idType,
          idNo: m.idNo,
          relationToHead: m.relationToHead,
          isCoOwner: m.isCoOwner,
          note: m.note,
        });
      }
    }
  },
  { immediate: true },
);

// 可见成员（含被标记删除的，灰色显示）
const visibleMembers = computed(() => {
  return (props.result.familyMembers || []).map((m) => ({
    ...m,
    _deleted: m._deleted || false,
    _isNew: m._isNew || false,
  }));
});

function isNewRow(row) {
  return row._isNew || (!row.memberUid && row.memberResultStatus === "added");
}

function isModifiedRow(row) {
  if (row._deleted || isNewRow(row)) return false;
  const snap = initialSnapshots.value.get(row.memberUid);
  if (!snap) return false;
  return (
    snap.name !== row.name ||
    snap.gender !== row.gender ||
    snap.idType !== row.idType ||
    snap.idNo !== row.idNo ||
    snap.relationToHead !== row.relationToHead ||
    snap.isCoOwner !== row.isCoOwner ||
    snap.note !== (row.note || "")
  );
}

function markModified(_row) {
  // computed 自动判断，无需手动标记
}

function addMember() {
  props.result.familyMembers.push({
    memberUid: "",
    name: "",
    gender: "1",
    idType: "1",
    idNo: "",
    relationToHead: "09",
    noteCode: "",
    isCoOwner: "0",
    note: "",
    memberResultStatus: "added",
    surveyStatus: "surveyed",
    isHouseholdHead: false,
    isUrbanSettled: false,
    isMarriedOutWoman: false,
    isDeceased: false,
    isFiveGuarantees: false,
    changeReason: "",
    policyBasis: "",
    rightsDisposition: "",
    remark: "",
    _isNew: true,
  });
}

function setAsHead(row) {
  // 取消其他成员的户主标记
  for (const m of props.result.familyMembers) {
    m.isHouseholdHead = false;
  }
  row.isHouseholdHead = true;
  row.relationToHead = "01";
  if (!isNewRow(row)) markModified(row);
}

function toggleDelete(row) {
  row._deleted = !row._deleted;
  if (row._deleted) {
    row.memberResultStatus = "deleted";
  } else {
    row.memberResultStatus = isNewRow(row) ? "added" : "normal";
  }
}

// 获取有效成员（排除被标记删除的）
function getValidMembers() {
  return (props.result.familyMembers || []).filter((m) => !m._deleted);
}

// 变化高亮
const fieldKeyMap = {
  code: "code", name: "name", typeCode: "typeCode", idType: "idType",
  idNo: "idNo", mobile: "mobile", address: "address", postcode: "postcode",
  groupRegionName: "groupRegionName",
};

function changedClass(field) {
  const key = fieldKeyMap[field];
  return props.changedFields.includes(key) ? "field-changed" : "";
}

defineExpose({ getValidMembers });
</script>

<style scoped>
.contractor-member-panel { min-height: 200px; }
.change-alert { margin-bottom: 12px; }

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.contractor-form { margin-bottom: 0; }
.form-grid-3 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 0 12px;
}
.form-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}

.member-table { margin-top: 0; }

.field-changed :deep(.el-input__wrapper),
.field-changed :deep(.el-select__wrapper) {
  background-color: #fdf6ec;
  box-shadow: 0 0 0 1px #e6a23c inset;
}
</style>
