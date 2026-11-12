"""离线验证村组公示签字表表头版式（不连库：monkeypatch 数据 loader）。

核对三点：
1. Excel 第 2 行 E 列（日期/公示期合并格）水平居中；
2. 第 3/4 行除四至 4 列（27-30）外，其余表头列纵向合并 (2,3)；
3. 四至主表头横跨 27-30、子表头东/南/西/北仍在第 4 行分列。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import xlrd  # noqa: E402
import xlwt  # noqa: E402

from app.services.village_publicity_export_service import (  # noqa: E402
    NCOLS,
    village_publicity_export_service as svc,
)
import app.services.village_publicity_export_service as _mod  # noqa: E402

FAKE_FBF = type("F", (), {"fbfbm": "15052610322700", "fbfmc": "测试村组"})()

svc._load_contractors = lambda db, fbfbm: []
svc._load_members = lambda db, uids: {}
svc._load_parcels = lambda db, fbfbm: {}
_mod._dictionary_maps = lambda db: {}


class FakeDB:
    def get(self, model, code):
        return FAKE_FBF


data, _ = svc.export(FakeDB(), ["15052610322700"])
out = os.path.join(os.path.dirname(__file__), "_village_publicity_check.xls")
with open(out, "wb") as fh:
    fh.write(data)

wb = xlrd.open_workbook(out, formatting_info=True)
sh = wb.sheet_by_index(0)
merges = set(sh.merged_cells)

errors = []

# 1) E2 水平居中
xf = wb.xf_list[sh.cell_xf_index(1, 4)]
if xf.alignment.hor_align != 2:  # 2 = centered
    errors.append(f"E2 水平对齐={xf.alignment.horz_horz}，应为 2(居中)")

# 2) 行 2/3：除 27-30 外每列纵向合并
for c in range(NCOLS):
    merged = (2, 4, c, c + 1) in merges
    if c in (27, 28, 29, 30):
        if merged:
            errors.append(f"四至列 {c} 不应纵向合并 2-3 行")
    elif not merged:
        errors.append(f"列 {c} 未纵向合并 2-3 行")

# 3) 四至主表头横跨 + 子表头
if (2, 3, 27, 31) not in merges:
    errors.append("四至主表头未横跨 27-30")
subs = [sh.cell_value(3, 27 + i) for i in range(4)]
if subs != ["东", "南", "西", "北"]:
    errors.append(f"四至子表头异常: {subs}")

# 表头内容仍在（抽查首尾列）
if sh.cell_value(2, 0) != "承包方编号" or sh.cell_value(2, 45) != "签字人(按印)":
    errors.append("表头文字丢失")

if errors:
    print("FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("PASS: E2 居中；第3/4行除四至(27-30)外全部纵向合并；四至主/子表头正常")
