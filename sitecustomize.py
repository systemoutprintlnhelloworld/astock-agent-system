"""Allow running the src-layout package without an editable install.

This keeps local commands such as `python -m astock_agent_system.cli` working
from the repository root on Windows PowerShell.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.exists():
    src_path = str(SRC_DIR)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
