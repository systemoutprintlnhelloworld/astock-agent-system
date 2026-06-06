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

The build creates a PyInstaller sidecar in `apps/desktop/src-tauri/binaries`, including the Windows target-triple name expected by Tauri. The final bundle starts the Python FastAPI backend as a Tauri sidecar and loads the built frontend from `apps/desktop/dist`.
