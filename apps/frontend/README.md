# AStock Modern Frontend

This is the Next.js / React control console for the AStock Agent desktop and modern UI preview.

## Development preview

Prefer the repository launcher so the FastAPI backend URL is injected consistently:

```powershell
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080
```

If you run the frontend directly, start it from this folder:

```powershell
npm run dev
```

`npm run dev` intentionally uses `next dev --webpack`. Next 16's Turbopack dev server can panic on Windows when its local persistence cache is corrupted, with errors such as `range start index ... out of range`. To reproduce or investigate Turbopack specifically, use:

```powershell
npm run dev:turbo
```

The default backend URL is `http://127.0.0.1:18080`. Override it when needed:

```powershell
$env:NEXT_PUBLIC_BACKEND_URL = "http://127.0.0.1:18080"
npm run dev
```

## Desktop build

```powershell
npm run build:desktop
```

This exports the static frontend and copies it to `apps/desktop/dist` for the Tauri shell.
