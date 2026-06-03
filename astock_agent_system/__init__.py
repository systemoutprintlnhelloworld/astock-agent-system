"""Local src-layout import shim.

This lets `python -m astock_agent_system.cli` work from the repository root
before the package is installed in editable mode.
"""

from __future__ import annotations

from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "astock_agent_system"
if _SRC_PACKAGE.exists():
    __path__.append(str(_SRC_PACKAGE))

__version__ = "0.1.0"
