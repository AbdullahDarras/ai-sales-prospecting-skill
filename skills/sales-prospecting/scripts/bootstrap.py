#!/usr/bin/env python3
"""يجهّز بيئة بايثون معزولة (مرة واحدة) ويثبّت متطلبات المهارة. لا يلمس أي شيء آخر على الجهاز."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sales_agent.runtime import BootstrapError, bootstrap, venv_dir  # noqa: E402

if __name__ == "__main__":
    try:
        py = bootstrap(HERE / "requirements.txt", venv_dir())
    except BootstrapError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"python": py, "venv": str(venv_dir()),
                      "note": "جاهز. شغّل sales_cli.py كالمعتاد، وسيستخدم هذه البيئة تلقائيًا."}, ensure_ascii=False))
