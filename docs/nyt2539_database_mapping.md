# NY/T 2539-2016 与系统数据库结构对照

- 来源文档：`docs/NYT2539-2016农村土地承包经营权确权登记数据库规范.docx`
- 目的：说明规范中的权属数据表在当前系统数据库中的落点，便于后续开发、导入、查询和扩展。
- 约定：规范字段代码在系统表中通常使用小写列名；调查类数据采用 `*_base` 保存原始/基准快照，`*_result` 保存调查成果。

## 1. 总体表对照

| 规范表 | 规范含义 | 系统表 | 状态 | 说明 |
|---|---|---|---|---|
| B.1 `CBDKXX` | 承包地块信息 | `survey_cbdkxx_base`, `survey_cbdkxx_result` | 已落库（调查基表/成果表） | 按批次保留原始快照和调查成果，字段基本按规范代码小写存储，并增加批次、来源追踪、成果状态等业务字段。 |
| B.2 `FBF` | 发包方 | `fbf`, `survey_fbf_base`, `survey_fbf_result`, `issuers` | 已落库（历史表 + 调查表 + 主数据视图） | fbf 保留规范字段；survey_fbf_* 用于调查批次；issuers 是系统业务侧发包方管理表，字段语义映射但命名更业务化。 |
| B.3 `CBF` | 承包方 | `survey_cbf_base`, `survey_cbf_result` | 已落库（调查基表/成果表） | 旧 cbf 表会迁移到 survey_cbf_* 后删除；当前以调查批次模型承载承包方。 |
| B.4 `CBF_JTCY` | 承包方家庭成员 | `survey_cbf_jtcy_base`, `survey_cbf_jtcy_result` | 已落库（调查基表/成果表） | 成果表扩展了成员状态、政策依据、权益处置等业务字段。 |
| B.5 `CBHT` | 承包合同 | `cbht` | 已落库（规范表） | 字段按规范代码小写保存，并增加租户和区域字段。 |
| B.6 `LZHT` | 流转合同 | 未建表 | 未单独建表 | 当前未发现流转合同专表；如需管理流转合同，可按 B.6 新增。 |
| B.7 `QSLYZLFJ` | 权属来源资料附件 | `survey_attachments`, `request_case_attachments` | 部分承载 | 系统用通用附件表承载调查/流程附件，未按 QSLYZLFJ 字段一比一建表。 |
| B.8 `CBJYQZDJB` | 承包经营权证登记簿 | `request_cases` | 流程侧部分承载 | 登记簿未单独建表；证书登记业务目前主要进入流程申请和档案。 |
| B.9 `CBJYQZ` | 承包经营权证 | `request_cases` | 流程侧部分承载 | 权证发放信息未单独建表。 |
| B.10 `CBJYQZ_QZBF` | 权证补发 | `request_cases` | 流程侧部分承载 | 补发作为业务类型/流程处理，未按规范表单独持久化全部字段。 |
| B.11 `CBJYQZ_QZHF` | 权证换发 | `request_cases` | 流程侧部分承载 | 换发作为业务类型/流程处理，未按规范表单独持久化全部字段。 |
| B.12 `CBJYQZ_QZZX` | 权证注销 | `request_cases` | 流程侧部分承载 | 注销作为业务类型/流程处理，未按规范表单独持久化全部字段。 |

## 2. 当前数据库表分层

| 类别 | 系统表 | 用途 |
|---|---|---|
| 系统管理 | `tenants` | 租户/县域数据隔离 |
| 系统管理 | `regions` | 行政区划与区域树 |
| 系统管理 | `users` | 用户账号 |
| 系统管理 | `roles` | 角色 |
| 系统管理 | `permissions` | 权限点 |
| 系统管理 | `user_region_permissions` | 用户可操作区域 |
| 系统管理 | `dictionary_items` | 系统字典项 |
| 业务支撑 | `map_layers` | 地图图层配置 |
| 导入追踪 | `data_import_batches` | 数据导入批次 |
| 导入追踪 | `data_import_files` | 导入文件 |
| 导入追踪 | `data_import_rows` | 导入行明细 |
| 权属/调查数据 | `survey_batches` | 承包方/地块调查批次 |
| 权属/调查数据 | `survey_contractor_tasks` | 调查任务 |
| 权属/调查数据 | `survey_change_records` | 调查变更记录 |
| 权属/调查数据 | `survey_change_diffs` | 字段级变更差异 |
| 流程业务 | `request_cases` | 业务申请/流程实例 |
| 流程业务 | `request_case_participants` | 流程办理记录 |
| 流程业务 | `request_case_attachments` | 流程附件 |
| 流程业务 | `request_attachment_templates` | 流程附件目录模板 |
| 流程业务 | `request_workflow_mappings` | 业务类型到流程定义映射 |
| 业务支撑 | `workflow_definition_versions` | 流程定义版本 |

## 3. 字段级对照

### B.1 `CBDKXX` 承包地块信息

- 系统落点：`survey_cbdkxx_base`, `survey_cbdkxx_result`
- 字段覆盖：12/12 个规范字段可按同名小写列直接对应。
- 说明：按批次保留原始快照和调查成果，字段基本按规范代码小写存储，并增加批次、来源追踪、成果状态等业务字段。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 地块代码 | `DKBM` | Char 19 | 非空 / M | `survey_cbdkxx_base.dkbm`, `survey_cbdkxx_result.dkbm` |
| 发包方代码a | `FBFBM` | Char 14 | 非空 / M | `survey_cbdkxx_base.fbfbm`, `survey_cbdkxx_result.fbfbm` |
| 承包方代码a | `CBFBM` | Char 18 | 非空 / M | `survey_cbdkxx_base.cbfbm`, `survey_cbdkxx_result.cbfbm` |
| 承包经营权取得方式 | `CBJYQQDFS` | Char 3 | 见表C.10 / M | `survey_cbdkxx_base.cbjyqqdfs`, `survey_cbdkxx_result.cbjyqqdfs` |
| 合同面积b | `HTMJ` | Float 15 2 | 非空 / M | `survey_cbdkxx_base.htmj`, `survey_cbdkxx_result.htmj` |
| 承包合同代码a | `CBHTBM` | Char 18 | 非空 / M | `survey_cbdkxx_base.cbhtbm`, `survey_cbdkxx_result.cbhtbm` |
| 流转合同代码c | `LZHTBM` | Char 20 | 非空 / O | `survey_cbdkxx_base.lzhtbm`, `survey_cbdkxx_result.lzhtbm` |
| 承包经营权证（登记薄）代码a | `CBJYQZBM` | Char 19 | 非空 / M | `survey_cbdkxx_base.cbjyqzbm`, `survey_cbdkxx_result.cbjyqzbm` |
| 原合同面积 | `YHTMJ` | Float 15 2 | >0 | `survey_cbdkxx_base.yhtmj`, `survey_cbdkxx_result.yhtmj` |
| 确权（合同）面积（亩） | `HTMJM` | Float 15 2 | >0 / O | `survey_cbdkxx_base.htmjm`, `survey_cbdkxx_result.htmjm` |
| 原合同面积（亩） | `YHTMJM` | Float 15 2 | >0 | `survey_cbdkxx_base.yhtmjm`, `survey_cbdkxx_result.yhtmjm` |
| 是否确权确股 | `SFQQQG` | Char 1 | O | `survey_cbdkxx_base.sfqqqg`, `survey_cbdkxx_result.sfqqqg` |

### B.2 `FBF` 发包方

- 系统落点：`fbf`, `survey_fbf_base`, `survey_fbf_result`, `issuers`
- 字段覆盖：11/11 个规范字段可按同名小写列直接对应。
- 说明：fbf 保留规范字段；survey_fbf_* 用于调查批次；issuers 是系统业务侧发包方管理表，字段语义映射但命名更业务化。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 发包方代码 | `FBFBM` | Char 14 | 非空 / M | `fbf.fbfbm`, `survey_fbf_base.fbfbm`, `survey_fbf_result.fbfbm` |
| 发包方名称 | `FBFMC` | Char 50 | 非空 / M | `fbf.fbfmc`, `survey_fbf_base.fbfmc`, `survey_fbf_result.fbfmc` |
| 发包方负责人姓名 | `FBFFZRXM` | Char 50 | 非空 / M | `fbf.fbffzrxm`, `survey_fbf_base.fbffzrxm`, `survey_fbf_result.fbffzrxm` |
| 负责人证件类型 | `FZRZJLX` | Char 1 | 见表C.15 / M | `fbf.fzrzjlx`, `survey_fbf_base.fzrzjlx`, `survey_fbf_result.fzrzjlx` |
| 负责人证件号码 | `FZRZJHM` | Char 30 | 非空 / M | `fbf.fzrzjhm`, `survey_fbf_base.fzrzjhm`, `survey_fbf_result.fzrzjhm` |
| 联系电话 | `LXDH` | Char 15 | 非空 / O | `fbf.lxdh`, `survey_fbf_base.lxdh`, `survey_fbf_result.lxdh` |
| 发包方地址 | `FBFDZ` | Char 100 | 非空 / M | `fbf.fbfdz`, `survey_fbf_base.fbfdz`, `survey_fbf_result.fbfdz` |
| 邮政代码 | `YZBM` | Char 6 | 非空 / M | `fbf.yzbm`, `survey_fbf_base.yzbm`, `survey_fbf_result.yzbm` |
| 发包方调查员 | `FBFDCY` | Char 254 | 非空 / M | `fbf.fbfdcy`, `survey_fbf_base.fbfdcy`, `survey_fbf_result.fbfdcy` |
| 发包方调查日期 | `FBFDCRQ` | Date 8 | YYYYMMDD / M | `fbf.fbfdcrq`, `survey_fbf_base.fbfdcrq`, `survey_fbf_result.fbfdcrq` |
| 发包方调查记事 | `FBFDCJS` | Char 254 | 非空 / C | `fbf.fbfdcjs`, `survey_fbf_base.fbfdcjs`, `survey_fbf_result.fbfdcjs` |

### B.3 `CBF` 承包方

- 系统落点：`survey_cbf_base`, `survey_cbf_result`
- 字段覆盖：16/16 个规范字段可按同名小写列直接对应。
- 说明：旧 cbf 表会迁移到 survey_cbf_* 后删除；当前以调查批次模型承载承包方。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包方代码 | `CBFBM` | Char 18 | 非空 / M | `survey_cbf_base.cbfbm`, `survey_cbf_result.cbfbm` |
| 承包方类型 | `CBFLX` | Char 1 | 见表C.16 / M | `survey_cbf_base.cbflx`, `survey_cbf_result.cbflx` |
| 承包方(代表)名称a | `CBFMC` | Char 50 | 非空 / M | `survey_cbf_base.cbfmc`, `survey_cbf_result.cbfmc` |
| 承包方(代表)证件类型a | `CBFZJLX` | Char 1 | 见表C.15 / M | `survey_cbf_base.cbfzjlx`, `survey_cbf_result.cbfzjlx` |
| 承包方(代表)证件号码a | `CBFZJHM` | Char 20 | 非空 / M | `survey_cbf_base.cbfzjhm`, `survey_cbf_result.cbfzjhm` |
| 承包方地址a | `CBFDZ` | Char 100 | 非空 / M | `survey_cbf_base.cbfdz`, `survey_cbf_result.cbfdz` |
| 邮政代码a | `YZBM` | Char 6 | 非空 / M | `survey_cbf_base.yzbm`, `survey_cbf_result.yzbm` |
| 联系电话a | `LXDH` | Char 20 | 非空 / O | `survey_cbf_base.lxdh`, `survey_cbf_result.lxdh` |
| 承包方成员数量b | `CBFCYSL` | Int 2 | ＞0 / M | `survey_cbf_base.cbfcysl`, `survey_cbf_result.cbfcysl` |
| 承包方调查日期 | `CBFDCRQ` | Date 8 | YYYYMMDD / M | `survey_cbf_base.cbfdcrq`, `survey_cbf_result.cbfdcrq` |
| 承包方调查员 | `CBFDCY` | Char 50 | 非空 / M | `survey_cbf_base.cbfdcy`, `survey_cbf_result.cbfdcy` |
| 承包方调查记事 | `CBFDCJS` | Char 254 | 非空 / C/有调查记事？ | `survey_cbf_base.cbfdcjs`, `survey_cbf_result.cbfdcjs` |
| 公示记事c | `GSJS` | Char 254 | 非空 / C/有公示记事？ | `survey_cbf_base.gsjs`, `survey_cbf_result.gsjs` |
| 公示记事人c | `GSJSR` | Char 50 | 非空 / M | `survey_cbf_base.gsjsr`, `survey_cbf_result.gsjsr` |
| 公示审核日期c | `GSSHRQ` | Date 8 | YYYYMMDD / M | `survey_cbf_base.gsshrq`, `survey_cbf_result.gsshrq` |
| 公示审核人c | `GSSHR` | Char 50 | 非空 / M | `survey_cbf_base.gsshr`, `survey_cbf_result.gsshr` |

### B.4 `CBF_JTCY` 承包方家庭成员

- 系统落点：`survey_cbf_jtcy_base`, `survey_cbf_jtcy_result`
- 字段覆盖：9/9 个规范字段可按同名小写列直接对应。
- 说明：成果表扩展了成员状态、政策依据、权益处置等业务字段。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包方代码 | `CBFBM` | Char 18 | 非空 / M | `survey_cbf_jtcy_base.cbfbm`, `survey_cbf_jtcy_result.cbfbm` |
| 成员姓名 | `CYXM` | Char 50 | 非空 / M | `survey_cbf_jtcy_base.cyxm`, `survey_cbf_jtcy_result.cyxm` |
| 成员性别 | `CYXB` | Char 1 | 见表C.17 / M | `survey_cbf_jtcy_base.cyxb`, `survey_cbf_jtcy_result.cyxb` |
| 成员证件类型 | `CYZJLX` | Char 1 | 见表C.15 / M | `survey_cbf_jtcy_base.cyzjlx`, `survey_cbf_jtcy_result.cyzjlx` |
| 成员证件号码 | `CYZJHM` | Char 20 | 非空 / M | `survey_cbf_jtcy_base.cyzjhm`, `survey_cbf_jtcy_result.cyzjhm` |
| 与户主关系 | `YHZGX` | Char 2 | 非空a / M | `survey_cbf_jtcy_base.yhzgx`, `survey_cbf_jtcy_result.yhzgx` |
| 成员备注 | `CYBZ` | Char 1 | 见表C.18 / O | `survey_cbf_jtcy_base.cybz`, `survey_cbf_jtcy_result.cybz` |
| 是否共有人b | `SFGYR` | Char 1 | 见表C.19 / O | `survey_cbf_jtcy_base.sfgyr`, `survey_cbf_jtcy_result.sfgyr` |
| 成员备注说明 | `CYBZSM` | Char 254 | 非空 / O | `survey_cbf_jtcy_base.cybzsm`, `survey_cbf_jtcy_result.cybzsm` |

### B.5 `CBHT` 承包合同

- 系统落点：`cbht`
- 字段覆盖：13/13 个规范字段可按同名小写列直接对应。
- 说明：字段按规范代码小写保存，并增加租户和区域字段。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包合同代码 | `CBHTBM` | Char 19 | 非空 / M | `cbht.cbhtbm` |
| 原承包合同代码 | `YCBHTBM` | Char 19 | 非空 / C/有原始承包合同？ | `cbht.ycbhtbm` |
| 发包方代码 | `FBFBM` | Char 14 | 非空 / M | `cbht.fbfbm` |
| 承包方代码 | `CBFBM` | Char 18 | 非空 / M | `cbht.cbfbm` |
| 承包方式 | `CBFS` | Char 3 | 见表C.10 / M | `cbht.cbfs` |
| 承包期限起 | `CBQXQ` | Date 8 | YYYYMMDD / M | `cbht.cbqxq` |
| 承包期限止 | `CBQXZ` | Date 8 | YYYYMMDD / M | `cbht.cbqxz` |
| 承包合同总面积 | `HTZMJ` | Float 15 2 | ＞0 / M | `cbht.htzmj` |
| 承包地块总数 | `CBDKZS` | Int 3 | ＞0 / M | `cbht.cbdkzs` |
| 签订时间 | `QDSJ` | Date 8 | YYYYMMDD / M | `cbht.qdsj` |
| 确权（合同）总面积（亩） | `HTZMJM` | Float 15 2 | ＞0 / O | `cbht.htzmjm` |
| 原合同总面积 | `YHTZMJ` | Float 15 2 | ＞0 / 约束条件C/有原承包合同？ | `cbht.yhtzmj` |
| 原合同总面积（亩） | `YHTZMJM` | Float 15 2 | ＞0 / 约束条件C/有原承包合同？ | `cbht.yhtzmjm` |

### B.6 `LZHT` 流转合同

- 系统落点：未单独建表
- 字段覆盖：0/15 个规范字段可按同名小写列直接对应。
- 说明：当前未发现流转合同专表；如需管理流转合同，可按 B.6 新增。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包合同代码a | `YCBHTBM` | Char 19 | 非空 / M | 未发现同名列 |
| 流转合同代码 | `LZHTBM` | Char 18 | 非空 / M | 未发现同名列 |
| 承包方代码 | `CFBBM` | Char 18 | 非空 / M | 未发现同名列 |
| 受让方代码b | `SRFBM` | Char 18 | 非空 / M | 未发现同名列 |
| 流转方式 | `LZFS` | Char 3 | 见表C.10 / M | 未发现同名列 |
| 流转期限 | `LZQX` | Char 10 | 非空 / M | 未发现同名列 |
| 流转期限开始日期 | `LZQXKSRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 流转期限结束日期 | `LZQXJSRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 流转面积 | `LZMJ` | Float 15 2 | ＞0 / M | 未发现同名列 |
| 流转地块数 | `LZDKS` | Int 2 | ＞0 / M | 未发现同名列 |
| 流转前土地用途 | `LZQTDYT` | Char 1 | 见表C.9 / O | 未发现同名列 |
| 流转后土地用途 | `LZHTDYT` | Char 1 | 见表C.9 / O | 未发现同名列 |
| 流转费用说明c | `LZJGSM` | Char 100 | 非空 / M | 未发现同名列 |
| 合同签订日期 | `HTQDRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 流转面积（亩） | `LZMJM` | Float 15 2 | >0 / O | 未发现同名列 |

### B.7 `QSLYZLFJ` 权属来源资料附件

- 系统落点：`survey_attachments`, `request_case_attachments`
- 字段覆盖：0/5 个规范字段可按同名小写列直接对应。
- 说明：系统用通用附件表承载调查/流程附件，未按 QSLYZLFJ 字段一比一建表。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包经营权证(登记簿)代码 | `CBJYQZBM` | Char 19 | 非空 / M | 未发现同名列 |
| 资料附件编号 | `ZLFJBH` | Char 20 | 非空 / M | 未发现同名列 |
| 资料附件名称 | `ZLFJMC` | Char 100 | 非空 / M | 未发现同名列 |
| 资料附件日期 | `ZLFJRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 附件a | `FJ` | Varbin | 非空 / M | 未发现同名列 |

### B.8 `CBJYQZDJB` 承包经营权证登记簿

- 系统落点：`request_cases`
- 字段覆盖：0/13 个规范字段可按同名小写列直接对应。
- 说明：登记簿未单独建表；证书登记业务目前主要进入流程申请和档案。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包经营权证(登记簿)代码 | `CBJYQZBM` | Char 19 | 非空 / M | 未发现同名列 |
| 发包方代码 | `FBFBM` | Char 14 | 非空 / M | 未发现同名列 |
| 承包方代码 | `CBFBM` | Char 18 | 非空 / M | 未发现同名列 |
| 承包方式 | `CBFS` | Char 3 | 见表C.10 / M | 未发现同名列 |
| 承包期限 | `CBQX` | Char 30 | 非空 / M | 未发现同名列 |
| 承包期限起 | `CBQXQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 承包期限止a | `CBQXZ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 地块示意图b | `DKSYT` | Varbin 254 | 非空 / M | 未发现同名列 |
| 承包经营权证流水号 | `CBJYQZLSH` | Char 50 | 非空 / M | 未发现同名列 |
| 登记簿附记 | `DJBFJ` | Char 50 | 非空 / O | 未发现同名列 |
| 原承包经营权证编号 | `YCBJYQZLSH` | Char 50 | 非空 / O | 未发现同名列 |
| 登簿人 | `DBR` | Char 50 | 非空 / M | 未发现同名列 |
| 登记时间 | `DJSJ` | DATE 8 | 非空 / M | 未发现同名列 |

### B.9 `CBJYQZ` 承包经营权证

- 系统落点：`request_cases`
- 字段覆盖：0/8 个规范字段可按同名小写列直接对应。
- 说明：权证发放信息未单独建表。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包经营权证(登记簿)代码 | `CBJYQZBM` | Char 19 | 非空 / M | 未发现同名列 |
| 发证机关 | `FZJG` | Char 50 | 非空 / M | 未发现同名列 |
| 发证日期 | `FZRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 权证是否领取 | `QZSFLY` | Char 1 | 见表C.19 / M | 未发现同名列 |
| 权证领取日期 | `QZLQRQ` | Date 8 | YYYYMMDD / C | 未发现同名列 |
| 权证领取人姓名 | `QZLQRXM` | Char 50 | 非空 / C | 未发现同名列 |
| 权证领取人证件类型 | `QZLQRZJLX` | Char 1 | 见表C.15 / C | 未发现同名列 |
| 权证领取人证件号码 | `QZLQRZJHM` | Char 20 | 非空 / C | 未发现同名列 |

### B.10 `CBJYQZ_QZBF` 权证补发

- 系统落点：`request_cases`
- 字段覆盖：0/7 个规范字段可按同名小写列直接对应。
- 说明：补发作为业务类型/流程处理，未按规范表单独持久化全部字段。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包经营权证(登记簿)代码 | `CBJYQZBM` | Char 19 | 非空 / M | 未发现同名列 |
| 权证补发原因 | `QZBFYY` | Char 200 | 非空 / M | 未发现同名列 |
| 补发日期 | `BFRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 权证补发领取日期 | `QZBFLQRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 权证补发领取人姓名 | `QZBFLQRXM` | Char 50 | 非空 / M | 未发现同名列 |
| 权证补发领取人证件类型 | `BFLQRZJLX` | Char 1 | 见表C.15 / M | 未发现同名列 |
| 权证补发领取人证件号码 | `BFLQRZJHM` | Char 20 | 非空 / M | 未发现同名列 |

### B.11 `CBJYQZ_QZHF` 权证换发

- 系统落点：`request_cases`
- 字段覆盖：0/7 个规范字段可按同名小写列直接对应。
- 说明：换发作为业务类型/流程处理，未按规范表单独持久化全部字段。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包经营权证(登记簿)代码 | `CBJYQZBM` | Char 19 | 非空 / M | 未发现同名列 |
| 权证换发原因 | `QZHFYY` | Char 200 | 非空 / M | 未发现同名列 |
| 换发日期 | `HFRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 权证换发领取日期 | `QZHFLQRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |
| 权证换发领取人姓名 | `QZHFLQRXM` | Char 50 | 非空 / M | 未发现同名列 |
| 权证换发领取人证件类型 | `HFLQRZJLX` | Char 1 | 见表C.15 / M | 未发现同名列 |
| 权证换发领取人证件号码 | `HFLQRZJHM` | Char 20 | 非空 / M | 未发现同名列 |

### B.12 `CBJYQZ_QZZX` 权证注销

- 系统落点：`request_cases`
- 字段覆盖：0/3 个规范字段可按同名小写列直接对应。
- 说明：注销作为业务类型/流程处理，未按规范表单独持久化全部字段。

| 规范字段 | 代码 | 类型 | 值域/约束 | 系统列落点 |
|---|---|---|---|---|
| 承包经营权证(登记簿)代码 | `CBJYQZBM` | Char 19 | 非空 / M | 未发现同名列 |
| 注销原因 | `ZXYY` | Char 200 | 非空 / M | 未发现同名列 |
| 注销日期 | `ZXRQ` | Date 8 | YYYYMMDD / M | 未发现同名列 |

## 4. NY/T 2539 附录 C 字典落库

附录 C 已整理为 `dictionary_items` 的初始化数据，字典类型采用 `nyt2539_cXX_...` 命名。业务页面可通过 `/api/v1/dictionaries/options/{dictType}` 读取，并由前端 `useDictionary` 自动缓存。

| 附录表 | dict_type | 条目数 | 示例 |
|---|---|---:|---|
| C.1 控制点类型及等级代码表 | `nyt2539_c01_control_point_type_grade` | 10 | 110100=平面控制点, 110101=大地原点 / 大地原点, 110102=三角点 / 一等，二等，三等，四等，5秒，10秒 |
| C.2 标石类型代码表 | `nyt2539_c02_marker_stone_type` | 4 | 1=基岩标石, 2=混凝土标石, 3=普通标石 |
| C.3 标志类型代码表 | `nyt2539_c03_marker_type` | 4 | 1=铜标志, 2=钢标志, 3=刻十字标志 |
| C.4 界线类型代码表 | `nyt2539_c04_boundary_type` | 12 | 250200=海岸线, 250201=大潮平均高潮线, 250202=零米等深线 |
| C.5 界线性质代码表 | `nyt2539_c05_boundary_property` | 5 | 600001=已定界, 600002=未定界, 600003=争议界 |
| C.6 所有权性质代码表 | `nyt2539_c06_ownership_property` | 6 | 10=国有土地所有权, 30=集体土地所有权, 31=村民小组 |
| C.7 地块类别代码表 | `nyt2539_c07_parcel_category` | 5 | 10=承包地块, 21=自留地, 22=机动地 |
| C.8 地力等级代码表 | `nyt2539_c08_land_grade` | 10 | 01=一等地, 02=二等地, 03=三等地 |
| C.9 土地用途代码表 | `nyt2539_c09_land_use` | 5 | 1=种植业, 2=林业, 3=畜牧业 |
| C.10 承包经营权取得方式代码表 | `nyt2539_c10_right_acquire_method` | 10 | 100=承包, 110=家庭承包, 120=其他方式承包 |
| C.11 界址点类型代码表 | `nyt2539_c11_boundary_point_type` | 3 | 1=实测法界址点, 2=航测法界址点, 3=图解法界址点 |
| C.12 界标类型 | `nyt2539_c12_boundary_marker_type` | 9 | 1=钢钉, 2=水泥桩, 3=石灰桩 |
| C.13 界址线类别代码表 | `nyt2539_c13_boundary_line_category` | 9 | 01=田垄（埂）, 02=沟渠, 03=道路 |
| C.14 界址线位置 | `nyt2539_c14_boundary_line_position` | 3 | 01=内, 02=中, 03=外 |
| C.15 证件类型代码表 | `nyt2539_c15_id_document_type` | 6 | 1=居民身份证, 2=军官证, 3=行政、企事业单位机构代码证或法人代码证 |
| C.16 承包方类型代码表 | `nyt2539_c16_contractor_type` | 3 | 1=农户, 2=个人, 3=单位 |
| C.17 性别代码表 | `nyt2539_c17_gender` | 2 | 1=男, 2=女 |
| C.18 成员备注代码表 | `nyt2539_c18_member_remark` | 8 | 1=外嫁女, 2=入赘男, 3=在校大学生 |
| C.19 是否代码表 | `nyt2539_c19_yes_no` | 2 | 1=是, 2=否 |

## 5. 后续扩展建议

- 若需要完整承载流转合同、权证登记簿、权证补换发/注销，应按 B.6-B.12 增建专表或在流程归档时固化结构化字段。
- 对已落库的规范字段，导入程序应优先使用规范代码小写列，避免再新增中文或业务别名列。
- 系统扩展字段应保留在规范字段之后，并在本对照文档中记录来源和用途。
