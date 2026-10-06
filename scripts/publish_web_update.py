# -*- coding: utf-8 -*-
"""
发布移动端 Web 热更包。

用法（在仓库根目录）：
    python scripts/publish_web_update.py --notes "修复xxx"
    python scripts/publish_web_update.py --no-build          # dist 已是最新，直接打包
    python scripts/publish_web_update.py --min-native 2      # 此包要求原生壳 versionCode >= 2

做什么：
1. 生成版本号 yyyyMMddHHmm（作为 VITE_BUNDLE_VERSION 注入构建，保证 dist 内置版本
   与清单一致 —— 这是客户端判断「我是什么版本」的唯一依据）；
2. `npm run build` 构建 frontend/dist（--no-build 跳过）；
3. 打包 dist → `backend/storage/app-updates/bundle-<版本>.zip`；
4. 计算 sha256 / size，写 `latest.json` 清单（原子写：临时文件 + replace）；
5. `npx cap sync` 把最新 bundle 同步进 android/assets —— 手机端走热更拿新包，
   而**以后新打的 APK 内置资源也不会落后**（内置版是热更失效时的兜底）；
6. 只保留最近 3 个 zip，其余清理。

发布即生效：后端无需重启（check 接口每次实时读清单）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
OUT_DIR = PROJECT_ROOT / "backend" / "storage" / "app-updates"
KEEP_ZIPS = 3


def gen_version() -> str:
    return datetime.now().strftime("%Y%m%d%H%M")


def build_frontend(version: str) -> None:
    env = dict(os.environ)
    env["VITE_BUNDLE_VERSION"] = version
    npm = "npm.cmd" if os.name == "nt" else "npm"
    print(f"[1/3] npm run build（VITE_BUNDLE_VERSION={version}）...")
    result = subprocess.run(
        [npm, "run", "build"],
        cwd=str(FRONTEND_DIR),
        env=env,
    )
    if result.returncode != 0:
        sys.exit("前端构建失败，终止发布。")
    if not (DIST_DIR / "index.html").is_file():
        sys.exit("构建产物缺 index.html，终止发布。")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pack_zip(version: str) -> Path:
    print("[2/3] 打包 dist ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = OUT_DIR / f"bundle-{version}.zip"
    file_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(DIST_DIR.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(DIST_DIR).as_posix())
                file_count += 1
    size = zip_path.stat().st_size
    print(f"      {file_count} 个文件 → {zip_path.name}（{size / 1024 / 1024:.1f} MB）")
    return zip_path


def write_manifest(version: str, zip_path: Path, notes: str, min_native: int) -> None:
    print("[3/3] 写 latest.json ...")
    manifest = {
        "version": version,
        "file": zip_path.name,
        "sha256": sha256_of(zip_path),
        "size": zip_path.stat().st_size,
        "min_native_version_code": min_native,
        "notes": notes,
        "published_at": datetime.now().isoformat(timespec="seconds"),
    }
    tmp = OUT_DIR / "latest.json.tmp"
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, OUT_DIR / "latest.json")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def prune_old_zips() -> None:
    zips = sorted(OUT_DIR.glob("bundle-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in zips[KEEP_ZIPS:]:
        old.unlink(missing_ok=True)
        print(f"已清理旧包：{old.name}")


def sync_android_assets() -> None:
    """cap sync：让 android/app/src/main/assets/public 带上最新 bundle。"""
    print("[4/4] npx cap sync（同步最新 bundle 进 android assets，供下次打 APK）...")
    npm = "npx.cmd" if os.name == "nt" else "npx"
    result = subprocess.run([npm, "cap", "sync"], cwd=str(FRONTEND_DIR))
    if result.returncode != 0:
        # 不终止：热更发布已生效，sync 失败只影响「下次打 APK 的内置兜底版本」
        print("⚠️ cap sync 失败 —— 热更不受影响，但下次打 APK 前请手动执行 npx cap sync")


def main() -> None:
    parser = argparse.ArgumentParser(description="发布移动端 Web 热更包")
    parser.add_argument("--notes", default="", help="更新说明（展示给用户可选）")
    parser.add_argument("--min-native", type=int, default=1, help="要求的最低原生壳 versionCode")
    parser.add_argument("--no-build", action="store_true", help="跳过 npm build，直接打包现有 dist")
    args = parser.parse_args()

    version = gen_version()
    if not args.no_build:
        build_frontend(version)
    else:
        if not (DIST_DIR / "index.html").is_file():
            sys.exit("frontend/dist 不存在，先构建或去掉 --no-build。")
        print(f"[1/3] 跳过构建（--no-build），版本号 {version}")
    zip_path = pack_zip(version)
    write_manifest(version, zip_path, args.notes, args.min_native)
    sync_android_assets()
    prune_old_zips()
    print("\n✅ 发布完成。手机端下次启动检查更新时即会拉取（后端无需重启）。")


if __name__ == "__main__":
    main()
