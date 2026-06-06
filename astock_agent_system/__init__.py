"""Local src-layout import shim.

This lets `python -m astock_agent_system.cli` work from the repository root
before the package is installed in editable mode.
"""

from __future__ import annotations

from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "astock_agent_system"
if _SRC_PACKAGE.exists():
    src_package_path = str(_SRC_PACKAGE)
    if src_package_path not in __path__:
        __path__.insert(0, src_package_path)

__version__ = "0.1.0"
