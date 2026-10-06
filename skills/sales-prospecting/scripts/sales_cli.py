#!/usr/bin/env python3
"""نقطة الدخول: python3 sales_cli.py <أمر> ... (انظر SKILL.md)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sales_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
