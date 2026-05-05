# 承包方调查二期预留功能

一期已落地“导入批次 -> 正式业务表 -> 调查批次 -> base/result -> 调查结果编辑”的主链路。

二期需要在当前调查成果体系上继续补充：

1. 分户/合户专项表与交互
   - `survey_household_restructure`
   - `survey_household_restructure_member`
   - 支持源户、目标户、新户、迁移成员、权益处置、合同/权证处理方式。

2. 农户标签结果表与自动规则
   - `survey_household_tag`
   - 支持全家进城落户户、整户消亡户、五保户、无地少地户。
   - 区分自动标记和人工标记，记录规则、原因、政策依据、停用原因。

3. 委托代理调查
   - `survey_authorization`
   - 支持授权委托书在线填写、模板生成、上传、有效期、作废、关联承包方和业务申请。

4. 调查附件
   - `survey_attachment`
   - 支持身份证、户口簿、死亡证明、婚嫁证明、进城落户证明、政策依据、授权委托书等。

5. 字段级差异明细
   - `survey_change_diff`
   - 自动比较 base/result，支持按字段查看变化前、变化后、变化原因。

6. 调查成果转业务申请
   - 从 `survey_change_record` 或 `survey_cbf_result` 生成互换、变更、注销等正式业务申请。
   - 转办后写回 `generated_request_id`，形成调查成果到业务办理的闭环。
