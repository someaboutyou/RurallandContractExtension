# -*- coding: utf-8 -*-
"""打包前剥离 Python 运行时源码：.py → .pyc（sourceless）。

⛔ 只对**打包临时副本**执行（package.ps1 调用，传入 temp 里的 python 根目录），
绝不指向开发机的 runtime\windows\python —— 开发期需要 .py 源码。

原理：CPython 支持 sourceless 导入——与 .py 同目录、同名的 .pyc
（直接放在原 .py 位置，而不是 __pycache__ 里）会被 SourcelessFileLoader
正常加载。CPython 官方 embeddable 发行版（python311.zip 内全是 .pyc）
就是这个机制的官方用法。

做什么：
1. compileall 强制编译 Lib（含 site-packages）；
2. 把 __pycache__/<name>.cpython-3XX.pyc 移回原 .py 位置，删除 .py；
   编译失败（无对应 .pyc）的 .py 保留不动 —— 宁可多带一个源码文件，不破坏导入；
3. 清空残留 __pycache__；
4. 整目录剔除运行时不需要的部分：
   - site-packages 内所有 tests/test 目录（测试套件从不被生产代码导入）；
   - 标准库 idlelib / turtledemo / lib2to3（IDE、演示、2to3 工具，仅构建期用）。

用法：python scripts/strip_python_sources.py <python-root-dir>
"""

from __future__ import annotations

import argparse
import shutil
import sys
import compileall
from pathlib import Path

# 标准库里运行时用不到、可整目录剔除的包
STDLIB_DROP_DIRS = ("idlelib", "turtledemo", "lib2to3")
# site-packages 内的测试目录名
TEST_DIR_NAMES = {"tests", "test"}


def drop_dirs(root: Path, names, *, search_subdirs: bool) -> int:
    """整目录删除，返回删除的目录数。"""
    removed = 0
    candidates = []
    if search_subdirs:
        for name in names:
            candidates.extend(root.rglob(name))
    else:
        candidates.extend(root / name for name in names)
    for path in candidates:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


def strip_sources(lib_dir: Path, tag: str) -> tuple[int, int]:
    """compileall + .py 换 .pyc，返回 (删除的 .py 数, 保留未编译的 .py 数)。"""
    print("[1/3] compileall（force，忽略个别编译失败文件）...")
    compileall.compile_dir(str(lib_dir), quiet=2, force=True, workers=4)

    print("[2/3] .py -> .pyc（移出 __pycache__ 到原位置）...")
    removed = kept = 0
    for py in list(lib_dir.rglob("*.py")):
        pyc = py.parent / "__pycache__" / f"{py.stem}.{tag}.pyc"
        if pyc.is_file():
            shutil.move(str(pyc), str(py.with_suffix(".pyc")))
            py.unlink()
            removed += 1
        else:
            kept += 1
    if kept:
        # 编译失败的 .py 保留：宁可留源码也不能破坏导入
        print(f"      {kept} 个 .py 无对应 .pyc，保留（多为跨版本语法/数据文件）")

    print("[3/3] 清理 __pycache__ ...")
    for cache in list(lib_dir.rglob("__pycache__")):
        shutil.rmtree(cache, ignore_errors=True)
    return removed, kept


def main() -> None:
    parser = argparse.ArgumentParser(description="剥离 Python 运行时 .py 源码（打包副本专用）")
    parser.add_argument("python_root", help="打包副本里的 python 根目录（含 Lib）")
    args = parser.parse_args()

    root = Path(args.python_root).resolve()
    lib_dir = root / "Lib"
    if not lib_dir.is_dir():
        sys.exit(f"Lib not found under {root} —— 传的应是 python 根目录")
    tag = f"cpython-{sys.version_info.major}{sys.version_info.minor}"

    tests_removed = drop_dirs(lib_dir / "site-packages", TEST_DIR_NAMES, search_subdirs=True)
    stdlib_removed = drop_dirs(lib_dir, STDLIB_DROP_DIRS, search_subdirs=False)
    print(f"已剔除目录：site-packages tests/test {tests_removed} 个，stdlib {stdlib_removed} 个")

    removed, kept = strip_sources(lib_dir, tag)
    print(f"完成：删除 .py {removed} 个，保留 {kept} 个（无 .pyc 可换）")


if __name__ == "__main__":
    main()
