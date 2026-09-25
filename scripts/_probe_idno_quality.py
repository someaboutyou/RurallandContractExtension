# -*- coding: utf-8 -*-
"""只读探测：库内身份证号（cbfzjhm / cyzjhm）的合规分布，用于评估前端加严校验的影响面。

不变更任何数据。用法：
    runtime/windows/python/python.exe scripts/_probe_idno_quality.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for line in open(os.path.join(ROOT, "runtime", ".state", "runtime.env"), encoding="utf-8-sig"):
    line = line.strip()
    if not line or "=" not in line:
        continue
    key, value = line.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())

import psycopg

WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
CHECK = "10X98765432"
PROVINCES = {
    "11", "12", "13", "14", "15", "21", "22", "23", "31", "32", "33", "34", "35", "36", "37",
    "41", "42", "43", "44", "45", "46", "50", "51", "52", "53", "54", "61", "62", "63", "64",
    "65", "71", "81", "82",
}


def check_18(value: str) -> str:
    if not re.fullmatch(r"\d{17}[\dXx]", value):
        return "格式"
    if value[:2] not in PROVINCES:
        return "地区码"
    y, m, d = int(value[6:10]), int(value[10:12]), int(value[12:14])
    if not (1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31):
        return "生日"
    total = sum(int(value[i]) * WEIGHTS[i] for i in range(17))
    if CHECK[total % 11].upper() != value[17].upper():
        return "校验位"
    return ""


def classify(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "空"
    if re.fullmatch(r"\d{15}", value):
        return "15位"
    return check_18(value) or "18位OK"


conn = psycopg.connect(
    host=os.environ["DATABASE_HOST"], port=os.environ["DATABASE_PORT"],
    dbname=os.environ["DATABASE_NAME"], user=os.environ["DATABASE_USER"],
    password=os.environ["DATABASE_PASSWORD"],
)
with conn.cursor() as cur:
    for table, column, label in (
        ("survey_cbf_result", "cbfzjhm", "承包方成果证件号"),
        ("survey_cbf_jtcy_result", "cyzjhm", "家庭成员成果证件号"),
        ("survey_cbf_base", "cbfzjhm", "承包方基础证件号"),
        ("survey_cbf_jtcy_base", "cyzjhm", "家庭成员基础证件号"),
    ):
        try:
            cur.execute(f"SELECT {column} FROM {table}")
        except Exception as exc:
            print(f"[skip] {table}.{column}: {exc}")
            conn.rollback()
            continue
        rows = [r[0] for r in cur.fetchall()]
        buckets = {}
        for item in rows:
            key = classify(item)
            buckets[key] = buckets.get(key, 0) + 1
        print(f"\n== {label}  {table}.{column}  共 {len(rows)} 行 ==")
        for key, count in sorted(buckets.items(), key=lambda kv: -kv[1]):
            print(f"   {key:<8} {count}")
        bad = [item for item in rows if classify(item) in ("格式", "地区码", "生日", "校验位")]
        for item in bad[:15]:
            print(f"   ! {classify(item)}  {item}")
conn.close()
