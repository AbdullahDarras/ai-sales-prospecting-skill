"""تجهيز بيئة التشغيل بدون تدخل المستخدم: بيئة Python معزولة خارج مجلد المهارة.

لا يعتمد هذا الملف على أي حزمة خارجية (يُستورد قبل التحقق من توفرها).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REQUIRED_MODULES = ["yaml", "openpyxl"]


class BootstrapError(Exception):
    pass


def venv_dir() -> Path:
    override = os.environ.get("SALES_VENV")
    return Path(override) if override else Path.home() / ".sales-prospecting" / "venv"


def venv_python(venv: Path | None = None) -> Path:
    venv = venv or venv_dir()
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def missing_modules(names: list[str]) -> list[str]:
    return [n for n in names if importlib.util.find_spec(n) is None]


def bootstrap_hint(script_dir: Path) -> str:
    return f"python3 {script_dir / 'bootstrap.py'}"


def resolve_runtime(required: list[str], current_python: str, venv_py: Path,
                    script_dir: Path | None = None) -> tuple[str, str]:
    """يعيد ('ok','') أو ('reexec', مسار بايثون البيئة) أو ('missing', رسالة)."""
    missing = missing_modules(required)
    if not missing:
        return "ok", ""
    if venv_py.exists() and Path(current_python) != venv_py:
        return "reexec", str(venv_py)
    hint = bootstrap_hint(script_dir or Path(__file__).resolve().parents[1])
    return "missing", ("حزم بايثون ناقصة: " + ", ".join(missing) +
                       f". جهّزها بأمر واحد (مرة واحدة): {hint}")


def bootstrap(requirements: Path, venv: Path, run=subprocess.run) -> str:
    """ينشئ البيئة المعزولة ويثبّت المتطلبات. يعيد مسار بايثون البيئة."""
    made = run([sys.executable, "-m", "venv", str(venv)], capture_output=True, text=True)
    if made.returncode != 0:
        raise BootstrapError(f"تعذّر إنشاء البيئة: {getattr(made, 'stderr', '')}")
    py = venv_python(venv)
    if not py.exists():
        raise BootstrapError(f"لم تُنشأ البيئة كما يجب ({py})")
    installed = run([str(py), "-m", "pip", "install", "-r", str(requirements)], capture_output=True, text=True)
    if installed.returncode != 0:
        raise BootstrapError(f"تعذّر تثبيت المتطلبات (هل الإنترنت متاح؟): {getattr(installed, 'stderr', '')[-400:]}")
    return str(py)
