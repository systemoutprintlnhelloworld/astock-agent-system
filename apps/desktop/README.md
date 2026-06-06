# AStock Desktop Shell

This folder contains the Tauri 2 desktop shell for the modern A-share Agent console.

Prerequisites for the packaged `.exe` path:

- Python 3.10+ with `python -m pip install -e ".[all]"`.
- Node.js/npm for building the static frontend and installing the Tauri CLI package.
- Rust/Cargo from <https://rustup.rs/> for `tauri dev` and `tauri build`.
- Windows: MSVC C++ Build Tools for the final Tauri/Rust build.

Check the local machine first:

```powershell
.\start.bat -Mode desktop-doctor
```

Fully automated release path:

```powershell
# Installs Python/frontend/desktop dependencies, builds the PyInstaller sidecar,
# exports the desktop frontend, runs validation, and builds the Tauri bundle.
.\start.bat -Mode desktop-release -AutoInstallRust
```

The desktop release is designed to build without fetching Google-hosted fonts. The frontend uses local system font fallbacks so locked-down or offline networks do not break the Tauri `beforeBuildCommand`.

If you do not want the script to install Rust/Cargo and Windows C++ build tools automatically, omit `-AutoInstallRust`; the flow will stop with a clear prerequisite message. To validate everything except the final Tauri `.exe` build, use:

```powershell
.\start.bat -Mode desktop-release -SkipDesktopBuild
```

Validation-only path:

```powershell
.\start.bat -Mode delivery-check
```

Development preview:

```powershell
python -m pip install -e ".[all]"
npm --prefix apps/frontend install
Push-Location apps/desktop; npm install; Pop-Location
.\start.bat -Mode desktop-sidecar
.\start.bat -Mode desktop-dev
```

Portable build preparation:

```powershell
Push-Location apps/desktop; npm install; Pop-Location
npm --prefix apps/frontend run build:desktop
.\start.bat -Mode desktop-sidecar
.\start.bat -Mode desktop-build
```

The build creates a PyInstaller sidecar in `apps/desktop/src-tauri/binaries`, including the Windows target-triple name expected by Tauri. Before rebuilding, `start.ps1` stops stale `astock-backend*.exe` and `astock-agent-desktop.exe` processes from this desktop folder, then uses per-process PyInstaller work/spec directories so repeated release runs do not fail on locked `base_library.zip` or sidecar binaries. The repository-root `astock_agent_system` shim also prioritizes `src/astock_agent_system`, which keeps PyInstaller hidden-import discovery aligned with the source package. The final bundle starts the Python FastAPI backend and loads the built frontend from `apps/desktop/dist`. At runtime the desktop shell checks `127.0.0.1:8000..8020`, reuses an existing healthy AStock backend if one is already running, otherwise starts the bundled backend on the first free port. The frontend probes the same range before opening HTTP/WebSocket connections, so a non-AStock process occupying port `8000` no longer blocks the packaged app.

If the desktop window stays on "waiting for WebSocket" while `/api/health` works in a browser, rebuild the backend sidecar and desktop bundle from the current source. The packaged WebView runs under the `tauri.localhost` origin, so the FastAPI adapter must allow that origin for the initial HTTP health probes; otherwise port discovery fails and the WebSocket falls back to the wrong port.

Useful checks:

```powershell
# Probe all possible backend ports.
for ($p=8000; $p -le 8020; $p++) { try { Invoke-RestMethod -Uri ("http://127.0.0.1:$p/api/health") -TimeoutSec 1 } catch {} }

# Rebuild packaged backend and desktop app after backend/API changes.
.\start.bat -Mode desktop-sidecar
.\start.bat -Mode desktop-build
```
