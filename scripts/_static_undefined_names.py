# -*- coding: utf-8 -*-
"""静态检查：找出函数体里「加载了但从未绑定」的裸名（未定义局部变量）。

用途：定位 rollback_remove_parcel 里 previous_result_status 这类
「从兄弟函数里复制代码、忘了搬变量定义」的确定性 NameError。
"""
import ast
import builtins
import sys
from pathlib import Path

TARGETS = [
    (r"E:\Work\RurallandContractExtension\backend\app\services\survey\parcel_ops.py",
     ["rollback_remove_parcel", "remove_parcel"]),
    (r"E:\Work\RurallandContractExtension\backend\app\services\survey\household.py",
     ["rollback_deregistered_contractor", "rollback_split_household", "rollback_merge_household"]),
    (r"E:\Work\RurallandContractExtension\backend\app\services\survey\changes.py",
     ["_rebuild_diffs", "_collect_diff_rebuild_uids"]),
    (r"E:\Work\RurallandContractExtension\backend\app\services\survey\result.py",
     ["update_result"]),
]


def module_level_names(tree):
    """只看模块顶层（含类顶层属性），**不能** ast.walk 整棵树，
    否则会把各个函数体内的赋值误当成模块级名字，检查就永远通不过。"""
    names = set(dir(builtins)) | {"self", "__class__"}

    def collect_from_body(body):
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
                if isinstance(node, ast.ClassDef):
                    collect_from_body(node.body)
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    for n in ast.walk(tgt):
                        if isinstance(n, ast.Name):
                            names.add(n.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, (ast.If, ast.Try, ast.For, ast.While, ast.With)):
                collect_from_body(getattr(node, "body", []) or [])
                collect_from_body(getattr(node, "orelse", []) or [])
                collect_from_body(getattr(node, "finalbody", []) or [])
                for handler in getattr(node, "handlers", []) or []:
                    collect_from_body(handler.body)

    collect_from_body(tree.body)
    return names


def bound_in_func(fn):
    """函数内所有会产生绑定的名字（赋值/参数/for/with/comprehension/嵌套def/except/global-nonlocal）。"""
    bound = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            bound.update(node.names)
    return bound


def loaded_in_func(fn):
    loads = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loads.setdefault(node.id, node.lineno)
    return loads


def main():
    total = 0
    for path, funcs in TARGETS:
        p = Path(path)
        if not p.exists():
            print(f"[SKIP] {path} 不存在")
            continue
        tree = ast.parse(p.read_text(encoding="utf-8-sig"))
        mod_names = module_level_names(tree)
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in funcs]:
            bound = bound_in_func(fn) | mod_names
            suspicious = {
                name: line for name, line in loaded_in_func(fn).items() if name not in bound
            }
            if suspicious:
                total += len(suspicious)
                print(f"[FAIL] {p.name}::{fn.name}  未定义引用：")
                for name, line in sorted(suspicious.items(), key=lambda kv: kv[1]):
                    print(f"        L{line}  {name}")
            else:
                print(f"[ OK ] {p.name}::{fn.name}")
    print(f"\n合计可疑未定义引用：{total} 处")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
