param(
    [ValidateSet("status", "storage", "offline", "online", "bench", "dashboard", "backend", "frontend", "modern-ui", "desktop-doctor", "desktop-bootstrap", "desktop-sidecar", "desktop-dev", "desktop-build", "desktop-release", "delivery-check", "scheduler", "docs")]
    [string]$Mode = "status",
    [string]$Models = "",
    [string]$BenchModel = "",
    [int]$MaxCount = 1,
    [int]$Days = 12,
    [int]$Port = 8501,
    [int]$BackendPort = 8000,
    [switch]$NoDocker,
    [switch]$AutoInstallRust,
    [switch]$SkipTests,
    [switch]$SkipDocs,
    [switch]$SkipDesktopBuild
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Import-LocalEnv {
    $envPath = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        Write-Host "No .env found; using current shell environment and config/config.yaml defaults." -ForegroundColor Yellow
        return
    }

    Get-Content -LiteralPath $envPath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($name) {
            Set-Item -Path ("Env:" + $name) -Value $value
        }
    }
}

function Invoke-AStockCli {
    param([string[]]$CliArgs)
    & python -m astock_agent_system.cli @CliArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Start-Storage {
    if (-not $NoDocker) {
        Write-Step "Starting MongoDB and Redis with Docker Compose"
        docker compose up -d
    }
    Write-Step "Checking MongoDB and Redis"
    Invoke-AStockCli @("storage", "status", "--strict")
}

function Get-PortOccupant {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $connections) {
        return $null
    }

    $connection = $connections | Select-Object -First 1
    $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    $processDetail = $null
    try {
        $processDetail = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction Stop
    }
    catch {
        $processDetail = $null
    }

    [PSCustomObject]@{
        Port = $Port
        ProcessId = $connection.OwningProcess
        ProcessName = if ($process) { $process.ProcessName } elseif ($processDetail) { $processDetail.Name } else { "unknown" }
        State = $connection.State
        Path = if ($processDetail) { $processDetail.ExecutablePath } else { $null }
        CommandLine = if ($processDetail) { $processDetail.CommandLine } else { $null }
    }
}

function Test-IsProjectBackendProcess {
    param([object]$ProcessInfo)

    if (-not $ProcessInfo -or -not $ProcessInfo.CommandLine) {
        return $false
    }

    $commandLine = $ProcessInfo.CommandLine.Replace("/", "\\")
    return $commandLine -match 'uvicorn\s+apps\.backend\.app:app' -or $commandLine -match '-m\s+uvicorn\s+apps\.backend\.app:app'
}

function Test-IsProjectFrontendProcess {
    param(
        [object]$ProcessInfo,
        [string]$FrontendDirectory
    )

    if (-not $ProcessInfo -or -not $ProcessInfo.CommandLine) {
        return $false
    }

    $commandLine = $ProcessInfo.CommandLine.Replace("/", "\\")
    $frontendMatch = $commandLine -match [Regex]::Escape($FrontendDirectory.Replace("/", "\\"))
    $nextMatch = $commandLine -match 'next(\.cmd)?\s+dev' -or $commandLine -match 'next\\dist\\server\\lib\\start-server\.js'
    return $frontendMatch -and $nextMatch
}

function Ensure-PortAvailable {
    param(
        [int]$Port,
        [string]$Purpose
    )

    $occupant = Get-PortOccupant -Port $Port
    if (-not $occupant) {
        return
    }

    Write-Host "Port $Port is already used by $Purpose." -ForegroundColor Yellow
    Write-Host "  PID: $($occupant.ProcessId)" -ForegroundColor Yellow
    Write-Host "  Process: $($occupant.ProcessName)" -ForegroundColor Yellow
    if ($occupant.Path) {
        Write-Host "  Path: $($occupant.Path)" -ForegroundColor Yellow
    }
    if ($occupant.CommandLine) {
        Write-Host "  Command: $($occupant.CommandLine)" -ForegroundColor DarkYellow
    }

    $confirmation = Read-Host "Terminate this process and continue? [y/N]"
    if ($confirmation -notmatch '^(y|yes)$') {
        throw "Startup cancelled because port $Port is occupied."
    }

    Stop-Process -Id $occupant.ProcessId -Force -ErrorAction Stop
    Start-Sleep -Milliseconds 800

    if (Get-PortOccupant -Port $Port) {
        throw "Port $Port is still occupied after trying to stop PID $($occupant.ProcessId)."
    }
}

function Get-NextDevProcesses {
    param([string]$FrontendDirectory)

    $normalizedDirectory = $FrontendDirectory.Replace("/", "\\")
    $escapedDirectory = [Regex]::Escape($normalizedDirectory)

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            if ($_.ProcessId -eq $PID -or -not $_.CommandLine) {
                return $false
            }

            $normalizedCommand = $_.CommandLine.Replace("/", "\\")
            $normalizedCommand -match $escapedDirectory -and
            (
                $normalizedCommand -match 'next(\.cmd)?\s+dev' -or
                $normalizedCommand -match 'next\\dist\\server\\lib\\start-server\.js'
            )
        } |
        ForEach-Object {
            [PSCustomObject]@{
                ProcessId = $_.ProcessId
                ProcessName = $_.Name
                ParentProcessId = $_.ParentProcessId
                Path = $_.ExecutablePath
                CommandLine = $_.CommandLine
            }
        }
}

function Ensure-NoExistingNextDevServer {
    param([string]$FrontendDirectory)

    $processes = @(Get-NextDevProcesses -FrontendDirectory $FrontendDirectory)
    if (-not $processes.Count) {
        return
    }

    Write-Host "Another Next.js dev server is already running for $FrontendDirectory." -ForegroundColor Yellow
    foreach ($process in $processes) {
        Write-Host "  PID: $($process.ProcessId)" -ForegroundColor Yellow
        Write-Host "  Process: $($process.ProcessName)" -ForegroundColor Yellow
        if ($process.Path) {
            Write-Host "  Path: $($process.Path)" -ForegroundColor Yellow
        }
        if ($process.CommandLine) {
            Write-Host "  Command: $($process.CommandLine)" -ForegroundColor DarkYellow
        }
    }

    $confirmation = Read-Host "Terminate these Next.js dev processes and continue? [y/N]"
    if ($confirmation -notmatch '^(y|yes)$') {
        throw "Startup cancelled because another Next.js dev server is already running."
    }

    $processes | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
    }
    Start-Sleep -Milliseconds 1000

    if ((@(Get-NextDevProcesses -FrontendDirectory $FrontendDirectory)).Count -gt 0) {
        throw "A Next.js dev server is still running for $FrontendDirectory after termination."
    }
}

function Wait-ForHttpReady {
    param(
        [string]$Url,
        [string]$ServiceName,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Step "$ServiceName is ready"
                return
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "$ServiceName did not become ready within $TimeoutSeconds seconds: $Url"
}

function Assert-CommandAvailable {
    param(
        [string]$CommandName,
        [string]$InstallHint
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "$CommandName is not available. $InstallHint"
    }
}

function Test-CommandAvailable {
    param([string]$CommandName)
    return [bool](Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Assert-LastCommandSucceeded {
    param([string]$Action)

    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE."
    }
}

function Get-DesktopRoot {
    return (Join-Path $PSScriptRoot "apps/desktop")
}

function Get-DesktopSidecarRoot {
    return (Join-Path (Get-DesktopRoot) "src-tauri/binaries")
}

function Get-DesktopSidecarPath {
    $binaryRoot = Get-DesktopSidecarRoot
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        return (Join-Path $binaryRoot "astock-backend-x86_64-pc-windows-msvc.exe")
    }
    return (Join-Path $binaryRoot "astock-backend")
}

function ConvertTo-NormalizedPathText {
    param([string]$Path)

    if (-not $Path) {
        return ""
    }

    try {
        $fullPath = [System.IO.Path]::GetFullPath($Path)
    }
    catch {
        $fullPath = $Path
    }

    return (($fullPath -replace '^\\\\\?\\', '').ToLowerInvariant())
}

function Stop-ProcessesUsingPath {
    param([string]$Path)

    $targetPath = ConvertTo-NormalizedPathText -Path $Path
    if (-not $targetPath) {
        return
    }

    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and (ConvertTo-NormalizedPathText -Path $_.ExecutablePath) -eq $targetPath
    })

    foreach ($process in $processes) {
        Write-Host "Stopping process using ${Path}: PID $($process.ProcessId) $($process.Name)" -ForegroundColor Yellow
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }

    if ($processes.Count -gt 0) {
        Start-Sleep -Milliseconds 1000
    }
}

function Stop-DesktopBackendProcesses {
    $desktopRoot = ConvertTo-NormalizedPathText -Path (Get-DesktopRoot)
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        if (-not $_.ExecutablePath -or $_.Name -notlike 'astock-backend*.exe') {
            return $false
        }
        $processPath = ConvertTo-NormalizedPathText -Path $_.ExecutablePath
        return $processPath.StartsWith($desktopRoot)
    })

    foreach ($process in $processes) {
        Write-Host "Stopping stale desktop backend sidecar: PID $($process.ProcessId) $($process.ExecutablePath)" -ForegroundColor Yellow
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }

    if ($processes.Count -gt 0) {
        Start-Sleep -Milliseconds 1000
    }
}

function Stop-DesktopShellProcesses {
    $desktopRoot = ConvertTo-NormalizedPathText -Path (Get-DesktopRoot)
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        if (-not $_.ExecutablePath -or $_.Name -ne 'astock-agent-desktop.exe') {
            return $false
        }
        $processPath = ConvertTo-NormalizedPathText -Path $_.ExecutablePath
        return $processPath.StartsWith($desktopRoot)
    })

    foreach ($process in $processes) {
        Write-Host "Stopping stale desktop app before rebuild: PID $($process.ProcessId) $($process.ExecutablePath)" -ForegroundColor Yellow
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }

    if ($processes.Count -gt 0) {
        Start-Sleep -Milliseconds 1000
    }
}

function Copy-FileWithRetry {
    param(
        [string]$Source,
        [string]$Destination,
        [int]$Retries = 5
    )

    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        try {
            Copy-Item -LiteralPath $Source -Destination $Destination -Force -ErrorAction Stop
            return
        }
        catch {
            if ($attempt -eq $Retries) {
                throw
            }
            Write-Host "Copy failed because the target may be locked; retrying after stopping stale sidecars ($attempt/$Retries)." -ForegroundColor Yellow
            Stop-ProcessesUsingPath -Path $Destination
            Stop-DesktopBackendProcesses
            Start-Sleep -Milliseconds (500 * $attempt)
        }
    }
}

function Get-DesktopSmokePort {
    for ($candidatePort = 8123; $candidatePort -le 8140; $candidatePort++) {
        if (-not (Get-NetTCPConnection -LocalPort $candidatePort -ErrorAction SilentlyContinue)) {
            return $candidatePort
        }
    }
    throw "No free localhost port found for desktop sidecar smoke test."
}

function Test-DesktopSidecarBinary {
    $sidecarPath = Get-DesktopSidecarPath
    if (-not (Test-Path -LiteralPath $sidecarPath)) {
        throw "Desktop sidecar smoke test cannot run because the binary does not exist: $sidecarPath"
    }

    $smokePort = Get-DesktopSmokePort
    $stdoutPath = Join-Path ([System.IO.Path]::GetTempPath()) "astock-sidecar-smoke-out.txt"
    $stderrPath = Join-Path ([System.IO.Path]::GetTempPath()) "astock-sidecar-smoke-err.txt"
    Remove-Item -LiteralPath $stdoutPath, $stderrPath -ErrorAction SilentlyContinue

    Write-Step "Smoke testing packaged sidecar on 127.0.0.1:$smokePort"
    $sidecarArgs = @(
        "--host", "127.0.0.1",
        "--port", [string]$smokePort,
        "--project-root", $PSScriptRoot,
        "--log-level", "warning"
    )
    $process = Start-Process -FilePath $sidecarPath -ArgumentList $sidecarArgs -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    try {
        $ready = $false
        $lastError = ""
        $deadline = (Get-Date).AddSeconds(120)
        while ((Get-Date) -lt $deadline) {
            if ($process.HasExited) {
                break
            }
            try {
                $health = Invoke-RestMethod -Uri ("http://127.0.0.1:$smokePort/api/health") -TimeoutSec 2
                if ($health.status -eq "ok") {
                    $ready = $true
                    break
                }
            }
            catch {
                $lastError = $_.Exception.Message
                Start-Sleep -Milliseconds 1000
            }
        }

        if (-not $ready) {
            $exitText = if ($process.HasExited) { [string]$process.ExitCode } else { "running" }
            $stderrText = if (Test-Path -LiteralPath $stderrPath) { (Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue) } else { "" }
            $stdoutText = if (Test-Path -LiteralPath $stdoutPath) { (Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue) } else { "" }
            throw "Packaged sidecar smoke test failed. exited=$($process.HasExited); exit=$exitText; lastError=$lastError; stderr=$stderrText; stdout=$stdoutText"
        }

        $websocket = [System.Net.WebSockets.ClientWebSocket]::new()
        try {
            $websocket.ConnectAsync([Uri]("ws://127.0.0.1:$smokePort/ws/events"), [Threading.CancellationToken]::None).GetAwaiter().GetResult()
            if ($websocket.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
                throw "WebSocket smoke test ended in state $($websocket.State)."
            }
        }
        finally {
            $websocket.Dispose()
        }
    }
    finally {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-DesktopReleaseExecutablePath {
    $releaseRoot = Join-Path (Get-DesktopRoot) "src-tauri/target/release"
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        return (Join-Path $releaseRoot "astock-agent-desktop.exe")
    }
    return (Join-Path $releaseRoot "astock-agent-desktop")
}

function Get-DesktopInstallerArtifacts {
    $installerRoot = Join-Path (Get-DesktopRoot) "src-tauri/target/release/bundle/nsis"
    if (-not (Test-Path -LiteralPath $installerRoot)) {
        return @()
    }
    return @(Get-ChildItem -LiteralPath $installerRoot -Filter "*.exe" -File -ErrorAction SilentlyContinue)
}

function Assert-DesktopReleaseArtifacts {
    $releaseExe = Get-DesktopReleaseExecutablePath
    if (-not (Test-Path -LiteralPath $releaseExe)) {
        throw "Tauri build completed but the desktop executable was not created: $releaseExe"
    }

    Write-Step "Desktop executable ready: $releaseExe"

    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        $installers = @(Get-DesktopInstallerArtifacts)
        if (-not $installers.Count) {
            throw "Tauri build completed but no NSIS installer was created under apps/desktop/src-tauri/target/release/bundle/nsis."
        }

        foreach ($installer in $installers) {
            Write-Step "Desktop installer ready: $($installer.FullName)"
        }
    }
}

function Build-DesktopSidecar {
    Assert-CommandAvailable -CommandName "python" -InstallHint "Install Python 3.10+ and run: python -m pip install -e `".[all]`""
    Write-Step "Building Python FastAPI sidecar with PyInstaller"
    $binaryRoot = Get-DesktopSidecarRoot
    New-Item -ItemType Directory -Force -Path $binaryRoot | Out-Null
    $buildRoot = Join-Path $PSScriptRoot "build/pyinstaller"
    $workRoot = Join-Path $buildRoot ("work-" + $PID)
    $specRoot = Join-Path $buildRoot ("spec-" + $PID)
    New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $specRoot | Out-Null

    Stop-DesktopShellProcesses
    Stop-DesktopBackendProcesses
    Stop-ProcessesUsingPath -Path (Join-Path $binaryRoot "astock-backend.exe")
    Stop-ProcessesUsingPath -Path (Get-DesktopSidecarPath)

    $env:ASTOCK_PROJECT_ROOT = $PSScriptRoot
    $sidecarEntry = Join-Path $PSScriptRoot "apps/backend/sidecar.py"
    $addDataSeparator = [System.IO.Path]::PathSeparator
    $srcPackageData = (Join-Path $PSScriptRoot "src/astock_agent_system") + $addDataSeparator + "src/astock_agent_system"
    $pyinstallerArgs = @(
        "--name", "astock-backend",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--paths", (Join-Path $PSScriptRoot "src"),
        "--paths", "$PSScriptRoot",
        "--distpath", $binaryRoot,
        "--workpath", $workRoot,
        "--specpath", $specRoot,
        "--add-data", $srcPackageData,
        "--collect-submodules", "apps.backend",
        "--collect-submodules", "astock_agent_system",
        "--collect-all", "requests",
        "--collect-all", "certifi",
        "--collect-submodules", "urllib3",
        "--collect-submodules", "charset_normalizer",
        "--collect-submodules", "idna",
        "--hidden-import", "yaml",
        $sidecarEntry
    )
    # Run PyInstaller from src so the real src-layout package wins over the
    # repository-root import shim during hidden-import discovery.
    Push-Location (Join-Path $PSScriptRoot "src")
    try {
        python -m PyInstaller @pyinstallerArgs
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }

    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        $baseExe = Join-Path $binaryRoot "astock-backend.exe"
        $targetExe = Get-DesktopSidecarPath
        if (Test-Path -LiteralPath $baseExe) {
            Copy-FileWithRetry -Source $baseExe -Destination $targetExe
        }
    }
    if (-not (Test-Path -LiteralPath (Get-DesktopSidecarPath))) {
        throw "PyInstaller completed but the expected sidecar binary was not created: $(Get-DesktopSidecarPath)"
    }
    Test-DesktopSidecarBinary
    Write-Step "Desktop sidecar ready: $(Get-DesktopSidecarPath)"
}

function Assert-DesktopPrerequisites {
    Add-CargoBinToPath
    Assert-CommandAvailable -CommandName "node" -InstallHint "Install Node.js before running desktop UI commands."
    Assert-CommandAvailable -CommandName "npm" -InstallHint "Install Node.js/npm before running desktop UI commands."
    Assert-CommandAvailable -CommandName "cargo" -InstallHint "Install Rust from https://rustup.rs/ before running Tauri dev/build."
    Assert-WindowsTauriBuildTools
}

function Invoke-NpmInstallInDirectory {
    param([string]$Directory)

    Assert-CommandAvailable -CommandName "npm" -InstallHint "Install Node.js/npm before running frontend or desktop commands."
    if (-not (Test-Path -LiteralPath (Join-Path $Directory "package.json"))) {
        throw "npm package.json was not found in $Directory"
    }

    Write-Step "Installing npm dependencies in $Directory"
    Push-Location $Directory
    try {
        $nodeModules = Join-Path $Directory "node_modules"
        $packageLock = Join-Path $Directory "package-lock.json"

        if (Test-Path -LiteralPath $packageLock) {
            npm ci --no-audit --no-fund
            if ($LASTEXITCODE -eq 0) {
                return
            }
            Write-Host "npm ci failed in $Directory; retrying npm install." -ForegroundColor Yellow
        }

        npm install --no-audit --no-fund
        if ($LASTEXITCODE -eq 0) {
            return
        }

        Write-Host "npm install failed in $Directory; retrying with legacy peer dependency resolution." -ForegroundColor Yellow
        npm install --legacy-peer-deps --no-audit --no-fund
        if ($LASTEXITCODE -eq 0) {
            return
        }

        if (Test-Path -LiteralPath $nodeModules) {
            Write-Host "npm install still failed in $Directory, but node_modules already exists; continuing and letting the following build/lint step validate dependency completeness." -ForegroundColor Yellow
            return
        }

        Assert-LastCommandSucceeded -Action "npm install in $Directory"
    }
    finally {
        Pop-Location
    }
}

function Build-DesktopFrontend {
    Assert-CommandAvailable -CommandName "npm" -InstallHint "Install Node.js/npm before building frontend assets."
    Write-Step "Building desktop frontend assets"
    npm --prefix apps/frontend run build:desktop
    Assert-LastCommandSucceeded -Action "Desktop frontend build"
}

function Get-CargoBinPath {
    if ($env:CARGO_HOME) {
        return (Join-Path $env:CARGO_HOME "bin")
    }
    return (Join-Path (Join-Path $env:USERPROFILE ".cargo") "bin")
}

function Add-CargoBinToPath {
    $cargoBin = Get-CargoBinPath
    if ((Test-Path -LiteralPath $cargoBin) -and ($env:Path -notlike "*$cargoBin*")) {
        $env:Path = "$cargoBin;$env:Path"
    }
}

function Get-LocalRustExecutable {
    param([string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $extension = if ($IsWindows -or $env:OS -eq "Windows_NT") { ".exe" } else { "" }
    $localPath = Join-Path (Get-CargoBinPath) "$Name$extension"
    if (Test-Path -LiteralPath $localPath) {
        return $localPath
    }
    return $null
}

function Test-RustToolchainAvailable {
    Add-CargoBinToPath
    $cargo = Get-LocalRustExecutable -Name "cargo"
    if (-not $cargo) {
        return $false
    }

    try {
        & $cargo --version | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Install-RustToolchainIfMissing {
    Add-CargoBinToPath
    if (Test-RustToolchainAvailable) {
        return
    }

    if (-not $AutoInstallRust) {
        throw "cargo is not available. Re-run with -AutoInstallRust to install Rust automatically, or install Rust from https://rustup.rs/."
    }

    Write-Step "Installing Rust toolchain for Tauri build"
    $rustup = Get-LocalRustExecutable -Name "rustup"
    if (-not $rustup) {
        $toolsDir = Join-Path $PSScriptRoot "build/tools"
        New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
        $installer = Join-Path $toolsDir "rustup-init.exe"

        try {
            Invoke-WebRequest -UseBasicParsing -Uri "https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe" -OutFile $installer
            & $installer -y --default-toolchain stable --profile minimal
            Assert-LastCommandSucceeded -Action "rustup-init"
        }
        catch {
            Write-Host "Direct rustup-init installation failed: $($_.Exception.Message)" -ForegroundColor Yellow
            if (-not (Test-CommandAvailable -CommandName "winget")) {
                throw
            }
            Write-Host "Falling back to winget Rustup installation." -ForegroundColor Yellow
            winget install --id Rustlang.Rustup -e --accept-package-agreements --accept-source-agreements
            Assert-LastCommandSucceeded -Action "winget Rustup install"
        }
    }

    Add-CargoBinToPath
    $rustup = Get-LocalRustExecutable -Name "rustup"
    if (-not $rustup) {
        throw "Rustup installation did not finish correctly. Close and reopen PowerShell, then retry."
    }
    & $rustup default stable
    Assert-LastCommandSucceeded -Action "rustup default stable"
    & $rustup target add x86_64-pc-windows-msvc
    Assert-LastCommandSucceeded -Action "rustup target add x86_64-pc-windows-msvc"
    Add-CargoBinToPath
    if (-not (Test-RustToolchainAvailable)) {
        throw "Rust was installed but cargo is not usable. Close and reopen PowerShell, then retry."
    }
}

function Test-WindowsMsvcBuildToolsAvailable {
    if (-not ($IsWindows -or $env:OS -eq "Windows_NT")) {
        return $true
    }

    if (Test-CommandAvailable -CommandName "cl") {
        return $true
    }

    $vswhereCandidates = @()
    $programFilesX86 = ${env:ProgramFiles(x86)}
    if ($programFilesX86) {
        $vswhereCandidates += (Join-Path $programFilesX86 "Microsoft Visual Studio/Installer/vswhere.exe")
    }
    if ($env:ProgramFiles) {
        $vswhereCandidates += (Join-Path $env:ProgramFiles "Microsoft Visual Studio/Installer/vswhere.exe")
    }

    foreach ($vswhere in $vswhereCandidates) {
        if (-not (Test-Path -LiteralPath $vswhere)) {
            continue
        }

        $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
        if ($LASTEXITCODE -eq 0 -and $installPath) {
            return $true
        }
    }

    return $false
}

function Assert-WindowsTauriBuildTools {
    if (-not ($IsWindows -or $env:OS -eq "Windows_NT")) {
        return
    }
    if (Test-WindowsMsvcBuildToolsAvailable) {
        return
    }
    if ($AutoInstallRust) {
        Install-WindowsTauriBuildToolsIfMissing
        if (Test-WindowsMsvcBuildToolsAvailable) {
            return
        }
    }

    $installCommand = 'winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"'
    throw "MSVC C++ Build Tools are not available. Tauri/Rust Windows builds require them. Install them with: $installCommand. Then reopen PowerShell and rerun desktop-release."
}

function Install-WindowsTauriBuildToolsIfMissing {
    if (-not ($IsWindows -or $env:OS -eq "Windows_NT")) {
        return
    }
    if (Test-WindowsMsvcBuildToolsAvailable) {
        return
    }
    if (-not $AutoInstallRust) {
        return
    }

    Assert-CommandAvailable -CommandName "winget" -InstallHint "Install Visual Studio 2022 Build Tools with the C++ workload before running the final Tauri build."
    Write-Step "Installing MSVC C++ Build Tools for Tauri build"
    winget install --id Microsoft.VisualStudio.2022.BuildTools -e --accept-package-agreements --accept-source-agreements --override "--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    Assert-LastCommandSucceeded -Action "Visual Studio Build Tools install"

    if (-not (Test-WindowsMsvcBuildToolsAvailable)) {
        throw "Visual Studio Build Tools installation finished, but the MSVC toolchain is still not visible. Close and reopen PowerShell, then rerun desktop-release."
    }
}

function Invoke-DeliverySecretScan {
    Write-Step "Scanning tracked files for accidental secrets"
    $patterns = @(
        'sk-[A-Za-z0-9_-]{20,}',
        'TUSHARE_TOKEN\s*=\s*(?!your-|""|''''|$)[A-Za-z0-9_-]{20,}',
        'LLM_API_KEY\s*=\s*(?!your-|""|''''|$)[A-Za-z0-9_-]{20,}'
    )
    $excludedPrefixes = @(
        '.venv/',
        'venv/',
        'node_modules/',
        'apps/frontend/node_modules/',
        'apps/desktop/node_modules/',
        'apps/frontend/out/',
        'apps/desktop/dist/',
        'apps/desktop/src-tauri/binaries/',
        'site/',
        'build/',
        'dist/'
    )

    $files = git ls-files
    foreach ($file in $files) {
        $normalized = $file.Replace('\\', '/')
        if ($normalized -eq '.env' -or $normalized -like '.env.*') {
            if ($normalized -notmatch '^\.env\.(example|sample|template)$') {
                throw "Local environment file is tracked: $file"
            }
        }
        if ($excludedPrefixes | Where-Object { $normalized.StartsWith($_) }) {
            continue
        }
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            continue
        }
        $content = Get-Content -LiteralPath $file -Raw -ErrorAction SilentlyContinue
        if ($null -eq $content) {
            continue
        }
        foreach ($pattern in $patterns) {
            if ($content -match $pattern) {
                throw "Potential secret found in tracked file: $file"
            }
        }
    }
    Write-Step "Secret scan passed"
}

function Invoke-DeliveryChecks {
    if (-not $SkipTests) {
        Write-Step "Running Python test suite"
        python -m pytest
        Assert-LastCommandSucceeded -Action "python -m pytest"
    }

    Write-Step "Running frontend lint"
    npm --prefix apps/frontend run lint
    Assert-LastCommandSucceeded -Action "frontend lint"

    if (-not $SkipDocs) {
        Write-Step "Building docs with strict MkDocs"
        python -m mkdocs build --strict
        Assert-LastCommandSucceeded -Action "mkdocs build --strict"
    }

    Write-Step "Checking backend app import"
    python -c "from apps.backend.app import app; print(app.title)"
    Assert-LastCommandSucceeded -Action "backend app import"

    Write-Step "Checking sidecar entrypoint"
    python -m apps.backend.sidecar --help
    Assert-LastCommandSucceeded -Action "sidecar help"

    Write-Step "Checking diff whitespace"
    git diff --check
    Assert-LastCommandSucceeded -Action "git diff --check"

    Invoke-DeliverySecretScan
}

function Invoke-PythonEditableInstall {
    Assert-CommandAvailable -CommandName "python" -InstallHint "Install Python 3.10+ before bootstrapping."
    Write-Step "Installing Python package with all extras"

    # Build isolation forces pip to fetch setuptools/wheel even when they are already
    # installed locally. That makes the release flow brittle on locked-down networks,
    # so prefer the local build environment and only fall back to isolated builds.
    python -m pip install -e ".[all]" --no-build-isolation
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Host "Editable install without build isolation failed; retrying with pip build isolation." -ForegroundColor Yellow
    python -m pip install -e ".[all]"
    Assert-LastCommandSucceeded -Action "python editable install"
}

function Invoke-DesktopBootstrap {
    Assert-CommandAvailable -CommandName "python" -InstallHint "Install Python 3.10+ before bootstrapping."
    Assert-CommandAvailable -CommandName "node" -InstallHint "Install Node.js before bootstrapping."
    Assert-CommandAvailable -CommandName "npm" -InstallHint "Install npm before bootstrapping."

    Invoke-PythonEditableInstall

    Invoke-NpmInstallInDirectory -Directory (Join-Path $PSScriptRoot "apps/frontend")
    Invoke-NpmInstallInDirectory -Directory (Get-DesktopRoot)

    if ($AutoInstallRust) {
        Install-RustToolchainIfMissing
    }
}

function Invoke-DesktopReleaseFlow {
    Write-Step "Starting automated desktop release flow"
    Invoke-DesktopBootstrap
    Build-DesktopSidecar
    Build-DesktopFrontend

    if ($SkipDesktopBuild) {
        Write-Host "Skipping final Tauri build because -SkipDesktopBuild was supplied." -ForegroundColor Yellow
    }
    else {
        Install-RustToolchainIfMissing
        Assert-DesktopPrerequisites
        Write-Step "Building Tauri desktop bundle"
        Push-Location (Get-DesktopRoot)
        try {
            $env:ASTOCK_PROJECT_ROOT = $PSScriptRoot
            npm run build
            Assert-LastCommandSucceeded -Action "Tauri desktop build"
            Assert-DesktopReleaseArtifacts
        }
        finally {
            Pop-Location
        }
    }

    Invoke-DeliveryChecks
    Write-Step "Automated desktop release flow completed"
}

Set-Location $PSScriptRoot
Import-LocalEnv

switch ($Mode) {
    "status" {
        Write-Step "Effective non-secret configuration"
        Invoke-AStockCli @("config")
        Write-Step "Storage health"
        Invoke-AStockCli @("storage", "status")
    }
    "storage" {
        Start-Storage
    }
    "offline" {
        Start-Storage
        Write-Step "Running offline automatic paper-investment round"
        Invoke-AStockCli @("scheduler", "run-auto-investment", "--offline", "--max-count", "$MaxCount", "--days", "$Days")
    }
    "online" {
        Start-Storage
        $selectedModels = $Models
        if (-not $selectedModels) {
            $selectedModels = $env:SCHEDULER_MODELS
        }
        if (-not $selectedModels) {
            $selectedModels = "rule-baseline"
        }
        Write-Step "Running online automatic paper-investment round"
        Invoke-AStockCli @("scheduler", "run-auto-investment", "--models", $selectedModels, "--max-count", "$MaxCount", "--days", "$Days")
    }
    "bench" {
        if ($BenchModel) {
            Write-Step "Running one-model LLM bench"
            Invoke-AStockCli @("bench", "--models", $BenchModel, "--limit", "1")
        } else {
            Write-Step "Listing LLM gateway models"
            Invoke-AStockCli @("bench", "--list-models")
        }
    }
    "dashboard" {
        Ensure-PortAvailable -Port $Port -Purpose "Streamlit dashboard"
        Write-Step "Starting Streamlit dashboard"
        streamlit run src/astock_agent_system/ui/streamlit_app.py --server.port $Port
    }
    "backend" {
        $backendOccupant = Get-PortOccupant -Port $Port
        if (Test-IsProjectBackendProcess -ProcessInfo $backendOccupant) {
            Write-Step "Reusing existing FastAPI backend adapter on port $Port"
            Wait-ForHttpReady -Url "http://127.0.0.1:$Port/api/health" -ServiceName "Backend API" -TimeoutSeconds 30
            break
        }

        Ensure-PortAvailable -Port $Port -Purpose "FastAPI backend adapter"
        Write-Step "Starting FastAPI backend adapter"
        python -m uvicorn apps.backend.app:app --host 127.0.0.1 --port $Port
    }
    "frontend" {
        $frontendDirectory = Join-Path $PSScriptRoot "apps/frontend"
        $frontendOccupant = Get-PortOccupant -Port $Port
        if (Test-IsProjectFrontendProcess -ProcessInfo $frontendOccupant -FrontendDirectory $frontendDirectory) {
            Write-Step "Reusing existing Next.js modern UI on port $Port"
            Wait-ForHttpReady -Url "http://127.0.0.1:$Port" -ServiceName "Frontend UI" -TimeoutSeconds 30
            break
        }

        Ensure-NoExistingNextDevServer -FrontendDirectory $frontendDirectory
        Ensure-PortAvailable -Port $Port -Purpose "Next.js modern UI"
        Write-Step "Starting Next.js modern UI"
        Push-Location $frontendDirectory
        try {
            $desiredBackendUrl = "http://127.0.0.1:$BackendPort"
            if ($env:NEXT_PUBLIC_BACKEND_URL -and $env:NEXT_PUBLIC_BACKEND_URL -ne $desiredBackendUrl) {
                Write-Host "Overriding NEXT_PUBLIC_BACKEND_URL for local modern UI preview: $desiredBackendUrl" -ForegroundColor Yellow
            }
            $env:NEXT_PUBLIC_BACKEND_URL = $desiredBackendUrl
            npx next dev --hostname 127.0.0.1 --port $Port
        }
        finally {
            Pop-Location
        }
    }
    "modern-ui" {
        $frontendDirectory = Join-Path $PSScriptRoot "apps/frontend"
        $backendOccupant = Get-PortOccupant -Port $BackendPort
        $reuseBackend = Test-IsProjectBackendProcess -ProcessInfo $backendOccupant
        $frontendOccupant = Get-PortOccupant -Port $Port
        $reuseFrontend = Test-IsProjectFrontendProcess -ProcessInfo $frontendOccupant -FrontendDirectory $frontendDirectory

        if (-not $reuseFrontend) {
            Ensure-NoExistingNextDevServer -FrontendDirectory $frontendDirectory
        }
        if (-not $reuseBackend) {
            Ensure-PortAvailable -Port $BackendPort -Purpose "FastAPI backend adapter"
        }
        if (-not $reuseFrontend) {
            Ensure-PortAvailable -Port $Port -Purpose "Next.js modern UI"
        }

        $backendScript = Join-Path $PSScriptRoot "start.ps1"
        $backendProcess = $null
        if ($reuseBackend) {
            Write-Step "Reusing existing backend adapter on port $BackendPort"
        }
        else {
            Write-Step "Starting backend sidecar preview in new window"
            $backendProcess = Start-Process powershell -PassThru -ArgumentList @(
                "-NoExit",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "& '$backendScript' -Mode backend -Port $BackendPort"
            )
        }

        Wait-ForHttpReady -Url "http://127.0.0.1:$BackendPort/api/health" -ServiceName "Backend API" -TimeoutSeconds 60

        $frontendProcess = $null
        if ($reuseFrontend) {
            Write-Step "Reusing existing Next.js modern UI on port $Port"
        }
        else {
            Write-Step "Starting Next.js modern UI in new window"
            $frontendProcess = Start-Process powershell -PassThru -ArgumentList @(
                "-NoExit",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "`$env:NEXT_PUBLIC_BACKEND_URL='http://127.0.0.1:$BackendPort'; & '$backendScript' -Mode frontend -Port $Port -BackendPort $BackendPort"
            )
        }

        Wait-ForHttpReady -Url "http://127.0.0.1:$Port" -ServiceName "Frontend UI" -TimeoutSeconds 90

        Write-Step "Modern UI is ready"
        Write-Host "Frontend: http://127.0.0.1:$Port" -ForegroundColor Green
        Write-Host "Backend:  http://127.0.0.1:$BackendPort/api/health" -ForegroundColor Green
        if ($frontendProcess) {
            Write-Host "Frontend window PID: $($frontendProcess.Id)" -ForegroundColor DarkGreen
        }
        if ($backendProcess) {
            Write-Host "Backend window PID:  $($backendProcess.Id)" -ForegroundColor DarkGreen
        }
    }
    "desktop-doctor" {
        Write-Step "Checking desktop packaging prerequisites"
        Add-CargoBinToPath
        foreach ($command in @("node", "npm", "python", "cargo")) {
            $found = Get-Command $command -ErrorAction SilentlyContinue
            if ($found) {
                Write-Host "  OK: $command -> $($found.Source)" -ForegroundColor Green
            }
            else {
                Write-Host "  MISSING: $command" -ForegroundColor Yellow
            }
        }
        if ($IsWindows -or $env:OS -eq "Windows_NT") {
            if (Test-WindowsMsvcBuildToolsAvailable) {
                Write-Host "  OK: MSVC C++ Build Tools for Tauri" -ForegroundColor Green
            }
            else {
                Write-Host "  MISSING: MSVC C++ Build Tools -> install Visual Studio 2022 Build Tools with the C++ workload" -ForegroundColor Yellow
            }
        }
        $sidecarPath = Get-DesktopSidecarPath
        if (Test-Path -LiteralPath $sidecarPath) {
            Write-Host "  OK: sidecar -> $sidecarPath" -ForegroundColor Green
        }
        else {
            Write-Host "  MISSING: sidecar -> run .\start.bat -Mode desktop-sidecar" -ForegroundColor Yellow
        }
        $desktopNodeModules = Join-Path (Get-DesktopRoot) "node_modules"
        if (Test-Path -LiteralPath $desktopNodeModules) {
            Write-Host "  OK: desktop npm dependencies installed" -ForegroundColor Green
        }
        else {
            Write-Host "  MISSING: desktop npm dependencies -> run .\start.bat -Mode desktop-bootstrap" -ForegroundColor Yellow
        }
        $desktopDist = Join-Path (Get-DesktopRoot) "dist/index.html"
        if (Test-Path -LiteralPath $desktopDist) {
            Write-Host "  OK: desktop frontend assets -> $desktopDist" -ForegroundColor Green
        }
        else {
            Write-Host "  MISSING: desktop frontend assets -> run .\start.bat -Mode desktop-release -SkipDesktopBuild" -ForegroundColor Yellow
        }
        Write-Host "  Note: Tauri dev/build requires Rust/Cargo. Use -AutoInstallRust to let this script install Rust automatically." -ForegroundColor Cyan
    }
    "desktop-bootstrap" {
        Invoke-DesktopBootstrap
    }
    "desktop-sidecar" {
        Build-DesktopSidecar
    }
    "desktop-dev" {
        if ($AutoInstallRust) {
            Install-RustToolchainIfMissing
        }
        Assert-DesktopPrerequisites
        if (-not (Test-Path -LiteralPath (Get-DesktopSidecarPath))) {
            Build-DesktopSidecar
        }
        if (-not (Test-Path -LiteralPath (Join-Path (Get-DesktopRoot) "node_modules"))) {
            Invoke-NpmInstallInDirectory -Directory (Get-DesktopRoot)
        }
        $desktopRoot = Get-DesktopRoot
        Write-Step "Starting Tauri desktop dev shell"
        Push-Location $desktopRoot
        try {
            $env:ASTOCK_PROJECT_ROOT = $PSScriptRoot
            npm run dev
        }
        finally {
            Pop-Location
        }
    }
    "desktop-build" {
        if ($AutoInstallRust) {
            Install-RustToolchainIfMissing
        }
        Assert-DesktopPrerequisites
        if (-not (Test-Path -LiteralPath (Join-Path (Get-DesktopRoot) "node_modules"))) {
            Invoke-NpmInstallInDirectory -Directory (Get-DesktopRoot)
        }
        Build-DesktopSidecar
        Build-DesktopFrontend
        Write-Step "Building Tauri desktop bundle"
        Push-Location (Get-DesktopRoot)
        try {
            $env:ASTOCK_PROJECT_ROOT = $PSScriptRoot
            npm run build
            Assert-LastCommandSucceeded -Action "Tauri desktop build"
            Assert-DesktopReleaseArtifacts
        }
        finally {
            Pop-Location
        }
    }
    "desktop-release" {
        Invoke-DesktopReleaseFlow
    }
    "delivery-check" {
        Invoke-DeliveryChecks
    }
    "scheduler" {
        Write-Step "Starting long-running scheduler"
        Invoke-AStockCli @("scheduler", "start")
    }
    "docs" {
        if (-not (Get-Command mkdocs -ErrorAction SilentlyContinue)) {
            throw "MkDocs is not installed. Run: python -m pip install -e `".[docs]`""
        }
        Write-Step "Starting documentation preview"
        mkdocs serve
    }
}
