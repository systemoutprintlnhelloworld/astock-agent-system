"""Executable entrypoint for the packaged FastAPI sidecar."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _configure_project_root(project_root: str | None) -> Path | None:
    if not project_root:
        return None
    root = Path(project_root).expanduser().resolve()
    os.environ.setdefault("ASTOCK_PROJECT_ROOT", str(root))

    # In a PyInstaller sidecar, prefer bundled Python modules first.  Placing
    # the source tree ahead of the bundle can make imports resolve to local
    # project files while third-party packages remain inside the extracted
    # bundle, which caused packaged runs to miss dependencies such as requests.
    frozen_root = getattr(sys, "_MEIPASS", "")
    if frozen_root:
        frozen_text = str(frozen_root)
        if frozen_text not in sys.path:
            sys.path.insert(0, frozen_text)
        for path in (root, root / "src"):
            text = str(path)
            if text not in sys.path:
                sys.path.append(text)
        return root

    for path in (root, root / "src"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AStock FastAPI backend sidecar.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--project-root", default=os.getenv("ASTOCK_PROJECT_ROOT", ""))
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    _configure_project_root(args.project_root)

    import uvicorn

    from apps.backend.app import app

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
