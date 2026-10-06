# -*- coding: utf-8 -*-
"""
热更接口离线验收（不触库、不跑 lifespan，TestClient 直接打路由）。

验证四件事：
1. 未发布清单（latest.json 缺失/损坏）→ check 返回 action=none，download 404；
2. 发布清单后：bundle_version 旧 → action=web 且字段齐全；版本一致 → none；
3. download 返回 zip 且与清单 sha256 一致、文件名目录穿越被拒；
4. license 失效场景模拟：路由在 LicenseCheckMiddleware 白名单里（前缀断言）。

用法：runtime/windows/python/python.exe scripts/_verify_app_updates_api.py
"""

import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.license.middleware import LicenseCheckMiddleware  # noqa: E402
from app.main import app  # noqa: E402

UPDATES_DIR = PROJECT_ROOT / "backend" / "storage" / "app-updates"
MANIFEST = UPDATES_DIR / "latest.json"

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  {detail}")


def backup_manifest():
    if MANIFEST.exists():
        return MANIFEST.read_bytes()
    return None


def restore_manifest(backup):
    if backup is None:
        MANIFEST.unlink(missing_ok=True)
    else:
        MANIFEST.write_bytes(backup)


def write_manifest(payload: dict) -> None:
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    backup = backup_manifest()
    zip_path = UPDATES_DIR / "bundle-test.zip"
    try:
        client = TestClient(app)  # 不用 with：不触发 lifespan，不连数据库

        print("\n[1] 白名单（license 失效时也应可检查更新）")
        whitelist = LicenseCheckMiddleware._API_WHITELIST
        check("/api/v1/app-updates 在白名单", "/api/v1/app-updates" in whitelist, str(whitelist))

        print("\n[2] 无清单时")
        MANIFEST.unlink(missing_ok=True)
        r = client.get("/api/v1/app-updates/check")
        check("check 200", r.status_code == 200, r.text)
        body = r.json().get("data", {})
        check("action=none", body.get("action") == "none", r.text)
        r = client.get("/api/v1/app-updates/download")
        check("download 404", r.status_code == 404, str(r.status_code))

        print("\n[3] 清单损坏时")
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text("{broken", encoding="utf-8")
        r = client.get("/api/v1/app-updates/check")
        check("check 不 500，action=none", r.status_code == 200 and r.json()["data"]["action"] == "none", r.text)

        print("\n[4] 已发布清单")
        UPDATES_DIR.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(b"PK\x03\x04 fake zip for verify")
        real_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        write_manifest(
            {
                "version": "202609291800",
                "file": "bundle-test.zip",
                "sha256": real_sha,
                "size": zip_path.stat().st_size,
                "min_native_version_code": 2,
                "notes": "verify",
                "published_at": "2026-09-29T18:00:00",
            }
        )

        r = client.get(
            "/api/v1/app-updates/check",
            params={"bundle_version": "202609291759", "native_version_code": 2},
        )
        data = r.json().get("data", {})
        check("旧版本 → action=web", data.get("action") == "web", r.text)
        bundle = data.get("bundle") or {}
        check("bundle.version", bundle.get("version") == "202609291800", str(bundle))
        check("bundle.sha256", bundle.get("sha256") == real_sha, str(bundle))
        check("bundle.min_native_version_code", bundle.get("min_native_version_code") == 2, str(bundle))

        r = client.get("/api/v1/app-updates/check", params={"bundle_version": "202609291800"})
        check("同版本 → action=none", r.json().get("data", {}).get("action") == "none", r.text)

        r = client.get("/api/v1/app-updates/download")
        check("download 200", r.status_code == 200, str(r.status_code))
        check(
            "sha256 与清单一致",
            hashlib.sha256(r.content).hexdigest() == real_sha,
        )
        check("X-Bundle-Version 头", r.headers.get("x-bundle-version") == "202609291800", str(dict(r.headers)))

        print("\n[5] 目录穿越防护")
        write_manifest(
            {
                "version": "evil",
                "file": "../evil.zip",
                "sha256": "x",
                "size": 1,
                "min_native_version_code": 0,
                "notes": "",
                "published_at": "",
            }
        )
        r = client.get("/api/v1/app-updates/download")
        check("穿越路径 404", r.status_code == 404, str(r.status_code))

    finally:
        restore_manifest(backup)
        zip_path.unlink(missing_ok=True)

    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
