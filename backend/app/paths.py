# -*- coding: utf-8 -*-
"""统一路径解析：源码布局与 Cython 编译布局双兼容。

⛔ 背景（2026-10-20 目标机事故）：源码布局下模块位于 backend/app/...，
编译布局下位于 backend/dist/app/...，两者相对 `__file__` 的层级差一级。
各处写死的 `Path(__file__).resolve().parents[N]` 在编译产物里全部少算一级：
`backend/storage` 被解析成 `backend/dist/storage`，用户按文档把 license.dat
放进 backend/storage 后端却报"授权文件不存在"。

统一口径（全项目存储/运行时路径一律从本模块取，禁止再写裸 parents[N]）：
- BACKEND_DIR   backend/（两种布局下都正确）
- PROJECT_ROOT  项目根（backend/ 的上一级）
- STORAGE_DIR   backend/storage（license.dat、导出、附件等）
- RUNTIME_DIR   <项目根>/runtime（日志、临时数据等）
"""

from pathlib import Path

# app/ 的上一级：源码布局 = backend/，编译布局 = backend/dist/
_APP_PARENT = Path(__file__).resolve().parents[1]

if _APP_PARENT.name.lower() == "dist":
    BACKEND_DIR = _APP_PARENT.parent
else:
    BACKEND_DIR = _APP_PARENT

PROJECT_ROOT = BACKEND_DIR.parent
STORAGE_DIR = BACKEND_DIR / "storage"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
