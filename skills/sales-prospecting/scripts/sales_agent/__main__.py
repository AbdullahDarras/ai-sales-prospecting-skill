"""python -m sales_agent <أمر>: مرادف لـ sales_cli.py."""

from __future__ import annotations
import sys

from .cli import main

sys.exit(main())
