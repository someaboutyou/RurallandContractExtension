# -*- coding: utf-8 -*-
"""「手机App下载地址」一次性验收（跑完即弃，不入常规用例集）。

覆盖三件事：
1. 种子幂等：app_download 三个键存在且 item_name 为空（未配置态）；
2. 拼接逻辑：临时填入 ip/port/path 调 compose_app_download_url，核对 URL，
   验完把 item_name 还原为空（不留测试脏数据）；
3. 未配置态：compose 返回 None（前端据此隐藏二维码）。

前置：由 bash 链先把 runtime.env 灌进 os.environ（本项目离线脚本铁律：
先注环境再 import app）。
"""

import os
import sys

sys.path.insert(0, r"E:\Work\RurallandContractExtension\backend")

from sqlalchemy import create_engine, text  # noqa: E402

from app.services.dictionary_service import dictionary_service  # noqa: E402

url = (
    f"postgresql+psycopg://{os.environ['DATABASE_USER']}:{os.environ['DATABASE_PASSWORD']}"
    f"@{os.environ['DATABASE_HOST']}:{os.environ['DATABASE_PORT']}/{os.environ['DATABASE_NAME']}"
)
engine = create_engine(url)

failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" | {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def read_parts():
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT item_value, item_name, enabled FROM dictionary_items "
                "WHERE dict_type = 'app_download' ORDER BY sort_order"
            )
        ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


by_key = read_parts()
check("种子：三个键齐全", set(by_key) == {"ip", "port", "path"}, str(sorted(by_key)))
check("种子：item_name 均为空（未配置态）", all(v[0] == "" for v in by_key.values()), str(by_key))

# ── 临时填值，验拼接 ────────────────────────────────────────────
with engine.begin() as conn:
    conn.execute(
        text(
            "UPDATE dictionary_items SET item_name = v.name FROM (VALUES "
            "('ip', '221.226.214.70'), ('port', '8090'), ('path', 'app/rural.apk')"
            ") AS v(key, name) WHERE dict_type = 'app_download' AND item_value = v.key"
        )
    )

from app.db.session import SessionLocal  # noqa: E402

db = SessionLocal()
try:
    composed = dictionary_service.compose_app_download_url(db)
    # path 故意填不带前导斜杠的 'app/rural.apk'，拼接层必须补上 '/'
    check("拼接：http://ip:port/path（path 自动补斜杠）",
          composed == "http://221.226.214.70:8090/app/rural.apk", repr(composed))

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE dictionary_items SET item_name = '' "
                 "WHERE dict_type = 'app_download' AND item_value IN ('port', 'path')")
        )
    composed = dictionary_service.compose_app_download_url(db)
    check("拼接：只配 ip → 默认 80 端口省略、指向根",
          composed == "http://221.226.214.70", repr(composed))

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE dictionary_items SET item_name = '' "
                 "WHERE dict_type = 'app_download' AND item_value = 'ip'")
        )
    composed = dictionary_service.compose_app_download_url(db)
    check("未配置：ip 为空 → url 为 None", composed is None, repr(composed))
finally:
    db.close()

check("还原：item_name 全部回到空（不留脏数据）",
      all(v[0] == "" for v in read_parts().values()), str(read_parts()))

if failures:
    print(f"RESULT: {len(failures)} FAILED")
    sys.exit(1)
print("RESULT: ALL PASS")
