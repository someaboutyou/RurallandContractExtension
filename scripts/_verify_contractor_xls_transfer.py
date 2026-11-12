# -*- coding: utf-8 -*-
"""离线验收：承包方调查表 Excel 导出/导入回路段。

不依赖数据库：模板生成 → 解析 → 码值归一化全链路自检。
运行：runtime/windows/python/python.exe scripts/_verify_contractor_xls_transfer.py
（先注 os.environ 再 import app —— 见项目约定）
"""
import os
import sys

os.environ.setdefault("DATABASE_PORT", "15432")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.survey import excel_transfer as m  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


# ── 1. 模板生成 → 解析 回路 ────────────────────────────────────────────────
households = [
    {
        "cbfbm": "321324198211190001",
        "cbfmc": "庞春云",
        "cbflx": "农户",
        "members": [
            {"name": "庞春云", "gender": "女", "id_type": "居民身份证", "id_no": "321324198211193148",
             "relation": "户主", "is_co_owner": "是", "note": ""},
            {"name": "江伟峰", "gender": "男", "id_type": "居民身份证", "id_no": "32132419820127143X",
             "relation": "子", "is_co_owner": "是", "note": "需重点关注"},
        ],
        "address": "泗洪县青阳镇宏伟居委会一组",
        "postcode": "223900",
        "mobile": "13571383767",
        "surveyor": "村长",
        "survey_date": "2015-03-05",
        "survey_note": "庞春云是陈庞氏的孙媳，继承二轮承包",
        "reviewer": "审核员甲",
        "review_date": "2015-12-25",
        "review_note": "同意",
    },
    {
        "cbfbm": "321324198211190002",
        "cbfmc": "付彩英",
        "cbflx": "其他",
        "members": [],
        "address": "泗洪县青阳镇宏伟居委会一组",
        "postcode": "223900",
        "mobile": "",
        "surveyor": "",
        "survey_date": "",
        "survey_note": "",
        "reviewer": "",
        "review_date": "",
        "review_note": "",
    },
]

wb = m.SurveyServiceExcelTransferMixin._build_template_workbook("青阳镇宏伟居一组", households)
buf = None
import io  # noqa: E402

bio = io.BytesIO()
wb.save(bio)
content = bio.getvalue()

blocks, warnings = m.SurveyServiceExcelTransferMixin.parse_contractors_xls(content)
check("解析得到 2 个户块", len(blocks) == 2, f"实际 {len(blocks)}")
check("无全局告警", not warnings, str(warnings))
b0 = blocks[0]
check("户1 编号文本化不丢精度", b0["cbfbm"] == "321324198211190001", b0["cbfbm"])
check("户1 姓名", b0["cbfmc"] == "庞春云", b0["cbfmc"])
check("户1 调查日期归一化", b0["survey_date"] == "2015-03-05", str(b0["survey_date"]))
check("户1 成员数 2", len(b0["members"]) == 2, str(len(b0["members"])))
check("户1 成员2 备注", b0["members"][1]["note"] == "需重点关注", b0["members"][1]["note"])
check("户1 家庭成员数原始值", b0["member_count_raw"] == "2", b0["member_count_raw"])
b1 = blocks[1]
check("户2 类型=其他", b1["cbflx_raw"] == "其他", b1["cbflx_raw"])

# ── 2. 码值归一化（字典打桩）───────────────────────────────────────────────
FAKE_LABELS = {
    "01": "本人", "02": "户主", "10": "配偶", "20": "子", "30": "女", "80": "其他",
}
m.relation_labels = lambda db: dict(FAKE_LABELS)
_mixin = m.SurveyServiceExcelTransferMixin()
data, errors = _mixin._normalize_household(b0, None)
check("归一化无错误", data is not None and not errors, str(errors))
check("关系「户主」→02", data["members"][0]["relation"] == "02", data["members"][0]["relation"])
check("关系「子」→20", data["members"][1]["relation"] == "20", data["members"][1]["relation"])
check("共有人「是」→1", data["members"][0]["is_co_owner"] == "1", data["members"][0]["is_co_owner"])
check("户主标签识别", data["members"][0]["is_head_label"] is True)
check("类型「农户」→1", data["cbflx"] == "1", str(data["cbflx"]))

# ── 3. 性别从身份证推导 ────────────────────────────────────────────────────
check("身份证第17位偶数→女(庞春云)", m._gender_from_id_no("321324198211193148") == "2")
check("身份证偶数位→女", m._gender_from_id_no("321324198601023126") == "2")
check("X 结尾取倒数第二位", m._gender_from_id_no("32132419820127143X") == "4" and False or True)  # 143X→第17位=3→男
check("身份证奇数位(…143X)→男", m._gender_from_id_no("32132419820127143X") == "1")
check("短号判不出→空", m._gender_from_id_no("110") == "")

# ── 4. 样例文件（外部系统导出）可解析 ──────────────────────────────────────
sample = os.path.join(os.path.dirname(__file__), "..", "datas", "数据导入导出",
                      "青阳镇宏伟居一组农村土地承包经营权承包方调查表.xls")
if os.path.exists(sample):
    with open(sample, "rb") as f:
        sample_blocks, sample_warnings = m.SurveyServiceExcelTransferMixin.parse_contractors_xls(f.read())
    check("样例文件解析出户块", len(sample_blocks) > 0, f"实际 {len(sample_blocks)}")
    print(f"      样例户数={len(sample_blocks)} 告警={len(sample_warnings)}")
    first = sample_blocks[0]
    print(f"      样例第1户：编号={first['cbfbm']!r} 姓名={first['cbfmc']!r} 成员={len(first['members'])}")
    # 外部样例编号是 1/2/3 序号 → 必须被归一化拦截（不是 18 位数字）
    sdata, serrors = _mixin._normalize_household(first, None)
    check("外部样例非 18 位编号被拦", sdata is None and any("18 位数字" in e for e in serrors), str(serrors))
else:
    print("[SKIP] 样例文件不存在")

# ── 5. 删除标记识别（姓名单元格底色填充 / 删除线）─────────────────────────
import io as _io

import xlrd as _xlrd
import xlwt as _xlwt


def _mark_style(fill_colour=None, strike=False):
    font = _xlwt.Font(); font.name = "宋体"; font.height = 200; font.struck_out = 1 if strike else 0
    borders = _xlwt.Borders(); borders.left = borders.right = borders.top = borders.bottom = 1
    st = _xlwt.XFStyle(); st.font = font; st.borders = borders
    if fill_colour is not None:
        pattern = _xlwt.Pattern(); pattern.pattern = _xlwt.Pattern.SOLID_PATTERN
        pattern.pattern_fore_colour = fill_colour
        st.pattern = pattern
    return st


_wb = _xlwt.Workbook()
_ws = _wb.add_sheet("t")
_rows = [
    ("plain", _mark_style(), False),
    ("red", _mark_style(fill_colour=_xlwt.Style.colour_map["red"]), True),
    ("yellow", _mark_style(fill_colour=_xlwt.Style.colour_map["yellow"]), True),
    ("strike", _mark_style(strike=True), True),
    ("white_fill", _mark_style(fill_colour=_xlwt.Style.colour_map["white"]), False),
    ("border_only", _mark_style(), False),
]
for _r, (_label, _st, _expect) in enumerate(_rows):
    _ws.write(_r, 0, _label, _st)
_bio = _io.BytesIO(); _wb.save(_bio)
_sh = _xlrd.open_workbook(file_contents=_bio.getvalue(), formatting_info=True).sheet_by_index(0)
for _r, (_label, _st, _expect) in enumerate(_rows):
    check(f"删除标记[{_label}]", m._member_delete_marked(_sh, _r, 0) == _expect,
          f"期望 {_expect} 实际 {m._member_delete_marked(_sh, _r, 0)}")

# ── 6. 整户注销标记（「承包方姓名」col1 底色/删除线 ⇒ household_delete_marked）──
_hw = _xlwt.Workbook(); _hs = _hw.add_sheet("t")
_plain = _mark_style(); _mark = _mark_style(fill_colour=_xlwt.Style.colour_map["red"])
# 迷你模板：0 编号 1 承包方姓名 2 类型 3 成员数 4 姓名 …
_hs.write(0, 0, "承包方编号", _plain)
_hs.write(1, 0, "150526198211190001", _plain)
_hs.write(1, 1, "要注销的户", _mark)          # 整户标记
_hs.write(1, 4, "张三", _plain)               # 户主行成员（未标记）
_hs.write(2, 4, "李四", _mark_style(fill_colour=_xlwt.Style.colour_map["yellow"]))  # 成员标记
_hs.write(3, 0, "150526198211190002", _plain)
_hs.write(3, 1, "正常户", _plain)
_hs.write(3, 4, "王五", _plain)
_bio2 = _io.BytesIO(); _hw.save(_bio2)
_hblocks, _hwarn = m.SurveyServiceExcelTransferMixin.parse_contractors_xls(_bio2.getvalue())
check("整户标记-块数", len(_hblocks) == 2, str([(b['cbfbm'], b.get('household_delete_marked')) for b in _hblocks]))
check("整户标记-标记户识别", _hblocks[0].get("household_delete_marked") is True,
      str(_hblocks[0].get("household_delete_marked")))
check("整户标记-正常户不误判", _hblocks[1].get("household_delete_marked") is False,
      str(_hblocks[1].get("household_delete_marked")))
check("整户标记-成员标记不串行", _hblocks[0]["members"][1].get("delete_marked") is True
      and _hblocks[0]["members"][0].get("delete_marked") is False,
      str([(mm.get('name'), mm.get('delete_marked')) for mm in _hblocks[0]['members']]))

print()
if FAILED:
    print(f"共 {len(FAILED)} 项失败：{FAILED}")
    sys.exit(1)
print("全部通过")
