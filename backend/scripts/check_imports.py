"""
check_imports.py — Chặn lỗi `UnboundLocalError` do import cục bộ che module import.
===================================================================================

BỐI CẢNH (vì sao có file này):
    Ngày 2026-07-11 backend crash ngầm giữa lúc render với lỗi:

        File "backend/main.py", line 338, in _run_pipeline
            shutil.rmtree(job_dir_audio, ignore_errors=True)
        UnboundLocalError: cannot access local variable 'shutil'

    Nguyên nhân KHÔNG phải thiếu `import shutil` — module đã import ở đầu file.
    Nguyên nhân là trong CÙNG hàm đó có thêm một `import shutil` cục bộ nằm PHÍA
    DƯỚI. Quy tắc scoping của Python: một tên được gán (kể cả bằng `import`) ở bất
    kỳ đâu trong hàm thì nó là biến CỤC BỘ của TOÀN BỘ hàm. Mọi lần đọc tên đó
    trước dòng import sẽ ném UnboundLocalError.

    Lỗi này đặc biệt nguy hiểm vì:
      - `python -m py_compile` KHÔNG bắt được (cú pháp hoàn toàn hợp lệ).
      - `ruff --select F821` KHÔNG bắt được (tên có được import, chỉ sai thứ tự).
      - Nó chỉ nổ lúc RUNTIME, ở đúng nhánh code hiếm khi chạy (dọn file tạm sau
        khi render xong) — nên lọt qua mọi lần test thủ công.

CÁCH DÙNG:
    python backend/scripts/check_imports.py              # quét mặc định
    python backend/scripts/check_imports.py <path> ...   # quét đường dẫn chỉ định

    Exit code 0 = sạch, 1 = phát hiện rủi ro (dùng được trong CI / pre-commit).
"""

from __future__ import annotations

import ast
import os
import sys

# Thư mục bỏ qua khi quét đệ quy
SKIP_DIRS = {"venv", "__pycache__", "node_modules", ".git", "test_workspace"}


def _own_scope_nodes(fn: ast.AST):
    """Duyệt thân hàm nhưng KHÔNG chui vào hàm/lambda/class lồng nhau.

    Cần thiết vì hàm lồng nhau có scope riêng — một `import` trong hàm con không
    ràng buộc tên ở hàm cha, và ngược lại.
    """
    for stmt in fn.body:
        stack = [stmt]
        while stack:
            node = stack.pop()
            yield node
            for child in ast.iter_child_nodes(node):
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef),
                ):
                    continue
                stack.append(child)


def analyze(path: str) -> list[tuple]:
    """Trả về danh sách (dòng_dùng, tên, tên_hàm, dòng_import, loại)."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src, filename=path)

    module_imports = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                module_imports.add((alias.asname or alias.name).split(".")[0])

    problems = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nodes = list(_own_scope_nodes(fn))

        # Gom import cục bộ. PHẢI lấy dòng NHỎ NHẤT: nếu một tên được import nhiều
        # lần trong cùng hàm thì lần SỚM NHẤT mới là lần bind. So với dòng import
        # muộn hơn sẽ báo động giả (ast.walk không đảm bảo thứ tự dòng).
        local_imports: dict[str, int] = {}
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    name = (alias.asname or alias.name).split(".")[0]
                    if name not in local_imports or node.lineno < local_imports[name]:
                        local_imports[name] = node.lineno

        for node in nodes:
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                imp_line = local_imports.get(node.id)
                if imp_line is not None and node.lineno < imp_line:
                    kind = "CHE module import" if node.id in module_imports else "chỉ có cục bộ"
                    problems.append((node.lineno, node.id, fn.name, imp_line, kind))
    return problems


def collect_files(roots: list[str]) -> list[str]:
    files: list[str] = []
    for root in roots:
        if os.path.isfile(root):
            files.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            files += [
                os.path.join(dirpath, fn) for fn in filenames if fn.endswith(".py")
            ]
    return sorted(set(files))


def main() -> int:
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    roots = sys.argv[1:] or [
        os.path.join(backend_dir, "main.py"),
        os.path.join(backend_dir, "config.py"),
        os.path.join(backend_dir, "services"),
    ]

    total = 0
    for path in collect_files(roots):
        try:
            problems = analyze(path)
        except SyntaxError as err:
            print(f"[LOI CU PHAP] {path}: {err}")
            total += 1
            continue
        for lineno, name, fname, imp_line, kind in sorted(problems):
            total += 1
            rel = os.path.relpath(path, backend_dir)
            print(
                f"{rel}:{lineno}  '{name}' duoc DUNG truoc 'import {name}' "
                f"(dong {imp_line}) trong ham {fname}()  [{kind}]"
            )

    if total:
        print(f"\n[THAT BAI] {total} vi tri co nguy co UnboundLocalError luc runtime.")
        print("Cach sua: dua import len dau file (module level) va XOA import cuc bo.")
        return 1

    print("[OK] Khong co nguy co UnboundLocalError do import cuc bo che module import.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
