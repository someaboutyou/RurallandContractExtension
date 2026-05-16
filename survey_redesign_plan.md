# 调查录入页面改造计划（最终版）

## 一、用户确认结果汇总

| 决策项 | 结论 |
|--------|------|
| 合同信息 | 显示电子合同(只读) + 扫描合同附件，提供打印和上传功能 |
| 注销承包方 | 从 result 表**物理删除**承包方及家庭成员，base 保留，diff 记录删除过程，支持恢复 |
| 切割地块 | 支持三种方式：上传 SHP、手绘(地图交互)、输入面积 |
| 分户地块分配 | 手动+自动结合（系统给默认建议，用户可调整） |
| 操作按钮位置 | 统一顶部工具栏 |
| 旧功能保留 | 仅保留"调查附件"和"转业务申请"，其余整合或移除 |
| 变化标记样式 | 黄色背景高亮 |
| Tab 布局 | 4 个基础信息 tab：承包方信息、家庭成员信息、地块信息、合同信息 |

---

## 二、改造后的 Dialog 布局

```
┌─────────────────────────────────────────────────────┐
│  调查录入 - [承包方名称]                              │
├─────────────────────────────────────────────────────┤
│  [更换户主] [注销承包方] [分户] [合户] [地块互换]    │  ← 顶部工具栏
│  [新增地块] [切割地块] [家庭成员维护]                 │
├─────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────┐   │
│  │ 承包方信息 │ 家庭成员 │ 地块信息 │ 合同信息 │   │  ← 4 个 Tab
│  ├──────────────────────────────────────────────┤   │
│  │                                              │   │
│  │  当前 Tab 内容（每个字段有变化时黄色高亮）     │   │
│  │  [查看变化] 按钮可打开 ChangeDiffViewer       │   │
│  │                                              │   │
│  └──────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  [调查附件] [转业务申请]                             │  ← 辅助功能
├─────────────────────────────────────────────────────┤
│                                    [保存] [取消]     │
└─────────────────────────────────────────────────────┘
```

---

## 三、各 Tab 详细设计

### 3.1 承包方信息 Tab
- 表单展示 `survey_cbf_result` 全部字段
- 黄色高亮标记变化字段，点击 [查看变化] 对比 base/result
- 字段包括：承包方编码、名称、类型、证件、地址、联系电话等

### 3.2 家庭成员信息 Tab
- 表格展示所有家庭成员
- 每行含：姓名、证件号码、与户主关系、性别、是否户主(徽章)、是否共有人等
- 表格上方有"新增成员"按钮
- 每行操作：设为户主、编辑、删除
- 黄色高亮标记变化成员/字段
- 变化成员旁显示 [查看变化]

### 3.3 地块信息 Tab
- **布局**：左侧地图(OpenLayers) + 右侧地块列表
- 地图复用 `useDialogMap` composable，加载 `survey_dk_result` 图层
- 列表显示：地块编码、名称、面积、类别、四至等
- 点击列表行 → 地图高亮对应地块
- 黄色高亮标记变化地块/字段
- 操作入口在顶部工具栏（新增地块、切割地块、地块互换）

### 3.4 合同信息 Tab
- **电子合同预览区**：根据合同模板渲染的合同内容（只读 HTML/PDF 预览）
- **合同附件区**：上传的扫描合同图片/PDF 列表，支持预览和下载
- 功能按钮：打印合同、上传合同附件
- 合同数据来源：通过 `cbfbm` 关联 `cbht` 表 + 附件表

---

## 四、8 个操作功能详细设计

### 4.1 更换户主
- **触发**：工具栏按钮
- **弹窗**：下拉选择家庭成员列表（仅当前户内成员）
- **后端逻辑**：
  1. 查询旧户主（`is_household_head=True`），设为 False
  2. 设置新户主的 `is_household_head=True`
  3. 创建 ChangeRecord(type=`change_head`) + ChangeDiff(记录户主变更前后)
- **校验**：户内至少保留一个成员，新户主年龄需≥18岁(如系统有年龄数据)

### 4.2 注销承包方
- **触发**：工具栏按钮（需二次确认弹窗）
- **后端逻辑**：
  1. 将该承包方的 `SurveyCbfResult` **物理删除**
  2. 将其所有 `SurveyCbfJtcyResult` **物理删除**
  3. 将其所有 `SurveyCbdkxxResult` **物理删除**
  4. 创建 ChangeRecord(type=`deregister`)，**将删除前的完整数据存入 `before_summary` JSON 字段**
  5. 创建 ChangeDiff 记录每个被删实体的快照
  6. 若地块需要处理：相应 `SurveyDkResult` 标记或删除(视业务而定)
- **关键**：`before_summary` 需存储完整可恢复数据，包括：
  ```json
  {
    "contractor": { /* 完整 CbfResult 字段 */ },
    "members": [ { /* 完整 JtcyResult 字段 */ }, ... ],
    "parcel_relations": [ { /* 完整 CbdkxxResult 字段 */ }, ... ]
  }
  ```
- **数据恢复**：(后续实现) 通过 ChangeRecord 的 `before_summary` 重建 result 数据
- **变更记录**：新增 `change_type` = `deregister`

### 4.3 分户
- **触发**：工具栏按钮 → 弹窗
- **弹窗内容**：
  1. 填写新户信息：新承包方编码(cbfbm)、名称(cbfmc)
  2. **成员分配**：左侧原户成员列表，右侧新户成员列表，支持拖拽/勾选移动
     - 系统默认：按成员人数大致均分建议（如5人→3+2，户主留在原户）
     - 用户可手动调整
  3. **地块分配**：左侧原地块列表，右侧新户地块列表
     - 系统默认：按面积比例大致均分建议
     - 用户可手动调整
  4. 必填：变更原因
- **后端逻辑**：
  1. 创建新 `SurveyCbfResult`（base_id 指向空或新 base 记录）
  2. 迁移指定成员的 `cbfbm` 到新户
  3. 迁移指定地块关系(`survey_cbdkxx_result`)的 `cbfbm` 到新户
  4. 更新双方承包方成员数量
  5. 创建新 `SurveyContractorTask`
  6. 创建 ChangeRecord(type=`split_household`) 各一份（原户+新户）
  7. 创建 ChangeDiff 记录迁移细节

### 4.4 合户
- **触发**：工具栏按钮 → 弹窗选择目标承包方
- **弹窗内容**：
  1. 下拉选择合入的目标承包方（同批次的承包方列表）
  2. 预览：合并后成员列表、合并后地块列表
  3. 必填：变更原因
- **后端逻辑**：
  1. 将源户所有成员的 `cbfbm` 改为目标户
  2. 将源户所有地块关系的 `cbfbm` 改为目标户
  3. 物理删除源户 `SurveyCbfResult`（base 保留，before_summary 存快照）
  4. 更新目标户成员数量
  5. 创建 ChangeRecord(type=`merge_household`)（目标户 + 被合并户各一份）

### 4.5 承包方地块互换
- **触发**：工具栏按钮 → 弹窗
- **弹窗内容**：
  1. 下拉选择目标承包方
  2. 左侧：本方地块列表(多选)，右侧：对方地块列表(多选)
  3. 交换预览
  4. 必填：变更原因
- **后端逻辑**：
  1. 将选中源地块的 `survey_cbdkxx_result.cbfbm` 改为目标户
  2. 将选中目标地块的 `survey_cbdkxx_result.cbfbm` 改为源户
  3. 创建 ChangeRecord(type=`swap_parcels`)（双方各一份）
  4. 创建 ChangeDiff 记录每个地块的归属变更

### 4.6 新增地块
- **触发**：工具栏按钮 → 弹窗表单
- **弹窗内容**：
  1. 地块基本信息：编码、名称、实测面积、类别、土地利用类型、四至等
  2. 可选：关联合同编号
  3. 空间数据：(可选) 上传 SHP 文件或在地图上绘制
  4. 必填：变更原因
- **后端逻辑**：
  1. 创建新 `SurveyDkResult`（base_id 为空，表示新增）
  2. 创建新 `SurveyCbdkxxResult` 关联承包方和地块
  3. 创建 ChangeRecord(type=`add_parcel`)
  4. 创建 ChangeDiff 记录新增详情

### 4.7 切割地块
- **触发**：工具栏按钮 → 在地块列表中选中一个地块 → 弹窗
- **三种切割方式**：
  1. **输入面积**：输入新地块面积，系统自动计算剩余面积
  2. **手绘**：在地图上绘制分割线或多边形，系统计算面积(需要 GIS 交互)
  3. **上传 SHP**：上传 Shapefile，系统解析几何并计算面积
- **后端逻辑**：
  1. 修改原 `SurveyDkResult` 面积 = 原面积 - 新地块面积
  2. 创建新 `SurveyDkResult`（面积 = 切割面积）
  3. 创建新 `SurveyCbdkxxResult` 关联新地块
  4. 更新原 `SurveyCbdkxxResult` 的面积字段
  5. 创建 ChangeRecord(type=`split_parcel`)
  6. 创建 ChangeDiff 记录切割前后对比

### 4.8 家庭成员维护
- **触发**：工具栏按钮 → 弹窗
- **弹窗内容**：
  1. **新增**：表单填写姓名、证件、性别、与户主关系、是否共有人等
  2. **编辑**：点击已有成员行，弹出编辑表单
  3. **删除**：选中成员，二次确认后删除
  4. 批量操作支持：可以一次提交多个增删改操作
- **后端逻辑**：
  1. `members_to_add` → 批量插入 `SurveyCbfJtcyResult`（base_id 为空，新增）
  2. `members_to_update` → 批量更新 `SurveyCbfJtcyResult`
  3. `members_to_delete` → 物理删除 `SurveyCbfJtcyResult`（before_value 存快照到 diff）
  4. 更新承包方成员数量
  5. 创建 ChangeRecord(type=`member_maintain`)
  6. 创建 ChangeDiff 记录每个成员的变更

---

## 五、数据库变更

### 5.1 SurveyCbfResult 新增字段
```python
# 删除相关（注销/合户后物理删除，但记录在 change_record 中）
# 无需新增 cbf_status 字段 —— 采用物理删除 + before_summary 方案
```

### 5.2 SurveyChangeRecord 扩展 change_type 值
| 操作 | change_type |
|------|-------------|
| 更换户主 | `change_head` |
| 注销承包方 | `deregister` |
| 分户 | `split_household` |
| 合户 | `merge_household` |
| 地块互换 | `swap_parcels` |
| 新增地块 | `add_parcel` |
| 切割地块 | `split_parcel` |
| 家庭成员维护 | `member_maintain` |

### 5.3 SurveyContractorTask 新增状态
- `deregistered` — 已注销
- `merged` — 已合并（合户中被合并方）

---

## 六、新增 API 端点

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/batches/{id}/results/{uid}/change-head` | `{new_head_member_uid, reason}` | 更换户主 |
| POST | `/batches/{id}/results/{uid}/deregister` | `{reason}` | 注销承包方 |
| POST | `/batches/{id}/results/{uid}/split` | `{new_cbfbm, new_cbfmc, member_uids, parcel_info_uids, reason}` | 分户 |
| POST | `/batches/{id}/results/{uid}/merge` | `{target_contractor_uid, reason}` | 合户 |
| POST | `/batches/{id}/results/{uid}/swap-parcels` | `{target_uid, source_uids, target_uids, reason}` | 地块互换 |
| POST | `/batches/{id}/results/{uid}/add-parcel` | `{dkbm, dkmc, scmj, ...}` | 新增地块 |
| POST | `/batches/{id}/results/{uid}/split-parcel` | `{parcel_info_uid, new_dkbm, new_dkmc, new_scmj, geometry_data?, reason}` | 切割地块 |
| POST | `/batches/{id}/results/{uid}/maintain-members` | `{members_to_add: [], members_to_update: [], members_to_delete: [], reason}` | 家庭成员维护 |
| GET  | `/batches/{id}/results/{uid}/contract` | - | 获取关联合同+附件 |
| POST | `/batches/{id}/results/{uid}/contract/upload` | FormData(file) | 上传合同附件 |
| POST | `/batches/{id}/results/{uid}/contract/print` | - | 打印合同(返回PDF) |
| POST | `/batches/{id}/results/{uid}/parcels/upload-shp` | FormData(file) + `parcel_info_uid` | 上传切割线/面SHP，对原地块执行空间切割 |
| POST | `/batches/{id}/results/{uid}/recover/{change_id}` | - | 从变更记录恢复已删除数据 |

---

## 七、前端文件结构

```
frontend/src/
├── views/
│   └── SurveyView.vue                    # 修改：重构 dialog（减少代码量）
├── components/survey/
│   ├── SurveyEntryDialog.vue             # 新建：主 dialog 容器（替代内联代码）
│   │   ├── SurveyToolbar.vue             # 新建：顶部操作工具栏
│   │   ├── ContractorInfoPanel.vue       # 新建：承包方信息 tab
│   │   ├── FamilyMemberPanel.vue         # 新建：家庭成员信息 tab
│   │   ├── ParcelInfoPanel.vue           # 新建：地块信息 tab（含地图）
│   │   ├── ContractInfoPanel.vue         # 新建：合同信息 tab
│   │   ├── ChangeDiffViewer.vue          # 新建：变化查看器（base vs result 对比）
│   │   └── panels/
│   │       ├── AttachmentPanel.vue       # 重构：调查附件面板
│   │       └── RequestGenPanel.vue       # 保留：转业务申请面板
│   └── dialogs/
│       ├── ChangeHeadDialog.vue          # 新建：更换户主
│       ├── DeregisterDialog.vue          # 新建：注销承包方（含二次确认）
│       ├── SplitHouseholdDialog.vue      # 新建：分户（含成员+地块分配）
│       ├── MergeHouseholdDialog.vue      # 新建：合户
│       ├── SwapParcelsDialog.vue         # 新建：地块互换
│       ├── AddParcelDialog.vue           # 新建：新增地块
│       ├── SplitParcelDialog.vue         # 新建：切割地块（三种方式）
│       └── MaintainMembersDialog.vue     # 新建：家庭成员维护
├── api/
│   └── survey.js                         # 修改：新增操作 API 调用
└── composables/
    └── useSurveyOperations.js            # 新建：调查操作逻辑
```

---

## 八、后端文件变更

| 文件 | 变更类型 | 内容 |
|------|---------|------|
| `backend/app/models/survey.py` | 修改 | SurveyContractorTask 新增状态值 |
| `backend/app/schemas/survey.py` | 修改 | 新增 8 个操作的 Request/Response schema |
| `backend/app/api/v1/endpoints/survey.py` | 修改 | 新增 11 个端点 |
| `backend/app/services/survey_service.py` | 修改 | 新增 8 个核心方法 + 辅助方法 |
| `backend/app/db/migrations.py` | 修改 | 新增 migration 脚本(如需要) |

---

## 九、实施顺序

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **Phase 1** | ContractInfoPanel + 合同 API(get/upload/print) | 无 |
| **Phase 2** | 4 tab 容器重构 + ChangeDiffViewer + 黄色高亮标记 | Phase 1 |
| **Phase 3** | 更换户主 + 家庭成员维护 | Phase 2 |
| **Phase 4** | 注销承包方(含恢复) + 新增地块 | Phase 2 |
| **Phase 5** | 切割地块(SHP/手绘/输入面积) | Phase 4 |
| **Phase 6** | 承包方地块互换 | Phase 2 |
| **Phase 7** | 分户 | Phase 3, 4 |
| **Phase 8** | 合户 | Phase 3, 4 |

---

## 十、补充确认结果（已全部确认）

### S1: 合同模板 ✅
HTML 模板 + Jinja2 渲染。模板已创建：`backend/app/templates/contract.html`，渲染服务：`backend/app/services/contract_template_service.py`。基于 PDF 合同 `docs/王传得--承包合同.pdf` 的结构制作。

### S2: 切割地块的 SHP 上传 ✅
**重要澄清**：上传的 SHP 是**切割线或切割面数据**，用于切割（分割）原有地块，不是上传新地块数据。SHP 几何用于空间分割运算，通过 PostGIS 空间函数（如 `ST_Split`、`ST_Intersection`）执行切割，无需在 `survey_dk_result` 中新增持久化几何列（切割后的结果地块本身就是 `survey_dk_result` 记录）。

### S3: 切割地块的手绘 ✅
可以使用 `ol/interaction/Draw` 模块在前端地图上交互式绘制分割线/面。

### S4: 分户时新户的 base 表 ✅
不需要创建空 base 记录。base 表保留原始数据（调查前快照），分户产生的新户在调查前不存在，因此无对应 base 记录。新户只有 result 记录。

### S5: 数据恢复粒度 ✅
恢复全部关联数据：承包方 + 所有家庭成员 + 所有地块关系。ChangeRecord 的 `before_summary` JSON 字段存储完整快照。
