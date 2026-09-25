# -*- coding: utf-8 -*-
"""
授权功能自检脚本

用法（在项目根目录执行）：
    backend\\.venv\\Scripts\\python.exe scripts\\check_license.py

检查内容：
1. 当前机器码
2. backend/storage/license.dat 的授权状态
3. 缓存失效回归测试：授权文件被改名/删除后，下一次校验是否立即失效；
   恢复文件后是否立即重新生效（无需重启后端、无需调用 /license/reload）
"""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.core.license.license_validator import LicenseValidator, LICENSE_FILE_PATH  # noqa: E402
from app.core.license.machine_fingerprint import get_machine_fingerprint  # noqa: E402

results = []


def check(name: str, actual, expected) -> None:
    ok = actual == expected
    results.append(ok)
    print("  [%s] %-46s 期望=%-14s 实际=%s" % ("PASS" if ok else "FAIL", name, expected, actual))


def main() -> int:
    print("=" * 78)
    print("授权功能自检")
    print("=" * 78)
    print("授权文件路径:", LICENSE_FILE_PATH)
    print("当前机器码  :", get_machine_fingerprint())
    print()

    # ---------- 1. 真实授权文件状态 ----------
    print("[1] 当前授权状态")
    validator = LicenseValidator()
    result = validator.validate(force=True)
    print("  状态:", result.status.value)
    print("  说明:", result.error_message or "-")
    if result.license_info:
        info = result.license_info
        print("  区域:", info.region_name, info.region_code)
        print("  签发:", info.issued_at)
        print("  到期:", info.expires_at or "永久")
        print("  功能:", info.features)
    print()

    if result.status.value != "valid":
        print("! 当前授权无效，跳过缓存失效回归测试（请先放入有效授权文件）")
        return 0

    # ---------- 2. 缓存失效回归测试 ----------
    print("[2] 缓存失效回归测试（在临时目录中操作，不影响真实授权文件）")
    tmp = Path(tempfile.mkdtemp(prefix="lic_check_"))
    target = tmp / "license.dat"
    renamed = tmp / "license1.dat"
    shutil.copy2(LICENSE_FILE_PATH, target)

    v = LicenseValidator(target)

    check("首次校验", v.validate().status.value, "valid")
    check("重复校验（命中缓存，结果不变）", v.validate().status.value, "valid")

    target.rename(renamed)
    check("文件改名后立即校验（修复前会误报 valid）", v.validate().status.value, "not_found")

    shutil.move(str(renamed), str(target))
    check("文件恢复后立即校验", v.validate().status.value, "valid")

    data = bytearray(target.read_bytes())
    data[20] ^= 0x01
    target.write_bytes(bytes(data))
    check("文件被篡改后立即校验", v.validate().status.value, "tampered")

    target.unlink()
    check("文件删除后立即校验", v.validate().status.value, "not_found")

    shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 78)
    failed = results.count(False)
    print("结果: %d 项通过, %d 项失败" % (results.count(True), failed))
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
