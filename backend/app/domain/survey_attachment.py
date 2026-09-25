"""调查附件（承包方调查材料）的领域常量。

类别清单复用「附件组管理」页（`request_attachment_templates`）承载，作用域固定为
「业务类型 = 调查附件、流程节点 = 承包方调查录入」。常量放在这里而不是 db / service 层，
是为了让两侧都能引用同一份定义而不互相 import。
"""

SURVEY_ATTACHMENT_REQUEST_TYPE = "调查附件"
SURVEY_ATTACHMENT_STAGE_CODE = "survey_entry"
SURVEY_ATTACHMENT_STAGE_NAME = "承包方调查录入"

#: 读取类别时用的筛选条件：(request_type, stage_code)
SURVEY_ATTACHMENT_TEMPLATE_SCOPE = (
    SURVEY_ATTACHMENT_REQUEST_TYPE,
    SURVEY_ATTACHMENT_STAGE_CODE,
)

#: 首次初始化时灌入的类别名。名称既是页面显示名，也是写入 survey_attachments.category 的值。
DEFAULT_SURVEY_ATTACHMENT_CATEGORY_NAMES = (
    "身份证",
    "户口簿",
    "死亡证明",
    "婚嫁证明",
    "进城落户证明",
    "政策依据",
    "授权委托书",
    "合同扫描件",
)
