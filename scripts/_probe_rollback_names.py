# -*- coding: utf-8 -*-
"""编译级证据：把 rollback_* 函数的字节码名字表摊开。

原理：CPython 编译时就把每个名字归好类——
  - 以「局部变量」方式访问  -> 出现在 co_varnames
  - 以「全局/内置」方式访问 -> 出现在 co_names（运行时去 globals()/builtins 找）
若一个名字既不在 co_varnames、也不在模块 globals、也不是内置，
那它就是运行时必然 NameError 的「未定义引用」。

跑法：runtime/windows/python/python.exe scripts/_probe_rollback_names.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    env_path = ROOT / "runtime" / ".state" / "runtime.env"
    if not env_path.exists():
        return data
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


for _k, _v in load_env().items():
    os.environ.setdefault(_k, _v)
os.environ.setdefault("SECRET_KEY", "probe-only")

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import builtins  # noqa: E402
import importlib  # noqa: E402

TARGETS = [
    ("app.services.survey.parcel_ops", "SurveyServiceParcelOpsMixin", "rollback_remove_parcel"),
    ("app.services.survey.parcel_ops", "SurveyServiceParcelOpsMixin", "rollback_split_parcel"),
    ("app.services.survey.parcel_ops", "SurveyServiceParcelOpsMixin", "rollback_swap_parcels"),
    ("app.services.survey.household", "SurveyServiceHouseholdMixin", "rollback_deregistered_contractor"),
]

bad_total = 0
for mod_name, cls_name, fn_name in TARGETS:
    try:
        module = importlib.import_module(mod_name)
    except Exception as exc:  # noqa: BLE001
        print(f"[SKIP] {mod_name} 导入失败：{type(exc).__name__}: {exc}")
        continue
    cls = getattr(module, cls_name, None)
    if cls is None:
        print(f"[SKIP] {mod_name}.{cls_name} 不存在")
        continue
    fn = getattr(cls, fn_name, None)
    if fn is None:
        print(f"[SKIP] {cls_name}.{fn_name} 不存在")
        continue

    code = fn.__code__
    var_names = set(code.co_varnames) | set(code.co_freevars) | set(code.co_cellvars)
    module_globals = set(vars(module)) | set(dir(builtins))
    # 只在函数体内被当作全局名查找、且模块里也没有的名字 —— 运行时必炸
    unresolved = sorted(n for n in code.co_names if n not in module_globals)

    print(f"\n=== {cls_name}.{fn_name} (L{code.co_firstlineno}) ===")
    print(f"  co_varnames : {sorted(code.co_varnames)}")
    if unresolved:
        bad_total += len(unresolved)
        print(f"  [!] 运行时必然 NameError 的引用：{unresolved}")
    else:
        print("  [OK] 无未定义引用")

print(f"\n合计未定义引用：{bad_total} 处")
sys.exit(1 if bad_total else 0)
