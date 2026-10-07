"""ماك جديد يأتي غالبًا بـPython 3.9. صيغة `X | None` بالتعليقات تنكسر عليه عند التنفيذ، إلا مع
`from __future__ import annotations`. ومكتبات تقرأ التعليقات وقت التشغيل (FastAPI/pydantic) تحتاج Optional/Union صريحة."""
import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "skills" / "sales-prospecting" / "scripts"
FILES = sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)
RUNTIME_ANNOTATION_MODULES = {"app.py"}   # pydantic/FastAPI تقيّم التعليقات فعليًا


def has_future(tree):
    return any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names)
               for n in tree.body)


def annotation_nodes(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.AnnAssign):
            yield n.annotation
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = n.args
            for a in args.posonlyargs + args.args + args.kwonlyargs + [x for x in (args.vararg, args.kwarg) if x]:
                if a.annotation:
                    yield a.annotation
            if n.returns:
                yield n.returns


def uses_pipe(node):
    return any(isinstance(x, ast.BinOp) and isinstance(x.op, ast.BitOr) for x in ast.walk(node))


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(PKG)))
def test_module_is_safe_on_python_39(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    piped = any(uses_pipe(a) for a in annotation_nodes(tree))
    if path.name in RUNTIME_ANNOTATION_MODULES:
        assert not piped, "استخدم Optional/Union: FastAPI وpydantic تقيّمان التعليقات وقت التشغيل"
    elif piped:
        assert has_future(tree), "أضف: from __future__ import annotations"


def test_no_python_310_only_statements():
    match_node = getattr(ast, "Match", None)       # غير موجود أصلًا على 3.9
    if match_node is None:
        return
    for path in FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(isinstance(n, match_node) for n in ast.walk(tree)), path
