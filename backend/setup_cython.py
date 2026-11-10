"""
Cython compilation script for the backend package.

Compiles all .py files under app/ into platform-native extension modules
(.pyd on Windows, .so on Linux) and outputs them to backend/dist/.
Source .py files under backend/app/ are left intact.

Usage:
    python setup_cython.py build_ext --build-lib dist

Requires:
    pip install cython
    A C compiler (MSVC on Windows, gcc/clang on Linux)
"""

import os
import shutil
import sys
from pathlib import Path

from setuptools import setup
from Cython.Build import cythonize
from Cython.Distutils import build_ext

HERE = Path(__file__).resolve().parent
APP_DIR = HERE / "app"
DIST_DIR = HERE / "dist"

# Files that must remain as .py (entry points loaded via -m or import strings)
# main.py is the FastAPI app entry point (uvicorn app.main:app)
# bootstrap.py is imported by init scripts (python -m app.db.bootstrap --schema)
# land_parcel_repository.py and data_import_service.py are kept editable
KEEP_AS_PY = {
    "app/main.py",
    "app/db/bootstrap.py",
    "app/repositories/land_parcel_repository.py",
    "app/services/data_import_service.py",
}

# Directories whose .py files must all remain uncompiled
# （2026-11-10 起为空：data_import 曾整目录保留 .py，是拆包时继承
#   data_import_service.py「kept editable」的惯性，无技术必要——试编译
#   12/12 通过、无动态加载引用、性能无差。热修需求由整包/增量更新覆盖。）
KEEP_AS_PY_DIRS: list[str] = [
]

# Directories containing non-Python runtime files that must be copied to dist/
# ⛔ app/templates 是打印模板（地籍调查/合同/申请表等，contract_template_*_service
#    按 parent.parent/templates 解析）——漏拷会导致目标机打印/出件全部报模板不存在
#    （2026-10-20 目标机事故）
COPY_DIRS = [
    "app/templates",
    "app/workflows",
    "app/storage",
]

# Non-Python single files that must be copied to dist/ preserving relative path.
# ⛔ app/db/region_seed.json 是区域初始化种子（scripts/fetch_region_seed.py 生成），
#    init_db.py 按 Path(__file__).with_name("region_seed.json") 读取 ——
#    漏拷会导致编译布局下部署后区域只剩江苏省/泗洪县两条。
COPY_FILES = [
    "app/db/region_seed.json",
    # 全国行政区划中心点（fetch_region_centroids.py 生成，~130KB）：
    # 部署初始化时按 REGION_SEED_COUNTIES 计算 system_config.map_center（地图默认中心点）。
    "app/db/region_centroids.json",
    # 全国行政区划数据包（fetch_region_seed.py --full 生成，~12MB）：
    # 目标机 .env 配 REGION_SEED_COUNTIES 后，首次启动自动初始化对应区域树。
    "app/db/region_full.zip",
]


def collect_py_files(root: Path) -> list[str]:
    """Collect all .py files relative to HERE."""
    files = []
    for py_file in root.rglob("*.py"):
        rel = str(py_file.relative_to(HERE)).replace("\\", "/")
        files.append(rel)
    return files


def copy_kept_files(compile_files: list[str], keep_files: list[str]) -> None:
    """Copy kept .py files and non-Python directories into dist/."""
    # Copy kept .py files preserving directory structure
    for py_rel in keep_files:
        src = HERE / py_rel
        dst = DIST_DIR / py_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        print(f"  Kept .py: {py_rel}")

    # Copy non-Python directories
    for dir_rel in COPY_DIRS:
        src_dir = HERE / dir_rel
        if src_dir.is_dir():
            dst_dir = DIST_DIR / dir_rel
            if dst_dir.exists():
                shutil.rmtree(str(dst_dir))
            shutil.copytree(str(src_dir), str(dst_dir))
            print(f"  Copied dir: {dir_rel}")

    # Copy non-Python single files
    for file_rel in COPY_FILES:
        src = HERE / file_rel
        if src.is_file():
            dst = DIST_DIR / file_rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            print(f"  Copied file: {file_rel}")


def main():
    # Clean previous dist
    if DIST_DIR.exists():
        shutil.rmtree(str(DIST_DIR))
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    py_files = collect_py_files(APP_DIR)

    # Separate files to compile vs keep as .py
    def _is_kept(f):
        if f in KEEP_AS_PY:
            return True
        return any(f.startswith(d) for d in KEEP_AS_PY_DIRS)
    compile_files = [f for f in py_files if not _is_kept(f)]
    keep_files = [f for f in py_files if _is_kept(f)]

    if not compile_files:
        print("No .py files to compile.")
        copy_kept_files(compile_files, keep_files)
        return

    print(f"Compiling {len(compile_files)} files with Cython...")
    print(f"Keeping {len(keep_files)} files as .py: {keep_files}")
    print(f"Output directory: {DIST_DIR}")
    print()

    setup(
        name="ruralland_backend_build",
        ext_modules=cythonize(
            compile_files,
            compiler_directives={
                "language_level": "3",
                "binding": True,
                "annotation_typing": False,
            },
            build_dir=str(HERE / "build" / "cython_cache"),
            nthreads=os.cpu_count() or 4,
        ),
        script_args=["build_ext", "--build-lib", str(DIST_DIR)],
        cmdclass={"build_ext": build_ext},
    )

    # Copy kept .py files and non-Python dirs to dist/
    copy_kept_files(compile_files, keep_files)

    # Clean up intermediate .c files generated by Cython
    for py_rel in compile_files:
        c_file = HERE / py_rel.replace(".py", ".c")
        if c_file.exists():
            c_file.unlink()

    print()
    print("Backend compilation complete.")
    print(f"  Compiled: {len(compile_files)} modules → .pyd/.so")
    print(f"  Kept .py: {len(keep_files)} entry modules")
    print(f"  Output:   {DIST_DIR}")
    print()
    print("Source .py files under backend/app/ are preserved.")


if __name__ == "__main__":
    main()
