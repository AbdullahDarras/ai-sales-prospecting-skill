#!/usr/bin/env python3
"""نقطة الدخول: python3 sales_cli.py <أمر> ... (انظر SKILL.md).

إن كانت الحزم ناقصة يستخدم البيئة المجهّزة بـbootstrap.py تلقائيًا، أو يشرح الأمر الواحد المطلوب."""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sales_agent.runtime import REQUIRED_MODULES, resolve_runtime, venv_python  # noqa: E402

action, info = resolve_runtime(REQUIRED_MODULES, sys.executable, venv_python(), HERE)
if action == "reexec":
    os.execv(info, [info, str(Path(__file__).resolve()), *sys.argv[1:]])
if action == "missing":
    print(json.dumps({"error": info}, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)

from sales_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
